(function () {
  'use strict';

  var PAGE_I18N = {
    'qc.pageTitle': { 'zh-CN': '成片质检 · AI 短剧工坊', en: 'Final Cut QC · AI Short Drama Studio' },
    'qc.heading': { 'zh-CN': '成片质检', en: 'Final Cut QC' },
    'qc.emptyHint': { 'zh-CN': '未指定成片，请从成片库进入。', en: 'No Final Cut specified — open this page from the Final Cut library.' },
    'qc.duration': { 'zh-CN': '时长', en: 'Duration' },
    'qc.createdAt': { 'zh-CN': '创建时间', en: 'Created at' },
    'qc.episode': { 'zh-CN': '所属剧集', en: 'Episode' },
    'qc.noteTitle': { 'zh-CN': '质检备注', en: 'QC note' },
    'qc.notePh': { 'zh-CN': '质检备注 / 打回原因', en: 'QC note / reason for rejection' },
    'qc.approve': { 'zh-CN': '通过', en: 'Approve' },
    'qc.reject': { 'zh-CN': '打回', en: 'Reject' },
    'qc.statusPending': { 'zh-CN': '待质检', en: 'Pending QC' },
    'qc.statusApproved': { 'zh-CN': '已通过', en: 'Approved' },
    'qc.statusRejected': { 'zh-CN': '已打回', en: 'Rejected' },
    'qc.statusUnknown': { 'zh-CN': '未知', en: 'Unknown' },
    'qc.finalCutHash': { 'zh-CN': '成片 #', en: 'Final Cut #' },
    'qc.episodeHash': { 'zh-CN': '剧集 #', en: 'Episode #' },
    'qc.noNote': { 'zh-CN': '（无备注）', en: '(no note)' },
    'qc.requestFailed': { 'zh-CN': '请求失败', en: 'Request failed' },
    'qc.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'qc.missingId': { 'zh-CN': '缺少成片 ID', en: 'Missing Final Cut ID' },
    'qc.approvedToast': { 'zh-CN': '已通过质检', en: 'QC approved' },
    'qc.rejectedToast': { 'zh-CN': '已打回', en: 'Rejected' },
    'qc.actionFailed': { 'zh-CN': '操作失败', en: 'Action failed' }
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

  var params = new URLSearchParams(window.location.search);
  var qcId = params.get('id');

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
      throw new Error((data && data.message) || _t('qc.requestFailed', '请求失败'));
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

  function toTimecode(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return '-';
    var s = Math.max(0, Math.floor(Number(seconds)));
    var m = Math.floor(s / 60);
    var sec = s % 60;
    return (m < 10 ? '0' + m : '' + m) + ':' + (sec < 10 ? '0' + sec : '' + sec);
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    function p(n) { return n < 10 ? '0' + n : '' + n; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function statusBadge(status) {
    switch (status) {
      case 'PENDING':
        return { dot: 'dot-amber', text: _t('qc.statusPending', '待质检') };
      case 'APPROVED':
        return { dot: 'dot-green', text: _t('qc.statusApproved', '已通过') };
      case 'REJECTED':
        return { dot: 'dot-red', text: _t('qc.statusRejected', '已打回') };
      default:
        return { dot: 'dot-gray', text: status || _t('qc.statusUnknown', '未知') };
    }
  }

  var current = null;

  async function loadQc() {
    if (!qcId) {
      var card = document.getElementById('qcCard');
      var empty = document.getElementById('qcEmpty');
      if (card) card.style.display = 'none';
      if (empty) {
        empty.classList.remove('is-hidden');
        if (window.lucide) lucide.createIcons();
        applyI18nTo(empty);
      }
      return;
    }
    try {
      var data = await api('/api/final-cuts/' + encodeURIComponent(qcId));
      current = data;

      var titleEl = document.getElementById('qcTitle');
      titleEl.textContent = data.title || (_t('qc.finalCutHash', '成片 #') + qcId);

      var badgeEl = document.getElementById('qcStatusBadge');
      var badge = statusBadge(data.qcStatus);
      badgeEl.innerHTML = '<span class="status-pill ' + badge.dot.replace('dot-', 'sp-') + '">' + escapeHtml(badge.text) + '</span>';

      document.getElementById('qcDuration').textContent = toTimecode(data.durationSeconds);
      document.getElementById('qcCreated').textContent = data.createdAt
        ? fmtTime(data.createdAt)
        : '-';
      document.getElementById('qcEpisode').textContent = data.episodeId
        ? (_t('qc.episodeHash', '剧集 #') + data.episodeId)
        : '-';

      var video = document.getElementById('qcVideo');
      video.src = '/media/finals/' + encodeURIComponent(qcId);

      var form = document.getElementById('qcForm');
      var noteView = document.getElementById('qcNoteView');
      var noteText = document.getElementById('qcNoteText');

      if (data.qcStatus && data.qcStatus !== 'PENDING') {
        form.style.display = 'none';
        noteView.style.display = '';
        noteText.textContent = data.qcNote ? data.qcNote : _t('qc.noNote', '（无备注）');
      } else {
        form.style.display = '';
        noteView.style.display = 'none';
        document.getElementById('qcNote').value = data.qcNote || '';
      }
    } catch (err) {
      showToast(err.message || _t('qc.loadFailed', '加载失败'));
    }
  }

  async function submitVerdict(verdict) {
    if (!qcId) {
      showToast(_t('qc.missingId', '缺少成片 ID'));
      return;
    }
    var noteEl = document.getElementById('qcNote');
    var note = noteEl ? noteEl.value.trim() : '';
    try {
      await api('/api/final-cuts/' + encodeURIComponent(qcId) + '/qc', {
        method: 'POST',
        body: JSON.stringify({ verdict: verdict, note: note })
      });
      showToast(verdict === 'APPROVED' ? _t('qc.approvedToast', '已通过质检') : _t('qc.rejectedToast', '已打回'));
      await loadQc();
    } catch (err) {
      showToast(err.message || _t('qc.actionFailed', '操作失败'));
    }
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n(document);
    var approveBtn = document.getElementById('approveBtn');
    var rejectBtn = document.getElementById('rejectBtn');
    if (approveBtn) {
      approveBtn.addEventListener('click', function () {
        submitVerdict('APPROVED');
      });
    }
    if (rejectBtn) {
      rejectBtn.addEventListener('click', function () {
        submitVerdict('REJECTED');
      });
    }
    loadQc();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  if (window.DFI18N && typeof DFI18N.onLangChange === 'function') {
    DFI18N.onLangChange(function () {
      loadQc();
    });
  }
})();
