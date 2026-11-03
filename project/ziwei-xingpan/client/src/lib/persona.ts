// 人格形象：基础款按命宫主星预设，本地出图，不依赖云端。
// All 14 major stars map to a color pair + motif + title. The notes
// describe the MOTIF (a decorative image theme), never the person's
// fate: no deterministic claims, no advice, no "you will" sentences.
// The persona card always carries a "形象仅为装饰" footnote.
// AI custom images are a separate paid flow (30 points, via the aiImage
// cloud function kind 'persona'); unconfigured cloud shows an honest
// unconfigured state instead of a fake image.

import type { ZiweiChart } from '../engine/types';

export interface PersonaPreset {
  star: string;
  title: string;
  colors: [string, string];
  motif: string;
  note: string;
}

export const PERSONA_PRESETS: Record<string, PersonaPreset> = {
  '紫微': { star: '紫微', title: '星垣之主', colors: ['#7c5cf0', '#b79cff'], motif: '星辰宝座', note: '以紫微星为意象的沉稳星空形象。' },
  '天机': { star: '天机', title: '灵枢智者', colors: ['#2f9e8f', '#7fd4c4'], motif: '齿轮星盘', note: '以运转机巧为意象的灵动形象。' },
  '太阳': { star: '太阳', title: '晨光行者', colors: ['#f59e0b', '#ffd97a'], motif: '旭日光轮', note: '以旭日为意象的明亮形象。' },
  '武曲': { star: '武曲', title: '坚石守将', colors: ['#8a6d3b', '#c9a86a'], motif: '磐石利刃', note: '以磐石为意象的坚定形象。' },
  '天同': { star: '天同', title: '和煦少年', colors: ['#f2a7c3', '#ffd9e6'], motif: '云朵暖阳', note: '以云朵暖阳为意象的柔和形象。' },
  '廉贞': { star: '廉贞', title: '赤焰舞者', colors: ['#e5484d', '#ff9a8a'], motif: '赤色焰火', note: '以赤色焰火为意象的热烈形象。' },
  '天府': { star: '天府', title: '宝库主人', colors: ['#b8860b', '#e8c96a'], motif: '金色宝库', note: '以金色宝库为意象的雍容形象。' },
  '太阴': { star: '太阴', title: '月下静客', colors: ['#5b7bb4', '#a8c3e8'], motif: '银月静湖', note: '以银月静湖为意象的宁静形象。' },
  '贪狼': { star: '贪狼', title: '星野旅人', colors: ['#a855f7', '#d8b4fe'], motif: '紫色星野', note: '以紫色星野为意象的自由形象。' },
  '巨门': { star: '巨门', title: '深谷回声', colors: ['#334155', '#7d8aa0'], motif: '深谷暗门', note: '以深谷暗门为意象的深邃形象。' },
  '天相': { star: '天相', title: '衡器执事', colors: ['#0ea5a5', '#7de3e3'], motif: '青玉衡器', note: '以青玉衡器为意象的端正形象。' },
  '天梁': { star: '天梁', title: '古松长者', colors: ['#4d7c0f', '#a3c47a'], motif: '古松荫下', note: '以古松为意象的安稳形象。' },
  '七杀': { star: '七杀', title: '锋刃先行', colors: ['#dc2626', '#fca5a5'], motif: '寒锋破晓', note: '以寒锋为意象的锐利形象。' },
  '破军': { star: '破军', title: '浪潮开拓', colors: ['#2563eb', '#93c5fd'], motif: '破浪潮头', note: '以破浪潮头为意象的开拓形象。' },
};

export const EMPTY_PALACE_PRESET: PersonaPreset = {
  star: '空宫',
  title: '未点亮的星野',
  colors: ['#8a94a6', '#c3cad6'],
  motif: '空旷星野',
  note: '命宫暂无主星时的中性形象。',
};

// 命宫首颗主星；空宫时用借宫首星；仍无则用空宫预设。
export function personaForChart(chart: ZiweiChart): PersonaPreset {
  const ming = chart.palaces.find((p) => p.isMingGong);
  if (ming) {
    const major = ming.stars.find((s) => s.type === 'major');
    if (major && PERSONA_PRESETS[major.name]) return PERSONA_PRESETS[major.name];
    const borrowedName = (ming.borrowedStars || []).find((n) => !!PERSONA_PRESETS[n]);
    if (borrowedName) return PERSONA_PRESETS[borrowedName];
  }
  return EMPTY_PALACE_PRESET;
}

export function personaForStarName(starName: string): PersonaPreset {
  return PERSONA_PRESETS[starName] || EMPTY_PALACE_PRESET;
}
