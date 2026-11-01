// 门户趣味工具的本地数据与逻辑：MBTI 自编问卷、塔罗、六爻、
// 星座骰子、许愿 / 祈福、解梦 journal、报告记录、AI 占星师人格。
//
// 原创性说明：MBTI 题目与 16 型描述、塔罗牌意、祈福文案均为本站
// 新写；塔罗牌名与六十四卦名属于传统公共知识，只列名、不抄他人
// 解读文本。六爻卦名表按文王卦序排列，(上卦, 下卦) 组合经唯一性
// 自检（见 scripts/portal-selfcheck.ts）。所有随机结果均标注为随
// 机娱乐，不作断言。

// ---- MBTI 自编问卷（16 题，每维 4 题；A 侧 = E/S/T/J，B 侧 = I/N/F/P）
export interface MbtiQuestion {
  q: string;
  a: string;
  b: string;
  dim: 'EI' | 'SN' | 'TF' | 'JP';
}

export const MBTI_QUESTIONS: MbtiQuestion[] = [
  { q: '休息日怎样充电？', a: '和朋友出门聚会，越热闹越放松', b: '独自在家做喜欢的事，安静才回血', dim: 'EI' },
  { q: '参加聚会时，你更倾向？', a: '主动和陌生人攀谈，认识新朋友', b: '和熟人待在一起就好', dim: 'EI' },
  { q: '遇到难题，你先？', a: '找人聊聊，边说边理清思路', b: '自己先想清楚再开口', dim: 'EI' },
  { q: '工作学习环境，你喜欢？', a: '开放热闹的氛围', b: '安静独立的空间', dim: 'EI' },
  { q: '看一篇文章，你先注意？', a: '具体的数字、步骤和事实', b: '背后的含义和可能性', dim: 'SN' },
  { q: '做计划时，你先看？', a: '当下可用的资源和条件', b: '长远的目标和方向', dim: 'SN' },
  { q: '讲一件事，你习惯？', a: '按时间顺序讲清楚经过', b: '更爱讲感受和联想到的画面', dim: 'SN' },
  { q: '学新东西，你从哪里开始？', a: '动手练、做例子', b: '理解原理和框架', dim: 'SN' },
  { q: '朋友向你倾诉烦恼，你先？', a: '帮他分析原因、给出办法', b: '先安慰情绪，让他感到被理解', dim: 'TF' },
  { q: '做决定时，你更看重？', a: '是否合乎逻辑、公平一致', b: '是否照顾到每个人的感受', dim: 'TF' },
  { q: '被批评时，你先想？', a: '批评有没有道理', b: '对方的语气和态度', dim: 'TF' },
  { q: '团队分工出现分歧，你倾向？', a: '按规则和能力分配', b: '兼顾大家的意愿再协调', dim: 'TF' },
  { q: '出门旅行，你习惯？', a: '提前订好行程和住宿', b: '走到哪算哪，随机应变', dim: 'JP' },
  { q: '桌面和文件，你习惯？', a: '分门别类，固定位置', b: '随手放，用时再找', dim: 'JP' },
  { q: '截止日期前，你通常？', a: '提前做完，留出余量', b: '最后一刻冲刺，灵感更好', dim: 'JP' },
  { q: '计划被打乱时，你感觉？', a: '不舒服，想尽快回到原计划', b: '灵活调整也挺好', dim: 'JP' },
];

export const MBTI_DESCS: Record<string, string> = {
  INTJ: '习惯先想透再动手，喜欢把复杂问题拆成系统；独处时效率最高。',
  INTP: '对原理和逻辑着迷，喜欢追问为什么；想法多，落地常靠截止日期推一把。',
  ENTJ: '目标感强，喜欢定方向、分任务、推着事情往前走。',
  ENTP: '点子来得快，爱讨论、爱尝试新可能；执行细节容易交给别人。',
  INFJ: '细腻且有长远眼光，常能察觉别人的情绪；需要独处时间恢复。',
  INFP: '重视内心价值，想象力丰富；做决定先问自己是否认同。',
  ENFJ: '天生的组织者，善于调动气氛、照顾每个人的感受。',
  ENFP: '热情好奇，点子多、人缘好；容易同时开好几个坑。',
  ISTJ: '踏实可靠，做事按步骤、有交代；讨厌临时变卦。',
  ISFJ: '细心体贴，记得每个人的习惯；默默把事情做到位。',
  ESTJ: '讲究效率和秩序，喜欢把事情安排得明明白白。',
  ESFJ: '热心周到，聚会里最会照顾人；被需要会很有成就感。',
  ISTP: '动手能力强，喜欢拆解和修理；话不多，解决问题很直接。',
  ISFP: '温和随性，审美在线；按自己的节奏生活，不爱被管。',
  ESTP: '行动派，现场反应快；喜欢变化，讨厌纸上谈兵。',
  ESFP: '气氛担当，走到哪热闹到哪；享受当下，开心最重要。',
};

