/* ==========================================================================
   workspace.js —— AI 工作区右侧生产概览（v5.1）
   项目列表/新建、剧集列表/新建、生产统计、待质检。与左侧 chat.js 通过
   projectSelect 的 change 事件同步所选项目。
   ========================================================================== */
(function () {
  'use strict';

  async function api(path, opts) {
    var options = Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {});
    if (options.body && typeof options.body !== 'string') options.body = JSON.stringify(options.body);
    var res = await fetch(path, options);
    var text = await res.text();
    var data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && (data.message || data.error)) || '请求失败');
    return data;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  var state = { projectId: null };

  function $(id) { return document.getElementById(id); }

  function toast(msg) {
    var t = $('toast');
    if (!t) return;
    t.className = 'toast align-items-center text-bg-danger border-0 show';
    t.innerHTML = '<div class="d-flex"><div class="toast-body">' + esc(msg) + '</div></div>';
    setTimeout(function () { t.className = 'toast'; }, 4000);
  }

  function statusBadge(status) {
    var map = {
      DRAFT: ['secondary', '草稿'], SCRIPTED: ['info', '已编剧'],
      GENERATING: ['warning', '生成中'], GENERATED: ['primary', '已生成'],
      REVIEWED: ['success', '已过审']
    };
    var m = map[status] || ['secondary', status || '未知'];
    return '<span class="badge bg-' + m[0] + '">' + esc(m[1]) + '</span>';
  }

  /* ---- 项目 ---- */
  async function loadProjects() {
    try {
      var list = await api('/api/projects');
      renderProjects(list || []);
      if (!state.projectId && list && list.length) {
        selectProject(list[0].id, true);
      }
    } catch (e) { toast('项目加载失败：' + e.message); }
  }

  function renderProjects(list) {
    var box = $('ws-project-list');
    box.innerHTML = '';
    if (!list.length) {
      box.innerHTML = '<p class="text-secondary small m-0">暂无项目，先新建一个</p>';
      return;
    }
    list.forEach(function (p) {
      var a = document.createElement('a');
      a.href = '#';
      a.className = 'ep-row' + (p.id === state.projectId ? ' active' : '');
      a.style.cssText = 'text-decoration:none;color:inherit;border-radius:6px;padding:8px 10px;' +
        (p.id === state.projectId ? 'background:var(--accent-soft);' : '');
      a.innerHTML = '<span class="t"><strong>' + esc(p.title) + '</strong>' +
        '<br><span class="text-secondary small">' + esc(p.genre || '未分类') + '</span></span>';
      a.addEventListener('click', function (e) { e.preventDefault(); selectProject(p.id); });
      box.appendChild(a);
    });
  }

  function selectProject(id, silent) {
    state.projectId = id;
    /* 同步左侧对话的项目选择器 */
    var sel = $('projectSelect');
    if (sel && sel.value !== String(id)) {
      sel.value = String(id);
      sel.dispatchEvent(new Event('change'));
    }
    loadProjectsSilent();
    loadEpisodes();
    loadStats();
    loadPendingQc();
  }

  async function loadProjectsSilent() {
    try {
      var list = await api('/api/projects');
      renderProjects(list || []);
    } catch (e) { /* 忽略 */ }
  }

  /* ---- 剧集 ---- */
  async function loadEpisodes() {
    var box = $('ws-episode-list');
    if (!state.projectId) {
      box.innerHTML = '<p class="text-secondary small m-0">先选择项目</p>';
      return;
    }
    try {
      var list = await api('/api/projects/' + state.projectId + '/episodes');
      box.innerHTML = '';
      if (!list || !list.length) {
        box.innerHTML = '<p class="text-secondary small m-0">暂无剧集</p>';
        return;
      }
      list.forEach(function (ep) {
        var row = document.createElement('div');
        row.className = 'ep-row';
        row.innerHTML = '<span class="t">第 ' + esc(ep.episodeNo) + ' 集' +
          (ep.title ? ' · ' + esc(ep.title) : '') + '</span>' +
          statusBadge(ep.status) +
          '<a class="btn btn-sm btn-ghost-primary" href="/storyboard.html?episodeId=' + ep.id + '">分镜</a>';
        box.appendChild(row);
      });
    } catch (e) { toast('剧集加载失败：' + e.message); }
  }

  /* ---- 生产统计 ---- */
  async function loadStats() {
    if (!state.projectId) return;
    try {
      var s = await api('/api/projects/' + state.projectId + '/stats');
      $('ws-shot-rate').textContent =
        Math.round((s.shotCompletionRate || 0) * 100) + '%（' + s.shotsCompleted + '/' + s.shotCount + '）';
      var total = (s.tasksDone || 0) + (s.tasksFailed || 0);
      $('ws-task-rate').textContent =
        total ? Math.round((s.taskSuccessRate || 0) * 100) + '%（' + s.tasksDone + '/' + total + '）' : '—';
      var secs = s.totalRenderSeconds || 0;
      $('ws-render-time').textContent =
        secs >= 60 ? Math.floor(secs / 60) + '分' + (secs % 60) + '秒' : secs + '秒';
    } catch (e) { /* 忽略 */ }
  }

  /* ---- 待质检 ---- */
  async function loadPendingQc() {
    var box = $('ws-qc-list');
    if (!state.projectId) {
      box.innerHTML = '<p class="text-secondary small m-0">暂无待质检成片</p>';
      return;
    }
    try {
      var view = await api('/api/projects/' + state.projectId + '/pipeline');
      var eps = (view && view.episodes) || [];
      var pending = [];
      for (var i = 0; i < eps.length; i++) {
        if (eps[i].finalCutStatus === 'READY') {
          var cuts = await api('/api/episodes/' + eps[i].episodeId + '/final-cuts');
          (cuts || []).forEach(function (c) {
            if (c.qcStatus === 'PENDING') {
              pending.push({ episodeNo: eps[i].episodeNo, title: eps[i].title, cutId: c.id });
            }
          });
        }
      }
      $('ws-pending-qc').textContent = pending.length ? pending.length + ' 个' : '0 个';
      if (!pending.length) {
        box.innerHTML = '<p class="text-secondary small m-0">暂无待质检成片</p>';
        return;
      }
      box.innerHTML = '';
      pending.forEach(function (p) {
        var row = document.createElement('div');
        row.className = 'ep-row';
        row.innerHTML = '<span class="t">第 ' + esc(p.episodeNo) + ' 集' +
          (p.title ? ' · ' + esc(p.title) : '') + '</span>' +
          '<a class="btn btn-sm btn-outline-primary" href="/qc.html?finalCutId=' + p.cutId + '">去质检</a>';
        box.appendChild(row);
      });
    } catch (e) { /* 忽略 */ }
  }

  /* ---- 新建表单 ---- */
  function init() {
    var npb = $('ws-new-project-btn');
    var npf = $('ws-project-form');
    npb.addEventListener('click', function () {
      npf.style.display = npf.style.display === 'none' ? 'block' : 'none';
    });
    $('ws-project-cancel').addEventListener('click', function () { npf.style.display = 'none'; });
    npf.addEventListener('submit', async function (e) {
      e.preventDefault();
      var title = $('ws-project-title').value.trim();
      if (!title) { toast('请填写项目标题'); return; }
      try {
        var p = await api('/api/projects', { method: 'POST', body: {
          title: title,
          genre: $('ws-project-genre').value.trim() || null
        }});
        npf.reset();
        npf.style.display = 'none';
        await loadProjects();
        if (p && p.id) selectProject(p.id);
      } catch (err) { toast('创建失败：' + err.message); }
    });

    var neb = $('ws-new-episode-btn');
    var nef = $('ws-episode-form');
    neb.addEventListener('click', function () {
      if (!state.projectId) { toast('请先选择项目'); return; }
      nef.style.display = nef.style.display === 'none' ? 'block' : 'none';
    });
    $('ws-episode-cancel').addEventListener('click', function () { nef.style.display = 'none'; });
    nef.addEventListener('submit', async function (e) {
      e.preventDefault();
      if (!state.projectId) { toast('请先选择项目'); return; }
      var no = parseInt($('ws-episode-no').value, 10);
      if (!no) { toast('请填写集号'); return; }
      try {
        await api('/api/projects/' + state.projectId + '/episodes', { method: 'POST', body: {
          episodeNo: no,
          title: $('ws-episode-title').value.trim() || null
        }});
        nef.reset();
        nef.style.display = 'none';
        await loadEpisodes();
        /* 同步对话的剧集选择器 */
        var sel = $('projectSelect');
        if (sel) sel.dispatchEvent(new Event('change'));
      } catch (err) { toast('创建失败：' + err.message); }
    });

    loadProjects();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
