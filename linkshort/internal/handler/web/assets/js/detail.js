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
  var burnPurge = false;
  function loadDetail() {
    api("/api/meta").then(function (meta) {
      burnPurge = !!(meta && meta.burn_purge_after_destroy);
    }).catch(function () {}).then(function () {
      return api("/api/links/" + encodeURIComponent(id));
    }).then(function (data) {
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

    var limitsText = document.getElementById("link-limits-text");
    var editMaxVisits = document.getElementById("edit-maxvisits");
    var editBurn = document.getElementById("edit-burn");
    var editPurge = document.getElementById("edit-purge");
    var purgeEffective = !!(data.purge_after_burn || burnPurge);
    if (limitsText) {
      if (data.burn) {
        var burnState = data.enabled ? "阅后即焚（待访问，一次性）" : "阅后即焚（已销毁）";
        burnState += purgeEffective ? "，销毁后彻底删除" : "，销毁后仅禁用、数据留档";
        limitsText.textContent = burnState;
      } else if (data.max_visits != null) {
        limitsText.textContent = "限 " + data.max_visits + " 次，剩余 " + (data.remaining != null ? data.remaining : "—") + " 次";
      } else {
        limitsText.textContent = "无限制";
      }
    }
    if (editBurn) {
      editBurn.checked = !!data.burn;
    }
    if (editPurge) {
      editPurge.checked = !!data.purge_after_burn;
    }
    if (editMaxVisits) {
      editMaxVisits.value = data.max_visits != null ? data.max_visits : "";
    }

    var saveLimits = document.getElementById("save-limits");
    var clearLimits = document.getElementById("clear-limits");
    var pwText = document.getElementById("link-password-text");
    if (pwText) {
      pwText.textContent = data.has_password ? "已设置（访问需输密码）" : "未设置";
    }

    if (saveLimits) {
      saveLimits.addEventListener("click", function () {
        var mvVal = (editMaxVisits && editMaxVisits.value) ? parseInt(editMaxVisits.value, 10) : null;
        var body = {
          max_visits: (mvVal && mvVal >= 1) ? mvVal : null,
          burn: editBurn ? !!editBurn.checked : false,
          purge: editPurge ? !!editPurge.checked : false
        };

        api("/api/links/" + encodeURIComponent(id), {
          method: "PATCH",
          body: body
        }).then(function () {
          toast("已更新");
          loadDetail();
        }).catch(function (err) {
          toast(err && err.message ? err.message : "更新失败");
        });
      });
    }
    if (clearLimits) {
      clearLimits.addEventListener("click", function () {
        api("/api/links/" + encodeURIComponent(id), {
          method: "PATCH",
          body: { max_visits: null, burn: false, purge: false }
        }).then(function () {

          toast("已清除");
          loadDetail();
        }).catch(function (err) {
          toast(err && err.message ? err.message : "清除失败");
        });
      });
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

  // 密码设置 / 清除（一次性绑定，不在 fill 内重复绑）
  var editPassword = document.getElementById("edit-password");
  var savePassword = document.getElementById("save-password");
  var clearPassword = document.getElementById("clear-password");
  if (savePassword) {
    savePassword.addEventListener("click", function () {
      var pw = editPassword && editPassword.value ? editPassword.value : "";
      if (!pw) {
        toast("请先输入新密码");
        return;
      }
      api("/api/links/" + encodeURIComponent(id), {
        method: "PATCH",
        body: { password: pw }
      }).then(function () {
        toast("密码已设置");
        if (editPassword) editPassword.value = "";
        loadDetail();
      }).catch(function (err) {
        toast(err && err.message ? err.message : "设置失败");
      });
    });
  }
  if (clearPassword) {
    clearPassword.addEventListener("click", function () {
      if (!confirm("确定清除访问密码吗？清除后链接变为公开访问。")) return;
      api("/api/links/" + encodeURIComponent(id), {
        method: "PATCH",
        body: { password: "" }
      }).then(function () {
        toast("密码已清除");
        loadDetail();
      }).catch(function (err) {
        toast(err && err.message ? err.message : "清除失败");
      });
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
