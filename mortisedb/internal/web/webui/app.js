const state = {
  sources: [],
  tables: [],
  views: [],
  currentView: null,
  pendingConflicts: []
};

function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

async function api(url, options) {
  const opts = options || {};
  const res = await fetch(url, opts);
  if (!res.ok) {
    let msg = 'HTTP ' + res.status;
    try {
      const data = await res.json();
      if (data && data.error) msg = data.error;
    } catch (e) {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.indexOf('application/json') !== -1) {
    return res.json();
  }
  return res.text();
}

let toastTimer = null;
function toast(msg, isError) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' error' : '');
  el.style.display = 'block';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = 'toast';
    el.style.display = 'none';
  }, 3000);
}

function switchTab(name) {
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t => {
    if (t.getAttribute('data-tab') === name) t.classList.add('active');
    else t.classList.remove('active');
  });
  const sections = document.querySelectorAll('.section');
  sections.forEach(s => {
    if (s.id === 'section-' + name) s.classList.add('active');
    else s.classList.remove('active');
  });

  if (name === 'overview') loadOverview();
  else if (name === 'sync') { loadSyncSources(); loadRuns(); }
  else if (name === 'data') loadTables();
  else if (name === 'views') loadViews();
  else if (name === 'conflicts') loadConflicts();
}

function fmtTime(t) {
  if (!t) return '从未同步';
  return esc(t);
}

async function loadOverview() {
  try {
    const sources = await api('/api/sources');
    state.sources = sources;
    renderSourceCards(sources);
  } catch (e) {
    toast('加载数据源失败: ' + e.message, true);
  }
  try {
    const runs = await api('/api/runs?limit=50');
    renderRecentRuns(runs.slice(0, 5));
  } catch (e) {
    toast('加载运行记录失败: ' + e.message, true);
  }
}

function renderSourceCards(sources) {
  const el = document.getElementById('source-cards');
  if (!el) return;
  if (!sources || sources.length === 0) {
    el.innerHTML = '<div class="empty">暂无数据源</div>';
    return;
  }
  el.innerHTML = sources.map(s => {
    const tables = (s.tables || []).map(t => {
      const pk = t.primary ? '(' + esc(t.primary) + ')' : '';
      return '<li>' + esc(t.name) + pk + ' · ' + esc(t.rows) + ' 行</li>';
    }).join('');
    return '<div class="source-card">' +
      '<div class="source-head"><span class="source-name">' + esc(s.name) + '</span>' +
      '<span class="badge">' + esc(s.type) + '</span></div>' +
      '<ul class="source-tables">' + tables + '</ul>' +
      '<div class="source-meta">上次同步: ' + fmtTime(s.last_sync) + '</div>' +
      '</div>';
  }).join('');
}

function renderRecentRuns(runs) {
  const el = document.getElementById('recent-runs');
  if (!el) return;
  let html = '<thead><tr><th>任务</th><th>开始</th><th>新增</th><th>更新</th><th>删除</th><th>冲突</th><th>状态</th></tr></thead><tbody>';
  if (!runs || runs.length === 0) {
    html += '<tr><td colspan="7" class="empty">暂无运行记录</td></tr>';
  } else {
    runs.forEach(r => {
      const status = r.error ? '错误' : (r.finished_at ? '完成' : '进行中');
      const cls = r.error ? 'status-error' : (r.finished_at ? 'status-ok' : 'status-run');
      html += '<tr>' +
        '<td>' + esc(r.job) + '</td>' +
        '<td>' + esc(r.started_at) + '</td>' +
        '<td>' + esc(r.inserted) + '</td>' +
        '<td>' + esc(r.updated) + '</td>' +
        '<td>' + esc(r.deleted) + '</td>' +
        '<td>' + esc(r.conflicts) + '</td>' +
        '<td><span class="' + cls + '">' + esc(status) + '</span></td>' +
        '</tr>';
    });
  }
  html += '</tbody>';
  el.innerHTML = html;
}

