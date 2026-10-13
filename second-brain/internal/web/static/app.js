// second-brain app.js — 原生 JS，无框架

// ---------- 工具 ----------
async function api(path, opts = {}) {
  const conf = { headers: { "Content-Type": "application/json" }, ...opts };
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
};

// ---------- 视图切换 ----------
function showView(name) {
  state.view = name;
  ["editor", "graph", "review"].forEach((v) => {
    const el = $("editor-view");
    if (!el) return;
  });
  const views = { editor: $("editor-view"), graph: $("graph-view"), review: $("review-view") };
  Object.entries(views).forEach(([k, el]) => {
    if (el) el.hidden = k !== name;
  });
  const navNotes = $("nav-notes");
  const navReview = $("nav-review");
  if (navNotes) navNotes.classList.toggle("is-active", name === "editor" || name === "graph");
  if (navReview) navReview.classList.toggle("is-active", name === "review");
}
window.__sbShowView = showView;

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

function renderList() {
  const listEl = $("note-list");
  const countEl = $("list-count");
  const titleEl = $("list-title");
  if (!listEl) return;

  if (titleEl) titleEl.textContent = state.tag ? `#${state.tag}` : "全部笔记";
  if (countEl) countEl.textContent = `共 ${state.notes.length} 篇`;

  if (!state.notes.length) {
    listEl.innerHTML = `<div class="empty-hint">还没有笔记，点上面「新建」写一条吧</div>`;
    return;
  }

  listEl.innerHTML = state.notes
    .map((n) => {
      const tags = (n.tags || []).map((t) => `<span class="chip">${escapeHtml(t)}</span>`).join("");
      const body = (n.body || "").slice(0, 60).replace(/\s+/g, " ");
      const date = n.updated_at ? new Date(n.updated_at).toLocaleDateString("zh-CN") : "";
      const active = n.id === state.currentId ? " is-active" : "";
      return `<div class="note-item${active}" data-id="${n.id}">
        <div class="note-item-title">${escapeHtml(n.title || "无标题")}</div>
        <div class="note-item-body">${escapeHtml(body)}</div>
        <div class="note-item-foot">
          <div class="note-item-tags">${tags}</div>
          <div class="note-item-date">${escapeHtml(date)}</div>
        </div>
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
    alert("保存失败：" + e.message);
  }
}

async function deleteNote() {
  if (!state.currentId) {
    alert("还没选中笔记呢");
    return;
  }
  if (!confirm("确定要删掉这条笔记吗？删了就找不回来了。")) return;
  try {
    await api(`/api/notes/${state.currentId}`, { method: "DELETE" });
    state.currentId = null;
    if ($("editor-title")) $("editor-title").value = "";
    if ($("editor-body")) $("editor-body").value = "";
    if ($("editor-tags")) $("editor-tags").value = "";
    if ($("editor-pinned")) $("editor-pinned").checked = false;
    await Promise.all([loadNotes(), loadTags(), loadStats()]);
  } catch (e) {
    alert("删除失败：" + e.message);
  }
}

// ---------- 搜索 ----------
let searchTimer = null;

async function doSearch() {
  const q = ($("search-input")?.value || "").trim();
  if (!q) {
    await loadNotes();
    return;
  }
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
    state.notes = Array.isArray(data) ? data : (data && data.notes) || [];
  } catch (e) {
    console.error("搜索失败", e);
    state.notes = [];
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

// ---------- 事件绑定 ----------
function bindEvents() {
  $("btn-new")?.addEventListener("click", newNote);
  $("btn-save")?.addEventListener("click", saveNote);
  $("btn-delete")?.addEventListener("click", deleteNote);
  $("btn-preview")?.addEventListener("click", togglePreview);

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

  $("nav-notes")?.addEventListener("click", () => showView("editor"));
  $("nav-review")?.addEventListener("click", () => {
    showView("review");
    window.__sbStartReview?.();
  });
}

// ---------- 初始化 ----------
async function init() {
  bindEvents();
  await Promise.all([loadNotes(), loadTags(), loadStats()]);
  showView("editor");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

/*
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
