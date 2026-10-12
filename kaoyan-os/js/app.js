/* ============================================================
 * app.js —— 路由分发 + 仪表盘
 * 依赖全局：SUBJECTS, EXAM_DATE, state, saveState, uid, todayStr,
 *          dateOffset, esc, subjName, daysLeft
 * 其他模块提供：renderPlan/renderPomodoro/renderMistakes/renderSRS/renderExams
 * ============================================================ */

/* ---------- 工具：中文日期 ---------- */
var WEEK_CN = ['星期日','星期一','星期二','星期三','星期四','星期五','星期六'];

function todayCN() {
  var d = new Date();
  return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + WEEK_CN[d.getDay()];
}

/* ---------- 路由表 ---------- */
var ROUTES = {
  dashboard: { title: '指挥舱',   render: renderDashboard },
  plan:      { title: '学习计划', render: function (v) { renderPlan(v); } },
  focus:     { title: '专注计时', render: function (v) { renderPomodoro(v); } },
  mistakes:  { title: '错题本',   render: function (v) { renderMistakes(v); } },
  words:     { title: '单词本',   render: function (v) { renderSRS(v); } },
  exams:     { title: '真题模考', render: function (v) { renderExams(v); } }
};

/* ---------- 读取当前路由 ---------- */
function currentRoute() {
  var h = location.hash || '';
  var m = h.match(/^#\/([a-zA-Z]+)/);
  var r = m ? m[1] : 'dashboard';
  return ROUTES[r] ? r : 'dashboard';
}

/* ---------- 倒计时填充 ---------- */
function renderCountdown() {
  var el = document.getElementById('countdown');
  if (!el) return;
  var n = daysLeft();
  el.innerHTML = n > 0
    ? '距初试还有 <strong>' + n + '</strong> 天'
    : (n === 0 ? '今天就是初试！' : '初试已结束');
}

/* ---------- 导航 ---------- */
function navigate() {
  var route = currentRoute();
  var cfg = ROUTES[route];

  // nav active
  var items = document.querySelectorAll('.sidebar .nav-item');
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    if (it.getAttribute('data-route') === route) {
      it.classList.add('active');
    } else {
      it.classList.remove('active');
    }
  }

  // 顶栏
  var t = document.getElementById('topTitle');
  if (t) t.textContent = cfg.title;
  var d = document.getElementById('topDate');
  if (d) d.textContent = todayCN();

  // 倒计时
  renderCountdown();

  // 视图
  var view = document.getElementById('view');
  if (view) {
    view.innerHTML = '';
    cfg.render(view);
  }
}

/* ============================================================
 * 仪表盘
 * ============================================================ */
