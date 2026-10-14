/* BYOK 模型加载共享逻辑：按模块拉取用户自配的供应商模型。
 * 空状态一句克制文案 + 去通道管理按钮；无模型时生成按钮置灰。
 * 注意：不许在这里硬编码任何假模型。 */
(function () {
  "use strict";

  var MODULE_LABEL = { IMAGE: "图片", MUSIC: "音乐", TTS: "TTS 语音", AVATAR: "数字人" };

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

  function icons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") { window.lucide.createIcons(); }
  }

  /**
   * 加载某模块的可用模型并驱动 UI。
   * opts: { select, emptyBox, generateBtn, hint, onChange }
   * - select: 模型 <select>；emptyBox: 空状态容器；generateBtn: 生成按钮；hint: 按钮旁提示
   */
  function loadModels(module, opts) {
    var label = MODULE_LABEL[module] || module;
    fetch("/api/providers?module=" + encodeURIComponent(module))
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (providers) {
        var models = [];
        (providers || []).forEach(function (p) {
          if (!p.enabled) return;
          (p.models || []).forEach(function (m) {
            if (m.enabled) models.push({ providerId: p.id, provider: p.name, model: m });
          });
        });
        render(module, label, models, opts);
      })
      .catch(function () {
        toast("模型列表加载失败", "error");
        render(module, label, [], opts);
      });
  }

  function render(module, label, models, opts) {
    var select = opts.select, emptyBox = opts.emptyBox,
        btn = opts.generateBtn, hint = opts.hint;
    if (!models.length) {
      if (select) select.style.display = "none";
      if (emptyBox) {
        emptyBox.hidden = false;
        emptyBox.innerHTML =
          '<p class="hint">还没有接入' + esc(label) + "模型</p>" +
          '<a class="btn btn-quiet btn-sm" href="/agents.html">去通道管理添加 API</a>';
      }
      if (btn) btn.disabled = true;
      if (hint) hint.textContent = "先在通道管理配置 API 后可用";
    } else {
      if (select) {
        select.style.display = "";
        select.innerHTML = models.map(function (it, i) {
          var m = it.model;
          return '<option value="' + esc(m.id) + '">' + esc(m.displayName) +
            "（" + esc(it.provider) + "）</option>";
        }).join("");
        if (typeof opts.onChange === "function") {
          select.onchange = function () { opts.onChange(models[select.selectedIndex]); };
          opts.onChange(models[0]);
        }
      }
      if (emptyBox) emptyBox.hidden = true;
      if (btn) btn.disabled = false;
      if (hint) hint.textContent = "";
    }
    icons();
  }

  /** 生成按钮的诚实占位：不伪造成功，明确告知开发中。 */
  function notYetReady(modelName) {
    toast("已选模型" + (modelName ? "「" + modelName + "」" : "") + "，生成调用下一轮上线", "info");
  }

  /**
   * 真实生成调用：POST /api/byok/generate，服务端阻塞轮询后返回产物 URL。
   * opts: { module, model, prompt, options, btn, hint, onDone(url) }
   * 生成中禁用按钮、hint 显示进度；失败 toast 显示脱敏错误；成功回调 onDone。
   */
  function generate(opts) {
    var btn = opts.btn, hint = opts.hint;
    if (!opts.model) { toast("请先选择模型", "error"); return; }
    var body = {
      module: opts.module,
      providerId: opts.model.providerId,
      modelId: opts.model.model.modelId,
      prompt: opts.prompt,
      options: opts.options || {}
    };
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = "生成中，请稍候…";
    fetch("/api/byok/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, d: d }; }); })
      .then(function (r) {
        if (btn) btn.disabled = false;
        if (r.ok && r.d && r.d.status === "SUCCEEDED" && r.d.url) {
          if (hint) hint.textContent = "";
          if (typeof opts.onDone === "function") opts.onDone(r.d.url);
        } else {
          var msg = (r.d && r.d.error) || ("HTTP " + (r.ok ? 200 : "错误"));
          if (hint) hint.textContent = "";
          toast("生成失败：" + msg, "error");
        }
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        if (hint) hint.textContent = "";
        toast("生成请求失败：" + (err && err.message || err), "error");
      });
  }

  window.Byok = {
    MODULE_LABEL: MODULE_LABEL,
    loadModels: loadModels,
    notYetReady: notYetReady,
    generate: generate,
    toast: toast,
    icons: icons
  };
})();
