/* ============================================================
 * 论文检索 · 前端交互逻辑
 * 视图：检索 / 文库 / 结构 / AI设置（hash 路由，无框架）
 * ============================================================ */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  view: "search",
  mode: "tf",
  cross: false,
  llm: false,
  lastQuery: "",
  libPage: 1,
  libSize: 15,
  libTotal: 0,
  libQuery: "",
  crawlTimer: null,
};

/* ---------------- api ---------------- */

async function api(url, options) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "请求失败 (" + resp.status + ")");
  return data;
}

function postJson(url, body) {
  return api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const EN = (s) => encodeURIComponent(s);

/* ---------------- ui ---------------- */

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer = null;
function toast(message, kind = "", ms = 3200) {
  const el = $("#toast");
  el.textContent = message;
  el.className = "toast " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), ms);
}

function openModal(title, bodyHtml) {
  const root = $("#modal-root");
  root.innerHTML =
    '<div class="overlay"><div class="modal">' +
    '<div class="modal-head"><h3>' + escapeHtml(title) + "</h3>" +
    '<button class="icon-btn" data-close title="关闭">✕</button></div>' +
    '<div class="modal-body">' + bodyHtml + "</div></div></div>";
  root.querySelector(".overlay").addEventListener("click", (e) => {
    if (e.target.classList.contains("overlay")) closeModal();
  });
  root.querySelector("[data-close]").addEventListener("click", closeModal);
  document.addEventListener("keydown", escHandler);
}

function closeModal() {
  $("#modal-root").innerHTML = "";
  document.removeEventListener("keydown", escHandler);
}

function escHandler(e) { if (e.key === "Escape") closeModal(); }

/* ---------------- 路由 ---------------- */

function switchView(name) {
  state.view = name;
  $$(".nav-item").forEach((n) =>
    n.classList.toggle("active", n.dataset.view === name));
  ["search", "library", "structure", "settings"].forEach((v) => {
    $("#view-" + v).classList.toggle("hidden", v !== name);
  });
  if (name === "library") loadLibrary();
  if (name === "search" && state.lastQuery) doSearch();
  if (name === "settings") loadSettingsView();
}

const VIEWS = ["search", "library", "structure", "settings"];

function parseHash() {
  let h = location.hash;
  if (h.startsWith("#")) h = h.slice(1);
  if (h.startsWith("/")) h = h.slice(1);
  if (VIEWS.includes(h)) switchView(h);
}

/* 跳到检索并查询 term */
function jumpSearch(term) {
  $("#q").value = term;
  state.lastQuery = term;
  if (state.view === "search") {
    doSearch();
  } else {
    location.hash = "#/search";
  }
}

/* ---------------- 统计 ---------------- */

async function refreshStats() {
  try {
    const m = await api("/api/meta");
    state.llm = m.llm_configured;
    $("#stat-papers").textContent = m.total_papers;
    $("#stat-terms-num").textContent = m.unique_terms;
    $("#stat-postings-num").textContent = m.total_postings;
    $("#lib-papers").textContent = m.total_papers;
    const aiEl = $("#lib-ai");
    aiEl.textContent = m.llm_configured ? "已启用" : "未配置";
    aiEl.style.color = m.llm_configured ? "var(--sage)" : "var(--muted)";
    ["#ai-single", "#ai-zip"].forEach((sel) => {
      const cb = $(sel);
      cb.checked = m.llm_configured;
      cb.disabled = !m.llm_configured;
    });
  } catch (err) {
    toast("加载统计失败：" + err.message, "err");
  }
}

/* ---------------- 检索 ---------------- */

async function doSearch() {
  const query = $("#q").value.trim();
  if (!query) return;
  state.lastQuery = query;
  hideSuggest();

  const meta = $("#results-meta");
  const wrap = $("#results");
  const list = $("#results-list");
  const traceBox = $("#trace-box");
  const empty = $("#empty");

  meta.classList.remove("hidden");
  wrap.classList.remove("hidden");
  meta.innerHTML = "<span>检索中…</span>";
  list.innerHTML = "";
  traceBox.innerHTML = "";

  try {
    const d = await api("/api/search?q=" + EN(query) + "&mode=" + state.mode +
      "&cross=" + (state.cross ? 1 : 0));
    if (d.error) {
      meta.innerHTML =
        '<span style="color:var(--danger)">查询错误：' + escapeHtml(d.error) + "</span>";
      wrap.classList.add("hidden");
      return;
    }
    const typeLabel = d.query_type === "boolean" ? "布尔表达式"
      : d.query_type === "cross" ? "互译扩展"
        : "多关键词 AND";
    const modeLabel = d.mode === "tfidf" ? "TF-IDF" : "词频";
    const trunc = d.count > d.results.length
      ? " · 仅展示前 <b>" + d.results.length + "</b> 条" : "";
    meta.innerHTML =
      "<span>共 <b>" + d.count + "</b> 条" + trunc + " · " +
      "<b>" + typeLabel + "</b> · <b>" + modeLabel + "</b> · " +
      d.time_ms + " ms</span>" +
      '<button class="btn btn-sm" id="btn-snapshot">查看索引快照</button>';
    $("#btn-snapshot").addEventListener("click", showIndexSnapshot);

    if (d.count === 0) {
      wrap.classList.add("hidden");
      empty.classList.remove("hidden");
      empty.innerHTML =
        '<div class="glyph">∅</div><p>未找到匹配论文</p>' +
        (d.trace && d.trace.strategy
          ? '<p style="font-size:12.5px">' + escapeHtml(d.trace.strategy) + "</p>" : "");
    } else {
      empty.classList.add("hidden");
      list.innerHTML = d.results.map(renderResult).join("");
    }
    renderTrace(d.trace);
  } catch (err) {
    meta.innerHTML =
      '<span style="color:var(--danger)">检索失败：' + escapeHtml(err.message) + "</span>";
    wrap.classList.add("hidden");
  }
}