function renderDashboard(view) {
  var today = todayStr();
  var dl = daysLeft();

  /* ---------- 统计计算 ---------- */
  // 今日任务
  var todayTasks = [];
  for (var i = 0; i < state.tasks.length; i++) {
    if (state.tasks[i].date === today) todayTasks.push(state.tasks[i]);
  }
  var doneTasks = 0;
  for (var i2 = 0; i2 < todayTasks.length; i2++) {
    if (todayTasks[i2].done) doneTasks++;
  }

  // 今日专注分钟
  var todayMinutes = 0;
  for (var s = 0; s < state.sessions.length; s++) {
    if (state.sessions[s].date === today) {
      todayMinutes += Number(state.sessions[s].minutes) || 0;
    }
  }

  // 四科待复习单词（due <= today 且 ease/reps 未掌握 —— 用 due<=today 判定待复习）
  var dueWords = 0;
  for (var w = 0; w < state.words.length; w++) {
    var wd = state.words[w];
    if (wd.due && wd.due <= today) dueWords++;
  }

  // 未掌握错题数
  var unmastered = 0;
  for (var m = 0; m < state.mistakes.length; m++) {
    if (!state.mistakes[m].mastered) unmastered++;
  }

  /* ---------- 近 7 天专注 ---------- */
  var days = [];
  for (var k = 6; k >= 0; k--) {
    var ds = dateOffset(-k);
    var total = 0;
    for (var ss = 0; ss < state.sessions.length; ss++) {
      if (state.sessions[ss].date === ds) {
        total += Number(state.sessions[ss].minutes) || 0;
      }
    }
    days.push({ date: ds, minutes: total });
  }
  var weekTotal = 0;
  for (var wk = 0; wk < days.length; wk++) weekTotal += days[wk].minutes;

  /* ---------- 各科累计专注 ---------- */
  var subjMinutes = {};
  for (var si = 0; si < SUBJECTS.length; si++) {
    subjMinutes[SUBJECTS[si].id] = 0;
  }
  for (var sc = 0; sc < state.sessions.length; sc++) {
    var sess = state.sessions[sc];
    if (subjMinutes[sess.subject] !== undefined) {
      subjMinutes[sess.subject] += Number(sess.minutes) || 0;
    }
  }
  var maxSubj = 1;
  for (var sk in subjMinutes) {
    if (subjMinutes[sk] > maxSubj) maxSubj = subjMinutes[sk];
  }

  /* ---------- 真题平均分 ---------- */
  var avgScoreHtml;
  if (state.exams && state.exams.length > 0) {
    var sumPct = 0, cnt = 0;
    for (var e = 0; e < state.exams.length; e++) {
      var ex = state.exams[e];
      if (ex.total > 0) {
        sumPct += (Number(ex.score) / Number(ex.total)) * 100;
        cnt++;
      }
    }
    avgScoreHtml = cnt > 0
      ? '<span class="stat-num">' + (sumPct / cnt).toFixed(1) + '</span><span class="stat-label">%</span>'
      : '<span class="stat-num">--</span>';
  } else {
    avgScoreHtml = '<span class="stat-num">--</span>';
  }

  /* ---------- 错题掌握率 ---------- */
  var totalMistakes = state.mistakes.length;
  var masteredCnt = totalMistakes - unmastered;
  var masterRate = totalMistakes > 0
    ? Math.round((masteredCnt / totalMistakes) * 100)
    : 0;

  /* ---------- 拼装 HTML ---------- */
  var html = '';

  // grid-4 统计卡
  html += '<div class="grid grid-4">';

  html += '<div class="card">'
        + '<div class="stat-num">' + doneTasks + '/' + todayTasks.length + '</div>'
        + '<div class="stat-label">今日任务完成</div>'
        + '</div>';

  html += '<div class="card">'
        + '<div class="stat-num">' + todayMinutes + '</div>'
        + '<div class="stat-label">今日专注分钟</div>'
        + '</div>';

  html += '<div class="card">'
        + '<div class="stat-num">' + dueWords + '</div>'
        + '<div class="stat-label">待复习单词</div>'
        + '</div>';

  html += '<div class="card">'
        + '<div class="stat-num">' + unmastered + '</div>'
        + '<div class="stat-label">未掌握错题</div>'
        + '</div>';

  html += '</div>';

  // 今日任务 + 近7天专注（两栏）
  html += '<div class="grid grid-2" style="margin-top:16px">';

  // 今日任务卡
  html += '<div class="card">';
  html += '<h3>今日任务</h3>';
  if (todayTasks.length === 0) {
    html += '<div class="empty">今天还没有安排任务</div>';
  } else {
    html += '<div class="row-list">';
    for (var ti = 0; ti < todayTasks.length; ti++) {
      var tk = todayTasks[ti];
      var checkedAttr = tk.done ? ' checked' : '';
      var doneCls = tk.done ? 'task-done' : '';
      html += '<label class="row task-row ' + doneCls + '">'
            + '<input type="checkbox" class="task-check" data-id="' + esc(tk.id) + '"' + checkedAttr + '>'
            + '<span class="tag subj-' + esc(tk.subject) + '">' + esc(subjName(tk.subject)) + '</span>'
            + '<span class="task-title">' + esc(tk.title) + '</span>'
            + '<span class="muted">' + (Number(tk.minutes) || 0) + '分钟</span>'
            + '</label>';
    }
    html += '</div>';
  }
  html += '</div>';

  // 近7天专注卡
  html += '<div class="card">';
  html += '<h3>近 7 天专注</h3>';
  if (weekTotal === 0) {
    html += '<div class="empty">近 7 天暂无专注记录</div>';
  } else {
    html += '<div class="chart-wrap"><canvas id="weekChart" width="640" height="260"></canvas></div>';
  }
  html += '</div>';

  html += '</div>';

  // 各科累计专注 + 倒计时概览
  html += '<div class="grid grid-2" style="margin-top:16px">';

  // 各科累计专注
  html += '<div class="card">';
  html += '<h3>各科累计专注</h3>';
  html += '<div class="row-list">';
  for (var sj = 0; sj < SUBJECTS.length; sj++) {
    var subj = SUBJECTS[sj];
    var mins = subjMinutes[subj.id] || 0;
    var pct = Math.round((mins / maxSubj) * 100);
    html += '<div class="row subj-row">'
          + '<span class="tag subj-' + esc(subj.id) + '">' + esc(subj.name) + '</span>'
          + '<div class="progress" style="flex:1;margin:0 10px">'
          + '<div class="progress-bar" style="width:' + pct + '%"></div>'
          + '</div>'
          + '<span class="muted">' + mins + '分钟</span>'
          + '</div>';
  }
  html += '</div>';
  html += '</div>';

  // 倒计时与概览
  html += '<div class="card">';
  html += '<h3>倒计时与概览</h3>';
  html += '<div class="overview">';
  html += '<div class="overview-item">'
        + '<div class="stat-num" style="font-size:42px">' + (dl > 0 ? dl : 0) + '</div>'
        + '<div class="stat-label">距初试天数</div>'
        + '</div>';
  html += '<div class="overview-item">'
        + '<div class="stat-num" style="font-size:32px">' + avgScoreHtml + '</div>'
        + '<div class="stat-label">真题平均得分率</div>'
        + '</div>';
  html += '<div class="overview-item">'
        + '<div class="stat-num" style="font-size:32px">' + masterRate + '%</div>'
        + '<div class="stat-label">错题掌握率</div>'
        + '</div>';
  html += '</div>';
  html += '</div>';

  html += '</div>';

  view.innerHTML = html;

  /* ---------- 事件绑定：任务复选框 ---------- */
  var checks = view.querySelectorAll('.task-check');
  for (var ci = 0; ci < checks.length; ci++) {
    checks[ci].addEventListener('change', onTaskToggle);
  }

  /* ---------- 绘制图表 ---------- */
  if (weekTotal > 0) {
    drawWeekChart(days);
  }
}

