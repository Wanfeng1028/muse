//! Stand-in runs, for tests of whatever holds a [`RunSet`] (the app's screens, a fork's own front
//! end): they start at once, run no coding agent, and report only what the test tells them to.
//! Each keeps its project's feed like a real run, so opening a project shows what it reported.

use super::runs::Starter;
use super::*;

struct Handle {
    root: PathBuf,
    /// Started to carry on where the last run stopped (`RunOptions::continuing`).
    continuing: bool,
    running: Arc<AtomicBool>,
    tx: Sender<RunEvent>,
    feed: Arc<Mutex<feed::FeedLog>>,
}

/// Hands out stand-in runs ([`StandIns::starter`]) and drives them.
#[derive(Default, Clone)]
pub struct StandIns {
    started: Arc<Mutex<Vec<Handle>>>,
    /// Projects (by name) whose runs fail to start.
    failing: Vec<String>,
}

impl StandIns {
    pub fn new() -> StandIns {
        StandIns::default()
    }

    /// Runs on the project named `name` fail to start, as with no coding agent.
    pub fn failing(mut self, name: &str) -> StandIns {
        self.failing.push(name.to_string());
        self
    }

    /// A starter for [`RunSet::with_starter`].
    pub fn starter(&self) -> Starter {
        let (all, failing) = (self.started.clone(), self.failing.clone());
        Box::new(move |_hub, ws, opts| {
            if failing.contains(&ws.manifest.name) {
                return Err(ToolError::invalid("No coding agent."));
            }
            let (tx, rx) = std::sync::mpsc::channel();
            let running = Arc::new(AtomicBool::new(true));
            let feed = Arc::new(Mutex::new(feed::FeedLog::open(&ws)));
            if let Some(shown) = opts.shown {
                feed.lock().unwrap_or_else(PoisonError::into_inner).push(feed::FeedItem::User(shown));
            }
            all.lock().unwrap_or_else(PoisonError::into_inner).push(Handle {
                root: ws.root.clone(),
                continuing: opts.continuing,
                running: running.clone(),
                tx,
                feed: feed.clone(),
            });
            let activity = feed.lock().unwrap_or_else(PoisonError::into_inner).activity();
            Ok(RebuildRun {
                activity,
                rx,
                stop: CancelToken::default(),
                inbox: Inbox::new(ws.inbox_dir()),
                running,
                preview: Arc::default(),
                notes: Arc::default(),
                feed,
                root: ws.root.clone(),
                started: std::time::Instant::now(),
            })
        })
    }

    /// Every run started so far, by project folder, in order.
    pub fn started(&self) -> Vec<PathBuf> {
        self.started.lock().unwrap_or_else(PoisonError::into_inner).iter().map(|h| h.root.clone()).collect()
    }

    /// The runs started to carry on where the last one stopped, by project folder, in order.
    pub fn continued(&self) -> Vec<PathBuf> {
        self.started.lock().unwrap_or_else(PoisonError::into_inner).iter().filter(|h| h.continuing).map(|h| h.root.clone()).collect()
    }

    /// The project's latest run reports `e` (kept in its feed too). A `Finished` ends it.
    /// False when no run was started for it.
    pub fn send(&self, root: &Path, e: RunEvent) -> bool {
        let all = self.started.lock().unwrap_or_else(PoisonError::into_inner);
        let Some(h) = all.iter().rev().find(|h| h.root == root) else { return false };
        h.feed.lock().unwrap_or_else(PoisonError::into_inner).record(&e);
        let done = matches!(e, RunEvent::Finished { .. });
        let _ = h.tx.send(e);
        if done {
            h.running.store(false, Ordering::SeqCst);
        }
        true
    }

    /// The project's latest run finishes well ("Done.").
    pub fn finish(&self, root: &Path) -> bool {
        self.send(root, RunEvent::Finished { ok: true, message: "Done.".into(), paused: false })
    }
}