// answers: 每题 0 = 选 A，1 = 选 B。平局取 A 侧（E/S/T/J），规则写死、可复现。
export function mbtiType(answers: number[]): string {
  const dims: Array<[string, string, string]> = [['EI', 'E', 'I'], ['SN', 'S', 'N'], ['TF', 'T', 'F'], ['JP', 'J', 'P']];
  let type = '';
  for (const [dim, aSide, bSide] of dims) {
    let bCount = 0;
    let total = 0;
    MBTI_QUESTIONS.forEach((q, i) => {
      if (q.dim !== dim) return;
      total += 1;
      if (answers[i] === 1) bCount += 1;
    });
    type += bCount * 2 > total ? bSide : aSide;
  }
  return type;
}

// ---- 塔罗：22 张大阿卡纳，牌意本站新写。
export interface TarotCard {
  name: string;
  up: string;
  rev: string;
}

export const TAROT: TarotCard[] = [
  { name: '愚者', up: '新的开始，带着好奇出发，别怕走弯路。', rev: '出发前先检查行囊，冲动容易踩空。' },
  { name: '魔术师', up: '手头资源已经够了，动手把想法变成现实。', rev: '别只停留在计划里，先做最小一步。' },
  { name: '女祭司', up: '安静下来，直觉会告诉你答案。', rev: '别忽视内心的提醒，也别过度猜疑。' },
  { name: '女皇', up: '丰盛与滋养的时期，适合照顾自己和身边人。', rev: '先把自己的杯子倒满，再去照顾别人。' },
  { name: '皇帝', up: '用规则和秩序稳住局面，适合做决定。', rev: '别把控制抓得太紧，留一点弹性。' },
  { name: '教皇', up: '向有经验的人请教，传统做法此刻管用。', rev: '规则可以质疑，但别为反而反。' },
  { name: '恋人', up: '面临选择时，听从内心真正看重的那个。', rev: '先理清自己要什么，再谈关系。' },
  { name: '战车', up: '方向已定，踩住油门，别被杂音带偏。', rev: '先刹车检查方向，硬冲容易翻车。' },
  { name: '力量', up: '温柔比强硬更有力，耐心能驯服难题。', rev: '别硬撑，承认累了也是力量。' },
  { name: '隐士', up: '独处不是逃避，是为了看清下一步。', rev: '想清楚了就出来，别在原地打转。' },
  { name: '命运之轮', up: '变化正在发生，顺势而为比硬抗轻松。', rev: '卡住的时候，先换一个小角度试试。' },
  { name: '正义', up: '按事实和公平说话，适合做清算与决定。', rev: '别急着下判断，先核对事实。' },
  { name: '倒吊人', up: '换个角度看问题，等待本身就是进展。', rev: '拖太久就成了停滞，该动就动。' },
  { name: '死神', up: '旧阶段结束，新阶段正在开门。', rev: '舍不得放手，反而拖住了自己。' },
  { name: '节制', up: '调和与平衡，慢慢来反而更快。', rev: '别走极端，先找回中间点。' },
  { name: '恶魔', up: '留意让你上瘾或依赖的东西，看清它就好了一半。', rev: '正在松绑，继续走，别回头。' },
  { name: '高塔', up: '突变打碎了旧结构，重建的机会也来了。', rev: '小震动提前预警，别等大塌方。' },
  { name: '星星', up: '希望回来了，适合许愿和做长期计划。', rev: '希望还在，只是需要多一点耐心。' },
  { name: '月亮', up: '迷雾里别急着信直觉，也别全信恐惧。', rev: '雾在散，真相快露出来了。' },
  { name: '太阳', up: '明朗、顺利、值得开心的一天。', rev: '阳光被云挡了一下，事情仍在向好。' },
  { name: '审判', up: '复盘过去，给自己一个重新开始的决定。', rev: '别反复自责，总结一次就翻篇。' },
  { name: '世界', up: '一个阶段圆满完成，值得庆祝和收尾。', rev: '差最后一小步，收好尾再开新局。' },
];

export function drawTarot(count: number): Array<{ card: TarotCard; reversed: boolean }> {
  const pool = [...TAROT];
  const out: Array<{ card: TarotCard; reversed: boolean }> = [];
  for (let i = 0; i < count && pool.length > 0; i++) {
    const idx = Math.floor(Math.random() * pool.length);
    out.push({ card: pool.splice(idx, 1)[0], reversed: Math.random() < 0.5 });
  }
  return out;
}

