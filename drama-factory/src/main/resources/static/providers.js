(function () {
  "use strict";

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
        toast("加载供应商失败", "error");
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
      html += '<h3 class="pv-module-title">' + esc(mod.label) + "</h3>";
      var count = 0;
      for (var i = 0; i < providers.length; i++) {
        if ((providers[i].module || "VIDEO") === mod.id) {
          html += renderProvider(providers[i]);
          count++;
        }
      }
      if (!count) {
        html += '<p class="hint">暂无' + esc(mod.label) + "供应商</p>";
      }
      html += '<div style="margin:4px 0 20px;display:flex;gap:8px;flex-wrap:wrap">' +
        '<button type="button" class="btn btn-quiet btn-sm pv-preset-add" data-module="' + esc(mod.id) +
        '"><i data-lucide="sparkles"></i> 从预设添加</button>' +
        '<button type="button" class="btn btn-quiet btn-sm pv-provider-add" data-module="' +
        esc(mod.id) + '"><i data-lucide="plus"></i> 添加' + esc(mod.label) + "供应商</button></div>";
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
    h += '<button type="button" class="btn btn-quiet btn-sm pv-model-add" data-pid="' + esc(p.id) + '"><i data-lucide="plus"></i> 手动添加</button>';
    h += "</div>";
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
        toast("已更新", "success");
        loadProviders();
      } else {
        toast("更新失败", "error");
        loadProviders();
      }
    });
  }

  function onDeleteProvider(pid) {
    if (!window.confirm("确定删除吗？")) return;
    api("DELETE", "/api/providers/" + encodeURIComponent(pid), null, function (status) {
      if (status >= 200 && status < 300) {
        toast("已删除", "success");
        loadProviders();
      } else {
        toast("删除失败", "error");
      }
    });
  }

  function onDeleteModel(pid, mid) {
    if (!window.confirm("确定删除吗？")) return;
    api("DELETE", "/api/providers/" + encodeURIComponent(pid) + "/models/" + encodeURIComponent(mid), null, function (status) {
      if (status >= 200 && status < 300) {
        toast("已删除", "success");
        loadProviders();
      } else {
        toast("删除失败", "error");
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
      title.textContent = "编辑媒体供应商";
      nameEl.value = p ? (p.name || "") : "";
      if (moduleEl) moduleEl.value = (p && p.module) || "VIDEO";
      descEl.value = p ? (p.description || "") : "";
      keyEl.value = "";
      keyEl.placeholder = "留空则保留原密钥";
      addrEl.value = p ? (p.apiAddress || "") : "";
    } else {
      title.textContent = "添加供应商";
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
    if (!name) { toast("供应商名不能为空", "error"); return; }

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
        toast("保存成功", "success");
        closeModal(providerModal);
        loadProviders();
      } else {
        toast("保存失败", "error");
      }
    });
  }

  var presetModal = document.getElementById("preset-modal");

  function openPresetPicker(module) {
    var title = document.getElementById("preset-title");
    var listBox = document.getElementById("preset-list");
    if (title) title.textContent = "从预设添加" + moduleLabel(module) + "供应商";
    if (listBox) listBox.innerHTML = '<p class="hint">加载预设中…</p>';
    openModal(presetModal);
    api("GET", "/api/providers/presets?module=" + encodeURIComponent(module), null, function (status, data) {
      if (!(status >= 200 && status < 300 && Array.isArray(data))) {
        if (listBox) listBox.innerHTML = '<p class="hint">预设加载失败</p>';
        return;
      }
      if (!data.length) {
        if (listBox) listBox.innerHTML = '<p class="hint">该模块暂无预设，可手动添加</p>';
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
    h += '<input type="password" class="preset-key" placeholder="粘贴你的 API Key" />';
    h += '<button type="button" class="btn btn-primary btn-sm preset-add">添加</button>';
    h += "</div></div>";
    return h;
  }

  function onPresetAdd() {
    var card = this.closest(".preset-card");
    var presetId = card.getAttribute("data-preset");
    var keyInput = card.querySelector(".preset-key");
    var key = (keyInput.value || "").trim();
    if (!key) { toast("请先粘贴 API Key", "error"); keyInput.focus(); return; }
    this.disabled = true;
    api("POST", "/api/providers/from-preset", { presetId: presetId, apiKey: key }, function (status) {
      if (status >= 200 && status < 300) {
        toast("已添加", "success");
        closeModal(presetModal);
        loadProviders();
      } else if (status === 404) {
        toast("预设不存在", "error");
      } else {
        toast("添加失败", "error");
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
      title.textContent = "编辑模型";
      nameEl.value = m ? (m.displayName || "") : "";
      modelIdEl.value = m ? (m.modelId || "") : "";
      scaleEl.value = m ? (m.scale || "") : "";
      descEl.value = m ? (m.description || "") : "";
      concEl.value = m && m.concurrency ? m.concurrency : 1;
    } else {
      title.textContent = "添加模型";
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
    if (!displayName) { toast("模型名不能为空", "error"); return; }

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
        toast("保存成功", "success");
        closeModal(modelModal);
        loadProviders();
      } else {
        toast("保存失败", "error");
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
