//! Locks that can't hang the app. Use [`Mutex`] here instead of `std::sync::Mutex` (clippy refuses
//! the standard one): it has the same API, and it knows who holds what.
//!
//! - **A real deadlock is broken at once.** A thread that waits on a lock it holds itself, or on a
//!   cycle of threads waiting on each other, can never get it. The waiter that finds this stops
//!   waiting and unwinds (a caught, reported error, never a crash): its locks are released, so
//!   everyone else carries on. Every thread's work runs inside a `catch_unwind` that turns this
//!   into an error the person sees.
//! - **Long work is left alone.** A holder labelled as a job ([`MutexGuard::label`], such as a tool,
//!   which has its own deadlines and Stop) may take hours. Waiting for it is reported, never cut off.
//! - **A holder that isn't a job and never lets go** is reported after [`Limits::stuck_after`], and
//!   anyone still waiting gives up after [`Limits::give_up_after`] rather than wait forever.
//! - **[`start_watchdog`] looks every few seconds** and writes what it finds to a log.
//!   [`problems`] is what the app shows.

#![allow(clippy::disallowed_types)]

use std::fmt;
use std::ops::{Deref, DerefMut};
use std::panic::Location;
use std::sync::{LockResult, PoisonError, TryLockError, TryLockResult};
use std::time::Duration;

/// When waiting on a lock stops being normal.
#[derive(Debug, Clone, Copy)]
pub struct Limits {
    /// How long a holder that isn't a labelled job may keep others waiting before it's reported.
    pub stuck_after: Duration,
    /// How long anyone waits on such a holder before giving up.
    pub give_up_after: Duration,
    /// How long waiting on a labelled job goes on before it's worth saying (it isn't cut off).
    pub slow_job_after: Duration,
}

impl Default for Limits {
    fn default() -> Self {
        Limits { stuck_after: Duration::from_secs(120), give_up_after: Duration::from_secs(900), slow_job_after: Duration::from_secs(1800) }
    }
}

/// How serious a [`Problem`] is.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProblemKind {
    /// A deadlock that was broken: the thread that found it stopped, and the rest carried on.
    Broken,
    /// A deadlock that couldn't be broken from here: restarting the app clears it.
    Deadlock,
    /// Something holds a lock far longer than it should, and others are waiting.
    Stuck,
    /// Work waits on a long job. Normal for big jobs; it's said so nobody wonders.
    SlowJob,
}

/// Something the watchdog or a waiting thread found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Problem {
    pub kind: ProblemKind,
    pub summary: String,
    pub log: Option<std::path::PathBuf>,
}

/// Why [`Mutex::lock_unless`] came back without the lock.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GaveUp {
    Stopped,
    /// The holder looks stuck; says who holds it.
    Stuck(String),
}

/// A mutual-exclusion lock whose waits are watched (see the module docs).
pub struct Mutex<T: ?Sized> {
    inner: std::sync::Mutex<T>,
}

/// Holds a [`Mutex`] until dropped.
pub struct MutexGuard<'a, T: ?Sized + 'a> {
    inner: std::sync::MutexGuard<'a, T>,
    id: usize,
}

impl<T> Mutex<T> {
    pub const fn new(value: T) -> Self {
        Mutex { inner: std::sync::Mutex::new(value) }
    }

    pub fn into_inner(self) -> LockResult<T> {
        self.inner.into_inner()
    }
}

impl<T: ?Sized> Mutex<T> {
    fn id(&self) -> usize {
        (&raw const self.inner).cast::<()>() as usize
    }

