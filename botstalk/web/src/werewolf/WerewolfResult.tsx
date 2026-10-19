import { RotateCcw, Trophy, X } from 'lucide-react';
import { isWerewolfState } from './WerewolfPanel';
import './werewolf.css';

interface WerewolfResultProps {
  state: unknown;
  seat: string;
  onRematch: () => void;
  onClose: () => void;
}

const ROLE_LABEL: Record<string, string> = {
  werewolf: '狼人',
  villager: '平民',
  seer: '预言家',
  witch: '女巫',
  hunter: '猎人',
  guard: '守卫',
};

export default function WerewolfResult({ state, seat, onRematch, onClose }: WerewolfResultProps) {
  if (!isWerewolfState(state)) {
    return (
      <div className="werewolf-result">
        <div className="werewolf-result-title">结算数据同步中…</div>
      </div>
    );
  }

  const { winner, players } = state;
  const winnerText = winner === 'wolves' ? '狼人获胜' : winner === 'good' ? '好人获胜' : '对局结束';

  return (
    <div className="werewolf-result">
      <div className="werewolf-result-title">
        <Trophy size={16} strokeWidth={2} />
        <span>{winnerText}</span>
      </div>

      <div className="werewolf-result-rows">
        {players.map((p) => (
          <div className="werewolf-result-row" key={p.seat}>
            <span className="werewolf-result-seat">
              {p.seat}
              {p.seat === seat ? '（你）' : ''}
            </span>
            <span className="werewolf-result-role">{p.role ? ROLE_LABEL[p.role] ?? p.role : '未知'}</span>
            <span className="werewolf-result-state">{p.alive ? '存活' : '出局'}</span>
          </div>
        ))}
      </div>

      <div className="werewolf-result-actions">
        <button className="btn-primary" type="button" onClick={onRematch}>
          <RotateCcw size={16} strokeWidth={2} />
          <span>再来一局</span>
        </button>
        <button className="btn-ghost" type="button" onClick={onClose}>
          <X size={16} strokeWidth={2} />
          <span>关闭</span>
        </button>
      </div>
    </div>
  );
}
