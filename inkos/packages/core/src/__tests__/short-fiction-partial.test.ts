import { describe, expect, it } from "vitest";
import { renderShortFictionDraftMarkdown, findIncompleteShortFictionChapters, validateShortFictionDraftForFinal, ShortFictionBatchDraftSchema } from "../agents/short-fiction.js";

describe("short-fiction partial persistence", () => {
  it("rejects near-empty chapters using actual native length and exposes the chapters to resume", () => {
    const draft = {storyTitle:"Draft",rawContent:"",chapters:[
      {number:1,title:"One",content:"One short line.",charCount:1000},
      {number:2,title:"Two",content:Array(60).fill("word").join(" "),charCount:1},
    ]};
    const minimum = {minChapterLength:50,language:"en" as const};
    expect(findIncompleteShortFictionChapters(draft, minimum)).toEqual([1]);
    expect(() => validateShortFictionDraftForFinal(draft, {expectedChapters:2,...minimum}))
      .toThrowError(expect.objectContaining({code:"SHORT_CHAPTER_INCOMPLETE",chapters:[1]}));
    const completed = {...draft,chapters:draft.chapters.map((chapter)=>({...chapter,content:Array(60).fill("word").join(" ")}))};
    expect(findIncompleteShortFictionChapters(completed,minimum)).toEqual([]);
    expect(()=>validateShortFictionDraftForFinal(completed,{expectedChapters:2,...minimum})).not.toThrow();
    const corrupted = {...completed,chapters:completed.chapters.map(chapter=>chapter.number===2?{...chapter,content:chapter.content+"\uFFFD"}:chapter)};
    expect(findIncompleteShortFictionChapters(corrupted,minimum)).toEqual([2]);
    expect(()=>validateShortFictionDraftForFinal(corrupted,{expectedChapters:2,...minimum}))
      .toThrowError(expect.objectContaining({code:"SHORT_CHAPTER_TEXT_CORRUPTED",chapters:[2]}));
  });
  it("renders completed batches while later chapters are still pending", () => {
    const persisted = ShortFictionBatchDraftSchema.parse({
      storyTitle: "失物招领处",
      chapters: [
        { number: 1, title: "旧钥匙", content: "第一章正文", charCount: 5 },
        { number: 2, title: "", content: "", charCount: 0 },
      ],
      rawContent: "",
    });
    expect(findIncompleteShortFictionChapters(persisted)).toEqual([2]);
    const markdown = renderShortFictionDraftMarkdown(persisted);

    expect(markdown).toContain("第1章 旧钥匙");
    expect(markdown).not.toContain("第2章");
  });
});
