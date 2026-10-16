// second-brain app.js — 原生 JS，无框架

// ---------- 工具 ----------
// ---------- 当前使用者（v0.6 多用户复习隔离） ----------
// 单机多用户简化方案：身份存在 localStorage（键 sb-user），每个请求经 X-User 头声明。
const SB_USER_KEY = "sb-user";
const SB_USERS_KEY = "sb-users";

function currentUser() {
  try {
    return localStorage.getItem(SB_USER_KEY) || "local";
  } catch {
    return "local";
  }
}

function knownUsers() {
  try {
    const raw = localStorage.getItem(SB_USERS_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter((u) => typeof u === "string") : [];
  } catch {
    return [];
  }
}

function rememberUser(u) {
  try {
    const users = [u, ...knownUsers().filter((x) => x !== u)].slice(0, 20);
    localStorage.setItem(SB_USERS_KEY, JSON.stringify(users));
  } catch {
    // 忽略存储异常
  }
}

// 与后端 NormalizeUser 对齐的归一化：去空格转小写，空→local。
function normalizeUserInput(u) {
  const t = String(u == null ? "" : u).trim().toLowerCase();
  return t === "" ? "local" : t.slice(0, 64);
}

function refreshUserDatalist() {
  const dl = $("user-datalist");
  if (!dl) return;
  dl.innerHTML = "";
  knownUsers().forEach((u) => {
    const opt = document.createElement("option");
    opt.value = u;
    dl.appendChild(opt);
  });
}

// 切换使用者：写 localStorage、记入历史、刷新输入框与联想列表，然后通知各视图按新身份刷新。
window.__sbSetUser = function (u) {
  const nu = normalizeUserInput(u);
  try {
    localStorage.setItem(SB_USER_KEY, nu);
  } catch {
    // 忽略存储异常
  }
  rememberUser(nu);
  const input = $("user-input");
  if (input) input.value = nu;
  refreshUserDatalist();
  if (typeof window.__sbOnUserChange === "function") window.__sbOnUserChange();
};
window.__sbCurrentUser = currentUser;

function initUserSwitcher() {
  const input = $("user-input");
  const btn = $("btn-user-switch");
  if (input) input.value = currentUser();
  refreshUserDatalist();
  rememberUser(currentUser());
  refreshUserDatalist();
  const apply = () => window.__sbSetUser(input ? input.value : "local");
  if (btn) btn.addEventListener("click", apply);
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        apply();
      }
    });
  }
}

