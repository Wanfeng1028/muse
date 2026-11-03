import { Type } from "@sinclair/typebox";

const StringArray = Type.Array(Type.String());

export const ForecastResultToolSchema = Type.Object({
  branches: Type.Array(Type.Object({
    title: Type.String(),
    premise: Type.String(),
    beats: Type.Array(Type.Object({
      chapter: Type.Integer({ minimum: 1 }),
      summary: Type.String(),
    })),
    characterDecisions: Type.Array(Type.Object({
      character: Type.String(),
      decision: Type.String(),
    })),
    projectedChanges: Type.Object({
      characters: StringArray,
      relationships: StringArray,
      world: StringArray,
      hooks: StringArray,
    }),
    risks: Type.Array(Type.Object({
      kind: Type.String(),
      description: Type.String(),
    })),
    uncertainties: StringArray,
    intentRationale: Type.String(),
  }), { minItems: 1 }),
});
