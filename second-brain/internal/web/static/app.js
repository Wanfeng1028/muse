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
  const views = { editor: $("editor-view"), graph: $("graph-view"), review: $("review-view"), push: $("push-view"), stats: $("stats-view") };
  Object.entries(views).forEach(([k, el]) => {
    if (el) el.hidden = k !== name;
  });
  const navNotes = $("nav-notes");
  const navReview = $("nav-review");
  const navPush = $("nav-push");
  if (navNotes) navNotes.classList.toggle("is-active", name === "editor" || name === "graph");
  if (navReview) navReview.classList.toggle("is-active", name === "review");
  if (navPush) navPush.classList.toggle("is-active", name === "push");
  const navStats = $("nav-stats");
  if (navStats) navStats.classList.toggle("is-active", name === "stats");
  if (name === "stats") loadReviewStatsView();
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

  // 图谱视图变换状态挂在 canvas 元素上，避免新增顶层变量；drawGraph 每次重绘都读取它
  if (!canvas._gz) canvas._gz = { scale: 1, tx: 0, ty: 0 };
  const gz = canvas._gz;

  let data;
  try {
    data = await api("/api/graph");
  } catch (e) {
    console.error("图谱加载失败", e);
    return;
  }

  const nodes = (data && data.nodes) || [];
  const edges = (data && data.edges) || [];

  // 孤立节点聚合：统计每个节点的度，度 0 即为孤立
  const degree = {};
  nodes.forEach((n) => { degree[n.id] = 0; });
  edges.forEach((e) => {
    const s = e.source ?? e.from;
    const t = e.target ?? e.to;
    if (degree[s] !== undefined) degree[s] += 1;
    if (degree[t] !== undefined) degree[t] += 1;
  });
  const isolated = nodes.filter((n) => degree[n.id] === 0);
  // 孤立节点 >= 8 个才聚合，小图没必要
  if (isolated.length >= 8) {
    const isolatedIds = {};
    isolated.forEach((n) => { isolatedIds[n.id] = true; });
    const members = isolated.map((n) => n.id);
    for (let i = nodes.length - 1; i >= 0; i--) {
      if (isolatedIds[nodes[i].id]) nodes.splice(i, 1);
    }
    nodes.push({
      id: "__isolated__",
      title: "孤立笔记 x" + isolated.length,
      isolated: true,
      members: members,
    });
  }

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
  // 初始位置：按序号排成圆（确定性，无随机抖动）
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(angle), y: cy + R * Math.sin(angle) };
  });

  // 力导向布局：同步迭代一次算完，canvas 静态渲染不做动画
  // 复杂度 O(n^2)，300 节点约 1350 万次运算，JS 秒级内可接受；
  // 节点数继续增长时建议改为空间网格近似或降迭代次数。
  if (nodes.length > 1) {
    const k = 90;
    const iters = nodes.length > 200 ? 60 : 150;
    const maxStep = 12;
    for (let it = 0; it < iters; it++) {
      const disp = {};
      nodes.forEach((n) => { disp[n.id] = { x: 0, y: 0 }; });
      // 斥力：每对节点 F = k*k / dist，方向推开
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = pos[nodes[i].id];
          const b = pos[nodes[j].id];
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 1) dist = 1;
          const f = (k * k) / dist;
          const ux = dx / dist;
          const uy = dy / dist;
          disp[nodes[i].id].x += ux * f;
          disp[nodes[i].id].y += uy * f;
          disp[nodes[j].id].x -= ux * f;
          disp[nodes[j].id].y -= uy * f;
        }
      }
      // 引力：每条边 F = dist*dist / k * 0.02，沿边拉近
      edges.forEach((e) => {
        const s = e.source ?? e.from;
        const t = e.target ?? e.to;
        const a = pos[s];
        const b = pos[t];
        if (!a || !b) return;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 1) dist = 1;
        const f = (dist * dist) / k * 0.02;
        const ux = dx / dist;
        const uy = dy / dist;
        disp[s].x -= ux * f;
        disp[s].y -= uy * f;
        disp[t].x += ux * f;
        disp[t].y += uy * f;
      });
      // 重力：向心小力 0.01 * (中心 - 位置)，防飞散
      nodes.forEach((n) => {
        const p = pos[n.id];
        disp[n.id].x += 0.01 * (cx - p.x);
        disp[n.id].y += 0.01 * (cy - p.y);
      });
      // 位移钳制：单次迭代单节点位移不超过 12px
      nodes.forEach((n) => {
        const d = disp[n.id];
        let len = Math.sqrt(d.x * d.x + d.y * d.y);
        if (len > maxStep) {
          d.x = d.x / len * maxStep;
          d.y = d.y / len * maxStep;
        }
        pos[n.id].x += d.x;
        pos[n.id].y += d.y;
      });
    }
    // 平移缩放进画布：留 40px 边距，按包围盒等比 fit
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach((n) => {
      const p = pos[n.id];
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    });
    const spanX = Math.max(maxX - minX, 1);
    const spanY = Math.max(maxY - minY, 1);
    const targetW = w - 80;
    const targetH = h - 80;
    const scale = Math.min(targetW / spanX, targetH / spanY);
    const offX = 40 + (targetW - spanX * scale) / 2 - minX * scale;
    const offY = 40 + (targetH - spanY * scale) / 2 - minY * scale;
    nodes.forEach((n) => {
      const p = pos[n.id];
      p.x = p.x * scale + offX;
      p.y = p.y * scale + offY;
    });
  }

  // 世界/屏幕坐标换算
  const toScreen = (x, y) => ({ sx: x * gz.scale + gz.tx, sy: y * gz.scale + gz.ty });
  const toWorld = (mx, my) => ({ wx: (mx - gz.tx) / gz.scale, wy: (my - gz.ty) / gz.scale });

  let hoverId = canvas._hoverId || null;

  const hitTest = (mx, my) => {
    let found = null;
    nodes.forEach((n) => {
      const p = pos[n.id];
      if (!p) return;
      const s = toScreen(p.x, p.y);
      const isCur = n.id === state.currentId;
      const isIso = n.id === "__isolated__";
      const r = isCur ? 10 : isIso ? 13 : 7;
      const dx = mx - s.sx;
      const dy = my - s.sy;
      if (dx * dx + dy * dy <= (r + 4) * (r + 4)) found = n;
    });
    return found;
  };

  const render = () => {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(gz.tx, gz.ty);
    ctx.scale(gz.scale, gz.scale);

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
    const boxes = [];
    nodes.forEach((n) => {
      const p = pos[n.id];
      if (!p) return;
      const isCur = n.id === state.currentId;
      const isIso = n.id === "__isolated__";
      const r = isCur ? 10 : isIso ? 13 : 7;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = isCur ? "#0f766e" : "#7fb8ae";
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 2;
      ctx.stroke();

      const label = (n.title || "无标题").slice(0, 10);
      const lw = label.length * 12;
      const lx = p.x - lw / 2;
      const ly = p.y + 12;
      let skip = false;
      if (!isCur && !isIso) {
        for (const b of boxes) {
          if (lx < b.x + b.w && lx + lw > b.x && ly < b.y + b.h && ly + 12 > b.y) {
            skip = true;
            break;
          }
        }
      }
      if (!skip) {
        boxes.push({ x: lx, y: ly, w: lw, h: 12 });
        ctx.fillStyle = "#333";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillText(label, p.x, p.y + 12);
      }
    });

    ctx.restore();

    // 悬停浮层（屏幕坐标）
    if (hoverId && pos[hoverId.id]) {
      const s = toScreen(pos[hoverId.id].x, pos[hoverId.id].y);
      const title = (hoverId.title || "无标题").slice(0, 20);
      ctx.font = "12px sans-serif";
      const tw = ctx.measureText(title).width;
      const sub = "双击打开笔记";
      ctx.font = "11px sans-serif";
      const sw = ctx.measureText(sub).width;
      const pw = Math.max(tw, sw) + 16;
      const ph = 40;
      let px = s.sx + 14;
      let py = s.sy - ph / 2;
      if (px + pw > w) px = s.sx - pw - 14;
      if (px < 0) px = 0;
      if (py < 0) py = 0;
      if (py + ph > h) py = h - ph;
      ctx.beginPath();
      const rr = 6;
      ctx.moveTo(px + rr, py);
      ctx.lineTo(px + pw - rr, py);
      ctx.quadraticCurveTo(px + pw, py, px + pw, py + rr);
      ctx.lineTo(px + pw, py + ph - rr);
      ctx.quadraticCurveTo(px + pw, py + ph, px + pw - rr, py + ph);
      ctx.lineTo(px + rr, py + ph);
      ctx.quadraticCurveTo(px, py + ph, px, py + ph - rr);
      ctx.lineTo(px, py + rr);
      ctx.quadraticCurveTo(px, py, px + rr, py);
      ctx.closePath();
      ctx.fillStyle = "#fff";
      ctx.fill();
      ctx.strokeStyle = "#ddd";
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = "#333";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(title, px + 8, py + 6);
      ctx.fillStyle = "#999";
      ctx.font = "11px sans-serif";
      ctx.fillText(sub, px + 8, py + 24);
    }
  };

  if (!canvas._gbound) {
    canvas._gbound = true;

    canvas.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        const rect = canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        const before = toWorld(mx, my);
        const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
        let ns = gz.scale * factor;
        if (ns < 0.3) ns = 0.3;
        if (ns > 4) ns = 4;
        gz.scale = ns;
        gz.tx = mx - before.wx * gz.scale;
        gz.ty = my - before.wy * gz.scale;
        render();
      },
      { passive: false }
    );

    let dragging = false;
    let lastX = 0;
    let lastY = 0;

    canvas.addEventListener("mousedown", (ev) => {
      dragging = true;
      lastX = ev.clientX;
      lastY = ev.clientY;
    });

    canvas.addEventListener("mousemove", (ev) => {
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      if (dragging) {
        gz.tx += ev.clientX - lastX;
        gz.ty += ev.clientY - lastY;
        lastX = ev.clientX;
        lastY = ev.clientY;
        render();
        return;
      }
      const hit = hitTest(mx, my);
      const nid = hit ? hit.id : null;
      if (nid !== hoverId) {
        hoverId = hit;
        canvas._hoverId = hoverId;
        render();
      }
    });

    canvas.addEventListener("mouseup", () => {
      dragging = false;
    });

    canvas.addEventListener("mouseleave", () => {
      dragging = false;
      if (hoverId) {
        hoverId = null;
        canvas._hoverId = null;
        render();
      }
    });

    canvas.addEventListener("dblclick", () => {
      // 双击暂不跳转，后续在此接入打开笔记逻辑
    });
  }

  render();
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
  $("nav-stats")?.addEventListener("click", () => showView("stats"));
  $("btn-stats-close")?.addEventListener("click", () => showView("editor"));
}

