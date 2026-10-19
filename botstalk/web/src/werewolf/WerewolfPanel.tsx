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

type NightStep = 'guard' | 'wolves' | 'seer' | 'witch';

type Role = '狼人' | '平民' | '预言家' | '女巫' | '猎人' | '守卫';

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

interface WerewolfSeerRecord {
  seat: string;
  result: string;
  day: number;
}

export interface WerewolfState {
  phase: Phase;
  day: number;
  players: WerewolfPlayer[];
  currentSeat: string;
  nightStep?: NightStep;
  deaths: WerewolfDeath[];
  lastwordsQueue: string[];
  lastwordsIdx: number;
  sheriffSeat?: string;
  votes: unknown;
  pkSeats: string[];
  sheriffVotes: unknown;
  hunterShootPending?: string;
  wolfSeats?: string[];
  seerHistory?: WerewolfSeerRecord[];
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
  if (!Array.isArray(v.lastwordsQueue)) return false;
  if (typeof v.lastwordsIdx !== 'number') return false;
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

const NIGHT_STEP_TEXT: Record<NightStep, string> = {
  guard: '守卫行动',
  wolves: '狼人行动',
  seer: '预言家查验',
  witch: '女巫行动',
};

const DEATH_REASON_TEXT: Record<WerewolfDeath['reason'], string> = {
  wolf: '被刀',
  poison: '被毒',
  vote: '放逐',
  shot: '被带走',
};

function roleText(role: string): string {
  return role;
}

function targetList(players: WerewolfPlayer[], exclude?: string): WerewolfPlayer[] {
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

  const { phase, day, players, currentSeat, nightStep, deaths, lastwordsQueue, lastwordsIdx } = state;

  const me = players.find((p) => p.seat === seat);
  const isMyTurn = currentSeat === seat;
  const isHunterPending = state.hunterShootPending === seat;

  const dayDeaths = deaths.filter((d) => d.day === day);
  const currentLastwordsSeat = lastwordsIdx >= 0 && lastwordsIdx < lastwordsQueue.length
    ? lastwordsQueue[lastwordsIdx]
    : null;

  const phaseLabel = PHASE_TEXT[phase];
  const turnLabel = nightStep ? NIGHT_STEP_TEXT[nightStep] : `${currentSeat} 行动`;

  const showNightTargets = phase === 'night' && isMyTurn && nightStep !== 'witch';
  const showWitchActions = phase === 'night' && isMyTurn && nightStep === 'witch';

  const handleNightPick = () => {
    onAction({ kind: 'night', target: picked });
  };

  const handleNightSkip = () => {
    onAction({ kind: 'night', target: null });
  };

  const handleWitchSave = () => {
    if (!picked) return;
    onAction({ kind: 'night', potion: 'save', target: picked });
  };

  const handleWitchPoison = () => {
    if (!picked) return;
    onAction({ kind: 'night', potion: 'poison', target: picked });
  };

  const handleWitchNone = () => {
    onAction({ kind: 'night' });
  };

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
    return (
      <div className="werewolf-role">
        <span className="werewolf-role-label">你的身份：</span>
        <span className="werewolf-role-value">{roleText(me.role)}</span>
        {me.role === '狼人' && state.wolfSeats && state.wolfSeats.length > 0 && (
          <span className="werewolf-role-extra">
            队友：{state.wolfSeats.filter((s) => s !== seat).join('、') || '无'}
          </span>
        )}
        {me.role === '预言家' && state.seerHistory && state.seerHistory.length > 0 && (
          <span className="werewolf-role-extra">
            查验：{state.seerHistory.map((h) => `${h.seat}${h.result === 'wolf' ? '狼人' : '好人'}`).join('、')}
          </span>
        )}
      </div>
    );
  };

