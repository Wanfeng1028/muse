// mini-os 前端主逻辑（原生 JS，无框架）
// 全局状态
const state = {
  windows: [],
  zTop: 10,
  fsCache: {},
};

// 统一的 fetch JSON 封装
async function api(path, opts) {
  const options = Object.assign({ headers: {} }, opts || {});
  if (options.body && !options.headers['Content-Type']) {
    options.headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(path, options);
  if (res.status === 204) return null;
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  if (!res.ok) {
    if (res.status === 401) { location.replace('/login.html'); throw new Error('未登录'); }
    const msg = data && data.error ? data.error : ('HTTP ' + res.status);
    throw new Error(msg);
  }
  return data;
}

// 桌面图标与应用定义
let appsRegistry = [];

// 初始化
async function init() {
  // v1.3 登录门卫：未登录跳登录页
  const me = await api('/api/me').catch(() => null);
  if (!me) { location.replace('/login.html'); return; }
  state.currentUser = me;
  try {
    appsRegistry = await api('/api/apps');
  } catch (e) {
    appsRegistry = [];
    console.error('加载应用列表失败', e);
  }
  renderDesktopIcons(appsRegistry);
  renderWidgets();

  // 应用设置
  try {
    const settings = await api('/api/settings');
    applyTheme(settings.theme || 'light');
    applyWallpaper(settings.wallpaper || 'ocean');
  } catch (e) {
    console.error('加载设置失败', e);
    applyTheme('light');
    applyWallpaper('ocean');
  }

  // 时钟
  updateClock();
  setInterval(updateClock, 1000);

  // v1.3 当前用户 + 注销
  const userLabel = document.getElementById('user-label');
  if (userLabel && state.currentUser) {
    const roleNameMap = { admin: '管理员', editor: '编辑者', viewer: '只读' };
    const roleName = roleNameMap[state.currentUser.role] || state.currentUser.role;
    userLabel.textContent = state.currentUser.username + '（' + roleName + '）';
  }
  const logoutBtn = document.getElementById('logout-btn');

  if (logoutBtn) logoutBtn.addEventListener('click', async () => {
    try { await api('/api/auth/logout', { method: 'POST' }); } catch (e) {}
    location.replace('/login.html');
  });

  // 开始菜单
  const startBtn = document.getElementById('start-btn');
  const startMenu = document.getElementById('start-menu');
  if (startBtn && startMenu) {
    startBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      startMenu.classList.toggle('hidden');
    });
    document.addEventListener('click', (ev) => {
      if (!startMenu.contains(ev.target) && ev.target !== startBtn) {
        startMenu.classList.add('hidden');
      }
    });
    renderStartMenu();
  }

  // WebSocket
  connectWebSocket();
}

// 渲染桌面图标
function renderDesktopIcons(apps) {
  const grid = document.getElementById('icon-grid');
  if (!grid) return;
  grid.innerHTML = '';
  apps.forEach((app) => {
    const icon = document.createElement('div');
    icon.className = 'desktop-icon';
    icon.dataset.appId = app.id;
    const isSvg = app.icon.indexOf('<svg') === 0;
    icon.innerHTML = `<div class="${isSvg ? 'icon-tile' : 'icon-emoji'}">${app.icon}</div><div class="icon-label">${escapeHtml(app.name)}</div>`;
    icon.addEventListener('dblclick', () => openApp(app.id));
    grid.appendChild(icon);
  });
}

// 渲染开始菜单
function renderStartMenu() {
  const menu = document.getElementById('start-menu');
  if (!menu) return;
  menu.innerHTML = '';
  appsRegistry.forEach((app) => {
    const item = document.createElement('div');
    item.className = 'start-menu-item';
    if (app.icon.indexOf('<svg') === 0) {
      item.innerHTML = `<span class="menu-svg">${app.icon}</span><span>${escapeHtml(app.name)}</span>`;
    } else {
      item.innerHTML = `<span class="menu-emoji">${app.icon}</span><span>${escapeHtml(app.name)}</span>`;
    }
    item.addEventListener('click', () => {
      openApp(app.id);
      menu.classList.add('hidden');
    });
    menu.appendChild(item);
  });
}

// 应用主题
function applyTheme(theme) {
  const desktop = document.getElementById('desktop');
  if (!desktop) return;
  desktop.setAttribute('data-theme', theme);
}

// 应用壁纸
function applyWallpaper(wallpaper) {
  const desktop = document.getElementById('desktop');
  if (!desktop) return;
  if (wallpaper !== 'ocean' && wallpaper !== 'sunset' && wallpaper !== 'forest') {
    wallpaper = 'ocean';
  }
  desktop.classList.remove('wallpaper', 'ocean', 'sunset', 'forest');
  desktop.classList.add('wallpaper', wallpaper);
}

