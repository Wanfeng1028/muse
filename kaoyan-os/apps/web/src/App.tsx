import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { DEFAULT_SETTINGS, type Settings } from '@kaoyan/shared';
import { api } from './api';
import Dashboard from './pages/Dashboard';
import Plans from './pages/Plans';
import Pomodoro from './pages/Pomodoro';
import Mistakes from './pages/Mistakes';
import Words from './pages/Words';
import Exams from './pages/Exams';
import DataTransfer from './pages/DataTransfer';

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
  { to: '/exams', label: '真题统计', end: false },
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

export default function App() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);

  // 挂载时拉取设置，失败则用默认值兜底；两者都同步一次主题
  useEffect(() => {
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
  }, []);

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
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/plans" element={<Plans />} />
          <Route path="/pomodoro" element={<Pomodoro />} />
          <Route path="/mistakes" element={<Mistakes />} />
          <Route path="/words" element={<Words />} />
          <Route path="/exams" element={<Exams />} />
          <Route path="/data" element={<DataTransfer />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
