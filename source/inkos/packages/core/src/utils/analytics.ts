import type { ChapterMeta } from "../models/chapter.js";

export interface TokenStats {
  readonly totalPromptTokens: number;
  readonly totalCompletionTokens: number;
  readonly totalTokens: number;
  readonly avgTokensPerChapter: number;
  readonly recentTrend: ReadonlyArray<{ readonly chapter: number; readonly totalTokens: number }>;
}

export interface AnalyticsData {
  readonly bookId: string;
  readonly totalChapters: number;
  readonly totalWords: number;
  readonly avgWordsPerChapter: number;
  readonly observationCount: number;
  readonly chaptersWithObservations: number;
  readonly tokenStats?: TokenStats;
}

export function computeAnalytics(bookId: string, chapters: ReadonlyArray<ChapterMeta>): AnalyticsData {
  const totalChapters = chapters.length;
  const totalWords = chapters.reduce((sum, chapter) => sum + chapter.wordCount, 0);
  const chaptersWithUsage = chapters.filter((chapter) => chapter.tokenUsage);
  const totalTokens = chaptersWithUsage.reduce((sum, chapter) => sum + (chapter.tokenUsage?.totalTokens ?? 0), 0);
  const tokenStats = chaptersWithUsage.length > 0
    ? {
        totalPromptTokens: chaptersWithUsage.reduce((sum, chapter) => sum + (chapter.tokenUsage?.promptTokens ?? 0), 0),
        totalCompletionTokens: chaptersWithUsage.reduce((sum, chapter) => sum + (chapter.tokenUsage?.completionTokens ?? 0), 0),
        totalTokens,
        avgTokensPerChapter: Math.round(totalTokens / chaptersWithUsage.length),
        recentTrend: [...chaptersWithUsage]
          .sort((left, right) => left.number - right.number)
          .slice(-5)
          .map((chapter) => ({ chapter: chapter.number, totalTokens: chapter.tokenUsage?.totalTokens ?? 0 })),
      }
    : undefined;
  return {
    bookId,
    totalChapters,
    totalWords,
    avgWordsPerChapter: totalChapters > 0 ? Math.round(totalWords / totalChapters) : 0,
    observationCount: chapters.reduce((sum, chapter) => sum + chapter.observations.length, 0),
    chaptersWithObservations: chapters.filter((chapter) => chapter.observations.length > 0).length,
    ...(tokenStats ? { tokenStats } : {}),
  };
}
