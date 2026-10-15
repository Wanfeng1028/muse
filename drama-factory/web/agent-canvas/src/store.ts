import { create } from 'zustand';
import {
  CanvasNode,
  CanvasEdge,
  CanvasProject,
  NodeKind,
  NODE_KINDS,
  EMPTY_PROJECT,
  isCanvasProject,
} from './types.js';
import { parseConflictBody, ConflictInfo } from './conflict.js';

interface CanvasState {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  src: string;
  dirty: boolean;
  loading: boolean;
  error: string | null;
  revision: number | null;
  conflict: ConflictInfo | null;
  load: (src: string) => Promise<void>;
  dismissConflict: () => void;
  setNodes: (nodes: CanvasNode[]) => void;
  setEdges: (edges: CanvasEdge[]) => void;
  moveNode: (id: string, x: number, y: number) => void;
  addNode: (kind: NodeKind) => void;
  removeNode: (id: string) => void;
  removeEdge: (id: string) => void;
  connect: (source: string, target: string) => void;
  save: () => Promise<void>;
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  nodes: [],
  edges: [],
  src: '',
  dirty: false,
  loading: false,
  error: null,
  revision: null,
  conflict: null,

  load: async (src: string) => {
    set({ src, loading: true, error: null });
    try {
      const res = await fetch(src, { method: 'GET' });
      if (!res.ok) {
        set({
          loading: false,
          error: `加载失败，服务返回状态码 ${res.status}`,
          nodes: [],
          edges: [],
          dirty: false,
        });
        return;
      }
      const json: unknown = await res.json();
      if (!isCanvasProject(json)) {
        set({
          loading: false,
          error: '数据格式不对，缺少节点或连线字段，画布保持为空',
          nodes: [],
          edges: [],
          dirty: false,
        });
        return;
      }
      const project: CanvasProject = json;
      const rev = (json as { revision?: unknown }).revision;
      set({
        nodes: project.nodes,
        edges: project.edges,
        revision: typeof rev === 'number' ? rev : null,
        loading: false,
        dirty: false,
        error: null,
        conflict: null,
      });
    } catch (e) {
      const reason = e instanceof Error ? e.message : '未知错误';
      set({
        loading: false,
        error: `加载失败：${reason}，画布保持为空`,
        nodes: [],
        edges: [],
        dirty: false,
      });
    }
  },

  dismissConflict: () => {
    set({ conflict: null });
  },

  setNodes: (nodes: CanvasNode[]) => {
    set({ nodes, dirty: true });
  },

  setEdges: (edges: CanvasEdge[]) => {
    set({ edges, dirty: true });
  },

  moveNode: (id: string, x: number, y: number) => {
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, x, y } : n)),
      dirty: true,
    }));
  },

  addNode: (kind: NodeKind) => {
    const id = `n${Date.now()}`;
    const base = 200 + (get().nodes.length % 5) * 40;
    const node: CanvasNode = {
      id,
      kind,
      label: NODE_KINDS[kind].label,
      x: base,
      y: base,
      status: 'idle',
    };
    set((state) => ({ nodes: [...state.nodes, node], dirty: true }));
  },

  removeNode: (id: string) => {
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
      edges: state.edges.filter((e) => e.source !== id && e.target !== id),
      dirty: true,
    }));
  },

  removeEdge: (id: string) => {
    set((state) => ({
      edges: state.edges.filter((e) => e.id !== id),
      dirty: true,
    }));
  },

  connect: (source: string, target: string) => {
    if (!source || !target) return;
    if (source === target) return;
    const exists = get().edges.some(
      (e) => e.source === source && e.target === target,
    );
    if (exists) return;
    const edge: CanvasEdge = { id: `e${Date.now()}`, source, target };
    set((state) => ({ edges: [...state.edges, edge], dirty: true }));
  },

  save: async () => {
    const { src, nodes, edges, revision } = get();
    if (!src) {
      set({ error: '没有配置保存地址，无法保存' });
      return;
    }
    if (revision === null) {
      set({ error: '请先加载画布后再保存' });
      return;
    }
    set({ loading: true, error: null });
    try {
      const body = { base_version: revision, version: 1, nodes, edges };
      const res = await fetch(src, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.status === 409) {
        const info = parseConflictBody(await res.json().catch(() => null));
        set({
          loading: false,
          conflict: info ?? { currentVersion: -1, updatedBy: 'unknown' },
        });
        return;
      }
      if (!res.ok) {
        set({ loading: false, error: `保存失败，服务返回状态码 ${res.status}` });
        return;
      }
      const saved = (await res.json()) as { revision?: unknown };
      set({
        loading: false,
        dirty: false,
        error: null,
        conflict: null,
        revision: typeof saved.revision === 'number' ? saved.revision : revision,
      });
    } catch (e) {
      const reason = e instanceof Error ? e.message : '未知错误';
      set({ loading: false, error: `保存失败：${reason}` });
    }
  },
}));

export const EMPTY: CanvasProject = EMPTY_PROJECT;
export type { CanvasNode, CanvasEdge, NodeKind };
