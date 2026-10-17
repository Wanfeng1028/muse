import { useState } from 'react';
import { Play, X } from 'lucide-react';
import './doudizhu.css';

interface DoudizhuLobbyProps {
  defaultSeat: string;
  err: string | null;
  onStart: (seats: string[]) => Promise<void>;
  onClose: () => void;
}

export default function DoudizhuLobby({ defaultSeat, err, onStart, onClose }: DoudizhuLobbyProps) {
  const [seats, setSeats] = useState<string[]>([defaultSeat, '', '']);
  const [starting, setStarting] = useState(false);

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
  const valid = allFilled && unique;

  let reason = '';
  if (!allFilled) {
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
    <div className="doudizhu-lobby">
      <div className="doudizhu-lobby-title">开一局斗地主</div>
      <div className="doudizhu-lobby-hint">三个人玩，人不够就让 AI 凑。</div>

      <button className="btn-ghost" type="button" onClick={fillAllAi}>
        一键 AI 补满
      </button>

      {seats.map((s, i) => (
        <div className="doudizhu-lobby-row" key={i}>
          <input
            className="doudizhu-lobby-input"
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

      {reason ? <div className="doudizhu-lobby-err">{reason}</div> : null}
      {err ? <div className="doudizhu-lobby-err">{err}</div> : null}

      <div className="doudizhu-lobby-actions">
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