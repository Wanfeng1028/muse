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

  function finalCutClass(v) {
    var k = finalCutKey(v);
    if (k === 'READY') return 'badge-success';
    if (k === 'BUILDING') return 'badge-info';
    if (k === 'FAILED') return 'badge-danger';
    if (k === 'PENDING') return 'badge-warning';
    return 'badge-muted';
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

  function refreshAll() {
    return loadProjects().then(loadPipeline);
  }

  function renderPipeline() {
    var board = document.getElementById('board');
    var empty = document.getElementById('boardEmpty');
    var titleEl = document.getElementById('projectTitle');
    var metaEl = document.getElementById('projectMeta');
    if (!board) return;

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
      metaEl.innerHTML = '共 <span class="timecode">' + pad2(episodes.length) + '</span> 集，卡点 <span class="timecode">' + pad2(stuckCount) + '</span> 集。';
    }

    // detach empty placeholder so we can re-insert it if needed
    if (empty && empty.parentNode) {
      empty.parentNode.removeChild(empty);
    }

    // clear previously rendered frames
    var old = board.querySelectorAll('.film-frame');
    for (var i = 0; i < old.length; i++) {
      board.removeChild(old[i]);
    }

    if (!episodes.length) {
      if (empty) {
        empty.textContent = '还没有剧集数据。';
        board.appendChild(empty);
      }
      return;
    }

    episodes.forEach(function (ep, idx) {
      var frame = renderEpisodeCard(ep, idx);
      board.appendChild(frame);
    });
  }

  function renderEpisodeCard(ep, idx) {
    ep = ep || {};
    var tasks = ep.tasks || {};
    var shots = Number(ep.shotCount || 0);
    var pending = Number(ep.pendingTasks || 0);
    var rendering = Number(ep.processingTasks || 0);
    var done = Number(ep.doneTasks || 0);
    var failed = Number(ep.failedTasks || 0);

    var stuck = episodeIsStuck(ep);

    var frame = document.createElement('div');
    frame.className = 'film-frame' + (stuck ? ' is-stuck' : '');

    // top perforation
    var perfTop = document.createElement('div');
    perfTop.className = 'film-perf';
    frame.appendChild(perfTop);

    // title row
    var titleRow = document.createElement('div');
    titleRow.className = 'film-title';

    var epNo = document.createElement('span');
    epNo.className = 'timecode';
    var num = (typeof ep.episodeNo !== 'undefined' && ep.episodeNo !== null)
      ? ep.episodeNo
      : (idx + 1);
    epNo.textContent = 'EP' + pad2(num);
    titleRow.appendChild(epNo);

    var titleText = document.createElement('span');
    titleText.textContent = ep.title || ('第 ' + pad2(num) + ' 集');
    titleRow.appendChild(titleText);

    var statusBadge = document.createElement('span');
    statusBadge.className = 'badge badge-muted';
    statusBadge.textContent = (ep.status || 'DRAFT').toString().toUpperCase();
    titleRow.appendChild(statusBadge);

    if (stuck) {
      var stuckTag = document.createElement('span');
      stuckTag.className = 'stuck-tag';
      stuckTag.textContent = '卡点';
      titleRow.appendChild(stuckTag);
    }

    frame.appendChild(titleRow);

    // strip with stages
    var strip = document.createElement('div');
    strip.className = 'film-strip';

    // stage 1: storyboard
    var stage1 = document.createElement('div');
    stage1.className = 'f-stage';
    var l1 = document.createElement('div');
    l1.className = 'f-stage-label';
    l1.textContent = '分镜';
    var v1 = document.createElement('div');
    v1.className = 'f-stage-value';
    v1.innerHTML = '<span class="timecode">' + shots + '</span> 个镜头';
    stage1.appendChild(l1);
    stage1.appendChild(v1);
    strip.appendChild(stage1);

    var arrow1 = document.createElement('div');
    arrow1.className = 'f-arrow';
    arrow1.textContent = '→';
    strip.appendChild(arrow1);

    // stage 2: video tasks
    var stage2 = document.createElement('div');
    stage2.className = 'f-stage';
    var l2 = document.createElement('div');
    l2.className = 'f-stage-label';
    l2.textContent = '视频任务';
    var v2 = document.createElement('div');
    v2.className = 'task-stats';

    function makeStat(label, count, extraClass) {
      var span = document.createElement('span');
      span.className = 'task-stat' + (extraClass ? ' ' + extraClass : '');
      var lbl = document.createElement('span');
      lbl.textContent = label + ' ';
      var numSpan = document.createElement('span');
      numSpan.className = 'badge ' + (extraClass || 'badge-muted');
      numSpan.textContent = String(count);
      span.appendChild(lbl);
      span.appendChild(numSpan);
      return span;
    }

    v2.appendChild(makeStat('待提交', pending, 'badge-muted'));
    v2.appendChild(makeStat('生成中', rendering, 'badge-info'));
    v2.appendChild(makeStat('已完成', done, 'badge-success'));
    v2.appendChild(makeStat('失败', failed, failed > 0 ? 'badge-danger' : 'badge-muted'));

    stage2.appendChild(l2);
    stage2.appendChild(v2);
    strip.appendChild(stage2);

    var arrow2 = document.createElement('div');
    arrow2.className = 'f-arrow';
    arrow2.textContent = '→';
    strip.appendChild(arrow2);

    // stage 3: final cut
    var stage3 = document.createElement('div');
    stage3.className = 'f-stage';
    var l3 = document.createElement('div');
    l3.className = 'f-stage-label';
    l3.textContent = '成片';
    var badge3 = document.createElement('span');
    badge3.className = 'badge ' + finalCutClass(ep.finalCutStatus);
    badge3.textContent = finalCutText(ep.finalCutStatus);
    stage3.appendChild(l3);
    stage3.appendChild(badge3);
    strip.appendChild(stage3);

    frame.appendChild(strip);

    // actions
    var actions = document.createElement('div');
    actions.className = 'film-actions';

    var epId = encodeURIComponent(ep.episodeId != null ? ep.episodeId : '');

    var a1 = document.createElement('a');
    a1.className = 'btn btn-sm';
    a1.href = '/storyboard.html?episodeId=' + epId;
    a1.textContent = '打开分镜板';
    actions.appendChild(a1);

    var a2 = document.createElement('a');
    a2.className = 'btn btn-sm';
    a2.href = '/tasks.html?episodeId=' + epId;
    a2.textContent = '查看任务';
    actions.appendChild(a2);

    var a3 = document.createElement('a');
    a3.className = 'btn btn-sm';
    a3.href = '/finals.html?episodeId=' + epId;
    a3.textContent = '成片库';
    actions.appendChild(a3);

    frame.appendChild(actions);

    // bottom perforation
    var perfBottom = document.createElement('div');
    perfBottom.className = 'film-perf';
    frame.appendChild(perfBottom);

    return frame;
  }

  function bind() {
    var sel = document.getElementById('projectSelect');
    if (sel) {
      sel.addEventListener('change', function () {
        state.projectId = sel.value;
        loadPipeline();
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
