(function () {
  'use strict';

  var PAGE_I18N = {
    'usg.pageTitle': { 'zh-CN': '用量统计 · AI 短剧工坊', en: 'Usage · AI Short Drama Studio' },
    'usg.heading': { 'zh-CN': '用量统计', en: 'Usage' },
    'usg.subtitle': { 'zh-CN': 'Token 与费用 · 仅统计真实发生的调用', en: 'Tokens and cost · Only actual calls are counted' },
    'usg.allProviders': { 'zh-CN': '全部供应商', en: 'All providers' },
    'usg.allModels': { 'zh-CN': '全部模型', en: 'All models' },
    'usg.days7': { 'zh-CN': '近 7 天', en: 'Last 7 days' },
    'usg.days30': { 'zh-CN': '近 30 天', en: 'Last 30 days' },
    'usg.days90': { 'zh-CN': '近 90 天', en: 'Last 90 days' },
    'usg.overview': { 'zh-CN': '概览', en: 'Overview' },
    'usg.totalCost': { 'zh-CN': '总成本', en: 'Total cost' },
    'usg.totalRequests': { 'zh-CN': '总请求数', en: 'Total requests' },
    'usg.totalTokens': { 'zh-CN': '真实消耗 Tokens', en: 'Tokens used' },
    'usg.cacheHitRate': { 'zh-CN': '缓存命中率', en: 'Cache hit rate' },
    'usg.notCollected': { 'zh-CN': '暂未采集', en: 'Not collected yet' },
    'usg.detailUsage': { 'zh-CN': '明细消耗', en: 'Detailed usage' },
    'usg.newInput': { 'zh-CN': '新增输入', en: 'New input' },
    'usg.output': { 'zh-CN': '输出', en: 'Output' },
    'usg.cacheCreate': { 'zh-CN': '缓存创建', en: 'Cache creation' },
    'usg.cacheRead': { 'zh-CN': '缓存命中', en: 'Cache read' },
    'usg.trend': { 'zh-CN': '使用趋势', en: 'Usage trend' },
    'usg.requests': { 'zh-CN': '请求数', en: 'Requests' },
    'usg.cost': { 'zh-CN': '成本', en: 'Cost' },
    'usg.requestLog': { 'zh-CN': '请求日志', en: 'Request log' },
    'usg.byModel': { 'zh-CN': '按模型', en: 'By model' },
    'usg.byRun': { 'zh-CN': '按运行', en: 'By Run' },
    'usg.loadFailed': { 'zh-CN': '加载失败', en: 'Failed to load' },
    'usg.thTime': { 'zh-CN': '时间', en: 'Time' },
    'usg.thKind': { 'zh-CN': '类型', en: 'Type' },
    'usg.thProvider': { 'zh-CN': '供应商', en: 'Provider' },
    'usg.thModel': { 'zh-CN': '模型', en: 'Model' },
    'usg.thCostEst': { 'zh-CN': '费用估算', en: 'Cost estimate' },
    'usg.thSpeed': { 'zh-CN': '速度', en: 'Speed' },
    'usg.thCost': { 'zh-CN': '费用', en: 'Cost' },
    'usg.thTaskCount': { 'zh-CN': '任务数', en: 'Tasks' },
    'usg.thGoal': { 'zh-CN': '目标', en: 'Goal' },
    'usg.thCreatedAt': { 'zh-CN': '创建时间', en: 'Created at' },
    'usg.kindVideoTask': { 'zh-CN': '视频任务', en: 'Video task' },
    'usg.kindAgentStep': { 'zh-CN': 'Agent 步骤', en: 'Agent step' },
    'usg.estimatedPrefix': { 'zh-CN': '约', en: '~' }
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

  var EM_DASH = '\u2014';

  function fmtNum(n) {
    if (n === null || n === undefined) return EM_DASH;
    var num = Number(n);
    if (!isFinite(num)) return EM_DASH;
    return num.toLocaleString('en-US');
  }

  function fmtCost(cents) {
    if (cents === null || cents === undefined) return EM_DASH;
    var num = Number(cents);
    if (!isFinite(num)) return EM_DASH;
    return '¥' + (num / 100).toFixed(2);
  }

  function fmtTime(s) {
    if (!s) return EM_DASH;
    var d = new Date(s);
    if (isNaN(d.getTime())) return EM_DASH;
    function p(x) { return x < 10 ? '0' + x : '' + x; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) +
      ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function fmtDate(s) {
    if (!s) return EM_DASH;
    var d = new Date(s);
    if (isNaN(d.getTime())) return s;
    function p(x) { return x < 10 ? '0' + x : '' + x; }
    return (d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function truncate(s, n) {
    if (s === null || s === undefined) return EM_DASH;
    var str = String(s);
    if (str.length <= n) return str;
    return str.slice(0, n - 1) + '\u2026';
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
        var v = attrs[k];
        if (v === null || v === undefined) continue;
        if (k === 'class') {
          node.className = v;
        } else if (k === 'text') {
          node.textContent = v;
        } else if (k === 'style') {
          node.setAttribute('style', v);
        } else {
          node.setAttribute(k, v);
        }
      }
    }
    if (children && children.length) {
      for (var i = 0; i < children.length; i++) {
        var c = children[i];
        if (c === null || c === undefined) continue;
        if (typeof c === 'string') {
          node.appendChild(document.createTextNode(c));
        } else {
          node.appendChild(c);
        }
      }
    }
    return node;
  }

  function show(id) {
    var node = document.getElementById(id);
    if (node) node.style.display = '';
  }

  function hide(id) {
    var node = document.getElementById(id);
    if (node) node.style.display = 'none';
  }

  function setState(prefix, state) {
    hide(prefix + '-loading');
    hide(prefix + '-empty');
    hide(prefix + '-error');
    if (state === 'loading') {
      show(prefix + '-loading');
    } else if (state === 'empty') {
      show(prefix + '-empty');
    } else if (state === 'error') {
      show(prefix + '-error');
    }
  }

  function getJSON(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      });
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  function failState(prefix) {
    setState(prefix, 'error');
  }

  var state = {
    provider: '',
    model: '',
    days: 30,
    metric: 'tokens',
    byDayRows: []
  };

  function qs(id) {
    return document.getElementById(id);
  }

  function buildQuery(params) {
    var parts = [];
    for (var k in params) {
      if (!Object.prototype.hasOwnProperty.call(params, k)) continue;
      var v = params[k];
      if (v === null || v === undefined || v === '') continue;
      parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
    }
    return parts.length ? ('?' + parts.join('&')) : '';
  }

  function loadFilters() {
    getJSON('/api/usage/filters')
      .then(function (data) {
        if (!data) return;
        var providerSel = qs('filter-provider');
        var modelSel = qs('filter-model');
        var providers = data.providers || [];
        var models = data.models || [];
        var i;
        for (i = 0; i < providers.length; i++) {
          providerSel.appendChild(el('option', { value: providers[i], text: providers[i] }));
        }
        for (i = 0; i < models.length; i++) {
          modelSel.appendChild(el('option', { value: models[i], text: models[i] }));
        }
      })
      .catch(function () {
        /* 过滤项加载失败不影响主流程 */
      });
  }

  function loadSummary() {
    setState('kpi', 'loading');
    var url = '/api/usage/summary' + buildQuery({
      provider: state.provider,
      model: state.model,
      days: state.days
    });
    getJSON(url)
      .then(function (data) {
        if (!data) {
          setState('kpi', 'error');
          return;
        }
        qs('kpi-cost').textContent = fmtCost(data.costCentsTotal);
        qs('kpi-requests').textContent = fmtNum(data.requestCount);
        qs('kpi-tokens').textContent = fmtNum(data.tokensTotal);
        qs('kpi-cache-hit').textContent = EM_DASH;
        setState('kpi', 'ready');
      })
      .catch(function () {
        failState('kpi');
      });
  }

  function loadTrend() {
    setState('trend', 'loading');
    var url = '/api/usage/by-day' + buildQuery({
      days: state.days,
      provider: state.provider,
      model: state.model
    });
    getJSON(url)
      .then(function (rows) {
        state.byDayRows = rows || [];
        renderTrend();
      })
      .catch(function () {
        failState('trend');
      });
  }

  function trendValue(row, metric) {
    if (!row) return null;
    if (metric === 'tokens') return row.tokens;
    if (metric === 'requests') {
      var vc = row.videoCount === null || row.videoCount === undefined ? 0 : Number(row.videoCount);
      var sc = row.stepCount === null || row.stepCount === undefined ? 0 : Number(row.stepCount);
      return vc + sc;
    }
    if (metric === 'cost') return row.costCents;
    return null;
  }

  function renderTrend() {
    var list = qs('trend-list');
    while (list.firstChild) list.removeChild(list.firstChild);

    var rows = state.byDayRows || [];
    if (!rows.length) {
      setState('trend', 'empty');
      return;
    }

    var metric = state.metric;
    var max = 0;
    var i;
    var vals = [];
    for (i = 0; i < rows.length; i++) {
      var v = trendValue(rows[i], metric);
      var num = (v === null || v === undefined) ? null : Number(v);
      vals.push(num);
      if (num !== null && isFinite(num) && num > max) max = num;
    }

    for (i = 0; i < rows.length; i++) {
      var row = rows[i];
      var raw = vals[i];
      var label;
      if (raw === null || !isFinite(raw)) {
        label = EM_DASH;
      } else if (metric === 'cost') {
        label = fmtCost(raw);
      } else {
        label = fmtNum(raw);
      }

      var pct = 0;
      if (raw !== null && isFinite(raw) && max > 0) {
        pct = (raw / max) * 100;
        if (pct < 0) pct = 0;
      }

      var fill = el('div', { class: 'bar-fill' });
      fill.style.width = pct + '%';

      var track = el('div', { class: 'bar-track' }, [fill]);

      var barRow = el('div', { class: 'bar-row' }, [
        el('div', { class: 'bar-date', text: fmtDate(row.date) }),
        track,
        el('div', { class: 'bar-value', text: label })
      ]);

      list.appendChild(barRow);
    }

    setState('trend', 'ready');
  }

  function kindLabel(kind) {
    if (kind === 'VIDEO_TASK') return _t('usg.kindVideoTask', '视频任务');
    return _t('usg.kindAgentStep', 'Agent 步骤');
  }

  function speedLabel(row) {
    var lat = row.latencyMs;
    var tok = row.tokensUsed;
    if (lat === null || lat === undefined || tok === null || tok === undefined) return EM_DASH;
    var latNum = Number(lat);
    var tokNum = Number(tok);
    if (!isFinite(latNum) || !isFinite(tokNum)) return EM_DASH;
    if (latNum <= 0) return EM_DASH;
    var tps = Math.round(tokNum * 1000 / latNum);
    if (!isFinite(tps)) return EM_DASH;
    return '\u2248' + tps + ' tok/s';
  }

  function costEstimatedLabel(row) {
    var base = fmtCost(row.costCents);
    if (base === EM_DASH) return EM_DASH;
    if (row.costEstimated === true) return _t('usg.estimatedPrefix', '约') + base;
    return base;
  }

  function loadRequests() {
    setState('req', 'loading');
    var url = '/api/usage/requests' + buildQuery({
      limit: 50,
      provider: state.provider,
      model: state.model,
      days: state.days
    });
    getJSON(url)
      .then(function (rows) {
        renderRequests(rows || []);
      })
      .catch(function () {
        failState('req');
      });
  }

  function renderRequests(rows) {
    var tbody = qs('req-tbody');
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    if (!rows.length) {
      setState('req', 'empty');
      return;
    }

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var tr = el('tr', null, [
        el('td', { text: fmtTime(row.time) }),
        el('td', { text: kindLabel(row.kind) }),
        el('td', { text: row.provider === null || row.provider === undefined ? EM_DASH : row.provider }),
        el('td', { text: row.model === null || row.model === undefined ? EM_DASH : row.model }),
        el('td', { text: fmtNum(row.tokensUsed) }),
        el('td', { text: costEstimatedLabel(row) }),
        el('td', { text: speedLabel(row) })
      ]);
      tbody.appendChild(tr);
    }

    setState('req', 'ready');
  }

  function loadByModel() {
    setState('model', 'loading');
    getJSON('/api/usage/by-model')
      .then(function (rows) {
        renderByModel(rows || []);
      })
      .catch(function () {
        failState('model');
      });
  }

  function renderByModel(rows) {
    var tbody = qs('model-tbody');
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    if (!rows.length) {
      setState('model', 'empty');
      return;
    }

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var tr = el('tr', null, [
        el('td', { text: row.model === null || row.model === undefined ? EM_DASH : row.model }),
        el('td', { text: fmtNum(row.tokens) }),
        el('td', { text: fmtCost(row.costCents) }),
        el('td', { text: fmtNum(row.taskCount) })
      ]);
      tbody.appendChild(tr);
    }

    setState('model', 'ready');
  }

  function loadByRun() {
    setState('run', 'loading');
    getJSON('/api/usage/by-run?limit=20')
      .then(function (rows) {
        renderByRun(rows || []);
      })
      .catch(function () {
        failState('run');
      });
  }

  function renderByRun(rows) {
    var tbody = qs('run-tbody');
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    if (!rows.length) {
      setState('run', 'empty');
      return;
    }

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var goalText = row.goal === null || row.goal === undefined ? EM_DASH : truncate(row.goal, 60);
      var tr = el('tr', null, [
        el('td', { text: row.runId === null || row.runId === undefined ? EM_DASH : String(row.runId) }),
        el('td', { class: 'wrap', text: goalText }),
        el('td', { text: fmtNum(row.tokens) }),
        el('td', { text: fmtCost(row.costCents) }),
        el('td', { text: fmtTime(row.createdAt) })
      ]);
      tbody.appendChild(tr);
    }

    setState('run', 'ready');
  }

  function loadFiltered() {
    loadSummary();
    loadTrend();
    loadRequests();
  }

  function loadAll() {
    loadFiltered();
    loadByModel();
    loadByRun();
  }

  function bindFilters() {
    qs('filter-provider').addEventListener('change', function (e) {
      state.provider = e.target.value || '';
      loadFiltered();
    });
    qs('filter-model').addEventListener('change', function (e) {
      state.model = e.target.value || '';
      loadFiltered();
    });
    qs('filter-days').addEventListener('change', function (e) {
      var v = parseInt(e.target.value, 10);
      state.days = isFinite(v) ? v : 30;
      loadFiltered();
    });
    qs('btn-refresh').addEventListener('click', function () {
      loadAll();
    });
  }

  function bindTabs() {
    var tabs = document.querySelectorAll('.tab-btn');
    for (var i = 0; i < tabs.length; i++) {
      (function (btn) {
        btn.addEventListener('click', function () {
          var metric = btn.getAttribute('data-metric');
          if (!metric) return;
          state.metric = metric;
          for (var j = 0; j < tabs.length; j++) {
            tabs[j].classList.remove('active');
          }
          btn.classList.add('active');
          renderTrend();
        });
      })(tabs[i]);
    }
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n(document);
    bindFilters();
    bindTabs();
    loadFilters();
    loadAll();
    refreshIcons();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  if (window.DFI18N && typeof DFI18N.onLangChange === 'function') {
    DFI18N.onLangChange(function () {
      renderTrend();
      loadAll();
    });
  }
})();
