/* P0-4: 发送按钮已改为 composer 内圆形按钮（id=sendBtn 不变），Ctrl+Enter 快捷发送保留 */
(function () {
  'use strict';

  async function api(url, options) {
    const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || '请求失败';
      throw new Error(msg);
    }
    return data;
  }

  function escapeHtml(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  const state = {
    projects: [],
    episodes: [],
    history: []
  };

  const el = {
    projectSelect: document.getElementById('projectSelect'),
    episodeSelect: document.getElementById('episodeSelect'),
    chatLog: document.getElementById('chatLog'),
    chatInput: document.getElementById('chatInput'),
    sendBtn: document.getElementById('sendBtn'),
    toast: document.getElementById('toast')
  };

  let toastInstance = null;
  function showToast(message, type) {
    if (!el.toast) return;
    el.toast.className = 'toast align-items-center text-bg-' + (type || 'danger') + ' border-0';
    el.toast.innerHTML = '<div class="d-flex"><div class="toast-body">' + escapeHtml(message) + '</div>' +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>';
    if (!toastInstance) {
      toastInstance = new tabler.Toast(el.toast, { delay: 4000 });
    }
    toastInstance.show();
  }

  async function loadProjects() {
    try {
      const data = await api('/api/projects');
      state.projects = Array.isArray(data) ? data : (data && data.items) || [];
      el.projectSelect.innerHTML = '';
      if (!state.projects.length) {
        el.projectSelect.innerHTML = '<option value="">暂无项目</option>';
        return;
      }
      state.projects.forEach(function (p) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.title || ('项目 ' + p.id);
        el.projectSelect.appendChild(opt);
      });
      el.projectSelect.value = state.projects[0].id;
      await loadEpisodes(state.projects[0].id);
    } catch (err) {
      showToast(err.message);
    }
  }

  async function loadEpisodes(projectId) {
    el.episodeSelect.innerHTML = '';
    if (!projectId) return;
    try {
      const data = await api('/api/projects/' + encodeURIComponent(projectId) + '/episodes');
      state.episodes = Array.isArray(data) ? data : (data && data.items) || [];
      if (!state.episodes.length) {
        el.episodeSelect.innerHTML = '<option value="">暂无剧集</option>';
        return;
      }
      state.episodes.forEach(function (ep) {
        const opt = document.createElement('option');
        opt.value = ep.id;
        opt.textContent = (ep.title || ep.name || ('第 ' + (ep.episodeNo || ep.id) + ' 集'));
        el.episodeSelect.appendChild(opt);
      });
      el.episodeSelect.value = state.episodes[0].id;
    } catch (err) {
      showToast(err.message);
    }
  }

  function renderMarkdown(text) {
    const escaped = escapeHtml(text);
    const blocks = [];
    let working = escaped.replace(/```([\s\S]*?)```/g, function (m, code) {
      const idx = blocks.length;
      blocks.push('<pre class="bg-dark text-light p-2 rounded"><code>' + code.replace(/^\w*\n/, '') + '</code></pre>');
      return '\u0000BLOCK' + idx + '\u0000';
    });
    working = working.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    working = working.replace(/\n/g, '<br>');
    working = working.replace(/\u0000BLOCK(\d+)\u0000/g, function (m, i) {
      return blocks[Number(i)] || '';
    });
    return working;
  }

  function scrollToBottom() {
    el.chatLog.scrollTop = el.chatLog.scrollHeight;
  }

  function addMessage(role, text) {
    const wrap = document.createElement('div');
    if (role === 'user') {
      wrap.className = 'd-flex justify-content-end mb-2';
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble-user p-2';
      bubble.style.maxWidth = '75%';
      bubble.innerHTML = renderMarkdown(text);
      wrap.appendChild(bubble);
    } else if (role === 'assistant') {
      wrap.className = 'd-flex justify-content-start mb-2';
      const bubble = document.createElement('div');
      bubble.className = 'chat-msg-assistant p-2';
      bubble.style.maxWidth = '75%';
      bubble.innerHTML = renderMarkdown(text);
      wrap.appendChild(bubble);
    } else {
      wrap.className = 'text-center text-secondary small mb-2';
      wrap.innerHTML = renderMarkdown(text);
    }
    el.chatLog.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function extractShots(text) {
    if (!text) return null;
    const re = /```json\s*([\s\S]*?)```/g;
    let m;
    while ((m = re.exec(text)) !== null) {
      const raw = m[1].trim();
      try {
        const parsed = JSON.parse(raw);
        if (parsed && Array.isArray(parsed.shots)) {
          return parsed.shots;
        }
      } catch (e) {
        // 忽略解析失败的块
      }
    }
    return null;
  }

  function field(label, idx, name, value, isTextarea) {
    const id = 'shot-' + idx + '-' + name;
    let control;
    if (isTextarea) {
      control = '<textarea class="form-control" rows="2" data-idx="' + idx + '" data-field="' + name + '" id="' + id + '">' + escapeHtml(value) + '</textarea>';
    } else {
      control = '<input type="text" class="form-control" data-idx="' + idx + '" data-field="' + name + '" id="' + id + '" value="' + escapeHtml(value) + '">';
    }
    return '<div class="mb-2"><label class="form-label" for="' + id + '">' + label + '</label>' + control + '</div>';
  }

  function renderShotEditor(shots) {
    const card = document.createElement('div');
    card.className = 'card mt-2';
    let body = '';
    shots.forEach(function (s, i) {
      const idx = i;
      const shotNo = s.shotNo != null ? s.shotNo : (i + 1);
      body += '<fieldset class="border rounded p-2 mb-3">';
      body += '<legend class="float-none w-auto px-1 small text-secondary">镜 ' + escapeHtml(shotNo) + '</legend>';
      body += '<div class="row g-2">';
      body += '<div class="col-md-4">' + field('镜号', idx, 'shotNo', shotNo, false) + '</div>';
      body += '<div class="col-md-4">' + field('景别', idx, 'shotSize', s.shotSize || '', false) + '</div>';
      body += '<div class="col-md-4">' + field('运镜', idx, 'cameraMove', s.cameraMove || '', false) + '</div>';
      body += '</div>';
      body += field('画面描述', idx, 'description', s.description || '', true);
      body += '<div class="row g-2">';
      body += '<div class="col-md-4">' + field('时长（秒）', idx, 'durationSeconds', s.durationSeconds != null ? s.durationSeconds : '', false) + '</div>';
      body += '<div class="col-md-8">' + field('台词', idx, 'dialogue', s.dialogue || '', true) + '</div>';
      body += '</div>';
      body += field('视频提示词', idx, 'videoPrompt', s.videoPrompt || '', true);
      body += '</fieldset>';
    });
    card.innerHTML = '<div class="card-header">分镜预览（可修改后落库）</div>' +
      '<div class="card-body">' + body +
      '<button id="confirmShots" class="btn btn-primary">确认落库</button></div>';

    const lastAssistant = el.chatLog.lastElementChild;
    if (lastAssistant && lastAssistant.parentNode === el.chatLog) {
      lastAssistant.insertAdjacentElement('afterend', card);
    } else {
      el.chatLog.appendChild(card);
    }
    scrollToBottom();

    const btn = card.querySelector('#confirmShots');
    btn.addEventListener('click', function () {
      collectAndCommit(card, btn);
    });
  }

  async function collectAndCommit(card, btn) {
    const episodeId = el.episodeSelect.value;
    if (!episodeId) {
      showToast('请先选择目标剧集');
      return;
    }
    const inputs = card.querySelectorAll('[data-idx][data-field]');
    const map = {};
    inputs.forEach(function (input) {
      const idx = Number(input.getAttribute('data-idx'));
      const f = input.getAttribute('data-field');
      if (!map[idx]) map[idx] = {};
      map[idx][f] = input.value;
    });
    const shots = Object.keys(map).map(function (k) {
      const item = map[k];
      const dur = parseFloat(item.durationSeconds);
      return {
        shotNo: item.shotNo,
        shotSize: item.shotSize,
        cameraMove: item.cameraMove,
        description: item.description,
        durationSeconds: isNaN(dur) ? null : dur,
        dialogue: item.dialogue,
        videoPrompt: item.videoPrompt
      };
    });
    if (!shots.length) {
      showToast('没有可落库的分镜');
      return;
    }
    btn.disabled = true;
    try {
      await api('/api/episodes/' + encodeURIComponent(episodeId) + '/shots/batch', {
        method: 'POST',
        body: JSON.stringify({ shots: shots })
      });
      addMessage('status', '已落库 ' + shots.length + ' 个分镜 → 去分镜板查看');
      const linkWrap = document.createElement('div');
      linkWrap.className = 'mb-2';
      linkWrap.innerHTML = '<a class="btn btn-sm btn-quiet" href="/storyboard.html">去分镜板查看</a>';
      el.chatLog.appendChild(linkWrap);
      scrollToBottom();
      btn.disabled = false;
    } catch (err) {
      btn.disabled = false;
      showToast(err.message);
    }
  }

  async function send() {
    const text = (el.chatInput.value || '').trim();
    if (!text) return;
    const episodeId = el.episodeSelect.value || null;

    el.sendBtn.disabled = true;
    el.chatInput.value = '';
    addMessage('user', text);
    const thinking = addMessage('status', 'AI 思考中…');

    try {
      const payload = {
        message: text,
        episodeId: episodeId,
        history: state.history.slice()
      };
      const data = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      const reply = (data && (data.reply || data.message || data.content)) || '（无回复）';

      if (thinking && thinking.parentNode) thinking.parentNode.removeChild(thinking);
      addMessage('assistant', reply);

      state.history.push({ role: 'user', content: text });
      state.history.push({ role: 'assistant', content: reply });
      if (state.history.length > 12) {
        state.history = state.history.slice(state.history.length - 12);
      }

      const shots = extractShots(reply);
      if (shots && shots.length) {
        renderShotEditor(shots);
      }
    } catch (err) {
      if (thinking && thinking.parentNode) thinking.parentNode.removeChild(thinking);
      addMessage('status', '出错了：' + err.message);
      showToast(err.message);
    } finally {
      el.sendBtn.disabled = false;
      el.chatInput.focus();
    }
  }

  function init() {
    el.projectSelect.addEventListener('change', function () {
      loadEpisodes(el.projectSelect.value);
    });

    el.sendBtn.addEventListener('click', send);

    el.chatInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        send();
      }
    });

    document.querySelectorAll('.chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        el.chatInput.value = chip.getAttribute('data-text') || '';
        el.chatInput.focus();
      });
    });

    loadProjects();
  }

  init();
})();
