/* ============================================================
 * 学术论文关键词索引与检索系统 —— 前端交互逻辑
 * 视图：检索 / 文库 / 结构说明（hash 路由，无框架）
 * 模块：api · ui · router · search · suggest · library · import · crawl
 * ============================================================ */

"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ---------------- 状态 ----------------

const state = {
  view: "search",
  mode: "tf",
  cross: false,
  lastQuery: "",
  libPage: 1,
  libSize: 15,
  libTotal: 0,
  libQuery: "",
  crawlTimer: null,
};

// ---------------- api ----------------

async function api(url, options) {
  const resp = await fetch(url, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `请求失败 (${resp.status})`);
  return data;
}

function postJson(url, body) {
  return api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------------- ui ----------------

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer = null;
function toast(message, kind = "", ms = 3000) {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), ms);
}

function openModal(title, bodyHtml) {
  const root = $("#modal-root");
  root.innerHTML = `
    <div class="overlay">
      <div class="modal">
        <div class="modal-head"><h3>${escapeHtml(title)}</h3>
          <button class="icon-btn" data-close>✕</button></div>
        <div class="modal-body">${bodyHtml}</div>
      </div>
    </div>`;
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

function escHandler(e) {
  if (e.key === "Escape") closeModal();
}

// ---------------- 路由 ----------------

function switchView(name) {
  state.view = name;
  $$(".nav-item").forEach((n) =>
    n.classList.toggle("active", n.dataset.view === name));
  ["search", "library", "structure"].forEach((v) => {
    $(`#view-${v}`).classList.toggle("hidden", v !== name);
  });
  if (name === "library") loadLibrary();
  if (name === "search" && state.lastQuery) doSearch();
}

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  if (["search", "library", "structure"].includes(h)) switchView(h);
}

// ---------------- 统计 ----------------

async function refreshStats() {
  try {
    const m = await api("/api/meta");
    state.llm = m.llm_configured;
    $("#stat-papers").textContent = m.total_papers;
    $("#stat-terms").textContent = m.unique_terms;
    $("#stat-postings").textContent = m.total_postings;
    $("#lib-papers").textContent = m.total_papers;
    $("#lib-ai").textContent = m.llm_configured ? "已启用" : "未配置";
    $("#lib-ai").style.color = m.llm_configured ? "var(--sage)" : "var(--muted)";
    // AI 已配置时默认勾选自动精修；未配置则禁用并提示
    ["#ai-single", "#ai-zip"].forEach((sel) => {
      const cb = $(sel);
      cb.checked = m.llm_configured;
      cb.disabled = !m.llm_configured;
    });
  } catch (err) {
    toast(`加载统计失败：${err.message}`, "err");
  }
}

// ---------------- 检索 ----------------

const EN = (s) => encodeURIComponent(s);

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
  meta.innerHTML = `<span>检索中…</span>`;
  list.innerHTML = "";
  traceBox.innerHTML = "";

  try {
    const d = await api(`/api/search?q=${EN(query)}&mode=${state.mode}` +
      `&cross=${state.cross ? 1 : 0}`);
    if (d.error) {
      meta.innerHTML = `<span style="color:var(--danger)">查询错误：${escapeHtml(d.error)}</span>`;
      wrap.classList.add("hidden");
      return;
    }
    const typeLabel = d.query_type === "boolean" ? "布尔表达式" : "多关键词 AND";
    const modeLabel = d.mode === "tfidf" ? "TF-IDF" : "TF";
    const trunc = d.count > d.results.length
      ? ` · 已展示前 <b>${d.results.length}</b> 条` : "";
    meta.innerHTML =
      `<span>共 <b>${d.count}</b> 条结果${trunc} · 耗时 <b>${d.time_ms}</b> ms · ` +
      `<b>${typeLabel}</b> · <b>${modeLabel}</b></span>` +
      `<button class="btn btn-sm" id="btn-snapshot">查看索引快照</button>`;
    $("#btn-snapshot").addEventListener("click", showIndexSnapshot);

    if (d.count === 0) {
      wrap.classList.add("hidden");
      empty.classList.remove("hidden");
      empty.innerHTML = `<div class="glyph">∅</div>
        <p style="margin-top:6px">未找到匹配论文</p>
        <p style="font-size:12.5px">${escapeHtml(d.trace?.strategy || "")}</p>`;
    } else {
      empty.classList.add("hidden");
      list.innerHTML = d.results.map(renderResult).join("");
    }
    renderTrace(d.trace);
  } catch (err) {
    meta.innerHTML = `<span style="color:var(--danger)">检索失败：${escapeHtml(err.message)}</span>`;
    wrap.classList.add("hidden");
  }
}

