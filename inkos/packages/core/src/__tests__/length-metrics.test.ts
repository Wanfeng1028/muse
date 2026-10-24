import { describe, it, expect } from "vitest";
import {
  buildLengthSpec,
  countChapterLength,
  defaultChapterLength,
} from "../utils/length-metrics.js";

describe("length metrics", () => {
  it("counts Chinese chapter length using zh_chars", () => {
    expect(countChapterLength("他抬头看天。", "zh_chars")).toBe(6);
  });

  it("counts English chapter length using en_words", () => {
    expect(countChapterLength("He looked at the sky.", "en_words")).toBe(5);
  });

  it("defaults chapter length to the language-native unit", () => {
    expect(defaultChapterLength("zh")).toBe(3000);
    expect(defaultChapterLength("en")).toBe(2000);
    expect(defaultChapterLength()).toBe(3000);
  });

  it("counts prose only for markdown-shaped Chinese chapters", () => {
    const markdownChapter = [
      "---",
      "title: 第1章 归来",
      "---",
      "",
      "# 第1章 归来",
      "",
      "陈风抬头看天。",
    ].join("\n");

    expect(countChapterLength(markdownChapter, "zh_chars")).toBe("陈风抬头看天。".length);
  });

  it("keeps only the user's target and language-native counting mode", () => {
    const spec = buildLengthSpec(2200, "zh");

    expect(spec).toEqual({
      target: 2200,
      countingMode: "zh_chars",
    });
    expect(buildLengthSpec(2200, "en")).toEqual({
      target: 2200,
      countingMode: "en_words",
    });
  });
});
