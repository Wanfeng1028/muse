export interface PlayChoiceSet {
  readonly key: string;
  readonly choices: readonly string[];
}

export interface PlayPresentation {
  readonly renderId: string;
  readonly turn: number;
  readonly sceneText: string;
  readonly suggestedActions: readonly string[] | null;
}

/** Choices belong to the persisted world render, not the active chat transcript. */
export function presentationChoiceSet(presentation: PlayPresentation | null | undefined): PlayChoiceSet | null {
  return presentation?.suggestedActions?.length
    ? { key: presentation.renderId, choices: presentation.suggestedActions } : null;
}
