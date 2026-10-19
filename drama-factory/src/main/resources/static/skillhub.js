(function () {
  'use strict';

  var PAGE_I18N = {
    'skh.heading': { 'zh-CN': 'SkillHub', 'en': 'SkillHub' },
    'skh.subtitle': { 'zh-CN': '浏览和安装官方与社区收录的 Skill', 'en': 'Browse and install official and community Skills' },
    'skh.search': { 'zh-CN': '搜索', 'en': 'Search' },
    'skh.searchPh': { 'zh-CN': '按名称、作者、描述搜索', 'en': 'Search by name, author, description' },
    'skh.sourceFilter': { 'zh-CN': '来源', 'en': 'Source' },
    'skh.sourceAll': { 'zh-CN': '全部', 'en': 'All' },
    'skh.sourceOfficial': { 'zh-CN': '官方出品', 'en': 'Official' },
    'skh.sourceCommunity': { 'zh-CN': '社区收录', 'en': 'Community' },
    'skh.updatedAt': { 'zh-CN': '索引更新于 -', 'en': 'Index updated at -' },
    'skh.empty': { 'zh-CN': '没有匹配的 Skill', 'en': 'No matching Skills' },
    'skh.pageTitle': { 'zh-CN': 'SkillHub · AI 短剧工坊', 'en': 'SkillHub · AI Short Drama Studio' },
    'skh.countLine': { 'zh-CN': '共 {n} 个', 'en': '{n} total' },
    'skh.install': { 'zh-CN': '安装', 'en': 'Install' },
    'skh.installing': { 'zh-CN': '安装中…', 'en': 'Installing…' },
    'skh.installedBadge': { 'zh-CN': '已安装', 'en': 'Installed' },
    'skh.uninstall': { 'zh-CN': '卸载', 'en': 'Uninstall' },
    'skh.authorLabel': { 'zh-CN': '作者', 'en': 'Author' },
    'skh.licenseLabel': { 'zh-CN': '许可', 'en': 'License' },
    'skh.versionLabel': { 'zh-CN': '版本', 'en': 'Version' },
    'skh.sourceRepo': { 'zh-CN': '来源仓库', 'en': 'Source repo' },
    'skh.installSuccess': { 'zh-CN': '安装成功', 'en': 'Installed' },
    'skh.installFailed': { 'zh-CN': '安装失败', 'en': 'Install failed' },
    'skh.uninstallSuccess': { 'zh-CN': '已卸载', 'en': 'Uninstalled' },
    'skh.uninstallFailed': { 'zh-CN': '卸载失败', 'en': 'Uninstall failed' },
    'skh.loadFailed': { 'zh-CN': '加载失败', 'en': 'Failed to load' },
    'skh.uninstallConfirm': { 'zh-CN': '确定卸载吗？', 'en': 'Uninstall?' },
    'skh.updatedAtFmt': { 'zh-CN': '索引更新于 {t}', 'en': 'Index updated at {t}' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N && typeof DFI18N.t === 'function') {
      var v = DFI18N.t(key);
      if (v && v !== key) return v;
    }
    return zh != null ? zh : key;
  }

  function applyI18nTo(root) {
    if (window.DFI18N && typeof DFI18N.apply === 'function') {
      DFI18N.apply(root || document);
      return;
    }
    var nodes = (root || document).querySelectorAll('[data-i18n]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var key = el.getAttribute('data-i18n');
      if (!key) continue;
      var val = _t(key, el.textContent);
      if (val != null) el.textContent = val;
    }
  }

  async function api(path, options) {
    var opts = options || {};
    var res = await fetch(path, opts);
    if (!res.ok) {
      var msg = 'HTTP ' + res.status;
      try {
        var body = await res.json();
        if (body && body.message) msg = body.message;
        else if (body && body.error) msg = body.error;
      } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function toast(kind, text) {
    var container = document.getElementById('skhToastContainer');
    if (!container) return;
    var cls = kind === 'success' ? 'alert alert-success' : 'alert alert-danger';
    var node = el('div', cls, text);
    node.setAttribute('role', 'alert');
    container.appendChild(node);
    setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 3000);
  }

  var state = {
    skills: [],
    filterText: '',
    filterSource: ''
  };

  function matches(skill) {
    var src = state.filterSource;
    if (src && skill.source !== src) return false;
    var q = state.filterText.trim().toLowerCase();
    if (!q) return true;
    var hay = [skill.id, skill.name, skill.description, skill.author]
      .map(function (v) { return v == null ? '' : String(v).toLowerCase(); })
      .join('\n');
    return hay.indexOf(q) !== -1;
  }

  function buildCard(skill) {
    var col = el('div', 'col-12 col-md-6 col-xl-4');
    var card = el('div', 'card');
    var body = el('div', 'card-body');

    var titleRow = el('div', 'd-flex align-items-center flex-wrap gap-2 mb-2');
    titleRow.appendChild(el('strong', null, skill.name || skill.id || ''));
    if (skill.version) {
      titleRow.appendChild(el('span', 'badge bg-blue-lt', skill.version));
    }
    if (skill.source === '官方出品') {
      titleRow.appendChild(el('span', 'badge bg-green-lt', _t('skh.sourceOfficial', '官方出品')));
    } else if (skill.source === '社区收录') {
      titleRow.appendChild(el('span', 'badge bg-secondary-lt', _t('skh.sourceCommunity', '社区收录')));
    } else if (skill.source) {
      titleRow.appendChild(el('span', 'badge bg-secondary-lt', skill.source));
    }
    body.appendChild(titleRow);

    var desc = skill.description && String(skill.description).trim() ? skill.description : '-';
    body.appendChild(el('p', 'text-secondary', desc));

    var meta = el('div', 'text-secondary small mb-3');
    var authorLine = el('div', null, _t('skh.authorLabel', '作者') + ': ' + (skill.author || '-'));
    meta.appendChild(authorLine);
    var licenseLine = el('div', null, _t('skh.licenseLabel', '许可') + ': ' + (skill.license || '-'));
    meta.appendChild(licenseLine);
    if (skill.sourceUrl) {
      var repoLine = el('div', null, _t('skh.sourceRepo', '来源仓库') + ': ');
      var link = el('a', null, skill.sourceUrl);
      link.setAttribute('href', skill.sourceUrl);
      link.setAttribute('target', '_blank');
      link.setAttribute('rel', 'noopener noreferrer');
      repoLine.appendChild(link);
      meta.appendChild(repoLine);
    }
    body.appendChild(meta);

    var btnRow = el('div', 'd-flex justify-content-end gap-2');
    body.appendChild(btnRow);

    renderActions(btnRow, skill);

    card.appendChild(body);
    col.appendChild(card);
    return col;
  }

  function renderActions(row, skill) {
    row.innerHTML = '';
    if (skill.installed) {
      row.appendChild(el('span', 'badge bg-green-lt', _t('skh.installedBadge', '已安装')));
      var unBtn = el('button', 'btn btn-ghost-danger btn-sm', _t('skh.uninstall', '卸载'));
      unBtn.setAttribute('type', 'button');
      unBtn.addEventListener('click', function () {
        doUninstall(skill, row, unBtn);
      });
      row.appendChild(unBtn);
    } else {
      var btn = el('button', 'btn btn-primary btn-sm', _t('skh.install', '安装'));
      btn.setAttribute('type', 'button');
      if (skill.installable === false) {
        btn.disabled = true;
      }
      btn.addEventListener('click', function () {
        doInstall(skill, row, btn);
      });
      row.appendChild(btn);
    }
  }

  async function doInstall(skill, row, btn) {
    btn.disabled = true;
    btn.textContent = _t('skh.installing', '安装中…');
    try {
      var res = await api('/api/official-skills/install/' + encodeURIComponent(skill.id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      });
      skill.installed = true;
      if (res && res.version) skill.installedVersion = res.version;
      toast('success', _t('skh.installSuccess', '安装成功'));
      renderActions(row, skill);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = _t('skh.install', '安装');
      toast('error', _t('skh.installFailed', '安装失败') + ': ' + (err && err.message ? err.message : ''));
    }
  }

  async function doUninstall(skill, row, btn) {
    if (!window.confirm(_t('skh.uninstallConfirm', '确定卸载吗？'))) return;
    btn.disabled = true;
    try {
      await api('/api/official-skills/installed/' + encodeURIComponent(skill.id), {
        method: 'DELETE'
      });
      skill.installed = false;
      skill.installedVersion = null;
      toast('success', _t('skh.uninstallSuccess', '已卸载'));
      renderActions(row, skill);
    } catch (err) {
      btn.disabled = false;
      toast('error', _t('skh.uninstallFailed', '卸载失败') + ': ' + (err && err.message ? err.message : ''));
    }
  }

  function render() {
    var grid = document.getElementById('skhGrid');
    var emptyEl = document.getElementById('skhEmpty');
    var countEl = document.getElementById('skhCount');
    if (!grid) return;

    var list = state.skills.filter(matches);

    grid.innerHTML = '';
    for (var i = 0; i < list.length; i++) {
      grid.appendChild(buildCard(list[i]));
    }

    if (countEl) {
      countEl.textContent = _t('skh.countLine', '共 {n} 个').replace('{n}', String(list.length));
    }

    if (emptyEl) {
      emptyEl.style.display = list.length === 0 ? 'block' : 'none';
    }
  }

  function setUpdated(updatedAt) {
    var node = document.getElementById('skhUpdated');
    if (!node) return;
    var t = '-';
    if (updatedAt) {
      var d = new Date(updatedAt);
      if (!isNaN(d.getTime())) {
        var p = function (n) { return (n < 10 ? '0' : '') + n; };
        t = d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' '
          + p(d.getHours()) + ':' + p(d.getMinutes());
      } else {
        t = String(updatedAt);
      }
    }
    node.textContent = _t('skh.updatedAtFmt', '索引更新于 {t}').replace('{t}', t);
  }

  function showError(err) {
    var node = document.getElementById('skhError');
    if (!node) return;
    node.textContent = _t('skh.loadFailed', '加载失败') + ': ' + (err && err.message ? err.message : '');
    node.style.display = 'block';
  }

  function hideError() {
    var node = document.getElementById('skhError');
    if (!node) return;
    node.style.display = 'none';
  }

  async function load() {
    hideError();
    try {
      var data = await api('/api/skillhub/index');
      state.skills = (data && data.skills) ? data.skills : [];
      setUpdated(data ? data.updatedAt : null);
      render();
    } catch (err) {
      state.skills = [];
      render();
      showError(err);
    }
  }

  function bind() {
    var search = document.getElementById('skhSearch');
    if (search) {
      search.addEventListener('input', function () {
        state.filterText = search.value || '';
        render();
      });
    }
    var source = document.getElementById('skhSource');
    if (source) {
      source.addEventListener('change', function () {
        state.filterSource = source.value || '';
        render();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.title = _t('skh.pageTitle', 'SkillHub · AI 短剧工坊');
    applyI18nTo(document);
    bind();
    load();
  });

  if (window.DFI18N && typeof DFI18N.onChange === 'function') {
    DFI18N.onChange(function () {
      document.title = _t('skh.pageTitle', 'SkillHub · AI 短剧工坊');
      setUpdated(state.updatedAt);
      render();
    });
  }
})();
