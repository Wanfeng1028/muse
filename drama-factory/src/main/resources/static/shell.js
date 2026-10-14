/* ==========================================================================
   shell.js —— drama-factory 应用壳（v5.1）
   注入左侧窄导航栏 + 顶部全局搜索条 + ⌘K 命令面板，统一 7 页视觉语言。
   约定：各页保留原有内容区；原 header.navbar 由 CSS 隐藏。
   ========================================================================== */
(function () {
  'use strict';

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
    layout: 'layout-grid', tools: 'wrench',
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
    { id: 'index', href: '/index.html', label: 'AI 工作区', icon: 'home', kbd: 'G H' },
    { id: 'chat', href: '/chat.html', label: 'AI 对话', icon: 'chat', kbd: 'G C' },
    { id: 'images', href: '/images.html', label: 'AI 图片', icon: 'images' },
    { id: 'music', href: '/music.html', label: 'AI 音乐', icon: 'music' },
    { id: 'mv', href: '/mv.html', label: 'AI MV', icon: 'film' },
    { id: 'avatar', href: '/avatar.html', label: '数字人', icon: 'avatar' },
    { id: 'runs', href: '/runs.html', label: '运行列表', icon: 'runs', kbd: 'G R' },
    { id: 'agents', href: '/agents.html', label: 'Agent 机队', icon: 'agents' },
    { id: 'usage', href: '/usage.html', label: '用量统计', icon: 'chart' },
    { id: 'storyboard', href: '/storyboard.html', label: '分镜板', icon: 'film', kbd: 'G S' },
    { id: 'canvas', href: '/canvas.html', label: '分镜画布', icon: 'layout' },
    { id: 'tasks', href: '/tasks.html', label: '任务队列', icon: 'tasks', kbd: 'G T' },
    { id: 'finals', href: '/finals.html', label: '成片库', icon: 'check', kbd: 'G F' },
    { id: 'pipeline', href: '/pipeline.html', label: '生产看板', icon: 'chart', kbd: 'G P' },
    { id: 'tools', href: '/tools.html', label: '快捷工具', icon: 'tools' },
    { id: 'settings', href: '/settings.html', label: '设置', icon: 'settings' },
    { id: 'account', href: '/account.html', label: '账号', icon: 'user' }
  ];

  /* 侧边栏分组 */
  var NAV_GROUPS = [
    { label: '创作', ids: ['index', 'chat', 'images', 'music', 'mv', 'avatar'] },
    { label: '运行', ids: ['runs', 'agents', 'usage'] },
    { label: '生产', ids: ['storyboard', 'canvas', 'tasks', 'finals', 'pipeline', 'tools'] }
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
      '<div class="sidebar-brand"><span class="logo-mark">' + LOGO_MARK + '</span><span>AI 短剧工坊</span></div>' +
      navGroupsHtml(cur) +
      '<div class="sidebar-footer">' +
        '<a class="sidebar-link' + (cur === 'settings' ? ' active' : '') + '" href="/settings.html">' + iconHtml('settings') + '<span>设置</span></a>' +
        '<a class="sidebar-link' + (cur === 'account' ? ' active' : '') + '" href="/account.html">' + iconHtml('user') + '<span>账号</span></a>' +
        '<button id="themeToggle" class="theme-toggle" title="切换亮色/深色" aria-label="切换主题"></button>' +
        '<button id="sbToggle" class="theme-toggle" title="折叠侧边栏" aria-label="折叠侧边栏"></button>' +
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
          btn.setAttribute('title', collapsed ? '展开侧边栏' : '折叠侧边栏');
          btn.setAttribute('aria-label', collapsed ? '展开侧边栏' : '折叠侧边栏');
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
      '<span class="topbar-title">' + pageTitle(cur) + '</span>';

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
  }

  function navLink(n, cur) {
    if (!n) return '';
    return '<a class="sidebar-link' + (n.id === cur ? ' active' : '') + '" href="' + n.href + '">' +
      iconHtml(n.icon) + '<span>' + n.label + '</span></a>';
  }

  function navGroupsHtml(cur) {
    var html = '';
    for (var g = 0; g < NAV_GROUPS.length; g++) {
      html += '<div class="sidebar-label">' + NAV_GROUPS[g].label + '</div><nav class="sidebar-nav">';
      for (var i = 0; i < NAV_GROUPS[g].ids.length; i++) {
        html += navLink(navById(NAV_GROUPS[g].ids[i]), cur);
      }
      html += '</nav>';
    }
    return html;
  }

  function pageTitle(id) {
    var titles = {
      index: 'AI 工作区', chat: 'AI 对话', storyboard: '分镜板',
      canvas: '分镜画布',
      tasks: '任务队列', finals: '成片库', pipeline: '生产看板',
      runs: '运行列表', 'run-detail': '运行详情', agents: 'Agent 机队', usage: '用量统计', settings: '设置',
      images: 'AI 图片', music: 'AI 音乐', avatar: '数字人',
      qc: '成片质检'
    };
    if (window.location.pathname.endsWith('/run-detail.html')) return '运行详情';
    return titles[id] || 'AI 短剧工坊';
  }

  /* ---- 命令面板 ---- */
  var paletteEl = null;
  var selectedIdx = 0;

  function paletteItems() {
    return [
      { group: '页面', items: NAV.map(function (n) {
        return { label: '前往' + n.label, hint: n.label, icon: n.icon, kbd: n.kbd, run: function () { location.href = n.href; } };
      }) },
      { group: '操作', items: [
        { label: '新建分镜', hint: '分镜板', icon: 'plus', kbd: '1', run: function () { location.href = '/storyboard.html#act=new-shot'; } },
        { label: '从剧本生成分镜', hint: '分镜板', icon: 'spark', kbd: '2', run: function () { location.href = '/storyboard.html#act=from-script'; } },
        { label: '提交本集全部任务', hint: '分镜板', icon: 'send', kbd: '3', run: function () { location.href = '/storyboard.html#act=submit-all'; } },
        { label: '生成成片', hint: '成片库', icon: 'film', kbd: '4', run: function () { location.href = '/finals.html#act=generate'; } },
        { label: '打开 AI 对话', hint: 'AI 对话页', icon: 'chat', kbd: '5', run: function () { location.href = '/chat.html'; } },
        { label: '新建运行', hint: '运行列表', icon: 'runs', kbd: '6', run: function () { location.href = '/runs.html#act=new-run'; } }
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
      '<div class="cmd-panel" role="dialog" aria-label="命令面板">' +
        '<div class="cmd-input-row">' + ICONS.search +
          '<input class="cmd-input" id="cmdInput" placeholder="输入命令或搜索页面…" autocomplete="off">' +
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
      list.innerHTML = '<div class="cmd-empty">没有匹配的命令</div>';
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
      var ops = currentFlat.filter(function (x) { return x.group === '操作'; });
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
