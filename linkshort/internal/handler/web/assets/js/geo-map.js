// internal/handler/web/assets/js/geo-map.js
// linkshort 地域分布热力图。手写 SVG 等距圆柱投影，无外部依赖，ES5。
// 设计注记见 README：邮政标签主题，纸底墨字邮戳红，等宽字体，方角图例。

(function () {
  'use strict';

  // ---- 国家码 -> 中文名（兜底） ----
  var CC_NAME = {
    CN: '中国', US: '美国', JP: '日本', KR: '韩国', SG: '新加坡',
    GB: '英国', DE: '德国', FR: '法国', AU: '澳大利亚', CA: '加拿大',
    RU: '俄罗斯', IN: '印度', BR: '巴西', NL: '荷兰', IE: '爱尔兰',
    ID: '印度尼西亚', MY: '马来西亚', TH: '泰国', VN: '越南', PH: '菲律宾',
    HK: '中国香港', TW: '中国台湾', MO: '中国澳门'
  };

  // ---- 热力色档（0 档无数据） ----
  var FILL0 = '#EDE6D6';
  var FILL1 = '#F3D9D2';
  var FILL2 = '#E5A894';
  var FILL3 = '#CD6B52';
  var FILL4 = '#B3402A';
  var STROKE = '#F7F3EC';
  var INK = '#1F1B16';
  var LINE = '#D8CFBC';
  var MUTED = '#6E6455';
  var PAPER = '#F7F3EC';

  // ---- 投影 ----
  function projX(lng) { return (lng + 180) / 360 * 1000; }
  function projY(lat) { return (90 - lat) / 180 * 500; }

  // 把经纬度顶点数组转成 "M x,y L x,y ... Z"
  function pathFromLL(points) {
    var out = '';
    for (var i = 0; i < points.length; i++) {
      var x = projX(points[i][0]);
      var y = projY(points[i][1]);
      if (i === 0) out += 'M' + x.toFixed(1) + ',' + y.toFixed(1);
      else out += 'L' + x.toFixed(1) + ',' + y.toFixed(1);
    }
    return out + 'Z';
  }

  // ---- 手写简化国界（经纬度，粗粒度，形状神似即可） ----
  // 每个国家至少 4 个顶点。列岛拆成多段。
  var COUNTRIES = [
    { cc: 'CN', name: '中国', parts: [[
      [73, 39], [80, 30], [88, 27], [97, 28], [105, 22], [110, 21],
      [122, 30], [121, 40], [130, 43], [135, 48], [125, 53], [95, 48], [80, 45]
    ]]},
    { cc: 'US', name: '美国', parts: [[
      [-124, 48], [-95, 49], [-83, 42], [-70, 45], [-67, 45],
      [-81, 25], [-97, 26], [-107, 31], [-117, 32], [-124, 42]
    ]]},
    { cc: 'CA', name: '加拿大', parts: [[
      [-141, 69], [-90, 70], [-60, 60], [-55, 52], [-65, 44], [-83, 42],
      [-95, 49], [-123, 49], [-130, 55], [-141, 60]
    ]]},
    { cc: 'BR', name: '巴西', parts: [[
      [-73, 5], [-60, 5], [-50, 0], [-35, -5], [-38, -15], [-48, -25],
      [-58, -30], [-65, -15], [-70, -5]
    ]]},
    { cc: 'RU', name: '俄罗斯', parts: [[
      [30, 68], [60, 70], [100, 76], [140, 72], [170, 68], [160, 58],
      [135, 50], [95, 50], [60, 52], [35, 55], [28, 60]
    ]]},
    { cc: 'IN', name: '印度', parts: [[
      [68, 24], [75, 32], [85, 27], [90, 22], [92, 25], [89, 22],
      [80, 8], [77, 8], [72, 20]
    ]]},
    { cc: 'AU', name: '澳大利亚', parts: [[
      [114, -22], [122, -17], [130, -12], [142, -11], [153, -25],
      [150, -37], [140, -38], [125, -33], [115, -34]
    ]]},
    { cc: 'JP', name: '日本', parts: [
      [[130, 31], [132, 34], [137, 35], [140, 40], [142, 42], [141, 38], [136, 33], [131, 31]],
      [[143, 43], [145, 44], [144, 42], [142, 42]]
    ]},
    { cc: 'KR', name: '韩国', parts: [[
      [126, 34], [128, 35], [129, 37], [128, 38], [126, 37], [125, 35]
    ]]},
    { cc: 'GB', name: '英国', parts: [[
      [-5, 50], [-5, 55], [-3, 58], [0, 54], [1, 52], [-1, 51]
    ]]},
    { cc: 'FR', name: '法国', parts: [[
      [-4, 43], [-2, 49], [4, 51], [8, 49], [7, 44], [3, 43]
    ]]},
    { cc: 'DE', name: '德国', parts: [[
      [6, 47], [6, 54], [10, 55], [14, 54], [15, 51], [12, 48]
    ]]},
    { cc: 'NL', name: '荷兰', parts: [[
      [3, 51], [4, 53], [7, 53], [7, 51], [5, 51]
    ]]},
    { cc: 'IE', name: '爱尔兰', parts: [[
      [-10, 52], [-10, 55], [-6, 55], [-6, 52]
    ]]},
    { cc: 'SG', name: '新加坡', parts: [[
      [103.6, 1.2], [104.1, 1.2], [104.1, 1.5], [103.6, 1.5]
    ]]},
    { cc: 'ID', name: '印度尼西亚', parts: [
      [[95, 5], [102, 2], [106, -3], [112, -7], [119, -9], [115, -8], [104, -2], [96, 3]],
      [[118, -8], [124, -9], [131, -8], [135, -4], [130, -3], [122, -5], [118, -7]]
    ]},
    { cc: 'MY', name: '马来西亚', parts: [
      [[100, 6], [104, 3], [104, 1], [101, 2], [100, 4]],
      [[110, 1], [117, 4], [119, 5], [116, 6], [110, 3]]
    ]},
    { cc: 'TH', name: '泰国', parts: [[
      [98, 19], [101, 20], [105, 15], [103, 12], [100, 6], [99, 10], [98, 14]
    ]]},
    { cc: 'VN', name: '越南', parts: [[
      [104, 22], [108, 21], [109, 16], [109, 11], [105, 9], [104, 12], [104, 17]
    ]]},
    { cc: 'PH', name: '菲律宾', parts: [
      [[120, 18], [122, 18], [123, 14], [121, 13], [120, 15]],
      [[123, 10], [126, 9], [126, 6], [124, 6], [122, 8]]
    ]},
    { cc: 'HK', name: '中国香港', parts: [[
      [113.8, 22.2], [114.4, 22.2], [114.4, 22.5], [113.8, 22.5]
    ]]},
    { cc: 'TW', name: '中国台湾', parts: [[
      [120.0, 22.0], [122.0, 25.0], [121.8, 25.3], [120.1, 22.6]
    ]]},
    { cc: 'MO', name: '中国澳门', parts: [[
      [113.5, 22.1], [113.6, 22.1], [113.6, 22.2], [113.5, 22.2]
    ]]}
  ];

  // ---- 数据聚合：按 country_code 加总 clicks ----
  function aggregate(items) {
    var map = {};
    var order = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (!it) continue;
      var cc = it.country_code;
      if (!cc) continue;
      cc = String(cc).toUpperCase();
      if (cc === 'UNKNOWN' || cc === 'LAN') continue;
      if (!map[cc]) {
        map[cc] = { clicks: 0, name: it.country_name || CC_NAME[cc] || cc };
        order.push(cc);
      }
      var c = typeof it.clicks === 'number' ? it.clicks : parseInt(it.clicks, 10);
      if (!isNaN(c) && c > 0) map[cc].clicks += c;
      if (!map[cc].name && it.country_name) map[cc].name = it.country_name;
    }
    var list = [];
    for (var k = 0; k < order.length; k++) list.push({ cc: order[k], v: map[order[k]] });
    return list;
  }

  // ---- 分档：4 分位阈值 ----
  function buildThresholds(max) {
    if (max <= 0) return [0, 0, 0];
    return [
      Math.ceil(max * 0.05),
      Math.ceil(max * 0.2),
      Math.ceil(max * 0.5)
    ];
  }

  function fillFor(clicks, th) {
    if (clicks <= 0) return FILL0;
    if (clicks <= th[0]) return FILL1;
    if (clicks <= th[1]) return FILL2;
    if (clicks <= th[2]) return FILL3;
    return FILL4;
  }

  // ---- SVG 元素创建 ----
  var SVGNS = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    if (attrs) {
      for (var k in attrs) {
        if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
      }
    }
    return e;
  }

  // ---- 主渲染 ----
  function renderGeoMap(el, items) {
    if (!el) return;
    el.innerHTML = '';
    items = items || [];

    var list = aggregate(items);
    var byCC = {};
    var max = 0;
    for (var i = 0; i < list.length; i++) {
      byCC[list[i].cc] = list[i].v;
      if (list[i].v.clicks > max) max = list[i].v.clicks;
    }
    var th = buildThresholds(max);

    // 容器
    var wrap = document.createElement('div');
    wrap.style.position = 'relative';
    wrap.style.width = '100%';
    wrap.style.background = PAPER;
    wrap.style.border = '1px solid ' + LINE;
    wrap.style.borderRadius = '4px';
    wrap.style.padding = '12px 12px 8px';
    wrap.style.boxSizing = 'border-box';

    var svgEl = svg('svg', {
      viewBox: '0 0 1000 500',
      width: '100%',
      height: '320',
      preserveAspectRatio: 'xMidYMid meet',
      xmlns: SVGNS
    });
    svgEl.style.display = 'block';

    // 背景海洋（极浅，避免大片留白恐慌）
    var ocean = svg('rect', {
      x: 0, y: 0, width: 1000, height: 500,
      fill: PAPER, stroke: 'none'
    });
    svgEl.appendChild(ocean);

    // 经纬网（极淡，仅作视觉锚点）
    var grid = svg('g', { stroke: LINE, 'stroke-width': 0.5, 'stroke-opacity': 0.6, fill: 'none' });
    var gx;
    for (gx = -150; gx <= 150; gx += 60) {
      var px = projX(gx);
      grid.appendChild(svg('line', { x1: px, y1: 0, x2: px, y2: 500 }));
    }
    var gy;
    for (gy = -60; gy <= 60; gy += 30) {
      var py = projY(gy);
      grid.appendChild(svg('line', { x1: 0, y1: py, x2: 1000, y2: py }));
    }
    svgEl.appendChild(grid);

    // 国家
    var gCountries = svg('g', { stroke: STROKE, 'stroke-width': 1, 'stroke-linejoin': 'round' });
    for (var ci = 0; ci < COUNTRIES.length; ci++) {
      var c = COUNTRIES[ci];
      var data = byCC[c.cc];
      var clicks = data ? data.clicks : 0;
      var name = (data && data.name) || c.name || CC_NAME[c.cc] || c.cc;
      var fill = fillFor(clicks, th);
      var d = '';
      for (var pi = 0; pi < c.parts.length; pi++) {
        d += pathFromLL(c.parts[pi]);
      }
      var p = svg('path', {
        d: d,
        'data-cc': c.cc,
        fill: fill,
        stroke: STROKE,
        'stroke-width': 1,
        'fill-rule': 'nonzero'
      });
      var title = document.createElementNS(SVGNS, 'title');
      title.textContent = name + '：' + clicks + ' 次';
      p.appendChild(title);
      gCountries.appendChild(p);
    }
    svgEl.appendChild(gCountries);

    // 空数据提示
    if (list.length === 0) {
      var empty = svg('text', {
        x: 500, y: 470,
        'text-anchor': 'middle',
        'font-size': 13,
        fill: MUTED,
        'font-family': 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
      });
      empty.textContent = '暂无数据';
      svgEl.appendChild(empty);
    }

    wrap.appendChild(svgEl);

    // 图例
    var legend = document.createElement('div');
    legend.style.display = 'flex';
    legend.style.alignItems = 'center';
    legend.style.gap = '10px';
    legend.style.marginTop = '6px';
    legend.style.fontFamily = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    legend.style.fontSize = '12px';
    legend.style.color = MUTED;
    legend.style.flexWrap = 'wrap';

    var swatches = [
      { color: FILL0, label: '无数据' },
      { color: FILL1, label: '少' },
      { color: FILL2, label: '中' },
      { color: FILL3, label: '多' },
      { color: FILL4, label: '很多' }
    ];
    for (var si = 0; si < swatches.length; si++) {
      var item = document.createElement('span');
      item.style.display = 'inline-flex';
      item.style.alignItems = 'center';
      item.style.gap = '4px';

      var box = document.createElement('span');
      box.style.display = 'inline-block';
      box.style.width = '14px';
      box.style.height = '14px';
      box.style.borderRadius = '3px';
      box.style.background = swatches[si].color;
      box.style.border = '1px solid ' + LINE;
      box.style.boxSizing = 'border-box';

      var txt = document.createElement('span');
      txt.textContent = swatches[si].label;
      txt.style.color = MUTED;

      item.appendChild(box);
      item.appendChild(txt);
      legend.appendChild(item);
    }

    wrap.appendChild(legend);
    el.appendChild(wrap);
  }

  window.renderGeoMap = renderGeoMap;
})();
