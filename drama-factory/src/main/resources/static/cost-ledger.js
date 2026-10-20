(function () {
  'use strict';

    const PAGE_I18N = {
    'cl.pageTitle': { 'zh-CN': '成本账本', en: 'Cost Ledger' },
    'cl.heading': { 'zh-CN': '成本账本', en: 'Cost Ledger' },
    'cl.subtitle': { 'zh-CN': '预算、消耗与明细一览', en: 'Budget, spend and entries at a glance' },
    'cl.budget': { 'zh-CN': '预算', en: 'Budget' },
    'cl.budgetTotal': { 'zh-CN': '预算总额', en: 'Budget Total' },
    'cl.spent': { 'zh-CN': '已花费', en: 'Spent' },
    'cl.reserved': { 'zh-CN': '冻结中', en: 'Reserved' },
    'cl.usable': { 'zh-CN': '可用余额', en: 'Usable' },
    'cl.today': { 'zh-CN': '今日花费', en: 'Today' },
    'cl.last7days': { 'zh-CN': '近 7 天花费', en: 'Last 7 Days' },
    'cl.totalEntries': { 'zh-CN': '累计条目', en: 'Total Entries' },
    'cl.providerCount': { 'zh-CN': '供应商数', en: 'Providers' },
    'cl.trend': { 'zh-CN': '趋势', en: 'Trend' },
    'cl.byProvider': { 'zh-CN': '按供应商', en: 'By Provider' },
    'cl.recentEntries': { 'zh-CN': '最近记录', en: 'Recent Entries' },
    'cl.thTime': { 'zh-CN': '时间', en: 'Time' },
    'cl.thProvider': { 'zh-CN': '供应商', en: 'Provider' },
    'cl.thModel': { 'zh-CN': '模型', en: 'Model' },
    'cl.thOp': { 'zh-CN': '操作', en: 'Operation' },
    'cl.thStatus': { 'zh-CN': '状态', en: 'Status' },
    'cl.thEst': { 'zh-CN': '预估', en: 'Estimated' },
    'cl.thActual': { 'zh-CN': '实际', en: 'Actual' },
    'cl.emptyEntries': { 'zh-CN': '还没有任何账本记录，先去跑一条视频任务吧', en: 'No ledger entries yet — run a video task first' },
    'cl.emptyProviders': { 'zh-CN': '今天还没有供应商产生花费', en: 'No provider spend today' },
    'cl.emptyBudget': { 'zh-CN': '账本为空，暂无预算数据', en: 'Ledger is empty, no budget data yet' },
    'cl.loadFailed': { 'zh-CN': '加载失败：', en: 'Failed to load: ' },
    'cl.noData': { 'zh-CN': '暂无数据', en: 'No data' },
    'cl.modeWarn': { 'zh-CN': '仅告警', en: 'Warn only' },
    'cl.modeCap': { 'zh-CN': '超额拦截', en: 'Over-cap block' },
    'cl.disabledTip': { 'zh-CN': '计费开关已关闭，数据仅供参考', en: 'Billing switch is off, data is for reference only' },
    'cl.legendSpent': { 'zh-CN': '实际花费', en: 'Actual spend' },
    'cl.legendEst': { 'zh-CN': '预估', en: 'Estimated' },
    'cl.utilization': { 'zh-CN': '使用率', en: 'Utilization' },
    'cl.statusEstimated': { 'zh-CN': '已估算', en: 'Estimated' },
    'cl.statusReserved': { 'zh-CN': '冻结中', en: 'Reserved' },
    'cl.statusCompleted': { 'zh-CN': '已完成', en: 'Completed' },
    'cl.statusFailed': { 'zh-CN': '已失败', en: 'Failed' },
    'cl.statusRefunded': { 'zh-CN': '已退款', en: 'Refunded' },
    'cl.kpiBudget': { 'zh-CN': '预算总额', en: 'Budget Total' },
    'cl.kpiSpent': { 'zh-CN': '已花费', en: 'Spent' },
    'cl.kpiReserved': { 'zh-CN': '冻结中', en: 'Reserved' },
    'cl.kpiUsable': { 'zh-CN': '可用余额', en: 'Usable' },
    'cl.kpiToday': { 'zh-CN': '今日花费', en: 'Today' },
    'cl.kpiWeek': { 'zh-CN': '近 7 天', en: 'Last 7 Days' },
    'cl.kpiEntries': { 'zh-CN': '累计条目', en: 'Total Entries' },
    'cl.kpiProviders': { 'zh-CN': '供应商数', en: 'Providers' },
    'cl.colTime': { 'zh-CN': '时间', en: 'Time' },
    'cl.colProvider': { 'zh-CN': '供应商', en: 'Provider' },
    'cl.colModel': { 'zh-CN': '模型', en: 'Model' },
    'cl.colOperation': { 'zh-CN': '操作', en: 'Operation' },
    'cl.colStatus': { 'zh-CN': '状态', en: 'Status' },
    'cl.colEstimated': { 'zh-CN': '预估 $', en: 'Est. $' },
    'cl.colActual': { 'zh-CN': '实际 $', en: 'Actual $' },
    'cl.trendEmpty': { 'zh-CN': '暂无趋势数据', en: 'No trend data yet' },
    'cl.entryEmpty': { 'zh-CN': '还没有任何账本记录，先去跑一条视频任务吧', en: 'No ledger entries yet' },
    'cl.providerEmpty': { 'zh-CN': '今天还没有供应商产生花费', en: 'No provider spend today' },
  };

  if (window.DFI18N && typeof window.DFI18N.register === 'function') {
    window.DFI18N.register(PAGE_I18N);
  }

  function _t(key, zh) {
    if (window.DFI18N && typeof window.DFI18N.tr === 'function') {
      const v = window.DFI18N.tr(key);
      if (v != null && v !== key) return v;
    }
    return zh;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function api(path) {
    return fetch(path, { headers: { 'Accept': 'application/json' } }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (txt) {
          const msg = txt && txt.length ? txt : ('HTTP ' + res.status);
          throw new Error(msg);
        }, function () {
          throw new Error('HTTP ' + res.status);
        });
      }
      return res.json();
    });
  }

  function toast(msg, kind) {
    if (window.DFUI && typeof window.DFUI.toast === 'function') {
      window.DFUI.toast(msg, kind);
      return;
    }
    if (kind === 'error') console.error(msg);
    else console.log(msg);
  }

  function fmtMoney(v) {
    const n = typeof v === 'number' ? v : parseFloat(v);
    if (!isFinite(n)) return '$0.00';
    return '$' + n.toFixed(2);
  }

  function pad2(n) {
    return (n < 10 ? '0' : '') + n;
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    const s = String(iso);
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
    if (!m) return esc(s);
    return m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5];
  }

  function todayISO() {
    const d = new Date();
    return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  }

  function showError(id, err) {
    const el = document.getElementById(id);
    if (!el) return;
    const detail = err && err.message ? err.message : String(err || '');
    el.textContent = _t('cl.loadFailed', '加载失败：') + detail;
    el.hidden = false;
  }

  function hideError(id) {
    const el = document.getElementById(id);
    if (el) el.hidden = true;
  }

  function statusBadge(status) {
    const s = String(status || '').toUpperCase();
    let cls = 'badge bg-secondary-lt';
    let label = s || '—';
    if (s === 'ESTIMATED') { cls = 'badge bg-secondary-lt'; label = _t('cl.statusEstimated', '已估算'); }
    else if (s === 'RESERVED') { cls = 'badge bg-yellow-lt'; label = _t('cl.statusReserved', '冻结中'); }
    else if (s === 'COMPLETED') { cls = 'badge bg-green-lt'; label = _t('cl.statusCompleted', '已完成'); }
    else if (s === 'FAILED') { cls = 'badge bg-red-lt'; label = _t('cl.statusFailed', '已失败'); }
    else if (s === 'REFUNDED') { cls = 'badge bg-blue-lt'; label = _t('cl.statusRefunded', '已退款'); }
    return '<span class="' + cls + '">' + esc(label) + '</span>';
  }

  function modeLabel(mode) {
    const m = String(mode || '').toUpperCase();
    if (m === 'CAP' || m === 'BLOCK' || m === 'HARD') return _t('cl.modeCap', '超额拦截');
    return _t('cl.modeWarn', '仅告警');
  }

  function setKpi(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function loadBudget() {
    hideError('budgetError');
    return api('/api/cost-ledger/budget').then(function (data) {
      data = data || {};
      const budgetTotalUsd = typeof data.budgetTotalUsd === 'number' ? data.budgetTotalUsd : 0;
      const spentUsd = typeof data.spentUsd === 'number' ? data.spentUsd : 0;
      const reservedUsd = typeof data.reservedUsd === 'number' ? data.reservedUsd : 0;
      const usableUsd = typeof data.usableUsd === 'number' ? data.usableUsd : 0;
      const utilizationPct = typeof data.utilizationPct === 'number' ? data.utilizationPct : 0;

      setKpi('kpiBudget', fmtMoney(budgetTotalUsd));
      setKpi('kpiSpent', fmtMoney(spentUsd));
      setKpi('kpiReserved', fmtMoney(reservedUsd));
      setKpi('kpiUsable', fmtMoney(usableUsd));

      const bar = document.getElementById('budgetBar');
      if (bar) {
        const w = Math.max(0, Math.min(utilizationPct, 100));
        bar.style.width = w + '%';
        let colorCls = 'bg-blue';
        if (utilizationPct >= 90) colorCls = 'bg-red';
        else if (utilizationPct >= 70) colorCls = 'bg-yellow';
        bar.className = 'progress-bar ' + colorCls;
      }

      const meta = document.getElementById('budgetMeta');
      if (meta) {
        const pctText = isFinite(utilizationPct) ? utilizationPct.toFixed(1) : '0.0';
        meta.textContent = _t('cl.utilization', '使用率') + ' ' + pctText + '%';
      }

      const badge = document.getElementById('budgetBadge');
      if (badge) {
        if (data.enabled === false) {
          badge.className = 'badge bg-secondary-lt';
          badge.textContent = _t('cl.disabledTip', '计费开关已关闭，数据仅供参考');
        } else {
          badge.className = 'badge bg-green-lt';
          badge.textContent = modeLabel(data.mode);
        }
      }
    }).catch(function (err) {
      showError('budgetError', err);
    });
  }

  function loadKpis() {
    hideError('kpiError');

    const pSummary = api('/api/cost-ledger/summary').then(function (data) {
      data = data || {};
      const entryCount = typeof data.entryCount === 'number' ? data.entryCount : 0;
      setKpi('kpiEntries', String(entryCount));
    }).catch(function () {
      setKpi('kpiEntries', '—');
    });

    const today = todayISO();
    const pDaily = api('/api/cost-ledger/daily?date=' + encodeURIComponent(today)).then(function (rows) {
      const arr = Array.isArray(rows) ? rows : [];
      let sum = 0;
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i] && typeof arr[i].spentUsd === 'number' ? arr[i].spentUsd : 0;
        sum += v;
      }
      setKpi('kpiToday', fmtMoney(sum));
      setKpi('kpiProviders', String(arr.length));
    }).catch(function () {
      setKpi('kpiToday', '—');
      setKpi('kpiProviders', '—');
    });

    const pTrend = api('/api/cost-ledger/trend?days=7').then(function (rows) {
      const arr = Array.isArray(rows) ? rows : [];
      let sum = 0;
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i] && typeof arr[i].spentUsd === 'number' ? arr[i].spentUsd : 0;
        sum += v;
      }
      setKpi('kpiWeek', fmtMoney(sum));
    }).catch(function () {
      setKpi('kpiWeek', '—');
    });

    return Promise.all([pSummary, pDaily, pTrend]);
  }

  function loadProviders() {
    const emptyEl = document.getElementById('providerEmpty');
    const barsEl = document.getElementById('providerBars');
    if (emptyEl) emptyEl.hidden = true;
    if (!barsEl) return Promise.resolve();

    const today = todayISO();
    return api('/api/cost-ledger/daily?date=' + encodeURIComponent(today)).then(function (rows) {
      const arr = Array.isArray(rows) ? rows : [];
      if (arr.length === 0) {
        barsEl.innerHTML = '';
        if (emptyEl) {
          emptyEl.textContent = _t('cl.emptyProviders', '今天还没有供应商产生花费');
          emptyEl.hidden = false;
        }
        return;
      }
      if (emptyEl) emptyEl.hidden = true;

      let maxSpents = 0;
      for (let i = 0; i < arr.length; i++) {
        const v = arr[i] && typeof arr[i].spentUsd === 'number' ? arr[i].spentUsd : 0;
        if (v > maxSpents) maxSpents = v;
      }
      if (maxSpents <= 0) maxSpents = 1;

      const parts = [];
      for (let i = 0; i < arr.length; i++) {
        const row = arr[i] || {};
        const provider = row.provider != null && row.provider !== '' ? String(row.provider) : '-';
        const spentUsd = typeof row.spentUsd === 'number' ? row.spentUsd : 0;
        const width = Math.max(0, Math.min((spentUsd / maxSpents) * 100, 100));
        parts.push(
          '<div class="mb-2">' +
            '<div class="d-flex justify-content-between align-items-center mb-1">' +
              '<span class="text-truncate">' + esc(provider) + '</span>' +
              '<span style="font-variant-numeric: tabular-nums;">' + esc(fmtMoney(spentUsd)) + '</span>' +
            '</div>' +
            '<div class="progress progress-sm">' +
              '<div class="progress-bar bg-blue" style="width: ' + width + '%"></div>' +
            '</div>' +
          '</div>'
        );
      }
      barsEl.innerHTML = parts.join('');
    }).catch(function (err) {
      barsEl.innerHTML = '';
      if (emptyEl) {
        emptyEl.textContent = _t('cl.loadFailed', '加载失败：') + (err && err.message ? err.message : '');
        emptyEl.hidden = false;
      }
    });
  }

  function loadEntries() {
    hideError('entryError');
    const rowsEl = document.getElementById('entryRows');
    const emptyEl = document.getElementById('entryEmpty');
    if (emptyEl) emptyEl.hidden = true;
    if (!rowsEl) return Promise.resolve();

    return api('/api/cost-ledger/entries?limit=20').then(function (rows) {
      const arr = Array.isArray(rows) ? rows : [];
      if (arr.length === 0) {
        rowsEl.innerHTML = '';
        if (emptyEl) {
          emptyEl.textContent = _t('cl.emptyEntries', '还没有任何账本记录，先去跑一条视频任务吧');
          emptyEl.hidden = false;
        }
        return;
      }
      if (emptyEl) emptyEl.hidden = true;

      const parts = [];
      for (let i = 0; i < arr.length; i++) {
        const row = arr[i] || {};
        const provider = row.provider != null && row.provider !== '' ? String(row.provider) : '-';
        const model = row.model != null && row.model !== '' ? String(row.model) : '-';
        const operation = row.operation != null && row.operation !== '' ? String(row.operation) : '-';
        const est = row.estimatedUsd;
        const act = row.actualUsd;
        const actualText = (act === null || act === undefined) ? '—' : fmtMoney(act);
        parts.push(
          '<tr>' +
            '<td style="font-variant-numeric: tabular-nums;">' + esc(fmtDateTime(row.createdAt)) + '</td>' +
            '<td>' + esc(provider) + '</td>' +
            '<td>' + esc(model) + '</td>' +
            '<td>' + esc(operation) + '</td>' +
            '<td>' + statusBadge(row.status) + '</td>' +
            '<td style="font-variant-numeric: tabular-nums;">' + esc(fmtMoney(est)) + '</td>' +
            '<td style="font-variant-numeric: tabular-nums;">' + esc(actualText) + '</td>' +
          '</tr>'
        );
      }
      rowsEl.innerHTML = parts.join('');
    }).catch(function (err) {
      rowsEl.innerHTML = '';
      showError('entryError', err);
    });
  }

  function init() {
    if (window.DFI18N && typeof DFI18N.applyI18n === 'function') {
      DFI18N.applyI18n(document);
    }
    loadBudget();
    loadKpis();
    loadProviders();
    loadEntries();
    bindTrendDays();
    loadTrend();
  }

  var TREND_DAYS = 14;

  function fmtDayLabel(isoDate) {
    // '2026-10-20' -> '10-20'
    if (!isoDate || isoDate.length < 10) return '';
    return isoDate.slice(5, 10);
  }

  function loadTrend() {
    var box = document.getElementById('trendChart');
    var empty = document.getElementById('trendEmpty');
    var errBox = document.getElementById('trendError');
    if (errBox) errBox.hidden = true;
    api('/api/cost-ledger/trend?days=' + TREND_DAYS)
      .then(function (points) { renderTrend(box, empty, points || []); })
      .catch(function (e) {
        if (box) box.innerHTML = '';
        if (empty) empty.hidden = true;
        if (errBox) { errBox.textContent = _t('cl.loadFailed', '加载失败') + '：' + (e && e.message ? e.message : e); errBox.hidden = false; }
      });
  }

  function renderTrend(box, empty, points) {
    if (!box) return;
    var W = 720, H = 220, PAD_L = 44, PAD_R = 12, PAD_T = 12, PAD_B = 28;
    var iw = W - PAD_L - PAD_R, ih = H - PAD_T - PAD_B;
    var maxV = 0;
    points.forEach(function (p) {
      maxV = Math.max(maxV, num(p.estimatedUsd), num(p.spentUsd));
    });
    var allZero = maxV <= 0;
    if (empty) empty.hidden = !allZero;
    if (allZero) { box.innerHTML = ''; return; }
    if (empty) empty.hidden = true;
    maxV = maxV * 1.15;
    function x(i) { return PAD_L + (points.length <= 1 ? iw / 2 : (iw * i) / (points.length - 1)); }
    function y(v) { return PAD_T + ih - (ih * v) / maxV; }
    function lineOf(getter) {
      return points.map(function (p, i) { return x(i).toFixed(1) + ',' + y(getter(p)).toFixed(1); }).join(' ');
    }
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" role="img" aria-label="trend">';
    // y 轴 4 档刻度
    for (var g = 0; g <= 3; g++) {
      var gv = (maxV * g) / 3;
      var gy = y(gv);
      svg += '<line x1="' + PAD_L + '" y1="' + gy.toFixed(1) + '" x2="' + (W - PAD_R) + '" y2="' + gy.toFixed(1) + '" stroke="#e6e8eb" stroke-width="1"/>';
      svg += '<text x="' + (PAD_L - 6) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" font-size="11" fill="#6c7a91">$' + gv.toFixed(gv < 10 ? 2 : 0) + '</text>';
    }
    // x 轴日期（最多标 7 个，避免挤）
    var step = Math.max(1, Math.ceil(points.length / 7));
    points.forEach(function (p, i) {
      if (i % step !== 0 && i !== points.length - 1) return;
      svg += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="11" fill="#6c7a91">' + esc(fmtDayLabel(p.date)) + '</text>';
    });
    // estimated 灰虚线
    svg += '<polyline fill="none" stroke="#a8b0bd" stroke-width="1.5" stroke-dasharray="5 4" points="' + lineOf(function (p) { return num(p.estimatedUsd); }) + '"/>';
    // spent 蓝实线 + 数据点（title 做悬停提示）
    svg += '<polyline fill="none" stroke="#206bc4" stroke-width="2" points="' + lineOf(function (p) { return num(p.spentUsd); }) + '"/>';
    points.forEach(function (p, i) {
      svg += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(num(p.spentUsd)).toFixed(1) + '" r="3.5" fill="#206bc4">'
        + '<title>' + esc(fmtDayLabel(p.date)) + ' 花费 $' + num(p.spentUsd).toFixed(2) + ' / 预估 $' + num(p.estimatedUsd).toFixed(2) + ' / ' + p.entryCount + ' 笔</title></circle>';
    });
    // 图例
    svg += '<g font-size="12" fill="#495057">'
      + '<line x1="' + PAD_L + '" y1="18" x2="' + (PAD_L + 22) + '" y2="18" stroke="#206bc4" stroke-width="2"/>'
      + '<text x="' + (PAD_L + 28) + '" y="22">' + esc(_t('cl.legendSpent', '实际花费')) + '</text>'
      + '<line x1="' + (PAD_L + 110) + '" y1="18" x2="' + (PAD_L + 132) + '" y2="18" stroke="#a8b0bd" stroke-width="1.5" stroke-dasharray="5 4"/>'
      + '<text x="' + (PAD_L + 138) + '" y="22">' + esc(_t('cl.legendEst', '预估')) + '</text></g>';
    svg += '</svg>';
    box.innerHTML = svg;
  }

  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }

  function bindTrendDays() {
    var btns = document.querySelectorAll('#trendDays button[data-days]');
    btns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var d = parseInt(btn.getAttribute('data-days'), 10);
        if (d === 7 || d === 14 || d === 30) TREND_DAYS = d;
        btns.forEach(function (b) { b.classList.toggle('btn-primary', b === btn); b.classList.toggle('btn-outline-secondary', b !== btn); });
        loadTrend();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
