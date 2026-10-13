(function () {
  'use strict';

  var API_BASE = '';

  function api(path, options) {
    options = options || {};
    var cfg = {
      method: options.method || 'GET',
      headers: { 'Content-Type': 'application/json' }
    };
    if (options.body !== undefined) {
      cfg.body = JSON.stringify(options.body);
    }
    return fetch(API_BASE + path, cfg).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        if (text) {
          try { data = JSON.parse(text); } catch (e) { data = text; }
        }
        if (!res.ok) {
          var msg = (data && data.message) ? data.message : ('请求失败 ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  var SHOT_SIZE_LABEL = {
    TE_XIE: '特写',
    JIN_JING: '近景',
    ZHONG_JING: '中景',
    QUAN_JING: '全景',
    YUAN_JING: '远景'
  };
  var CAMERA_MOVE_LABEL = {
    GU_DING: '固定机位',
    TUI: '推镜头',
    LA: '拉镜头',
    YAO: '摇镜头',
    YI: '移镜头',
    GEN: '跟镜头',
    SHENG_JIANG: '升降'
  };

  var state = {
    projects: [],
    episodes: [],
    projectId: '',
    episodeId: '',
    shots: [],
    taskMap: {},
    editingId: null
  };

  function $(id) { return document.getElementById(id); }

  function toast(msg, isError) {
    var el = $('toast');
    el.textContent = msg;
    el.className = 'toast' + (isError ? ' toast-error' : '');
    el.classList.remove('hidden');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.classList.add('hidden'); }, 3200);
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function statusClass(label) {
    if (!label) return 'badge';
    var l = String(label);
    if (l.indexOf('完成') >= 0 || l.indexOf('成功') >= 0 || l === 'DONE') return 'badge badge-success';
    if (l.indexOf('处理') >= 0 || l.indexOf('进行') >= 0 || l.indexOf('生成') >= 0 || l === 'PROCESSING') return 'badge badge-info';
    if (l.indexOf('失败') >= 0 || l.indexOf('错误') >= 0 || l === 'FAILED') return 'badge badge-danger';
    if (l.indexOf('待') >= 0 || l.indexOf('排队') >= 0 || l === 'PENDING') return 'badge badge-warning';
    return 'badge';
  }

  function loadProjects() {
    return api('/api/projects').then(function (list) {
      state.projects = Array.isArray(list) ? list : [];
      var sel = $('projectSelect');
      if (!state.projects.length) {
        sel.innerHTML = '<option value="">无项目</option>';
        return;
      }
      var html = '<option value="">请选择项目</option>';
      state.projects.forEach(function (p) {
        var pid = p.id !== undefined ? p.id : p.projectId;
        var title = p.title || p.name || ('项目 ' + pid);
        html += '<option value="' + escapeHtml(pid) + '">' + escapeHtml(title) + '</option>';
      });
      sel.innerHTML = html;
      // 自动选中首个项目并加载其剧集
      var firstPid = state.projects[0].id !== undefined ? state.projects[0].id : state.projects[0].projectId;
      state.projectId = firstPid;
      sel.value = firstPid;
      return loadEpisodes(firstPid);
    }).catch(function (err) {
      toast('项目加载失败：' + err.message, true);
    });
  }

  function loadEpisodes(pid) {
    var sel = $('episodeSelect');
    state.episodes = [];
    state.episodeId = '';
    sel.innerHTML = '<option value="">加载中…</option>';
    $('episodeMeta').textContent = '';
    if (!pid) {
      sel.innerHTML = '<option value="">请选择项目</option>';
      renderShots();
      return Promise.resolve();
    }
    return api('/api/projects/' + encodeURIComponent(pid) + '/episodes').then(function (list) {
      state.episodes = Array.isArray(list) ? list : [];
      if (!state.episodes.length) {
        sel.innerHTML = '<option value="">无剧集</option>';
        renderShots();
        return;
      }
      var html = '<option value="">请选择剧集</option>';
      state.episodes.forEach(function (e) {
        var eid = e.id !== undefined ? e.id : e.episodeId;
        var label = '第' + (e.episodeNo !== undefined ? e.episodeNo : '?') + '集';
        if (e.title) label += ' · ' + e.title;
        html += '<option value="' + escapeHtml(eid) + '">' + escapeHtml(label) + '</option>';
      });
      sel.innerHTML = html;
      // 自动选中首个剧集并加载分镜
      var firstEid = state.episodes[0].id !== undefined ? state.episodes[0].id : state.episodes[0].episodeId;
      state.episodeId = firstEid;
      state.taskMap = {};
      sel.value = firstEid;
      updateEpisodeMeta();
      return loadShots();
    }).catch(function (err) {
      sel.innerHTML = '<option value="">加载失败</option>';
      toast('剧集加载失败：' + err.message, true);
      renderShots();
    });
  }

  function currentEpisode() {
    for (var i = 0; i < state.episodes.length; i++) {
      var eid = state.episodes[i].id !== undefined ? state.episodes[i].id : state.episodes[i].episodeId;
      if (String(eid) === String(state.episodeId)) return state.episodes[i];
    }
    return null;
  }

  function updateEpisodeMeta() {
    var ep = currentEpisode();
    var el = $('episodeMeta');
    if (!ep) { el.textContent = ''; return; }
    var parts = [];
    if (ep.status) parts.push('状态：' + ep.status);
    if (ep.shotCount !== undefined) parts.push('分镜 ' + ep.shotCount + ' 个');
    el.textContent = parts.join(' ｜ ');
  }

  function loadShots() {
    var eid = state.episodeId;
    if (!eid) { state.shots = []; state.taskMap = {}; renderShots(); return Promise.resolve(); }
    return api('/api/episodes/' + encodeURIComponent(eid) + '/shots').then(function (list) {
      state.shots = Array.isArray(list) ? list : [];
      state.shots.sort(function (a, b) {
        return (a.shotNo || 0) - (b.shotNo || 0);
      });
      return loadTasksForShots();
    }).then(function () {
      renderShots();
    }).catch(function (err) {
      toast('分镜加载失败：' + err.message, true);
      state.shots = [];
      renderShots();
    });
  }

  function loadTasksForShots() {
    var jobs = state.shots.map(function (shot) {
      var sid = shot.id !== undefined ? shot.id : shot.shotId;
      return api('/api/shots/' + encodeURIComponent(sid) + '/video-tasks').then(function (tasks) {
        var list = Array.isArray(tasks) ? tasks : [];
        var latest = null;
        list.forEach(function (t) {
          if (!latest) { latest = t; return; }
          var ta = t.createdAt || t.id || 0;
          var la = latest.createdAt || latest.id || 0;
          if (ta > la) latest = t;
        });
        state.taskMap[sid] = latest;
      }).catch(function () {
        state.taskMap[sid] = null;
      });
    });
    return Promise.all(jobs);
  }

  function renderShots() {
    var tbody = $('shotTbody');
    updateEpisodeMeta();
    if (!state.episodeId) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">请选择项目与剧集</td></tr>';
      return;
    }
    if (!state.shots.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">本集暂无分镜，点击"添加分镜"新建</td></tr>';
      return;
    }
    var html = '';
    state.shots.forEach(function (shot, idx) {
      var sid = shot.id !== undefined ? shot.id : shot.shotId;
      var task = state.taskMap[sid];
      var taskLabel = task ? (task.statusLabel || task.status || '—') : '未生成';
      var taskCls = task ? statusClass(task.statusLabel || task.status) : 'badge badge-muted';
      var duration = shot.durationSeconds !== undefined && shot.durationSeconds !== null ? shot.durationSeconds : '';
      html += '<tr data-sid="' + escapeHtml(sid) + '">';
      html += '<td>' + escapeHtml(shot.shotNo) + '</td>';
      html += '<td>' + escapeHtml(SHOT_SIZE_LABEL[shot.shotSize] || shot.shotSize || '') + '</td>';
      html += '<td>' + escapeHtml(CAMERA_MOVE_LABEL[shot.cameraMove] || shot.cameraMove || '') + '</td>';
      html += '<td>' + escapeHtml(duration) + '</td>';
      html += '<td class="cell-text">' + escapeHtml(shot.description || '') + '</td>';
      html += '<td class="cell-text">' + escapeHtml(shot.dialogue || '') + '</td>';
      html += '<td class="cell-text">' + escapeHtml(shot.videoPrompt || '') + '</td>';
      html += '<td><span class="' + taskCls + '">' + escapeHtml(taskLabel) + '</span></td>';
      html += '<td class="ops">';
      html += '<button class="btn btn-sm" data-act="up" ' + (idx === 0 ? 'disabled' : '') + '>上移</button>';
      html += '<button class="btn btn-sm" data-act="down" ' + (idx === state.shots.length - 1 ? 'disabled' : '') + '>下移</button>';
      html += '<button class="btn btn-sm" data-act="edit">编辑</button>';
      html += '<button class="btn btn-sm btn-danger" data-act="del">删除</button>';
      html += '<button class="btn btn-sm btn-primary" data-act="gen">生成视频</button>';
      html += '</td>';
      html += '</tr>';
    });
    tbody.innerHTML = html;
  }

  function findShot(sid) {
    for (var i = 0; i < state.shots.length; i++) {
      var id = state.shots[i].id !== undefined ? state.shots[i].id : state.shots[i].shotId;
      if (String(id) === String(sid)) return state.shots[i];
    }
    return null;
  }

  function openForm(shot) {
    state.editingId = shot ? (shot.id !== undefined ? shot.id : shot.shotId) : null;
    $('formTitle').textContent = shot ? ('编辑分镜 #' + shot.shotNo) : '添加分镜';
    $('shotId').value = state.editingId || '';
    $('shotNo').value = shot ? (shot.shotNo || '') : (state.shots.length ? (state.shots[state.shots.length - 1].shotNo || 0) + 1 : 1);
    $('shotSize').value = shot && shot.shotSize ? shot.shotSize : 'ZHONG_JING';
    $('cameraMove').value = shot && shot.cameraMove ? shot.cameraMove : 'GU_DING';
    $('durationSeconds').value = shot && shot.durationSeconds !== undefined ? shot.durationSeconds : 3;
    $('description').value = shot && shot.description ? shot.description : '';
    $('dialogue').value = shot && shot.dialogue ? shot.dialogue : '';
    $('videoPrompt').value = shot && shot.videoPrompt ? shot.videoPrompt : '';
    $('formError').textContent = '';
    $('formPanel').classList.remove('hidden');
    $('shotNo').focus();
  }

  function closeForm() {
    state.editingId = null;
    $('formPanel').classList.add('hidden');
    $('shotForm').reset();
    $('shotId').value = '';
  }

  function collectForm() {
    return {
      shotNo: parseInt($('shotNo').value, 10) || 0,
      shotSize: $('shotSize').value,
      cameraMove: $('cameraMove').value,
      description: $('description').value.trim(),
      durationSeconds: parseFloat($('durationSeconds').value) || 0,
      dialogue: $('dialogue').value.trim(),
      videoPrompt: $('videoPrompt').value.trim()
    };
  }

  function saveShot(e) {
    e.preventDefault();
    var eid = state.episodeId;
    if (!eid) { $('formError').textContent = '请先选择剧集'; return; }
    var body = collectForm();
    if (!body.shotNo) { $('formError').textContent = '镜号必填'; return; }
    var editing = state.editingId;
    var p;
    if (editing) {
      p = api('/api/shots/' + encodeURIComponent(editing), { method: 'PUT', body: body });
    } else {
      p = api('/api/episodes/' + encodeURIComponent(eid) + '/shots', { method: 'POST', body: body });
    }
    p.then(function () {
      toast(editing ? '分镜已更新' : '分镜已添加');
      closeForm();
      return loadShots();
    }).catch(function (err) {
      $('formError').textContent = err.message;
      toast('保存失败：' + err.message, true);
    });
  }

  function deleteShot(sid) {
    var shot = findShot(sid);
    var label = shot ? ('镜号 ' + shot.shotNo) : ('ID ' + sid);
    if (!window.confirm('确定删除分镜 ' + label + ' 吗？此操作不可撤销。')) return;
    api('/api/shots/' + encodeURIComponent(sid), { method: 'DELETE' }).then(function () {
      toast('分镜已删除');
      return loadShots();
    }).catch(function (err) {
      toast('删除失败：' + err.message, true);
    });
  }

  function reorder(newOrder) {
    var eid = state.episodeId;
    var ids = newOrder.map(function (s) {
      return s.id !== undefined ? s.id : s.shotId;
    });
    api('/api/episodes/' + encodeURIComponent(eid) + '/shots/reorder', {
      method: 'POST',
      body: { shotIds: ids }
    }).then(function () {
      return loadShots();
    }).catch(function (err) {
      toast('排序失败：' + err.message, true);
      renderShots();
    });
  }

  function moveShot(sid, dir) {
    var idx = -1;
    for (var i = 0; i < state.shots.length; i++) {
      var id = state.shots[i].id !== undefined ? state.shots[i].id : state.shots[i].shotId;
      if (String(id) === String(sid)) { idx = i; break; }
    }
    if (idx < 0) return;
    var target = idx + dir;
    if (target < 0 || target >= state.shots.length) return;
    var arr = state.shots.slice();
    var tmp = arr[idx];
    arr[idx] = arr[target];
    arr[target] = tmp;
    arr.forEach(function (s, i) { s.shotNo = i + 1; });
    state.shots = arr;
    renderShots();
    reorder(arr);
  }

  function genVideo(sid) {
    api('/api/shots/' + encodeURIComponent(sid) + '/video-tasks', { method: 'POST', body: {} }).then(function () {
      toast('已提交视频生成任务');
      return loadShots();
    }).catch(function (err) {
      toast('提交失败：' + err.message, true);
    });
  }

  function submitAll() {
    var eid = state.episodeId;
    if (!eid) { toast('请先选择剧集', true); return; }
    if (!state.shots.length) { toast('本集暂无分镜', true); return; }
    if (!window.confirm('为本集全部 ' + state.shots.length + ' 个分镜提交视频生成任务？')) return;
    api('/api/episodes/' + encodeURIComponent(eid) + '/video-tasks/submit-all', { method: 'POST', body: {} }).then(function () {
      toast('已提交本集全部任务');
      return loadShots();
    }).catch(function (err) {
      toast('提交失败：' + err.message, true);
    });
  }

  function bindEvents() {
    $('projectSelect').addEventListener('change', function () {
      state.projectId = this.value;
      loadEpisodes(state.projectId);
    });
    $('episodeSelect').addEventListener('change', function () {
      state.episodeId = this.value;
      state.taskMap = {};
      loadShots();
    });
    $('addBtn').addEventListener('click', function () {
      if (!state.episodeId) { toast('请先选择剧集', true); return; }
      openForm(null);
    });
    $('submitAllBtn').addEventListener('click', submitAll);
    $('refreshBtn').addEventListener('click', function () {
      if (state.episodeId) loadShots();
      else toast('请先选择剧集', true);
    });
    $('cancelBtn').addEventListener('click', closeForm);
    $('shotForm').addEventListener('submit', saveShot);

    $('shotTbody').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-act]');
      if (!btn) return;
      var tr = btn.closest('tr');
      if (!tr) return;
      var sid = tr.getAttribute('data-sid');
      var act = btn.getAttribute('data-act');
      if (act === 'up') moveShot(sid, -1);
      else if (act === 'down') moveShot(sid, 1);
      else if (act === 'edit') {
        var shot = findShot(sid);
        if (shot) openForm(shot);
      }
      else if (act === 'del') deleteShot(sid);
      else if (act === 'gen') genVideo(sid);
    });
  }

  function init() {
    bindEvents();
    loadProjects();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
