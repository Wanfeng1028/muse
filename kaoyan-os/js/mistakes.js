/* 错题本模块：录入、筛选、列表展示与掌握状态管理 */

// 模块级筛选状态（不持久化，仅当前会话有效）
var _mistakesFilter = {
  subject: '',
  status: '',
  keyword: ''
};

// 展开详情的错题 id 集合
var _mistakesExpanded = {};

/**
 * 渲染错题本主视图
 * @param {HTMLElement} view 容器元素
 */
function renderMistakes(view) {
  var list = state.mistakes || [];

  // ========== 统计计算 ==========
  var total = list.length;
  var unmastered = 0;
  var mastered = 0;
  for (var i = 0; i < list.length; i++) {
    if (list[i].mastered) mastered++;
    else unmastered++;
  }
  var rate = total > 0 ? Math.round((mastered / total) * 100) : 0;

  // ========== 筛选后列表 ==========
  var filtered = [];
  for (var j = 0; j < list.length; j++) {
    var m = list[j];
    // 科目筛选
    if (_mistakesFilter.subject && m.subject !== _mistakesFilter.subject) continue;
    // 状态筛选
    if (_mistakesFilter.status === 'unmastered' && m.mastered) continue;
    if (_mistakesFilter.status === 'mastered' && !m.mastered) continue;
    // 关键词搜索（标题/错因）
    if (_mistakesFilter.keyword) {
      var kw = _mistakesFilter.keyword.toLowerCase();
      var t = (m.title || '').toLowerCase();
      var r = (m.reason || '').toLowerCase();
      if (t.indexOf(kw) === -1 && r.indexOf(kw) === -1) continue;
    }
    filtered.push(m);
  }

  // ========== 构建 HTML ==========
  var html = '';

  // --- 顶部统计 ---
  html += '<div class="card" style="margin-bottom:12px">';
  html += '<div class="row">';
  html += '<div><strong>错题本</strong></div>';
  html += '<div class="spacer"></div>';
  html += '<span class="tag">总数 ' + total + '</span> ';
  html += '<span class="tag">未掌握 ' + unmastered + '</span> ';
  html += '<span class="tag">掌握率 ' + rate + '%</span>';
  html += '</div>';
  html += '</div>';

  // --- 录入错题卡 ---
  html += '<div class="card" style="margin-bottom:12px">';
  html += '<div style="margin-bottom:8px"><strong>录入错题</strong></div>';
  html += '<div class="form-row">';
  html += '<select class="select" id="mk-subject">';
  for (var s = 0; s < SUBJECTS.length; s++) {
    html += '<option value="' + esc(SUBJECTS[s].id) + '">' + esc(SUBJECTS[s].name) + '</option>';
  }
  html += '</select>';
  html += '<input class="input" id="mk-title" placeholder="题目标题（必填）" style="flex:1">';
  html += '<input class="input" id="mk-reason" placeholder="错因（如：概念不清/计算失误）" style="flex:1">';
  html += '</div>';
  html += '<textarea class="textarea" id="mk-detail" placeholder="详细记录：题目、思路、正确答案、反思……" style="margin-top:8px;width:100%" rows="3"></textarea>';
  html += '<div class="row" style="margin-top:8px">';
  html += '<div class="spacer"></div>';
  html += '<button class="btn btn-primary" id="mk-save">保存错题</button>';
  html += '</div>';
  html += '</div>';

  // --- 筛选行 ---
  html += '<div class="card" style="margin-bottom:12px">';
  html += '<div class="form-row">';
  html += '<select class="select" id="mk-f-subject">';
  html += '<option value="">全部科目</option>';
  for (var s2 = 0; s2 < SUBJECTS.length; s2++) {
    var selSubj = _mistakesFilter.subject === SUBJECTS[s2].id ? ' selected' : '';
    html += '<option value="' + esc(SUBJECTS[s2].id) + '"' + selSubj + '>' + esc(SUBJECTS[s2].name) + '</option>';
  }
  html += '</select>';
  html += '<select class="select" id="mk-f-status">';
  html += '<option value="">全部状态</option>';
  html += '<option value="unmastered"' + (_mistakesFilter.status === 'unmastered' ? ' selected' : '') + '>未掌握</option>';
  html += '<option value="mastered"' + (_mistakesFilter.status === 'mastered' ? ' selected' : '') + '>已掌握</option>';
  html += '</select>';
  html += '<input class="input" id="mk-f-keyword" placeholder="搜索标题/错因" style="flex:1" value="' + esc(_mistakesFilter.keyword) + '">';
  html += '</div>';
  html += '</div>';

  // --- 错题列表 ---
  html += '<div class="card">';
  html += '<div style="margin-bottom:8px"><strong>错题列表</strong> <span class="muted">（' + filtered.length + ' 条）</span></div>';

  if (filtered.length === 0) {
    html += '<div class="empty">暂无错题，去录入第一道吧 ✍️</div>';
  } else {
    // 按创建日期倒序（新的在前）
    filtered.sort(function (a, b) {
      if (a.created === b.created) return 0;
      return a.created < b.created ? 1 : -1;
    });

    for (var k = 0; k < filtered.length; k++) {
      var item = filtered[k];
      var faded = item.mastered ? ' style="opacity:0.55"' : '';
      var expanded = !!_mistakesExpanded[item.id];

      html += '<div class="row" data-mk-row="' + esc(item.id) + '"' + faded + ' style="border-bottom:1px solid #eee;padding:8px 0;align-items:flex-start">';

      // 左侧信息
      html += '<div style="flex:1;min-width:0">';
      html += '<div class="row" style="flex-wrap:wrap;gap:6px">';
      html += '<span class="tag subj-' + esc(item.subject) + '">' + esc(subjName(item.subject)) + '</span>';
      html += '<strong>' + esc(item.title || '(无标题)') + '</strong>';
      if (item.reason) {
        html += '<span class="tag">' + esc(item.reason) + '</span>';
      }
      html += '<span class="muted" style="font-size:12px">' + esc(item.created || '') + '</span>';
      if (item.mastered) {
        html += '<span class="tag" style="background:#d4edda;color:#155724">已掌握</span>';
      }
      html += '</div>';

      // 折叠详情
      if (expanded && item.detail) {
        html += '<div class="muted" style="margin-top:6px;white-space:pre-wrap;font-size:13px">' + esc(item.detail) + '</div>';
      }

      html += '</div>';

      // 右侧操作按钮
      html += '<div class="row" style="gap:4px;flex-shrink:0">';
      if (item.detail) {
        html += '<button class="btn btn-ghost btn-sm" data-mk-toggle="' + esc(item.id) + '">' + (expanded ? '收起' : '详情') + '</button>';
      }
      if (item.mastered) {
        html += '<button class="btn btn-ghost btn-sm" data-mk-master="' + esc(item.id) + '">取消掌握</button>';
      } else {
        html += '<button class="btn btn-sm" data-mk-master="' + esc(item.id) + '">标记已掌握</button>';
      }
      html += '<button class="btn btn-danger btn-sm" data-mk-del="' + esc(item.id) + '">删除</button>';
      html += '</div>';

      html += '</div>';
    }
  }

  html += '</div>';

  view.innerHTML = html;

  // ========== 事件绑定 ==========
  bindMistakesEvents(view);
}

