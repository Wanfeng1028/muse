import { useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Panel,
  Controls,
  Node as RFNode,
  Edge as RFEdge,
  NodeChange,
  EdgeChange,
  Connection,
  applyNodeChanges,
  applyEdgeChanges,
} from '@xyflow/react';
import DramaNode, { DramaNodeData } from './nodes/DramaNode';
import { useCanvasStore } from './store';
import { NodeKind, NODE_KINDS } from './types';
import { conflictMessage } from './conflict';

const nodeTypes = { drama: DramaNode };

const KIND_ORDER: NodeKind[] = ['script', 'storyboard', 'video', 'edit', 'qc'];

export default function AgentCanvas() {
  const nodes = useCanvasStore((s) => s.nodes);
  const edges = useCanvasStore((s) => s.edges);
  const dirty = useCanvasStore((s) => s.dirty);
  const loading = useCanvasStore((s) => s.loading);
  const error = useCanvasStore((s) => s.error);
  const moveNode = useCanvasStore((s) => s.moveNode);
  const removeNode = useCanvasStore((s) => s.removeNode);
  const removeEdge = useCanvasStore((s) => s.removeEdge);
  const connect = useCanvasStore((s) => s.connect);
  const addNode = useCanvasStore((s) => s.addNode);
  const save = useCanvasStore((s) => s.save);
  const conflict = useCanvasStore((s) => s.conflict);
  const dismissConflict = useCanvasStore((s) => s.dismissConflict);
  const src = useCanvasStore((s) => s.src);
  const reload = useCanvasStore((s) => s.load);

  const [kind, setKind] = useState<NodeKind>('script');
  const [rfNodes, setRfNodes] = useState<RFNode[]>([]);
  const [rfEdges, setRfEdges] = useState<RFEdge[]>([]);

  useEffect(() => {
    setRfNodes(
      nodes.map((n) => ({
        id: n.id,
        type: 'drama',
        position: { x: n.x, y: n.y },
        data: {
          label: n.label,
          kind: n.kind,
          status: n.status,
        } satisfies DramaNodeData,
      })),
    );
  }, [nodes]);

  useEffect(() => {
    setRfEdges(
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      })),
    );
  }, [edges]);

  const onNodesChange = (changes: NodeChange[]) => {
    setRfNodes((prev) => applyNodeChanges(changes, prev));
    for (const c of changes) {
      if (c.type === 'position' && c.position) {
        moveNode(c.id, c.position.x, c.position.y);
      } else if (c.type === 'remove') {
        removeNode(c.id);
      }
    }
  };

  const onEdgesChange = (changes: EdgeChange[]) => {
    setRfEdges((prev) => applyEdgeChanges(changes, prev));
    for (const c of changes) {
      if (c.type === 'remove') {
        removeEdge(c.id);
      }
    }
  };

  const onConnect = (conn: Connection) => {
    if (!conn.source || !conn.target) return;
    connect(conn.source, conn.target);
  };

  const saving = loading && dirty;

  return (
    <div className="agent-canvas-root">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e7eb" />

        <Panel position="top-left">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 10px',
              background: '#ffffff',
              border: '1px solid #e5e7eb',
              borderRadius: 8,
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
              fontFamily: 'inherit',
            }}
          >
            <span style={{ fontSize: 12, color: '#6b7280' }}>编排画布</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as NodeKind)}
              style={{
                fontSize: 12,
                padding: '4px 6px',
                border: '1px solid #e5e7eb',
                borderRadius: 6,
                background: '#ffffff',
                color: '#111827',
              }}
            >
              {KIND_ORDER.map((k) => (
                <option key={k} value={k}>
                  {NODE_KINDS[k].label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => addNode(kind)}
              style={{
                fontSize: 12,
                padding: '5px 10px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                background: '#ffffff',
                color: '#111827',
                cursor: 'pointer',
              }}
            >
              添加节点
            </button>
            <button
              type="button"
              onClick={() => save()}
              disabled={saving}
              style={{
                fontSize: 12,
                padding: '5px 10px',
                border: dirty ? '1px solid #2563eb' : '1px solid #d1d5db',
                borderRadius: 6,
                background: dirty ? '#2563eb' : '#ffffff',
                color: dirty ? '#ffffff' : '#111827',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
          {loading && !saving && (
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
              画布加载中…
            </div>
          )}
          {error && (
            <div
              style={{
                fontSize: 12,
                color: '#dc2626',
                marginTop: 6,
                maxWidth: 320,
              }}
            >
              {error}
            </div>
          )}
        </Panel>

        <Panel position="bottom-right">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end' }}>
            <Controls />
          </div>
        </Panel>
      </ReactFlow>
      {conflict && (
        <div className="agent-canvas-conflict-overlay">
          <div className="agent-canvas-conflict-box">
            <div className="agent-canvas-conflict-title">{conflictMessage(conflict)}</div>
            <div className="agent-canvas-conflict-sub">
              当前版本 {conflict.currentVersion}，最后修改者：{conflict.updatedBy}
            </div>
            <div className="agent-canvas-conflict-actions">
              <button
                type="button"
                className="agent-canvas-conflict-btn primary"
                onClick={() => {
                  dismissConflict();
                  void reload(src);
                }}
              >
                刷新
              </button>
              <button
                type="button"
                className="agent-canvas-conflict-btn"
                onClick={() => dismissConflict()}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
