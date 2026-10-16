// static/app.js —— 原生 JS，无框架，简体中文注释

/* ========== 通用工具 ========== */

// 分转元字符串：千分位、保留两位小数、去掉多余的零
function fmtMoney(cents) {
  if (cents === null || cents === undefined || isNaN(cents)) return "0";
  var n = Number(cents);
  var negative = n < 0;
  n = Math.abs(n);
  var yuan = n / 100;
  var str = yuan.toFixed(2);
  // 去掉末尾的 ".00" 或 ".X0"
  str = str.replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
  // 加千分位
  var parts = str.split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  str = parts.join(".");
  return (negative ? "-" : "") + str;
}

// fetch JSON 封装
async function api(path, opts) {
  opts = opts || {};
  var fetchOpts = {
    method: opts.method || "GET",
    headers: opts.headers || {}
  };
  if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
    fetchOpts.body = JSON.stringify(opts.body);
    fetchOpts.headers["Content-Type"] = "application/json";
  } else if (opts.body !== undefined) {
    fetchOpts.body = opts.body;
  }
  if (opts.headers) {
    for (var k in opts.headers) {
      fetchOpts.headers[k] = opts.headers[k];
    }
  }
  var res = await fetch(path, fetchOpts);
  var data = null;
  var text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch (e) { data = text; }
  }
  if (!res.ok) {
    var msg = (data && data.detail) ? data.detail : ("请求失败：" + res.status);
    throw new Error(msg);
  }
  return data;
}

// 确认后删除
async function confirmDelete(url) {
  if (!confirm("确定要删除吗？此操作不可恢复。")) return false;
  try {
    await api(url, { method: "DELETE" });
    return true;
  } catch (e) {
    alert("删除失败：" + e.message);
    return false;
  }
}

// 类型中文
function typeText(t) {
  if (t === "income") return "收入";
  if (t === "expense") return "支出";
  if (t === "transfer") return "转账";
  return t;
}

// 今天 YYYY-MM-DD
function todayStr() {
  var d = new Date();
  var m = String(d.getMonth() + 1).padStart(2, "0");
  var day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + m + "-" + day;
}

/* ========== 交易页 ========== */