// ---------- 复习统计 ----------
async function loadReviewStatsView() {
  try {
    const [trendRes, masteryRes, heatmapRes, healthRes, streakRes, forecastRes, overdueRes] = await Promise.all([
      api("/api/review/trend?days=7"),
      api("/api/review/mastery"),
      api("/api/review/heatmap?days=365").catch(() => { console.error("热力图加载失败"); return null; }),
      api("/api/review/health").catch(() => { console.error("记忆健康加载失败"); return null; }),
      api("/api/review/streak").catch(() => { console.error("打卡连续加载失败"); return null; }),
      api("/api/review/forecast?days=7").catch(() => { console.error("未来到期预测加载失败"); return null; }),
      api("/api/review/overdue?limit=50").catch(() => { console.error("逾期明细加载失败"); return null; }),
    ]);
    drawTrend(trendRes && trendRes.trend ? trendRes.trend : []);
    renderMastery(masteryRes && masteryRes.mastery ? masteryRes.mastery : []);
    renderHeatmap(heatmapRes && heatmapRes.heatmap ? heatmapRes.heatmap : null);
    renderHealth(healthRes);
    renderStreak(streakRes);
    renderForecast(forecastRes);
    renderOverdue(overdueRes);
  } catch (e) {
    console.error("复习统计加载失败", e);
  }
}

