/* ==========================================================================
   i18n.js —— drama-factory 全站国际化（v1.0）
   零依赖 IIFE 全局单例，挂载 window.DFI18N。
   所有页面须在本页脚本之前引入本文件（<script src="/i18n.js"></script>）。

   key 命名规范：<页前缀>.<小驼峰名>
     页前缀：ws(工作区首页) chat img mus mv ava run(运行列表) rund(运行详情)
             agt sk usg qc sb task fin pipe tool set login reg
             shell 相关：nav. navgroup. title. pal. shell.
             account 页沿用既有无前缀 key（doc.title/page.title/profile.* 等）
     通用 key 以 c. 开头（见 SHARED），各页直接复用，不得自造同义 key。

   用法：
     DFI18N.register({ 'x.y': { 'zh-CN': '中文', 'en': 'English' } });
     DFI18N.applyI18n(document);
     DFI18N.setLang('en').then(...).catch(...);
     DFI18N.onLangChange(function (lang) { ... });
   ========================================================================== */
(function () {
  'use strict';

  var dicts = [];

  function readLang() {
    var v = null;
    try { v = localStorage.getItem('df-lang'); } catch (e) { v = null; }
    return v === 'en' ? 'en' : 'zh-CN';
  }

  var currentLang = readLang();

  function getLang() {
    return currentLang;
  }

  function tr(key) {
    if (key == null || key === '') return key;
    for (var i = dicts.length - 1; i >= 0; i--) {
      var d = dicts[i];
      if (!d || !Object.prototype.hasOwnProperty.call(d, key)) continue;
      var entry = d[key];
      if (!entry) continue;
      if (entry[currentLang] !== undefined) return entry[currentLang];
      if (entry['zh-CN'] !== undefined) return entry['zh-CN'];
      return key;
    }
    return key;
  }

  function register(dict) {
    if (!dict || typeof dict !== 'object') return;
    dicts.push(dict);
  }

  function applyI18n(root) {
    currentLang = readLang();
    document.documentElement.lang = currentLang;
    var scope = root || document;
    var nodes = scope.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute('data-i18n');
      if (key) nodes[i].textContent = tr(key);
    }
    var phNodes = scope.querySelectorAll('[data-i18n-ph]');
    for (var j = 0; j < phNodes.length; j++) {
      var phKey = phNodes[j].getAttribute('data-i18n-ph');
      if (phKey) phNodes[j].setAttribute('placeholder', tr(phKey));
    }
    var titleNodes = scope.querySelectorAll('[data-i18n-title]');
    for (var k = 0; k < titleNodes.length; k++) {
      var tKey = titleNodes[k].getAttribute('data-i18n-title');
      if (tKey) titleNodes[k].setAttribute('title', tr(tKey));
    }
  }

  var listeners = [];

  function onLangChange(cb) {
    if (typeof cb !== 'function') return function () {};
    listeners.push(cb);
    return function () {
      for (var i = 0; i < listeners.length; i++) {
        if (listeners[i] === cb) { listeners.splice(i, 1); return; }
      }
    };
  }

  function setLang(lang) {
    var next = (lang === 'en') ? 'en' : 'zh-CN';
    if (next === currentLang) return Promise.resolve(next);

    var apply = function () {
      try { localStorage.setItem('df-lang', next); } catch (e) { /* 存储不可用时忽略 */ }
      currentLang = next;
      applyI18n(document);
      for (var i = 0; i < listeners.length; i++) {
        try { listeners[i](next); } catch (e2) { /* 单个回调抛错不影响其他 */ }
      }
      try {
        document.dispatchEvent(new CustomEvent('df:i18n-change', { detail: { lang: next } }));
      } catch (e3) { /* 老浏览器忽略 */ }
      return next;
    };

    if (window.Auth && typeof window.Auth.updateProfile === 'function') {
      return window.Auth.updateProfile(null, null, next).then(apply);
    }
    return Promise.resolve(apply());
  }

  /* ---- SHARED 通用字典（key 以 c. 开头，各页复用） ---- */
  var SHARED = {
    'c.save': { 'zh-CN': '保存', 'en': 'Save' },
    'c.cancel': { 'zh-CN': '取消', 'en': 'Cancel' },
    'c.delete': { 'zh-CN': '删除', 'en': 'Delete' },
    'c.edit': { 'zh-CN': '编辑', 'en': 'Edit' },
    'c.new': { 'zh-CN': '新建', 'en': 'New' },
    'c.close': { 'zh-CN': '关闭', 'en': 'Close' },
    'c.confirm': { 'zh-CN': '确认', 'en': 'Confirm' },
    'c.loading': { 'zh-CN': '加载中…', 'en': 'Loading…' },
    'c.empty': { 'zh-CN': '暂无数据', 'en': 'No data yet' },
    'c.search': { 'zh-CN': '搜索', 'en': 'Search' },
    'c.retry': { 'zh-CN': '重试', 'en': 'Retry' },
    'c.back': { 'zh-CN': '返回', 'en': 'Back' },
    'c.refresh': { 'zh-CN': '刷新', 'en': 'Refresh' },
    'c.all': { 'zh-CN': '全部', 'en': 'All' },
    'c.create': { 'zh-CN': '创建', 'en': 'Create' },
    'c.update': { 'zh-CN': '更新', 'en': 'Update' },
    'c.submit': { 'zh-CN': '提交', 'en': 'Submit' },
    'c.view': { 'zh-CN': '查看', 'en': 'View' },
    'c.download': { 'zh-CN': '下载', 'en': 'Download' },
    'c.upload': { 'zh-CN': '上传', 'en': 'Upload' },
    'c.copy': { 'zh-CN': '复制', 'en': 'Copy' }
  };

  register(SHARED);

  window.DFI18N = {
    readLang: readLang,
    getLang: getLang,
    tr: tr,
    register: register,
    applyI18n: applyI18n,
    setLang: setLang,
    onLangChange: onLangChange
  };
})();
