/* ==========================================================================
   shell.js —— drama-factory 应用壳（v5.2）
   注入左侧窄导航栏 + 顶部全局搜索条 + ⌘K 命令面板，统一 7 页视觉语言。
   约定：各页保留原有内容区；原 header.navbar 由 CSS 隐藏。
   v5.2：接入 DFI18N 中英双语（侧边栏/顶栏/命令面板/语言切换器）。
   ========================================================================== */
(function () {
  'use strict';

  /* ---- 应用壳字典：注册进 DFI18N（后注册覆盖先注册） ---- */
  var SHELL_I18N = {
    'nav.index': { 'zh-CN': 'AI 工作区', 'en': 'AI Workspace' },
    'nav.chat': { 'zh-CN': 'AI 对话', 'en': 'AI Chat' },
    'nav.images': { 'zh-CN': 'AI 图片', 'en': 'AI Images' },
    'nav.music': { 'zh-CN': 'AI 音乐', 'en': 'AI Music' },
    'nav.mv': { 'zh-CN': 'AI MV', 'en': 'AI MV' },
    'nav.avatar': { 'zh-CN': '数字人', 'en': 'Digital Human' },
    'nav.runs': { 'zh-CN': '运行列表', 'en': 'Runs' },
    'nav.agents': { 'zh-CN': 'Agent 机队', 'en': 'Agent Fleet' },
    'nav.skills': { 'zh-CN': 'Skill 市场', 'en': 'Skill Marketplace' },
    'nav.officialSkills': { 'zh-CN': '官方 Skill 库', 'en': 'Official Skills' },
    'nav.skillhub': { 'zh-CN': 'SkillHub', 'en': 'SkillHub' },
    'nav.usage': { 'zh-CN': '用量统计', 'en': 'Usage' },
    'nav.prompts': { 'zh-CN': '提示词库', 'en': 'Prompt Library' },
    'nav.costLedger': { 'zh-CN': '成本账本', 'en': 'Cost Ledger' },
    'nav.storyboard': { 'zh-CN': '分镜板', 'en': 'Storyboard' },
    'nav.canvas': { 'zh-CN': '分镜画布', 'en': 'Shot Canvas' },
    'nav.tasks': { 'zh-CN': '任务队列', 'en': 'Task Queue' },
    'nav.finals': { 'zh-CN': '成片库', 'en': 'Final Cuts' },
    'nav.pipeline': { 'zh-CN': '生产看板', 'en': 'Production Board' },
    'nav.tools': { 'zh-CN': '快捷工具', 'en': 'Quick Tools' },
    'nav.settings': { 'zh-CN': '设置', 'en': 'Settings' },
    'nav.account': { 'zh-CN': '账号', 'en': 'Account' },

    'navgroup.create': { 'zh-CN': '创作', 'en': 'Create' },
    'navgroup.run': { 'zh-CN': '运行', 'en': 'Run' },
    'navgroup.produce': { 'zh-CN': '生产', 'en': 'Produce' },

    'shell.brand': { 'zh-CN': 'AI 短剧工坊', 'en': 'AI Drama Factory' },

    'title.index': { 'zh-CN': 'AI 工作区', 'en': 'AI Workspace' },
    'title.chat': { 'zh-CN': 'AI 对话', 'en': 'AI Chat' },
    'title.images': { 'zh-CN': 'AI 图片', 'en': 'AI Images' },
    'title.music': { 'zh-CN': 'AI 音乐', 'en': 'AI Music' },
    'title.mv': { 'zh-CN': 'AI MV', 'en': 'AI MV' },
    'title.avatar': { 'zh-CN': '数字人', 'en': 'Digital Human' },
    'title.runs': { 'zh-CN': '运行列表', 'en': 'Runs' },
    'title.run-detail': { 'zh-CN': '运行详情', 'en': 'Run Detail' },
    'title.agents': { 'zh-CN': 'Agent 机队', 'en': 'Agent Fleet' },
    'title.skills': { 'zh-CN': 'Skill 市场', 'en': 'Skill Marketplace' },
    'title.officialSkills': { 'zh-CN': '官方 Skill 库', 'en': 'Official Skills' },
    'title.skillhub': { 'zh-CN': 'SkillHub', 'en': 'SkillHub' },
    'title.usage': { 'zh-CN': '用量统计', 'en': 'Usage' },
    'title.storyboard': { 'zh-CN': '分镜板', 'en': 'Storyboard' },
    'title.canvas': { 'zh-CN': '分镜画布', 'en': 'Shot Canvas' },
    'title.tasks': { 'zh-CN': '任务队列', 'en': 'Task Queue' },
    'title.finals': { 'zh-CN': '成片库', 'en': 'Final Cuts' },
    'title.pipeline': { 'zh-CN': '生产看板', 'en': 'Production Board' },
    'title.tools': { 'zh-CN': '快捷工具', 'en': 'Quick Tools' },
    'title.settings': { 'zh-CN': '设置', 'en': 'Settings' },
    'title.account': { 'zh-CN': '账号', 'en': 'Account' },
    'title.qc': { 'zh-CN': '成片质检', 'en': 'QC Review' },
    'title.review': { 'zh-CN': '审核队列', 'en': 'Review Queue' },
    'nav.review': { 'zh-CN': '审核队列', 'en': 'Review Queue' },
    'nav.deconstruct': { 'zh-CN': '视频拆解', 'en': 'Video Deconstruction' },

    'pal.pages': { 'zh-CN': '页面', 'en': 'Pages' },
    'pal.actions': { 'zh-CN': '操作', 'en': 'Actions' },
    'pal.placeholder': { 'zh-CN': '输入命令或搜索页面…', 'en': 'Type a command or search pages…' },
    'pal.empty': { 'zh-CN': '没有匹配的命令', 'en': 'No matching commands' },
    'pal.go': { 'zh-CN': '前往', 'en': 'Go to' },

    'pal.act.newShot': { 'zh-CN': '新建分镜', 'en': 'New shot' },
    'pal.act.fromScript': { 'zh-CN': '从剧本生成分镜', 'en': 'Generate shots from script' },
    'pal.act.submitAll': { 'zh-CN': '提交本集全部任务', 'en': 'Submit all tasks of this episode' },
    'pal.act.genFinal': { 'zh-CN': '生成成片', 'en': 'Generate final cut' },
    'pal.act.openChat': { 'zh-CN': '打开 AI 对话', 'en': 'Open AI chat' },
    'pal.act.newRun': { 'zh-CN': '新建运行', 'en': 'New run' },

    'shell.theme': { 'zh-CN': '切换亮色/深色', 'en': 'Toggle color theme' },
    'shell.collapse': { 'zh-CN': '折叠侧边栏', 'en': 'Collapse sidebar' },
    'shell.expand': { 'zh-CN': '展开侧边栏', 'en': 'Expand sidebar' },
    'shell.lang': { 'zh-CN': '语言', 'en': 'Language' }
  };

  if (window.DFI18N) DFI18N.register(SHELL_I18N);

  function T(key, fallback) {
    if (window.DFI18N && typeof DFI18N.tr === 'function') {
      var v = DFI18N.tr(key);
      if (v && v !== key) return v;
    }
    return fallback != null ? fallback : key;
  }

  /* ---- 账号鉴权守卫：非游客页先验登录，未登录跳 login.html ----
     auth.js 动态注入（各页无需改 script 引入）；login/register/oauth-callback 为游客页。 */
  (function authGuard() {
    var p = window.location.pathname;
    var guests = ['/login.html', '/register.html', '/oauth-callback.html'];
    for (var i = 0; i < guests.length; i++) {
      if (p === guests[i]) return;
    }
    var s = document.createElement('script');
    s.src = '/auth.js';
    s.onload = function () {
      if (window.Auth && typeof window.Auth.requireAuth === 'function') window.Auth.requireAuth();
    };
    document.head.appendChild(s);
  })();

  /* ---- 品牌 Logo：场记板 + 播放三角（SVG mark，随主题 currentColor） ---- */
  var LOGO_MARK = '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="4" y="10" width="24" height="18" rx="2"/>' +
    '<line x1="4" y1="16" x2="28" y2="16"/>' +
    '<line x1="9" y1="4" x2="12" y2="10"/>' +
    '<line x1="15" y1="4" x2="18" y2="10"/>' +
    '<line x1="21" y1="4" x2="24" y2="10"/>' +
    '<polygon points="14,20 14,26 20,23" fill="currentColor" stroke="none"/></svg>';

  /* ---- 图标：Lucide（/vendor/lucide.min.js 本地包），名称映射 ---- */
  var ICONS = {
    home: 'home', chat: 'message-circle', film: 'clapperboard', tasks: 'list-checks',
    check: 'badge-check', chart: 'bar-chart-3', search: 'search', plus: 'plus',
    send: 'send', spark: 'sparkles', sun: 'sun', moon: 'moon',
    runs: 'rocket', 'run-detail': 'rocket', agents: 'bot', settings: 'settings',
    images: 'image', music: 'music', avatar: 'scan-face', user: 'user',
    layout: 'layout-grid', skills: 'puzzle', tools: 'wrench', review: 'clipboard-check', prompts: 'file-text',
  };

  function iconHtml(name) {
    return '<i data-lucide="' + (ICONS[name] || 'circle') + '" class="nav-icon"></i>';
  }

  /* Lucide 按需加载（老页面未引入时动态注入），加载后刷新图标 */
  function ensureLucide(cb) {
    if (window.lucide && window.lucide.createIcons) { cb(); return; }
    var s = document.createElement('script');
    s.src = '/vendor/lucide.min.js';
    s.onload = function () { cb(); };
    s.onerror = function () { cb(); };
    document.head.appendChild(s);
  }
  function refreshIcons() {
    if (window.lucide && window.lucide.createIcons) { window.lucide.createIcons(); }
  }

  /* ---- 主题切换：深色显示太阳（点按切亮色），亮色显示月亮（点按切深色） ---- */
  function renderThemeIcon() {
    var btn = document.getElementById('themeToggle');
    if (!btn) return;
    var t = document.documentElement.getAttribute('data-bs-theme');
    btn.innerHTML = (t === 'dark') ? iconHtml('sun') : iconHtml('moon');
    refreshIcons();
  }

  var NAV = [
    { id: 'index', href: '/index.html', label: 'AI 工作区', i18n: 'nav.index', icon: 'home', kbd: 'G H' },
    { id: 'chat', href: '/chat.html', label: 'AI 对话', i18n: 'nav.chat', icon: 'chat', kbd: 'G C' },
    { id: 'images', href: '/images.html', label: 'AI 图片', i18n: 'nav.images', icon: 'images' },
    { id: 'music', href: '/music.html', label: 'AI 音乐', i18n: 'nav.music', icon: 'music' },
    { id: 'mv', href: '/mv.html', label: 'AI MV', i18n: 'nav.mv', icon: 'film' },
    { id: 'avatar', href: '/avatar.html', label: '数字人', i18n: 'nav.avatar', icon: 'avatar' },
    { id: 'runs', href: '/runs.html', label: '运行列表', i18n: 'nav.runs', icon: 'runs', kbd: 'G R' },
    { id: 'agents', href: '/agents.html', label: 'Agent 机队', i18n: 'nav.agents', icon: 'agents' },
    { id: 'skills', href: '/skills.html', label: 'Skill 市场', i18n: 'nav.skills', icon: 'skills' },
    { id: 'official-skills', href: '/official-skills.html', label: '官方 Skill 库', i18n: 'nav.officialSkills', icon: 'skills' },
    { id: 'prompts', href: '/prompts.html', label: '提示词库', i18n: 'nav.prompts', icon: 'prompts' },
    { id: 'skillhub', href: '/skillhub.html', label: 'SkillHub', i18n: 'nav.skillhub', icon: 'skills' },
    { id: 'usage', href: '/usage.html', label: '用量统计', i18n: 'nav.usage', icon: 'chart' },
    { id: 'cost-ledger', href: '/cost-ledger.html', label: '成本账本', i18n: 'nav.costLedger', icon: 'chart' },
    { id: 'storyboard', href: '/storyboard.html', label: '分镜板', i18n: 'nav.storyboard', icon: 'film', kbd: 'G S' },
    { id: 'canvas', href: '/canvas.html', label: '分镜画布', i18n: 'nav.canvas', icon: 'layout' },
    { id: 'tasks', href: '/tasks.html', label: '任务队列', i18n: 'nav.tasks', icon: 'tasks', kbd: 'G T' },
    { id: 'finals', href: '/finals.html', label: '成片库', i18n: 'nav.finals', icon: 'check', kbd: 'G F' },
    { id: 'review', href: '/review.html', label: '审核队列', i18n: 'nav.review', icon: 'review' },
    { id: 'deconstruct', href: '/deconstruct.html', label: '视频拆解', i18n: 'nav.deconstruct', icon: 'search' },
    { id: 'pipeline', href: '/pipeline.html', label: '生产看板', i18n: 'nav.pipeline', icon: 'chart', kbd: 'G P' },
    { id: 'tools', href: '/tools.html', label: '快捷工具', i18n: 'nav.tools', icon: 'tools' },
    { id: 'settings', href: '/settings.html', label: '设置', i18n: 'nav.settings', icon: 'settings' },
    { id: 'account', href: '/account.html', label: '账号', i18n: 'nav.account', icon: 'user' }
  ];

  /* 侧边栏分组 */
  var NAV_GROUPS = [
    { i18n: 'navgroup.create', label: '创作', ids: ['index', 'chat', 'images', 'music', 'mv', 'avatar'] },
    { i18n: 'navgroup.run', label: '运行', ids: ['runs', 'agents', 'skills', 'official-skills', 'prompts', 'skillhub', 'usage', 'cost-ledger'] },
    { i18n: 'navgroup.produce', label: '生产', ids: ['storyboard', 'canvas', 'tasks', 'finals', 'review', 'deconstruct', 'pipeline', 'tools'] }
  ];
  function navById(id) {
    for (var i = 0; i < NAV.length; i++) { if (NAV[i].id === id) return NAV[i]; }
    return null;
  }

  function currentId() {
    var p = window.location.pathname;
    for (var i = 0; i < NAV.length; i++) {
      if (p.endsWith('/' + NAV[i].id + '.html') || p === NAV[i].href) return NAV[i].id;
    }
    if (p.endsWith('/qc.html')) return 'qc';
    if (p.endsWith('/run-detail.html')) return 'runs';
    return 'index';
  }

  function isMac() {
    return /Mac|iPhone|iPad/.test(navigator.platform || '');
  }
  function modK() {
    return isMac() ? '⌘K' : 'Ctrl+K';
  }

  /* ---- 构建应用壳 ---- */
  function buildShell() {
    var body = document.body;
    if (!body || document.getElementById('sidebar')) return;

    var cur = currentId();

    /* 侧边栏 */
    var aside = document.createElement('aside');
    aside.className = 'sidebar';
    aside.id = 'sidebar';
    aside.innerHTML =
      '<div class="sidebar-brand"><span class="logo-mark">' + LOGO_MARK + '</span><span data-i18n="shell.brand">AI 短剧工坊</span></div>' +
      navGroupsHtml(cur) +
      '<div class="sidebar-footer">' +
        '<a class="sidebar-link' + (cur === 'settings' ? ' active' : '') + '" href="/settings.html">' + iconHtml('settings') + '<span data-i18n="nav.settings">设置</span></a>' +
        '<a class="sidebar-link' + (cur === 'account' ? ' active' : '') + '" href="/account.html">' + iconHtml('user') + '<span data-i18n="nav.account">账号</span></a>' +
        '<button id="themeToggle" class="theme-toggle" title="' + T('shell.theme', '切换亮色/深色') + '" data-i18n-title="shell.theme" aria-label="' + T('shell.theme', '切换亮色/深色') + '"></button>' +
        '<button id="sbToggle" class="theme-toggle" title="' + T('shell.collapse', '折叠侧边栏') + '" data-i18n-title="shell.collapse" aria-label="' + T('shell.collapse', '折叠侧边栏') + '"></button>' +
      '</div>';

    /* 侧边栏折叠：localStorage 持久化（df-sb），body.sb-collapsed 驱动 CSS */
    (function () {
      var sbVal = '0';
      try { sbVal = localStorage.getItem('df-sb') || '0'; } catch (e) {}
      if (sbVal === '1') document.body.classList.add('sb-collapsed');
      function applySb() {
        var collapsed = document.body.classList.contains('sb-collapsed');
        var links = aside.querySelectorAll('.sidebar-link');
        for (var i = 0; i < links.length; i++) {
          var span = links[i].querySelector('span');
          if (!span) continue;
          if (collapsed) links[i].setAttribute('title', span.textContent);
          else links[i].removeAttribute('title');
        }
        var btn = aside.querySelector('#sbToggle');
        if (btn) {
          btn.innerHTML = '<i data-lucide="' + (collapsed ? 'panel-left-open' : 'panel-left-close') + '" class="nav-icon"></i>';
          btn.setAttribute('title', collapsed ? T('shell.expand', '展开侧边栏') : T('shell.collapse', '折叠侧边栏'));
          btn.setAttribute('aria-label', collapsed ? T('shell.expand', '展开侧边栏') : T('shell.collapse', '折叠侧边栏'));
          if (window.lucide && lucide.createIcons) lucide.createIcons();
        }
      }
      var tgl = aside.querySelector('#sbToggle');
      if (tgl) tgl.addEventListener('click', function () {
        var next = document.body.classList.toggle('sb-collapsed');
        try { localStorage.setItem('df-sb', next ? '1' : '0'); } catch (e) {}
        applySb();
      });
      applySb();
    })();

    /* 主列 */
    var main = document.createElement('div');
    main.className = 'app-main';

    var topbar = document.createElement('header');
    topbar.className = 'topbar';
    topbar.innerHTML =
      '<span class="topbar-title" data-i18n="' + pageTitleKey(cur) + '">' + pageTitle(cur) + '</span>' +
      '<div class="lang-switch" role="group" aria-label="' + T('shell.lang', '语言') + '">' +
        '<button type="button" data-lang="zh-CN">中文</button>' +
        '<button type="button" data-lang="en">EN</button>' +
      '</div>';

    var content = document.createElement('main');
    content.className = 'app-content';
    content.id = 'appContent';

    /* 把 body 现有节点搬进 content（保留脚本执行顺序） */
    var nodes = Array.prototype.slice.call(body.childNodes);
    var app = document.createElement('div');
    app.className = 'app';
    body.innerHTML = '';
    body.appendChild(app);
    app.appendChild(aside);
    app.appendChild(main);
    main.appendChild(topbar);
    main.appendChild(content);
    nodes.forEach(function (n) {
      /* 脚本保留在 body 末尾，避免重复执行 */
      if (n.nodeName === 'SCRIPT') { body.appendChild(n); }
      else { content.appendChild(n); }
    });

    /* 主题切换：翻转 data-bs-theme 并持久化到 localStorage */
    var themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
      themeToggle.onclick = function () {
        var next = (document.documentElement.getAttribute('data-bs-theme') === 'dark') ? 'light' : 'dark';
        document.documentElement.setAttribute('data-bs-theme', next);
        try { localStorage.setItem('df-theme', next); } catch (e) {}
        renderThemeIcon();
      };
    }
    renderThemeIcon();
    ensureLucide(refreshIcons);

    /* 语言切换器：点击调 DFI18N.setLang；失败仅 console.error */
    var langBtns = topbar.querySelectorAll('.lang-switch button');
    for (var lb = 0; lb < langBtns.length; lb++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var next = btn.getAttribute('data-lang') === 'en' ? 'en' : 'zh-CN';
          if (!window.DFI18N) return;
          DFI18N.setLang(next).then(function () {
            syncLangSwitch();
          }).catch(function (e) {
            console.error('setLang failed', e);
          });
        });
      })(langBtns[lb]);
    }
    syncLangSwitch();

    if (window.DFI18N) {
      DFI18N.applyI18n(document);
      DFI18N.onLangChange(function () {
        DFI18N.applyI18n(document);
        syncLangSwitch();
      });
    }
  }

  /* 语言切换器：给当前语言按钮加 .active */
  function syncLangSwitch() {
    var btns = document.querySelectorAll('.lang-switch button');
    var cur = window.DFI18N ? DFI18N.getLang() : 'zh-CN';
    for (var i = 0; i < btns.length; i++) {
      var v = btns[i].getAttribute('data-lang') === 'en' ? 'en' : 'zh-CN';
      if (v === cur) btns[i].classList.add('active');
      else btns[i].classList.remove('active');
    }
  }

  function navLink(n, cur) {
    if (!n) return '';
    return '<a class="sidebar-link' + (n.id === cur ? ' active' : '') + '" href="' + n.href + '">' +
      iconHtml(n.icon) + '<span data-i18n="' + n.i18n + '">' + n.label + '</span></a>';
  }

  function navGroupsHtml(cur) {
    var html = '';
    for (var g = 0; g < NAV_GROUPS.length; g++) {
      html += '<div class="sidebar-label" data-i18n="' + NAV_GROUPS[g].i18n + '">' + NAV_GROUPS[g].label + '</div><nav class="sidebar-nav">';
      for (var i = 0; i < NAV_GROUPS[g].ids.length; i++) {
        html += navLink(navById(NAV_GROUPS[g].ids[i]), cur);
      }
      html += '</nav>';
    }
    return html;
  }

  function pageTitleKey(id) {
    if (window.location.pathname.endsWith('/run-detail.html')) return 'title.run-detail';
    var titles = {
      index: 'title.index', chat: 'title.chat', storyboard: 'title.storyboard',
      canvas: 'title.canvas',
      tasks: 'title.tasks', finals: 'title.finals', pipeline: 'title.pipeline',
      runs: 'title.runs', 'run-detail': 'title.run-detail', agents: 'title.agents', skills: 'title.skills', 'official-skills': 'title.officialSkills', prompts: 'title.prompts', skillhub: 'title.skillhub', usage: 'title.usage', settings: 'title.settings',
      images: 'title.images', music: 'title.music', avatar: 'title.avatar',
      qc: 'title.qc',
      mv: 'title.mv', tools: 'title.tools', account: 'title.account'
    };
    return titles[id] || 'shell.brand';
  }

  function pageTitle(id) {
    var titles = {
      index: 'AI 工作区', chat: 'AI 对话', storyboard: '分镜板',
      canvas: '分镜画布',
      tasks: '任务队列', finals: '成片库', pipeline: '生产看板',
      runs: '运行列表', 'run-detail': '运行详情', agents: 'Agent 机队', skills: 'Skill 市场', 'official-skills': '官方 Skill 库', prompts: '提示词库', skillhub: 'SkillHub', usage: '用量统计', settings: '设置',
      images: 'AI 图片', music: 'AI 音乐', avatar: '数字人',
      qc: '成片质检',
      mv: 'AI MV', tools: '快捷工具', account: '账号'
    };
    if (window.location.pathname.endsWith('/run-detail.html')) return '运行详情';
    return titles[id] || 'AI 短剧工坊';
  }

  /* ---- 命令面板 ---- */
  var paletteEl = null;
  var selectedIdx = 0;

  function paletteItems() {
    return [
      { group: T('pal.pages', '页面'), groupKey: 'pal.pages', items: NAV.map(function (n) {
        var label = window.DFI18N ? (T('pal.go', '前往') + T(n.i18n, n.label)) : ('前往' + n.label);
        return { label: label, hint: window.DFI18N ? T(n.i18n, n.label) : n.label, icon: n.icon, kbd: n.kbd, run: function () { location.href = n.href; } };
      }) },
      { group: T('pal.actions', '操作'), groupKey: 'pal.actions', items: [
        { label: T('pal.act.newShot', '新建分镜'), hint: T('nav.storyboard', '分镜板'), icon: 'plus', kbd: '1', run: function () { location.href = '/storyboard.html#act=new-shot'; } },
        { label: T('pal.act.fromScript', '从剧本生成分镜'), hint: T('nav.storyboard', '分镜板'), icon: 'spark', kbd: '2', run: function () { location.href = '/storyboard.html#act=from-script'; } },
        { label: T('pal.act.submitAll', '提交本集全部任务'), hint: T('nav.storyboard', '分镜板'), icon: 'send', kbd: '3', run: function () { location.href = '/storyboard.html#act=submit-all'; } },
        { label: T('pal.act.genFinal', '生成成片'), hint: T('nav.finals', '成片库'), icon: 'film', kbd: '4', run: function () { location.href = '/finals.html#act=generate'; } },
        { label: T('pal.act.openChat', '打开 AI 对话'), hint: T('nav.chat', 'AI 对话页'), icon: 'chat', kbd: '5', run: function () { location.href = '/chat.html'; } },
        { label: T('pal.act.newRun', '新建运行'), hint: T('nav.runs', '运行列表'), icon: 'runs', kbd: '6', run: function () { location.href = '/runs.html#act=new-run'; } }
      ] }
    ];
  }

  function openPalette() {
    if (paletteEl) { closePalette(); return; }
    selectedIdx = 0;
    paletteEl = document.createElement('div');
    paletteEl.className = 'cmd-overlay';
    paletteEl.id = 'cmdPalette';
    paletteEl.innerHTML =
      '<div class="cmd-panel" role="dialog" aria-label="' + T('pal.placeholder', '输入命令或搜索页面…') + '">' +
        '<div class="cmd-input-row">' + ICONS.search +
          '<input class="cmd-input" id="cmdInput" placeholder="' + T('pal.placeholder', '输入命令或搜索页面…') + '" autocomplete="off">' +
          '<span class="kbd">ESC</span>' +
        '</div>' +
        '<div class="cmd-list" id="cmdList"></div>' +
      '</div>';
    document.body.appendChild(paletteEl);
    paletteEl.addEventListener('click', function (e) {
      if (e.target === paletteEl) closePalette();
    });
    document.getElementById('cmdInput').addEventListener('input', renderPalette);
    document.getElementById('cmdInput').addEventListener('keydown', paletteKey);
    renderPalette();
    setTimeout(function () { document.getElementById('cmdInput').focus(); }, 30);
  }

  function closePalette() {
    if (paletteEl && paletteEl.parentNode) paletteEl.parentNode.removeChild(paletteEl);
    paletteEl = null;
  }

  function flatItems(filter) {
    var out = [];
    paletteItems().forEach(function (g) {
      g.items.forEach(function (it) {
        it.group = g.group;
        if (!filter || (it.label + it.hint).toLowerCase().indexOf(filter.toLowerCase()) >= 0) out.push(it);
      });
    });
    return out;
  }

  var currentFlat = [];
  function renderPalette() {
    var q = document.getElementById('cmdInput').value.trim();
    currentFlat = flatItems(q);
    selectedIdx = Math.min(selectedIdx, Math.max(0, currentFlat.length - 1));
    var list = document.getElementById('cmdList');
    if (!currentFlat.length) {
      list.innerHTML = '<div class="cmd-empty">' + T('pal.empty', '没有匹配的命令') + '</div>';
      return;
    }
    var html = '';
    var lastGroup = null;
    currentFlat.forEach(function (it, i) {
      if (it.group !== lastGroup) {
        html += '<div class="cmd-group-label">' + it.group + '</div>';
        lastGroup = it.group;
      }
      html += '<button class="cmd-item' + (i === selectedIdx ? ' selected' : '') + '" data-i="' + i + '">' +
        '<span>' + it.label + '</span>' +
        '<span class="cmd-hint">' + (it.hint || '') + '</span>' +
        (it.kbd ? '<span class="kbd">' + it.kbd + '</span>' : '') + '</button>';
    });
    list.innerHTML = html;
    list.querySelectorAll('.cmd-item').forEach(function (el) {
      el.addEventListener('click', function () {
        var it = currentFlat[Number(el.getAttribute('data-i'))];
        closePalette();
        if (it) it.run();
      });
      el.addEventListener('mousemove', function () {
        selectedIdx = Number(el.getAttribute('data-i'));
        renderPalette();
      });
    });
    var sel = list.querySelector('.cmd-item.selected');
    if (sel) sel.scrollIntoView({ block: 'nearest' });
  }

  function paletteKey(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); selectedIdx = Math.min(selectedIdx + 1, currentFlat.length - 1); renderPalette(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); selectedIdx = Math.max(selectedIdx - 1, 0); renderPalette(); }
    else if (/^[1-6]$/.test(e.key) && document.getElementById('cmdInput').value.trim() === '') {
      e.preventDefault();
      var actionsGroup = T('pal.actions', '操作');
      var ops = currentFlat.filter(function (x) { return x.group === actionsGroup; });
      var op = ops[Number(e.key) - 1];
      closePalette();
      if (op) op.run();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      var it = currentFlat[selectedIdx];
      closePalette();
      if (it) it.run();
    } else if (e.key === 'Escape') { closePalette(); }
  }

  /* ---- 全局快捷键 ---- */
  document.addEventListener('keydown', function (e) {
    var mod = isMac() ? e.metaKey : e.ctrlKey;
    if (mod && (e.key === 'k' || e.key === 'K')) {
      var tag = (document.activeElement && document.activeElement.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      e.preventDefault();
      openPalette();
    } else if (e.key === 'Escape' && paletteEl) {
      closePalette();
    }
    /* G + 字母：页面跳转 */
    if (!mod && !e.altKey && (e.key === 'g' || e.key === 'G')) {
      var tag2 = (document.activeElement && document.activeElement.tagName) || '';
      if (tag2 === 'INPUT' || tag2 === 'TEXTAREA') return;
      window._gPending = true;
      setTimeout(function () { window._gPending = false; }, 800);
      return;
    }
    if (window._gPending && !mod) {
      var k = (e.key || '').toUpperCase();
      var map = { H: 'index', C: 'chat', S: 'storyboard', T: 'tasks', F: 'finals', P: 'pipeline' };
      if (map[k]) {
        window._gPending = false;
        var tag3 = (document.activeElement && document.activeElement.tagName) || '';
        if (tag3 === 'INPUT' || tag3 === 'TEXTAREA') return;
        location.href = '/' + map[k] + '.html';
      }
    }
  });

  /* ---- 页面动作（URL hash 触发，供命令面板调用） ---- */
  function handleHashAction() {
    var h = window.location.hash || '';
    if (h.indexOf('#act=') !== 0) return;
    var act = h.slice(5);
    window.location.hash = '';
    setTimeout(function () {
      if (act === 'new-shot') {
        var b = document.getElementById('addBtn');
        if (b) b.click();
      } else if (act === 'from-script') {
        if (typeof openScriptModal === 'function') openScriptModal();
        else { var b2 = document.getElementById('fromScriptBtn'); if (b2) b2.click(); }
      } else if (act === 'submit-all') {
        if (typeof submitAll === 'function') submitAll();
      } else if (act === 'generate') {
        if (typeof generateFinalCut === 'function') generateFinalCut();
      }
    }, 600);
  }

  /* ---- 启动 ---- */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { buildShell(); handleHashAction(); });
  } else {
    buildShell();
    handleHashAction();
  }
})();
