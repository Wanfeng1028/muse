// feedflow/static/js/app.js
// 原生 JS：阅读器 / 订阅管理 / OPML 页交互逻辑

// 通用 API 封装：返回 JSON，非 2xx 抛错
async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  const resp = await fetch(path, opts);
  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch (e) { data = null; }
  }
  if (!resp.ok) {
    const msg = (data && data.error) ? data.error : ("HTTP " + resp.status);
    throw new Error(msg);
  }
  return data;
}

// ---------------- 阅读器页 ----------------
function initReader() {
  const state = { scope: "unread", feedId: null, folderId: null, selectedId: null, tagId: null, tagName: "" };
  const elTree = document.getElementById("feed-tree");
  const elList = document.getElementById("article-list");
  const elReader = document.getElementById("reader-pane");
  // 真正的滚动容器是 .col-reader 列（CSS 里 .col{overflow-y:auto}），
  // #reader-pane 本身不滚动，只随内容长高。进度读写都必须走这一列。
  const elScroller = elReader ? elReader.closest(".col") : null;
  const elStatus = document.getElementById("list-status");
  const elMoreWrap = document.getElementById("list-more-wrap");

  const scopeLabel = { unread: "未读", starred: "星标", all: "全部" };

  // 过滤按钮切换 scope
  document.querySelectorAll(".filter-btn[data-scope]").forEach(btn => {
    btn.addEventListener("click", () => {
      state.scope = btn.dataset.scope;
      state.feedId = null;
      state.folderId = null;
      document.querySelectorAll(".filter-btn[data-scope]").forEach(b => b.classList.toggle("is-active", b === btn));
      clearActive();
      state.tagId = null; state.tagName = "";
      loadArticles();
    });
  });

  const clearTagFilterBtn = document.getElementById("clear-tag-filter");
  if (clearTagFilterBtn) clearTagFilterBtn.addEventListener("click", clearTagFilter);

  // 清除树中激活态
  function clearActive() {
    elTree.querySelectorAll(".tree-item.active, .tree-group-head.active").forEach(n => n.classList.remove("active"));
  }

  // 事件委托：源 / 分组
  elTree.addEventListener("click", (e) => {
    const feedBtn = e.target.closest("[data-feed-id]");
    if (feedBtn && elTree.contains(feedBtn)) {
      state.feedId = parseInt(feedBtn.dataset.feedId, 10);
      state.folderId = null;
      clearActive();
      feedBtn.classList.add("active");
      state.tagId = null; state.tagName = "";
      loadArticles();
      return;
    }
    const head = e.target.closest(".tree-group-head");
    if (head && elTree.contains(head)) {
      const sec = head.closest(".tree-group");
      const fid = sec ? sec.dataset.folderId : "";
      state.folderId = fid === "" ? null : parseInt(fid, 10);
      state.feedId = null;
      clearActive();
      head.classList.add("active");
      state.tagId = null; state.tagName = "";
      loadArticles();
    }
  });

  // 渲染中栏文章列表
  async function loadArticles() {
    elStatus.textContent = (scopeLabel[state.scope] || "未读") + (state.tagName ? " · 标签：" + state.tagName : "");
    const params = new URLSearchParams();
    params.set("scope", state.scope);
    if (state.feedId != null) params.set("feed_id", state.feedId);
    if (state.folderId != null) params.set("folder_id", state.folderId);
    if (state.tagId != null) params.set("tag_id", state.tagId);
    params.set("limit", "100");
    const clearTagBtn = document.getElementById("clear-tag-filter");
    if (clearTagBtn) clearTagBtn.style.display = state.tagId == null ? "none" : "";
    let data;
    try { data = await api("/api/articles?" + params.toString()); } catch (e) { data = { total: 0, articles: [] }; }
    const arts = (data && data.articles) || [];
    let html = "";
    if (!arts.length) {
      html = `<p class="empty-hint">没有文章</p>`;
    } else {
      const renderItem = (a) => {
        const cls = "article-item" + (state.selectedId === a.id ? " active" : "") + (a.is_read ? "" : " unread");

        let h = `<div class="${cls}" data-id="${a.id}">`;
        h += `<div class="title">${escapeHtml(a.title || "(无标题)")}${a.is_starred ? '<span class="star"><svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6 4.2 13.6l.7-4.3-3.1-3 4.3-.6z" fill="currentColor"/></svg></span>' : ""}</div>`;
        h += `<div class="meta">${escapeHtml(a.feed_title || "")} · ${fmtTime(a.published_at || a.fetched_at)}</div>`;
        h += `</div>`;

        return h;
      };
      const seenClusters = new Set();
      for (const a of arts) {
        const cid = a.cluster_id;
        const csize = a.cluster_size || 0;
        if (cid != null && csize > 1) {
          if (seenClusters.has(cid)) continue;
          seenClusters.add(cid);
          const cluster = arts.filter(x => x.cluster_id === cid);
          const others = cluster.slice(1);
          html += renderItem(a);
          if (others.length) {
            const groupId = "cluster-" + cid;
            html += `<div class="cluster-toggle" data-target="${groupId}" style="font-size:12px;color:#888;text-align:left;cursor:pointer;padding:2px 8px;user-select:none;">▸ 还有 ${others.length} 篇相似报道</div>`;
            html += `<div class="cluster-group" id="${groupId}" style="display:none;">`;
            for (const o of others) html += renderItem(o);
            html += `</div>`;
          }
        } else {
          html += renderItem(a);
        }
      }
    }
    elList.innerHTML = html;
    elList.querySelectorAll("[data-id]").forEach(n => n.addEventListener("click", () => {
      openArticle(parseInt(n.dataset.id, 10));
    }));
    elList.querySelectorAll(".cluster-toggle").forEach(t => t.addEventListener("click", () => {
      const target = document.getElementById(t.dataset.target);
      if (!target) return;
      const expanded = target.style.display !== "none";
      if (expanded) {
        target.style.display = "none";
        t.textContent = "▸ 还有 " + target.children.length + " 篇相似报道";
      } else {
        target.style.display = "";
        t.textContent = "▾ 收起相似报道";
      }
    }));
    if (elMoreWrap) elMoreWrap.hidden = true;
  }
  // 保存当前文章阅读进度（同步，不等防抖）
  function saveScrollPos(id) {
    if (!id || !elScroller) return;
    try {
      api("/api/articles/" + id + "/progress", {
        method: "POST",
        body: JSON.stringify({ scroll_pos: elScroller.scrollTop }),
      }).catch(() => {});
    } catch (e) {
      // 静默
    }
  }

  // 打开文章，自动标已读
  async function openArticle(id) {
    // 切换前保存上一篇进度
    if (state.selectedId && state.selectedId !== id) {
      saveScrollPos(state.selectedId);
    }
    let a;
    try { a = await api("/api/articles/" + id); } catch (e) { return; }
    state.selectedId = id;
    elList.querySelectorAll(".article-item").forEach(n => n.classList.toggle("active", parseInt(n.dataset.id, 10) === id));
    renderReader(a);
    loadScoreCard(id);
    loadArticleTags(id);
    loadArticleNote(id);
    requestAnimationFrame(() => {
      if (elScroller) elScroller.scrollTop = a.scroll_pos || 0;
    });
    // 列表中对应项去掉 unread
    const item = elList.querySelector(`[data-id="${id}"]`);
    if (item) item.classList.remove("unread");
    if (!a.is_read) {
      try { await api("/api/articles/" + id + "/read", { method: "POST", body: JSON.stringify({ is_read: 1 }) }); } catch (e) {}
    }
  }

  function renderReader(a) {
    const star = a.is_starred ? "★ 取消星标" : "☆ 星标";
    const readBtn = a.is_read ? "标为未读" : "标为已读";
    let html = `<div class="reader-head">`;
    html += `<h1>${escapeHtml(a.title || "(无标题)")}</h1>`;
    html += `<div class="reader-meta">${escapeHtml(a.feed_title || "")} · ${escapeHtml(a.author || "")} · ${fmtTime(a.published_at || a.fetched_at)}</div>`;
    html += `<div class="reader-actions">`;
    html += `<button id="btn-read" class="btn">${readBtn}</button>`;
    html += `<button id="btn-star" class="btn">${star}</button>`;
    if (a.link) html += `<a class="btn" href="${escapeAttr(a.link)}" target="_blank" rel="noopener">查看原文</a>`;
    html += `</div></div>`;
    html += `<div id="article-tags" class="article-tags"></div>`;
    html += `<div class="tag-editor"><select id="tag-select"></select><input id="tag-new" type="text" placeholder="或填新标签名"><button id="btn-add-tag" class="btn">贴标签</button></div>`;
    html += `<div id="article-note" class="article-note"><h3>我的笔记</h3><textarea id="note-text" rows="4"></textarea><button id="btn-save-note" class="btn">保存笔记</button><button id="btn-delete-note" class="btn">删除笔记</button><span id="note-status" class="note-status"></span></div>`;
    html += `<div id="score-card" class="score-card is-loading"><span class="score-loading">正在算这篇为什么值得读…</span></div>`;
    html += `<div class="content">${a.content_html || a.content_text || a.summary || ""}</div>`;
    elReader.innerHTML = html;
    const btnRead = document.getElementById("btn-read");
    const btnStar = document.getElementById("btn-star");
    if (btnRead) btnRead.addEventListener("click", () => markRead(a.id, a.is_read ? 0 : 1));
    if (btnStar) btnStar.addEventListener("click", () => toggleStar(a.id, a.is_starred ? 0 : 1));
    loadTagOptions();
    bindTagEditor(a.id);
    bindNoteEditor(a.id);
  }

  const SCORE_FACTORS = [["recency","时效"],["heat","事件热度"],["source","来源权重"],["keyword","关键词"],["unread","未读加成"]];
  async function loadScoreCard(id) {
    const card = document.getElementById("score-card");
    if (!card) return;
    let data;
    try { data = await api("/api/articles/" + id + "/score"); } catch (e) { card.remove(); return; }
    if (state.selectedId !== id) return;
    if (!data || typeof data.score !== "number" || !data.parts) { card.remove(); return; }
    let html = '<div class="score-head"><span class="score-title">' + escapeHtml("为什么排前面") + '</span><span class="score-num">' + data.score.toFixed(2) + '</span></div>';
    html += '<div class="score-factors">';
    const parts = data.parts;
    for (const [key, label] of SCORE_FACTORS) {
      const v = Math.max(0, Math.min(1, Number(parts[key]) || 0));
      const pct = Math.round(v * 100);
      html += '<div class="score-factor"><span class="factor-label">' + escapeHtml(label) + '</span><span class="factor-bar"><i style="width:' + pct + '%"></i></span><span class="factor-val">' + v.toFixed(2) + '</span></div>';
    }
    html += '</div>';
    if (Array.isArray(data.reasons) && data.reasons.length > 0) {
      html += '<ul class="score-reasons">';
      for (const r of data.reasons) {
        html += '<li>' + escapeHtml(r) + '</li>';
      }
      html += '</ul>';
    }
    const reasonsArr = Array.isArray(data.reasons) ? data.reasons : [];
    const hasAgeReason = reasonsArr.some(function (r) { return /发布|刚刚/.test(String(r)); });
    if (!hasAgeReason && typeof data.age_hours === "number" && isFinite(data.age_hours)) {
      const ageText = data.age_hours < 1 ? "刚刚发布" : "约 " + Math.round(data.age_hours) + " 小时前发布";
      html += '<div class="score-foot">' + escapeHtml(ageText) + '</div>';
    }
    card.classList.remove("is-loading");
    card.innerHTML = html;
  }


  async function loadArticleTags(id) {
    const box = document.getElementById("article-tags");
    if (!box) return;
    let tags = [];
    try {
      const res = await api("/api/articles/" + id + "/tags");
      tags = Array.isArray(res.tags) ? res.tags : [];
    } catch (e) {
      return;
    }
    if (state.selectedId !== id) return;
    if (!tags.length) {
      box.innerHTML = `<span class="tag-empty">还没有标签</span>`;
      return;
    }
    box.innerHTML = "";
    tags.forEach((t) => {
      const chip = document.createElement("button");
      chip.className = "tag-chip";
      chip.dataset.tagId = t.id;
      chip.dataset.tagName = t.name || "";
      chip.textContent = t.name || "";
      chip.addEventListener("click", () => {
        if (typeof setTagFilter === "function") setTagFilter(t.id, t.name || "");
      });
      const x = document.createElement("button");
      x.className = "tag-chip-x";
      x.dataset.tagId = t.id;
      x.textContent = "×";
      x.setAttribute("aria-label", "取消关联");
      x.addEventListener("click", async () => {
        try {
          await api("/api/articles/" + id + "/tags/" + t.id, { method: "DELETE" });
          loadArticleTags(id);
        } catch (e) {}
      });
      box.appendChild(chip);
      box.appendChild(x);
    });
  }

  async function loadTagOptions() {
    const sel = document.getElementById("tag-select");
    if (!sel) return;
    sel.innerHTML = "";
    const first = document.createElement("option");
    first.value = "";
    first.textContent = "选已有标签";
    sel.appendChild(first);
    try {
      const data = await api("/api/tags");
      (data.tags || []).forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.id;
        opt.textContent = t.name;
        sel.appendChild(opt);
      });
    } catch (e) {}
  }

  function bindTagEditor(articleId) {
    const btn = document.getElementById("btn-add-tag");
    if (!btn) return;
    btn.addEventListener("click", async () => {
      const sel = document.getElementById("tag-select");
      const input = document.getElementById("tag-new");
      let body = null;
      if (sel && sel.value) {
        body = { tag_id: Number(sel.value) };
      } else if (input && input.value.trim()) {
        body = { name: input.value.trim() };
      }
      if (!body) return;
      try {
        await api(`/api/articles/${articleId}/tags`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        loadArticleTags(articleId);
        loadTagOptions();
        if (input) input.value = "";
        if (sel) sel.value = "";
      } catch (e) {}
    });
  }

async function loadArticleNote(id) {
  const container = document.getElementById('article-note');
  if (!container) return;
  let data = null;
  try {
    data = await api(`/api/articles/${id}/note`);
  } catch (e) {
    return;
  }
  if (state.selectedId !== id) return;
  const text = document.getElementById('note-text');
  if (text) text.value = data && data.body != null ? data.body : '';
  const status = document.getElementById('note-status');
  if (status) status.textContent = '';
}

function bindNoteEditor(articleId) {
  const saveBtn = document.getElementById('btn-save-note');
  const deleteBtn = document.getElementById('btn-delete-note');
  if (saveBtn) saveBtn.onclick = async () => {
    const text = document.getElementById('note-text');
    const status = document.getElementById('note-status');
    try {
      await api(`/api/articles/${articleId}/note`, { method: 'PUT', body: JSON.stringify({ body: text ? text.value : '' }) });
      if (status) status.textContent = '已保存';
    } catch (e) {
      if (status) status.textContent = '保存失败';
    }
  };
  if (deleteBtn) deleteBtn.onclick = async () => {
    const text = document.getElementById('note-text');
    const status = document.getElementById('note-status');
    try {
      await api(`/api/articles/${articleId}/note`, { method: 'DELETE' });
      if (text) text.value = '';
      if (status) status.textContent = '已删除';
    } catch (e) {
      if (status) status.textContent = '删除失败';
    }
  };
}

  function setTagFilter(id, name) {
    state.tagId = id;
    state.tagName = name;
    state.feedId = null;
    state.folderId = null;
    clearActive();
    loadArticles();
  }

  function clearTagFilter() {
    state.tagId = null;
    state.tagName = "";
    loadArticles();
  }

  // 标记已读/未读
  async function markRead(id, v) {
    try { await api("/api/articles/" + id + "/read", { method: "POST", body: JSON.stringify({ is_read: v }) }); } catch (e) { return; }
    if (state.selectedId === id) {
      try { const a = await api("/api/articles/" + id); renderReader(a); loadArticleTags(a.id); loadArticleNote(a.id); } catch (e) {}
    }
    loadArticles();
  }

  // 星标切换
  async function toggleStar(id, v) {
    try { await api("/api/articles/" + id + "/star", { method: "POST", body: JSON.stringify({ is_starred: v }) }); } catch (e) { return; }
    if (state.selectedId === id) {
      try { const a = await api("/api/articles/" + id); renderReader(a); loadArticleTags(a.id); loadArticleNote(a.id); } catch (e) {}
    }
    loadArticles();
  }

  // 全部标已读
  async function markAllRead() {
    const body = { scope: state.scope };
    if (state.feedId != null) body.feed_id = state.feedId;
    if (state.folderId != null) body.folder_id = state.folderId;
    if (state.tagId != null) body.tag_id = state.tagId;
    try { await api("/api/articles/mark_read", { method: "POST", body: JSON.stringify(body) }); } catch (e) { return; }
    loadArticles();
  }

  // 快捷键
  document.addEventListener("keydown", (e) => {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if (e.key === "Escape") {
      const ov = document.getElementById("kbd-help");
      if (ov) { ov.remove(); e.preventDefault(); return; }
    }
    if (e.key === "?") {
      const ov = document.getElementById("kbd-help");
      if (ov) { ov.remove(); } else { renderHelpOverlay(); }
      e.preventDefault();
      return;
    }
    if (document.getElementById("kbd-help")) return;
    const items = Array.from(elList.querySelectorAll("[data-id]")).map(n => parseInt(n.dataset.id, 10));
    const idx = items.indexOf(state.selectedId);
    if (e.key === "j") {
      const n = idx < 0 ? 0 : Math.min(items.length - 1, idx + 1);
      if (items[n]) { openArticle(items[n]); e.preventDefault(); }
    } else if (e.key === "k") {
      const n = idx <= 0 ? 0 : idx - 1;
      if (items[n]) { openArticle(items[n]); e.preventDefault(); }
    } else if (e.key === "m" && state.selectedId) {
      const cur = elReader.querySelector("#btn-read");
      const toRead = cur && cur.textContent.indexOf("未读") >= 0;
      markRead(state.selectedId, toRead ? 0 : 1); e.preventDefault();
    } else if (e.key === "s" && state.selectedId) {
      const cur = elReader.querySelector("#btn-star");
      const toStar = cur && cur.textContent.indexOf("取消") >= 0;
      toggleStar(state.selectedId, toStar ? 0 : 1); e.preventDefault();
    } else if (e.key === "o" && state.selectedId) {
      const linkEl = elReader.querySelector("a.btn[target='_blank']");
      if (linkEl && linkEl.href) {
        window.open(linkEl.href, "_blank", "noopener");
        e.preventDefault();
      }
    } else if (e.key === "r" && state.selectedId) {
      const cur = elReader.querySelector("#btn-read");
      const toRead = cur && cur.textContent.indexOf("未读") >= 0;
      markRead(state.selectedId, toRead ? 0 : 1); e.preventDefault();
    }
  });

  // 滚动监听（防抖 500ms 保存）。监听 .col-reader 列，它才是滚动容器。
  let scrollTimer = null;
  if (elScroller) elScroller.addEventListener("scroll", () => {
    if (!state.selectedId) return;
    const id = state.selectedId;
    if (scrollTimer) clearTimeout(scrollTimer);
    scrollTimer = setTimeout(() => {
      try {
        api("/api/articles/" + id + "/progress", {
          method: "POST",
          body: JSON.stringify({ scroll_pos: elScroller.scrollTop }),
        }).catch(() => {});
      } catch (e) {
        // 静默
      }
    }, 500);
  });

  // 快捷键帮助浮层
  function renderHelpOverlay() {
    const rows = [
      ["j", "下一篇"],
      ["k", "上一篇"],
      ["o", "在新标签页打开原文"],
      ["r", "标已读/未读"],
      ["s", "加星/取消星标"],
      ["m", "标已读/未读（兼容）"],
      ["?", "打开/关闭本帮助"],
      ["Esc", "关闭"],
    ];
    const overlay = document.createElement("div");
    overlay.id = "kbd-help";
    overlay.className = "kbd-help-overlay";
    let list = "";
    for (const [k, desc] of rows) {
      list += `<div class="kbd-row"><span class="kbd">${escapeHtml(k)}</span><span class="kbd-desc">${escapeHtml(desc)}</span></div>`;
    }
    overlay.innerHTML = `<div class="kbd-help-card">
      <h3 class="kbd-help-title">键盘快捷键</h3>
      ${list}
      <div class="kbd-help-actions"><button class="btn" type="button">关闭</button></div>
    </div>`;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) { overlay.remove(); }
    });
    overlay.querySelector("button").addEventListener("click", () => overlay.remove());
    document.body.appendChild(overlay);
  }

  const btnAll = document.getElementById("mark-all-read");
  if (btnAll) btnAll.addEventListener("click", markAllRead);

  loadArticles();
}

