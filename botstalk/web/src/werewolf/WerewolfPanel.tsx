import { useEffect, useState } from 'react';
import { Check, Moon, Skull, Sun, Vote } from 'lucide-react';
import './werewolf.css';

type WerewolfPhase =
  | 'night'
  | 'announce'
  | 'lastwords'
  | 'sheriff'
  | 'speak'
  | 'vote'
  | 'pk_speak'
  | 'pk_vote'
  | 'finished';

type Role = 'werewolf' | 'villager' | 'seer' | 'witch' | 'hunter' | 'guard';

interface WerewolfPlayer {
  seat: string;
  alive: boolean;
  isSheriff: boolean;
  role?: Role;
}

interface WerewolfDeath {
  seat: string;
  reason: 'wolf' | 'poison' | 'vote' | 'shot';
  day: number;
}

interface WerewolfVoteRecord {
  voter: string;
  target: string | null;
}

interface WerewolfVoteRound {
  day: number;
  records: WerewolfVoteRecord[];
  exiled: string | null;
}

interface WerewolfSeerEntry {
  seat: string;
  result: 'wolf' | 'good';
  day: number;
}

export interface WerewolfView {
  phase: WerewolfPhase;
  day: number;
  currentSeat: string;
  nightStep?: 'guard' | 'wolves' | 'seer' | 'witch';
  players: WerewolfPlayer[];
  deaths: WerewolfDeath[];
  lastwordsQueue: string[];
  lastwordsIdx: number;
  sheriffSeat?: string;
  votes: WerewolfVoteRound[];
  pkSeats: string[];
  sheriffVotes: WerewolfVoteRecord[];
  hunterShootPending?: string;
  wolfSeats?: string[];
  seerHistory?: WerewolfSeerEntry[];
  winner?: 'wolves' | 'good';
}

const ROLE_LABEL: Record<Role, string> = {
  werewolf: '狼人',
  villager: '平民',
  seer: '预言家',
  witch: '女巫',
  hunter: '猎人',
  guard: '守卫',
};

const PHASE_LABEL: Record<WerewolfPhase, string> = {
  night: '天黑请闭眼',
  announce: '公布死讯',
  lastwords: '遗言',
  sheriff: '竞选警长',
  speak: '发言',
  vote: '投票放逐',
  pk_speak: 'PK 发言',
  pk_vote: 'PK 投票',
  finished: '已结束',
};

const DEATH_LABEL: Record<WerewolfDeath['reason'], string> = {
  wolf: '夜里被刀',
  poison: '被女巫毒死',
  vote: '被投票放逐',
  shot: '被猎人带走',
};

export function isWerewolfState(value: unknown): value is WerewolfView {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  const phase = v.phase;
  if (
    phase !== 'night' &&
    phase !== 'announce' &&
    phase !== 'lastwords' &&
    phase !== 'sheriff' &&
    phase !== 'speak' &&
    phase !== 'vote' &&
    phase !== 'pk_speak' &&
    phase !== 'pk_vote' &&
    phase !== 'finished'
  ) {
    return false;
  }
  if (typeof v.day !== 'number') return false;
  if (typeof v.currentSeat !== 'string') return false;
  if (!Array.isArray(v.players)) return false;
  for (const p of v.players) {
    if (typeof p !== 'object' || p === null) return false;
    const pp = p as Record<string, unknown>;
    if (typeof pp.seat !== 'string') return false;
    if (typeof pp.alive !== 'boolean') return false;
    if (typeof pp.isSheriff !== 'boolean') return false;
  }
  if (!Array.isArray(v.deaths)) return false;
  if (!Array.isArray(v.lastwordsQueue)) return false;
  if (typeof v.lastwordsIdx !== 'number') return false;
  if (!Array.isArray(v.votes)) return false;
  if (!Array.isArray(v.pkSeats)) return false;
  if (!Array.isArray(v.sheriffVotes)) return false;
  return true;
}

interface Props {
  state: unknown;
  seat: string;
  onAction: (action: unknown) => void;
}

function aliveSeats(players: WerewolfPlayer[]): string[] {
  return players.filter((p) => p.alive).map((p) => p.seat);
}

function seatLabel(seat: string, me: string): string {
  return seat === me ? `${seat}（你）` : seat;
}

