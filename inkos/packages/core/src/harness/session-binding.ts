import type { SessionKind } from "../interaction/session.js";

const PROFILE_ID_BY_SESSION_KIND: Readonly<Record<SessionKind, string>> = {
  chat: "workspace-default",
  work: "workspace-default",
  "book-create": "longform-novel",
  book: "longform-novel",
  edit: "longform-novel",
  short: "short-fiction",
  script: "script",
  storyboard: "storyboard",
  "interactive-film": "interactive-film",
  "interactive-film-authoring": "interactive-film",
  play: "interactive-world",
};

export function resolveSessionHarnessBinding(input: {
  readonly sessionKind: SessionKind;
  readonly bookId: string | null;
  readonly sessionId: string;
}): { readonly profileId: string; readonly workId: string | null } {
  return {
    profileId: PROFILE_ID_BY_SESSION_KIND[input.sessionKind],
    workId: input.bookId ?? (input.sessionKind === "play" ? input.sessionId : null),
  };
}