    fn wrap<'a>(id: usize, g: std::sync::MutexGuard<'a, T>, at: &'static Location<'static>) -> MutexGuard<'a, T> {
        tracker::held(id, at);
        MutexGuard { inner: g, id }
    }

    /// Take the lock, waiting while it's busy. Comes back with the lock unless waiting could never
    /// end: then this thread's work unwinds, releasing what it holds, and its `catch_unwind`
    /// reports the error.
    #[track_caller]
    pub fn lock(&self) -> LockResult<MutexGuard<'_, T>> {
        let at = Location::caller();
        match self.wait(at, &|| false, Limits::default(), false) {
            Ok(r) => r,
            Err(GaveUp::Stuck(why)) => tracker::unwind(why),
            // `stopped` above never says stop.
            Err(GaveUp::Stopped) => tracker::unwind(format!("A wait at {at} stopped for no reason.")),
        }
    }

    /// [`Mutex::lock`] for work that can report an error: gives up when `stop` says so, or as soon
    /// as the holder looks stuck, instead of waiting on. A deadlock still unwinds.
    #[track_caller]
    pub fn lock_unless(&self, stop: &dyn Fn() -> bool) -> Result<LockResult<MutexGuard<'_, T>>, GaveUp> {
        self.wait(Location::caller(), stop, Limits::default(), true)
    }

    fn wait(&self, at: &'static Location<'static>, stop: &dyn Fn() -> bool, limits: Limits, early: bool) -> Result<LockResult<MutexGuard<'_, T>>, GaveUp> {
        let id = self.id();
        let mut pause = Duration::from_millis(1);
        let mut waiting = false;
        loop {
            match self.inner.try_lock() {
                Ok(g) => {
                    if waiting {
                        tracker::end_wait();
                    }
                    return Ok(Ok(Self::wrap(id, g, at)));
                }
                Err(TryLockError::Poisoned(p)) => {
                    if waiting {
                        tracker::end_wait();
                    }
                    return Ok(Err(PoisonError::new(Self::wrap(id, p.into_inner(), at))));
                }
                Err(TryLockError::WouldBlock) => {}
            }
            if !waiting {
                tracker::begin_wait(id, at);
                waiting = true;
            }
            // Under one lock, so two threads in a cycle can't both decide to break it.
            if let Some(why) = tracker::must_give_up(id, limits, early) {
                match why {
                    tracker::Verdict::Deadlock(text) => tracker::unwind(text),
                    tracker::Verdict::Stuck(text) => {
                        tracker::end_wait();
                        return Err(GaveUp::Stuck(text));
                    }
                }
            }
            if stop() {
                tracker::end_wait();
                return Err(GaveUp::Stopped);
            }
            tracker::pause(pause);
            pause = (pause * 2).min(Duration::from_millis(20));
        }
    }

    #[track_caller]
    pub fn try_lock(&self) -> TryLockResult<MutexGuard<'_, T>> {
        let at = Location::caller();
        let id = self.id();
        match self.inner.try_lock() {
            Ok(g) => Ok(Self::wrap(id, g, at)),
            Err(TryLockError::Poisoned(p)) => Err(TryLockError::Poisoned(PoisonError::new(Self::wrap(id, p.into_inner(), at)))),
            Err(TryLockError::WouldBlock) => Err(TryLockError::WouldBlock),
        }
    }

    pub fn get_mut(&mut self) -> LockResult<&mut T> {
        self.inner.get_mut()
    }
}

impl<T: Default> Default for Mutex<T> {
    fn default() -> Self {
        Mutex::new(T::default())
    }
}

impl<T> From<T> for Mutex<T> {
    fn from(value: T) -> Self {
        Mutex::new(value)
    }
}

impl<T: ?Sized> fmt::Debug for Mutex<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("Mutex")
    }
}

impl<T: ?Sized> MutexGuard<'_, T> {
    /// Say this hold is a job that may take a long time, by name. It's then never treated as stuck.
    pub fn label(&self, job: &'static str) {
        tracker::label(self.id, job);
    }
}

impl<T: ?Sized> Deref for MutexGuard<'_, T> {
    type Target = T;
    fn deref(&self) -> &T {
        &self.inner
    }
}

impl<T: ?Sized> DerefMut for MutexGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut T {
        &mut self.inner
    }
}

impl<T: ?Sized + fmt::Debug> fmt::Debug for MutexGuard<'_, T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        (**self).fmt(f)
    }
}

impl<T: ?Sized + fmt::Display> fmt::Display for MutexGuard<'_, T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        (**self).fmt(f)
    }
}

