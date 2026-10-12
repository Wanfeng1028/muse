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
    const msg = data && data.error ? data.error : ('HTTP ' + res.status);
    throw new Error(msg);
  }
  return data;
}

// 桌面图标与应用定义
let appsRegistry = [];

// 初始化
async function init() {
  try {
    appsRegistry = await api('/api/apps');
  } catch (e) {
    appsRegistry = [];
    console.error('加载应用列表失败', e);
  }
  renderDesktopIcons(appsRegistry);

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
    icon.innerHTML = `<div class="icon-emoji">${app.icon}</div><div class="icon-label">${escapeHtml(app.name)}</div>`;
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
    item.innerHTML = `<span class="menu-emoji">${app.icon}</span><span>${escapeHtml(app.name)}</span>`;
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
  desktop.className = desktop.className.replace(/wallpaper-\S+/g, '').trim();
  desktop.classList.add('wallpaper-' + wallpaper);
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
  title.textContent = app.icon + ' ' + app.name;
  const controls = document.createElement('div');
  controls.className = 'window-controls';
  const btnMin = document.createElement('button');
  btnMin.className = 'win-btn win-min';
  btnMin.textContent = '—';
  const btnClose = document.createElement('button');
  btnClose.className = 'win-btn win-close';
  btnClose.textContent = '×';
  controls.appendChild(btnMin);
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
    default:
      body.textContent = '未知应用: ' + appId;
  }
}

// 聚焦窗口
function focusWindow(winObj) {
  state.windows.forEach((w) => w.el.classList.remove('focused'));
  winObj.el.classList.add('focused');
  winObj.el.style.zIndex = ++state.zTop;
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
    btn.textContent = (app ? app.icon + ' ' + app.name : w.appId);
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

// ================= 文件管理器 =================
function renderFiles(body) {
  const current = { parentId: null, parentStack: [] };
  body.innerHTML = `
    <div class="files-toolbar">
      <button class="btn-back">← 返回</button>
      <span class="files-path">/</span>
      <button class="btn-new-folder">新建文件夹</button>
      <button class="btn-new-file">新建文件</button>
    </div>
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
        row.addEventListener('dblclick', () => {
          if (node.kind === 'folder') {
            current.parentStack.push({ id: current.parentId, name: pathEl.textContent });
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
        listEl.appendChild(row);
      });
    }
  }

  function updatePath() {
    if (current.parentId === null) {
      pathEl.textContent = '/';
    } else {
      // 简单展示父级 id 路径
      pathEl.textContent = '/ #' + current.parentId;
    }
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
    <div class="terminal">
      <div class="terminal-output"></div>
      <div class="terminal-input-line">
        <span class="terminal-prompt">$</span>
        <input class="terminal-input" type="text" autocomplete="off" />
      </div>
    </div>
  `;
  const output = body.querySelector('.terminal-output');
  const input = body.querySelector('.terminal-input');

  function print(text) {
    const line = document.createElement('div');
    line.className = 'terminal-line';
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  print('mini-os terminal. 输入 help 查看命令。');

  input.addEventListener('keydown', async (ev) => {
    if (ev.key !== 'Enter') return;
    const raw = input.value.trim();
    input.value = '';
    if (!raw) return;
    print('$ ' + raw);
    const parts = raw.split(/\s+/);
    const cmd = parts[0];
    const args = parts.slice(1);

    if (cmd === 'help') {
      print('可用命令: help, clear, ls, stats, health, echo <text>');
    } else if (cmd === 'clear') {
      output.innerHTML = '';
    } else if (cmd === 'ls') {
      try {
        const nodes = await api('/api/fs');
        if (!nodes || nodes.length === 0) {
          print('（空）');
        } else {
          nodes.forEach((n) => {
            const icon = n.kind === 'folder' ? '📁' : '📄';
            print(`${icon} ${n.name}`);
          });
        }
      } catch (e) {
        print('错误: ' + e.message);
      }
    } else if (cmd === 'stats') {
      try {
        const s = await api('/api/stats');
        print(`文件: ${s.files}  文件夹: ${s.folders}  总字节: ${s.totalBytes}`);
      } catch (e) {
        print('错误: ' + e.message);
      }
    } else if (cmd === 'health') {
      try {
        const h = await api('/api/health');
        print(`状态: ${h.status}  版本: ${h.version}`);
      } catch (e) {
        print('错误: ' + e.message);
      }
    } else if (cmd === 'echo') {
      print(args.join(' '));
    } else {
      print('未知命令: ' + cmd + '（输入 help 查看帮助）');
    }
  });

  input.focus();
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
}

// ================= 关于 =================
function renderAbout(body) {
  body.innerHTML = `
    <div class="about">
      <div class="about-title">mini-os</div>
      <div class="about-version">版本 1.0.0</div>
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
