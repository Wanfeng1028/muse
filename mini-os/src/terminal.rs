use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TermError {
    NotFound,
    Forbidden,
    LimitReached,
    Io,
}

struct TermSession {
    id: String,
    user_id: i64,
    pty: Mutex<Box<dyn MasterPty + Send>>,
    writer: Mutex<Box<dyn Write + Send>>,
    reader: Mutex<Box<dyn Read + Send>>,
    child: Mutex<Box<dyn Child + Send + Sync>>,
    last_active: Mutex<Instant>,
}

pub struct TerminalManager {
    sessions: Mutex<HashMap<String, Arc<TermSession>>>,
    data_dir: String,
    max_per_user: usize,
    idle_timeout: Duration,
}

impl TerminalManager {
    pub fn new(data_dir: String, max_per_user: usize, idle_timeout_secs: u64) -> Self {
        TerminalManager {
            sessions: Mutex::new(HashMap::new()),
            data_dir,
            max_per_user,
            idle_timeout: Duration::from_secs(idle_timeout_secs),
        }
    }

    pub fn open(&self, user_id: i64, cols: u16, rows: u16) -> Result<String, TermError> {
        let cols = cols.clamp(2, 500);
        let rows = rows.clamp(2, 500);

        // 先做容量检查；持有 sessions 锁期间不进行任何可能阻塞的 PTY 操作，
        // 避免 openpty/spawn 的耗时把其他用户的 open 全部卡住。
        {
            let map = self.sessions.lock().map_err(|_| TermError::Io)?;
            let count = map.values().filter(|s| s.user_id == user_id).count();
            if count >= self.max_per_user {
                return Err(TermError::LimitReached);
            }
        }

        if !Path::new(&self.data_dir).exists() {
            std::fs::create_dir_all(&self.data_dir).map_err(|_| TermError::Io)?;
        }

        let pty_system = native_pty_system();
        let pair = pty_system
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|_| TermError::Io)?;

        // /bin/bash 存在时优先使用，带 --noprofile --norc 避免加载用户 dotfile
        // 影响服务器端 PTY 行为；否则退化为 /bin/sh。
        let mut cmd = if Path::new("/bin/bash").exists() {
            let mut c = CommandBuilder::new("/bin/bash");
            c.arg("--noprofile");
            c.arg("--norc");
            c
        } else {
            CommandBuilder::new("/bin/sh")
        };
        cmd.cwd(&self.data_dir);
        cmd.env("TERM", "xterm-256color");
        cmd.env("MINIOS_TERM", "1");

        let child = pair.slave.spawn_command(cmd).map_err(|_| TermError::Io)?;
        // slave 必须显式丢弃，否则子进程退出后 master 端读不到 EOF。
        drop(pair.slave);

        let reader = pair.master.try_clone_reader().map_err(|_| TermError::Io)?;
        let writer = pair.master.take_writer().map_err(|_| TermError::Io)?;

        let id = hex::encode(rand::random::<[u8; 16]>());
        let session = Arc::new(TermSession {
            id: id.clone(),
            user_id,
            pty: Mutex::new(pair.master),
            writer: Mutex::new(writer),
            reader: Mutex::new(reader),
            child: Mutex::new(child),
            last_active: Mutex::new(Instant::now()),
        });

        {
            let mut map = self.sessions.lock().map_err(|_| TermError::Io)?;
            // 并发 open 可能在我们构建 PTY 期间把配额占满，需要再检查一次；
            // 若超限则直接丢弃刚构建的会话，并杀掉子进程。
            let count = map.values().filter(|s| s.user_id == user_id).count();
            if count >= self.max_per_user {
                if let Ok(mut c) = session.child.lock() {
                    let _ = c.kill();
                }
                return Err(TermError::LimitReached);
            }
            map.insert(id.clone(), session);
        }

