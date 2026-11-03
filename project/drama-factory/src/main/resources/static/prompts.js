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
    'prm.requestFailed': { 'zh-CN': '请求失败', en: 'Request failed' },
    'prm.kicker': { 'zh-CN': 'PROMPT LIBRARY · 实测收录', en: 'PROMPT LIBRARY · TESTED' },
    'prm.tagAll': { 'zh-CN': '全部', en: 'All' },
    'prm.favOnly': { 'zh-CN': '只看收藏', en: 'Favorites only' },
    'prm.pageInfo': { 'zh-CN': '第 {page} / {pages} 页 · 共 {total} 条', en: 'Page {page} / {pages} · {total} items' },
    'prm.prevPage': { 'zh-CN': '上一页', en: 'Previous' },
    'prm.nextPage': { 'zh-CN': '下一页', en: 'Next' },
    'prm.favAdd': { 'zh-CN': '已加入收藏', en: 'Added to favorites' },
    'prm.favRemove': { 'zh-CN': '已取消收藏', en: 'Removed from favorites' },
    'prm.copied': { 'zh-CN': '全文已复制到剪贴板', en: 'Full text copied to clipboard' },
    'prm.copyFailed': { 'zh-CN': '复制失败，请手动选择复制', en: 'Copy failed, please select and copy manually' },
    'prm.emptyFiltered': { 'zh-CN': '没有找到与当前筛选匹配的提示词，换个关键词或清空筛选试试。', en: 'No prompts match the current filters. Try a different keyword or clear the filters.' },
    'prm.emptyAll': { 'zh-CN': '提示词库现在是空的。提示词由后端自动从 resources/prompt-library/ 目录下的 Markdown 文件加载（子目录名即来源分类），新增 .md 文件后重启服务即可收录。', en: 'The prompt library is currently empty. Prompts are loaded automatically by the backend from Markdown files under resources/prompt-library/ (subdirectory names become source categories). Add a new .md file and restart the service to include it.' },
    'prm.favTitle': { 'zh-CN': '收藏/取消收藏', en: 'Add to / remove from favorites' },
    'prm.favDetailAdd': { 'zh-CN': '收藏', en: 'Favorite' },
    'prm.favDetailRemove': { 'zh-CN': '取消收藏', en: 'Unfavorite' },
    'prm.copyBtn': { 'zh-CN': '一键复制全文', en: 'Copy full text' }
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
    const text = await res.text();
    if (!res.ok) {
      let msg = _t('prm.requestFailed', '请求失败');
      try {
        const data = text ? JSON.parse(text) : null;
        if (data && (data.detail || data.message)) msg = data.detail || data.message;
      } catch (e) {}
      var err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    if (!text) return null;
    return JSON.parse(text);
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
    filter: '',
    tag: '',
    page: 0,
    size: 20,
    totalElements: 0,
    totalPages: 0,
    usePaging: true,
    favoritesOnly: false,
    favorites: {},
    favBusy: {}
  };

  function cardHtml(p) {
    var isFav = state.favorites[p.id] ? true : false;
    var starSvg = isFav
      ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-star text-warning"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>'
      : '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-star"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>';
    return ''
      + '<div class="col-md-6 col-lg-4">'
      +   '<div class="card h-100 prm-card">'
      +     '<div class="card-body">'
      +       '<h3 class="card-title mb-1">' + esc(p.title || p.id) + '</h3>'
      +       '<div class="text-secondary mb-2">' + esc(p.summary || '') + '</div>'
      +       '<div class="prm-meta mb-3">'
      +         esc(_t('prm.sourceLabel', '来源')) + ': ' + esc(p.source || '-')
      +         ' · ' + esc(p.path || '-')
      +       '</div>'
      +     '</div>'
      +     '<div class="card-footer d-flex align-items-center justify-content-between">'
      +       '<button type="button" class="btn btn-sm btn-primary d-inline-flex align-items-center gap-1" data-action="view" data-id="' + esc(p.id) + '">'
      +         '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-arrow-right"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>'
      +         esc(_t('prm.view', '查看全文')) + '</button>'
      +       '<button type="button" class="btn btn-sm btn-ghost-secondary" data-action="fav" data-id="' + esc(p.id) + '" title="' + esc(_t('prm.favTitle', '收藏/取消收藏')) + '">'
      +         starSvg
      +       '</button>'
      +     '</div>'
      +   '</div>'
      + '</div>';
  }

  function renderGrid() {
    var grid = document.getElementById('promptGrid');
    var empty = document.getElementById('promptEmpty');
    if (!grid) return;
    grid.innerHTML = state.prompts.map(cardHtml).join('');
    if (empty) {
      if (state.prompts.length !== 0) {
        empty.hidden = true;
      } else {
        var hasFilter = state.filter || state.tag || state.favoritesOnly;
        if (hasFilter) {
          empty.textContent = _t('prm.emptyFiltered', '没有找到与当前筛选匹配的提示词，换个关键词或清空筛选试试。');
        } else {
          empty.textContent = _t('prm.emptyAll', '提示词库现在是空的。提示词由后端自动从 resources/prompt-library/ 目录下的 Markdown 文件加载（子目录名即来源分类），新增 .md 文件后重启服务即可收录。');
        }
        empty.hidden = false;
      }
    }
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
    if (state.favoritesOnly) {
      try {
        var favData = await api('/api/prompts/favorites');
        state.prompts = Array.isArray(favData) ? favData : [];
        state.totalElements = state.prompts.length;
        state.totalPages = 1;
        state.page = 0;
        renderGrid();
        renderPager();
      } catch (e) {
        state.prompts = [];
        renderGrid();
        showError(_t('prm.loadFailed', '加载失败') + ': ' + (e && e.message ? e.message : ''));
      }
      return;
    }
    if (state.usePaging) {
      try {
        var qs = '?q=' + encodeURIComponent(state.filter || '')
          + '&tag=' + encodeURIComponent(state.tag || '')
          + '&page=' + state.page
          + '&size=' + state.size;
        var data = await api('/api/prompts/page' + qs);
        state.prompts = Array.isArray(data.content) ? data.content : [];
        state.page = typeof data.page === 'number' ? data.page : 0;
        state.size = typeof data.size === 'number' ? data.size : 20;
        state.totalElements = typeof data.totalElements === 'number' ? data.totalElements : 0;
        state.totalPages = typeof data.totalPages === 'number' ? data.totalPages : 0;
        renderGrid();
        renderPager();
      } catch (e) {
        if ((e && e.status === 404) || (e && e.message && e.message.indexOf('404') !== -1)) {
          state.usePaging = false;
          loadPrompts();
        } else {
          state.prompts = [];
          renderGrid();
          showError(_t('prm.loadFailed', '加载失败') + ': ' + (e && e.message ? e.message : ''));
        }
      }
      return;
    }
    try {
      var url = '/api/prompts' + (state.filter ? '?q=' + encodeURIComponent(state.filter) : '');
      var data = await api(url);
      var arr = Array.isArray(data) ? data : [];
      if (state.tag) {
        arr = arr.filter(function (p) {
          return (p.tags || []).indexOf(state.tag) !== -1 || p.source === state.tag;
        });
      }
      state.prompts = arr;
      state.totalElements = arr.length;
      state.totalPages = 1;
      state.page = 0;
      renderGrid();
      renderPager();
    } catch (e) {
      state.prompts = [];
      renderGrid();
      showError(_t('prm.loadFailed', '加载失败') + ': ' + (e && e.message ? e.message : ''));
    }
  }

  async function loadTags() {
    try {
      var tags = await api('/api/prompts/tags');
      if (Array.isArray(tags)) {
        renderTagChips(tags);
      } else {
        var chips = document.getElementById('tagChips');
        if (chips) chips.hidden = true;
      }
    } catch (e) {
      var chips = document.getElementById('tagChips');
      if (chips) chips.hidden = true;
    }
  }

  function renderTagChips(tags) {
    var container = document.getElementById('tagChips');
    if (!container) return;
    container.hidden = false;
    var html = '';
    html += '<button type="button" class="prm-chip' + (state.tag === '' ? ' is-active' : '') + '" data-tag="">' + esc(_t('prm.tagAll', '全部')) + '</button>';
    for (var i = 0; i < tags.length; i++) {
      var t = tags[i];
      html += '<button type="button" class="prm-chip' + (state.tag === t ? ' is-active' : '') + '" data-tag="' + esc(t) + '">' + esc(t) + '</button>';
    }
    container.innerHTML = html;
  }

  async function loadFavorites() {
    try {
      var favs = await api('/api/prompts/favorites');
      state.favorites = {};
      if (Array.isArray(favs)) {
        for (var i = 0; i < favs.length; i++) {
          if (favs[i] && favs[i].id) state.favorites[favs[i].id] = true;
        }
      }
    } catch (e) {
      state.favorites = {};
    }
  }

  function renderPager() {
    var pager = document.getElementById('pager');
    if (!pager) return;
    var prev = document.getElementById('pagePrev');
    var next = document.getElementById('pageNext');
    var info = document.getElementById('pageInfo');
    if (state.favoritesOnly || !state.usePaging) {
      pager.hidden = true;
      return;
    }
    pager.hidden = false;
    if (prev) {
      prev.disabled = state.page <= 0;
      prev.textContent = _t('prm.prevPage', '上一页');
    }
    if (next) {
      next.disabled = state.page >= state.totalPages - 1;
      next.textContent = _t('prm.nextPage', '下一页');
    }
    if (info) {
      var tpl = _t('prm.pageInfo', '第 {page} / {pages} 页 · 共 {total} 条');
      info.textContent = tpl
        .replace('{page}', String(state.page + 1))
        .replace('{pages}', String(state.totalPages))
        .replace('{total}', String(state.totalElements));
    }
  }

  function setFavButtonsDisabled(id, disabled) {
    var selector = '[data-action="fav"][data-id="' + id + '"]';
    var btns = document.querySelectorAll(selector);
    for (var i = 0; i < btns.length; i++) {
      btns[i].disabled = disabled;
      btns[i].style.opacity = disabled ? '0.45' : '';
    }
    var detailBtn = document.getElementById('promptDetailFavBtn');
    if (detailBtn && detailBtn.dataset.currentId === id) {
      detailBtn.disabled = disabled;
      detailBtn.style.opacity = disabled ? '0.45' : '';
    }
  }

  async function toggleFavorite(id, afterToggle) {
    if (state.favBusy[id]) return;
    state.favBusy[id] = true;
    setFavButtonsDisabled(id, true);
    var isFav = state.favorites[id] ? true : false;
    try {
      if (isFav) {
        await api('/api/prompts/' + encodeURIComponent(id) + '/favorite', { method: 'DELETE' });
        delete state.favorites[id];
        showToast(_t('prm.favRemove', '已取消收藏'));
      } else {
        await api('/api/prompts/' + encodeURIComponent(id) + '/favorite', { method: 'POST' });
        state.favorites[id] = true;
        showToast(_t('prm.favAdd', '已加入收藏'));
      }
      if (state.favoritesOnly) {
        state.prompts = state.prompts.filter(function (p) { return p && (p.id !== id || state.favorites[p.id]); });
        state.totalElements = state.prompts.length;
      }
      renderGrid();
      if (typeof afterToggle === 'function') afterToggle(state.favorites[id] ? true : false);
    } catch (e) {
      showToast((e && e.message ? e.message : _t('prm.requestFailed', '请求失败')));
    } finally {
      delete state.favBusy[id];
      setFavButtonsDisabled(id, false);
    }
  }

  function copyDetailText() {
    var content = document.getElementById('promptDetailContent');
    if (!content) return;
    var text = content.textContent || '';
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        showToast(_t('prm.copied', '全文已复制到剪贴板'));
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    if (ok) {
      showToast(_t('prm.copied', '全文已复制到剪贴板'));
    } else {
      showToast(_t('prm.copyFailed', '复制失败，请手动选择复制'));
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
      var copyBtn = document.getElementById('copyPromptBtn');
      if (copyBtn) {
        copyBtn.onclick = function () { copyDetailText(); };
      }
      var favBtn = document.getElementById('promptDetailFavBtn');
      if (favBtn) {
        favBtn.dataset.currentId = id;
        var syncDetailFavBtn = function (favNow) {
          var on = typeof favNow === 'boolean' ? favNow : (state.favorites[id] ? true : false);
          favBtn.textContent = on ? _t('prm.favDetailRemove', '取消收藏') : _t('prm.favDetailAdd', '收藏');
          favBtn.classList.toggle('btn-outline-warning', !on);
          favBtn.classList.toggle('btn-warning', on);
        };
        syncDetailFavBtn();
        favBtn.onclick = function () { toggleFavorite(id, syncDetailFavBtn); };
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
          state.page = 0;
          loadPrompts();
        }, 300);
      });
    }
    var favSwitch = document.getElementById('favOnlySwitch');
    if (favSwitch) {
      favSwitch.addEventListener('change', function () {
        state.favoritesOnly = favSwitch.checked;
        state.page = 0;
        loadPrompts();
      });
    }
    var tagChips = document.getElementById('tagChips');
    if (tagChips) {
      tagChips.addEventListener('click', function (ev) {
        var chip = ev.target.closest ? ev.target.closest('[data-tag]') : null;
        if (!chip) return;
        state.tag = chip.getAttribute('data-tag') || '';
        state.page = 0;
        loadPrompts();
      });
    }
    var prev = document.getElementById('pagePrev');
    if (prev) {
      prev.addEventListener('click', function () {
        if (state.page > 0) {
          state.page = state.page - 1;
          loadPrompts();
        }
      });
    }
    var next = document.getElementById('pageNext');
    if (next) {
      next.addEventListener('click', function () {
        if (state.page < state.totalPages - 1) {
          state.page = state.page + 1;
          loadPrompts();
        }
      });
    }
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-action]') : null;
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var id = btn.getAttribute('data-id');
      if (!id) return;
      if (action === 'view') viewPrompt(id);
      if (action === 'fav') toggleFavorite(id);
    });
    var back = document.getElementById('promptBackBtn');
    if (back) {
      back.addEventListener('click', function () {
        var card = document.getElementById('promptDetailCard');
        if (card) card.hidden = true;
      });
    }
  }

  async function init() {
    bindEvents();
    applyI18nTo(document);
    await loadFavorites();
    loadTags();
    loadPrompts();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