// ---------- 工具 ----------
async function api(path, opts = {}) {
  const baseHeaders = { "Content-Type": "application/json", "X-User": currentUser() };
  const conf = { headers: baseHeaders, ...opts };
  conf.headers = Object.assign({}, baseHeaders, opts.headers || {});
  if (conf.body && typeof conf.body !== "string") conf.body = JSON.stringify(conf.body);
  const res = await fetch(path, conf);
  if (res.status === 204) return null;
  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const msg = (data && data.error) || (typeof data === "string" && data) || `请求失败 (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const $ = (id) => document.getElementById(id);

// ---------- 状态 ----------
const state = {
  notes: [],
  currentId: null,
  tag: "",
  view: "editor",
  attachments: [],
  search: null,
};


// ---------- 视图切换 ----------
function showView(name) {
  state.view = name;
  ["editor", "graph", "review"].forEach((v) => {
    const el = $("editor-view");
    if (!el) return;
  });
  const views = { editor: $("editor-view"), graph: $("graph-view"), review: $("review-view"), push: $("push-view") };
  Object.entries(views).forEach(([k, el]) => {
    if (el) el.hidden = k !== name;
  });
  const navNotes = $("nav-notes");
  const navReview = $("nav-review");
  const navPush = $("nav-push");
  if (navNotes) navNotes.classList.toggle("is-active", name === "editor" || name === "graph");
  if (navReview) navReview.classList.toggle("is-active", name === "review");
  if (navPush) navPush.classList.toggle("is-active", name === "push");
}
window.__sbShowView = showView;

async function loadPushSettings() {
  try {
    const s = await api("/api/push/settings");
    const set = (id, v) => { const el = $(id); if (el) el.value = v == null ? "" : v; };
    const en = $("push-enabled");
    if (en) en.checked = !!s.enabled;
    set("push-time", s.time);
    set("push-timezone", s.timezone);
    set("push-mail-to", s.mailTo);
    set("push-smtp-host", s.smtpHost);
    set("push-smtp-from", s.smtpFrom);
    set("push-webhook-url", s.webhookUrl);
  } catch (e) {
    alert("读取推送设置失败：" + (e && e.message ? e.message : e));
  }
}

async function savePushSettings() {
  const tip = $("push-save-tip");
  if (tip) tip.textContent = "";
  const en = $("push-enabled");
  const val = (id) => { const el = $(id); return el ? el.value.trim() : ""; };
  const body = {
    enabled: !!(en && en.checked),
    time: val("push-time"),
    timezone: val("push-timezone"),
    mail_to: val("push-mail-to"),
    smtp_host: val("push-smtp-host"),
    smtp_from: val("push-smtp-from"),
    webhook_url: val("push-webhook-url"),
  };
  try {
    await api("/api/push/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (tip) tip.textContent = "已保存";
  } catch (e) {
    alert("保存推送设置失败：" + (e && e.message ? e.message : e));
  }
}

async function testPushChannel(channel) {
  const box = $("push-test-result");
  if (box) {
    box.textContent = "测试中…";
    box.classList.remove("is-ok", "is-fail");
  }
  try {
    const r = await api("/api/push/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel }),
    });
    if (box) {
      if (r && r.ok) {
        box.textContent = "成功";
        box.classList.add("is-ok");
      } else {
        box.textContent = "失败：" + escapeHtml(r && r.detail ? r.detail : "未知错误");
        box.classList.add("is-fail");
      }
    }
  } catch (e) {
    if (box) {
      box.textContent = "失败：" + escapeHtml(e && e.message ? e.message : String(e));
      box.classList.add("is-fail");
    }
  }
}

async function loadPushHistory() {
  const tbody = $("push-history-body");
  const empty = $("push-history-empty");
  if (!tbody) return;
  try {
    const rows = await api("/api/push/history");
    const list = Array.isArray(rows) ? rows : [];
    tbody.innerHTML = "";
    if (list.length === 0) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    list.forEach((r) => {
      const tr = document.createElement("tr");
      const td = (v) => {
        const c = document.createElement("td");
        c.innerHTML = escapeHtml(v == null ? "" : String(v));
        return c;
      };
      tr.appendChild(td(r.date));
      tr.appendChild(td(r.channel));
      tr.appendChild(td(r.status));
      tr.appendChild(td(r.detail));
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = "";
    if (empty) {
      empty.hidden = false;
      empty.textContent = "读取推送历史失败：" + (e && e.message ? e.message : e);
    }
  }
}

const _navPush = $("nav-push");
if (_navPush) {
  _navPush.addEventListener("click", () => {
    showView("push");
    loadPushSettings();
    loadPushHistory();
    window.__sbRefreshWebPush?.();
  });
}
const _btnPushSave = $("btn-push-save");
if (_btnPushSave) _btnPushSave.addEventListener("click", savePushSettings);
const _btnPushTestSmtp = $("btn-push-test-smtp");
if (_btnPushTestSmtp) _btnPushTestSmtp.addEventListener("click", () => testPushChannel("smtp"));
const _btnPushTestWebhook = $("btn-push-test-webhook");
if (_btnPushTestWebhook) _btnPushTestWebhook.addEventListener("click", () => testPushChannel("webhook"));

// ---------- 列表 ----------
async function loadNotes() {
  const q = state.tag ? `?tag=${encodeURIComponent(state.tag)}` : "";
  try {
    const data = await api(`/api/notes${q}`);
    state.notes = Array.isArray(data) ? data : (data && data.notes) || [];
  } catch (e) {
    state.notes = [];
    console.error("加载笔记失败", e);
  }
  renderList();
}

function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightText(text, terms) {
  const safe = escapeHtml(text);
  if (!terms || !terms.length) return safe;
  const valid = terms.filter((t) => t != null && String(t).length);
  if (!valid.length) return safe;
  const pattern = valid.map((t) => escapeRegExp(String(t))).join("|");
  const re = new RegExp(`(${pattern})`, "gi");
  return safe.replace(re, `<mark class="search-mark">$1</mark>`);
}

function matchSnippet(body, terms) {
  const raw = String(body || "").replace(/\s+/g, " ");
  const valid = (terms || []).filter((t) => t != null && String(t).length);
  let start = -1;
  let hitLen = 0;
  for (const t of valid) {
    const idx = raw.toLowerCase().indexOf(String(t).toLowerCase());
    if (idx !== -1 && (start === -1 || idx < start)) {
      start = idx;
      hitLen = String(t).length;
    }
  }
  if (start === -1) {
    return highlightText(raw.slice(0, 60), terms);
  }
  const from = Math.max(0, start - 30);
  const to = Math.min(raw.length, start + hitLen + 30);
  const prefix = from > 0? "…": "";
  const suffix = to < raw.length? "…": "";
  return prefix + highlightText(raw.slice(from, to), terms) + suffix;
}

function renderList() {
  const listEl = $("note-list");
  const countEl = $("list-count");
  const titleEl = $("list-title");
  if (!listEl) return;

  const search = state.search;
  if (titleEl) titleEl.textContent = search
    ? `搜索"${search.q}"`
    : (state.tag? `#${state.tag}`: "全部笔记");
  if (countEl) countEl.textContent = search
    ? `找到 ${state.notes.length} 篇`
    : `共 ${state.notes.length} 篇`;

  if (!state.notes.length) {
    listEl.innerHTML = `<div class="empty-hint">还没有笔记，点上面「新建」写一条吧</div>`;
    return;
  }

  listEl.innerHTML = state.notes
    .map((n, i) => {
      const tags = (n.tags || []).map((t) => `<span class="chip">${escapeHtml(t)}</span>`).join("");
      const date = n.updated_at? new Date(n.updated_at).toLocaleDateString("zh-CN"): "";
      const active = n.id === state.currentId? " is-active": "";
      let titleHtml;
      let bodyHtml;
      let reasonsHtml = "";
      if (search) {
        const terms = search.terms || [];
        titleHtml = highlightText(n.title || "无标题", terms);
        bodyHtml = matchSnippet(n.body || "", terms);
        const meta = search.meta && search.meta[i];
        if (meta && Array.isArray(meta.fields) && meta.fields.length) {
          const joined = meta.fields.map((f) => escapeHtml(String(f))).join(" · ");
          reasonsHtml = `<div class="match-reasons">命中：${joined}</div>`;
        }
      } else {
        const body = (n.body || "").slice(0, 60).replace(/\s+/g, " ");
        titleHtml = escapeHtml(n.title || "无标题");
        bodyHtml = escapeHtml(body);
      }
      return `<div class="note-item${active}" data-id="${n.id}">
        <div class="note-item-title">${titleHtml}</div>
        <div class="note-item-body">${bodyHtml}</div>
        <div class="note-item-foot">
          <div class="note-item-tags">${tags}</div>
          <div class="note-item-date">${escapeHtml(date)}</div>
        </div>
        ${reasonsHtml}
      </div>`;
    })
    .join("");

  listEl.querySelectorAll(".note-item").forEach((el) => {
    el.addEventListener("click", () => selectNote(Number(el.dataset.id)));
  });
}


