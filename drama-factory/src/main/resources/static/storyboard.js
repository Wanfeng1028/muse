const SHOT_SIZE_LABEL = {
  wide: '远景',
  full: '全景',
  medium: '中景',
  closeup: '特写',
  extreme_closeup: '大特写'
};

const CAMERA_MOVE_LABEL = {
  static: '固定机位',
  pan: '摇镜',
  tilt: '俯仰',
  dolly: '推拉',
  zoom: '变焦',
  handheld: '手持'
};

const state = {
  projects: [],
  episodes: [],
  shots: [],
  tasks: [],
  editingId: null
};

async function api(path, options) {
  const res = await fetch(path, Object.assign({
    headers: { 'Content-Type': 'application/json' }
  }, options || {}));
  if (!res.ok) {
    let msg = '请求失败';
    try {
      const data = await res.json();
      if (data && data.detail) msg = data.detail;
    } catch (e) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function statusBadgeClass(status) {
  switch (String(status || '').toUpperCase()) {
    case 'PENDING': return 'bg-yellow-lt';
    case 'PROCESSING': return 'bg-blue-lt';
    case 'DONE': return 'bg-green-lt';
    case 'FAILED': return 'bg-red-lt';
    default: return 'bg-secondary-lt';
  }
}

function showToast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; el.textContent = ''; }, 2600);
}

function getProjectId() {
  const el = document.getElementById('projectSelect');
  return el ? el.value : '';
}

function getEpisodeId() {
  const el = document.getElementById('episodeSelect');
  return el ? el.value : '';
}