function renderResult(item) {
  const url = item.url || "";
  const fileHref = item.file_name ? "/api/papers/" + item.paper_id + "/file" : "";
  const title = url
    ? '<a class="result-title" href="' + escapeHtml(url) + '" target="_blank" rel="noopener" title="打开文献页">' +
      escapeHtml(item.title) + "</a>"
    : '<span class="result-title">' + escapeHtml(item.title) + "</span>";
  const year = item.year ? " · " + item.year : "";
  const authors = escapeHtml((item.authors || []).join(", ") || "佚名");
  const readLink = fileHref
    ? '<a class="file-link" href="' + fileHref + '" target="_blank" title="查看/下载原文">' +
      '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>阅读原文</a>'
    : "";
  const tags = [item.source, item.language].filter(Boolean)
    .map((t) => '<span class="lang-tag">' + escapeHtml(t) + "</span>").join(" ");

  const matched = (item.matched_terms || []).map((m) => {
    const display = escapeHtml(m.display);
    const stem = m.term !== m.display
      ? ' <span class="dim">(' + escapeHtml(m.term) + ")</span>" : "";
    const pos = m.positions && m.positions.length
      ? ' <span class="dim">@' + m.positions.slice(0, 6).join(",") +
        (m.positions.length > 6 ? "…" : "") + "</span>" : "";
    return '<span class="chip"><span class="hit">' + display + "</span>×" +
      m.tf + stem + pos + "</span>";
  }).join("");

  const kws = (item.keywords || []).map((k) =>
    '<span class="chip kw" data-kw="' + escapeHtml(k) + '">' + escapeHtml(k) + "</span>").join("");

  const abs = escapeHtml(item.abstract);
  const expand = item.abstract && item.abstract.length > 180
    ? '<div><button class="expand">展开全文</button></div>' : "";
  const chips = matched || kws
    ? '<div class="chips">' + matched + (matched && kws ? " " : "") + kws + "</div>" : "";

  return '<article class="result" data-id="' + item.paper_id + '">' +
    '<div class="result-top"><div>' + title + "</div>" +
    '<span class="score">' + item.score + "</span></div>" +
    '<div class="result-meta">' + authors + year + " " + readLink + " " + tags + "</div>" +
    '<p class="result-abstract">' + abs + "</p>" + expand + chips +
    "</article>";
}

function renderTrace(trace) {
  const box = $("#trace-box");
  if (!trace || trace.strategy === undefined) { box.innerHTML = ""; return; }
  let rows = "";
  if (trace.terms && trace.terms.length) {
    rows = '<table class="trace-table"><thead><tr>' +
      "<th>词条（词干）</th><th>原词</th><th>df</th><th>Posting 长度</th></tr></thead><tbody>" +
      trace.terms.map((t) =>
        "<tr><td>" + escapeHtml(t.term) + "</td><td>" + escapeHtml(t.display || "—") +
        "</td><td>" + t.df + "</td><td>" + t.df + "</td></tr>").join("") +
      "</tbody></table>";
  }
  let trans = "";
  const tr = trace.translations;
  if (tr && Object.keys(tr).length) {
    const tRows = Object.entries(tr).map(([term, info]) =>
      "<tr><td>" + escapeHtml(term) + "</td><td>" +
      escapeHtml((info.syn || []).join(" / ")) + "</td></tr>").join("");
    trans = '<table class="trace-table" style="margin-top:8px"><thead><tr>' +
      "<th>原词</th><th>互译同义词（已并入检索）</th></tr></thead><tbody>" +
      tRows + "</tbody></table>";
  }
  const ast = trace.ast ? '<pre class="ast">' + escapeHtml(trace.ast) + "</pre>" : "";
  box.innerHTML =
    '<div class="trace"><h4>检索剖析</h4>' +
    '<div class="strategy">' + escapeHtml(trace.strategy) + "</div>" +
    rows + trans + ast + "</div>";
  box.classList.remove("hidden");
}

/* ---------------- 索引快照 ---------------- */

