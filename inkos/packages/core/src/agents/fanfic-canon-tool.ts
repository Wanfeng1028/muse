import { Type } from "@sinclair/typebox";

export const FanficCanonToolSchema = Type.Object({
  canonMarkdown: Type.String({ minLength: 1 }),
});
