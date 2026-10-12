// second-brain 前端主逻辑（原生 JS，无框架）

// 全局状态
const state = {
  notes: [],        // 当前列表中的笔记
  currentId: null,  // 当前选中的笔记 id
  tag: ""           // 当前过滤标签（空字符串表示全部）
};

// 统一封装 fetch，返回 JSON
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} 失败: ${res.status} ${text}`);
  }
  // 204 无内容
  if (res.status === 204) return null;
  return res.json();
}

// 获取 DOM 元素的快捷方法
const $ = (id) => document.getElementById(id);

// 加载笔记列表（按 tag 过滤）
async function loadNotes() {
  try {
    const q = state.tag ? `?tag=${encodeURIComponent(state.tag)}` : "";
    const data = await api(`/api/notes${q}`);
    state.notes = Array.isArray(data) ? data : (data.notes || []);
    renderList();
  } catch (e) {
    console.error(e);
    $("list").innerHTML = `<div class="error">加载笔记失败: ${e.message}</div>`;
  }
}

// 渲染笔记列表
function renderList() {
  const list = $("list");
  if (!state.notes.length) {
    list.innerHTML = `<div class="empty">暂无笔记</div>`;
    return;
  }
  list.innerHTML = state.notes.map(n => {
    const active = n.id === state.currentId ? " active" : "";
    const tags = (n.tags || []).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("");
    const preview = (n.content || "").slice(0, 60).replace(/\n/g, " ");
    return `
      <div class="note-item${active}" data-id="${n.id}">
        <div class="note-title">${escapeHtml(n.title || "(无标题)")}</div>
        <div class="note-preview">${escapeHtml(preview)}</div>
        <div class="note-tags">${tags}</div>
      </div>`;
  }).join("");

  // 绑定点击事件
  list.querySelectorAll(".note-item").forEach(el => {
    el.addEventListener("click", () => selectNote(el.dataset.id));
  });
}

// 加载所有标签
async function loadTags() {
  try {
    const data = await api("/api/tags");
    const tags = Array.isArray(data) ? data : (data.tags || []);
    renderTags(tags);
  } catch (e) {
    console.error(e);
  }
}

// 渲染标签栏
function renderTags(tags) {
  const box = $("tags");
  const all = `<span class="tag${state.tag === "" ? " active" : ""}" data-tag="">全部</span>`;
  const items = tags.map(t => {
    const name = typeof t === "string" ? t : t.name;
    const count = typeof t === "string" ? "" : ` (${t.count})`;
    const active = state.tag === name ? " active" : "";
    return `<span class="tag${active}" data-tag="${escapeHtml(name)}">${escapeHtml(name)}${count}</span>`;
  }).join("");
  box.innerHTML = all + items;

  box.querySelectorAll(".tag").forEach(el => {
    el.addEventListener("click", () => {
      state.tag = el.dataset.tag || "";
      loadNotes();
      loadTags();
    });
  });
}

// 加载统计信息
async function loadStats() {
  try {
    const s = await api("/api/stats");
    const parts = [];
    if (s.notes != null) parts.push(`笔记 ${s.notes}`);
    if (s.tags != null) parts.push(`标签 ${s.tags}`);
    if (s.links != null) parts.push(`链接 ${s.links}`);
    $("stats").textContent = parts.join(" · ") || "";
  } catch (e) {
    console.error(e);
  }
}

// 选中笔记，填充编辑器
async function selectNote(id) {
  state.currentId = id;
  try {
    const n = await api(`/api/notes/${encodeURIComponent(id)}`);
    $("title").value = n.title || "";
    $("content").value = n.content || "";
    $("tags-input").value = (n.tags || []).join(", ");
    // 隐藏预览
    $("preview").style.display = "none";
    $("content").style.display = "";
    // 刷新列表高亮
    renderList();
  } catch (e) {
    alert("加载笔记失败: " + e.message);
  }
}

// 新建笔记（清空编辑器）
function newNote() {
  state.currentId = null;
  $("title").value = "";
  $("content").value = "";
  $("tags-input").value = "";
  $("preview").style.display = "none";
  $("content").style.display = "";
  renderList();
  $("title").focus();
}

// 保存笔记（POST 新建 / PUT 更新）
async function saveNote() {
  const title = $("title").value.trim();
  const content = $("content").value;
  const tagsRaw = $("tags-input").value;
  // 逗号拆分标签，去空白、去重
  const tags = tagsRaw
    .split(",")
    .map(t => t.trim())
    .filter(Boolean);
  const payload = { title, content, tags };

  try {
    let saved;
    if (state.currentId) {
      saved = await api(`/api/notes/${encodeURIComponent(state.currentId)}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      });
    } else {
      saved = await api("/api/notes", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    }
    if (saved && saved.id != null) state.currentId = saved.id;
    await loadNotes();
    await loadTags();
    await loadStats();
    await drawGraph();
  } catch (e) {
    alert("保存失败: " + e.message);
  }
}

