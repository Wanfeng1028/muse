/* P0-4: 发送按钮已改为 composer 内圆形按钮（id=sendBtn 不变），Ctrl+Enter 快捷发送保留 */
(function () {
  'use strict';

  var PAGE_I18N = {
    'chat.docTitle': { 'zh-CN': 'AI 对话 · AI 短剧工坊', 'en': 'AI Chat · AI Drama Factory' },
    'chat.pageTitle': { 'zh-CN': 'AI 对话', 'en': 'AI Chat' },
    'chat.project': { 'zh-CN': '项目', 'en': 'Project' },
    'chat.targetEpisode': { 'zh-CN': '目标剧集', 'en': 'Target episode' },
    'chat.chipScript': { 'zh-CN': '写一个3镜小剧本', 'en': 'Write a 3-shot script' },
    'chat.chipSplit': { 'zh-CN': '把上面的剧本拆成…', 'en': 'Break the script above into…' },
    'chat.chipOptimize': { 'zh-CN': '优化第1镜的视频提示词', 'en': 'Improve shot 1 video prompt' },
    'chat.inputPh': { 'zh-CN': '和 AI 编剧聊剧本、分镜、提示词…', 'en': 'Chat with the AI writer about scripts, shots, prompts…' },
    'chat.sendAria': { 'zh-CN': '发送', 'en': 'Send' },
    'chat.quotaNote': { 'zh-CN': '对话会产生模型调用费用，请按需使用。', 'en': 'Chats use model calls and cost money — use as needed.' },
    'chat.requestFailed': { 'zh-CN': '请求失败', 'en': 'Request failed' },
    'chat.noProjects': { 'zh-CN': '暂无项目', 'en': 'No projects yet' },
    'chat.noEpisodes': { 'zh-CN': '暂无剧集', 'en': 'No episodes yet' },
    'chat.projectLabel': { 'zh-CN': '项目 ', 'en': 'Project ' },
    'chat.episodeLabel': { 'zh-CN': '第 ', 'en': 'Ep ' },
    'chat.episodeSuffix': { 'zh-CN': ' 集', 'en': '' },
    'chat.pickEpisode': { 'zh-CN': '请先选择目标剧集', 'en': 'Please select a target episode first' },
    'chat.noShots': { 'zh-CN': '没有可落库的分镜', 'en': 'No shots to save' },
    'chat.committedPrefix': { 'zh-CN': '已落库 ', 'en': 'Saved ' },
    'chat.committedSuffix': { 'zh-CN': ' 个分镜 → 去分镜板查看', 'en': ' shots → view on the storyboard' },
    'chat.goStoryboard': { 'zh-CN': '去分镜板查看', 'en': 'View on storyboard' },
    'chat.thinking': { 'zh-CN': 'AI 思考中…', 'en': 'AI is thinking…' },
    'chat.noReply': { 'zh-CN': '（无回复）', 'en': '(no reply)' },
    'chat.errorPrefix': { 'zh-CN': '出错了：', 'en': 'Error: ' },
    'chat.shotPreview': { 'zh-CN': '分镜预览（可修改后落库）', 'en': 'Shot preview (edit before saving)' },
    'chat.confirmCommit': { 'zh-CN': '确认落库', 'en': 'Confirm and save' },
    'chat.shotNo': { 'zh-CN': '镜号', 'en': 'Shot No.' },
    'chat.shotSize': { 'zh-CN': '景别', 'en': 'Shot Size' },
    'chat.cameraMove': { 'zh-CN': '运镜', 'en': 'Camera Move' },
    'chat.description': { 'zh-CN': '画面描述', 'en': 'Description' },
    'chat.durationSeconds': { 'zh-CN': '时长（秒）', 'en': 'Duration (sec)' },
    'chat.dialogue': { 'zh-CN': '台词', 'en': 'Dialogue' },
    'chat.videoPrompt': { 'zh-CN': '视频提示词', 'en': 'Video prompt' },
    'chat.shot': { 'zh-CN': '镜 ', 'en': 'Shot ' }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  async function api(url, options) {
    const opts = Object.assign({ headers: { 'Content-Type': 'application/json' } }, options || {});
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) || _t('chat.requestFailed', '请求失败');
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
        el.projectSelect.innerHTML = '<option value="">' + escapeHtml(_t('chat.noProjects', '暂无项目')) + '</option>';
        return;
      }
      state.projects.forEach(function (p) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.title || (_t('chat.projectLabel', '项目 ') + p.id);
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
        el.episodeSelect.innerHTML = '<option value="">' + escapeHtml(_t('chat.noEpisodes', '暂无剧集')) + '</option>';
        return;
      }
      state.episodes.forEach(function (ep) {
        const opt = document.createElement('option');
        opt.value = ep.id;
        opt.textContent = (ep.title || ep.name || (_t('chat.episodeLabel', '第 ') + (ep.episodeNo || ep.id) + _t('chat.episodeSuffix', ' 集')));
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
      bubble.innerHTML = renderMarkdown(text);
      wrap.appendChild(bubble);
    } else if (role === 'assistant') {
      wrap.className = 'd-flex justify-content-start mb-2';
      const bubble = document.createElement('div');
      bubble.className = 'chat-msg-assistant p-2';
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
      body += '<legend class="float-none w-auto px-1 small text-secondary">' + _t('chat.shot', '镜 ') + escapeHtml(shotNo) + '</legend>';
      body += '<div class="row g-2">';
      body += '<div class="col-md-4">' + field(_t('chat.shotNo', '镜号'), idx, 'shotNo', shotNo, false) + '</div>';
      body += '<div class="col-md-4">' + field(_t('chat.shotSize', '景别'), idx, 'shotSize', s.shotSize || '', false) + '</div>';
      body += '<div class="col-md-4">' + field(_t('chat.cameraMove', '运镜'), idx, 'cameraMove', s.cameraMove || '', false) + '</div>';
      body += '</div>';
      body += field(_t('chat.description', '画面描述'), idx, 'description', s.description || '', true);
      body += '<div class="row g-2">';
      body += '<div class="col-md-4">' + field(_t('chat.durationSeconds', '时长（秒）'), idx, 'durationSeconds', s.durationSeconds != null ? s.durationSeconds : '', false) + '</div>';
      body += '<div class="col-md-8">' + field(_t('chat.dialogue', '台词'), idx, 'dialogue', s.dialogue || '', true) + '</div>';
      body += '</div>';
      body += field(_t('chat.videoPrompt', '视频提示词'), idx, 'videoPrompt', s.videoPrompt || '', true);
      body += '</fieldset>';
    });
    card.innerHTML = '<div class="card-header">' + _t('chat.shotPreview', '分镜预览（可修改后落库）') + '</div>' +
      '<div class="card-body">' + body +
      '<button id="confirmShots" class="btn btn-primary">' + _t('chat.confirmCommit', '确认落库') + '</button></div>';

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
      showToast(_t('chat.pickEpisode', '请先选择目标剧集'));
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
      showToast(_t('chat.noShots', '没有可落库的分镜'));
      return;
    }
    btn.disabled = true;
    try {
      await api('/api/episodes/' + encodeURIComponent(episodeId) + '/shots/batch', {
        method: 'POST',
        body: JSON.stringify({ shots: shots })
      });
      addMessage('status', _t('chat.committedPrefix', '已落库 ') + shots.length + _t('chat.committedSuffix', ' 个分镜 → 去分镜板查看'));
      const linkWrap = document.createElement('div');
      linkWrap.className = 'mb-2';
      linkWrap.innerHTML = '<a class="btn btn-sm btn-quiet" href="/storyboard.html">' + _t('chat.goStoryboard', '去分镜板查看') + '</a>';
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
    const thinking = addMessage('status', _t('chat.thinking', 'AI 思考中…'));

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
      const reply = (data && (data.reply || data.message || data.content)) || _t('chat.noReply', '（无回复）');

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
      addMessage('status', _t('chat.errorPrefix', '出错了：') + err.message);
      showToast(err.message);
    } finally {
      el.sendBtn.disabled = false;
      el.chatInput.focus();
    }
  }

  function init() {
    if (window.DFI18N) DFI18N.applyI18n();

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

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        DFI18N.applyI18n();
        loadProjects();
      });
    }
  }

  init();
})();
