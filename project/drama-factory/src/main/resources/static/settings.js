(function () {
  "use strict";

  var PAGE_I18N = {
    'set.title': { 'zh-CN': '设置中心 · AI 短剧工坊', 'en': 'Settings · AI Short Drama Studio' },
    'set.heading': { 'zh-CN': '设置中心', 'en': 'Settings' },
    'set.sub': { 'zh-CN': '运行参数与密钥配置（标记"需重启"的字段在重启后生效）', 'en': 'Runtime options and credentials (fields marked "restart required" apply after restart)' },
    'set.saveAll': { 'zh-CN': '保存全部', 'en': 'Save all' },
    'set.configTitle': { 'zh-CN': '配置项', 'en': 'Configuration' },
    'set.loadingConfig': { 'zh-CN': '正在加载配置…', 'en': 'Loading configuration…' },
    'set.empty': { 'zh-CN': '暂无可配置项', 'en': 'Nothing to configure' },
    'set.loadFailed': { 'zh-CN': '加载失败', 'en': 'Failed to load' },
    'set.restartBadge': { 'zh-CN': '需重启', 'en': 'Restart required' },
    'set.showKey': { 'zh-CN': '显示配置键名', 'en': 'Show config key' },
    'set.hideKey': { 'zh-CN': '隐藏配置键名', 'en': 'Hide config key' },
    'set.enabled': { 'zh-CN': '已启用', 'en': 'Enabled' },
    'set.disabled': { 'zh-CN': '已禁用', 'en': 'Disabled' },
    'set.noOptions': { 'zh-CN': '（无选项）', 'en': '(no options)' },
    'set.placeholderEmpty': { 'zh-CN': '未设置，留空则保持原值', 'en': 'Not set — leave blank to keep current value' },
    'set.secrets': { 'zh-CN': '密钥', 'en': 'Credentials' },
    'set.itemCount': { 'zh-CN': '{0} 项', 'en': '{0} item(s)' },
    'set.loadErrorFmt': { 'zh-CN': '加载失败：{0}', 'en': 'Failed to load: {0}' },
    'set.networkError': { 'zh-CN': '网络错误', 'en': 'Network error' },
    'set.toastLoadFailed': { 'zh-CN': '设置加载失败', 'en': 'Failed to load settings' },
    'set.noChanges': { 'zh-CN': '没有需要保存的改动', 'en': 'No changes to save' },
    'set.saved': { 'zh-CN': '设置已保存', 'en': 'Settings saved' },
    'set.saveFailedFmt': { 'zh-CN': '保存失败：{0}', 'en': 'Save failed: {0}' }
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

  var els = {
    save: document.getElementById("settings-save"),
    count: document.getElementById("settings-count"),
    loading: document.getElementById("settings-loading"),
    empty: document.getElementById("settings-empty"),
    error: document.getElementById("settings-error"),
    errorText: document.getElementById("settings-error-text"),
    retry: document.getElementById("settings-retry"),
    form: document.getElementById("settings-form")
  };

  var schema = [];
  var values = {};
  var inputs = {}; // key -> 采集函数
  var saving = false;

  function toast(msg, kind) {
    if (window.Harness && typeof window.Harness.toast === "function") {
      window.Harness.toast(msg, kind);
      return;
    }
    if (window.toast) {
      window.toast(msg, kind);
      return;
    }
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

  function maskPlaceholder(raw) {
    var s = String(raw == null ? "" : raw);
    if (!s) return _t("set.placeholderEmpty", "未设置，留空则保持原值");
    // 后端可能返回 ****3456 或 3456；统一成 ****后4位
    var tail = s.replace(/^\*+/, "");
    tail = tail.slice(-4);
    return "****" + tail;
  }

  function showState(name) {
    els.loading.classList.toggle("is-hidden", name !== "loading");
    els.empty.classList.toggle("is-hidden", name !== "empty");
    els.error.classList.toggle("is-hidden", name !== "error");
    els.form.classList.toggle("is-hidden", name !== "form");
    els.save.disabled = name !== "form";
  }

  function restartBadge() {
    return '<span class="badge badge-warn badge-restart">' + _t("set.restartBadge", "需重启") + '</span>';
  }

  function buildRow(item) {
    var key = item.key;
    var type = item.type || "text";
    var label = item.label || key;
    var value = values[key];

    var row = document.createElement("div");
    row.className = "form-row";
    row.dataset.key = key;

    var labelWrap = document.createElement("div");
    labelWrap.className = "form-label";
    var showKeyText = _t("set.showKey", "显示配置键名");
    labelWrap.innerHTML =
      '<span class="form-label-text">' +
      esc(label) +
      "</span>" +
      (item.restartRequired ? restartBadge() : "") +
      '<button type="button" class="form-key-toggle" title="' + esc(showKeyText) + '" aria-label="' + esc(showKeyText) + '">key</button>' +
      '<code class="form-key is-hidden">' +
      esc(key) +
      "</code>";
    row.appendChild(labelWrap);

    var control = document.createElement("div");
    control.className = "form-control";

    if (type === "boolean") {
      var id = "chk-" + key.replace(/[^a-zA-Z0-9_-]/g, "_");
      var wrap = document.createElement("label");
      wrap.className = "switch";
      wrap.setAttribute("for", id);
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = id;
      cb.checked = value === true || value === "true";
      var track = document.createElement("span");
      track.className = "switch-track";
      var txt = document.createElement("span");
      txt.className = "switch-text";
      txt.textContent = cb.checked ? _t("set.enabled", "已启用") : _t("set.disabled", "已禁用");
      cb.addEventListener("change", function () {
        txt.textContent = cb.checked ? _t("set.enabled", "已启用") : _t("set.disabled", "已禁用");
      });
      wrap.appendChild(cb);
      wrap.appendChild(track);
      wrap.appendChild(txt);
      control.appendChild(wrap);
      inputs[key] = function () {
        return cb.checked;
      };
    } else if (type === "select") {
      var sel = document.createElement("select");
      sel.className = "input select";
      var opts = item.options || [];
      if (opts.length === 0) {
        var opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = _t("set.noOptions", "（无选项）");
        sel.appendChild(opt0);
      } else {
        opts.forEach(function (o) {
          var val = typeof o === "object" ? o.value : o;
          var text = typeof o === "object" ? o.label || o.value : o;
          var op = document.createElement("option");
          op.value = String(val);
          op.textContent = String(text);
          sel.appendChild(op);
        });
      }
      sel.value = value == null ? "" : String(value);
      control.appendChild(sel);
      inputs[key] = function () {
        return sel.value;
      };
    } else if (type === "password") {
      var inp = document.createElement("input");
      inp.type = "password";
      inp.className = "input";
      inp.autocomplete = "new-password";
      inp.value = "";
      inp.placeholder = maskPlaceholder(value);
      control.appendChild(inp);
      inputs[key] = function () {
        // 留空 = 保持原值不改
        return inp.value === "" ? undefined : inp.value;
      };
    } else {
      var tinp = document.createElement("input");
      tinp.type = "text";
      tinp.className = "input";
      tinp.value = value == null ? "" : String(value);
      control.appendChild(tinp);
      inputs[key] = function () {
        return tinp.value;
      };
    }

    if (item.hint) {
      var hint = document.createElement("p");
      hint.className = "hint";
      hint.textContent = item.hint;
      control.appendChild(hint);
    }

    var keyToggle = labelWrap.querySelector(".form-key-toggle");
    var keyCode = labelWrap.querySelector(".form-key");
    keyToggle.addEventListener("click", function () {
      var hidden = keyCode.classList.toggle("is-hidden");
      keyToggle.setAttribute("title", hidden ? _t("set.showKey", "显示配置键名") : _t("set.hideKey", "隐藏配置键名"));
      keyToggle.setAttribute("aria-label", hidden ? _t("set.showKey", "显示配置键名") : _t("set.hideKey", "隐藏配置键名"));
    });
    row.appendChild(control);
    return row;
  }

  function render(data) {
    schema = (data && data.schema) || [];
    values = (data && data.values) || {};
    inputs = {};

    if (schema.length === 0) {
      els.count.textContent = "";
      showState("empty");
      icons();
      return;
    }

    els.count.textContent = _fmt("set.itemCount", "{0} 项", [schema.length]);
    els.form.innerHTML = "";

    // secret 字段与普通字段分组：普通在前
    var normal = schema.filter(function (i) {
      return !i.secret;
    });
    var secrets = schema.filter(function (i) {
      return i.secret;
    });

    normal.forEach(function (item) {
      els.form.appendChild(buildRow(item));
    });

    if (secrets.length) {
      var divider = document.createElement("div");
      divider.className = "form-divider";
      divider.innerHTML = '<i data-lucide="key-round"></i><span>' + _t("set.secrets", "密钥") + '</span>';
      els.form.appendChild(divider);
      secrets.forEach(function (item) {
        els.form.appendChild(buildRow(item));
      });
    }

    showState("form");
    icons();
  }

  function load() {
    showState("loading");
    icons();

    fetch("/api/settings")
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        render(data);
      })
      .catch(function (err) {
        els.errorText.textContent =
          _fmt("set.loadErrorFmt", "加载失败：{0}", [(err && err.message ? err.message : _t("set.networkError", "网络错误"))]);
        showState("error");
        icons();
        toast(_t("set.toastLoadFailed", "设置加载失败"), "error");
      });
  }

  function collect() {
    var payload = {};
    Object.keys(inputs).forEach(function (key) {
      var v = inputs[key]();
      if (v === undefined) return; // password 留空
      payload[key] = v;
    });
    return payload;
  }

  function save() {
    if (saving) return;
    var payload = collect();

    if (Object.keys(payload).length === 0) {
      toast(_t("set.noChanges", "没有需要保存的改动"), "info");
      return;
    }

    saving = true;
    els.save.disabled = true;
    els.save.classList.add("is-pending");

    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (newValues) {
        saving = false;
        els.save.classList.remove("is-pending");
        els.save.disabled = false;
        toast(_t("set.saved", "设置已保存"), "success");
        values = newValues || {};
        // 用新掩码视图刷新（password 框重新变空，placeholder 更新）
        fetch("/api/settings")
          .then(function (res) {
            if (!res.ok) throw new Error("HTTP " + res.status);
            return res.json();
          })
          .then(function (data) {
            render(data);
          })
          .catch(function () {
            // 刷新失败不阻塞：保留当前表单
          });
      })
      .catch(function (err) {
        saving = false;
        els.save.classList.remove("is-pending");
        els.save.disabled = false;
        toast(_fmt("set.saveFailedFmt", "保存失败：{0}", [(err && err.message ? err.message : _t("set.networkError", "网络错误"))]), "error");
      });
  }

  els.save.addEventListener("click", save);
  els.retry.addEventListener("click", load);

  if (window.DFI18N) {
    DFI18N.onLangChange(function () {
      if (schema && schema.length) {
        render({ schema: schema, values: values });
      } else {
        load();
      }
    });
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n(document);
    icons();
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
