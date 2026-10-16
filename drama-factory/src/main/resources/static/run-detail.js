(function () {
  'use strict';

  var PAGE_I18N = {
    'rund.loading': { 'zh-CN': '加载中…', 'en': 'Loading…' },
    'rund.titleFallback': { 'zh-CN': '运行详情', 'en': 'Run Detail' },
    'rund.logs': { 'zh-CN': '日志', 'en': 'Logs' },
    'rund.artifacts': { 'zh-CN': '产物', 'en': 'Artifacts' },
    'rund.summary': { 'zh-CN': '汇总', 'en': 'Summary' },
    'rund.timeline': { 'zh-CN': '执行时间线', 'en': 'Execution timeline' },
    'rund.totalTokens': { 'zh-CN': '总 Token', 'en': 'Total tokens' },
    'rund.totalCost': { 'zh-CN': '总费用', 'en': 'Total cost' },
    'rund.statusLabel': { 'zh-CN': '状态', 'en': 'Status' },
    'rund.createdAt': { 'zh-CN': '创建 ', 'en': 'Created ' },
    'rund.updatedAt': { 'zh-CN': '更新 ', 'en': 'Updated ' },
    'rund.projectId': { 'zh-CN': '项目 ', 'en': 'Project ' },
    'rund.noGoal': { 'zh-CN': '(无目标)', 'en': '(No goal)' },
    'rund.pause': { 'zh-CN': '暂停', 'en': 'Pause' },
    'rund.resume': { 'zh-CN': '继续', 'en': 'Resume' },
    'rund.cancel': { 'zh-CN': '取消', 'en': 'Cancel' },
    'rund.approve': { 'zh-CN': '通过', 'en': 'Approve' },
    'rund.reject': { 'zh-CN': '打回', 'en': 'Reject' },
    'rund.retryFailedSteps': { 'zh-CN': '重试失败步', 'en': 'Retry failed steps' },
    'rund.rerun': { 'zh-CN': '重跑', 'en': 'Rerun' },
    'rund.approvalBanner': { 'zh-CN': '质检等待人工审批', 'en': 'QC is waiting for manual approval' },
    'rund.notePlaceholder': { 'zh-CN': '备注（可选）', 'en': 'Note (optional)' },
    'rund.noSteps': { 'zh-CN': '暂无步骤', 'en': 'No steps yet' },
    'rund.noStepsDesc': { 'zh-CN': '运行开始后会显示各 Agent 的执行步骤。', 'en': 'Agent execution steps will appear once the run starts.' },
    'rund.expandFull': { 'zh-CN': '展开全文', 'en': 'Show all' },
    'rund.collapse': { 'zh-CN': '收起', 'en': 'Collapse' },
    'rund.inputSummary': { 'zh-CN': '输入摘要', 'en': 'Input summary' },
    'rund.outputSummary': { 'zh-CN': '输出摘要', 'en': 'Output summary' },
    'rund.toolCalls': { 'zh-CN': '工具调用', 'en': 'Tool calls' },
    'rund.colTool': { 'zh-CN': 'tool', 'en': 'tool' },
    'rund.colInput': { 'zh-CN': 'input', 'en': 'input' },
    'rund.colOutput': { 'zh-CN': 'output', 'en': 'output' },
    'rund.colLatency': { 'zh-CN': 'latencyMs', 'en': 'latencyMs' },
    'rund.estimated': { 'zh-CN': '（估算）', 'en': ' (estimated)' },
    'rund.retryStep': { 'zh-CN': '重试该步', 'en': 'Retry step' },
    'rund.script': { 'zh-CN': '剧本', 'en': 'Script' },
    'rund.shotsCount': { 'zh-CN': '分镜（', 'en': 'Shots (' },
    'rund.closeParen': { 'zh-CN': '）', 'en': ')' },
    'rund.noShots': { 'zh-CN': '暂无分镜', 'en': 'No shots yet' },
    'rund.videosCount': { 'zh-CN': '视频（', 'en': 'Videos (' },
    'rund.finalCutsCount': { 'zh-CN': '成片（', 'en': 'Final Cuts (' },
    'rund.noPreview': { 'zh-CN': '无预览', 'en': 'No preview' },
    'rund.costLabel': { 'zh-CN': '费用 ', 'en': 'Cost ' },
    'rund.download': { 'zh-CN': '下载', 'en': 'Download' },
    'rund.episodeNo': { 'zh-CN': '第 {n} 集', 'en': 'Episode {n}' },
    'rund.untitled': { 'zh-CN': '(无标题)', 'en': '(Untitled)' },
    'rund.seconds': { 'zh-CN': ' 秒', 'en': ' s' },
    'rund.durMs': { 'zh-CN': ' 毫秒', 'en': ' ms' },
    'rund.durSec': { 'zh-CN': ' 秒', 'en': ' s' },
    'rund.durMinSec': { 'zh-CN': ' 分 ', 'en': ' min ' },
    'rund.noRunSpecified': { 'zh-CN': '未指定运行，请从', 'en': 'No run specified. Go back to the ' },
    'rund.runListLink': { 'zh-CN': '运行列表', 'en': 'runs list' },
    'rund.enterFrom': { 'zh-CN': '进入。', 'en': ' to pick one.' },
    'rund.loadDetailFailed': { 'zh-CN': '加载运行详情失败', 'en': 'Failed to load run detail' },
    'rund.loadDetailFailedDetail': { 'zh-CN': '加载运行详情失败：', 'en': 'Failed to load run detail: ' },
    'rund.loadArtifactsFailed': { 'zh-CN': '加载产物失败：', 'en': 'Failed to load artifacts: ' },
    'rund.paused': { 'zh-CN': '已暂停', 'en': 'Paused' },
    'rund.resumed': { 'zh-CN': '已继续', 'en': 'Resumed' },
    'rund.cancelled': { 'zh-CN': '已取消', 'en': 'Cancelled' },
    'rund.approved': { 'zh-CN': '已通过', 'en': 'Approved' },
    'rund.rejected': { 'zh-CN': '已打回', 'en': 'Rejected' },
    'rund.confirmCancel': { 'zh-CN': '确认取消该运行？', 'en': 'Cancel this run?' },
    'rund.newRunCreated': { 'zh-CN': '已创建新运行', 'en': 'New run created' },
    'rund.actionFailed': { 'zh-CN': '操作失败：', 'en': 'Action failed: ' },
    'rund.stepRetried': { 'zh-CN': '已重试该步', 'en': 'Step retried' },
    'rund.retryFailed': { 'zh-CN': '重试失败：', 'en': 'Retry failed: ' },
    'rund.noFailedSteps': { 'zh-CN': '没有失败步骤', 'en': 'No failed steps' },
    'rund.retriedFailedSteps': { 'zh-CN': '已重试失败步', 'en': 'Failed steps retried' },
    'rund.logAtEnd': { 'zh-CN': '已到末尾', 'en': 'End of log' },
    'rund.logStreaming': { 'zh-CN': '持续读取中…', 'en': 'Streaming…' },
    'rund.logLoadFailed': { 'zh-CN': '日志加载失败：', 'en': 'Failed to load logs: ' },
    'rund.logLoadFailedShort': { 'zh-CN': '日志加载失败', 'en': 'Failed to load logs' },
    'rund.durUnitSecond': { 'zh-CN': ' 秒', 'en': ' s' },
    'rund.qcPrefix': { 'zh-CN': 'QC ', 'en': 'QC ' },
    'rund.episodeNoPlain': { 'zh-CN': '第 ', 'en': 'Episode ' },
    'rund.episodeNoSuffix': { 'zh-CN': ' 集', 'en': '' },
    'rund.status.SUCCEEDED': { 'zh-CN': '已完成', 'en': 'Succeeded' },
    'rund.status.FAILED': { 'zh-CN': '失败', 'en': 'Failed' },
    'rund.status.WAITING_APPROVAL': { 'zh-CN': '等待审批', 'en': 'Waiting for approval' },
    'rund.status.RUNNING': { 'zh-CN': '运行中', 'en': 'Running' },
    'rund.status.PAUSED': { 'zh-CN': '已暂停', 'en': 'Paused' },
    'rund.status.CANCELLED': { 'zh-CN': '已取消', 'en': 'Cancelled' },
    'rund.status.PENDING': { 'zh-CN': '待开始', 'en': 'Pending' }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  function statusLabel(status, fallback) {
    if (fallback) return fallback;
    var key = 'rund.status.' + status;
    var v = _t(key, status);
    return v === key ? (status || '') : v;
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
      el.style.opacity = '0'; el.style.transform = 'translateX(12px)';
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
    if (n < 1000) return n + _t('rund.durMs', ' 毫秒');
    if (n < 60000) return (n / 1000).toFixed(1) + _t('rund.durSec', ' 秒');
    var m = Math.floor(n / 60000), s = Math.round((n % 60000) / 1000);
    return m + _t('rund.durMinSec', ' 分 ') + s + _t('rund.durSec', ' 秒');
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
  function statusClass(status) {
    switch (status) {
      case 'SUCCEEDED': return 'badge-green';
      case 'FAILED': return 'badge-red';
      case 'WAITING_APPROVAL': return 'badge-amber';
      case 'RUNNING': return 'badge-blue';
      default: return 'badge-gray';
    }
  }
  function badge(status, label) {
    return '<span class="badge ' + statusClass(status) + '"><span class="dot"></span>' + esc(statusLabel(status, label)) + '</span>';
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

  var runId = new URLSearchParams(location.search).get('id');
  var pollTimer = null;
  var current = null; // {run, steps, projectId}
  var TERMINAL = { SUCCEEDED: 1, FAILED: 1, CANCELLED: 1 };

  /* ---------------- control buttons ---------------- */
  function renderControls(run) {
    var area = $('#controlArea');
    var html = '';
    var s = run.status;
    if (s === 'RUNNING') {
      html += '<button class="btn btn-secondary" data-act="pause"><i data-lucide="pause"></i>' + esc(_t('rund.pause', '暂停')) + '</button>';
      html += '<button class="btn btn-secondary" data-act="cancel"><i data-lucide="x-circle"></i>' + esc(_t('rund.cancel', '取消')) + '</button>';
    } else if (s === 'PAUSED') {
      html += '<button class="btn btn-secondary" data-act="resume"><i data-lucide="play"></i>' + esc(_t('rund.resume', '继续')) + '</button>';
      html += '<button class="btn btn-secondary" data-act="cancel"><i data-lucide="x-circle"></i>' + esc(_t('rund.cancel', '取消')) + '</button>';
    } else if (s === 'WAITING_APPROVAL') {
      html += '<button class="btn btn-secondary" data-act="approve"><i data-lucide="check"></i>' + esc(_t('rund.approve', '通过')) + '</button>';
      html += '<button class="btn btn-secondary" data-act="reject"><i data-lucide="x"></i>' + esc(_t('rund.reject', '打回')) + '</button>';
    } else if (s === 'FAILED' || s === 'CANCELLED') {
      var hasFailed = (current && current.steps || []).some(function (st) { return st.status === 'FAILED'; });
      if (hasFailed) html += '<button class="btn btn-secondary" data-act="retry-failed"><i data-lucide="rotate-cw"></i>' + esc(_t('rund.retryFailedSteps', '重试失败步')) + '</button>';
      html += '<button class="btn btn-secondary" data-act="rerun"><i data-lucide="refresh-cw"></i>' + esc(_t('rund.rerun', '重跑')) + '</button>';
    }
    area.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  }

  function renderBanner(run) {
    var area = $('#bannerArea');
    if (run.status !== 'WAITING_APPROVAL') { area.innerHTML = ''; return; }
    area.innerHTML =
      '<div class="banner">' +
        '<i data-lucide="shield-check"></i>' +
        '<span class="msg">' + esc(_t('rund.approvalBanner', '质检等待人工审批')) + '</span>' +
        '<input type="text" id="approveNote" data-i18n-ph="rund.notePlaceholder" placeholder="备注（可选）">' +
        '<button class="btn btn-secondary btn-sm" data-act="approve"><i data-lucide="check"></i>' + esc(_t('rund.approve', '通过')) + '</button>' +
        '<button class="btn btn-secondary btn-sm" data-act="reject"><i data-lucide="x"></i>' + esc(_t('rund.reject', '打回')) + '</button>' +
      '</div>';
    if (window.DFI18N) DFI18N.applyI18n(area);
    if (window.lucide) lucide.createIcons();
  }

  /* ---------------- steps timeline ---------------- */
  function parseTools(json) {
    if (!json) return null;
    try {
      var v = typeof json === 'string' ? JSON.parse(json) : json;
      if (!Array.isArray(v)) return null;
      return v;
    } catch (e) { return null; }
  }

  function renderSummary(text, key) {
    if (!text) return '';
    var long = String(text).length > 400;
    return '<div class="row"><div class="lbl">' + key + '</div>' +
      '<div class="summary-box' + (long ? ' collapsed' : '') + '" data-full="1">' + esc(text) + '</div>' +
      (long ? '<button class="expand-btn" data-expand="1">' + esc(_t('rund.expandFull', '展开全文')) + '</button>' : '') +
      '</div>';
  }

  function renderStep(step) {
    var cls = 'step s-' + String(step.status || '').toLowerCase();
    var html = '<div class="' + cls + '" data-step-id="' + esc(step.id) + '">';
    html += '<span class="dot"></span>';
    html += '<div class="step-card">';
    html += '<div class="step-head">' +
      '<span class="seq">#' + esc(step.seqNo) + '</span>' +
      (step.agentLabel ? '<span class="agent">' + esc(step.agentLabel) + '</span>' : '') +
      '<span class="name">' + esc(step.name || '') + '</span>' +
      '<span class="spacer"></span>' +
      (step.latencyMs != null ? '<span class="dur">' + esc(fmtDuration(step.latencyMs)) + '</span>' : '') +
      badge(step.status, step.statusLabel) +
      '<button class="btn btn-secondary btn-sm" data-logs="' + esc(step.id) + '"><i data-lucide="file-text"></i>' + esc(_t('rund.logs', '日志')) + '</button>' +
      '</div>';

    var body = '';
    if (step.status === 'FAILED' && step.errorMessage) {
      body += '<div class="err-box">' + esc(step.errorMessage) + '</div>';
      body += '<button class="btn btn-sm" data-retry="' + esc(step.id) + '"><i data-lucide="rotate-cw"></i>' + esc(_t('rund.retryStep', '重试该步')) + '</button>';
    }
    if (step.inputSummary) body += renderSummary(step.inputSummary, esc(_t('rund.inputSummary', '输入摘要')));
    if (step.outputSummary) body += renderSummary(step.outputSummary, esc(_t('rund.outputSummary', '输出摘要')));

    var tools = parseTools(step.toolCallsJson);
    if (tools && tools.length) {
      body += '<div class="row"><div class="lbl">' + esc(_t('rund.toolCalls', '工具调用')) + '</div>' +
        '<table class="tools"><thead><tr><th>' + esc(_t('rund.colTool', 'tool')) + '</th><th>' + esc(_t('rund.colInput', 'input')) + '</th><th>' + esc(_t('rund.colOutput', 'output')) + '</th><th>' + esc(_t('rund.colLatency', 'latencyMs')) + '</th></tr></thead><tbody>';
      tools.forEach(function (t) {
        body += '<tr>' +
          '<td>' + esc(t.tool || t.name || '') + '</td>' +
          '<td>' + esc(typeof t.input === 'string' ? t.input : JSON.stringify(t.input == null ? '' : t.input)) + '</td>' +
          '<td>' + esc(typeof t.output === 'string' ? t.output : JSON.stringify(t.output == null ? '' : t.output)) + '</td>' +
          '<td>' + esc(t.latencyMs == null ? '—' : t.latencyMs) + '</td>' +
        '</tr>';
      });
      body += '</tbody></table></div>';
    }

    var extra = '';
    if (step.tokensUsed != null || step.costCents != null) {
      extra = '<div class="row meta-grid">' +
        (step.tokensUsed != null ? '<span class="item"><i data-lucide="hash"></i>Token ' + esc(step.tokensUsed) + '</span>' : '') +
        (step.costCents != null ? '<span class="item"><i data-lucide="coins"></i>' + esc(fmtMoney(step.costCents)) + (step.costEstimated ? esc(_t('rund.estimated', '（估算）')) : '') + '</span>' : '') +
        '</div>';
    }

    if (body || extra) html += '<div class="step-body">' + body + extra + '</div>';
    html += '</div></div>';
    return html;
  }

  function renderTimeline(steps) {
    if (!steps || !steps.length) {
      return '<div class="card empty"><i data-lucide="list-tree"></i>' +
        '<div class="t">' + esc(_t('rund.noSteps', '暂无步骤')) + '</div><div class="d">' + esc(_t('rund.noStepsDesc', '运行开始后会显示各 Agent 的执行步骤。')) + '</div></div>';
    }
    var sorted = steps.slice().sort(function (a, b) { return (a.seqNo || 0) - (b.seqNo || 0); });
    return '<div class="timeline">' + sorted.map(renderStep).join('') + '</div>';
  }

  /* ---------------- detail render ---------------- */
  function renderDetail(data) {
    current = data;
    var run = data.run || {};
    document.title = (run.goal || _t('rund.titleFallback', '运行详情')) + ' · Drama Factory';

    $('#runGoal').textContent = run.goal || _t('rund.noGoal', '(无目标)');
    $('#runMeta').innerHTML =
      badge(run.status, run.statusLabel) +
      '<span class="item"><i data-lucide="clock"></i>' + esc(_t('rund.createdAt', '创建 ')) + esc(fmtTime(run.createdAt)) + '</span>' +
      '<span class="item"><i data-lucide="refresh-cw"></i>' + esc(_t('rund.updatedAt', '更新 ')) + esc(fmtTime(run.updatedAt)) + '</span>' +
      (run.projectId ? '<span class="item"><i data-lucide="film"></i>' + esc(_t('rund.projectId', '项目 ')) + esc(run.projectId) + '</span>' : '');

    renderControls(run);
    renderBanner(run);

    $('#detailBody').innerHTML =
      '<h2 class="section-title"><i data-lucide="activity"></i>' + esc(_t('rund.timeline', '执行时间线')) + '</h2>' +
      renderTimeline(data.steps);

    // summary
    $('#summarySection').hidden = false;
    $('#summaryArea').innerHTML =
      '<div class="kv"><span class="k">' + esc(_t('rund.totalTokens', '总 Token')) + '</span><span>' + esc(run.totalTokens == null ? '—' : run.totalTokens) + '</span></div>' +
      '<div class="kv"><span class="k">' + esc(_t('rund.totalCost', '总费用')) + '</span><span>' + esc(fmtMoney(run.totalCostCents)) + '</span></div>' +
      '<div class="kv"><span class="k">' + esc(_t('rund.statusLabel', '状态')) + '</span><span>' + esc(statusLabel(run.status, run.statusLabel) || '—') + '</span></div>';

    if (window.lucide) lucide.createIcons();
  }

  /* ---------------- artifacts ---------------- */
  function renderArtifacts(data) {
    var sec = $('#artifactsSection');
    var area = $('#artifactsArea');
    var eps = (data && data.episodes) || [];
    if (!eps.length) {
      sec.hidden = true;
      return;
    }
    sec.hidden = false;
    var html = '';
    eps.forEach(function (ep, idx) {
      html += '<div class="ep-card">';
      html += '<div class="ep-head" data-ep-toggle="' + idx + '">' +
        '<span class="no">' + esc(_t('rund.episodeNo', '第 {n} 集').replace('{n}', ep.episodeNo)) + '</span>' +
        '<span class="t">' + esc(ep.title || _t('rund.untitled', '(无标题)')) + '</span>' +
        '<i data-lucide="chevron-down"></i>' +
        '</div>';
      html += '<div class="ep-body" id="ep-body-' + idx + '" hidden>';

      if (ep.scriptText) {
        html += '<div class="sub">' + esc(_t('rund.script', '剧本')) + '</div><div class="script-box">' + esc(ep.scriptText) + '</div>';
      }

      var shots = ep.shots || [];
      html += '<div class="sub">' + esc(_t('rund.shotsCount', '分镜（')) + shots.length + esc(_t('rund.closeParen', '）')) + '</div>';
      if (shots.length) {
        html += '<div class="shot-list">';
        shots.forEach(function (sh) {
          html += '<div class="shot"><div class="h">' +
            '<span class="n">#' + esc(sh.shotNo) + '</span>' +
            (sh.shotSize ? '<span>' + esc(sh.shotSize) + '</span>' : '') +
            (sh.cameraMove ? '<span>' + esc(sh.cameraMove) + '</span>' : '') +
            (sh.durationSeconds != null ? '<span>' + esc(sh.durationSeconds) + esc(_t('rund.seconds', ' 秒')) + '</span>' : '') +
            '</div><div>' + esc(sh.description || '') + '</div></div>';
        });
        html += '</div>';
      } else {
        html += '<div class="dim" style="font-size:13px">' + esc(_t('rund.noShots', '暂无分镜')) + '</div>';
      }

      var videos = ep.videos || [];
      if (videos.length) {
        html += '<div class="sub">' + esc(_t('rund.videosCount', '视频（')) + videos.length + esc(_t('rund.closeParen', '）')) + '</div><div class="video-grid">';
        videos.forEach(function (v) {
          html += '<div class="video-item">' +
            (v.url ? '<video src="' + esc(v.url) + '" controls preload="metadata"></video>' : '<div class="dim" style="padding:24px;text-align:center">' + esc(_t('rund.noPreview', '无预览')) + '</div>') +
            '<div class="video-meta">' +
              '<div class="l"><span>' + esc(v.provider || '') + (v.modelUsed ? ' · ' + esc(v.modelUsed) : '') + '</span>' + badge(v.status, v.statusLabel) + '</div>' +
              '<div class="l"><span>' + esc(_t('rund.costLabel', '费用 ')) + esc(fmtMoney(v.costCents)) + '</span>' +
              (v.url ? '<a href="' + esc(v.url) + '" download>' + esc(_t('rund.download', '下载')) + '</a>' : '') + '</div>' +
            '</div></div>';
        });
        html += '</div>';
      }

      var cuts = ep.finalCuts || [];
      if (cuts.length) {
        html += '<div class="sub">' + esc(_t('rund.finalCutsCount', '成片（')) + cuts.length + esc(_t('rund.closeParen', '）')) + '</div><div class="video-grid">';
        cuts.forEach(function (c) {
          html += '<div class="video-item">' +
            (c.url ? '<video src="' + esc(c.url) + '" controls preload="metadata"></video>' : '<div class="dim" style="padding:24px;text-align:center">' + esc(_t('rund.noPreview', '无预览')) + '</div>') +
            '<div class="video-meta">' +
              '<div class="l"><span>' + esc(c.filePath || '') + '</span>' + badge(c.status, c.status) + '</div>' +
              '<div class="l"><span>' + esc(_t('rund.qcPrefix', 'QC ')) + esc(c.qcStatus || '—') + '</span><span>' + esc(c.durationSeconds == null ? '—' : c.durationSeconds + esc(_t('rund.seconds', ' 秒'))) + '</span></div>' +
              (c.qcNote ? '<div>' + esc(c.qcNote) + '</div>' : '') +
              (c.url ? '<div class="l"><a href="' + esc(c.url) + '" download>' + esc(_t('rund.download', '下载')) + '</a></div>' : '') +
            '</div></div>';
        });
        html += '</div>';
      }

      html += '</div></div>';
    });
    area.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  }

  async function loadArtifacts() {
    try {
      var data = await req('/api/runs/' + encodeURIComponent(runId) + '/artifacts');
      renderArtifacts(data);
    } catch (e) {
      var sec = $('#artifactsSection');
      sec.hidden = false;
      $('#artifactsArea').innerHTML = '<div class="error-box">' + esc(_t('rund.loadArtifactsFailed', '加载产物失败：')) + esc(e.message) + '</div>';
    }
  }

  /* ---------------- logs drawer ---------------- */
  var logState = { stepId: null, offset: 0, eof: false, timer: null };

  function openDrawer(stepId, title) {
    closeLogPolling();
    logState = { stepId: stepId, offset: 0, eof: false, timer: null };
    $('#drawerTitle').textContent = title || _t('rund.logs', '日志');
    $('#drawerBody').textContent = '';
    $('#drawerFoot').textContent = _t('c.loading', '加载中…');
    $('#drawer').classList.add('open');
    $('#drawerMask').classList.add('open');
    if (window.lucide) lucide.createIcons();
    pollLog();
  }

  function closeDrawer() {
    closeLogPolling();
    $('#drawer').classList.remove('open');
    $('#drawerMask').classList.remove('open');
  }

  function closeLogPolling() {
    if (logState.timer) { clearTimeout(logState.timer); logState.timer = null; }
  }

  async function pollLog() {
    if (!logState.stepId) return;
    try {
      var d = await req('/api/runs/' + encodeURIComponent(runId) + '/steps/' +
        encodeURIComponent(logState.stepId) + '/logs?offset=' + logState.offset);
      var body = $('#drawerBody');
      if (d.content) {
        body.textContent += d.content;
        body.scrollTop = body.scrollHeight;
      }
      if (d.nextOffset != null) logState.offset = d.nextOffset;
      logState.eof = !!d.eof;
      $('#drawerFoot').textContent = logState.eof ? _t('rund.logAtEnd', '已到末尾') : _t('rund.logStreaming', '持续读取中…');
      if (!logState.eof) {
        logState.timer = setTimeout(pollLog, 2000);
      }
    } catch (e) {
      $('#drawerFoot').textContent = _t('rund.logLoadFailed', '日志加载失败：') + e.message;
      toast(_t('rund.logLoadFailedShort', '日志加载失败'), 'err');
    }
  }

  /* ---------------- actions ---------------- */
  async function postAction(path, body) {
    var opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    return req(path, opts);
  }

  async function loadDetail() {
    try {
      var data = await req('/api/runs/' + encodeURIComponent(runId));
      renderDetail(data);
      return data;
    } catch (e) {
      $('#detailBody').innerHTML = '<div class="error-box"><i data-lucide="alert-triangle" style="width:15px;height:15px;vertical-align:-2px"></i> ' + esc(_t('rund.loadDetailFailedDetail', '加载运行详情失败：')) + esc(e.message) + '</div>';
      if (window.lucide) lucide.createIcons();
      toast(_t('rund.loadDetailFailed', '加载运行详情失败'), 'err');
      return null;
    }
  }

  function schedulePolling(run) {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (!run || TERMINAL[run.status]) return;
    pollTimer = setInterval(function () {
      loadDetail().then(function (data) {
        if (data && TERMINAL[data.run && data.run.status]) {
          clearInterval(pollTimer); pollTimer = null;
        }
      });
    }, 5000);
  }

  async function handleAction(act) {
    if (!runId) return;
    try {
      if (act === 'pause') { await postAction('/api/runs/' + runId + '/pause'); toast(_t('rund.paused', '已暂停'), 'ok'); }
      else if (act === 'resume') { await postAction('/api/runs/' + runId + '/resume'); toast(_t('rund.resumed', '已继续'), 'ok'); }
      else if (act === 'cancel') {
        if (!confirm(_t('rund.confirmCancel', '确认取消该运行？'))) return;
        await postAction('/api/runs/' + runId + '/cancel'); toast(_t('rund.cancelled', '已取消'), 'ok');
      }
      else if (act === 'approve' || act === 'reject') {
        var noteEl = $('#approveNote');
        var note = noteEl ? noteEl.value.trim() : '';
        await postAction('/api/runs/' + runId + '/approve', { approved: act === 'approve', note: note });
        toast(act === 'approve' ? _t('rund.approved', '已通过') : _t('rund.rejected', '已打回'), 'ok');
      }
      else if (act === 'rerun') {
        var goal = (current && current.run && current.run.goal) || '';
        var res = await postAction('/api/runs/' + runId + '/rerun', { goal: goal });
        toast(_t('rund.newRunCreated', '已创建新运行'), 'ok');
        if (res && res.runId) { location.href = '/run-detail.html?id=' + encodeURIComponent(res.runId); return; }
      }
      var data = await loadDetail();
      if (data) schedulePolling(data.run);
    } catch (e) {
      toast(_t('rund.actionFailed', '操作失败：') + e.message, 'err');
    }
  }

  async function handleRetryStep(stepId) {
    try {
      await postAction('/api/runs/' + runId + '/steps/' + encodeURIComponent(stepId) + '/retry');
      toast(_t('rund.stepRetried', '已重试该步'), 'ok');
      var data = await loadDetail();
      if (data) schedulePolling(data.run);
    } catch (e) {
      toast(_t('rund.retryFailed', '重试失败：') + e.message, 'err');
    }
  }

  async function handleRetryFailed() {
    if (!current) return;
    var failed = (current.steps || []).filter(function (s) { return s.status === 'FAILED'; });
    if (!failed.length) { toast(_t('rund.noFailedSteps', '没有失败步骤'), 'info'); return; }
    for (var i = 0; i < failed.length; i++) {
      try {
        await postAction('/api/runs/' + runId + '/steps/' + encodeURIComponent(failed[i].id) + '/retry');
      } catch (e) {
        toast(_t('rund.retryFailed', '重试失败：') + e.message, 'err');
      }
    }
    toast(_t('rund.retriedFailedSteps', '已重试失败步'), 'ok');
    var data = await loadDetail();
    if (data) schedulePolling(data.run);
  }

  /* ---------------- event wiring ---------------- */
  function bindEvents() {
    document.addEventListener('click', function (ev) {
      var t = ev.target.closest('[data-act],[data-retry],[data-logs],[data-expand],[data-ep-toggle]');
      if (!t) return;

      if (t.hasAttribute('data-act')) {
        ev.preventDefault();
        handleAction(t.getAttribute('data-act'));
        return;
      }
      if (t.hasAttribute('data-retry')) {
        ev.preventDefault();
        handleRetryStep(t.getAttribute('data-retry'));
        return;
      }
      if (t.hasAttribute('data-logs')) {
        ev.preventDefault();
        var stepId = t.getAttribute('data-logs');
        var stepEl = t.closest('.step');
        var nameEl = stepEl ? stepEl.querySelector('.name') : null;
        var seqEl = stepEl ? stepEl.querySelector('.seq') : null;
        openDrawer(stepId, (seqEl ? seqEl.textContent + ' ' : '') + (nameEl ? nameEl.textContent : _t('rund.logs', '日志')));
        return;
      }
      if (t.hasAttribute('data-expand')) {
        ev.preventDefault();
        var box = t.previousElementSibling;
        if (box) {
          var collapsed = box.classList.toggle('collapsed');
          t.textContent = collapsed ? _t('rund.expandFull', '展开全文') : _t('rund.collapse', '收起');
        }
        return;
      }
      if (t.hasAttribute('data-ep-toggle')) {
        var idx = t.getAttribute('data-ep-toggle');
        var body = document.getElementById('ep-body-' + idx);
        if (body) body.hidden = !body.hidden;
        return;
      }
    });

    $('#drawerClose').addEventListener('click', closeDrawer);
    $('#drawerMask').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') closeDrawer();
    });
  }

  /* ---------------- init ---------------- */
  async function init() {
    if (window.DFI18N) DFI18N.applyI18n();
    if (window.lucide) lucide.createIcons();
    bindEvents();

    if (!runId) {
      $('#detailBody').innerHTML = '<div class="state-empty"><i data-lucide="inbox"></i><span>' + esc(_t('rund.noRunSpecified', '未指定运行，请从')) + '<a href="/runs.html">' + esc(_t('rund.runListLink', '运行列表')) + '</a>' + esc(_t('rund.enterFrom', '进入。')) + '</span></div>';
      if (window.lucide) lucide.createIcons();
      return;
    }

    var data = await loadDetail();
    if (data) {
      schedulePolling(data.run);
      loadArtifacts();
    }

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        if (current) renderDetail(current);
        if (!$('#artifactsSection').hidden) loadArtifacts();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
