(function () {
  "use strict";

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
      ? CHANNEL_LABEL[current] || current
      : "未设置";

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
        esc(CHANNEL_LABEL[id] || id) +
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
        toast("已切换，立即生效", "success");
        loadChannels();
      })
      .catch(function (err) {
        switching = false;
        btn.classList.remove("is-pending");
        setSwitchDisabled(false);
        toast("切换失败：" + (err && err.message ? err.message : "网络错误"), "error");
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
        els.channelCurrent.textContent = "加载失败";
        els.channelSwitch.innerHTML = "";
        els.channelNote.textContent =
          "通道信息加载失败：" + (err && err.message ? err.message : "网络错误");
        els.channelNote.classList.remove("is-hidden");
        toast("通道信息加载失败", "error");
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
    var label = agent.label || TYPE_LABEL[type] || type;

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
      '<div class="meta-row"><span class="meta-key">选用模型</span>' +
      '<span class="meta-val">' +
      esc(agent.model || "—") +
      "</span></div>" +
      '<div class="meta-row"><span class="meta-key">降级策略</span>' +
      '<span class="meta-val">' +
      esc(agent.fallback || "—") +
      "</span></div>" +
      '<div class="meta-row"><span class="meta-key">模板</span>' +
      '<span class="meta-val">' +
      esc(agent.templateName || "—") +
      " · 更新于 " +
      esc(fmtTime(agent.templateUpdatedAt)) +
      "</span></div>";
    card.appendChild(meta);

    var actions = document.createElement("div");
    actions.className = "agent-actions";

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-secondary btn-sm";
    toggle.innerHTML = '<i data-lucide="eye"></i><span>查看模板</span>';

    var editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-secondary btn-sm";
    editBtn.innerHTML = '<i data-lucide="pencil"></i><span>编辑模板</span>';

    actions.appendChild(toggle);
    actions.appendChild(editBtn);
    card.appendChild(actions);

    var details = document.createElement("details");
    details.className = "agent-template";
    var summary = document.createElement("summary");
    summary.className = "agent-template-summary";
    summary.innerHTML = '<i data-lucide="file-text"></i><span>模板全文</span>';
    var pre = document.createElement("pre");
    pre.className = "template-pre";
    pre.textContent = agent.template || "（空模板）";
    details.appendChild(summary);
    details.appendChild(pre);
    card.appendChild(details);

    toggle.addEventListener("click", function () {
      details.open = !details.open;
      toggle.querySelector("span").textContent = details.open
        ? "收起模板"
        : "查看模板";
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
    saveBtn.innerHTML = '<i data-lucide="check"></i><span>保存</span>';

    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary btn-sm";
    cancelBtn.innerHTML = '<i data-lucide="x"></i><span>取消</span>';

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
          toast("模板已保存，对新 Run 生效", "success");

          if (updated && typeof updated === "object") {
            agent.template = updated.template != null ? updated.template : content;
            agent.templateUpdatedAt = updated.templateUpdatedAt || agent.templateUpdatedAt;
            if (updated.model) agent.model = updated.model;
            if (updated.fallback) agent.fallback = updated.fallback;
            pre.textContent = agent.template || "（空模板）";
            meta.querySelectorAll(".meta-row")[2].querySelector(".meta-val").textContent =
              (agent.templateName || "—") +
              " · 更新于 " +
              fmtTime(agent.templateUpdatedAt);
          } else {
            agent.template = content;
            pre.textContent = content || "（空模板）";
          }
          closeEditor();
        })
        .catch(function (err) {
          saveBtn.disabled = false;
          cancelBtn.disabled = false;
          saveBtn.classList.remove("is-pending");
          var msg = err && err.message ? err.message : "网络错误";
          editorErr.textContent = "保存失败：" + msg;
          editorErr.classList.remove("is-hidden");
          toast("保存失败：" + msg, "error");
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
          "加载失败：" + (err && err.message ? err.message : "网络错误");
        showState("error");
        icons();
        toast("Agent 机队加载失败", "error");
      });
  }

  els.retry.addEventListener("click", function () {
    loadAgents();
  });

  function init() {
    icons();
    loadChannels();
    loadAgents();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
