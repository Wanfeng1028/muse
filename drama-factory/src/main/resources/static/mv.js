/* AI MV 前端逻辑 */
(function () {
  'use strict';

  var songId = null;
  var pollTimer = null;

  function $(id) { return document.getElementById(id); }

  function chipValue(groupId) {
    var on = document.querySelector('#' + groupId + ' .chip.is-on');
    return on ? on.dataset.value : '';
  }

  document.querySelectorAll('.chips').forEach(function (g) {
    g.addEventListener('click', function (e) {
      var b = e.target.closest('.chip');
      if (!b) return;
      g.querySelectorAll('.chip').forEach(function (c) { c.classList.remove('is-on'); });
      b.classList.add('is-on');
    });
  });

  function goStep(n) {
    document.querySelectorAll('#steps .mv-step').forEach(function (li) {
      var s = parseInt(li.dataset.step, 10);
      li.classList.toggle('is-current', s === n);
      li.classList.toggle('is-done', s < n);
    });
    document.querySelectorAll('[data-panel]').forEach(function (p) {
      p.classList.toggle('is-hidden', parseInt(p.dataset.panel, 10) !== n);
    });
    window.scrollTo(0, 0);
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    return fetch(path, opts).then(function (r) {
      if (!r.ok) return r.text().then(function (t) { throw new Error(t || ('HTTP ' + r.status)); });
      var ct = r.headers.get('content-type') || '';
      return ct.indexOf('json') >= 0 ? r.json() : r.text();
    });
  }

  /* ---- 步骤1：写词 ---- */
  $('btnLyrics').addEventListener('click', function () {
    var theme = $('themeInput').value.trim();
    if (!theme) { $('lyricsNote').textContent = '请先输入主题'; return; }
    var btn = $('btnLyrics');
    btn.disabled = true;
    $('lyricsNote').textContent = '正在生成…';
    api('/api/mv', {
      method: 'POST',
      body: JSON.stringify({ theme: theme, mood: chipValue('moodGroup'), style: chipValue('styleGroup') })
    }).then(function (created) {
      songId = created.id;
      return api('/api/mv/' + songId + '/lyrics', { method: 'POST' });
    }).then(function (res) {
      renderLyrics(res.lyrics);
      $('lyricsNote').textContent = '';
      goStep(2);
    }).catch(function (e) {
      $('lyricsNote').textContent = '生成失败：' + e.message;
    }).finally(function () { btn.disabled = false; });
  });

  function renderLyrics(lyrics) {
    $('lyricsTitle').textContent = lyrics.title || '未命名';
    var box = $('lyricsSections');
    box.innerHTML = '';
    (lyrics.sections || []).forEach(function (s) {
      var card = document.createElement('div');
      card.className = 'lyric-card';
      card.innerHTML =
        '<div class="head"><span class="sec-name"></span>' +
        '<span class="mood-tag"></span><span class="dur"></span></div>' +
        '<textarea rows="3"></textarea>';
      card.querySelector('.sec-name').textContent = s.name || '';
      card.querySelector('.mood-tag').textContent = s.mood || '';
      card.querySelector('.dur').textContent = '约' + (s.estSeconds || 0) + '秒';
      card.querySelector('textarea').value = s.lyrics || '';
      box.appendChild(card);
    });
  }

  /* ---- 步骤2：作曲 ---- */
  $('btnCompose').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnCompose');
    btn.disabled = true;
    $('composeNote').textContent = '作曲中，可能需要几分钟…';
    api('/api/mv/' + songId + '/compose', { method: 'POST', body: JSON.stringify({}) })
      .then(function (res) {
        var audioUrl = '/api/mv/' + songId + '/audio';
        $('audioEl').src = audioUrl;
        $('audioMeta').textContent = res.durationMs
          ? '时长约 ' + Math.round(res.durationMs / 1000) + ' 秒' : '';
        $('audioBar').classList.remove('is-hidden');
        $('composeNote').textContent = '';
      })
      .catch(function (e) { $('composeNote').textContent = '作曲失败：' + e.message; })
      .finally(function () { btn.disabled = false; });
  });

  $('btnToStoryboard').addEventListener('click', function () { goStep(3); });

  /* ---- 步骤3：分镜 ---- */
  $('btnStoryboard').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnStoryboard');
    btn.disabled = true;
    api('/api/mv/' + songId + '/storyboard', { method: 'POST' })
      .then(function (res) {
        var box = $('storyboardList');
        box.innerHTML = '';
        (res.sections || []).forEach(function (s) {
          var card = document.createElement('div');
          card.className = 'sb-card';
          card.innerHTML = '<div class="sec-name"></div><textarea rows="3"></textarea><div class="cam"></div>';
          card.querySelector('.sec-name').textContent = s.name || '';
          card.querySelector('textarea').value = s.visualPrompt || '';
          card.querySelector('.cam').textContent = '运镜：' + (s.camera || '—');
          box.appendChild(card);
        });
        $('btnToRender').classList.remove('is-hidden');
      })
      .catch(function (e) { alert('分镜生成失败：' + e.message); })
      .finally(function () { btn.disabled = false; });
  });

  $('btnToRender').addEventListener('click', function () { goStep(4); });

  /* ---- 步骤4：渲染 ---- */
  $('btnRender').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnRender');
    btn.disabled = true;
    $('progressText').textContent = '渲染中…';
    api('/api/mv/' + songId + '/render', {
      method: 'POST',
      body: JSON.stringify({ dryRun: $('dryRunToggle').checked })
    }).then(function () {
      pollStatus();
    }).catch(function (e) {
      $('progressText').textContent = '渲染失败：' + e.message;
      btn.disabled = false;
    });
  });

  function pollStatus() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(function () {
      api('/api/mv/' + songId + '/status').then(function (st) {
        renderAgentList(st.steps || []);
        var done = (st.steps || []).filter(function (s) { return s.status === 'SUCCEEDED'; }).length;
        var total = (st.steps || []).length || 6;
        var pct = Math.round(done / total * 100);
        $('progressFill').style.width = pct + '%';
        $('progressPct').textContent = pct + '%';
        if (st.status === 'RENDERED') {
          clearInterval(pollTimer);
          $('progressText').textContent = '渲染完成';
          var vurl = '/api/mv/' + songId + '/video';
          $('videoEl').src = vurl;
          $('btnDownload').href = vurl;
          goStep(5);
          $('btnRender').disabled = false;
        } else if (st.status === 'FAILED') {
          clearInterval(pollTimer);
          $('progressText').textContent = '渲染失败，请重试';
          $('btnRender').disabled = false;
        } else {
          $('progressText').textContent = '渲染中…';
        }
      }).catch(function () { /* 轮询容错 */ });
    }, 3000);
  }

  function renderAgentList(steps) {
    var box = $('agentList');
    box.innerHTML = '';
    var names = { LYRICS: '作词', COMPOSE: '作曲', BOARD: '分镜', VIDEO: '视频生成', EDIT: '剪辑', QC: '质检' };
    steps.forEach(function (s) {
      var li = document.createElement('li');
      var dot = s.status === 'SUCCEEDED' ? '✓' : (s.status === 'FAILED' ? '✗' : '…');
      li.innerHTML = '<span></span><span class="st"></span>';
      li.children[0].textContent = dot + ' ' + (names[s.agentType] || s.agentType);
      li.children[1].textContent = s.status || '';
      box.appendChild(li);
    });
  }

  /* ---- 步骤5：再做一支 ---- */
  $('btnAgain').addEventListener('click', function () {
    songId = null;
    if (pollTimer) clearInterval(pollTimer);
    $('themeInput').value = '';
    $('lyricsSections').innerHTML = '';
    $('storyboardList').innerHTML = '';
    $('audioBar').classList.add('is-hidden');
    $('btnToRender').classList.add('is-hidden');
    $('progressFill').style.width = '0%';
    $('progressPct').textContent = '0%';
    $('progressText').textContent = '未开始';
    $('agentList').innerHTML = '';
    $('videoEl').removeAttribute('src');
    goStep(1);
  });
})();
