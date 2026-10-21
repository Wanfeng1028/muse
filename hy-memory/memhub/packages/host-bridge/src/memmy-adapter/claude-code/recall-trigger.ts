import { createHash } from "node:crypto";

/** Openers and acknowledgements that carry no question for history to answer.
 *
 * Deliberately a closed list rather than a rule. Recall costs a round trip and
 * a line of user-visible text; not recalling costs an answer the user wanted.
 * The two are not symmetric, so anything outside this list still recalls. */
const PLEASANTRIES = new Set([
  "hi",
  "hey",
  "hello",
  "yo",
  "thanks",
  "thank you",
  "thx",
  "ty",
  "ok",
  "okay",
  "k",
  "cool",
  "nice",
  "got it",
  "sounds good",
  "bye",
  "goodbye",
  "good morning",
  "good afternoon",
  "good evening",
  "你好",
  "您好",
  "哈喽",
  "嗨",
  "在吗",
  "在么",
  "谢谢",
  "多谢",
  "感谢",
  "辛苦了",
  "好",
  "好的",
  "行",
  "行吧",
  "可以",
  "收到",
  "明白",
  "懂了",
  "知道了",
  "没问题",
  "再见",
  "拜拜",
  "早上好",
  "下午好",
  "晚上好",
]);

/** Punctuation and emphasis that change nothing about what was asked. */
const DECORATION =
  /^[\s!?.,;:~、。，！？；：…·\-—"'“”‘’()（）]+|[\s!?.,;:~、。，！？；：…·\-—"'“”‘’()（）]+$/gu;

function bare(prompt: string): string {
  return prompt.trim().replace(DECORATION, "").trim().toLowerCase();
}

/** Same question asked twice is the same question, whatever the spacing. */
export function queryFingerprint(prompt: string): string {
  return createHash("sha256")
    .update(prompt.trim().replace(/\s+/gu, " ").toLowerCase())
    .digest("hex");
}

export function isPleasantry(prompt: string): boolean {
  return PLEASANTRIES.has(bare(prompt));
}