async function showIndexSnapshot() {
  openModal("倒排索引 · 文档频率 Top 20", '<p class="hint">加载中…</p>');
  try {
    const d = await api("/api/index?limit=20");
    const rows = d.terms.map((t) =>
      "<tr><td>" + escapeHtml(t.display || t.term) + "</td>" +
      '<td style="color:var(--muted)">' + escapeHtml(t.term) + "</td>" +
      "<td>df=" + t.df + "</td>" +
      "<td>" + t.postings.slice(0, 5).map((p) => p.paper_id + "×" + p.tf).join(" · ") +
      (t.postings.length > 5 ? " …" : "") + "</td></tr>").join("");
    const body =
      '<p class="hint">共 ' + d.stats.unique_terms + " 个词条 · 索引总项数 " +
      d.stats.total_postings + "，以下按文档频率降序取前 20：</p>" +
      '<table class="trace-table"><thead><tr><th>原词</th><th>词干</th>' +
      "<th>df</th><th>Posting 片段（论文ID×词频）</th></tr></thead><tbody>" +
      rows + "</tbody></table>" +
      '<div class="pane-actions" style="margin-top:14px">' +
      '<button class="btn btn-sm" id="btn-all-terms">浏览全部关键词</button>' +
      '<button class="btn btn-sm" id="btn-raw">查看原始 JSON</button></div>';
    $("#modal-root .modal-body").innerHTML = body;
    $("#btn-all-terms").addEventListener("click", () => {
      closeModal();
      openTermsBrowser("postings");
    });
    $("#btn-raw").addEventListener("click", () => {
      $("#modal-root .modal-body").innerHTML =
        '<pre class="json">' + escapeHtml(JSON.stringify(d, null, 2)) + "</pre>";
    });
  } catch (err) {
    $("#modal-root .modal-body").innerHTML =
      '<p style="color:var(--danger)">加载失败：' + escapeHtml(err.message) + "</p>";
  }
}

/* ---------------- 词条浏览器（统计展开） ---------------- */

let termsPage = 1;
let termsTotal = 0;
let termsQ = "";
let termsKind = "unique";
let termsRows = [];
let termsPostingsTotal = null;

function openTermsBrowser(kind) {
  termsKind = kind;
  termsQ = "";
  termsPage = 1;
  termsRows = [];
  termsPostingsTotal = null;
  const title = kind === "unique" ? "全部唯一关键词" : "索引总项数构成";
  openModal(title,
    '<div class="terms-head">' +
    '<span class="pill" id="terms-stat">…</span>' +
    '<span class="pill" id="terms-total"></span></div>' +
    '<div class="terms-filter">' +
    '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.4-3.4"/></svg>' +
    '<input id="terms-q" class="input" placeholder="输入关键词筛选…"></div>' +
    '<div class="terms-list" id="terms-list"><p class="hint">加载中…</p></div>' +
    '<div class="terms-more"><button class="btn btn-sm hidden" id="terms-more">加载更多</button></div>');
  $("#terms-q").addEventListener("input", () => {
    clearTimeout(window._tq);
    window._tq = setTimeout(() => { termsQ = $("#terms-q").value.trim(); termsPage = 1; termsRows = []; fetchTerms(true); }, 220);
  });
  $("#terms-more").addEventListener("click", () => { termsPage += 1; fetchTerms(false); });
  fetchTerms(true);
}

async function fetchTerms(reset) {
  try {
    const listEl = $("#terms-list");
    const moreBtn = $("#terms-more");
    if (!listEl) return; // modal 已关闭
    const url = "/api/terms?page=" + termsPage + "&size=200" +
      (termsQ ? "&q=" + EN(termsQ) : "");
    const d = await api(url);
    termsTotal = d.total;
    termsRows = reset ? d.terms : termsRows.concat(d.terms);
    const hasMore = termsRows.length < d.total;

    const statEl = $("#terms-stat");
    const totalEl = $("#terms-total");
    if (termsKind === "unique") {
      statEl.innerHTML = "唯一关键词 <b>" + d.total + "</b>";
      if (totalEl) totalEl.innerHTML = "";
    } else {
      statEl.innerHTML = "词条 <b>" + d.total + "</b>";
      if (termsPostingsTotal == null) {
        try {
          const meta = await api("/api/meta");
          termsPostingsTotal = meta.total_postings;
        } catch (_) { /* 忽略 */ }
      }
      if (totalEl) {
        totalEl.innerHTML = "索引总项数（Σdf）<b>" +
          (termsPostingsTotal == null ? "…" : termsPostingsTotal) + "</b>";
      }
    }

    if (!termsRows.length) {
      listEl.innerHTML = '<div class="terms-empty">无匹配词条</div>';
      moreBtn.classList.add("hidden");
      return;
    }
    listEl.innerHTML = termsRows.map((t) =>
      '<div class="trow" data-term="' + escapeHtml(t.display) + '">' +
      '<span class="tk">' + escapeHtml(t.display) + "</span>" +
      (t.term !== t.display ? '<span class="ts">' + escapeHtml(t.term) + "</span>" : '<span class="ts"></span>') +
      '<span class="td">df ' + t.df + "</span></div>").join("") +
      '<div class="terms-empty hint" style="padding:6px 0 0">当前显示 ' +
      termsRows.length + " / " + d.total + " 条" +
      (termsQ ? "（已筛选）" : "") + "</div>";
    moreBtn.classList.toggle("hidden", !hasMore);
  } catch (err) {
    const listEl = $("#terms-list");
    if (listEl) listEl.innerHTML =
      '<p style="color:var(--danger)">加载失败：' + escapeHtml(err.message) + "</p>";
  }
}

