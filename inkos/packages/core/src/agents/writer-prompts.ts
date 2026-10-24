import type { BookConfig } from "../models/book.js";
import type { BookRules } from "../models/book-rules.js";
import type { LengthSpec } from "../models/length-governance.js";
import { buildLengthSpec } from "../utils/length-metrics.js";

/** Writer protocol. Narrative craft comes from the active long-writing Skill. */
export function buildWriterSystemPrompt(
  book: BookConfig,
  bookRules: BookRules | null,
  bookRulesBody: string,
  styleGuide: string,
  languageOverride?: "zh" | "en",
  lengthSpec?: LengthSpec,
): string {
  const language = languageOverride ?? book.language;
  const resolvedLength = lengthSpec ?? buildLengthSpec(book.chapterWordCount, language);
  const sections = language === "en"
    ? [
        `Write one chapter for the active ${book.genre} Work on ${book.platform} using the activated professional Skills.`,
        governedContract("en"),
        lengthContract(resolvedLength, "en"),
        narrativePersonContract(bookRules, "en"),
        protagonistContract(bookRules, "en"),
        authorityBlock("Book rules", bookRulesBody),
        authorityBlock("Style guide", styleGuide),
      ]
    : [
        `按已激活的专业 Skill 为当前${book.genre}作品写一章。平台：${book.platform}。`,
        governedContract("zh"),
        lengthContract(resolvedLength, "zh"),
        narrativePersonContract(bookRules, "zh"),
        protagonistContract(bookRules, "zh"),
        authorityBlock("本书规则", bookRulesBody),
        authorityBlock("文风指南", styleGuide),
      ];
  return sections.filter(Boolean).join("\n\n");
}

function governedContract(language: "zh" | "en"): string {
  return language === "en"
    ? `## Authority
The current user instruction and chapter memo govern this chapter. Established facts, explicit prohibitions, selected context, and real hook ids remain binding. The outline is a fallback only when it does not conflict with higher authority. Satisfy every populated memo requirement in the prose; do not duplicate or rename an existing narrative promise.`
    : `## 权威顺序
当前用户指令和 chapter memo 决定本章任务；既成事实、显式禁令、已选上下文和真实 hook id 必须保留。卷纲仅在无冲突时作为兜底。memo 已填写的每项要求都要在正文落地，不要为同一承诺重复开 hook，也不要改名既有叙事承诺。`;
}

function lengthContract(spec: LengthSpec, language: "zh" | "en"): string {
  return language === "en"
    ? `## Length\nUser target: ${spec.target} words. Preserve scene completeness instead of padding or cutting mechanically.`
    : `## 字数\n用户目标：${spec.target} 字。保持场景完整，不要机械注水或裁切。`;
}

function narrativePersonContract(bookRules: BookRules | null, language: "zh" | "en"): string {
  const person = bookRules?.narrativePerson;
  if (!person) return "";
  if (language === "en") return `## Narrative person\n${person}; this durable constraint overrides model defaults.`;
  return `## 叙事人称\n${person}；该持久约束优先于模型默认。`;
}

function protagonistContract(bookRules: BookRules | null, language: "zh" | "en"): string {
  const protagonist = bookRules?.protagonist;
  if (!protagonist) return "";
  const separator = language === "en" ? ", " : "、";
  const locks = protagonist.personalityLock.join(separator);
  const boundaries = protagonist.behavioralConstraints.join(language === "en" ? "; " : "；");
  const prohibitions = bookRules.prohibitions.join(language === "en" ? "; " : "；");
  return language === "en"
    ? `## Protagonist authority\nName: ${protagonist.name}\nPersonality: ${locks || "(none)"}\nBehavioral constraints: ${boundaries || "(none)"}\nBook prohibitions: ${prohibitions || "(none)"}`
    : `## 主角权威\n名字：${protagonist.name}\n性格锁：${locks || "（无）"}\n行为约束：${boundaries || "（无）"}\n本书禁忌：${prohibitions || "（无）"}`;
}

function authorityBlock(title: string, body: string | undefined): string {
  const trimmed = body?.trim();
  if (!trimmed) return "";
  return `## ${title}\n${trimmed}`;
}
