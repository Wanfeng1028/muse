(function () {
  "use strict";

  var PAGE_I18N = {
    "prov.loadFailed": { "zh-CN": "加载供应商失败", "en": "Failed to load providers" },
    "prov.updated": { "zh-CN": "已更新", "en": "Updated" },
    "prov.updateFailed": { "zh-CN": "更新失败", "en": "Update failed" },
    "prov.confirmDelete": { "zh-CN": "确定删除吗？", "en": "Delete this?" },
    "prov.deleted": { "zh-CN": "已删除", "en": "Deleted" },
    "prov.deleteFailed": { "zh-CN": "删除失败", "en": "Delete failed" },
    "prov.testing": { "zh-CN": "正在检测…", "en": "Checking…" },
    "prov.testFailed": { "zh-CN": "检测失败", "en": "Check failed" },
    "prov.noProvidersInModule": { "zh-CN": "暂无", "en": "No " },
    "prov.noProvidersSuffix": { "zh-CN": "供应商", "en": " providers yet" },
    "prov.addFromPreset": { "zh-CN": "从预设添加", "en": "Add from preset" },
    "prov.addProviderOf": { "zh-CN": "添加", "en": "Add " },
    "prov.addProviderSuffix": { "zh-CN": "供应商", "en": " provider" },
    "prov.testConnection": { "zh-CN": "测试连接", "en": "Test connection" },
    "prov.manualAdd": { "zh-CN": "手动添加", "en": "Add manually" },
    "prov.connectionOk": { "zh-CN": "连接正常", "en": "Connection OK" },
    "prov.authFailed": { "zh-CN": "密钥无效", "en": "Invalid key" },
    "prov.rateLimited": { "zh-CN": "触发限流", "en": "Rate limited" },
    "prov.unreachable": { "zh-CN": "网络不可达", "en": "Unreachable" },
    "prov.providerError": { "zh-CN": "服务方异常", "en": "Provider error" },
    "prov.unsupported": { "zh-CN": "暂不支持", "en": "Not supported" },
    "prov.editProviderTitle": { "zh-CN": "编辑媒体供应商", "en": "Edit media provider" },
    "prov.addProviderTitle": { "zh-CN": "添加供应商", "en": "Add provider" },
    "prov.keepKeyPlaceholder": { "zh-CN": "留空则保留原密钥", "en": "Leave blank to keep the current key" },
    "prov.nameRequired": { "zh-CN": "供应商名不能为空", "en": "Provider name is required" },
    "prov.saveOk": { "zh-CN": "保存成功", "en": "Saved" },
    "prov.saveFailed": { "zh-CN": "保存失败", "en": "Save failed" },
    "prov.addFromPresetOf": { "zh-CN": "从预设添加", "en": "Add from preset: " },
    "prov.addFromPresetSuffix": { "zh-CN": "供应商", "en": " provider" },
    "prov.loadingPresets": { "zh-CN": "加载预设中…", "en": "Loading presets…" },
    "prov.presetsFailed": { "zh-CN": "预设加载失败", "en": "Failed to load presets" },
    "prov.noPresets": { "zh-CN": "该模块暂无预设，可手动添加", "en": "No presets for this module; add one manually." },
    "prov.pasteKey": { "zh-CN": "粘贴你的 API Key", "en": "Paste your API Key" },
    "prov.add": { "zh-CN": "添加", "en": "Add" },
    "prov.pasteKeyFirst": { "zh-CN": "请先粘贴 API Key", "en": "Paste an API Key first" },
    "prov.added": { "zh-CN": "已添加", "en": "Added" },
    "prov.presetNotFound": { "zh-CN": "预设不存在", "en": "Preset not found" },
    "prov.addFailed": { "zh-CN": "添加失败", "en": "Add failed" },
    "prov.editModelTitle": { "zh-CN": "编辑模型", "en": "Edit model" },
    "prov.addModelTitle": { "zh-CN": "添加模型", "en": "Add model" },
    "prov.modelNameRequired": { "zh-CN": "模型名不能为空", "en": "Model name is required" },
    "prov.module.VIDEO": { "zh-CN": "视频", "en": "Video" },
    "prov.module.TEXT": { "zh-CN": "文本", "en": "Text" },
    "prov.module.IMAGE": { "zh-CN": "图片", "en": "Image" },
    "prov.module.MUSIC": { "zh-CN": "音乐", "en": "Music" },
    "prov.module.TTS": { "zh-CN": "TTS 语音", "en": "TTS voice" },
    "prov.module.AVATAR": { "zh-CN": "数字人", "en": "Digital human" }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  function icons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function toast(msg, kind) {
    if (window.Harness && typeof window.Harness.toast === "function") { window.Harness.toast(msg, kind); return; }
    if (window.toast) { window.toast(msg, kind); return; }
    alert(msg);
  }

  function api(method, url, body, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    xhr.setRequestHeader("Accept", "application/json");
    if (body !== undefined && body !== null) {
      xhr.setRequestHeader("Content-Type", "application/json");
    }
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      var data = null;
      if (xhr.responseText) {
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
      }
      cb(xhr.status, data);
    };
    xhr.send(body !== undefined && body !== null ? JSON.stringify(body) : null);
  }

  var providers = [];
  var editingProviderId = null;
  var editingModelProviderId = null;
  var editingModelId = null;

  var MODULES = [
    { id: "VIDEO", label: "视频" },
    { id: "TEXT", label: "文本" },
    { id: "IMAGE", label: "图片" },
    { id: "MUSIC", label: "音乐" },
    { id: "TTS", label: "TTS 语音" },
    { id: "AVATAR", label: "数字人" }
  ];

  function moduleLabel(id) {
    var key = "prov.module." + id;
    var v = _t(key, null);
    if (v && v !== key) return v;
    for (var i = 0; i < MODULES.length; i++) {
      if (MODULES[i].id === id) return MODULES[i].label;
    }
    return id || "视频";
  }

  var listEl = document.getElementById("provider-list");
  var providerModal = document.getElementById("provider-modal");
  var modelModal = document.getElementById("model-modal");

  function openModal(el) {
    providerModal.classList.add("is-hidden");
    modelModal.classList.add("is-hidden");
    el.classList.remove("is-hidden");
    icons();
  }
  function closeModal(el) {
    el.classList.add("is-hidden");
  }

  function loadProviders() {
    api("GET", "/api/providers", null, function (status, data) {
      if (status >= 200 && status < 300 && Array.isArray(data)) {
        providers = data;
        render();
      } else {
        toast(_t("prov.loadFailed", "加载供应商失败"), "error");
      }
    });
  }

  function findProvider(id) {
    for (var i = 0; i < providers.length; i++) {
      if (String(providers[i].id) === String(id)) return providers[i];
    }
    return null;
  }

  function render() {
    if (!listEl) return;
    var html = "";
    for (var g = 0; g < MODULES.length; g++) {
      var mod = MODULES[g];
      html += '<h3 class="pv-module-title">' + esc(moduleLabel(mod.id)) + "</h3>";
      var count = 0;
      for (var i = 0; i < providers.length; i++) {
        if ((providers[i].module || "VIDEO") === mod.id) {
          html += renderProvider(providers[i]);
          count++;
        }
      }
      if (!count) {
        html += '<p class="hint">' + esc(_t("prov.noProvidersInModule", "暂无")) + esc(moduleLabel(mod.id)) + esc(_t("prov.noProvidersSuffix", "供应商")) + "</p>";
      }
      html += '<div style="margin:4px 0 20px;display:flex;gap:8px;flex-wrap:wrap">' +
        '<button type="button" class="btn btn-quiet btn-sm pv-preset-add" data-module="' + esc(mod.id) +
        '"><i data-lucide="sparkles"></i> ' + esc(_t("prov.addFromPreset", "从预设添加")) + '</button>' +
        '<button type="button" class="btn btn-quiet btn-sm pv-provider-add" data-module="' +
        esc(mod.id) + '"><i data-lucide="plus"></i> ' + esc(_t("prov.addProviderOf", "添加")) + esc(moduleLabel(mod.id)) + esc(_t("prov.addProviderSuffix", "供应商")) + "</button></div>";
    }
    listEl.innerHTML = html;
    bind();
    icons();
  }

  function renderProvider(p) {
    var h = '<article class="card pv-card" data-pid="' + esc(p.id) + '">';
    h += '<div class="card-head">';
    h += '<div>';
    h += '<div style="font-weight:600">' + esc(p.name) + "</div>";
    if (p.description) h += '<p class="hint">' + esc(p.description) + "</p>";
    h += "</div>";
    h += '<div style="display:flex;align-items:center;gap:8px">';
    h += '<input type="checkbox" class="pv-switch" data-pid="' + esc(p.id) + '"' + (p.enabled ? " checked" : "") + " />";
    h += '<button type="button" class="btn btn-quiet btn-sm pv-test" data-pid="' + esc(p.id) + '"><i data-lucide="plug-zap"></i> ' + esc(_t("prov.testConnection", "测试连接")) + '</button>';
    h += '<button type="button" class="btn btn-quiet btn-sm pv-edit" data-pid="' + esc(p.id) + '"><i data-lucide="pencil"></i></button>';
    h += '<button type="button" class="btn btn-quiet btn-sm pv-del" data-pid="' + esc(p.id) + '"><i data-lucide="trash-2"></i></button>';
    h += "</div>";
    h += "</div>";

    h += '<div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text-3);margin:8px 0">';
    if (p.apiAddress) h += '<span class="mono">' + esc(p.apiAddress) + "</span>";
    if (p.maskedKey) h += '<span class="mono">' + esc(p.maskedKey) + "</span>";
    h += "</div>";

    h += '<div class="pv-models">';
    var models = p.models || [];
    for (var j = 0; j < models.length; j++) {
      h += renderModel(p.id, models[j]);
    }
    h += "</div>";
    h += '<div style="margin-top:8px">';
    h += '<button type="button" class="btn btn-quiet btn-sm pv-model-add" data-pid="' + esc(p.id) + '"><i data-lucide="plus"></i> ' + esc(_t("prov.manualAdd", "手动添加")) + '</button>';
    h += "</div>";
    h += '<div class="pv-test-result" style="margin-top:8px;font-size:12px" hidden></div>';
    h += "</article>";
    return h;
  }

  function renderModel(pid, m) {
    var h = '<div class="pv-model-row" data-pid="' + esc(pid) + '" data-mid="' + esc(m.id) + '" style="display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border-soft);flex-wrap:wrap">';
    h += '<div style="min-width:160px">';
    h += '<div style="font-weight:600;font-size:13px">' + esc(m.displayName) + "</div>";
    if (m.modelId) h += '<div class="mono" style="font-size:12px;color:var(--text-3)">' + esc(m.modelId) + "</div>";
    h += "</div>";
    if (m.scale) h += '<span class="badge">' + esc(m.scale) + "</span>";
    if (m.description) h += '<span class="hint">' + esc(m.description) + "</span>";
    if (m.concurrency) h += '<span class="hint">×' + esc(m.concurrency) + "</span>";
    h += '<div style="margin-left:auto;display:flex;gap:6px">';
    h += '<button type="button" class="btn btn-quiet btn-sm pv-model-edit" data-pid="' + esc(pid) + '" data-mid="' + esc(m.id) + '"><i data-lucide="pencil"></i></button>';
    h += '<button type="button" class="btn btn-quiet btn-sm pv-model-del" data-pid="' + esc(pid) + '" data-mid="' + esc(m.id) + '"><i data-lucide="trash-2"></i></button>';
    h += "</div>";
    h += "</div>";
    return h;
  }

  function bind() {
    if (!listEl) return;

    var switches = listEl.querySelectorAll(".pv-switch");
    for (var i = 0; i < switches.length; i++) {
      switches[i].onchange = onSwitchChange;
    }

    var edits = listEl.querySelectorAll(".pv-edit");
    for (var j = 0; j < edits.length; j++) {
      edits[j].onclick = function () { openProviderModal(this.getAttribute("data-pid")); };
    }

    var dels = listEl.querySelectorAll(".pv-del");
    for (var k = 0; k < dels.length; k++) {
      dels[k].onclick = function () { onDeleteProvider(this.getAttribute("data-pid")); };
    }

    var tests = listEl.querySelectorAll(".pv-test");
    for (var t = 0; t < tests.length; t++) {
      tests[t].onclick = function () { onTestConnection(this); };
    }

    var presetAdds = listEl.querySelectorAll(".pv-preset-add");
    for (var r = 0; r < presetAdds.length; r++) {
      presetAdds[r].onclick = function () { openPresetPicker(this.getAttribute("data-module")); };
    }

    var provAdds = listEl.querySelectorAll(".pv-provider-add");
    for (var q = 0; q < provAdds.length; q++) {
      provAdds[q].onclick = function () { openProviderModal(null, this.getAttribute("data-module")); };
    }

    var modelAdds = listEl.querySelectorAll(".pv-model-add");
    for (var a = 0; a < modelAdds.length; a++) {
      modelAdds[a].onclick = function () { openModelModal(this.getAttribute("data-pid"), null); };
    }

    var modelEdits = listEl.querySelectorAll(".pv-model-edit");
    for (var b = 0; b < modelEdits.length; b++) {
      modelEdits[b].onclick = function () {
        openModelModal(this.getAttribute("data-pid"), this.getAttribute("data-mid"));
      };
    }

    var modelDels = listEl.querySelectorAll(".pv-model-del");
    for (var c = 0; c < modelDels.length; c++) {
      modelDels[c].onclick = function () {
        onDeleteModel(this.getAttribute("data-pid"), this.getAttribute("data-mid"));
      };
    }
  }

  function onSwitchChange() {
    var pid = this.getAttribute("data-pid");
    var p = findProvider(pid);
    if (!p) return;
    var enabled = !!this.checked;
    api("PUT", "/api/providers/" + encodeURIComponent(pid), {
      name: p.name,
      module: p.module || "VIDEO",
      description: p.description || "",
      apiKey: "",
      apiAddress: p.apiAddress || "",
      enabled: enabled
    }, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.updated", "已更新"), "success");
        loadProviders();
      } else {
        toast(_t("prov.updateFailed", "更新失败"), "error");
        loadProviders();
      }
    });
  }

  function onDeleteProvider(pid) {
    if (!window.confirm(_t("prov.confirmDelete", "确定删除吗？"))) return;
    api("DELETE", "/api/providers/" + encodeURIComponent(pid), null, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.deleted", "已删除"), "success");
        loadProviders();
      } else {
        toast(_t("prov.deleteFailed", "删除失败"), "error");
      }
    });
  }

  var PV_TEST_MAP = {
    OK: ["var(--green-soft)", "var(--green)", "prov.connectionOk", "连接正常"],
    AUTH_FAILED: ["var(--red-soft)", "var(--red)", "prov.authFailed", "密钥无效"],
    RATE_LIMITED: ["var(--amber-soft)", "var(--amber)", "prov.rateLimited", "触发限流"],
    UNREACHABLE: ["var(--red-soft)", "var(--red)", "prov.unreachable", "网络不可达"],
    PROVIDER_ERROR: ["var(--red-soft)", "var(--red)", "prov.providerError", "服务方异常"],
    UNSUPPORTED: ["var(--surface-2)", "var(--text-3)", "prov.unsupported", "暂不支持"]
  };

  function onTestConnection(btn) {
    var pid = btn.getAttribute("data-pid");
    var card = btn.closest(".pv-card");
    var box = card.querySelector(".pv-test-result");
    btn.disabled = true;
    box.hidden = false;
    box.innerHTML = '<span class="hint">' + esc(_t("prov.testing", "正在检测…")) + '</span>';
    api("POST", "/api/providers/" + encodeURIComponent(pid) + "/test", null, function (status, data) {
      btn.disabled = false;
      if (status !== 200 || !data) {
        box.innerHTML = '<span class="badge" style="background:var(--red-soft);color:var(--red)">' + esc(_t("prov.testFailed", "检测失败")) + '</span>'
          + ' <span class="hint">HTTP ' + esc(status) + '</span>';
        icons();
        return;
      }
      var entry = PV_TEST_MAP[data.status] || PV_TEST_MAP.UNSUPPORTED;
      box.innerHTML = '<span class="badge" style="background:' + entry[0] + ';color:' + entry[1] + '">'
        + esc(_t(entry[2], entry[3])) + '</span> <span class="hint">' + esc(data.detail || "") + '</span>';
      icons();
    });
  }

  function onDeleteModel(pid, mid) {
    if (!window.confirm(_t("prov.confirmDelete", "确定删除吗？"))) return;
    api("DELETE", "/api/providers/" + encodeURIComponent(pid) + "/models/" + encodeURIComponent(mid), null, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.deleted", "已删除"), "success");
        loadProviders();
      } else {
        toast(_t("prov.deleteFailed", "删除失败"), "error");
      }
    });
  }

  function openProviderModal(pid, presetModule) {
    editingProviderId = pid || null;
    var title = document.getElementById("pm-title");
    var nameEl = document.getElementById("pm-name");
    var moduleEl = document.getElementById("pm-module");
    var descEl = document.getElementById("pm-desc");
    var keyEl = document.getElementById("pm-key");
    var addrEl = document.getElementById("pm-addr");

    keyEl.type = "password";
    setKeyToggleIcon(false);

    if (pid) {
      var p = findProvider(pid);
      title.textContent = _t("prov.editProviderTitle", "编辑媒体供应商");
      nameEl.value = p ? (p.name || "") : "";
      if (moduleEl) moduleEl.value = (p && p.module) || "VIDEO";
      descEl.value = p ? (p.description || "") : "";
      keyEl.value = "";
      keyEl.placeholder = _t("prov.keepKeyPlaceholder", "留空则保留原密钥");
      addrEl.value = p ? (p.apiAddress || "") : "";
    } else {
      title.textContent = _t("prov.addProviderTitle", "添加供应商");
      nameEl.value = "";
      if (moduleEl) moduleEl.value = presetModule || "VIDEO";
      descEl.value = "";
      keyEl.value = "";
      keyEl.placeholder = "";
      addrEl.value = "";
    }
    openModal(providerModal);
    nameEl.focus();
  }

  function setKeyToggleIcon(shown) {
    var btn = document.getElementById("pm-key-toggle");
    if (!btn) return;
    btn.innerHTML = shown ? '<i data-lucide="eye-off"></i>' : '<i data-lucide="eye"></i>';
    icons();
  }

  function saveProvider() {
    var nameEl = document.getElementById("pm-name");
    var descEl = document.getElementById("pm-desc");
    var keyEl = document.getElementById("pm-key");
    var addrEl = document.getElementById("pm-addr");

    var name = (nameEl.value || "").trim();
    if (!name) { toast(_t("prov.nameRequired", "供应商名不能为空"), "error"); return; }

    var moduleEl = document.getElementById("pm-module");
    var payload = {
      name: name,
      module: moduleEl ? moduleEl.value : "VIDEO",
      description: descEl.value || "",
      apiKey: keyEl.value || "",
      apiAddress: addrEl.value || ""
    };

    var method, url;
    if (editingProviderId) {
      method = "PUT";
      url = "/api/providers/" + encodeURIComponent(editingProviderId);
    } else {
      method = "POST";
      url = "/api/providers";
    }

    api(method, url, payload, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.saveOk", "保存成功"), "success");
        closeModal(providerModal);
        loadProviders();
      } else {
        toast(_t("prov.saveFailed", "保存失败"), "error");
      }
    });
  }

  var presetModal = document.getElementById("preset-modal");

  function openPresetPicker(module) {
    var title = document.getElementById("preset-title");
    var listBox = document.getElementById("preset-list");
    if (title) title.textContent = _t("prov.addFromPresetOf", "从预设添加") + moduleLabel(module) + _t("prov.addFromPresetSuffix", "供应商");
    if (listBox) listBox.innerHTML = '<p class="hint">' + esc(_t("prov.loadingPresets", "加载预设中…")) + '</p>';
    openModal(presetModal);
    api("GET", "/api/providers/presets?module=" + encodeURIComponent(module), null, function (status, data) {
      if (!(status >= 200 && status < 300 && Array.isArray(data))) {
        if (listBox) listBox.innerHTML = '<p class="hint">' + esc(_t("prov.presetsFailed", "预设加载失败")) + '</p>';
        return;
      }
      if (!data.length) {
        if (listBox) listBox.innerHTML = '<p class="hint">' + esc(_t("prov.noPresets", "该模块暂无预设，可手动添加")) + '</p>';
        return;
      }
      var h = "";
      for (var i = 0; i < data.length; i++) {
        h += renderPreset(data[i]);
      }
      if (listBox) {
        listBox.innerHTML = h;
        var adds = listBox.querySelectorAll(".preset-add");
        for (var j = 0; j < adds.length; j++) {
          adds[j].onclick = onPresetAdd;
        }
      }
      icons();
    });
  }

  function renderPreset(p) {
    var h = '<div class="preset-card" data-preset="' + esc(p.id) + '">';
    h += "<h4>" + esc(p.name) + "</h4>";
    if (p.description) h += '<p class="hint">' + esc(p.description) + "</p>";
    if (p.apiAddress) h += '<div class="mono">' + esc(p.apiAddress) + "</div>";
    if (p.models && p.models.length) {
      h += '<div class="preset-models">';
      for (var i = 0; i < p.models.length; i++) {
        var m = p.models[i];
        h += "<div>" + esc(m.displayName) + ' <span class="mono">' + esc(m.modelId) + "</span></div>";
      }
      h += "</div>";
    }
    h += '<div class="preset-keyrow">';
    h += '<input type="password" class="preset-key" placeholder="' + esc(_t("prov.pasteKey", "粘贴你的 API Key")) + '" />';
    h += '<button type="button" class="btn btn-primary btn-sm preset-add">' + esc(_t("prov.add", "添加")) + '</button>';
    h += "</div></div>";
    return h;
  }

  function onPresetAdd() {
    var card = this.closest(".preset-card");
    var presetId = card.getAttribute("data-preset");
    var keyInput = card.querySelector(".preset-key");
    var key = (keyInput.value || "").trim();
    if (!key) { toast(_t("prov.pasteKeyFirst", "请先粘贴 API Key"), "error"); keyInput.focus(); return; }
    this.disabled = true;
    api("POST", "/api/providers/from-preset", { presetId: presetId, apiKey: key }, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.added", "已添加"), "success");
        closeModal(presetModal);
        loadProviders();
      } else if (status === 404) {
        toast(_t("prov.presetNotFound", "预设不存在"), "error");
      } else {
        toast(_t("prov.addFailed", "添加失败"), "error");
      }
      var btn = card.querySelector(".preset-add");
      if (btn) btn.disabled = false;
    });
  }

  function openModelModal(pid, mid) {
    editingModelProviderId = pid;
    editingModelId = mid || null;
    var title = document.getElementById("mm-title");
    var nameEl = document.getElementById("mm-name");
    var modelIdEl = document.getElementById("mm-model-id");
    var scaleEl = document.getElementById("mm-scale");
    var descEl = document.getElementById("mm-desc");
    var concEl = document.getElementById("mm-concurrency");

    if (mid) {
      var p = findProvider(pid);
      var m = null;
      if (p && p.models) {
        for (var i = 0; i < p.models.length; i++) {
          if (String(p.models[i].id) === String(mid)) { m = p.models[i]; break; }
        }
      }
      title.textContent = _t("prov.editModelTitle", "编辑模型");
      nameEl.value = m ? (m.displayName || "") : "";
      modelIdEl.value = m ? (m.modelId || "") : "";
      scaleEl.value = m ? (m.scale || "") : "";
      descEl.value = m ? (m.description || "") : "";
      concEl.value = m && m.concurrency ? m.concurrency : 1;
    } else {
      title.textContent = _t("prov.addModelTitle", "添加模型");
      nameEl.value = "";
      modelIdEl.value = "";
      scaleEl.value = "";
      descEl.value = "";
      concEl.value = 1;
    }
    openModal(modelModal);
    nameEl.focus();
  }

  function saveModel() {
    var nameEl = document.getElementById("mm-name");
    var modelIdEl = document.getElementById("mm-model-id");
    var scaleEl = document.getElementById("mm-scale");
    var descEl = document.getElementById("mm-desc");
    var concEl = document.getElementById("mm-concurrency");

    var displayName = (nameEl.value || "").trim();
    if (!displayName) { toast(_t("prov.modelNameRequired", "模型名不能为空"), "error"); return; }

    var concurrency = parseInt(concEl.value, 10);
    if (!isFinite(concurrency) || concurrency < 1) concurrency = 1;

    var payload = {
      displayName: displayName,
      modelId: modelIdEl.value || "",
      scale: scaleEl.value || "",
      description: descEl.value || "",
      concurrency: concurrency
    };

    var method, url;
    if (editingModelId) {
      method = "PUT";
      url = "/api/providers/" + encodeURIComponent(editingModelProviderId) + "/models/" + encodeURIComponent(editingModelId);
    } else {
      method = "POST";
      url = "/api/providers/" + encodeURIComponent(editingModelProviderId) + "/models";
    }

    api(method, url, payload, function (status) {
      if (status >= 200 && status < 300) {
        toast(_t("prov.saveOk", "保存成功"), "success");
        closeModal(modelModal);
        loadProviders();
      } else {
        toast(_t("prov.saveFailed", "保存失败"), "error");
      }
    });
  }

  function init() {
    var addBtn = document.getElementById("provider-add");
    if (addBtn) addBtn.onclick = function () { openProviderModal(null); };

    var pmCancel = document.getElementById("pm-cancel");
    if (pmCancel) pmCancel.onclick = function () { closeModal(providerModal); };

    var pmSave = document.getElementById("pm-save");
    if (pmSave) pmSave.onclick = saveProvider;

    var pmToggle = document.getElementById("pm-key-toggle");
    if (pmToggle) pmToggle.onclick = function () {
      var keyEl = document.getElementById("pm-key");
      if (keyEl.type === "password") {
        keyEl.type = "text";
        setKeyToggleIcon(true);
      } else {
        keyEl.type = "password";
        setKeyToggleIcon(false);
      }
    };

    var mmCancel = document.getElementById("mm-cancel");
    if (mmCancel) mmCancel.onclick = function () { closeModal(modelModal); };

    var mmSave = document.getElementById("mm-save");
    if (mmSave) mmSave.onclick = saveModel;

    providerModal.onclick = function (e) {
      if (e.target === providerModal) closeModal(providerModal);
    };
    var presetCancel = document.getElementById("preset-cancel");
    if (presetCancel) presetCancel.onclick = function () { closeModal(presetModal); };
    if (presetModal) presetModal.onclick = function (e) {
      if (e.target === presetModal) closeModal(presetModal);
    };
    modelModal.onclick = function (e) {
      if (e.target === modelModal) closeModal(modelModal);
    };

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.keyCode === 27) {
        if (!providerModal.classList.contains("is-hidden")) closeModal(providerModal);
        if (presetModal && !presetModal.classList.contains("is-hidden")) closeModal(presetModal);
        if (!modelModal.classList.contains("is-hidden")) closeModal(modelModal);
      }
    });

    loadProviders();
    icons();

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        loadProviders();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