function renderResult(item) {
  const url = item.url || "";
  const fileHref = item.file_name ? `/api/papers/${item.paper_id}/file` : "";
  const title = url
    ? `<a class="result-title" href="${escapeHtml(url)}" target="_blank" rel="noopener" title="打开文献页面">${escapeHtml(item.title)}</a>`
    : `<span class="result-title">${escapeHtml(item.title)}</span>`;
  const year = item.year ? ` · ${item.year}` : "";
  const authors = (item.authors || []).join(", ") || "佚名";
  const readLink = fileHref
    ? `<a class="file-link" href="${fileHref}" target="_blank" title="下载/查看原文文件 ${escapeHtml(item.file_name)}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>
        阅读原文</a>` : "";
  const tags = [item.source, item.language].filter(Boolean)
    .map((t) => `<span class="lang-tag">${escapeHtml(t)}</span>`).join(" ");

  const matched = (item.matched_terms || []).map((m) => {
    const display = escapeHtml(m.display);
    const stem = m.term !== m.display ? ` <span style="opacity:.55">(${escapeHtml(m.term)})</span>` : "";
    const pos = m.positions.length
      ? ` <span style="opacity:.55">@[${m.positions.slice(0, 6).join(",")}${m.positions.length > 6 ? "…" : ""}]</span>` : "";
    return `<span class="chip"><span class="hit">${display}</span>×${m.tf}${stem}${pos}</span>`;
  }).join("");

  const kws = (item.keywords || []).map((k) =>
    `<span class="chip kw" data-kw="${escapeHtml(k)}">${escapeHtml(k)}</span>`).join("");

  const abs = escapeHtml(item.abstract);
  const expand = item.abstract && item.abstract.length > 180
    ? `<div><button class="expand">展开全文</button></div>` : "";
  const chips = matched || kws
    ? `<div class="chips">${matched}${matched ? " " : ""}${kws}</div>` : "";

  return `
  <article class="result" data-id="${item.paper_id}">
    <div class="result-top">
      <div>${title}</div>
      <span class="score">${item.score}</span>
    </div>
    <div class="result-meta">${escapeHtml(authors)}${year} ${readLink} ${tags}</div>
    <p class="result-abstract">${abs}</p>
    ${expand}
    ${chips}
  </article>`;
}

function renderTrace(trace) {
  const box = $("#trace-box");
  if (!trace || trace.strategy === undefined) { box.innerHTML = ""; return; }
  let rows = "";
  if (trace.terms && trace.terms.length) {
    rows = `<table class="trace-table">
      <thead><tr><th>词条（词干）</th><th>原词示例</th><th>文档频率 df</th><th>Posting 列表长度</th></tr></thead>
      <tbody>` +
      trace.terms.map((t) =>
        `<tr><td>${escapeHtml(t.term)}</td><td>${escapeHtml(t.display || "—")}</td>
         <td>${t.df}</td><td>${t.df}</td></tr>`).join("") +
      `</tbody></table>`;
  }
  const ast = trace.ast ? `<pre class="ast">${escapeHtml(trace.ast)}</pre>` : "";
  let trans = "";
  const tr = trace.translations;
  if (tr && Object.keys(tr).length) {
    const rows = Object.entries(tr).map(([term, info]) =>
      `<tr><td>${escapeHtml(term)}</td><td>${escapeHtml((info.syn || []).join(" / "))}</td></tr>`).join("");
    trans = `<table class="trace-table" style="margin-top:8px">
      <thead><tr><th>原词</th><th>互译同义词（已并入检索）</th></tr></thead><tbody>${rows}</tbody></table>`;
  }
  box.innerHTML = `
    <div class="trace">
      <h4>检索剖析 · Query Trace</h4>
      <div class="strategy">${escapeHtml(trace.strategy)}</div>
      ${rows}${trans}${ast}
    </div>`;
  box.classList.remove("hidden");
}