// ---- 六爻：文王卦序 64 卦（名 + 上卦 + 下卦），卦名本身即上下卦的
// 传统组合（如“水雷屯”=上坎下震），组合唯一性由自检脚本验证。
export interface Hexagram {
  name: string;
  upper: string;
  lower: string;
}

export const HEXAGRAMS: Hexagram[] = [
  { name: '乾', upper: '乾', lower: '乾' }, { name: '坤', upper: '坤', lower: '坤' },
  { name: '屯', upper: '坎', lower: '震' }, { name: '蒙', upper: '艮', lower: '坎' },
  { name: '需', upper: '坎', lower: '乾' }, { name: '讼', upper: '乾', lower: '坎' },
  { name: '师', upper: '坤', lower: '坎' }, { name: '比', upper: '坎', lower: '坤' },
  { name: '小畜', upper: '巽', lower: '乾' }, { name: '履', upper: '乾', lower: '兑' },
  { name: '泰', upper: '坤', lower: '乾' }, { name: '否', upper: '乾', lower: '坤' },
  { name: '同人', upper: '乾', lower: '离' }, { name: '大有', upper: '离', lower: '乾' },
  { name: '谦', upper: '坤', lower: '艮' }, { name: '豫', upper: '震', lower: '坤' },
  { name: '随', upper: '兑', lower: '震' }, { name: '蛊', upper: '艮', lower: '巽' },
  { name: '临', upper: '坤', lower: '兑' }, { name: '观', upper: '巽', lower: '坤' },
  { name: '噬嗑', upper: '离', lower: '震' }, { name: '贲', upper: '艮', lower: '离' },
  { name: '剥', upper: '艮', lower: '坤' }, { name: '复', upper: '坤', lower: '震' },
  { name: '无妄', upper: '乾', lower: '震' }, { name: '大畜', upper: '艮', lower: '乾' },
  { name: '颐', upper: '艮', lower: '震' }, { name: '大过', upper: '兑', lower: '巽' },
  { name: '坎', upper: '坎', lower: '坎' }, { name: '离', upper: '离', lower: '离' },
  { name: '咸', upper: '兑', lower: '艮' }, { name: '恒', upper: '震', lower: '巽' },
  { name: '遁', upper: '乾', lower: '艮' }, { name: '大壮', upper: '震', lower: '乾' },
  { name: '晋', upper: '离', lower: '坤' }, { name: '明夷', upper: '坤', lower: '离' },
  { name: '家人', upper: '巽', lower: '离' }, { name: '睽', upper: '离', lower: '兑' },
  { name: '蹇', upper: '坎', lower: '艮' }, { name: '解', upper: '震', lower: '坎' },
  { name: '损', upper: '艮', lower: '兑' }, { name: '益', upper: '巽', lower: '震' },
  { name: '夬', upper: '兑', lower: '乾' }, { name: '姤', upper: '乾', lower: '巽' },
  { name: '萃', upper: '兑', lower: '坤' }, { name: '升', upper: '坤', lower: '巽' },
  { name: '困', upper: '兑', lower: '坎' }, { name: '井', upper: '坎', lower: '巽' },
  { name: '革', upper: '兑', lower: '离' }, { name: '鼎', upper: '离', lower: '巽' },
  { name: '震', upper: '震', lower: '震' }, { name: '艮', upper: '艮', lower: '艮' },
  { name: '渐', upper: '巽', lower: '艮' }, { name: '归妹', upper: '震', lower: '兑' },
  { name: '丰', upper: '震', lower: '离' }, { name: '旅', upper: '离', lower: '艮' },
  { name: '巽', upper: '巽', lower: '巽' }, { name: '兑', upper: '兑', lower: '兑' },
  { name: '涣', upper: '巽', lower: '坎' }, { name: '节', upper: '坎', lower: '兑' },
  { name: '中孚', upper: '巽', lower: '兑' }, { name: '小过', upper: '震', lower: '艮' },
  { name: '既济', upper: '坎', lower: '离' }, { name: '未济', upper: '离', lower: '坎' },
];

// 八卦三爻（自下而上，阳=1）：乾 111、兑 110、离 101、震 100、巽 011、坎 010、艮 001、坤 000。
const TRIGRAM_BITS: Record<string, string> = {
  '乾': '111', '兑': '110', '离': '101', '震': '100',
  '巽': '011', '坎': '010', '艮': '001', '坤': '000',
};

function trigramOf(linesBottomUp: boolean[]): string {
  const bits = linesBottomUp.map((y) => (y ? '1' : '0')).join('');
  for (const [name, b] of Object.entries(TRIGRAM_BITS)) if (b === bits) return name;
  return '';
}

export interface YaoLine {
  yang: boolean;
  moving: boolean;
  label: string;
}