function renderStreak(data) {
  const summary = document.getElementById("streak-summary");
  const empty = document.getElementById("streak-empty");
  if (!summary) return;
  while (summary.firstChild) summary.removeChild(summary.firstChild);
  if (!data || !data.totalDays) {
    summary.style.display = "none";
    if (empty) empty.hidden = false;
    return;
  }
  summary.style.display = "";
  if (empty) empty.hidden = true;
  const items = [
    { num: (data.currentStreak || 0) + " 天", label: "当前连续" },
    { num: (data.longestStreak || 0) + " 天", label: "历史最长" },
    { num: String(data.totalDays || 0), label: "累计复习天数" },
    { num: data.lastReviewedDate || "还没有记录", label: "最近复习日" }
  ];
  for (const item of items) {
    const chip = document.createElement("div");
    chip.className = "health-chip";
    const numSpan = document.createElement("span");
    numSpan.className = "health-chip-num";
    numSpan.textContent = item.num;
    const labelSpan = document.createElement("span");
    labelSpan.className = "health-chip-label";
    labelSpan.textContent = item.label;
    chip.appendChild(numSpan);
    chip.appendChild(labelSpan);
    summary.appendChild(chip);
  }
}
function renderOverdue(items) {
  const list = document.getElementById('overdue-list');
  const empty = document.getElementById('overdue-empty');
  if (!list || !empty) return;
  if (!items) return;
  list.textContent = '';
  if (items.length === 0) {
    empty.style.display = '';
    return;
  }
  empty.style.display = 'none';
  for (const item of items) {
    const row = document.createElement('li');
    row.className = 'overdue-row';
    const title = document.createElement('span');
    title.className = 'overdue-title';
    title.textContent = item.title;
    const meta = document.createElement('span');
    meta.className = 'overdue-meta';
    meta.textContent = '逾期 ' + item.overdueDays + ' 天 · 到期 ' + item.dueDate;
    row.append(title, meta);
    list.append(row);
  }
}
function renderForecast(data) {
  const summary = document.getElementById("forecast-summary");
  const list = document.getElementById("forecast-list");
  const empty = document.getElementById("forecast-empty");
  if (!summary || !list) return;
  while (summary.firstChild) summary.removeChild(summary.firstChild);
  while (list.firstChild) list.removeChild(list.firstChild);
  if (data == null) {
    summary.style.display = "none";
    if (empty) empty.hidden = true;
    return;
  }
  if (data.total === 0 || !data.forecast || data.forecast.length === 0) {
    summary.style.display = "none";
    empty.hidden = false;
    return;
  }
  summary.style.display = "";
  empty.hidden = true;
  const chip1 = document.createElement("div");
  chip1.className = "health-chip";
  const num1 = document.createElement("span");
  num1.className = "health-chip-num";
  num1.textContent = data.overdue + " 条";
  const label1 = document.createElement("span");
  label1.className = "health-chip-label";
  label1.textContent = "已逾期";
  chip1.appendChild(num1);
  chip1.appendChild(label1);
  summary.appendChild(chip1);
  const totalDue = data.forecast.reduce((s, d) => s + d.due, 0);
  const chip2 = document.createElement("div");
  chip2.className = "health-chip";
  const num2 = document.createElement("span");
  num2.className = "health-chip-num";
  num2.textContent = totalDue + " 条";
  const label2 = document.createElement("span");
  label2.className = "health-chip-label";
  label2.textContent = "未来 7 天到期";
  chip2.appendChild(num2);
  chip2.appendChild(label2);
  summary.appendChild(chip2);
  const chip3 = document.createElement("div");
  chip3.className = "health-chip";
  const num3 = document.createElement("span");
  num3.className = "health-chip-num";
  num3.textContent = data.total + " 条";
  const label3 = document.createElement("span");
  label3.className = "health-chip-label";
  label3.textContent = "待处理合计";
  chip3.appendChild(num3);
  chip3.appendChild(label3);
  summary.appendChild(chip3);
  const maxDue = Math.max(...data.forecast.map(d => d.due));
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  for (const item of data.forecast) {
    const row = document.createElement("div");
    row.className = "forecast-row";
    const dateSpan = document.createElement("span");
    dateSpan.className = "forecast-date";
    const dayIdx = new Date(item.date + "T00:00:00").getDay();
    dateSpan.textContent = item.date.slice(5) + " " + weekdays[dayIdx];
    row.appendChild(dateSpan);
    const barWrap = document.createElement("div");
    barWrap.className = "forecast-bar-wrap";
    const bar = document.createElement("div");
    bar.className = "forecast-bar";
    const pct = maxDue === 0 ? 0 : Math.round(item.due / maxDue * 100);
    bar.style.width = pct + "%";
    barWrap.appendChild(bar);
    row.appendChild(barWrap);
    const countSpan = document.createElement("span");
    countSpan.className = "forecast-count";
    countSpan.textContent = item.due + " 条";
    row.appendChild(countSpan);
    list.appendChild(row);
  }
}