export default function WerewolfPanel({ state, seat, onAction }: Props) {
  const [target, setTarget] = useState<string | null>(null);

  useEffect(() => {
    setTarget(null);
  }, [state]);

  if (!isWerewolfState(state)) {
    return <div className="werewolf-empty">局面同步中…</div>;
  }

  if (state.phase === 'finished') return null;

  const {
    phase,
    day,
    currentSeat,
    players,
    deaths,
    lastwordsQueue,
    lastwordsIdx,
    sheriffSeat,
    pkSeats,
    hunterShootPending,
    wolfSeats,
    seerHistory,
  } = state;

  const me = players.find((p) => p.seat === seat);
  const myRole = me?.role;
  const isMyTurn = currentSeat === seat;
  const isNight = phase === 'night';
  const alive = aliveSeats(players);

  const todayDeaths = deaths.filter((d) => d.day === day);

  const renderTargetPicker = (
    candidates: string[],
    actionKind: 'night' | 'vote' | 'hunter_shoot' | 'sheriff',
    extra?: Record<string, unknown>,
  ) => (
    <div className="werewolf-targets">
      {candidates.map((s) => {
        const cls = ['werewolf-target'];
        if (target === s) cls.push('is-picked');
        return (
          <button
            key={s}
            type="button"
            className={cls.join(' ')}
            onClick={() => setTarget(s)}
          >
            {seatLabel(s, seat)}
          </button>
        );
      })}
      <button
        type="button"
        className="btn-primary"
        disabled={target === null}
        onClick={() => {
          onAction({ kind: actionKind, target, ...(extra ?? {}) });
          setTarget(null);
        }}
      >
        确定
      </button>
    </div>
  );

  const renderNight = () => {
    if (!isMyTurn) {
      return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
    }
    if (myRole === 'guard') {
      const cands = alive.filter((s) => s !== seat);
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">今晚守护谁</div>
          {renderTargetPicker(cands, 'night')}
        </div>
      );
    }
    if (myRole === 'werewolf') {
      const mates = (wolfSeats ?? []).filter((s) => s !== seat);
      const cands = alive.filter((s) => !(wolfSeats ?? []).includes(s));
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">狼队行动</div>
          {mates.length > 0 ? (
            <div className="werewolf-wolves">
              狼队友：{mates.map((s) => seatLabel(s, seat)).join('、')}
            </div>
          ) : (
            <div className="werewolf-wolves">只有你一只狼</div>
          )}
          {renderTargetPicker(cands, 'night')}
        </div>
      );
    }
    if (myRole === 'seer') {
      const cands = alive.filter((s) => s !== seat);
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">今晚查验谁</div>
          {seerHistory && seerHistory.length > 0 ? (
            <div className="werewolf-history">
              {seerHistory.map((h, i) => (
                <div key={i} className="werewolf-history-row">
                  第 {h.day} 天：{h.seat} 是 {h.result === 'wolf' ? '狼人' : '好人'}
                </div>
              ))}
            </div>
          ) : null}
          {renderTargetPicker(cands, 'night')}
        </div>
      );
    }
    if (myRole === 'witch') {
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">今晚死讯</div>
          {todayDeaths.length > 0 ? (
            <div className="werewolf-deaths">
              {todayDeaths.map((d) => (
                <div key={d.seat} className="werewolf-death-row">
                  <Skull size={14} strokeWidth={2} />
                  <span>{seatLabel(d.seat, seat)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="werewolf-deaths">今晚无人倒牌</div>
          )}
          <div className="werewolf-witch-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={todayDeaths.length === 0}
              onClick={() => onAction({ kind: 'night', potion: 'save', target: todayDeaths[0]?.seat ?? null })}
            >
              用解药
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => onAction({ kind: 'night', potion: 'poison', target })}
              disabled={target === null}
            >
              用毒药
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => onAction({ kind: 'night', potion: null, target: null })}
            >
              不用
            </button>
          </div>
          {renderTargetPicker(alive.filter((s) => s !== seat), 'night', { potion: 'poison' })}
        </div>
      );
    }
    return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
  };

  const renderDay = () => {
    if (phase === 'announce') {
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">第 {day} 天死讯</div>
          {todayDeaths.length > 0 ? (
            <div className="werewolf-deaths">
              {todayDeaths.map((d) => (
                <div key={d.seat} className="werewolf-death-row">
                  <Skull size={14} strokeWidth={2} />
                  <span>{seatLabel(d.seat, seat)}</span>
                  <span className="werewolf-death-reason">{DEATH_LABEL[d.reason]}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="werewolf-deaths">昨晚平安夜</div>
          )}
          <button type="button" className="btn-primary" onClick={() => onAction({ kind: 'announce_done' })}>
            <Check size={14} strokeWidth={2} />
            确认
          </button>
        </div>
      );
    }
    if (phase === 'lastwords') {
      const currentSpeaker = lastwordsQueue[lastwordsIdx];
      if (currentSpeaker === seat) {
        return (
          <div className="werewolf-block">
            <div className="werewolf-block-title">轮到你留遗言</div>
            <button type="button" className="btn-primary" onClick={() => onAction({ kind: 'lastwords_done' })}>
              <Check size={14} strokeWidth={2} />
              说完遗言
            </button>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSpeaker ?? currentSeat} 留遗言…</div>;
    }
    if (phase === 'sheriff') {
      if (isMyTurn) {
        return (
          <div className="werewolf-block">
            <div className="werewolf-block-title">竞选警长</div>
            <div className="werewolf-targets">
              <button type="button" className="btn-primary" onClick={() => onAction({ kind: 'sheriff', target: seat })}>
                上警
              </button>
              <button type="button" className="btn-ghost" onClick={() => onAction({ kind: 'sheriff', target: null })}>
                退水
              </button>
            </div>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSeat} 上警…</div>;
    }
    if (phase === 'speak' || phase === 'pk_speak') {
      if (isMyTurn) {
        return (
          <div className="werewolf-block">
            <div className="werewolf-block-title">轮到你发言</div>
            <button type="button" className="btn-primary" onClick={() => onAction({ kind: 'speak_done' })}>
              <Check size={14} strokeWidth={2} />
              发言完毕
            </button>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSeat} 发言…</div>;
    }
    if (phase === 'vote' || phase === 'pk_vote') {
      if (!isMyTurn) {
        return <div className="werewolf-wait">等 {currentSeat} 投票…</div>;
      }
      const onPk = phase === 'pk_vote';
      const cands = onPk ? pkSeats.filter((s) => s !== seat) : alive.filter((s) => s !== seat);
      return (
        <div className="werewolf-block">
          <div className="werewolf-block-title">{onPk ? 'PK 台上选一个' : '投票放逐'}</div>
          {onPk && pkSeats.includes(seat) ? (
            <div className="werewolf-wait">你在 PK 台上，不能投自己</div>
          ) : null}
          <div className="werewolf-targets">
            {cands.map((s) => (
              <button
                key={s}
                type="button"
                className={`werewolf-target${target === s ? ' is-picked' : ''}`}
                onClick={() => setTarget(s)}
              >
                <Vote size={14} strokeWidth={2} />
                {seatLabel(s, seat)}
              </button>
            ))}
            <button
              type="button"
              className="btn-ghost"
              onClick={() => onAction({ kind: 'vote', target: null })}
            >
              弃票
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={target === null}
              onClick={() => {
                onAction({ kind: 'vote', target });
                setTarget(null);
              }}
            >
              投他
            </button>
          </div>
        </div>
      );
    }
    return null;
  };

  const renderHunter = () => {
    if (hunterShootPending !== seat) return null;
    const cands = alive.filter((s) => s !== seat);
    return (
      <div className="werewolf-block">
        <div className="werewolf-block-title">猎人开枪</div>
        {renderTargetPicker(cands, 'hunter_shoot')}
      </div>
    );
  };

  return (
    <div className="werewolf-panel">
      <div className="werewolf-bar">
        <span className="werewolf-bar-day">第 {day} 天</span>
        <span className="werewolf-bar-phase">
          {isNight ? <Moon size={14} strokeWidth={2} /> : <Sun size={14} strokeWidth={2} />}
          {PHASE_LABEL[phase]}
        </span>
        <span className="werewolf-bar-turn">
          轮到：{seatLabel(currentSeat, seat)}
          {isMyTurn ? '' : ''}
        </span>
        {sheriffSeat ? <span className="werewolf-bar-sheriff">警长：{seatLabel(sheriffSeat, seat)}</span> : null}
        {myRole ? <span className="werewolf-bar-role">你是 {ROLE_LABEL[myRole]}</span> : null}
      </div>

      <div className="werewolf-seats">
        {players.map((p) => {
          const cls = ['werewolf-seat'];
          if (p.seat === currentSeat) cls.push('is-current');
          if (!p.alive) cls.push('is-dead');
          if (p.isSheriff) cls.push('is-sheriff');
          if (p.role && p.role === 'werewolf' && myRole === 'werewolf' && p.seat !== seat) cls.push('is-mate');
          return (
            <div key={p.seat} className={cls.join(' ')}>
              <span className="werewolf-seat-name">{seatLabel(p.seat, seat)}</span>
              {p.isSheriff ? <span className="werewolf-seat-badge">警长</span> : null}
              {p.role ? <span className="werewolf-seat-role">{ROLE_LABEL[p.role]}</span> : null}
              <span className="werewolf-seat-state">{p.alive ? '存活' : '出局'}</span>
            </div>
          );
        })}
      </div>

      {isNight ? renderNight() : renderDay()}
      {renderHunter()}
    </div>
  );
}