async function loadSyncSources() {
  const sel = document.getElementById('sync-sources');
  if (!sel) return;
  try {
    const sources = await api('/api/sources');
    state.sources = sources;
    sel.innerHTML = sources.map(s =>
      '<option value="' + esc(s.name) + '">' + esc(s.name) + ' (' + esc(s.type) + ')</option>'
    ).join('');
  } catch (e) {
    toast('加载数据源失败: ' + e.message, true);
  }
}

async function loadRuns() {
  const el = document.getElementById('runs-table');
  if (!el) return;
  try {
    const runs = await api('/api/runs?limit=50');
    let html = '<thead><tr><th>ID</th><th>任务</th><th>开始</th><th>结束</th><th>新增</th><th>更新</th><th>删除</th><th>冲突</th><th>状态</th></tr></thead><tbody>';
    if (!runs || runs.length === 0) {
      html += '<tr><td colspan="9" class="empty">暂无运行记录</td></tr>';
    } else {
      runs.forEach(r => {
        const status = r.error ? esc(r.error) : (r.finished_at ? '完成' : '进行中');
        const cls = r.error ? 'status-error' : (r.finished_at ? 'status-ok' : 'status-run');
        html += '<tr>' +
          '<td>' + esc(r.id) + '</td>' +
          '<td>' + esc(r.job) + '</td>' +
          '<td>' + esc(r.started_at) + '</td>' +
          '<td>' + esc(r.finished_at) + '</td>' +
          '<td>' + esc(r.inserted) + '</td>' +
          '<td>' + esc(r.updated) + '</td>' +
          '<td>' + esc(r.deleted) + '</td>' +
          '<td>' + esc(r.conflicts) + '</td>' +
          '<td><span class="' + cls + '">' + status + '</span></td>' +
          '</tr>';
      });
    }
    html += '</tbody>';
    el.innerHTML = html;
  } catch (e) {
    toast('加载运行记录失败: ' + e.message, true);
  }
}

async function doSync() {
  const btn = document.getElementById('btn-sync');
  const sel = document.getElementById('sync-sources');
  if (!btn) return;
  const selected = sel ? Array.from(sel.selectedOptions).map(o => o.value) : [];
  btn.disabled = true;
  const oldText = btn.textContent;
  btn.textContent = '同步中...';
  try {
    const data = await api('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sources: selected, job: 'manual' })
    });
    const stats = data && data.stats ? data.stats : [];
    let ins = 0, upd = 0, del = 0, con = 0;
    stats.forEach(s => {
      ins += (s.inserted || 0);
      upd += (s.updated || 0);
      del += (s.deleted || 0);
      con += (s.conflicts || 0);
    });
    toast('同步完成: 新增 ' + ins + ' / 更新 ' + upd + ' / 删除 ' + del + ' / 冲突 ' + con);
    loadRuns();
    loadSyncSources();
  } catch (e) {
    toast('同步失败: ' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = oldText;
  }
}

async function loadTables() {
  const sel = document.getElementById('table-select');
  if (!sel) return;
  try {
    const tables = await api('/api/tables');
    state.tables = tables;
    const cur = sel.value;
    sel.innerHTML = tables.map(t =>
      '<option value="' + esc(t.name) + '">' + esc(t.name) + ' (' + esc(t.rows) + ' 行)</option>'
    ).join('');
    if (cur && tables.some(t => t.name === cur)) sel.value = cur;
    if (sel.value) loadTableRows(sel.value);
    else {
      const grid = document.getElementById('data-grid');
      if (grid) grid.innerHTML = '<div class="empty">暂无数据表</div>';
    }
  } catch (e) {
    toast('加载表失败: ' + e.message, true);
  }
}

