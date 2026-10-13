// 仪表盘页面逻辑（index.html）
(function () {
  // 页面初始化
  initKeyBanner();
  setActiveNav("dashboard");

  // 拉取总览数据并填充卡片
  function loadOverview() {
    api("/api/stats/overview").then(function (data) {
      data = data || {};
      var links = data.links || 0;
      setText("stat-links", links);
      setText("total-links", links);
      setText("stat-total", data.total_clicks || 0);
      setText("stat-today", data.today_clicks || 0);
      setText("stat-enabled", data.enabled_links || 0);
    }).catch(function (err) {
      toast("加载总览失败：" + err.message);
    });
  }

  // 最近 30 天点击柱状图
  function loadDaily() {
    api("/api/stats/daily?days=30").then(function (data) {
      var items = (data && data.items) || [];
      barChart(document.getElementById("daily-chart"), items);
    }).catch(function (err) {
      toast("加载趋势失败：" + err.message);
    });
  }

  // 点击最多的短链表格
  function loadTopLinks() {
    var table = document.getElementById("top-links");
    if (!table) return;
    var tbody = table.querySelector("tbody");
    if (!tbody) return;

    // top-links 只返回 {name(短码), clicks}，先拉链接列表做关联拿到 id/标题/短地址。
    api("/api/links?per_page=100").then(function (ldata) {
      var bySlug = {};
      var arr = (ldata && ldata.items) || [];
      for (var k = 0; k < arr.length; k++) { bySlug[arr[k].slug] = arr[k]; }
      return api("/api/stats/top-links?n=8").then(function (data) {
        return { items: (data && data.items) || [], bySlug: bySlug };
      });
    }).then(function (joined) {
      var items = joined.items;
      var bySlug = joined.bySlug;
      tbody.innerHTML = "";
      if (!items.length) {
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = 4;
        td.style.color = "#888";
        td.textContent = "还没有数据";
        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
      }

      for (var i = 0; i < items.length; i++) {
        var raw = items[i];
        var it = bySlug[raw.name] || { slug: raw.name, clicks: raw.clicks };
        it.clicks = raw.clicks;
        var tr2 = document.createElement("tr");

        // 短码（等宽，链接到详情页）
        var tdCode = document.createElement("td");
        var a = document.createElement("a");
        a.className = "mono";
        a.href = "detail.html?id=" + encodeURIComponent(it.id);
        a.textContent = it.slug || it.short_code || "";
        tdCode.appendChild(a);
        tr2.appendChild(tdCode);

        // 标题（没有标题则用 URL，截断 40 字符）
        var tdTitle = document.createElement("td");
        var label = it.title || it.url || "";
        if (label.length > 40) label = label.slice(0, 40) + "…";
        tdTitle.textContent = label;
        tr2.appendChild(tdTitle);

        // 点击数
        var tdClicks = document.createElement("td");
        tdClicks.className = "right mono";
        tdClicks.textContent = it.clicks || 0;
        tr2.appendChild(tdClicks);

        // 复制短地址
        var tdAct = document.createElement("td");
        var btn = document.createElement("button");
        btn.className = "btn tiny";
        btn.textContent = "复制";
        (function (shortUrl) {
          btn.addEventListener("click", function () {
            copyText(shortUrl);
          });
        })(it.short_url || "");
        tdAct.appendChild(btn);
        tr2.appendChild(tdAct);

        tbody.appendChild(tr2);
      }
    }).catch(function (err) {
      toast("加载排行失败：" + err.message);
    });
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  loadOverview();
  loadDaily();
  loadTopLinks();
})();