/**
 * 绑定错题本内所有事件
 * @param {HTMLElement} view
 */
function bindMistakesEvents(view) {
  // --- 保存错题 ---
  var saveBtn = view.querySelector('#mk-save');
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      var subjectEl = view.querySelector('#mk-subject');
      var titleEl = view.querySelector('#mk-title');
      var reasonEl = view.querySelector('#mk-reason');
      var detailEl = view.querySelector('#mk-detail');

      var title = (titleEl.value || '').trim();
      if (!title) {
        alert('请填写题目标题');
        titleEl.focus();
        return;
      }

      var item = {
        id: uid(),
        subject: subjectEl.value,
        title: title,
        reason: (reasonEl.value || '').trim(),
        detail: (detailEl.value || '').trim(),
        mastered: false,
        created: todayStr()
      };

      if (!state.mistakes) state.mistakes = [];
      state.mistakes.push(item);
      saveState();
      renderMistakes(view);
    });
  }

  // --- 筛选：科目 ---
  var fSubject = view.querySelector('#mk-f-subject');
  if (fSubject) {
    fSubject.addEventListener('change', function () {
      _mistakesFilter.subject = this.value;
      renderMistakes(view);
    });
  }

  // --- 筛选：状态 ---
  var fStatus = view.querySelector('#mk-f-status');
  if (fStatus) {
    fStatus.addEventListener('change', function () {
      _mistakesFilter.status = this.value;
      renderMistakes(view);
    });
  }

  // --- 筛选：关键词（输入时即时过滤） ---
  var fKeyword = view.querySelector('#mk-f-keyword');
  if (fKeyword) {
    fKeyword.addEventListener('input', function () {
      _mistakesFilter.keyword = this.value || '';
      // 保留焦点与光标位置，简单做法：只重渲染列表部分会复杂，直接重渲染后恢复焦点
      var pos = this.selectionStart;
      renderMistakes(view);
      var newInput = view.querySelector('#mk-f-keyword');
      if (newInput) {
        newInput.focus();
        try { newInput.setSelectionRange(pos, pos); } catch (e) {}
      }
    });
  }

  // --- 列表操作：详情切换 ---
  var toggleBtns = view.querySelectorAll('[data-mk-toggle]');
  for (var i = 0; i < toggleBtns.length; i++) {
    toggleBtns[i].addEventListener('click', function () {
      var id = this.getAttribute('data-mk-toggle');
      _mistakesExpanded[id] = !_mistakesExpanded[id];
      renderMistakes(view);
    });
  }

  // --- 列表操作：标记掌握/取消掌握 ---
  var masterBtns = view.querySelectorAll('[data-mk-master]');
  for (var j = 0; j < masterBtns.length; j++) {
    masterBtns[j].addEventListener('click', function () {
      var id = this.getAttribute('data-mk-master');
      var arr = state.mistakes || [];
      for (var n = 0; n < arr.length; n++) {
        if (arr[n].id === id) {
          arr[n].mastered = !arr[n].mastered;
          break;
        }
      }
      saveState();
      renderMistakes(view);
    });
  }

  // --- 列表操作：删除 ---
  var delBtns = view.querySelectorAll('[data-mk-del]');
  for (var k = 0; k < delBtns.length; k++) {
    delBtns[k].addEventListener('click', function () {
      var id = this.getAttribute('data-mk-del');
      if (!confirm('确定删除这道错题吗？')) return;
      var arr = state.mistakes || [];
      var next = [];
      for (var n = 0; n < arr.length; n++) {
        if (arr[n].id !== id) next.push(arr[n]);
      }
      state.mistakes = next;
      saveState();
      renderMistakes(view);
    });
  }
}
