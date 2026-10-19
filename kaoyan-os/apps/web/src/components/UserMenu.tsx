import { useState } from 'react';
import { api } from '../api';

type Props = {
  username: string;
};

export default function UserMenu({ username }: Props) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onLogout = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await api.logout();
      // 退出后跳登录页；用 location 而非 navigate，避免残留业务页 state
      window.location.href = '/login';
    } catch (e) {
      console.warn('[logout] 失败', e);
      setErr('退出失败，重试一下');
      setBusy(false);
    }
  };

  return (
    <div className="user-menu">
      <span className="user-menu-name" title={username}>
        {username}
      </span>
      <button
        type="button"
        className="user-menu-logout"
        onClick={onLogout}
        disabled={busy}
      >
        {busy ? '退出中…' : '退出登录'}
      </button>
      {err ? <span className="user-menu-err">{err}</span> : null}
    </div>
  );
}
