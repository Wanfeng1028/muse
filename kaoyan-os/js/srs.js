// js/srs.js —— 考研指挥舱 · 单词 SRS 间隔重复模块（SM-2 简化版）
// 依赖：js/store.js 提供的 SUBJECTS / state / saveState / uid / todayStr / dateOffset / esc
// 全局导出：renderSRS(view)

/* ============ 工具函数 ============ */

// 安全取词表数组（避免 state.words 未初始化）
function srsGetWords() {
  if (!state.words || !Array.isArray(state.words)) state.words = [];
  return state.words;
}

// 计算某词是否为「已掌握」：interval >= 21 天
function srsIsMastered(w) {
  return (w.interval || 0) >= 21;
}

// 是否到期：due <= 今天（字符串比较对 YYYY-MM-DD 有效）
function srsIsDue(w, today) {
  if (!w.due) return true;
  return w.due <= today;
}

// 简易转义（store.js 已有 esc，这里做一层保护性包装）
function srsEsc(s) {
  if (typeof esc === 'function') return esc(s);
  // 兜底实现
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 日期偏移：优先用 store.js 的 dateOffset，否则本地实现
function srsDateOffset(n) {
  if (typeof dateOffset === 'function') return dateOffset(n);
  const d = new Date();
  d.setDate(d.getDate() + (n || 0));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + dd;
}

// 今天的字符串
function srsToday() {
  if (typeof todayStr === 'function') return todayStr();
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + dd;
}

// 唯一 id
function srsUid() {
  if (typeof uid === 'function') return uid();
  return 'w_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

/* ============ 复习算法：SM-2 简化版 ============ */
// grade: 0=不认识 1=模糊 2=认识
// 返回新的 { ease, interval, reps, due }
function srsApplyGrade(word, grade) {
  let ease = typeof word.ease === 'number' ? word.ease : 2.5;
  let interval = typeof word.interval === 'number' ? word.interval : 0;
  let reps = typeof word.reps === 'number' ? word.reps : 0;

  if (grade === 0) {
    // 完全不认识：重置
    reps = 0;
    interval = 1;
    ease = Math.max(1.3, ease - 0.2);
  } else if (grade === 1) {
    // 模糊
    if (reps === 0) {
      interval = 1;
    } else {
      interval = Math.max(1, Math.round(interval * 1.2));
    }
    reps = reps + 1;
    ease = Math.max(1.3, ease - 0.1);
  } else {
    // grade === 2 认识（reps 使用评分前的值）
    if (reps === 0) {
      interval = 1;
    } else if (reps === 1) {
      interval = 3;
    } else {
      interval = Math.round(interval * ease);
    }
    reps = reps + 1;
    ease = Math.min(2.8, ease + 0.05);
  }

  // 保证最小间隔为 1
  if (!interval || interval < 1) interval = 1;

  return {
    ease: ease,
    interval: interval,
    reps: reps,
    due: srsDateOffset(interval)
  };
}

/* ============ 模块内 UI 状态 ============ */
// 当前复习队列的 id 顺序、当前索引、当前卡是否翻面、本次已复习计数
const srsUI = {
  queue: [],        // 待复习词 id 数组
  index: 0,         // 当前卡在队列中的位置
  flipped: false,   // 当前卡是否已翻面
  reviewedCount: 0, // 本次会话已评分数量
  sessionTotal: 0,  // 本次会话开始时的待复习总数
  sortByDue: false, // 词表是否按 due 排序
  inited: false     // 是否已经初始化过会话
};

// 重置/刷新复习队列（仅当队列为空或首次进入时初始化，避免打断复习）
function srsBuildQueue(force) {
  const today = srsToday();
  const words = srsGetWords();
  const dueList = words
    .filter(function (w) { return srsIsDue(w, today); })
    .sort(function (a, b) {
      // 按 due 升序，无 due 的排前
      const da = a.due || '';
      const db = b.due || '';
      if (da < db) return -1;
      if (da > db) return 1;
      return 0;
    });

  if (force || !srsUI.inited || srsUI.queue.length === 0) {
    srsUI.queue = dueList.map(function (w) { return w.id; });
    srsUI.index = 0;
    srsUI.flipped = false;
    srsUI.reviewedCount = 0;
    srsUI.sessionTotal = srsUI.queue.length;
    srsUI.inited = true;
  }
  return dueList;
}

// 根据 id 取词
function srsFindWord(id) {
  const words = srsGetWords();
  for (let i = 0; i < words.length; i++) {
    if (words[i].id === id) return words[i];
  }
  return null;
}

// 当前正在复习的词对象（可能为 null）
function srsCurrentWord() {
  if (srsUI.index >= srsUI.queue.length) return null;
  return srsFindWord(srsUI.queue[srsUI.index]);
}

// 队列里是否还有未复习的卡
function srsHasMore() {
  return srsUI.index < srsUI.queue.length;
}

/* ============ 渲染主入口 ============ */
function renderSRS(view) {
  const root = typeof view === 'string' ? document.querySelector(view) : view;
  if (!root) return;

  const today = srsToday();
  const words = srsGetWords();

  // 首次进入构建队列
  srsBuildQueue(false);

  // 统计信息
  const dueWords = words.filter(function (w) { return srsIsDue(w, today); });
  const dueCount = dueWords.length;
  const masteredCount = words.filter(srsIsMastered).length;
  const totalCount = words.length;

  // 复习进度
  const reviewed = srsUI.reviewedCount;
  const sessionTotal = srsUI.sessionTotal || (reviewed + srsUI.queue.length);
  const progressTotal = Math.max(1, sessionTotal);
  const progressPct = Math.min(100, Math.round((reviewed / progressTotal) * 100));

  // 构建 DOM
  const container = document.createElement('div');
  container.className = 'srs-page';

  /* ---------- 1. 复习区卡 ---------- */
  const reviewCard = document.createElement('div');
  reviewCard.className = 'card srs-review-card';

  // 顶部统计
  const statsLine = document.createElement('div');
  statsLine.className = 'row srs-stats';
  statsLine.innerHTML =
    '<span class="tag">待复习 ' + srsEsc(String(dueCount)) + '</span>' +
    '<span class="tag">已掌握 ' + srsEsc(String(masteredCount)) + '</span>' +
    '<span class="tag">总词数 ' + srsEsc(String(totalCount)) + '</span>';
  reviewCard.appendChild(statsLine);

  // 进度条
  const progressWrap = document.createElement('div');
  progressWrap.className = 'progress';
  const progressBar = document.createElement('div');
  progressBar.className = 'progress-bar';
  progressBar.style.width = progressPct + '%';
  progressWrap.appendChild(progressBar);
  reviewCard.appendChild(progressWrap);

  const progressText = document.createElement('div');
  progressText.className = 'muted srs-progress-text';
  progressText.textContent = '本次复习 ' + reviewed + ' / ' + sessionTotal;
  reviewCard.appendChild(progressText);

  // 当前卡片区域
  const cardArea = document.createElement('div');
  cardArea.className = 'srs-card-area';

  if (!srsHasMore()) {
    // 队列为空 —— 显示完成提示
    const empty = document.createElement('div');
    empty.className = 'empty srs-done';
    if (totalCount === 0) {
      empty.textContent = '词表还是空的，先在下方添加单词吧。';
    } else if (dueCount === 0) {
      empty.textContent = '太棒了，今天没有需要复习的单词！';
    } else {
      empty.textContent = '本轮复习完成，休息一下。';
    }
    cardArea.appendChild(empty);

    // 如果今天还有到期的词（说明是新加进来或算法调整），提供继续按钮
    if (dueCount > 0 && srsUI.reviewedCount > 0) {
      const continueRow = document.createElement('div');
      continueRow.className = 'row srs-continue-row';
      const continueBtn = document.createElement('button');
      continueBtn.className = 'btn btn-primary';
      continueBtn.textContent = '继续复习（还有 ' + dueCount + ' 个）';
      continueBtn.addEventListener('click', function () {
        srsBuildQueue(true);
        renderSRS(root);
      });
      continueRow.appendChild(continueBtn);
      cardArea.appendChild(continueRow);
    }
  } else {
    const cur = srsCurrentWord();
    if (!cur) {
      // 理论不会发生，兜底
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = '没有可复习的单词。';
      cardArea.appendChild(empty);
    } else {
      // flashcard
      const flash = document.createElement('div');
      flash.className = 'flashcard' + (srsUI.flipped ? ' flipped' : '');

      // 正面
      const front = document.createElement('div');
      front.className = 'flashcard-front';
      const wordEl = document.createElement('div');
      wordEl.className = 'flashcard-word';
      wordEl.textContent = cur.word || '';
      front.appendChild(wordEl);
      if (cur.phonetic) {
        const ph = document.createElement('div');
        ph.className = 'flashcard-phonetic muted';
        ph.textContent = cur.phonetic;
        front.appendChild(ph);
      }
      const hint = document.createElement('div');
      hint.className = 'muted srs-flip-hint';
      hint.textContent = srsUI.flipped ? '（点击卡片收起释义）' : '（点击卡片查看释义）';
      front.appendChild(hint);
      flash.appendChild(front);

      // 反面（释义）
      const back = document.createElement('div');
      back.className = 'flashcard-back';
      const meaningEl = document.createElement('div');
      meaningEl.className = 'flashcard-meaning';
      meaningEl.textContent = cur.meaning || '';
      back.appendChild(meaningEl);
      flash.appendChild(back);

      // 点击翻面
      flash.addEventListener('click', function (e) {
        // 避免点到评分按钮时误翻
        if (e && e.target && e.target.closest && e.target.closest('.grade-row')) return;
        srsUI.flipped = !srsUI.flipped;
        if (srsUI.flipped) {
          flash.classList.add('flipped');
        } else {
          flash.classList.remove('flipped');
        }
        // 更新提示文案与评分区显隐
        const hintEl = flash.querySelector('.srs-flip-hint');
        if (hintEl) {
          hintEl.textContent = srsUI.flipped ? '（点击卡片收起释义）' : '（点击卡片查看释义）';
        }
        const gradeRowEl = cardArea.querySelector('.grade-row');
        if (gradeRowEl) {
          gradeRowEl.style.display = srsUI.flipped ? '' : 'none';
        }
      });

      cardArea.appendChild(flash);

      // 评分按钮区（翻面后显示）
      const gradeRow = document.createElement('div');
      gradeRow.className = 'grade-row';
      gradeRow.style.display = srsUI.flipped ? '' : 'none';

      const btn0 = document.createElement('button');
      btn0.className = 'btn btn-danger btn-sm';
      btn0.textContent = '不认识';
      btn0.addEventListener('click', function () { srsGradeCurrent(0, root); });

      const btn1 = document.createElement('button');
      btn1.className = 'btn btn-ghost btn-sm';
      btn1.textContent = '模糊';
      btn1.addEventListener('click', function () { srsGradeCurrent(1, root); });

      const btn2 = document.createElement('button');
      btn2.className = 'btn btn-primary btn-sm';
      btn2.textContent = '认识';
      btn2.addEventListener('click', function () { srsGradeCurrent(2, root); });

      gradeRow.appendChild(btn0);
      gradeRow.appendChild(btn1);
      gradeRow.appendChild(btn2);
      cardArea.appendChild(gradeRow);

      // 当前词的简要信息
      const meta = document.createElement('div');
      meta.className = 'muted srs-word-meta';
      meta.textContent = '间隔 ' + (cur.interval || 0) + ' 天 · 复习次数 ' + (cur.reps || 0) +
        ' · 熟练度 ' + (typeof cur.ease === 'number' ? cur.ease.toFixed(2) : '2.50') +
        ' · 到期 ' + (cur.due || '未设置');
      cardArea.appendChild(meta);
    }
  }

  reviewCard.appendChild(cardArea);
  container.appendChild(reviewCard);

  /* ---------- 2. 添加单词卡 ---------- */
  const addCard = document.createElement('div');
  addCard.className = 'card srs-add-card';

  const addTitle = document.createElement('div');
  addTitle.className = 'srs-section-title';
  addTitle.textContent = '添加单词';
  addCard.appendChild(addTitle);

  const formRow = document.createElement('div');
  formRow.className = 'form-row';

  const inputWord = document.createElement('input');
  inputWord.className = 'input';
  inputWord.type = 'text';
  inputWord.placeholder = '单词';

  const inputPhonetic = document.createElement('input');
  inputPhonetic.className = 'input';
  inputPhonetic.type = 'text';
  inputPhonetic.placeholder = '音标（可选）';

  const inputMeaning = document.createElement('input');
  inputMeaning.className = 'input';
  inputMeaning.type = 'text';
  inputMeaning.placeholder = '释义';

  const addBtn = document.createElement('button');
  addBtn.className = 'btn btn-primary';
  addBtn.textContent = '添加';

  function doAdd() {
    const w = (inputWord.value || '').trim();
    const p = (inputPhonetic.value || '').trim();
    const m = (inputMeaning.value || '').trim();
    if (!w) {
      inputWord.focus();
      return;
    }
    const wordsArr = srsGetWords();
    const newWord = {
      id: srsUid(),
      word: w,
      phonetic: p,
      meaning: m,
      ease: 2.5,
      interval: 0,
      reps: 0,
      due: srsToday()
    };
    wordsArr.push(newWord);
    if (typeof saveState === 'function') saveState();
    // 清空输入
    inputWord.value = '';
    inputPhonetic.value = '';
    inputMeaning.value = '';
    // 重新构建队列（新词到期，会被加入）
    srsBuildQueue(true);
    renderSRS(root);
    inputWord.focus();
  }

  addBtn.addEventListener('click', doAdd);
  inputWord.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); inputPhonetic.focus(); }
  });
  inputPhonetic.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); inputMeaning.focus(); }
  });
  inputMeaning.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
  });

  formRow.appendChild(inputWord);
  formRow.appendChild(inputPhonetic);
  formRow.appendChild(inputMeaning);
  formRow.appendChild(addBtn);
  addCard.appendChild(formRow);
  container.appendChild(addCard);

  /* ---------- 3. 词表卡 ---------- */
  const listCard = document.createElement('div');
  listCard.className = 'card srs-list-card';

  const listHeader = document.createElement('div');
  listHeader.className = 'row srs-list-header';

  const listTitle = document.createElement('div');
  listTitle.className = 'srs-section-title';
  listTitle.textContent = '词表（' + totalCount + '）';
  listHeader.appendChild(listTitle);

  const sortBtn = document.createElement('button');
  sortBtn.className = 'btn btn-ghost btn-sm';
  sortBtn.textContent = srsUI.sortByDue ? '按添加顺序' : '按到期排序';
  sortBtn.addEventListener('click', function () {
    srsUI.sortByDue = !srsUI.sortByDue;
    renderSRS(root);
  });
  listHeader.appendChild(sortBtn);

  listCard.appendChild(listHeader);

  if (totalCount === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '暂无单词。';
    listCard.appendChild(empty);
  } else {
    // 排序副本
    const listWords = words.slice();
    if (srsUI.sortByDue) {
      listWords.sort(function (a, b) {
        const da = a.due || '';
        const db = b.due || '';
        if (da < db) return -1;
        if (da > db) return 1;
        return 0;
      });
    }

    const table = document.createElement('table');
    table.className = 'table srs-table';

    const thead = document.createElement('thead');
    thead.innerHTML =
      '<tr>' +
      '<th>单词</th>' +
      '<th>释义</th>' +
      '<th>间隔(天)</th>' +
      '<th>次数</th>' +
      '<th>到期</th>' +
      '<th></th>' +
      '</tr>';
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    listWords.forEach(function (w) {
      const tr = document.createElement('tr');

      const tdWord = document.createElement('td');
      tdWord.textContent = w.word || '';
      tr.appendChild(tdWord);

      const tdMeaning = document.createElement('td');
      tdMeaning.textContent = w.meaning || '';
      tr.appendChild(tdMeaning);

      const tdInterval = document.createElement('td');
      tdInterval.textContent = String(w.interval || 0);
      tr.appendChild(tdInterval);

      const tdReps = document.createElement('td');
      tdReps.textContent = String(w.reps || 0);
      tr.appendChild(tdReps);

      const tdDue = document.createElement('td');
      tdDue.textContent = w.due || '';
      if (w.due && w.due <= today) {
        tdDue.classList.add('srs-due-now');
      }
      tr.appendChild(tdDue);

      const tdOps = document.createElement('td');
      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-danger btn-sm';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', function () {
        const wordsArr = srsGetWords();
        for (let i = 0; i < wordsArr.length; i++) {
          if (wordsArr[i].id === w.id) {
            wordsArr.splice(i, 1);
            break;
          }
        }
        // 从复习队列中移除
        const qi = srsUI.queue.indexOf(w.id);
        if (qi !== -1) {
          srsUI.queue.splice(qi, 1);
          if (qi < srsUI.index) srsUI.index--;
          if (srsUI.index < 0) srsUI.index = 0;
        }
        if (typeof saveState === 'function') saveState();
        renderSRS(root);
      });
      tdOps.appendChild(delBtn);
      tr.appendChild(tdOps);

      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    listCard.appendChild(table);
  }

  container.appendChild(listCard);

  // 挂载
  root.innerHTML = '';
  root.appendChild(container);
}

/* ============ 评分处理 ============ */
function srsGradeCurrent(grade, root) {
  const cur = srsCurrentWord();
  if (!cur) return;

  const updated = srsApplyGrade(cur, grade);
  cur.ease = updated.ease;
  cur.interval = updated.interval;
  cur.reps = updated.reps;
  cur.due = updated.due;

  if (typeof saveState === 'function') saveState();

  // 推进队列
  srsUI.reviewedCount += 1;
  srsUI.index += 1;
  srsUI.flipped = false;

  // 如果队列已走完，检查是否还有新的到期词（例如刚才算法调整后的）
  if (!srsHasMore()) {
    const today = srsToday();
    const stillDue = srsGetWords().filter(function (w) { return srsIsDue(w, today); });
    if (stillDue.length > 0) {
      // 重建队列但保留已复习计数
      const prevReviewed = srsUI.reviewedCount;
      srsUI.queue = stillDue.map(function (w) { return w.id; });
      srsUI.index = 0;
      srsUI.flipped = false;
      srsUI.reviewedCount = prevReviewed;
      srsUI.sessionTotal = prevReviewed + srsUI.queue.length;
    }
  }

  renderSRS(root);
}
