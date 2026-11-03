// 公共工具与 API 封装（ES5 语法）
// 说明：本文件被所有页面引入，必须在其它页面脚本之前加载。

// 从 localStorage 读取管理员密钥
var API_KEY = localStorage.getItem("linkshort_key") || "";

// 顶部小黑条 toast（2 秒后消失）
function toast(msg) {
  var el = document.createElement("div");
  el.textContent = msg;
  el.style.position = "fixed";
  el.style.top = "16px";
  el.style.left = "50%";
  el.style.transform = "translateX(-50%)";
  el.style.background = "#111";
  el.style.color = "#fff";
  el.style.padding = "8px 16px";
  el.style.borderRadius = "6px";
  el.style.fontSize = "13px";
  el.style.zIndex = "9999";
  el.style.boxShadow = "0 4px 12px rgba(0,0,0,.25)";
  el.style.transition = "opacity .3s";
  document.body.appendChild(el);
  setTimeout(function () {
    el.style.opacity = "0";
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 300);
  }, 2000);
}

// HTML 转义，防止注入
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// 格式化日期为 "M-D HH:mm"
function fmtDate(iso) {
  if (!iso) return "";
  var d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  var p = function (n) { return n < 10 ? "0" + n : "" + n; };
  return (d.getMonth() + 1) + "-" + d.getDate() + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}

// 复制文本：优先使用剪贴板 API，失败时回落到 textarea
function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function () {
      toast("已复制");
    }, function () {
      fallbackCopy(text);
    });
  } else {
    fallbackCopy(text);
  }
}
function fallbackCopy(text) {
  var ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); toast("已复制"); }
  catch (e) { toast("复制失败，请手动选择"); }
  document.body.removeChild(ta);
}

// 请求封装：自动加 X-API-Key；401 时提示输入 key 并重试一次
function api(path, opts) {
  opts = opts || {};
  var method = opts.method || "GET";
  var headers = {};
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  var body;
  if (opts.formData) {
    body = opts.formData; // 不设置 Content-Type，浏览器自动带 boundary
  } else if (opts.body !== undefined && opts.body !== null) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  function doFetch() {
    return fetch(path, {
      method: method,
      headers: headers,
      body: body
    }).then(function (res) {
      if (res.status === 401) {
        var input = prompt("请输入管理员密钥（Admin Key）：", API_KEY || "");
        if (input) {
          API_KEY = input;
          localStorage.setItem("linkshort_key", API_KEY);
          headers["X-API-Key"] = API_KEY;
          return fetch(path, { method: method, headers: headers, body: body }).then(function (res2) {
            return handleRes(res2);
          });
        }
      }
      return handleRes(res);
    });
  }

  function handleRes(res) {
    if (res.status === 204) return null;
    if (!res.ok) {
      return res.json().then(function (data) {
        var msg = (data && data.error) ? data.error : ("请求失败 (" + res.status + ")");
        throw new Error(msg);
      }, function () {
        throw new Error("请求失败 (" + res.status + ")");
      });
    }
    var ct = res.headers.get("content-type") || "";
    if (ct.indexOf("application/json") >= 0) return res.json();
    return res.text();
  }

  return doFetch();
}

// 手写内联 SVG 柱状图：items = [{date, clicks}]
function barChart(el, items) {
  if (!el) return;
  el.innerHTML = "";
  items = items || [];
  if (!items.length) {
    el.innerHTML = '<div class="chart-empty" style="color:#888;font-size:13px;padding:20px 0">还没有点击数据</div>';
    return;
  }

  var W = 600, H = 180;
  var padL = 30, padR = 10, padT = 16, padB = 26;
  var innerW = W - padL - padR;
  var innerH = H - padT - padB;

  var max = 0;
  for (var i = 0; i < items.length; i++) {
    var v = Number(items[i].clicks) || 0;
    if (v > max) max = v;
  }
  if (max <= 0) max = 1;

  var n = items.length;
  var slot = innerW / n;
  var barW = Math.max(2, Math.min(slot * 0.7, 40));

  var svg = [];
  svg.push('<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="180" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">');

  // 基线
  svg.push('<line x1="' + padL + '" y1="' + (padT + innerH) + '" x2="' + (padL + innerW) + '" y2="' + (padT + innerH) + '" stroke="#e5e5e5" stroke-width="1"/>');

  // 柱状
  for (var j = 0; j < n; j++) {
    var item = items[j];
    var clicks = Number(item.clicks) || 0;
    var h = innerH * (clicks / max);
    if (clicks > 0 && h < 1) h = 1;
    var x = padL + slot * j + (slot - barW) / 2;
    var y = padT + innerH - h;
    svg.push('<rect x="' + x.toFixed(2) + '" y="' + y.toFixed(2) + '" width="' + barW.toFixed(2) + '" height="' + h.toFixed(2) + '" fill="#B3402A">');
    svg.push('<title>' + esc(item.date) + "：" + clicks + ' 次</title>');
    svg.push('</rect>');
  }

  // X 轴首/中/尾日期
  var firstDate = items[0].date || "";
  var midDate = items[Math.floor(n / 2)].date || "";
  var lastDate = items[n - 1].date || "";
  svg.push('<text x="' + padL + '" y="' + (H - 8) + '" font-size="10" fill="#888">' + esc(firstDate) + '</text>');
  svg.push('<text x="' + (padL + innerW / 2) + '" y="' + (H - 8) + '" font-size="10" fill="#888" text-anchor="middle">' + esc(midDate) + '</text>');
  svg.push('<text x="' + (padL + innerW) + '" y="' + (H - 8) + '" font-size="10" fill="#888" text-anchor="end">' + esc(lastDate) + '</text>');

  svg.push('</svg>');
  el.innerHTML = svg.join("");
}

// 高亮当前导航
function setActiveNav(name) {
  var links = document.querySelectorAll("a[data-nav]");
  for (var i = 0; i < links.length; i++) {
    if (links[i].getAttribute("data-nav") === name) {
      links[i].className = (links[i].className + " active").replace(/\s+/g, " ").trim();
    }
  }
}

// 初始化密钥提示条
function initKeyBanner() {
  var banner = document.getElementById("key-banner");
  var changeBtn = document.getElementById("change-key");

  if (banner) {
    if (!API_KEY) {
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
    banner.addEventListener("click", function () {
      var input = prompt("请输入管理员密钥（Admin Key）：", API_KEY || "");
      if (input) {
        API_KEY = input;
        localStorage.setItem("linkshort_key", API_KEY);
        location.reload();
      }
    });
  }

  if (changeBtn) {
    changeBtn.addEventListener("click", function () {
      API_KEY = "";
      localStorage.removeItem("linkshort_key");
      var input = prompt("请输入新的管理员密钥（Admin Key）：", "");
      if (input) {
        API_KEY = input;
        localStorage.setItem("linkshort_key", API_KEY);
      }
      location.reload();
    });
  }
}
