import type {
  GovernedMemory,
  Matter,
  MemoryGraphNode,
  MemoryGraphResponse,
} from "@one-memory/contracts";

export function projectMatterMap(
  matter: Matter | undefined,
  memories: GovernedMemory[],
  graph: MemoryGraphResponse | null,
): { memories: GovernedMemory[]; graph: MemoryGraphResponse } {
  const readable =
    matter?.source_engine === "hy-memory" &&
    ["ready", "needs_update"].includes(matter.availability);
  const refs = readable
    ? matter.claims.flatMap((claim) => claim.memory_refs)
    : [];
  const items = memories.filter(
    (memory) =>
      memory.status === "confirmed" &&
      refs.some(
        (ref) =>
          ref.memory_id === memory.memory_id &&
          ref.revision === memory.revision,
      ),
  );
  const ids = new Set(items.map((item) => item.memory_id));
  const memoryNodes = (graph?.nodes ?? []).filter(
    (node) => node.memory_id && ids.has(node.memory_id),
  );
  for (const item of items) {
    if (!memoryNodes.some((node) => node.memory_id === item.memory_id)) {
      memoryNodes.push({
        node_id: `memory:${item.memory_id}`,
        node_type: "memory",
        label: item.content,
        memory_id: item.memory_id,
        source_id: null,
        kind: item.kind,
        status: item.status,
        confidence: null,
      });
    }
  }
  const nodeIds = new Set(memoryNodes.map((node) => node.node_id));
  const neighborIds = new Set(
    (graph?.edges ?? []).flatMap((edge) =>
      nodeIds.has(edge.source_node_id)
        ? [edge.target_node_id]
        : nodeIds.has(edge.target_node_id)
          ? [edge.source_node_id]
          : [],
    ),
  );
  const nodes: MemoryGraphNode[] = [
    ...memoryNodes,
    ...(graph?.nodes ?? []).filter(
      (node) => !node.memory_id && neighborIds.has(node.node_id),
    ),
  ];
  const visible = new Set(nodes.map((node) => node.node_id));
  return {
    memories: items,
    graph: {
      total_memories: items.length,
      projected_memories: items.length,
      nodes,
      edges: (graph?.edges ?? []).filter(
        (edge) =>
          visible.has(edge.source_node_id) && visible.has(edge.target_node_id),
      ),
      hy_graph_available: graph?.hy_graph_available ?? false,
    },
  };
}