// ---------- 选中笔记 ----------
async function selectNote(id) {
  try {
    const n = await api(`/api/notes/${id}`);
    state.currentId = n.id;
    if ($("editor-title")) $("editor-title").value = n.title || "";
    if ($("editor-body")) $("editor-body").value = n.body || "";
    if ($("editor-tags")) $("editor-tags").value = (n.tags || []).join(", ");
    if ($("editor-pinned")) $("editor-pinned").checked = !!n.pinned;
    const pv = $("preview-box");
    const body = $("editor-body");
    if (pv) pv.hidden = true;
    if (body) body.hidden = false;
    renderList();
    loadAttachments();
    loadBacklinks();
  } catch (e) {
    alert("打开失败：" + e.message);
  }
}

// ---------- 新建 / 保存 / 删除 ----------
function newNote() {
  state.currentId = null;
  if ($("editor-title")) $("editor-title").value = "";
  if ($("editor-body")) $("editor-body").value = "";
  if ($("editor-tags")) $("editor-tags").value = "";
  if ($("editor-pinned")) $("editor-pinned").checked = false;
  const pv = $("preview-box");
  const body = $("editor-body");
  if (pv) pv.hidden = true;
  if (body) body.hidden = false;
  renderList();
  state.attachments = [];
  renderAttachments();
  loadBacklinks();
  if ($("editor-title")) $("editor-title").focus();
}

