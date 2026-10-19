import { useEffect, useState } from 'react';
import { Check, Moon, Skull, Sun, Vote, X } from 'lucide-react';
import './werewolf.css';

type Phase =
  | 'night'
  | 'announce'
  | 'lastwords'
  | 'sheriff'
  | 'speak'
  | 'vote'
  | 'pk_speak'
  | 'pk_vote'
  | 'finished';

type DeathReason = 'wolf' | 'witch' | 'vote' | 'hunter';

interface WerewolfPlayer {
  seat: string;
  alive: boolean;
  isSheriff: boolean;
  role?: string;
}

interface WerewolfDeath {
  seat: string;
  reason: DeathReason;
}

interface SeerRecord {
  day: number;
  target: string;
  result: 'wolf' | 'good';
}

export interface WerewolfState {
  phase: Phase;
  day: number;
  players: WerewolfPlayer[];
  currentSeat: string;
  deaths: WerewolfDeath[];
  lastwordsQueue: string[];
  sheriffSeat: string | null;
  votes: Array<{ seat: string; target: string | null }>;
  sheriffVotes: Array<{ seat: string; target: string | null }>;
  pkSeats: string[];
  pkVotes: Array<{ seat: string; target: string | null }>;
  wolfSeats?: string[];
  seerHistory?: SeerRecord[];
  seerResult?: 'wolf' | 'good' | null;
  wolfTarget?: string | null;
  winner?: 'wolves' | 'good';
}

export function isWerewolfState(value: unknown): value is WerewolfState {
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
  if (!Array.isArray(v.players)) return false;
  for (const p of v.players) {
    if (typeof p !== 'object' || p === null) return false;
    const pp = p as Record<string, unknown>;
    if (typeof pp.seat !== 'string') return false;
    if (typeof pp.alive !== 'boolean') return false;
    if (typeof pp.isSheriff !== 'boolean') return false;
  }
  if (typeof v.currentSeat !== 'string') return false;
  if (!Array.isArray(v.deaths)) return false;
  for (const d of v.deaths) {
    const dd = d as Record<string, unknown>;
    if (typeof dd.seat !== 'string') return false;
    if (dd.reason !== 'wolf' && dd.reason !== 'witch' && dd.reason !== 'vote' && dd.reason !== 'hunter') {
      return false;
    }
  }
  if (!Array.isArray(v.lastwordsQueue)) return false;
  if (!Array.isArray(v.pkSeats)) return false;
  return true;
}

interface Props {
  state: unknown;
  seat: string;
  onAction: (action: unknown) => void;
}

const PHASE_TEXT: Record<Phase, string> = {
  night: '天黑请闭眼',
  announce: '公布死讯',
  lastwords: '遗言',
  sheriff: '竞选警长',
  speak: '发言',
  vote: '投票',
  pk_speak: 'PK发言',
  pk_vote: 'PK投票',
  finished: '已结束',
};

const DEATH_REASON_TEXT: Record<DeathReason, string> = {
  wolf: '被刀',
  witch: '被毒',
  vote: '放逐',
  hunter: '被带走',
};

const ROLE_TEXT: Record<string, string> = {
  werewolf: '狼人',
  villager: '平民',
  seer: '预言家',
  witch: '女巫',
  hunter: '猎人',
  guard: '守卫',
};

function roleText(role: string): string {
  return ROLE_TEXT[role] ?? role;
}

function alivePlayers(players: WerewolfPlayer[]): WerewolfPlayer[] {
  return players.filter((p) => p.alive);
}

function alivePlayersExcept(players: WerewolfPlayer[], exclude: string): WerewolfPlayer[] {
  return players.filter((p) => p.alive && p.seat !== exclude);
}

