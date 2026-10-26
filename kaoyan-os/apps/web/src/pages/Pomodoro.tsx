import { useCallback, useEffect, useRef, useState } from 'react';
import {
  SUBJECTS,
  DEFAULT_SETTINGS,
  type SubjectKey,
  type Settings,
  type Plan,
  type FocusBySubjectResponse,
} from '@kaoyan/shared';
import { api } from '../api';

// 播放蜂鸣声，次数可指定（用 WebAudio 合成，无需音频文件）
function beep(times = 1) {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    const ctx = new AudioCtx();
    let delay = 0;
    for (let i = 0; i < times; i++) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = 880;
      gain.gain.value = 0.2;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime + delay);
      osc.stop(ctx.currentTime + delay + 0.2);
      delay += 0.35;
    }
    // 播放完毕后关闭上下文
    setTimeout(() => ctx.close().catch(() => {}), delay * 1000 + 200);
  } catch {
    // 忽略浏览器不支持音频的情况
  }
}

// 秒数格式化 mm:ss
function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function Pomodoro() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [mode, setMode] = useState<'focus' | 'break'>('focus');
  const [subject, setSubject] = useState<SubjectKey>('math');
  const [running, setRunning] = useState(false);
  const [remaining, setRemaining] = useState(DEFAULT_SETTINGS.pomodoroMinutes * 60);
  const [todayMinutes, setTodayMinutes] = useState(0);
  const [bySubject, setBySubject] = useState<FocusBySubjectResponse | null>(null);
  const [subjectWindow, setSubjectWindow] = useState<'all' | '7' | '1'>('all');
  const [todayPlans, setTodayPlans] = useState<Plan[]>([]);
  const [planId, setPlanId] = useState<number | ''>('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  // 记录目标结束时间戳，用于防漂移
  const endAtRef = useRef<number | null>(null);
  // 保存定时器句柄
  const timerRef = useRef<number | null>(null);
  // 用 ref 保存最新状态，供 interval 回调读取，避免闭包过期
  const modeRef = useRef(mode);
  const subjectRef = useRef(subject);
  const settingsRef = useRef(settings);
  const runningRef = useRef(running);
  const planIdRef = useRef<number | ''>(planId);

  modeRef.current = mode;
  subjectRef.current = subject;
  settingsRef.current = settings;
  runningRef.current = running;
  planIdRef.current = planId;

  // 拉取设置
  useEffect(() => {
    let alive = true;
    api
      .getSettings()
      .then((s) => {
        if (!alive) return;
        setSettings(s);
        setRemaining(s.pomodoroMinutes * 60);
      })
      .catch(() => {
        if (!alive) return;
        setSettings(DEFAULT_SETTINGS);
        setRemaining(DEFAULT_SETTINGS.pomodoroMinutes * 60);
      });
    return () => {
      alive = false;
    };
  }, []);

  // 刷新今日专注与分科累计
  const refreshToday = useCallback(() => {
    api
      .focusStats(1)
      .then((stats) => setTodayMinutes(stats.todayMinutes))
      .catch(() => {
        // 忽略错误
      });
    api
      .focusBySubject(subjectWindow === 'all' ? undefined : Number(subjectWindow))
      .then((data) => setBySubject(data))
      .catch(() => {
        // 忽略错误
      });
  }, [subjectWindow]);

  // 本地日期 -> YYYY-MM-DD
  const todayLocal = () => {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${day}`;
  };

  // 拉取今日计划（供"关联计划"下拉）
  const loadTodayPlans = useCallback(() => {
    api
      .listPlans({ date: todayLocal() })
      .then((list) => setTodayPlans(list))
      .catch(() => {
        // 忽略错误
      });
  }, []);

  useEffect(() => {
    refreshToday();
    loadTodayPlans();
  }, [refreshToday, loadTodayPlans]);

  // 专注自然结束的处理
  const finishFocus = useCallback(() => {
    const s = settingsRef.current;
    // 蜂鸣两声
    beep(2);
    // 落库
    const pid = planIdRef.current;
    api
      .createFocus({
        subject: subjectRef.current,
        minutes: s.pomodoroMinutes,
        ...(pid === '' ? {} : { planId: pid }),
      })
      .then(() => refreshToday())
      .catch(() => {
        // 落库失败也刷新一次，尽量保持显示一致
        refreshToday();
      });
    // 切到休息模式，停住待手动开始
    setMode('break');
    setRunning(false);
    endAtRef.current = null;
    setRemaining(s.breakMinutes * 60);
  }, [refreshToday]);

  // 休息结束的处理
  const finishBreak = useCallback(() => {
    beep(1);
    setRunning(false);
    endAtRef.current = null;
    setRemaining(settingsRef.current.pomodoroMinutes * 60);
    setMode('focus');
  }, []);

  // 定时器：250ms 轮询，用时间戳计算剩余
  useEffect(() => {
    if (!running) {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(() => {
      const endAt = endAtRef.current;
      if (endAt === null) return;
      const left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
      if (left <= 0) {
        if (modeRef.current === 'focus') {
          finishFocus();
        } else {
          finishBreak();
        }
      } else {
        setRemaining(left);
      }
    }, 250);
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [running, finishFocus, finishBreak]);

  // 卸载清理定时器
  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  // 开始 / 暂停
  const toggleRunning = () => {
    if (running) {
      // 暂停：保存剩余秒数
      const endAt = endAtRef.current;
      if (endAt !== null) {
        const left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
        setRemaining(left);
      }
      endAtRef.current = null;
      setRunning(false);
    } else {
      // 开始：记录结束时间戳
      endAtRef.current = Date.now() + remaining * 1000;
      setRunning(true);
    }
  };

  // 重置：回到当前模式对应的整段时长，停住
  const reset = () => {
    endAtRef.current = null;
    setRunning(false);
    const s = settingsRef.current;
    setRemaining(mode === 'focus' ? s.pomodoroMinutes * 60 : s.breakMinutes * 60);
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError('');
    try {
      const blob = await api.exportFocusCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'kaoyan-focus.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : '导出失败');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>番茄专注</h1>
        <button
          className="btn btn-ghost"
          type="button"
          onClick={handleExport}
          disabled={exporting}
        >
          {exporting ? '导出中…' : '导出 CSV'}
        </button>
      </div>
      {exportError && <p className="muted">导出失败：{exportError}</p>}

      <div className="timer-wrap pomo-timer-wrap">
        <div className="timer-mode pomo-mode">{mode === 'focus' ? '专注' : '休息'}</div>
        <div className="timer-display pomo-display">
          <span className="pomo-time-part">{fmt(remaining).slice(0, 2)}</span>
          <span className="pomo-time-colon" aria-hidden="true">:</span>
          <span className="pomo-time-part">{fmt(remaining).slice(3, 5)}</span>
        </div>
        {(() => {
          const total =
            (mode === 'focus' ? settings.pomodoroMinutes : settings.breakMinutes) * 60;
          const pct = total > 0 ? Math.min(100, Math.max(0, ((total - remaining) / total) * 100)) : 0;
          const color = SUBJECTS.find((x) => x.key === subject)?.color ?? '#4f7cff';
          return (
            <div
              className="pomo-progress"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pct)}
            >
              <span
                className="pomo-progress-fill"
                style={{ width: `${pct}%`, background: color }}
              />
            </div>
          );
        })()}

        <div className="form-row pomo-subject-row">
          <label className="pomo-subject-label">科目</label>
          <select
            className="select pomo-subject-select"
            value={subject}
            disabled={mode === 'break'}
            onChange={(e) => setSubject(e.target.value as SubjectKey)}
          >
            {SUBJECTS.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row pomo-plan-row">
          <label className="pomo-plan-label">关联计划</label>
          <select
            className="select pomo-plan-select"
            value={planId}
            disabled={running || mode === 'break'}
            onChange={(e) => setPlanId(Number(e.target.value) || '')}
          >
            <option value="">不关联</option>
            {todayPlans.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}（{o.plannedMinutes} 分钟）
              </option>
            ))}
          </select>
        </div>

        <div className="form-row pomo-actions">
          <button className="btn btn-primary pomo-btn" onClick={toggleRunning}>
            {running ? '暂停' : '开始'}
          </button>
          <button className="btn btn-ghost pomo-btn" onClick={reset}>
            重置
          </button>
        </div>
      </div>

      <div className="form-row pomo-window-row">
        <label className="pomo-subject-label">分科范围</label>
        <div className="pomo-window-btns">
          {(
            [
              ['all', '全部'],
              ['7', '近 7 天'],
              ['1', '今日'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`pomo-window-btn${subjectWindow === value ? ' active' : ''}`}
              onClick={() => setSubjectWindow(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {bySubject && bySubject.subjects.length > 0 && (
        <div className="card">
          <div className="stat-label">各科专注累计</div>
          <ul className="list">
            {(() => {
              const max = Math.max(1, ...bySubject.subjects.map((r) => r.totalMinutes));
              return bySubject.subjects.map((row) => {
                const s = SUBJECTS.find((x) => x.key === row.subject);
                const pct = Math.min(100, Math.max(0, (row.totalMinutes / max) * 100));
                return (
                  <li key={row.subject} className="list-item pomo-subject-bar-row">
                    <span className="pomo-subject-name">{s ? s.name : row.subject}</span>
                    <span className="pomo-subject-minutes">{row.totalMinutes} 分钟</span>
                    <span className="pomo-subject-bar">
                      <span
                        className="pomo-subject-fill"
                        style={{ width: `${pct}%`, background: s?.color ?? '#4f7cff' }}
                      />
                    </span>
                    <span className="pomo-subject-sessions">{row.sessions} 次</span>
                  </li>
                );
              });
            })()}
          </ul>
        </div>
      )}

      <div className="card pomo-stats-card">
        <div className="stat-card pomo-stat-card">
          <div className="stat-value">{todayMinutes}</div>
          <div className="stat-label">今日专注（分钟）</div>
        </div>
        <p className="stat-label pomo-stat-hint">
          专注 {settings.pomodoroMinutes} 分钟 / 休息 {settings.breakMinutes} 分钟
        </p>
      </div>
    </div>
  );
}