/* ---------------- 自动补全 ---------------- */

let suggestTimer = null;
let suggestIdx = -1;

function hideSuggest() { $("#suggest").classList.add("hidden"); suggestIdx = -1; }

async function doSuggest() {
  const prefix = $("#q").value.trim();
  if (!prefix) { hideSuggest(); return; }
  try {
    const d = await api("/api/suggest?prefix=" + EN(prefix));
    if ($("#q").value.trim() !== prefix) return;
    if (!d.suggestions.length) { hideSuggest(); return; }
    $("#suggest").innerHTML = d.suggestions.map((s, i) =>
      '<li class="' + (i === 0 ? "selected" : "") + '">' +
      "<span>" + escapeHtml(s.term) + "</span>" +
      '<span class="freq">词频 ' + s.freq + "</span></li>").join("");
    $("#suggest").classList.remove("hidden");
    suggestIdx = 0;
  } catch (_) { /* 忽略补全错误 */ }
}

function applySuggest(idx) {
  const items = $$("#suggest li");
  if (idx < 0 || idx >= items.length) return;
  $("#q").value = items[idx].querySelector("span").textContent;
  hideSuggest();
  doSearch();
}

function moveSuggest(delta) {
  const items = $$("#suggest li");
  if (!items.length) return;
  suggestIdx = (suggestIdx + delta + items.length) % items.length;
  items.forEach((li, i) => li.classList.toggle("selected", i === suggestIdx));
}

/* ---------------- 文库 ---------------- */

async function loadLibrary() {
  const box = $("#lib-list");
  try {
    const d = await api("/api/papers?page=" + state.libPage + "&size=" + state.libSize +
      (state.libQuery ? "&q=" + EN(state.libQuery) : ""));
    state.libTotal = d.total;
    const pages = Math.max(1, Math.ceil(d.total / d.size));
    $("#lib-total").textContent = "共 " + d.total + " 篇 · 第 " + d.page + "/" + pages + " 页";
    $("#lib-page").textContent = d.page + "/" + pages;
    $("#page-input").value = d.page;
    $("#page-input").max = pages;
    $("#page-prev").disabled = d.page <= 1;
    $("#page-next").disabled = d.page >= pages;
    if (!d.papers.length) {
      box.innerHTML = '<div class="empty"><div class="glyph">∅</div><p>文库为空</p></div>';
      return;
    }
    box.innerHTML = d.papers.map((p) => {
      const link = p.url
        ? '<a class="tt" href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener" title="打开文献页">' +
          escapeHtml(p.title) + "</a>"
        : '<span class="tt">' + escapeHtml(p.title) + "</span>";
      const tags = [p.source, p.language].filter(Boolean)
        .map((t) => '<span class="lang-tag">' + escapeHtml(t) + "</span>").join(" ");
      const fileLink = p.file_name
        ? '<a class="btn btn-sm" href="/api/papers/' + p.id + '/file" target="_blank" title="' +
          escapeHtml(p.file_name) + '">阅读原文</a>'
        : "";
      const kws = (p.keywords || []).slice(0, 5).map((k) =>
        '<span class="chip kw" data-kw="' + escapeHtml(k) + '">' + escapeHtml(k) + "</span>").join("");
      return '<div class="paper-row" data-id="' + p.id + '">' +
        '<span class="pid">#' + p.id + "</span>" +
        "<div>" + link + '<div class="au">' +
        escapeHtml((p.authors || []).join(", ") || "佚名") + " " + tags + "</div></div>" +
        '<span class="yr">' + (p.year ?? "—") + "</span>" +
        '<div class="kwcell">' + kws + "</div>" +
        '<div class="act">' + fileLink +
        '<button class="btn btn-sm" data-act="view">详情</button>' +
        '<button class="btn btn-sm btn-danger-text" data-act="del">删除</button>' +
        "</div></div>";
    }).join("");
  } catch (err) {
    box.innerHTML =
      '<p class="hint" style="color:var(--danger)">加载失败：' + escapeHtml(err.message) + "</p>";
  }
}

