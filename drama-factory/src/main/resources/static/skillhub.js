'use strict';
(function () {
  var PAGE_I18N = {
    'skh.title': { 'zh-CN': '技能中心', 'en': 'Skill Hub' },
    'skh.search': { 'zh-CN': '搜索技能...', 'en': 'Search skills...' },
    'skh.source': { 'zh-CN': '来源', 'en': 'Source' },
    'skh.all': { 'zh-CN': '全部', 'en': 'All' },
    'skh.install': { 'zh-CN': '安装', 'en': 'Install' },
    'skh.uninstall': { 'zh-CN': '卸载', 'en': 'Uninstall' },
    'skh.installed': { 'zh-CN': '已安装', 'en': 'Installed' },
    'skh.prev': { 'zh-CN': '上一页', 'en': 'Previous' },
    'skh.next': { 'zh-CN': '下一页', 'en': 'Next' },
    'skh.perPage': { 'zh-CN': '每页', 'en': 'Per page' },
    'skh.pageInfo': { 'zh-CN': '第 {p}/{t} 页，共 {n} 个', 'en': 'Page {p} of {t}, {n} total' }
  };

  function el(tag, className, text) {
    var e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
  }

  function _t(key, fallback) {
    var lang = (window.DFI18N && window.DFI18N.lang) || 'zh-CN';
    var dict = PAGE_I18N[key];
    if (dict && dict[lang]) return dict[lang];
    return fallback;
  }

  function api(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function toast(msg) {
    var t = el('div', 'position-fixed bottom-0 end-0 p-3', msg);
    t.style.zIndex = 1080;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 3000);
  }

  function showError(err) {
    var e = document.getElementById('skhError');
    if (e) {
      e.textContent = (err && err.message) ? err.message : String(err);
      e.style.display = 'block';
    }
  }

  function hideError() {
    var e = document.getElementById('skhError');
    if (e) e.style.display = 'none';
  }

  function setUpdated(ts) {
    var e = document.getElementById('skhUpdated');
    if (e && ts) e.textContent = new Date(ts).toLocaleString();
  }

  function applyI18nTo(root) {
    if (!root) return;
    var nodes = root.querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var key = n.getAttribute('data-i18n');
      if (key && PAGE_I18N[key]) {
        var lang = (window.DFI18N && window.DFI18N.lang) || 'zh-CN';
        n.textContent = PAGE_I18N[key][lang] || n.textContent;
      }
    }
  }

  function buildCard(skill) {
    var card = el('div', 'card h-100');
    var body = el('div', 'card-body');
    body.appendChild(el('h5', 'card-title', skill.name || skill.id));
    body.appendChild(el('p', 'card-text', skill.desc || ''));
    renderActions(body, skill);
    card.appendChild(body);
    return card;
  }

  function renderActions(container, skill) {
    var btn = el('button', 'btn btn-sm btn-primary', _t('skh.install', '安装'));
    btn.addEventListener('click', function () { doInstall(skill); });
    container.appendChild(btn);
  }

  function doInstall(skill) {
    toast('Installing ' + skill.name);
  }

  function doUninstall(skill) {
    toast('Uninstalling ' + skill.name);
  }

  var state = { skills: [], filterText: '', filterSource: '', page: 0, size: 48, total: 0, totalPages: 0 };

  function render() {
    var grid = document.getElementById('skhGrid');
    var emptyEl = document.getElementById('skhEmpty');
    var countEl = document.getElementById('skhCount');
    if (!grid) return;
    grid.innerHTML = '';
    for (var i = 0; i < state.skills.length; i++) { grid.appendChild(buildCard(state.skills[i])); }
    if (countEl) {
      var p = state.page + 1, t = Math.max(state.totalPages, 1);
      countEl.textContent = _t('skh.pageInfo', '第 {p}/{t} 页，共 {n} 个')
        .replace('{p}', String(p)).replace('{t}', String(t)).replace('{n}', String(state.total));
    }
    if (emptyEl) { emptyEl.style.display = state.total === 0 ? 'block' : 'none'; }
    renderPagination();
  }

  function renderPagination() {
    var grid = document.getElementById('skhGrid');
    var bar = document.getElementById('skhPagination');
    if (!bar) {
      bar = el('div', 'd-flex align-items-center justify-content-center flex-wrap gap-2 my-4');
      bar.id = 'skhPagination';
      var emptyEl = document.getElementById('skhEmpty');
      grid.parentNode.insertBefore(bar, emptyEl);
    }
    bar.innerHTML = '';
    if (state.total <= state.size) { bar.style.display = 'none'; return; }
    bar.style.display = '';
    var cur = state.page, totalP = state.totalPages;
    function pageBtn(label, p, disabled, active) {
      var b = el('button', 'btn btn-sm ' + (active ? 'btn-primary' : 'btn-ghost-secondary'), label);
      b.setAttribute('type', 'button');
      if (disabled) b.disabled = true;
      b.addEventListener('click', function () { state.page = p; load(); window.scrollTo(0, 0); });
      return b;
    }
    bar.appendChild(pageBtn(_t('skh.prev', '上一页'), cur - 1, cur === 0, false));
    var pages = [];
    for (var i = 0; i < totalP; i++) {
      if (i === 0 || i === totalP - 1 || Math.abs(i - cur) <= 2) pages.push(i);
    }
    var lastShown = -1;
    for (var k = 0; k < pages.length; k++) {
      if (pages[k] - lastShown > 1) bar.appendChild(el('span', 'text-secondary', '…'));
      bar.appendChild(pageBtn(String(pages[k] + 1), pages[k], false, pages[k] === cur));
      lastShown = pages[k];
    }
    bar.appendChild(pageBtn(_t('skh.next', '下一页'), cur + 1, cur >= totalP - 1, false));
    var perWrap = el('span', 'text-secondary small ms-2', _t('skh.perPage', '每页') + ' ');
    var sel = document.createElement('select');
    sel.className = 'form-select form-select-sm d-inline-block w-auto';
    [24, 48, 96].forEach(function (n) {
      var o = document.createElement('option');
      o.value = String(n); o.textContent = String(n);
      if (n === state.size) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () { state.size = parseInt(sel.value, 10) || 48; state.page = 0; load(); });
    perWrap.appendChild(sel);
    bar.appendChild(perWrap);
    applyI18nTo(bar);
  }

  async function load() {
    hideError();
    try {
      var url = '/api/skillhub/index?page=' + state.page + '&size=' + state.size
        + '&q=' + encodeURIComponent(state.filterText.trim())
        + '&source=' + encodeURIComponent(state.filterSource);
      var data = await api(url);
      state.skills = (data && data.skills) ? data.skills : [];
      state.total = data && data.total != null ? data.total : state.skills.length;
      state.page = data && data.page != null ? data.page : state.page;
      state.size = data && data.size != null ? data.size : state.size;
      state.totalPages = data && data.totalPages != null ? data.totalPages : 1;
      setUpdated(data ? data.updatedAt : null);
      render();
    } catch (err) {
      state.skills = []; state.total = 0; state.totalPages = 0;
      render();
      showError(err);
    }
  }

  var searchTimer = null;
  function bind() {
    var search = document.getElementById('skhSearch');
    if (search) {
      search.addEventListener('input', function () {
        if (searchTimer) clearTimeout(searchTimer);
        searchTimer = setTimeout(function () {
          state.filterText = search.value || '';
          state.page = 0;
          load();
        }, 300);
      });
    }
    var source = document.getElementById('skhSource');
    if (source) {
      source.addEventListener('change', function () {
        state.filterSource = source.value || '';
        state.page = 0;
        load();
      });
    }
  }

  function init() {
    bind();
    load();
    if (window.DFI18N && window.DFI18N.onChange) {
      window.DFI18N.onChange(function () {
        renderPagination();
        applyI18nTo(document.body);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();