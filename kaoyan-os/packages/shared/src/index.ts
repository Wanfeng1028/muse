// 考研指挥舱 —— 前后端共享类型契约

/** 应用名称 */
export const APP_NAME = "考研指挥舱";

/** 科目列表（唯一数据源） */
export const SUBJECTS = [
  { key: 'math', name: '数学', color: '#4f7cff' },
  { key: 'english', name: '英语', color: '#22b07d' },
  { key: 'politics', name: '政治', color: '#e05d5d' },
  { key: 'major', name: '专业课821', color: '#f0a13c' },
] as const;

/** 科目 key 联合类型 */
export type SubjectKey = 'math' | 'english' | 'politics' | 'major';

/** 判断字符串是否为合法科目 key */
export function isSubjectKey(v: unknown): v is SubjectKey {
  return v === 'math' || v === 'english' || v === 'politics' || v === 'major';
}

/** 学习计划 */
export interface Plan {
  id: number;
  date: string;
  subject: SubjectKey;
  title: string;
  plannedMinutes: number;
  done: boolean;
  createdAt: string;
}

/** 智能排期输入 */
export interface AutoScheduleInput {
  subjects: SubjectKey[];
  dailyMinutes: number;
  examDate: string;
  startDate?: string;
}
/** 智能排期条目（预览用，不写库） */
export interface AutoScheduleItem {
  date: string;
  subject: SubjectKey;
  title: string;
  plannedMinutes: number;
  kind: 'new' | 'review';
}
/** 智能排期结果 */
export interface AutoScheduleResult {
  created: number;
  skipped: number;
  discarded: number;
  items: Plan[];
}

/** 创建计划输入 */
export interface CreatePlanInput {
  date: string;
  subject: SubjectKey;
  title: string;
  plannedMinutes: number;
}

/** 更新计划输入 */
export type UpdatePlanInput = Partial<CreatePlanInput & { done: boolean }>;

/** 周报统计 */
export interface WeeklyStats {
  weekStart: string; // 周一 YYYY-MM-DD
  weekEnd: string; // 下周一 YYYY-MM-DD（开区间）
  focusMinutes: number;
  focusBySubject: Record<SubjectKey, number>;
  focusMinutesByDay: number[]; // 7 个数：周一..周日每日专注分钟（与 focusMinutes 口径一致）
  currentStreak: number; // 连续打卡天数：今日有专注则从今日往前数，否则从昨日往前数
  plansTotal: number;
  plansDone: number;
  wordsTotal: number;
  wordsLearned: number;  // srs_state.repetitions > 0 的词数（累计）
  wordsDue: number;      // due_date <= 今天的词数
  mistakesNew: number;   // 本周新增错题（created_at >= weekStart）
  mistakesUnmastered: number; // 全部未掌握错题数
  examsTaken: number;    // 本周模考场次（taken_at >= weekStart 且 < weekEnd）
}

/** 专注会话 */
export interface FocusSession {
  id: number;
  subject: SubjectKey;
  minutes: number;
  startedAt: string;
  note: string | null;
  planId: number | null;
}

/** 创建专注输入 */
export interface CreateFocusInput {
  subject: SubjectKey;
  minutes: number;
  startedAt?: string;
  note?: string;
  planId?: number;
}

/** 单日专注统计 */
export interface FocusDayStat {
  date: string;
  minutes: number;
}

/** 专注统计汇总 */
export interface FocusStats {
  days: FocusDayStat[];
  todayMinutes: number;
  weekMinutes: number;
  totalMinutes: number;
}

export interface FocusSubjectSummary {
  subject: SubjectKey;
  sessions: number;
  totalMinutes: number;
}

export interface FocusBySubjectResponse {
  subjects: FocusSubjectSummary[];
}

/** 计划完成情况汇总 */
/** 单条计划的执行进度（计划分钟 vs 实际专注分钟） */
export interface PlanProgress {
  id: number;
  title: string;
  subject: SubjectKey;
  plannedMinutes: number;
  actualMinutes: number;
  done: boolean;
}

export interface PlanSummary {
  date: string;
  total: number;
  done: number;
  completionRate: number;
  plans: PlanProgress[];
}

export interface OverduePlansResponse {
  date: string;
  count: number;
  plans: Plan[];
}

/** 排期区间查询参数 */
export interface PlansRangeQuery { from: string; to: string; }
/** 单日负荷 */
export interface DayLoadItem { id: number; date: string; subject: SubjectKey; title: string; plannedMinutes: number; kind: 'new' | 'review' | 'manual'; done: boolean; }
export interface DayLoad { date: string; items: DayLoadItem[]; totalMinutes: number; overloaded: boolean; }
/** 周负荷预警响应 */
export interface OverloadResponse { weekStart: string; weekEnd: string; dailyMinutes: number; overloadedDays: number; days: DayLoad[]; }

/** 错题 */
export interface Mistake {
  id: number;
  subject: SubjectKey;
  title: string;
  content: string;
  analysis: string;
  mastered: boolean;
  createdAt: string;
}

/** 创建错题输入 */
export interface CreateMistakeInput {
  subject: SubjectKey;
  title: string;
  content: string;
  analysis: string;
}

