import { it, expect } from "vitest";
import { presentationChoiceSet } from "../play-choices";

it("keys choices by the restored render, keeping absent legacy choices distinct from a previous chat", () => {
  const current = { renderId: "render-1", turn: 3, sceneText: "scene", suggestedActions: ["Wait", "Leave"] };
  expect(presentationChoiceSet(current)).toEqual({ key: "render-1", choices: current.suggestedActions });
  expect(presentationChoiceSet({ ...current, renderId: "render-2", suggestedActions: ["Look", "Ask"] }))
    .toEqual({ key: "render-2", choices: ["Look", "Ask"] });
  expect(presentationChoiceSet(current)).toEqual({ key: "render-1", choices: current.suggestedActions });
  expect(presentationChoiceSet({ ...current, suggestedActions: [] })).toBeNull();
  expect(presentationChoiceSet({ ...current, suggestedActions: null })).toBeNull();
});
