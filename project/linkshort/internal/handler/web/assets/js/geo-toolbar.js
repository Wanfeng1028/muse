// internal/handler/web/assets/js/geo-toolbar.js
// linkshort v1.9 B5 - 地域统计工具栏：时间维度切换 + 导出 CSV
// 依赖：common.js 提供的全局 API_KEY（可选）

window.initGeoToolbar = function (el, state, onChange) {
  if (!el) return;
  if (!state || typeof state !== "object") state = { days: 30 };
  if (state.days !== 7 && state.days !== 30) state.days = 30;
  if (typeof onChange !== "function") onChange = function () {};

  el.innerHTML = "";
  el.className = (el.className || "") + " geo-toolbar";

  function makeBtn(label, extraClass) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "btn" + (extraClass ? " " + extraClass : "");
    b.textContent = label;
    return b;
  }

  var btn7 = makeBtn("近 7 天", "");
  var btn30 = makeBtn("近 30 天", "");
  var spacer = document.createElement("span");
  spacer.className = "spacer";

  var exportBtn = makeBtn("", "ghost");
  // 下载 SVG 线性小图标（纯 DOM 拼装，无 innerHTML 注入风险）
  var svgNS = "http://www.w3.org/2000/svg";
  var svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", "14");
  svg.setAttribute("height", "14");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.style.marginRight = "6px";
  svg.style.verticalAlign = "-2px";
  var p1 = document.createElementNS(svgNS, "path");
  p1.setAttribute("d", "M12 3v12");
  var p2 = document.createElementNS(svgNS, "path");
  p2.setAttribute("d", "M7 10l5 5 5-5");
  var p3 = document.createElementNS(svgNS, "path");
  p3.setAttribute("d", "M5 21h14");
  svg.appendChild(p1);
  svg.appendChild(p2);
  svg.appendChild(p3);
  var exportLabel = document.createElement("span");
  exportLabel.textContent = "导出 CSV";
  exportBtn.appendChild(svg);
  exportBtn.appendChild(exportLabel);

  el.appendChild(btn7);
  el.appendChild(btn30);
  el.appendChild(spacer);
  el.appendChild(exportBtn);

  function sync() {
    btn7.className = "btn" + (state.days === 7 ? " primary" : "");
    btn30.className = "btn" + (state.days === 30 ? " primary" : "");
  }

  function setDays(d) {
    if (d !== 7 && d !== 30) return;
    if (state.days === d) return;
    state.days = d;
    sync();
    onChange(d);
  }

  btn7.onclick = function () { setDays(7); };
  btn30.onclick = function () { setDays(30); };

  exportBtn.onclick = function () {
    var url = "/api/stats/geo.csv?days=" + state.days;
    if (typeof API_KEY !== "undefined" && API_KEY) {
      url += "&key=" + encodeURIComponent(API_KEY);
    }
    window.location.href = url;
  };

  sync();
};
