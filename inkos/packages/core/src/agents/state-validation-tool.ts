import { Type } from "@sinclair/typebox";

export const StateValidationToolSchema = Type.Object({
  reconciliationRequired: Type.Boolean({
    description: "True only when recalculating the derived truth projection can resolve the mismatch. False for contradictions in prose or between authority sources.",
  }),
  reportMarkdown: Type.String({description:"Concise readable findings with source evidence. Explain every required projection correction and any unresolved authority conflict. Return an empty string when there are no findings."}),
});
