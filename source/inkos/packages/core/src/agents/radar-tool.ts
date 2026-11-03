import { Type } from "@sinclair/typebox";

const PlatformSchema = Type.Union([
  Type.Literal("tomato"),
  Type.Literal("feilu"),
  Type.Literal("qidian"),
  Type.Literal("other"),
]);

export const RadarResultToolSchema = Type.Object({
  recommendations: Type.Array(Type.Object({
    platform: PlatformSchema,
    genre: Type.String(),
    concept: Type.String(),
    reasoning: Type.String(),
    benchmarkTitles: Type.Array(Type.String()),
  })),
  marketSummary: Type.String(),
});
