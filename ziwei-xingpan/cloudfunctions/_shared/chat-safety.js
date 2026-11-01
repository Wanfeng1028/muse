'use strict';

// Chat safety detector (server-side, dependency-free).
// Approach adopted from shanemhamilton/llm-prompt-guard (MIT): a
// normalization pipeline that defeats encoding smuggling, then pattern
// matching across 8 documented categories, then output scanning for
// prompt-leak markers and PII shapes. The pattern table here is written
// for this project (Chinese + English); the pipeline steps and the
// category set follow the documented approach. The client mirror is
// client/src/lib/chat-safety.ts and must keep the same pattern table;
// cloudfunctions/tests/chat-safety.test.js pins both tables' verdicts
// on a shared fixture list (see that file's FIXTURES comment).
//
// Verdict shape: { blocked, categories, matches }.
// blocked = any category matched. The caller refuses with a fixed
// message and writes an audit record; it never echoes the input back
// as an instruction.

// Homoglyph map: Cyrillic / Greek lookalikes -> Latin.
const HOMOGLYPHS = {
  '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p', '\u0441': 'c',
  '\u03bf': 'o', '\u03b1': 'a', '\u0445': 'x', '\u0443': 'y', '\u0456': 'i'
};

const LEET = { '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '@': 'a', '$': 's' };

function decodePlane14Tags(text) {
  // Plane 14 tag code points U+E0000-U+E007F mirror ASCII.
  return text.replace(/[\u{e0000}-\u{e007f}]/gu, function (ch) {
    const code = ch.codePointAt(0) - 0xe0000;
    return (code >= 0x20 && code < 0x7f) ? String.fromCharCode(code) : '';
  });
}

function tryBase64Segments(text) {
  // Append ASCII-printable decodings of long base64-looking runs so a
  // payload hidden in base64 is still visible to the patterns. Bounded:
  // at most 3 segments, each at most 200 chars.
  const out = [];
  const re = /[A-Za-z0-9+/=]{20,200}/g;
  let m;
  let count = 0;
  while ((m = re.exec(text)) !== null && count < 3) {
    count++;
    try {
      const decoded = Buffer.from(m[0], 'base64').toString('utf8');
      if (decoded && /^[\x20-\x7e\u4e00-\u9fff\s]+$/.test(decoded)) {
        out.push(decoded);
      }
    } catch (e) { /* not base64, ignore */ }
  }
  return out.join(' ');
}

// Normalize once; returns { plain, compact } where compact has all
// whitespace and dots removed (catches "i.g.n.o.r.e" / "i g n o r e").
function normalize(text) {
  let s = String(text || '');
  try { s = decodeURIComponent(s); } catch (e) { /* keep raw */ }
  s = decodePlane14Tags(s);
  s = s.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/[​‌‍﻿­]/g, '');
  s = s.split('').map(function (ch) { return HOMOGLYPHS[ch] || ch; }).join('');
  const leet = s.split('').map(function (ch) { return LEET[ch] || ch; }).join('');
  const plain = s.toLowerCase();
  const plainLeet = leet.toLowerCase();
  const compact = plain.replace(/[\s.·。]+/g, '');
  const compactLeet = plainLeet.replace(/[\s.·。]+/g, '');
  const b64 = tryBase64Segments(s);
  return { plain: plain, plainLeet: plainLeet, compact: compact, compactLeet: compactLeet, b64: b64.toLowerCase() };
}

// Pattern table. Each entry: { category, pattern (string, used as
// RegExp source), note }. English patterns use \s* between words so
// they match both the plain and the compact variant.
const PATTERNS = [
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
  { category: 'markup_inject', pattern: '\\[HIDDEN\\]', note: 'hidden marker' }
];

function detect(text) {
  const n = normalize(text);
  const haystacks = [n.plain, n.plainLeet, n.compact, n.compactLeet, n.b64];
  const categories = [];
  const matches = [];
  PATTERNS.forEach(function (entry) {
    let re;
    try { re = new RegExp(entry.pattern, 'i'); } catch (e) { return; }
    for (let i = 0; i < haystacks.length; i++) {
      if (re.test(haystacks[i])) {
        if (categories.indexOf(entry.category) === -1) categories.push(entry.category);
        if (matches.indexOf(entry.note) === -1) matches.push(entry.note);
        break;
      }
    }
  });
  return { blocked: categories.length > 0, categories: categories, matches: matches };
}

// Output scan: returns { flagged, flags }. Flagged output must not be
// delivered verbatim; the caller replaces it with a safe fallback.
const OUTPUT_PATTERNS = [
  { flag: 'system_prompt_leak', pattern: '我的系统提示词是|my\\s*system\\s*prompt\\s*is|my\\s*instructions\\s*are' },
  { flag: 'dan_marker', pattern: 'DAN\\s*mode|jailbreak\\s*mode\\s*enabled|越狱模式已开启' },
  { flag: 'chatml_leak', pattern: '<\\|im_start\\|>|<<SYS>>|\\[INST\\]' },
  { flag: 'secret_shape', pattern: 'sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}' }
];

function scanOutput(text) {
  const s = String(text || '');
  const flags = [];
  OUTPUT_PATTERNS.forEach(function (entry) {
    if (new RegExp(entry.pattern, 'i').test(s) && flags.indexOf(entry.flag) === -1) {
      flags.push(entry.flag);
    }
  });
  return { flagged: flags.length > 0, flags: flags };
}

// Compliance filter for generated answers: banned deterministic /
// remedy-sales wording. Returns the list of banned words found.
const BANNED_WORDS = ['改运', '化解', '法事', '必定会', '一定会', '包治', '转运物', '开光'];

function complianceHits(text) {
  let s = String(text || '');
  return BANNED_WORDS.filter(function (w) { return s.indexOf(w) !== -1; });
}

module.exports = {
  normalize: normalize,
  detect: detect,
  scanOutput: scanOutput,
  complianceHits: complianceHits,
  PATTERNS: PATTERNS,
  BANNED_WORDS: BANNED_WORDS
};
