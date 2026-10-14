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
    return t === "IMAGE" ? "图片" : t === "AUDIO" ? "音频" : t === "VIDEO" ? "视频" : (t || "");
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
      d.textContent = "暂无资产";
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
      d.textContent = "请先在上方选择资产";
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
        o.textContent = "暂无视频资产";
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
      state.projects = await api("/api/projects/");
    } catch (e) {
      state.projects = [];
    }
    const sel = el("export-project");
    sel.innerHTML = "";
    if (!state.projects.length) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = "暂无项目";
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
        o.textContent = "暂无剧集";
        sel.appendChild(o);
        return;
      }
      eps.forEach(ep => {
        const o = document.createElement("option");
        o.value = String(ep.id);
        o.textContent = (ep.episodeNo != null ? "第" + ep.episodeNo + "集 · " : "") + ep.title;
        sel.appendChild(o);
      });
    } catch (e) {
      const o = document.createElement("option");
      o.value = "";
      o.textContent = "加载失败";
      sel.appendChild(o);
    }
  }

  async function loadLogs() {
    if (state.logsLoading) return;
    state.logsLoading = true;
    const body = el("logs-body");
    body.innerHTML = '<tr><td colspan="6" class="text-secondary">加载中…</td></tr>';
    try {
      const logs = await api("/api/tools/op-logs");
      body.innerHTML = "";
      if (!logs.length) {
        body.innerHTML = '<tr><td colspan="6" class="text-secondary">暂无记录</td></tr>';
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
        pill.textContent = l.success ? "成功" : "失败";
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
      body.innerHTML = '<tr><td colspan="6" class="text-danger">加载失败：' + (e.message || "") + '</td></tr>';
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
      if (!ids.length) { setMsg("tag-result", "请先选择资产", "err"); return; }
      const tags = el("tag-input").value.trim();
      if (!tags) { setMsg("tag-result", "请填写标签", "err"); return; }
      const mode = el("tag-mode").value;
      setMsg("tag-result", "处理中…");
      try {
        const r = await api("/api/tools/assets/batch-tag", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ids: ids, tags: tags, mode: mode})
        });
        setMsg("tag-result", "已处理 " + r.count + " 个资产", "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("tag-result", "失败：" + e.message, "err");
      }
    });
  }

  function bindRename() {
    el("rename-btn").addEventListener("click", async () => {
      const inputs = el("rename-list").querySelectorAll("input[data-asset-id]");
      if (!inputs.length) { setMsg("rename-result", "请先选择资产", "err"); return; }
      const renames = {};
      inputs.forEach(inp => {
        const v = inp.value.trim();
        if (v) renames[inp.dataset.assetId] = v;
      });
      if (!Object.keys(renames).length) { setMsg("rename-result", "请填写新文件名", "err"); return; }
      setMsg("rename-result", "处理中…");
      try {
        const r = await api("/api/tools/assets/batch-rename", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({renames: renames})
        });
        setMsg("rename-result", "已重命名 " + r.count + " 个资产", "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("rename-result", "失败：" + e.message, "err");
      }
    });
  }

  function bindConvert() {
    el("convert-btn").addEventListener("click", async () => {
      const assetId = el("convert-video").value;
      if (!assetId) { setMsg("convert-result", "请选择视频资产", "err"); return; }
      const format = el("convert-format").value;
      const widthRaw = el("convert-width").value.trim();
      const body = {assetId: Number(assetId), format: format};
      if (widthRaw) {
        const w = Number(widthRaw);
        if (!Number.isFinite(w) || w < 144 || w > 3840) {
          setMsg("convert-result", "宽度需在 144~3840 之间", "err");
          return;
        }
        body.maxWidth = w;
      }
      const btn = el("convert-btn");
      btn.disabled = true;
      const old = btn.textContent;
      btn.textContent = "转换中…";
      setMsg("convert-result", "");
      try {
        const a = await api("/api/tools/video/convert", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        setMsg("convert-result", "完成：" + a.fileName + "（" + fmtSize(a.fileSize) + "）", "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("convert-result", "失败：" + e.message, "err");
      } finally {
        btn.disabled = false;
        btn.textContent = old;
      }
    });
  }

  function bindExtract() {
    el("extract-btn").addEventListener("click", async () => {
      const assetId = el("extract-video").value;
      if (!assetId) { setMsg("extract-result", "请选择视频资产", "err"); return; }
      const format = el("extract-format").value;
      const btn = el("extract-btn");
      btn.disabled = true;
      const old = btn.textContent;
      btn.textContent = "处理中…";
      setMsg("extract-result", "");
      try {
        const a = await api("/api/tools/video/extract-audio", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({assetId: Number(assetId), format: format})
        });
        setMsg("extract-result", "完成：" + a.fileName + "（" + fmtSize(a.fileSize) + "）", "ok");
        await loadAssets();
        loadLogs();
      } catch (e) {
        setMsg("extract-result", "失败：" + e.message, "err");
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
      if (!id) { setMsg("export-result", "请选择剧集", "err"); return; }
      setMsg("export-result", "开始下载…", "ok");
      window.location.href = "/api/tools/episodes/" + id + "/shots.csv";
    });
  }

  function init() {
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
