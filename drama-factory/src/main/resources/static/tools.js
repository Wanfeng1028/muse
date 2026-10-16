(function () {
  function el(id) { return document.getElementById(id); }
  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let msg = res.status + " " + res.statusText;
      try { const data = await res.json(); if (data && data.detail) msg = data.detail; } catch (e) {}
      throw new Error(msg);
    }
    return res.json();
  }

  const PAGE_I18N = {
    'tool.title': { 'zh-CN': '快捷工具 · AI 短剧工坊', 'en': 'Quick Tools · AI Short Drama Studio' },
    'tool.heading': { 'zh-CN': '快捷工具', 'en': 'Quick Tools' },
    'tool.batchTagTitle': { 'zh-CN': '资产批量打标', 'en': 'Batch tag assets' },
    'tool.selectAll': { 'zh-CN': '全选', 'en': 'Select all' },
    'tool.allTypes': { 'zh-CN': '全部类型', 'en': 'All types' },
    'tool.typeImage': { 'zh-CN': '图片', 'en': 'Image' },
    'tool.typeAudio': { 'zh-CN': '音频', 'en': 'Audio' },
    'tool.typeVideo': { 'zh-CN': '视频', 'en': 'Video' },
    'tool.tagPlaceholder': { 'zh-CN': '标签，逗号分隔', 'en': 'Tags, comma separated' },
    'tool.modeMerge': { 'zh-CN': '合并', 'en': 'Merge' },
    'tool.modeReplace': { 'zh-CN': '替换', 'en': 'Replace' },
    'tool.batchTagBtn': { 'zh-CN': '批量打标', 'en': 'Tag selected' },
    'tool.batchRenameTitle': { 'zh-CN': '资产批量重命名', 'en': 'Batch rename assets' },
    'tool.pickAssetsFirst': { 'zh-CN': '请先在上方选择资产', 'en': 'Pick assets above first' },
    'tool.batchRenameBtn': { 'zh-CN': '批量重命名', 'en': 'Rename selected' },
    'tool.convertTitle': { 'zh-CN': '视频格式转换', 'en': 'Convert video format' },
    'tool.widthPlaceholder': { 'zh-CN': '宽度（可选，144~3840）', 'en': 'Width (optional, 144–3840)' },
    'tool.convertBtn': { 'zh-CN': '开始转换', 'en': 'Convert' },
    'tool.extractTitle': { 'zh-CN': '音频提取', 'en': 'Extract audio' },
    'tool.extractBtn': { 'zh-CN': '提取音频', 'en': 'Extract audio' },
    'tool.exportTitle': { 'zh-CN': '分镜表导出', 'en': 'Export shot list' },
    'tool.exportBtn': { 'zh-CN': '导出 CSV', 'en': 'Export CSV' },
    'tool.logsTitle': { 'zh-CN': '操作记录', 'en': 'Operation log' },
    'tool.colTime': { 'zh-CN': '时间', 'en': 'Time' },
    'tool.colTool': { 'zh-CN': '工具', 'en': 'Tool' },
    'tool.colOperation': { 'zh-CN': '操作', 'en': 'Operation' },
    'tool.colParams': { 'zh-CN': '参数', 'en': 'Params' },
    'tool.colResult': { 'zh-CN': '结果', 'en': 'Result' },
    'tool.colStatus': { 'zh-CN': '状态', 'en': 'Status' },
    'tool.noAssets': { 'zh-CN': '暂无资产', 'en': 'No assets' },
    'tool.noVideoAssets': { 'zh-CN': '暂无视频资产', 'en': 'No video assets' },
    'tool.noProjects': { 'zh-CN': '暂无项目', 'en': 'No projects' },
    'tool.noEpisodes': { 'zh-CN': '暂无剧集', 'en': 'No episodes' },
    'tool.loadFailed': { 'zh-CN': '加载失败', 'en': 'Failed to load' },
    'tool.noRecords': { 'zh-CN': '暂无记录', 'en': 'No records' },
    'tool.success': { 'zh-CN': '成功', 'en': 'Success' },
    'tool.failed': { 'zh-CN': '失败', 'en': 'Failed' },
    'tool.episodeNoFmt': { 'zh-CN': '第{0}集 · {1}', 'en': 'Ep {0} · {1}' },
    'tool.selectAssetsFirst': { 'zh-CN': '请先选择资产', 'en': 'Pick assets first' },
    'tool.fillTags': { 'zh-CN': '请填写标签', 'en': 'Enter tags first' },
    'tool.processing': { 'zh-CN': '处理中…', 'en': 'Working…' },
    'tool.taggedCount': { 'zh-CN': '已处理 {0} 个资产', 'en': 'Tagged {0} asset(s)' },
    'tool.fillNewName': { 'zh-CN': '请填写新文件名', 'en': 'Enter new file names first' },
    'tool.renamedCount': { 'zh-CN': '已重命名 {0} 个资产', 'en': 'Renamed {0} asset(s)' },
    'tool.pickVideo': { 'zh-CN': '请选择视频资产', 'en': 'Pick a video asset first' },
    'tool.widthRange': { 'zh-CN': '宽度需在 144~3840 之间', 'en': 'Width must be between 144 and 3840' },
    'tool.converting': { 'zh-CN': '转换中…', 'en': 'Converting…' },
    'tool.convertDone': { 'zh-CN': '完成：{0}（{1}）', 'en': 'Done: {0} ({1})' },
    'tool.pickEpisode': { 'zh-CN': '请选择剧集', 'en': 'Pick an episode first' },
    'tool.downloadStarted': { 'zh-CN': '开始下载…', 'en': 'Download starting…' },
    'tool.loadLogsFailed': { 'zh-CN': '加载失败：{0}', 'en': 'Failed to load: {0}' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  function _fmt(key, zh, args) {
    var s = _t(key, zh);
    for (var i = 0; i < args.length; i++) {
      s = s.replace('{' + i + '}', args[i]);
    }
    return s;
  }

  const state = {
    assets: [],
    selected: new Set(),
    projects: [],
    logsLoading: false
  };

  function fmtSize(n) {
    if (n == null) return "";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(2) + " MB";
  }
  function typeLabel(t) {
    return t === "IMAGE" ? _t("tool.typeImage", "图片") : t === "AUDIO" ? _t("tool.typeAudio", "音频") : t === "VIDEO" ? _t("tool.typeVideo", "视频") : (t || "");
  }
  function setMsg(id, text, kind) {
    const node = el(id);
    if (!node) return;
    node.textContent = text || "";
    node.className = "mt-2 small" + (kind === "err" ? " text-danger" : kind === "ok" ? " text-success" : "");
  }

  function renderAssetPicker() {
    const filter = el("tag-type-filter").value;
    const list = el("tag-asset-list");
    list.innerHTML = "";
    const filtered = state.assets.filter(a => !filter || a.type === filter);
    if (!filtered.length) {
      const d = document.createElement("div");
      d.className = "text-secondary small";
      d.textContent = _t("tool.noAssets", "暂无资产");
      list.appendChild(d);
      return;
    }
    filtered.forEach(a => {
      const wrap = document.createElement("label");
      wrap.className = "form-check";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "form-check-input";
      cb.checked = state.selected.has(a.id);
      cb.addEventListener("change", () => {
        if (cb.checked) state.selected.add(a.id);
        else state.selected.delete(a.id);
        renderRenameList();
      });
      const span = document.createElement("span");
      span.className = "form-check-label";
      span.textContent = a.fileName + " · " + typeLabel(a.type) + (a.tags ? " · " + a.tags : "");
      wrap.appendChild(cb);
      wrap.appendChild(span);
      list.appendChild(wrap);
    });
  }

  function renderRenameList() {
    const box = el("rename-list");
    box.innerHTML = "";
    if (!state.selected.size) {
      const d = document.createElement("div");
      d.className = "text-secondary small";
      d.textContent = _t("tool.pickAssetsFirst", "请先在上方选择资产");
      box.appendChild(d);
      return;
    }
    state.selected.forEach(id => {
      const a = state.assets.find(x => x.id === id);
      if (!a) return;
      const row = document.createElement("div");
      row.className = "input-group input-group-sm mb-1";
      const label = document.createElement("span");
      label.className = "input-group-text";
      label.style.maxWidth = "180px";
      label.style.overflow = "hidden";
      label.textContent = a.fileName;
      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-control";
      input.value = a.fileName;
      input.dataset.assetId = String(a.id);
      row.appendChild(label);
      row.appendChild(input);
      box.appendChild(row);
    });
  }

  function fillVideoSelects() {
    const videos = state.assets.filter(a => a.type === "VIDEO");
    ["convert-video", "extract-video"].forEach(id => {
      const sel = el(id);
      sel.innerHTML = "";
      if (!videos.length) {
        const o = document.createElement("option");
        o.value = "";
        o.textContent = _t("tool.noVideoAssets", "暂无视频资产");
        sel.appendChild(o);
        return;
      }
      videos.forEach(v => {
        const o = document.createElement("option");
        o.value = String(v.id);
        o.textContent = v.fileName;
        sel.appendChild(o);
      });
    });
  }

  async function loadAssets() {
    try {
      state.assets = await api("/api/assets/");
    } catch (e) {
      state.assets = [];
    }
    renderAssetPicker();
    renderRenameList();
    fillVideoSelects();
  }

  async function loadProjects() {
    try {
      state.projects = await api("/api/projects");
    } catch (e) {
      state.projects = [];
    }
    const sel = el("export-project");
    sel.innerHTML = "";
    if (!state.projects.length) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = _t("tool.noProjects", "暂无项目");
      sel.appendChild(o);
      el("export-episode").innerHTML = "";
      return;
    }
    state.projects.forEach(p => {
      const o = document.createElement("option");
      o.value = String(p.id);
      o.textContent = p.title;
      sel.appendChild(o);
    });
    await loadEpisodes();
  }

  async function loadEpisodes() {
    const sel = el("export-episode");
    sel.innerHTML = "";
    const pid = el("export-project").value;
    if (!pid) return;
    try {
      const eps = await api("/api/projects/" + pid + "/episodes");
      if (!eps.length) {
        const o = document.createElement("option");
        o.value = "";
        o.textContent = _t("tool.noEpisodes", "暂无剧集");
        sel.appendChild(o);
        return;
      }
      eps.forEach(ep => {
        const o = document.createElement("option");
        o.value = String(ep.id);
        o.textContent = (ep.episodeNo != null ? _fmt("tool.episodeNoFmt", "第{0}集 · {1}", [ep.episodeNo, ep.title]) : ep.title);
        sel.appendChild(o);
      });
    } catch (e) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = _t("tool.loadFailed", "加载失败");
      sel.appendChild(o);
    }
  }

  async function loadLogs() {
    if (state.logsLoading) return;
    state.logsLoading = true;
    const body = el("logs-body");
    body.innerHTML = '<tr><td colspan="6" class="text-secondary">' + _t("c.loading", "加载中…") + '</td></tr>';
    try {
      const logs = await api("/api/tools/op-logs");
      body.innerHTML = "";
      if (!logs.length) {
        body.innerHTML = '<tr><td colspan="6" class="text-secondary">' + _t("tool.noRecords", "暂无记录") + '</td></tr>';
        return;
      }
      logs.forEach(l => {
        const tr = document.createElement("tr");
        const td1 = document.createElement("td");
        td1.textContent = l.createdAt || "";
        const td2 = document.createElement("td");
        td2.textContent = l.toolName || "";
        const td3 = document.createElement("td");
        td3.textContent = l.operation || "";
        const td4 = document.createElement("td");
        td4.textContent = typeof l.params === "string" ? l.params : JSON.stringify(l.params || "");
        td4.style.maxWidth = "220px";
        td4.style.overflow = "hidden";
        td4.style.textOverflow = "ellipsis";
        td4.style.whiteSpace = "nowrap";
        const td5 = document.createElement("td");
        td5.textContent = typeof l.result === "string" ? l.result : JSON.stringify(l.result || "");
        td5.style.maxWidth = "220px";
        td5.style.overflow = "hidden";
        td5.style.textOverflow = "ellipsis";
        td5.style.whiteSpace = "nowrap";
        const td6 = document.createElement("td");
        const pill = document.createElement("span");
        pill.className = "status-pill " + (l.success ? "sp-green" : "sp-red");
        pill.textContent = l.success ? _t("tool.success", "成功") : _t("tool.failed", "失败");
        td6.appendChild(pill);
        tr.appendChild(td1);
        tr.appendChild(td2);
        tr.appendChild(td3);
        tr.appendChild(td4);
        tr.appendChild(td5);
        tr.appendChild(td6);
        body.appendChild(tr);
      });
    } catch (e) {
      body.innerHTML = '<tr><td colspan="6" class="text-danger">' + _fmt("tool.loadLogsFailed", "加载失败：{0}", [e.message || ""]) + '</td></tr>';
    } finally {
      state.logsLoading = false;
    }
  }

  function bindTag() {
    el("tag-select-all").addEventListener("change", e => {
      const filter = el("tag-type-filter").value;
      const filtered = state.assets.filter(a => !filter || a.type === filter);
      if (e.target.checked) filtered.forEach(a => state.selected.add(a.id));
      else filtered.forEach(a => state.selected.delete(a.id));
      renderAssetPicker();
      renderRenameList();
    });
    el("tag-type-filter").addEventListener("change", renderAssetPicker);
    el("tag-btn").addEventListener("click", async () => {
      const ids = Array.from(state.selected);
      if (!ids.length) { setMsg("tag-result", _t("tool.selectAssetsFirst", "请先选择资产"), "err"); return; }
      const tags = el("tag-input").value.trim();
      if (!tags) { setMsg("tag-result", _t("tool.fillTags", "请填写标签"), "err"); return; }
      const mode = el("tag-mode").value;
      setMsg("tag-result", _t("tool.processing", "处理中…"));
      try {
        const r = await api("/api/tools/assets/batch-tag", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ids: ids, tags: tags, mode: mode})
        });
        setMsg("tag-result", _fmt("tool.taggedCount", "已处理 {0} 个资产", [r.count]), "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("tag-result", _fmt("tool.loadLogsFailed", "加载失败：{0}", [e.message]), "err");
      }
    });
  }

  function bindRename() {
    el("rename-btn").addEventListener("click", async () => {
      const inputs = el("rename-list").querySelectorAll("input[data-asset-id]");
      if (!inputs.length) { setMsg("rename-result", _t("tool.selectAssetsFirst", "请先选择资产"), "err"); return; }
      const renames = {};
      inputs.forEach(inp => {
        const v = inp.value.trim();
        if (v) renames[inp.dataset.assetId] = v;
      });
      if (!Object.keys(renames).length) { setMsg("rename-result", _t("tool.fillNewName", "请填写新文件名"), "err"); return; }
      setMsg("rename-result", _t("tool.processing", "处理中…"));
      try {
        const r = await api("/api/tools/assets/batch-rename", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({renames: renames})
        });
        setMsg("rename-result", _fmt("tool.renamedCount", "已重命名 {0} 个资产", [r.count]), "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("rename-result", _fmt("tool.loadLogsFailed", "加载失败：{0}", [e.message]), "err");
      }
    });
  }

  function bindConvert() {
    el("convert-btn").addEventListener("click", async () => {
      const assetId = el("convert-video").value;
      if (!assetId) { setMsg("convert-result", _t("tool.pickVideo", "请选择视频资产"), "err"); return; }
      const format = el("convert-format").value;
      const widthRaw = el("convert-width").value.trim();
      const body = {assetId: Number(assetId), format: format};
      if (widthRaw) {
        const w = Number(widthRaw);
        if (!Number.isFinite(w) || w < 144 || w > 3840) {
          setMsg("convert-result", _t("tool.widthRange", "宽度需在 144~3840 之间"), "err");
          return;
        }
        body.maxWidth = w;
      }
      const btn = el("convert-btn");
      btn.disabled = true;
      const old = btn.textContent;
      btn.textContent = _t("tool.converting", "转换中…");
      setMsg("convert-result", "");
      try {
        const a = await api("/api/tools/video/convert", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        setMsg("convert-result", _fmt("tool.convertDone", "完成：{0}（{1}）", [a.fileName, fmtSize(a.fileSize)]), "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("convert-result", _fmt("tool.loadLogsFailed", "加载失败：{0}", [e.message]), "err");
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  }

  function bindExtract() {
    el("extract-btn").addEventListener("click", async () => {
      const assetId = el("extract-video").value;
      if (!assetId) { setMsg("extract-result", _t("tool.pickVideo", "请选择视频资产"), "err"); return; }
      const format = el("extract-format").value;
      const btn = el("extract-btn");
      btn.disabled = true;
      const old = btn.textContent;
      btn.textContent = _t("tool.processing", "处理中…");
      setMsg("extract-result", "");
      try {
        const a = await api("/api/tools/video/extract-audio", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({assetId: Number(assetId), format: format})
        });
        setMsg("extract-result", _fmt("tool.convertDone", "完成：{0}（{1}）", [a.fileName, fmtSize(a.fileSize)]), "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("extract-result", _fmt("tool.loadLogsFailed", "加载失败：{0}", [e.message]), "err");
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  }

  function bindExport() {
    el("export-project").addEventListener("change", loadEpisodes);
    el("export-btn").addEventListener("click", () => {
      const id = el("export-episode").value;
      if (!id) { setMsg("export-result", _t("tool.pickEpisode", "请选择剧集"), "err"); return; }
      setMsg("export-result", _t("tool.downloadStarted", "开始下载…"), "ok");
      window.location.href = "/api/tools/episodes/" + id + "/shots.csv";
    });
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n(document);
    bindTag();
    bindRename();
    bindConvert();
    bindExtract();
    bindExport();
    el("logs-refresh").addEventListener("click", loadLogs);
    loadAssets();
    loadProjects();
    loadLogs();
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  if (window.DFI18N) {
    DFI18N.onLangChange(function () {
      renderAssetPicker();
      renderRenameList();
      fillVideoSelects();
      loadEpisodes();
      loadLogs();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