// 更新时钟
function updateClock() {
  const clock = document.getElementById('clock');
  if (!clock) return;
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  clock.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// WebSocket 连接
function connectWebSocket() {
  const statusEl = document.getElementById('ws-status');
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.host}/ws`;
  let ws;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    if (statusEl) statusEl.textContent = 'WS: 连接失败';
    return;
  }
  ws.addEventListener('open', () => {
    if (statusEl) statusEl.textContent = 'WS: 已连接';
  });
  ws.addEventListener('message', (ev) => {
    try {
      const data = JSON.parse(ev.data);
      console.log('[ws]', data);
    } catch (e) {
      console.log('[ws raw]', ev.data);
    }
  });
  ws.addEventListener('close', () => {
    if (statusEl) statusEl.textContent = 'WS: 已断开';
  });
  ws.addEventListener('error', () => {
    if (statusEl) statusEl.textContent = 'WS: 错误';
  });
}

// 打开应用窗口
function openApp(appId) {
  const app = appsRegistry.find((a) => a.id === appId);
  if (!app) return;
  // 若已存在则聚焦
  const existing = state.windows.find((w) => w.appId === appId);
  if (existing) {
    focusWindow(existing);
    return;
  }

  const win = document.createElement('div');
  win.className = 'window';
  win.style.left = (80 + state.windows.length * 30) + 'px';
  win.style.top = (60 + state.windows.length * 30) + 'px';
  win.style.zIndex = ++state.zTop;

  const titlebar = document.createElement('div');
  titlebar.className = 'window-titlebar';
  const title = document.createElement('div');
  title.className = 'window-title';
  if (app.icon.indexOf('<svg') === 0) {
    title.innerHTML = '<span class="title-icon">' + app.icon + '</span><span>' + escapeHtml(app.name) + '</span>';
  } else {
    title.textContent = app.icon + ' ' + app.name;
  }

  const controls = document.createElement('div');
  controls.className = 'window-controls';
  const btnMin = document.createElement('button');
  btnMin.className = 'win-btn win-min';
  btnMin.textContent = '—';
  btnMin.title = '最小化';
  const btnMax = document.createElement('button');
  btnMax.className = 'win-btn win-max';
  btnMax.textContent = '▢';
  btnMax.title = '最大化 / 还原';
  const btnClose = document.createElement('button');
  btnClose.className = 'win-btn win-close';
  btnClose.textContent = '×';
  btnClose.title = '关闭';
  controls.appendChild(btnMin);
  controls.appendChild(btnMax);
  controls.appendChild(btnClose);
  titlebar.appendChild(title);
  titlebar.appendChild(controls);

  const body = document.createElement('div');
  body.className = 'window-body';

  win.appendChild(titlebar);
  win.appendChild(body);

  document.getElementById('desktop').appendChild(win);

  const winObj = { appId, el: win, body };
  state.windows.push(winObj);

  // 关闭
  btnClose.addEventListener('click', (ev) => {
    ev.stopPropagation();
    closeWindow(winObj);
  });
  // 最小化
  btnMin.addEventListener('click', (ev) => {
    ev.stopPropagation();
    win.classList.toggle('minimized');
  });

  // 聚焦
  win.addEventListener('mousedown', () => focusWindow(winObj));

  // 拖拽
  makeDraggable(win, titlebar, winObj);

  // 最大化 / 还原（双击标题栏同样触发）
  function toggleMaximize() {
    if (win.classList.contains('maximized')) {
      win.classList.remove('maximized');
      const g = winObj.savedGeom;
      if (g) {
        win.style.left = g.left;
        win.style.top = g.top;
        win.style.width = g.width;
        win.style.height = g.height;
      }
    } else {
      winObj.savedGeom = {
        left: win.style.left,
        top: win.style.top,
        width: win.style.width,
        height: win.style.height,
      };
      win.classList.add('maximized');
    }
    // xterm 终端窗口需要重算列数
    win.dispatchEvent(new CustomEvent('window-resize'));
  }
  btnMax.addEventListener('click', (ev) => {
    ev.stopPropagation();
    toggleMaximize();
  });
  titlebar.addEventListener('dblclick', (ev) => {
    if (ev.target.closest('.win-btn')) return;
    toggleMaximize();
  });

  // 右下角缩放手柄
  const resizeHandle = document.createElement('div');
  resizeHandle.className = 'window-resize-handle';
  win.appendChild(resizeHandle);
  makeResizable(win, resizeHandle);

  // 任务栏按钮
  syncTaskbar();

  // 渲染对应应用内容
  renderAppContent(appId, body);

  focusWindow(winObj);
}

// 渲染应用内容
function renderAppContent(appId, body) {
  switch (appId) {
    case 'files':
      renderFiles(body);
      break;
    case 'editor':
      renderEditor(body);
      break;
    case 'terminal':
      renderTerminal(body);
      break;
    case 'settings':
      renderSettings(body);
      break;
    case 'about':
      renderAbout(body);
      break;
    case 'users':
      renderUsers(body);
      break;
    default:
      body.textContent = '未知应用: ' + appId;
  }

}

// 聚焦窗口
function focusWindow(winObj) {
  state.windows.forEach((w) => {
    w.el.classList.remove('focused');
    w.el.classList.remove('active');
  });
  winObj.el.classList.add('focused');
  winObj.el.classList.add('active');
  winObj.el.style.zIndex = ++state.zTop;
  syncTaskbar();
}

// 关闭窗口
function closeWindow(winObj) {
  const idx = state.windows.indexOf(winObj);
  if (idx >= 0) state.windows.splice(idx, 1);
  winObj.el.remove();
  syncTaskbar();
}

// 任务栏同步
function syncTaskbar() {
  const container = document.getElementById('taskbar-apps');
  if (!container) return;
  container.innerHTML = '';
  state.windows.forEach((w) => {
    const app = appsRegistry.find((a) => a.id === w.appId);
    const btn = document.createElement('button');
    btn.className = 'taskbar-app-btn';
    if (app && app.icon.indexOf('<svg') === 0) {
      btn.innerHTML = '<span class="title-icon">' + app.icon + '</span><span>' + escapeHtml(app.name) + '</span>';
    } else {
      btn.textContent = app ? app.name : w.appId;
    }
    if (w.el.classList.contains('active') && !w.el.classList.contains('minimized')) {
      btn.classList.add('active');
    }
    if (w.el.classList.contains('minimized')) {
      btn.classList.add('minimized');
    }
    btn.addEventListener('click', () => {
      if (w.el.classList.contains('minimized')) {
        w.el.classList.remove('minimized');
      }
      focusWindow(w);
    });
    container.appendChild(btn);
  });
}

// 使窗口可拖拽
function makeDraggable(win, handle, winObj) {
  let dragging = false;
  let startX = 0, startY = 0, origX = 0, origY = 0;

  handle.addEventListener('mousedown', (ev) => {
    if (ev.target.closest('.win-btn')) return;
    if (win.classList.contains('maximized')) {
      // 拖拽最大化窗口时先还原为普通窗口（标准桌面行为）
      win.classList.remove('maximized');
      const g = winObj.savedGeom;
      if (g) {
        win.style.left = Math.max(0, ev.clientX - 200) + 'px';
        win.style.top = Math.max(0, ev.clientY - 20) + 'px';
        win.style.width = g.width;
        win.style.height = g.height;
      }
      win.dispatchEvent(new CustomEvent('window-resize'));
    }
    dragging = true;
    startX = ev.clientX;
    startY = ev.clientY;
    origX = parseInt(win.style.left || '0', 10);
    origY = parseInt(win.style.top || '0', 10);
    focusWindow(winObj);
    ev.preventDefault();
  });

  function onMove(ev) {
    if (!dragging) return;
    const dx = ev.clientX - startX;
    const dy = ev.clientY - startY;
    win.style.left = Math.max(0, origX + dx) + 'px';
    win.style.top = Math.max(0, origY + dy) + 'px';
  }
  function onUp() {
    dragging = false;
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// 使窗口可缩放（右下角手柄）
function makeResizable(win, handle) {
  let resizing = false;
  let startX = 0, startY = 0, origW = 0, origH = 0;

  handle.addEventListener('mousedown', (ev) => {
    if (win.classList.contains('maximized')) return;
    resizing = true;
    startX = ev.clientX;
    startY = ev.clientY;
    const rect = win.getBoundingClientRect();
    origW = rect.width;
    origH = rect.height;
    ev.preventDefault();
    ev.stopPropagation();
  });

  function onMove(ev) {
    if (!resizing) return;
    const desktop = document.getElementById('desktop');
    const maxW = desktop ? desktop.clientWidth : window.innerWidth;
    const maxH = desktop ? desktop.clientHeight : window.innerHeight;
    const w = Math.min(Math.max(320, origW + (ev.clientX - startX)), maxW);
    const h = Math.min(Math.max(200, origH + (ev.clientY - startY)), maxH);
    win.style.width = w + 'px';
    win.style.height = h + 'px';
  }
  function onUp() {
    if (!resizing) return;
    resizing = false;
    win.dispatchEvent(new CustomEvent('window-resize'));
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
}

// ================= 文件管理器 =================
function renderFiles(body) {
  const current = { parentId: null, parentStack: [] };
  body.innerHTML = `
    <div class="files-toolbar">
      <button class="btn-back">← 返回</button>
      <span class="files-path">/</span>
      <input class="fs-search" type="search" placeholder="搜索文件名…" autocomplete="off">
      <button class="btn-new-folder">新建文件夹</button>
      <button class="btn-new-file">新建文件</button>
      <button class="btn-upload">上传</button>
      <input type="file" class="file-input-hidden" multiple style="display:none">
    </div>
    <div class="upload-progress hidden"><div class="upload-progress-bar"></div><span class="upload-progress-text"></span></div>
    <div class="files-error hidden"></div>
    <div class="files-list"></div>
  `;
  const listEl = body.querySelector('.files-list');
  const pathEl = body.querySelector('.files-path');
  const backBtn = body.querySelector('.btn-back');

  async function refresh() {
    let url = '/api/fs';
    if (current.parentId !== null) url += '?parent_id=' + current.parentId;
    let nodes = [];
    try {
      nodes = await api(url);
    } catch (e) {
      listEl.innerHTML = '<div class="empty">加载失败: ' + escapeHtml(e.message) + '</div>';
      return;
    }
    state.fsCache[current.parentId === null ? 'root' : current.parentId] = nodes;
    listEl.innerHTML = '';
    if (!nodes || nodes.length === 0) {
      listEl.innerHTML = '<div class="empty">（空）</div>';
    } else {
      nodes.forEach((node) => {
        const row = document.createElement('div');
        row.className = 'fs-row';
        const icon = node.kind === 'folder' ? '📁' : '📄';
        row.innerHTML = `<span class="fs-icon">${icon}</span><span class="fs-name">${escapeHtml(node.name)}</span>`;
        const del = document.createElement('button');
        del.className = 'fs-del';
        del.textContent = '删除';
        del.addEventListener('click', async (ev) => {
          ev.stopPropagation();
          if (!confirm('确认删除 ' + node.name + ' ？')) return;
          try {
            await api('/api/fs/' + node.id, { method: 'DELETE' });
            refresh();
          } catch (e) {
            alert('删除失败: ' + e.message);
          }
        });
        row.appendChild(del);
        if (node.kind === 'file') {
          const dl = document.createElement('button');
          dl.className = 'fs-download';
          dl.textContent = '下载';
          dl.addEventListener('click', (ev) => {
            ev.stopPropagation();
            clearError();
            const dirPath = currentDirPath();
            const fullPath = (dirPath === '/' ? '/' + node.name : dirPath.replace(/\/$/, '') + '/' + node.name);
            const a = document.createElement('a');
            a.href = '/api/files/download?path=' + encodeURIComponent(fullPath);
            a.download = node.name;
            document.body.appendChild(a);
            a.click();
            a.remove();
          });
          row.appendChild(dl);

          // v1.3 行内分享按钮（仅文件）
          const shareBtn = document.createElement('button');
          shareBtn.className = 'fs-share';
          shareBtn.textContent = '分享';
          shareBtn.addEventListener('click', async (ev) => {
            ev.stopPropagation();
            clearError();
            try {
              const r = await api('/api/shares', { method: 'POST', body: JSON.stringify({ nodeId: node.id }) });
              const url = location.origin + r.url;
              showShareDialog(node.name, url);
            } catch (e) {
              showError('分享失败：' + e.message);
            }
          });
          row.appendChild(shareBtn);
        }
        row.addEventListener('dblclick', () => {
          if (node.kind === 'folder') {
            current.parentStack.push({ id: current.parentId, name: node.name });
            current.parentId = node.id;
            updatePath();
            refresh();
          } else {
            // 打开编辑器
            openApp('editor');
            const editorWin = state.windows.find((w) => w.appId === 'editor');
            if (editorWin) {
              editorWin.body.innerHTML = '';
              renderEditor(editorWin.body, node.id);
            }
          }
        });

        if (!body._ctxHelpers) {
          body._ctxHelpers = {
            el: null,
            close() { if (this.el) { this.el.remove(); this.el = null; } },
          };
          document.addEventListener('click', () => body._ctxHelpers.close());
        }
        const ctxH = body._ctxHelpers;
        async function ctxRename(n) {
          const name = prompt('重命名为', n.name);
          if (!name || name === n.name) return;
          try {
            await api('/api/fs/' + n.id, { method: 'PUT', body: JSON.stringify({ name }) });
            refresh();
          } catch (e) { showError('重命名失败：' + e.message); }
        }
        async function ctxDelete(n) {
          if (!confirm('确认删除「' + n.name + '」？')) return;
          if (!confirm('再次确认：删除后无法恢复，继续吗？')) return;
          try {
            await api('/api/fs/' + n.id, { method: 'DELETE' });
            refresh();
          } catch (e) { showError('删除失败：' + e.message); }
        }
        async function ctxMove(n) {
          const banned = new Set([n.id]);
          if (n.kind === 'folder') {
            const queue = [n.id];
            let depth = 0;
            while (queue.length > 0 && depth < 6) {
              depth++;
              const pid = queue.shift();
              let kids = [];
              try { kids = await api('/api/fs?parent_id=' + pid); } catch (e) { break; }
              (kids || []).forEach((k) => {
                banned.add(k.id);
                if (k.kind === 'folder') queue.push(k.id);
              });
            }
          }
          const folders = [{ id: null, path: '/' }];
          const queue = [null];
          let depth = 0;
          while (queue.length > 0 && depth < 6) {
            depth++;
            const pid = queue.shift();
            let kids = [];
            try { kids = await api(pid === null ? '/api/fs' : '/api/fs?parent_id=' + pid); } catch (e) { break; }
            for (const k of (kids || [])) {
              if (k.kind !== 'folder') continue;
              if (banned.has(k.id)) continue;
              const parentPath = folders.find((f) => f.id === pid);
              const base = parentPath ? parentPath.path : '/';
              const p = base.replace(/\/$/, '') + '/' + k.name;
              folders.push({ id: k.id, path: p });
              queue.push(k.id);
            }
          }
          const overlay = document.createElement('div');
          overlay.className = 'move-overlay';
          const card = document.createElement('div');
          card.className = 'move-card';
          const title = document.createElement('div');
          title.className = 'move-title';
          title.textContent = '移动「' + n.name + '」到…';
          const list = document.createElement('div');
          list.className = 'move-list';
          folders.forEach((f) => {
            const r = document.createElement('div');
            r.className = 'move-row';
            r.textContent = f.path;
            r.addEventListener('click', async () => {
              try {
                await api('/api/fs/' + n.id + '/move', { method: 'PATCH', body: JSON.stringify({ parent_id: f.id }) });
                overlay.remove();
                refresh();
              } catch (e) { showError('移动失败：' + e.message); }
            });
            list.appendChild(r);
          });
          const cancel = document.createElement('button');
          cancel.className = 'move-cancel';
          cancel.textContent = '取消';
          cancel.addEventListener('click', () => overlay.remove());
          card.appendChild(title);
          card.appendChild(list);
          card.appendChild(cancel);
          overlay.appendChild(card);
          overlay.addEventListener('click', (ev) => { if (ev.target === overlay) overlay.remove(); });
          document.body.appendChild(overlay);
        }
        row.addEventListener('contextmenu', (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          ctxH.close();
          const menu = document.createElement('div');
          menu.className = 'ctx-menu';
          [
            { label: '重命名', fn: () => ctxRename(node) },
            { label: '移动到…', fn: () => ctxMove(node) },
            { label: '删除', danger: true, fn: () => ctxDelete(node) },
          ].forEach((it) => {
            const mi = document.createElement('div');
            mi.className = 'ctx-item' + (it.danger ? ' danger' : '');
            mi.textContent = it.label;
            mi.addEventListener('click', (ev2) => { ev2.stopPropagation(); ctxH.close(); it.fn(); });
            menu.appendChild(mi);
          });
          document.body.appendChild(menu);
          ctxH.el = menu;
          menu.style.left = Math.min(ev.clientX, window.innerWidth - 180) + 'px';
          menu.style.top = Math.min(ev.clientY, window.innerHeight - 160) + 'px';
        });
        listEl.appendChild(row);
      });
    }
  }

  function updatePath() {
    pathEl.innerHTML = '';
    const mkCrumb = (label, target) => {
      const c = document.createElement('span');
      c.className = 'crumb';
      c.textContent = label;
      c.addEventListener('click', () => {
        current.parentStack = current.parentStack.slice(0, target.stackLen);
        current.parentId = target.parentId;
        clearSearch();
        updatePath();
        refresh();
      });
      return c;
    };
    const sep = () => {
      const s = document.createElement('span');
      s.className = 'crumb-sep';
      s.textContent = '/';
      return s;
    };
    pathEl.appendChild(mkCrumb('根目录', { stackLen: 0, parentId: null }));
    const n = current.parentStack.length;
    current.parentStack.forEach((p, i) => {
      pathEl.appendChild(sep());
      const pid = (i + 1 < n) ? current.parentStack[i + 1].id : current.parentId;
      pathEl.appendChild(mkCrumb(p.name, { stackLen: i + 1, parentId: pid }));
    });
  }

  // ---- 文件名搜索 ----
  const searchInput = body.querySelector('.fs-search');
  let searchTimer = null;
  function clearSearch() {
    if (searchInput && searchInput.value !== '') {
      searchInput.value = '';
    }
  }
  async function runSearch(q) {
    const query = q.trim();
    if (!query) { refresh(); return; }
    listEl.innerHTML = '<div class="empty">搜索中…</div>';
    let results = [];
    try {
      results = await api('/api/fs/search?q=' + encodeURIComponent(query) + '&limit=50');
    } catch (e) {
      listEl.innerHTML = '<div class="empty">搜索失败: ' + escapeHtml(e.message) + '</div>';
      return;
    }
    listEl.innerHTML = '';
    if (!results || results.length === 0) {
      listEl.innerHTML = '<div class="empty">没有找到「' + escapeHtml(query) + '」</div>';
      return;
    }
    results.forEach((node) => {
      const row = document.createElement('div');
      row.className = 'fs-row search-row';
      const icon = node.kind === 'folder' ? '📁' : '📄';
      row.innerHTML = '<span class="fs-icon">' + icon + '</span>' +
        '<span class="fs-name">' + escapeHtml(node.name) + '</span>' +
        '<span class="search-path">' + escapeHtml(node.path || '') + '</span>';
      row.addEventListener('dblclick', () => {
        if (node.kind === 'folder') {
          navigateToPath(node.path + '/' + node.name).then(() => { clearSearch(); });
        } else {
          openApp('editor');
          const editorWin = state.windows.find((w) => w.appId === 'editor');
          if (editorWin) {
            editorWin.body.innerHTML = '';
            renderEditor(editorWin.body, node.id);
          }
          clearSearch();
        }
      });
      listEl.appendChild(row);
    });
  }
  async function navigateToPath(path) {
    const segs = (path || '/').split('/').filter((s) => s.length > 0);
    const stack = [];
    let pid = null;
    for (const seg of segs) {
      const url = pid === null ? '/api/fs' : '/api/fs?parent_id=' + pid;
      let kids = [];
      try { kids = await api(url); } catch (e) { showError('进入失败：' + e.message); return; }
      const hit = (kids || []).find((k) => k.kind === 'folder' && k.name === seg);
      if (!hit) { showError('路径不存在：' + path); return; }
      stack.push({ id: pid, name: seg });
      pid = hit.id;
    }
    current.parentStack = stack;
    current.parentId = pid;
    updatePath();
    refresh();
  }
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => runSearch(searchInput.value), 300);
    });
    searchInput.addEventListener('keydown', (ev) => { ev.stopPropagation(); });
  }

  backBtn.addEventListener('click', () => {
    if (current.parentStack.length > 0) {
      const prev = current.parentStack.pop();
      current.parentId = prev.id;
    } else {
      current.parentId = null;
    }
    updatePath();
    refresh();
  });

  body.querySelector('.btn-new-folder').addEventListener('click', async () => {
    const name = prompt('文件夹名称');
    if (!name) return;
    try {
      await api('/api/fs', {
        method: 'POST',
        body: JSON.stringify({ parentId: current.parentId, name, kind: 'folder', content: '' }),
      });
      refresh();
    } catch (e) {
      alert('创建失败: ' + e.message);
    }
  });

  body.querySelector('.btn-new-file').addEventListener('click', async () => {
    const name = prompt('文件名称');
    if (!name) return;
    try {
      await api('/api/fs', {
        method: 'POST',
        body: JSON.stringify({ parentId: current.parentId, name, kind: 'file', content: '' }),
      });
      refresh();
    } catch (e) {
      alert('创建失败: ' + e.message);
    }
  });

  // ---- 上传 / 下载（v1.1.0 新增）----
  const uploadInput = body.querySelector('.file-input-hidden');
  const progressBox = body.querySelector('.upload-progress');
  const progressBar = body.querySelector('.upload-progress-bar');
  const progressText = body.querySelector('.upload-progress-text');
  const errorBox = body.querySelector('.files-error');

  // 当前目录的真实 path（由 updatePath 维护的 parentStack 拼出）
  function currentDirPath() {
    if (current.parentId === null || current.parentStack.length === 0) return '/';
    return '/' + current.parentStack.map((p) => p.name).join('/');
  }

  function showError(msg) {
    errorBox.textContent = msg;
    errorBox.classList.remove('hidden');
  }
  function clearError() {
    errorBox.textContent = '';
    errorBox.classList.add('hidden');
  }

  function showShareDialog(fileName, url) {
    const overlay = document.createElement('div');
    overlay.className = 'share-dialog-overlay';
    const card = document.createElement('div');
    card.className = 'share-dialog-card';

    const title = document.createElement('div');
    title.className = 'share-dialog-title';
    title.textContent = '分享：' + fileName;

    const input = document.createElement('input');
    input.className = 'share-dialog-input';
    input.type = 'text';
    input.readOnly = true;
    input.value = url;
    input.addEventListener('click', () => input.select());

    const actions = document.createElement('div');
    actions.className = 'share-dialog-actions';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'share-dialog-copy';
    copyBtn.textContent = '复制链接';
    copyBtn.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          input.select();
          document.execCommand('copy');
        }
        copyBtn.textContent = '已复制';
        setTimeout(() => { copyBtn.textContent = '复制链接'; }, 1500);
      } catch (e) {
        input.select();
        try { document.execCommand('copy'); } catch (e2) {}
      }
    });

    const closeBtn = document.createElement('button');
    closeBtn.className = 'share-dialog-close';
    closeBtn.textContent = '关闭';
    closeBtn.addEventListener('click', () => overlay.remove());

    actions.appendChild(copyBtn);
    actions.appendChild(closeBtn);

    card.appendChild(title);
    card.appendChild(input);
    card.appendChild(actions);
    overlay.appendChild(card);
    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) overlay.remove();
    });
    document.body.appendChild(overlay);
    input.focus();
    input.select();
  }

  function uploadFiles(fileList) {
    const files = Array.from(fileList || []);
    if (files.length === 0) return;
    clearError();
    const dirPath = currentDirPath();
    const total = files.length;
    let idx = 0;
    let okCount = 0;
    const failed = [];

    function next() {
      if (idx >= total) {
        progressBox.classList.add('hidden');
        if (failed.length > 0) {
          const names = failed.slice(0, 3).map((it) => it.name);
          let nameStr = names.join('，');
          if (failed.length > 3) nameStr += '等';
          showError('上传完成：成功 ' + okCount + ' 个，失败 ' + failed.length + ' 个（' + nameStr + '）');
        }
        refresh();
        return;
      }
      const i = idx + 1;
      const f = files[idx++];
      progressBox.classList.remove('hidden');
      progressBar.style.width = '0%';
      progressText.textContent = '上传中 ' + i + '/' + total + '：' + f.name + ' (0%)';

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/files/upload?path=' + encodeURIComponent(dirPath));
      xhr.upload.addEventListener('progress', (ev) => {
        if (ev.lengthComputable) {
          const pct = Math.round((ev.loaded / ev.total) * 100);
          progressBar.style.width = pct + '%';
          progressText.textContent = '上传中 ' + i + '/' + total + '：' + f.name + ' (' + pct + '%)';
        }
      });
      xhr.addEventListener('load', () => {
        if (xhr.status === 201) {
          okCount++;
        } else {
          let msg = 'HTTP ' + xhr.status;
          try {
            const data = JSON.parse(xhr.responseText);
            if (data && data.error) msg = data.error;
          } catch (e) {}
          failed.push({ name: f.name, reason: msg });
        }
        next();
      });
      xhr.addEventListener('error', () => {
        failed.push({ name: f.name, reason: '网络错误' });
        next();
      });
      const form = new FormData();
      form.append('file', f, f.name);
      xhr.send(form);
    }
    next();
  }

  body.querySelector('.btn-upload').addEventListener('click', () => {
    clearError();
    uploadInput.click();
  });
  uploadInput.addEventListener('change', () => {
    uploadFiles(uploadInput.files);
    uploadInput.value = '';
  });

  // 拖拽上传：拖到文件管理器窗口任意位置
  let dragDepth = 0;
  body.addEventListener('dragenter', (ev) => {
    ev.preventDefault();
    dragDepth++;
    body.classList.add('files-dragover');
  });
  body.addEventListener('dragover', (ev) => {
    ev.preventDefault();
  });
  body.addEventListener('dragleave', (ev) => {
    ev.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) body.classList.remove('files-dragover');
  });
  body.addEventListener('drop', (ev) => {
    ev.preventDefault();
    dragDepth = 0;
    body.classList.remove('files-dragover');
    if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files.length > 0) {
      uploadFiles(ev.dataTransfer.files);
    }
  });

  updatePath();
  refresh();
}

// ================= 文本编辑器 =================
function renderEditor(body, nodeId) {
  body.innerHTML = `
    <div class="editor-layout">
      <div class="editor-sidebar">
        <div class="editor-sidebar-title">文件</div>
        <div class="editor-file-list">加载中...</div>
        <button class="btn-new-note">新建 untitled.txt</button>
      </div>
      <div class="editor-main">
        <div class="editor-toolbar">
          <span class="editor-current">未选择文件</span>
          <button class="btn-save" disabled>保存</button>
        </div>
        <textarea class="editor-textarea" placeholder="在此输入内容..."></textarea>
      </div>
    </div>
  `;

  const fileListEl = body.querySelector('.editor-file-list');
  const textarea = body.querySelector('.editor-textarea');
  const saveBtn = body.querySelector('.btn-save');
  const currentEl = body.querySelector('.editor-current');

  let currentNode = null;

  async function loadFileList() {
    let nodes = [];
    try {
      nodes = await api('/api/fs');
    } catch (e) {
      fileListEl.textContent = '加载失败';
      return;
    }
    const files = (nodes || []).filter((n) => n.kind === 'file');
    fileListEl.innerHTML = '';
    if (files.length === 0) {
      fileListEl.innerHTML = '<div class="empty">（无文件）</div>';
    }
    files.forEach((f) => {
      const item = document.createElement('div');
      item.className = 'editor-file-item';
      item.textContent = '📄 ' + f.name;
      item.addEventListener('click', () => selectFile(f.id));
      fileListEl.appendChild(item);
    });
  }

  async function selectFile(id) {
    try {
      const node = await api('/api/fs/' + id);
      currentNode = node;
      textarea.value = node.content || '';
      currentEl.textContent = node.name;
      saveBtn.disabled = false;
    } catch (e) {
      alert('打开失败: ' + e.message);
    }
  }

  async function saveFile() {
    if (currentNode) {
      try {
        const updated = await api('/api/fs/' + currentNode.id, {
          method: 'PUT',
          body: JSON.stringify({ content: textarea.value }),
        });
        currentNode = updated;
        currentEl.textContent = updated.name;
        alert('已保存');
      } catch (e) {
        alert('保存失败: ' + e.message);
      }
    } else {
      // 新建
      const name = prompt('文件名', 'untitled.txt');
      if (!name) return;
      try {
        const created = await api('/api/fs', {
          method: 'POST',
          body: JSON.stringify({ parentId: null, name, kind: 'file', content: textarea.value }),
        });
        currentNode = created;
        currentEl.textContent = created.name;
        saveBtn.disabled = false;
        await loadFileList();
        alert('已创建');
      } catch (e) {
        alert('创建失败: ' + e.message);
      }
    }
  }

  saveBtn.addEventListener('click', saveFile);

  body.querySelector('.btn-new-note').addEventListener('click', () => {
    currentNode = null;
    textarea.value = '';
    currentEl.textContent = 'untitled.txt（未保存）';
    saveBtn.disabled = false;
  });

  loadFileList();

  if (nodeId) {
    selectFile(nodeId);
  }
}

// ================= 终端 =================
function renderTerminal(body) {
  body.innerHTML = `
    <div class="xterm-wrap">
      <div class="xterm-tabs"></div>
      <div class="xterm-viewport"></div>
      <div class="xterm-status">连接中…</div>
    </div>`;
  const tabsEl = body.querySelector('.xterm-tabs');
  const viewport = body.querySelector('.xterm-viewport');
  const statusEl = body.querySelector('.xterm-status');

  const TERM_THEME = {
    background: '#161511',
    foreground: '#ece7d9',
    cursor: '#d8a24a',
    cursorAccent: '#161511',
    selectionBackground: 'rgba(216, 162, 74, 0.35)',
    black: '#161511', red: '#e06c5b', green: '#9db35c', yellow: '#d8a24a',
    blue: '#7fa8c9', magenta: '#b085b0', cyan: '#7fb5a8', white: '#ece7d9',
    brightBlack: '#5a5648', brightRed: '#e88a76', brightGreen: '#b3c47a',
    brightYellow: '#e3b85e', brightBlue: '#93bcd6', brightMagenta: '#bd93bd',
    brightCyan: '#93c4b8', brightWhite: '#fbf8ef'
  };

  const sessions = new Map();
  let activeId = null;
  let ws = null;
  let reconnectTimer = null;
  let dead = false;

  function setStatus(t) { if (statusEl) statusEl.textContent = t; }

  function measureCell(term) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const fs = term.options.fontSize || 14;
    ctx.font = fs + 'px ' + term.options.fontFamily;
    const w = ctx.measureText('WWWWWWWWWW').width / 10;
    return { w: Math.max(5, w), h: Math.ceil(fs * 1.5) };
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
  }

  function fitTerm(rec) {
    const rect = viewport.getBoundingClientRect();
    if (rect.width < 40 || rect.height < 40) return;
    const cell = measureCell(rec.term);
    const cols = Math.max(20, Math.floor(rect.width / cell.w));
    const rows = Math.max(8, Math.floor(rect.height / cell.h));
    rec.term.resize(cols, rows);
    send({ type: 'term_resize', session_id: rec.sid, cols, rows });
  }

  function activate(sid) {
    activeId = sid;
    sessions.forEach((rec, id) => {
      const on = id === sid;
      rec.paneEl.classList.toggle('hidden', !on);
      rec.tabEl.classList.toggle('active', on);
    });
    const rec = sessions.get(sid);
    if (rec) { fitTerm(rec); rec.term.focus(); }
  }

  function closeSession(sid) {
    const rec = sessions.get(sid);
    if (!rec) return;
    send({ type: 'term_close', session_id: sid });
    rec.term.dispose();
    rec.tabEl.remove();
    rec.paneEl.remove();
    sessions.delete(sid);
    if (activeId === sid) {
      const next = sessions.keys().next();
      if (!next.done) activate(next.value);
      else { activeId = null; openSession(); }
    }
  }

  function openSession() {
    const tabEl = document.createElement('div');
    tabEl.className = 'xterm-tab';
    tabEl.innerHTML = '<span class="xterm-tab-label">终端</span><button class="xterm-tab-x" title="关闭">×</button>';
    const paneEl = document.createElement('div');
    paneEl.className = 'xterm-pane hidden';
    tabsEl.appendChild(tabEl);
    viewport.appendChild(paneEl);
    const term = new Terminal({
      theme: TERM_THEME,
      fontSize: 14,
      fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, "Noto Sans Mono", monospace',
      cursorBlink: true,
      scrollback: 2000,
      allowProposedApi: true
    });
    term.open(paneEl);
    const tmpSid = 'pending-' + Math.random().toString(36).slice(2);
    const rec = { term, tabEl, paneEl, sid: tmpSid };
    sessions.set(tmpSid, rec);
    tabEl.querySelector('.xterm-tab-x').addEventListener('click', (ev) => {
      ev.stopPropagation();
      closeSession(rec.sid);
    });
    tabEl.addEventListener('click', () => activate(rec.sid));
    term.onData((data) => send({ type: 'term_input', session_id: rec.sid, data }));
    term.attachCustomKeyEventHandler((ev) => {
      if (ev.ctrlKey && !ev.shiftKey && !ev.altKey && !ev.metaKey) {
        const k = ev.key.toLowerCase();
        if (k === 'c') { send({ type: 'term_signal', session_id: rec.sid, signal: 'int' }); return false; }
        if (k === 'd') { send({ type: 'term_input', session_id: rec.sid, data: '\x04' }); return false; }
      }
      return true;
    });
    send({ type: 'term_open', cols: 80, rows: 24 });
    activate(tmpSid);
    new ResizeObserver(() => { if (activeId === rec.sid) fitTerm(rec); }).observe(viewport);
  }

  function onMessage(ev) {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === 'term_ready') {
      const pending = [...sessions.entries()].find(([id]) => id.startsWith('pending-'));
      if (pending) {
        const [tmpId, r] = pending;
        sessions.delete(tmpId);
        r.sid = msg.session_id;
        sessions.set(msg.session_id, r);
        r.tabEl.querySelector('.xterm-tab-label').textContent = '终端 ' + sessions.size;
        if (activeId === tmpId) activeId = msg.session_id;
        fitTerm(r);
        r.term.focus();
      }
      return;
    }
    if (msg.type === 'term_output') {
      const rec = sessions.get(msg.session_id);
      if (rec) rec.term.write(msg.data);
      return;
    }
    if (msg.type === 'term_exited') {
      const rec = sessions.get(msg.session_id);
      if (rec) rec.term.writeln('\r\n[进程已退出 — 回车重开]');
      return;
    }
    if (msg.type === 'term_error') {
      const rec = activeId ? sessions.get(activeId) : null;
      if (rec) rec.term.writeln('\r\n[错误] ' + msg.message);
      else setStatus('[错误] ' + msg.message);
      return;
    }
  }

  function connect() {
    if (dead) return;
    setStatus('连接中…');
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sock = new WebSocket(proto + '://' + location.host + '/ws');
    ws = sock;
    sock.addEventListener('open', () => {
      setStatus('已连接');
      if (sessions.size === 0) { openSession(); return; }
      const n = sessions.size;
      [...sessions.keys()].forEach((sid) => closeSession(sid));
      for (let i = 0; i < Math.max(1, n); i++) openSession();
    });
    sock.addEventListener('message', onMessage);
    sock.addEventListener('close', () => {
      if (dead) return;
      setStatus('连接断开，3 秒后重连…');
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, 3000);
    });
    sock.addEventListener('error', () => { try { sock.close(); } catch (e) {} });
  }

  const newTabBtn = document.createElement('button');
  newTabBtn.className = 'xterm-newtab';
  newTabBtn.textContent = '+ 新标签';
  newTabBtn.addEventListener('click', () => openSession());
  tabsEl.appendChild(newTabBtn);

  const mo = new MutationObserver(() => {
    if (!document.contains(body)) {
      dead = true;
      clearTimeout(reconnectTimer);
      try { if (ws) ws.close(); } catch (e) {}
      sessions.forEach((rec) => { try { rec.term.dispose(); } catch (e) {} });
      mo.disconnect();
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });

  connect();
}

// ================= 设置 =================
function renderSettings(body) {
  body.innerHTML = `
    <div class="settings">
      <div class="settings-row">
        <label>主题</label>
        <select class="sel-theme">
          <option value="light">浅色</option>
          <option value="dark">深色</option>
        </select>
      </div>
      <div class="settings-row">
        <label>壁纸</label>
        <select class="sel-wallpaper">
          <option value="ocean">海洋</option>
          <option value="sunset">日落</option>
          <option value="forest">森林</option>
        </select>
      </div>
      <div class="settings-hint">修改后立即生效并保存。</div>
    </div>
  `;
  const themeSel = body.querySelector('.sel-theme');
  const wallSel = body.querySelector('.sel-wallpaper');

  // 初始化当前值
  api('/api/settings').then((s) => {
    if (s.theme) themeSel.value = s.theme;
    if (s.wallpaper) wallSel.value = s.wallpaper;
  }).catch(() => {});

  themeSel.addEventListener('change', async () => {
    const v = themeSel.value;
    applyTheme(v);
    try {
      await api('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ key: 'theme', value: v }),
      });
    } catch (e) {
      alert('保存失败: ' + e.message);
    }
  });

  wallSel.addEventListener('change', async () => {
    const v = wallSel.value;
    applyWallpaper(v);
    try {
      await api('/api/settings', {
        method: 'PUT',
        body: JSON.stringify({ key: 'wallpaper', value: v }),
      });
    } catch (e) {
      alert('保存失败: ' + e.message);
    }
  });

  initTfa(body);
}

// 两步验证（TOTP）设置区：状态查询 → 启用向导（密码→二维码→验证码→备用码）/ 停用 / 重生成备用码。
function initTfa(body) {
  if (!document.getElementById('tfa-css')) {
    var st = document.createElement('style');
    st.id = 'tfa-css';
    st.textContent = '.tfa-qr{background:#fff;padding:8px;display:inline-block;border:1px solid #e2e2e2;border-radius:4px}.tfa-qr svg{display:block;width:180px;height:180px}.tfa-codes{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}.tfa-codes code{font-family:ui-monospace,monospace;background:#f4f4f5;padding:4px 8px;border-radius:4px}.tfa-btn{margin-right:8px}.tfa-btn.danger{color:#c0392b}';
    document.head.appendChild(st);
  }
  var wrap = document.createElement('div');
  wrap.className = 'settings';
  wrap.innerHTML = '<div class="settings-row"><label>两步验证</label><span class="tfa-status">加载中…</span></div><div class="tfa-area"></div><div class="settings-hint">开启后，登录时除了密码，还要输入手机验证器上的 6 位验证码。密钥经加密保存在本机数据库。</div>';
  body.appendChild(wrap);
  var statusEl = wrap.querySelector('.tfa-status');
  var area = wrap.querySelector('.tfa-area');

  function errLine(msg) {
    area.innerHTML = '<div class="settings-hint" style="color:#c0392b">' + escapeHtml(msg) + '</div>';
  }

  async function refresh() {
    area.innerHTML = '';
    var st;
    try {
      st = await api('/api/2fa/status');
    } catch (e) { statusEl.textContent = '加载失败'; errLine(e.message); return; }
    if (st.enabled) {
      statusEl.textContent = '已启用';
      area.innerHTML = '<div class="settings-row"><button class="tfa-btn" data-act="regen">重新生成备用码</button><button class="tfa-btn danger" data-act="disable">停用</button></div>';
    } else {
      statusEl.textContent = '未启用';
      area.innerHTML = '<div class="settings-row"><button class="tfa-btn primary" data-act="start">启用两步验证</button></div>';
    }
    area.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () { onAction(b.dataset.act); });
    });
  }

  function pwdRow(hint) {
    return '<div class="settings-row"><label>登录密码</label><input type="password" class="tfa-pwd" autocomplete="current-password" placeholder="' + escapeHtml(hint || '确认是本人操作') + '"/></div>';
  }

  async function onAction(act) {
    if (act === 'start') {
      area.innerHTML = pwdRow('') + '<div class="settings-row"><button class="tfa-btn primary" data-go="setup">下一步</button></div>';
      area.querySelector('[data-go="setup"]').addEventListener('click', doSetup);
    } else if (act === 'disable') {
      area.innerHTML = pwdRow('停用需要确认密码') + '<div class="settings-row"><button class="tfa-btn danger" data-go="disable">确认停用</button></div>';
      area.querySelector('[data-go="disable"]').addEventListener('click', doDisable);
    } else if (act === 'regen') {
      area.innerHTML = pwdRow('重新生成需要确认密码') + '<div class="settings-row"><button class="tfa-btn primary" data-go="regen">生成新的备用码</button></div>';
      area.querySelector('[data-go="regen"]').addEventListener('click', doRegen);
    }
  }

  async function doSetup() {
    var pwd = area.querySelector('.tfa-pwd').value;
    if (!pwd) { errLine('请输入登录密码'); return; }
    var data;
    try {
      data = await api('/api/2fa/setup', { method: 'POST', body: JSON.stringify({ password: pwd }) });
    } catch (e) { errLine(e.message); return; }
    area.innerHTML = '<div class="settings-row"><label>1. 扫码</label></div><div class="tfa-qr"><!-- 服务端生成的 SVG，可信 --></div><div class="settings-hint">扫不上？手动添加：<code class="tfa-secret"></code> <button class="tfa-btn" data-copy>复制</button></div><div class="settings-row"><label>2. 输入验证码</label><input type="text" class="tfa-code" inputmode="numeric" maxlength="12" placeholder="6 位验证码"/></div><div class="settings-row"><button class="tfa-btn primary" data-go="enable">启用</button></div>';
    area.querySelector('.tfa-qr').innerHTML = data.qrSvg;
    area.querySelector('.tfa-secret').textContent = data.secret;
    area.querySelector('[data-copy]').addEventListener('click', function () {
      navigator.clipboard.writeText(data.secret).catch(function () {});
    });
    area.querySelector('[data-go="enable"]').addEventListener('click', async function () {
      var code = area.querySelector('.tfa-code').value.trim();
      if (!code) { errLine('请输入验证器上的 6 位验证码'); return; }
      var out;
      try {
        out = await api('/api/2fa/enable', { method: 'POST', body: JSON.stringify({ code: code }) });
      } catch (e) { errLine(e.message); return; }
      showBackupCodes(out.backupCodes, '两步验证已启用！下面是 10 个备用码，验证器不在身边时用，每个只能用一次。请现在抄下来，离开这个页面就再也看不到了。');
      refresh();
    });
  }

  function showBackupCodes(codes, title) {
    var list = codes.map(function (c) { return '<code>' + escapeHtml(c) + '</code>'; }).join(' ');
    area.innerHTML = '<div class="settings-row"><label>' + escapeHtml(title) + '</label></div><div class="tfa-codes">' + list + '</div><div class="settings-row"><button class="tfa-btn" data-copyall>复制全部</button></div>';
    area.querySelector('[data-copyall]').addEventListener('click', function () {
      navigator.clipboard.writeText(codes.join('\n')).catch(function () {});
    });
  }

  async function doDisable() {
    var pwd = area.querySelector('.tfa-pwd').value;
    if (!pwd) { errLine('请输入登录密码'); return; }
    try {
      await api('/api/2fa/disable', { method: 'POST', body: JSON.stringify({ password: pwd }) });
    } catch (e) { errLine(e.message); return; }
    refresh();
  }

  async function doRegen() {
    var pwd = area.querySelector('.tfa-pwd').value;
    if (!pwd) { errLine('请输入登录密码'); return; }
    var out;
    try {
      out = await api('/api/2fa/backup-codes/regenerate', { method: 'POST', body: JSON.stringify({ password: pwd }) });
    } catch (e) { errLine(e.message); return; }
    showBackupCodes(out.backupCodes, '新的备用码已生成，旧的全部作废：');
  }

  refresh();
}

// ================= 关于 =================
function renderAbout(body) {
  body.innerHTML = `
    <div class="about">
      <div class="about-title">mini-os</div>
      <div class="about-version">版本 1.1.0</div>



      <div class="about-stats">统计加载中...</div>
      <div class="about-desc">一个运行在网页里的迷你操作系统。</div>
    </div>
  `;
  const statsEl = body.querySelector('.about-stats');
  api('/api/stats').then((s) => {
    statsEl.innerHTML = `文件: ${s.files}　文件夹: ${s.folders}　总字节: ${s.totalBytes}`;
  }).catch((e) => {
    statsEl.textContent = '统计加载失败: ' + e.message;
  });
}

// HTML 转义
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 启动
document.addEventListener('DOMContentLoaded', init);

// 视觉逻辑：延续桌面系统 token，左对齐数据表，无装饰性渐变
const ROLE_LABELS = { admin: '管理员', editor: '编辑者', viewer: '只读' };
const ROLE_ORDER = ['viewer', 'editor', 'admin'];

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
}

function roleBadge(role) {
  const cls = 'role-badge rb-' + (ROLE_LABELS[role] ? role : 'viewer');
  return '<span class="' + cls + '">' + escapeHtml(roleLabel(role)) + '</span>';
}

function permMatrixHtml() {
  const rows = [
    ['文件读取', '是', '是', '是'],
    ['文件写入', '—', '是', '是'],
    ['创建分享', '—', '是', '是'],
    ['管理分享', '—', '是', '是'],
    ['管理用户', '—', '—', '是'],
  ];
  let html = '<table class="perm-matrix"><thead><tr><th>能力</th><th>只读</th><th>编辑者</th><th>管理员</th></tr></thead><tbody>';
  rows.forEach(function (r) {
    html += '<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td><td>' + r[3] + '</td></tr>';
  });
  html += '</tbody></table>';
  html += '<p class="perm-note">个人设置（主题、壁纸）是每人管自己的，不算在上面这张表里。</p>';
  html += '<p class="perm-note">只读用户不能创建分享；分享链接本身一律只读。</p>';
  html += '<p class="perm-note">改完角色后，那个人要重新登录才生效。</p>';
  return html;
}

async function renderUsers(body) {
  // 视觉逻辑：延续桌面系统 token，左对齐数据表，无装饰性渐变
  body.innerHTML = '<div class="users-wrap"><div class="loading">加载中…</div></div>';

  let res;
  try {
    res = await fetch('/api/users', { credentials: 'same-origin' });
  } catch (e) {
    body.querySelector('.users-wrap').innerHTML =
      '<div class="perm-notice">请求失败：' + escapeHtml(e.message) + '</div>';
    return;
  }

  if (res.status === 401) {
    location.replace('/login.html');
    return;
  }

  const data = await res.json().catch(function () { return null; });
  const wrap = body.querySelector('.users-wrap');

  if (res.status === 403) {
    const me = state.currentUser || {};
    const myRole = roleLabel(me.role);
    const reason = data && data.reason ? data.reason : '需要「用户管理」权限。';
    let html = '<div class="perm-notice">';
    html += '你现在的角色是「' + escapeHtml(myRole) + '」，这个页面需要「管理员」才能改东西。';
    html += '下面这张表告诉你每个角色能干什么——想调权限的话，找管理员。';
    html += '<br><span class="row-err">服务端说明：' + escapeHtml(reason) + '</span>';
    html += '</div>';
    html += '<h3>权限说明</h3>';
    html += permMatrixHtml();
    wrap.innerHTML = html;
    return;
  }

  if (!res.ok) {
    const msg = data && data.error ? data.error : ('HTTP ' + res.status);
    wrap.innerHTML = '<div class="perm-notice">加载失败：' + escapeHtml(msg) + '</div>';
    return;
  }

  const me = state.currentUser || {};
  const isAdmin = me.role === 'admin';
  let html = '';

  html += '<div class="me-bar">当前登录：' + escapeHtml(me.username || '未知') + '（' + escapeHtml(roleLabel(me.role)) + '）</div>';

  if (!isAdmin) {
    html += '<div class="perm-notice">你不是管理员，下面的角色下拉框是灰的，改不了。要看自己能干什么，看页面最下面的权限说明。</div>';
  }

  html += '<h3>用户列表</h3>';
  html += '<table class="users-table"><thead><tr><th>用户名</th><th>角色</th><th>注册时间</th><th>操作</th></tr></thead><tbody>';
  const users = Array.isArray(data) ? data : [];
  users.forEach(function (u) {
    html += '<tr data-uid="' + u.id + '">';
    html += '<td>' + escapeHtml(u.username) + '</td>';
    html += '<td class="role-cell">' + roleBadge(u.role) + '</td>';
    html += '<td>' + escapeHtml(u.createdAt) + '</td>';
    html += '<td>';
    html += '<select class="role-select" data-uid="' + u.id + '"' + (isAdmin ? '' : ' disabled title="需要管理员权限"') + '>';
    ROLE_ORDER.forEach(function (r) {
      html += '<option value="' + r + '"' + (u.role === r ? ' selected' : '') + '>' + roleLabel(r) + '</option>';
    });
    html += '</select>';
    html += '<div class="row-err" data-err-for="' + u.id + '"></div>';
    html += '</td>';
    html += '</tr>';
  });
  html += '</tbody></table>';

  html += '<h3>权限说明</h3>';
  html += permMatrixHtml();

  wrap.innerHTML = html;

  wrap.querySelectorAll('.role-select').forEach(function (sel) {
    sel.addEventListener('change', async function () {
      const uid = sel.getAttribute('data-uid');
      const errBox = wrap.querySelector('[data-err-for="' + uid + '"]');
      if (errBox) errBox.textContent = '';
      const newRole = sel.value;
      const row = sel.closest('tr');
      const prevRole = row ? row.querySelector('.role-cell') : null;
      const prevHtml = prevRole ? prevRole.innerHTML : '';
      try {
        const r = await fetch('/api/users/' + encodeURIComponent(uid) + '/role', {
          method: 'PUT',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: newRole }),
        });
        const respData = await r.json().catch(function () { return null; });
        if (!r.ok) {
          const reason = respData && (respData.reason || respData.error) ? (respData.reason || respData.error) : ('HTTP ' + r.status);
          if (errBox) errBox.textContent = reason;
          if (prevRole) prevRole.innerHTML = prevHtml;
          return;
        }
        if (respData && respData.role && prevRole) {
          prevRole.innerHTML = roleBadge(respData.role);
        }
      } catch (e) {
        if (errBox) errBox.textContent = '请求失败：' + e.message;
        if (prevRole) prevRole.innerHTML = prevHtml;
      }
    });
  });
}

/* ============================================================
   桌面小组件：今日日程 + 速记便签（v1.9.0）
   数据全部走后端 API 持久化，不用 localStorage 做唯一存储。
   ============================================================ */

// 当天 00:00:00 与次日 00:00:00（本地时间，ISO 字符串）
function todayRange() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const day = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  return { from: day + 'T00:00:00', to: addDays(day, 1) + 'T00:00:00', label: day };
}
function addDays(dayStr, n) {
  const d = new Date(dayStr + 'T00:00:00');
  d.setDate(d.getDate() + n);
  const pad = (x) => String(x).padStart(2, '0');
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}
// "2026-10-20T09:00:00" -> "09:00"
function shortTime(iso) {
  if (!iso) return '';
  const m = iso.match(/T(\d{2}):(\d{2})/);
  return m ? m[1] + ':' + m[2] : iso;
}
// 转义 HTML
function escHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

// 渲染两个小组件到桌面右上角
async function renderWidgets() {
  const desktop = document.getElementById('desktop');
  if (!desktop || document.getElementById('widget-panel')) return;
  const panel = document.createElement('div');
  panel.id = 'widget-panel';
  panel.innerHTML =
    '<div class="widget" id="widget-schedule">' +
      '<div class="widget-title"><span>今日日程</span><span class="widget-date" id="widget-date"></span></div>' +
      '<ul class="widget-list" id="widget-event-list"><li class="widget-empty">加载中…</li></ul>' +
      '<div class="widget-add">' +
        '<input id="widget-event-title" type="text" maxlength="60" placeholder="新日程，如：10:00 开会" />' +
        '<button id="widget-event-add" title="添加">＋</button>' +
      '</div>' +
    '</div>' +
    '<div class="widget" id="widget-note">' +
      '<div class="widget-title"><span>速记便签</span><span class="widget-save-hint" id="widget-save-hint"></span></div>' +
      '<textarea id="widget-note-body" placeholder="随手记点什么，自动保存…"></textarea>' +
    '</div>';
  desktop.appendChild(panel);
  document.getElementById('widget-date').textContent = todayRange().label;
  await refreshWidgetEvents();
  await initWidgetNote();
  bindWidgetEvents();
}

// 刷新今日日程列表
async function refreshWidgetEvents() {
  const list = document.getElementById('widget-event-list');
  try {
    const r = todayRange();
    const events = await api('/api/events?from=' + encodeURIComponent(r.from) + '&to=' + encodeURIComponent(r.to));
    if (!events.length) {
      list.innerHTML = '<li class="widget-empty">今天没有安排</li>';
      return;
    }
    list.innerHTML = events.map((e) => {
      const time = e.allDay ? '全天' : shortTime(e.startsAt) + (e.endsAt ? '–' + shortTime(e.endsAt) : '');
      return '<li class="widget-event' + (e.done ? ' done' : '') + '" data-id="' + e.id + '">' +
        '<button class="widget-check" data-act="toggle" title="' + (e.done ? '标为未完成' : '标为完成') + '">' +
          (e.done ? '✓' : '') +
        '</button>' +
        '<span class="widget-event-text"><span class="widget-event-title">' + escHtml(e.title) + '</span>' +
          '<span class="widget-event-time">' + escHtml(time) + '</span></span>' +
        '<button class="widget-del" data-act="del" title="删除">×</button>' +
      '</li>';
    }).join('');
  } catch (err) {
    list.innerHTML = '<li class="widget-empty">加载失败</li>';
  }
}

function bindWidgetEvents() {
  const list = document.getElementById('widget-event-list');
  list.addEventListener('click', async (ev) => {
    const li = ev.target.closest('.widget-event');
    if (!li) return;
    const id = li.getAttribute('data-id');
    const act = ev.target.getAttribute('data-act');
    try {
      if (act === 'toggle') {
        const done = !li.classList.contains('done');
        await api('/api/events/' + id, { method: 'PUT', body: JSON.stringify({ done }) });
      } else if (act === 'del') {
        if (!confirm('删除这条日程？')) return;
        await api('/api/events/' + id, { method: 'DELETE' });
      }
      await refreshWidgetEvents();
    } catch (e) { /* 静默：保持桌面不打扰 */ }
  });

  const input = document.getElementById('widget-event-title');
  const addBtn = document.getElementById('widget-event-add');
  const submit = async () => {
    let title = input.value.trim();
    if (!title) return;
    // 支持 "10:00 开会" 快捷写法：开头的时间自动拆成 startsAt
    let startsAt = null;
    const m = title.match(/^(\d{1,2}):(\d{2})\s+(.+)$/);
    const r = todayRange();
    if (m) {
      const hh = m[1].padStart(2, '0'), mm = m[2];
      startsAt = r.from.slice(0, 11) + hh + ':' + mm + ':00';
      title = m[3];
    } else {
      startsAt = r.from;
    }
    try {
      await api('/api/events', {
        method: 'POST',
        body: JSON.stringify({ title, startsAt }),
      });
      input.value = '';
      await refreshWidgetEvents();
    } catch (e) { /* 静默 */ }
  };
  addBtn.addEventListener('click', submit);
  input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') submit(); });
}

// 速记便签：绑定到第一条 pinned 便签，没有就自动建一条
let widgetNoteId = null;
let widgetNoteTimer = null;
async function initWidgetNote() {
  const ta = document.getElementById('widget-note-body');
  const hint = document.getElementById('widget-save-hint');
  try {
    const notes = await api('/api/notes');
    let note = notes.find((n) => n.pinned) || notes[0];
    if (!note) {
      note = await api('/api/notes', {
        method: 'POST',
        body: JSON.stringify({ title: '桌面速记', body: '' }),
      });
      await api('/api/notes/' + note.id, { method: 'PUT', body: JSON.stringify({ pinned: true }) });
    }
    widgetNoteId = note.id;
    ta.value = note.body || '';
  } catch (e) {
    ta.placeholder = '便签加载失败';
    ta.disabled = true;
    return;
  }
  ta.addEventListener('input', () => {
    hint.textContent = '输入中…';
    clearTimeout(widgetNoteTimer);
    widgetNoteTimer = setTimeout(async () => {
      try {
        await api('/api/notes/' + widgetNoteId, {
          method: 'PUT',
          body: JSON.stringify({ body: ta.value }),
        });
        hint.textContent = '已保存 ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      } catch (e) {
        hint.textContent = '保存失败';
      }
    }, 800);
  });
}