async function saveNote() {
  const title = ($("editor-title")?.value || "").trim();
  const body = $("editor-body")?.value || "";
  const rawTags = ($("editor-tags")?.value || "").split(",");
  const tags = [...new Set(rawTags.map((t) => t.trim()).filter(Boolean))];
  const pinned = !!$("editor-pinned")?.checked;

  if (!title && !body.trim()) {
    alert("标题和内容都是空的，先写点啥吧");
    return;
  }

  const payload = { title, body, tags, pinned };
  try {
    let saved;
    if (state.currentId) {
      saved = await api(`/api/notes/${state.currentId}`, { method: "PUT", body: payload });
    } else {
      saved = await api("/api/notes", { method: "POST", body: payload });
    }
    if (saved && saved.id) state.currentId = saved.id;
    await Promise.all([loadNotes(), loadTags(), loadStats()]);
    if (state.view === "graph") drawGraph();
  } catch (e) {
    const offline = !navigator.onLine || /failed to fetch|networkerror|load failed/i.test(e.message || "");
    if (offline) {
      await window.__sbOfflineQueue?.enqueue({method: state.currentId ? "PUT" : "POST", url: state.currentId ? `/api/notes/${state.currentId}` : "/api/notes", headers: {"Content-Type":"application/json","X-User": currentUser()}, body: JSON.stringify(payload)});
      alert("现在没网，已把这次修改排进队列，联网后自动同步");
      return;
    }
    alert("保存失败：" + e.message);
  }
}

async function clearEditorAndRefresh() {
  state.currentId = null;
  if ($("editor-title")) $("editor-title").value = "";
  if ($("editor-body")) $("editor-body").value = "";
  if ($("editor-tags")) $("editor-tags").value = "";
  if ($("editor-pinned")) $("editor-pinned").checked = false;
  await Promise.all([loadNotes(), loadTags(), loadStats()]);
}

async function deleteNote() {
  if (!state.currentId) {
    alert("还没选中笔记呢");
    return;
  }
  if (!confirm("确定要删掉这条笔记吗？删了就找不回来了。")) return;
  try {
    await api(`/api/notes/${state.currentId}`, { method: "DELETE" });
    await clearEditorAndRefresh();
  } catch (e) {
    const offline = !navigator.onLine || /failed to fetch|networkerror|load failed/i.test(e.message || "");
    if (offline) {
      await window.__sbOfflineQueue?.enqueue({method:"DELETE", url:`/api/notes/${state.currentId}`, headers:{"X-User": currentUser()}, body: null});
      alert("现在没网，已把删除排进队列，联网后自动同步");
      await clearEditorAndRefresh();
      return;
    }
    alert("删除失败：" + e.message);
  }
}

// ---------- 搜索 ----------
let searchTimer = null;

