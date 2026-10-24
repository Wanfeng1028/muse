import { Type } from "@sinclair/typebox";

export const ChapterDraftToolSchema = Type.Object({
  title: Type.String({ description: "Chapter title without a chapter-number prefix." }),
  content: Type.String({ description: "Complete chapter prose." }),
});
