import type { DatabaseSync } from 'node:sqlite';
import { DEFAULT_SETTINGS, type SubjectKey } from '@kaoyan/shared';
import { addDays, nowIso, todayStr } from './db';

/**
 * 当各表为空时写入示例数据。
 */
export function seedIfEmpty(db: DatabaseSync): void {
  const today = todayStr();
  const now = nowIso();

  // 1) settings 表为空时写入默认设置
  const settingsCount = db.prepare('SELECT COUNT(*) AS c FROM settings').get() as { c: number };
  if (settingsCount.c === 0) {
    const insertSetting = db.prepare('INSERT INTO settings (key, value) VALUES (?, ?)');
    insertSetting.run('exam_date', DEFAULT_SETTINGS.examDate);
    insertSetting.run('daily_goal_minutes', String(DEFAULT_SETTINGS.dailyGoalMinutes));
    insertSetting.run('pomodoro_minutes', String(DEFAULT_SETTINGS.pomodoroMinutes));
    insertSetting.run('break_minutes', String(DEFAULT_SETTINGS.breakMinutes));
  }

  // 2) words 表为空时插入 24 个考研核心单词并初始化 srs_state
  const wordsCount = db.prepare('SELECT COUNT(*) AS c FROM words').get() as { c: number };
  if (wordsCount.c === 0) {
    const wordList: Array<{ word: string; phonetic: string; meaning: string; example: string }> = [
      { word: 'abandon', phonetic: '/əˈbændən/', meaning: '抛弃；放弃', example: 'He abandoned his car in the snow and walked home.' },
      { word: 'abstract', phonetic: '/ˈæbstrækt/', meaning: '抽象的；摘要', example: 'The concept is too abstract for beginners to grasp.' },
      { word: 'accumulate', phonetic: '/əˈkjuːmjəleɪt/', meaning: '积累；积聚', example: 'Dust had accumulated on the old books over the years.' },
      { word: 'adequate', phonetic: '/ˈædɪkwət/', meaning: '足够的；适当的', example: 'The room was small but adequate for our needs.' },
      { word: 'ambiguous', phonetic: '/æmˈbɪɡjuəs/', meaning: '模糊的；有歧义的', example: 'His answer was ambiguous and left everyone confused.' },
      { word: 'anticipate', phonetic: '/ænˈtɪsɪpeɪt/', meaning: '预期；预料', example: 'We anticipate a rise in demand during the holidays.' },
      { word: 'arbitrary', phonetic: '/ˈɑːbɪtrəri/', meaning: '任意的；武断的', example: 'The decision seemed arbitrary and lacked any clear reason.' },
      { word: 'assess', phonetic: '/əˈses/', meaning: '评估；评定', example: 'Teachers assess students through both exams and projects.' },
      { word: 'compensate', phonetic: '/ˈkɒmpenseɪt/', meaning: '补偿；弥补', example: 'The company compensated workers for the extra hours.' },
      { word: 'comprehensive', phonetic: '/ˌkɒmprɪˈhensɪv/', meaning: '全面的；综合的', example: 'She gave a comprehensive report on the project.' },
      { word: 'constitute', phonetic: '/ˈkɒnstɪtjuːt/', meaning: '构成；组成', example: 'Women constitute more than half of the workforce.' },
      { word: 'controversial', phonetic: '/ˌkɒntrəˈvɜːʃl/', meaning: '有争议的', example: 'The new policy proved highly controversial among citizens.' },
      { word: 'deliberate', phonetic: '/dɪˈlɪbərət/', meaning: '故意的；深思熟虑的', example: 'It was a deliberate attempt to mislead the public.' },
      { word: 'diminish', phonetic: '/dɪˈmɪnɪʃ/', meaning: '减少；降低', example: 'His influence diminished after the scandal.' },
      { word: 'elaborate', phonetic: '/ɪˈlæbərət/', meaning: '详尽的；精心制作的', example: 'She gave an elaborate explanation of the process.' },
      { word: 'equivalent', phonetic: '/ɪˈkwɪvələnt/', meaning: '等同的；相当的', example: 'One mile is equivalent to about 1.6 kilometers.' },
      { word: 'explicit', phonetic: '/ɪkˈsplɪsɪt/', meaning: '明确的；清楚的', example: 'The instructions were explicit and easy to follow.' },
      { word: 'fundamental', phonetic: '/ˌfʌndəˈmentl/', meaning: '基本的；根本的', example: 'Trust is fundamental to any healthy relationship.' },
      { word: 'hypothesis', phonetic: '/haɪˈpɒθəsɪs/', meaning: '假设；假说', example: 'The experiment was designed to test the hypothesis.' },
      { word: 'inevitable', phonetic: '/ɪnˈevɪtəbl/', meaning: '不可避免的', example: 'With so little preparation, failure was inevitable.' },
      { word: 'integrate', phonetic: '/ˈɪntɪɡreɪt/', meaning: '整合；使融合', example: 'The software integrates data from several sources.' },
      { word: 'manipulate', phonetic: '/məˈnɪpjuleɪt/', meaning: '操纵；控制', example: 'He tried to manipulate the results to his advantage.' },
      { word: 'preliminary', phonetic: '/prɪˈlɪmɪnəri/', meaning: '初步的；预备的', example: 'Preliminary results suggest the treatment is effective.' },
      { word: 'subsequent', phonetic: '/ˈsʌbsɪkwənt/', meaning: '随后的；后来的', example: 'Subsequent events proved him right.' },
    ];

    const insertWord = db.prepare(
      'INSERT INTO words (word, phonetic, meaning, example, source) VALUES (?, ?, ?, ?, ?)'
    );
    const insertSrs = db.prepare(
      'INSERT INTO srs_state (word_id, ease, interval_days, repetitions, due_date) VALUES (?, ?, ?, ?, ?)'
    );

    for (const w of wordList) {
      const result = insertWord.run(w.word, w.phonetic, w.meaning, w.example, 'builtin');
      const wordId = Number(result.lastInsertRowid);
      insertSrs.run(wordId, 2.5, 0, 0, today);
    }
  }

  // 3) plans 表为空时插入 6 条今天的示例计划
  const plansCount = db.prepare('SELECT COUNT(*) AS c FROM plans').get() as { c: number };
  if (plansCount.c === 0) {
    const planList: Array<{ subject: SubjectKey; title: string; plannedMinutes: number; done: number }> = [
      { subject: 'math', title: '高数极限与连续练习', plannedMinutes: 90, done: 1 },
      { subject: 'english', title: '考研核心词汇背诵', plannedMinutes: 45, done: 1 },
      { subject: 'politics', title: '马原哲学部分精讲', plannedMinutes: 60, done: 0 },
      { subject: 'major', title: '信号与系统第3章', plannedMinutes: 120, done: 0 },
      { subject: 'math', title: '线性代数行列式复习', plannedMinutes: 75, done: 0 },
      { subject: 'english', title: '阅读理解真题一篇', plannedMinutes: 50, done: 0 },
    ];

    const insertPlan = db.prepare(
      'INSERT INTO plans (date, subject, title, planned_minutes, done, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    );
    for (const p of planList) {
      insertPlan.run(today, p.subject, p.title, p.plannedMinutes, p.done, now);
    }
  }

  // 4) mistakes 表为空时插入 3 条示例错题
  const mistakesCount = db.prepare('SELECT COUNT(*) AS c FROM mistakes').get() as { c: number };
  if (mistakesCount.c === 0) {
    const mistakeList: Array<{
      subject: SubjectKey;
      title: string;
      content: string;
      analysis: string;
    }> = [
      {
        subject: 'math',
        title: '极限计算：0/0 型未定式',
        content: '求 lim(x→0) (sin x − x) / x³。',
        analysis: '使用泰勒展开：sin x = x − x³/6 + o(x³)，代入得极限为 −1/6。常见错误是直接用等价无穷小替换 sin x ≈ x，导致结果为 0，忽略了更高阶项。',
      },
      {
        subject: 'english',
        title: '长难句结构分析',
        content: 'The idea that the process of learning itself, rather than the mere accumulation of facts, is what matters most has gradually gained acceptance among educators.',
        analysis: '主干为 "The idea ... has gradually gained acceptance"。that 引导同位语从句解释 idea，从句主语为 "the process of learning itself"，rather than 结构作对比插入，what matters most 为表语从句。易错点在于把 rather than 误作并列连词。',
      },
      {
        subject: 'major',
        title: '信号与系统：卷积积分',
        content: '已知 x(t) = e^(−2t)u(t)，h(t) = u(t)，求 y(t) = x(t) * h(t)。',
        analysis: 'y(t) = ∫₀^t e^(−2τ) dτ = (1 − e^(−2t))/2 · u(t)。易错点是积分上限判断错误，忘记 u(t) 对积分区间的约束导致结果不符因果性。',
      },
    ];

    const insertMistake = db.prepare(
      'INSERT INTO mistakes (subject, title, content, analysis, mastered, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    );
    for (const m of mistakeList) {
      insertMistake.run(m.subject, m.title, m.content, m.analysis, 0, now);
    }
  }

  // 5) exam_records 表为空时插入 2 条真题模拟记录
  const examsCount = db.prepare('SELECT COUNT(*) AS c FROM exam_records').get() as { c: number };
  if (examsCount.c === 0) {
    const insertExam = db.prepare(
      'INSERT INTO exam_records (subject, paper, score, total_score, duration_minutes, taken_at) VALUES (?, ?, ?, ?, ?, ?)'
    );
    insertExam.run('math', '2025 年真题模拟', 118, 150, 180, addDays(today, -5));
    insertExam.run('english', '英语一 2024 年真题', 72, 100, 180, addDays(today, -10));
  }

  // 6) focus_sessions 表为空时插入 9 条专注记录（过去 6 天各 1 条 + 今天 2 条）
  const focusCount = db.prepare('SELECT COUNT(*) AS c FROM focus_sessions').get() as { c: number };
  if (focusCount.c === 0) {
    const insertFocus = db.prepare(
      'INSERT INTO focus_sessions (subject, minutes, started_at, note) VALUES (?, ?, ?, ?)'
    );

    const pastSessions: Array<{ subject: SubjectKey; minutes: number; note: string }> = [
      { subject: 'math', minutes: 120, note: '高数强化' },
      { subject: 'english', minutes: 60, note: '单词与阅读' },
      { subject: 'politics', minutes: 75, note: '马原精讲' },
      { subject: 'major', minutes: 180, note: '专业课系统复习' },
      { subject: 'math', minutes: 90, note: '概率论练习' },
      { subject: 'english', minutes: 70, note: '真题精读' },
    ];

    for (let i = 0; i < pastSessions.length; i++) {
      const day = addDays(today, -(6 - i));
      const s = pastSessions[i];
      insertFocus.run(s.subject, s.minutes, `${day}T09:00:00`, s.note);
    }

    insertFocus.run('math', 95, `${today}T09:00:00`, '高数极限练习');
    insertFocus.run('major', 130, `${today}T14:00:00`, '信号与系统第3章');
  }
}
