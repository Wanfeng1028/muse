import type {
  Plan,
  CreatePlanInput,
  UpdatePlanInput,
  FocusSession,
  CreateFocusInput,
  FocusStats,
  PlanSummary,
  Mistake,
  CreateMistakeInput,
  UpdateMistakeInput,
  CreateWordInput,
  WordWithState,
  SrsState,
  ReviewGrade,
  ExamRecord,
  CreateExamInput,
  ExamTrendPoint,
  Settings,
} from '@kaoyan/shared';

const BASE = '/api';

// 通用请求封装：自动 JSON、错误解析、204 处理
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((init?.headers as Record<string, string>) || {}),
  };

  const res = await fetch(BASE + url, { ...init, headers });

  if (!res.ok) {
    let message = res.statusText || String(res.status);
    try {
      const data = await res.json();
      if (data && typeof data.error === 'string') message = data.error;
    } catch {
      // 忽略解析失败，使用状态码文本
    }
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
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

  // 专注
  listFocus: (limit?: number) => request<FocusSession[]>(`/focus${qs({ limit })}`),
  createFocus: (input: CreateFocusInput) =>
    request<FocusSession>('/focus', { method: 'POST', body: JSON.stringify(input) }),
  focusStats: (days?: number) => request<FocusStats>(`/focus/stats${qs({ days })}`),

  // 错题
  listMistakes: (params?: { subject?: string; mastered?: boolean; q?: string }) =>
    request<Mistake[]>(`/mistakes${qs(params)}`),
  createMistake: (input: CreateMistakeInput) =>
    request<Mistake>('/mistakes', { method: 'POST', body: JSON.stringify(input) }),
  updateMistake: (id: number, patch: UpdateMistakeInput) =>
    request<Mistake>(`/mistakes/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteMistake: (id: number) =>
    request<void>(`/mistakes/${id}`, { method: 'DELETE' }),

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

  // 考试
  listExams: (subject?: string) => request<ExamRecord[]>(`/exams${qs({ subject })}`),
  examTrend: (subject?: string) =>
    request<ExamTrendPoint[]>(`/exams/trend${qs({ subject })}`),
  createExam: (input: CreateExamInput) =>
    request<ExamRecord>('/exams', { method: 'POST', body: JSON.stringify(input) }),
  deleteExam: (id: number) =>
    request<void>(`/exams/${id}`, { method: 'DELETE' }),

  // 设置
  getSettings: () => request<Settings>('/settings'),
  updateSettings: (patch: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(patch) }),
};
