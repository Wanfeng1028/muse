import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { DEFAULT_SETTINGS, type Settings } from '@kaoyan/shared';
import { api } from './api';
import UserMenu from './components/UserMenu';
import Dashboard from './pages/Dashboard';
import Plans from './pages/Plans';
import Pomodoro from './pages/Pomodoro';
import Mistakes from './pages/Mistakes';
import Words from './pages/Words';
import Vocab from './pages/Vocab';
import Exams from './pages/Exams';
import DataTransfer from './pages/DataTransfer';
import Weekly from './pages/Weekly';
import Heatmap from './pages/Heatmap';
import Login from './pages/Login';


type Theme = 'light' | 'dark';

// 将主题写入 <html data-theme>，CSS 侧据此切换 token
function applyTheme(theme: Theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

// 导航项定义
const NAV_ITEMS = [
  { to: '/', label: '仪表盘', end: true },
  { to: '/plans', label: '复习计划', end: false },
  { to: '/pomodoro', label: '番茄专注', end: false },
  { to: '/mistakes', label: '错题本', end: false },
  { to: '/words', label: '单词 SRS', end: false },
  { to: '/vocab', label: '词库浏览', end: false },
  { to: '/exams', label: '真题统计', end: false },
  { to: '/weekly', label: '周报', end: false },
  { to: '/heatmap', label: '自律热力图', end: false },

  { to: '/data', label: '数据导入导出', end: false },
];

// 计算距考试日期剩余天数（按自然日）
function daysUntil(examDate: string): number {
  const target = new Date(examDate + 'T00:00:00');
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = target.getTime() - today.getTime();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

// 底部导航前 5 个主 tab
const MOBILE_TABS = [
  { to: '/', label: '仪表盘', end: true },
  { to: '/plans', label: '复习计划', end: false },
  { to: '/mistakes', label: '错题本', end: false },
  { to: '/words', label: '单词', end: false },
  { to: '/exams', label: '真题', end: false },
];

// 更多动作表条目：除番茄专注走路由外，其余为回调
type MoreAction = {
  key: string;
  label: string;
  to?: string;
  onSelect?: () => void;
};

// 移动端底部导航 + 更多动作表
function MobileNav({
  username,
  theme,
  remainDays,
  examDate,
  onToggleTheme,
}: {
  username: string;
  theme: Theme;
  remainDays: number;
  examDate: string;
  onToggleTheme: () => void;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const onLogout = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await api.logout();
      window.location.href = '/login';
    } catch (e) {
      console.warn('[logout] 失败', e);
      setBusy(false);
    }
  };

  const closeSheet = () => setSheetOpen(false);

  const actions: MoreAction[] = [
    { key: 'pomodoro', label: '番茄专注', to: '/pomodoro' },
    { key: 'vocab', label: '词库浏览', to: '/vocab' },
    { key: 'weekly', label: '周报', to: '/weekly' },
    { key: 'heatmap', label: '自律热力图', to: '/heatmap' },
    { key: 'data', label: '数据导入导出', to: '/data' },
    {
      key: 'theme',
      label: theme === 'dark' ? '切换浅色模式' : '切换深色模式',
      onSelect: () => {
        onToggleTheme();
        closeSheet();
      },
    },
    {
      key: 'logout',
      label: busy ? '退出中…' : '退出登录',
      onSelect: () => {
        void onLogout();
      },
    },
  ];

  return (
    <>
      <nav className="mobile-nav" aria-label="底部导航">
        {MOBILE_TABS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              isActive ? 'mobile-nav-tab active' : 'mobile-nav-tab'
            }
          >
            {item.label}
          </NavLink>
        ))}
        <button
          type="button"
          className={sheetOpen ? 'mobile-nav-tab active' : 'mobile-nav-tab'}
          onClick={() => setSheetOpen((v) => !v)}
          aria-expanded={sheetOpen}
        >
          更多
        </button>
      </nav>

      {sheetOpen ? (
        <div className="mobile-sheet-mask" onClick={closeSheet}>
          <div
            className="mobile-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="更多功能"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-sheet-header">
              <span className="mobile-sheet-user">{username}</span>
              <span className="mobile-sheet-countdown">
                距考试还有 {remainDays} 天（{examDate}）
              </span>
            </div>
            <div className="mobile-sheet-list">
              {actions.map((a) =>
                a.to ? (
                  <NavLink
                    key={a.key}
                    to={a.to}
                    className="mobile-sheet-item"
                    onClick={closeSheet}
                  >
                    {a.label}
                  </NavLink>
                ) : (
                  <button
                    key={a.key}
                    type="button"
                    className="mobile-sheet-item"
                    onClick={a.onSelect}
                    disabled={a.key === 'logout' && busy}
                  >
                    {a.label}
                  </button>
                ),
              )}
            </div>
            <button
              type="button"
              className="mobile-sheet-cancel"
              onClick={closeSheet}
            >
              取消
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}

type AuthState =
  | { status: 'loading' }
  | { status: 'authed'; username: string }
  | { status: 'anon' };

export default function App() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [auth, setAuth] = useState<AuthState>({ status: 'loading' });

  // 先确认登录状态，再拉设置；未登录不发业务请求
  useEffect(() => {
    let alive = true;
    api
      .me()
      .then((me) => {
        if (!alive) return;
        setAuth({ status: 'authed', username: me.username });
      })
      .catch(() => {
        if (!alive) return;
        setAuth({ status: 'anon' });
      });
    return () => {
      alive = false;
    };
  }, []);

  // 登录后再拉设置，失败则用默认值兜底；两者都同步一次主题
  useEffect(() => {
    if (auth.status !== 'authed') return;
    let alive = true;
    api
      .getSettings()
      .then((s) => {
        if (!alive) return;
        setSettings(s);
        applyTheme(s.theme);
      })
      .catch(() => {
        if (!alive) return;
        setSettings(DEFAULT_SETTINGS);
        applyTheme(DEFAULT_SETTINGS.theme);
      });
    return () => {
      alive = false;
    };
  }, [auth.status]);

  // 切换主题：先落库，成功后再更新本地状态与 DOM；失败保持原主题
  const toggleTheme = async () => {
    const next: Theme = settings.theme === 'dark' ? 'light' : 'dark';
    try {
      const updated = await api.updateSettings({ theme: next });
      setSettings(updated);
      applyTheme(updated.theme);
    } catch (err) {
      console.warn('[theme] 切换失败，保持原主题', err);
    }
  };

  const remainDays = daysUntil(settings.examDate);

  // 登录态未确认时占位，避免闪一下未登录页
  if (auth.status === 'loading') {
    return (
      <div className="auth-loading" role="status" aria-live="polite">
        加载中…
      </div>
    );
  }

  // 未登录：只渲染登录页，不挂侧栏
  if (auth.status === 'anon') {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="brand">
          <div>考研指挥舱</div>
          <div className="brand-sub">Kaoyan OS</div>
        </div>

        <nav className="nav-list">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="countdown-big">{remainDays}</div>
          <div>距考试还有 {remainDays} 天</div>
          <div className="brand-sub">考试日期 {settings.examDate}</div>
          <button
            type="button"
            className="theme-toggle"
            onClick={toggleTheme}
            aria-label="切换主题"
          >
            {settings.theme === 'dark' ? '浅色模式' : '深色模式'}
          </button>
          <UserMenu username={auth.username} />
        </div>
      </aside>

      <MobileNav
        username={auth.username}
        theme={settings.theme}
        remainDays={remainDays}
        examDate={settings.examDate}
        onToggleTheme={toggleTheme}
      />

      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/plans" element={<Plans />} />
          <Route path="/pomodoro" element={<Pomodoro />} />
          <Route path="/mistakes" element={<Mistakes />} />
          <Route path="/words" element={<Words />} />
          <Route path="/vocab" element={<Vocab />} />
          <Route path="/exams" element={<Exams />} />
          <Route path="/weekly" element={<Weekly />} />
          <Route path="/heatmap" element={<Heatmap />} />

          <Route path="/data" element={<DataTransfer />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
