import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { BookRulesSchema, type ParsedBookRules } from "../models/book-rules.js";

/**
 * Load structured book rules.
 *
 * Books keep human-readable guidance in book_rules.md and the small host
 * surface in book_rules.json. Prose is never reinterpreted by code.
 */
export async function readBookRules(bookDir: string): Promise<ParsedBookRules> {
  const [rulesRaw, dataRaw] = await Promise.all([
    readFile(join(bookDir, "story/book_rules.md"), "utf-8"),
    readFile(join(bookDir, "story/book_rules.json"), "utf-8"),
  ]);
  return { rules: BookRulesSchema.parse(JSON.parse(dataRaw)), body: rulesRaw.trim() };
}
