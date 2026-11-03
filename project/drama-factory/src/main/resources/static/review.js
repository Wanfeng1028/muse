(function () {
  'use strict';

  var PAGE_I18N = {
    'review.pageTitle': { 'zh-CN': '审核队列 · AI 短剧工坊', en: 'Review Queue · AI Short Drama Studio' },
    'review.heading': { 'zh-CN': '审核队列', en: 'Review Queue' },
    'review.project': { 'zh-CN': '项目', en: 'Project' },
    'review.kind': { 'zh-CN': '类型', en: 'Kind' },
    'review.status': { 'zh-CN': '状态', en: 'Status' },
    'review.episode': { 'zh-CN': '剧集', en: 'Episode' },
    'review.newKind': { 'zh-CN': '审核类型', en: 'Review kind' },
    'review.submitReview': { 'zh-CN': '发起审核', en: 'Submit for review' },
    'review.kindAll': { 'zh-CN': '全部', en: 'All' },
    'review.kindScript': { 'zh-CN': '剧本', en: 'Script' },
    'review.kindBoard': { 'zh-CN': '分镜', en: 'Board' },
    'review.statusAll': { 'zh-CN': '全部', en: 'All' },
    'review.statusDraft': { 'zh-CN': '草稿', en: 'Draft' },
    'review.statusPendingL1': { 'zh-CN': '待一审', en: 'Pending L1' },
    'review.statusPendingL2': { 'zh-CN': '待二审', en: 'Pending L2' },
    'review.statusPending': { 'zh-CN': '待审核', en: 'Pending' },
    'review.statusApproved': { 'zh-CN': '已通过', en: 'Approved' },
    'review.statusRejected': { 'zh-CN': '已驳回', en: 'Rejected' },
    'review.statusUnknown': { 'zh-CN': '未知', en: 'Unknown' },
    'review.colEpisodeNo': { 'zh-CN': '集号', en: 'No.' },
    'review.colTitle': { 'zh-CN': '标题', en: 'Title' },
    'review.colKind': { 'zh-CN': '类型', en: 'Kind' },
    'review.colStatus': { 'zh-CN': '状态', en: 'Status' },
    'review.colSubmittedBy': { 'zh-CN': '提交人', en: 'Submitted by' },
    'review.colActions': { 'zh-CN': '操作', en: 'Actions' },
    'review.view': { 'zh-CN': '查看', en: 'View' },
    'review.emptyHint': { 'zh-CN': '这里还没有需要审核的内容，先去剧集页生成剧本吧', en: 'Nothing to review here yet — generate a script from the episodes page first.' },
    'review.episodeHash': { 'zh-CN': '第', en: 'Episode ' },
    'review.episodeHashSuffix': { 'zh-CN': ' 集', en: '' },
    'review.submittedBy': { 'zh-CN': '提交人', en: 'Submitted by' },
    'review.l1Reviewer': { 'zh-CN': '一审人', en: 'L1 reviewer' },
    'review.l2Reviewer': { 'zh-CN': '二审人', en: 'L2 reviewer' },
    'review.version': { 'zh-CN': '版本', en: 'Version' },
    'review.lastComment': { 'zh-CN': '最后意见', en: 'Last comment' },
    'review.history': { 'zh-CN': '审核历史', en: 'Review history' },
    'review.comment': { 'zh-CN': '意见', en: 'Comment' },
    'review.commentPh': { 'zh-CN': '审核意见 / 驳回原因', en: 'Review comment / reason for rejection' },
    'review.selfReviewed': { 'zh-CN': '这是你自己提交的内容，系统已记下自审', en: 'You submitted this yourself — the system recorded it as self-review.' },
    'review.submit': { 'zh-CN': '提交审核', en: 'Submit for review' },
    'review.l1Approve': { 'zh-CN': '一审通过', en: 'L1 approve' },
    'review.l1Reject': { 'zh-CN': '一审驳回', en: 'L1 reject' },
    'review.l2Approve': { 'zh-CN': '二审通过', en: 'L2 approve' },
    'review.l2Reject': { 'zh-CN': '二审驳回', en: 'L2 reject' },
    'review.approve': { 'zh-CN': '通过', en: 'Approve' },
    'review.reject': { 'zh-CN': '驳回', en: 'Reject' },
    'review.alreadyApproved': { 'zh-CN': '已通过', en: 'Approved' },
    'review.rejectedHint': { 'zh-CN': '已驳回，可重新生成剧本后再提交', en: 'Rejected — regenerate the script before submitting again.' },
    'review.evSubmit': { 'zh-CN': '提交审核', en: 'Submitted' },
    'review.evL1Approve': { 'zh-CN': '一审通过', en: 'L1 approved' },
    'review.evL1Reject': { 'zh-CN': '一审驳回', en: 'L1 rejected' },
    'review.evL2Approve': { 'zh-CN': '二审通过', en: 'L2 approved' },
    'review.evL2Reject': { 'zh-CN': '二审驳回', en: 'L2 rejected' },
    'review.evApprove': { 'zh-CN': '通过', en: 'Approved' },
    'review.evReject': { 'zh-CN': '驳回', en: 'Rejected' },
    'review.evRegenerate': { 'zh-CN': '重新生成（打回草稿）', en: 'Regenerated (back to draft)' },
    'review.okToast': { 'zh-CN': '操作成功', en: 'Done' },
    'review.conflictToast': { 'zh-CN': '数据有变化，请刷新重试', en: 'Data changed — please refresh and try again.' },
    'review.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'review.actionFailed': { 'zh-CN': '操作失败', en: 'Action failed' },
    'review.noData': { 'zh-CN': '（无）', en: '(none)' },
    'review.noProject': { 'zh-CN': '没有项目', en: 'No project' },
    'review.pickEpisode': { 'zh-CN': '请选择剧集', en: 'Pick an episode' },
    'review.noEpisode': { 'zh-CN': '没有剧集', en: 'No episodes' },
    'review.continuity': { 'zh-CN': '分镜连续性检查', en: 'Shot continuity check' },
    'review.continuityShot': { 'zh-CN': '镜号', en: 'Shot' },
    'review.continuitySeverity': { 'zh-CN': '级别', en: 'Severity' },
    'review.continuityRule': { 'zh-CN': '规则', en: 'Rule' },
    'review.continuityIssue': { 'zh-CN': '问题', en: 'Issue' },
    'review.continuitySuggestion': { 'zh-CN': '建议', en: 'Suggestion' },
    'review.continuityNone': { 'zh-CN': '未发现连续性问题', en: 'No continuity issues found' },
    'review.continuityChecked': { 'zh-CN': '已检查', en: 'Checked' },
    'review.continuityShotsUnit': { 'zh-CN': '镜', en: 'shots' },
    'review.continuityIssuesUnit': { 'zh-CN': '个问题', en: 'issues' },
    'review.sevWarn': { 'zh-CN': '警告', en: 'Warning' },
    'review.sevInfo': { 'zh-CN': '提示', en: 'Info' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N && typeof DFI18N.tr === 'function') {
      var v = DFI18N.tr(key);
      if (v && v !== key) return v;
    }
    return zh;
  }

  function applyI18nTo(root) {
    if (window.DFI18N && typeof DFI18N.applyI18n === 'function') {
      DFI18N.applyI18n(root);
    }
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

  async function api(path, options) {
    var res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...(options || {})
    });
    var data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      var err = new Error((data && data.message) || _t('review.actionFailed', '操作失败'));
      err.status = res.status;
      throw err;
    }
    return data;
  }

  var toastTimer = null;
  function showToast(message) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = message;
    el.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.classList.remove('show');
    }, 2600);
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    function p(n) { return n < 10 ? '0' + n : '' + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function statusPill(status) {
    var text, cls;
    switch (status) {
      case 'DRAFT':
        cls = 'sp-gray'; text = _t('review.statusDraft', '草稿'); break;
      case 'PENDING_L1':
        cls = 'sp-amber'; text = _t('review.statusPendingL1', '待一审'); break;
      case 'PENDING_L2':
        cls = 'sp-amber'; text = _t('review.statusPendingL2', '待二审'); break;
      case 'PENDING':
        cls = 'sp-amber'; text = _t('review.statusPending', '待审核'); break;
      case 'APPROVED':
        cls = 'sp-green'; text = _t('review.statusApproved', '已通过'); break;
      case 'REJECTED':
        cls = 'sp-red'; text = _t('review.statusRejected', '已驳回'); break;
      default:
        cls = 'sp-gray'; text = status || _t('review.statusUnknown', '未知'); break;
    }
    return '<span class="status-pill ' + cls + '">' + escapeHtml(text) + '</span>';
  }

  function kindText(kind) {
    if (kind === 'SCRIPT') return _t('review.kindScript', '剧本');
    if (kind === 'BOARD') return _t('review.kindBoard', '分镜');
    return kind || '-';
  }

  function eventText(event) {
    switch (event) {
      case 'SUBMIT': return _t('review.evSubmit', '提交审核');
      case 'L1_APPROVE': return _t('review.evL1Approve', '一审通过');
      case 'L1_REJECT': return _t('review.evL1Reject', '一审驳回');
      case 'L2_APPROVE': return _t('review.evL2Approve', '二审通过');
      case 'L2_REJECT': return _t('review.evL2Reject', '二审驳回');
      case 'APPROVE': return _t('review.evApprove', '通过');
      case 'REJECT': return _t('review.evReject', '驳回');
      case 'REGENERATE': return _t('review.evRegenerate', '重新生成（打回草稿）');
      default: return event || '-';
    }
  }

  var state = {
    projectId: null,
    current: null,
    version: 0,
    currentEpisodeId: null,
    currentKind: null
  };

  async function loadProjects() {
    var sel = document.getElementById('projectSelect');
    try {
      var list = await api('/api/projects');
      sel.innerHTML = '';
      if (!list || !list.length) {
        var opt = document.createElement('option');
        opt.value = '';
        opt.textContent = _t('review.noProject', '没有项目');
        sel.appendChild(opt);
        return;
      }
      list.forEach(function (p) {
        var o = document.createElement('option');
        o.value = p.id;
        o.textContent = p.title || ('#' + p.id);
        sel.appendChild(o);
      });
      state.projectId = list[0].id;
      sel.value = state.projectId;
      await loadEpisodes();
      await loadQueue();
    } catch (err) {
      showToast(err.message || _t('review.loadFailed', '加载失败'));
    }
  }

  async function loadEpisodes() {
    var sel = document.getElementById('episodeSelect');
    sel.innerHTML = '';
    if (!state.projectId) return;
    try {
      var list = await api('/api/projects/' + encodeURIComponent(state.projectId) + '/episodes');
      if (!list || !list.length) {
        var opt = document.createElement('option');
        opt.value = '';
        opt.textContent = _t('review.noEpisode', '没有剧集');
        sel.appendChild(opt);
        return;
      }
      list.forEach(function (ep) {
        var o = document.createElement('option');
        o.value = ep.id;
        o.textContent = '第 ' + (ep.episodeNo != null ? ep.episodeNo : ep.id) + ' 集 · ' + (ep.title || '');
        sel.appendChild(o);
      });
    } catch (err) {
      showToast(err.message || _t('review.loadFailed', '加载失败'));
    }
  }

  async function loadQueue() {
    if (!state.projectId) return;
    var kind = document.getElementById('kindFilter').value;
    var status = document.getElementById('statusFilter').value;
    var qs = [];
    if (kind) qs.push('kind=' + encodeURIComponent(kind));
    if (status) qs.push('status=' + encodeURIComponent(status));
    var url = '/api/projects/' + encodeURIComponent(state.projectId) + '/review/queue';
    if (qs.length) url += '?' + qs.join('&');

    var body = document.getElementById('queueBody');
    var empty = document.getElementById('queueEmpty');
    try {
      var list = await api(url);
      body.innerHTML = '';
      if (!list || !list.length) {
        empty.classList.remove('is-hidden');
        if (window.lucide) lucide.createIcons();
        applyI18nTo(empty);
        return;
      }
      empty.classList.add('is-hidden');
      list.forEach(function (row) {
        var tr = document.createElement('tr');
        var submittedBy = row.submittedBy || row.submittedById || '';
        tr.innerHTML =
          '<td>' + escapeHtml(row.episodeNo != null ? row.episodeNo : '') + '</td>' +
          '<td>' + escapeHtml(row.episodeTitle || '') + '</td>' +
          '<td>' + escapeHtml(kindText(row.kind)) + '</td>' +
          '<td>' + statusPill(row.status) + '</td>' +
          '<td>' + escapeHtml(submittedBy) + '</td>' +
          '<td><button type="button" class="btn btn-sm btn-secondary" data-ep="' + escapeHtml(row.episodeId) + '" data-kind="' + escapeHtml(row.kind) + '">' + escapeHtml(_t('review.view', '查看')) + '</button></td>';
        body.appendChild(tr);
      });
      body.querySelectorAll('button[data-ep]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          openDetail(btn.getAttribute('data-ep'), btn.getAttribute('data-kind'));
        });
      });
    } catch (err) {
      showToast(err.message || _t('review.loadFailed', '加载失败'));
    }
  }

  async function openDetail(episodeId, kind) {
    if (!state.projectId) return;
    state.currentEpisodeId = episodeId;
    state.currentKind = kind;

    var detailCard = document.getElementById('detailCard');
    detailCard.classList.remove('is-hidden');

    var base = '/api/projects/' + encodeURIComponent(state.projectId) + '/episodes/' + encodeURIComponent(episodeId);

    try {
      var results = await Promise.all([
        api(base + '/review?kind=' + encodeURIComponent(kind)),
        api(base + '/review/history?kind=' + encodeURIComponent(kind) + '&page=0&size=50'),
        api(base + '/review/continuity').catch(function () { return null; })
      ]);
      var info = results[0] || {};
      var history = results[1] || [];

      state.current = info;
      state.version = info.version != null ? info.version : 0;

      var titleEl = document.getElementById('detailTitle');
      titleEl.textContent = _t('review.episodeHash', '第') + ' ' +
        (state.currentEpisodeId || '') + _t('review.episodeHashSuffix', ' 集');

      document.getElementById('detailKindBadge').textContent = kindText(kind);
      document.getElementById('detailStatusBadge').innerHTML = statusPill(info.status);

      document.getElementById('dSubmittedBy').textContent = info.submittedBy || _t('review.noData', '（无）');
      document.getElementById('dL1').textContent = info.l1ReviewerId || _t('review.noData', '（无）');
      document.getElementById('dL2').textContent = info.l2ReviewerId || _t('review.noData', '（无）');
      document.getElementById('dVersion').textContent = info.version != null ? info.version : '-';
      document.getElementById('dLastComment').textContent = info.lastComment || _t('review.noData', '（无）');

      var selfAlert = document.getElementById('selfReviewedAlert');
      if (info.selfReviewed) {
        selfAlert.classList.remove('is-hidden');
        applyI18nTo(selfAlert);
      } else {
        selfAlert.classList.add('is-hidden');
      }

      var histEl = document.getElementById('historyList');
      histEl.innerHTML = '';
      if (!history || !history.length) {
        var li0 = document.createElement('li');
        li0.className = 'text-secondary';
        li0.textContent = _t('review.noData', '（无）');
        histEl.appendChild(li0);
      } else {
        history.forEach(function (h) {
          var li = document.createElement('li');
          var actor = h.actorId ? escapeHtml(h.actorId) : '';
          var comment = h.comment ? escapeHtml(h.comment) : '';
          li.innerHTML =
            '<strong>' + escapeHtml(eventText(h.event)) + '</strong>' +
            (actor ? ' · ' + actor : '') +
            ' · ' + escapeHtml(fmtTime(h.createdAt)) +
            (comment ? '<div class="text-secondary">' + comment + '</div>' : '');
          histEl.appendChild(li);
        });
      }

      renderContinuity(results[2]);

      document.getElementById('commentInput').value = info.lastComment || '';

      renderActions(kind, info.status);
    } catch (err) {
      if (err && err.status === 404) {
        showToast(_t('review.loadFailed', '加载失败'));
      } else {
        showToast(err.message || _t('review.loadFailed', '加载失败'));
      }
    }
  }

  function severityPill(sev, sevLabel) {
    var text = sevLabel || (sev === 'WARN' ? _t('review.sevWarn', '警告') : _t('review.sevInfo', '提示'));
    var cls = sev === 'WARN' ? 'sp-amber' : 'sp-gray';
    return '<span class="status-pill ' + cls + '">' + escapeHtml(text) + '</span>';
  }

  function renderContinuity(report) {
    var section = document.getElementById('continuitySection');
    if (!section) return;
    var summary = document.getElementById('continuitySummary');
    var wrap = document.getElementById('continuityTableWrap');
    var body = document.getElementById('continuityBody');
    var empty = document.getElementById('continuityEmpty');
    if (!report) { section.classList.add('is-hidden'); return; }
    section.classList.remove('is-hidden');
    var issues = report.issues || [];
    var checked = report.shotsChecked != null ? report.shotsChecked : 0;
    summary.textContent = _t('review.continuityChecked', '已检查') + ' ' + checked + ' ' +
      _t('review.continuityShotsUnit', '镜') + ' · ' + issues.length + ' ' +
      _t('review.continuityIssuesUnit', '个问题');
    body.innerHTML = '';
    if (!issues.length) {
      wrap.classList.add('is-hidden');
      empty.classList.remove('is-hidden');
      if (window.lucide) lucide.createIcons();
      applyI18nTo(empty);
      return;
    }
    wrap.classList.remove('is-hidden');
    empty.classList.add('is-hidden');
    issues.forEach(function (it) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + escapeHtml(it.shotNo != null ? it.shotNo : '') + '</td>' +
        '<td>' + severityPill(it.severity, it.severityLabel) + '</td>' +
        '<td>' + escapeHtml(it.rule || '') + '</td>' +
        '<td>' + escapeHtml(it.message || '') + '</td>' +
        '<td>' + escapeHtml(it.suggestion || '') + '</td>';
      body.appendChild(tr);
    });
    applyI18nTo(section);
  }

  function renderActions(kind, status) {
    var bar = document.getElementById('actionBar');
    bar.innerHTML = '';
    if (kind === 'SCRIPT') {
      if (status === 'DRAFT') {
        addBtn(bar, _t('review.submit', '提交审核'), 'btn-secondary', function () { doSubmit(); });
      } else if (status === 'PENDING_L1') {
        addBtn(bar, _t('review.l1Approve', '一审通过'), 'btn-secondary', function () { doAction('l1/approve'); });
        addBtn(bar, _t('review.l1Reject', '一审驳回'), 'btn-secondary', function () { doAction('l1/reject'); });
      } else if (status === 'PENDING_L2') {
        addBtn(bar, _t('review.l2Approve', '二审通过'), 'btn-secondary', function () { doAction('l2/approve'); });
        addBtn(bar, _t('review.l2Reject', '二审驳回'), 'btn-secondary', function () { doAction('l2/reject'); });
      } else if (status === 'APPROVED') {
        addHint(bar, _t('review.alreadyApproved', '已通过'));
      } else if (status === 'REJECTED') {
        addHint(bar, _t('review.rejectedHint', '已驳回，可重新生成剧本后再提交'));
      }
    } else if (kind === 'BOARD') {
      if (status === 'DRAFT') {
        addBtn(bar, _t('review.submit', '提交审核'), 'btn-secondary', function () { doSubmit(); });
      } else if (status === 'PENDING') {
        addBtn(bar, _t('review.approve', '通过'), 'btn-secondary', function () { doAction('board/approve'); });
        addBtn(bar, _t('review.reject', '驳回'), 'btn-secondary', function () { doAction('board/reject'); });
      } else if (status === 'APPROVED') {
        addHint(bar, _t('review.alreadyApproved', '已通过'));
      }
    }
  }

  function addBtn(bar, label, cls, handler) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn ' + cls;
    b.textContent = label;
    b.addEventListener('click', handler);
    bar.appendChild(b);
  }

  function addHint(bar, text) {
    var s = document.createElement('span');
    s.className = 'text-secondary';
    s.textContent = text;
    bar.appendChild(s);
  }

  async function doSubmit() {
    if (!state.projectId || !state.currentEpisodeId || !state.currentKind) return;
    var base = '/api/projects/' + encodeURIComponent(state.projectId) + '/episodes/' + encodeURIComponent(state.currentEpisodeId);
    try {
      var info = await api(base + '/review?kind=' + encodeURIComponent(state.currentKind));
      var version = info && info.version != null ? info.version : 0;
      await api(base + '/review/submit', {
        method: 'POST',
        body: JSON.stringify({ kind: state.currentKind, version: version })
      });
      showToast(_t('review.okToast', '操作成功'));
      await refresh();
    } catch (err) {
      handleActionError(err);
    }
  }

  async function doAction(action) {
    if (!state.projectId || !state.currentEpisodeId || !state.currentKind) return;
    var base = '/api/projects/' + encodeURIComponent(state.projectId) + '/episodes/' + encodeURIComponent(state.currentEpisodeId);
    var comment = document.getElementById('commentInput').value.trim();
    var path = base + '/review/' + state.currentKind.toLowerCase() + '/' + action;
    try {
      await api(path, {
        method: 'POST',
        body: JSON.stringify({ version: state.version, comment: comment })
      });
      showToast(_t('review.okToast', '操作成功'));
      await refresh();
    } catch (err) {
      handleActionError(err);
    }
  }

  async function refresh() {
    await loadQueue();
    if (state.currentEpisodeId && state.currentKind) {
      await openDetail(state.currentEpisodeId, state.currentKind);
    }
  }

  function handleActionError(err) {
    if (err && err.status === 409) {
      showToast(_t('review.conflictToast', '数据有变化，请刷新重试'));
      refresh();
      return;
    }
    showToast((err && err.message) || _t('review.actionFailed', '操作失败'));
  }

  async function submitNewReview() {
    if (!state.projectId) {
      showToast(_t('review.noProject', '没有项目'));
      return;
    }
    var epId = document.getElementById('episodeSelect').value;
    var kind = document.getElementById('newKind').value;
    if (!epId) {
      showToast(_t('review.pickEpisode', '请选择剧集'));
      return;
    }
    var base = '/api/projects/' + encodeURIComponent(state.projectId) + '/episodes/' + encodeURIComponent(epId);
    try {
      var info = await api(base + '/review?kind=' + encodeURIComponent(kind));
      var version = info && info.version != null ? info.version : 0;
      await api(base + '/review/submit', {
        method: 'POST',
        body: JSON.stringify({ kind: kind, version: version })
      });
      showToast(_t('review.okToast', '操作成功'));
      await loadQueue();
      await openDetail(epId, kind);
    } catch (err) {
      handleActionError(err);
    }
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n(document);

    document.getElementById('projectSelect').addEventListener('change', function (e) {
      state.projectId = e.target.value || null;
      document.getElementById('detailCard').classList.add('is-hidden');
      loadEpisodes();
      loadQueue();
    });
    document.getElementById('kindFilter').addEventListener('change', loadQueue);
    document.getElementById('statusFilter').addEventListener('change', loadQueue);
    document.getElementById('submitReviewBtn').addEventListener('click', submitNewReview);

    if (window.lucide) lucide.createIcons();
    loadProjects();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  if (window.DFI18N && typeof DFI18N.onLangChange === 'function') {
    DFI18N.onLangChange(function () {
      loadProjects();
    });
  }
})();