async function showPaperDetail(id) {
  try {
    const p = await api("/api/papers/" + id);
    const kws = (p.keywords || []).map((k) =>
      '<span class="chip kw">' + escapeHtml(k) + "</span>").join(" ") || "—";
    const body =
      '<p style="font-size:18px;font-weight:800;line-height:1.5">' + escapeHtml(p.title) + "</p>" +
      '<div class="kv"><span class="k">作者</span><span>' +
      escapeHtml((p.authors || []).join(", ") || "佚名") + "</span></div>" +
      (p.url ? '<div class="kv"><span class="k">文献页</span><span><a href="' +
        escapeHtml(p.url) + '" target="_blank" rel="noopener">' + escapeHtml(p.url) +
        "</a></span></div>" : "") +
      '<div class="kv"><span class="k">年份</span><span>' +
      escapeHtml(String(p.year ?? "—")) + "</span></div>" +
      '<div class="kv"><span class="k">来源</span><span><code>' +
      escapeHtml(p.source_id || p.source || "—") + "</code>" +
      (p.language ? ' <span class="lang-tag">' + escapeHtml(p.language) + "</span>" : "") +
      "</span></div>" +
      (p.file_name ? '<div class="kv"><span class="k">原文</span><span>' +
        '<a class="file-link" href="/api/papers/' + p.id + '/file" target="_blank">' +
        escapeHtml(p.file_name) + "</a></span></div>" : "") +
      '<div class="kv" style="align-items:flex-start"><span class="k">关键词</span>' +
      '<span style="display:flex;flex-wrap:wrap;gap:5px">' + kws + "</span></div>" +
      '<div style="margin-top:10px"><span class="k" style="color:var(--muted);font-size:12.5px">摘要</span>' +
      '<p style="font-size:13.5px;color:var(--soft);margin-top:4px">' +
      (escapeHtml(p.abstract) || "（无摘要）") + "</p></div>";
    openModal("论文详情 #" + id, body);
  } catch (err) {
    toast("加载详情失败：" + err.message, "err");
  }
}

/* ---------------- 导入 ---------------- */

function bindFilePick(inputId, labelId, btnId) {
  const input = $(inputId);
  input.addEventListener("change", () => {
    const f = input.files[0];
    $(labelId).textContent = f ? "已选择：" + f.name : "点击选择文件";
    $(labelId).parentElement.classList.toggle("has", !!f);
    $(btnId).disabled = !f;
  });
}

function resetFileInput(inputId, labelId, btnId) {
  $(inputId).value = "";
  $(labelId).textContent = "点击选择文件";
  $(labelId).parentElement.classList.remove("has");
  $(btnId).disabled = true;
}

function showReport(head, sub) {
  const r = $("#report");
  r.classList.remove("hidden");
  r.innerHTML = '<div class="ok"><b>' + escapeHtml(head) + "</b></div>" +
    (sub ? '<div class="hint" style="margin-top:4px">' + escapeHtml(sub) + "</div>" : "");
}

function showMsg(html) {
  const el = $("#setting-msg");
  el.classList.remove("hidden");
  el.innerHTML = html;
}

async function uploadSingle() {
  const file = $("#file-single").files[0];
  if (!file) return;
  const btn = $("#btn-file");
  btn.disabled = true;
  const form = new FormData();
  form.append("file", file);
  form.append("ai", $("#ai-single").checked ? "1" : "0");
  try {
    const d = await api("/api/papers/file", { method: "POST", body: form });
    if (d.ok === false && d.duplicate) {
      showReport("该文献已存在，未重复入库",
        "已有论文 #" + d.existing.paper_id + "「" + d.existing.title + "」内容完全一致");
      toast("重复导入已拦截（#" + d.existing.paper_id + "）", "err");
    } else {
      showReport("已入库「" + d.paper.title + "」",
        "置信度 " + d.confidence + (d.ai_used ? " · AI 精修" : " · 规则拆解"));
    }
    resetFileInput("#file-single", "#file-single-name", "#btn-file");
    refreshStats(); loadLibrary();
  } catch (err) {
    toast("解析失败：" + err.message, "err");
  } finally { btn.disabled = false; }
}

async function uploadZip() {
  const file = $("#file-zip").files[0];
  if (!file) return;
  const btn = $("#btn-zip");
  btn.disabled = true;
  const form = new FormData();
  form.append("file", file);
  form.append("ai", $("#ai-zip").checked ? "1" : "0");
  try {
    const d = await api("/api/papers/file", { method: "POST", body: form });
    const added = (d.added || []).map((a) =>
      '<li><span class="ok">＋</span> ' + escapeHtml(a.name) + " → " + escapeHtml(a.title) + "</li>").join("");
    const duplicated = (d.duplicated || []).map((x) =>
      '<li><span class="bad">＝</span> ' + escapeHtml(x.name) + "：与 #" + x.paper_id +
      "「" + escapeHtml(x.title) + "」一致，已跳过</li>").join("");
    const failed = (d.failed || []).map((f) =>
      '<li><span class="bad">－</span> ' + escapeHtml(f.name) + "：" + escapeHtml(f.error) + "</li>").join("");
    showReport("ZIP 导入完成", "");
    $("#report").insertAdjacentHTML("beforeend",
      '<div class="ok">成功 ' + (d.added || []).length + " · 重复跳过 " +
      (d.duplicated || []).length + " · 失败 " + (d.failed || []).length + "</div><ul>" +
      added + duplicated + failed + "</ul>");
    resetFileInput("#file-zip", "#file-zip-name", "#btn-zip");
    refreshStats(); loadLibrary();
  } catch (err) {
    toast("导入失败：" + err.message, "err");
  } finally { btn.disabled = false; }
}

function switchTab(name) {
  $$(".tabs button").forEach((t) =>
    t.classList.toggle("active", t.dataset.tab === name));
  $$(".tabpane").forEach((p) =>
    p.classList.toggle("active", p.id === name));
}

