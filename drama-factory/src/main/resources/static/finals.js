const state = {
  projects: [],
  episodes: [],
  finals: [],
  projectId: null,
  episodeId: null,
};

function el(id) {
  return document.getElementById(id);
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = res.status + " " + res.statusText;
    try {
      const data = await res.json();
      if (data && data.detail) msg = data.detail;
    } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

function setHint(text) {
  el("hint").textContent = text || "";
}

function statusBadge(status) {
  const map = {
    READY: "badge badge-ready",
    BUILDING: "badge badge-building",
    FAILED: "badge badge-failed",
    PENDING: "badge badge-pending",
  };
  return map[status] || "badge";
}

function statusNote(status) {
  if (status === "BUILDING") return "正在剪辑生成中，请稍候…";
  if (status === "FAILED") return "生成失败，请重试。";
  if (status === "PENDING") return "排队中…";
  return "";
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m + ":" + String(r).padStart(2, "0");
}

function formatTime(value) {
  if (!value) return "";
  const d = new Date(value);
  if (isNaN(d.getTime())) return String(value);
  const pad = (n) => String(n).padStart(2, "0");
  return (
    d.getFullYear() +
    "-" +
    pad(d.getMonth() + 1) +
    "-" +
    pad(d.getDate()) +
    " " +
    pad(d.getHours()) +
    ":" +
    pad(d.getMinutes())
  );
}

async function loadProjects() {
  try {
    state.projects = await api("/api/projects");
  } catch (e) {
    setHint("加载项目失败：" + e.message);
    return;
  }
  const sel = el("projectSelect");
  sel.innerHTML = "";
  state.projects.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.title || p.name || p.id;
    sel.appendChild(opt);
  });
  if (state.projects.length > 0) {
    state.projectId = state.projects[0].id;
    sel.value = state.projectId;
    await loadEpisodes();
  } else {
    renderFinals();
  }
}

async function loadEpisodes() {
  const sel = el("episodeSelect");
  sel.innerHTML = "";
  state.episodes = [];
  state.episodeId = null;
  if (!state.projectId) {
    renderFinals();
    return;
  }
  try {
    state.episodes = await api("/api/projects/" + state.projectId + "/episodes");
  } catch (e) {
    setHint("加载剧集失败：" + e.message);
    renderFinals();
    return;
  }
  state.episodes.forEach((ep) => {
    const opt = document.createElement("option");
    opt.value = ep.id;
    opt.textContent = ep.title || ep.name || ("第 " + ep.index + " 集");
    sel.appendChild(opt);
  });
  if (state.episodes.length > 0) {
    state.episodeId = state.episodes[0].id;
    sel.value = state.episodeId;
    await loadFinals();
  } else {
    renderFinals();
  }
}

async function loadFinals() {
  if (!state.episodeId) {
    state.finals = [];
    renderFinals();
    return;
  }
  try {
    state.finals = await api("/api/episodes/" + state.episodeId + "/final-cuts");
  } catch (e) {
    setHint("加载成片失败：" + e.message);
    state.finals = [];
    renderFinals();
    return;
  }
  renderFinals();
}

async function generateFinalCut() {
  if (!state.episodeId) {
    setHint("请先选择项目和剧集。");
    return;
  }
  el("generateBtn").disabled = true;
  setHint("正在提交生成任务…");
  try {
    await api("/api/episodes/" + state.episodeId + "/final-cuts", {
      method: "POST",
    });
    setHint("已提交生成任务。");
    await loadFinals();
  } catch (e) {
    setHint("生成失败：" + e.message);
  } finally {
    el("generateBtn").disabled = false;
  }
}

function renderFinals() {
  const list = el("finalsList");
  list.innerHTML = "";

  if (!state.episodeId) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "请先选择项目和剧集。";
    list.appendChild(empty);
    return;
  }

  if (!state.finals || state.finals.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "这个剧集还没有成片，点右上角“生成成片”开始剪辑。";
    list.appendChild(empty);
    return;
  }

  state.finals.forEach((fc) => {
    const status = fc.status || "PENDING";

    const card = document.createElement("article");
    card.className = "final-card";

    const poster = document.createElement("div");
    poster.className = "final-poster";

    const img = document.createElement("img");
    img.src = "/media/finals/" + fc.id + "/poster.jpg";
    img.alt = "成片海报";
    img.loading = "lazy";
    img.addEventListener("error", () => {
      img.style.display = "none";
    });
    poster.appendChild(img);

    const badge = document.createElement("span");
    badge.className = statusBadge(status);
    badge.textContent = fc.statusLabel || status;
    poster.appendChild(badge);

    card.appendChild(poster);

    const info = document.createElement("div");
    info.className = "final-info";

    const title = document.createElement("h3");
    title.textContent = fc.title || "成片 " + fc.id;
    info.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "final-meta";

    const dur = document.createElement("span");
    dur.className = "timecode";
    dur.textContent = "时长 " + formatDuration(fc.durationSeconds);
    meta.appendChild(dur);

    const created = document.createElement("span");
    created.textContent = "创建 " + formatTime(fc.createdAt);
    meta.appendChild(created);

    info.appendChild(meta);

    const note = statusNote(status);
    if (note) {
      const p = document.createElement("p");
      p.className = "final-card-note";
      p.textContent = note;
      info.appendChild(p);
    }

    const actions = document.createElement("div");
    actions.className = "final-actions";

    if (status === "READY") {
      const playBtn = document.createElement("button");
      playBtn.className = "btn btn-sm btn-primary";
      playBtn.textContent = "播放";
      playBtn.setAttribute("data-play", "");
      playBtn.addEventListener("click", () => {
        const video = document.createElement("video");
        video.controls = true;
        video.autoplay = true;
        video.src = "/media/finals/" + fc.id;
        poster.innerHTML = "";
        poster.appendChild(video);
      });
      actions.appendChild(playBtn);

      const dl = document.createElement("a");
      dl.className = "btn btn-sm btn-secondary";
      dl.href = "/media/finals/" + fc.id;
      dl.setAttribute("download", "");
      dl.textContent = "下载 MP4";
      actions.appendChild(dl);
    }

    info.appendChild(actions);
    card.appendChild(info);

    list.appendChild(card);
  });
}

el("projectSelect").addEventListener("change", async (e) => {
  state.projectId = e.target.value;
  await loadEpisodes();
});

el("episodeSelect").addEventListener("change", async (e) => {
  state.episodeId = e.target.value;
  await loadFinals();
});

el("generateBtn").addEventListener("click", generateFinalCut);

loadProjects();
