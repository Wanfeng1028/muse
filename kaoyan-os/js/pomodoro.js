// js/pomodoro.js —— 番茄专注计时模块（普通 script，全局函数 renderPomodoro）

// 模块级状态：interval id 与计时运行数据
var _pomoTimerId = null;      // setInterval 的 id，用于清理
var _pomoRunning = false;     // 是否正在计时
var _pomoPaused = false;      // 是否已暂停
var _pomoMode = 'focus';      // 'focus' 或 'break'
var _pomoEndAt = 0;           // 计时结束的时间戳（Date.now() 基准）
var _pomoRemainMs = 0;        // 暂停时保存的剩余毫秒
var _pomoTotalMs = 0;         // 本次计时总毫秒（用于比例条）
var _pomoSubject = null;      // 当前选中的科目 id
var _pomoHint = '';           // 页面内提示文字

// 清理旧计时器，避免多重 interval
function _pomoClearTimer() {
  if (_pomoTimerId !== null) {
    clearInterval(_pomoTimerId);
    _pomoTimerId = null;
  }
}

// 秒数格式化 mm:ss
function _pomoFmt(sec) {
  sec = Math.max(0, Math.floor(sec));
  var m = Math.floor(sec / 60);
  var s = sec % 60;
  return (m < 10 ? '0' + m : '' + m) + ':' + (s < 10 ? '0' + s : '' + s);
}

// 根据模式取总时长（毫秒）
function _pomoModeMs(mode) {
  var mins = (mode === 'break')
    ? Number(state.settings.breakMin) || 5
    : Number(state.settings.focusMin) || 25;
  return mins * 60 * 1000;
}

// WebAudio 简单蜂鸣（try/catch 包裹，失败静默）
function _pomoBeep() {
  try {
    var Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    var ctx = new Ctx();
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.65);
    // 第二声，稍作间隔
    setTimeout(function () {
      try {
        var osc2 = ctx.createOscillator();
        var g2 = ctx.createGain();
        osc2.type = 'sine';
        osc2.frequency.value = 1046;
        g2.gain.setValueAtTime(0.001, ctx.currentTime);
        g2.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
        g2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
        osc2.connect(g2);
        g2.connect(ctx.destination);
        osc2.start();
        osc2.stop(ctx.currentTime + 0.65);
      } catch (e) {}
    }, 700);
    // 释放资源
    setTimeout(function () {
      try { ctx.close(); } catch (e) {}
    }, 2000);
  } catch (e) {
    // 忽略音频错误
  }
}

// 专注完成：写入 session 并刷新记录区
function _pomoCommitFocus(minutes) {
  var sid = _pomoSubject || (SUBJECTS && SUBJECTS.length ? SUBJECTS[0].id : '');
  if (!sid) return;
  try {
    state.sessions.push({
      id: (typeof uid === 'function') ? uid() : String(Date.now()),
      subject: sid,
      date: (typeof todayStr === 'function') ? todayStr() : new Date().toISOString().slice(0, 10),
      minutes: minutes
    });
    if (typeof saveState === 'function') saveState();
  } catch (e) {}
}

// 构建今日专注记录卡的 DOM 片段
function _pomoRecordsHTML() {
  var today = (typeof todayStr === 'function') ? todayStr() : new Date().toISOString().slice(0, 10);
  var list = (state.sessions || []).filter(function (s) { return s && s.date === today; });
  var total = 0;
  list.forEach(function (s) { total += Number(s.minutes) || 0; });

  var inner;
  if (!list.length) {
    inner = '<div class="empty">今天还没有专注记录，开始第一个番茄吧。</div>';
  } else {
    var rows = list.map(function (s) {
      var nm = (typeof subjName === 'function') ? subjName(s.subject) : (s.subject || '');
      var cls = 'tag subj-' + (s.subject || 'major');
      return '<tr>'
        + '<td><span class="' + cls + '">' + ((typeof esc === 'function') ? esc(nm) : nm) + '</span></td>'
        + '<td>' + (Number(s.minutes) || 0) + ' 分钟</td>'
        + '</tr>';
    }).join('');
    inner = '<table class="table">'
      + '<thead><tr><th>科目</th><th>时长</th></tr></thead>'
      + '<tbody>' + rows + '</tbody>'
      + '</table>';
  }

  return '<div class="card">'
    + '<div class="row" style="justify-content:space-between;align-items:center;">'
    + '<h3 style="margin:0;">今日专注记录</h3>'
    + '<div class="muted">今日合计：<b>' + total + '</b> 分钟</div>'
    + '</div>'
    + '<div style="margin-top:8px;">' + inner + '</div>'
    + '</div>';
}

