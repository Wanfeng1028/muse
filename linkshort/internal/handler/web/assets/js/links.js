// 链接管理页面逻辑（links.html）
(function () {
  initKeyBanner();
  setActiveNav("links");

  // 列表状态
  var state = {
    q: "",
    sort: "created_at",
    page: 1,
    per: 20
  };
  var total = 0;

  var searchEl = document.getElementById("search");
  var sortEl = document.getElementById("sort");
  var table = document.getElementById("links-table");
  var tbody = table ? table.querySelector("tbody") : null;
  var pageInfo = document.getElementById("page-info");
  var prevBtn = document.getElementById("prev-page");
  var nextBtn = document.getElementById("next-page");
  var exportBtn = document.getElementById("export-btn");
  var importBtn = document.getElementById("import-btn");
  var importFile = document.getElementById("import-file");

  // 加载列表
  function load() {
    var params = [];
    if (state.q) params.push("search=" + encodeURIComponent(state.q));
    params.push("page=" + state.page);
    params.push("per_page=" + state.per);
    params.push("sort=" + encodeURIComponent(state.sort));
    var url = "/api/links?" + params.join("&");

    api(url).then(function (data) {
      data = data || {};
      var items = data.items || [];
      total = data.total || 0;
      render(items);
      renderPager();
      setText("total-links", total);
    }).catch(function (err) {
      toast("加载列表失败：" + err.message);
    });
  }

  // 渲染表格
  function render(items) {
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!items.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 6;
      td.style.color = "#888";
      td.textContent = "没有匹配的短链";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    for (var i = 0; i < items.length; i++) {
      (function (it) {
        var tr2 = document.createElement("tr");

        // 短码
        var tdCode = document.createElement("td");
        var aCode = document.createElement("a");
        aCode.className = "mono";
        aCode.href = "detail.html?id=" + encodeURIComponent(it.id);
        aCode.textContent = it.slug || it.short_code || "";
        tdCode.appendChild(aCode);
        tr2.appendChild(tdCode);

        // 标题 + URL
        var tdUrl = document.createElement("td");
        var titleLine = document.createElement("div");
        var t = it.title || "";
        if (t.length > 40) t = t.slice(0, 40) + "…";
        titleLine.textContent = t;
        var urlLine = document.createElement("div");
        urlLine.style.fontSize = "12px";
        urlLine.style.color = "#888";
        var u = it.url || "";
        if (u.length > 60) u = u.slice(0, 60) + "…";
        urlLine.textContent = u;
        tdUrl.appendChild(titleLine);
        tdUrl.appendChild(urlLine);
        tr2.appendChild(tdUrl);

        // 点击数
        var tdClicks = document.createElement("td");
        tdClicks.className = "right mono";
        tdClicks.textContent = it.clicks || 0;
        tr2.appendChild(tdClicks);

        // 启用 checkbox
        var tdEnabled = document.createElement("td");
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!it.enabled;
        cb.addEventListener("change", function () {
          var val = cb.checked;
          cb.disabled = true;
          api("/api/links/" + encodeURIComponent(it.id), {
            method: "PATCH",
            body: { enabled: val }
          }).then(function () {
            toast("已更新");
            cb.disabled = false;
          }).catch(function (err) {
            toast("更新失败：" + err.message);
            cb.checked = !val;
            cb.disabled = false;
          });
        });
        tdEnabled.appendChild(cb);
        tr2.appendChild(tdEnabled);

        // 到期时间
        var tdExp = document.createElement("td");
        tdExp.className = "mono";
        tdExp.textContent = it.expires_at ? fmtDate(it.expires_at) : "长期";
        tr2.appendChild(tdExp);

        // 操作：复制 / 删除
        var tdAct = document.createElement("td");

        var copyBtn = document.createElement("button");
        copyBtn.className = "btn tiny";
        copyBtn.textContent = "复制";
        copyBtn.style.marginRight = "6px";
        copyBtn.addEventListener("click", function () {
          copyText(it.short_url || "");
        });
        tdAct.appendChild(copyBtn);

        var delBtn = document.createElement("button");
        delBtn.className = "btn tiny ghost";
        delBtn.textContent = "删除";
        delBtn.addEventListener("click", function () {
          if (!confirm("确定要删除这条短链吗？此操作不可撤销。")) return;
          api("/api/links/" + encodeURIComponent(it.id), {
            method: "DELETE"
          }).then(function () {
            toast("已删除");
            load();
          }).catch(function (err) {
            toast("删除失败：" + err.message);
          });
        });
        tdAct.appendChild(delBtn);

        tr2.appendChild(tdAct);

        tbody.appendChild(tr2);
      })(items[i]);
    }
  }

  // 更新分页信息
  function renderPager() {
    var totalPages = Math.max(1, Math.ceil(total / state.per));
    if (pageInfo) {
      pageInfo.textContent = "第 " + state.page + " 页 / 共 " + total + " 条";
    }
    if (prevBtn) prevBtn.disabled = state.page <= 1;
    if (nextBtn) nextBtn.disabled = state.page >= totalPages;
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  // 搜索防抖
  var searchTimer = null;
  if (searchEl) {
    searchEl.addEventListener("input", function () {
      if (searchTimer) clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.q = searchEl.value.trim();
        state.page = 1;
        load();
      }, 400);
    });
  }

  // 排序切换
  if (sortEl) {
    sortEl.addEventListener("change", function () {
      state.sort = sortEl.value;
      state.page = 1;
      load();
    });
  }

  // 翻页
  if (prevBtn) {
    prevBtn.addEventListener("click", function () {
      if (state.page > 1) {
        state.page -= 1;
        load();
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener("click", function () {
      var totalPages = Math.max(1, Math.ceil(total / state.per));
      if (state.page < totalPages) {
        state.page += 1;
        load();
      }
    });
  }

  // 导入 CSV
  if (importBtn && importFile) {
    importBtn.addEventListener("click", function () {
      importFile.click();
    });
    importFile.addEventListener("change", function () {
      var f = importFile.files && importFile.files[0];
      if (!f) return;
      var fd = new FormData();
      fd.append("file", f);
      importBtn.disabled = true;
      api("/api/import", {
        method: "POST",
        formData: fd
      }).then(function (res) {
        res = res || {};
        toast("导入完成：新增 " + (res.imported || 0) + "，跳过 " + (res.skipped || 0) + "，错误 " + (res.errors || 0));
        importBtn.disabled = false;
        importFile.value = "";
        state.page = 1;
        load();
      }).catch(function (err) {
        toast("导入失败：" + err.message);
        importBtn.disabled = false;
        importFile.value = "";
      });
    });
  }

  // 导出 CSV
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      location.href = "/api/export.csv?key=" + encodeURIComponent(API_KEY);
    });
  }

  // 首次加载
  load();
})();