// 记忆健康：汇总数字 + EF 分布条 + 需关注卡片 + 大白话建议
function renderHealth(data) {
  const summaryEl = document.getElementById("health-summary");
  const efEl = document.getElementById("health-ef");
  const attEl = document.getElementById("health-attention");
  const advEl = document.getElementById("health-advice");
  const emptyEl = document.getElementById("health-empty");
  if (!summaryEl) return;
  summaryEl.innerHTML = "";
  efEl.innerHTML = "";
  attEl.innerHTML = "";
  advEl.innerHTML = "";
  if (!data || !data.total) {
    summaryEl.style.display = "none";
    efEl.style.display = "none";
    emptyEl.hidden = false;
    return;
  }
  summaryEl.style.display = "";
  efEl.style.display = "";
  emptyEl.hidden = true;
  const chips = [
    ["今日到期", data.dueNow || 0],
    ["逾期 7 天以上", data.overdue7d || 0],
    ["从未复习", data.neverReviewed || 0],
    ["平均 EF", (data.avgEf || 0).toFixed(1)],
  ];
  for (const [label, val] of chips) {
    const d = document.createElement("div");
    d.className = "health-chip";
    const n = document.createElement("span");
    n.className = "health-chip-num";
    n.textContent = String(val);
    const l = document.createElement("span");
    l.className = "health-chip-label";
    l.textContent = label;
    d.appendChild(n);
    d.appendChild(l);
    summaryEl.appendChild(d);
  }
  const buckets = Array.isArray(data.efBuckets) ? data.efBuckets : [];
  const maxC = Math.max(1, ...buckets.map((b) => b.count || 0));
  for (const b of buckets) {
    const row = document.createElement("div");
    row.className = "health-ef-row";
    const lab = document.createElement("span");
    lab.className = "health-ef-label";
    lab.textContent = b.label || "";
    const bar = document.createElement("span");
    bar.className = "ef-bar health-ef-bar";
    const fill = document.createElement("span");
    fill.className = "ef-fill";
    fill.style.width = Math.round(((b.count || 0) / maxC) * 100) + "%";
    bar.appendChild(fill);
    const cnt = document.createElement("span");
    cnt.className = "health-ef-count";
    cnt.textContent = String(b.count || 0);
    row.appendChild(lab);
    row.appendChild(bar);
    row.appendChild(cnt);
    efEl.appendChild(row);
  }
  const attention = Array.isArray(data.attention) ? data.attention : [];
  for (const a of attention) {
    const li = document.createElement("li");
    li.className = "health-attention-item";
    const link = document.createElement("button");
    link.type = "button";
    link.className = "health-attention-title";
    link.textContent = a.title || ("笔记 " + a.noteId);
    link.addEventListener("click", () => selectNote(a.noteId));
    const meta = document.createElement("span");
    meta.className = "health-attention-meta";
    meta.textContent = (a.reasonText || "") + "（EF " + (a.ef || 0).toFixed(1) + "）";
    li.appendChild(link);
    li.appendChild(meta);
    attEl.appendChild(li);
  }
  const advice = Array.isArray(data.advice) ? data.advice : [];
  for (const txt of advice) {
    const li = document.createElement("li");
    li.textContent = txt;
    advEl.appendChild(li);
  }
}
// 7 日趋势条形图：深色 reviewed 柱 + 浅色 added 柱并排，无图表库
function drawTrend(trend) {
  const canvas = $("trend-canvas");
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 600;
  const h = 180;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  const emptyEl = $("trend-empty");
  const maxV = Math.max(1, ...trend.map((d) => Math.max(d.reviewed || 0, d.added || 0)));
  const allZero = trend.every((d) => !(d.reviewed || 0) && !(d.added || 0));
  if (emptyEl) emptyEl.hidden = !allZero;
  if (allZero) return;

  const padL = 8, padB = 22, padT = 10;
  const n = trend.length || 1;
  const slotW = (w - padL * 2) / n;
  const barW = Math.min(14, slotW / 3);
  trend.forEach((d, i) => {
    const cx = padL + slotW * i + slotW / 2;
    const rh = (h - padB - padT) * ((d.reviewed || 0) / maxV);
    const ah = (h - padB - padT) * ((d.added || 0) / maxV);
    // added 浅色柱在左，reviewed 深色柱在右
    ctx.fillStyle = "#e2dccf";
    ctx.fillRect(cx - barW - 2, h - padB - ah, barW, ah);
    ctx.fillStyle = "#0f766e";
    ctx.fillRect(cx + 2, h - padB - rh, barW, rh);
    // 日期标签 MM-DD
    ctx.fillStyle = "#999";
    ctx.font = "10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText((d.date || "").slice(5), cx, h - 8);
    // 柱顶数字（>0 才标）
    if (d.reviewed > 0) {
      ctx.fillStyle = "#333";
      ctx.fillText(String(d.reviewed), cx + 2 + barW / 2, h - padB - rh - 4);
    }
  });
  // 图例
  ctx.textAlign = "left";
  ctx.fillStyle = "#0f766e";
  ctx.fillRect(padL, 4, 10, 10);
  ctx.fillStyle = "#666";
  ctx.fillText("复习", padL + 14, 13);
  ctx.fillStyle = "#e2dccf";
  ctx.fillRect(padL + 60, 4, 10, 10);
  ctx.fillStyle = "#666";
  ctx.fillText("新增", padL + 74, 13);
}

