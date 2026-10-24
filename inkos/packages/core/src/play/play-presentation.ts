import { createHash, randomUUID } from "node:crypto";
import { z } from "zod";

export const PlayPresentationSchema = z.object({
  version: z.literal(1),
  renderId: z.string().min(1),
  turn: z.number().int().nonnegative(),
  sceneText: z.string(),
  // null means an old save has no trustworthy choice record; [] means no choices.
  suggestedActions: z.array(z.string()).nullable(),
}).strict();
export type PlayPresentation = z.infer<typeof PlayPresentationSchema>;

export function createPlayPresentation(turn: number, sceneText: string, suggestedActions: readonly string[] | null): PlayPresentation {
  return PlayPresentationSchema.parse({ version: 1, renderId: `render-${randomUUID()}`, turn, sceneText,
    suggestedActions: suggestedActions === null ? null : [...suggestedActions] });
}

export function legacyPresentation(turn: number, sceneText: string, transcriptRaw: string): PlayPresentation {
  const latest = transcriptRaw.trim().split("\n").filter(Boolean).map(line => JSON.parse(line)).at(-1);
  const suggestedActions = latest?.role === "assistant" && latest.content?.trim() === sceneText.trim()
    && Array.isArray(latest.suggestedActions) && latest.suggestedActions.every((item: unknown) => typeof item === "string")
    ? latest.suggestedActions as string[] : null;
  const identity = JSON.stringify({ turn, sceneText, suggestedActions });
  return { version: 1, renderId: `legacy-${createHash("sha256").update(identity).digest("hex").slice(0,24)}`, turn, sceneText, suggestedActions };
}
