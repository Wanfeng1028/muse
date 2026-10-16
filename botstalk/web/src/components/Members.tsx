import { Bot, User } from 'lucide-react';

export interface MemberEntry {
  adapter_id: string;
  status: 'online' | 'offline';
  last_seen_ms: number;
  isSelf: boolean;
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

function MemberRow({ m, selfNick }: { m: MemberEntry; selfNick: string }) {
  const isSelf = m.adapter_id === selfNick || m.isSelf;
  return (
    <div className={`member ${m.status === 'online' ? 'is-online' : 'is-offline'}`}>
      <span className="member-icon" aria-hidden="true">
        {isSelf ? <User size={14} strokeWidth={2} /> : <Bot size={14} strokeWidth={2} />}
      </span>
      <span className="member-name">
        {m.adapter_id}
        {isSelf && <span className="member-you">（我）</span>}
      </span>
      <span className="member-dot" aria-hidden="true" />
    </div>
  );
}
