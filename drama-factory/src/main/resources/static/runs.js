(function () {
  'use strict';

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
    if (n < 1000) return n + ' 毫秒';
    if (n < 60000) return (n / 1000).toFixed(1) + ' 秒';
    var m = Math.floor(n / 60000), s = Math.round((n % 60000) / 1000);
    return m + ' 分 ' + s + ' 秒';
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
        '总运行数 ' + esc(s.totalRuns) + '<span class="sep">·</span>' +
        '成功率 ' + esc(rate) + '<span class="sep">·</span>' +
        '平均耗时 ' + esc(fmtDuration(s.avgDurationMs));
      if (window.lucide) lucide.createIcons();
    } catch (e) {
      bar.innerHTML = '';
    }
  }

  /* ---------------- run list ---------------- */
  function renderEmpty() {
    return '<div class="card empty">' +
      '<i data-lucide="inbox"></i>' +
      '<div class="t">还没有运行，创建第一条 Run 吧</div>' +
      '<div class="d">点击下方按钮，输入目标即可生成短剧计划并执行。</div>' +
      '<button class="btn btn-primary" id="emptyNewBtn"><i data-lucide="plus"></i>新建运行</button>' +
      '</div>';
  }

  function renderRuns(runs) {
    var list = $('#listArea');
    if (!runs || !runs.length) {
      list.innerHTML = renderEmpty();
      if (window.lucide) lucide.createIcons();
      var b = $('#emptyNewBtn');
      if (b) b.addEventListener('click', openWizard);
      return;
    }
    var html = '<div class="run-list">';
    runs.forEach(function (r) {
      var badge = '<span class="badge ' + statusClass(r.status) + '"><span class="dot"></span>' + esc(r.statusLabel || r.status || '') + '</span>';
      html += '<a class="run-row" href="/run-detail.html?id=' + encodeURIComponent(r.id) + '">' +
        '<div class="goal">' + esc(truncate(r.goal || '(无目标)', 80)) + '</div>' +
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
      list.innerHTML = '<div class="error-box"><i data-lucide="alert-triangle" style="width:15px;height:15px;vertical-align:-2px"></i> 加载运行列表失败：' + esc(e.message) + '</div>';
      if (window.lucide) lucide.createIcons();
      toast('加载运行列表失败', 'err');
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
    if (!goal) { toast('请先输入目标', 'err'); return; }
    var btn = $('#previewBtn');
    var area = $('#planArea');
    btn.disabled = true;
    area.innerHTML = '<div class="loading"><span class="spinner"></span>正在生成计划…</div>';
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
      area.innerHTML = '<div class="error-box"><i data-lucide="alert-triangle" style="width:15px;height:15px;vertical-align:-2px"></i> 生成计划失败：' + esc(e.message) + '</div>';
      if (window.lucide) lucide.createIcons();
      toast('生成计划失败', 'err');
    } finally {
      btn.disabled = false;
    }
  }

  function renderPlan(plan) {
    var area = $('#planArea');
    var html = '';
    if (plan && plan.fallback) {
      html += '<div class="notice notice-amber"><i data-lucide="alert-triangle"></i><div>模型不可用，已用模板计划。</div></div>';
    }
    var eps = (plan && plan.episodes) || [];
    if (!eps.length) {
      html += '<div class="empty" style="padding:24px"><div class="d">未生成分集计划</div></div>';
    } else {
      eps.forEach(function (ep) {
        html += '<div class="plan-ep">' +
          '<div class="no">第 ' + esc(ep.episodeNo) + ' 集</div>' +
          '<div class="t">' + esc(ep.title || '(无标题)') + '</div>' +
          '<div class="o">' + esc(ep.outline || '') + '</div>' +
        '</div>';
      });
    }
    area.innerHTML = html;
    if (window.lucide) lucide.createIcons();
  }

  async function doConfirm() {
    var goal = $('#goalInput').value.trim();
    if (!goal) { toast('请先输入目标', 'err'); return; }
    var btn = $('#confirmBtn');
    btn.disabled = true;
    try {
      var res = await req('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal: goal, plan: lastPlan })
      });
      var runId = res && res.runId;
      if (!runId) throw new Error('未返回 runId');
      toast('运行已创建', 'ok');
      location.href = '/run-detail.html?id=' + encodeURIComponent(runId);
    } catch (e) {
      toast('创建运行失败：' + e.message, 'err');
      btn.disabled = false;
    }
  }

  /* ---------------- init ---------------- */
  function init() {
    if (window.lucide) lucide.createIcons();

    $('#newRunBtn').addEventListener('click', openWizard);
    $('#refreshBtn').addEventListener('click', function () {
      loadStats();
      loadRuns();
      toast('已刷新', 'ok');
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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