        Ok(id)
    }

    pub fn write(&self, user_id: i64, session_id: &str, data: &[u8]) -> Result<(), TermError> {
        if data.is_empty() {
            // 空写直接成功；但仍需校验会话归属，避免泄露他人 session 存在性。
            let _ = self.get_session(user_id, session_id)?;
            return Ok(());
        }
        let session = self.get_session(user_id, session_id)?;
        {
            let mut w = session.writer.lock().map_err(|_| TermError::Io)?;
            w.write_all(data).map_err(|_| TermError::Io)?;
            w.flush().map_err(|_| TermError::Io)?;
        }
        self.touch(&session);
        Ok(())
    }

    pub fn resize(
        &self,
        user_id: i64,
        session_id: &str,
        cols: u16,
        rows: u16,
    ) -> Result<(), TermError> {
        let cols = cols.clamp(2, 500);
        let rows = rows.clamp(2, 500);
        let session = self.get_session(user_id, session_id)?;
        session
            .pty
            .lock()
            .map_err(|_| TermError::Io)?
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|_| TermError::Io)?;
        self.touch(&session);
        Ok(())
    }

    pub fn interrupt(&self, user_id: i64, session_id: &str) -> Result<(), TermError> {
        let session = self.get_session(user_id, session_id)?;
        {
            let mut w = session.writer.lock().map_err(|_| TermError::Io)?;
            // 真 PTY 语义：写入 0x03，由 line discipline 的 ISIG 转换为
            // 前台进程组的 SIGINT。绝不能直接 kill 子进程。
            w.write_all(&[0x03u8]).map_err(|_| TermError::Io)?;
            w.flush().map_err(|_| TermError::Io)?;
        }
        self.touch(&session);
        Ok(())
    }

    pub fn read_chunk(
        &self,
        user_id: i64,
        session_id: &str,
        buf: &mut [u8],
    ) -> Result<usize, TermError> {
        if buf.is_empty() {
            let _ = self.get_session(user_id, session_id)?;
            return Ok(0);
        }
        let session = self.get_session(user_id, session_id)?;
        // 只锁该会话的 reader；这是阻塞读，调用方负责放到 spawn_blocking 里。
        // 锁住单个会话的 reader 不会阻塞其它会话或 sessions 表。
        let mut r = session.reader.lock().map_err(|_| TermError::Io)?;
        let n = r.read(buf).map_err(|_| TermError::Io)?;
        drop(r);
        self.touch(&session);
        Ok(n)
    }

    pub fn is_alive(&self, user_id: i64, session_id: &str) -> Result<bool, TermError> {
        let session = self.get_session(user_id, session_id)?;
        let mut child = session.child.lock().map_err(|_| TermError::Io)?;
        match child.try_wait() {
            Ok(None) => Ok(true),
            Ok(Some(_)) => Ok(false),
            Err(_) => Err(TermError::Io),
        }
    }

    pub fn close(&self, user_id: i64, session_id: &str) -> Result<(), TermError> {
        // 先查表并校验归属，再移除；不存在直接 NotFound。
        let session = self.get_session(user_id, session_id)?;
        if let Ok(mut child) = session.child.lock() {
            // kill 失败忽略：可能子进程已退出。
            let _ = child.kill();
        }
        let mut map = self.sessions.lock().map_err(|_| TermError::Io)?;
        // 二次校验：极少数情况下并发 close 已删除，视为幂等之外的竞态，仍按 NotFound 返回。
        match map.remove(session_id) {
            Some(_) => Ok(()),
            None => Err(TermError::NotFound),
        }
    }

    pub fn session_count(&self, user_id: i64) -> usize {
        match self.sessions.lock() {
            Ok(map) => map.values().filter(|s| s.user_id == user_id).count(),
            Err(_) => 0,
        }
    }

    pub fn reap_idle(&self) -> usize {
        let now = Instant::now();
        let timeout = self.idle_timeout;

        // 第一阶段：只读扫描，收集候选 id。不在持锁期间做 kill/阻塞操作。
        let candidates: Vec<String> = {
            let map = match self.sessions.lock() {
                Ok(m) => m,
                Err(_) => return 0,
            };
            map.values()
                .filter(|s| {
                    let idle = match s.last_active.lock() {
                        Ok(t) => now.duration_since(*t) >= timeout,
                        // 锁中毒时保守判定为超时以便回收。
                        Err(_) => true,
                    };
                    if idle {
                        return true;
                    }
                    // 子进程已退出也视为可回收，避免僵尸会话占配额。
                    match s.child.lock() {
                        Ok(mut c) => matches!(c.try_wait(), Ok(Some(_))),
                        Err(_) => true,
                    }
                })
                .map(|s| s.id.clone())
                .collect()
        };

        let mut reaped = 0;
        for id in candidates {
            // 逐个处理：先取出 Arc（从表移除），再 kill，避免长时间持锁。
            let session = {
                let mut map = match self.sessions.lock() {
                    Ok(m) => m,
                    Err(_) => break,
                };
                map.remove(&id)
            };
            if let Some(s) = session {
                if let Ok(mut child) = s.child.lock() {
                    let _ = child.kill();
                }
                reaped += 1;
            }
        }
        reaped
    }

    /// 启动空闲会话回收器。有 Tokio runtime 时用 tokio::spawn；
    /// 无 runtime（如普通 #[test] 线程）时退化为独立 OS 线程
    /// 自带 current-thread runtime，绝不 panic。
    pub fn spawn_reaper(self: &Arc<Self>) {
        let me = Arc::clone(self);
        if tokio::runtime::Handle::try_current().is_ok() {
            tokio::spawn(async move {
                Self::reaper_loop(me).await;
            });
        } else {
            std::thread::Builder::new()
                .name("terminal-reaper".to_string())
                .spawn(move || {
                    let rt = tokio::runtime::Builder::new_current_thread()
                        .enable_time()
                        .build()
                        .expect("reaper runtime");
                    rt.block_on(Self::reaper_loop(me));
                })
                .expect("spawn reaper thread");
        }
    }

    async fn reaper_loop(me: Arc<Self>) {
        let mut ticker = tokio::time::interval(Duration::from_secs(60));
        // 第一次 tick 会立即触发，跳过以免刚启动就回收。
        ticker.tick().await;
        loop {
            ticker.tick().await;
            let _ = me.reap_idle();
        }
    }

    /// 测试/运维用途：直接设置某会话的最后活跃时间（集成测试无法启用 cfg(test)，
    /// 因此不加 cfg 门，由调用方保证只在测试中使用）。
    pub fn set_last_active_for_test(&self, session_id: &str, t: Instant) {
        let session = match self.sessions.lock() {
            Ok(map) => map.get(session_id).cloned(),
            Err(_) => None,
        };
        if let Some(s) = session {
            if let Ok(mut guard) = s.last_active.lock() {
                *guard = t;
            }
        }
    }

    /// 按 session_id 查表并校验归属；跨用户访问一律返回 Forbidden（安全红线）。
    /// 返回 Arc 以便后续在锁外操作会话内部字段。
    fn get_session(&self, user_id: i64, session_id: &str) -> Result<Arc<TermSession>, TermError> {
        let map = self.sessions.lock().map_err(|_| TermError::Io)?;
        let session = map.get(session_id).ok_or(TermError::NotFound)?;
        if session.user_id != user_id {
            return Err(TermError::Forbidden);
        }
        Ok(Arc::clone(session))
    }

    fn touch(&self, session: &TermSession) {
        if let Ok(mut t) = session.last_active.lock() {
            *t = Instant::now();
        }
    }
}