export default function WerewolfPanel({ state, seat, onAction }: Props) {
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    setPicked(null);
  }, [state]);

  if (!isWerewolfState(state)) {
    return <div className="werewolf-empty">局面同步中…</div>;
  }

  if (state.phase === 'finished') return null;

  const { phase, day, players, currentSeat, deaths, lastwordsQueue } = state;

  const me = players.find((p) => p.seat === seat);
  const isMyTurn = currentSeat === seat;


  const phaseLabel = PHASE_TEXT[phase];
  const PhaseIcon = phase === 'night' ? Moon : Sun;

  const hunterShootPendingSeat = (state as unknown as { hunterShootPending?: string }).hunterShootPending;
  const isHunterPending = hunterShootPendingSeat === seat;

  const sheriffCandidates = (() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const sv of state.sheriffVotes) {
      if (sv.target && !seen.has(sv.target)) {
        seen.add(sv.target);
        out.push(sv.target);
      }
    }
    return out;
  })();

  const renderSeats = () => (
    <div className="werewolf-seats">
      {players.map((p) => {
        const cls = ['werewolf-seat'];
        if (p.seat === currentSeat) cls.push('is-current');
        if (!p.alive) cls.push('is-dead');
        if (p.isSheriff) cls.push('is-sheriff');
        const death = deaths.find((d) => d.seat === p.seat);
        return (
          <div key={p.seat} className={cls.join(' ')}>
            <span className="werewolf-seat-name">
              {p.seat}
              {p.seat === seat ? '（你）' : ''}
            </span>
            {p.isSheriff && <span className="werewolf-seat-badge">警长</span>}
            {!p.alive && death && (
              <span className="werewolf-seat-death">{DEATH_REASON_TEXT[death.reason]}</span>
            )}
          </div>
        );
      })}
    </div>
  );

  const renderRole = () => {
    if (!me || !me.role) return null;
    const isWolf = me.role === 'werewolf';
    const isSeer = me.role === 'seer';
    return (
      <div className="werewolf-role">
        <span className="werewolf-role-label">你的身份：</span>
        <span className="werewolf-role-value">{roleText(me.role)}</span>
        {isWolf && state.wolfSeats && state.wolfSeats.length > 0 && (
          <span className="werewolf-role-extra">
            队友：{state.wolfSeats.filter((s) => s !== seat).join('、') || '无'}
          </span>
        )}
        {isSeer && state.seerHistory && state.seerHistory.length > 0 && (
          <span className="werewolf-role-extra">
            查验：
            {state.seerHistory
              .map((h) => `第${h.day}天 ${h.target} 是${h.result === 'wolf' ? '狼人' : '好人'}`)
              .join('、')}
          </span>
        )}
      </div>
    );
  };

  const renderTargetButtons = (pool: WerewolfPlayer[]) => (
    <div className="werewolf-target-list">
      {pool.map((p) => {
        const cls = ['werewolf-target'];
        if (picked === p.seat) cls.push('is-picked');
        return (
          <button
            key={p.seat}
            className={cls.join(' ')}
            type="button"
            onClick={() => setPicked(p.seat)}
          >
            {p.seat}
          </button>
        );
      })}
    </div>
  );

  const renderHunterShoot = () => (
    <div className="werewolf-targets">
      {renderTargetButtons(alivePlayersExcept(players, seat))}
      <div className="werewolf-actions">
        <button
          className="btn-primary"
          type="button"
          disabled={!picked}
          onClick={() => picked && onAction({ kind: 'hunter_shoot', target: picked })}
        >
          <Skull size={14} />
          开枪
        </button>
      </div>
    </div>
  );

  const renderNight = () => {
    if (!isMyTurn || !me || !me.role) {
      return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
    }
    const role = me.role;

    if (role === 'guard') {
      return (
        <div className="werewolf-targets">
          {renderTargetButtons(alivePlayers(players))}
          <div className="werewolf-actions">
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'night', target: picked })}
            >
              <Check size={14} />
              守护
            </button>
            <button
              className="btn-ghost"
              type="button"
              onClick={() => onAction({ kind: 'night', target: null })}
            >
              <X size={14} />
              空守
            </button>
          </div>
        </div>
      );
    }

    if (role === 'werewolf') {
      return (
        <div className="werewolf-targets">
          {renderTargetButtons(alivePlayersExcept(players, seat))}
          <div className="werewolf-actions">
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'night', target: picked })}
            >
              <Skull size={14} />
              刀
            </button>
            <button
              className="btn-ghost"
              type="button"
              onClick={() => onAction({ kind: 'night', target: null })}
            >
              <X size={14} />
              空刀
            </button>
          </div>
        </div>
      );
    }

    if (role === 'seer') {
      return (
        <div className="werewolf-targets">
          {renderTargetButtons(alivePlayersExcept(players, seat))}
          <div className="werewolf-actions">
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'night', target: picked })}
            >
              <Check size={14} />
              查验
            </button>
          </div>
        </div>
      );
    }

    if (role === 'witch') {
      const wolfTarget = state.wolfTarget ?? null;
      return (
        <div className="werewolf-targets">
          <div className="werewolf-wait">
            {wolfTarget ? `昨晚被刀：${wolfTarget}` : '昨晚平安'}
          </div>
          {renderTargetButtons(alivePlayers(players))}
          <div className="werewolf-actions">
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'night', potion: 'save', target: picked })}
            >
              <Sun size={14} />
              用解药救
            </button>
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'night', potion: 'poison', target: picked })}
            >
              <Skull size={14} />
              用毒药
            </button>
            <button
              className="btn-ghost"
              type="button"
              onClick={() => onAction({ kind: 'night' })}
            >
              <X size={14} />
              不用药
            </button>
          </div>
        </div>
      );
    }

    return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
  };

  const renderAnnounce = () => {
    const list = lastwordsQueue;
    return (
      <div className="werewolf-announce">
        {list.length > 0 ? (
          <div className="werewolf-announce-list">
            <span>昨晚出局：</span>
            {list.map((s) => {
              const d = deaths.find((x) => x.seat === s);
              const reason = d ? DEATH_REASON_TEXT[d.reason] : '';
              return (
                <span key={s} className="werewolf-announce-item">
                  {s}
                  {reason ? ` ${reason}` : ''}
                </span>
              );
            })}
          </div>
        ) : (
          <div className="werewolf-announce-none">昨晚平安无事</div>
        )}
        <div className="werewolf-actions">
          <button
            className="btn-primary"
            type="button"
            onClick={() => onAction({ kind: 'announce_done' })}
          >
            <Check size={14} />
            知道了
          </button>
        </div>
      </div>
    );
  };

  const renderLastwords = () => {
    if (currentSeat === seat) {
      return (
        <div className="werewolf-actions">
          <button
            className="btn-primary"
            type="button"
            onClick={() => onAction({ kind: 'lastwords_done' })}
          >
            <Check size={14} />
            遗言说完
          </button>
        </div>
      );
    }
    if (currentSeat) {
      return <div className="werewolf-wait">等 {currentSeat} 说遗言…</div>;
    }
    return <div className="werewolf-wait">等待遗言流程…</div>;
  };

  const renderSheriff = () => {
    const candidates = sheriffCandidates;
    const candidatePlayers = players.filter((p) => candidates.includes(p.seat));
    return (
      <div className="werewolf-targets">
        {candidatePlayers.length > 0 && renderTargetButtons(candidatePlayers)}
        <div className="werewolf-actions">
          <button
            className="btn-primary"
            type="button"
            onClick={() => onAction({ kind: 'sheriff' })}
          >
            <Vote size={14} />
            上警
          </button>
          <button
            className="btn-ghost"
            type="button"
            onClick={() => onAction({ kind: 'sheriff_pass' })}
          >
            <X size={14} />
            退水
          </button>
          {candidatePlayers.length > 0 && (
            <button
              className="btn-primary"
              type="button"
              disabled={!picked}
              onClick={() => picked && onAction({ kind: 'sheriff', target: picked })}
            >
              <Vote size={14} />
              投票
            </button>
          )}
          <button
            className="btn-ghost"
            type="button"
            onClick={() => onAction({ kind: 'sheriff_done' })}
          >
            <Check size={14} />
            结束上警投票
          </button>
        </div>
      </div>
    );
  };

  const renderSpeak = () => {
    if (isMyTurn) {
      return (
        <div className="werewolf-actions">
          <button
            className="btn-primary"
            type="button"
            onClick={() => onAction({ kind: 'speak_done' })}
          >
            <Check size={14} />
            发言结束
          </button>
        </div>
      );
    }
    return <div className="werewolf-wait">等 {currentSeat} 发言…</div>;
  };

  const renderVote = (isPk: boolean) => {
    if (!isMyTurn) {
      return <div className="werewolf-wait">等 {currentSeat} 投票…</div>;
    }
    const pool = isPk && state.pkSeats.length > 0
      ? players.filter((p) => state.pkSeats.includes(p.seat) && p.seat !== seat)
      : alivePlayersExcept(players, seat);
    return (
      <div className="werewolf-targets">
        {renderTargetButtons(pool)}
        <div className="werewolf-actions">
          <button
            className="btn-primary"
            type="button"
            disabled={!picked}
            onClick={() => picked && onAction({ kind: 'vote', target: picked })}
          >
            <Vote size={14} />
            投票
          </button>
          <button
            className="btn-ghost"
            type="button"
            onClick={() => onAction({ kind: 'vote', target: null })}
          >
            <X size={14} />
            弃票
          </button>
        </div>
      </div>
    );
  };

  const renderActions = () => {
    if (isHunterPending) return renderHunterShoot();

    switch (phase) {
      case 'night':
        return renderNight();
      case 'announce':
        return renderAnnounce();
      case 'lastwords':
        return renderLastwords();
      case 'sheriff':
        return renderSheriff();
      case 'speak':
      case 'pk_speak':
        return renderSpeak();
      case 'vote':
        return renderVote(false);
      case 'pk_vote':
        return renderVote(true);
      default:
        return null;
    }
  };

  return (
    <div className="werewolf-panel">
      <div className="werewolf-bar">
        <span className="werewolf-bar-phase">
          <PhaseIcon size={14} strokeWidth={2} />
          {phaseLabel}
        </span>
        <span className="werewolf-bar-day">第 {day} 天</span>
        <span className="werewolf-bar-turn">
          轮到：{currentSeat}
          {isMyTurn ? '（你）' : ''}
        </span>
      </div>

      {renderSeats()}
      {renderRole()}
      {renderActions()}
    </div>
  );
}