async function doSearch() {
  const q = ($("search-input")?.value || "").trim();
  if (!q) {
    state.search = null;
    await loadNotes();
    return;
  }
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
    state.notes = Array.isArray(data)? data: (data && data.notes) || [];
    state.search = {
      q,
      terms: (data && data.terms) || [],
      meta: (data && data.meta) || [],
    };
  } catch (e) {
    console.error("搜索失败", e);
    state.notes = [];
    state.search = null;
  }
  renderList();
}


// ---------- 标签 ----------
async function loadTags() {
  try {
    const data = await api("/api/tags");
    state.tags = Array.isArray(data) ? data : (data && data.tags) || [];
  } catch (e) {
    state.tags = [];
  }
  renderTags();
}

function renderTags() {
  const el = $("tag-list");
  if (!el) return;
  const allActive = state.tag === "" ? " is-active" : "";
  const total = state.notes.length;
  let html = `<span class="chip tag-chip${allActive}" data-tag="">全部</span>`;
  html += (state.tags || [])
    .map((t) => {
      const name = typeof t === "string" ? t : t.name;
      const count = typeof t === "string" ? "" : t.count;
      const active = state.tag === name ? " is-active" : "";
      return `<span class="chip tag-chip${active}" data-tag="${escapeHtml(name)}">${escapeHtml(name)}${count != null ? ` <b>${count}</b>` : ""}</span>`;
    })
    .join("");
  el.innerHTML = html;

  el.querySelectorAll(".tag-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.tag = chip.dataset.tag || "";
      if ($("search-input")) $("search-input").value = "";
      loadNotes();
      renderTags();
    });
  });
}

// ---------- 统计 ----------
async function loadStats() {
  try {
    const s = await api("/api/stats");
    if ($("stat-notes")) $("stat-notes").textContent = s.notes ?? 0;
    if ($("stat-tags")) $("stat-tags").textContent = s.tags ?? 0;
    if ($("stat-links")) $("stat-links").textContent = s.links ?? 0;
    if ($("stat-words")) $("stat-words").textContent = s.words ?? 0;
  } catch (e) {
    console.error("统计加载失败", e);
  }
}

// ---------- 预览 ----------
async function togglePreview() {
  const pv = $("preview-box");
  const body = $("editor-body");
  if (!pv || !body) return;

  if (!pv.hidden) {
    pv.hidden = true;
    body.hidden = false;
    return;
  }
  if (!state.currentId) {
    alert("先保存再预览吧");
    return;
  }
  try {
    const data = await api(`/api/notes/${state.currentId}/preview`);
    const html = typeof data === "string" ? data : (data && data.html) || "";
    pv.innerHTML = html;
    pv.hidden = false;
    body.hidden = true;
  } catch (e) {
    alert("预览失败：" + e.message);
  }
}

// ---------- 图谱 ----------
async function drawGraph() {
  const canvas = $("graph-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  let data;
  try {
    data = await api("/api/graph");
  } catch (e) {
    console.error("图谱加载失败", e);
    return;
  }

  const nodes = (data && data.nodes) || [];
  const edges = (data && data.edges) || [];

  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 800;
  const h = canvas.clientHeight || 500;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fafafa";
  ctx.fillRect(0, 0, w, h);

  if (!nodes.length) {
    ctx.fillStyle = "#999";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("还没有笔记，画不出图", w / 2, h / 2);
    return;
  }

  const cx = w / 2;
  const cy = h / 2;
  const R = Math.min(w, h) / 2 - 60;
  const pos = {};
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  });

  // 连线
  ctx.strokeStyle = "#c8c8c8";
  ctx.lineWidth = 1;
  edges.forEach((e) => {
    const a = pos[e.source ?? e.from];
    const b = pos[e.target ?? e.to];
    if (!a || !b) return;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  });

  // 节点
  nodes.forEach((n) => {
    const p = pos[n.id];
    const isCur = n.id === state.currentId;
    ctx.beginPath();
    ctx.arc(p.x, p.y, isCur ? 10 : 7, 0, Math.PI * 2);
    ctx.fillStyle = isCur ? "#2b7de9" : "#7aa9e0";
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = "#333";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const label = (n.title || "无标题").slice(0, 10);
    ctx.fillText(label, p.x, p.y + 12);
  });
}

