(function () {
  'use strict';

  function toast(msg, kind) {
    var el = document.getElementById('toast');
    if (!el) { alert(msg); return; }
    el.textContent = msg;
    el.className = 'toast' + (kind ? ' toast-' + kind : '');
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.hidden = true; }, 3200);
  }

  async function api(method, url, body) {
    var opt = { method: method, headers: {} };
    if (body !== undefined) {
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    var res;
    try {
      res = await fetch(url, opt);
    } catch (e) {
      toast('网络请求失败：' + url, 'danger');
      throw e;
    }
    if (!res.ok) {
      var text = '';
      try { text = await res.text(); } catch (e2) {}
      toast('请求出错 ' + res.status + '：' + (text || url), 'danger');
      throw new Error('HTTP ' + res.status);
    }
    if (res.status === 204) return null;
    var ct = res.headers.get('content-type') || '';
    if (ct.indexOf('application/json') === -1) return null;
    return res.json();
  }

  var state = {
    projects: [],
    currentProjectId: null,
    pipeline: null
  };

  var FINAL_CUT_LABELS = {
    NONE: '无',
    EDITING: '剪辑中',
    DONE: '已完成',
    FAILED: '失败',
    PENDING: '待处理'
  };

  function finalCutText(status) {
    if (!status) return '无';
    var key = String(status).toUpperCase();
    return FINAL_CUT_LABELS[key] || String(status);
  }

  function finalCutClass(status) {
    if (!status) return 'badge-muted';
    var key = String(status).toUpperCase();
    if (key === 'DONE') return 'badge-success';
    if (key === 'FAILED') return 'badge-danger';
    if (key === 'EDITING' || key === 'PENDING') return 'badge-warning';
    return 'badge-muted';
  }

  function episodeIsStuck(ep) {
    var failed = ep.failedTasks || 0;
    var pending = ep.pendingTasks || 0;
    var processing = ep.processingTasks || 0;
    var done = ep.doneTasks || 0;
    var shots = ep.shotCount || 0;
    if (failed > 0) return true;
    // 分镜数 > 已完成任务数 表示还有镜头没有产出视频
    if (shots > 0 && done < shots && pending === 0 && processing === 0) return true;
    return false;
  }

  function renderProjectSelect() {
    var sel = document.getElementById('projectSelect');
    sel.innerHTML = '';
    if (!state.projects.length) {
      var o = document.createElement('option');
      o.value = '';
      o.textContent = '（无项目）';
      sel.appendChild(o);
      sel.disabled = true;
      return;
    }
    sel.disabled = false;
    state.projects.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = (p.title || p.name || ('项目 ' + p.id));
      if (String(p.id) === String(state.currentProjectId)) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function renderPipeline() {
    var board = document.getElementById('board');
    var empty = document.getElementById('boardEmpty');
    // 空状态节点是 #board 的子节点，清空 innerHTML 会把它 detach；
    // 先暂存，渲染结束后再按需放回，避免二次调用时取不到而抛错。
    if (empty && empty.parentNode) empty.parentNode.removeChild(empty);
    board.innerHTML = '';

    var data = state.pipeline;
    if (!data || !data.episodes || !data.episodes.length) {
      if (empty) {
        board.appendChild(empty);
        empty.hidden = false;
      }
      return;
    }
    if (empty) {
      board.appendChild(empty);
      empty.hidden = true;
    }

    document.getElementById('projectTitle').textContent = data.title || '生产看板';
    var total = data.episodes.length;
    var stuck = data.episodes.filter(episodeIsStuck).length;
    document.getElementById('projectMeta').textContent =
      '共 ' + total + ' 集，卡点 ' + stuck + ' 集。';

    data.episodes.forEach(function (ep) {
      board.appendChild(renderEpisodeCard(ep));
    });
  }

  function renderEpisodeCard(ep) {
    var card = document.createElement('div');
    card.className = 'pipeline-card' + (episodeIsStuck(ep) ? ' is-stuck' : '');

    var head = document.createElement('div');
    head.className = 'pipeline-head';

    var titleWrap = document.createElement('div');
    titleWrap.className = 'pipeline-title';

    var noSpan = document.createElement('span');
    noSpan.className = 'ep-no';
    noSpan.textContent = '第 ' + (ep.episodeNo != null ? ep.episodeNo : '?') + ' 集';
    titleWrap.appendChild(noSpan);

    var tSpan = document.createElement('span');
    tSpan.className = 'ep-title';
    tSpan.textContent = ep.title || '（未命名）';
    titleWrap.appendChild(tSpan);

    var stBadge = document.createElement('span');
    stBadge.className = 'badge badge-muted';
    stBadge.textContent = ep.status || '未开始';
    titleWrap.appendChild(stBadge);

    if (episodeIsStuck(ep)) {
      var stuck = document.createElement('span');
      stuck.className = 'stuck-mark';
      stuck.textContent = '卡点';
      titleWrap.appendChild(stuck);
    }

    head.appendChild(titleWrap);
    card.appendChild(head);

    var flow = document.createElement('div');
    flow.className = 'pipeline-flow';

    // 阶段一：分镜
    var stageShots = document.createElement('div');
    stageShots.className = 'stage';
    stageShots.appendChild(stageLabel('分镜'));
    stageShots.appendChild(stageValue(String(ep.shotCount || 0) + ' 个镜头'));
    flow.appendChild(stageShots);

    flow.appendChild(arrow());

    // 阶段二：视频任务
    var stageTasks = document.createElement('div');
    stageTasks.className = 'stage';
    stageTasks.appendChild(stageLabel('视频任务'));
    var taskWrap = document.createElement('div');
    taskWrap.className = 'task-stats';
    taskWrap.appendChild(taskStat('待提交', ep.pendingTasks || 0, 'badge-muted'));
    taskWrap.appendChild(taskStat('生成中', ep.processingTasks || 0, 'badge-info'));
    taskWrap.appendChild(taskStat('已完成', ep.doneTasks || 0, 'badge-success'));
    taskWrap.appendChild(taskStat('失败', ep.failedTasks || 0, (ep.failedTasks || 0) > 0 ? 'badge-danger' : 'badge-muted'));
    stageTasks.appendChild(taskWrap);
    flow.appendChild(stageTasks);

    flow.appendChild(arrow());

    // 阶段三：成片
    var stageFinal = document.createElement('div');
    stageFinal.className = 'stage';
    stageFinal.appendChild(stageLabel('成片'));
    var finalBadge = document.createElement('span');
    finalBadge.className = 'badge ' + finalCutClass(ep.finalCutStatus);
    finalBadge.textContent = finalCutText(ep.finalCutStatus);
    stageFinal.appendChild(finalBadge);
    flow.appendChild(stageFinal);

    card.appendChild(flow);

    var actions = document.createElement('div');
    actions.className = 'pipeline-actions';
    var link = document.createElement('a');
    link.className = 'btn btn-link';
    link.href = '/storyboard.html?episodeId=' + encodeURIComponent(ep.episodeId);
    link.textContent = '打开分镜板';
    actions.appendChild(link);
    var linkTasks = document.createElement('a');
    linkTasks.className = 'btn btn-link';
    linkTasks.href = '/tasks.html?episodeId=' + encodeURIComponent(ep.episodeId);
    linkTasks.textContent = '查看任务';
    actions.appendChild(linkTasks);
    var linkFinals = document.createElement('a');
    linkFinals.className = 'btn btn-link';
    linkFinals.href = '/finals.html?episodeId=' + encodeURIComponent(ep.episodeId);
    linkFinals.textContent = '成片库';
    actions.appendChild(linkFinals);
    card.appendChild(actions);

    return card;
  }

  function stageLabel(text) {
    var el = document.createElement('div');
    el.className = 'stage-label';
    el.textContent = text;
    return el;
  }

  function stageValue(text) {
    var el = document.createElement('div');
    el.className = 'stage-value';
    el.textContent = text;
    return el;
  }

  function arrow() {
    var el = document.createElement('div');
    el.className = 'stage-arrow';
    el.textContent = '→';
    return el;
  }

  function taskStat(label, value, badgeClass) {
    var el = document.createElement('span');
    el.className = 'task-stat ' + badgeClass;
    el.textContent = label + ' ' + value;
    return el;
  }

  async function loadProjects() {
    var list = await api('GET', '/api/projects');
    state.projects = Array.isArray(list) ? list : (list && list.items) || [];
    if (!state.currentProjectId && state.projects.length) {
      state.currentProjectId = state.projects[0].id;
    }
    renderProjectSelect();
  }

  async function loadPipeline() {
    if (!state.currentProjectId) {
      state.pipeline = null;
      renderPipeline();
      document.getElementById('projectMeta').textContent = '还没有可查看的项目。';
      return;
    }
    var data = await api('GET', '/api/projects/' + encodeURIComponent(state.currentProjectId) + '/pipeline');
    state.pipeline = data;
    renderPipeline();
  }

  async function refreshAll() {
    try {
      await loadProjects();
      await loadPipeline();
    } catch (e) {
      // 错误提示已在 api() 中处理
    }
  }

  function bind() {
    document.getElementById('projectSelect').addEventListener('change', function (e) {
      state.currentProjectId = e.target.value || null;
      loadPipeline().catch(function () {});
    });
    document.getElementById('refreshBtn').addEventListener('click', function () {
      refreshAll();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    bind();
    refreshAll();
  });
})();
