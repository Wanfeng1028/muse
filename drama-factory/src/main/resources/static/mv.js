/* AI MV 前端逻辑 */
(function () {
  'use strict';

  var PAGE_I18N = {
    'mv.docTitle': { 'zh-CN': 'AI MV · drama-factory', en: 'AI MV · drama-factory' },
    'mv.tagline': { 'zh-CN': '一句话主题，生成完整音乐短片。', en: 'One line of theme. A complete music video.' },
    'mv.stepLyrics': { 'zh-CN': '写词', en: 'Lyrics' },
    'mv.stepCompose': { 'zh-CN': '作曲', en: 'Composition' },
    'mv.stepStoryboard': { 'zh-CN': '分镜', en: 'Shot' },
    'mv.stepRender': { 'zh-CN': '渲染', en: 'Render' },
    'mv.stepFinal': { 'zh-CN': '成片', en: 'Final Cut' },
    'mv.startTitle': { 'zh-CN': '开始', en: 'Get Started' },
    'mv.modeAiTitle': { 'zh-CN': 'AI 创作歌曲', en: 'AI writes the song' },
    'mv.modeAiDesc': { 'zh-CN': '给主题，AI 作词作曲，一条龙生成', en: 'Give a theme. AI writes lyrics and music in one pass.' },
    'mv.modeImportTitle': { 'zh-CN': '导入已有音频', en: 'Import existing audio' },
    'mv.modeImportDesc': { 'zh-CN': '有现成的歌，直接上传跳过作词作曲', en: 'You already have the song — upload it and skip lyrics and composition.' },
    'mv.aiHint': { 'zh-CN': '给出主题、情绪和曲风，生成分段歌词。生成后可以逐段修改。', en: 'Pick a theme, mood, and style to get sectioned lyrics. Edit each section after.' },
    'mv.themeLabel': { 'zh-CN': '主题', en: 'Theme' },
    'mv.themePlaceholder': { 'zh-CN': '例如：末班地铁上的重逢', en: 'e.g. Meeting again on the last train' },
    'mv.moodLabel': { 'zh-CN': '情绪', en: 'Mood' },
    'mv.moodUpbeat': { 'zh-CN': '欢快', en: 'Upbeat' },
    'mv.moodLyrical': { 'zh-CN': '抒情', en: 'Lyrical' },
    'mv.moodPassionate': { 'zh-CN': '激昂', en: 'Passionate' },
    'mv.moodCalm': { 'zh-CN': '舒缓', en: 'Calm' },
    'mv.moodFiery': { 'zh-CN': '热血', en: 'Fiery' },
    'mv.styleLabel': { 'zh-CN': '曲风', en: 'Style' },
    'mv.stylePop': { 'zh-CN': '流行', en: 'Pop' },
    'mv.styleFolk': { 'zh-CN': '民谣', en: 'Folk' },
    'mv.styleRock': { 'zh-CN': '摇滚', en: 'Rock' },
    'mv.styleElectronic': { 'zh-CN': '电子', en: 'Electronic' },
    'mv.styleClassical': { 'zh-CN': '古风', en: 'Classical' },
    'mv.generateLyrics': { 'zh-CN': '生成歌词', en: 'Generate lyrics' },
    'mv.importHint': { 'zh-CN': '上传音频文件（mp3 / wav / m4a，最大 100MB），自动进入资产库。歌词可选：填了按歌词做字幕时间轴，不填按纯音乐分镜。', en: 'Upload audio (mp3 / wav / m4a, up to 100MB) — it lands in your asset library. Lyrics are optional: with them, subtitles follow the timeline; without them, the shots run on music alone.' },
    'mv.importTitleLabel': { 'zh-CN': '歌曲标题', en: 'Song title' },
    'mv.importTitlePlaceholder': { 'zh-CN': '例如：归途的光', en: 'e.g. Light on the Way Home' },
    'mv.importFileLabel': { 'zh-CN': '音频文件', en: 'Audio file' },
    'mv.importLyricsLabel': { 'zh-CN': '歌词（可选）', en: 'Lyrics (optional)' },
    'mv.importLyricsPlaceholder': { 'zh-CN': '粘贴歌词，空行分段；不填则按纯音乐分镜', en: 'Paste lyrics, blank lines split sections. Leave empty to shot on music alone.' },
    'mv.uploadImport': { 'zh-CN': '上传并导入', en: 'Upload and import' },
    'mv.gotoStoryboard': { 'zh-CN': '进入分镜', en: 'Go to shots' },
    'mv.composeTitle': { 'zh-CN': '作曲', en: 'Composition' },
    'mv.composeHint': { 'zh-CN': '歌词确认后开始作曲。试听满意再进入分镜。', en: 'Compose once the lyrics look right. Listen, then move on to shots.' },
    'mv.untitled': { 'zh-CN': '未命名', en: 'Untitled' },
    'mv.startCompose': { 'zh-CN': '开始作曲', en: 'Start composing' },
    'mv.storyboardTitle': { 'zh-CN': '分镜', en: 'Shot' },
    'mv.storyboardHint': { 'zh-CN': '每行歌词对应一个镜头，可编辑画面描述。', en: 'Each lyric line gets a shot. Edit the visual description as you like.' },
    'mv.generateStoryboard': { 'zh-CN': '生成分镜', en: 'Generate shots' },
    'mv.gotoRender': { 'zh-CN': '进入渲染', en: 'Go to render' },
    'mv.renderTitle': { 'zh-CN': '渲染', en: 'Render' },
    'mv.renderHint': { 'zh-CN': '按分镜逐段合成视频。测试时可打开短片段模式。', en: 'Each shot is composited into video. Turn on short-clip mode for a quick test.' },
    'mv.startRender': { 'zh-CN': '开始渲染', en: 'Start render' },
    'mv.dryRun': { 'zh-CN': '短片段模式', en: 'Short-clip mode' },
    'mv.notStarted': { 'zh-CN': '未开始', en: 'Not started' },
    'mv.finalTitle': { 'zh-CN': '成片', en: 'Final Cut' },
    'mv.finalHint': { 'zh-CN': '渲染完成后可直接播放或下载。', en: 'Once rendering finishes, play it here or download it.' },
    'mv.downloadVideo': { 'zh-CN': '下载视频', en: 'Download video' },
    'mv.again': { 'zh-CN': '再做一支', en: 'Make another' },
    'mv.skippedTitle': { 'zh-CN': '已跳过（导入音频）', en: 'Skipped (audio imported)' },
    'mv.needTheme': { 'zh-CN': '请先输入主题', en: 'Enter a theme first' },
    'mv.generatingLyrics': { 'zh-CN': '正在生成…', en: 'Generating…' },
    'mv.lyricsParseFail': { 'zh-CN': '歌词解析失败', en: 'Could not parse lyrics' },
    'mv.lyricsFail': { 'zh-CN': '生成失败：', en: 'Generation failed: ' },
    'mv.aboutSeconds': { 'zh-CN': '约', en: 'about ' },
    'mv.seconds': { 'zh-CN': '秒', en: 's' },
    'mv.composing': { 'zh-CN': '作曲中，可能需要几分钟…', en: 'Composing — this can take a few minutes…' },
    'mv.durationAbout': { 'zh-CN': '时长约 ', en: 'Duration about ' },
    'mv.durationSec': { 'zh-CN': ' 秒', en: 's' },
    'mv.composeFail': { 'zh-CN': '作曲失败：', en: 'Composition failed: ' },
    'mv.timeline': { 'zh-CN': '时间轴', en: 'Timeline' },
    'mv.totalLen': { 'zh-CN': '总长 ', en: 'Total ' },
    'mv.needTitle': { 'zh-CN': '请填写歌曲标题', en: 'Enter a song title' },
    'mv.needFile': { 'zh-CN': '请选择音频文件', en: 'Pick an audio file' },
    'mv.extOnly': { 'zh-CN': '仅支持 mp3 / wav / m4a', en: 'Only mp3 / wav / m4a are supported' },
    'mv.sizeLimit': { 'zh-CN': '文件超过 100MB 上限', en: 'File is over the 100MB limit' },
    'mv.uploading': { 'zh-CN': '上传中…', en: 'Uploading…' },
    'mv.importedSkipped': { 'zh-CN': '已跳过作词作曲', en: 'Lyrics and composition skipped' },
    'mv.durationSkipped': { 'zh-CN': '时长约 ', en: 'Duration about ' },
    'mv.durationSkippedTail': { 'zh-CN': ' 秒，已跳过作词作曲', en: 's, lyrics and composition skipped' },
    'mv.importFail': { 'zh-CN': '导入失败：', en: 'Import failed: ' },
    'mv.netError': { 'zh-CN': '网络错误', en: 'network error' },
    'mv.storyboardFail': { 'zh-CN': '分镜生成失败：', en: 'Shot generation failed: ' },
    'mv.rendering': { 'zh-CN': '渲染中…', en: 'Rendering…' },
    'mv.renderFail': { 'zh-CN': '渲染失败：', en: 'Render failed: ' },
    'mv.renderDone': { 'zh-CN': '渲染完成', en: 'Render complete' },
    'mv.renderFailedRetry': { 'zh-CN': '渲染失败，请重试', en: 'Render failed — try again' },
    'mv.shotPrefix': { 'zh-CN': '第', en: 'Shot ' },
    'mv.shotSuffix': { 'zh-CN': '镜', en: '' },
    'mv.shotDurationPre': { 'zh-CN': '（共', en: '(total ' },
    'mv.shotDurationPost': { 'zh-CN': '秒）', en: 's)' },
    'mv.agentLyrics': { 'zh-CN': '作词', en: 'Lyrics' },
    'mv.agentCompose': { 'zh-CN': '作曲', en: 'Composition' },
    'mv.agentBoard': { 'zh-CN': '分镜', en: 'Shot' },
    'mv.agentVideo': { 'zh-CN': '视频生成', en: 'Video generation' },
    'mv.agentEdit': { 'zh-CN': '剪辑', en: 'Editing' },
    'mv.agentQc': { 'zh-CN': '质检', en: 'QC' },
    'mv.statusSucceeded': { 'zh-CN': '已完成', en: 'Done' },
    'mv.statusFailed': { 'zh-CN': '失败', en: 'Failed' },
    'mv.statusSkipped': { 'zh-CN': '已跳过', en: 'Skipped' },
    'mv.statusRunning': { 'zh-CN': '进行中', en: 'Running' },
    'mv.statusPending': { 'zh-CN': '待执行', en: 'Pending' }
  };

  if (window.DFI18N) DFI18N.register(PAGE_I18N);

  function _t(key, zh) {
    if (window.DFI18N) {
      var s = DFI18N.tr(key);
      if (s !== key) return s;
    }
    return zh;
  }

  var songId = null;
  var pollTimer = null;

  function $(id) { return document.getElementById(id); }

  function fmtT(ms) {
    var total = Math.max(0, Math.round((ms || 0) / 1000));
    var m = Math.floor(total / 60);
    var s = total % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

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

  /* ---- 模式切换：AI 创作 / 导入音频 ---- */
  var importMode = false;
  $('modeTabs').addEventListener('click', function (e) {
    var b = e.target.closest('.mode-tab');
    if (!b) return;
    document.querySelectorAll('#modeTabs .mode-tab').forEach(function (t) { t.classList.remove('is-on'); });
    b.classList.add('is-on');
    importMode = b.dataset.mode === 'import';
    $('aiModePanel').classList.toggle('is-hidden', importMode);
    $('importModePanel').classList.toggle('is-hidden', !importMode);
  });

  function markStepsSkipped() {
    document.querySelectorAll('#steps .mv-step').forEach(function (li) {
      var s = parseInt(li.dataset.step, 10);
      if (s === 1 || s === 2) {
        li.classList.add('is-skipped');
        li.title = _t('mv.skippedTitle', '已跳过（导入音频）');
      }
    });
  }

  function clearStepsSkipped() {
    document.querySelectorAll('#steps .mv-step').forEach(function (li) {
      li.classList.remove('is-skipped');
      li.removeAttribute('title');
    });
  }

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
    if (!theme) { $('lyricsNote').textContent = _t('mv.needTheme', '请先输入主题'); return; }
    var btn = $('btnLyrics');
    btn.disabled = true;
    $('lyricsNote').textContent = _t('mv.generatingLyrics', '正在生成…');
    api('/api/mv', {
      method: 'POST',
      body: JSON.stringify({ theme: theme, mood: chipValue('moodGroup'), style: chipValue('styleGroup') })
    }).then(function (created) {
      songId = created.id;
      return api('/api/mv/' + songId + '/lyrics', { method: 'POST' });
    }).then(function (res) {
      var parsed = null;
      try {
        parsed = JSON.parse(res.lyricsJson);
      } catch (e) {
        $('lyricsNote').textContent = _t('mv.lyricsParseFail', '歌词解析失败');
        return;
      }
      renderLyrics(parsed);
      $('lyricsNote').textContent = '';
      goStep(2);
    }).catch(function (e) {
      $('lyricsNote').textContent = _t('mv.lyricsFail', '生成失败：') + e.message;
    }).finally(function () { btn.disabled = false; });
  });

  function renderLyrics(lyrics) {
    $('lyricsTitle').textContent = lyrics.title || _t('mv.untitled', '未命名');
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
      card.querySelector('.dur').textContent = _t('mv.aboutSeconds', '约') + (s.estSeconds || 0) + _t('mv.seconds', '秒');
      card.querySelector('textarea').value = s.lyrics || '';
      box.appendChild(card);
    });
    if (window.DFI18N) DFI18N.applyI18n(box);
  }

  /* ---- 步骤2：作曲 ---- */
  $('btnCompose').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnCompose');
    btn.disabled = true;
    $('composeNote').textContent = _t('mv.composing', '作曲中，可能需要几分钟…');
    api('/api/mv/' + songId + '/compose', { method: 'POST', body: JSON.stringify({}) })
      .then(function (res) {
        var audioUrl = res.audioUrl || '';
        $('audioEl').src = audioUrl;
        $('audioMeta').textContent = res.durationMs
          ? _t('mv.durationAbout', '时长约 ') + Math.round(res.durationMs / 1000) + _t('mv.durationSec', ' 秒') : '';
        $('audioBar').classList.remove('is-hidden');
        $('composeNote').textContent = '';
        return api('/api/mv/' + songId).then(function (detail) {
          renderTimeline(detail);
        }).catch(function () { /* 时间轴拉取失败不影响主流程 */ });
      })
      .catch(function (e) { $('composeNote').textContent = _t('mv.composeFail', '作曲失败：') + e.message; })
      .finally(function () { btn.disabled = false; });
  });

  function renderTimeline(detail) {
    var box = $('timelineBox');
    box.innerHTML = '';
    var tl = null;
    if (detail && detail.timelineJson) {
      try { tl = JSON.parse(detail.timelineJson); } catch (e) { tl = null; }
    }
    if (!tl) { box.classList.add('is-hidden'); return; }
    var totalMs = tl.totalMs || detail.durationMs || 0;
    var wrap = document.createElement('div');
    wrap.className = 'tl-box';
    var head = document.createElement('div');
    head.className = 'tl-head';
    head.innerHTML = '<span></span><span class="tl-total"></span>';
    head.querySelector('span').textContent = _t('mv.timeline', '时间轴');
    head.querySelector('.tl-total').textContent = _t('mv.totalLen', '总长 ') + fmtT(totalMs);
    wrap.appendChild(head);
    (tl.sections || []).forEach(function (sec) {
      var secEl = document.createElement('div');
      secEl.className = 'tl-sec';
      var secHead = document.createElement('div');
      secHead.className = 'tl-sec-head';
      secHead.innerHTML = '<span class="tl-sec-name"></span><span class="tl-mood"></span><span class="tl-sec-time"></span>';
      secHead.querySelector('.tl-sec-name').textContent = sec.name || '';
      secHead.querySelector('.tl-mood').textContent = sec.mood || '';
      secHead.querySelector('.tl-sec-time').textContent =
        fmtT(sec.startMs) + '–' + fmtT(sec.endMs);
      secEl.appendChild(secHead);
      (sec.lines || []).forEach(function (ln) {
        var lineEl = document.createElement('div');
        lineEl.className = 'tl-line';
        lineEl.innerHTML = '<span class="tl-text"></span><span class="tl-time"></span>';
        lineEl.querySelector('.tl-text').textContent = ln.text || '';
        lineEl.querySelector('.tl-time').textContent =
          fmtT(ln.startMs) + '–' + fmtT(ln.endMs);
        secEl.appendChild(lineEl);
      });
      wrap.appendChild(secEl);
    });
    box.appendChild(wrap);
    box.classList.remove('is-hidden');
    if (window.DFI18N) DFI18N.applyI18n(box);
  }

  $('btnToStoryboard').addEventListener('click', function () { goStep(3); });

  /* ---- 导入已有音频 ---- */
  $('btnImport').addEventListener('click', function () {
    var title = $('importTitle').value.trim();
    var file = $('importFile').files[0];
    if (!title) { $('importNote').textContent = _t('mv.needTitle', '请填写歌曲标题'); return; }
    if (!file) { $('importNote').textContent = _t('mv.needFile', '请选择音频文件'); return; }
    var ext = (file.name.split('.').pop() || '').toLowerCase();
    if (['mp3', 'wav', 'm4a'].indexOf(ext) < 0) { $('importNote').textContent = _t('mv.extOnly', '仅支持 mp3 / wav / m4a'); return; }
    if (file.size > 100 * 1024 * 1024) { $('importNote').textContent = _t('mv.sizeLimit', '文件超过 100MB 上限'); return; }
    var btn = $('btnImport');
    btn.disabled = true;
    $('importNote').textContent = _t('mv.uploading', '上传中…');
    var bar = $('uploadProgress');
    bar.classList.remove('is-hidden');
    $('uploadFill').style.width = '0%';
    var fd = new FormData();
    fd.append('file', file);
    fd.append('title', title);
    fd.append('lyrics', $('importLyrics').value);
    fd.append('mood', $('importMood').value);
    fd.append('style', $('importStyle').value);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/mv/import');
    xhr.upload.addEventListener('progress', function (ev) {
      if (ev.lengthComputable) {
        $('uploadFill').style.width = Math.round(ev.loaded / ev.total * 100) + '%';
      }
    });
    xhr.addEventListener('load', function () {
      btn.disabled = false;
      var res = null;
      try { res = JSON.parse(xhr.responseText); } catch (e) { /* 忽略 */ }
      if (xhr.status >= 200 && xhr.status < 300 && res && res.status === 'SUCCEEDED') {
        songId = res.id;
        $('importAudioEl').src = res.audioUrl || '';
        $('importAudioMeta').textContent = res.durationMs
          ? _t('mv.durationSkipped', '时长约 ') + Math.round(res.durationMs / 1000) + _t('mv.durationSkippedTail', ' 秒，已跳过作词作曲') : _t('mv.importedSkipped', '已跳过作词作曲');
        $('importAudioBar').classList.remove('is-hidden');
        $('importNote').textContent = '';
        bar.classList.add('is-hidden');
        markStepsSkipped();
      } else {
        var msg = (res && res.error) || xhr.responseText || ('HTTP ' + xhr.status);
        $('importNote').textContent = _t('mv.importFail', '导入失败：') + msg;
        bar.classList.add('is-hidden');
      }
    });
    xhr.addEventListener('error', function () {
      btn.disabled = false;
      $('importNote').textContent = _t('mv.importFail', '导入失败：') + _t('mv.netError', '网络错误');
      bar.classList.add('is-hidden');
    });
    xhr.send(fd);
  });

  $('btnImportToStoryboard').addEventListener('click', function () { goStep(3); });

  /* ---- 步骤3：分镜 ---- */
  $('btnStoryboard').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnStoryboard');
    btn.disabled = true;
    api('/api/mv/' + songId + '/storyboard', { method: 'POST' })
      .then(function (res) {
        var box = $('storyboardList');
        box.innerHTML = '';
        (res.items || []).forEach(function (it, i) {
          var card = document.createElement('div');
          card.className = 'sb-card';
          card.innerHTML =
            '<div class="sb-head"><span class="sb-idx"></span>' +
            '<span class="sb-sec"></span><span class="sb-time"></span></div>' +
            '<div class="sb-line"></div>' +
            '<textarea rows="3"></textarea>';
          card.querySelector('.sb-idx').textContent = _t('mv.shotPrefix', '第') + (i + 1) + _t('mv.shotSuffix', '镜');
          card.querySelector('.sb-sec').textContent = it.section || '';
          var durSec = ((it.durationMs || 0) / 1000).toFixed(1);
          card.querySelector('.sb-time').textContent =
            fmtT(it.startMs) + '–' + fmtT(it.endMs) + _t('mv.shotDurationPre', '（共') + durSec + _t('mv.shotDurationPost', '秒）');
          card.querySelector('.sb-line').textContent = it.text || '';
          card.querySelector('textarea').value = it.visualPrompt || '';
          box.appendChild(card);
        });
        $('btnToRender').classList.remove('is-hidden');
        if (window.DFI18N) DFI18N.applyI18n(box);
      })
      .catch(function (e) { alert(_t('mv.storyboardFail', '分镜生成失败：') + e.message); })
      .finally(function () { btn.disabled = false; });
  });

  $('btnToRender').addEventListener('click', function () { goStep(4); });

  /* ---- 步骤4：渲染 ---- */
  $('btnRender').addEventListener('click', function () {
    if (!songId) return;
    var btn = $('btnRender');
    btn.disabled = true;
    $('progressText').textContent = _t('mv.rendering', '渲染中…');
    api('/api/mv/' + songId + '/render', {
      method: 'POST',
      body: JSON.stringify({ dryRun: $('dryRunToggle').checked })
    }).then(function () {
      pollStatus();
    }).catch(function (e) {
      $('progressText').textContent = _t('mv.renderFail', '渲染失败：') + e.message;
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
          $('progressText').textContent = _t('mv.renderDone', '渲染完成');
          var vurl = '/api/mv/' + songId + '/video';
          $('videoEl').src = vurl;
          $('btnDownload').href = vurl;
          goStep(5);
          $('btnRender').disabled = false;
        } else if (st.status === 'FAILED') {
          clearInterval(pollTimer);
          $('progressText').textContent = _t('mv.renderFailedRetry', '渲染失败，请重试');
          $('btnRender').disabled = false;
        } else {
          $('progressText').textContent = _t('mv.rendering', '渲染中…');
        }
      }).catch(function () { /* 轮询容错 */ });
    }, 3000);
  }

  function renderAgentList(steps) {
    var box = $('agentList');
    box.innerHTML = '';
    var names = {
      LYRICS: _t('mv.agentLyrics', '作词'),
      COMPOSE: _t('mv.agentCompose', '作曲'),
      BOARD: _t('mv.agentBoard', '分镜'),
      VIDEO: _t('mv.agentVideo', '视频生成'),
      EDIT: _t('mv.agentEdit', '剪辑'),
      QC: _t('mv.agentQc', '质检')
    };
    steps.forEach(function (s) {
      var li = document.createElement('li');
      var dot = s.status === 'SUCCEEDED' ? '✓' : (s.status === 'FAILED' ? '✗' : (s.status === 'SKIPPED' ? '⊘' : '…'));
      li.innerHTML = '<span></span><span class="st"></span>';
      li.children[0].textContent = dot + ' ' + (names[s.agentType] || s.agentType);
      var stText = {
        SUCCEEDED: _t('mv.statusSucceeded', '已完成'),
        FAILED: _t('mv.statusFailed', '失败'),
        SKIPPED: _t('mv.statusSkipped', '已跳过'),
        RUNNING: _t('mv.statusRunning', '进行中'),
        PENDING: _t('mv.statusPending', '待执行')
      }[s.status] || s.status || '';
      li.children[1].textContent = stText;
      box.appendChild(li);
    });
    if (window.DFI18N) DFI18N.applyI18n(box);
  }

  /* ---- 步骤5：再做一支 ---- */
  $('btnAgain').addEventListener('click', function () {
    songId = null;
    if (pollTimer) clearInterval(pollTimer);
    $('themeInput').value = '';
    $('lyricsSections').innerHTML = '';
    $('storyboardList').innerHTML = '';
    $('timelineBox').innerHTML = '';
    $('timelineBox').classList.add('is-hidden');
    $('audioBar').classList.add('is-hidden');
    $('importAudioBar').classList.add('is-hidden');
    $('importTitle').value = '';
    $('importFile').value = '';
    $('importLyrics').value = '';
    $('importNote').textContent = '';
    $('uploadProgress').classList.add('is-hidden');
    clearStepsSkipped();
    $('btnToRender').classList.add('is-hidden');
    $('progressFill').style.width = '0%';
    $('progressPct').textContent = '0%';
    $('progressText').textContent = _t('mv.notStarted', '未开始');
    $('agentList').innerHTML = '';
    $('videoEl').removeAttribute('src');
    goStep(1);
  });

  /* ---- 语言切换后重绘主渲染 ---- */
  if (window.DFI18N && typeof DFI18N.onLangChange === 'function') {
    DFI18N.onLangChange(function () {
      var box = $('lyricsSections');
      if (box && box.children.length) {
        Array.prototype.forEach.call(box.querySelectorAll('.dur'), function (el) {
          var m = (el.textContent || '').match(/(\d+)/);
          if (m) el.textContent = _t('mv.aboutSeconds', '约') + m[1] + _t('mv.seconds', '秒');
        });
      }
      var tl = $('timelineBox');
      if (tl && !tl.classList.contains('is-hidden')) {
        var head = tl.querySelector('.tl-head span');
        if (head) head.textContent = _t('mv.timeline', '时间轴');
        var total = tl.querySelector('.tl-total');
        if (total) {
          var mt = (total.textContent || '').match(/(\d{2}:\d{2})/);
          if (mt) total.textContent = _t('mv.totalLen', '总长 ') + mt[1];
        }
      }
      var sb = $('storyboardList');
      if (sb && sb.children.length) {
        Array.prototype.forEach.call(sb.querySelectorAll('.sb-idx'), function (el, i) {
          el.textContent = _t('mv.shotPrefix', '第') + (i + 1) + _t('mv.shotSuffix', '镜');
        });
        Array.prototype.forEach.call(sb.querySelectorAll('.sb-time'), function (el) {
          var mt = (el.textContent || '').match(/(\d{2}:\d{2})–(\d{2}:\d{2})（?共?([\d.]+)秒?）?/);
          if (!mt) mt = (el.textContent || '').match(/(\d{2}:\d{2})–(\d{2}:\d{2})\(total ([\d.]+)s\)/);
          if (mt) el.textContent = mt[1] + '–' + mt[2] + _t('mv.shotDurationPre', '（共') + mt[3] + _t('mv.shotDurationPost', '秒）');
        });
      }
      var al = $('agentList');
      if (al && al.children.length) {
        var names = {
          LYRICS: _t('mv.agentLyrics', '作词'),
          COMPOSE: _t('mv.agentCompose', '作曲'),
          BOARD: _t('mv.agentBoard', '分镜'),
          VIDEO: _t('mv.agentVideo', '视频生成'),
          EDIT: _t('mv.agentEdit', '剪辑'),
          QC: _t('mv.agentQc', '质检')
        };
        var statusMap = {
          SUCCEEDED: _t('mv.statusSucceeded', '已完成'),
          FAILED: _t('mv.statusFailed', '失败'),
          SKIPPED: _t('mv.statusSkipped', '已跳过'),
          RUNNING: _t('mv.statusRunning', '进行中'),
          PENDING: _t('mv.statusPending', '待执行')
        };
        Array.prototype.forEach.call(al.children, function (li) {
          var st = li.querySelector('.st');
          if (st && statusMap[st.dataset.code]) st.textContent = statusMap[st.dataset.code];
          var nameEl = li.children[0];
          if (nameEl && nameEl.dataset.agentType && names[nameEl.dataset.agentType]) {
            var dot = (nameEl.textContent || '').charAt(0);
            nameEl.textContent = dot + ' ' + names[nameEl.dataset.agentType];
          }
        });
      }
      var pt = $('progressText');
      if (pt) {
        var code = pt.dataset.code;
        if (code === 'rendering') pt.textContent = _t('mv.rendering', '渲染中…');
        else if (code === 'done') pt.textContent = _t('mv.renderDone', '渲染完成');
        else if (code === 'failed') pt.textContent = _t('mv.renderFailedRetry', '渲染失败，请重试');
        else if (code === 'notStarted') pt.textContent = _t('mv.notStarted', '未开始');
      }
      if (window.DFI18N) DFI18N.applyI18n(document);
    });
  }
})();
