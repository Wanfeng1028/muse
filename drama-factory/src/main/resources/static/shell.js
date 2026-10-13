/* ==========================================================================
   shell.js —— drama-factory 应用壳（v5.1）
   注入左侧窄导航栏 + 顶部全局搜索条 + ⌘K 命令面板，统一 7 页视觉语言。
   约定：各页保留原有内容区；原 header.navbar 由 CSS 隐藏。
   ========================================================================== */
(function () {
  'use strict';

  /* ---- 内联 SVG 图标（线性，1.7px 描边，无 emoji） ---- */
  var ICONS = {
    home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/></svg>',
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/></svg>',
    film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14M17 5v14M3 10h4M3 14h4M17 10h4M17 14h4"/></svg>',
    tasks: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="m3.5 5 1 1 2-2M3.5 11l1 1 2-2M3.5 17l1 1 2-2"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="m8.5 12.5 2.5 2.5 5-5.5"/></svg>',
    chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10M10 20V4M16 20v-8M21 20H3"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m4 11 16-7-7 16-2.5-6.5L4 11z"/></svg>',
    spark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/></svg>'
  };

  var NAV = [
    { id: 'index', href: '/index.html', label: 'AI 工作区', icon: 'home', kbd: 'G H' },
    { id: 'chat', href: '/chat.html', label: 'AI 对话', icon: 'chat', kbd: 'G C' },
    { id: 'storyboard', href: '/storyboard.html', label: '分镜板', icon: 'film', kbd: 'G S' },
    { id: 'tasks', href: '/tasks.html', label: '任务队列', icon: 'tasks', kbd: 'G T' },
    { id: 'finals', href: '/finals.html', label: '成片库', icon: 'check', kbd: 'G F' },
    { id: 'pipeline', href: '/pipeline.html', label: '生产看板', icon: 'chart', kbd: 'G P' }
  ];

  function currentId() {
    var p = window.location.pathname;
    for (var i = 0; i < NAV.length; i++) {
      if (p.endsWith('/' + NAV[i].id + '.html') || p === NAV[i].href) return NAV[i].id;
    }
    if (p.endsWith('/qc.html')) return 'finals';
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
      '<div class="sidebar-brand"><span class="mark">剧</span><span>AI 短剧工坊</span></div>' +
      '<div class="sidebar-label">创作</div>' +
      '<nav class="sidebar-nav">' +
        navLink(NAV[0], cur) + navLink(NAV[1], cur) +
      '</nav>' +
      '<div class="sidebar-label">生产</div>' +
      '<nav class="sidebar-nav">' +
        navLink(NAV[2], cur) + navLink(NAV[3], cur) + navLink(NAV[4], cur) + navLink(NAV[5], cur) +
      '</nav>';

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
  }

  function navLink(n, cur) {
    return '<a class="sidebar-link' + (n.id === cur ? ' active' : '') + '" href="' + n.href + '">' +
      ICONS[n.icon] + '<span>' + n.label + '</span></a>';
  }

  function pageTitle(id) {
    var titles = {
      index: 'AI 工作区', chat: 'AI 对话', storyboard: '分镜板',
      tasks: '任务队列', finals: '成片库', pipeline: '生产看板'
    };
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
        { label: '新建分镜', hint: '分镜板', icon: 'plus', run: function () { location.href = '/storyboard.html#act=new-shot'; } },
        { label: '从剧本生成分镜', hint: '分镜板', icon: 'spark', run: function () { location.href = '/storyboard.html#act=from-script'; } },
        { label: '提交本集全部任务', hint: '分镜板', icon: 'send', run: function () { location.href = '/storyboard.html#act=submit-all'; } },
        { label: '生成成片', hint: '成片库', icon: 'film', run: function () { location.href = '/finals.html#act=generate'; } },
        { label: '打开 AI 对话', hint: '工作区', icon: 'chat', kbd: modK(), run: function () { location.href = '/chat.html'; } }
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
    else if (e.key === 'Enter') {
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