// ---------------- 索引快照 ----------------

async function showIndexSnapshot() {
  openModal("倒排索引原始结构（文档频率 Top 20）", `<p class="hint">加载中…</p>`);
  try {
    const d = await api("/api/index?limit=20");
    const rows = d.terms.map((t) =>
      `<tr><td style="text-align:right"><code>${escapeHtml(t.display || t.term)}</code></td>` +
      `<td style="text-align:center;color:var(--muted)">${escapeHtml(t.term)}</td>` +
      `<td style="text-align:center">df=${t.df}</td>` +
      `<td><code style="font-size:11px">${t.postings.slice(0, 5).map((p) =>
        `${p.paper_id}×${p.tf}`).join(" · ")}${t.postings.length > 5 ? " …" : ""}</code></td></tr>`).join("");
    const body = `<p class="hint">共 ${d.stats.unique_terms} 个词条 · 索引总项数 ${d.stats.total_postings}，以下为文档频率最高的词项。</p>
      <table class="trace-table"><thead><tr><th style="text-align:right">原词</th><th>词干</th><th>df</th><th>Posting 片段 (paper_id×tf)</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div style="margin-top:12px"><button class="btn btn-sm" id="btn-raw">查看原始 JSON</button></div>`;
    $("#modal-root .modal-body").innerHTML = body;
    $("#btn-raw").addEventListener("click", () => {
      $("#modal-root .modal-body").innerHTML =
        `<pre class="json">${escapeHtml(JSON.stringify(d, null, 2))}</pre>`;
    });
  } catch (err) {
    $("#modal-root .modal-body").innerHTML = `<p style="color:var(--danger)">加载失败：${escapeHtml(err.message)}</p>`;
  }
}

// ---------------- 自动补全 ----------------

let suggestTimer = null;
let suggestIdx = -1;

function hideSuggest() { $("#suggest").classList.add("hidden"); suggestIdx = -1; }

