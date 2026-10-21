import type {
  GovernedMemory,
  Matter,
  MemoryGraphResponse,
} from "@one-memory/contracts";
import { expect, it } from "vitest";
import { projectMatterMap } from "./matter-map";

const memory = (id: string, revision = 1): GovernedMemory => ({
  memory_id: id,
  user_id: "local",
  kind: "working",
  status: "confirmed",
  content: `Memory ${id}`,
  scopes: ["all-apps"],
  evidence_ids: ["e1"],
  origin: "extracted",
  tags: [],
  revision,
  created_at: "2026-09-12",
  updated_at: "2026-09-12",
  deleted_at: null,
});
const matter = {
  matter_id: "matter-1",
  availability: "ready",
  source_engine: "hy-memory",
  claims: [{ memory_refs: [{ memory_id: "m1", revision: 1 }] }],
} as Matter;
const graph: MemoryGraphResponse = {
  total_memories: 2,
  projected_memories: 2,
  hy_graph_available: true,
  nodes: [
    {
      node_id: "memory:m1",
      node_type: "memory",
      label: "First",
      memory_id: "m1",
      source_id: null,
      kind: "working",
      status: "confirmed",
      confidence: null,
    },
    {
      node_id: "memory:m2",
      node_type: "memory",
      label: "Other matter",
      memory_id: "m2",
      source_id: null,
      kind: "working",
      status: "confirmed",
      confidence: null,
    },
    {
      node_id: "source:codex",
      node_type: "source",
      label: "Codex",
      memory_id: null,
      source_id: "codex",
      kind: null,
      status: "active",
      confidence: null,
    },
  ],
  edges: [
    {
      edge_id: "e1",
      source_node_id: "memory:m1",
      target_node_id: "source:codex",
      relation: "evidence_source",
      origin: "provenance",
      weight: null,
    },
    {
      edge_id: "e2",
      source_node_id: "memory:m2",
      target_node_id: "source:codex",
      relation: "evidence_source",
      origin: "provenance",
      weight: null,
    },
  ],
};

it("projects referenced governed memories and their existing links only", () => {
  const result = projectMatterMap(matter, [memory("m1"), memory("m2")], graph);
  expect(result.memories.map((item) => item.memory_id)).toEqual(["m1"]);
  expect(result.graph.nodes.map((node) => node.node_id)).toEqual([
    "memory:m1",
    "source:codex",
  ]);
  expect(result.graph.edges.map((edge) => edge.edge_id)).toEqual(["e1"]);
});

it("never shows a revoked matter or a changed/deleted memory as the old reference", () => {
  expect(
    projectMatterMap(
      { ...matter, availability: "source_unavailable" },
      [memory("m1")],
      graph,
    ).graph.nodes,
  ).toEqual([]);
  expect(projectMatterMap(matter, [memory("m1", 2)], graph).memories).toEqual(
    [],
  );
  expect(
    projectMatterMap(matter, [{ ...memory("m1"), status: "deleted" }], graph)
      .memories,
  ).toEqual([]);
});

it("keeps actual memory nodes when a sampled graph omits them, without inventing relations", () => {
  const result = projectMatterMap(matter, [memory("m1")], null);
  expect(result.graph.nodes[0]).toMatchObject({
    memory_id: "m1",
    label: "Memory m1",
  });
  expect(result.graph.edges).toEqual([]);
  expect(result.graph.hy_graph_available).toBe(false);
});

it("does not turn legacy Wiki claims into governed memory nodes", () => {
  expect(
    projectMatterMap(
      { ...matter, source_engine: "legacy_direct" },
      [memory("m1")],
      graph,
    ).memories,
  ).toEqual([]);
});
