
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
      return '<span class="status-line"><span class="status-dot dot-amber"></span>待提交</span>';
    case "PROCESSING":
      return '<span class="status-line"><span class="status-dot dot-blue"></span>生成中</span>';
    case "DONE":
      return '<span class="status-line"><span class="status-dot dot-green"></span>已完成</span>';
    case "FAILED":
      return '<span class="status-line"><span class="status-dot dot-red"></span>失败</span>';
    default:
      return '<span class="status-line"><span class="status-dot dot-amber"></span>待提交</span>';
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
    const emptyWrap = document.createElement("div");
    emptyWrap.className = "col-12";
    const empty = document.createElement("div");
    empty.className = "card";
    const emptyBody = document.createElement("div");
    emptyBody.className = "card-body text-secondary";
    emptyBody.textContent = "当前分镜下没有任务";
    empty.appendChild(emptyBody);
    emptyWrap.appendChild(empty);
    grid.appendChild(emptyWrap);
    return;
  }

  tasks.forEach((task) => {
    const col = document.createElement("div");
    col.className = "col-md-6 col-lg-4";

    const card = document.createElement("div");
    card.className = "card";
    card.dataset.status = task.status;

    const header = document.createElement("div");
    header.className = "card-header";
    const title = document.createElement("h3");
    title.className = "card-title";
    title.textContent = "#" + task.id;
    const badge = document.createElement("span");
    badge.innerHTML = statusDotHtml(task.status);
    header.appendChild(title);
    header.appendChild(badge);
    card.appendChild(header);

    const body = document.createElement("div");
    body.className = "card-body";

    const shotLine = document.createElement("div");
    shotLine.className = "text-secondary mb-2";
    shotLine.textContent = findShotLabel(task.shotId);
    body.appendChild(shotLine);

    const progress = document.createElement("div");
    progress.className = "progress progress-sm mb-3";
    const bar = document.createElement("div");
    bar.className = statusProgressClass(task.status);
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuenow", statusProgressWidth(task.status));
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.style.width = statusProgressWidth(task.status);
    progress.appendChild(bar);
    body.appendChild(progress);

    const meta = document.createElement("div");
    meta.className = "d-flex justify-content-between text-secondary";
    const provider = document.createElement("span");
    provider.textContent = task.provider || "mock";
    const attempts = document.createElement("span");
    attempts.textContent = "尝试 " + (task.attempts != null ? task.attempts : 1) + " 次";
    meta.appendChild(provider);
    meta.appendChild(attempts);
    body.appendChild(meta);

    if (task.errorMessage) {
      const err = document.createElement("div");
      err.className = "alert alert-danger mt-2 mb-0";
      err.textContent = task.errorMessage;
      body.appendChild(err);
    }

    card.appendChild(body);

    if (task.status === "DONE") {
      const actions = document.createElement("div");
      actions.className = "card-footer";
      const link = document.createElement("a");
      link.className = "btn btn-outline-secondary btn-sm";
      link.href = "/media/videos/" + task.id;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "预览";
      actions.appendChild(link);
      card.appendChild(actions);
    } else if (task.status === "FAILED") {
      const actions = document.createElement("div");
      actions.className = "card-footer";
      const btn = document.createElement("button");
      btn.className = "btn btn-danger btn-sm";
      btn.textContent = "重试";
      btn.addEventListener("click", () => retryTask(task.id));
      actions.appendChild(btn);
      card.appendChild(actions);
    }

    col.appendChild(card);
    grid.appendChild(col);
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

