// Lightweight pure chat (client side). No multi-step tool loop: each
// round packs context (this chart's key-data summary + session history
// + the user's question) and sends it to the backend model in one call.
// The cloud function holds the system prompt; this file never contains
// it. When cloud is not configured, a local template answers from the
// chart summary only (grounded by construction: every sentence cites
// data the summary builder produced; anything beyond the chart data is
// answered with "不知道" + a pointer back to the chart).
//
// Safety split: the client runs the injection detector for instant
// feedback, but the cloud function re-checks everything and is the
// authority (client checks are never trusted for billing or refusal).

import Taro from '@tarojs/taro';
import type { ZiweiChart } from '../engine/types';
import { getLiuNianSiHua } from '../engine/sihua';
import { getDaXianIndexForYear } from '../engine/yunxian-context';
import { detectPatterns } from '../engine/patterns';
import { detectInjection } from './chat-safety';
import { DISCLAIMER, branchLabel } from './chart';

export const CHAT_SUMMARY_MAX_CHARS = 1500;

const PALACE_ORDER = ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'];

function starText(palace: ZiweiChart['palaces'][number]): string {
  const majors = palace.stars.filter((s) => s.type === 'major').map((s) => s.name + (s.siHua ? '(' + s.siHua + ')' : '')).join('、');
  const borrowed = (palace.borrowedStars || []).join('、');
  if (majors) return majors;
  if (borrowed) return '借' + borrowed;
  return '无主星';
}

// Key-data summary: palaces + main stars + sihua + current fortune
// context + pattern names. This is the ONLY chart data the model sees
// (plus the session history), so grounding can be audited from it.
export function buildChartSummary(chart: ZiweiChart, now?: Date): string {
  const current = now || new Date();
  const year = current.getFullYear();
  const ming = chart.palaces.find((p) => p.isMingGong);
  const lines: string[] = [];
  lines.push('命宫：' + (ming ? ming.name + '（' + branchLabel(ming.branch) + '）' : '未知') + '；五行局：' + (chart.wuxingJuName || chart.wuxingJu || '未知') + '；命主：' + (chart.mingZhu || '未知') + '；身主：' + (chart.shenZhu || '未知') + '。');
  const palaceLines = chart.palaces.map((p) => p.name + '（' + branchLabel(p.branch) + '）：' + starText(p)).join('；');
  lines.push('十二宫：' + palaceLines + '。');
  const daXianIndex = getDaXianIndexForYear(chart, year);
  const daXian = daXianIndex >= 0 && chart.daXians[daXianIndex] ? chart.daXians[daXianIndex] : null;
  if (daXian) {
    lines.push('当前大限：第 ' + (daXianIndex + 1) + ' 限，' + daXian.palaceName + '宫，' + daXian.startAge + '–' + daXian.endAge + '岁。');
  }
  const liuNian = getLiuNianSiHua(year);
  lines.push(year + '年流年：天干' + liuNian.stemName + '，四化：禄' + (liuNian.transforms['禄'] || '') + '、权' + (liuNian.transforms['权'] || '') + '、科' + (liuNian.transforms['科'] || '') + '、忌' + (liuNian.transforms['忌'] || '') + '。');
  const patterns = detectPatterns(chart);
  lines.push('格局：' + (patterns.length > 0 ? patterns.map((p) => p.name).join('、') : '无入格格局') + '。');
  let out = lines.join('\n');
  if (out.length > CHAT_SUMMARY_MAX_CHARS) {
    out = out.slice(0, CHAT_SUMMARY_MAX_CHARS) + '…（摘要已截断）';
  }
  return out;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  at: number;
}

const HISTORY_KEY = 'zw_chat_history_v1';

function historyKey(chartKey: string): string {
  return HISTORY_KEY + ':' + chartKey;
}

export function loadHistory(chartKey: string, rounds: number): ChatMessage[] {
  try {
    const raw = Taro.getStorageSync(historyKey(chartKey));
    if (!Array.isArray(raw)) return [];
    return (raw as ChatMessage[]).slice(-rounds * 2);
  } catch {
    return [];
  }
}

export function appendHistory(chartKey: string, msg: ChatMessage, rounds: number): void {
  try {
    const list = loadHistory(chartKey, 100);
    list.push(msg);
    Taro.setStorageSync(historyKey(chartKey), list.slice(-rounds * 2));
  } catch {
    // History loss must not break the chat round.
  }
}

export function clearHistory(chartKey: string): void {
  try {
    Taro.removeStorageSync(historyKey(chartKey));
  } catch {
    // Ignore.
  }
}

// Local template answer: grounded by construction. It only restates
// summary data; questions about a named palace/star get that palace's
// line; anything else gets the whole summary + a "beyond the chart"
// disclaimer. No model, no points, no quota.
export function localTemplateAnswer(chart: ZiweiChart, question: string): string {
  const summary = buildChartSummary(chart);
  const palaceHit = PALACE_ORDER.find((name) => question.indexOf(name) >= 0);
  if (palaceHit) {
    const palace = chart.palaces.find((p) => p.name === palaceHit);
    if (palace) {
      return '结合本盘：' + palace.name + '（' + palace.branch + '）主星为' + starText(palace) + '。'
        + '本地模板回答，仅复述本盘数据，未调用模型，不耗积分。'
        + '超出本盘数据的推断我不知道，建议结合完整解读页查看。'
        + DISCLAIMER;
    }
  }
  const starHit = chart.palaces
    .map((p) => p.stars.find((s) => question.indexOf(s.name) >= 0))
    .find((s) => !!s);
  if (starHit) {
    const palace = chart.palaces.find((p) => p.stars.indexOf(starHit) >= 0);
    return '结合本盘：' + starHit.name + '落在' + (palace ? palace.name + '（' + palace.branch + '）' : '未知宫位')
      + (starHit.siHua ? '，带四化' + starHit.siHua : '') + '。'
      + '本地模板回答，仅复述本盘数据，未调用模型，不耗积分。' + DISCLAIMER;
  }
  if (question.indexOf('格局') >= 0) {
    const patterns = detectPatterns(chart);
    return '结合本盘：格局为' + (patterns.length > 0 ? patterns.map((p) => p.name).join('、') : '无入格格局') + '。'
      + '本地模板回答，仅复述本盘数据，未调用模型，不耗积分。' + DISCLAIMER;
  }
  return '结合本盘关键数据：\n' + summary + '\n本地模板回答，仅复述本盘数据，未调用模型，不耗积分。'
    + '超出本盘数据的问题我不知道，建议回命盘图页或解读页查看对应内容。' + DISCLAIMER;
}

// Client-side injection pre-check (instant feedback only; the cloud
// function re-checks and is authoritative).
export function clientInjectionCheck(question: string): { blocked: boolean; categories: string[] } {
  const res = detectInjection(question);
  return { blocked: res.blocked, categories: res.categories };
}

export interface ChatAgentResult {
  text: string;
  chargedPoints: number;
  tokensUsed: number;
  quotaCoveredTokens: number;
  degraded: boolean;
  truncated: boolean;
  disclaimer: string;
}

export interface ChatAgentError {
  code: string;
  message: string;
}
