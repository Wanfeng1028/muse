import type {
  Plan,
  CreatePlanInput,
  UpdatePlanInput,
  FocusSession,
  CreateFocusInput,
  FocusStats,
  PlanSummary,
  AutoScheduleInput,
  AutoScheduleItem,
  AutoScheduleResult,
  OverloadResponse,
  Mistake,
  MistakeSummary,
  CreateMistakeInput,
  UpdateMistakeInput,
  QuizItem,
  QuizGenerateInput,
  QuizGradeInput,
  QuizGradeResult,

  CreateWordInput,
  WordWithState,
  SrsState,
  ReviewGrade,
  ExamRecord,
  CreateExamInput,
  ExamTrendPoint,
  ExamSummary,
  HeatmapResponse,
  Settings,
  WeeklyStats,
} from '@kaoyan/shared';



export interface BackupPayload {
  format: string;
  version: number;
  exportedAt: string;
  tables: Record<string, Array<Record<string, unknown>>>;
}
export interface BackupImportResult {
  mode: 'replace' | 'merge';
  imported: Record<string, number>;
  skipped: Record<string, number>;
}
export interface WordsImportResult {
  imported: number;
  skippedEmpty: number;
  skippedExisting: number;
  errors: Array<{ row: number; message: string }>;
  errorRows: number;
}
export interface MistakesImportResult {
  imported: number;
  errors: Array<{ row: number; message: string }>;
  errorRows: number;
}
export interface VocabSeedResult {
  imported: number;
  skippedExisting: number;
  skippedInvalid: number;
  errors: Array<{ file: string; index: number; message: string }>;
}
export interface VocabStatus {
  total: number;
  mastered: number;
  pending: number;
}
const BASE = '/api';

// 401 统一跳登录：排除 /api/auth/* 自身，避免登录页请求也被弹走
function handleUnauthorized(url: string) {
  if (url.startsWith('/auth/')) return;
  const path = window.location.pathname;
  if (path === '/login') return;
  window.location.href = '/login';
}

