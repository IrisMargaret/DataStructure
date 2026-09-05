package com.academic.search;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.MimeTypeMap;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.content.FileProvider;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;

/**
 * Academic paper search engine - Android shell.
 *
 * Startup flow:
 * 1. First run: unpack assets/academic into filesDir/academic (data root);
 * 2. Background thread: Chaquopy starts CPython -> mobile_server.start(dataRoot, port)
 *    launches the Flask app inside the APK;
 * 3. While the server boots, a local "starting..." page is shown instead of a blank
 *    WebView; once /api/meta answers 200 the real home page is loaded.
 * 4. On failure the exception text is rendered on screen (plus logcat + log file)
 *    so problems are visible instead of an endless white screen.
 *
 * Link policy:
 * - Local pages/APIs stay inside the WebView;
 * - External links (arXiv/DOI) open in the system browser;
 * - target=_blank new windows are bridged with the same rules;
 * - Paper file URLs (local /api/papers/.../file) are downloaded to cacheDir
 *   and opened via FileProvider with the system viewer.
 */
public class MainActivity extends Activity {

    private static final String TAG = "AcademicSearch";
    private static final String ASSET_ROOT = "academic";
    private static final int PORT = 8765;
    private static final String BASE_URL = "http://127.0.0.1:" + PORT;
    private static final int REQ_FILE_CHOOSER = 1001;
    // First boot unpacks the embedded Python runtime and builds the paper index;
    // give it plenty of time on slow devices.
    private static final long SERVER_TIMEOUT_MS = 180_000;

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        configureWebView();
        FrameLayout content = new FrameLayout(this);
        content.addView(webView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(content);
        applySystemBarInsets(content);

        ensurePermissions();

        // Show a local status page immediately instead of a blank screen.
        webView.loadDataWithBaseURL(null, startingHtml(),
                "text/html", "utf-8", null);

        new Thread(() -> {
            File dataRoot = null;
            try {
                dataRoot = extractAssetsIfNeeded();
                Log.i(TAG, "data root ready: " + dataRoot);
                startPython(dataRoot);
                Log.i(TAG, "python started, waiting for server");
                waitForServer();
                Log.i(TAG, "server ready, loading home page");
                ui.post(() -> webView.loadUrl(BASE_URL + "/"));
            } catch (Throwable e) {
                Log.e(TAG, "startup failed", e);
                String msg = describe(e);
                writeLogFile(dataRoot, msg);
                ui.post(() -> {
                    webView.loadDataWithBaseURL(null, errorHtml(msg),
                            "text/html", "utf-8", null);
                    Toast.makeText(MainActivity.this,
                            "启动失败: " + msg, Toast.LENGTH_LONG).show();
                });
            }
        }, "server-bootstrap").start();
    }

    // ---------------- Permissions ----------------

