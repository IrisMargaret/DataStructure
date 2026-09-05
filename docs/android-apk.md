# Android APK：安装 / 构建 / 真机调试指南

## 1. 安装

1. 把 `android/AcademicSearchEngine-debug.apk`（约 85MB，内置 CPython 3.12 与 1126 篇预置数据）传到手机；
2. 点击安装，提示「未知来源」时允许（各厂商入口：设置 → 安全/更多设置 → 允许安装未知应用）；
3. 桌面出现「学术论文检索」图标。debug 签名仅供个人安装演示，商店分发需正式签名。

## 2. 使用要点

- 首次打开先解压内置数据并建索引（约 10 秒 ~ 1 分钟），界面显示加载动画；启动失败会红底显示错误并写入 `startup-error.log`；
- 检索/文库/结构说明/AI 设置四个入口：竖屏=底部导航，横屏=顶部导航；统计条「唯一关键词」「索引总项数」可点击展开全部词条；
- 上传 PDF/TXT/ZIP 立即可检索；上传过的文件可「阅读原文」用系统查看器打开；
- 联网功能：arXiv/OpenAlex 抓取、外部原文链接、AI 精修（需先在「AI 设置」配置，密钥只存手机私有目录）。
- 为控制包体未内置 4 篇历史 PDF 原文（元数据完整可检索）；手机上**新上传**的原文仍可正常阅读。

## 3. 重新构建 APK

### 3.1 环境

| 组件 | 版本/说明 |
| --- | --- |
| JDK | 17（keytool 可用） |
| Android SDK | platform 36、build-tools 36.x（`android/local.properties` 的 sdk.dir） |
| Gradle | 9.x（wrapper 或系统安装均可，脚本自动查找缓存发行版） |
| Python(构建) | 3.12（脚本自动探测；也可设 `ACADEMIC_PYTHON`，或写 `local.properties` 的 `python.executable`） |
| 网络 | 首次构建需 Maven Central / Google Maven / PyPI / chaquo.com |

### 3.2 一键构建

```bat
cd android
build_apk.bat       （或 PowerShell: .\build_apk.ps1）
```

脚本自动完成：写入 `local.properties` 的 python 路径 → 缺失时现场生成 jieba wheel 与 debug keystore →
同步项目源码（python 包 + 前端 + 数据种子）→ Gradle `:app:assembleDebug`。
产物：`android/app/build/outputs/apk/debug/app-debug.apk`，可改名/复制为交付包。

### 3.3 机制备忘

- **Chaquopy 17**：APK 内嵌 CPython 3.12；`mobile_server.py` 在应用私有目录启动 Flask(127.0.0.1:8765)，WebView 加载首页；
- **读写分离**：源码模块经 `paths.py` 读取 `ACADEMIC_DATA_ROOT`（= filesDir/academic，assets 首次解压处），资源与数据都在该可写目录；
- **jieba wheel**：PyPI 只有 sdist 而 Chaquopy pip 强制 `--only-binary`，故 `local-wheels/` 提供预构建 py3-none-any wheel（缺失自动生成）；
- **sitecustomize**：`android/sitecustomize.py` 注入构建 venv，规避沙箱 0o700 目录 ACL 导致的 pip 解包失败；
- **ABI**：arm64-v8a + x86_64（Python 3.12 不支持 armeabi-v7a）；
- **升级安装**：versionCode/解压标记升级后自动重新解压新资源。

## 4. 真机调试（USB 与无线两种）

前提：手机开「开发者选项」（设置→关于→连点版本号 7 次）。

### 4.1 USB 连接

1. 使用支持数据的 USB 线连接电脑；开启「USB 调试」并在手机上允许授权；
2. `adb devices` 出现设备即就绪。

### 4.2 无线调试（Android 11+，配对码）

1. 手机与电脑连同一 Wi-Fi；开发者选项 → **无线调试** → 「使用配对码配对设备」；
2. 记录配对页显示的 **IP:端口** 与 **6 位配对码**，以及无线调试主页面显示的连接 **IP:端口**；
3. 电脑执行：

```
adb pair 192.168.x.x:3xxxx        ← 提示输入配对码时输入 6 位码（adb 30+ 可直接 adb pair IP:PORT 配对码）
adb connect 192.168.x.x:4xxxx     ← 无线调试主页面显示的端口
adb devices                       ← 出现 device 即成功
```

4. 随后即可 `adb install -r xxx.apk`、`adb exec-out screencap -p > s.png` 截图迭代。

> 说明：无线连接在重启/断网后可能失效，需要重新 pair+connect；配对码连接不到时可先用 USB 方式。

### 4.3 抓日志

```
adb logcat -s AcademicSearch AndroidRuntime Python native.stdout native.stderr
adb shell "run-as com.academic.search cat files/academic/startup-error.log 2>/dev/null || echo no-log"
```

adb 不在 PATH 时用 `C:\Users\<用户名>\AppData\Local\Android\Sdk\platform-tools\adb.exe`。