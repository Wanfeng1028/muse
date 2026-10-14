
(function () {
  'use strict';

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
      throw new Error((data && data.message) || '请求失败');
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
        return { dot: 'dot-amber', text: '待质检' };
      case 'APPROVED':
        return { dot: 'dot-green', text: '已通过' };
      case 'REJECTED':
        return { dot: 'dot-red', text: '已打回' };
      default:
        return { dot: 'dot-gray', text: status || '未知' };
    }
  }

  var current = null;

  async function loadQc() {
    if (!qcId) {
      showToast('缺少成片 ID');
      return;
    }
    try {
      var data = await api('/api/final-cuts/' + encodeURIComponent(qcId));
      current = data;

      var titleEl = document.getElementById('qcTitle');
      titleEl.textContent = data.title || ('成片 #' + qcId);

      var badgeEl = document.getElementById('qcStatusBadge');
      var badge = statusBadge(data.qcStatus);
      badgeEl.innerHTML = '<span class="status-pill ' + badge.dot.replace('dot-', 'sp-') + '">' + escapeHtml(badge.text) + '</span>';

      document.getElementById('qcDuration').textContent = toTimecode(data.durationSeconds);
      document.getElementById('qcCreated').textContent = data.createdAt
        ? fmtTime(data.createdAt)
        : '-';
      document.getElementById('qcEpisode').textContent = data.episodeId
        ? ('剧集 #' + data.episodeId)
        : '-';

      var video = document.getElementById('qcVideo');
      video.src = '/media/finals/' + encodeURIComponent(qcId);

      var form = document.getElementById('qcForm');
      var noteView = document.getElementById('qcNoteView');
      var noteText = document.getElementById('qcNoteText');

      if (data.qcStatus && data.qcStatus !== 'PENDING') {
        form.style.display = 'none';
        noteView.style.display = '';
        noteText.textContent = data.qcNote ? data.qcNote : '（无备注）';
      } else {
        form.style.display = '';
        noteView.style.display = 'none';
        document.getElementById('qcNote').value = data.qcNote || '';
      }
    } catch (err) {
      showToast(err.message || '加载失败');
    }
  }

  async function submitVerdict(verdict) {
    if (!qcId) {
      showToast('缺少成片 ID');
      return;
    }
    var noteEl = document.getElementById('qcNote');
    var note = noteEl ? noteEl.value.trim() : '';
    try {
      await api('/api/final-cuts/' + encodeURIComponent(qcId) + '/qc', {
        method: 'POST',
        body: JSON.stringify({ verdict: verdict, note: note })
      });
      showToast(verdict === 'APPROVED' ? '已通过质检' : '已打回');
      await loadQc();
    } catch (err) {
      showToast(err.message || '操作失败');
    }
  }

  function init() {
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
})();
