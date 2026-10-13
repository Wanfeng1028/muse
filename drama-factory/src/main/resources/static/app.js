// AI 短剧工坊 - 前端控制台逻辑（原生 JS，无框架）
// 所有请求均通过 api() 封装，统一处理 JSON 与错误。

// ============ 基础请求封装 ============
async function api(path, opts = {}) {
  const options = {
    headers: { 'Content-Type': 'application/json' },
    ...opts
  };
  if (options.body && typeof options.body !== 'string') {
    options.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = '请求失败';
    try {
      const err = await res.json();
      msg = err.message || err.error || msg;
    } catch (e) { /* ignore */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// ============ 全局状态 ============
let currentProjectId = null;
let currentEpisodeId = null;

// ============ 工具 ============
function $(id) { return document.getElementById(id); }

function showMessage(msg) {
  const box = $('message');
  if (!box) return;
  box.textContent = msg;
  box.style.display = 'block';
  clearTimeout(showMessage._t);
  showMessage._t = setTimeout(() => { box.style.display = 'none'; }, 3000);
}

// ============ 统计 ============
async function loadStats() {
  try {
    const s = await api('/api/stats');
    $('stat-projects').textContent = s.projects;
    $('stat-episodes').textContent = s.episodes;
    $('stat-characters').textContent = s.characters;
    $('stat-scenes').textContent = s.scenes;
  } catch (e) {
    showMessage('统计加载失败：' + e.message);
  }
}

// ============ 项目 ============
async function loadProjects() {
  try {
    const list = await api('/api/projects');
    renderProjects(list);
  } catch (e) {
    showMessage('项目加载失败：' + e.message);
  }
}

function renderProjects(list) {
  const box = $('project-list');
  box.innerHTML = '';
  if (!list.length) {
    box.innerHTML = '<p class="text-secondary m-0">暂无项目</p>';
    return;
  }
  list.forEach(p => {
    const div = document.createElement('div');
    div.className = 'card mb-0' + (p.id === currentProjectId ? ' border-primary' : '');
    div.innerHTML = `
      <div class="card-body p-2">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <div class="fw-bold">${escapeHtml(p.title)}</div>
            <div class="text-secondary small">${p.genre ? escapeHtml(p.genre) : '未分类'} · ${p.status}</div>
            <div class="text-secondary small">剧集 ${p.episodeCount} · 角色 ${p.characterCount}</div>
          </div>
          <div class="btn-list">
            <button class="btn btn-secondary btn-sm" data-action="delete">删除</button>
          </div>
        </div>
      </div>
    `;
    div.style.cursor = 'pointer';
    div.onclick = () => selectProject(p.id);
    div.querySelector('[data-action="delete"]').onclick = (ev) => { ev.stopPropagation(); deleteProject(p.id); };
    box.appendChild(div);
  });
}

async function selectProject(id) {
  currentProjectId = id;
  currentEpisodeId = null;
  await loadProjects();
  await loadEpisodes(id);
  await loadCharacters(id);
  $('project-detail').style.display = 'block';
  $('empty-hint').style.display = 'none';
  $('scene-panel').style.display = 'none';
  $('script-box').textContent = '';
}

async function createProject(ev) {
  ev.preventDefault();
  const body = {
    title: $('project-title').value.trim(),
    genre: $('project-genre').value.trim() || null,
    synopsis: $('project-synopsis').value.trim() || null,
    targetEpisodes: $('project-target-episodes').value ? parseInt($('project-target-episodes').value) : null
  };
  if (!body.title) { showMessage('请填写标题'); return; }
  try {
    await api('/api/projects', { method: 'POST', body });
    $('project-form').reset();
    await loadProjects();
    await loadStats();
    showMessage('项目创建成功');
  } catch (e) {
    showMessage('创建失败：' + e.message);
  }
}

async function deleteProject(id) {
  if (!confirm('确认删除该项目及其剧集/角色？')) return;
  try {
    await api('/api/projects/' + id, { method: 'DELETE' });
    if (currentProjectId === id) {
      currentProjectId = null;
      currentEpisodeId = null;
      $('project-detail').style.display = 'none';
      $('empty-hint').style.display = 'block';
    }
    await loadProjects();
    await loadStats();
    showMessage('项目已删除');
  } catch (e) {
    showMessage('删除失败：' + e.message);
  }
}

// ============ 剧集 ============
async function loadEpisodes(projectId) {
  try {
    const list = await api('/api/projects/' + projectId + '/episodes');
    renderEpisodes(list);
  } catch (e) {
    showMessage('剧集加载失败：' + e.message);
  }
}

function renderEpisodes(list) {
  const box = $('episode-list');
  box.innerHTML = '';
  if (!list.length) {
    box.innerHTML = '<p class="text-secondary m-0">暂无剧集</p>';
    return;
  }
  list.forEach(ep => {
    const div = document.createElement('div');
    div.className = 'card mb-0' + (ep.id === currentEpisodeId ? ' border-primary' : '');
    div.innerHTML = `
      <div class="card-body p-2">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <div class="fw-bold">第 ${ep.episodeNo} 集 ${ep.title ? '· ' + escapeHtml(ep.title) : ''}</div>
            <div class="text-secondary small">${ep.status} · 场景 ${ep.sceneCount}</div>
          </div>
          <div class="btn-list">
            <button class="btn btn-primary btn-sm" data-action="generate">生成剧本</button>
            <button class="btn btn-secondary btn-sm" data-action="delete">删除</button>
          </div>
        </div>
      </div>
    `;
    div.style.cursor = 'pointer';
    div.onclick = () => selectEpisode(ep.id);
    div.querySelector('[data-action="generate"]').onclick = (ev) => { ev.stopPropagation(); generateScript(ep.id); };
    div.querySelector('[data-action="delete"]').onclick = (ev) => { ev.stopPropagation(); deleteEpisode(ep.id); };
    box.appendChild(div);
  });
}

async function createEpisode(ev) {
  ev.preventDefault();
  if (!currentProjectId) { showMessage('请先选择项目'); return; }
  const body = {
    episodeNo: parseInt($('episode-no').value),
    title: $('episode-title').value.trim() || null,
    outline: $('episode-outline').value.trim() || null,
    durationSec: $('episode-duration').value ? parseInt($('episode-duration').value) : null
  };
  if (!body.episodeNo) { showMessage('请填写集号'); return; }
  try {
    await api('/api/projects/' + currentProjectId + '/episodes', { method: 'POST', body });
    $('episode-form').reset();
    await loadEpisodes(currentProjectId);
    await loadProjects();
    await loadStats();
    showMessage('剧集创建成功');
  } catch (e) {
    showMessage('创建失败：' + e.message);
  }
}

async function deleteEpisode(id) {
  if (!confirm('确认删除该剧集及其场景？')) return;
  try {
    await api('/api/episodes/' + id, { method: 'DELETE' });
    if (currentEpisodeId === id) {
      currentEpisodeId = null;
      $('scene-panel').style.display = 'none';
      $('script-box').textContent = '';
    }
    if (currentProjectId) await loadEpisodes(currentProjectId);
    await loadProjects();
    await loadStats();
    showMessage('剧集已删除');
  } catch (e) {
    showMessage('删除失败：' + e.message);
  }
}

async function selectEpisode(id) {
  currentEpisodeId = id;
  if (currentProjectId) await loadEpisodes(currentProjectId);
  await loadScenes(id);
  $('scene-panel').style.display = 'block';
}

// ============ 角色 ============
async function loadCharacters(projectId) {
  try {
    const list = await api('/api/projects/' + projectId + '/characters');
    renderCharacters(list);
  } catch (e) {
    showMessage('角色加载失败：' + e.message);
  }
}

function renderCharacters(list) {
  const box = $('character-list');
  box.innerHTML = '';
  if (!list.length) {
    box.innerHTML = '<p class="text-secondary m-0">暂无角色</p>';
    return;
  }
  list.forEach(c => {
    const div = document.createElement('div');
    div.className = 'card mb-0';
    div.innerHTML = `
      <div class="card-body p-2">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <div class="fw-bold">${escapeHtml(c.name)}</div>
            <div class="text-secondary small">${c.role || 'SUPPORTING'}</div>
            <div class="text-secondary small">${c.traits ? escapeHtml(c.traits) : ''}</div>
          </div>
          <div class="btn-list">
            <button class="btn btn-secondary btn-sm" data-action="delete">删除</button>
          </div>
        </div>
      </div>
    `;
    div.querySelector('[data-action="delete"]').onclick = () => deleteCharacter(c.id);
    box.appendChild(div);
  });
}

async function createCharacter(ev) {
  ev.preventDefault();
  if (!currentProjectId) { showMessage('请先选择项目'); return; }
  const body = {
    name: $('character-name').value.trim(),
    role: $('character-role').value || null,
    description: $('character-description').value.trim() || null,
    traits: $('character-traits').value.trim() || null
  };
  if (!body.name) { showMessage('请填写角色名'); return; }
  try {
    await api('/api/projects/' + currentProjectId + '/characters', { method: 'POST', body });
    $('character-form').reset();
    await loadCharacters(currentProjectId);
    await loadProjects();
    await loadStats();
    showMessage('角色创建成功');
  } catch (e) {
    showMessage('创建失败：' + e.message);
  }
}

async function deleteCharacter(id) {
  if (!confirm('确认删除该角色？')) return;
  try {
    await api('/api/characters/' + id, { method: 'DELETE' });
    if (currentProjectId) await loadCharacters(currentProjectId);
    await loadProjects();
    await loadStats();
    showMessage('角色已删除');
  } catch (e) {
    showMessage('删除失败：' + e.message);
  }
}

// ============ 场景 ============
async function loadScenes(episodeId) {
  try {
    const list = await api('/api/episodes/' + episodeId + '/scenes');
    renderScenes(list);
  } catch (e) {
    showMessage('场景加载失败：' + e.message);
  }
}

function renderScenes(list) {
  const box = $('scene-list');
  box.innerHTML = '';
  if (!list.length) {
    box.innerHTML = '<p class="text-secondary m-0">暂无场景，可点击「生成剧本」</p>';
    return;
  }
  list.forEach(s => {
    const div = document.createElement('div');
    div.className = 'card mb-0';
    div.innerHTML = `
      <div class="card-body p-2">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <div class="fw-bold">场景 ${s.sceneNo} · ${escapeHtml(s.location || '')} · ${escapeHtml(s.timeOfDay || '')}</div>
            <div class="text-secondary small">画面：${escapeHtml(s.description || '')}</div>
            <div class="text-secondary small">对白：${escapeHtml(s.dialogue || '')}</div>
            <div class="text-secondary small">提示词：${escapeHtml(s.prompt || '')}</div>
          </div>
          <div class="btn-list">
            <button class="btn btn-secondary btn-sm" data-action="delete">删除</button>
          </div>
        </div>
      </div>
    `;
    div.querySelector('[data-action="delete"]').onclick = () => deleteScene(s.id);
    box.appendChild(div);
  });
}

async function createScene(ev) {
  ev.preventDefault();
  if (!currentEpisodeId) { showMessage('请先选择剧集'); return; }
  const body = {
    sceneNo: parseInt($('scene-no').value),
    location: $('scene-location').value.trim() || null,
    timeOfDay: $('scene-time').value.trim() || null,
    description: $('scene-desc').value.trim() || null,
    dialogue: $('scene-dialogue').value.trim() || null,
    prompt: $('scene-prompt').value.trim() || null
  };
  if (!body.sceneNo) { showMessage('请填写场景号'); return; }
  try {
    await api('/api/episodes/' + currentEpisodeId + '/scenes', { method: 'POST', body });
    $('scene-form').reset();
    await loadScenes(currentEpisodeId);
    if (currentProjectId) await loadEpisodes(currentProjectId);
    await loadStats();
    showMessage('场景创建成功');
  } catch (e) {
    showMessage('创建失败：' + e.message);
  }
}

async function deleteScene(id) {
  if (!confirm('确认删除该场景？')) return;
  try {
    await api('/api/scenes/' + id, { method: 'DELETE' });
    if (currentEpisodeId) await loadScenes(currentEpisodeId);
    if (currentProjectId) await loadEpisodes(currentProjectId);
    await loadStats();
    showMessage('场景已删除');
  } catch (e) {
    showMessage('删除失败：' + e.message);
  }
}

// ============ 生成剧本 ============
async function generateScript(episodeId) {
  try {
    const res = await api('/api/episodes/' + episodeId + '/generate-script', { method: 'POST' });
    $('script-box').textContent = res.scriptText || '';
    if (currentEpisodeId === episodeId) {
      await loadScenes(episodeId);
    }
    if (currentProjectId) await loadEpisodes(currentProjectId);
    await loadStats();
    showMessage('剧本生成完成，共 ' + res.sceneCount + ' 场');
  } catch (e) {
    showMessage('生成失败：' + e.message);
  }
}

// ============ 辅助 ============
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ============ 初始化 ============
document.addEventListener('DOMContentLoaded', () => {
  $('project-form').addEventListener('submit', createProject);
  $('episode-form').addEventListener('submit', createEpisode);
  $('character-form').addEventListener('submit', createCharacter);
  var _sf = $('scene-form');
  if (_sf) _sf.addEventListener('submit', createScene);

  loadStats();
  loadProjects();
});
