// js/plan.js —— 复习计划模块（普通 script，仅暴露 renderPlan）
// 依赖全局：SUBJECTS, state, saveState, uid, todayStr, dateOffset, esc, subjName

// 模块内筛选状态（跨重渲染保留）
var planFilter = {
  dateMode: 'today', // 'today' | 'tomorrow' | 'all'
  subject: 'all'     // 'all' | 科目 id
};

/**
 * 渲染复习计划视图
 * @param {HTMLElement} view 挂载容器
 */
function renderPlan(view) {
  // ---------- 1. 计算当前筛选后的任务集合 ----------
  var allTasks = Array.isArray(state.tasks) ? state.tasks : [];
  var today = todayStr();
  var tomorrow = dateOffset(1);

  var filtered = allTasks.filter(function (t) {
    // 科目筛选
    if (planFilter.subject !== 'all' && t.subject !== planFilter.subject) return false;
    // 日期筛选
    if (planFilter.dateMode === 'today' && t.date !== today) return false;
    if (planFilter.dateMode === 'tomorrow' && t.date !== tomorrow) return false;
    // 'all' 不限制
    return true;
  });

  // 排序：日期升序，同日未完成在前
  filtered.sort(function (a, b) {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    var ad = a.done ? 1 : 0;
    var bd = b.done ? 1 : 0;
    if (ad !== bd) return ad - bd;
    return 0;
  });

  // ---------- 2. 完成情况统计 ----------
  var totalCount = filtered.length;
  var doneCount = filtered.filter(function (t) { return t.done; }).length;
  var totalMinutes = filtered.reduce(function (s, t) { return s + (Number(t.minutes) || 0); }, 0);
  var doneMinutes = filtered.reduce(function (s, t) {
    return s + (t.done ? (Number(t.minutes) || 0) : 0);
  }, 0);
  var percent = totalCount === 0 ? 0 : Math.round((doneCount / totalCount) * 100);

  // ---------- 3. 构建科目下拉选项 ----------
  var subjectOptions = SUBJECTS.map(function (s) {
    return '<option value="' + esc(s.id) + '">' + esc(s.name) + '</option>';
  }).join('');

  var filterSubjectOptions = '<option value="all">全部科目</option>' + subjectOptions;

  // ---------- 4. 构建任务列表 HTML ----------
  var listHtml = '';
  if (filtered.length === 0) {
    listHtml = '<div class="empty">当前筛选范围内暂无任务，先添加一个吧。</div>';
  } else {
    listHtml = filtered.map(function (t) {
      var subj = subjName(t.subject);
      var cls = 'task-item' + (t.done ? ' done' : '');
      return (
        '<div class="' + cls + '" data-id="' + esc(t.id) + '">' +
          '<label class="row" style="flex:1;align-items:center;gap:8px;cursor:pointer">' +
            '<input type="checkbox" class="plan-toggle" data-id="' + esc(t.id) + '"' +
              (t.done ? ' checked' : '') + '>' +
            '<span class="tag subj-' + esc(t.subject) + '">' + esc(subj) + '</span>' +
            '<span style="flex:1">' + esc(t.title) + '</span>' +
          '</label>' +
          '<span class="muted">' + esc(t.date) + ' · ' + esc(String(t.minutes)) + ' 分钟</span>' +
          '<button class="btn btn-danger btn-sm plan-del" data-id="' + esc(t.id) + '">删除</button>' +
        '</div>'
      );
    }).join('');
  }

  // ---------- 5. 组装整体模板 ----------
  view.innerHTML =
    // 新建任务卡
    '<div class="card">' +
      '<div class="row"><strong>新建任务</strong><span class="spacer"></span></div>' +
      '<div class="form-row">' +
        '<select class="select" id="plan-new-subject">' + subjectOptions + '</select>' +
        '<input class="input" id="plan-new-title" type="text" placeholder="任务标题">' +
        '<input class="input" id="plan-new-date" type="date" value="' + esc(today) + '">' +
        '<input class="input" id="plan-new-minutes" type="number" min="1" step="5" value="60">' +
        '<button class="btn btn-primary" id="plan-add">添加</button>' +
      '</div>' +
    '</div>' +

    // 筛选行
    '<div class="card">' +
      '<div class="row" style="flex-wrap:wrap;gap:8px">' +
        '<button class="btn btn-sm' + (planFilter.dateMode === 'today' ? ' btn-primary' : ' btn-ghost') + '" data-date="today">今天</button>' +
        '<button class="btn btn-sm' + (planFilter.dateMode === 'tomorrow' ? ' btn-primary' : ' btn-ghost') + '" data-date="tomorrow">明天</button>' +
        '<button class="btn btn-sm' + (planFilter.dateMode === 'all' ? ' btn-primary' : ' btn-ghost') + '" data-date="all">全部</button>' +
        '<span class="spacer"></span>' +
        '<select class="select" id="plan-filter-subject">' +
          '<option value="all"' + (planFilter.subject === 'all' ? ' selected' : '') + '>全部科目</option>' +
          SUBJECTS.map(function (s) {
            return '<option value="' + esc(s.id) + '"' +
              (planFilter.subject === s.id ? ' selected' : '') + '>' + esc(s.name) + '</option>';
          }).join('') +
        '</select>' +
      '</div>' +
    '</div>' +

    // 任务列表卡
    '<div class="card">' +
      '<div class="row"><strong>任务列表</strong><span class="spacer"></span>' +
        '<span class="muted">共 ' + totalCount + ' 项</span>' +
      '</div>' +
      listHtml +
    '</div>' +

    // 完成情况卡
    '<div class="card">' +
      '<div class="row"><strong>完成情况</strong><span class="spacer"></span>' +
        '<span class="muted">' + doneCount + '/' + totalCount + ' 项 · ' + percent + '%</span>' +
      '</div>' +
      '<div class="progress"><div class="progress-bar" style="width:' + percent + '%"></div></div>' +
      '<div class="muted" style="margin-top:6px">已完成 ' + doneMinutes + ' 分钟 / 计划 ' + totalMinutes + ' 分钟</div>' +
    '</div>';

  // ---------- 6. 事件绑定（统一在模板插入后处理） ----------

  // 6.1 新建任务
  var addBtn = view.querySelector('#plan-add');
  if (addBtn) {
    addBtn.addEventListener('click', function () {
      var subjectEl = view.querySelector('#plan-new-subject');
      var titleEl = view.querySelector('#plan-new-title');
      var dateEl = view.querySelector('#plan-new-date');
      var minutesEl = view.querySelector('#plan-new-minutes');

      var title = (titleEl.value || '').trim();
      var minutes = parseInt(minutesEl.value, 10);

      if (!title) {
        alert('请输入任务标题');
        titleEl.focus();
        return;
      }
      if (!minutes || minutes <= 0) {
        alert('计划分钟需大于 0');
        minutesEl.focus();
        return;
      }

      if (!Array.isArray(state.tasks)) state.tasks = [];
      state.tasks.push({
        id: uid(),
        subject: subjectEl.value,
        title: title,
        date: dateEl.value || todayStr(),
        minutes: minutes,
        done: false
      });
      saveState();
      renderPlan(view);
    });
  }

  // 6.2 日期快捷按钮
  view.querySelectorAll('[data-date]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      planFilter.dateMode = btn.getAttribute('data-date');
      renderPlan(view);
    });
  });

  // 6.3 科目筛选下拉
  var filterSubj = view.querySelector('#plan-filter-subject');
  if (filterSubj) {
    filterSubj.addEventListener('change', function () {
      planFilter.subject = filterSubj.value;
      renderPlan(view);
    });
  }

  // 6.4 复选框切换完成状态
  view.querySelectorAll('.plan-toggle').forEach(function (cb) {
    cb.addEventListener('change', function () {
      var id = cb.getAttribute('data-id');
      var task = (state.tasks || []).filter(function (t) { return t.id === id; })[0];
      if (task) {
        task.done = cb.checked;
        saveState();
        renderPlan(view);
      }
    });
  });

  // 6.5 删除按钮
  view.querySelectorAll('.plan-del').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-id');
      state.tasks = (state.tasks || []).filter(function (t) { return t.id !== id; });
      saveState();
      renderPlan(view);
    });
  });
}
