import type { Palace, ZiweiChart } from '../engine/types';

// All interpretation text in this file is newly written for this project,
// in neutral traditional-culture wording. No quoted source text is used.
export interface Dimension {
  id: string;
  title: string;
  palaceName: string;
  body: string;
}

function palaceByName(chart: ZiweiChart, name: string): Palace | undefined {
  return chart.palaces.find((p) => p.name === name);
}

function starSummary(p?: Palace): string {
  if (!p) return '未找到该宫。';
  const majors = p.stars.filter((s) => s.type === 'major');
  if (majors.length === 0) {
    const borrowed = p.borrowedStars?.length ? `，可参考对宫 ${p.borrowedFromName ?? ''}的 ${p.borrowedStars.join('、')}` : '';
    return `本宫无主星${borrowed}，宜结合三方四正一起看。`;
  }
  const parts = majors.map((s) => {
    const b = s.brightnessRaw ? `（${s.brightnessRaw}）` : '';
    const h = s.siHua ? `化${s.siHua}` : '';
    return `${s.name}${b}${h}`;
  });
  return `主星：${parts.join('、')}。`;
}

function genericNote(title: string): string {
  const notes: Record<string, string> = {
    命宫: '命宫反映个人气质与行事风格的倾向，宜结合全盘看，不宜单宫定论。',
    财帛: '财帛宫反映收入与开支的倾向，宜量入为出、做好预算。',
    事业: '官禄宫反映职业发展的倾向，宜结合自身技能与行业实际选择。',
    感情: '夫妻宫反映亲密关系的相处倾向，沟通与互相尊重比星曜更重要。',
    健康: '疾厄宫反映体质与健康方面需要留意的倾向，不能替代医学建议。',
    子女: '子女宫反映与子女、晚辈相处及创作方面的倾向。',
    手足: '兄弟宫反映与兄弟姐妹、同辈相处的倾向。',
    迁移: '迁移宫反映外出、变动与对外交往方面的倾向。',
    田宅: '田宅宫反映居住与置业方面的倾向，决策仍以现实条件为准。',
    福德: '福德宫反映心态与休闲方面的倾向，保持规律作息有益身心。',
    父母: '父母宫反映与长辈相处及家庭支持方面的倾向。',
    交友: '交友宫反映朋友与合作方面的倾向，合作前宜核实对方与条款。',
    身宫: '身宫反映中年之后生活重心的倾向，宜与命宫对照着看。',
  };
  return notes[title] ?? '';
}

const DIMS: Array<{ id: string; title: string; palace: string }> = [
  { id: 'ming', title: '命宫', palace: '命宫' },
  { id: 'cai', title: '财帛', palace: '财帛' },
  { id: 'shiye', title: '事业', palace: '官禄' },
  { id: 'ganqing', title: '感情', palace: '夫妻' },
  { id: 'jiankang', title: '健康', palace: '疾厄' },
  { id: 'zinv', title: '子女', palace: '子女' },
  { id: 'shouzu', title: '手足', palace: '兄弟' },
  { id: 'qianyi', title: '迁移', palace: '迁移' },
  { id: 'tianzhai', title: '田宅', palace: '田宅' },
  { id: 'fude', title: '福德', palace: '福德' },
  { id: 'fumu', title: '父母', palace: '父母' },
  { id: 'jiaoyou', title: '交友', palace: '仆役' },
  { id: 'shen', title: '身宫', palace: '' },
];

export function buildDimensions(chart: ZiweiChart): Dimension[] {
  return DIMS.map((d) => {
    let p: Palace | undefined;
    if (d.id === 'shen') {
      p = chart.palaces.find((x) => x.isShenGong);
    } else {
      p = palaceByName(chart, d.palace);
    }
    const palaceName = p?.name ?? d.palace;
    return {
      id: d.id,
      title: d.title,
      palaceName,
      body: `${starSummary(p)}${genericNote(d.title)}`,
    };
  });
}
