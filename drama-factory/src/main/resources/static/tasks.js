const SHOT_SIZE_LABEL = {
  CLOSE_UP: "特写",
  MEDIUM: "中景",
  WIDE: "全景",
};

const state = {
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

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    throw new Error("请求失败：" + res.status);
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
      return '<span class="status-pill sp-gray">待提交</span>';
    case "PROCESSING":
      return '<span class="status-pill sp-blue">生成中</span>';
    case "DONE":
      return '<span class="status-pill sp-green">已完成</span>';
    case "FAILED":
      return '<span class="status-pill sp-red">失败</span>';
    default:
      return '<span class="status-pill sp-gray">待提交</span>';
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
    return "镜号 " + shotId;
  }
  const size = shot.shotSizeLabel || SHOT_SIZE_LABEL[shot.shotSize] || shot.shotSize || "";
  return "镜号 " + shot.shotNo + (size ? " · " + size : "");
}

async function retryTask(taskId) {
  try {
    await api("/api/video-tasks/" + taskId + "/retry", { method: "POST" });
    showHint("已提交重试：任务 #" + taskId);
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
    "全部项目"
  );
}

async function loadEpisodes(projectId) {
  if (!projectId) {
    state.episodes = [];
    fillSelect($("episodeSelect"), [], "id", () => "", "全部分集");
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
    (e) => "第 " + e.episodeNo + " 集",
    "全部分集"
  );
}

async function loadShots(episodeId) {
  if (!episodeId) {
    state.shots = [];
    fillSelect($("shotSelect"), [], "id", () => "", "全部分镜");
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
    "全部分镜"
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
    countEl.textContent = tasks.length + " 条";
  }

  if (!tasks.length) {
    const empty = document.createElement("div");
    empty.className = "text-secondary py-3";
    empty.style.fontSize = "13px";
    empty.textContent = "当前分镜下没有任务";
    grid.appendChild(empty);
    return;
  }

  tasks.forEach((task) => {
    const row = document.createElement("div");
    row.className = "py-3";
    row.style.borderBottom = "1px solid var(--surface)";
    row.dataset.status = task.status;

    // 第一行：状态 + 任务名 + 进度 + 操作
    const top = document.createElement("div");
    top.className = "d-flex align-items-center";
    top.style.gap = "12px";

    const left = document.createElement("div");
    left.className = "d-flex align-items-center";
    left.style.gap = "8px";
    left.style.minWidth = "0";
    left.style.flex = "1 1 auto";

    const statusWrap = document.createElement("span");
    statusWrap.innerHTML = statusDotHtml(task.status);
    statusWrap.style.fontSize = "12px";
    statusWrap.style.color = "var(--text-2)";
    left.appendChild(statusWrap);

    const name = document.createElement("span");
    name.style.fontSize = "14px";
    name.style.color = "var(--text)";
    name.style.whiteSpace = "nowrap";
    name.style.overflow = "hidden";
    name.style.textOverflow = "ellipsis";
    name.textContent = "任务 #" + task.id + " · " + findShotLabel(task.shotId);
    left.appendChild(name);

    top.appendChild(left);

    const progressWrap = document.createElement("div");
    progressWrap.className = "d-flex align-items-center";
    progressWrap.style.gap = "8px";
    progressWrap.style.flex = "0 0 auto";

    const progress = document.createElement("div");
    progress.className = "progress";
    progress.style.width = "120px";
    progress.style.height = "4px";
    progress.style.borderRadius = "2px";
    progress.style.overflow = "hidden";

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
    pct.style.fontSize = "12px";
    pct.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
    pct.style.color = "var(--text-2)";
    pct.style.minWidth = "40px";
    pct.style.textAlign = "right";
    pct.textContent = statusProgressPercent(task.status);
    progressWrap.appendChild(pct);

    top.appendChild(progressWrap);

    if (task.status === "DONE") {
      const link = document.createElement("a");
      link.href = "/media/videos/" + task.id;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "预览";
      link.style.fontSize = "13px";
      link.style.color = "var(--accent)";
      link.style.textDecoration = "none";
      link.style.flex = "0 0 auto";
      top.appendChild(link);
    } else if (task.status === "FAILED") {
      const link = document.createElement("a");
      link.href = "javascript:void(0)";
      link.textContent = "重试";
      link.style.fontSize = "13px";
      link.style.color = "var(--accent)";
      link.style.textDecoration = "none";
      link.style.cursor = "pointer";
      link.style.flex = "0 0 auto";
      link.addEventListener("click", (e) => {
        e.preventDefault();
        retryTask(task.id);
      });
      top.appendChild(link);
    }

    row.appendChild(top);

    // 第二行：辅助信息
    const meta = document.createElement("div");
    meta.className = "mt-1";
    meta.style.fontSize = "12px";
    meta.style.color = "var(--text-3)";

    const providerText = (task.provider || "mock");
    const attemptsText = "尝试 " + (task.attempts != null ? task.attempts : 1) + " 次";
    meta.appendChild(document.createTextNode("提供方 " + providerText + " · " + attemptsText));

    if (task.errorMessage) {
      const err = document.createElement("span");
      err.style.color = "var(--danger, #b0453f)";
      err.style.marginLeft = "6px";
      err.textContent = " · " + task.errorMessage;
      meta.appendChild(err);
    }

    row.appendChild(meta);

    grid.appendChild(row);
  });
}

function init() {
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
  })();
}

document.addEventListener("DOMContentLoaded", init);
