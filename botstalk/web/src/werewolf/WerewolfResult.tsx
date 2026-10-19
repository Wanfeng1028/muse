import { Trophy, RotateCcw, X } from 'lucide-react';
import { isWerewolfState } from './WerewolfPanel';
import './werewolf.css';

interface WerewolfResultProps {
  state: unknown;
  seat: string;
  onRematch: () => void;
  onClose: () => void;
}

const ROLE_TEXT: Record<string, string> = {
  werewolf: '狼人',
  villager: '平民',
  seer: '预言家',
  witch: '女巫',
  hunter: '猎人',
  guard: '守卫',
};

const DEATH_REASON_TEXT: Record<string, string> = {
  wolf: '被刀',
  witch: '被毒',
  vote: '放逐',
  hunter: '被带走',
};

export default function WerewolfResult({ state, seat, onRematch, onClose }: WerewolfResultProps) {
  if (!isWerewolfState(state)) {
    return (
      <div className="werewolf-result">
        <div className="werewolf-result-title">结算数据同步中…</div>
      </div>
    );
  }

  const { winner, players, wolfSeats, deaths } = state;

  const me = players.find((p) => p.seat === seat);

  let myCamp: 'wolves' | 'good' | null = null;
  if (me && me.role) {
    myCamp = me.role === 'werewolf' ? 'wolves' : 'good';
  } else if (wolfSeats) {
    myCamp = wolfSeats.includes(seat) ? 'wolves' : 'good';
  }

  const winnerText =
    winner === 'wolves' ? '狼人阵营获胜' : winner === 'good' ? '好人阵营获胜' : '对局结束';

  const won = winner !== undefined && myCamp !== null && winner === myCamp;

  return (
    <div className="werewolf-result">
      <div className="werewolf-result-title">
        <Trophy size={16} strokeWidth={2} />
        <span>{winnerText}</span>
        {winner !== undefined && myCamp !== null && <span>{won ? '你赢了' : '你输了'}</span>}
      </div>

      <div className="werewolf-result-rows">
        {players.map((p) => {
          const death = deaths.find((d) => d.seat === p.seat);
          const roleText = p.role ? ROLE_TEXT[p.role] ?? p.role : '未知';
          return (
            <div className="werewolf-result-row" key={p.seat}>
              <span>
                {p.seat}
                {p.seat === seat ? '（你）' : ''}
              </span>
              <span>{roleText}</span>
              <span>
                {p.alive
                  ? '存活'
                  : death
                    ? `出局 · ${DEATH_REASON_TEXT[death.reason] ?? ''}`
                    : '出局'}
              </span>
            </div>
          );
        })}
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