impl<T: ?Sized> Drop for MutexGuard<'_, T> {
    fn drop(&mut self) {
        tracker::released(self.id);
    }
}

/// What's wrong right now and what went wrong recently, for the app to show.
pub fn problems() -> Vec<Problem> {
    tracker::problems()
}

/// Add a problem found some other way, so it's logged and shown like the rest.
pub fn report(kind: ProblemKind, summary: impl Into<String>) {
    tracker::report(kind, summary.into());
}

/// Forget a problem the person has dismissed.
pub fn dismiss(summary: &str) {
    tracker::dismiss(summary);
}

/// Check every few seconds for locks in trouble, writing each new problem to a log in `log_dir`.
/// Starts once per process; apps call it, tests don't.
pub fn start_watchdog(log_dir: std::path::PathBuf) {
    tracker::start_watchdog(log_dir);
}

#[cfg(target_arch = "wasm32")]
mod tracker {
    //! One thread and no clock: nothing to watch, and nothing that could wait.
    use super::*;
    pub enum Verdict {
        Deadlock(String),
        Stuck(String),
    }
    pub fn held(_: usize, _: &'static Location<'static>) {}
    pub fn released(_: usize) {}
    pub fn label(_: usize, _: &'static str) {}
    pub fn begin_wait(_: usize, _: &'static Location<'static>) {}
    pub fn end_wait() {}
    pub fn pause(_: Duration) {}
    pub fn must_give_up(id: usize, _: Limits, _: bool) -> Option<Verdict> {
        Some(Verdict::Deadlock(format!("Lock {id} is busy on the only thread.")))
    }
    pub fn unwind(text: String) -> ! {
        std::panic::resume_unwind(Box::new(text))
    }
    pub fn problems() -> Vec<Problem> {
        Vec::new()
    }
    pub fn dismiss(_: &str) {}
    pub fn report(_: ProblemKind, _: String) {}
    pub fn start_watchdog(_: std::path::PathBuf) {}
}

#[cfg(not(target_arch = "wasm32"))]
mod tracker {
    use super::*;
    use std::collections::HashMap;
    use std::sync::OnceLock;
    use std::thread::ThreadId;
    use std::time::Instant;

    /// How often the watchdog looks.
    const WATCH_EVERY: Duration = Duration::from_secs(5);
    /// Problems remembered for the app.
    const KEEP_PROBLEMS: usize = 8;

    pub enum Verdict {
        Deadlock(String),
        Stuck(String),
    }

    struct Hold {
        thread: ThreadId,
        thread_name: String,
        at: &'static Location<'static>,
        since: Instant,
        job: Option<&'static str>,
    }

    struct Wait {
        lock: usize,
        thread_name: String,
        at: &'static Location<'static>,
        since: Instant,
    }

    #[derive(Default)]
    struct Registry {
        holds: HashMap<usize, Hold>,
        waits: HashMap<ThreadId, Wait>,
        problems: Vec<Problem>,
        dismissed: Vec<String>,
    }

    /// Held only for short bookkeeping, never while taking another lock, so it can't deadlock.
    fn registry() -> std::sync::MutexGuard<'static, Registry> {
        static REGISTRY: OnceLock<std::sync::Mutex<Registry>> = OnceLock::new();
        REGISTRY.get_or_init(Default::default).lock().unwrap_or_else(PoisonError::into_inner)
    }

    fn thread_name() -> String {
        std::thread::current().name().unwrap_or("unnamed").to_string()
    }

    pub fn held(id: usize, at: &'static Location<'static>) {
        let hold = Hold { thread: std::thread::current().id(), thread_name: thread_name(), at, since: Instant::now(), job: None };
        registry().holds.insert(id, hold);
    }

    pub fn released(id: usize) {
        registry().holds.remove(&id);
    }

    pub fn label(id: usize, job: &'static str) {
        if let Some(h) = registry().holds.get_mut(&id) {
            h.job = Some(job);
        }
    }

