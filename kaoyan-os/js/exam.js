/* 考研指挥舱 - 真题计时与统计模块
 * 依赖：js/store.js 提供的 SUBJECTS、state、saveState()、uid()、todayStr()、esc(s)、subjName(id)
 * 全局函数：renderExams(view)
 */

// 模块级计时器 id，用于 renderExams 重入时清理
let _examTimerId = null;

// 计时相关状态（模块级，重渲染不丢失）
let _timerRunning = false;
let _timerStartTs = 0;       // 开始计时的时间戳
let _timerElapsedMs = 0;     // 累计已用毫秒（暂停场景用，这里连续累加）
let _timerSubject = null;    // 当前计时科目
let _timerPaperName = '';    // 当前计时试卷名

// 科目建议满分
function _suggestTotal(subject) {
  if (subject === 'math' || subject === 'major') return 150;
  return 100;
}

// 科目颜色
const _SUBJ_COLORS = {
  math: '#4f7cff',
  english: '#ff8a3d',
  politics: '#e5484d',
  major: '#8b5cf6'
};

// 毫秒 -> hh:mm:ss
function _fmtHMS(ms) {
  if (!ms || ms < 0) ms = 0;
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const pad = (n) => (n < 10 ? '0' + n : '' + n);
  return pad(h) + ':' + pad(m) + ':' + pad(s);
}

// 计算当前已用毫秒
function _currentElapsedMs() {
  if (_timerRunning && _timerStartTs) {
    return _timerElapsedMs + (Date.now() - _timerStartTs);
  }
  return _timerElapsedMs;
}

// 清理旧计时器
function _clearTimer() {
  if (_examTimerId !== null) {
    clearInterval(_examTimerId);
    _examTimerId = null;
  }
}

// 重置计时状态
function _resetTimerState() {
  _timerRunning = false;
  _timerStartTs = 0;
  _timerElapsedMs = 0;
  _timerSubject = null;
  _timerPaperName = '';
}

