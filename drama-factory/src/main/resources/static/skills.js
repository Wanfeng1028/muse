(function () {
  'use strict';

  var PAGE_I18N = {
    'sk.pageTitle': { 'zh-CN': 'Skill 市场 · AI 短剧工坊', en: 'Skill Market · AI Short Drama Studio' },
    'sk.heading': { 'zh-CN': 'Skill 市场', en: 'Skill Market' },
    'sk.subtitle': { 'zh-CN': 'Agent 技能的发布、安装与管理', en: 'Publish, install, and manage Agent Skills' },
    'sk.search': { 'zh-CN': '搜索', en: 'Search' },
    'sk.searchPh': { 'zh-CN': '按名称、描述、作者搜索', en: 'Search by name, description, or author' },
    'sk.category': { 'zh-CN': '分类', en: 'Category' },
    'sk.sort': { 'zh-CN': '排序', en: 'Sort' },
    'sk.sortPopular': { 'zh-CN': '最受欢迎', en: 'Most popular' },
    'sk.sortRating': { 'zh-CN': '评分最高', en: 'Top rated' },
    'sk.sortNewest': { 'zh-CN': '最新发布', en: 'Newest' },
    'sk.sortName': { 'zh-CN': '名称', en: 'Name' },
    'sk.catScript': { 'zh-CN': 'SCRIPT 编剧', en: 'SCRIPT · Writing' },
    'sk.catBoard': { 'zh-CN': 'BOARD 分镜', en: 'BOARD · Storyboard' },
    'sk.catVideo': { 'zh-CN': 'VIDEO 视频', en: 'VIDEO' },
    'sk.catEdit': { 'zh-CN': 'EDIT 剪辑', en: 'EDIT · Editing' },
    'sk.catGeneral': { 'zh-CN': 'GENERAL 通用', en: 'GENERAL' },
    'sk.empty': { 'zh-CN': '没有找到匹配的 Skill', en: 'No matching Skill found' },
    'sk.installedTitle': { 'zh-CN': '已安装', en: 'Installed' },
    'sk.installedEmpty': { 'zh-CN': '还没有安装任何 Skill，去市场逛逛吧', en: 'No Skill installed yet — browse the market to get started' },
    'sk.publishTitle': { 'zh-CN': '发布 Skill', en: 'Publish Skill' },
    'sk.name': { 'zh-CN': '名称', en: 'Name' },
    'sk.slug': { 'zh-CN': '唯一标识', en: 'Slug' },
    'sk.slugPh': { 'zh-CN': '小写字母/数字/短横线，如 hook-opener', en: 'Lowercase letters, digits, or hyphens, e.g. hook-opener' },
    'sk.description': { 'zh-CN': '描述', en: 'Description' },
    'sk.author': { 'zh-CN': '作者', en: 'Author' },
    'sk.icon': { 'zh-CN': '图标', en: 'Icon' },
    'sk.tags': { 'zh-CN': '标签', en: 'Tags' },
    'sk.tagsPh': { 'zh-CN': '逗号分隔，如 钩子,开场,短视频', en: 'Comma-separated, e.g. hook,opening,short-video' },
    'sk.promptTemplate': { 'zh-CN': 'Prompt 模板', en: 'Prompt template' },
    'sk.promptTemplatePh': { 'zh-CN': '支持 {{变量名}} 占位，如：为{{topic}}写一个{{duration}}秒的开场钩子', en: 'Supports {{variable}} placeholders, e.g. write a {{duration}}-second opening hook about {{topic}}' },
    'sk.changelog': { 'zh-CN': '更新说明', en: 'Changelog' },
    'sk.publishBtn': { 'zh-CN': '发布', en: 'Publish' },
    'sk.detailTitle': { 'zh-CN': 'Skill 详情', en: 'Skill details' },
    'sk.official': { 'zh-CN': '官方', en: 'Official' },
    'sk.ratingNone': { 'zh-CN': '暂无评分', en: 'No ratings yet' },
    'sk.install': { 'zh-CN': '安装', en: 'Install' },
    'sk.installedBadge': { 'zh-CN': '已安装 ✓', en: 'Installed ✓' },
    'sk.detail': { 'zh-CN': '详情', en: 'Details' },
    'sk.allTags': { 'zh-CN': '全部标签', en: 'All tags' },
    'sk.installCount': { 'zh-CN': '安装', en: 'Installs' },
    'sk.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'sk.loadDetailFailed': { 'zh-CN': '加载详情失败', en: 'Failed to load details' },
    'sk.installSuccess': { 'zh-CN': '安装成功', en: 'Installed' },
    'sk.installFailed': { 'zh-CN': '安装失败', en: 'Install failed' },
    'sk.uninstallSuccess': { 'zh-CN': '已卸载', en: 'Uninstalled' },
    'sk.uninstallFailed': { 'zh-CN': '卸载失败', en: 'Uninstall failed' },
    'sk.rateSuccess': { 'zh-CN': '评分已提交', en: 'Rating submitted' },
    'sk.rateFailed': { 'zh-CN': '评分失败', en: 'Failed to submit rating' },
    'sk.ratePickStar': { 'zh-CN': '请选择评分星数', en: 'Pick a star rating first' },
    'sk.publishSuccess': { 'zh-CN': '发布成功', en: 'Published' },
    'sk.publishFailed': { 'zh-CN': '发布失败', en: 'Publish failed' },
    'sk.versionPublishSuccess': { 'zh-CN': '新版本已发布', en: 'New version published' },
    'sk.versionRequired': { 'zh-CN': '请填写版本号', en: 'Version number is required' },
    'sk.nameSlugRequired': { 'zh-CN': '请填写名称和唯一标识', en: 'Name and slug are required' },
    'sk.version': { 'zh-CN': '版本', en: 'Version' },
    'sk.installSelected': { 'zh-CN': '安装选中版本', en: 'Install selected version' },
    'sk.uninstall': { 'zh-CN': '卸载', en: 'Uninstall' },
    'sk.rating': { 'zh-CN': '评分', en: 'Rating' },
    'sk.rateCommentPh': { 'zh-CN': '评论（可选）', en: 'Comment (optional)' },
    'sk.rateSubmit': { 'zh-CN': '提交评分', en: 'Submit rating' },
    'sk.publishNewVersion': { 'zh-CN': '发布新版本', en: 'Publish new version' },
    'sk.versionPh': { 'zh-CN': '版本号，如 1.1.0', en: 'Version number, e.g. 1.1.0' },
    'sk.newPromptTemplatePh': { 'zh-CN': 'Prompt 模板，支持 {{变量名}}', en: 'Prompt template, supports {{variable}} placeholders' },
    'sk.newChangelogPh': { 'zh-CN': '更新说明', en: 'Changelog' },
    'sk.publishVersionBtn': { 'zh-CN': '发布版本', en: 'Publish version' },
    'sk.latestVersion': { 'zh-CN': '最新版本', en: 'Latest version' },
    'sk.authorLabel': { 'zh-CN': '作者', en: 'Author' },
    'sk.installedAt': { 'zh-CN': '安装于', en: 'Installed at' },
    'sk.installedHint': { 'zh-CN': '可在分镜板生成剧本/分镜时选用', en: 'Available when generating scripts or storyboards in the storyboard board' },
    'sk.requestFailed': { 'zh-CN': '请求失败', en: 'Request failed' }
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
      let msg = _t('sk.requestFailed', '请求失败');
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

  function fmtDateTime(s) {
    if (s === null || s === undefined || s === '') return '';
    var d = new Date(s);
    if (isNaN(d.getTime())) return String(s);
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  const state = { skills: [], installed: [], detailId: null };

  function currentFilters() {
    return {
      q: (document.getElementById('skillSearch') || {}).value || '',
      tag: state.activeTag || '',
      category: (document.getElementById('skillCategory') || {}).value || '',
      sort: (document.getElementById('skillSort') || {}).value || 'popular'
    };
  }

  function buildQuery(filters) {
    const params = new URLSearchParams();
    if (filters.q) params.set('q', filters.q);
    if (filters.tag) params.set('tag', filters.tag);
    if (filters.category) params.set('category', filters.category);
    if (filters.sort) params.set('sort', filters.sort);
    const qs = params.toString();
    return qs ? '?' + qs : '';
  }

  function categoryLabel(cat) {
    switch (cat) {
      case 'SCRIPT': return _t('sk.catScript', 'SCRIPT 编剧');
      case 'BOARD': return _t('sk.catBoard', 'BOARD 分镜');
      case 'VIDEO': return _t('sk.catVideo', 'VIDEO 视频');
      case 'EDIT': return _t('sk.catEdit', 'EDIT 剪辑');
      case 'GENERAL': return _t('sk.catGeneral', 'GENERAL 通用');
      default: return cat || '';
    }
  }

  async function loadMarket() {
    const grid = document.getElementById('skillGrid');
    const empty = document.getElementById('skillEmpty');
    try {
      const filters = currentFilters();
      const skills = await api('/api/skills' + buildQuery(filters));
      state.skills = Array.isArray(skills) ? skills : [];
      renderSkills();
      renderTagRow();
    } catch (e) {
      if (grid) grid.innerHTML = '';
      if (empty) { empty.hidden = false; empty.textContent = e.message || _t('sk.loadFailed', '加载失败'); }
    }
  }

  function renderSkills() {
    const grid = document.getElementById('skillGrid');
    const empty = document.getElementById('skillEmpty');
    if (!grid) return;
    const skills = state.skills || [];
    if (!skills.length) {
      grid.innerHTML = '';
      if (empty) { empty.hidden = false; empty.textContent = _t('sk.empty', '没有找到匹配的 Skill'); }
      refreshIcons();
      applyI18nTo(grid);
      return;
    }
    if (empty) empty.hidden = true;
    grid.innerHTML = skills.map((s) => {
      const icon = s.icon || 'puzzle';
      const version = s.latestVersion ? `<span class="badge">${esc(s.latestVersion)}</span>` : '';
      const official = s.official ? `<span class="badge">${_t('sk.official', '官方')}</span>` : '';
      const tags = (s.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
        .map((t) => `<span class="badge">${esc(t)}</span>`).join(' ');
      const rating = s.avgRating ? s.avgRating.toFixed(1) + '★' : _t('sk.ratingNone', '暂无评分');
      const installed = !!s.installedVersion;
      const installBtn = installed
        ? `<button class="btn btn-secondary btn-sm" disabled>${_t('sk.installedBadge', '已安装 ✓')}</button>`
        : `<button class="btn btn-primary btn-sm" data-install="${s.id}">${_t('sk.install', '安装')}</button>`;
      return `
      <div class="col-md-6 col-lg-4">
        <div class="card h-100">
          <div class="card-body d-flex flex-column">
            <div class="d-flex align-items-center gap-2 mb-2">
              <i data-lucide="${esc(icon)}"></i>
              <strong>${esc(s.name)}</strong>
              ${version}
              ${official}
            </div>
            <div class="text-secondary small mb-2">${esc(s.author || '')} · ${esc(categoryLabel(s.category))}</div>
            <div class="mb-2">${esc(s.description || '')}</div>
            <div class="mb-2">${tags}</div>
            <div class="text-secondary small mb-3">${_t('sk.installCount', '安装')} ${s.installCount || 0} · ${esc(rating)}</div>
            <div class="mt-auto d-flex gap-2">
              <button class="btn btn-secondary btn-sm" data-detail="${s.id}">${_t('sk.detail', '详情')}</button>
              ${installBtn}
            </div>
          </div>
        </div>
      </div>
    `;
    }).join('');
    refreshIcons();
    applyI18nTo(grid);
  }

  function renderTagRow() {
    const row = document.getElementById('skillTagRow');
    if (!row) return;
    const set = new Set();
    (state.skills || []).forEach((s) => {
      (s.tags || '').split(',').map((t) => t.trim()).filter(Boolean).forEach((t) => set.add(t));
    });
    const tags = Array.from(set);
    if (!tags.length) { row.innerHTML = ''; return; }
    const active = state.activeTag || '';
    const allBtn = `<button class="btn btn-sm ${active === '' ? 'btn-primary' : 'btn-secondary'}" data-tag="">${_t('sk.allTags', '全部标签')}</button>`;
    const chips = tags.map((t) => {
      const cls = active === t ? 'btn-primary' : 'btn-secondary';
      return `<button class="btn btn-sm ${cls}" data-tag="${esc(t)}">${esc(t)}</button>`;
    }).join('');
    row.innerHTML = `<div class="d-flex flex-wrap gap-2">${allBtn}${chips}</div>`;
    refreshIcons();
    applyI18nTo(row);
  }

  async function openDetail(id) {
    state.detailId = id;
    try {
      const skill = await api('/api/skills/' + id);
      renderDetail(skill);
      const modalEl = document.getElementById('skillDetailModal');
      if (window.tabler && tabler.Modal) {
        tabler.Modal.getOrCreateInstance(modalEl).show();
      }
    } catch (e) {
      showToast(e.message || _t('sk.loadDetailFailed', '加载详情失败'));
    }
  }

  function renderDetail(skill) {
    const body = document.getElementById('skillDetailBody');
    if (!body) return;
    const versions = (skill.versions || []).slice().sort((a, b) => {
      return (b.createdAt || '').localeCompare(a.createdAt || '');
    });
    const versionOptions = versions.map((v) => {
      const selected = v.version === skill.installedVersion ? ' selected' : '';
      return `<option value="${esc(v.version)}"${selected}>${esc(v.version)}</option>`;
    }).join('');
    const installed = !!skill.installedVersion;
    const installBtn = installed
      ? `<button class="btn btn-primary btn-sm" id="detailInstallBtn">${_t('sk.installSelected', '安装选中版本')}</button>`
      : `<button class="btn btn-primary btn-sm" id="detailInstallBtn">${_t('sk.install', '安装')}</button>`;
    const uninstallBtn = installed
      ? `<button class="btn btn-secondary btn-sm" id="detailUninstallBtn">${_t('sk.uninstall', '卸载')}</button>`
      : `<button class="btn btn-secondary btn-sm" id="detailUninstallBtn" disabled>${_t('sk.uninstall', '卸载')}</button>`;

    const ratings = (skill.ratings || []).slice().sort((a, b) => {
      return (b.createdAt || '').localeCompare(a.createdAt || '');
    }).slice(0, 5);
    const ratingsHtml = ratings.length
      ? ratings.map((r) => `
        <div class="mb-1">
          <span>${r.score}★</span>
          <span class="text-secondary small">${esc(r.comment || '')}</span>
        </div>`).join('')
      : `<div class="text-secondary small">${_t('sk.ratingNone', '暂无评分')}</div>`;

    const tags = (skill.tags || '').split(',').map((t) => t.trim()).filter(Boolean)
      .map((t) => `<span class="badge">${esc(t)}</span>`).join(' ');

    const stars = [1, 2, 3, 4, 5].map((n) =>
      `<button type="button" class="btn btn-sm btn-secondary" data-star="${n}">${n}★</button>`
    ).join('');

    body.innerHTML = `
    <div class="d-flex align-items-center gap-2 mb-2">
      <i data-lucide="${esc(skill.icon || 'puzzle')}"></i>
      <strong>${esc(skill.name)}</strong>
      ${skill.official ? '<span class="badge">' + _t('sk.official', '官方') + '</span>' : ''}
    </div>
    <div class="text-secondary small mb-2">
      ${_t('sk.latestVersion', '最新版本')} ${esc(skill.latestVersion || '-')} · ${_t('sk.authorLabel', '作者')} ${esc(skill.author || '')} · ${esc(categoryLabel(skill.category))}
    </div>
    <div class="mb-2">${tags}</div>
    <div class="mb-3">${esc(skill.description || '')}</div>

    <div class="mb-3">
      <label class="form-label" for="detailVersionSel">${_t('sk.version', '版本')}</label>
      <select class="form-select" id="detailVersionSel">${versionOptions}</select>
    </div>

    <div class="mb-3">
      <div class="form-label">${_t('sk.promptTemplate', 'Prompt 模板')}</div>
      <pre class="p-2 border rounded" style="white-space: pre-wrap; border-color: var(--border) !important;">${esc((versions[0] && versions[0].promptTemplate) || '')}</pre>
    </div>

    <div class="d-flex gap-2 mb-4">
      ${installBtn}
      ${uninstallBtn}
    </div>

    <div class="mb-3">
      <div class="form-label">${_t('sk.rating', '评分')}</div>
      <div class="d-flex gap-2 mb-2" id="rateStars">${stars}</div>
      <input type="text" class="form-control mb-2" id="rateComment" placeholder="${esc(_t('sk.rateCommentPh', '评论（可选）'))}">
      <button class="btn btn-primary btn-sm" id="rateBtn">${_t('sk.rateSubmit', '提交评分')}</button>
      <div class="mt-3">${ratingsHtml}</div>
    </div>

    <hr>

    <div class="mb-2">
      <div class="form-label">${_t('sk.publishNewVersion', '发布新版本')}</div>
      <div class="row g-2">
        <div class="col-md-4">
          <input type="text" class="form-control" id="newVersion" placeholder="${esc(_t('sk.versionPh', '版本号，如 1.1.0'))}">
        </div>
        <div class="col-12">
          <textarea class="form-control" id="newPromptTemplate" rows="3" placeholder="${esc(_t('sk.newPromptTemplatePh', 'Prompt 模板，支持 {{变量名}}'))}"></textarea>
        </div>
        <div class="col-12">
          <input type="text" class="form-control" id="newChangelog" placeholder="${esc(_t('sk.newChangelogPh', '更新说明'))}">
        </div>
      </div>
      <button class="btn btn-primary btn-sm mt-2" id="publishVersionBtn">${_t('sk.publishVersionBtn', '发布版本')}</button>
    </div>
  `;

    const versionSel = document.getElementById('detailVersionSel');
    if (versionSel) {
      versionSel.addEventListener('change', () => {
        const v = versions.find((x) => x.version === versionSel.value);
        const pre = body.querySelector('pre');
        if (pre && v) pre.textContent = v.promptTemplate || '';
      });
    }

    const installEl = document.getElementById('detailInstallBtn');
    if (installEl) installEl.addEventListener('click', () => installSkill(skill.id));
    const uninstallEl = document.getElementById('detailUninstallBtn');
    if (uninstallEl && installed) uninstallEl.addEventListener('click', () => uninstallSkill(skill.id));

    let selectedScore = 0;
    body.querySelectorAll('[data-star]').forEach((btn) => {
      btn.addEventListener('click', () => {
        selectedScore = parseInt(btn.getAttribute('data-star'), 10);
        body.querySelectorAll('[data-star]').forEach((b) => {
          const n = parseInt(b.getAttribute('data-star'), 10);
          b.className = 'btn btn-sm ' + (n <= selectedScore ? 'btn-primary' : 'btn-secondary');
        });
      });
    });
    const rateBtn = document.getElementById('rateBtn');
    if (rateBtn) {
      rateBtn.addEventListener('click', () => {
        if (!selectedScore) { showToast(_t('sk.ratePickStar', '请选择评分星数')); return; }
        rateSkill(skill.id, selectedScore);
      });
    }

    const publishVersionBtn = document.getElementById('publishVersionBtn');
    if (publishVersionBtn) publishVersionBtn.addEventListener('click', () => publishVersion(skill.id));

    refreshIcons();
    applyI18nTo(body);
  }

  async function installSkill(id) {
    const sel = document.getElementById('detailVersionSel');
    const version = sel ? sel.value : null;
    try {
      await api('/api/skills/' + id + '/install', {
        method: 'POST',
        body: JSON.stringify({ version: version || null })
      });
      showToast(_t('sk.installSuccess', '安装成功'));
      await loadMarket();
      await loadInstalled();
      if (state.detailId === id) {
        const skill = await api('/api/skills/' + id);
        renderDetail(skill);
      }
    } catch (e) {
      showToast(e.message || _t('sk.installFailed', '安装失败'));
    }
  }

  async function uninstallSkill(id) {
    try {
      await api('/api/skills/' + id + '/install', { method: 'DELETE' });
      showToast(_t('sk.uninstallSuccess', '已卸载'));
      await loadMarket();
      await loadInstalled();
      if (state.detailId === id) {
        const skill = await api('/api/skills/' + id);
        renderDetail(skill);
      }
    } catch (e) {
      showToast(e.message || _t('sk.uninstallFailed', '卸载失败'));
    }
  }

  async function rateSkill(id, score) {
    const commentEl = document.getElementById('rateComment');
    const comment = commentEl ? commentEl.value : '';
    try {
      await api('/api/skills/' + id + '/rate', {
        method: 'POST',
        body: JSON.stringify({ score: score, comment: comment })
      });
      showToast(_t('sk.rateSuccess', '评分已提交'));
      const skill = await api('/api/skills/' + id);
      renderDetail(skill);
      await loadMarket();
    } catch (e) {
      showToast(e.message || _t('sk.rateFailed', '评分失败'));
    }
  }

  async function publishVersion(id) {
    const versionEl = document.getElementById('newVersion');
    const tmplEl = document.getElementById('newPromptTemplate');
    const logEl = document.getElementById('newChangelog');
    const version = versionEl ? versionEl.value.trim() : '';
    const promptTemplate = tmplEl ? tmplEl.value : '';
    const changelog = logEl ? logEl.value : '';
    if (!version) { showToast(_t('sk.versionRequired', '请填写版本号')); return; }
    try {
      await api('/api/skills/' + id + '/versions', {
        method: 'POST',
        body: JSON.stringify({ version: version, promptTemplate: promptTemplate, changelog: changelog })
      });
      showToast(_t('sk.versionPublishSuccess', '新版本已发布'));
      const skill = await api('/api/skills/' + id);
      renderDetail(skill);
      await loadMarket();
    } catch (e) {
      showToast(e.message || _t('sk.publishFailed', '发布失败'));
    }
  }

  async function loadInstalled() {
    const list = document.getElementById('installedList');
    const empty = document.getElementById('installedEmpty');
    if (!list) return;
    try {
      const items = await api('/api/skills/installed');
      state.installed = Array.isArray(items) ? items : [];
      if (!state.installed.length) {
        list.innerHTML = '';
        if (empty) empty.hidden = false;
        refreshIcons();
        applyI18nTo(list);
        return;
      }
      if (empty) empty.hidden = true;
      list.innerHTML = state.installed.map((it) => {
        const skill = it.skill || {};
        const install = it.install || {};
        return `
        <div class="d-flex align-items-center justify-content-between py-2 installed-row">
          <div>
            <div class="d-flex align-items-center gap-2">
              <i data-lucide="${esc(skill.icon || 'puzzle')}"></i>
              <strong>${esc(skill.name || '')}</strong>
              <span class="badge">${esc(install.version || '')}</span>
            </div>
            <div class="text-secondary small">
              ${_t('sk.installedAt', '安装于')} ${esc(fmtDateTime(install.installedAt))} · ${_t('sk.installedHint', '可在分镜板生成剧本/分镜时选用')}
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" data-uninstall="${skill.id}">${_t('sk.uninstall', '卸载')}</button>
        </div>
      `;
      }).join('');
      refreshIcons();
      applyI18nTo(list);
    } catch (e) {
      if (list) list.innerHTML = '';
      if (empty) { empty.hidden = false; empty.textContent = e.message || _t('sk.loadFailed', '加载失败'); }
    }
  }

  async function publishSkill(e) {
    if (e) e.preventDefault();
    const body = {
      name: document.getElementById('pubName').value.trim(),
      slug: document.getElementById('pubSlug').value.trim(),
      description: document.getElementById('pubDescription').value,
      author: document.getElementById('pubAuthor').value.trim(),
      category: document.getElementById('pubCategory').value,
      tags: document.getElementById('pubTags').value.trim(),
      icon: document.getElementById('pubIcon').value,
      promptTemplate: document.getElementById('pubPromptTemplate').value,
      changelog: document.getElementById('pubChangelog').value
    };
    if (!body.name || !body.slug) { showToast(_t('sk.nameSlugRequired', '请填写名称和唯一标识')); return; }
    try {
      await api('/api/skills', { method: 'POST', body: JSON.stringify(body) });
      showToast(_t('sk.publishSuccess', '发布成功'));
      document.getElementById('publishForm').reset();
      await loadMarket();
      await loadInstalled();
    } catch (err) {
      showToast(err.message || _t('sk.publishFailed', '发布失败'));
    }
  }

  function bindEvents() {
    const search = document.getElementById('skillSearch');
    if (search) search.addEventListener('input', debounce(loadMarket, 300));
    const cat = document.getElementById('skillCategory');
    if (cat) cat.addEventListener('change', loadMarket);
    const sort = document.getElementById('skillSort');
    if (sort) sort.addEventListener('change', loadMarket);

    const tagRow = document.getElementById('skillTagRow');
    if (tagRow) {
      tagRow.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-tag]');
        if (!btn) return;
        state.activeTag = btn.getAttribute('data-tag') || '';
        loadMarket();
      });
    }

    const grid = document.getElementById('skillGrid');
    if (grid) {
      grid.addEventListener('click', (ev) => {
        const detailBtn = ev.target.closest('[data-detail]');
        if (detailBtn) {
          openDetail(detailBtn.getAttribute('data-detail'));
          return;
        }
        const installBtn = ev.target.closest('[data-install]');
        if (installBtn) {
          installSkill(installBtn.getAttribute('data-install'));
        }
      });
    }

    const installedList = document.getElementById('installedList');
    if (installedList) {
      installedList.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-uninstall]');
        if (!btn) return;
        uninstallSkill(btn.getAttribute('data-uninstall'));
      });
    }

    const form = document.getElementById('publishForm');
    if (form) form.addEventListener('submit', publishSkill);
  }

  function debounce(fn, wait) {
    let t = null;
    return function () {
      const args = arguments;
      if (t) clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), wait);
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (window.DFI18N) DFI18N.applyI18n(document);
    bindEvents();
    loadMarket();
    loadInstalled();
  });

  if (window.DFI18N && typeof DFI18N.onLangChange === 'function') {
    DFI18N.onLangChange(() => {
      renderSkills();
      renderTagRow();
      loadInstalled();
    });
  }
})();