    pub fn begin_wait(lock: usize, at: &'static Location<'static>) {
        let me = std::thread::current().id();
        registry().waits.insert(me, Wait { lock, thread_name: thread_name(), at, since: Instant::now() });
    }

    pub fn end_wait() {
        let me = std::thread::current().id();
        registry().waits.remove(&me);
    }

    pub fn pause(d: Duration) {
        std::thread::sleep(d);
    }

    /// The chain of threads waiting on each other that leads from `start` back to it, if there is one.
    fn cycle(r: &Registry, start: ThreadId) -> Option<String> {
        let mut parts = Vec::new();
        let mut thread = start;
        // A chain can't be longer than the number of waiting threads.
        for _ in 0..=r.waits.len() {
            let wait = r.waits.get(&thread)?;
            let hold = r.holds.get(&wait.lock)?;
            parts.push(format!("thread '{}' at {} waits on a lock taken at {} by thread '{}'", wait.thread_name, wait.at, hold.at, hold.thread_name));
            if hold.thread == start {
                return Some(parts.join("; "));
            }
            thread = hold.thread;
        }
        None
    }

    fn remember(r: &mut Registry, kind: ProblemKind, summary: String) {
        if r.dismissed.contains(&summary) || r.problems.iter().any(|p| p.summary == summary) {
            return;
        }
        log::error!("{summary}");
        r.problems.push(Problem { kind, summary, log: None });
        if r.problems.len() > KEEP_PROBLEMS {
            r.problems.remove(0);
        }
    }

    /// Should the waiting thread stop? Removes its wait when it should, in the same step as the
    /// decision, so the next thread in a cycle no longer sees one and carries on.
    pub fn must_give_up(lock: usize, limits: Limits, early: bool) -> Option<Verdict> {
        let me = std::thread::current().id();
        let mut r = registry();
        if let Some(chain) = cycle(&r, me) {
            // Unwinding during an unwind would abort the process; left waiting, it's reported
            // by the watchdog as a deadlock to restart from.
            if std::thread::panicking() {
                return None;
            }
            r.waits.remove(&me);
            let text = format!("A deadlock was found and broken: {chain}.");
            remember(&mut r, ProblemKind::Broken, text.clone());
            return Some(Verdict::Deadlock(text));
        }
        let waited = r.waits.get(&me)?.since.elapsed();
        let hold = r.holds.get(&lock)?;
        if hold.job.is_some() {
            return None;
        }
        let limit = if early { limits.stuck_after } else { limits.give_up_after };
        if waited < limit || hold.since.elapsed() < limit {
            return None;
        }
        let text = format!(
            "A lock taken at {} by thread '{}' hasn't been released for {} s, so a wait was given up.",
            hold.at,
            hold.thread_name,
            hold.since.elapsed().as_secs()
        );
        if std::thread::panicking() {
            return None;
        }
        r.waits.remove(&me);
        remember(&mut r, ProblemKind::Stuck, text.clone());
        Some(if early { Verdict::Stuck(text) } else { Verdict::Deadlock(text) })
    }

    pub fn unwind(text: String) -> ! {
        end_wait();
        // Not `panic!`: this is a caught, expected way out, and the panic hook isn't what reports it.
        std::panic::resume_unwind(Box::new(text))
    }

    pub fn problems() -> Vec<Problem> {
        registry().problems.clone()
    }

    pub fn report(kind: ProblemKind, summary: String) {
        remember(&mut registry(), kind, summary);
    }

    pub fn dismiss(summary: &str) {
        let mut r = registry();
        r.problems.retain(|p| p.summary != summary);
        r.dismissed.push(summary.to_string());
    }

