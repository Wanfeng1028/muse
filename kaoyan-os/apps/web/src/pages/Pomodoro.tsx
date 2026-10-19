import { useCallback, useEffect, useRef, useState } from 'react';
import {
  SUBJECTS,
  DEFAULT_SETTINGS,
  type SubjectKey,
  type Settings,
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

  // 记录目标结束时间戳，用于防漂移
  const endAtRef = useRef<number | null>(null);
  // 保存定时器句柄
  const timerRef = useRef<number | null>(null);
  // 用 ref 保存最新状态，供 interval 回调读取，避免闭包过期
  const modeRef = useRef(mode);
  const subjectRef = useRef(subject);
  const settingsRef = useRef(settings);
  const runningRef = useRef(running);

  modeRef.current = mode;
  subjectRef.current = subject;
  settingsRef.current = settings;
  runningRef.current = running;

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

  // 刷新今日专注
  const refreshToday = useCallback(() => {
    api
      .focusStats(1)
      .then((stats) => setTodayMinutes(stats.todayMinutes))
      .catch(() => {
        // 忽略错误
      });
  }, []);

  useEffect(() => {
    refreshToday();
  }, [refreshToday]);

  // 专注自然结束的处理
  const finishFocus = useCallback(() => {
    const s = settingsRef.current;
    // 蜂鸣两声
    beep(2);
    // 落库
    api
      .createFocus({
        subject: subjectRef.current,
        minutes: s.pomodoroMinutes,
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

  return (
    <div className="page">
      <div className="page-header">
        <h1>番茄专注</h1>
      </div>

      <div className="timer-wrap pomo-timer-wrap">
        <div className="timer-mode pomo-mode">{mode === 'focus' ? '专注' : '休息'}</div>
        <div className="timer-display pomo-display">{fmt(remaining)}</div>

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

        <div className="form-row pomo-actions">
          <button className="btn btn-primary pomo-btn" onClick={toggleRunning}>
            {running ? '暂停' : '开始'}
          </button>
          <button className="btn btn-ghost pomo-btn" onClick={reset}>
            重置
          </button>
        </div>
      </div>

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
