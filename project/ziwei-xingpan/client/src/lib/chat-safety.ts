// Client mirror of cloudfunctions/_shared/chat-safety.js.
// Same pattern table, same verdict shape { blocked, categories, matches }.
// The cloud function is authoritative; this mirror only gives instant
// local feedback (and powers the local template loop when cloud is not
// configured). Keep the two tables in sync: cloudfunctions/tests/
// chat-safety.test.js pins the verdicts on a shared fixture list.

const HOMOGLYPHS: Record<string, string> = {
  'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c',
  'ο': 'o', 'α': 'a', 'х': 'x', 'у': 'y', 'і': 'i',
};

const LEET: Record<string, string> = {
  '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's',
};

function decodePlane14Tags(text: string): string {
  return text.replace(/[\u{e0000}-\u{e007f}]/gu, (ch) => {
    const code = ch.codePointAt(0)! - 0xe0000;
    return code >= 0x20 && code < 0x7f ? String.fromCharCode(code) : '';
  });
}

function tryBase64Segments(text: string): string {
  const out: string[] = [];
  const re = /[A-Za-z0-9+/=]{20,200}/g;
  let m: RegExpExecArray | null;
  let count = 0;
  while ((m = re.exec(text)) !== null && count < 3) {
    count++;
    try {
      // Taro/JS base64 decode without Buffer (weapp has no Buffer).
      const bin = atob(m[0]);
      const decoded = decodeURIComponent(
        bin.split('').map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''),
      );
      if (decoded && /^[\x20-\x7e\u4e00-\u9fff\s]+$/.test(decoded)) out.push(decoded);
    } catch { /* not base64, ignore */ }
  }
  return out.join(' ');
}

export interface SafetyVerdict {
  blocked: boolean;
  categories: string[];
  matches: string[];
}

interface Normalized {
  plain: string;
  plainLeet: string;
  compact: string;
  compactLeet: string;
  b64: string;
}

export function normalizeSafety(text: string): Normalized {
  let s = String(text || '');
  try { s = decodeURIComponent(s); } catch { /* keep raw */ }
  s = decodePlane14Tags(s);
  s = s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/[\u200b\u200c\u200d\ufeff\u00ad]/g, '');
  s = s.split('').map((ch) => HOMOGLYPHS[ch] || ch).join('');
  const leet = s.split('').map((ch) => LEET[ch] || ch).join('');
  const plain = s.toLowerCase();
  const plainLeet = leet.toLowerCase();
  const compact = plain.replace(/[\s.·。]+/g, '');
  const compactLeet = plainLeet.replace(/[\s.·。]+/g, '');
  return { plain, plainLeet, compact, compactLeet, b64: tryBase64Segments(s).toLowerCase() };
}