  const renderTargetPicker = (onConfirm: () => void, confirmLabel: string, skipLabel?: string, onSkip?: () => void, requirePick?: boolean) => (
    <div className="werewolf-targets">
      <div className="werewolf-target-list">
        {targetList(players, phase === 'night' && nightStep === 'seer' ? seat : undefined).map((p) => {
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
      <div className="werewolf-actions">
        <button className="btn-primary" type="button" onClick={onConfirm} disabled={requirePick && !picked}>
          <Check size={14} />
          {confirmLabel}
        </button>
        {onSkip && (
          <button className="btn-ghost" type="button" onClick={onSkip}>
            <X size={14} />
            {skipLabel ?? '跳过'}
          </button>
        )}
      </div>
    </div>
  );

  const renderActions = () => {
    if (isHunterPending) {
      return (
        <div className="werewolf-targets">
          <div className="werewolf-target-list">
            {targetList(players, seat).map((p) => {
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
    }

    if (phase === 'night') {
      if (!isMyTurn) {
        return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
      }
      if (showNightTargets) {
        const isWolves = nightStep === 'wolves';
        const isGuard = nightStep === 'guard';
        const isSeer = nightStep === 'seer';
        const confirmLabel = isGuard ? '守护' : isWolves ? '刀' : isSeer ? '查验' : '确定';
        const skipLabel = isGuard ? '空守' : isWolves ? '空刀' : isSeer ? '跳过' : '跳过';
        return renderTargetPicker(handleNightPick, confirmLabel, skipLabel, handleNightSkip, isWolves);
      }
      if (showWitchActions) {
        return (
          <div className="werewolf-targets">
            <div className="werewolf-target-list">
              {targetList(players).map((p) => {
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
            <div className="werewolf-actions">
              <button className="btn-primary" type="button" onClick={handleWitchSave} disabled={!picked}>
                <Sun size={14} />
                用解药救
              </button>
              <button className="btn-primary" type="button" onClick={handleWitchPoison} disabled={!picked}>
                <Skull size={14} />
                用毒药
              </button>
              <button className="btn-ghost" type="button" onClick={handleWitchNone}>
                <X size={14} />
                不用药
              </button>
            </div>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSeat} 行动…</div>;
    }

    if (phase === 'announce') {
      return (
        <div className="werewolf-announce">
          {dayDeaths.length > 0 ? (
            <div className="werewolf-announce-list">
              {dayDeaths.map((d) => (
                <span key={d.seat} className="werewolf-announce-item">
                  {d.seat} {DEATH_REASON_TEXT[d.reason]}
                </span>
              ))}
            </div>
          ) : (
            <div className="werewolf-announce-none">昨晚平安无事</div>
          )}
          <div className="werewolf-actions">
            <button className="btn-primary" type="button" onClick={() => onAction({ kind: 'announce_done' })}>
              <Check size={14} />
              知道了
            </button>
          </div>
        </div>
      );
    }

    if (phase === 'lastwords') {
      if (currentLastwordsSeat === seat) {
        return (
          <div className="werewolf-actions">
            <button className="btn-primary" type="button" onClick={() => onAction({ kind: 'lastwords_done' })}>
              <Check size={14} />
              遗言说完
            </button>
          </div>
        );
      }
      if (currentLastwordsSeat) {
        return <div className="werewolf-wait">等 {currentLastwordsSeat} 说遗言…</div>;
      }
      return <div className="werewolf-wait">等待遗言流程…</div>;
    }

    if (phase === 'sheriff') {
      if (isMyTurn) {
        return (
          <div className="werewolf-targets">
            <div className="werewolf-target-list">
              {targetList(players).map((p) => {
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
            <div className="werewolf-actions">
              <button
                className="btn-primary"
                type="button"
                disabled={!picked}
                onClick={() => picked && onAction({ kind: 'sheriff', target: picked })}
              >
                <Vote size={14} />
                上警投票
              </button>
              <button className="btn-ghost" type="button" onClick={() => onAction({ kind: 'sheriff_pass' })}>
                <X size={14} />
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
          <div className="werewolf-actions">
            <button className="btn-primary" type="button" onClick={() => onAction({ kind: 'speak_done' })}>
              <Check size={14} />
              发言结束
            </button>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSeat} 发言…</div>;
    }

    if (phase === 'vote' || phase === 'pk_vote') {
      if (isMyTurn) {
        const pool = phase === 'pk_vote' && state.pkSeats.length > 0
          ? players.filter((p) => p.alive && state.pkSeats.includes(p.seat))
          : targetList(players, seat);
        return (
          <div className="werewolf-targets">
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
              <button className="btn-ghost" type="button" onClick={() => onAction({ kind: 'vote', target: null })}>
                <X size={14} />
                弃票
              </button>
            </div>
          </div>
        );
      }
      return <div className="werewolf-wait">等 {currentSeat} 投票…</div>;
    }

    return null;
  };

  const PhaseIcon = phase === 'night' ? Moon : Sun;

  return (
    <div className="werewolf-panel">
      <div className="werewolf-bar">
        <span className="werewolf-bar-phase">
          <PhaseIcon size={14} strokeWidth={2} />
          {phaseLabel}
        </span>
        <span className="werewolf-bar-day">第 {day} 天</span>
        <span className="werewolf-bar-turn">
          轮到：{turnLabel}
          {isMyTurn ? '（你）' : ''}
        </span>
      </div>

      {renderSeats()}
      {renderRole()}
      {renderActions()}
    </div>
  );
}