    private void ensurePermissions() {
        // INTERNET is a normal permission; request is harmless for old devices.
        if (Build.VERSION.SDK_INT >= 33) return;
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.INTERNET)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.INTERNET}, 200);
        }
    }

    // ---------------- Asset unpacking ----------------

    /** Bump when the unpack layout changes so stale/legacy data is refreshed. */
    private static final String UNPACK_MARKER = ".unpacked-v3";

    /**
     * Unpack assets/academic to private dir.
     * A marker file guards against legacy/corrupted layouts (e.g. v1 unpacked
     * data files as directories); if the marker is missing the whole tree is
     * wiped and re-unpacked.
     */
    private File extractAssetsIfNeeded() {
        File target = new File(getFilesDir(), ASSET_ROOT);
        File marker = new File(target, UNPACK_MARKER);
        if (!marker.exists()) {
            // wipe any legacy / partially corrupted layout
            if (target.exists()) {
                deleteRecursively(target);
            }
            target.mkdirs();
            copyAssetTree("academic", target);
            try (FileOutputStream fos = new FileOutputStream(marker)) {
                fos.write(1);
            } catch (Exception e) {
                Log.e(TAG, "cannot write unpack marker", e);
            }
        }
        return target;
    }

    private void deleteRecursively(File f) {
        if (f.isDirectory()) {
            File[] kids = f.listFiles();
            if (kids != null) {
                for (File k : kids) deleteRecursively(k);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }

    /**
     * Recursively copy an assets subtree.
     * assetPath is the assets-relative path; dest is the target file (for a
     * leaf) or the target directory (for a directory in assets). A directory
     * in assets has non-null children; a file has none.
     */
    private void copyAssetTree(String assetPath, File dest) {
        try {
            String[] children = getAssets().list(assetPath);
            boolean isDir = children != null && children.length > 0;
            if (isDir) {
                if (!dest.exists()) dest.mkdirs();
                for (String child : children) {
                    copyAssetTree(assetPath + "/" + child,
                            new File(dest, child));
                }
            } else {
                // leaf file: dest is the final file path
                File parent = dest.getParentFile();
                if (parent != null) parent.mkdirs();
                try (InputStream in = getAssets().open(assetPath);
                     FileOutputStream fos = new FileOutputStream(dest)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) fos.write(buf, 0, n);
                }
            }
        } catch (Exception e) {
            throw new RuntimeException("asset unpack failed: " + assetPath
                    + " -> " + e, e);
        }
    }

    // ---------------- Python / Flask ----------------

    private void startPython(File dataRoot) throws Exception {
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        Python.getInstance().getModule("mobile_server")
                .callAttr("start", dataRoot.getAbsolutePath(), PORT);
    }

    /** Poll /api/meta until Flask is ready. */
    private void waitForServer() throws Exception {
        long deadline = System.currentTimeMillis() + SERVER_TIMEOUT_MS;
        int attempt = 0;
        while (System.currentTimeMillis() < deadline) {
            try {
                HttpURLConnection c = (HttpURLConnection)
                        new URL(BASE_URL + "/api/meta").openConnection();
                c.setConnectTimeout(1500);
                c.setReadTimeout(1500);
                int code = c.getResponseCode();
                c.disconnect();
                if (code == 200) return;
            } catch (Exception ignored) {
                // server not up yet, keep polling
            }
            attempt++;
            if (attempt % 20 == 0) {
                Log.i(TAG, "waiting for server... " + attempt);
            }
            Thread.sleep(500);
        }
        throw new IllegalStateException(
                "Flask not ready within " + (SERVER_TIMEOUT_MS / 1000) + "s");
    }

    // ---------------- 系统栏安全间距 ----------------

    /**
     * 让内容按系统栏 insets 整体避让：用一个 FrameLayout 承载 WebView，
     * 为容器设置状态栏/导航栏内边距。此方案不依赖 WebView 是否支持
     * env(safe-area-inset-*)，兼容各版本与厂商；Android 15+ 强制边到边下
     * 内容不再与系统下拉区/手势区重叠。
     */
    private void applySystemBarInsets(FrameLayout content) {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        ViewCompat.setOnApplyWindowInsetsListener(content, (v, insets) -> {
            androidx.core.graphics.Insets bars = insets.getInsets(
                    WindowInsetsCompat.Type.systemBars());
            v.setPadding(0, bars.top, 0, bars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        content.requestApplyInsets();
    }

    // ---------------- Error surfacing ----------------

    private static String describe(Throwable e) {
        StringWriter sw = new StringWriter();
        e.printStackTrace(new PrintWriter(sw));
        String s = sw.toString();
        return s.length() > 4000 ? s.substring(0, 4000) : s;
    }

    private void writeLogFile(File dataRoot, String msg) {
        try {
            File dir = dataRoot != null ? dataRoot
                    : new File(getFilesDir(), ASSET_ROOT);
            File f = new File(dir, "startup-error.log");
            try (FileOutputStream fos = new FileOutputStream(f, false)) {
                fos.write(msg.getBytes("UTF-8"));
            }
            Log.i(TAG, "error log written to " + f.getAbsolutePath());
        } catch (Exception ex) {
            Log.e(TAG, "cannot write error log", ex);
        }
    }

    private static String startingHtml() {
        return "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                + "<style>body{background:#faf6ee;color:#3a2f1f;font-family:sans-serif;"
                + "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
                + ".box{text-align:center;max-width:80%}"
                + ".spin{width:44px;height:44px;border:5px solid #d8c9a8;"
                + "border-top-color:#8a6d3b;border-radius:50%;margin:0 auto 18px;"
                + "animation:r 1s linear infinite}@keyframes r{to{transform:rotate(360deg)}}"
                + "h2{font-size:18px}p{color:#7a6a4d;font-size:14px;line-height:1.7}"
                + "</style></head><body><div class='box'>"
                + "<div class='spin'></div>"
                + "<h2>正在启动本地检索服务…</h2>"
                + "<p>首次启动需解压内置数据并建立论文索引，<br>"
                + "通常需要 10 秒至 1 分钟，请稍候。</p>"
                + "</div></body></html>";
    }

    private static String errorHtml(String msg) {
        String esc = msg.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace("\n", "<br>");
        return "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                + "<style>body{background:#fdf3f0;color:#5b2a20;font-family:monospace;"
                + "padding:24px;line-height:1.6}h1{font-size:17px}"
                + "pre{background:#fff;border:1px solid #e5c9c0;padding:12px;"
                + "border-radius:6px;white-space:pre-wrap;word-break:break-all;font-size:12px}"
                + "</style></head><body>"
                + "<h1>启动失败</h1>"
                + "<pre>" + esc + "</pre>"
                + "<p>可尝试关闭应用后重新打开；若仍失败，请把上方错误信息反馈给开发者。</p>"
                + "</body></html>";
    }

    // ---------------- WebView ----------------

    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMediaPlaybackRequiresUserGesture(true);
        // support target=_blank: new windows are bridged, see onCreateWindow
        s.setSupportMultipleWindows(true);
        // 响应式页面：以视口宽度渲染，禁用缩放/文本自动放大，
        // 避免不同机型 WebView 自动缩放破坏布局
        s.setUseWideViewPort(false);
        s.setLoadWithOverviewMode(false);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);

        WebViewClient client = new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleLink(url);
            }
        };
        webView.setWebViewClient(client);

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view,
                                             ValueCallback<Uri[]> callback,
                                             FileChooserParams params) {
                filePathCallback = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                try {
                    startActivityForResult(
                            Intent.createChooser(intent, "Choose paper file"), REQ_FILE_CHOOSER);
                } catch (Exception e) {
                    filePathCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public boolean onCreateWindow(WebView view, boolean isDialog,
                                          boolean isUserGesture,
                                          android.os.Message resultMsg) {
                // target=_blank new window: create a hidden WebView to carry the
                // navigation; shouldOverrideUrlLoading decides how to open it.
                WebView newView = new WebView(MainActivity.this);
                WebSettings ns = newView.getSettings();
                ns.setJavaScriptEnabled(true);
                newView.setWebViewClient(new WebViewClient() {
                    @Override
                    public boolean shouldOverrideUrlLoading(WebView v, String url) {
                        return handleLink(url);
                    }
                });
                WebView.WebViewTransport transport =
                        (WebView.WebViewTransport) resultMsg.obj;
                transport.setWebView(newView);
                resultMsg.sendToTarget();
                return true;
            }
        });
    }

    /**
     * Link dispatch:
     * local paper file download -> system viewer;
     * local page -> stay in WebView;
     * external link -> system browser. Returns true when handled.
     */
    private boolean handleLink(String url) {
        if (url == null) return true;
        if (url.startsWith(BASE_URL + "/api/papers/") && url.contains("/file")) {
            downloadAndOpen(url);
            return true;
        }
        if (!url.startsWith(BASE_URL)) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
            } catch (Exception ignored) {
            }
            return true;
        }
        return false; // local page/api: keep in WebView
    }

    /** Download the paper file in background, then open with the system viewer. */
    private void downloadAndOpen(String url) {
        new Thread(() -> {
            File out = null;
            try {
                File dir = new File(getCacheDir(), "downloads");
                dir.mkdirs();
                String name = guessFileName(url);
                out = new File(dir, name);
                HttpURLConnection c = (HttpURLConnection)
                        new URL(url).openConnection();
                c.setConnectTimeout(8000);
                c.setReadTimeout(8000);
                int code = c.getResponseCode();
                if (code != 200) throw new RuntimeException("HTTP " + code);
                try (InputStream in = c.getInputStream();
                     FileOutputStream fos = new FileOutputStream(out)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) fos.write(buf, 0, n);
                }
                c.disconnect();
                File f = out;
                ui.post(() -> openWithSystemViewer(f));
            } catch (Exception e) {
                e.printStackTrace();
                ui.post(() -> Toast.makeText(this,
                        "Download failed: " + e.getMessage(), Toast.LENGTH_LONG).show());
            }
        }, "file-download").start();
    }

    private String guessFileName(String url) {
        String path = url.substring(url.indexOf("/api/"));
        String raw = path.substring(path.lastIndexOf('/') + 1);
        if (raw.contains(".")) return raw;
        return raw + ".pdf"; // fallback: stored originals are mostly PDFs
    }

    private void openWithSystemViewer(File file) {
        try {
            Uri uri = FileProvider.getUriForFile(this,
                    getPackageName() + ".fileprovider", file);
            String mime = MimeTypeMap.getSingleton()
                    .getMimeTypeFromExtension(ext(file.getName()));
            if (mime == null) mime = "application/octet-stream";
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, mime);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            startActivity(intent);
        } catch (Exception e) {
            Toast.makeText(this, "Cannot open file: " + e.getMessage(),
                    Toast.LENGTH_LONG).show();
        }
    }

    private static String ext(String name) {
        int i = name.lastIndexOf('.');
        return i < 0 ? "" : name.substring(i + 1).toLowerCase(Locale.ROOT);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (filePathCallback == null) return;
            Uri[] result = (resultCode == RESULT_OK && data != null)
                    ? new Uri[]{data.getData()} : null;
            filePathCallback.onReceiveValue(result);
            filePathCallback = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
