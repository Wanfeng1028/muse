import { describe, expect, it } from "vitest";
import { materializeStoryGraph } from "../interactive-film/generate.js";

function playableGraphContent() {
  return {
    worldAnchor: {
      storyCore: "A branching mystery",
      theme: "Trust",
      genre: "Mystery",
      worldRules: "Choices persist",
      durationMinutes: 15,
    },
    characters: [],
    variables: [{ name: "trust", type: "relationship", default: 0, desc: "Trust" }],
    nodes: [
      {
        id: "s",
        type: "start" as const,
        title: "Opening",
        sceneDesc: "The player chooses.",
        dialogue: [],
        choices: [
          { id: "s-e1", text: "report", targetNodeId: "e1", effects: [{ var: "trust", op: "add" as const, value: 1 }] },
          { id: "s-e2", text: "investigate", targetNodeId: "e2", effects: [{ var: "trust", op: "sub" as const, value: 1 }] },
        ],
        act: "one",
      },
      { id: "e1", type: "ending" as const, title: "Report", sceneDesc: "Reported.", dialogue: [], choices: [], act: "two" },
      { id: "e2", type: "ending" as const, title: "Investigate", sceneDesc: "Investigated.", dialogue: [], choices: [], act: "two" },
    ],
    endings: [
      { id: "ending-1", nodeId: "e1", title: "Report", type: "neutral", description: "Reported." },
      { id: "ending-2", nodeId: "e2", title: "Investigate", type: "neutral", description: "Investigated." },
    ],
  };
}

describe("interactive-film graph materialization", () => {
  it("keeps host-owned identity authoritative", () => {
    const graph = materializeStoryGraph({
      projectId: "real-id",
      title: "Real title",
      content: playableGraphContent(),
    });

    expect(graph.projectId).toBe("real-id");
    expect(graph.title).toBe("Real title");
    expect(graph.nodes).toHaveLength(3);
  });

  it("rejects a structurally typed but unplayable graph", () => {
    const content = playableGraphContent();
    content.nodes[0] = { ...content.nodes[0]!, choices: [] };

    expect(() => materializeStoryGraph({
      projectId: "p",
      title: "T",
      content,
    })).toThrow();
  });

  it("accepts an opening node that directly carries the meaningful branch", () => {
    const graph = materializeStoryGraph({
      projectId: "p",
      title: "T",
      content: playableGraphContent(),
    });

    expect(graph.nodes[0]?.type).toBe("start");
    expect(graph.nodes[0]?.choices).toHaveLength(2);
  });
});
