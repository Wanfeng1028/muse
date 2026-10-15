import { Handle, Position, NodeProps } from '@xyflow/react';
import { NodeKind, NodeStatus, NODE_KINDS } from '../types';

export interface DramaNodeData {
  label: string;
  kind: NodeKind;
  status: NodeStatus;
  [key: string]: unknown;
}

const STATUS_COLOR: Record<NodeStatus, string> = {
  idle: '#9ca3af',
  running: '#3b82f6',
  done: '#22c55e',
  failed: '#ef4444',
};

const STATUS_TEXT: Record<NodeStatus, string> = {
  idle: '待命',
  running: '运行中',
  done: '已完成',
  failed: '失败',
};

const handleStyle: React.CSSProperties = {
  width: 8,
  height: 8,
  background: '#9ca3af',
  border: '1px solid #ffffff',
};

export default function DramaNode(props: NodeProps) {
  const data = props.data as DramaNodeData;
  const kind = data.kind;
  const status = data.status;
  const meta = NODE_KINDS[kind];

  return (
    <div
      className="agent-canvas-node"
      style={{
        width: 180,
        background: '#ffffff',
        border: '1px solid #e5e7eb',
        borderRadius: 8,
        overflow: 'hidden',
        boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
        fontFamily: 'inherit',
      }}
    >
      <div
        style={{
          height: 4,
          background: meta.color,
          borderTopLeftRadius: 7,
          borderTopRightRadius: 7,
        }}
      />
      <Handle type="target" position={Position.Top} style={handleStyle} />
      <div style={{ padding: '8px 10px 10px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 6,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: '#6b7280',
              letterSpacing: 0.2,
            }}
          >
            {meta.label}
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: STATUS_COLOR[status],
              }}
            />
            <span style={{ fontSize: 11, color: '#6b7280' }}>
              {STATUS_TEXT[status]}
            </span>
          </span>
        </div>
        <div
          style={{
            fontSize: 14,
            color: '#111827',
            fontWeight: 500,
            lineHeight: 1.4,
            wordBreak: 'break-word',
          }}
        >
          {data.label}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} style={handleStyle} />
    </div>
  );
}
