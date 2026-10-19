import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

type Tab = 'login' | 'register';

// 用户名规则：与后端校验保持一致
// 与后端保持一致：小写字母开头，3~32 位
const USERNAME_RE = /^[a-z][a-z0-9_]{2,31}$/;

export default function Login() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [password2, setPassword2] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const switchTab = (next: Tab) => {
    if (busy) return;
    setTab(next);
    setError('');
    setPassword('');
    setPassword2('');
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;

    const name = username.trim();
    if (!USERNAME_RE.test(name)) {
      setError('用户名要 3 到 32 位，小写字母开头，只能用小写字母、数字和下划线。');
      return;
    }
    if (password.length < 8) {
      setError('密码至少 8 位。');
      return;
    }
    if (tab === 'register' && password !== password2) {
      setError('两次输入的密码不一样。');
      return;
    }

    setError('');
    setBusy(true);
    try {
      if (tab === 'login') {
        await api.login(name, password);
      } else {
        // 注册接口只建账号不下发会话，注册完紧接着登录一次
        await api.register(name, password);
        await api.login(name, password);
      }
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : '请求失败，稍后再试。');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-head">
          <div className="login-brand">考研指挥舱</div>
          <div className="login-sub">登录后才能用你的计划、错题和词库</div>
        </div>

        <div className="login-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'login'}
            className={tab === 'login' ? 'login-tab active' : 'login-tab'}
            onClick={() => switchTab('login')}
          >
            登录
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'register'}
            className={tab === 'register' ? 'login-tab active' : 'login-tab'}
            onClick={() => switchTab('register')}
          >
            注册
          </button>
        </div>

        <form className="login-form" onSubmit={onSubmit}>
          <label className="login-field">
            <span className="login-label">用户名</span>
            <input
              className="login-input"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="小写字母开头，3-32 位"
              autoComplete="username"
              autoFocus
            />
          </label>

          <label className="login-field">
            <span className="login-label">密码</span>
            <input
              className="login-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="至少 8 位"
              autoComplete={tab === 'login' ? 'current-password' : 'new-password'}
            />
          </label>

          {tab === 'register' && (
            <label className="login-field">
              <span className="login-label">再输一次密码</span>
              <input
                className="login-input"
                type="password"
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
                placeholder="和上面保持一致"
                autoComplete="new-password"
              />
            </label>
          )}

          {error && <div className="login-error">{error}</div>}

          <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
            {busy ? '处理中…' : tab === 'login' ? '登录' : '注册并登录'}
          </button>
        </form>

        <div className="login-hint">
          用户名小写字母开头，3-32 位，可用小写字母、数字、下划线；密码至少 8 位。
        </div>
      </div>
    </div>
  );
}