// Pattern table: identical to cloudfunctions/_shared/chat-safety.js.
// English patterns use \s* between words so they match both the plain
// and the compact variant.
export const SAFETY_PATTERNS: Array<{ category: string; pattern: string; note: string }> = [
  { category: 'instruction_override', pattern: '忽略(之前|以上|所有)?(指令|提示|规则|设定)', note: 'ignore previous instructions (zh)' },
  { category: 'instruction_override', pattern: 'ignore\\s*(all\\s*)?(previous|above|prior)\\s*instructions', note: 'ignore previous instructions (en)' },
  { category: 'instruction_override', pattern: '(不遵守|不要遵守|无视|忘记).*?(指令|提示|规则)', note: 'disregard instructions (zh)' },
  { category: 'instruction_override', pattern: '(forget|disregard)\\s*(all\\s*)?(previous\\s*)?instructions', note: 'forget/disregard instructions (en)' },
  { category: 'role_hijack', pattern: '你现在是|你扮演|假装你是|假装你是一', note: 'role hijack (zh)' },
  { category: 'role_hijack', pattern: 'pretend\\s*(you\\s*are|to\\s*be)', note: 'pretend to be (en)' },
  { category: 'role_hijack', pattern: 'you\\s*are\\s*now\\s*(a|an|the)', note: 'you are now (en)' },
  { category: 'prompt_extract', pattern: '(告诉|透露|泄露|显示|输出|打印|复述).{0,6}?(系统提示词|系统指令|system\\s*prompt)', note: 'prompt extraction (zh)' },
  { category: 'prompt_extract', pattern: '(reveal|show|print|output|tell\\s*me)\\s*(your\\s*)?(system\\s*prompt|instructions)', note: 'prompt extraction (en)' },
  { category: 'prompt_extract', pattern: '你的(系统)?提示词是(什么|啥)', note: 'what is your prompt (zh)' },
  { category: 'prompt_extract', pattern: 'what\\s*(is|are)\\s*your\\s*(system\\s*)?(prompt|instructions)', note: 'what is your prompt (en)' },
  { category: 'format_inject', pattern: '<\\|im_start\\|>', note: 'ChatML marker' },
  { category: 'format_inject', pattern: '<<SYS>>', note: 'Llama SYS marker' },
  { category: 'format_inject', pattern: '\\[INST\\]', note: 'Llama INST marker' },
  { category: 'format_inject', pattern: '###\\s*System\\s*:', note: 'Alpaca system header' },
  { category: 'format_inject', pattern: '<\\|system\\|>', note: 'system role marker' },
  { category: 'data_exfil', pattern: '(导出|转储|dump|export).{0,8}?(数据库|全部数据|database|all\\s*data)', note: 'dump database' },
  { category: 'data_exfil', pattern: '(把|将).{0,8}?(密码|密钥|api\\s*key|apikey).{0,8}?(发|告诉|输出)', note: 'exfiltrate secrets (zh)' },
  { category: 'confidence_manip', pattern: 'confidence\\s*=\\s*100', note: 'confidence override' },
  { category: 'confidence_manip', pattern: 'auto_approve', note: 'auto approve' },
  { category: 'jailbreak', pattern: 'DAN', note: 'DAN jailbreak' },
  { category: 'jailbreak', pattern: '越狱|jailbreak', note: 'jailbreak (zh/en)' },
  { category: 'jailbreak', pattern: '开发者模式|developer\\s*mode', note: 'developer mode' },
  { category: 'jailbreak', pattern: '绕过.{0,6}?(限制|过滤|安全)|bypass\\s*(the\\s*)?(filter|safety|restriction)', note: 'bypass safety' },
  { category: 'markup_inject', pattern: '<script', note: 'script tag' },
  { category: 'markup_inject', pattern: '<!--\\s*INJECTION', note: 'injection comment' },
  { category: 'markup_inject', pattern: '\\[HIDDEN\\]', note: 'hidden marker' },
];

export function detectInjection(text: string): SafetyVerdict {
  const n = normalizeSafety(text);
  const haystacks = [n.plain, n.plainLeet, n.compact, n.compactLeet, n.b64];
  const categories: string[] = [];
  const matches: string[] = [];
  for (const entry of SAFETY_PATTERNS) {
    let re: RegExp;
    try { re = new RegExp(entry.pattern, 'i'); } catch { continue; }
    for (const hay of haystacks) {
      if (re.test(hay)) {
        if (categories.indexOf(entry.category) === -1) categories.push(entry.category);
        if (matches.indexOf(entry.note) === -1) matches.push(entry.note);
        break;
      }
    }
  }
  return { blocked: categories.length > 0, categories, matches };
}

const OUTPUT_PATTERNS: Array<{ flag: string; pattern: string }> = [
  { flag: 'system_prompt_leak', pattern: '我的系统提示词是|my\\s*system\\s*prompt\\s*is|my\\s*instructions\\s*are' },
  { flag: 'dan_marker', pattern: 'DAN\\s*mode|jailbreak\\s*mode\\s*enabled|越狱模式已开启' },
  { flag: 'chatml_leak', pattern: '<\\|im_start\\|>|<<SYS>>|\\[INST\\]' },
  { flag: 'secret_shape', pattern: 'sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}' },
];

export function scanOutput(text: string): { flagged: boolean; flags: string[] } {
  const s = String(text || '');
  const flags: string[] = [];
  for (const entry of OUTPUT_PATTERNS) {
    if (new RegExp(entry.pattern, 'i').test(s) && flags.indexOf(entry.flag) === -1) flags.push(entry.flag);
  }
  return { flagged: flags.length > 0, flags };
}

export const BANNED_WORDS = ['改运', '化解', '法事', '必定会', '一定会', '包治', '转运物', '开光'];

export function complianceHits(text: string): string[] {
  const s = String(text || '');
  return BANNED_WORDS.filter((w) => s.indexOf(w) !== -1);
}
