(function () {
  'use strict';

  var PAGE_I18N = {
    'fin.pageTitle': { 'zh-CN': '成片库', en: 'Final Cuts' },
    'fin.generate': { 'zh-CN': '生成成片', en: 'Generate Final Cut' },
    'fin.statusReady': { 'zh-CN': '已完成', en: 'Done' },
    'fin.statusBuilding': { 'zh-CN': '剪辑中', en: 'Editing' },
    'fin.statusFailed': { 'zh-CN': '失败', en: 'Failed' },
    'fin.statusPending': { 'zh-CN': '待处理', en: 'Pending' },
    'fin.qcPending': { 'zh-CN': '待质检', en: 'QC pending' },
    'fin.qcApproved': { 'zh-CN': '已通过', en: 'Approved' },
    'fin.qcRejected': { 'zh-CN': '已打回', en: 'Rejected' },
    'fin.qcUnknown': { 'zh-CN': '未知', en: 'Unknown' },
    'fin.noteBuilding': { 'zh-CN': '正在剪辑生成中，请稍候…', en: 'Editing in progress, please wait…' },
    'fin.noteFailed': { 'zh-CN': '生成失败，请重试。', en: 'Generation failed. Please retry.' },
    'fin.notePending': { 'zh-CN': '排队中…', en: 'Queued…' },
    'fin.loadProjectsFailed': { 'zh-CN': '加载项目失败：', en: 'Failed to load projects: ' },
    'fin.loadEpisodesFailed': { 'zh-CN': '加载剧集失败：', en: 'Failed to load episodes: ' },
    'fin.loadFinalsFailed': { 'zh-CN': '加载成片失败：', en: 'Failed to load final cuts: ' },
    'fin.pickProjectEpisode': { 'zh-CN': '请先选择项目和剧集。', en: 'Please select a project and an episode first.' },
    'fin.submitting': { 'zh-CN': '正在提交生成任务…', en: 'Submitting generation task…' },
    'fin.submitted': { 'zh-CN': '已提交生成任务。', en: 'Generation task submitted.' },
    'fin.generateFailed': { 'zh-CN': '生成失败：', en: 'Generation failed: ' },
    'fin.emptyPick': { 'zh-CN': '请先选择项目和剧集。', en: 'Please select a project and an episode first.' },
    'fin.emptyNoFinals': { 'zh-CN': '这个剧集还没有成片，点击上方“生成成片”开始剪辑。', en: 'This episode has no final cut yet. Click "Generate Final Cut" above to start editing.' },
    'fin.episodePrefix': { 'zh-CN': '第 ', en: 'Episode ' },
    'fin.episodeSuffix': { 'zh-CN': ' 集', en: '' },
    'fin.posterAlt': { 'zh-CN': '成片海报', en: 'Final cut poster' },
    'fin.titlePrefix': { 'zh-CN': '成片 ', en: 'Final cut ' },
    'fin.durationPrefix': { 'zh-CN': '时长 ', en: 'Duration ' },
    'fin.createdPrefix': { 'zh-CN': '创建 ', en: 'Created ' },
    'fin.play': { 'zh-CN': '播放', en: 'Play' },
    'fin.downloadMp4': { 'zh-CN': '下载 MP4', en: 'Download MP4' },
    'fin.toQc': { 'zh-CN': '去质检', en: 'Go to QC' },
    'fin.viewQc': { 'zh-CN': '查看质检', en: 'View QC' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  var state = {
    projects: [],
    episodes: [],
    finals: [],
    projectId: null,
    episodeId: null,
  };

  function el(id) {
    return document.getElementById(id);
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let msg = res.status + " " + res.statusText;
      try {
        const data = await res.json();
        if (data && data.detail) msg = data.detail;
      } catch (e) {}
      throw new Error(msg);
    }
    return res.json();
  }

  function setHint(text) {
    el("hint").textContent = text || "";
  }

  function statusBadge(status) {
    switch (status) {
      case "READY":
        return '<span class="status-pill sp-green">' + _t('fin.statusReady', '已完成') + '</span>';
      case "BUILDING":
        return '<span class="status-pill sp-blue">' + _t('fin.statusBuilding', '剪辑中') + '</span>';
      case "FAILED":
        return '<span class="status-pill sp-red">' + _t('fin.statusFailed', '失败') + '</span>';
      case "PENDING":
        return '<span class="status-pill sp-amber">' + _t('fin.statusPending', '待处理') + '</span>';
      default:
        return '<span class="status-pill sp-gray">' + (status || "") + '</span>';
    }
  }

  function qcBadge(qcStatus) {
    switch (qcStatus) {
      case "PENDING":
        return '<span class="status-pill sp-amber">' + _t('fin.qcPending', '待质检') + '</span>';
      case "APPROVED":
        return '<span class="status-pill sp-green">' + _t('fin.qcApproved', '已通过') + '</span>';
      case "REJECTED":
        return '<span class="status-pill sp-red">' + _t('fin.qcRejected', '已打回') + '</span>';
      default:
        return '<span class="status-pill sp-gray">' + (qcStatus || _t('fin.qcUnknown', '未知')) + '</span>';
    }
  }

  function statusNote(status) {
    if (status === "BUILDING") return _t('fin.noteBuilding', '正在剪辑生成中，请稍候…');
    if (status === "FAILED") return _t('fin.noteFailed', '生成失败，请重试。');
    if (status === "PENDING") return _t('fin.notePending', '排队中…');
    return "";
  }

  function formatDuration(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + ":" + String(r).padStart(2, "0");
  }

  function formatTime(value) {
    if (!value) return "";
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    const pad = (n) => String(n).padStart(2, "0");
    return (
      d.getFullYear() +
      "-" +
      pad(d.getMonth() + 1) +
      "-" +
      pad(d.getDate()) +
      " " +
      pad(d.getHours()) +
      ":" +
      pad(d.getMinutes())
    );
  }

  async function loadProjects() {
    try {
      state.projects = await api("/api/projects");
    } catch (e) {
      setHint(_t('fin.loadProjectsFailed', '加载项目失败：') + e.message);
      return;
    }
    const sel = el("projectSelect");
    sel.innerHTML = "";
    state.projects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.title || p.name || p.id;
      sel.appendChild(opt);
    });
    if (state.projects.length > 0) {
      state.projectId = state.projects[0].id;
      sel.value = state.projectId;
      await loadEpisodes();
    } else {
      renderFinals();
    }
  }

  async function loadEpisodes() {
    const sel = el("episodeSelect");
    sel.innerHTML = "";
    state.episodes = [];
    state.episodeId = null;
    if (!state.projectId) {
      renderFinals();
      return;
    }
    try {
      state.episodes = await api("/api/projects/" + state.projectId + "/episodes");
    } catch (e) {
      setHint(_t('fin.loadEpisodesFailed', '加载剧集失败：') + e.message);
      renderFinals();
      return;
    }
    state.episodes.forEach((ep) => {
      const opt = document.createElement("option");
      opt.value = ep.id;
      opt.textContent = ep.title || ep.name || (_t('fin.episodePrefix', '第 ') + ep.index + _t('fin.episodeSuffix', ' 集'));
      sel.appendChild(opt);
    });
    if (state.episodes.length > 0) {
      state.episodeId = state.episodes[0].id;
      sel.value = state.episodeId;
      await loadFinals();
    } else {
      renderFinals();
    }
  }

  async function loadFinals() {
    if (!state.episodeId) {
      state.finals = [];
      renderFinals();
      return;
    }
    try {
      state.finals = await api("/api/episodes/" + state.episodeId + "/final-cuts");
    } catch (e) {
      setHint(_t('fin.loadFinalsFailed', '加载成片失败：') + e.message);
      state.finals = [];
      renderFinals();
      return;
    }
    renderFinals();
  }

  async function generateFinalCut() {
    if (!state.episodeId) {
      setHint(_t('fin.pickProjectEpisode', '请先选择项目和剧集。'));
      return;
    }
    el("generateBtn").disabled = true;
    setHint(_t('fin.submitting', '正在提交生成任务…'));
    try {
      await api("/api/episodes/" + state.episodeId + "/final-cuts", {
        method: "POST",
      });
      setHint(_t('fin.submitted', '已提交生成任务。'));
      await loadFinals();
    } catch (e) {
      setHint(_t('fin.generateFailed', '生成失败：') + e.message);
    } finally {
      el("generateBtn").disabled = false;
    }
  }

  function renderEmpty(text) {
    const wrap = document.createElement("div");
    wrap.className = "state-empty";
    const icon = document.createElement("i");
    icon.setAttribute("data-lucide", "inbox");
    wrap.appendChild(icon);
    const span = document.createElement("span");
    span.textContent = text;
    wrap.appendChild(span);
    if (window.lucide) lucide.createIcons();
    return wrap;
  }

  function renderFinals() {
    const list = el("finalsList");
    list.innerHTML = "";

    if (!state.episodeId) {
      list.appendChild(renderEmpty(_t('fin.emptyPick', '请先选择项目和剧集。')));
      return;
    }

    if (!state.finals || state.finals.length === 0) {
      list.appendChild(renderEmpty(_t('fin.emptyNoFinals', '这个剧集还没有成片，点击上方“生成成片”开始剪辑。')));
      return;
    }

    state.finals.forEach((fc, idx) => {
      const status = fc.status || "PENDING";

      const item = document.createElement("article");
      item.style.cssText =
        "max-width:880px;display:flex;flex-wrap:wrap;gap:20px;padding:20px 0;" +
        (idx === 0 ? "" : "border-top:1px solid var(--surface);") +
        (idx === state.finals.length - 1 ? "border-bottom:1px solid var(--surface);" : "");

      const poster = document.createElement("div");
      poster.style.cssText =
        "flex:0 0 400px;max-width:100%;width:400px;aspect-ratio:16/9;" +
        "border-radius:10px;overflow:hidden;position:relative;background:#211d1b;";

      const img = document.createElement("img");
      img.src = "/media/finals/" + fc.id + "/poster.jpg";
      img.alt = _t('fin.posterAlt', '成片海报');
      img.loading = "lazy";
      img.style.cssText = "width:100%;height:100%;object-fit:cover;display:block;";
      img.addEventListener("error", () => {
        img.style.display = "none";
      });
      poster.appendChild(img);

      item.appendChild(poster);

      const body = document.createElement("div");
      body.style.cssText = "flex:1 1 320px;min-width:0;display:flex;flex-direction:column;";

      const title = document.createElement("h3");
      title.style.cssText = "font-size:18px;font-weight:600;margin:0 0 8px;color:var(--text);";
      title.textContent = fc.title || (_t('fin.titlePrefix', '成片 ') + fc.id);
      body.appendChild(title);

      const meta = document.createElement("div");
      meta.style.cssText =
        "font-size:13px;color:var(--text-2);display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px;";

      const dur = document.createElement("span");
      dur.textContent = _t('fin.durationPrefix', '时长 ') + formatDuration(fc.durationSeconds);
      meta.appendChild(dur);

      const sep1 = document.createElement("span");
      sep1.style.color = "var(--text-3)";
      sep1.textContent = "·";
      meta.appendChild(sep1);

      const created = document.createElement("span");
      created.textContent = _t('fin.createdPrefix', '创建 ') + formatTime(fc.createdAt);
      meta.appendChild(created);

      const sep2 = document.createElement("span");
      sep2.style.color = "var(--text-3)";
      sep2.textContent = "·";
      meta.appendChild(sep2);

      const statusEl = document.createElement("span");
      statusEl.innerHTML = statusBadge(status);
      meta.appendChild(statusEl);

      if (status === "READY") {
        const sep3 = document.createElement("span");
        sep3.style.color = "var(--text-3)";
        sep3.textContent = "·";
        meta.appendChild(sep3);

        const qcEl = document.createElement("span");
        qcEl.innerHTML = qcBadge(fc.qcStatus);
        meta.appendChild(qcEl);
      }

      body.appendChild(meta);

      const note = statusNote(status);
      if (note) {
        const p = document.createElement("p");
        p.style.cssText = "font-size:13px;color:var(--text-2);margin:0 0 8px;";
        p.textContent = note;
        body.appendChild(p);
      }

      const actions = document.createElement("div");
      actions.style.cssText =
        "display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-top:auto;padding-top:12px;";

      if (status === "READY") {
        const playLink = document.createElement("button");
        playLink.type = "button";
        playLink.className = "btn-quiet";
        playLink.style.cssText =
          "background:none;border:0;padding:0;color:var(--text);font-size:15px;cursor:pointer;";
        playLink.textContent = _t('fin.play', '播放');
        playLink.addEventListener("click", () => {
          const video = document.createElement("video");
          video.controls = true;
          video.autoplay = true;
          video.src = "/media/finals/" + fc.id;
          video.style.cssText = "width:100%;height:100%;display:block;background:#000;";
          poster.innerHTML = "";
          poster.appendChild(video);
        });
        actions.appendChild(playLink);

        const dl = document.createElement("a");
        dl.className = "btn-quiet";
        dl.style.cssText =
          "background:none;border:0;padding:0;color:var(--text);font-size:15px;text-decoration:none;cursor:pointer;";
        dl.href = "/media/finals/" + fc.id;
        dl.setAttribute("download", "");
        dl.textContent = _t('fin.downloadMp4', '下载 MP4');
        actions.appendChild(dl);

        const qcLink = document.createElement("a");
        qcLink.className = "btn-quiet";
        qcLink.style.cssText =
          "background:none;border:0;padding:0;color:var(--text);font-size:15px;text-decoration:none;cursor:pointer;";
        qcLink.href = "/qc.html?id=" + fc.id;
        qcLink.textContent = fc.qcStatus === "PENDING" ? _t('fin.toQc', '去质检') : _t('fin.viewQc', '查看质检');
        actions.appendChild(qcLink);
      }

      body.appendChild(actions);
      item.appendChild(body);

      list.appendChild(item);
    });
  }

  el("projectSelect").addEventListener("change", async (e) => {
    state.projectId = e.target.value;
    await loadEpisodes();
  });

  el("episodeSelect").addEventListener("change", async (e) => {
    state.episodeId = e.target.value;
    await loadFinals();
  });

  el("generateBtn").addEventListener("click", generateFinalCut);

  if (window.DFI18N) {
    DFI18N.onLangChange(function () {
      renderFinals();
    });
  }

  loadProjects();
  if (window.DFI18N) DFI18N.applyI18n(document);
})();
