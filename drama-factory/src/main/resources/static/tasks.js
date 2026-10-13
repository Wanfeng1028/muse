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
  el.textContent = message || "";
  el.classList.toggle("is-error", Boolean(isError));
}

function clearChildren(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

function statusClass(status) {
  switch (status) {
    case "PENDING":
      return "badge-pending";
    case "PROCESSING":
      return "badge-processing";
    case "DONE":
      return "badge-done";
    case "FAILED":
      return "badge-failed";
    default:
      return "badge-pending";
  }
}

function statusLabelOf(status) {
  switch (status) {
    case "PENDING":
      return "等待中";
    case "PROCESSING":
      return "生成中";
    case "DONE":
      return "已完成";
    case "FAILED":
      return "失败";
    default:
      return status || "未知";
  }
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
    empty.className = "empty";
    empty.textContent = "当前分镜下没有任务";
    grid.appendChild(empty);
    return;
  }

  tasks.forEach((task) => {
    const card = document.createElement("article");
    card.className = "task-card";
    card.dataset.status = task.status;

    const top = document.createElement("div");
    top.className = "task-top";
    const timecode = document.createElement("span");
    timecode.className = "timecode";
    timecode.textContent = "#" + task.id;
    const badge = document.createElement("span");
    badge.className = "badge " + statusClass(task.status);
    badge.textContent = statusLabelOf(task.status);
    top.appendChild(timecode);
    top.appendChild(badge);
    card.appendChild(top);

    const shotLine = document.createElement("div");
    shotLine.className = "task-shot";
    shotLine.textContent = findShotLabel(task.shotId);
    card.appendChild(shotLine);

    const progressWrap = document.createElement("div");
    progressWrap.className = "task-progress";
    const bar = document.createElement("div");
    bar.className = "bar";
    if (task.status === "PENDING") {
      bar.style.width = "8%";
    } else if (task.status === "PROCESSING") {
      bar.style.width = "55%";
      progressWrap.classList.add("is-processing");
    } else if (task.status === "DONE") {
      bar.style.width = "100%";
    } else if (task.status === "FAILED") {
      bar.style.width = "100%";
      bar.classList.add("is-failed");
    } else {
      bar.style.width = "8%";
    }
    progressWrap.appendChild(bar);
    card.appendChild(progressWrap);

    const meta = document.createElement("div");
    meta.className = "task-meta";
    const provider = document.createElement("span");
    provider.textContent = task.provider || "mock";
    const attempts = document.createElement("span");
    attempts.textContent = "尝试 " + (task.attempts != null ? task.attempts : 1) + " 次";
    meta.appendChild(provider);
    meta.appendChild(attempts);
    card.appendChild(meta);

    if (task.errorMessage) {
      const err = document.createElement("p");
      err.className = "task-err";
      err.textContent = task.errorMessage;
      card.appendChild(err);
    }

    if (task.status === "DONE") {
      const actions = document.createElement("div");
      actions.className = "task-actions";
      const link = document.createElement("a");
      link.className = "btn btn-sm";
      link.href = "/media/videos/" + task.id;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "预览";
      actions.appendChild(link);
      card.appendChild(actions);
    } else if (task.status === "FAILED") {
      const actions = document.createElement("div");
      actions.className = "task-actions";
      const btn = document.createElement("button");
      btn.className = "btn btn-sm btn-danger";
      btn.textContent = "重试";
      btn.addEventListener("click", () => retryTask(task.id));
      actions.appendChild(btn);
      card.appendChild(actions);
    }

    grid.appendChild(card);
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
