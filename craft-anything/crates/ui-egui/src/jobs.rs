//! Background work. Everything slow (engine tools, AI detection, file dialogs, file writes) runs on
//! a worker thread; the UI polls finished results once per frame and never waits.

use craft_anything_engine::{CancelToken, Progress};
use craft_anything_platform::sync::Mutex;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::sync::{Arc, PoisonError};
use std::time::Instant;

/// What a worker hands back. `T` is the app's result type.
pub struct Finished<T> {
    pub job: u64,
    pub result: Result<T, String>,
}

/// One job, as the Jobs panel shows it.
pub struct JobInfo {
    pub id: u64,
    pub title: String,
    pub started: Instant,
    pub cancel: CancelToken,
    pub progress: Arc<Mutex<Option<Progress>>>,
    /// `None` while running; `Some(Ok|Err)` once done (kept briefly for the panel).
    pub outcome: Option<Result<(), String>>,
    pub finished_at: Option<Instant>,
    /// Shown in the Jobs panel only (quick housekeeping jobs are hidden).
    pub visible: bool,
}

impl JobInfo {
    pub fn progress(&self) -> Option<Progress> {
        self.progress.lock().unwrap_or_else(PoisonError::into_inner).clone()
    }
}

/// Hands passed to a job body.
pub struct JobCtx {
    pub cancel: CancelToken,
    progress: Arc<Mutex<Option<Progress>>>,
    repaint: Option<egui::Context>,
}

impl JobCtx {
    /// An owned progress callback (for `CallOptions::with_progress`).
    pub fn reporter(&self) -> impl Fn(Progress) + Send + Sync + 'static {
        let progress = self.progress.clone();
        let repaint = self.repaint.clone();
        move |p| {
            *progress.lock().unwrap_or_else(PoisonError::into_inner) = Some(p);
            if let Some(c) = &repaint {
                c.request_repaint();
            }
        }
    }

    /// Report progress; the UI repaints to show it.
    pub fn report(&self, p: Progress) {
        *self.progress.lock().unwrap_or_else(PoisonError::into_inner) = Some(p);
        if let Some(c) = &self.repaint {
            c.request_repaint();
        }
    }
}

pub struct Jobs<T: Send + 'static> {
    tx: Sender<Finished<T>>,
    rx: Receiver<Finished<T>>,
    next: u64,
    pub list: Vec<JobInfo>,
    repaint: Option<egui::Context>,
}

impl<T: Send + 'static> Default for Jobs<T> {
    fn default() -> Self {
        let (tx, rx) = channel();
        Jobs { tx, rx, next: 1, list: Vec::new(), repaint: None }
    }
}

impl<T: Send + 'static> Jobs<T> {
    pub fn set_repaint(&mut self, ctx: &egui::Context) {
        self.repaint = Some(ctx.clone());
    }

    /// The window to repaint when work done elsewhere has news (`None` before the first frame).
    pub fn repaint_ctx(&self) -> Option<&egui::Context> {
        self.repaint.as_ref()
    }

    /// Run `f` on a new thread. A panic inside it becomes an error result, never a crash.
    pub fn spawn(&mut self, title: impl Into<String>, visible: bool, f: impl FnOnce(&JobCtx) -> Result<T, String> + Send + 'static) -> u64 {
        let id = self.next;
        self.next = self.next.saturating_add(1);
        let cancel = CancelToken::default();
        let progress = Arc::new(Mutex::new(None));
        let title = title.into();
        self.list.push(JobInfo {
            id,
            title: title.clone(),
            started: Instant::now(),
            cancel: cancel.clone(),
            progress: progress.clone(),
            outcome: None,
            finished_at: None,
            visible,
        });
        let tx = self.tx.clone();
        let repaint = self.repaint.clone();
        let jctx = JobCtx { cancel, progress, repaint: repaint.clone() };
        let spawned = std::thread::Builder::new().name(format!("job-{id}")).spawn(move || {
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| f(&jctx))).unwrap_or_else(|p| {
                let what = p.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.downcast_ref::<String>().cloned()).unwrap_or_default();
                log::error!("job {title} panicked: {what}");
                Err(format!("{title} hit a bug and stopped safely. ({what})"))
            });
            let _ = tx.send(Finished { job: id, result });
            if let Some(c) = repaint {
                c.request_repaint();
            }
        });
        if let Err(e) = spawned {
            let _ = self.tx.send(Finished { job: id, result: Err(format!("Couldn't start a worker thread: {e}")) });
        }
        id
    }

    /// Drain finished jobs (non-blocking).
    pub fn poll(&mut self) -> Vec<Finished<T>> {
        let mut out = Vec::new();
        while let Ok(f) = self.rx.try_recv() {
            if let Some(j) = self.list.iter_mut().find(|j| j.id == f.job) {
                j.outcome = Some(f.result.as_ref().map(|_| ()).map_err(Clone::clone));
                j.finished_at = Some(Instant::now());
            }
            out.push(f);
        }
        // Keep the last few finished jobs for the panel; drop older ones.
        let finished = self.list.iter().filter(|j| j.outcome.is_some()).count();
        if finished > 30 {
            let mut drop = finished - 30;
            self.list.retain(|j| {
                if drop > 0 && j.outcome.is_some() {
                    drop -= 1;
                    false
                } else {
                    true
                }
            });
        }
        out
    }

    pub fn running(&self) -> impl Iterator<Item = &JobInfo> {
        self.list.iter().filter(|j| j.outcome.is_none())
    }

    pub fn busy(&self) -> bool {
        self.list.iter().any(|j| j.outcome.is_none() && j.visible)
    }

    pub fn cancel(&self, id: u64) {
        if let Some(j) = self.list.iter().find(|j| j.id == id) {
            j.cancel.cancel();
        }
    }

    pub fn clear_finished(&mut self) {
        self.list.retain(|j| j.outcome.is_none());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn wait<T: Send>(jobs: &mut Jobs<T>) -> Vec<Finished<T>> {
        for _ in 0..500 {
            let got = jobs.poll();
            if !got.is_empty() {
                return got;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        Vec::new()
    }

    #[test]
    fn results_come_back_and_panics_become_errors() {
        let mut jobs: Jobs<u32> = Jobs::default();
        jobs.spawn("ok", true, |_| Ok(7));
        let got = wait(&mut jobs);
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].result, Ok(7));
        jobs.spawn("boom", true, |_| -> Result<u32, String> { panic!("kaboom") });
        let got = wait(&mut jobs);
        assert!(got[0].result.as_ref().unwrap_err().contains("kaboom"));
        assert!(!jobs.busy());
    }

    #[test]
    fn cancel_reaches_the_job() {
        let mut jobs: Jobs<bool> = Jobs::default();
        let id = jobs.spawn("wait", true, |c| {
            for _ in 0..1000 {
                if c.cancel.is_cancelled() {
                    return Ok(true);
                }
                std::thread::sleep(Duration::from_millis(2));
            }
            Ok(false)
        });
        assert!(jobs.busy());
        jobs.cancel(id);
        let got = wait(&mut jobs);
        assert_eq!(got[0].result, Ok(true));
    }
}
