import { Type } from "@sinclair/typebox";

export const ChapterRewriteToolSchema = Type.Object({
  revisedContent: Type.String({ minLength: 1, description: "Complete revised chapter prose." }),
});
