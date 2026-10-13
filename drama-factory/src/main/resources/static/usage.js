
(function () {
  'use strict';

  var EM_DASH = '—';

  function fmtNum(n) {
    if (n === null || n === undefined || n === '') return EM_DASH;
    var num = Number(n);
    if (!isFinite(num)) return EM_DASH;
    return num.toLocaleString('en-US');
  }

  function fmtCost(costCents) {
    if (costCents === null || costCents === undefined || costCents === '') return EM_DASH;
    var c = Number(costCents);
    if (!isFinite(c)) return EM_DASH;
    return '¥' + (c / 100).toFixed(2);
  }

  function pad2(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  function fmtTime(iso) {
    if (!iso) return EM_DASH;
    var s = String(iso);
    var d = new Date(s);
    if (isNaN(d.getTime())) {
      return s.length >= 16 ? s.slice(0, 16).replace('T', ' ') : s;
    }
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()) +
      ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }

  function fmtDate(dateStr) {
    if (!dateStr) return EM_DASH;
    return String(dateStr);
  }

  function truncate(str, max) {
    if (str === null || str === undefined) return EM_DASH;
    var s = String(str);
    if (s.length <= max) return s;
    return s.slice(0, max) + '…';
  }

  function el(id) {
    return document.getElementById(id);
  }

  function show(ids) {
    for (var i = 0; i < ids.length; i++) {
      var node = el(ids[i]);
      if (node) node.hidden = false;
    }
  }

  function hide(ids) {
    for (var i = 0; i < ids.length; i++) {
      var node = el(ids[i]);
      if (node) node.hidden = true;
    }
  }

  function setState(prefix, state) {
    var loading = el(prefix + '-loading');
    var empty = el(prefix + '-empty');
    var error = el(prefix + '-error');
    if (loading) loading.hidden = state !== 'loading';
    if (empty) empty.hidden = state !== 'empty';
    if (error) error.hidden = state !== 'error';
  }

  function getJSON(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    });
  }

  function refreshIcons() {
    try {
      if (window.lucide && typeof window.lucide.createIcons === 'function') {
        window.lucide.createIcons();
      }
    } catch (e) { /* ignore */ }
  }

  // ---------- summary strip ----------
  function renderSummary(data) {
    var strip = el('usage-strip');
    if (!strip) return;
    if (!data || typeof data !== 'object') {
      strip.textContent = EM_DASH;
      return;
    }
    var parts = [];
    parts.push('累计 Token ' + fmtNum(data.tokensTotal));
    parts.push('累计费用约 ' + fmtCost(data.costCentsTotal));
    parts.push('视频任务 ' + fmtNum(data.taskCount));
    parts.push('运行 ' + fmtNum(data.runCount));
    strip.textContent = parts.join(' · ');
  }

  // ---------- by model ----------
  function renderByModel(rows) {
    var tbody = el('usage-by-model');
    var table = el('by-model-table');
    if (!tbody || !table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      setState('by-model', 'empty');
      table.hidden = true;
      return;
    }

    tbody.innerHTML = '';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      var tr = document.createElement('tr');

      var tdModel = document.createElement('td');
      tdModel.textContent = (r.model === null || r.model === undefined || r.model === '') ? EM_DASH : String(r.model);
      tr.appendChild(tdModel);

      var tdTokens = document.createElement('td');
      tdTokens.textContent = fmtNum(r.tokens);
      tr.appendChild(tdTokens);

      var tdCost = document.createElement('td');
      tdCost.textContent = fmtCost(r.costCents);
      tr.appendChild(tdCost);

      var tdTasks = document.createElement('td');
      tdTasks.textContent = fmtNum(r.taskCount);
      tr.appendChild(tdTasks);

      tbody.appendChild(tr);
    }

    setState('by-model', 'ready');
    table.hidden = false;
  }

  // ---------- by day ----------
  function renderByDay(rows) {
    var container = el('usage-by-day');
    if (!container) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      setState('by-day', 'empty');
      container.hidden = true;
      return;
    }

    var max = 0;
    for (var i = 0; i < rows.length; i++) {
      var t = rows[i] && rows[i].tokens;
      var n = Number(t);
      if (isFinite(n) && n > max) max = n;
    }

    container.innerHTML = '';
    for (var j = 0; j < rows.length; j++) {
      var r = rows[j] || {};
      var row = document.createElement('div');
      row.className = 'bar-row';

      var dateEl = document.createElement('span');
      dateEl.className = 'bar-date';
      dateEl.textContent = fmtDate(r.date);
      row.appendChild(dateEl);

      var track = document.createElement('span');
      track.className = 'bar-track';
      var fill = document.createElement('span');
      fill.className = 'bar-fill';
      var tokensNum = Number(r.tokens);
      var pct = 0;
      if (max > 0 && isFinite(tokensNum) && tokensNum > 0) {
        pct = (tokensNum / max) * 100;
      }
      fill.style.width = pct.toFixed(2) + '%';
      track.appendChild(fill);
      row.appendChild(track);

      var valEl = document.createElement('span');
      valEl.className = 'bar-value';
      valEl.textContent = fmtNum(r.tokens);
      row.appendChild(valEl);

      container.appendChild(row);
    }

    setState('by-day', 'ready');
    container.hidden = false;
  }

  // ---------- by run ----------
  function renderByRun(rows) {
    var tbody = el('usage-by-run');
    var table = el('by-run-table');
    if (!tbody || !table) return;

    if (!Array.isArray(rows) || rows.length === 0) {
      setState('by-run', 'empty');
      table.hidden = true;
      return;
    }

    tbody.innerHTML = '';
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i] || {};
      var tr = document.createElement('tr');

      var tdRun = document.createElement('td');
      tdRun.textContent = (r.runId === null || r.runId === undefined || r.runId === '') ? EM_DASH : String(r.runId);
      tr.appendChild(tdRun);

      var tdGoal = document.createElement('td');
      tdGoal.textContent = truncate(r.goal, 30);
      tr.appendChild(tdGoal);

      var tdTokens = document.createElement('td');
      tdTokens.textContent = fmtNum(r.tokens);
      tr.appendChild(tdTokens);

      var tdCost = document.createElement('td');
      tdCost.textContent = fmtCost(r.costCents);
      tr.appendChild(tdCost);

      var tdTime = document.createElement('td');
      tdTime.textContent = fmtTime(r.createdAt);
      tr.appendChild(tdTime);

      tbody.appendChild(tr);
    }

    setState('by-run', 'ready');
    table.hidden = false;
  }

  function failState(prefix) {
    setState(prefix, 'error');
  }

  // ---------- boot ----------
  function boot() {
    setState('by-model', 'loading');
    setState('by-day', 'loading');
    setState('by-run', 'loading');

    var strip = el('usage-strip');
    if (strip) strip.textContent = '加载中…';

    getJSON('/api/usage/summary')
      .then(function (data) { renderSummary(data); })
      .catch(function () {
        if (strip) strip.textContent = EM_DASH;
      });

    getJSON('/api/usage/by-model')
      .then(function (rows) { renderByModel(rows); })
      .catch(function () { failState('by-model'); });

    getJSON('/api/usage/by-day?days=30')
      .then(function (rows) { renderByDay(rows); })
      .catch(function () { failState('by-day'); });

    getJSON('/api/usage/by-run?limit=20')
      .then(function (rows) { renderByRun(rows); })
      .catch(function () { failState('by-run'); });

    refreshIcons();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.refreshIcons = refreshIcons;
})();

