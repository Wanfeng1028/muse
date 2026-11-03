import { useEffect, useState } from 'react';
import { Play, X, Gavel } from 'lucide-react';
import { rankLabel, suitMark, sortHand } from './cards';
import './doudizhu.css';

interface DoudizhuPlayer {
  seat: string;
  hand: number[];
  isLandlord: boolean;
}

interface DoudizhuLastPlay {
  seat: string;
  combo: unknown;
}

export interface DoudizhuState {
  phase: 'bidding' | 'playing' | 'finished';
  players: DoudizhuPlayer[];
  landlordSeat?: string;
  currentSeat: string;
  lastPlay: DoudizhuLastPlay | null;
  baseScore: number;
  bombs: number;
  spring?: boolean;
  winner?: string;
}

export function isDoudizhuState(value: unknown): value is DoudizhuState {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  const phase = v.phase;
  if (phase !== 'bidding' && phase !== 'playing' && phase !== 'finished') return false;
  if (!Array.isArray(v.players)) return false;
  for (const p of v.players) {
    if (typeof p !== 'object' || p === null) return false;
    const pp = p as Record<string, unknown>;
    if (typeof pp.seat !== 'string') return false;
    if (!Array.isArray(pp.hand)) return false;
    if (typeof pp.isLandlord !== 'boolean') return false;
  }
  if (typeof v.currentSeat !== 'string') return false;
  if (typeof v.baseScore !== 'number') return false;
  if (typeof v.bombs !== 'number') return false;
  if (v.lastPlay !== null) {
    if (typeof v.lastPlay !== 'object') return false;
    const lp = v.lastPlay as Record<string, unknown>;
    if (typeof lp.seat !== 'string') return false;
    if (!('combo' in lp)) return false;
  }
  return true;
}

interface Props {
  state: unknown;
  seat: string;
  onAction: (action: unknown) => void;
}

function lastPlayCards(combo: unknown): number[] {
  if (Array.isArray(combo)) {
    return combo.filter((c): c is number => typeof c === 'number');
  }
  if (combo && typeof combo === 'object' && 'cards' in combo) {
    const cards = (combo as { cards: unknown }).cards;
    if (Array.isArray(cards)) {
      return cards.filter((c): c is number => typeof c === 'number');
    }
  }
  return [];
}

function Card({
  n,
  selected,
  onClick,
  interactive,
}: {
  n: number;
  selected?: boolean;
  onClick?: () => void;
  interactive: boolean;
}) {
  const { mark, red } = suitMark(n);
  const classes = ['doudizhu-card'];
  if (selected) classes.push('is-selected');
  if (red) classes.push('red');
  if (interactive) classes.push('is-interactive');
  return (
    <div className={classes.join(' ')} onClick={interactive ? onClick : undefined}>
      <span className="doudizhu-card-rank">{rankLabel(n)}</span>
      {mark && <span className="doudizhu-card-suit">{mark}</span>}
    </div>
  );
}

export default function DoudizhuPanel({ state, seat, onAction }: Props) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    setSelected(new Set());
  }, [state]);

  if (!isDoudizhuState(state)) {
    return <div className="doudizhu-empty">局面同步中…</div>;
  }

  if (state.phase === 'finished') return null;

  const { phase, players, currentSeat, lastPlay, baseScore, bombs } = state;

  const me = players.find((p) => p.seat === seat);
  const myHand = me ? sortHand(me.hand) : [];
  const isMyTurn = currentSeat === seat;

  const phaseText =
    phase === 'bidding' ? '叫分中' : phase === 'playing' ? '出牌中' : '已结束';

  const multiplier = baseScore * Math.pow(2, bombs);

  const toggleSelect = (index: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const handlePlay = () => {
    const cards: number[] = [];
    selected.forEach((i) => {
      if (i >= 0 && i < myHand.length) cards.push(myHand[i]);
    });
    onAction({ kind: 'play', cards });
    setSelected(new Set());
  };

  const handlePass = () => {
    onAction({ kind: 'play', cards: [] });
    setSelected(new Set());
  };

  const canPass = lastPlay !== null && lastPlay.seat !== seat;

  return (
    <div className="doudizhu-panel">
      <div className="doudizhu-bar">
        <span className="doudizhu-bar-phase">{phaseText}</span>
        <span className="doudizhu-bar-turn">
          轮到：{currentSeat}
          {currentSeat === seat ? '（你）' : ''}
        </span>
        <span className="doudizhu-bar-mult">倍数：{baseScore}×{Math.pow(2, bombs)}</span>
        <span className="doudizhu-bar-bombs">炸弹数：{bombs}</span>
        <span className="doudizhu-bar-total">当前分：{multiplier}</span>
      </div>

      <div className="doudizhu-seats">
        {players.map((p) => {
          const cls = ['doudizhu-seat'];
          if (p.seat === currentSeat) cls.push('is-current');
          if (p.isLandlord) cls.push('is-landlord');
          return (
            <div key={p.seat} className={cls.join(' ')}>
              <span className="doudizhu-seat-name">
                {p.seat}
                {p.seat === seat ? '（你）' : ''}
              </span>
              {p.isLandlord && <span className="doudizhu-seat-badge">地主</span>}
              <span className="doudizhu-seat-count">{p.hand.length} 张</span>
            </div>
          );
        })}
      </div>

      {lastPlay ? (
        <div className="doudizhu-lastplay">
          <span className="doudizhu-lastplay-label">{lastPlay.seat} 出了：</span>
          <span className="doudizhu-lastplay-cards">
            {lastPlayCards(lastPlay.combo).map((c, i) => (
              <span key={i} className="doudizhu-lastplay-card">
                {rankLabel(c)}
              </span>
            ))}
          </span>

        </div>
      ) : phase === 'playing' ? (
        <div className="doudizhu-lastplay">自由出牌</div>
      ) : null}

      {phase === 'bidding' && (
        <div className="doudizhu-bidrow">
          {isMyTurn ? (
            <>
              <button
                className="btn-ghost"
                onClick={() => onAction({ kind: 'bid', score: 0 })}
              >
                <X size={14} />
                不叫
              </button>
              <button
                className="btn-primary"
                onClick={() => onAction({ kind: 'bid', score: 1 })}
              >
                <Gavel size={14} />
                1分
              </button>
              <button
                className="btn-primary"
                onClick={() => onAction({ kind: 'bid', score: 2 })}
              >
                <Gavel size={14} />
                2分
              </button>
              <button
                className="btn-primary"
                onClick={() => onAction({ kind: 'bid', score: 3 })}
              >
                <Gavel size={14} />
                3分
              </button>
            </>
          ) : (
            <span className="doudizhu-wait">等 {currentSeat} 叫分…</span>
          )}
        </div>
      )}

      {phase === 'playing' && (
        <>
          <div className="doudizhu-hand">
            {myHand.map((n, i) => (
              <Card
                key={i}
                n={n}
                selected={selected.has(i)}
                onClick={() => toggleSelect(i)}
                interactive={isMyTurn}
              />
            ))}
          </div>
          <div className="doudizhu-actions">
            {isMyTurn ? (
              <>
                <button
                  className="btn-primary"
                  disabled={selected.size === 0}
                  onClick={handlePlay}
                >
                  <Play size={14} />
                  出牌
                </button>
                <button className="btn-ghost" disabled={!canPass} onClick={handlePass}>
                  <X size={14} />
                  不出
                </button>
              </>
            ) : (
              <span className="doudizhu-wait">等 {currentSeat} 出牌…</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}