function initTransactionsPage() {
  var fType = document.getElementById("f-type");
  var fAccount = document.getElementById("f-account");
  var fCategory = document.getElementById("f-category");
  var fFrom = document.getElementById("f-from");
  var fTo = document.getElementById("f-to");
  var fQ = document.getElementById("f-q");
  var btnSearch = document.getElementById("btn-search");
  var txBody = document.getElementById("tx-body");
  var btnPrev = document.getElementById("btn-prev");
  var btnNext = document.getElementById("btn-next");
  var pageInfo = document.getElementById("page-info");
  var txForm = document.getElementById("tx-form");
  var tType = document.getElementById("t-type");
  var tAccount = document.getElementById("t-account");
  var tTo = document.getElementById("t-to");
  var tCategory = document.getElementById("t-category");
  var tAmount = document.getElementById("t-amount");
  var tDate = document.getElementById("t-date");
  var tNote = document.getElementById("t-note");
  var tCurrency = document.getElementById("t-currency");
  var tToRow = document.getElementById("t-to-row");
  var tCategoryRow = document.getElementById("t-category-row");

  var accountsMap = {};
  var categoriesMap = {};
  var expenseCats = [];
  var incomeCats = [];
  var currentPage = 1;
  var totalPages = 1;

  // 填充账户下拉
  function fillAccountSelect(sel, includeEmpty) {
    if (!sel) return;
    var html = includeEmpty ? '<option value="">全部</option>' : "";
    Object.keys(accountsMap).forEach(function (id) {
      var a = accountsMap[id];
      html += '<option value="' + id + '">' + a.name + '</option>';
    });
    sel.innerHTML = html;
  }

  // 填充分类下拉（按类型过滤）
  function fillCategorySelect(sel, type, includeEmpty) {
    if (!sel) return;
    var list = [];
    if (type === "income") list = incomeCats;
    else if (type === "expense") list = expenseCats;
    else list = expenseCats.concat(incomeCats);
    var html = includeEmpty ? '<option value="">全部</option>' : "";
    list.forEach(function (c) {
      html += '<option value="' + c.id + '">' + c.name + '</option>';
    });
    sel.innerHTML = html;
  }

  // 初始化下拉
  async function loadRefs() {
    var accs = await api("/api/accounts");
    accountsMap = {};
    (accs || []).forEach(function (a) { accountsMap[a.id] = a; });

    var cats = await api("/api/categories");
    // 兼容两种返回：数组 或 {expense:[],income:[]}
    var allCats = [];
    if (Array.isArray(cats)) {
      allCats = cats;
    } else if (cats && (cats.expense || cats.income)) {
      allCats = (cats.expense || []).concat(cats.income || []);
    }
    categoriesMap = {};
    expenseCats = [];
    incomeCats = [];
    allCats.forEach(function (c) {
      categoriesMap[c.id] = c;
      if (c.kind === "income") incomeCats.push(c);
      else expenseCats.push(c);
    });

    fillAccountSelect(fAccount, true);
    fillAccountSelect(tAccount, false);
    fillAccountSelect(tTo, false);
    fillCategorySelect(fCategory, fType ? fType.value : "", true);
    fillCategorySelect(tCategory, tType ? tType.value : "expense", false);
  }

  // 类型切换：显示/隐藏行、过滤分类
  function updateFormRows() {
    var type = tType.value;
    if (type === "transfer") {
      if (tToRow) tToRow.style.display = "";
      if (tCategoryRow) tCategoryRow.style.display = "none";
      if (tCategory) tCategory.value = "";
    } else {
      if (tToRow) tToRow.style.display = "none";
      if (tCategoryRow) tCategoryRow.style.display = "";
      fillCategorySelect(tCategory, type, false);
    }
  }

  // 加载交易列表
  async function loadTx(page) {
    currentPage = page || 1;
    var limit = 20;
    var offset = (currentPage - 1) * limit;
    var params = new URLSearchParams();
    params.set("limit", limit);
    params.set("offset", offset);
    if (fType && fType.value) params.set("type", fType.value);
    if (fAccount && fAccount.value) params.set("account_id", fAccount.value);
    if (fCategory && fCategory.value) params.set("category_id", fCategory.value);
    if (fFrom && fFrom.value) params.set("date_from", fFrom.value);
    if (fTo && fTo.value) params.set("date_to", fTo.value);
    if (fQ && fQ.value) params.set("q", fQ.value);

    var data = await api("/api/transactions?" + params.toString());
    var items = Array.isArray(data) ? data : (data.items || data.transactions || []);
    var total = (data && typeof data.total === "number") ? data.total : items.length;
    totalPages = Math.max(1, Math.ceil(total / limit));

    if (!items.length) {
      txBody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#999">暂无记录</td></tr>';
    } else {
      var html = "";
      items.forEach(function (tx) {
        var accName = accountsMap[tx.account_id] ? accountsMap[tx.account_id].name : "-";
        var catName = tx.category_id && categoriesMap[tx.category_id] ? categoriesMap[tx.category_id].name : "-";
        var amt = tx.amount_cents || 0;
        var amtStr, amtColor;
        if (tx.type === "income") { amtStr = "+" + fmtMoney(amt); amtColor = "green"; }
        else if (tx.type === "expense") { amtStr = "−" + fmtMoney(amt); amtColor = "red"; }
        else { amtStr = fmtMoney(amt); amtColor = "blue"; }
        var note = tx.note ? tx.note : "";
        html += "<tr>" +
          "<td>" + (tx.occurred_on || "") + "</td>" +
          "<td>" + typeText(tx.type) + "</td>" +
          "<td>" + accName + "</td>" +
          "<td>" + catName + "</td>" +
          '<td style="color:' + amtColor + '">' + amtStr + "</td>" +
          "<td>" + (tx.currency || "CNY") + "</td>" +
          "<td>" + note + "</td>" +
          '<td><button class="btn-del-tx" data-id="' + tx.id + '">删除</button></td>' +
          "</tr>";
      });
      txBody.innerHTML = html;
      txBody.querySelectorAll(".btn-del-tx").forEach(function (btn) {
        btn.addEventListener("click", async function () {
          var id = btn.getAttribute("data-id");
          var ok = await confirmDelete("/api/transactions/" + id);
          if (ok) loadTx(currentPage);
        });
      });
    }

    if (pageInfo) pageInfo.textContent = "第 " + currentPage + " / " + totalPages + " 页";
    if (btnPrev) btnPrev.disabled = currentPage <= 1;
    if (btnNext) btnNext.disabled = currentPage >= totalPages;
  }

  // 事件绑定
  if (fType) fType.addEventListener("change", function () {
    fillCategorySelect(fCategory, fType.value, true);
  });
  if (btnSearch) btnSearch.addEventListener("click", function () { loadTx(1); });
  if (btnPrev) btnPrev.addEventListener("click", function () { if (currentPage > 1) loadTx(currentPage - 1); });
  if (btnNext) btnNext.addEventListener("click", function () { if (currentPage < totalPages) loadTx(currentPage + 1); });
  if (tType) tType.addEventListener("change", updateFormRows);

  if (txForm) {
    txForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var type = tType.value;
      var amountYuan = parseFloat(tAmount.value);
      if (isNaN(amountYuan)) { alert("请输入有效金额"); return; }
      var payload = {
        type: type,
        account_id: tAccount.value ? parseInt(tAccount.value) : null,
        amount_cents: Math.round(amountYuan * 100),
        date: tDate.value || todayStr(),
        note: tNote.value || null,
        currency: tCurrency && tCurrency.value ? tCurrency.value : "CNY"
      };
      if (type === "transfer") {
        if (!tTo.value) { alert("请选择转入账户"); return; }
        payload.to_account_id = parseInt(tTo.value);
        payload.category_id = null;
      } else {
        payload.category_id = tCategory.value ? parseInt(tCategory.value) : null;
        payload.to_account_id = null;
      }
      try {
        await api("/api/transactions", { method: "POST", body: payload });
        txForm.reset();
        if (tDate) tDate.value = todayStr();
        updateFormRows();
        loadTx(1);
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    });
  }

  if (tDate) tDate.value = todayStr();
  updateFormRows();
  loadRefs().then(function () { loadTx(1); }).catch(function (e) { alert("加载失败：" + e.message); });
}