// 通用请求封装：自动 JSON、错误解析、204 处理、401 跳登录
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) || {}),
  };

  const res = await fetch(BASE + url, { ...init, headers, credentials: 'same-origin' });

  if (!res.ok) {
    let message = res.statusText || String(res.status);
    try {
      const data = await res.json();
      if (data && typeof data.error === 'string') message = data.error;
    } catch {
      // 忽略解析失败，使用状态码文本
    }
    if (res.status === 401) handleUnauthorized(url);
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface AuthUser {
  id: number;
  username: string;
  createdAt: string;
}
// 构建查询字符串
function qs(params?: Record<string, unknown>): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    sp.append(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const api = {
  // 健康检查
  health: () => request<{ ok: boolean }>('/health'),

  // 认证
  register: (username: string, password: string) =>
    request<AuthUser>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  login: (username: string, password: string) =>
    request<AuthUser>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<AuthUser>('/auth/me'),
  // 计划
  listPlans: (params?: { date?: string; subject?: string }) =>
    request<Plan[]>(`/plans${qs(params)}`),
  planSummary: (date?: string) =>
    request<PlanSummary>(`/plans/summary${qs({ date })}`),
  createPlan: (input: CreatePlanInput) =>
    request<Plan>('/plans', { method: 'POST', body: JSON.stringify(input) }),
  updatePlan: (id: number, patch: UpdatePlanInput) =>
    request<Plan>(`/plans/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deletePlan: (id: number) =>
    request<void>(`/plans/${id}`, { method: 'DELETE' }),
  autoSchedulePreview: (params: { subjects: string; dailyMinutes: number; examDate: string; startDate?: string }) =>
    request<{ items: AutoScheduleItem[] }>(`/plans/auto-schedule/preview${qs(params)}`),
  autoSchedule: (input: AutoScheduleInput) =>
    request<AutoScheduleResult>('/plans/auto-schedule', { method: 'POST', body: JSON.stringify(input) }),
  plansRange: (from: string, to: string) =>
    request<Plan[]>(`/plans/range${qs({ from, to })}`),
  plansOverload: (weekStart: string, dailyMinutes: number) =>
    request<OverloadResponse>(`/plans/overload${qs({ weekStart, dailyMinutes })}`),

  // 专注
  listFocus: (limit?: number) => request<FocusSession[]>(`/focus${qs({ limit })}`),
  createFocus: (input: CreateFocusInput) =>
    request<FocusSession>('/focus', { method: 'POST', body: JSON.stringify(input) }),
  focusStats: (days?: number) => request<FocusStats>(`/focus/stats${qs({ days })}`),

  // 错题
  listMistakes: (params?: { subject?: string; mastered?: boolean; q?: string }) => {
    const { mastered, ...rest } = params ?? {};
    const query = {
      ...rest,
      ...(mastered === undefined ? {} : { mastered: mastered ? '1' : '0' }),
    };
    return request<Mistake[]>(`/mistakes${qs(query)}`);
  },
  createMistake: (input: CreateMistakeInput) =>
    request<Mistake>('/mistakes', { method: 'POST', body: JSON.stringify(input) }),
  updateMistake: (id: number, patch: UpdateMistakeInput) =>
    request<Mistake>(`/mistakes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteMistake: (id: number) =>
    request<void>(`/mistakes/${id}`, { method: 'DELETE' }),
  // 错题掌握率汇总
  mistakeSummary: (subject?: string) =>
    request<MistakeSummary>(`/mistakes/summary${qs({ subject })}`),
  mistakeSourceExams: (id: number, windowDays?: number) =>
    request<ExamRecord[]>(`/mistakes/${id}/source-exams${qs({ windowDays })}`),
  generateQuiz: (input: QuizGenerateInput) =>
    request<QuizItem[]>('/mistakes/quiz/generate', { method: 'POST', body: JSON.stringify(input) }),
  gradeQuiz: (input: QuizGradeInput) =>
    request<QuizGradeResult>('/mistakes/quiz/grade', { method: 'POST', body: JSON.stringify(input) }),


  // 单词
  listWords: () => request<WordWithState[]>('/words'),
  dueWords: () => request<WordWithState[]>('/words/due'),
  createWord: (input: CreateWordInput) =>
    request<WordWithState>('/words', { method: 'POST', body: JSON.stringify(input) }),
  reviewWord: (id: number, grade: ReviewGrade) =>
    request<WordWithState>(`/words/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ grade }),
    }),
  deleteWord: (id: number) =>
    request<void>(`/words/${id}`, { method: 'DELETE' }),
  seedVocab: () => request<VocabSeedResult>('/words/seed-vocab', { method: 'POST' }),
  vocabStatus: () => request<VocabStatus>('/words/vocab-status'),

  // 考试
  listExams: (subject?: string) => request<ExamRecord[]>(`/exams${qs({ subject })}`),
  examTrend: (subject?: string) =>
    request<ExamTrendPoint[]>(`/exams/trend${qs({ subject })}`),
  examSummary: (subject?: string) =>
    request<ExamSummary>(`/exams/summary${qs({ subject })}`),
  createExam: (input: CreateExamInput) =>
    request<ExamRecord>('/exams', { method: 'POST', body: JSON.stringify(input) }),
  deleteExam: (id: number) =>
    request<void>(`/exams/${id}`, { method: 'DELETE' }),
  examRelatedMistakes: (id: number, windowDays?: number) =>
    request<Mistake[]>(`/exams/${id}/related-mistakes${qs({ windowDays })}`),

  // 考试 CSV 导出：返回 Blob，由调用方触发下载
  exportExamsCsv: async (subject?: string): Promise<Blob> => {
    const res = await fetch(BASE + `/exams/export${qs({ subject })}`, {
      credentials: 'same-origin',
    });
    if (res.status === 401) {
      handleUnauthorized('/exams/export');
      throw new Error('登录已过期，请重新登录。');
    }
    if (!res.ok) throw new Error(`导出失败（${res.status}）`);
    return await res.blob();
  },


  // 设置
  getSettings: () => request<Settings>('/settings'),
  updateSettings: (patch: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(patch) }),
  // 备份与导入
  exportBackup: () => request<BackupPayload>('/backup/export'),
  importBackup: (data: unknown, mode: 'replace' | 'merge') =>
    request<BackupImportResult>('/backup/import', {
      method: 'POST',
      body: JSON.stringify({ data, mode }),
    }),
  importWordsCsv: (csv: string) =>
    request<WordsImportResult>('/import/words', {
      method: 'POST',
      body: JSON.stringify({ csv }),
    }),
  importMistakesCsv: (csv: string) =>
    request<MistakesImportResult>('/import/mistakes', {
      method: 'POST',
      body: JSON.stringify({ csv }),
    }),

  // 热力图
  heatmapStats: (months?: number) =>
    request<HeatmapResponse>(`/stats/heatmap${qs({ months })}`),

  // 周报
  weeklyStats: (start?: string) =>
    request<WeeklyStats>(`/stats/weekly${qs({ start })}`),
};

