export type NodeKind = 'script' | 'storyboard' | 'video' | 'edit' | 'qc';
export type NodeStatus = 'idle' | 'running' | 'done' | 'failed';

export interface CanvasNode {
  id: string;
  kind: NodeKind;
  label: string;
  x: number;
  y: number;
  status: NodeStatus;
}

export interface CanvasEdge {
  id: string;
  source: string;
  target: string;
}

export interface CanvasProject {
  version: 1;
  nodes: CanvasNode[];
  edges: CanvasEdge[];
}

export const NODE_KINDS: Record<NodeKind, { label: string; color: string }> = {
  script: { label: '编剧', color: '#2563eb' },
  storyboard: { label: '分镜', color: '#d97706' },
  video: { label: '视频生成', color: '#059669' },
  edit: { label: '剪辑', color: '#dc2626' },
  qc: { label: '质检', color: '#475569' },
};

export const EMPTY_PROJECT: CanvasProject = {
  version: 1,
  nodes: [],
  edges: [],
};

const NODE_KIND_SET: ReadonlySet<string> = new Set<NodeKind>([
  'script',
  'storyboard',
  'video',
  'edit',
  'qc',
]);

const NODE_STATUS_SET: ReadonlySet<string> = new Set<NodeStatus>([
  'idle',
  'running',
  'done',
  'failed',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isCanvasNode(value: unknown): value is CanvasNode {
  if (!isRecord(value)) {
    return false;
  }
  const { id, kind, label, x, y, status } = value;
  return (
    typeof id === 'string' &&
    typeof kind === 'string' &&
    NODE_KIND_SET.has(kind) &&
    typeof label === 'string' &&
    typeof x === 'number' &&
    typeof y === 'number' &&
    typeof status === 'string' &&
    NODE_STATUS_SET.has(status)
  );
}

function isCanvasEdge(value: unknown): value is CanvasEdge {
  if (!isRecord(value)) {
    return false;
  }
  const { id, source, target } = value;
  return (
    typeof id === 'string' &&
    typeof source === 'string' &&
    typeof target === 'string'
  );
}

export function isCanvasProject(value: unknown): value is CanvasProject {
  if (!isRecord(value)) {
    return false;
  }
  const { version, nodes, edges } = value;
  return (
    version === 1 &&
    Array.isArray(nodes) &&
    nodes.every(isCanvasNode) &&
    Array.isArray(edges) &&
    edges.every(isCanvasEdge)
  );
}
