(function () {
  "use strict";

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
    if (!s) return "未设置，留空则保持原值";
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
    return '<span class="badge badge-warn badge-restart">需重启</span>';
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
    labelWrap.innerHTML =
      '<span class="form-label-text">' +
      esc(label) +
      "</span>" +
      (item.restartRequired ? restartBadge() : "") +
      '<code class="form-key">' +
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
      txt.textContent = cb.checked ? "已启用" : "已禁用";
      cb.addEventListener("change", function () {
        txt.textContent = cb.checked ? "已启用" : "已禁用";
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
        opt0.textContent = "（无选项）";
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

    els.count.textContent = schema.length + " 项";
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
      divider.innerHTML = '<i data-lucide="key-round"></i><span>密钥</span>';
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
          "加载失败：" + (err && err.message ? err.message : "网络错误");
        showState("error");
        icons();
        toast("设置加载失败", "error");
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
      toast("没有需要保存的改动", "info");
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
        toast("设置已保存", "success");
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
        toast("保存失败：" + (err && err.message ? err.message : "网络错误"), "error");
      });
  }

  els.save.addEventListener("click", save);
  els.retry.addEventListener("click", load);

  function init() {
    icons();
    load();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
