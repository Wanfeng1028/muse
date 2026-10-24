/** Physical source lines, retaining their exact terminators for scoped edits. */
export function splitSourceLines(source: string): string[] {
  return source.match(/[^\n]*\n|[^\n]+$/g) ?? [];
}

export function sourceLineBodies(source: string): string[] {
  return splitSourceLines(source).map(line => line.replace(/\n$/, ""));
}

export function numberSourceLines(source: string, startLine = 1): string {
  return sourceLineBodies(source).map((line, index) => `${startLine + index}\t${line}`).join("\n");
}

/** Full-document collection counts remain valid when the displayed JSON is paged. */
export function measureJsonStructure(source: string) {
  let value: unknown;
  try { value = JSON.parse(source); } catch { return undefined; }
  const arrayLengths: Record<string, number> = {};
  const visit = (item: unknown, pointer: string, depth: number): void => {
    if (Array.isArray(item)) { arrayLengths[pointer] = item.length; return; }
    if (!item || typeof item !== "object" || depth >= 3) return;
    for (const [key, child] of Object.entries(item)) {
      visit(child, pointer + "/" + key.replace(/~/g, "~0").replace(/\//g, "~1"), depth + 1);
    }
  };
  visit(value, "", 0);
  return { format: "json" as const, scope: "full_artifact" as const, arrayLengths };
}

/** Smallest contiguous line region enclosing the edit; may include unchanged inner lines. */
export function changedSourceRegion(before: string, after: string, maxCharsPerSide = 2000) {
  const oldLines = splitSourceLines(before), newLines = splitSourceLines(after);
  let start = 0, oldEnd = oldLines.length, newEnd = newLines.length;
  while (start < oldEnd && start < newEnd && oldLines[start] === newLines[start]) start++;
  while (oldEnd > start && newEnd > start && oldLines[oldEnd - 1] === newLines[newEnd - 1]) {oldEnd--;newEnd--;}
  const region = (lines: string[], end: number) => {
    const content = lines.slice(start, end).join('');
    return {startLine: start + 1, lineCount: end - start, content: content.slice(0, maxCharsPerSide), truncated: content.length > maxCharsPerSide};
  };
  return {scope: 'contiguous_changed_region', before: region(oldLines, oldEnd), after: region(newLines, newEnd)};
}

/** Measurements describe the full supplied source, including headings and markup. */
export function measureSourceText(source: string) {
  return {
    scope: "full_artifact" as const,
    lineCount: splitSourceLines(source).length,
    hanCharacters: (source.match(/\p{Script=Han}/gu) ?? []).length,
    nonWhitespaceCharacters: [...source.replace(/\s/gu, "")].length,
    englishWords: (source.match(/[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?/g) ?? []).length,
  };
}
