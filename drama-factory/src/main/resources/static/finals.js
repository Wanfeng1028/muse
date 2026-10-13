(function () {
  'use strict';

  const API_BASE = '';

  async function api(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(API_BASE + path, opts);
    } catch (err) {
      throw new Error('网络请求失败：' + err.message);
    }
    const text = await res.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = text; }
    }
    if (!res.ok) {
      const msg = data && data.message ? data.message : (typeof data === 'string' ? data : res.statusText);
      throw new Error('接口出错 (' + res.status + ')：' + msg);
    }
    return data;
  }

  const el = {
    projectSelect: document.getElementById('projectSelect'),
    episodeSelect: document.getElementById('episodeSelect'),
    generateBtn: document.getElementById('generateBtn'),
    hint: document.getElementById('hint'),
    finalsList: document.getElementById('finalsList')
  };

  const state = {
    projectId: null,
    episodeId: null,
    finals: [],
    loading: false
  };

  function setHint(msg, type) {
    el.hint.textContent = msg || '';
    el.hint.className = 'hint' + (type ? ' hint-' + type : '');
    el.hint.hidden = !msg;
  }

  function statusBadge(status, label) {
    const cls = {
      READY: 'badge badge-success',
      BUILDING: 'badge badge-warning',
      FAILED: 'badge badge-danger'
    }[status] || 'badge';
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = label || status || '未知';
    return span;
  }

  function statusNote(status) {
    if (status === 'BUILDING') return '正在剪辑合成，完成后会自动出现在列表里，稍后刷新。';
    if (status === 'FAILED') return '合成失败，可检查分镜与任务后重新生成。';
    return '';
  }

  function formatDuration(sec) {
    if (sec == null || isNaN(sec)) return '—';
    const s = Math.round(Number(sec));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + ':' + (r < 10 ? '0' : '') + r;
  }

  function formatTime(t) {
    if (!t) return '—';
    const d = new Date(t);
    if (isNaN(d.getTime())) return String(t);
    const p = n => (n < 10 ? '0' : '') + n;
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
      p(d.getHours()) + ':' + p(d.getMinutes());
  }

  function renderFinals() {
    el.finalsList.innerHTML = '';

    if (!state.episodeId) {
      const p = document.createElement('p');
      p.className = 'empty';
      p.textContent = '请先选择项目和剧集。';
      el.finalsList.appendChild(p);
      return;
    }

    if (!state.finals.length) {
      const p = document.createElement('p');
      p.className = 'empty';
      p.textContent = '这个剧集还没有成片，点右上角“生成成片”开始剪辑。';
      el.finalsList.appendChild(p);
      return;
    }

    state.finals.forEach(function (f) {
      const card = document.createElement('div');
      card.className = 'final-card';

      const head = document.createElement('div');
      head.className = 'final-card-head';

      const titleWrap = document.createElement('div');
      titleWrap.className = 'final-card-title';
      const title = document.createElement('h3');
      title.textContent = f.title || f.fileName || ('成片 #' + f.id);
      titleWrap.appendChild(title);

      const meta = document.createElement('div');
      meta.className = 'final-card-meta';
      const durSpan = document.createElement('span');
      durSpan.textContent = '时长 ' + formatDuration(f.durationSeconds);
      const timeSpan = document.createElement('span');
      timeSpan.textContent = '创建 ' + formatTime(f.createdAt);
      meta.appendChild(durSpan);
      meta.appendChild(timeSpan);

      titleWrap.appendChild(meta);
      head.appendChild(titleWrap);
      head.appendChild(statusBadge(f.status, f.statusLabel));

      card.appendChild(head);

      const note = statusNote(f.status);
      if (note) {
        const noteEl = document.createElement('p');
        noteEl.className = 'final-card-note';
        noteEl.textContent = note;
        card.appendChild(noteEl);
      }

      if (f.status === 'READY') {
        const video = document.createElement('video');
        video.className = 'final-video';
        video.controls = true;
        video.preload = 'metadata';
        video.src = '/media/finals/' + f.id;
        card.appendChild(video);

        const actions = document.createElement('div');
        actions.className = 'final-card-actions';
        const dl = document.createElement('a');
        dl.className = 'btn btn-secondary';
        dl.href = '/media/finals/' + f.id;
        dl.setAttribute('download', f.fileName || ('final-' + f.id + '.mp4'));
        dl.textContent = '下载 MP4';
        actions.appendChild(dl);
        card.appendChild(actions);
      }

      el.finalsList.appendChild(card);
    });
  }

  async function loadProjects() {
    const projects = await api('/api/projects');
    el.projectSelect.innerHTML = '';
    if (!projects || !projects.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '暂无项目';
      el.projectSelect.appendChild(opt);
      return;
    }
    projects.forEach(function (p) {
      const opt = document.createElement('option');
      opt.value = p.id != null ? p.id : p.projectId;
      opt.textContent = p.title || p.name || ('项目 ' + (p.id != null ? p.id : p.projectId));
      el.projectSelect.appendChild(opt);
    });
    state.projectId = el.projectSelect.value;
    await loadEpisodes();
  }

  async function loadEpisodes() {
    el.episodeSelect.innerHTML = '';
    state.episodeId = null;
    state.finals = [];
    renderFinals();

    if (!state.projectId) return;

    let episodes = [];
    try {
      episodes = await api('/api/projects/' + encodeURIComponent(state.projectId) + '/episodes');
    } catch (err) {
      setHint(err.message, 'error');
      return;
    }

    if (!episodes || !episodes.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '暂无剧集';
      el.episodeSelect.appendChild(opt);
      setHint('这个项目下还没有剧集。', 'warning');
      return;
    }

    episodes.forEach(function (e) {
      const opt = document.createElement('option');
      opt.value = e.id != null ? e.id : e.episodeId;
      const no = e.episodeNo != null ? ('第 ' + e.episodeNo + ' 集 ') : '';
      opt.textContent = no + (e.title || '');
      el.episodeSelect.appendChild(opt);
    });

    state.episodeId = el.episodeSelect.value;
    await loadFinals();
  }

  async function loadFinals() {
    if (!state.episodeId) {
      state.finals = [];
      renderFinals();
      return;
    }
    setHint('正在加载成片列表…');
    try {
      const list = await api('/api/episodes/' + encodeURIComponent(state.episodeId) + '/final-cuts');
      state.finals = Array.isArray(list) ? list : (list && list.items ? list.items : []);
      setHint('');
      renderFinals();
    } catch (err) {
      state.finals = [];
      renderFinals();
      setHint(err.message, 'error');
    }
  }

  async function generateFinalCut() {
    if (!state.episodeId) {
      setHint('先选一个剧集再生成成片。', 'warning');
      return;
    }
    if (state.loading) return;
    state.loading = true;
    el.generateBtn.disabled = true;
    setHint('已提交生成请求，剪辑可能需要几分钟，请稍候…', 'info');
    try {
      await api('/api/episodes/' + encodeURIComponent(state.episodeId) + '/final-cuts', {
        method: 'POST',
        body: {}
      });
      setHint('已提交生成请求，剪辑可能需要几分钟，完成后会自动出现在下方列表。', 'success');
      await loadFinals();
    } catch (err) {
      setHint(err.message, 'error');
    } finally {
      state.loading = false;
      el.generateBtn.disabled = false;
    }
  }

  el.projectSelect.addEventListener('change', function () {
    state.projectId = el.projectSelect.value;
    setHint('');
    loadEpisodes();
  });

  el.episodeSelect.addEventListener('change', function () {
    state.episodeId = el.episodeSelect.value;
    setHint('');
    loadFinals();
  });

  el.generateBtn.addEventListener('click', generateFinalCut);

  loadProjects().catch(function (err) {
    setHint(err.message, 'error');
  });
})();
