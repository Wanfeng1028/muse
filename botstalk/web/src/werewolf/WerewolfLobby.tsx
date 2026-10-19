import { useState } from 'react';
import { Play, X } from 'lucide-react';
import './werewolf.css';

interface WerewolfLobbyProps {
  defaultSeat: string;
  err: string | null;
  onStart: (seats: string[]) => Promise<void>;
  onClose: () => void;
}

const DEFAULT_COUNT = 9;
const MIN_COUNT = 6;
const MAX_COUNT = 12;

function buildSeats(count: number, defaultSeat: string): string[] {
  const seats: string[] = [];
  for (let i = 0; i < count; i += 1) {
    seats.push(i === 0 ? defaultSeat : '');
  }
  return seats;
}

export default function WerewolfLobby({ defaultSeat, err, onStart, onClose }: WerewolfLobbyProps) {
  const [count, setCount] = useState(DEFAULT_COUNT);
  const [seats, setSeats] = useState<string[]>(() => buildSeats(DEFAULT_COUNT, defaultSeat));
  const [starting, setStarting] = useState(false);

  const changeCount = (next: number) => {
    const clamped = Math.min(MAX_COUNT, Math.max(MIN_COUNT, next));
    setCount(clamped);
    setSeats((prev) => {
      const out: string[] = [];
      for (let i = 0; i < clamped; i += 1) {
        out.push(i < prev.length ? prev[i] : i === 0 ? defaultSeat : '');
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
    reason = '座位数和人数对不上';
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
      <div className="werewolf-lobby-hint">6 到 12 人都能开，人不够就让 AI 凑。</div>

      <div className="werewolf-lobby-countrow">
        <span className="werewolf-lobby-countlabel">人数</span>
        <button className="btn-ghost" type="button" onClick={() => changeCount(count - 1)} disabled={count <= MIN_COUNT}>
          -
        </button>
        <span className="werewolf-lobby-countvalue">{count}</span>
        <button className="btn-ghost" type="button" onClick={() => changeCount(count + 1)} disabled={count >= MAX_COUNT}>
          +
        </button>
        <button className="btn-ghost" type="button" onClick={fillAllAi}>
          一键 AI 补满
        </button>
      </div>

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