async function doSuggest() {
  const prefix = $("#q").value.trim();
  if (!prefix) { hideSuggest(); return; }
  try {
    const d = await api(`/api/suggest?prefix=${EN(prefix)}`);
    if ($("#q").value.trim() !== prefix) return;
    if (!d.suggestions.length) { hideSuggest(); return; }
    $("#suggest").innerHTML = d.suggestions.map((s, i) =>
      `<li class="${i === 0 ? "selected" : ""}">
        <span>${escapeHtml(s.term)}</span>
        <span class="freq">词频 ${s.freq}</span></li>`).join("");
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

// ---------------- 文库 ----------------

async function loadLibrary() {
  const box = $("#lib-list");
  try {
    const d = await api(`/api/papers?page=${state.libPage}&size=${state.libSize}` +
      (state.libQuery ? `&q=${EN(state.libQuery)}` : ""));
    state.libTotal = d.total;
    const pages = Math.max(1, Math.ceil(d.total / d.size));
    $("#lib-total").textContent = `共 ${d.total} 篇 · 第 ${d.page} / ${pages} 页`;
    $("#lib-page").textContent = `${d.page} / ${pages}`;
    $("#page-input").value = d.page;
    $("#page-input").max = pages;
    $("#page-prev").disabled = d.page <= 1;
    $("#page-next").disabled = d.page >= pages;
    if (!d.papers.length) {
      box.innerHTML = `<div class="empty"><div class="glyph">∅</div><p>文库为空</p></div>`;
      return;
    }
    box.innerHTML = d.papers.map((p) => {
      const link = p.url
        ? `<a class="tt" href="${escapeHtml(p.url)}" target="_blank" rel="noopener" title="打开文献页面">${escapeHtml(p.title)}</a>`
        : `<span class="tt">${escapeHtml(p.title)}</span>`;
      const tags = [p.source, p.language].filter(Boolean)
        .map((t) => `<span class="lang-tag">${escapeHtml(t)}</span>`).join(" ");
      const fileLink = p.file_name
        ? `<a class="file-link" href="/api/papers/${p.id}/file" target="_blank" title="${escapeHtml(p.file_name)}">阅读原文</a>`
        : "";
      const kws = (p.keywords || []).slice(0, 4).map((k) =>
        `<span class="chip kw" data-kw="${escapeHtml(k)}">${escapeHtml(k)}</span>`).join("");
      return `<div class="paper-row" data-id="${p.id}">
        <span class="pid">#${p.id}</span>
        <div>${link}
          <div class="au">${escapeHtml((p.authors || []).join(", ") || "佚名")} ${tags}</div>
        </div>
        <span class="yr">${p.year ?? "—"}</span>
        <div class="kwcell">${kws}</div>
        <div class="act">
          ${fileLink}
          <button class="btn btn-sm" data-act="view">详情</button>
          <button class="btn btn-sm btn-danger" data-act="del">删除</button>
        </div>
      </div>`;
    }).join("");
  } catch (err) {
    box.innerHTML = `<p class="hint" style="color:var(--danger)">加载失败：${escapeHtml(err.message)}</p>`;
  }
}

async function showPaperDetail(id) {
  try {
    const p = await api(`/api/papers/${id}`);
    const kws = (p.keywords || []).map((k) =>
      `<span class="chip kw">${escapeHtml(k)}</span>`).join(" ") || "—";
    const body = `
      <p style="font-family:var(--serif);font-size:19px;font-weight:700;line-height:1.5">${escapeHtml(p.title)}</p>
      <div class="kv"><span class="k">作者</span><span>${escapeHtml((p.authors || []).join(", ") || "佚名")}</span></div>
      ${p.url ? `<div class="kv"><span class="k">文献页</span><span><a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">${escapeHtml(p.url)}</a></span></div>` : ""}
      <div class="kv"><span class="k">年份</span><span>${escapeHtml(String(p.year ?? "—"))}</span></div>
      <div class="kv"><span class="k">内部 ID</span><span>#${p.id}</span></div>
      <div class="kv"><span class="k">来源</span><span><code>${escapeHtml(p.source_id || p.source || "—")}</code>${p.language ? ` <span class="lang-tag">${escapeHtml(p.language)}</span>` : ""}</span></div>
      ${p.file_name ? `<div class="kv"><span class="k">原文</span>
        <span><a class="file-link" href="/api/papers/${p.id}/file" target="_blank">${escapeHtml(p.file_name)}</a>
        （点击下载/查看 PDF）</span></div>` : ""}
      <div class="kv"><span class="k">关键词</span><span style="display:flex;flex-wrap:wrap;gap:5px">${kws}</span></div>
      <div style="margin-top:10px"><span class="k" style="color:var(--muted);font-size:12.5px">摘要</span>
        <p style="font-size:13.5px;color:var(--ink-soft);margin-top:4px">${escapeHtml(p.abstract) || "（无摘要）"}</p></div>`;
    openModal(`论文详情 #${p.id}`, body);
  } catch (err) {
    toast(`加载详情失败：${err.message}`, "err");
  }
}

// ---------------- 导入 ----------------

function bindFilePick(inputId, labelId, btnId) {
  const input = $(inputId);
  input.addEventListener("change", () => {
    const f = input.files[0];
    $(labelId).textContent = f ? `已选择：${f.name}` : "点击选择文件";
    $(labelId).parentElement.classList.toggle("has", !!f);
    $(btnId).disabled = !f;
  });
}

async function uploadSingle() {
  const file = $("#file-single").files[0];
  if (!file) return;
  const btn = $("#btn-file");
  btn.disabled = true;
  const form = new FormData();
  form.append("file", file);
  // 显式携带开关状态：勾选=AI 精修，取消=纯规则
  form.append("ai", $("#ai-single").checked ? "1" : "0");
  try {
    const d = await api("/api/papers/file", { method: "POST", body: form });
    if (d.ok === false && d.duplicate) {
      showReport("该文献已存在，未重复入库",
        `已有论文 #${d.existing.paper_id}「${d.existing.title}」内容完全一致`);
      toast(`重复导入已拦截（#${d.existing.paper_id}）`, "err");
    } else {
      showReport(`已入库「${d.paper.title}」`, `置信度 ${d.confidence}${d.ai_used ? " · AI 精修" : " · 规则拆解"}`);
    }
    resetFileInput("#file-single", "#file-single-name", "#btn-file");
    refreshStats(); loadLibrary();
  } catch (err) {
    toast(`解析失败：${err.message}`, "err");
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
      `<li><span class="ok">＋</span> ${escapeHtml(a.name)} → ${escapeHtml(a.title)}</li>`).join("");
    const duplicated = (d.duplicated || []).map((x) =>
      `<li><span class="bad">＝</span> ${escapeHtml(x.name)}：与 #${x.paper_id}「${escapeHtml(x.title)}」内容一致，已跳过</li>`).join("");
    const failed = (d.failed || []).map((f) =>
      `<li><span class="bad">－</span> ${escapeHtml(f.name)}：${escapeHtml(f.error)}</li>`).join("");
    showReport("压缩包导入完成", "");
    $("#report").insertAdjacentHTML("beforeend", `
      <div class="ok">成功入库 ${(d.added || []).length} 篇 · 内容重复跳过 ${(d.duplicated || []).length} · 失败 ${(d.failed || []).length}</div>
      <ul>${added}${duplicated}${failed}</ul>`);
    resetFileInput("#file-zip", "#file-zip-name", "#btn-zip");
    refreshStats(); loadLibrary();
  } catch (err) {
    toast(`导入失败：${err.message}`, "err");
  } finally { btn.disabled = false; }
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
  r.innerHTML = `<div class="ok"><b>${escapeHtml(head)}</b></div>
    ${sub ? `<div class="hint">${escapeHtml(sub)}</div>` : ""}`;
}

function switchTab(name) {
  $$(".tabs button").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".tabpane").forEach((p) => p.classList.toggle("active", p.id === name));
}