// ---------- 附件 ----------
function formatSize(bytes) {
  if (bytes == null) return "";
  const b = Number(bytes);
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

async function loadAttachments() {
  if (!state.currentId) {
    state.attachments = [];
    renderAttachments();
    return;
  }
  try {
    const data = await api(`/api/notes/${state.currentId}/attachments`);
    state.attachments = Array.isArray(data) ? data : [];
  } catch (e) {
    console.error("附件加载失败", e);
    state.attachments = [];
  }
  renderAttachments();
}

function renderAttachments() {
  const listEl = $("attach-list");
  const countEl = $("attach-count");
  if (!listEl) return;
  const atts = state.attachments || [];
  if (countEl) countEl.textContent = atts.length ? `共 ${atts.length} 个` : "";
  if (!atts.length) {
    listEl.innerHTML = `<li class="empty-hint">还没有附件，选个文件传上来吧</li>`;
    return;
  }
  listEl.innerHTML = atts
    .map((a) => {
      const isImg = (a.mime || "").startsWith("image/");
      const thumb = isImg
        ? `<img class="attach-thumb" src="/api/attachments/${a.id}" alt="" loading="lazy">`
        : `<span class="attach-thumb attach-thumb-file">${escapeHtml((a.filename || "?").slice(-4))}</span>`;
      return `<li class="attach-item" data-id="${a.id}">
        ${thumb}
        <div class="attach-info">
          <div class="attach-name">${escapeHtml(a.filename || "未命名")}</div>
          <div class="attach-meta">${escapeHtml(a.mime || "")} · ${formatSize(a.size)}</div>
        </div>
        <div class="attach-actions">
          <button type="button" data-act="insert">插入引用</button>
          <button type="button" data-act="download">下载</button>
          <button type="button" data-act="delete">删除</button>
        </div>
      </li>`;
    })
    .join("");
  listEl.querySelectorAll(".attach-item").forEach((el) => {
    const id = Number(el.dataset.id);
    const att = atts.find((x) => x.id === id);
    el.querySelector('[data-act="insert"]')?.addEventListener("click", () => insertAttachmentRef(att));
    el.querySelector('[data-act="download"]')?.addEventListener("click", () => {
      window.open(`/api/attachments/${id}`, "_blank");
    });
    el.querySelector('[data-act="delete"]')?.addEventListener("click", () => deleteAttachment(id));
  });
}

// ---------- 反向链接 ----------
async function loadBacklinks() {
  if (!state.currentId) {
    renderBacklinks([]);
    return;
  }
  try {
    const data = await api(`/api/notes/${state.currentId}/backlinks`);
    renderBacklinks(Array.isArray(data) ? data : []);
  } catch (e) {
    console.error("反向链接加载失败", e);
    renderBacklinks([]);
  }
}

function renderBacklinks(items) {
  const listEl = $("backlink-list");
  const countEl = $("backlink-count");
  if (!listEl) return;
  const bls = items || [];
  if (countEl) countEl.textContent = bls.length ? `共 ${bls.length} 篇` : "";
  if (!state.currentId) {
    listEl.innerHTML = `<li class="empty-hint">选中一篇笔记，这里会列出引用它的笔记</li>`;
    return;
  }
  if (!bls.length) {
    listEl.innerHTML = `<li class="empty-hint">还没有笔记引用这一篇</li>`;
    return;
  }
  listEl.innerHTML = bls
    .map(
      (b) => `<li class="backlink-item" data-id="${b.id}">
        <div class="backlink-title">${escapeHtml(b.title || "无标题")}</div>
        <div class="backlink-snippet">${escapeHtml(b.snippet || "")}</div>
      </li>`
    )
    .join("");
  listEl.querySelectorAll(".backlink-item").forEach((el) => {
    el.addEventListener("click", () => selectNote(Number(el.dataset.id)));
  });
}

function insertAttachmentRef(att) {
  if (!att) return;
  const body = $("editor-body");
  if (!body) return;
  const name = att.filename || "附件";
  const ref = (att.mime || "").startsWith("image/")
    ? `![${name}](attachment:${att.id})`
    : `[${name}](attachment:${att.id})`;
  const cur = body.value || "";
  body.value = cur && !cur.endsWith("\n") ? cur + "\n" + ref + "\n" : cur + ref + "\n";
  body.focus();
}

async function uploadAttachment() {
  const input = $("attach-file");
  const btn = $("btn-attach-upload");
  if (!input || !input.files || !input.files.length) {
    alert("先选个文件吧");
    return;
  }
  if (!state.currentId) {
    alert("先保存笔记再传附件吧");
    return;
  }
  const fd = new FormData();
  fd.append("file", input.files[0]);
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/notes/${state.currentId}/attachments`, { method: "POST", body: fd });
    if (res.status === 204) {
      input.value = "";
      await loadAttachments();
      return;
    }
    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch { data = text; }
    }
    if (!res.ok) {
      const msg = (data && data.error) || `上传失败 (${res.status})`;
      throw new Error(msg);
    }
    input.value = "";
    await loadAttachments();
  } catch (e) {
    alert("上传失败：" + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function deleteAttachment(id) {
  if (!confirm("确定删除这个附件吗？")) return;
  try {
    await api(`/api/attachments/${id}`, { method: "DELETE" });
    await loadAttachments();
  } catch (e) {
    alert("删除失败：" + e.message);
  }
}

// ---------- 事件绑定 ----------

// ---------- 事件绑定 ----------
function bindEvents() {
  $("btn-new")?.addEventListener("click", newNote);
  $("btn-save")?.addEventListener("click", saveNote);
  $("btn-delete")?.addEventListener("click", deleteNote);
  $("btn-preview")?.addEventListener("click", togglePreview);
  $("btn-attach-upload")?.addEventListener("click", uploadAttachment);
  $("btn-export-md")?.addEventListener("click", () => {
    window.location.href = "/api/export/markdown";
  });
  $("btn-export-json")?.addEventListener("click", () => {
    window.location.href = "/api/export/json";
  });

  $("btn-graph")?.addEventListener("click", () => {
    showView("graph");
    drawGraph();
  });
  $("btn-graph-close")?.addEventListener("click", () => showView("editor"));

  $("btn-review-exit")?.addEventListener("click", () => showView("editor"));

  const search = $("search-input");
  if (search) {
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        clearTimeout(searchTimer);
        doSearch();
      }
    });
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(doSearch, 300);
    });
  }

  initUserSwitcher();
  $("nav-notes")?.addEventListener("click", () => showView("editor"));
  $("nav-review")?.addEventListener("click", () => {
    showView("review");
    window.__sbStartReview?.();
  });
}

// ---------- 初始化 ----------
async function init() {
  window.__sbPwaInit?.();
  window.__sbOnQueueSynced = async (ok) => { if (ok > 0) await Promise.all([loadNotes(), loadTags(), loadStats()]); };
  bindEvents();
  await Promise.all([loadNotes(), loadTags(), loadStats()]);
  if (window.location.hash === "#review") {
    showView("review");
    window.__sbStartReview?.();
  } else {
    showView("editor");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

/*
用到的 id 清单（附件与导出）：
  attach-list, attach-count, attach-file, btn-attach-upload
  btn-export-md, btn-export-json

用到的 id 清单：
  editor-view, graph-view, review-view
  nav-notes, nav-review
  note-list, list-count, list-title
  search-input
  tag-list
  editor-title, editor-body, editor-tags, editor-pinned
  preview-box
  btn-new, btn-save, btn-delete, btn-preview
  btn-graph, btn-graph-close
  btn-review-exit
  graph-canvas
  stat-notes, stat-tags, stat-links, stat-words
*/
