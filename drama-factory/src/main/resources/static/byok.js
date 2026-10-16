/* BYOK 模型加载共享逻辑：按模块拉取用户自配的供应商模型。
 * 空状态一句克制文案 + 去通道管理按钮；无模型时生成按钮置灰。
 * 注意：不许在这里硬编码任何假模型。 */
(function () {
  "use strict";

  var PAGE_I18N = {
    'byok.docTitle': { 'zh-CN': 'AI 生成 · AI 短剧工坊', 'en': 'AI Generation · AI Drama Factory' },
    'img.docTitle': { 'zh-CN': 'AI 图片 · AI 短剧工坊', 'en': 'AI Images · AI Drama Factory' },
    'img.pageTitle': { 'zh-CN': 'AI 图片', 'en': 'AI Images' },
    'img.pageSub': { 'zh-CN': '用你自己的 API 生成剧照、海报与分镜参考图（BYOK）', 'en': 'Generate stills, posters and shot references with your own API keys (BYOK)' },
    'img.generate': { 'zh-CN': '生成', 'en': 'Generate' },
    'img.prompt': { 'zh-CN': '提示词', 'en': 'Prompt' },
    'img.promptPh': { 'zh-CN': '描述你想要的画面…', 'en': 'Describe the image you want…' },
    'img.model': { 'zh-CN': '模型', 'en': 'Model' },
    'img.ratio': { 'zh-CN': '比例', 'en': 'Aspect ratio' },
    'img.size': { 'zh-CN': '尺寸', 'en': 'Size' },
    'img.ref': { 'zh-CN': '参考图（可选）', 'en': 'Reference image (optional)' },
    'img.refPreviewAlt': { 'zh-CN': '参考图预览', 'en': 'Reference image preview' },
    'img.generateBtn': { 'zh-CN': '生成图片', 'en': 'Generate image' },
    'img.promptRequired': { 'zh-CN': '请填写提示词', 'en': 'Please enter a prompt' },
    'img.generated': { 'zh-CN': '图片已生成', 'en': 'Image generated' },

    'mus.docTitle': { 'zh-CN': 'AI 音乐 · AI 短剧工坊', 'en': 'AI Music · AI Drama Factory' },
    'mus.pageTitle': { 'zh-CN': 'AI 音乐', 'en': 'AI Music' },
    'mus.pageSub': { 'zh-CN': '用你自己的 API 生成配乐与主题曲（BYOK）', 'en': 'Generate scores and theme songs with your own API keys (BYOK)' },
    'mus.generate': { 'zh-CN': '生成', 'en': 'Generate' },
    'mus.mode': { 'zh-CN': '模式', 'en': 'Mode' },
    'mus.modeSimple': { 'zh-CN': '简易', 'en': 'Simple' },
    'mus.modeCustom': { 'zh-CN': '自定义', 'en': 'Custom' },
    'mus.instrumental': { 'zh-CN': '纯音乐（无歌词）', 'en': 'Instrumental (no lyrics)' },
    'mus.prompt': { 'zh-CN': '提示词 / 歌词', 'en': 'Prompt / lyrics' },
    'mus.promptPh': { 'zh-CN': '描述风格、情绪，或粘贴歌词…', 'en': 'Describe the style and mood, or paste lyrics…' },
    'mus.model': { 'zh-CN': '模型', 'en': 'Model' },
    'mus.generateBtn': { 'zh-CN': '生成音乐', 'en': 'Generate music' },
    'mus.promptRequired': { 'zh-CN': '请填写提示词 / 歌词', 'en': 'Please enter a prompt or lyrics' },
    'mus.generated': { 'zh-CN': '音乐已生成', 'en': 'Music generated' },

    'ava.docTitle': { 'zh-CN': '数字人 · AI 短剧工坊', 'en': 'Digital Human · AI Drama Factory' },
    'ava.pageTitle': { 'zh-CN': '数字人', 'en': 'Digital Human' },
    'ava.pageSub': { 'zh-CN': '人物图 + 音频 + TTS 音色，生成数字人播报（BYOK）', 'en': 'Combine a portrait, audio and a TTS voice into a talking digital human (BYOK)' },
    'ava.generate': { 'zh-CN': '生成', 'en': 'Generate' },
    'ava.photo': { 'zh-CN': '人物图 URL（需公网可访问）', 'en': 'Portrait image URL (must be publicly reachable)' },
    'ava.photoPh': { 'zh-CN': 'https://…/photo.png', 'en': 'https://…/photo.png' },
    'ava.photoHint': { 'zh-CN': 'v1.0 暂需公网可访问的图片 URL；本地文件上传后续随资产库支持。', 'en': 'v1.0 needs a publicly reachable image URL; local file upload will come with the asset library.' },
    'ava.audio': { 'zh-CN': '音频 URL（可选，为空则用下方文案驱动 TTS）', 'en': 'Audio URL (optional — leave empty to drive TTS with the script below)' },
    'ava.audioPh': { 'zh-CN': 'https://…/voice.mp3', 'en': 'https://…/voice.mp3' },
    'ava.voice': { 'zh-CN': '数字人模型', 'en': 'Digital human model' },
    'ava.script': { 'zh-CN': '文案', 'en': 'Script' },
    'ava.scriptPh': { 'zh-CN': '数字人要说的内容…', 'en': 'What the digital human should say…' },
    'ava.generateBtn': { 'zh-CN': '生成数字人视频', 'en': 'Generate digital human video' },
    'ava.photoRequired': { 'zh-CN': '请填写人物图 URL', 'en': 'Please enter a portrait image URL' },
    'ava.audioOrScriptRequired': { 'zh-CN': '请提供音频 URL 或文案', 'en': 'Provide an audio URL or a script' },
    'ava.generated': { 'zh-CN': '数字人视频已生成', 'en': 'Digital human video generated' },

    'byok.modelListFail': { 'zh-CN': '模型列表加载失败', 'en': 'Failed to load the model list' },
    'byok.emptyPrefix': { 'zh-CN': '还没有接入', 'en': 'No ' },
    'byok.emptySuffix': { 'zh-CN': '模型', 'en': ' models connected yet' },
    'byok.goProviders': { 'zh-CN': '去通道管理添加 API', 'en': 'Add an API in Provider Settings' },
    'byok.configureHint': { 'zh-CN': '先在通道管理配置 API 后可用', 'en': 'Configure an API in Provider Settings to enable this' },
    'byok.pickModel': { 'zh-CN': '请先选择模型', 'en': 'Please select a model first' },
    'byok.generating': { 'zh-CN': '生成中，请稍候…', 'en': 'Generating, please wait…' },
    'byok.generateFail': { 'zh-CN': '生成失败：', 'en': 'Generation failed: ' },
    'byok.requestFail': { 'zh-CN': '生成请求失败：', 'en': 'Generation request failed: ' },
    'byok.notYetPrefix': { 'zh-CN': '已选模型', 'en': 'Selected model ' },
    'byok.notYetSuffix': { 'zh-CN': '，生成调用下一轮上线', 'en': '; generation will ship in the next round' },
    'byok.moduleImage': { 'zh-CN': '图片', 'en': 'image' },
    'byok.moduleMusic': { 'zh-CN': '音乐', 'en': 'music' },
    'byok.moduleTts': { 'zh-CN': 'TTS 语音', 'en': 'TTS voice' },
    'byok.moduleAvatar': { 'zh-CN': '数字人', 'en': 'digital human' }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  var MODULE_LABEL_KEY = { IMAGE: 'byok.moduleImage', MUSIC: 'byok.moduleMusic', TTS: 'byok.moduleTts', AVATAR: 'byok.moduleAvatar' };
  var MODULE_LABEL = { IMAGE: '图片', MUSIC: '音乐', TTS: 'TTS 语音', AVATAR: '数字人' };

  function moduleLabel(module) {
    var key = MODULE_LABEL_KEY[module];
    if (key) return _t(key, MODULE_LABEL[module] || module);
    return MODULE_LABEL[module] || module;
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

  function icons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") { window.lucide.createIcons(); }
  }

  /**
   * 加载某模块的可用模型并驱动 UI。
   * opts: { select, emptyBox, generateBtn, hint, onChange }
   * - select: 模型 <select>；emptyBox: 空状态容器；generateBtn: 生成按钮；hint: 按钮旁提示
   */
  function loadModels(module, opts) {
    var label = moduleLabel(module);
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
        toast(_t('byok.modelListFail', '模型列表加载失败'), "error");
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
          '<p class="hint">' + esc(_t('byok.emptyPrefix', '还没有接入') + label + _t('byok.emptySuffix', '模型')) + '</p>' +
          '<a class="btn btn-quiet btn-sm" href="/agents.html">' + esc(_t('byok.goProviders', '去通道管理添加 API')) + '</a>';
      }
      if (btn) btn.disabled = true;
      if (hint) hint.textContent = _t('byok.configureHint', '先在通道管理配置 API 后可用');
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
    var msg = _t('byok.notYetPrefix', '已选模型') + (modelName ? "「" + modelName + "」" : "") + _t('byok.notYetSuffix', '，生成调用下一轮上线');
    toast(msg, "info");
  }

  /**
   * 真实生成调用：POST /api/byok/generate，服务端阻塞轮询后返回产物 URL。
   * opts: { module, model, prompt, options, btn, hint, onDone(url) }
   * 生成中禁用按钮、hint 显示进度；失败 toast 显示脱敏错误；成功回调 onDone。
   */
  function generate(opts) {
    var btn = opts.btn, hint = opts.hint;
    if (!opts.model) { toast(_t('byok.pickModel', '请先选择模型'), "error"); return; }
    var body = {
      module: opts.module,
      providerId: opts.model.providerId,
      modelId: opts.model.model.modelId,
      prompt: opts.prompt,
      options: opts.options || {}
    };
    if (btn) btn.disabled = true;
    if (hint) hint.textContent = _t('byok.generating', '生成中，请稍候…');
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
          toast(_t('byok.generateFail', '生成失败：') + msg, "error");
        }
      })
      .catch(function (err) {
        if (btn) btn.disabled = false;
        if (hint) hint.textContent = "";
        toast(_t('byok.requestFail', '生成请求失败：') + (err && err.message || err), "error");
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