/* ---------- 任务勾选切换 ---------- */
function onTaskToggle(ev) {
  var id = ev.target.getAttribute('data-id');
  for (var i = 0; i < state.tasks.length; i++) {
    if (state.tasks[i].id === id) {
      state.tasks[i].done = ev.target.checked;
      break;
    }
  }
  saveState();
  // 重渲染仪表盘
  var view = document.getElementById('view');
  if (view) {
    view.innerHTML = '';
    renderDashboard(view);
  }
}

/* ---------- 手写柱状图 ---------- */
function drawWeekChart(days) {
  var canvas = document.getElementById('weekChart');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');

  var W = canvas.width;
  var H = canvas.height;
  var padL = 44, padR = 16, padT = 20, padB = 34;

  var plotW = W - padL - padR;
  var plotH = H - padT - padB;

  ctx.clearRect(0, 0, W, H);

  // 求最大值（至少为 1，避免除零）
  var maxVal = 1;
  for (var i = 0; i < days.length; i++) {
    if (days[i].minutes > maxVal) maxVal = days[i].minutes;
  }
  // 向上取整到刻度
  var step = Math.ceil(maxVal / 4);
  if (step < 1) step = 1;
  var topVal = step * 4;

  // 绘制 Y 轴刻度线
  ctx.strokeStyle = '#e5e7eb';
  ctx.fillStyle = '#9ca3af';
  ctx.font = '12px sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (var g = 0; g <= 4; g++) {
    var val = step * g;
    var y = padT + plotH - (val / topVal) * plotH;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();
    ctx.fillText(String(val), padL - 8, y);
  }

  // 柱状
  var n = days.length;
  var slot = plotW / n;
  var barW = slot * 0.5;
  var barGap = (slot - barW) / 2;

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  for (var b = 0; b < n; b++) {
    var d = days[b];
    var bh = (d.minutes / topVal) * plotH;
    var bx = padL + b * slot + barGap;
    var by = padT + plotH - bh;

    // 柱体
    if (d.minutes > 0) {
      var grad = ctx.createLinearGradient(0, by, 0, padT + plotH);
      grad.addColorStop(0, '#4f8cff');
      grad.addColorStop(1, '#8ab4ff');
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = '#eef2f7';
    }
    ctx.fillRect(bx, by, barW, bh > 0 ? bh : 2);

    // 顶部数值
    if (d.minutes > 0) {
      ctx.fillStyle = '#4f8cff';
      ctx.font = '11px sans-serif';
      ctx.fillText(String(d.minutes), bx + barW / 2, by - 14);
    }

    // X 轴日期标签（月/日）
    var parts = d.date.split('-');
    var label = parts[1] + '/' + parts[2];
    ctx.fillStyle = '#9ca3af';
    ctx.font = '12px sans-serif';
    ctx.fillText(label, bx + barW / 2, padT + plotH + 8);
  }

  // 基线
  ctx.strokeStyle = '#d1d5db';
  ctx.beginPath();
  ctx.moveTo(padL, padT + plotH);
  ctx.lineTo(padL + plotW, padT + plotH);
  ctx.stroke();
}

/* ============================================================
 * 初始化
 * ============================================================ */
function init() {
  // 若 store 未自动加载，尝试加载
  if (typeof loadState === 'function') {
    try { loadState(); } catch (e) { /* ignore */ }
  }
  navigate();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// 路由变化监听
window.addEventListener('hashchange', navigate);
