(function () {
  "use strict";

  var PAGE_I18N = {
    "agt.title": { "zh-CN": "Agent 机队", "en": "Agent Fleet" },
    "agt.subtitle": { "zh-CN": "管理 7 个专用 Agent 的提示词与模型", "en": "Manage prompts and models for the 7 dedicated Agents" },
    "agt.videoChannel": { "zh-CN": "视频通道", "en": "Video channel" },
    "agt.mediaProviders": { "zh-CN": "媒体供应商", "en": "Media providers" },
    "agt.mediaProvidersHint": { "zh-CN": "每个供应商配一个 API Key，在卡片里管理可用模型", "en": "Each provider holds one API Key; manage available models on its card" },
    "agt.addProvider": { "zh-CN": "添加供应商", "en": "Add provider" },
    "agt.noProviders": { "zh-CN": "暂无供应商，点击右上添加", "en": "No providers yet. Use the button at the top right to add one." },
    "agt.loadingFleet": { "zh-CN": "正在加载 Agent 机队…", "en": "Loading Agent Fleet…" },
    "agt.emptyFleet": { "zh-CN": "暂无 Agent 配置", "en": "No Agent configs yet" },
    "agt.loadFailed": { "zh-CN": "加载失败", "en": "Load failed" },
    "agt.providerName": { "zh-CN": "供应商名 *", "en": "Provider name *" },
    "agt.moduleLabel": { "zh-CN": "所属模块", "en": "Module" },
    "agt.providerDesc": { "zh-CN": "简介说明", "en": "Description" },
    "agt.apiKey": { "zh-CN": "API 密钥", "en": "API Key" },
    "agt.apiAddress": { "zh-CN": "API 地址", "en": "API address" },
    "agt.addModel": { "zh-CN": "添加模型", "en": "Add model" },
    "agt.modelName": { "zh-CN": "模型名 *", "en": "Model name *" },
    "agt.modelId": { "zh-CN": "模型 id", "en": "Model id" },
    "agt.modelScale": { "zh-CN": "规模/档位", "en": "Scale / tier" },
    "agt.modelDesc": { "zh-CN": "文档说明", "en": "Documentation notes" },
    "agt.modelConcurrency": { "zh-CN": "并发数", "en": "Concurrency" },
    "agt.addFromPreset": { "zh-CN": "从预设添加", "en": "Add from preset" },
    "agt.module.VIDEO": { "zh-CN": "视频", "en": "Video" },
    "agt.module.TEXT": { "zh-CN": "文本", "en": "Text" },
    "agt.module.IMAGE": { "zh-CN": "图片", "en": "Image" },
    "agt.module.MUSIC": { "zh-CN": "音乐", "en": "Music" },
    "agt.module.TTS": { "zh-CN": "TTS 语音", "en": "TTS voice" },
    "agt.module.AVATAR": { "zh-CN": "数字人", "en": "Digital human" },
    "agt.type.SCRIPT": { "zh-CN": "剧本 Agent", "en": "Script Agent" },
    "agt.type.BOARD": { "zh-CN": "分镜 Agent", "en": "Storyboard Agent" },
    "agt.type.VIDEO": { "zh-CN": "视频 Agent", "en": "Video Agent" },
    "agt.type.EDIT": { "zh-CN": "剪辑 Agent", "en": "Editing Agent" },
    "agt.type.QC": { "zh-CN": "质检 Agent", "en": "QC Agent" },
    "agt.channel.mock": { "zh-CN": "Mock（本地模拟）", "en": "Mock (local simulation)" },
    "agt.channel.qwen": { "zh-CN": "Qwen", "en": "Qwen" },
    "agt.channel.agnes": { "zh-CN": "Agnes", "en": "Agnes" },
    "agt.channelUnset": { "zh-CN": "未设置", "en": "Not set" },
    "agt.channelLoadFailed": { "zh-CN": "加载失败", "en": "Load failed" },
    "agt.channelLoadFailedDetail": { "zh-CN": "通道信息加载失败：", "en": "Failed to load channel info: " },
    "agt.networkError": { "zh-CN": "网络错误", "en": "Network error" },
    "agt.switched": { "zh-CN": "已切换，立即生效", "en": "Switched. Takes effect immediately." },
    "agt.switchFailed": { "zh-CN": "切换失败：", "en": "Switch failed: " },
    "agt.channelInfoFailed": { "zh-CN": "通道信息加载失败", "en": "Failed to load channel info" },
    "agt.fleetLoadFailed": { "zh-CN": "Agent 机队加载失败", "en": "Failed to load Agent Fleet" },
    "agt.loadFailedDetail": { "zh-CN": "加载失败：", "en": "Load failed: " },
    "agt.modelKey": { "zh-CN": "选用模型", "en": "Model" },
    "agt.fallbackKey": { "zh-CN": "降级策略", "en": "Fallback" },
    "agt.templateKey": { "zh-CN": "模板", "en": "Template" },
    "agt.updatedAt": { "zh-CN": " · 更新于 ", "en": " · updated " },
    "agt.viewTemplate": { "zh-CN": "查看模板", "en": "View template" },
    "agt.hideTemplate": { "zh-CN": "收起模板", "en": "Hide template" },
    "agt.editTemplate": { "zh-CN": "编辑模板", "en": "Edit template" },
    "agt.templateFull": { "zh-CN": "模板全文", "en": "Full template" },
    "agt.emptyTemplate": { "zh-CN": "（空模板）", "en": "(Empty template)" },
    "agt.save": { "zh-CN": "保存", "en": "Save" },
    "agt.cancel": { "zh-CN": "取消", "en": "Cancel" },
    "agt.templateSaved": { "zh-CN": "模板已保存，对新 Run 生效", "en": "Template saved. Applies to new Runs." },
    "agt.saveFailed": { "zh-CN": "保存失败：", "en": "Save failed: " }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  var TYPE_LABEL = {
    SCRIPT: "剧本 Agent",
    BOARD: "分镜 Agent",
    VIDEO: "视频 Agent",
    EDIT: "剪辑 Agent",
    QC: "质检 Agent"
  };

  var CHANNEL_LABEL = {
    mock: "Mock（本地模拟）",
    qwen: "Qwen",
    agnes: "Agnes"
  };

  function typeLabel(type) {
    var key = 'agt.type.' + type;
    var v = _t(key, null);
    if (v && v !== key) return v;
    return TYPE_LABEL[type] || type;
  }

  function channelLabel(id) {
    var key = 'agt.channel.' + id;
    var v = _t(key, null);
    if (v && v !== key) return v;
    return CHANNEL_LABEL[id] || id;
  }

  var PROVIDER_KEY = "drama.video.provider";

  var els = {
    channelCurrent: document.getElementById("channel-current"),
    channelSwitch: document.getElementById("channel-switch"),
    channelNote: document.getElementById("channel-note"),
    loading: document.getElementById("agents-loading"),
    empty: document.getElementById("agents-empty"),
    error: document.getElementById("agents-error"),
    errorText: document.getElementById("agents-error-text"),
    retry: document.getElementById("agents-retry"),
    grid: document.getElementById("agent-grid")
  };

  var currentProvider = null;
  var switching = false;

  function toast(msg, kind) {
    if (window.Harness && typeof window.Harness.toast === "function") {
      window.Harness.toast(msg, kind);
      return;
    }
    if (window.toast) {
      window.toast(msg, kind);
      return;
    }
    // 兜底：不阻塞交互
    var box = document.getElementById("harness-toast-fallback");
    if (!box) {
      box = document.createElement("div");
      box.id = "harness-toast-fallback";
      box.className = "toast-fallback";
      document.body.appendChild(box);
    }
    var item = document.createElement("div");
    item.className = "toast-fallback-item" + (kind ? " is-" + kind : "");
    item.textContent = msg;
    box.appendChild(item);
    setTimeout(function () {
      item.remove();
    }, 3200);
  }

  function icons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTime(v) {
    if (!v) return "—";
    var d = new Date(v);
    if (isNaN(d.getTime())) return String(v);
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    return (
      d.getFullYear() +
      "-" +
      p(d.getMonth() + 1) +
      "-" +
      p(d.getDate()) +
      " " +
      p(d.getHours()) +
      ":" +
      p(d.getMinutes())
    );
  }

  function showState(name) {
    els.loading.classList.toggle("is-hidden", name !== "loading");
    els.empty.classList.toggle("is-hidden", name !== "empty");
    els.error.classList.toggle("is-hidden", name !== "error");
    els.grid.classList.toggle("is-hidden", name !== "list");
  }

  function renderChannels(data) {
    var available = (data && data.available) || [];
    var current = data && data.current;
    currentProvider = current || null;

    els.channelCurrent.textContent = current
      ? channelLabel(current)
      : _t("agt.channelUnset", "未设置");

    els.channelSwitch.innerHTML = "";
    available.forEach(function (id) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-chip" + (id === current ? " is-active" : "");
      btn.dataset.provider = id;
      btn.innerHTML =
        '<i data-lucide="' +
        (id === current ? "check" : "radio") +
        '"></i><span>' +
        esc(channelLabel(id)) +
        "</span>";
      btn.disabled = id === current;
      btn.addEventListener("click", function () {
        switchProvider(id, btn);
      });
      els.channelSwitch.appendChild(btn);
    });

    els.channelNote.textContent = (data && data.note) || "";
    els.channelNote.classList.toggle("is-hidden", !(data && data.note));
    icons();
  }

  function setSwitchDisabled(disabled) {
    var btns = els.channelSwitch.querySelectorAll("button");
    Array.prototype.forEach.call(btns, function (b) {
      b.disabled = disabled || b.dataset.provider === currentProvider;
    });
  }

  function switchProvider(id, btn) {
    if (switching || id === currentProvider) return;
    switching = true;
    setSwitchDisabled(true);
    btn.classList.add("is-pending");

    var payload = {};
    payload[PROVIDER_KEY] = id;

    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function () {
        switching = false;
        btn.classList.remove("is-pending");
        toast(_t("agt.switched", "已切换，立即生效"), "success");
        loadChannels();
      })
      .catch(function (err) {
        switching = false;
        btn.classList.remove("is-pending");
        setSwitchDisabled(false);
        toast(_t("agt.switchFailed", "切换失败：") + (err && err.message ? err.message : _t("agt.networkError", "网络错误")), "error");
      });
  }

  function loadChannels() {
    fetch("/api/agents/channels")
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        renderChannels(data);
      })
      .catch(function (err) {
        els.channelCurrent.textContent = _t("agt.channelLoadFailed", "加载失败");
        els.channelSwitch.innerHTML = "";
        els.channelNote.textContent =
          _t("agt.channelLoadFailedDetail", "通道信息加载失败：") + (err && err.message ? err.message : _t("agt.networkError", "网络错误"));
        els.channelNote.classList.remove("is-hidden");
        toast(_t("agt.channelInfoFailed", "通道信息加载失败"), "error");
      });
  }

  function renderAgents(list) {
    if (!Array.isArray(list) || list.length === 0) {
      showState("empty");
      icons();
      return;
    }

    els.grid.innerHTML = "";
    list.forEach(function (agent) {
      els.grid.appendChild(buildAgentCard(agent));
    });
    showState("list");
    icons();
  }

  function buildAgentCard(agent) {
    var type = agent.type;
    var label = agent.label || typeLabel(type);

    var card = document.createElement("article");
    card.className = "card agent-card";
    card.dataset.type = type;

    var head = document.createElement("div");
    head.className = "card-head";
    head.innerHTML =
      '<h2 class="card-title">' +
      '<i data-lucide="bot" class="card-title-icon"></i>' +
      "<span>" +
      esc(label) +
      "</span></h2>" +
      '<span class="badge badge-muted">' +
      esc(type) +
      "</span>";
    card.appendChild(head);

    var meta = document.createElement("div");
    meta.className = "agent-meta";
    meta.innerHTML =
      '<div class="meta-row"><span class="meta-key">' + esc(_t("agt.modelKey", "选用模型")) + '</span>' +
      '<span class="meta-val">' +
      esc(agent.model || "—") +
      "</span></div>" +
      '<div class="meta-row"><span class="meta-key">' + esc(_t("agt.fallbackKey", "降级策略")) + '</span>' +
      '<span class="meta-val">' +
      esc(agent.fallback || "—") +
      "</span></div>" +
      '<div class="meta-row"><span class="meta-key">' + esc(_t("agt.templateKey", "模板")) + '</span>' +
      '<span class="meta-val">' +
      esc(agent.templateName || "—") +
      esc(_t("agt.updatedAt", " · 更新于 ")) +
      esc(fmtTime(agent.templateUpdatedAt)) +
      "</span></div>";
    card.appendChild(meta);

    var actions = document.createElement("div");
    actions.className = "agent-actions";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-secondary btn-sm";
    toggle.innerHTML = '<i data-lucide="eye"></i><span>' + esc(_t("agt.viewTemplate", "查看模板")) + '</span>';

    var editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-secondary btn-sm";
    editBtn.innerHTML = '<i data-lucide="pencil"></i><span>' + esc(_t("agt.editTemplate", "编辑模板")) + '</span>';

    actions.appendChild(toggle);
    actions.appendChild(editBtn);
    card.appendChild(actions);

    var details = document.createElement("details");
    details.className = "agent-template";
    var summary = document.createElement("summary");
    summary.className = "agent-template-summary";
    summary.innerHTML = '<i data-lucide="file-text"></i><span>' + esc(_t("agt.templateFull", "模板全文")) + '</span>';
    var pre = document.createElement("pre");
    pre.className = "template-pre";
    pre.textContent = agent.template || _t("agt.emptyTemplate", "（空模板）");
    details.appendChild(summary);
    details.appendChild(pre);
    card.appendChild(details);

    toggle.addEventListener("click", function () {
      details.open = !details.open;
      toggle.querySelector("span").textContent = details.open
        ? _t("agt.hideTemplate", "收起模板")
        : _t("agt.viewTemplate", "查看模板");
    });

    var editorWrap = document.createElement("div");
    editorWrap.className = "agent-editor is-hidden";

    var textarea = document.createElement("textarea");
    textarea.className = "template-textarea";
    textarea.spellcheck = false;
    textarea.value = agent.template || "";

    var editorActions = document.createElement("div");
    editorActions.className = "editor-actions";

    var saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "btn btn-primary btn-sm";
    saveBtn.innerHTML = '<i data-lucide="check"></i><span>' + esc(_t("agt.save", "保存")) + '</span>';

    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary btn-sm";
    cancelBtn.innerHTML = '<i data-lucide="x"></i><span>' + esc(_t("agt.cancel", "取消")) + '</span>';

    var editorErr = document.createElement("p");
    editorErr.className = "form-error is-hidden";

    editorActions.appendChild(saveBtn);
    editorActions.appendChild(cancelBtn);
    editorWrap.appendChild(textarea);
    editorWrap.appendChild(editorActions);
    editorWrap.appendChild(editorErr);
    card.appendChild(editorWrap);

    function openEditor() {
      textarea.value = agent.template || "";
      editorErr.classList.add("is-hidden");
      editorErr.textContent = "";
      editorWrap.classList.remove("is-hidden");
      editBtn.disabled = true;
      textarea.focus();
    }

    function closeEditor() {
      editorWrap.classList.add("is-hidden");
      editBtn.disabled = false;
      editorErr.classList.add("is-hidden");
      editorErr.textContent = "";
    }

    editBtn.addEventListener("click", openEditor);
    cancelBtn.addEventListener("click", closeEditor);

    saveBtn.addEventListener("click", function () {
      var content = textarea.value;
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      saveBtn.classList.add("is-pending");

      fetch("/api/agents/" + encodeURIComponent(type) + "/template", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content })
      })
        .then(function (res) {
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(function (updated) {
          saveBtn.disabled = false;
          cancelBtn.disabled = false;
          saveBtn.classList.remove("is-pending");
          toast(_t("agt.templateSaved", "模板已保存，对新 Run 生效"), "success");

          if (updated && typeof updated === "object") {
            agent.template = updated.template != null ? updated.template : content;
            agent.templateUpdatedAt = updated.templateUpdatedAt || agent.templateUpdatedAt;
            if (updated.model) agent.model = updated.model;
            if (updated.fallback) agent.fallback = updated.fallback;
            pre.textContent = agent.template || _t("agt.emptyTemplate", "（空模板）");
            meta.querySelectorAll(".meta-row")[2].querySelector(".meta-val").textContent =
              (agent.templateName || "—") +
              _t("agt.updatedAt", " · 更新于 ") +
              fmtTime(agent.templateUpdatedAt);
          } else {
            agent.template = content;
            pre.textContent = content || _t("agt.emptyTemplate", "（空模板）");
          }
          closeEditor();
        })
        .catch(function (err) {
          saveBtn.disabled = false;
          cancelBtn.disabled = false;
          saveBtn.classList.remove("is-pending");
          var msg = err && err.message ? err.message : _t("agt.networkError", "网络错误");
          editorErr.textContent = _t("agt.saveFailed", "保存失败：") + msg;
          editorErr.classList.remove("is-hidden");
          toast(_t("agt.saveFailed", "保存失败：") + msg, "error");
        });
    });

    return card;
  }

  function loadAgents() {
    showState("loading");
    icons();

    fetch("/api/agents")
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (list) {
        renderAgents(list);
      })
      .catch(function (err) {
        els.errorText.textContent =
          _t("agt.loadFailedDetail", "加载失败：") + (err && err.message ? err.message : _t("agt.networkError", "网络错误"));
        showState("error");
        icons();
        toast(_t("agt.fleetLoadFailed", "Agent 机队加载失败"), "error");
      });
  }

  els.retry.addEventListener("click", function () {
    loadAgents();
  });

  function init() {
    if (window.DFI18N) DFI18N.applyI18n();
    icons();
    loadChannels();
    loadAgents();

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        loadChannels();
        loadAgents();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
