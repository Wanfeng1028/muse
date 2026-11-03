(function () {
  'use strict';

  var PAGE_I18N = {
    'osk.pageTitle': { 'zh-CN': '官方 Skill 库 · AI 短剧工坊', en: 'Official Skills · AI Short Drama Studio' },
    'osk.heading': { 'zh-CN': '官方 Skill 库', en: 'Official Skills' },
    'osk.subtitle': { 'zh-CN': '官方收录的视频剪辑 skills，一键安装到本地。', en: 'Officially curated video-editing skills. Install to your local workspace in one click.' },
    'osk.search': { 'zh-CN': '搜索', en: 'Search' },
    'osk.searchPh': { 'zh-CN': '按名称、描述、作者搜索', en: 'Search by name, description, or author' },
    'osk.empty': { 'zh-CN': '没有找到匹配的 Skill', en: 'No matching Skill found' },
    'osk.installedTitle': { 'zh-CN': '已安装', en: 'Installed' },
    'osk.installedEmpty': { 'zh-CN': '还没有安装任何官方 Skill', en: 'No official Skill installed yet' },
    'osk.install': { 'zh-CN': '安装', en: 'Install' },
    'osk.uninstall': { 'zh-CN': '卸载', en: 'Uninstall' },
    'osk.installedBadge': { 'zh-CN': '已安装', en: 'Installed' },
    'osk.authorLabel': { 'zh-CN': '作者', en: 'Author' },
    'osk.licenseLabel': { 'zh-CN': '许可', en: 'License' },
    'osk.versionLabel': { 'zh-CN': '版本', en: 'Version' },
    'osk.sourceRepo': { 'zh-CN': '来源仓库', en: 'Source repo' },
    'osk.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'osk.installSuccess': { 'zh-CN': '安装成功', en: 'Installed' },
    'osk.installFailed': { 'zh-CN': '安装失败', en: 'Install failed' },
    'osk.uninstallSuccess': { 'zh-CN': '已卸载', en: 'Uninstalled' },
    'osk.uninstallFailed': { 'zh-CN': '卸载失败', en: 'Uninstall failed' },
    'osk.requestFailed': { 'zh-CN': '请求失败', en: 'Request failed' }
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
      let msg = _t('osk.requestFailed', '请求失败');
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
    skills: [],
    filter: ''
  };

  function filterSkills(list) {
    var q = state.filter.trim().toLowerCase();
    if (!q) return list;
    return list.filter(function (s) {
      var name = (s.name || '').toLowerCase();
      var desc = (s.description || '').toLowerCase();
      var author = (s.author || '').toLowerCase();
      return name.indexOf(q) !== -1 || desc.indexOf(q) !== -1 || author.indexOf(q) !== -1;
    });
  }

  function sourceLinkHtml(s) {
    if (!s.sourceUrl) return '';
    return '<a class="text-secondary" href="' + esc(s.sourceUrl) + '" target="_blank" rel="noopener noreferrer">'
      + esc(_t('osk.sourceRepo', '来源仓库')) + '</a>';
  }

  function cardHtml(s) {
    var installed = !!s.installed;
    var action = installed
      ? '<span class="badge bg-green-lt me-2">' + esc(_t('osk.installedBadge', '已安装')) + '</span>'
        + '<button type="button" class="btn btn-sm btn-outline-danger" data-action="uninstall" data-id="' + esc(s.id) + '">'
        + esc(_t('osk.uninstall', '卸载')) + '</button>'
      : '<button type="button" class="btn btn-sm btn-primary" data-action="install" data-id="' + esc(s.id) + '">'
        + esc(_t('osk.install', '安装')) + '</button>';
    return ''
      + '<div class="col-md-6 col-lg-4">'
      +   '<div class="card h-100">'
      +     '<div class="card-body">'
      +       '<h3 class="card-title mb-1">' + esc(s.name || s.id) + '</h3>'
      +       '<div class="text-secondary mb-2">' + esc(s.description || '') + '</div>'
      +       '<div class="text-secondary small">'
      +         esc(_t('osk.authorLabel', '作者')) + ': ' + esc(s.author || '-')
      +       '</div>'
      +       '<div class="text-secondary small">'
      +         esc(_t('osk.licenseLabel', '许可')) + ': ' + esc(s.license || '-')
      +         ' · ' + esc(_t('osk.versionLabel', '版本')) + ': ' + esc(s.version || '-')
      +       '</div>'
      +       (s.sourceUrl ? '<div class="small mt-1">' + sourceLinkHtml(s) + '</div>' : '')
      +     '</div>'
      +     '<div class="card-footer d-flex align-items-center justify-content-end">'
      +       action
      +     '</div>'
      +   '</div>'
      + '</div>';
  }

  function renderGrid() {
    var grid = document.getElementById('officialGrid');
    var empty = document.getElementById('officialEmpty');
    if (!grid) return;
    var list = filterSkills(state.skills);
    grid.innerHTML = list.map(cardHtml).join('');
    if (empty) empty.hidden = list.length !== 0;
    refreshIcons();
  }

  function renderInstalled() {
    var grid = document.getElementById('installedGrid');
    var empty = document.getElementById('installedEmpty');
    if (!grid) return;
    var list = state.skills.filter(function (s) { return !!s.installed; });
    grid.innerHTML = list.map(cardHtml).join('');
    if (empty) empty.hidden = list.length !== 0;
    refreshIcons();
  }

  function renderAll() {
    renderGrid();
    renderInstalled();
  }

  function showError(msg) {
    var el = document.getElementById('officialError');
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
  }

  function clearError() {
    var el = document.getElementById('officialError');
    if (!el) return;
    el.hidden = true;
    el.textContent = '';
  }

  async function loadSkills() {
    clearError();
    try {
      var data = await api('/api/official-skills/official');
      state.skills = Array.isArray(data) ? data : [];
      renderAll();
    } catch (e) {
      state.skills = [];
      renderAll();
      showError(_t('osk.loadFailed', '加载失败') + ': ' + (e && e.message ? e.message : ''));
    }
  }

  async function installSkill(id) {
    try {
      await api('/api/official-skills/install/' + encodeURIComponent(id), {
        method: 'POST',
        body: JSON.stringify({})
      });
      showToast(_t('osk.installSuccess', '安装成功'));
      await loadSkills();
    } catch (e) {
      showToast(_t('osk.installFailed', '安装失败') + ': ' + (e && e.message ? e.message : ''));
    }
  }

  async function uninstallSkill(id) {
    try {
      await api('/api/official-skills/installed/' + encodeURIComponent(id), { method: 'DELETE' });
      showToast(_t('osk.uninstallSuccess', '已卸载'));
      await loadSkills();
    } catch (e) {
      showToast(_t('osk.uninstallFailed', '卸载失败') + ': ' + (e && e.message ? e.message : ''));
    }
  }

  function bindEvents() {
    var search = document.getElementById('officialSearch');
    if (search) {
      search.addEventListener('input', function () {
        state.filter = search.value || '';
        renderGrid();
      });
    }
    document.addEventListener('click', function (ev) {
      var btn = ev.target.closest ? ev.target.closest('[data-action]') : null;
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var id = btn.getAttribute('data-id');
      if (!id) return;
      if (action === 'install') installSkill(id);
      else if (action === 'uninstall') uninstallSkill(id);
    });
  }

  function init() {
    bindEvents();
    applyI18nTo(document);
    loadSkills();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
