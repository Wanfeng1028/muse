import { useState } from 'react';
import { Play, X } from 'lucide-react';
import './werewolf.css';

interface WerewolfLobbyProps {
  defaultSeat: string;
  err: string | null;
  onStart: (seats: string[]) => Promise<void>;
  onClose: () => void;
}

const SUPPORTED_COUNTS: number[] = [6, 7, 8, 9, 10, 11, 12];

const ROLE_CONFIG: Record<number, string> = {
  6: '2 狼人 · 3 平民 · 预言家',
  7: '2 狼人 · 3 平民 · 预言家 · 女巫',
  8: '2 狼人 · 4 平民 · 预言家 · 女巫',
  9: '3 狼人 · 3 平民 · 预言家 · 女巫 · 猎人',
  10: '3 狼人 · 3 平民 · 预言家 · 女巫 · 猎人 · 守卫',
  11: '3 狼人 · 4 平民 · 预言家 · 女巫 · 猎人 · 守卫',
  12: '4 狼人 · 4 平民 · 预言家 · 女巫 · 猎人 · 守卫',
};

function buildSeats(defaultSeat: string, count: number): string[] {
  const next: string[] = [];
  for (let i = 0; i < count; i += 1) {
    next.push(i === 0 ? defaultSeat : '');
  }
  return next;
}

export default function WerewolfLobby({ defaultSeat, err, onStart, onClose }: WerewolfLobbyProps) {
  const [count, setCount] = useState(9);
  const [seats, setSeats] = useState<string[]>(() => buildSeats(defaultSeat, 9));
  const [starting, setStarting] = useState(false);

  const changeCount = (next: number) => {
    if (!SUPPORTED_COUNTS.includes(next)) {
      return;
    }
    setCount(next);
    setSeats((prev) => {
      const out: string[] = [];
      for (let i = 0; i < next; i += 1) {
        out.push(prev[i] !== undefined ? prev[i] : '');
      }
      if (out[0] === '' && defaultSeat) {
        out[0] = defaultSeat;
      }
      return out;
    });
  };

  const setSeatAt = (index: number, value: string) => {
    setSeats((prev) => prev.map((s, i) => (i === index ? value : s)));
  };

  const nextAiName = (current: string[]): string => {
    let n = 1;
    while (current.includes(`ai:电脑${n}`)) {
      n += 1;
    }
    return `ai:电脑${n}`;
  };

  const fillAi = (index: number) => {
    setSeats((prev) => {
      const others = prev.filter((_, i) => i !== index);
      return prev.map((s, i) => (i === index ? nextAiName(others) : s));
    });
  };

  const fillAllAi = () => {
    setSeats((prev) => {
      const next = [...prev];
      for (let i = 0; i < next.length; i += 1) {
        if (next[i].trim() === '') {
          const others = next.filter((_, j) => j !== i);
          next[i] = nextAiName(others);
        }
      }
      return next;
    });
  };

  const trimmed = seats.map((s) => s.trim());
  const allFilled = trimmed.every((s) => s !== '');
  const unique = new Set(trimmed).size === trimmed.length;
  const countMatch = trimmed.length === count;
  const valid = allFilled && unique && countMatch;

  let reason = '';
  if (!countMatch) {
    reason = '人数和座位数量对不上';
  } else if (!allFilled) {
    reason = '还有座位没填';
  } else if (!unique) {
    reason = '座位不能重复';
  }

  const handleStart = async () => {
    if (!valid || starting) {
      return;
    }
    setStarting(true);
    try {
      await onStart(trimmed);
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="werewolf-lobby">
      <div className="werewolf-lobby-title">开一局狼人杀</div>
      <div className="werewolf-lobby-hint">6 到 12 人都能开，人不够就让 AI 凑</div>

      <div className="werewolf-lobby-count">
        <span className="werewolf-lobby-count-label">人数</span>
        <button
          className="btn-ghost"
          type="button"
          onClick={() => changeCount(count - 1)}
          disabled={!SUPPORTED_COUNTS.includes(count - 1)}
        >
          -
        </button>
        <span className="werewolf-lobby-count-value">{count}</span>
        <button
          className="btn-ghost"
          type="button"
          onClick={() => changeCount(count + 1)}
          disabled={!SUPPORTED_COUNTS.includes(count + 1)}
        >
          +
        </button>
      </div>

      <div className="werewolf-lobby-roles">
        <div className="werewolf-lobby-roles-title">角色构成</div>
        <div className="werewolf-lobby-roles-list">{ROLE_CONFIG[count]}</div>
      </div>

      <button className="btn-ghost" type="button" onClick={fillAllAi}>
        一键 AI 补满
      </button>

      {seats.map((s, i) => (
        <div className="werewolf-lobby-row" key={i}>
          <input
            className="werewolf-lobby-input"
            type="text"
            value={s}
            placeholder={`座位 ${i + 1}`}
            onChange={(e) => setSeatAt(i, e.target.value)}
          />
          <button className="btn-ghost" type="button" onClick={() => fillAi(i)}>
            AI补位
          </button>
        </div>
      ))}

      {reason ? <div className="werewolf-lobby-err">{reason}</div> : null}
      {err ? <div className="werewolf-lobby-err">{err}</div> : null}

      <div className="werewolf-lobby-actions">
        <button className="btn-primary" type="button" onClick={handleStart} disabled={!valid || starting}>
          <Play size={16} strokeWidth={2} />
          <span>{starting ? '开局中…' : '开局'}</span>
        </button>
        <button className="btn-ghost" type="button" onClick={onClose}>
          <X size={16} strokeWidth={2} />
          <span>取消</span>
        </button>
      </div>
    </div>
  );
}