/* ---------------- 爬虫 ---------------- */

function gotoPage() {
  const pages = Math.max(1, Math.ceil(state.libTotal / state.libSize));
  let page = Number($("#page-input").value) || 1;
  page = Math.min(Math.max(1, page), pages);
  $("#page-input").value = page;
  state.libPage = page;
  loadLibrary();
}

async function startCrawl() {
  const source = $("#crawl-source").value;
  try {
    await postJson("/api/crawl", { source });
    toast("已启动数据采集（" + source + "）…");
    pollCrawl(true);
  } catch (err) { toast(err.message, "err"); }
}

function pollCrawl(force = false) {
  const btn = $("#btn-crawl");
  const badge = $("#crawl-state");
  clearInterval(state.crawlTimer);
  state.crawlTimer = setInterval(async () => {
    try {
      const s = await api("/api/crawl/status");
      badge.textContent = s.running ? "采集中 " + s.total : (s.message || "待机");
      badge.style.color = s.running ? "var(--accent)" : "var(--muted)";
      if (!s.running) {
        clearInterval(state.crawlTimer);
        btn.disabled = false;
        if (force || (s.message || "").includes("完成")) {
          toast("采集：" + s.message, (s.message || "").includes("失败") ? "err" : "ok");
          refreshStats(); loadLibrary();
          if (state.lastQuery) doSearch();
        }
      }
    } catch (_) { /* 忽略轮询错误 */ }
  }, 2000);
}

/* ---------------- AI 设置视图 ---------------- */

function setSettingStatus(on, text) {
  const box = $("#setting-status");
  box.classList.toggle("on", on);
  box.classList.toggle("off", !on);
  $("#setting-status-text").textContent = text;
}

async function loadSettingsView() {
  const msg = $("#setting-msg");
  msg.classList.add("hidden");
  try {
    const s = await api("/api/settings");
    $("#s-base").value = s.api_base || "";
    $("#s-key").value = "";
    $("#s-key").placeholder = s.configured
      ? "已保存 " + s.api_key_masked + "（重新输入可更换）" : "sk-…";
    $("#s-model").value = s.model || "";
    $("#s-timeout").value = s.timeout || 30;
    if (s.configured) {
      setSettingStatus(true, "已配置：模型 " + s.model + " · Key " + s.api_key_masked);
    } else {
      setSettingStatus(false, "未配置：AI 拆解关闭，将使用本地规则拆解");
    }
  } catch (err) {
    setSettingStatus(false, "读取配置失败：" + err.message);
  }
}

function settingsPayload() {
  const key = $("#s-key").value.trim();
  return {
    api_base: $("#s-base").value.trim(),
    api_key: key,
    model: $("#s-model").value.trim(),
    timeout: Number($("#s-timeout").value) || 30,
  };
}

async function settingsSave() {
  const btn = $("#btn-save");
  btn.disabled = true;
  try {
    const payload = settingsPayload();
    if (!payload.api_base || !payload.model) {
      throw new Error("请填写 API 地址与模型名");
    }
    const s = await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (s.configured) {
      setSettingStatus(true, "已配置：模型 " + s.model + " · Key " + s.api_key_masked);
    } else {
      setSettingStatus(false, "缺少 API Key：AI 拆解暂不可用");
    }
    showMsg('<div class="ok">配置已保存并生效</div>');
    refreshStats();
    toast("配置已保存", "ok");
  } catch (err) {
    showMsg('<div class="bad">保存失败：' + escapeHtml(err.message) + "</div>");
    toast("保存失败：" + err.message, "err");
  } finally { btn.disabled = false; }
}

async function settingsTest() {
  const btn = $("#btn-test");
  btn.disabled = true;
  showMsg('<div class="hint" style="margin:0">正在连接测试…</div>');
  try {
    const r = await postJson("/api/settings/test", settingsPayload());
    if (r.ok) {
      showMsg('<div class="ok">连接成功，AI 服务可用</div>');
      toast("连接成功", "ok");
    } else {
      showMsg('<div class="bad">' + escapeHtml(r.message) + "</div>");
    }
  } catch (err) {
    showMsg('<div class="bad">测试失败：' + escapeHtml(err.message) + "</div>");
  } finally { btn.disabled = false; }
}

async function settingsClear() {
  if (!confirm("确认清除本地保存的 AI 配置（含 API Key）？")) return;
  try {
    await api("/api/settings", { method: "DELETE" });
    $("#s-key").value = "";
    $("#s-key").placeholder = "sk-…";
    setSettingStatus(false, "未配置：AI 拆解关闭，将使用本地规则拆解");
    showMsg('<div class="ok">配置已清除</div>');
    refreshStats();
    toast("已清除配置", "ok");
  } catch (err) {
    toast("清除失败：" + err.message, "err");
  }
}

/* ---------------- 事件绑定 ---------------- */