    /// What's wrong right now, whole-app: the watchdog's look at everything.
    pub(super) fn scan(limits: Limits) {
        let mut r = registry();
        let mut found = Vec::new();
        for (thread, wait) in &r.waits {
            if let Some(chain) = cycle(&r, *thread) {
                found.push((ProblemKind::Deadlock, format!("A deadlock can't be broken from here, so restart the app: {chain}.")));
                continue;
            }
            let Some(hold) = r.holds.get(&wait.lock) else { continue };
            let waited = wait.since.elapsed();
            let (kind, limit, what) = match hold.job {
                Some(job) => (ProblemKind::SlowJob, limits.slow_job_after, format!("'{job}' is still running")),
                None => (ProblemKind::Stuck, limits.stuck_after, format!("a lock taken at {} by thread '{}' hasn't been released", hold.at, hold.thread_name)),
            };
            if waited >= limit && hold.since.elapsed() >= limit {
                found.push((kind, format!("Thread '{}' at {} is waiting because {what}.", wait.thread_name, wait.at)));
            }
        }
        for (kind, text) in found {
            remember(&mut r, kind, text);
        }
    }

    pub fn start_watchdog(log_dir: std::path::PathBuf) {
        static STARTED: OnceLock<()> = OnceLock::new();
        if STARTED.set(()).is_err() {
            return;
        }
        let spawned = std::thread::Builder::new().name("lock-watch".into()).spawn(move || {
            loop {
                std::thread::sleep(WATCH_EVERY);
                scan(Limits::default());
                write_logs(&log_dir);
            }
        });
        if let Err(e) = spawned {
            log::warn!("couldn't start the lock watchdog: {e}");
        }
    }

    /// Give each new problem its log file. Files are written outside the registry's lock.
    pub(super) fn write_logs(dir: &std::path::Path) {
        let new: Vec<(usize, String)> = registry().problems.iter().enumerate().filter(|(_, p)| p.log.is_none()).map(|(i, p)| (i, p.summary.clone())).collect();
        for (n, summary) in new {
            let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
            let path = dir.join(format!("lock-{stamp}-{n}.log"));
            let text = format!("Craft Anything lock report\n\n{summary}\n\nEverything holding or waiting on a lock now:\n{}\n", snapshot());
            let saved = std::fs::create_dir_all(dir)
                .map_err(|e| e.to_string())
                .and_then(|()| crate::write_atomic_private(&path, text.as_bytes()).map_err(|e| e.message));
            match saved {
                Ok(()) => {
                    if let Some(p) = registry().problems.iter_mut().find(|p| p.summary == summary) {
                        p.log = Some(path);
                    }
                }
                Err(e) => log::warn!("couldn't save a lock report: {e}"),
            }
        }
    }

    fn snapshot() -> String {
        let r = registry();
        let holds = r.holds.values().map(|h| {
            let job = h.job.map(|j| format!(" for '{j}'")).unwrap_or_default();
            format!("  held by thread '{}' at {} for {} s{job}", h.thread_name, h.at, h.since.elapsed().as_secs())
        });
        let waits = r.waits.values().map(|w| format!("  waited on by thread '{}' at {} for {} s", w.thread_name, w.at, w.since.elapsed().as_secs()));
        holds.chain(waits).collect::<Vec<_>>().join("\n")
    }
}

