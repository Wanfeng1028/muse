(function () {
  'use strict';

  var SHOT_SIZES = [
    { value: 'TE_XIE', label: '特写' },
    { value: 'JIN_JING', label: '近景' },
    { value: 'ZHONG_JING', label: '中景' },
    { value: 'QUAN_JING', label: '全景' },
    { value: 'YUAN_JING', label: '远景' }
  ];
  var CAMERA_MOVES = [
    { value: 'GU_DING', label: '固定机位' },
    { value: 'TUI', label: '推镜头' },
    { value: 'LA', label: '拉镜头' },
    { value: 'YAO', label: '摇镜头' },
    { value: 'YI', label: '移镜头' },
    { value: 'GEN', label: '跟镜头' },
    { value: 'SHENG_JIANG', label: '升降' }
  ];

  var state = {
    projects: [],
    episodes: [],
    shots: [],
    projectId: null,
    episodeId: null,
    taskStatusByShot: {},
    dragShotId: null,
    dragOverShotId: null,
    dragSide: null
  };

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtDuration(sec) {
    if (sec === null || sec === undefined || isNaN(sec)) return '--:--';
    var n = Math.max(0, Math.round(Number(sec)));
    var m = Math.floor(n / 60);
    var s = n % 60;
    return (m < 10 ? '0' + m : String(m)) + ':' + (s < 10 ? '0' + s : String(s));
  }

  function renderIcons() {
    if (window.lucide && window.lucide.createIcons) {
      window.lucide.createIcons();
    }
  }

  function toast(msg, kind) {
    var host = $('toastHost');
    if (!host) return;
    var el = document.createElement('div');
    el.className = 'toast-item ' + (kind === 'error' ? 'toast-error' : (kind === 'ok' ? 'toast-ok' : ''));
    el.textContent = msg;
    host.appendChild(el);
    setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 3200);
  }

  function apiGet(url) {
    return fetch(url, { headers: { 'Accept': 'application/json' } }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function apiSend(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('application/json') !== -1) return r.json();
      return null;
    });
  }

  function getQueryParam(name) {
    var m = new RegExp('[?&]' + name + '=([^&]+)').exec(window.location.search);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function updateUrl(episodeId) {
    try {
      var url = window.location.pathname + (episodeId ? '?episodeId=' + encodeURIComponent(episodeId) : '');
      window.history.replaceState(null, '', url);
    } catch (e) { /* ignore */ }
  }

  function latestTaskStatus(shotId) {
    var list = state.taskStatusByShot[shotId];
    if (!list || !list.length) return null;
    var latest = list[0];
    for (var i = 1; i < list.length; i++) {
      var a = list[i].createdAt || '';
      var b = latest.createdAt || '';
      if (a > b) latest = list[i];
    }
    return latest;
  }

  function statusBadgeHtml(shotId) {
    var t = latestTaskStatus(shotId);
    if (!t) {
      return '<span class="badge-status">草稿</span>';
    }
    var cls = 'badge-status';
    if (t.status) cls += ' badge-' + t.status;
    var label = t.statusLabel || t.status || '';
    return '<span class="' + cls + '">' + escapeHtml(label) + '</span>';
  }

  function fillSelect(select, items, valueKey, labelKey, placeholder) {
    select.innerHTML = '';
    if (!items.length) {
      var opt = document.createElement('option');
      opt.value = '';
      opt.textContent = placeholder || '无';
      select.appendChild(opt);
      select.disabled = true;
      return;
    }
    select.disabled = false;
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var o = document.createElement('option');
      o.value = String(it[valueKey]);
      o.textContent = it[labelKey] !== undefined && it[labelKey] !== null ? it[labelKey] : ('#' + it[valueKey]);
      select.appendChild(o);
    }
  }

  function loadProjects() {
    return apiGet('/api/projects').then(function (list) {
      state.projects = Array.isArray(list) ? list : [];
      fillSelect($('projectSelect'), state.projects, 'id', 'title', '无项目');
      if (state.projects.length) {
        state.projectId = state.projects[0].id;
        $('projectSelect').value = String(state.projectId);
      } else {
        state.projectId = null;
      }
    }).catch(function (err) {
      toast('加载项目失败：' + err.message, 'error');
      state.projects = [];
      state.projectId = null;
      fillSelect($('projectSelect'), [], 'id', 'name', '无项目');
    });
  }

  function loadEpisodes(preferredEpisodeId) {
    if (state.projectId === null || state.projectId === undefined) {
      state.episodes = [];
      state.episodeId = null;
      fillSelect($('episodeSelect'), [], 'id', 'title', '无剧集');
      return Promise.resolve();
    }
    return apiGet('/api/projects/' + state.projectId + '/episodes').then(function (list) {
      state.episodes = Array.isArray(list) ? list : [];
      fillSelect($('episodeSelect'), state.episodes, 'id', 'title', '无剧集');
      var chosen = null;
      if (preferredEpisodeId !== undefined && preferredEpisodeId !== null) {
        for (var i = 0; i < state.episodes.length; i++) {
          if (String(state.episodes[i].id) === String(preferredEpisodeId)) { chosen = state.episodes[i].id; break; }
        }
      }
      if (chosen === null && state.episodes.length) {
        chosen = state.episodes[0].id;
      }
      state.episodeId = chosen;
      if (chosen !== null) $('episodeSelect').value = String(chosen);
    }).catch(function (err) {
      toast('加载剧集失败：' + err.message, 'error');
      state.episodes = [];
      state.episodeId = null;
      fillSelect($('episodeSelect'), [], 'id', 'title', '无剧集');
    });
  }

  function loadShots() {
    if (state.episodeId === null || state.episodeId === undefined) {
      state.shots = [];
      state.taskStatusByShot = {};
      render();
      return Promise.resolve();
    }
    return apiGet('/api/episodes/' + state.episodeId + '/shots').then(function (list) {
      state.shots = Array.isArray(list) ? list : [];
      return Promise.all(state.shots.map(function (s) {
        return apiGet('/api/shots/' + s.id + '/video-tasks').then(function (tasks) {
          return { id: s.id, tasks: Array.isArray(tasks) ? tasks : [] };
        }).catch(function () {
          return { id: s.id, tasks: [] };
        });
      }));
    }).then(function (results) {
      state.taskStatusByShot = {};
      for (var i = 0; i < results.length; i++) {
        state.taskStatusByShot[results[i].id] = results[i].tasks;
      }
      render();
    }).catch(function (err) {
      toast('加载分镜失败：' + err.message, 'error');
      state.shots = [];
      state.taskStatusByShot = {};
      render();
    });
  }

  function render() {
    renderTimeline();
    renderGrid();
    renderIcons();
  }

  function renderTimeline() {
    var host = $('timelineStrip');
    if (!host) return;
    if (!state.shots.length) {
      host.innerHTML = '<div class="timeline-empty">暂无分镜节点</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < state.shots.length; i++) {
      var s = state.shots[i];
      var grow = (s.durationSeconds !== null && s.durationSeconds !== undefined && !isNaN(s.durationSeconds) && Number(s.durationSeconds) > 0)
        ? Number(s.durationSeconds) : 1;
      html += '<div class="timeline-node" data-shot-id="' + escapeHtml(s.id) + '" style="flex-grow:' + grow + ';">' +
        '<span class="tn-no">#' + escapeHtml(s.shotNo) + '</span>' +
        '<span class="tn-dur">' + escapeHtml(fmtDuration(s.durationSeconds)) + '</span>' +
        '</div>';
    }
    host.innerHTML = html;
    var nodes = host.querySelectorAll('.timeline-node');
    for (var j = 0; j < nodes.length; j++) {
      nodes[j].addEventListener('click', onTimelineClick);
    }
  }

  function onTimelineClick() {
    var id = this.getAttribute('data-shot-id');
    var card = document.querySelector('.shot-card[data-shot-id="' + id + '"]');
    if (!card) return;
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    card.classList.add('flash');
    setTimeout(function () {
      card.classList.remove('flash');
    }, 900);
  }

  function renderGrid() {
    var host = $('gridHost');
    if (!host) return;

    if (!state.projects.length) {
      host.innerHTML = '<div class="empty-block">还没有项目，请先在项目页创建。</div>';
      return;
    }
    if (state.episodeId === null || state.episodeId === undefined) {
      host.innerHTML = '<div class="empty-block">当前项目还没有剧集，请先创建剧集。</div>';
      return;
    }
    if (!state.shots.length) {
      host.innerHTML = '<div class="empty-block">这一集还没有分镜，<a href="/storyboard.html">去分镜板添加</a>。</div>';
      return;
    }

    var html = '<div class="shot-grid">';
    for (var i = 0; i < state.shots.length; i++) {
      var s = state.shots[i];
      var sizeLabel = s.shotSizeLabel !== null && s.shotSizeLabel !== undefined && s.shotSizeLabel !== '' ? s.shotSizeLabel : '—';
      var moveLabel = s.cameraMoveLabel !== null && s.cameraMoveLabel !== undefined && s.cameraMoveLabel !== '' ? s.cameraMoveLabel : '—';
      var durLabel = s.durationSeconds !== null && s.durationSeconds !== undefined ? fmtDuration(s.durationSeconds) : '—';
      var desc = (s.description !== null && s.description !== undefined && String(s.description).trim() !== '') ? String(s.description) : '—';
      var dialogueHtml = '';
      if (s.dialogue !== null && s.dialogue !== undefined && String(s.dialogue).trim() !== '') {
        dialogueHtml = '<div class="shot-dialogue"><span class="lbl">台词</span>' + escapeHtml(s.dialogue) + '</div>';
      }
      html += '<div class="shot-card" data-shot-id="' + escapeHtml(s.id) + '" draggable="false">' +
        '<div class="shot-card-head">' +
          '<span class="drag-handle" data-drag-handle="' + escapeHtml(s.id) + '" title="拖动排序"><i data-lucide="grip-vertical"></i></span>' +
          '<span class="shot-no">#' + escapeHtml(s.shotNo) + '</span>' +
          '<span class="shot-spacer"></span>' +
          statusBadgeHtml(s.id) +
        '</div>' +
        '<div class="shot-desc">' + escapeHtml(desc) + '</div>' +
        dialogueHtml +
        '<div class="shot-meta">' + escapeHtml(sizeLabel) + ' · ' + escapeHtml(moveLabel) + ' · ' + escapeHtml(durLabel) + '</div>' +
        '</div>';
    }
    html += '</div>';
    host.innerHTML = html;

    var cards = host.querySelectorAll('.shot-card');
    for (var k = 0; k < cards.length; k++) {
      var card = cards[k];
      card.addEventListener('click', onCardClick);
      card.addEventListener('dragstart', onCardDragStart);
      card.addEventListener('dragend', onCardDragEnd);
      card.addEventListener('dragover', onCardDragOver);
      card.addEventListener('dragleave', onCardDragLeave);
      card.addEventListener('drop', onCardDrop);
    }
    var handles = host.querySelectorAll('.drag-handle');
    for (var h = 0; h < handles.length; h++) {
      handles[h].addEventListener('mousedown', onHandleMouseDown);
    }
  }

  function onHandleMouseDown(e) {
    var card = this.closest ? this.closest('.shot-card') : null;
    if (card) card.setAttribute('draggable', 'true');
    e.stopPropagation();
  }

  function onCardClick(e) {
    var card = e.currentTarget;
    if (e.target && e.target.closest && e.target.closest('.drag-handle')) return;
    var id = card.getAttribute('data-shot-id');
    openEditor(id);
  }

  function onCardDragStart(e) {
    var card = e.currentTarget;
    state.dragShotId = card.getAttribute('data-shot-id');
    card.classList.add('dragging');
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', state.dragShotId); } catch (err) { /* ignore */ }
    }
  }

  function onCardDragEnd(e) {
    var card = e.currentTarget;
    card.classList.remove('dragging');
    card.setAttribute('draggable', 'false');
    clearInsertLines();
    state.dragShotId = null;
    state.dragOverShotId = null;
    state.dragSide = null;
  }

  function onCardDragOver(e) {
    if (!state.dragShotId) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    var card = e.currentTarget;
    var targetId = card.getAttribute('data-shot-id');
    if (targetId === state.dragShotId) {
      clearInsertLines();
      return;
    }
    var rect = card.getBoundingClientRect();
    var side = (e.clientX - rect.left) < rect.width / 2 ? 'left' : 'right';
    state.dragOverShotId = targetId;
    state.dragSide = side;
    showInsertLine(card, side);
  }

  function onCardDragLeave(e) {
    var card = e.currentTarget;
    var related = e.relatedTarget;
    if (related && card.contains(related)) return;
    var line = card.querySelector('.insert-line');
    if (line && line.parentNode) line.parentNode.removeChild(line);
  }

  function onCardDrop(e) {
    e.preventDefault();
    if (!state.dragShotId) return;
    var card = e.currentTarget;
    var targetId = card.getAttribute('data-shot-id');
    var side = state.dragSide;
    clearInsertLines();
    if (!targetId || targetId === state.dragShotId) return;
    performReorder(state.dragShotId, targetId, side);
  }

  function showInsertLine(card, side) {
    var existing = card.querySelectorAll('.insert-line');
    for (var i = 0; i < existing.length; i++) {
      if (existing[i].parentNode) existing[i].parentNode.removeChild(existing[i]);
    }
    var line = document.createElement('div');
    line.className = 'insert-line ' + side;
    card.appendChild(line);
  }

  function clearInsertLines() {
    var lines = document.querySelectorAll('.insert-line');
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].parentNode) lines[i].parentNode.removeChild(lines[i]);
    }
  }

  function performReorder(dragId, targetId, side) {
    var oldOrder = state.shots.slice();
    var fromIdx = -1, toIdx = -1;
    for (var i = 0; i < state.shots.length; i++) {
      if (String(state.shots[i].id) === String(dragId)) fromIdx = i;
      if (String(state.shots[i].id) === String(targetId)) toIdx = i;
    }
    if (fromIdx < 0 || toIdx < 0) return;

    var moved = state.shots.splice(fromIdx, 1)[0];
    if (fromIdx < toIdx) toIdx--;
    var insertIdx = side === 'right' ? toIdx + 1 : toIdx;
    state.shots.splice(insertIdx, 0, moved);

    render();

    var ids = state.shots.map(function (s) { return s.id; });
    apiSend('POST', '/api/episodes/' + state.episodeId + '/shots/reorder', { shotIds: ids })
      .then(function (list) {
        if (Array.isArray(list)) {
          state.shots = list;
          render();
        }
        toast('顺序已更新', 'ok');
      })
      .catch(function (err) {
        state.shots = oldOrder;
        render();
        toast('排序失败：' + err.message, 'error');
      });
  }

  function openEditor(shotId) {
    var shot = null;
    for (var i = 0; i < state.shots.length; i++) {
      if (String(state.shots[i].id) === String(shotId)) { shot = state.shots[i]; break; }
    }
    if (!shot) return;

    var sizeOpts = '<option value="">—</option>';
    for (var a = 0; a < SHOT_SIZES.length; a++) {
      var sel = shot.shotSize === SHOT_SIZES[a].value ? ' selected' : '';
      sizeOpts += '<option value="' + SHOT_SIZES[a].value + '"' + sel + '>' + SHOT_SIZES[a].label + '</option>';
    }
    var moveOpts = '<option value="">—</option>';
    for (var b = 0; b < CAMERA_MOVES.length; b++) {
      var sel2 = shot.cameraMove === CAMERA_MOVES[b].value ? ' selected' : '';
      moveOpts += '<option value="' + CAMERA_MOVES[b].value + '"' + sel2 + '>' + CAMERA_MOVES[b].label + '</option>';
    }

    var durVal = (shot.durationSeconds !== null && shot.durationSeconds !== undefined) ? String(shot.durationSeconds) : '';
    var descVal = shot.description !== null && shot.description !== undefined ? String(shot.description) : '';
    var dlgVal = shot.dialogue !== null && shot.dialogue !== undefined ? String(shot.dialogue) : '';
    var vpVal = shot.videoPrompt !== null && shot.videoPrompt !== undefined ? String(shot.videoPrompt) : '';

    var html = '' +
      '<div class="modal-backdrop" id="editorBackdrop">' +
        '<div class="modal-box">' +
          '<h2>编辑镜头 #' + escapeHtml(shot.shotNo) + '</h2>' +
          '<div class="field-row">' +
            '<label>画面描述</label>' +
            '<textarea id="editDescription">' + escapeHtml(descVal) + '</textarea>' +
          '</div>' +
          '<div class="field-row video-prompt">' +
            '<label>视频 Prompt</label>' +
            '<textarea id="editVideoPrompt">' + escapeHtml(vpVal) + '</textarea>' +
          '</div>' +
          '<div class="field-row">' +
            '<label>台词</label>' +
            '<textarea id="editDialogue">' + escapeHtml(dlgVal) + '</textarea>' +
          '</div>' +
          '<div class="field-grid-3">' +
            '<div class="field-row">' +
              '<label>景别</label>' +
              '<select id="editShotSize">' + sizeOpts + '</select>' +
            '</div>' +
            '<div class="field-row">' +
              '<label>运镜</label>' +
              '<select id="editCameraMove">' + moveOpts + '</select>' +
            '</div>' +
            '<div class="field-row">' +
              '<label>时长（秒）</label>' +
              '<input type="number" min="0" step="1" id="editDuration" value="' + escapeHtml(durVal) + '">' +
            '</div>' +
          '</div>' +
          '<div class="field-inline-err" id="editDurationErr"></div>' +
          '<div class="form-error" id="editFormErr"></div>' +
          '<div class="modal-actions">' +
            '<button type="button" class="btn btn-outline-secondary btn-sm" id="editCancel">取消</button>' +
            '<button type="button" class="btn btn-primary btn-sm" id="editSave">保存</button>' +
          '</div>' +
        '</div>' +
      '</div>';

    var host = $('modalHost');
    host.innerHTML = html;
    renderIcons();

    var backdrop = $('editorBackdrop');
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeEditor();
    });
    $('editCancel').addEventListener('click', closeEditor);
    $('editSave').addEventListener('click', function () { saveEditor(shot); });
  }

  function closeEditor() {
    $('modalHost').innerHTML = '';
  }

  function saveEditor(shot) {
    var errEl = $('editFormErr');
    var durErrEl = $('editDurationErr');
    errEl.textContent = '';
    durErrEl.textContent = '';

    var durRaw = $('editDuration').value;
    var dur = null;
    if (durRaw !== null && String(durRaw).trim() !== '') {
      var n = Number(durRaw);
      if (isNaN(n) || n < 0 || Math.floor(n) !== n) {
        durErrEl.textContent = '时长必须是不小于 0 的整数';
        return;
      }
      dur = n;
    }

    var payload = {
      shotNo: shot.shotNo,
      shotSize: $('editShotSize').value || null,
      cameraMove: $('editCameraMove').value || null,
      description: $('editDescription').value || null,
      durationSeconds: dur,
      dialogue: $('editDialogue').value || null,
      videoPrompt: $('editVideoPrompt').value || null
    };

    apiSend('PUT', '/api/shots/' + shot.id, payload).then(function (updated) {
      if (updated && typeof updated === 'object') {
        for (var i = 0; i < state.shots.length; i++) {
          if (String(state.shots[i].id) === String(shot.id)) {
            state.shots[i] = updated;
            break;
          }
        }
      }
      closeEditor();
      render();
      toast('已保存', 'ok');
    }).catch(function (err) {
      errEl.textContent = '保存失败：' + err.message;
    });
  }

  function addShot() {
    if (state.episodeId === null || state.episodeId === undefined) {
      toast('请先选择剧集', 'error');
      return;
    }
    var maxNo = 0;
    for (var i = 0; i < state.shots.length; i++) {
      var n = Number(state.shots[i].shotNo);
      if (!isNaN(n) && n > maxNo) maxNo = n;
    }
    var payload = {
      shotNo: maxNo + 1,
      shotSize: null,
      cameraMove: null,
      description: null,
      durationSeconds: null,
      dialogue: null,
      videoPrompt: null
    };
    apiSend('POST', '/api/episodes/' + state.episodeId + '/shots', payload).then(function (created) {
      if (created && typeof created === 'object') {
        state.shots.push(created);
        state.taskStatusByShot[created.id] = [];
      }
      render();
      toast('已新增镜头 #' + payload.shotNo, 'ok');
    }).catch(function (err) {
      toast('新增失败：' + err.message, 'error');
    });
  }

  function bindEvents() {
    $('projectSelect').addEventListener('change', function () {
      state.projectId = this.value ? Number(this.value) : null;
      loadEpisodes().then(function () {
        updateUrl(state.episodeId);
        return loadShots();
      });
    });

    $('episodeSelect').addEventListener('change', function () {
      state.episodeId = this.value ? Number(this.value) : null;
      updateUrl(state.episodeId);
      loadShots();
    });

    $('btnRefresh').addEventListener('click', function () {
      loadShots();
    });

    $('btnAddShot').addEventListener('click', addShot);
  }

  function init() {
    bindEvents();
    var preferred = getQueryParam('episodeId');
    loadProjects().then(function () {
      return loadEpisodes(preferred);
    }).then(function () {
      updateUrl(state.episodeId);
      return loadShots();
    }).then(function () {
      renderIcons();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
