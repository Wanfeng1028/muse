// ============ 考研指挥舱 kaoyan-os · 数据层 ============

// ---------- 常量 ----------
const SUBJECTS = [
  { id: 'math',     name: '数学一' },
  { id: 'english',  name: '英语一' },
  { id: 'politics', name: '政治' },
  { id: 'major',    name: '专业课821' }
];
const EXAM_DATE = '2026-12-19';       // 初试日期
const DB_KEY = 'kaoyan_os_v1';        // localStorage 键名

// ---------- 工具函数 ----------
// 生成唯一 id
function uid() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

// 今天 'YYYY-MM-DD'
function todayStr() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// 今天 ± n 天的 'YYYY-MM-DD'
function dateOffset(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// HTML 转义
function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// 根据科目 id 取名称
function subjName(id) {
  const s = SUBJECTS.find(x => x.id === id);
  return s ? s.name : id;
}

// 距初试剩余天数（向上/向下：按自然日差向下取整）
function daysLeft() {
  const now = new Date(todayStr() + 'T00:00:00');
  const exam = new Date(EXAM_DATE + 'T00:00:00');
  const diff = Math.floor((exam - now) / 86400000);
  return diff;
}

// ---------- 全局状态 ----------
let state = {
  tasks: [],
  sessions: [],
  mistakes: [],
  words: [],
  exams: [],
  settings: { focusMin: 25, breakMin: 5 }
};

// ---------- 持久化 ----------
function saveState() {
  try {
    localStorage.setItem(DB_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn('saveState 失败', e);
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(DB_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        state = Object.assign(
          { tasks: [], sessions: [], mistakes: [], words: [], exams: [],
            settings: { focusMin: 25, breakMin: 5 } },
          parsed
        );
        if (!state.settings) state.settings = { focusMin: 25, breakMin: 5 };
        return;
      }
    }
  } catch (e) {
    console.warn('loadState 解析失败，使用种子数据', e);
  }
  state = seedData();
  saveState();
}

// ---------- 种子数据 ----------
function seedData() {
  const d_m1 = dateOffset(-1);
  const d_0  = dateOffset(0);
  const d_p1 = dateOffset(1);

  // --- 任务 8 条，四科覆盖，日期覆盖 -1 / 0 / +1 ---
  const tasks = [
    { id: uid(), subject: 'math',     title: '张宇 1000 题 线性代数第 3 章',     date: d_m1, minutes: 90,  done: true  },
    { id: uid(), subject: 'english',  title: '英语一 2015 年真题阅读精翻',       date: d_m1, minutes: 60,  done: true  },
    { id: uid(), subject: 'major',    title: '821 电路 第 5 章课后题',           date: d_0,  minutes: 120, done: false },
    { id: uid(), subject: 'politics', title: '肖秀荣 1000 题 马原多选第 2 章',   date: d_0,  minutes: 45,  done: true  },
    { id: uid(), subject: 'math',     title: '李永乐 660 题 高数填空 30 道',     date: d_0,  minutes: 60,  done: false },
    { id: uid(), subject: 'english',  title: '背考研核心词汇 List 12 并默写',    date: d_p1, minutes: 30,  done: false },
    { id: uid(), subject: 'politics', title: '徐涛强化班 近代史 第 4 讲',        date: d_p1, minutes: 50,  done: false },
    { id: uid(), subject: 'major',    title: '821 数字电路 时序逻辑设计复盘',    date: d_p1, minutes: 90,  done: false }
  ];

  // --- 专注记录 5 条，过去 5 天 ---
  const sessions = [
    { id: uid(), subject: 'math',     date: dateOffset(-5), minutes: 95  },
    { id: uid(), subject: 'english',  date: dateOffset(-4), minutes: 60  },
    { id: uid(), subject: 'politics', date: dateOffset(-3), minutes: 40  },
    { id: uid(), subject: 'major',    date: dateOffset(-2), minutes: 110 },
    { id: uid(), subject: 'math',     date: dateOffset(-1), minutes: 75  }
  ];

  // --- 错题 4 条 ---
  const mistakes = [
    {
      id: uid(), subject: 'math', title: '矩阵秩的性质用错',
      reason: '概念混淆', detail: '误把 r(AB)=r(A) 当作恒成立，实际只有当 B 可逆时才成立。',
      mastered: false, created: dateOffset(-6)
    },
    {
      id: uid(), subject: 'english', title: '长难句主谓分离没看清',
      reason: '语法结构', detail: '句中插入语过长，把插入语的谓语误当作主句谓语，导致选项判断错误。',
      mastered: false, created: dateOffset(-4)
    },
    {
      id: uid(), subject: 'major', title: '叠加定理独立源处理错误',
      reason: '解题步骤', detail: '使用叠加定理时忘记把电压源短路、电流源开路，直接叠加导致结果偏差。',
      mastered: false, created: dateOffset(-3)
    },
    {
      id: uid(), subject: 'politics', title: '史纲时间节点记混',
      reason: '记忆不清', detail: '把中共七届二中全会和十一届三中全会的时间搞反了，需要重新梳理时间轴。',
      mastered: true, created: dateOffset(-7)
    }
  ];

  // --- 高频词汇 ≥ 36 个，due 分布在 -2 ~ +2 ---
  const wordSeed = [
    ['abandon',      '/əˈbændən/',     'vt. 放弃，抛弃'],
    ['abolish',      '/əˈbɒlɪʃ/',      'vt. 废除，取消'],
    ['abstract',     '/ˈæbstrækt/',    'a. 抽象的 n. 摘要'],
    ['accelerate',   '/əkˈseləreɪt/',  'vt. 加速，促进'],
    ['accommodate',  '/əˈkɒmədeɪt/',   'vt. 容纳，适应'],
    ['accumulate',   '/əˈkjuːmjəleɪt/','v. 积累，积聚'],
    ['accurate',     '/ˈækjərət/',     'a. 精确的，准确的'],
    ['acknowledge',  '/əkˈnɒlɪdʒ/',    'vt. 承认，致谢'],
    ['acquire',      '/əˈkwaɪə(r)/',   'vt. 获得，学到'],
    ['adequate',     '/ˈædɪkwət/',     'a. 充足的，适当的'],
    ['adjust',       '/əˈdʒʌst/',      'v. 调整，适应'],
    ['advocate',     '/ˈædvəkeɪt/',    'vt. 提倡 n. 拥护者'],
    ['aggressive',   '/əˈɡresɪv/',     'a. 侵略的，积极的'],
    ['alter',        '/ˈɔːltə(r)/',    'v. 改变，修改'],
    ['ambiguous',    '/æmˈbɪɡjuəs/',   'a. 模棱两可的'],
    ['ambitious',    '/æmˈbɪʃəs/',     'a. 有雄心的'],
    ['anticipate',   '/ænˈtɪsɪpeɪt/',  'vt. 预期，期望'],
    ['apparent',     '/əˈpærənt/',     'a. 明显的，表面的'],
    ['appreciate',   '/əˈpriːʃieɪt/',  'vt. 感激，欣赏'],
    ['approach',     '/əˈprəʊtʃ/',     'v. 接近 n. 方法'],
    ['appropriate',  '/əˈprəʊpriət/',  'a. 恰当的，合适的'],
    ['approve',      '/əˈpruːv/',      'v. 批准，赞成'],
    ['arbitrary',    '/ˈɑːbɪtrəri/',   'a. 任意的，专断的'],
    ['assess',       '/əˈses/',        'vt. 评估，评定'],
    ['assume',       '/əˈsjuːm/',      'vt. 假定，承担'],
    ['attribute',    '/əˈtrɪbjuːt/',   'vt. 归因于 n. 属性'],
    ['authentic',    '/ɔːˈθentɪk/',    'a. 真实的，可靠的'],
    ['available',    '/əˈveɪləbl/',    'a. 可获得的'],
    ['beneficial',   '/ˌbenɪˈfɪʃl/',   'a. 有益的'],
    ['capable',      '/ˈkeɪpəbl/',     'a. 有能力的'],
    ['cease',        '/siːs/',         'v. 停止，终止'],
    ['coherent',     '/kəʊˈhɪərənt/',  'a. 连贯的，一致的'],
    ['coincide',     '/ˌkəʊɪnˈsaɪd/',  'vi. 同时发生，一致'],
    ['commence',     '/kəˈmens/',      'v. 开始，着手'],
    ['comprehensive','/ˌkɒmprɪˈhensɪv/','a. 全面的，综合的'],
    ['conceive',     '/kənˈsiːv/',     'v. 构想，设想'],
    ['consecutive',  '/kənˈsekjətɪv/', 'a. 连续的'],
    ['constitute',   '/ˈkɒnstɪtjuːt/', 'vt. 构成，组成']
  ];

  const words = wordSeed.map(([w, p, m], i) => {
    // due 从 -2 到 +2 循环分布，保证有到期可复习的
    const off = (i % 5) - 2;
    return {
      id: uid(),
      word: w,
      phonetic: p,
      meaning: m,
      ease: 2.5,
      interval: 0,
      reps: 0,
      due: dateOffset(off)
    };
  });

  // --- 模拟考 3 条 ---
  const exams = [
    { id: uid(), subject: 'english', name: '英语一 2016 年真题',  date: dateOffset(-12), minutes: 180, score: 62,  total: 100 },
    { id: uid(), subject: 'math',    name: '数学一 2019 年真题',  date: dateOffset(-8),  minutes: 180, score: 98,  total: 150 },
    { id: uid(), subject: 'major',   name: '821 2021 年真题',    date: dateOffset(-5),  minutes: 180, score: 105, total: 150 }
  ];

  return {
    tasks,
    sessions,
    mistakes,
    words,
    exams,
    settings: { focusMin: 25, breakMin: 5 }
  };
}

// ---------- 初始化 ----------
loadState();