/** 更新错题输入 */
export type UpdateMistakeInput = Partial<CreateMistakeInput & { mastered: boolean }>;

/** 单词来源 */
export type WordSource = 'builtin' | 'core500' | 'manual' | 'csv';

/** 单词来源中文名 */
export const WORD_SOURCES: Record<WordSource, string> = {
  builtin: '内置种子',
  core500: '核心500词库',
  manual: '手动录入',
  csv: 'CSV导入',
};

/** 单词 */
export interface Word {
  id: number;
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
  source: WordSource;
  memory_tip?: string;
}

/** 创建单词输入 */
export type CreateWordInput = Omit<Word, 'id' | 'source'>;

/** 记忆曲线状态 */
export interface SrsState {
  wordId: number;
  ease: number;
  intervalDays: number;
  repetitions: number;
  dueDate: string;
}

/** 带记忆状态的单词 */
export type WordWithState = Word & { state: SrsState };

/** 按来源的单词汇总 */
export interface WordSourceSummary {
  source: WordSource;
  total: number;
  due: number;
  notStarted: number;
}

export interface WordsBySourceResponse {
  sources: WordSourceSummary[];
}

/** 复习评分（0=忘记，1=模糊，2=熟悉） */
export type ReviewGrade = 0 | 1 | 2;

/** 模考记录 */
export interface ExamRecord {
  id: number;
  subject: SubjectKey;
  paper: string;
  score: number;
  totalScore: number;
  durationMinutes: number;
  takenAt: string;
}

/** 创建模考输入 */
export interface CreateExamInput {
  subject: SubjectKey;
  paper: string;
  score: number;
  totalScore: number;
  durationMinutes: number;
  takenAt?: string;
}

/** 模考趋势点 */
export interface ExamTrendPoint {
takenAt: string;
paper: string;
score: number;
totalScore: number;
rate: number;
}

/** 真题汇总 */
export interface ExamSummary {
subject: string | null;
count: number;
avgScore: number;
avgRate: number;
bestScore: number;
bestTakenAt: string;
latestScore: number;
latestTakenAt: string;
firstScore: number;
firstTakenAt: string;
improvement: number;
}

/** 真题分科汇总 */
export interface ExamSubjectSummary {
  subject: SubjectKey;
  count: number;
  avgScore: number;
  avgRate: number;
  bestScore: number;
  bestTakenAt: string;
  latestScore: number;
  latestTakenAt: string;
  firstScore: number;
  firstTakenAt: string;
  improvement: number;
}
export interface ExamsBySubjectResponse {
  subjects: ExamSubjectSummary[];
}

/** 主题模式 */
export type ThemeMode = 'light' | 'dark';

/** 全局设置 */
export interface Settings {
  examDate: string;
  dailyGoalMinutes: number;
  pomodoroMinutes: number;
  breakMinutes: number;
  theme: ThemeMode;
}

/** 默认设置 */
export const DEFAULT_SETTINGS = {
  examDate: '2026-12-19',
  dailyGoalMinutes: 300,
  pomodoroMinutes: 25,
  breakMinutes: 5,
  theme: 'light',
} as const;

/** 热力图单日聚合 */
export interface HeatmapDay {
  date: string;
  focusMinutes: number;
  plansTotal: number;
  plansDone: number;
  mistakesNew: number;
  examsTaken: number;
}

/** 热力图响应 */
export interface HeatmapResponse {
  months: number;
  startDate: string;
  endDate: string;
  days: HeatmapDay[];
  currentStreak: number;
  bestStreak: number;
  activeDays: number;
}

/** 组卷条目（组卷时隐藏 analysis，考完再看解析） */
export interface QuizItem {
  id: number;
  subject: SubjectKey;
  title: string;
  content: string;
  createdAt: string;
}
/** 组卷输入 */
export interface QuizGenerateInput {
  subject?: SubjectKey;
  unmasteredOnly?: boolean; // 缺省 true：只组未掌握的
  from?: string; // 创建日期下限 YYYY-MM-DD
  to?: string;   // 创建日期上限 YYYY-MM-DD
  limit?: number; // 缺省 20，范围 1..100
}
/** 批改输入 */
export interface QuizGradeInput {
  results: Array<{ mistakeId: number; correct: boolean }>;
}
/** 批改结果 */
export interface QuizGradeResult {
  total: number;
  correct: number;
  wrong: number;
  updatedIds: number[];
}

/** 错题掌握率响应 */
export interface MistakeSummary {
subject: string | null;
total: number;
mastered: number;
unmastered: number;
masteredRate: number;
}
export interface MistakeSubjectSummary {
  subject: SubjectKey;
  total: number;
  mastered: number;
  unmastered: number;
  masteredRate: number;
}
export interface MistakesBySubjectResponse {
  subjects: MistakeSubjectSummary[];
}

/** 账号体系：用户 */
export interface User { id: number; username: string; createdAt: string;}
/** 注册输入 */
export interface RegisterInput { username: string; password: string;}
/** 登录输入 */
export interface LoginInput { username: string; password: string;}
/** 登录/me 响应 */
export interface AuthUser { id: number; username: string;}


