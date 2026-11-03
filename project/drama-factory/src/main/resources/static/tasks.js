(function () {
  'use strict';

  var PAGE_I18N = {
    'task.pageTitle': { 'zh-CN': '任务队列', en: 'Task Queue' },
    'task.project': { 'zh-CN': '项目', en: 'Project' },
    'task.episode': { 'zh-CN': '剧集', en: 'Episode' },
    'task.shot': { 'zh-CN': '分镜', en: 'Shot' },
    'task.allProjects': { 'zh-CN': '全部项目', en: 'All projects' },
    'task.allEpisodes': { 'zh-CN': '全部分集', en: 'All episodes' },
    'task.allShots': { 'zh-CN': '全部分镜', en: 'All shots' },
    'task.requestFailed': { 'zh-CN': '请求失败：', en: 'Request failed: ' },
    'task.statusPending': { 'zh-CN': '待提交', en: 'Pending' },
    'task.statusProcessing': { 'zh-CN': '生成中', en: 'Generating' },
    'task.statusDone': { 'zh-CN': '已完成', en: 'Done' },
    'task.statusFailed': { 'zh-CN': '失败', en: 'Failed' },
    'task.emptyHint': { 'zh-CN': '暂无任务，先在分镜板添加分镜。', en: 'No tasks yet. Add shots on the storyboard first.' },
    'task.shotNoPrefix': { 'zh-CN': '镜号 ', en: 'Shot ' },
    'task.taskNoPrefix': { 'zh-CN': '任务 #', en: 'Task #' },
    'task.retrySubmitted': { 'zh-CN': '已提交重试：任务 #', en: 'Retry submitted: task #' },
    'task.preview': { 'zh-CN': '预览', en: 'Preview' },
    'task.retry': { 'zh-CN': '重试', en: 'Retry' },
    'task.episodePrefix': { 'zh-CN': '第 ', en: 'Episode ' },
    'task.episodeSuffix': { 'zh-CN': ' 集', en: '' },
    'task.providerPrefix': { 'zh-CN': '提供方 ', en: 'Provider: ' },
    'task.attemptsPrefix': { 'zh-CN': '尝试 ', en: 'Attempts: ' },
    'task.attemptsSuffix': { 'zh-CN': ' 次', en: '' },
    'task.countSuffix': { 'zh-CN': ' 条', en: ' items' },
    'task.shotSizeCloseUp': { 'zh-CN': '特写', en: 'Close-up' },
    'task.shotSizeMedium': { 'zh-CN': '中景', en: 'Medium' },
    'task.shotSizeWide': { 'zh-CN': '全景', en: 'Wide' },
    'task.constraintHint': { 'zh-CN': '通道硬约束', en: 'Channel limits' },
    'task.promptLimit': { 'zh-CN': '提示词≤', en: 'Prompt ≤' },
    'task.durationRange': { 'zh-CN': '时长', en: 'Duration' },
    'task.resolutions': { 'zh-CN': '分辨率', en: 'Resolutions' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  var SHOT_SIZE_LABEL = {
    CLOSE_UP: _t('task.shotSizeCloseUp', '特写'),
    MEDIUM: _t('task.shotSizeMedium', '中景'),
    WIDE: _t('task.shotSizeWide', '全景'),
  };

  var state = {
    projects: [],
    episodes: [],
    shots: [],
    currentProjectId: null,
    currentEpisodeId: null,
    currentShotId: null,
    tasks: [],
  };

  function $(id) {
    return document.getElementById(id);
  }

  // 通道硬约束提示：取第一个描述符通道的第一个 video 模型约束展示。
  // 接口失败时静默不展示。
  async function loadConstraintHint() {
    var hintEl = $("hint");
    if (!hintEl) return;
    try {
      var resp = await fetch("/api/descriptor-providers");
      if (!resp.ok) return;
      var providers = await resp.json();
      if (!Array.isArray(providers) || providers.length === 0) return;
      var shown = false;
      for (var i = 0; i < providers.length && !shown; i++) {
        var models = providers[i].models || [];
        for (var j = 0; j < models.length; j++) {
          var m = models[j];
          if (m.type !== "video" || !m.constraints) continue;
          var c = m.constraints;
          var parts = [];
          if (c.maxPromptChars) parts.push(_t("task.promptLimit", "提示词≤") + c.maxPromptChars + "字");
          if (c.minDurationSeconds != null && c.maxDurationSeconds != null) {
            parts.push(_t("task.durationRange", "时长") + c.minDurationSeconds + "–" + c.maxDurationSeconds + "秒");
          }
          if (Array.isArray(c.resolutions) && c.resolutions.length > 0) {
            parts.push(_t("task.resolutions", "分辨率") + c.resolutions.join("/"));
          }
          if (parts.length === 0) continue;
          var label = providers[i].label || providers[i].id;
          hintEl.textContent = _t("task.constraintHint", "通道硬约束")
            + "（" + label + " / " + (m.label || m.id) + "）：" + parts.join(" · ");
          hintEl.style.display = "";
          shown = true;
          break;
        }
      }
    } catch (e) {
      // 静默：约束提示是增值信息，不许干扰主流程
    }
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      throw new Error(_t('task.requestFailed', '请求失败：') + res.status);
    }
    if (res.status === 204) {
      return null;
    }
    return res.json();
  }

  function showHint(message, isError) {
    const el = $("hint");
    if (!el) return;
    if (!message) {
      el.textContent = "";
      el.style.display = "none";
      return;
    }
    el.textContent = message;
    el.className = "alert mb-3 " + (isError ? "alert-danger" : "alert-info");
    el.style.display = "";
  }

  function clearChildren(el) {
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function statusDotHtml(status) {
    switch (status) {
      case "PENDING":
        return '<span class="status-pill sp-gray">' + _t('task.statusPending', '待提交') + '</span>';
      case "PROCESSING":
        return '<span class="status-pill sp-blue">' + _t('task.statusProcessing', '生成中') + '</span>';
      case "DONE":
        return '<span class="status-pill sp-green">' + _t('task.statusDone', '已完成') + '</span>';
      case "FAILED":
        return '<span class="status-pill sp-red">' + _t('task.statusFailed', '失败') + '</span>';
      default:
        return '<span class="status-pill sp-gray">' + _t('task.statusPending', '待提交') + '</span>';
    }
  }

  function statusProgressClass(status) {
    switch (status) {
      case "PROCESSING":
        return "progress-bar progress-bar-indeterminate bg-blue";
      case "DONE":
        return "progress-bar bg-green";
      case "FAILED":
        return "progress-bar bg-red";
      default:
        return "progress-bar bg-yellow";
    }
  }

  function statusProgressWidth(status) {
    switch (status) {
      case "PENDING":
        return "8%";
      case "PROCESSING":
        return "55%";
      case "DONE":
        return "100%";
      case "FAILED":
        return "100%";
      default:
        return "8%";
    }
  }

  function statusProgressPercent(status) {
    const w = statusProgressWidth(status);
    return w;
  }

  function findShotLabel(shotId) {
    const shot = state.shots.find((s) => s.id === shotId);
    if (!shot) {
      return _t('task.shotNoPrefix', '镜号 ') + shotId;
    }
    const size = shot.shotSizeLabel || SHOT_SIZE_LABEL[shot.shotSize] || shot.shotSize || "";
    return _t('task.shotNoPrefix', '镜号 ') + shot.shotNo + (size ? " · " + size : "");
  }

  async function retryTask(taskId) {
    try {
      await api("/api/video-tasks/" + taskId + "/retry", { method: "POST" });
      showHint(_t('task.retrySubmitted', '已提交重试：任务 #') + taskId);
      await loadTasksForCurrentShot();
    } catch (err) {
      showHint(err.message, true);
    }
  }

  function fillSelect(select, items, valueKey, labelFn, placeholder) {
    clearChildren(select);
    const placeholderOption = document.createElement("option");
    placeholderOption.value = "";
    placeholderOption.textContent = placeholder;
    select.appendChild(placeholderOption);
    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = String(item[valueKey]);
      option.textContent = labelFn(item);
      select.appendChild(option);
    });
  }

  async function loadProjects() {
    try {
      state.projects = await api("/api/projects");
    } catch (err) {
      showHint(err.message, true);
      state.projects = [];
    }
    fillSelect(
      $("projectSelect"),
      state.projects,
      "id",
      (p) => p.title,
      _t('task.allProjects', '全部项目')
    );
  }

  async function loadEpisodes(projectId) {
    if (!projectId) {
      state.episodes = [];
      fillSelect($("episodeSelect"), [], "id", () => "", _t('task.allEpisodes', '全部分集'));
      return;
    }
    try {
      state.episodes = await api("/api/projects/" + projectId + "/episodes");
    } catch (err) {
      showHint(err.message, true);
      state.episodes = [];
    }
    fillSelect(
      $("episodeSelect"),
      state.episodes,
      "id",
      (e) => _t('task.episodePrefix', '第 ') + e.episodeNo + _t('task.episodeSuffix', ' 集'),
      _t('task.allEpisodes', '全部分集')
    );
  }

  async function loadShots(episodeId) {
    if (!episodeId) {
      state.shots = [];
      fillSelect($("shotSelect"), [], "id", () => "", _t('task.allShots', '全部分镜'));
      return;
    }
    try {
      state.shots = await api("/api/episodes/" + episodeId + "/shots");
    } catch (err) {
      showHint(err.message, true);
      state.shots = [];
    }
    fillSelect(
      $("shotSelect"),
      state.shots,
      "id",
      (s) => findShotLabel(s.id),
      _t('task.allShots', '全部分镜')
    );
  }

  async function loadTasksForCurrentShot() {
    const shotId = $("shotSelect").value;
    state.currentShotId = shotId ? Number(shotId) : null;
    if (!shotId) {
      state.tasks = [];
      renderTasks();
      return;
    }
    try {
      state.tasks = await api("/api/shots/" + shotId + "/video-tasks");
    } catch (err) {
      showHint(err.message, true);
      state.tasks = [];
    }
    renderTasks();
  }

  function renderTasks() {
    const grid = $("taskGrid");
    clearChildren(grid);

    const tasks = state.tasks || [];
    const countEl = $("taskCount");
    if (countEl) {
      countEl.textContent = tasks.length + _t('task.countSuffix', ' 条');
    }

    if (!tasks.length) {
      const empty = document.createElement("div");
      empty.className = "state-empty";
      empty.innerHTML = '<i data-lucide="inbox"></i><span>' + _t('task.emptyHint', '暂无任务，先在分镜板添加分镜。') + '</span>';
      if (window.lucide) lucide.createIcons();
      grid.appendChild(empty);
      if (window.DFI18N) DFI18N.applyI18n(grid);
      return;
    }

    tasks.forEach((task) => {
      const row = document.createElement("div");
      row.className = "py-3 task-row";
      row.dataset.status = task.status;

      // 第一行：状态 + 任务名 + 进度 + 操作
      const top = document.createElement("div");
      top.className = "d-flex align-items-center task-top";

      const left = document.createElement("div");
      left.className = "d-flex align-items-center task-left";

      const statusWrap = document.createElement("span");
      statusWrap.className = "task-status";
      statusWrap.innerHTML = statusDotHtml(task.status);
      left.appendChild(statusWrap);

      const name = document.createElement("span");
      name.className = "task-name";
      name.textContent = _t('task.taskNoPrefix', '任务 #') + task.id + " · " + findShotLabel(task.shotId);
      left.appendChild(name);

      top.appendChild(left);

      const progressWrap = document.createElement("div");
      progressWrap.className = "d-flex align-items-center task-progress-wrap";

      const progress = document.createElement("div");
      progress.className = "progress task-progress";

      const bar = document.createElement("div");
      bar.className = statusProgressClass(task.status);
      bar.setAttribute("role", "progressbar");
      bar.setAttribute("aria-valuenow", statusProgressWidth(task.status));
      bar.setAttribute("aria-valuemin", "0");
      bar.setAttribute("aria-valuemax", "100");
      bar.style.width = statusProgressWidth(task.status);
      progress.appendChild(bar);
      progressWrap.appendChild(progress);

      const pct = document.createElement("span");
      pct.className = "task-pct";
      pct.textContent = statusProgressPercent(task.status);
      progressWrap.appendChild(pct);

      top.appendChild(progressWrap);

      if (task.status === "DONE") {
        const link = document.createElement("a");
        link.href = "/media/videos/" + task.id;
        link.target = "_blank";
        link.rel = "noopener";
        link.className = "task-link";
        link.textContent = _t('task.preview', '预览');
        top.appendChild(link);
      } else if (task.status === "FAILED") {
        const link = document.createElement("a");
        link.href = "javascript:void(0)";
        link.className = "task-link task-retry";
        link.textContent = _t('task.retry', '重试');
        link.addEventListener("click", (e) => {
          e.preventDefault();
          retryTask(task.id);
        });
        top.appendChild(link);
      }

      row.appendChild(top);

      // 第二行：辅助信息
      const meta = document.createElement("div");
      meta.className = "mt-1 task-meta";

      const providerText = (task.provider || "mock");
      const attemptsText = _t('task.attemptsPrefix', '尝试 ') + (task.attempts != null ? task.attempts : 1) + _t('task.attemptsSuffix', ' 次');
      meta.appendChild(document.createTextNode(_t('task.providerPrefix', '提供方 ') + providerText + " · " + attemptsText));

      if (task.errorMessage) {
        const err = document.createElement("span");
        err.className = "task-error";
        err.textContent = " · " + task.errorMessage;
        meta.appendChild(err);
      }

      row.appendChild(meta);

      grid.appendChild(row);
    });

    if (window.DFI18N) DFI18N.applyI18n(grid);
  }

  function init() {
    loadConstraintHint();
    $("projectSelect").addEventListener("change", async (e) => {
      state.currentProjectId = e.target.value ? Number(e.target.value) : null;
      await loadEpisodes(state.currentProjectId);
      state.currentEpisodeId = null;
      await loadShots(null);
      await loadTasksForCurrentShot();
    });

    $("episodeSelect").addEventListener("change", async (e) => {
      state.currentEpisodeId = e.target.value ? Number(e.target.value) : null;
      await loadShots(state.currentEpisodeId);
      await loadTasksForCurrentShot();
    });

    $("shotSelect").addEventListener("change", async () => {
      await loadTasksForCurrentShot();
    });

    $("refreshBtn").addEventListener("click", async () => {
      await loadTasksForCurrentShot();
    });

    (async () => {
      await loadProjects();
      if (state.projects.length) {
        state.currentProjectId = state.projects[0].id;
        $("projectSelect").value = String(state.currentProjectId);
        await loadEpisodes(state.currentProjectId);
        if (state.episodes.length) {
          state.currentEpisodeId = state.episodes[0].id;
          $("episodeSelect").value = String(state.currentEpisodeId);
          await loadShots(state.currentEpisodeId);
          if (state.shots.length) {
            $("shotSelect").value = String(state.shots[0].id);
          }
        }
      }
      await loadTasksForCurrentShot();
      if (window.DFI18N) DFI18N.applyI18n(document);
    })();
  }

  if (window.DFI18N) {
    DFI18N.onLangChange(function () {
      SHOT_SIZE_LABEL.CLOSE_UP = _t('task.shotSizeCloseUp', '特写');
      SHOT_SIZE_LABEL.MEDIUM = _t('task.shotSizeMedium', '中景');
      SHOT_SIZE_LABEL.WIDE = _t('task.shotSizeWide', '全景');
      const p = state.currentProjectId;
      loadEpisodes(p).then(function () {
        return loadShots(state.currentEpisodeId);
      }).then(function () {
        return loadTasksForCurrentShot();
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
