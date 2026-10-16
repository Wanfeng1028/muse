import { useState, FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';

interface Props {
  onJoin: (nick: string) => void;
}

export default function Join({ onJoin }: Props) {
  const [name, setName] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 2 || trimmed.length > 12) {
      setErr('昵称长度 2 到 12 个字');
      return;
    }
    setErr(null);
    onJoin(trimmed);
  };

  return (
    <div className="join">
      <div className="join-panel">
        <h1 className="join-title">起个名字，进群聊天</h1>
        <p className="join-hint">
          这个名字就是你在 lobby 里的身份，其他人看到的就是它。
        </p>
        <form onSubmit={submit} className="join-form" noValidate>
          <label className="join-label" htmlFor="nick">
            昵称
          </label>
          <div className="join-row">
            <input
              id="nick"
              className="join-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="2 到 12 个字"
              maxLength={12}
              autoFocus
            />
            <button className="btn-primary" type="submit">
              进入
              <ArrowRight size={16} strokeWidth={2} />
            </button>
          </div>
          {err && <div className="join-err">{err}</div>}
        </form>
      </div>
    </div>
  );
}
