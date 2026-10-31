import { STAR_DESCRIPTIONS } from '../engine/constants';

// Knowledge entries are newly written short notes in generic traditional terms.
export interface KnowledgeEntry { title: string; body: string }

export const STAR_ENTRIES: KnowledgeEntry[] = Object.entries(STAR_DESCRIPTIONS).map(
  ([name, v]) => ({
    title: `${name}（${v.element}，${v.nature}）`,
    body: `关键词：${v.keywords}。亮度庙旺利陷表示该星在所在宫位的得力程度，仅作参考。`,
  }),
);

export const PALACE_ENTRIES: KnowledgeEntry[] = [
  { title: '命宫', body: '看个人气质与行事倾向的宫位，是全盘的起点。' },
  { title: '兄弟宫', body: '看兄弟姐妹与同辈关系的宫位，也与平辈助力有关。' },
  { title: '夫妻宫', body: '看亲密关系与婚恋相处倾向的宫位。' },
  { title: '子女宫', body: '看子女、晚辈与创作、投资兴趣倾向的宫位。' },
  { title: '财帛宫', body: '看收入、开支与理财倾向的宫位。' },
  { title: '疾厄宫', body: '看体质与健康方面需留意倾向的宫位，不能替代医学建议。' },
  { title: '迁移宫', body: '看外出、变动与对外交往倾向的宫位。' },
  { title: '交友宫', body: '看朋友、下属与合作关系的宫位，盘上亦称仆役宫。' },
  { title: '官禄宫', body: '看职业发展与事业倾向的宫位。' },
  { title: '田宅宫', body: '看居住、置业与家庭资产倾向的宫位。' },
  { title: '福德宫', body: '看心态、福分感受与休闲倾向的宫位。' },
  { title: '父母宫', body: '看父母长辈与家庭支持倾向的宫位。' },
];

export const SIHUA_ENTRIES: KnowledgeEntry[] = [
  { title: '化禄', body: '表示顺遂、得益的倾向，常与财源、机会联系在一起看。' },
  { title: '化权', body: '表示掌控、进取的倾向，常与权力、执行力联系在一起看。' },
  { title: '化科', body: '表示名声、文书、学习的倾向，常与考试、声誉联系在一起看。' },
  { title: '化忌', body: '表示阻滞、牵挂的倾向，宜多留意该宫所主事项的准备工作。' },
];

export const PATTERN_ENTRIES: KnowledgeEntry[] = [
  { title: '格局是什么', body: '格局是若干星曜组合形成的传统分类，用于概括命盘的某种倾向。成格与否要看亮度、三方四正与煞星，不能只看一两颗星。' },
  { title: '三方四正', body: '以命宫为中心，命宫、财帛宫、官禄宫为三方，加上对宫迁移宫为四正，是论命时最常对照的一组宫位。' },
  { title: '空宫与借对宫', body: '某宫无主星称为空宫，传统上可参考对宫主星，但仍以本宫辅星与三方为主要依据。' },
];
