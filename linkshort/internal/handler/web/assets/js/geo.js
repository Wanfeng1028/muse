(function () {
  initKeyBanner();
  setActiveNav("geo");

  var state = { days: 30, country: "", countryName: "" };

  function setText(id, txt) {
    var el = document.getElementById(id);
    if (el) el.textContent = txt;
  }

  function show(id, on) {
    var el = document.getElementById(id);
    if (!el) return;
    if (on) el.removeAttribute("hidden");
    else el.setAttribute("hidden", "hidden");
  }

  function loadGeo() {
    if (typeof window.initGeoToolbar === "function") {
      window.initGeoToolbar(document.getElementById("geo-toolbar"), state, onToolbarChange);
    }

    var qs = "?days=" + state.days + "&n=100";
    if (state.country) qs += "&country=" + encodeURIComponent(state.country);

    api("/api/stats/geo" + qs).then(function (data) {
      data = data || {};
      var items = data.items || [];
      var totalClicks = data.total_clicks || 0;
      var totalUv = data.total_uv || 0;
      var unknownPct = data.unknown_pct || 0;

      var countrySet = {};
      var c;
      for (var i = 0; i < items.length; i++) {
        c = items[i].country_code || "";
        if (c) countrySet[c] = true;
      }
      var countryCount = 0;
      for (var k in countrySet) {
        if (countrySet.hasOwnProperty(k)) countryCount++;
      }

      setText("sum-clicks", String(totalClicks));
      setText("sum-uv", String(totalUv));
      setText("sum-countries", String(countryCount));
      setText("sum-unknown", (Math.round(unknownPct * 10) / 10).toFixed(1) + "%");

      if (totalClicks === 0) {
        show("geo-summary", false);
        show("geo-map-panel", false);
        show("geo-rank-panel", false);
        show("geo-empty", true);
      } else {
        show("geo-summary", true);
        show("geo-map-panel", true);
        show("geo-rank-panel", true);
        show("geo-empty", false);
      }

      if (typeof window.renderGeoMap === "function") {
        window.renderGeoMap(document.getElementById("geo-map"), items);
      }
      if (typeof window.renderGeoRank === "function") {
        window.renderGeoRank(document.getElementById("geo-rank"), items, {
          mode: state.country ? "city" : "country",
          countryName: state.countryName
        });
      }

      if (state.country) {
        setText("geo-meta", (state.countryName || state.country) + " · 城市下钻");
      } else {
        setText("geo-meta", "近 " + state.days + " 天 · 共 " + totalClicks + " 次点击");
      }

      setText("map-title", state.country ? (state.countryName || state.country) + " · 城市地图" : "世界地图");
      setText("rank-title", state.country ? (state.countryName || state.country) + " · 城市排行" : "国家排行");
    }).catch(function (err) {
      toast("加载地域数据失败：" + err.message);
    });
  }

  function onToolbarChange(days) {
    state.days = days;
    loadGeo();
  }

  window.geoDrill = function (code, name) {
    state.country = code;
    state.countryName = name;
    loadGeo();
  };

  window.geoBack = function () {
    state.country = "";
    state.countryName = "";
    loadGeo();
  };

  loadGeo();
})();