function bindEvents() {
  $$(".nav-item").forEach((n) => n.addEventListener("click", () => {
    location.hash = "#/" + n.dataset.view;
  }));
  window.addEventListener("hashchange", parseHash);

  // 统计卡 -> 词条浏览器
  $$(".stat-link").forEach((card) => card.addEventListener("click", () => {
    openTermsBrowser(card.dataset.terms || "unique");
  }));

  // 检索
  $("#btn-search").addEventListener("click", doSearch);
  $("#q").addEventListener("keydown", (e) => {
    const open = !$("#suggest").classList.contains("hidden");
    if (e.key === "Enter") {
      e.preventDefault();
      if (open && suggestIdx >= 0) applySuggest(suggestIdx); else doSearch();
    }
    if (open && e.key === "ArrowDown") { e.preventDefault(); moveSuggest(1); }
    if (open && e.key === "ArrowUp") { e.preventDefault(); moveSuggest(-1); }
    if (e.key === "Escape") hideSuggest();
  });
  $("#q").addEventListener("input", () => {
    clearTimeout(suggestTimer);
    suggestTimer = setTimeout(doSuggest, 180);
  });
  $("#q").addEventListener("blur", () => setTimeout(hideSuggest, 160));
  $("#suggest").addEventListener("mousedown", (e) => {
    const li = e.target.closest("li");
    if (li) applySuggest($$("#suggest li").indexOf(li));
  });
  $("#mode-seg").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    state.mode = btn.dataset.mode;
    $$("#mode-seg button").forEach((b) =>
      b.classList.toggle("active", b === btn));
    if (state.lastQuery) doSearch();
  });
  $("#cross-toggle").addEventListener("click", () => {
    state.cross = !state.cross;
    $("#cross-toggle").classList.toggle("btn-on", state.cross);
    if (state.lastQuery) doSearch();
  });

  // 结果区：关键词跳检索 / 展开摘要
  $("#results-list").addEventListener("click", (e) => {
    const kw = e.target.closest("[data-kw]");
    if (kw) { jumpSearch(kw.dataset.kw); return; }
    const btn = e.target.closest(".expand");
    if (!btn) return;
    const ab = btn.closest(".result").querySelector(".result-abstract");
    const open = ab.classList.toggle("expanded");
    btn.textContent = open ? "收起全文" : "展开全文";
  });

  // 词条浏览器点击 -> 检索该词
  $("#modal-root").addEventListener("click", (e) => {
    const row = e.target.closest(".trow");
    if (!row) return;
    closeModal();
    jumpSearch(row.dataset.term);
  });

  // 文库
  $("#lib-filter").addEventListener("input", () => {
    clearTimeout(window._ft);
    window._ft = setTimeout(() => {
      state.libQuery = $("#lib-filter").value.trim();
      state.libPage = 1;
      loadLibrary();
    }, 250);
  });
  $("#page-prev").addEventListener("click", () => {
    state.libPage = Math.max(1, state.libPage - 1); loadLibrary();
  });
  $("#page-next").addEventListener("click", () => { state.libPage += 1; loadLibrary(); });
  $("#btn-goto").addEventListener("click", gotoPage);
  $("#page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") gotoPage();
  });
  $("#lib-list").addEventListener("click", (e) => {
    const kw = e.target.closest("[data-kw]");
    if (kw) { jumpSearch(kw.dataset.kw); return; }
    const row = e.target.closest(".paper-row");
    if (!row) return;
    const id = Number(row.dataset.id);
    const act = e.target.closest("[data-act]");
    if (!act) return;
    if (act.dataset.act === "del") {
      if (!confirm("确认删除论文 #" + id + "？")) return;
      api("/api/papers/" + id, { method: "DELETE" })
        .then(() => { toast("已删除 #" + id, "ok"); refreshStats(); loadLibrary(); })
        .catch((err) => toast(err.message, "err"));
    } else if (act.dataset.act === "view") {
      showPaperDetail(id);
    }
  });

  // 导入
  $$(".tabs button").forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)));
  bindFilePick("#file-single", "#file-single-name", "#btn-file");
  bindFilePick("#file-zip", "#file-zip-name", "#btn-zip");
  $("#btn-file").addEventListener("click", uploadSingle);
  $("#btn-zip").addEventListener("click", uploadZip);
  $("#btn-url").addEventListener("click", async () => {
    const url = $("#url-input").value.trim();
    if (!url) return toast("请输入 arXiv 链接或编号", "err");
    try {
      const d = await postJson("/api/papers/url", { url });
      if (d.ok === false && d.duplicate) {
        toast("该论文已存在（#" + d.existing.paper_id + "），未重复入库", "err");
      } else {
        toast("已入库「" + d.paper.title + "」", "ok");
        $("#url-input").value = "";
      }
      refreshStats(); loadLibrary();
    } catch (err) { toast("添加失败：" + err.message, "err"); }
  });
  $("#btn-manual").addEventListener("click", async () => {
    const payload = {
      title: $("#m-title").value.trim(),
      abstract: $("#m-abstract").value.trim(),
      authors: $("#m-authors").value.split(/[,，;；]/)
        .map((s) => s.trim()).filter(Boolean),
      year: $("#m-year").value ? Number($("#m-year").value) : null,
    };
    if (!payload.title) return toast("请填写标题", "err");
    try {
      const d = await postJson("/api/papers/manual", payload);
      if (d.ok === false && d.duplicate) {
        toast("该论文已存在（#" + d.existing.paper_id + "），未重复入库", "err");
      } else {
        toast("已入库「" + d.paper.title + "」", "ok");
        ["#m-title", "#m-authors", "#m-year", "#m-abstract"].forEach((s) => ($(s).value = ""));
      }
      refreshStats(); loadLibrary();
    } catch (err) { toast("添加失败：" + err.message, "err"); }
  });

  // AI 设置
  $("#btn-save").addEventListener("click", settingsSave);
  $("#btn-test").addEventListener("click", settingsTest);
  $("#btn-clear").addEventListener("click", settingsClear);
  const eye = $("#s-key-eye");
  eye.addEventListener("click", () => {
    const k = $("#s-key");
    const show = k.type === "password";
    k.type = show ? "text" : "password";
    eye.textContent = show ? "隐藏" : "显示";
  });

  // 爬虫
  $("#btn-crawl").addEventListener("click", async () => {
    const btn = $("#btn-crawl");
    btn.disabled = true;
    try { await startCrawl(); } catch (err) { btn.disabled = false; toast(err.message, "err"); }
  });
  pollCrawl();
}