/* ========== 汇率页 ========== */

function initCurrenciesPage() {
var fxBody = document.getElementById("fx-body");
var fxForm = document.getElementById("fx-form");
var fxCode = document.getElementById("fx-code");
var fxRate = document.getElementById("fx-rate");

async function loadFx() {
var data = await api("/api/currencies");
var baseCode = document.getElementById("fx-base-code");
var base = baseCode? baseCode.getAttribute("data-base"): null;
var rowsHtml = "";
var optsHtml = "";
(data || []).forEach(function (c) {
rowsHtml += "<tr>" +
"<td>" + c.code + "</td>" +
"<td>" + c.rate_to_base + "</td>" +
"<td>" + (c.updated_at || "") + "</td>" +
"<td>" + (c.code === base? "本位币": "-") + "</td>" +
"</tr>";
if (c.code!== base) {
optsHtml += '<option value="' + c.code + '">' + c.code + "</option>";
}
});
// 常用币种补齐（库中没有的也可新增）
["USD", "EUR", "JPY", "GBP", "HKD", "AUD", "CAD", "SGD"].forEach(function (code) {
var exists = (data || []).some(function (c) { return c.code === code;});
if (!exists && code!== base) {
optsHtml += '<option value="' + code + '">' + code + "</option>";
}
});
if (fxBody) fxBody.innerHTML = rowsHtml || '<tr><td colspan="4" style="text-align:center;color:#999">暂无汇率</td></tr>';
if (fxCode) fxCode.innerHTML = optsHtml;
}

if (fxForm) {
fxForm.addEventListener("submit", async function (e) {
e.preventDefault();
var rate = parseFloat(fxRate.value);
if (!(rate > 0)) { alert("请输入大于 0 的汇率"); return;}
try {
await api("/api/currencies/" + encodeURIComponent(fxCode.value), {
method: "PUT",
body: { rate_to_base: rate}
});
fxForm.reset();
loadFx();
} catch (err) {
alert("保存失败：" + err.message);
}
});
}

loadFx().catch(function (e) { alert("加载失败：" + e.message);});
}

/* ========== 账户页 ========== */

function initAccountsPage() {
  var accForm = document.getElementById("acc-form");
  var aName = document.getElementById("a-name");
  var aType = document.getElementById("a-type");
  var aCurrency = document.getElementById("a-currency");
  var aOpening = document.getElementById("a-opening");
  var aNote = document.getElementById("a-note");

  if (accForm) {
    accForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var openingYuan = parseFloat(aOpening.value) || 0;
      var payload = {
        name: aName.value,
        type: aType.value,
        currency: aCurrency.value || "CNY",
        opening_balance_cents: Math.round(openingYuan * 100),
        note: aNote.value || null
      };
      try {
        await api("/api/accounts", { method: "POST", body: payload });
        location.reload();
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    });
  }

  document.querySelectorAll(".btn-del-account").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var id = btn.getAttribute("data-id");
      var ok = await confirmDelete("/api/accounts/" + id);
      if (ok) location.reload();
    });
  });
}

