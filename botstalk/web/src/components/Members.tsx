import { Bot, User } from 'lucide-react';

export interface MemberEntry {
  adapter_id: string;
  status: 'online' | 'offline';
  last_seen_ms: number;
  isSelf: boolean;
  usage_in?: number;
  usage_out?: number;
}

interface Props {
  members: MemberEntry[];
  selfNick: string;
}

export default function Members({ members, selfNick }: Props) {
  const online = members.filter((m) => m.status === 'online');
  const offline = members.filter((m) => m.status !== 'online');

  return (
    <aside className="members" aria-label="成员列表">
      <div className="members-head">
        <span className="members-title">成员</span>
        <span className="members-count">{online.length} 在线</span>
      </div>
      <div className="members-list">
        {online.length === 0 && offline.length === 0 && (
          <div className="members-empty">还没有人</div>
        )}
        {online.map((m) => (
          <MemberRow key={m.adapter_id} m={m} selfNick={selfNick} />
        ))}
        {offline.length > 0 && (
          <div className="members-sep">离线</div>
        )}
        {offline.map((m) => (
          <MemberRow key={m.adapter_id} m={m} selfNick={selfNick} />
        ))}
      </div>
    </aside>
  );
}

const ROLE_COLORS = ['#7c8899', '#b3541e', '#2e7d32', '#8a6d3b', '#5b7fa6', '#4a7d7a'];

// 角色卡头像色只由 adapter_id 本身派生（字符和取模），同一成员每次渲染同一色，
// 不引入外部人名或品牌素材；职责只分老板与 Agent 两档，取自房间的派活/汇报规则。
function roleColor(adapterId: string): string {
  let sum = 0;
  for (let i = 0; i < adapterId.length; i += 1) sum += adapterId.charCodeAt(i);
  return ROLE_COLORS[sum % ROLE_COLORS.length];
}

function MemberRow({ m, selfNick }: { m: MemberEntry; selfNick: string }) {
  const isSelf = m.adapter_id === selfNick || m.isSelf;
  const hasUsage = typeof m.usage_in === 'number' || typeof m.usage_out === 'number';
  return (
    <div className={`member ${m.status === 'online' ? 'is-online' : 'is-offline'}`}>
      <span className="member-icon" aria-hidden="true" style={{ backgroundColor: roleColor(m.adapter_id) }}>
        {isSelf ? <User size={14} strokeWidth={2} /> : <Bot size={14} strokeWidth={2} />}
      </span>
      <span className="member-text">
        <span className="member-name">
          {m.adapter_id}
          {isSelf && <span className="member-you">（我）</span>}
          {m.status === 'online' && hasUsage && (
            <span className="member-usage">
              {fmt(m.usage_in ?? 0)} in / {fmt(m.usage_out ?? 0)} out
            </span>
          )}
          {m.status !== 'online' && (
            <span className="member-offline-tag">离线</span>
          )}
        </span>
        <span className="member-role">{isSelf ? '老板 · 派活、验收、拍板' : 'Agent · 接活、交接'}</span>
      </span>
      <span className="member-dot" aria-hidden="true" />
    </div>
  );
}

// 把大数字压短，方便一眼看个大概：12000 变成 12.0k，1200000 变成 1.2M
function fmt(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}