// ---------------- 订阅管理页 ----------------
function initFeeds() {
  const formAdd = document.getElementById("form-add-feed");
  if (formAdd) {
    formAdd.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(formAdd);
      const body = { feed_url: (fd.get("feed_url") || "").trim() };
      const fid = (fd.get("folder_id") || "").trim();
      if (fid) body.folder_id = parseInt(fid, 10);
      const iv = (fd.get("interval_min") || "").trim();
      if (iv) body.interval_min = parseInt(iv, 10);
      const msg = document.getElementById("feed-msg");
      try {
        await api("/api/feeds", { method: "POST", body: JSON.stringify(body) });
        if (msg) msg.textContent = "添加成功";
        location.reload();
      } catch (err) {
        if (msg) msg.textContent = "错误：" + err.message;
      }
    });
  }

  // 新建分组
  const formFolder = document.getElementById("form-add-folder");
  if (formFolder) {
    formFolder.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = (new FormData(formFolder).get("name") || "").trim();
      if (!name) return;
      try { await api("/api/folders", { method: "POST", body: JSON.stringify({ name }) }); location.reload(); } catch (err) { alert(err.message); }
    });
  }

  document.querySelectorAll("[data-del-feed]").forEach(n => n.addEventListener("click", async () => {
    if (!confirm("确认删除该订阅及其文章？")) return;
    try { await api("/api/feeds/" + n.dataset.delFeed, { method: "DELETE" }); location.reload(); } catch (err) { alert(err.message); }
  }));

  document.querySelectorAll("[data-fetch-feed]").forEach(n => n.addEventListener("click", async () => {
    const id = n.dataset.fetchFeed;
    n.disabled = true;
    try {
      const r = await api("/api/feeds/" + id + "/fetch", { method: "POST" });
      alert("抓取完成：新增 " + r.added + "，状态 " + r.status + (r.error ? ("，错误 " + r.error) : ""));
      location.reload();
    } catch (err) { alert(err.message); n.disabled = false; }
  }));

  // 行内编辑保存
  document.querySelectorAll("[data-edit-feed]").forEach(n => n.addEventListener("click", async () => {
    const id = n.dataset.editFeed;
    const row = document.querySelector(`tr[data-row-feed="${id}"]`);
    if (!row) return;
    const body = {
      title: row.querySelector("[name=title]").value,
      interval_min: parseInt(row.querySelector("[name=interval_min]").value || "0", 10),
      enabled: row.querySelector("[name=enabled]").checked ? 1 : 0,
    };
    const fsel = row.querySelector("[name=folder_id]");
    body.folder_id = fsel && fsel.value ? parseInt(fsel.value, 10) : null;
    try { await api("/api/feeds/" + id, { method: "PUT", body: JSON.stringify(body) }); location.reload(); } catch (err) { alert(err.message); }
  }));

  document.querySelectorAll("[data-del-folder]").forEach(n => n.addEventListener("click", async () => {
    if (!confirm("确认删除该分组？（组内源将变为未分组）")) return;
    try { await api("/api/folders/" + n.dataset.delFolder, { method: "DELETE" }); location.reload(); } catch (err) { alert(err.message); }
  }));

  document.querySelectorAll("[data-rename-folder]").forEach(n => n.addEventListener("click", async () => {
    const id = n.dataset.renameFolder;
    const cur = n.dataset.name || "";
    const name = prompt("新分组名", cur);
    if (!name) return;
    try { await api("/api/folders/" + id, { method: "PUT", body: JSON.stringify({ name }) }); location.reload(); } catch (err) { alert(err.message); }
  }));

  document.querySelectorAll("[data-move-folder]").forEach(n => n.addEventListener("click", async () => {
    const id = n.dataset.moveFolder;
    const dir = n.dataset.dir;
    const pos = parseInt(n.dataset.pos || "0", 10);
    const newPos = dir === "up" ? Math.max(0, pos - 1) : pos + 1;
    try { await api("/api/folders/" + id, { method: "PUT", body: JSON.stringify({ position: newPos }) }); location.reload(); } catch (err) { alert(err.message); }
  }));
}

// ---------------- OPML 页 ----------------
function initOpml() {
  const form = document.getElementById("form-import-opml");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const file = fd.get("file");
    const msg = document.getElementById("opml-msg");
    if (!file || !file.size) { if (msg) msg.textContent = "请选择文件"; return; }
    const text = await file.text();
    try {
      const resp = await fetch("/opml", { method: "POST", headers: { "Content-Type": "application/xml" }, body: text });
      const data = await resp.json();
      if (msg) msg.textContent = "导入完成：新增 " + (data.imported || 0) + "，跳过 " + (data.skipped || 0);
      setTimeout(() => location.reload(), 1200);
    } catch (err) {
      if (msg) msg.textContent = "错误：" + err.message;
    }
  });
}

// ---------------- 工具 ----------------
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }
function fmtTime(s) {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const p = (n) => (n < 10 ? "0" + n : "" + n);
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  } catch (e) { return s; }
}

document.addEventListener("DOMContentLoaded", () => {
  if (document.getElementById("feed-tree") && document.getElementById("article-list")) initReader();
  if (document.getElementById("form-add-feed") || document.getElementById("form-add-folder")) initFeeds();
  initOpml();
});