/* ========== 分类页 ========== */

function initCategoriesPage() {
  var catForm = document.getElementById("cat-form");
  var cName = document.getElementById("c-name");
  var cKind = document.getElementById("c-kind");
  var cIcon = document.getElementById("c-icon");
  var cColor = document.getElementById("c-color");
  var cSort = document.getElementById("c-sort");

  if (catForm) {
    catForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var payload = {
        name: cName.value,
        kind: cKind.value,
        icon: cIcon.value || null,
        color: cColor.value || null,
        sort_order: parseInt(cSort.value) || 0
      };
      try {
        await api("/api/categories", { method: "POST", body: payload });
        location.reload();
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    });
  }

  document.querySelectorAll(".btn-del-category").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var id = btn.getAttribute("data-id");
      if (!confirm("确定要删除吗？此操作不可恢复。")) return;
      try {
        await api("/api/categories/" + id, { method: "DELETE" });
        location.reload();
      } catch (err) {
        if (err.message && err.message.indexOf("使用") >= 0) {
          alert("该分类正被使用，无法删除");
        } else {
          alert("删除失败：" + err.message);
        }
      }
    });
  });
}

/* ========== 预算页 ========== */

function initBudgetsPage() {
  var monthInput = document.getElementById("month");
  var bForm = document.getElementById("b-form");
  var bCategory = document.getElementById("b-category");
  var bAmount = document.getElementById("b-amount");
  var bMonth = document.getElementById("b-month");

  if (monthInput) {
    monthInput.addEventListener("change", function () {
      location.search = "?month=" + monthInput.value;
    });
  }

  async function loadCategories() {
    try {
      var cats = await api("/api/categories?kind=expense");
      var list = Array.isArray(cats) ? cats : (cats.expense || []);
      var html = "";
      list.forEach(function (c) {
        html += '<option value="' + c.id + '">' + c.name + '</option>';
      });
      if (bCategory) bCategory.innerHTML = html;
    } catch (e) {
      alert("加载分类失败：" + e.message);
    }
  }

  if (bForm) {
    bForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var amountYuan = parseFloat(bAmount.value);
      if (isNaN(amountYuan)) { alert("请输入有效金额"); return; }
      var payload = {
        category_id: parseInt(bCategory.value),
        year_month: bMonth.value,
        amount_cents: Math.round(amountYuan * 100)
      };
      try {
        await api("/api/budgets", { method: "POST", body: payload });
        location.reload();
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    });
  }

  document.querySelectorAll(".btn-del-budget").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var id = btn.getAttribute("data-id");
      var ok = await confirmDelete("/api/budgets/" + id);
      if (ok) location.reload();
    });
  });

  loadCategories();
}

/* ========== 周期账单页 ========== */