async function loadProjects() {
  const sel = document.getElementById('projectSelect');
  try {
    const projects = await api('/api/projects');
    state.projects = projects || [];
    sel.innerHTML = '<option value="">选择项目</option>' + state.projects
      .map(p => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name || p.title || p.id)}</option>`)
      .join('');
  } catch (e) {
    showToast(e.message);
  }
}

async function loadEpisodes() {
  const sel = document.getElementById('episodeSelect');
  const pid = getProjectId();
  state.episodes = [];
  if (!pid) {
    sel.innerHTML = '<option value="">选择剧集</option>';
    renderShots();
    return;
  }
  try {
    const episodes = await api(`/api/projects/${encodeURIComponent(pid)}/episodes`);
    state.episodes = episodes || [];
    sel.innerHTML = '<option value="">选择剧集</option>' + state.episodes
      .map(ep => `<option value="${escapeHtml(ep.id)}">${escapeHtml(ep.title || ep.name || ('第' + ep.number + '集'))}</option>`)
      .join('');
  } catch (e) {
    showToast(e.message);
  }
  renderShots();
}

function updateEpisodeMeta() {
  const meta = document.getElementById('episodeMeta');
  if (!meta) return;
  const eid = getEpisodeId();
  const ep = state.episodes.find(x => String(x.id) === String(eid));
  if (!ep) {
    meta.textContent = '';
    return;
  }
  const parts = [];
  // 剧集标题已显示在下拉框中，此处只展示简介，避免标题重复渲染
  if (ep.summary) parts.push(ep.summary);
  meta.textContent = parts.join(' · ');
}

async function loadShots() {
  const pid = getProjectId();
  const eid = getEpisodeId();
  if (!pid || !eid) {
    state.shots = [];
    state.tasks = [];
    renderShots();
    return;
  }
  try {
    const shots = await api(`/api/episodes/${encodeURIComponent(eid)}/shots`);
    state.shots = shots || [];
    await loadTasksForShots();
  } catch (e) {
    showToast(e.message);
  }
  renderShots();
}

async function loadTasksForShots() {
  state.taskMap = {};
  if (!state.shots.length) return;
  await Promise.all(state.shots.map(async (shot) => {
    const sid = shot.id;
    try {
      const list = await api(`/api/shots/${encodeURIComponent(sid)}/video-tasks`);
      const tasks = Array.isArray(list) ? list : [];
      let latest = null;
      tasks.forEach((t) => {
        if (!latest) { latest = t; return; }
        const ta = t.createdAt || t.id || 0;
        const la = latest.createdAt || latest.id || 0;
        if (ta > la) latest = t;
      });
      state.taskMap[sid] = latest;
    } catch (e) {
      state.taskMap[sid] = null;
    }
  }));
}

function taskForShot(shotId) {
  return (state.taskMap && state.taskMap[shotId]) || null;
}

function toTimecode(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, '0');
  const ss = String(total % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function renderShots() {
  const grid = document.getElementById('slateGrid');
  if (!grid) return;

  const pid = getProjectId();
  const eid = getEpisodeId();

  if (!pid || !eid) {
    grid.innerHTML = '<div class="alert alert-info">请选择项目与剧集</div>';
    return;
  }

  if (!state.shots.length) {
    grid.innerHTML = '<div class="alert alert-info">本集暂无分镜，点击“添加分镜”新建</div>';
    return;
  }

  const lastIndex = state.shots.length - 1;

  grid.innerHTML = state.shots.map((shot, index) => {
    const no = String(index + 1).padStart(2, '0');
    const sizeLabel = shot.shotSizeLabel || SHOT_SIZE_LABEL[shot.shotSize] || shot.shotSize || '';
    const moveLabel = shot.cameraMoveLabel || CAMERA_MOVE_LABEL[shot.cameraMove] || shot.cameraMove || '';
    const task = taskForShot(shot.id);
    const vStatus = task ? task.status : null;

    const badges = [];
    if (sizeLabel) badges.push(`<span class="badge bg-blue-lt me-1">${escapeHtml(sizeLabel)}</span>`);
    if (moveLabel) badges.push(`<span class="badge bg-orange-lt me-1">${escapeHtml(moveLabel)}</span>`);

    const descHtml = shot.description
      ? `<div class="mb-2"><div class="text-secondary small">画面描述</div><div>${escapeHtml(shot.description)}</div></div>`
      : '';
    const dialogueHtml = shot.dialogue
      ? `<div class="mb-2"><div class="text-secondary small">对白</div><div>${escapeHtml(shot.dialogue)}</div></div>`
      : '';
    const promptHtml = shot.videoPrompt
      ? `<div class="mb-2"><div class="text-secondary small">视频提示词</div><div>${escapeHtml(shot.videoPrompt)}</div></div>`
      : '';

    const statusText = task
      ? escapeHtml(task.statusLabel || task.status || '未知')
      : '未生成';

    const upDisabled = index === 0 ? ' disabled' : '';
    const downDisabled = index === lastIndex ? ' disabled' : '';

    return `
<div class="card mb-3" data-sid="${escapeHtml(shot.id)}">
  <div class="card-header">
    <h3 class="card-title">镜号 ${escapeHtml(no)}</h3>
    <div class="card-actions">
      ${badges.join('')}
    </div>
  </div>
  <div class="card-body">
    ${descHtml}
    ${dialogueHtml}
    ${promptHtml}
    <div class="d-flex align-items-center gap-2 mb-3">
      <span class="badge bg-secondary-lt">时长 ${escapeHtml(toTimecode(shot.durationSeconds))}</span>
      <span class="badge ${statusBadgeClass(vStatus)}">${statusText}</span>
    </div>
    <div class="btn-list">
      <button class="btn btn-sm btn-outline-secondary" data-act="up"${upDisabled}>上移</button>
      <button class="btn btn-sm btn-outline-secondary" data-act="down"${downDisabled}>下移</button>
      <button class="btn btn-sm btn-secondary" data-act="edit">编辑</button>
      <button class="btn btn-sm btn-danger" data-act="del">删除</button>
      <button class="btn btn-sm btn-primary" data-act="gen">生成视频</button>
    </div>
  </div>
</div>`;
  }).join('');
}

function openForm(shot) {
  const panel = document.getElementById('formPanel');
  const title = document.getElementById('formTitle');
  document.getElementById('shotId').value = shot ? shot.id : '';
  document.getElementById('shotNo').value = shot ? (shot.shotNo || '') : (state.shots.length + 1);
  document.getElementById('shotSize').value = shot ? (shot.shotSize || '') : '';
  document.getElementById('cameraMove').value = shot ? (shot.cameraMove || '') : '';
  document.getElementById('durationSeconds').value = shot ? (shot.durationSeconds || '') : '';
  document.getElementById('description').value = shot ? (shot.description || '') : '';
  document.getElementById('dialogue').value = shot ? (shot.dialogue || '') : '';
  document.getElementById('videoPrompt').value = shot ? (shot.videoPrompt || '') : '';
  document.getElementById('formError').textContent = '';
  title.textContent = shot ? '编辑分镜' : '添加分镜';
  state.editingId = shot ? shot.id : null;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeForm() {
  const panel = document.getElementById('formPanel');
  panel.hidden = true;
  state.editingId = null;
  document.getElementById('shotForm').reset();
  document.getElementById('shotId').value = '';
  document.getElementById('formError').textContent = '';
}

function collectForm() {
  return {
    shotNo: Number(document.getElementById('shotNo').value) || 0,
    shotSize: document.getElementById('shotSize').value || null,
    cameraMove: document.getElementById('cameraMove').value || null,
    durationSeconds: Number(document.getElementById('durationSeconds').value) || 0,
    description: document.getElementById('description').value.trim(),
    dialogue: document.getElementById('dialogue').value.trim(),
    videoPrompt: document.getElementById('videoPrompt').value.trim()
  };
}

async function saveShot(event) {
  event.preventDefault();
  const errEl = document.getElementById('formError');
  errEl.textContent = '';
  const pid = getProjectId();
  const eid = getEpisodeId();
  if (!pid || !eid) {
    errEl.textContent = '请先选择项目与剧集';
    return;
  }
  const payload = collectForm();
  const id = document.getElementById('shotId').value;
  try {
    if (id) {
      await api(`/api/shots/${encodeURIComponent(id)}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      showToast('分镜已更新');
    } else {
      await api(`/api/episodes/${encodeURIComponent(eid)}/shots`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      showToast('分镜已添加');
    }
    closeForm();
    await loadShots();
  } catch (e) {
    errEl.textContent = e.message;
  }
}

