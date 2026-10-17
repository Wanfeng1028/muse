import { Trophy, RotateCcw, X } from 'lucide-react';
import { isDoudizhuState } from './DoudizhuPanel';
import './doudizhu.css';

interface DoudizhuResultProps {
  state: unknown;
  seat: string;
  onRematch: () => void;
  onClose: () => void;
}

export default function DoudizhuResult({ state, seat, onRematch, onClose }: DoudizhuResultProps) {
  if (!isDoudizhuState(state)) {
    return (
      <div className="doudizhu-result">
        <div className="doudizhu-result-title">结算数据同步中…</div>
      </div>
    );
  }

  const { winner, players, landlordSeat, baseScore, bombs, spring } = state;
  const won = winner !== null && winner !== undefined && seat === winner;

  return (
    <div className="doudizhu-result">
      <div className="doudizhu-result-title">
        <Trophy size={16} strokeWidth={2} />
        <span>{winner ? `获胜：${winner}` : '对局结束'}</span>
        <span>{won ? '你赢了' : '你输了'}</span>
      </div>

      <div className="doudizhu-result-mult">
        <span>{`底分 ${baseScore} × 炸弹翻倍 ${Math.pow(2, bombs)}`}</span>
        {spring ? <span className="doudizhu-spring">春天 ×2</span> : null}
      </div>

      <div className="doudizhu-result-rows">
        {players.map((p) => (
          <div className="doudizhu-result-row" key={p.seat}>
            <span>{p.seat}</span>
            <span>{p.seat === landlordSeat ? '地主' : '农民'}</span>
            <span>{`剩余 ${Array.isArray(p.hand) ? p.hand.length : 0} 张`}</span>
          </div>
        ))}
      </div>

      <div className="doudizhu-result-actions">
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