function initRecurringPage() {
  var recBody = document.getElementById("rec-body");
  var rForm = document.getElementById("r-form");
  var rName = document.getElementById("r-name");
  var rType = document.getElementById("r-type");
  var rAccount = document.getElementById("r-account");
  var rCategory = document.getElementById("r-category");
  var rAmount = document.getElementById("r-amount");
  var rDay = document.getElementById("r-day");
  var rNote = document.getElementById("r-note");

  var accountsMap = {};
  var categoriesMap = {};

  async function loadRefs() {
    var accs = await api("/api/accounts");
    accountsMap = {};
    var accHtml = "";
    (accs || []).forEach(function (a) {
      accountsMap[a.id] = a;
      accHtml += '<option value="' + a.id + '">' + a.name + '</option>';
    });
    if (rAccount) rAccount.innerHTML = accHtml;

    var cats = await api("/api/categories");
    var allCats = Array.isArray(cats) ? cats : (cats.expense || []).concat(cats.income || []);
    categoriesMap = {};
    var catHtml = '<option value="">无</option>';
    allCats.forEach(function (c) {
      categoriesMap[c.id] = c;
      catHtml += '<option value="' + c.id + '">' + c.name + '</option>';
    });
    if (rCategory) rCategory.innerHTML = catHtml;
  }

  async function loadRecurring() {
    var data = await api("/api/recurring");
    var items = Array.isArray(data) ? data : (data.items || []);
    if (!items.length) {
      if (recBody) recBody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#999">暂无记录</td></tr>';
      return;
    }
    var html = "";
    items.forEach(function (r) {
      var active = r.is_active !== undefined ? r.is_active : true;
      var statusText = active ? "启用" : "停用";
      var toggleText = active ? "停用" : "启用";
      html += "<tr>" +
        "<td>" + r.name + "</td>" +
        "<td>" + typeText(r.type) + "</td>" +
        "<td>" + fmtMoney(r.amount_cents) + "</td>" +
        "<td>每月 " + r.day_of_month + " 日</td>" +
        "<td>" + statusText + "</td>" +
        "<td>" +
          '<button class="btn-toggle-recurring" data-id="' + r.id + '" data-active="' + (active ? "true" : "false") + '">' + toggleText + '</button> ' +
          '<button class="btn-del-recurring" data-id="' + r.id + '">删除</button>' +
        "</td>" +
        "</tr>";
    });
    if (recBody) recBody.innerHTML = html;

    recBody.querySelectorAll(".btn-toggle-recurring").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-id");
        var current = btn.getAttribute("data-active") === "true";
        try {
          await api("/api/recurring/" + id, { method: "PUT", body: { is_active: !current } });
          loadRecurring();
        } catch (err) {
          alert("操作失败：" + err.message);
        }
      });
    });

    recBody.querySelectorAll(".btn-del-recurring").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-id");
        var ok = await confirmDelete("/api/recurring/" + id);
        if (ok) loadRecurring();
      });
    });
  }

  if (rForm) {
    rForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      var amountYuan = parseFloat(rAmount.value);
      if (isNaN(amountYuan)) { alert("请输入有效金额"); return; }
      var payload = {
        name: rName.value,
        type: rType.value,
        account_id: parseInt(rAccount.value),
        category_id: rCategory.value ? parseInt(rCategory.value) : null,
        amount_cents: Math.round(amountYuan * 100),
        day_of_month: parseInt(rDay.value),
        note: rNote.value || null
      };
      try {
        await api("/api/recurring", { method: "POST", body: payload });
        rForm.reset();
        loadRecurring();
      } catch (err) {
        alert("保存失败：" + err.message);
      }
    });
  }

  loadRefs().then(loadRecurring).catch(function (e) { alert("加载失败：" + e.message); });
}

/* ========== 导入导出页 ========== */

function initImportPage() {
  var importFile = document.getElementById("import-file");
  var btnUpload = document.getElementById("btn-upload");
  var importResult = document.getElementById("import-result");
  var expFrom = document.getElementById("exp-from");
  var expTo = document.getElementById("exp-to");
  var btnExport = document.getElementById("btn-export");

  if (btnUpload) {
    btnUpload.addEventListener("click", async function () {
      if (!importFile || !importFile.files.length) {
        alert("请选择文件");
        return;
      }
      var fd = new FormData();
      fd.append("file", importFile.files[0]);
      try {
        var res = await fetch("/api/import/csv", { method: "POST", body: fd });
        var data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "导入失败");
        }
        var created = data.created || 0;
        var skipped = data.skipped || 0;
        var errors = data.errors || [];
        var html = "<p>成功导入：" + created + " 条，跳过：" + skipped + " 条</p>";
        if (errors.length) {
          html += "<p>错误信息：</p><ul>";
          errors.forEach(function (err) {
            html += "<li>" + (typeof err === "string" ? err : JSON.stringify(err)) + "</li>";
          });
          html += "</ul>";
        }
        if (importResult) importResult.innerHTML = html;
      } catch (err) {
        if (importResult) importResult.innerHTML = "<p style='color:red'>" + err.message + "</p>";
      }
    });
  }

  if (btnExport) {
    btnExport.addEventListener("click", function () {
      var params = new URLSearchParams();
      if (expFrom && expFrom.value) params.set("date_from", expFrom.value);
      if (expTo && expTo.value) params.set("date_to", expTo.value);
      location.href = "/api/export/csv?" + params.toString();
    });
  }
}

/* ========== 自动初始化 ========== */

document.addEventListener("DOMContentLoaded", function () {
  if (document.getElementById("tx-form")) initTransactionsPage();
  if (document.getElementById("fx-form")) initCurrenciesPage();
  if (document.getElementById("acc-form")) initAccountsPage();
  if (document.getElementById("cat-form")) initCategoriesPage();
  if (document.getElementById("b-form")) initBudgetsPage();
  if (document.getElementById("r-form")) initRecurringPage();
  if (document.getElementById("btn-upload")) initImportPage();
});
