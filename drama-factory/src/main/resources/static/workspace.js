/* ==========================================================================
   workspace.js —— chat-first 工作区上下文同步（v6.0）
   顶部状态条、项目/剧集选择器、新建表单、与 chat.js 通过 projectSelect 同步。
   ========================================================================== */
(function () {
  'use strict';

  var PAGE_I18N = {
    'ws.docTitle': { 'zh-CN': 'AI 工作区 · AI 短剧工坊', 'en': 'AI Workspace · AI Drama Factory' },
    'ws.greeting': { 'zh-CN': '和 AI 一起做短剧', 'en': 'Make short dramas with AI' },
    'ws.statusEmpty': { 'zh-CN': '分镜 — · 任务 — · 待质检 —', 'en': 'Shots — · Tasks — · QC —' },
    'ws.context': { 'zh-CN': '上下文', 'en': 'Context' },
    'ws.projectAria': { 'zh-CN': '项目', 'en': 'Project' },
    'ws.episodeAria': { 'zh-CN': '剧集', 'en': 'Episode' },
    'ws.toggleNew': { 'zh-CN': '＋ 新建', 'en': '+ New' },
    'ws.newProject': { 'zh-CN': '新建项目', 'en': 'New Project' },
    'ws.projectTitlePh': { 'zh-CN': '项目标题，例如：逆袭千金', 'en': 'Project title, e.g. Comeback Heiress' },
    'ws.projectGenrePh': { 'zh-CN': '类型，例如：都市/爽文', 'en': 'Genre, e.g. Urban / Revenge' },
    'ws.newEpisode': { 'zh-CN': '新建剧集', 'en': 'New Episode' },
    'ws.episodeNoPh': { 'zh-CN': '集号', 'en': 'Episode No.' },
    'ws.episodeTitlePh': { 'zh-CN': '标题（可选）', 'en': 'Title (optional)' },
    'ws.chipScript': { 'zh-CN': '写一个3镜小剧本', 'en': 'Write a 3-shot script' },
    'ws.chipSplit': { 'zh-CN': '把上面的剧本拆成…', 'en': 'Break the script above into…' },
    'ws.chipOptimize': { 'zh-CN': '优化第1镜的视频提示词', 'en': 'Improve shot 1 video prompt' },
    'ws.inputPh': { 'zh-CN': '和 AI 编剧聊剧本、分镜、提示词…', 'en': 'Chat with the AI writer about scripts, shots, prompts…' },
    'ws.sendAria': { 'zh-CN': '发送', 'en': 'Send' },
    'ws.quotaNote': { 'zh-CN': '对话会产生模型调用费用，请按需使用。', 'en': 'Chats use model calls and cost money — use as needed.' },
    'ws.recentAria': { 'zh-CN': '最近动态', 'en': 'Recent activity' },
    'ws.recentTitle': { 'zh-CN': '最近动态', 'en': 'Recent activity' },
    'ws.recentEmpty': { 'zh-CN': '暂无动态，从上面的输入框开始。', 'en': 'No activity yet. Start with the input above.' },
    'ws.noProjects': { 'zh-CN': '暂无项目', 'en': 'No projects yet' },
    'ws.noEpisodes': { 'zh-CN': '暂无剧集', 'en': 'No episodes yet' },
    'ws.pickProjectFirst': { 'zh-CN': '先选择项目', 'en': 'Select a project first' },
    'ws.loadProjectsFail': { 'zh-CN': '项目加载失败：', 'en': 'Failed to load projects: ' },
    'ws.loadEpisodesFail': { 'zh-CN': '剧集加载失败：', 'en': 'Failed to load episodes: ' },
    'ws.requestFailed': { 'zh-CN': '请求失败', 'en': 'Request failed' },
    'ws.shots': { 'zh-CN': '分镜', 'en': 'Shots' },
    'ws.tasks': { 'zh-CN': '任务', 'en': 'Tasks' },
    'ws.tasksSuccess': { 'zh-CN': '成功', 'en': 'ok' },
    'ws.pendingQc': { 'zh-CN': '待质检', 'en': 'QC pending' },
    'ws.minutesAgo': { 'zh-CN': '分钟前', 'en': 'min ago' },
    'ws.hoursAgo': { 'zh-CN': '小时前', 'en': 'h ago' },
    'ws.daysAgo': { 'zh-CN': '天前', 'en': 'd ago' },
    'ws.monthDay': { 'zh-CN': '月', 'en': '/' },
    'ws.day': { 'zh-CN': '日', 'en': '' },
    'ws.episode': { 'zh-CN': '第 ', 'en': 'Ep ' },
    'ws.episodeSuffix': { 'zh-CN': ' 集', 'en': '' },
    'ws.qcApproved': { 'zh-CN': '质检通过', 'en': 'QC passed' },
    'ws.qcRejected': { 'zh-CN': '质检未通过', 'en': 'QC failed' },
    'ws.qcPending': { 'zh-CN': '待质检', 'en': 'QC pending' },
    'ws.finalCutReady': { 'zh-CN': '成片已生成', 'en': 'Final cut ready' },
    'ws.episodeCreated': { 'zh-CN': '剧集已创建', 'en': 'Episode created' },
    'ws.fillProjectTitle': { 'zh-CN': '请填写项目标题', 'en': 'Please enter a project title' },
    'ws.createFail': { 'zh-CN': '创建失败：', 'en': 'Create failed: ' },
    'ws.pickProject': { 'zh-CN': '请先选择项目', 'en': 'Please select a project first' },
    'ws.fillEpisodeNo': { 'zh-CN': '请填写集号', 'en': 'Please enter an episode number' }
  };
  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) return DFI18N.tr(key);
    return zh;
  }

  async function api(path, opts) {
    var options = Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {});
    if (options.body && typeof options.body !== 'string') options.body = JSON.stringify(options.body);
    var res = await fetch(path, options);
    var text = await res.text();
    var data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!res.ok) throw new Error((data && (data.message || data.error)) || _t('ws.requestFailed', '请求失败'));
    return data;
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  var state = { projectId: null };

  function $(id) { return document.getElementById(id); }

  function toast(msg) {
    var t = $('toast');
    if (!t) return;
    t.className = 'toast align-items-center text-bg-danger border-0 show';
    t.innerHTML = '<div class="d-flex"><div class="toast-body">' + esc(msg) + '</div></div>';
    setTimeout(function () { t.className = 'toast'; }, 4000);
  }

  /* ---- 项目选择器 ---- */
  async function loadProjects() {
    try {
      var list = await api('/api/projects');
      var sel = $('projectSelect');
      if (!sel) return;
      sel.innerHTML = '';
      if (!list || !list.length) {
        sel.innerHTML = '<option value="">' + esc(_t('ws.noProjects', '暂无项目')) + '</option>';
        return;
      }
      list.forEach(function (p) {
        var o = document.createElement('option');
        o.value = p.id;
        o.textContent = p.title + (p.genre ? ' · ' + p.genre : '');
        sel.appendChild(o);
      });
      var prefer = state.projectId || sel.value || list[0].id;
      sel.value = String(prefer);
      state.projectId = sel.value || null;
      await loadEpisodes();
      loadStatusStrip();
      loadRecentActivity();
    } catch (e) { toast(_t('ws.loadProjectsFail', '项目加载失败：') + e.message); }
  }

  /* ---- 剧集选择器 ---- */
  async function loadEpisodes() {
    var sel = $('episodeSelect');
    if (!sel) return;
    if (!state.projectId) {
      sel.innerHTML = '<option value="">' + esc(_t('ws.pickProjectFirst', '先选择项目')) + '</option>';
      return;
    }
    try {
      var list = await api('/api/projects/' + state.projectId + '/episodes');
      sel.innerHTML = '';
      if (!list || !list.length) {
        sel.innerHTML = '<option value="">' + esc(_t('ws.noEpisodes', '暂无剧集')) + '</option>';
        return;
      }
      list.forEach(function (ep) {
        var o = document.createElement('option');
        o.value = ep.id;
        o.textContent = _t('ws.episode', '第 ') + ep.episodeNo + _t('ws.episodeSuffix', ' 集') + (ep.title ? ' · ' + ep.title : '');
        sel.appendChild(o);
      });
    } catch (e) { toast(_t('ws.loadEpisodesFail', '剧集加载失败：') + e.message); }
  }

  /* ---- 顶部状态条 ---- */
  async function loadStatusStrip() {
    var strip = $('ws-status-strip');
    if (!strip) return;
    if (!state.projectId) {
      strip.textContent = _t('ws.statusEmpty', '分镜 — · 任务 — · 待质检 —');
      return;
    }
    var shotsText = _t('ws.shots', '分镜') + ' —';
    var tasksText = _t('ws.tasks', '任务') + ' —';
    var qcCount = null;
    try {
      var s = await api('/api/projects/' + state.projectId + '/stats');
      var shotTotal = s.shotCount || 0;
      var shotDone = s.shotsCompleted || 0;
      shotsText = _t('ws.shots', '分镜') + ' ' + shotDone + '/' + shotTotal;
      var taskTotal = (s.tasksDone || 0) + (s.tasksFailed || 0);
      if (taskTotal > 0) {
        tasksText = _t('ws.tasks', '任务') + ' ' + (s.tasksDone || 0) + '/' + taskTotal + ' ' + _t('ws.tasksSuccess', '成功');
      } else {
        tasksText = _t('ws.tasks', '任务') + ' —';
      }
    } catch (e) { /* 忽略 */ }
    try {
      qcCount = await countPendingQc();
    } catch (e) { /* 忽略 */ }
    strip.textContent = shotsText + ' · ' + tasksText + ' · ' + _t('ws.pendingQc', '待质检') + ' ' +
      (qcCount == null ? '—' : qcCount);
  }

  async function countPendingQc() {
    if (!state.projectId) return 0;
    var view = await api('/api/projects/' + state.projectId + '/pipeline');
    var eps = (view && view.episodes) || [];
    var pending = 0;
    for (var i = 0; i < eps.length; i++) {
      if (eps[i].finalCutStatus === 'READY') {
        var cuts = await api('/api/episodes/' + eps[i].episodeId + '/final-cuts');
        (cuts || []).forEach(function (c) {
          if (c.qcStatus === 'PENDING') pending++;
        });
      }
    }
    return pending;
  }

  /* ---- 最近动态（真实记录，最多 5 条） ---- */
  function formatRecentTime(v) {
    var t = new Date(v);
    if (isNaN(t.getTime())) return '';
    var diff = Date.now() - t.getTime();
    if (diff < 0) diff = 0;
    var min = Math.floor(diff / 60000);
    if (diff < 3600000) return (min < 1 ? 1 : min) + ' ' + _t('ws.minutesAgo', '分钟前');
    if (diff < 86400000) return Math.floor(diff / 3600000) + ' ' + _t('ws.hoursAgo', '小时前');
    if (diff < 2592000000) return Math.floor(diff / 86400000) + ' ' + _t('ws.daysAgo', '天前');
    return (t.getMonth() + 1) + _t('ws.monthDay', '月') + t.getDate() + _t('ws.day', '日');
  }

  function pickCutTime(cut) {
    if (!cut) return '';
    return cut.createdAt || cut.updatedAt || cut.createTime || '';
  }

  function qcDot(qcStatus) {
    if (qcStatus === 'APPROVED') return 'is-success';
    return 'is-waiting';
  }

  function qcText(qcStatus) {
    if (qcStatus === 'APPROVED') return _t('ws.qcApproved', '质检通过');
    if (qcStatus === 'REJECTED') return _t('ws.qcRejected', '质检未通过');
    if (qcStatus === 'PENDING') return _t('ws.qcPending', '待质检');
    return _t('ws.finalCutReady', '成片已生成');
  }

  async function loadRecentActivity() {
    var listEl = document.getElementById('ws-recent-list');
    if (!listEl || !state.projectId) return;
    try {
      var episodes = await api('/api/projects/' + state.projectId + '/episodes');
      if (!Array.isArray(episodes)) episodes = [];
      var cuts = [];
      for (var i = 0; i < episodes.length; i++) {
        var ep = episodes[i] || {};
        var epNo = (ep.episodeNo != null ? ep.episodeNo : (i + 1));
        try {
          var epCuts = await api('/api/episodes/' + ep.id + '/final-cuts');
          if (!Array.isArray(epCuts)) epCuts = [];
          for (var j = 0; j < epCuts.length; j++) {
            var c = epCuts[j] || {};
            cuts.push({
              epNo: epNo,
              time: pickCutTime(c),
              cls: qcDot(c.qcStatus),
              text: qcText(c.qcStatus)
            });
          }
        } catch (e) { /* 单集失败不影响整体，静默 */ }
      }
      cuts.sort(function (a, b) {
        var ta = a.time ? new Date(a.time).getTime() : 0;
        var tb = b.time ? new Date(b.time).getTime() : 0;
        if (isNaN(ta)) ta = 0;
        if (isNaN(tb)) tb = 0;
        return tb - ta;
      });
      var items = cuts.slice(0, 5);
      if (!items.length) {
        for (var k = 0; k < episodes.length && items.length < 5; k++) {
          var e2 = episodes[k] || {};
          var n2 = (e2.episodeNo != null ? e2.episodeNo : (k + 1));
          items.push({ epNo: n2, time: '', cls: 'is-waiting', text: _t('ws.episodeCreated', '剧集已创建') });
        }
      }
      if (!items.length) return;
      var html = '';
      for (var m = 0; m < items.length; m++) {
        var it = items[m];
        var timeStr = it.time ? formatRecentTime(it.time) : '';
        html += '<div class="ws-recent-item">'
          + '<span class="ws-recent-dot ' + it.cls + '"></span>'
          + '<span class="ws-recent-text"><span class="ws-recent-name">' + esc(_t('ws.episode', '第 ') + it.epNo + _t('ws.episodeSuffix', ' 集')) + '</span> · ' + esc(it.text) + '</span>'
          + '<span class="ws-recent-time">' + esc(timeStr) + '</span>'
          + '</div>';
      }
      listEl.innerHTML = html;
    } catch (e) { /* 静默保留空状态 */ }
  }

  function selectProject(id) {
    state.projectId = id || null;
    var sel = $('projectSelect');
    if (sel && sel.value !== String(id)) sel.value = String(id);
    loadEpisodes();
    loadStatusStrip();
    loadRecentActivity();
  }

  /* ---- 新建表单 ---- */
  function init() {
    if (window.DFI18N) DFI18N.applyI18n();

    var panel = $('ws-new-panel');
    var toggle = $('ws-toggle-new');
    if (toggle && panel) {
      toggle.addEventListener('click', function () {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      });
    }

    var npf = $('ws-project-form');
    var npc = $('ws-project-cancel');
    if (npc && npf) npc.addEventListener('click', function () { npf.style.display = 'none'; });
    if (npf) {
      npf.addEventListener('submit', async function (e) {
        e.preventDefault();
        var title = $('ws-project-title').value.trim();
        if (!title) { toast(_t('ws.fillProjectTitle', '请填写项目标题')); return; }
        try {
          var p = await api('/api/projects', { method: 'POST', body: {
            title: title,
            genre: $('ws-project-genre').value.trim() || null
          }});
          npf.reset();
          npf.style.display = 'none';
          state.projectId = p && p.id ? String(p.id) : state.projectId;
          await loadProjects();
          if (panel) panel.style.display = 'none';
        } catch (err) { toast(_t('ws.createFail', '创建失败：') + err.message); }
      });
    }

    var nef = $('ws-episode-form');
    var nec = $('ws-episode-cancel');
    if (nec && nef) nec.addEventListener('click', function () { nef.style.display = 'none'; });
    if (nef) {
      nef.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (!state.projectId) { toast(_t('ws.pickProject', '请先选择项目')); return; }
        var no = parseInt($('ws-episode-no').value, 10);
        if (!no) { toast(_t('ws.fillEpisodeNo', '请填写集号')); return; }
        try {
          await api('/api/projects/' + state.projectId + '/episodes', { method: 'POST', body: {
            episodeNo: no,
            title: $('ws-episode-title').value.trim() || null
          }});
          nef.reset();
          nef.style.display = 'none';
          await loadEpisodes();
        } catch (err) { toast(_t('ws.createFail', '创建失败：') + err.message); }
      });
    }

    var ps = $('projectSelect');
    if (ps) {
      ps.addEventListener('change', function () {
        if (ps.value) selectProject(ps.value);
      });
    }

    loadProjects();

    if (window.DFI18N) {
      DFI18N.onLangChange(function () {
        loadStatusStrip();
        loadRecentActivity();
        loadEpisodes();
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