// 渲染记录区（局部刷新，避免重建计时卡导致计时中断）
function _pomoRenderRecords(view) {
  var host = view.querySelector('#pomo-records');
  if (host) host.innerHTML = _pomoRecordsHTML();
}

// 渲染整页
function renderPomodoro(view) {
  // 每次进入都先清理旧计时器
  _pomoClearTimer();

  // 若上次在计时中，重置运行态（切换路由视为停止）
  _pomoRunning = false;
  _pomoPaused = false;
  _pomoRemainMs = 0;

  // 确保设置默认值
  if (!state.settings) state.settings = {};
  if (typeof state.settings.focusMin !== 'number') state.settings.focusMin = 25;
  if (typeof state.settings.breakMin !== 'number') state.settings.breakMin = 5;

  // 默认科目
  if (!_pomoSubject && SUBJECTS && SUBJECTS.length) {
    _pomoSubject = SUBJECTS[0].id;
  }

  _pomoMode = 'focus';
  _pomoTotalMs = _pomoModeMs('focus');
  _pomoRemainMs = _pomoTotalMs;
  _pomoHint = '';

  // 科目选项
  var subjOpts = (SUBJECTS || []).map(function (s) {
    var sel = (s.id === _pomoSubject) ? ' selected' : '';
    var nm = (typeof esc === 'function') ? esc(s.name || s.id) : (s.name || s.id);
    return '<option value="' + s.id + '"' + sel + '>' + nm + '</option>';
  }).join('');

  // 主 HTML
  view.innerHTML = ''
    + '<div class="card">'
    + '  <div class="row" style="justify-content:space-between;align-items:center;">'
    + '    <h3 style="margin:0;">番茄专注</h3>'
    + '    <div class="timer-modes">'
    + '      <button class="btn btn-sm btn-primary" id="pomo-mode-focus">专注</button>'
    + '      <button class="btn btn-sm btn-ghost" id="pomo-mode-break">休息</button>'
    + '    </div>'
    + '  </div>'
    + '  <div class="row" style="gap:12px;margin-top:12px;flex-wrap:wrap;">'
    + '    <label class="muted">科目 <select class="select" id="pomo-subject">' + subjOpts + '</select></label>'
    + '    <label class="muted">专注(分) <input class="input" type="number" min="1" max="180" id="pomo-focus-min" value="' + state.settings.focusMin + '" style="width:80px;"></label>'
    + '    <label class="muted">休息(分) <input class="input" type="number" min="1" max="60" id="pomo-break-min" value="' + state.settings.breakMin + '" style="width:80px;"></label>'
    + '  </div>'
    + '  <div class="timer-wrap" style="margin-top:16px;">'
    + '    <div class="timer-display" id="pomo-display">' + _pomoFmt(_pomoRemainMs / 1000) + '</div>'
    + '    <div class="row" style="margin-top:12px;gap:10px;">'
    + '      <button class="btn btn-primary" id="pomo-start">开始</button>'
    + '      <button class="btn btn-ghost" id="pomo-reset">重置</button>'
    + '    </div>'
    + '    <div id="pomo-hint" class="muted" style="margin-top:10px;min-height:20px;">' + _pomoHint + '</div>'
    + '    <div style="margin-top:12px;height:8px;background:#eee;border-radius:4px;overflow:hidden;">'
    + '      <div id="pomo-progress" style="height:100%;width:100%;background:#4a90e2;transition:width 0.3s linear;"></div>'
    + '    </div>'
    + '  </div>'
    + '</div>'
    + '<div id="pomo-records">' + _pomoRecordsHTML() + '</div>';

  // 元素引用
  var display = view.querySelector('#pomo-display');
  var progress = view.querySelector('#pomo-progress');
  var hintEl = view.querySelector('#pomo-hint');
  var startBtn = view.querySelector('#pomo-start');
  var resetBtn = view.querySelector('#pomo-reset');
  var focusModeBtn = view.querySelector('#pomo-mode-focus');
  var breakModeBtn = view.querySelector('#pomo-mode-break');
  var subjSel = view.querySelector('#pomo-subject');
  var focusInp = view.querySelector('#pomo-focus-min');
  var breakInp = view.querySelector('#pomo-break-min');

  // 更新显示与比例条
  function paint() {
    var remainSec = _pomoRemainMs / 1000;
    display.textContent = _pomoFmt(remainSec);
    var ratio = _pomoTotalMs > 0 ? (_pomoRemainMs / _pomoTotalMs) : 0;
    ratio = Math.max(0, Math.min(1, ratio));
    progress.style.width = (ratio * 100) + '%';
    hintEl.textContent = _pomoHint || '';
  }

  // 切换模式按钮样式
  function paintModes() {
    if (_pomoMode === 'focus') {
      focusModeBtn.className = 'btn btn-sm btn-primary';
      breakModeBtn.className = 'btn btn-sm btn-ghost';
    } else {
      focusModeBtn.className = 'btn btn-sm btn-ghost';
      breakModeBtn.className = 'btn btn-sm btn-primary';
    }
  }

  // 开始计时（内部）
  function startTick() {
    _pomoClearTimer();
    _pomoTimerId = setInterval(function () {
      var remain = Math.max(0, _pomoEndAt - Date.now());
      _pomoRemainMs = remain;
      paint();
      if (remain <= 0) {
        _pomoClearTimer();
        _pomoRunning = false;
        _pomoPaused = false;
        _pomoRemainMs = 0;
        paint();
        _pomoBeep();
        if (_pomoMode === 'focus') {
          var mins = Math.round(_pomoTotalMs / 60000);
          _pomoCommitFocus(mins);
          _pomoRenderRecords(view);
          _pomoHint = '专注完成！已记录 ' + mins + ' 分钟。休息一下吧。';
        } else {
          _pomoHint = '休息结束！准备开始下一个番茄。';
        }
        paint();
        startBtn.textContent = '开始';
        // 完成后重置为当前模式满时长
        _pomoTotalMs = _pomoModeMs(_pomoMode);
        _pomoRemainMs = _pomoTotalMs;
        setTimeout(function () {
          paint();
        }, 0);
      }
    }, 1000);
  }

  // 开始 / 暂停
  function onStart() {
    if (_pomoRunning && !_pomoPaused) {
      // 暂停：保存剩余
      _pomoPaused = true;
      _pomoClearTimer();
      startBtn.textContent = '继续';
      _pomoHint = '已暂停';
      paint();
      return;
    }
    if (_pomoPaused) {
      // 继续：用剩余毫秒重建 endAt
      _pomoPaused = false;
      _pomoEndAt = Date.now() + _pomoRemainMs;
      _pomoRunning = true;
      startBtn.textContent = '暂停';
      _pomoHint = '计时中…';
      paint();
      startTick();
      return;
    }
    // 全新开始
    _pomoTotalMs = _pomoModeMs(_pomoMode);
    _pomoRemainMs = _pomoTotalMs;
    _pomoEndAt = Date.now() + _pomoRemainMs;
    _pomoRunning = true;
    _pomoPaused = false;
    startBtn.textContent = '暂停';
    _pomoHint = (_pomoMode === 'focus') ? '专注中…' : '休息中…';
    paint();
    startTick();
  }

  // 重置
  function onReset() {
    _pomoClearTimer();
    _pomoRunning = false;
    _pomoPaused = false;
    _pomoTotalMs = _pomoModeMs(_pomoMode);
    _pomoRemainMs = _pomoTotalMs;
    _pomoEndAt = 0;
    startBtn.textContent = '开始';
    _pomoHint = '已重置';
    paint();
  }

  // 切换模式
  function onMode(mode) {
    if (_pomoRunning) {
      // 运行中切换：先停止
      _pomoClearTimer();
      _pomoRunning = false;
      _pomoPaused = false;
      startBtn.textContent = '开始';
    }
    _pomoMode = mode;
    _pomoTotalMs = _pomoModeMs(mode);
    _pomoRemainMs = _pomoTotalMs;
    _pomoHint = '';
    paintModes();
    paint();
  }

  // 事件绑定
  startBtn.addEventListener('click', onStart);
  resetBtn.addEventListener('click', onReset);
  focusModeBtn.addEventListener('click', function () { onMode('focus'); });
  breakModeBtn.addEventListener('click', function () { onMode('break'); });

  subjSel.addEventListener('change', function () {
    _pomoSubject = subjSel.value;
  });

  focusInp.addEventListener('change', function () {
    var v = parseInt(focusInp.value, 10);
    if (isNaN(v) || v < 1) v = 1;
    if (v > 180) v = 180;
    focusInp.value = v;
    state.settings.focusMin = v;
    if (typeof saveState === 'function') saveState();
    // 若当前是专注模式且未运行，则同步剩余时间
    if (_pomoMode === 'focus' && !_pomoRunning) {
      _pomoTotalMs = _pomoModeMs('focus');
      _pomoRemainMs = _pomoTotalMs;
      paint();
    }
  });

  breakInp.addEventListener('change', function () {
    var v = parseInt(breakInp.value, 10);
    if (isNaN(v) || v < 1) v = 1;
    if (v > 60) v = 60;
    breakInp.value = v;
    state.settings.breakMin = v;
    if (typeof saveState === 'function') saveState();
    if (_pomoMode === 'break' && !_pomoRunning) {
      _pomoTotalMs = _pomoModeMs('break');
      _pomoRemainMs = _pomoTotalMs;
      paint();
    }
  });

  // 初始渲染
  paintModes();
  paint();
}