async function loadTableRows(name) {
  const grid = document.getElementById('data-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="loading">加载中...</div>';
  try {
    const data = await api('/api/tables/' + encodeURIComponent(name) + '/rows?limit=100&offset=0');
    renderGrid(grid, data.columns, data.rows);
  } catch (e) {
    grid.innerHTML = '<div class="empty">加载失败: ' + esc(e.message) + '</div>';
  }
}

function renderGrid(container, columns, rows) {
  const cols = (columns || []).filter(c => String(c).indexOf('_m_') !== 0);
  if (cols.length === 0) {
    container.innerHTML = '<div class="empty">无数据</div>';
    return;
  }
  const colIdx = cols.map(c => columns.indexOf(c));
  let html = '<table><thead><tr>' + cols.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>';
  if (!rows || rows.length === 0) {
    html += '<tr><td colspan="' + cols.length + '" class="empty">无数据</td></tr>';
  } else {
    rows.forEach(r => {
      html += '<tr>' + colIdx.map(i => '<td>' + esc(r[i]) + '</td>').join('') + '</tr>';
    });
  }
  html += '</tbody></table>';
  container.innerHTML = html;
}

async function loadViews() {
  const el = document.getElementById('view-list');
  if (!el) return;
  try {
    const views = await api('/api/views');
    state.views = views;
    if (!views || views.length === 0) {
      el.innerHTML = '<div class="empty">暂无视图</div>';
      return;
    }
    el.innerHTML = views.map(v =>
      '<div class="view-item" data-name="' + esc(v.name) + '">' +
      '<div class="view-name">' + esc(v.name) + '</div>' +
      '<div class="view-desc">' + esc(v.description || '') + '</div>' +
      '<button class="btn-del-view" data-name="' + esc(v.name) + '">删除</button>' +
      '</div>'
    ).join('');
    el.querySelectorAll('.view-item').forEach(item => {
      item.addEventListener('click', (ev) => {
        if (ev.target.classList.contains('btn-del-view')) return;
        const name = item.getAttribute('data-name');
        selectView(name);
      });
    });
    el.querySelectorAll('.btn-del-view').forEach(btn => {
      btn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        deleteView(btn.getAttribute('data-name'));
      });
    });
  } catch (e) {
    toast('加载视图失败: ' + e.message, true);
  }
}

function selectView(name) {
  const v = state.views.find(x => x.name === name);
  if (!v) return;
  state.currentView = v;
  const editor = document.getElementById('sql-editor');
  if (editor) editor.value = v.sql;
  const exportLink = document.getElementById('btn-export-csv');
  if (exportLink) exportLink.href = '/api/views/' + encodeURIComponent(name) + '/rows?format=csv';
  runSql();
}

async function deleteView(name) {
  try {
    await api('/api/views/' + encodeURIComponent(name), { method: 'DELETE' });
    toast('已删除视图: ' + name);
    if (state.currentView && state.currentView.name === name) state.currentView = null;
    loadViews();
  } catch (e) {
    toast('删除失败: ' + e.message, true);
  }
}

async function runSql() {
  const editor = document.getElementById('sql-editor');
  const grid = document.getElementById('view-grid');
  if (!editor || !grid) return;
  const sql = editor.value.trim();
  if (!sql) {
    toast('请输入 SQL', true);
    return;
  }
  grid.innerHTML = '<div class="loading">执行中...</div>';
  try {
    const data = await api('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql: sql, limit: 200 })
    });
    if (data && data.error) {
      grid.innerHTML = '<div class="empty">错误: ' + esc(data.error) + '</div>';
      return;
    }
    renderGrid(grid, data.columns, data.rows);
  } catch (e) {
    grid.innerHTML = '<div class="empty">执行失败: ' + esc(e.message) + '</div>';
    toast('执行失败: ' + e.message, true);
  }
}

