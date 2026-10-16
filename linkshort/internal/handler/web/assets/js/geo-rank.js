// internal/handler/web/assets/js/geo-rank.js
// 地域排行表格渲染：国家排行 / 城市下钻
// 依赖 common.js 的 esc()，以及可选的 window.geoDrill / window.geoBack

(function () {
  'use strict';

  var UNKNOWN = '—';

  function isUnknownName(name) {
    if (name === null || name === undefined) return true;
    var s = String(name).trim();
    if (s === '') return true;
    if (s.toLowerCase() === 'unknown') return true;
    return false;
  }

  function safeEsc(s) {
    if (typeof window.esc === 'function') return window.esc(s);
    // 兜底：保持 ES5，简单转义
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function sumClicks(rows) {
    var t = 0;
    for (var i = 0; i < rows.length; i++) {
      var c = Number(rows[i].clicks);
      if (isFinite(c) && c > 0) t += c;
    }
    return t;
  }

  function pctStr(clicks, total) {
    if (!total || total <= 0) return '0.0%';
    var v = (Number(clicks) || 0) / total * 100;
    return v.toFixed(1) + '%';
  }

  // 占比条：轨道 + 填充，内联样式，不改 style.css
  function barHtml(clicks, total) {
    var ratio = 0;
    if (total > 0) {
      ratio = (Number(clicks) || 0) / total;
      if (ratio < 0) ratio = 0;
      if (ratio > 1) ratio = 1;
    }
    var w = (ratio * 100).toFixed(2) + '%';
    var track = 'background:#EDE6D6;height:6px;border-radius:3px;overflow:hidden;flex:1;min-width:60px;';
    var fill = 'background:#B3402A;height:100%;width:' + w + ';display:block;';
    var wrap = 'display:flex;align-items:center;gap:8px;';
    var txt = 'font-size:12px;color:#6E6455;min-width:48px;text-align:right;';
    return '<div style="' + wrap + '">' +
             '<div style="' + track + '"><span style="' + fill + '"></span></div>' +
             '<span style="' + txt + '">' + safeEsc(pctStr(clicks, total)) + '</span>' +
           '</div>';
  }

  function numCell(v) {
    var n = Number(v);
    if (!isFinite(n)) n = 0;
    return '<td class="mono">' + safeEsc(String(n)) + '</td>';
  }

  function emptyRow(colspan) {
    return '<tr><td colspan="' + colspan + '" style="color:#6E6455;">暂无数据</td></tr>';
  }

  function renderCountry(el, items) {
    // 先按国家聚合：API 返回的是城市粒度，同一国家多行需加总
    var agg = {};
    var order = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (isUnknownName(it.country_name)) continue;
      var cc = it.country_code || '';
      if (!agg[cc]) {
        agg[cc] = { country_code: cc, country_name: it.country_name || cc, clicks: 0, uv: 0 };
        order.push(cc);
      }
      agg[cc].clicks += (Number(it.clicks) || 0);
      agg[cc].uv += (Number(it.uv) || 0);
    }
    var rows = [];
    for (var k = 0; k < order.length; k++) rows.push(agg[order[k]]);
    // 按 clicks 降序
    rows.sort(function (a, b) { return b.clicks - a.clicks; });
    var total = sumClicks(rows);

    var html = '';
    html += '<table class="table">';
    html += '<thead><tr>' +
              '<th>国家</th>' +
              '<th>点击</th>' +
              '<th>独立访客</th>' +
              '<th>占比</th>' +
            '</tr></thead>';
    html += '<tbody>';

    if (rows.length === 0) {
      html += emptyRow(4);
    } else {
      var canDrill = typeof window.geoDrill === 'function';
      for (var j = 0; j < rows.length; j++) {
        var r = rows[j];
        var code = r.country_code || '';
        var name = r.country_name || '';
        var nameHtml;
        if (canDrill) {
          nameHtml = '<a href="javascript:void(0)" data-cc="' + safeEsc(code) + '" ' +
                     'data-cn="' + safeEsc(name) + '" ' +
                     'style="color:#1F1B16;text-decoration:none;border-bottom:1px solid transparent;">' +
                     safeEsc(name) + '</a>';
        } else {
          nameHtml = safeEsc(name);
        }
        html += '<tr>';
        html += '<td>' + nameHtml + '</td>';
        html += numCell(r.clicks);
        html += numCell(r.uv);
        html += '<td>' + barHtml(r.clicks, total) + '</td>';
        html += '</tr>';
      }
    }

    html += '</tbody></table>';
    el.innerHTML = html;

    // 绑定点击（若 geoDrill 存在）
    if (typeof window.geoDrill === 'function') {
      var links = el.querySelectorAll('a[data-cc]');
      for (var k = 0; k < links.length; k++) {
        (function (a) {
          a.onclick = function () {
            var cc = a.getAttribute('data-cc');
            var cn = a.getAttribute('data-cn');
            if (typeof window.geoDrill === 'function') {
              window.geoDrill(cc, cn);
            }
          };
          a.onmouseover = function () { a.style.color = '#B3402A'; a.style.borderBottomColor = '#B3402A'; };
          a.onmouseout = function () { a.style.color = '#1F1B16'; a.style.borderBottomColor = 'transparent'; };
        })(links[k]);
      }
    }
  }

  function renderCity(el, items, opts) {
    var rows = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (isUnknownName(it.country_name)) continue;
      rows.push(it);
    }
    var total = sumClicks(rows);

    var countryName = (opts && opts.countryName) ? String(opts.countryName) : '';
    var html = '';

    // 返回行
    html += '<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px 0;">';
    html += '<button type="button" class="btn tiny ghost" data-geo-back>‹ 返回国家排行</button>';
    if (countryName) {
      html += '<span style="color:#6E6455;font-size:13px;">' +
                safeEsc(countryName) + ' · 城市排行' +
              '</span>';
    }
    html += '</div>';

    html += '<table class="table">';
    html += '<thead><tr>' +
              '<th>省份</th>' +
              '<th>城市</th>' +
              '<th>点击</th>' +
              '<th>独立访客</th>' +
              '<th>占比</th>' +
            '</tr></thead>';
    html += '<tbody>';

    if (rows.length === 0) {
      html += emptyRow(5);
    } else {
      for (var j = 0; j < rows.length; j++) {
        var r = rows[j];
        var prov = r.province;
        var city = r.city;
        var provHtml = isUnknownName(prov) ? UNKNOWN : safeEsc(prov);
        var cityHtml = isUnknownName(city) ? UNKNOWN : safeEsc(city);
        html += '<tr>';
        html += '<td>' + provHtml + '</td>';
        html += '<td>' + cityHtml + '</td>';
        html += numCell(r.clicks);
        html += numCell(r.uv);
        html += '<td>' + barHtml(r.clicks, total) + '</td>';
        html += '</tr>';
      }
    }

    html += '</tbody></table>';
    el.innerHTML = html;

    var backBtn = el.querySelector('button[data-geo-back]');
    if (backBtn) {
      backBtn.onclick = function () {
        if (opts && typeof opts.onBack === 'function') {
          opts.onBack();
        } else if (typeof window.geoBack === 'function') {
          window.geoBack();
        }
      };
    }
  }

  window.renderGeoRank = function (el, items, opts) {
    if (!el) return;
    if (!items || !items.length) {
      var o = opts || {};
      var mode = o.mode === 'city' ? 'city' : 'country';
      if (mode === 'city') {
        var countryName = o.countryName ? String(o.countryName) : '';
        var h = '';
        h += '<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px 0;">';
        h += '<button type="button" class="btn tiny ghost" data-geo-back>‹ 返回国家排行</button>';
        if (countryName) {
          h += '<span style="color:#6E6455;font-size:13px;">' + safeEsc(countryName) + ' · 城市排行</span>';
        }
        h += '</div>';
        h += '<table class="table"><thead><tr>' +
             '<th>省份</th><th>城市</th><th>点击</th><th>独立访客</th><th>占比</th>' +
             '</tr></thead><tbody>' + emptyRow(5) + '</tbody></table>';
        el.innerHTML = h;
        var b = el.querySelector('button[data-geo-back]');
        if (b) {
          b.onclick = function () {
            if (typeof o.onBack === 'function') o.onBack();
            else if (typeof window.geoBack === 'function') window.geoBack();
          };
        }
      } else {
        el.innerHTML = '<table class="table"><thead><tr>' +
          '<th>国家</th><th>点击</th><th>独立访客</th><th>占比</th>' +
          '</tr></thead><tbody>' + emptyRow(4) + '</tbody></table>';
      }
      return;
    }

    var o2 = opts || {};
    var mode2 = o2.mode === 'city' ? 'city' : 'country';
    if (mode2 === 'city') {
      renderCity(el, items, o2);
    } else {
      renderCountry(el, items);
    }
  };
})();