// 取得某科目的 exams 列表（按日期升序）
function _examsBySubject(subject) {
  return (state.exams || [])
    .filter((e) => e.subject === subject)
    .slice()
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

// 得分率（0-100，保留1位小数）
function _rate(score, total) {
  if (!total || total <= 0) return 0;
  const r = (Number(score) / Number(total)) * 100;
  if (!isFinite(r)) return 0;
  return Math.round(r * 10) / 10;
}

/* ============================================================
 * 渲染主函数
 * ============================================================ */
function renderExams(view) {
  // 防止重入：先清旧计时器
  _clearTimer();

  view.innerHTML = '';

  // 容器
  const wrap = document.createElement('div');
  wrap.className = 'grid';
  view.appendChild(wrap);

  /* ---------- 卡 1：真题计时 ---------- */
  const timerCard = document.createElement('div');
  timerCard.className = 'card';
  timerCard.innerHTML =
    '<div class="row"><strong>真题计时</strong></div>' +
    '<div class="form-row">' +
      '<label>科目</label>' +
      '<select class="select" id="exam-subject">' +
        SUBJECTS.map((s) =>
          '<option value="' + esc(s.id) + '"' + (s.id === _timerSubject ? ' selected' : '') + '>' +
            esc(s.name) +
          '</option>'
        ).join('') +
      '</select>' +
    '</div>' +
    '<div class="form-row">' +
      '<label>试卷名</label>' +
      '<input class="input" id="exam-name" type="text" placeholder="如：数学一 2020 年真题" value="' + esc(_timerPaperName || '') + '" />' +
    '</div>' +
    '<div class="timer-wrap">' +
      '<div class="timer-display" id="exam-timer-display">' + _fmtHMS(_currentElapsedMs()) + '</div>' +
    '</div>' +
    '<div class="row">' +
      '<button class="btn btn-primary" id="exam-start-btn">开始</button>' +
      '<button class="btn btn-ghost" id="exam-end-btn"' + (_timerRunning ? '' : ' disabled') + '>结束</button>' +
    '</div>' +
    '<div id="exam-score-form"></div>';
  wrap.appendChild(timerCard);

  const subjectSel = timerCard.querySelector('#exam-subject');
  const nameInput = timerCard.querySelector('#exam-name');
  const displayEl = timerCard.querySelector('#exam-timer-display');
  const startBtn = timerCard.querySelector('#exam-start-btn');
  const endBtn = timerCard.querySelector('#exam-end-btn');
  const scoreFormWrap = timerCard.querySelector('#exam-score-form');

  // 计时器刷新
  const tick = () => {
    displayEl.textContent = _fmtHMS(_currentElapsedMs());
  };

  // 若之前已在运行（重渲染前），继续运行
  if (_timerRunning) {
    tick();
    _examTimerId = setInterval(tick, 250);
  }

  // 开始
  startBtn.addEventListener('click', () => {
    if (_timerRunning) return;
    const subj = subjectSel.value;
    const paper = (nameInput.value || '').trim();
    _timerSubject = subj;
    _timerPaperName = paper;
    _timerElapsedMs = 0;
    _timerStartTs = Date.now();
    _timerRunning = true;
    endBtn.disabled = false;
    startBtn.disabled = true;
    // 清空记分表单
    scoreFormWrap.innerHTML = '';
    _clearTimer();
    _examTimerId = setInterval(tick, 250);
    tick();
  });

  // 结束 -> 展开记分表单
  endBtn.addEventListener('click', () => {
    if (!_timerRunning) return;
    // 停止计时
    _timerElapsedMs = _currentElapsedMs();
    _timerRunning = false;
    _timerStartTs = 0;
    _clearTimer();
    tick();
    endBtn.disabled = true;
    startBtn.disabled = false;

    const subj = _timerSubject || subjectSel.value;
    const paper = (_timerPaperName || nameInput.value || '').trim();
    const minutes = Math.max(0, Math.round(_timerElapsedMs / 60000));
    const suggestTotal = _suggestTotal(subj);

    // 构建记分表单
    scoreFormWrap.innerHTML =
      '<div class="form-row">' +
        '<label>得分</label>' +
        '<input class="input" id="exam-score-input" type="number" min="0" step="0.5" placeholder="得分" />' +
      '</div>' +
      '<div class="form-row">' +
        '<label>满分</label>' +
        '<input class="input" id="exam-total-input" type="number" min="1" step="1" value="' + suggestTotal + '" />' +
      '</div>' +
      '<div class="muted">用时：' + minutes + ' 分钟 · 科目：' + esc(subjName(subj)) + ' · 试卷：' + esc(paper || '（未命名）') + '</div>' +
      '<div class="row">' +
        '<button class="btn btn-primary" id="exam-save-btn">保存记录</button>' +
        '<button class="btn btn-ghost" id="exam-cancel-btn">取消</button>' +
      '</div>';

    const scoreInput = scoreFormWrap.querySelector('#exam-score-input');
    const totalInput = scoreFormWrap.querySelector('#exam-total-input');
    const saveBtn = scoreFormWrap.querySelector('#exam-save-btn');
    const cancelBtn = scoreFormWrap.querySelector('#exam-cancel-btn');

    if (scoreInput) scoreInput.focus();

    // 取消：仅清空表单，重置计时显示为 0
    cancelBtn.addEventListener('click', () => {
      scoreFormWrap.innerHTML = '';
      _resetTimerState();
      displayEl.textContent = _fmtHMS(0);
      endBtn.disabled = true;
      startBtn.disabled = false;
    });

    // 保存
    saveBtn.addEventListener('click', () => {
      const score = Number(scoreInput.value);
      const total = Number(totalInput.value);
      if (!isFinite(score) || score < 0) {
        alert('请输入有效的得分');
        return;
      }
      if (!isFinite(total) || total <= 0) {
        alert('请输入有效的满分');
        return;
      }
      const rec = {
        id: uid(),
        subject: subj,
        name: paper || (subjName(subj) + ' 真题'),
        date: todayStr(),
        minutes: minutes,
        score: score,
        total: total
      };
      if (!Array.isArray(state.exams)) state.exams = [];
      state.exams.push(rec);
      saveState();

      // 重置计时状态并重渲染
      _resetTimerState();
      renderExams(view);
    });
  });

  /* ---------- 卡 2：成绩记录 ---------- */
  const listCard = document.createElement('div');
  listCard.className = 'card';
  const exams = (state.exams || []).slice().sort((a, b) => {
    const d = String(b.date).localeCompare(String(a.date));
    if (d !== 0) return d;
    return String(b.id).localeCompare(String(a.id));
  });

  let listHtml = '<div class="row"><strong>成绩记录</strong></div>';
  if (!exams.length) {
    listHtml += '<div class="empty">暂无真题记录，先从上方开始一次计时吧</div>';
  } else {
    listHtml +=
      '<div class="chart-wrap"><table class="table">' +
        '<thead><tr>' +
          '<th>日期</th><th>科目</th><th>试卷</th><th>得分/满分</th><th>得分率</th><th>用时</th><th></th>' +
        '</tr></thead><tbody>' +
        exams.map((e) => {
          const r = _rate(e.score, e.total);
          const subjCls = 'subj-' + e.subject;
          return '<tr>' +
            '<td>' + esc(e.date) + '</td>' +
            '<td><span class="tag ' + subjCls + '">' + esc(subjName(e.subject)) + '</span></td>' +
            '<td>' + esc(e.name) + '</td>' +
            '<td>' + esc(String(e.score)) + ' / ' + esc(String(e.total)) + '</td>' +
            '<td>' + r + '%</td>' +
            '<td>' + esc(String(e.minutes)) + ' 分钟</td>' +
            '<td><button class="btn btn-danger btn-sm" data-del-id="' + esc(e.id) + '">删除</button></td>' +
          '</tr>';
        }).join('') +
      '</tbody></table></div>';
  }
  listCard.innerHTML = listHtml;
  wrap.appendChild(listCard);

  // 删除按钮事件
  listCard.querySelectorAll('[data-del-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-del-id');
      const idx = (state.exams || []).findIndex((e) => e.id === id);
      if (idx >= 0) {
        state.exams.splice(idx, 1);
        saveState();
        renderExams(view);
      }
    });
  });

  /* ---------- 卡 3：统计 ---------- */
  const statCard = document.createElement('div');
  statCard.className = 'card';
  const allExams = state.exams || [];

  let statHtml = '<div class="row"><strong>统计</strong></div>';

  if (!allExams.length) {
    statHtml += '<div class="empty">暂无数据，完成一次真题计时后这里会出现统计</div>';
    statCard.innerHTML = statHtml;
    wrap.appendChild(statCard);
    return;
  }

  // 每科统计
  const rows = [];
  SUBJECTS.forEach((s) => {
    const list = _examsBySubject(s.id);
    if (!list.length) {
      rows.push(
        '<tr>' +
          '<td><span class="tag subj-' + s.id + '">' + esc(s.name) + '</span></td>' +
          '<td class="muted">-</td><td class="muted">-</td><td class="muted">-</td><td class="muted">' + list.length + '</td>' +
        '</tr>'
      );
      return;
    }
    let sumRate = 0, sumMin = 0, best = 0, bestScore = 0;
    list.forEach((e) => {
      const r = _rate(e.score, e.total);
      sumRate += r;
      sumMin += Number(e.minutes) || 0;
      if (r > best) { best = r; bestScore = e.score; }
    });
    const avgRate = Math.round((sumRate / list.length) * 10) / 10;
    const avgMin = Math.round(sumMin / list.length);
    rows.push(
      '<tr>' +
        '<td><span class="tag subj-' + s.id + '">' + esc(s.name) + '</span></td>' +
        '<td>' + avgRate + '%</td>' +
        '<td>' + best + '%（' + esc(String(bestScore)) + '分）</td>' +
        '<td>' + avgMin + ' 分钟</td>' +
        '<td>' + list.length + '</td>' +
      '</tr>'
    );
  });

  statHtml +=
    '<div class="chart-wrap"><table class="table">' +
      '<thead><tr><th>科目</th><th>平均得分率</th><th>最高得分率</th><th>平均用时</th><th>次数</th></tr></thead>' +
      '<tbody>' + rows.join('') + '</tbody>' +
    '</table></div>';

  // 图例
  statHtml +=
    '<div class="row" style="flex-wrap:wrap;gap:12px;margin-top:8px;">' +
      SUBJECTS.map((s) =>
        '<span class="muted"><span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:' +
        _SUBJ_COLORS[s.id] + ';margin-right:4px;vertical-align:middle;"></span>' + esc(s.name) + '</span>'
      ).join('') +
    '</div>';

  // 折线图容器
  statHtml += '<div class="chart-wrap" style="margin-top:8px;"><canvas id="exam-chart" width="720" height="260" style="width:100%;max-width:720px;height:260px;"></canvas></div>';

  statCard.innerHTML = statHtml;
  wrap.appendChild(statCard);

  // 绘制折线图
  const canvas = statCard.querySelector('#exam-chart');
  if (canvas) {
    _drawRateChart(canvas);
  }
}