async function saveView() {
  const nameEl = document.getElementById('view-name');
  const editor = document.getElementById('sql-editor');
  if (!nameEl || !editor) return;
  const name = nameEl.value.trim();
  const sql = editor.value.trim();
  if (!name) { toast('请输入视图名称', true); return; }
  if (!sql) { toast('请输入 SQL', true); return; }
  try {
    await api('/api/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, sql: sql, description: '' })
    });
    toast('视图已保存: ' + name);
    nameEl.value = '';
    loadViews();
  } catch (e) {
    toast('保存失败: ' + e.message, true);
  }
}

async function loadConflicts() {
  const el = document.getElementById('conflicts-table');
  if (!el) return;
  try {
    const conflicts = await api('/api/conflicts?status=pending');
    state.pendingConflicts = conflicts;
    if (!state.sources || state.sources.length === 0) {
      try { state.sources = await api('/api/sources'); } catch (e) {}
    }
    let html = '<thead><tr><th>ID</th><th>表</th><th>主键</th><th>现有方</th><th>挑战方</th><th>状态</th><th>操作</th></tr></thead><tbody>';
    if (!conflicts || conflicts.length === 0) {
      html += '<tr><td colspan="7" class="empty">暂无冲突</td></tr>';
    } else {
      conflicts.forEach(c => {
        html += '<tr>' +
          '<td>' + esc(c.id) + '</td>' +
          '<td>' + esc(c.table_name) + '</td>' +
          '<td>' + esc(c.pk) + '</td>' +
          '<td>' + esc(c.source_a) + '</td>' +
          '<td>' + esc(c.source_b) + '</td>' +
          '<td>' + esc(c.status) + '</td>' +
          '<td><button class="btn-resolve" data-id="' + esc(c.id) + '">采纳挑战方</button></td>' +
          '</tr>';
      });
    }
    html += '</tbody>';
    el.innerHTML = html;
    el.querySelectorAll('.btn-resolve').forEach(btn => {
      btn.addEventListener('click', () => resolveConflict(btn.getAttribute('data-id'), btn));
    });
  } catch (e) {
    toast('加载冲突失败: ' + e.message, true);
  }
}

function findPkCol(tableName) {
  for (const s of state.sources) {
    if (s.tables) {
      for (const t of s.tables) {
        if (t.name === tableName) return t.primary || 'id';
      }
    }
  }
  return 'id';
}

async function resolveConflict(id, btn) {
  const c = state.pendingConflicts.find(x => String(x.id) === String(id));
  if (!c) return;
  const pkCol = findPkCol(c.table_name);
  let rowJson = c.row_json;
  if (typeof rowJson === 'string') {
    try { rowJson = JSON.parse(rowJson); } catch (e) {}
  }
  btn.disabled = true;
  btn.textContent = '处理中...';
  try {
    await api('/api/conflicts/' + encodeURIComponent(id) + '/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        table: c.table_name,
        pk_col: pkCol,
        pk: c.pk,
        row_json: rowJson
      })
    });
    toast('冲突已解决: ' + c.table_name + ' #' + c.pk);
    loadConflicts();
  } catch (e) {
    toast('解决失败: ' + e.message, true);
    btn.disabled = false;
    btn.textContent = '采纳挑战方';
  }
}

function init() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.getAttribute('data-tab')));
  });

  const btnSync = document.getElementById('btn-sync');
  if (btnSync) btnSync.addEventListener('click', doSync);

  const tableSel = document.getElementById('table-select');
  if (tableSel) tableSel.addEventListener('change', () => loadTableRows(tableSel.value));

  const btnRun = document.getElementById('btn-run-sql');
  if (btnRun) btnRun.addEventListener('click', runSql);

  const btnSave = document.getElementById('btn-save-view');
  if (btnSave) btnSave.addEventListener('click', saveView);

  const editor = document.getElementById('sql-editor');
  if (editor) {
    editor.addEventListener('keydown', (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
        ev.preventDefault();
        runSql();
      }
    });
  }

  switchTab('overview');
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
