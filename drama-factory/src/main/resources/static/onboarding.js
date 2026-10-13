/* ==========================================================================
   onboarding.js —— 首次引导横幅（新文件）
   未在设置中心配置任何 Key 且用户未手动关闭时，在首页顶部显示三步引导。
   ========================================================================== */
(function () {
  'use strict';

  var DISMISS_KEY = 'df-onboard-dismissed';

  function dismissed() {
    try { return localStorage.getItem(DISMISS_KEY) === '1'; } catch (e) { return true; }
  }

  function keysConfigured(values) {
    if (!values) return false;
    // 掩码值（****后4位）即表示已配置；空字符串表示未配置
    return ['deepseek.api-key', 'dashscope.api-key', 'agnes.api-key'].some(function (k) {
      var v = values[k];
      return typeof v === 'string' && v.length > 0;
    });
  }

  function buildBanner() {
    if (document.getElementById('onboard-banner')) return;
    var host = document.getElementById('appContent') || document.body;
    var el = document.createElement('div');
    el.id = 'onboard-banner';
    el.className = 'onboard-banner';
    el.innerHTML =
      '<div class="onboard-text">' +
        '<strong>开始之前，先完成三步</strong>' +
        '<span>1. <a href="/settings.html">填写 API Key</a></span>' +
        '<span>2. <a href="/runs.html#act=new-run">创建第一条运行</a></span>' +
        '<span>3. 在运行详情看 Agent 时间线</span>' +
      '</div>' +
      '<button class="onboard-dismiss" id="onboard-dismiss" aria-label="关闭引导">知道了</button>';
    host.insertBefore(el, host.firstChild);
    document.getElementById('onboard-dismiss').onclick = function () {
      try { localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
      el.remove();
    };
    if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
  }

  function init() {
    if (dismissed()) return;
    fetch('/api/settings')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        if (!keysConfigured(data.values) && !dismissed()) buildBanner();
      })
      .catch(function () { /* 设置接口不可用时不打扰 */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
