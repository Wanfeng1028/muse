(function () {
  'use strict';

  var PAGE_I18N = {
    'run.title': { 'zh-CN': '运行列表', 'en': 'Runs' },
    'run.subtitle': { 'zh-CN': '创建与管理短剧生成运行，实时查看步骤进度与产物。', 'en': 'Create and manage drama generation runs, with live step progress and artifacts.' },
    'run.newRun': { 'zh-CN': '新建运行', 'en': 'New Run' },
    'run.collapse': { 'zh-CN': '收起', 'en': 'Collapse' },
    'run.goalLabel': { 'zh-CN': '目标', 'en': 'Goal' },
    'run.goalPlaceholder': { 'zh-CN': '做一部 3 集短剧，题材都市情感', 'en': 'A 3-episode drama, urban romance' },
    'run.goalHint': { 'zh-CN': '描述清楚题材、集数与风格，模型会据此生成分集计划。', 'en': 'Describe the genre, episode count, and style; the model uses this to plan the episodes.' },
    'run.previewPlan': { 'zh-CN': '预览计划', 'en': 'Preview Plan' },
    'run.confirmRun': { 'zh-CN': '确认执行', 'en': 'Confirm' },
    'run.refill': { 'zh-CN': '重新填写', 'en': 'Start Over' },
    'run.allRuns': { 'zh-CN': '全部运行', 'en': 'All Runs' },
    'run.statTotal': { 'zh-CN': '总运行数', 'en': 'Total runs' },
    'run.statRate': { 'zh-CN': '成功率', 'en': 'Success rate' },
    'run.statAvg': { 'zh-CN': '平均耗时', 'en': 'Avg. duration' },
    'run.emptyText': { 'zh-CN': '暂无运行，点击下方按钮创建第一条。', 'en': 'No runs yet. Use the button below to create your first one.' },
    'run.loadingPlan': { 'zh-CN': '正在生成计划…', 'en': 'Generating plan…' },
    'run.planFallback': { 'zh-CN': '模型不可用，已用模板计划。', 'en': 'Model unavailable; used the template plan.' },
    'run.noEpisodes': { 'zh-CN': '未生成分集计划', 'en': 'No episode plan was generated' },
    'run.episodeNo': { 'zh-CN': '第 {n} 集', 'en': 'Episode {n}' },
    'run.untitled': { 'zh-CN': '(无标题)', 'en': '(Untitled)' },
    'run.noGoal': { 'zh-CN': '(无目标)', 'en': '(No goal)' },
    'run.loadListFailed': { 'zh-CN': '加载运行列表失败', 'en': 'Failed to load runs' },
    'run.loadListFailedDetail': { 'zh-CN': '加载运行列表失败：', 'en': 'Failed to load runs: ' },
    'run.needGoal': { 'zh-CN': '请先输入目标', 'en': 'Enter a goal first' },
    'run.genPlanFailed': { 'zh-CN': '生成计划失败', 'en': 'Failed to generate plan' },
    'run.genPlanFailedDetail': { 'zh-CN': '生成计划失败：', 'en': 'Failed to generate plan: ' },
    'run.created': { 'zh-CN': '运行已创建', 'en': 'Run created' },
    'run.createFailed': { 'zh-CN': '创建运行失败：', 'en': 'Failed to create run: ' },
    'run.noRunId': { 'zh-CN': '未返回 runId', 'en': 'No runId returned' },
    'run.refreshed': { 'zh-CN': '已刷新', 'en': 'Refreshed' },
    'run.status.SUCCEEDED': { 'zh-CN': '已完成', 'en': 'Succeeded' },
    'run.status.FAILED': { 'zh-CN': '失败', 'en': 'Failed' },
    'run.status.WAITING_APPROVAL': { 'zh-CN': '等待审批', 'en': 'Waiting for approval' },
    'run.status.RUNNING': { 'zh-CN': '运行中', 'en': 'Running' },
    'run.status.PAUSED': { 'zh-CN': '已暂停', 'en': 'Paused' },
    'run.status.CANCELLED': { 'zh-CN': '已取消', 'en': 'Cancelled' },
    'run.status.PENDING': { 'zh-CN': '待开始', 'en': 'Pending' },
    'run.durMs': { 'zh-CN': ' 毫秒', 'en': ' ms' },
    'run.durSec': { 'zh-CN': ' 秒', 'en': ' s' },
    'run.durMinSec': { 'zh-CN': ' 分 ', 'en': ' min ' }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  var $ = function (s, r) { return (r || document).querySelector(s); };

  /* ---------------- toast ---------------- */
  function toast(msg, type) {
    type = type || 'info';
    var host = $('#toast-host');
    if (!host) return;
    var el = document.createElement('div');
    el.className = 'toast ' + type;
    var icon = type === 'ok' ? 'check-circle' : type === 'err' ? 'alert-circle' : 'info';
    el.innerHTML = '<i data-lucide="' + icon + '"></i><div></div>';
    el.lastChild.textContent = msg;
    host.appendChild(el);
    if (window.lucide) lucide.createIcons();
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transform = 'translateX(12px)';
      el.style.transition = 'all .2s';
      setTimeout(function () { el.remove(); }, 220);
    }, 2800);
  }

  /* ---------------- utils ---------------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function truncate(s, n) {
    s = String(s == null ? '' : s);
    return s.length > n ? s.slice(0, n) + '…' : s;
  }
  function fmtMoney(cents) {
    if (cents == null || cents === '') return '—';
    var n = Number(cents);
    if (isNaN(n)) return '—';
    return '¥' + (n / 100).toFixed(2);
  }
  function fmtDuration(ms) {
    if (ms == null) return '—';
    var n = Number(ms);
    if (isNaN(n)) return '—';
    if (n < 1000) return n + _t('run.durMs', ' 毫秒');
    if (n < 60000) return (n / 1000).toFixed(1) + _t('run.durSec', ' 秒');
    var m = Math.floor(n / 60000), s = Math.round((n % 60000) / 1000);
    return m + _t('run.durMinSec', ' 分 ') + s + _t('run.durSec', ' 秒');
  }
  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    function p(n) {
      return n < 10 ? '0' + n : '' + n;
    }
    return (
      d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
      ' ' + p(d.getHours()) + ':' + p(d.getMinutes())
    );
  }

  /* run/step status -> badge class */
  function statusClass(status) {
    switch (status) {
      case 'SUCCEEDED': return 'badge-green';
      case 'FAILED': return 'badge-red';
      case 'WAITING_APPROVAL': return 'badge-amber';
      case 'RUNNING': return 'badge-blue';
      default: return 'badge-gray';
    }
  }

  function statusLabel(status, fallback) {
    if (fallback) return fallback;
    var key = 'run.status.' + status;
    var v = _t(key, status);
    return v === key ? (status || '') : v;
  }

  async function req(url, opts) {
    var res = await fetch(url, opts);
    if (!res.ok) {
      var t = '';
      try { t = await res.text(); } catch (e) {}
      throw new Error('HTTP ' + res.status + (t ? ' · ' + t.slice(0, 160) : ''));
    }
    var ct = res.headers.get('content-type') || '';
    if (ct.indexOf('application/json') >= 0) return res.json();
    return res.text();
  }

  /* ---------------- stats ---------------- */
  async function loadStats() {
    var bar = $('#statsBar');
    try {
      var s = await req('/api/runs/stats');
      if (!s || s.totalRuns == null) { bar.innerHTML = ''; return; }
      var rate = s.successRate == null ? '—' : (Math.round(Number(s.successRate) * 1000) / 10) + '%';
      bar.className = 'stats-strip';
      bar.innerHTML =
        esc(_t('run.statTotal', '总运行数')) + ' ' + esc(s.totalRuns) + '<span class="sep">·</span>' +
        esc(_t('run.statRate', '成功率')) + ' ' + esc(rate) + '<span class="sep">·</span>' +
        esc(_t('run.statAvg', '平均耗时')) + ' ' + esc(fmtDuration(s.avgDurationMs));
      if (window.lucide) lucide.createIcons();
      if (window.DFI18N) DFI18N.applyI18n(bar);
    } catch (e) {
      bar.innerHTML = '';
    }
  }

  /* ---------------- run list ---------------- */
  function renderEmpty() {
    return '<div class="state-empty">' +
      '<i data-lucide="inbox"></i>' +
      '<span>' + esc(_t('run.emptyText', '暂无运行，点击下方按钮创建第一条。')) + '</span>' +
      '<button class="btn btn-primary" id="emptyNewBtn"><i data-lucide="plus"></i>' + esc(_t('run.newRun', '新建运行')) + '</button>' +
      '</div>';
  }

  function renderRuns(runs) {
    var list = $('#listArea');
    var toolbarBtn = $('#newRunBtn');
    if (!runs || !runs.length) {
      list.innerHTML = renderEmpty();
      if (window.lucide) lucide.createIcons();
      var b = $('#emptyNewBtn');
      if (b) b.addEventListener('click', openWizard);
      if (toolbarBtn) toolbarBtn.style.display = 'none';
      return;
    }
    if (toolbarBtn) toolbarBtn.style.display = '';
    var html = '<div class="run-list">';
    runs.forEach(function (r) {
      var badge = '<span class="badge ' + statusClass(r.status) + '"><span class="dot"></span>' + esc(statusLabel(r.status, r.statusLabel)) + '</span>';
      html += '<a class="run-row" href="/run-detail.html?id=' + encodeURIComponent(r.id) + '">' +
        '<div class="goal">' + esc(truncate(r.goal || _t('run.noGoal', '(无目标)'), 80)) + '</div>' +
        '<div class="run-meta">' +
          '<span class="item">' + badge + '</span>' +
          '<span class="item"><i data-lucide="coins"></i>' + esc(fmtMoney(r.totalCostCents)) + '</span>' +
          '<span class="item"><i data-lucide="clock"></i>' + esc(fmtTime(r.createdAt)) + '</span>' +
        '</div>' +
      '</a>';
    });
    html += '</div>';
    list.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  }

  async function loadRuns() {
    var list = $('#listArea');
    try {
      var runs = await req('/api/runs');
      renderRuns(runs);
    } catch (e) {
      list.innerHTML = '<div class="error-box"><i data-lucide="alert-triangle"></i> ' + esc(_t('run.loadListFailedDetail', '加载运行列表失败：')) + esc(e.message) + '</div>';
      if (window.lucide) lucide.createIcons();
      toast(_t('run.loadListFailed', '加载运行列表失败'), 'err');
    }
  }

  /* ---------------- wizard ---------------- */
  var lastPlan = null;

  function openWizard() {
    var w = $('#wizard');
    w.hidden = false;
    w.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    $('#goalInput').focus();
  }

  function closeWizard() {
    $('#wizard').hidden = true;
  }

  function resetWizard() {
    lastPlan = null;
    $('#goalInput').value = '';
    $('#planArea').innerHTML = '';
    $('#confirmBtn').hidden = true;
    $('#wizardReset').hidden = true;
    $('#previewBtn').disabled = false;
  }

  async function doPreview() {
    var goal = $('#goalInput').value.trim();
    if (!goal) { toast(_t('run.needGoal', '请先输入目标'), 'err'); return; }
    var btn = $('#previewBtn');
    var area = $('#planArea');
    btn.disabled = true;
    area.innerHTML = '<div class="loading"><span class="spinner"></span>' + esc(_t('run.loadingPlan', '正在生成计划…')) + '</div>';
    try {
      var plan = await req('/api/runs/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal })
      });
      lastPlan = plan;
      renderPlan(plan);
      $('#confirmBtn').hidden = false;
      $('#wizardReset').hidden = false;
    } catch (e) {
      area.innerHTML = '<div class="error-box"><i data-lucide="alert-triangle"></i> ' + esc(_t('run.genPlanFailedDetail', '生成计划失败：')) + esc(e.message) + '</div>';
      if (window.lucide) lucide.createIcons();
      toast(_t('run.genPlanFailed', '生成计划失败'), 'err');
    } finally {
      btn.disabled = false;
    }
  }

  function renderPlan(plan) {
    var area = $('#planArea');
    var html = '';
    if (plan && plan.fallback) {
      html += '<div class="notice notice-amber"><i data-lucide="alert-triangle"></i><div>' + esc(_t('run.planFallback', '模型不可用，已用模板计划。')) + '</div></div>';
    }
    var eps = (plan && plan.episodes) || [];
    if (!eps.length) {
      html += '<div class="empty"><div class="d">' + esc(_t('run.noEpisodes', '未生成分集计划')) + '</div></div>';
    } else {
      eps.forEach(function (ep) {
        html += '<div class="plan-ep">' +
          '<div class="no">' + esc(_t('run.episodeNo', '第 {n} 集').replace('{n}', ep.episodeNo)) + '</div>' +
          '<div class="t">' + esc(ep.title || _t('run.untitled', '(无标题)')) + '</div>' +
          '<div class="o">' + esc(ep.outline || '') + '</div>' +
        '</div>';
      });
    }
    area.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  }

  async function doConfirm() {
    var goal = $('#goalInput').value.trim();
    if (!goal) { toast(_t('run.needGoal', '请先输入目标'), 'err'); return; }
    var btn = $('#confirmBtn');
    btn.disabled = true;
    try {
      var res = await req('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal, plan: lastPlan })
      });
      var runId = res && res.runId;
      if (!runId) throw new Error(_t('run.noRunId', '未返回 runId'));
      toast(_t('run.created', '运行已创建'), 'ok');
      location.href = '/run-detail.html?id=' + encodeURIComponent(runId);
    } catch (e) {
      toast(_t('run.createFailed', '创建运行失败：') + e.message, 'err');
      btn.disabled = false;
    }
  }

  /* ---------------- init ---------------- */
  function init() {
    if (window.DFI18N) DFI18N.applyI18n();
    if (window.lucide) lucide.createIcons();

    $('#newRunBtn').addEventListener('click', openWizard);
    $('#refreshBtn').addEventListener('click', function () {
      loadStats();
      loadRuns();
      toast(_t('run.refreshed', '已刷新'), 'ok');
    });
    $('#wizardClose').addEventListener('click', closeWizard);
    $('#previewBtn').addEventListener('click', doPreview);
    $('#confirmBtn').addEventListener('click', doConfirm);
    $('#wizardReset').addEventListener('click', function () {
      resetWizard();
      $('#goalInput').focus();
    });

    loadStats();
    loadRuns();

    /* hash 动作：#act=new-run 时自动展开新建向导 */
    if ((window.location.hash || '') === '#act=new-run') {
      window.location.hash = '';
      openWizard();
      setTimeout(function () { var g = $('#goalInput'); if (g) g.focus(); }, 300);
    }

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        loadStats();
        loadRuns();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
