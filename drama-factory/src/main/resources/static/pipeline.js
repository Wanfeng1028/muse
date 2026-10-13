
(function () {
  'use strict';

  var state = {
    projects: [],
    projectId: null,
    pipeline: null
  };

  var FINAL_CUT_LABELS = {
    READY: '已完成',
    BUILDING: '剪辑中',
    FAILED: '失败',
    PENDING: '待处理'
  };

  function finalCutKey(v) {
    return v ? String(v).toUpperCase() : '';
  }

  function finalCutText(v) {
    var k = finalCutKey(v);
    if (!k) return '未开始';
    return FINAL_CUT_LABELS[k] || v;
  }

  function statusLine(dotClass, text) {
    var s = document.createElement('span');
    s.className = 'status-line';
    var d = document.createElement('span');
    d.className = 'status-dot ' + dotClass;
    s.appendChild(d);
    s.appendChild(document.createTextNode(text));
    return s;
  }

  function episodeIsStuck(ep) {
    if (!ep) return false;
    var failed = Number(ep.failedTasks || 0);
    var pending = Number(ep.pendingTasks || 0);
    var processing = Number(ep.processingTasks || 0);
    var done = Number(ep.doneTasks || 0);
    var shots = Number(ep.shotCount || 0);
    if (failed > 0) return true;
    if (shots > 0 && done < shots && pending === 0 && processing === 0) return true;
    if (finalCutKey(ep.finalCutStatus) === 'FAILED') return true;
    return false;
  }

  function toast(msg) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(function () {
      el.classList.remove('show');
      el.textContent = '';
    }, 2600);
  }

  function api(path, opts) {
    opts = opts || {};
    return fetch(path, {
      method: opts.method || 'GET',
      headers: { 'Content-Type': 'application/json' },
      body: opts.body ? JSON.stringify(opts.body) : undefined
    }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    });
  }

  function pad2(n) {
    n = Number(n) || 0;
    return n < 10 ? '0' + n : String(n);
  }

  function renderProjectSelect() {
    var sel = document.getElementById('projectSelect');
    if (!sel) return;
    sel.innerHTML = '';
    state.projects.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.title || ('项目 ' + p.id);
      if (String(p.id) === String(state.projectId)) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function loadProjects() {
    return api('/api/projects').then(function (data) {
      state.projects = (data && data.projects) || data || [];
      if (!state.projectId && state.projects.length) {
        state.projectId = state.projects[0].id;
      }
      renderProjectSelect();
    }).catch(function (err) {
      toast('加载项目失败：' + err.message);
    });
  }

  function loadPipeline() {
    if (!state.projectId) {
      state.pipeline = null;
      renderPipeline();
      return Promise.resolve();
    }
    return api('/api/projects/' + encodeURIComponent(state.projectId) + '/pipeline').then(function (data) {
      state.pipeline = data;
      renderPipeline();
    }).catch(function (err) {
      toast('加载生产线失败：' + err.message);
    });
  }

  function loadStats() {
    if (!state.projectId) return Promise.resolve();
    return api('/api/projects/' + encodeURIComponent(state.projectId) + '/stats').then(function (s) {
      var shotRate = document.getElementById('statShotRate');
      var shotDetail = document.getElementById('statShotDetail');
      var taskRate = document.getElementById('statTaskRate');
      var taskDetail = document.getElementById('statTaskDetail');
      var renderTime = document.getElementById('statRenderTime');
      if (shotRate) shotRate.textContent = Math.round((s.shotCompletionRate || 0) * 100) + '%';
      if (shotDetail) shotDetail.textContent = '分镜完成率（' + (s.shotsCompleted || 0) + '/' + (s.shotCount || 0) + '）';
      if (taskRate) taskRate.textContent = Math.round((s.taskSuccessRate || 0) * 100) + '%';
      if (taskDetail) taskDetail.textContent = '任务成功率（' + (s.tasksDone || 0) + ' 成功/' + (s.tasksFailed || 0) + ' 失败）';
      if (renderTime) {
        var secs = s.totalRenderSeconds || 0;
        renderTime.textContent = Math.floor(secs / 60) + ':' + String(secs % 60).padStart(2, '0');
      }
    }).catch(function (err) {
      toast('加载统计失败：' + err.message);
    });
  }

  function refreshAll() {
    return loadProjects().then(loadPipeline).then(loadStats);
  }

  function renderPipeline() {
    var body = document.getElementById('pipelineBody');
    var empty = document.getElementById('boardEmpty');
    var titleEl = document.getElementById('projectTitle');
    var metaEl = document.getElementById('projectMeta');
    if (!body) return;

    var data = state.pipeline;

    if (titleEl) {
      titleEl.textContent = (data && data.title) || '生产看板';
    }

    var episodes = (data && data.episodes) || [];

    var stuckCount = 0;
    episodes.forEach(function (ep) {
      if (episodeIsStuck(ep)) stuckCount++;
    });

    if (metaEl) {
      metaEl.innerHTML = '共 <span class="fw-bold">' + pad2(episodes.length) + '</span> 集，卡点 <span class="fw-bold">' + pad2(stuckCount) + '</span> 集。';
    }

    body.innerHTML = '';

    if (!episodes.length) {
      if (empty) {
        empty.classList.remove('d-none');
        empty.textContent = '还没有剧集数据。';
      }
      return;
    }

    if (empty) empty.classList.add('d-none');

    episodes.forEach(function (ep, idx) {
      body.appendChild(renderEpisodeRow(ep, idx));
    });
  }

  function renderEpisodeRow(ep, idx) {
    ep = ep || {};
    var shots = Number(ep.shotCount || 0);
    var pending = Number(ep.pendingTasks || 0);
    var rendering = Number(ep.processingTasks || 0);
    var done = Number(ep.doneTasks || 0);
    var failed = Number(ep.failedTasks || 0);

    var stuck = episodeIsStuck(ep);

    var num = (typeof ep.episodeNo !== 'undefined' && ep.episodeNo !== null)
      ? ep.episodeNo
      : (idx + 1);

    var tr = document.createElement('tr');
    if (stuck) tr.classList.add('table-warning');

    var tdNo = document.createElement('td');
    tdNo.className = 'text-nowrap';
    tdNo.textContent = '第 ' + num + ' 集';
    tr.appendChild(tdNo);

    var tdTitle = document.createElement('td');
    var titleStrong = document.createElement('div');
    titleStrong.className = 'fw-medium';
    titleStrong.textContent = ep.title || ('第 ' + pad2(num) + ' 集');
    tdTitle.appendChild(titleStrong);
    if (stuck) {
      var stuckBadge = statusLine('dot-amber', '卡点');
      stuckBadge.className = 'status-line ms-2';
      tdTitle.appendChild(stuckBadge);
    }
    tr.appendChild(tdTitle);

    var tdStatus = document.createElement('td');
    var epStatusKey = (ep.status || '').toString().toUpperCase();
    var epStatusText = (ep.status || 'DRAFT').toString().toUpperCase();
    var epStatusDot = 'dot-gray';
    var epStatusLabel = epStatusText;
    if (epStatusKey === 'DRAFT') { epStatusDot = 'dot-gray'; epStatusLabel = '草稿'; }
    else if (epStatusKey === 'SCRIPTED') { epStatusDot = 'dot-blue'; epStatusLabel = '已编剧'; }
    else if (epStatusKey === 'GENERATING') { epStatusDot = 'dot-amber'; epStatusLabel = '生成中'; }
    else if (epStatusKey === 'GENERATED') { epStatusDot = 'dot-green'; epStatusLabel = '已生成'; }
    else if (epStatusKey === 'REVIEWED') { epStatusDot = 'dot-green'; epStatusLabel = '已过审'; }
    var statusLineEl = statusLine(epStatusDot, epStatusLabel);
    tdStatus.appendChild(statusLineEl);
    tr.appendChild(tdStatus);

    var tdShots = document.createElement('td');
    tdShots.className = 'text-end text-nowrap';
    tdShots.innerHTML = '<span class="fw-bold">' + shots + '</span> <span class="text-secondary">个镜头</span>';
    tr.appendChild(tdShots);

    var tdTasks = document.createElement('td');
    tdTasks.className = 'text-nowrap';

    function makeStat(label, count, dotClass) {
      var span = statusLine(dotClass, label + ' ' + count);
      span.className = 'status-line me-2';
      return span;
    }

    tdTasks.appendChild(makeStat('待提交', pending, 'dot-gray'));
    tdTasks.appendChild(makeStat('生成中', rendering, 'dot-blue'));
    tdTasks.appendChild(makeStat('已完成', done, 'dot-green'));
    tdTasks.appendChild(makeStat('失败', failed, failed > 0 ? 'dot-red' : 'dot-gray'));
    tr.appendChild(tdTasks);

    var tdFinal = document.createElement('td');
    tdFinal.className = 'text-nowrap';
    var fk = finalCutKey(ep.finalCutStatus);
    var finalDot = 'dot-gray';
    var finalLabel = finalCutText(ep.finalCutStatus);
    if (fk === 'READY') { finalDot = 'dot-green'; finalLabel = '已完成'; }
    else if (fk === 'BUILDING') { finalDot = 'dot-blue'; finalLabel = '剪辑中'; }
    else if (fk === 'FAILED') { finalDot = 'dot-red'; finalLabel = '失败'; }
    else if (fk === 'PENDING') { finalDot = 'dot-amber'; finalLabel = '待处理'; }
    var finalBadge = statusLine(finalDot, finalLabel);
    tdFinal.appendChild(finalBadge);
    tr.appendChild(tdFinal);

    var tdActions = document.createElement('td');
    tdActions.className = 'text-end';
    var btnGroup = document.createElement('div');
    btnGroup.className = 'btn-list justify-content-end row-actions';

    var epId = encodeURIComponent(ep.episodeId != null ? ep.episodeId : '');

    var a1 = document.createElement('a');
    a1.className = 'btn btn-sm btn-secondary';
    a1.href = '/storyboard.html?episodeId=' + epId;
    a1.textContent = '打开分镜板';
    btnGroup.appendChild(a1);

    var a2 = document.createElement('a');
    a2.className = 'btn btn-sm btn-quiet secondary-action';
    a2.href = '/tasks.html?episodeId=' + epId;
    a2.textContent = '查看任务';
    btnGroup.appendChild(a2);

    var a3 = document.createElement('a');
    a3.className = 'btn btn-sm btn-quiet secondary-action';
    a3.href = '/finals.html?episodeId=' + epId;
    a3.textContent = '成片库';
    btnGroup.appendChild(a3);

    tdActions.appendChild(btnGroup);
    tr.appendChild(tdActions);

    return tr;
  }

  function bind() {
    var sel = document.getElementById('projectSelect');
    if (sel) {
      sel.addEventListener('change', function () {
        state.projectId = sel.value;
        loadPipeline().then(loadStats);
      });
    }

    var refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        refreshAll();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    bind();
    refreshAll();
  });
})();