const YAO_NAMES = ['初爻', '二爻', '三爻', '四爻', '五爻', '上爻'];

// 三枚铜钱一掷：3 正=老阳（动），2 正=少阳，1 正=少阴，0 正=老阴（动）。
export function throwCoins(): YaoLine[] {
  const lines: YaoLine[] = [];
  for (let i = 0; i < 6; i++) {
    let heads = 0;
    for (let c = 0; c < 3; c++) if (Math.random() < 0.5) heads += 1;
    const yang = heads >= 2;
    const moving = heads === 3 || heads === 0;
    lines.push({ yang, moving, label: YAO_NAMES[i] });
  }
  return lines;
}

export function hexagramOf(lines: YaoLine[]): { base: Hexagram; changed: Hexagram | null; movingNames: string[] } {
  const baseValues = lines.map((l) => l.yang);
  const lower = trigramOf(baseValues.slice(0, 3));
  const upper = trigramOf(baseValues.slice(3, 6));
  const base = HEXAGRAMS.find((h) => h.upper === upper && h.lower === lower)
    ?? { name: '未名', upper, lower };
  const movingNames = lines.filter((l) => l.moving).map((l) => l.label);
  if (movingNames.length === 0) return { base, changed: null, movingNames };
  const changedValues = lines.map((l) => (l.moving ? !l.yang : l.yang));
  const cLower = trigramOf(changedValues.slice(0, 3));
  const cUpper = trigramOf(changedValues.slice(3, 6));
  const changed = HEXAGRAMS.find((h) => h.upper === cUpper && h.lower === cLower)
    ?? { name: '未名', upper: cUpper, lower: cLower };
  return { base, changed, movingNames };
}

// ---- 星座骰子：行星 × 星座 × 宫位，随机组合，本站新写句式。
const DICE_SIGNS = ['白羊座', '金牛座', '双子座', '巨蟹座', '狮子座', '处女座', '天秤座', '天蝎座', '射手座', '摩羯座', '水瓶座', '双鱼座'];
const DICE_PLANETS: Array<[string, string]> = [
  ['太阳', '照亮'], ['月亮', '牵动情绪'], ['水星', '推动沟通'], ['金星', '温柔以待'],
  ['火星', '点燃行动'], ['木星', '放大机会'], ['土星', '考验耐心'], ['天王星', '带来变化'],
  ['海王星', '增添想象'], ['冥王星', '推动转变'],
];
const DICE_SIGNS_ADJ = ['直接', '踏实', '灵活', '温情', '热烈', '细致', '平衡', '专注', '远方', '务实', '新奇', '柔软'];
const DICE_HOUSES = ['自我与形象', '金钱与拥有', '沟通与学习', '家庭与根基', '创造与欢愉', '日常与健康', '关系与合作', '共享与转变', '远行与理念', '事业与声望', '朋友与愿景', '独处与潜意识'];

export function rollDice(): { planet: string; sign: string; house: string; line: string } {
  const planet = DICE_PLANETS[Math.floor(Math.random() * DICE_PLANETS.length)];
  const si = Math.floor(Math.random() * 12);
  const hi = Math.floor(Math.random() * 12);
  return {
    planet: planet[0],
    sign: DICE_SIGNS[si],
    house: `第${['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'][hi]}宫`,
    line: `${planet[0]}落入${DICE_SIGNS[si]}第${['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二'][hi]}宫：${planet[1]}着${DICE_SIGNS_ADJ[si]}的${DICE_HOUSES[hi]}，适合顺势留意这一方面的变化。`,
  };
}

// ---- AI 占星师：4 位本站原创人格（名、介绍、擅长均为新写，不用
// 参照对象的名与头像，不展示任何聊过人数——没有该数据就不编）。
export interface Persona {
  id: string;
  name: string;
  glyph: 'sparkles' | 'heart' | 'briefcase' | 'graduation-cap';
  intro: string;
  tags: string[];
}

export const PERSONAS: Persona[] = [
  { id: 'xingheng', name: '星衡', glyph: 'sparkles', intro: '沉稳的命盘解读师，先看全盘再谈细节，不夸大、不吓人。', tags: ['命盘总览', '大运流年'] },
  { id: 'yuetang', name: '月棠', glyph: 'heart', intro: '温柔的关系倾听者，陪你理清亲密关系里的真实感受。', tags: ['感情', '合盘对照'] },
  { id: 'yunzhou', name: '云舟', glyph: 'briefcase', intro: '务实的事业参谋，只谈可落地的选择，不谈空泛的运气。', tags: ['事业', '财富'] },
  { id: 'dengxia', name: '灯下', glyph: 'graduation-cap', intro: '耐心的学业伙伴，陪你把学习与生活节奏安排得明明白白。', tags: ['学业', '生活节奏'] },
];