/* ============================================================
 * 折线图：每科按时间顺序的得分率走势
 * ============================================================ */
function _drawRateChart(canvas) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // 高分屏适配
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 720;
  const cssH = 260;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const W = cssW;
  const H = cssH;
  ctx.clearRect(0, 0, W, H);

  const padL = 44, padR = 16, padT = 18, padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // 收集每科序列
  const series = SUBJECTS.map((s) => {
    const list = _examsBySubject(s.id);
    return {
      id: s.id,
      name: s.name,
      color: _SUBJ_COLORS[s.id],
      points: list.map((e, i) => ({ idx: i, rate: _rate(e.score, e.total), date: e.date }))
    };
  }).filter((s) => s.points.length > 0);

  if (!series.length) {
    ctx.fillStyle = '#999';
    ctx.font = '13px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('暂无数据', W / 2, H / 2);
    return;
  }

  // 横轴：以最大长度为准，0..maxLen-1 均匀分布
  const maxLen = Math.max.apply(null, series.map((s) => s.points.length));
  const xCount = Math.max(maxLen, 2);

  // Y 轴 0-100
  const yMin = 0, yMax = 100;
  const xOf = (i) => padL + (plotW * i) / (xCount - 1);
  const yOf = (v) => padT + plotH - (plotH * (v - yMin)) / (yMax - yMin);

  // 背景网格
  ctx.strokeStyle = 'rgba(0,0,0,0.08)';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#999';
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let v = 0; v <= 100; v += 25) {
    const y = yOf(v);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();
    ctx.fillText(v + '%', padL - 6, y);
  }

  // 坐标轴
  ctx.strokeStyle = 'rgba(0,0,0,0.25)';
  ctx.beginPath();
  ctx.moveTo(padL, padT);
  ctx.lineTo(padL, padT + plotH);
  ctx.lineTo(padL + plotW, padT + plotH);
  ctx.stroke();

  // 横轴刻度
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = '#999';
  for (let i = 0; i < xCount; i++) {
    const x = xOf(i);
    ctx.fillText('#' + (i + 1), x, padT + plotH + 6);
  }

  // 绘制每科折线
  series.forEach((s) => {
    if (!s.points.length) return;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    s.points.forEach((p, i) => {
      const x = xOf(i);
      const y = yOf(p.rate);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // 数据点
    s.points.forEach((p, i) => {
      const x = xOf(i);
      const y = yOf(p.rate);
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = s.color;
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  });
}
