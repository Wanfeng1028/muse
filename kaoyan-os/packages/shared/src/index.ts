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

/** 创建计划输入 */
export interface CreatePlanInput {
  date: string;
  subject: SubjectKey;
  title: string;
  plannedMinutes: number;
}

/** 更新计划输入 */
export type UpdatePlanInput = Partial<CreatePlanInput & { done: boolean }>;

/** 专注会话 */
export interface FocusSession {
  id: number;
  subject: SubjectKey;
  minutes: number;
  startedAt: string;
  note: string | null;
}

/** 创建专注输入 */
export interface CreateFocusInput {
  subject: SubjectKey;
  minutes: number;
  startedAt?: string;
  note?: string;
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

/** 计划完成情况汇总 */
export interface PlanSummary {
  date: string;
  total: number;
  done: number;
  completionRate: number;
}

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

/** 单词 */
export interface Word {
  id: number;
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
}

/** 创建单词输入 */
export type CreateWordInput = Omit<Word, 'id'>;

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