#[cfg(all(test, not(target_arch = "wasm32")))]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::mpsc::channel;

    const LIMIT: Duration = Duration::from_secs(20);

    fn text(p: Box<dyn std::any::Any + Send>) -> String {
        p.downcast_ref::<String>().cloned().unwrap_or_default()
    }

    #[test]
    fn a_thread_that_locks_twice_stops_instead_of_hanging() {
        let m = Arc::new(Mutex::new(1));
        let m2 = m.clone();
        let (done, finished) = channel();
        std::thread::spawn(move || {
            // Exactly the shape of the bug: both guards live until the statement ends.
            let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| *m2.lock().unwrap() + *m2.lock().unwrap()));
            let _ = done.send(r.map_err(text));
        });
        let why = finished.recv_timeout(LIMIT).expect("it hung").unwrap_err();
        assert!(why.contains("deadlock") && why.contains("sync.rs"), "says where: {why}");
        assert!(problems().iter().any(|p| p.kind == ProblemKind::Broken && p.summary == why));
        // The lock is free again, poisoned by the unwind and still usable.
        assert_eq!(*m.lock().unwrap_or_else(PoisonError::into_inner), 1);
    }

    #[test]
    fn two_threads_in_a_cycle_are_untangled_and_one_finishes() {
        let (a, b) = (Arc::new(Mutex::new(0)), Arc::new(Mutex::new(0)));
        let (done, finished) = channel();
        for (first, second) in [(a.clone(), b.clone()), (b, a)] {
            let done = done.clone();
            std::thread::spawn(move || {
                let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let _one = first.lock().unwrap_or_else(PoisonError::into_inner);
                    std::thread::sleep(Duration::from_millis(100));
                    let _two = second.lock().unwrap_or_else(PoisonError::into_inner);
                }));
                let _ = done.send(r.is_ok());
            });
        }
        let results = [finished.recv_timeout(LIMIT).expect("it hung"), finished.recv_timeout(LIMIT).expect("it hung")];
        assert_eq!(results.iter().filter(|ok| **ok).count(), 1, "one stops, so the other finishes: {results:?}");
    }

    #[test]
    fn a_long_job_is_waited_for_however_short_the_limits() {
        let m = Arc::new(Mutex::new(0));
        let g = m.lock().unwrap();
        g.label("big-job");
        let (m2, (done, finished)) = (m.clone(), channel());
        std::thread::spawn(move || {
            let limits = Limits { stuck_after: Duration::ZERO, give_up_after: Duration::ZERO, slow_job_after: Duration::ZERO };
            let got = m2.wait(Location::caller(), &|| false, limits, true).map(|_| ());
            let _ = done.send(got);
        });
        assert!(finished.recv_timeout(Duration::from_millis(300)).is_err(), "still waiting on the job");
        drop(g);
        assert_eq!(finished.recv_timeout(LIMIT).expect("it hung"), Ok(()));
    }

    #[test]
    fn a_holder_that_never_lets_go_is_given_up_on_and_stop_works_while_waiting() {
        let m = Arc::new(Mutex::new(0));
        let g = m.lock().unwrap();
        let (m2, (done, finished)) = (m.clone(), channel());
        std::thread::spawn(move || {
            let limits = Limits { stuck_after: Duration::from_millis(50), ..Limits::default() };
            let _ = done.send(m2.wait(Location::caller(), &|| false, limits, true).map(|_| ()));
        });
        match finished.recv_timeout(LIMIT).expect("it hung") {
            Err(GaveUp::Stuck(why)) => assert!(why.contains("hasn't been released"), "{why}"),
            other => panic!("{other:?}"),
        }
        let stopped = m.clone();
        let (done, finished) = channel();
        std::thread::spawn(move || {
            let _ = done.send(stopped.lock_unless(&|| true).map(|_| ()));
        });
        assert_eq!(finished.recv_timeout(LIMIT).expect("it hung"), Err(GaveUp::Stopped));
        drop(g);
        assert!(m.try_lock().is_ok());
    }

    #[test]
    fn the_watchdog_reports_a_stuck_holder_in_a_log_and_can_forget_it() {
        let dir = tempfile::tempdir().unwrap();
        let m = Arc::new(Mutex::new(0));
        let g = m.lock().unwrap();
        let (m2, (done, finished)) = (m.clone(), channel());
        std::thread::spawn(move || {
            let _ = done.send(m2.lock_unless(&|| false).map(|_| ()));
        });
        std::thread::sleep(Duration::from_millis(50));
        tracker::scan(Limits { stuck_after: Duration::ZERO, ..Limits::default() });
        tracker::write_logs(dir.path());
        let p = problems().into_iter().find(|p| p.kind == ProblemKind::Stuck && p.summary.contains("sync.rs")).expect("reported");
        let log = std::fs::read_to_string(p.log.clone().expect("has a log")).unwrap();
        assert!(log.contains(&p.summary) && log.contains("held by thread"), "{log}");
        dismiss(&p.summary);
        assert!(!problems().iter().any(|q| q.summary == p.summary));
        drop(g);
        assert_eq!(finished.recv_timeout(LIMIT).expect("it hung"), Ok(()));
    }
}
