// 链接详情页面逻辑（detail.html）
(function () {
  initKeyBanner();
  setActiveNav("links");

  // 解析 URL 中的 id
  function getQuery(name) {
    var m = location.search.match(new RegExp("[?&]" + name + "=([^&]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  var id = getQuery("id");
  if (!id) {
    toast("缺少链接 id");
    return;
  }

  // 加载详情
  function loadDetail() {
    api("/api/links/" + encodeURIComponent(id)).then(function (data) {
      if (!data) return;
      fill(data);
    }).catch(function (err) {
      toast("加载详情失败：" + err.message);
    });
  }

  // 填充详情字段
  function fill(data) {
    var titleEl = document.getElementById("link-title");
    if (titleEl) titleEl.textContent = data.title || "未命名短链";

    var urlEl = document.getElementById("link-url");
    if (urlEl) {
      urlEl.textContent = data.url || "";
      urlEl.href = data.url || "#";
    }

    var shortEl = document.getElementById("link-short");
    if (shortEl) shortEl.textContent = data.short_url || "";

    var createdEl = document.getElementById("link-created");
    if (createdEl) createdEl.textContent = fmtDate(data.created_at);

    var expEl = document.getElementById("link-expires");
    if (expEl) expEl.textContent = data.expires_at ? fmtDate(data.expires_at) : "长期有效";

    var enabledEl = document.getElementById("link-enabled");
    if (enabledEl) {
      enabledEl.checked = !!data.enabled;
      enabledEl.addEventListener("change", function () {
        var val = enabledEl.checked;
        enabledEl.disabled = true;
        api("/api/links/" + encodeURIComponent(id), {
          method: "PATCH",
          body: { enabled: val }
        }).then(function () {
          toast("已更新");
          enabledEl.disabled = false;
        }).catch(function (err) {
          toast("更新失败：" + err.message);
          enabledEl.checked = !val;
          enabledEl.disabled = false;
        });
      });
    }

    // 在 info-panel 追加点击数一行
    var panel = document.getElementById("info-panel");
    if (panel) {
      var oldRow = panel.querySelector("[data-clicks-row]");
      if (oldRow) oldRow.parentNode.removeChild(oldRow);
      var kv = panel.querySelector(".kv");
      if (kv) {
        var row = document.createElement("div");
        row.className = "kv-row";
        row.setAttribute("data-clicks-row", "1");
        var key = document.createElement("div");
        key.className = "kv-key";
        key.textContent = "点击数";
        var val2 = document.createElement("div");
        val2.className = "kv-val mono";
        val2.textContent = data.clicks || 0;
        row.appendChild(key);
        row.appendChild(val2);
        kv.appendChild(row);
      }
    }

    // 二维码
    var qr = document.getElementById("qr-img");
    if (qr) {
      qr.src = "/api/links/" + encodeURIComponent(id) + "/qrcode.png?size=240&key=" + encodeURIComponent(API_KEY);
    }
  }

  // 复制短地址按钮
  var copyBtn = document.getElementById("copy-short");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var el = document.getElementById("link-short");
      if (el) copyText(el.textContent || "");
    });
  }

  // 本链最近 30 天点击
  function loadDaily() {
    api("/api/links/" + encodeURIComponent(id) + "/daily?days=30").then(function (data) {
      var items = (data && data.items) || [];
      barChart(document.getElementById("link-chart"), items);
    }).catch(function (err) {
      toast("加载趋势失败：" + err.message);
    });
  }

  // 来源 Top
  function loadReferers() {
    var table = document.getElementById("referer-table");
    if (!table) return;
    var tbody = table.querySelector("tbody");
    if (!tbody) return;

    api("/api/stats/top-referers?n=8").then(function (data) {
      var items = (data && data.items) || [];
      tbody.innerHTML = "";
      if (!items.length) {
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = 2;
        td.style.color = "#888";
        td.textContent = "还没有来源数据";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }
      for (var i = 0; i < items.length; i++) {
        var it = items[i];
        var tr2 = document.createElement("tr");
        var tdName = document.createElement("td");
        tdName.textContent = it.name || "(直接访问)";
        var tdClicks = document.createElement("td");
        tdClicks.className = "right mono";
        tdClicks.textContent = it.clicks || 0;
        tr2.appendChild(tdName);
        tr2.appendChild(tdClicks);
        tbody.appendChild(tr2);
      }
    }).catch(function (err) {
      toast("加载来源失败：" + err.message);
    });
  }

  loadDetail();
  loadDaily();
  loadReferers();
})();
