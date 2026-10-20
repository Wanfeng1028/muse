(function () {
  'use strict';

  var PAGE_I18N = {
    'prm.pageTitle': { 'zh-CN': '提示词库 · AI 短剧工坊', en: 'Prompt Library · AI Short Drama Studio' },
    'prm.heading': { 'zh-CN': '提示词库', en: 'Prompt Library' },
    'prm.subtitle': { 'zh-CN': '收集的实测提示词与教程拆解：浏览、搜索、查看全文。', en: 'Collected battle-tested prompts and tutorial breakdowns: browse, search, and read in full.' },
    'prm.search': { 'zh-CN': '搜索', en: 'Search' },
    'prm.searchPh': { 'zh-CN': '按标题、摘要搜索', en: 'Search by title or summary' },
    'prm.empty': { 'zh-CN': '没有找到匹配的提示词', en: 'No matching prompt found' },
    'prm.view': { 'zh-CN': '查看全文', en: 'View' },
    'prm.back': { 'zh-CN': '返回列表', en: 'Back to list' },
    'prm.sourceLabel': { 'zh-CN': '来源', en: 'Source' },
    'prm.pathLabel': { 'zh-CN': '路径', en: 'Path' },
    'prm.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'prm.requestFailed': { 'zh-CN': '请求失败', en: 'Request failed' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N && typeof DFI18N.tr === 'function') {
      var v = DFI18N.tr(key);
      if (v && v !== key) return v;
    }
    return zh;
  }

  function applyI18nTo(root) {
    if (window.DFI18N && typeof DFI18N.applyI18n === 'function') {
      DFI18N.applyI18n(root);
    }
  }

  async function api(path, options) {
    const res = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' }
    }, options || {}));
    if (!res.ok) {
      let msg = _t('prm.requestFailed', '请求失败');
      try {
        const data = await res.json();
        if (data && (data.detail || data.message)) msg = data.detail || data.message;
      } catch (e) {}
      throw new Error(msg);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  let toastTimer = null;
  function showToast(msg) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2500);
  }

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  var state = {
    prompts: [],
    filter: ''
  };

  function cardHtml(p) {
    return ''
      + '<div class="col-md-6 col-lg-4">'
      +   '<div class="card h-100">'
      +     '<div class="card-body">'
      +       '<h3 class="card-title mb-1">' + esc(p.title || p.id) + '</h3>'
      +       '<div class="text-secondary mb-2">' + esc(p.summary || '') + '</div>'
      +       '<div class="text-secondary small">'
      +         esc(_t('prm.sourceLabel', '来源')) + ': ' + esc(p.source || '-')
      +         ' · ' + esc(p.path || '-')
      +       '</div>'
      +     '</div>'
      +     '<div class="card-footer d-flex align-items-center justify-content-end">'
      +       '<button type="button" class="btn btn-sm btn-primary" data-action="view" data-id="' + esc(p.id) + '">'
      +         esc(_t('prm.view', '查看全文')) + '</button>'
      +     '</div>'
      +   '</div>'
      + '</div>';
  }

  function renderGrid() {
    var grid = document.getElementById('promptGrid');
    var empty = document.getElementById('promptEmpty');
    if (!grid) return;
    grid.innerHTML = state.prompts.map(cardHtml).join('');
    if (empty) empty.hidden = state.prompts.length !== 0;
    refreshIcons();
  }

  function showError(msg) {
    var el = document.getElementById('promptError');
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
  }

  function clearError() {
    var el = document.getElementById('promptError');
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
  }

  async function loadPrompts() {
    clearError();
    try {
      var url = '/api/prompts' + (state.filter ? '?q=' + encodeURIComponent(state.filter) : '');
      var data = await api(url);
      state.prompts = Array.isArray(data) ? data : [];
      renderGrid();
    } catch (e) {
      state.prompts = [];
      renderGrid();
      showError(_t('prm.loadFailed', '加载失败') + ': ' + (e && e.message ? e.message : ''));
    }
  }

  async function viewPrompt(id) {
    try {
      var data = await api('/api/prompts/' + encodeURIComponent(id));
      if (!data) return;
      var card = document.getElementById('promptDetailCard');
      var title = document.getElementById('promptDetailTitle');
      var meta = document.getElementById('promptDetailMeta');
      var content = document.getElementById('promptDetailContent');
      if (title) title.textContent = data.title || data.id || '';
      if (meta) {
        meta.textContent = _t('prm.sourceLabel', '来源') + ': ' + (data.source || '-')
          + ' · ' + _t('prm.pathLabel', '路径') + ': ' + (data.path || '-');
      }
      if (content) content.textContent = data.content || '';
      if (card) {
        card.hidden = false;
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (e) {
      showToast((e && e.message ? e.message : _t('prm.requestFailed', '请求失败')));
    }
  }

  function bindEvents() {
    var search = document.getElementById('promptSearch');
    var timer = null;
    if (search) {
      search.addEventListener('input', function () {
        if (timer) clearTimeout(timer);
        timer = setTimeout(function () {
          state.filter = search.value || '';
          loadPrompts();
        }, 300);
      });
    }
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-action]') : null;
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var id = btn.getAttribute('data-id');
      if (!id) return;
      if (action === 'view') viewPrompt(id);
    });
    var back = document.getElementById('promptBackBtn');
    if (back) {
      back.addEventListener('click', function () {
        var card = document.getElementById('promptDetailCard');
        if (card) card.hidden = true;
      });
    }
  }

  function init() {
    bindEvents();
    applyI18nTo(document);
    loadPrompts();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