/* ---------------- 初始化 ---------------- */

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshStats();
  parseHash();
  if (!location.hash) switchView("search");
  // 演示入口：?modal=terms 自动打开「索引总项数构成」弹窗（便于无头截图预览）
  if (new URLSearchParams(location.search).has("modal")) {
    setTimeout(() => openTermsBrowser("postings"), 1000);
  }
});

/* ---------- 无头布局探针（?probe=1 触发，仅开发校验用） ---------- */
window.addEventListener("load", () => {
  if (!new URLSearchParams(location.search).has("probe")) return;
  setTimeout(() => {
    const out = [];
    const doc = document.documentElement;
    out.push("VW=" + window.innerWidth + "x" + window.innerHeight);
    out.push("doc scrollW=" + doc.scrollWidth + " clientW=" + doc.clientWidth + (doc.scrollWidth > doc.clientWidth + 1 ? " OVERFLOW" : ""));
    const nav = document.querySelector(".nav");
    if (nav) {
      const cs = getComputedStyle(nav);
      const rect = nav.getBoundingClientRect();
      out.push("nav pos=" + cs.position + " flexDir=" + cs.flexDirection + " rect=" + Math.round(rect.left) + "," + Math.round(rect.top) + "," + Math.round(rect.width) + "x" + Math.round(rect.height));
    }
    ["search", "library", "structure", "settings"].forEach((v) => {
      const el = document.getElementById("view-" + v);
      if (!el) return;
      const wasHidden = el.classList.contains("hidden");
      if (wasHidden) el.classList.remove("hidden");
      const sw = el.scrollWidth, cw = el.clientWidth;
      out.push("view-" + v + " scrollW=" + sw + " clientW=" + cw + (sw > cw + 1 ? " OVERFLOW" : ""));
      const offenders = [];
      el.querySelectorAll("div,table,section,main,ul,ol,dl,details,pre").forEach((n) => {
        if (n.scrollWidth > cw + 2) offenders.push((n.className && n.className.toString ? n.className.toString().slice(0, 34) : n.tagName) + ":" + n.tagName);
      });
      if (offenders.length) out.push("  offenders " + offenders.slice(0, 6).join(" | "));
      if (wasHidden) el.classList.add("hidden");
    });
    const pre = document.createElement("pre");
    pre.id = "probe-out";
    pre.textContent = out.join("\n");
    document.body.appendChild(pre);
  }, 600);
});

/* ---------- 交互自测（?actions=1 触发，仅开发校验用） ---------- */
window.addEventListener("load", () => {
  if (!new URLSearchParams(location.search).has("actions")) return;
  (async () => {
    const out = [];
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    try {
      openTermsBrowser("unique");
      await wait(1100);
      const st = document.getElementById("terms-stat");
      out.push("uniqueRows=" + document.querySelectorAll(".trow").length + " stat=" + (st ? st.textContent : "none"));
      closeModal();
      await wait(250);
      openTermsBrowser("postings");
      await wait(1100);
      const st2 = document.getElementById("terms-stat");
      const tl2 = document.getElementById("terms-total");
      out.push("postingsStat=" + (st2 ? st2.textContent : "") + " total=" + (tl2 ? tl2.textContent : ""));
      closeModal();
      await wait(250);
      document.getElementById("q").value = "attention";
      await doSearch();
      await wait(1600);
      out.push("results=" + document.querySelectorAll("#results-list .result").length);
      const mm = document.getElementById("results-meta");
      out.push("meta=" + (mm ? mm.textContent.slice(0, 150) : ""));
      const settings = await api("/api/settings");
      out.push("settingsGet=" + (settings.configured ? "on" : "off"));
    } catch (e) { out.push("PROBE2 ERR " + e.message); }
    const pre = document.createElement("pre");
    pre.id = "probe-out2";
    pre.textContent = out.join(" || ");
    document.body.appendChild(pre);
  })();
});