async function deleteShot(id) {
  if (!confirm('确定删除该分镜？')) return;
  try {
    await api(`/api/shots/${encodeURIComponent(id)}`, { method: 'DELETE' });
    showToast('分镜已删除');
    await loadShots();
  } catch (e) {
    showToast(e.message);
  }
}

async function reorder(ids) {
  const eid = getEpisodeId();
  if (!eid) { showToast('请先选择剧集'); return; }
  try {
    await api(`/api/episodes/${encodeURIComponent(eid)}/shots/reorder`, {
      method: 'POST',
      body: JSON.stringify({ shotIds: ids })
    });
    await loadShots();
  } catch (e) {
    showToast(e.message);
  }
}

function moveShot(id, dir) {
  const ids = state.shots.map(s => s.id);
  const index = ids.findIndex(x => String(x) === String(id));
  if (index < 0) return;
  const target = index + dir;
  if (target < 0 || target >= ids.length) return;
  const tmp = ids[index];
  ids[index] = ids[target];
  ids[target] = tmp;
  reorder(ids);
}

async function genVideo(id) {
  try {
    await api(`/api/shots/${encodeURIComponent(id)}/video-tasks`, { method: 'POST', body: '{}' });
    showToast('已提交生成任务');
    await loadShots();
  } catch (e) {
    showToast(e.message);
  }
}

async function submitAll() {
  const eid = getEpisodeId();
  if (!eid) {
    showToast('请先选择剧集');
    return;
  }
  try {
    await api(`/api/episodes/${encodeURIComponent(eid)}/video-tasks/submit-all`, { method: 'POST', body: '{}' });
    showToast('已提交本集全部任务');
    await loadShots();
  } catch (e) {
    showToast(e.message);
  }
}

function bindEvents() {
  const addBtn = document.getElementById('addBtn');
  const submitAllBtn = document.getElementById('submitAllBtn');
  const refreshBtn = document.getElementById('refreshBtn');
  const cancelBtn = document.getElementById('cancelBtn');
  const form = document.getElementById('shotForm');
  const projectSelect = document.getElementById('projectSelect');
  const episodeSelect = document.getElementById('episodeSelect');
  const grid = document.getElementById('slateGrid');

  if (addBtn) addBtn.addEventListener('click', () => openForm(null));
  if (submitAllBtn) submitAllBtn.addEventListener('click', submitAll);
  if (refreshBtn) refreshBtn.addEventListener('click', () => loadShots());
  if (cancelBtn) cancelBtn.addEventListener('click', closeForm);
  if (form) form.addEventListener('submit', saveShot);

  if (projectSelect) {
    projectSelect.addEventListener('change', async () => {
      await loadEpisodes();
      updateEpisodeMeta();
      await loadShots();
    });
  }

  if (episodeSelect) {
    episodeSelect.addEventListener('change', async () => {
      updateEpisodeMeta();
      await loadShots();
    });
  }

  if (grid) {
    grid.addEventListener('click', (event) => {
      const btn = event.target.closest('button[data-act]');
      if (!btn) return;
      const card = btn.closest('[data-sid]');
      if (!card) return;
      const sid = card.getAttribute('data-sid');
      const act = btn.getAttribute('data-act');
      if (act === 'up') moveShot(sid, -1);
      else if (act === 'down') moveShot(sid, 1);
      else if (act === 'edit') {
        const shot = state.shots.find(s => String(s.id) === String(sid));
        if (shot) openForm(shot);
      } else if (act === 'del') deleteShot(sid);
      else if (act === 'gen') genVideo(sid);
    });
  }
}

function fillSelects() {
  const sizeSel = document.getElementById('shotSize');
  const moveSel = document.getElementById('cameraMove');
  if (sizeSel && !sizeSel.options.length) {
    sizeSel.innerHTML = '<option value="">选择景别</option>' + Object.keys(SHOT_SIZE_LABEL)
      .map(k => `<option value="${escapeHtml(k)}">${escapeHtml(SHOT_SIZE_LABEL[k])}</option>`)
      .join('');
  }
  if (moveSel && !moveSel.options.length) {
    moveSel.innerHTML = '<option value="">选择运镜</option>' + Object.keys(CAMERA_MOVE_LABEL)
      .map(k => `<option value="${escapeHtml(k)}">${escapeHtml(CAMERA_MOVE_LABEL[k])}</option>`)
      .join('');
  }
}

async function init() {
  fillSelects();
  bindEvents();
  await loadProjects();
  const psel = document.getElementById('projectSelect');
  if (state.projects.length) {
    psel.value = String(state.projects[0].id);
    await loadEpisodes();
    const esel = document.getElementById('episodeSelect');
    if (state.episodes.length) {
      esel.value = String(state.episodes[0].id);
    }
  }
  updateEpisodeMeta();
  await loadShots();
}

init();