// ---------------- 爬虫 ----------------

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
    toast(`已启动数据采集（${source}），可查看文库状态条进度…`);
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
      badge.textContent = s.running ? `采集中 ${s.total}` : (s.message || "待机");
      badge.style.color = s.running ? "var(--accent)" : "var(--muted)";
      if (!s.running) {
        clearInterval(state.crawlTimer);
        btn.disabled = false;
        if (force || s.message.includes("完成")) {
          toast(`爬虫：${s.message}`, s.message.includes("失败") ? "err" : "ok");
          refreshStats(); loadLibrary();
          if (state.lastQuery) doSearch();
        }
      }
    } catch (_) { /* 忽略轮询错误 */ }
  }, 2000);
}

// ---------------- 事件绑定 ----------------

function bindEvents() {
  // 路由
  $$(".nav-item").forEach((n) => n.addEventListener("click", () => {
    location.hash = `#/${n.dataset.view}`;
  }));
  window.addEventListener("hashchange", parseHash);

  // 检索
  $("#btn-search").addEventListener("click", doSearch);
  $("#q").addEventListener("keydown", (e) => {
    const open = !$("#suggest").classList.contains("hidden");
    if (e.key === "Enter") { e.preventDefault(); if (open && suggestIdx >= 0) applySuggest(suggestIdx); else doSearch(); }
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
    $$("#mode-seg button").forEach((b) => b.classList.toggle("active", b === btn));
    if (state.lastQuery) doSearch();
  });

  // 中英互译开关（英文查询开启后才扩展中文同义词）
  $("#cross-toggle").addEventListener("click", () => {
    state.cross = !state.cross;
    $("#cross-toggle").classList.toggle("btn-on", state.cross);
    if (state.lastQuery) doSearch();
  });

  // 结果区：展开摘要 / 关键词跳转 / 详情
  $("#results-list").addEventListener("click", (e) => {
    const kw = e.target.closest("[data-kw]");
    if (kw) { location.hash = "#/search"; $("#q").value = kw.dataset.kw; doSearch(); return; }
    const btn = e.target.closest(".expand");
    if (!btn) return;
    const ab = btn.closest(".result").querySelector(".result-abstract");
    const open = ab.classList.toggle("expanded");
    btn.textContent = open ? "收起全文" : "展开全文";
  });

  // 文库
  $("#btn-refresh").addEventListener("click", loadLibrary);
  $("#lib-filter").addEventListener("input", () => {
    clearTimeout(window._ft);
    window._ft = setTimeout(() => {
      state.libQuery = $("#lib-filter").value.trim();
      state.libPage = 1;
      loadLibrary();
    }, 250);
  });
  $("#page-prev").addEventListener("click", () => { state.libPage = Math.max(1, state.libPage - 1); loadLibrary(); });
  $("#page-next").addEventListener("click", () => { state.libPage += 1; loadLibrary(); });
  $("#btn-goto").addEventListener("click", gotoPage);
  $("#page-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") gotoPage();
  });
  $("#lib-list").addEventListener("click", (e) => {
    const kw = e.target.closest("[data-kw]");
    if (kw) {
      location.hash = "#/search";
      $("#q").value = kw.dataset.kw;
      doSearch();
      return;
    }
    const row = e.target.closest(".paper-row");
    if (!row) return;
    const id = Number(row.dataset.id);
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "del") {
      if (!confirm(`确认删除论文 #${id} ？`)) return;
      api(`/api/papers/${id}`, { method: "DELETE" })
        .then(() => { toast(`已删除 #${id}`, "ok"); refreshStats(); loadLibrary(); })
        .catch((err) => toast(err.message, "err"));
    } else if (act === "view") {
      showPaperDetail(id);
    }
  });

  // 导入
  $$(".tabs button").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  bindFilePick("#file-single", "#file-single-name", "#btn-file");
  bindFilePick("#file-zip", "#file-zip-name", "#btn-zip");
  $("#btn-file").addEventListener("click", uploadSingle);
  $("#btn-zip").addEventListener("click", uploadZip);
  $("#btn-url").addEventListener("click", async () => {
    const url = $("#url-input").value.trim();
    if (!url) return toast("请输入 arXiv URL 或编号", "err");
    try {
      const d = await postJson("/api/papers/url", { url });
      if (d.ok === false && d.duplicate) {
        toast(`该论文已存在（#${d.existing.paper_id}），未重复入库`, "err");
      } else {
        toast(`已入库「${d.paper.title}」`, "ok");
        $("#url-input").value = "";
      }
      refreshStats(); loadLibrary();
    } catch (err) { toast(`添加失败：${err.message}`, "err"); }
  });
  $("#btn-manual").addEventListener("click", async () => {
    const payload = {
      title: $("#m-title").value.trim(),
      abstract: $("#m-abstract").value.trim(),
      authors: $("#m-authors").value.split(/[,，;；]/).map((s) => s.trim()).filter(Boolean),
      year: $("#m-year").value ? Number($("#m-year").value) : null,
    };
    if (!payload.title) return toast("请填写标题", "err");
    try {
      const d = await postJson("/api/papers/manual", payload);
      if (d.ok === false && d.duplicate) {
        toast(`该论文已存在（#${d.existing.paper_id}），未重复入库`, "err");
      } else {
        toast(`已入库「${d.paper.title}」`, "ok");
        ["#m-title", "#m-authors", "#m-year", "#m-abstract"].forEach((s) => ($(s).value = ""));
      }
      refreshStats(); loadLibrary();
    } catch (err) { toast(`添加失败：${err.message}`, "err"); }
  });

  // 爬虫
  $("#btn-crawl").addEventListener("click", async () => {
    const btn = $("#btn-crawl");
    btn.disabled = true;
    try { await startCrawl(); } catch (err) { btn.disabled = false; toast(err.message, "err"); }
  });
  pollCrawl();
}

function moveSuggest(delta) {
  const items = $$("#suggest li");
  if (!items.length) return;
  suggestIdx = (suggestIdx + delta + items.length) % items.length;
  items.forEach((li, i) => li.classList.toggle("selected", i === suggestIdx));
}

// ---------------- 初始化 ----------------

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  refreshStats();
  parseHash();
  if (!location.hash) switchView("search");
});
