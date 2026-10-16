(function () {
  'use strict';

  var PAGE_I18N = {
    'pipe.title': { 'zh-CN': '生产看板 · AI 短剧工坊', 'en': 'Production Board · AI Short Drama Studio' },
    'pipe.heading': { 'zh-CN': '生产看板', 'en': 'Production Board' },
    'pipe.selectProject': { 'zh-CN': '选择项目', 'en': 'Select project' },
    'pipe.statShotDetail': { 'zh-CN': '分镜完成率', 'en': 'Shot completion' },
    'pipe.statTaskDetail': { 'zh-CN': '任务成功率', 'en': 'Task success rate' },
    'pipe.statRenderTime': { 'zh-CN': '累计渲染时长', 'en': 'Total render time' },
    'pipe.boardTitle': { 'zh-CN': '剧集管线', 'en': 'Episode Pipeline' },
    'pipe.colEpisodeNo': { 'zh-CN': '集号', 'en': 'Episode' },
    'pipe.colTitle': { 'zh-CN': '标题', 'en': 'Title' },
    'pipe.colStatus': { 'zh-CN': '状态', 'en': 'Status' },
    'pipe.colShotCount': { 'zh-CN': '分镜数', 'en': 'Shots' },
    'pipe.colTasks': { 'zh-CN': '视频任务', 'en': 'Video tasks' },
    'pipe.colFinalCut': { 'zh-CN': '成片', 'en': 'Final cut' },
    'pipe.colActions': { 'zh-CN': '操作', 'en': 'Actions' },
    'pipe.empty': { 'zh-CN': '暂无剧集数据。', 'en': 'No episodes yet.' },
    'pipe.metaLine': { 'zh-CN': '共 {0} 集，卡点 {1} 集。', 'en': '{0} episodes, {1} stuck.' },
    'pipe.episodeNo': { 'zh-CN': '第 {0} 集', 'en': 'Episode {0}' },
    'pipe.episodeNoPadded': { 'zh-CN': '第 {0} 集', 'en': 'Episode {0}' },
    'pipe.stuck': { 'zh-CN': '卡点', 'en': 'Stuck' },
    'pipe.shotUnit': { 'zh-CN': '个镜头', 'en': 'shots' },
    'pipe.taskPending': { 'zh-CN': '待提交', 'en': 'Pending' },
    'pipe.taskProcessing': { 'zh-CN': '生成中', 'en': 'Generating' },
    'pipe.taskDone': { 'zh-CN': '已完成', 'en': 'Done' },
    'pipe.taskFailed': { 'zh-CN': '失败', 'en': 'Failed' },
    'pipe.statusDraft': { 'zh-CN': '草稿', 'en': 'Draft' },
    'pipe.statusScripted': { 'zh-CN': '已编剧', 'en': 'Scripted' },
    'pipe.statusGenerating': { 'zh-CN': '生成中', 'en': 'Generating' },
    'pipe.statusGenerated': { 'zh-CN': '已生成', 'en': 'Generated' },
    'pipe.statusReviewed': { 'zh-CN': '已过审', 'en': 'Reviewed' },
    'pipe.finalReady': { 'zh-CN': '已完成', 'en': 'Ready' },
    'pipe.finalBuilding': { 'zh-CN': '剪辑中', 'en': 'Editing' },
    'pipe.finalFailed': { 'zh-CN': '失败', 'en': 'Failed' },
    'pipe.finalPending': { 'zh-CN': '待处理', 'en': 'Pending' },
    'pipe.finalNone': { 'zh-CN': '未开始', 'en': 'Not started' },
    'pipe.openBoard': { 'zh-CN': '打开分镜板', 'en': 'Open storyboard' },
    'pipe.viewTasks': { 'zh-CN': '查看任务', 'en': 'View tasks' },
    'pipe.finalCutLibrary': { 'zh-CN': '成片库', 'en': 'Final cut library' },
    'pipe.toastLoadProjectsFailed': { 'zh-CN': '加载项目失败：{0}', 'en': 'Failed to load projects: {0}' },
    'pipe.toastLoadPipelineFailed': { 'zh-CN': '加载生产线失败：{0}', 'en': 'Failed to load pipeline: {0}' },
    'pipe.toastLoadStatsFailed': { 'zh-CN': '加载统计失败：{0}', 'en': 'Failed to load stats: {0}' },
    'pipe.projectFallback': { 'zh-CN': '项目 {0}', 'en': 'Project {0}' },
    'pipe.shotDetailFmt': { 'zh-CN': '分镜完成率（{0}/{1}）', 'en': 'Shot completion ({0}/{1})' },
    'pipe.taskDetailFmt': { 'zh-CN': '任务成功率（{0} 成功/{1} 失败）', 'en': 'Task success rate ({0} done / {1} failed)' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  function _fmt(key, zh, args) {
    var s = _t(key, zh);
    for (var i = 0; i < args.length; i++) {
      s = s.replace('{' + i + '}', args[i]);
    }
    return s;
  }

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
    if (!k) return _t('pipe.finalNone', '未开始');
    if (k === 'READY') return _t('pipe.finalReady', '已完成');
    if (k === 'BUILDING') return _t('pipe.finalBuilding', '剪辑中');
    if (k === 'FAILED') return _t('pipe.finalFailed', '失败');
    if (k === 'PENDING') return _t('pipe.finalPending', '待处理');
    return v;
  }

  function statusLine(spClass, text) {
    var s = document.createElement('span');
    s.className = 'status-pill ' + spClass;
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
      opt.textContent = p.title || _fmt('pipe.projectFallback', '项目 {0}', [p.id]);
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
      toast(_fmt('pipe.toastLoadProjectsFailed', '加载项目失败：{0}', [err.message]));
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
      toast(_fmt('pipe.toastLoadPipelineFailed', '加载生产线失败：{0}', [err.message]));
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
      if (shotDetail) shotDetail.textContent = _fmt('pipe.shotDetailFmt', '分镜完成率（{0}/{1}）', [(s.shotsCompleted || 0), (s.shotCount || 0)]);
      if (taskRate) taskRate.textContent = Math.round((s.taskSuccessRate || 0) * 100) + '%';
      if (taskDetail) taskDetail.textContent = _fmt('pipe.taskDetailFmt', '任务成功率（{0} 成功/{1} 失败）', [(s.tasksDone || 0), (s.tasksFailed || 0)]);
      if (renderTime) {
        var secs = s.totalRenderSeconds || 0;
        renderTime.textContent = Math.floor(secs / 60) + ':' + String(secs % 60).padStart(2, '0');
      }
    }).catch(function (err) {
      toast(_fmt('pipe.toastLoadStatsFailed', '加载统计失败：{0}', [err.message]));
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
      titleEl.textContent = (data && data.title) || _t('pipe.heading', '生产看板');
    }

    var episodes = (data && data.episodes) || [];

    var stuckCount = 0;
    episodes.forEach(function (ep) {
      if (episodeIsStuck(ep)) stuckCount++;
    });

    if (metaEl) {
      var metaTpl = _t('pipe.metaLine', '共 {0} 集，卡点 {1} 集。');
      var metaHtml = metaTpl
        .replace('{0}', '<span class="fw-bold">' + pad2(episodes.length) + '</span>')
        .replace('{1}', '<span class="fw-bold">' + pad2(stuckCount) + '</span>');
      metaEl.innerHTML = metaHtml;
    }

    body.innerHTML = '';

    if (!episodes.length) {
      if (empty) {
        empty.classList.remove('d-none');
        empty.innerHTML = '<i data-lucide="inbox"></i><span>' + _t('pipe.empty', '暂无剧集数据。') + '</span>';
        if (window.lucide) lucide.createIcons();
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
    tdNo.textContent = _fmt('pipe.episodeNo', '第 {0} 集', [num]);
    tr.appendChild(tdNo);

    var tdTitle = document.createElement('td');
    var titleStrong = document.createElement('div');
    titleStrong.className = 'fw-medium';
    titleStrong.textContent = ep.title || _fmt('pipe.episodeNoPadded', '第 {0} 集', [pad2(num)]);
    tdTitle.appendChild(titleStrong);
    if (stuck) {
      var stuckBadge = statusLine('sp-amber', _t('pipe.stuck', '卡点'));
      stuckBadge.className = 'status-pill sp-amber ms-2';
      tdTitle.appendChild(stuckBadge);
    }
    tr.appendChild(tdTitle);

    var tdStatus = document.createElement('td');
    var epStatusKey = (ep.status || '').toString().toUpperCase();
    var epStatusText = (ep.status || 'DRAFT').toString().toUpperCase();
    var epStatusPill = 'sp-gray';
    var epStatusLabel = epStatusText;
    if (epStatusKey === 'DRAFT') { epStatusPill = 'sp-gray'; epStatusLabel = _t('pipe.statusDraft', '草稿'); }
    else if (epStatusKey === 'SCRIPTED') { epStatusPill = 'sp-blue'; epStatusLabel = _t('pipe.statusScripted', '已编剧'); }
    else if (epStatusKey === 'GENERATING') { epStatusPill = 'sp-amber'; epStatusLabel = _t('pipe.statusGenerating', '生成中'); }
    else if (epStatusKey === 'GENERATED') { epStatusPill = 'sp-green'; epStatusLabel = _t('pipe.statusGenerated', '已生成'); }
    else if (epStatusKey === 'REVIEWED') { epStatusPill = 'sp-green'; epStatusLabel = _t('pipe.statusReviewed', '已过审'); }
    var statusLineEl = statusLine(epStatusPill, epStatusLabel);
    tdStatus.appendChild(statusLineEl);
    tr.appendChild(tdStatus);

    var tdShots = document.createElement('td');
    tdShots.className = 'text-end text-nowrap';
    tdShots.innerHTML = '<span class="fw-bold">' + shots + '</span> <span class="text-secondary">' + _t('pipe.shotUnit', '个镜头') + '</span>';
    tr.appendChild(tdShots);

    var tdTasks = document.createElement('td');
    tdTasks.className = 'text-nowrap';

    function makeStat(label, count, spClass) {
      var span = statusLine(spClass, label + ' ' + count);
      span.className = 'status-pill ' + spClass + ' me-2';
      return span;
    }

    tdTasks.appendChild(makeStat(_t('pipe.taskPending', '待提交'), pending, 'sp-gray'));
    tdTasks.appendChild(makeStat(_t('pipe.taskProcessing', '生成中'), rendering, 'sp-blue'));
    tdTasks.appendChild(makeStat(_t('pipe.taskDone', '已完成'), done, 'sp-green'));
    tdTasks.appendChild(makeStat(_t('pipe.taskFailed', '失败'), failed, failed > 0 ? 'sp-red' : 'sp-gray'));
    tr.appendChild(tdTasks);

    var tdFinal = document.createElement('td');
    tdFinal.className = 'text-nowrap';
    var fk = finalCutKey(ep.finalCutStatus);
    var finalPill = 'sp-gray';
    var finalLabel = finalCutText(ep.finalCutStatus);
    if (fk === 'READY') { finalPill = 'sp-green'; finalLabel = _t('pipe.finalReady', '已完成'); }
    else if (fk === 'BUILDING') { finalPill = 'sp-blue'; finalLabel = _t('pipe.finalBuilding', '剪辑中'); }
    else if (fk === 'FAILED') { finalPill = 'sp-red'; finalLabel = _t('pipe.finalFailed', '失败'); }
    else if (fk === 'PENDING') { finalPill = 'sp-amber'; finalLabel = _t('pipe.finalPending', '待处理'); }
    var finalBadge = statusLine(finalPill, finalLabel);
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
    a1.textContent = _t('pipe.openBoard', '打开分镜板');
    btnGroup.appendChild(a1);

    var a2 = document.createElement('a');
    a2.className = 'btn btn-sm btn-quiet secondary-action';
    a2.href = '/tasks.html?episodeId=' + epId;
    a2.textContent = _t('pipe.viewTasks', '查看任务');
    btnGroup.appendChild(a2);

    var a3 = document.createElement('a');
    a3.className = 'btn btn-sm btn-quiet secondary-action';
    a3.href = '/finals.html?episodeId=' + epId;
    a3.textContent = _t('pipe.finalCutLibrary', '成片库');
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

  if (window.DFI18N) {
    DFI18N.onLangChange(function () {
      renderProjectSelect();
      renderPipeline();
      loadStats();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (window.DFI18N) DFI18N.applyI18n(document);
    bind();
    refreshAll();
  });
})();