function renderMastery(mastery) {
  const tbody = $("mastery-tbody");
  const emptyEl = $("mastery-empty");
  const table = $("mastery-table");
  if (!tbody) return;
  tbody.innerHTML = "";
  const empty = !mastery.length;
  if (emptyEl) emptyEl.hidden = !empty;
  if (table) table.style.display = empty ? "none" : "";
  mastery.forEach((m) => {
    const tr = document.createElement("tr");
    // EF 条：1.3~2.5+ 映射为宽度百分比，基准 1.3
    const pct = Math.max(4, Math.min(100, ((m.avgEf - 1.3) / 1.4) * 100));
    tr.innerHTML =
      "<td>" + escapeHtmlStats(m.tag) + "</td>" +
      "<td>" + m.total + "</td>" +
      "<td><span class='ef-bar'><span class='ef-fill' style='width:" + pct.toFixed(0) + "%'></span></span> " +
      m.avgEf.toFixed(2) + "</td>" +
      "<td>" + m.hard + "</td>" +
      "<td>" + m.due + "</td>";
    tbody.appendChild(tr);
  });
}

function escapeHtmlStats(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
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
function renderHeatmap(data) {
  const container = document.getElementById("heatmap");
  const legend = document.querySelector(".heatmap-legend");
  const emptyEl = document.getElementById("heatmap-empty");

  while (container.firstChild) container.removeChild(container.firstChild);

  if (!Array.isArray(data)) data = [];

  const hasActivity = data.some(d => d.reviewed > 0 || d.added > 0);
  if (!hasActivity) {
    container.style.display = "none";
    legend.style.display = "none";
    emptyEl.hidden = false;
    return;
  }
  container.style.display = "";
  legend.style.display = "";
  emptyEl.hidden = true;

  const getColor = (reviewed) => {
    if (reviewed === 0) return "#eef1f4";
    if (reviewed <= 2) return "#cce8e2";
    if (reviewed <= 5) return "#7fb8ae";
    if (reviewed <= 9) return "#0f766e";
    return "#1558b0";
  };

  if (data.length > 0) {
    const firstDate = new Date(data[0].date + "T00:00:00Z");
    const offset = (firstDate.getUTCDay() + 6) % 7;
    for (let i = 0; i < offset; i++) {
      const ph = document.createElement("span");
      ph.className = "heatmap-placeholder";
      container.appendChild(ph);
    }
  }

  for (const d of data) {
    const rv = d.reviewed || 0, ad = d.added || 0;
    const cell = document.createElement("span");
    cell.className = "heatmap-cell";
    cell.style.background = getColor(rv);
    let tip = d.date + "：复习 " + rv + " 篇";
    if (ad > 0) {
      tip += "，新增 " + ad + " 篇";
    }
    cell.title = tip;
    container.appendChild(cell);
  }
}
