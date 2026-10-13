(function () {
  "use strict";

  var API_BASE = "";

  function api(path, options) {
    options = options || {};
    var opts = {
      method: options.method || "GET",
      headers: { "Accept": "application/json" }
    };
    if (options.body !== undefined && options.body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(options.body);
    }
    return fetch(API_BASE + path, opts).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) {
          try { data = JSON.parse(text); } catch (e) { data = null; }
        }
        if (!res.ok) {
          var msg = (data && (data.message || data.error)) || ("请求失败：" + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function $(id) { return document.getElementById(id); }

  function showHint(text, type) {
    var el = $("hint");
    if (!text) { el.hidden = true; el.textContent = ""; return; }
    el.hidden = false;
    el.textContent = text;
    el.className = "hint hint-" + (type || "info");
  }

  function clearChildren(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  var SHOT_SIZE_LABEL = {
    TE_XIE: "特写", JIN_JING: "近景", ZHONG_JING: "中景",
    QUAN_JING: "全景", YUAN_JING: "远景"
  };

  var state = {
    projects: [],
    episodes: [],
    shots: [],
    tasks: []
  };

  function statusClass(status) {
    switch (status) {
      case "PENDING": return "badge badge-pending";
      case "PROCESSING": return "badge badge-processing";
      case "DONE": return "badge badge-done";
      case "FAILED": return "badge badge-failed";
      default: return "badge badge-pending";
    }
  }

  function statusLabelOf(task) {
    if (task.statusLabel) return task.statusLabel;
    switch (task.status) {
      case "PENDING": return "待提交";
      case "PROCESSING": return "生成中";
      case "DONE": return "已完成";
      case "FAILED": return "失败";
      default: return task.status || "未知";
    }
  }

  function findShotLabel(shotId) {
    for (var i = 0; i < state.shots.length; i++) {
      if (state.shots[i].id === shotId) {
        var s = state.shots[i];
        var size = SHOT_SIZE_LABEL[s.shotSize] || s.shotSize || "";
        return "镜号 " + s.shotNo + (size ? " · " + size : "");
      }
    }
    return "分镜 " + shotId;
  }

  function renderTasks() {
    var tbody = $("taskBody");
    clearChildren(tbody);
    $("taskCount").textContent = state.tasks.length + " 条";

    if (!state.tasks.length) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 7;
      td.className = "empty-cell";
      td.textContent = "当前分镜下没有任务";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    state.tasks.forEach(function (task) {
      var tr = document.createElement("tr");

      var tdId = document.createElement("td");
      tdId.className = "cell-mono";
      tdId.textContent = task.id;
      tr.appendChild(tdId);

      var tdShot = document.createElement("td");
      tdShot.textContent = findShotLabel(task.shotId);
      tr.appendChild(tdShot);

      var tdProvider = document.createElement("td");
      tdProvider.textContent = task.provider || "mock";
      tr.appendChild(tdProvider);

      var tdStatus = document.createElement("td");
      var badge = document.createElement("span");
      badge.className = statusClass(task.status);
      badge.textContent = statusLabelOf(task);
      tdStatus.appendChild(badge);
      tr.appendChild(tdStatus);

      var tdAttempts = document.createElement("td");
      tdAttempts.textContent = (task.attempts === null || task.attempts === undefined) ? "0" : task.attempts;
      tr.appendChild(tdAttempts);

      var tdErr = document.createElement("td");
      tdErr.className = "cell-err";
      tdErr.textContent = task.errorMessage || "-";
      if (task.errorMessage) tdErr.title = task.errorMessage;
      tr.appendChild(tdErr);

      var tdOps = document.createElement("td");
      tdOps.className = "cell-ops";
      if (task.status === "DONE") {
        var a = document.createElement("a");
        a.className = "link";
        a.href = "/media/videos/" + encodeURIComponent(task.id);
        a.target = "_blank";
        a.rel = "noopener";
        a.textContent = "预览";
        tdOps.appendChild(a);
      } else if (task.status === "FAILED") {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-danger btn-sm";
        btn.textContent = "重试";
        btn.addEventListener("click", function () { retryTask(task, btn); });
        tdOps.appendChild(btn);
      } else {
        tdOps.textContent = "-";
      }
      tr.appendChild(tdOps);

      tbody.appendChild(tr);
    });
  }

  function retryTask(task, btn) {
    btn.disabled = true;
    btn.textContent = "重试中…";
    api("/api/video-tasks/" + encodeURIComponent(task.id) + "/retry", { method: "POST" })
      .then(function () {
        showHint("任务 " + task.id + " 已重新提交", "success");
        return loadTasksForCurrentShot();
      })
      .catch(function (err) {
        showHint("重试失败：" + err.message, "error");
        btn.disabled = false;
        btn.textContent = "重试";
      });
  }

  function fillSelect(sel, items, valueKey, labelFn, placeholder) {
    clearChildren(sel);
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = placeholder;
    sel.appendChild(opt0);
    items.forEach(function (it) {
      var o = document.createElement("option");
      o.value = it[valueKey];
      o.textContent = labelFn(it);
      sel.appendChild(o);
    });
  }

  function loadProjects() {
    return api("/api/projects").then(function (data) {
      state.projects = Array.isArray(data) ? data : (data && data.items) || [];
      var sel = $("projectSelect");
      if (!state.projects.length) {
        fillSelect(sel, [], "id", function () { return ""; }, "暂无项目");
        return;
      }
      fillSelect(sel, state.projects, "id", function (p) {
        return p.title || p.name || ("项目 " + p.id);
      }, "请选择项目");
      sel.value = state.projects[0].id;
      return loadEpisodes();
    }).catch(function (err) {
      showHint("项目加载失败：" + err.message, "error");
    });
  }

  function loadEpisodes() {
    var pid = $("projectSelect").value;
    var esel = $("episodeSelect");
    var ssel = $("shotSelect");
    fillSelect(esel, [], "id", function () { return ""; }, "-");
    fillSelect(ssel, [], "id", function () { return ""; }, "-");
    state.episodes = [];
    state.shots = [];
    state.tasks = [];
    renderTasks();
    if (!pid) return Promise.resolve();

    return api("/api/projects/" + encodeURIComponent(pid) + "/episodes").then(function (data) {
      state.episodes = Array.isArray(data) ? data : (data && data.items) || [];
      if (!state.episodes.length) {
        fillSelect(esel, [], "id", function () { return ""; }, "暂无剧集");
        return;
      }
      fillSelect(esel, state.episodes, "id", function (e) {
        var no = e.episodeNo !== undefined && e.episodeNo !== null ? ("第" + e.episodeNo + "集") : "";
        return (no ? no + " " : "") + (e.title || ("剧集 " + e.id));
      }, "请选择剧集");
      esel.value = state.episodes[0].id;
      return loadShots();
    }).catch(function (err) {
      showHint("剧集加载失败：" + err.message, "error");
    });
  }

  function loadShots() {
    var eid = $("episodeSelect").value;
    var ssel = $("shotSelect");
    fillSelect(ssel, [], "id", function () { return ""; }, "-");
    state.shots = [];
    state.tasks = [];
    renderTasks();
    if (!eid) return Promise.resolve();

    return api("/api/episodes/" + encodeURIComponent(eid) + "/shots").then(function (data) {
      state.shots = Array.isArray(data) ? data : (data && data.items) || [];
      if (!state.shots.length) {
        fillSelect(ssel, [], "id", function () { return ""; }, "暂无分镜");
        return;
      }
      fillSelect(ssel, state.shots, "id", function (s) {
        var size = SHOT_SIZE_LABEL[s.shotSize] || s.shotSize || "";
        return "镜号 " + s.shotNo + (size ? " · " + size : "");
      }, "请选择分镜");
      ssel.value = state.shots[0].id;
      return loadTasksForCurrentShot();
    }).catch(function (err) {
      showHint("分镜加载失败：" + err.message, "error");
    });
  }

  function loadTasksForCurrentShot() {
    var sid = $("shotSelect").value;
    state.tasks = [];
    if (!sid) { renderTasks(); return Promise.resolve(); }
    return api("/api/shots/" + encodeURIComponent(sid) + "/video-tasks").then(function (data) {
      state.tasks = Array.isArray(data) ? data : (data && data.items) || [];
      renderTasks();
    }).catch(function (err) {
      showHint("任务加载失败：" + err.message, "error");
      renderTasks();
    });
  }

  function init() {
    $("projectSelect").addEventListener("change", loadEpisodes);
    $("episodeSelect").addEventListener("change", loadShots);
    $("shotSelect").addEventListener("change", function () {
      loadTasksForCurrentShot();
    });
    $("refreshBtn").addEventListener("click", function () {
      showHint("");
      loadTasksForCurrentShot();
    });
    loadProjects();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