// 删除当前笔记
async function deleteNote() {
  if (!state.currentId) {
    alert("没有选中的笔记");
    return;
  }
  if (!confirm("确定删除该笔记吗？")) return;
  try {
    await api(`/api/notes/${encodeURIComponent(state.currentId)}`, { method: "DELETE" });
    state.currentId = null;
    $("title").value = "";
    $("content").value = "";
    $("tags-input").value = "";
    await loadNotes();
    await loadTags();
    await loadStats();
    await drawGraph();
  } catch (e) {
    alert("删除失败: " + e.message);
  }
}

// 搜索
async function doSearch() {
  const q = $("search").value.trim();
  if (!q) {
    await loadNotes();
    return;
  }
  try {
    const data = await api(`/api/search?q=${encodeURIComponent(q)}`);
    state.notes = Array.isArray(data) ? data : (data.results || data.notes || []);
    renderList();
  } catch (e) {
    alert("搜索失败: " + e.message);
  }
}

// 切换预览（Markdown → HTML）
async function togglePreview() {
  if (!state.currentId) {
    alert("请先保存或选中一篇笔记");
    return;
  }
  const preview = $("preview");
  const content = $("content");
  if (preview.style.display === "block") {
    preview.style.display = "none";
    content.style.display = "";
    return;
  }
  try {
    const data = await api(`/api/notes/${encodeURIComponent(state.currentId)}/preview`);
    preview.innerHTML = (data && (data.html || data.content)) || "<em>无内容</em>";
    preview.style.display = "block";
    content.style.display = "none";
  } catch (e) {
    alert("预览失败: " + e.message);
  }
}

// 绘制关系图（圆形布局）
async function drawGraph() {
  const canvas = $("graph");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  let data;
  try {
    data = await api("/api/graph");
  } catch (e) {
    console.error("加载图谱失败", e);
    return;
  }

  const nodes = Array.isArray(data) ? data : (data.nodes || []);
  const edges = (data && data.edges) || [];

  // 自适应画布尺寸
  const wrap = canvas.parentElement;
  const w = canvas.width = wrap.clientWidth || 400;
  const h = canvas.height = wrap.clientHeight || 400;

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#fafafa";
  ctx.fillRect(0, 0, w, h);

  if (!nodes.length) {
    ctx.fillStyle = "#999";
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("暂无图谱数据", w / 2, h / 2);
    return;
  }

  // 圆形布局
  const cx = w / 2;
  const cy = h / 2;
  const radius = Math.max(40, Math.min(w, h) / 2 - 40);
  const pos = {};
  nodes.forEach((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    pos[n.id] = {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle)
    };
  });

  // 画连线
  ctx.strokeStyle = "#bbb";
  ctx.lineWidth = 1;
  edges.forEach(e => {
    const a = pos[e.source != null ? e.source : e.from];
    const b = pos[e.target != null ? e.target : e.to];
    if (!a || !b) return;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  });

  // 画节点与标题
  nodes.forEach(n => {
    const p = pos[n.id];
    if (!p) return;
    // 节点圆
    ctx.beginPath();
    ctx.arc(p.x, p.y, 6, 0, Math.PI * 2);
    ctx.fillStyle = n.id === state.currentId ? "#e63946" : "#457b9d";
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.stroke();

    // 标题
    ctx.fillStyle = "#333";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    let title = n.title || "(无标题)";
    if (title.length > 8) title = title.slice(0, 8) + "…";
    ctx.fillText(title, p.x, p.y + 18);
  });
}

// 简单 HTML 转义，避免 XSS
function escapeHtml(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// 绑定 index.html 中的 id 事件
function bindEvents() {
  const bind = (id, evt, fn) => {
    const el = $(id);
    if (el) el.addEventListener(evt, fn);
  };

  bind("new", "click", newNote);
  bind("save", "click", saveNote);
  bind("delete", "click", deleteNote);
  bind("preview-btn", "click", togglePreview);
  bind("search-btn", "click", doSearch);
  bind("search", "keydown", (e) => { if (e.key === "Enter") doSearch(); });
  bind("refresh", "click", () => { loadNotes(); loadTags(); loadStats(); drawGraph(); });

  // 窗口尺寸变化时重绘图谱
  window.addEventListener("resize", () => {
    clearTimeout(window.__graphTimer);
    window.__graphTimer = setTimeout(drawGraph, 200);
  });
}

// 初始化
async function init() {
  bindEvents();
  await Promise.all([loadNotes(), loadTags(), loadStats()]);
  await drawGraph();
}

// DOM 就绪后启动
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
