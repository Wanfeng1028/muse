//! Process capture under a pseudo-terminal.
//!
//! [`capture`] runs one program inside a PTY with a scripted timeline of input, resize and signal
//! events, renders its output into a terminal grid, optionally snapshots a set of filesystem paths
//! before and after, and tears the whole process group down on timeout, idle, cancel or drop.
//!
//! Guarantees mirror [`crate::process`]:
//! - a wall-clock deadline and an idle (no-output) deadline always apply;
//! - captured output is capped so memory cannot blow up and the PTY never blocks the child;
//! - the child is spawned as its own session/process-group leader (the PTY is its controlling
//!   terminal), and the **whole process group** is killed on every exit path;
//! - a run-ownership token is placed in the child's environment so cleanup can be reasoned about;
//! - nothing ever blocks forever: every wait is bounded.
//!
//! Capture executes foreign code, so the engine gates the tool that calls this behind consent.
//! On Windows there is no terminal to render into: the program runs through [`crate::process`]
//! (its Job Object ends every process in it on timeout, cancel or drop) and its output is read
//! through pipes, which the result says; scripted events and watched files need the terminal
//! capture and are refused there. On other hosts (FreeBSD) [`capture`] returns a clear error
//! rather than pretending.
#![cfg_attr(not(any(target_os = "linux", target_os = "macos")), allow(dead_code, unused_imports))]

use crate::process::Cancel;
#[cfg(unix)]
use craft_anything_evidence::sha256_hex;
use craft_anything_evidence::{ErrorCode, ToolError};
use serde::Serialize;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::path::PathBuf;
use std::time::Duration;
// Only the Unix capture (and its tests) use these.
use crate::sync::Mutex;
#[cfg(unix)]
use std::sync::atomic::{AtomicU64, Ordering};
#[cfg(unix)]
use std::sync::{Arc, PoisonError};
#[cfg(unix)]
use std::time::{Instant, SystemTime};

/// Reserved environment variable that carries the per-run ownership token.
pub const RUN_ID_ENV: &str = "CRAFT_ANYTHING_RUN_ID";

/// A scripted terminal event, dispatched when the capture clock reaches `at_ms`.
#[derive(Debug, Clone)]
pub struct Event {
    pub at_ms: u64,
    pub kind: EventKind,
}

#[derive(Debug, Clone)]
pub enum EventKind {
    /// Write bytes to the child's terminal input. `sensitive` keeps the bytes out of the record.
    Input { data: Vec<u8>, sensitive: bool },
    /// Resize the terminal.
    Resize { cols: u16, rows: u16 },
    /// Send a signal to the child's whole process group.
    Signal(Sig),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Sig {
    Int,
    Term,
    Kill,
}

#[cfg(unix)]
impl Sig {
    fn as_str(self) -> &'static str {
        match self {
            Sig::Int => "SIGINT",
            Sig::Term => "SIGTERM",
            Sig::Kill => "SIGKILL",
        }
    }
}

/// Terminal geometry. `cols * (rows + scrollback)` is bounded by [`CELL_BUDGET`].
#[derive(Debug, Clone, Copy)]
pub struct Terminal {
    pub cols: u16,
    pub rows: u16,
    pub scrollback: usize,
}

impl Default for Terminal {
    fn default() -> Self {
        Terminal { cols: 80, rows: 24, scrollback: 1000 }
    }
}

/// The largest terminal cell budget we allocate for a capture.
pub const CELL_BUDGET: u64 = 1_000_000;

impl Terminal {
    pub fn validate(&self) -> Result<(), ToolError> {
        if self.cols == 0 || self.rows == 0 {
            return Err(ToolError::invalid("terminal columns and rows must be at least 1"));
        }
        let cells = u64::from(self.cols).saturating_mul(u64::from(self.rows).saturating_add(self.scrollback as u64));
        if cells > CELL_BUDGET {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("terminal is too large ({cells} cells); the limit is {CELL_BUDGET}"))
                .with_remediation("Use a smaller terminal size or less scrollback."));
        }
        Ok(())
    }
}

/// Resource ceilings for one capture.
#[derive(Debug, Clone, Copy)]
pub struct Limits {
    pub output_bytes: usize,
    pub files: usize,
    pub file_bytes: u64,
    pub watch_depth: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Limits { output_bytes: 1_000_000, files: 10_000, file_bytes: 10_000_000, watch_depth: 16 }
    }
}

/// Whether to run the child inside a sandbox when one is available.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum SandboxRequest {
    /// Never sandbox; run the program directly.
    #[default]
    Off,
    /// Use bubblewrap if it is installed; otherwise run directly and record that.
    IfAvailable,
}

/// Everything one capture needs.
#[derive(Debug, Clone)]
pub struct Spec {
    pub executable: OsString,
    pub args: Vec<OsString>,
    pub cwd: Option<PathBuf>,
    /// Extra environment, applied on top of the inherited environment.
    pub env: Vec<(String, String)>,
    pub terminal: Terminal,
    pub events: Vec<Event>,
    pub timeout: Duration,
    pub idle_timeout: Duration,
    pub settle: Duration,
    /// 0 = SIGKILL at the deadline; > 0 = SIGTERM, wait this long, then SIGKILL.
    pub finalization: Duration,
    pub observation_paths: Vec<PathBuf>,
    pub limits: Limits,
    pub sandbox: SandboxRequest,
}

// --------------------------------------------------------------------------------------------
// Result model (serde-serializable; becomes the evidence result)

#[derive(Debug, Clone, Serialize)]
pub struct Capture {
    pub manifest: Manifest,
    pub terminal: TerminalGrid,
    pub events: Vec<EventOutcome>,
    pub exit: ExitRecord,
    pub settlement: Settlement,
    pub filesystem: Option<Filesystem>,
    pub cleanup: Cleanup,
    pub limitations: Vec<Limitation>,
    pub still_unknown: Vec<Residual>,
    pub truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Manifest {
    pub platform: String,
    pub architecture: String,
    pub pty_backend: &'static str,
    pub started_at_unix_ms: u64,
    pub completed_at_unix_ms: u64,
    pub run_id: String,
    pub executable_name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub executable_sha256: Option<String>,
    pub argument_count: usize,
    pub sandbox: Sandbox,
}

#[derive(Debug, Clone, Serialize)]
pub struct Sandbox {
    pub available: bool,
    pub used: bool,
    pub kind: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TerminalGrid {
    pub columns: u16,
    pub rows: u16,
    pub cursor_row: u16,
    pub cursor_col: u16,
    pub alternate_screen: bool,
    /// Viewport rows, trailing spaces trimmed.
    pub lines: Vec<String>,
    pub output_bytes: usize,
    pub output_truncated: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct EventOutcome {
    pub at_ms: u64,
    pub sent_at_ms: u64,
    #[serde(rename = "type")]
    pub kind: String,
    /// `dispatched`, `program_exited`, or `failed`.
    pub outcome: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExitRecord {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signal: Option<String>,
    /// `exited`, `timeout`, `idle_timeout`, `cancelled`.
    pub reason: String,
    pub leader_pid: Option<u32>,
    pub finalized_with: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Settlement {
    /// `settled`, `still_running`, `unverifiable`.
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Cleanup {
    /// `verified` or `incomplete`.
    pub process_group: String,
    pub temporary_root: &'static str,
}

#[derive(Debug, Clone, Serialize)]
pub struct Filesystem {
    pub roots: Vec<Root>,
    pub before: Vec<FileState>,
    pub after: Vec<FileState>,
    pub effects: Vec<Effect>,
    pub file_list_cut_short: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct Root {
    pub alias: String,
    pub path: String,
    pub exhausted: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct FileState {
    pub path: String,
    #[serde(rename = "type")]
    pub kind: &'static str,
    pub size: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub symlink_target: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Effect {
    pub path: String,
    /// `created`, `deleted`, `modified`, `unchanged`, `unknown`.
    pub change: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub size: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Limitation {
    pub code: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Residual {
    pub scope: String,
    pub reason: String,
}

/// Generate a per-run ownership token (not a secret; a correlation id).
#[cfg(unix)]
fn run_id() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let n = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let seed = format!("{}|{nanos}|{n}", std::process::id());
    let h = sha256_hex(seed.as_bytes());
    h.get(..32).unwrap_or(&h).to_string()
}

#[cfg(unix)]
fn now_unix_ms() -> u64 {
    SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX)).unwrap_or(0)
}

/// Run a capture. Never blocks longer than the configured deadlines plus settlement.
#[cfg(any(target_os = "linux", target_os = "macos"))]
pub fn capture(spec: Spec, cancel: Cancel) -> Result<Capture, ToolError> {
    unix::capture(spec, cancel)
}

/// On Windows: through pipes, under the program's Job Object ([`piped`]).
#[cfg(windows)]
pub fn capture(spec: Spec, cancel: Cancel) -> Result<Capture, ToolError> {
    piped::capture(spec, cancel)
}

/// Elsewhere capture is unavailable: on FreeBSD the kernel discards output the reader has not
/// read yet when the program (the session leader) exits, so a short program's output was lost.
#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
pub fn capture(_spec: Spec, _cancel: Cancel) -> Result<Capture, ToolError> {
    Err(ToolError::new(ErrorCode::FeatureMissing, "Process capture is only available on Linux and macOS.")
        .with_remediation("Run the capture on a Linux or macOS host."))
}

/// Run a program that crashes without a real console (it asks the console for its size, which
/// fails on [`crate::process`]'s pipes) and return what it drew and its exit code. The deadline
/// and `cancel` still end it; nothing writes to its input.
#[cfg(windows)]
pub fn console_text(program: &std::path::Path, args: &[OsString], timeout: Duration, cancel: Option<Cancel>) -> Result<(String, Option<i32>), ToolError> {
    use portable_pty::{CommandBuilder, PtySize, native_pty_system};
    use std::io::{Read, Write};

    const ROWS: u16 = 50;
    const COLS: u16 = 200;
    let failed = |e: &dyn std::fmt::Display| ToolError::new(ErrorCode::ProgramFailed, format!("{}: {e}", program.display()));
    let portable_pty::PtyPair { master, slave } =
        native_pty_system().openpty(PtySize { rows: ROWS, cols: COLS, pixel_width: 0, pixel_height: 0 }).map_err(|e| failed(&e))?;
    let mut cmd = CommandBuilder::new(program.as_os_str());
    cmd.args(args);
    let mut child = slave.spawn_command(cmd).map_err(|e| failed(&e))?;
    drop(slave);
    let mut reader = master.try_clone_reader().map_err(|e| failed(&e))?;
    let mut writer = master.take_writer().map_err(|e| failed(&e))?;
    // The console asks where the cursor is and starts nothing until it's told.
    writer.write_all(b"\x1b[1;1R").map_err(|e| failed(&e))?;

    let (screen_tx, screen_rx) = std::sync::mpsc::channel();
    let received = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let counted = received.clone();
    std::thread::Builder::new()
        .name("console-reader".into())
        .spawn(move || {
            // A fixed grid, so a chatty program can't grow this.
            let mut screen = vt100::Parser::new(ROWS, COLS, 0);
            let mut chunk = vec![0u8; 16 * 1024];
            while let Ok(n) = reader.read(&mut chunk) {
                let Some(part) = chunk.get(..n).filter(|p| !p.is_empty()) else { break };
                counted.fetch_add(n, std::sync::atomic::Ordering::Relaxed);
                screen.process(part);
            }
            let _ = screen_tx.send(screen.screen().contents());
        })
        .map_err(|e| failed(&e))?;

    let start = std::time::Instant::now();
    let stopped = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status.exit_code()),
            Ok(None) => {}
            Err(e) => break Err(failed(&e)),
        }
        if cancel.as_ref().is_some_and(|c| c()) {
            break Err(ToolError::new(ErrorCode::Cancelled, format!("{} was stopped.", program.display())));
        }
        if start.elapsed() >= timeout {
            break Err(ToolError::new(ErrorCode::TimedOut, format!("{} didn't finish in time and was stopped.", program.display())));
        }
        std::thread::sleep(Duration::from_millis(50));
    };
    if stopped.is_err() {
        let _ = child.kill();
    } else {
        // The console sends what the program drew a moment after it exits, and closing it first
        // can lose that on a busy computer: wait until output has come and stopped coming (2 s
        // at most).
        let until = std::time::Instant::now() + Duration::from_secs(2);
        let mut seen = usize::MAX;
        while std::time::Instant::now() < until {
            let now = received.load(std::sync::atomic::Ordering::Relaxed);
            if now > 0 && now == seen {
                break;
            }
            seen = now;
            std::thread::sleep(Duration::from_millis(150));
        }
    }
    // Closing the console flushes it and ends everything attached to it, which is what ends a
    // launcher's children here. It can block, so it happens away from here.
    // ponytail: no Job Object (portable-pty gives no process handle, and this workspace forbids
    // unsafe), so a program that leaves this console for one of its own survives.
    let _ = std::thread::Builder::new().name("console-close".into()).spawn(move || drop((writer, master)));
    let code = stopped?.try_into().ok();
    // On a busy computer closing the console takes seconds; output that never arrives is an
    // error, not an empty screen (a device list would read as "no devices").
    let text = screen_rx
        .recv_timeout(Duration::from_secs(15))
        .map_err(|_| ToolError::new(ErrorCode::TimedOut, format!("{} ended, but what it wrote didn't arrive in time.", program.display())))?;
    Ok((text, code))
}

#[cfg(all(test, windows))]
mod console_tests {
    use super::*;

    #[test]
    fn reads_what_the_program_drew_and_stops_at_the_deadline() {
        let cmd = PathBuf::from(std::env::var_os("ComSpec").unwrap());
        let echo: Vec<OsString> = ["/c", "echo hello-console & exit 3"].map(OsString::from).to_vec();
        let (text, code) = console_text(&cmd, &echo, Duration::from_secs(30), None).unwrap();
        assert!(text.contains("hello-console"), "{text:?}");
        assert_eq!(code, Some(3));
        let hang: Vec<OsString> = ["/c", "ping -n 60 127.0.0.1"].map(OsString::from).to_vec();
        assert_eq!(console_text(&cmd, &hang, Duration::from_millis(300), None).unwrap_err().code, ErrorCode::TimedOut);
    }

    #[test]
    fn nothing_it_started_outlives_the_deadline() {
        // The program starts a second one that keeps adding to a file, like a launcher and its Python.
        let dir = tempfile::tempdir().unwrap();
        let ticks = dir.path().join("ticks");
        std::fs::write(dir.path().join("tick.cmd"), "@echo off\r\n:again\r\necho x>>\"%~dp0ticks\"\r\nping -n 2 127.0.0.1 >nul\r\ngoto again\r\n").unwrap();
        std::fs::write(dir.path().join("main.cmd"), "@echo off\r\nstart /b cmd /c \"%~dp0tick.cmd\"\r\nping -n 60 127.0.0.1 >nul\r\n").unwrap();
        let cmd = PathBuf::from(std::env::var_os("ComSpec").unwrap());
        let run = vec![OsString::from("/c"), dir.path().join("main.cmd").into_os_string()];
        let e = console_text(&cmd, &run, Duration::from_secs(4), None).unwrap_err();
        assert_eq!(e.code, ErrorCode::TimedOut);
        assert!(ticks.is_file(), "the second program never ran");
        std::thread::sleep(Duration::from_secs(2));
        let before = std::fs::metadata(&ticks).unwrap().len();
        std::thread::sleep(Duration::from_secs(4));
        assert_eq!(std::fs::metadata(&ticks).unwrap().len(), before, "the second program is still running");
    }
}

/// A capture without a terminal: the program's output read through pipes. Its Job Object ends
/// every process it started when the run ends, times out or is cancelled.
#[cfg(any(windows, test))]
mod piped {
    use super::*;
    use crate::process::Process;
    use serde_json::Value;

    /// Why a capture on this host has no terminal, recorded with every result.
    pub const NO_TERMINAL: &str = "There's no terminal capture on Windows: the output was read through pipes, so a program that draws a full-screen terminal interface or colours its output looks different, and its error output follows its normal output instead of being interleaved.";

    pub fn capture(spec: Spec, cancel: Cancel) -> Result<Capture, ToolError> {
        if !spec.events.is_empty() || !spec.observation_paths.is_empty() {
            return Err(ToolError::new(
                ErrorCode::FeatureMissing,
                "Typed input, resizes, signals and watched files need the terminal capture, which runs on Linux and macOS.",
            )
            .with_remediation("Leave out events and watched_paths, or run the capture on Linux or macOS."));
        }
        let now = || {
            std::time::SystemTime::now()
                .duration_since(std::time::SystemTime::UNIX_EPOCH)
                .map(|d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
                .unwrap_or(0)
        };
        let started = now();
        let mut p = Process::new(&spec.executable)
            .args(&spec.args)
            .timeout(spec.timeout)
            .idle_timeout(spec.idle_timeout)
            .stdout_cap(spec.limits.output_bytes)
            .stderr_cap(spec.limits.output_bytes)
            .cancel(cancel);
        for (k, v) in &spec.env {
            p = p.env(k, v);
        }
        if let Some(cwd) = &spec.cwd {
            p = p.cwd(cwd);
        }
        let partial = |e: &ToolError, k: &str| {
            e.details.as_ref().and_then(|d| d.pointer(&format!("/partial/{k}"))).and_then(Value::as_str).unwrap_or_default().to_string()
        };
        let (code, reason, stdout, stderr, truncated) = match p.run() {
            Ok(o) => (o.code, "exited", o.stdout_text(), o.stderr_text(), o.stdout_truncated || o.stderr_truncated),
            // A program still running at its deadline is a normal result; only its output's end is kept.
            Err(e) if e.code == ErrorCode::TimedOut => {
                let idle = e.details.as_ref().and_then(|d| d.get("deadline")).and_then(Value::as_str) == Some("idle");
                (None, if idle { "idle_timeout" } else { "timeout" }, partial(&e, "stdout_tail"), partial(&e, "stderr_tail"), true)
            }
            Err(e) if e.code == ErrorCode::Cancelled => (None, "cancelled", partial(&e, "stdout_tail"), partial(&e, "stderr_tail"), true),
            Err(e) => return Err(e),
        };
        let output_bytes = stdout.len().saturating_add(stderr.len());
        let text = [stdout, stderr].into_iter().filter(|t| !t.trim().is_empty()).collect::<Vec<_>>().join("\n");
        Ok(Capture {
            manifest: Manifest {
                platform: std::env::consts::OS.into(),
                architecture: std::env::consts::ARCH.into(),
                pty_backend: "pipes",
                started_at_unix_ms: started,
                completed_at_unix_ms: now(),
                run_id: format!("{started:x}-{}", std::process::id()),
                executable_name: std::path::Path::new(&spec.executable).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
                executable_sha256: super::hash_file(std::path::Path::new(&spec.executable)),
                argument_count: spec.args.len(),
                sandbox: Sandbox { available: false, used: false, kind: "none", reason: Some("no sandbox on this host".into()) },
            },
            terminal: TerminalGrid {
                columns: spec.terminal.cols,
                rows: spec.terminal.rows,
                cursor_row: 0,
                cursor_col: 0,
                alternate_screen: false,
                lines: screen(&text, spec.terminal.rows),
                output_bytes,
                output_truncated: truncated,
            },
            events: Vec::new(),
            exit: ExitRecord { code, signal: None, reason: reason.into(), leader_pid: None, finalized_with: None },
            settlement: Settlement { status: if reason == "exited" { "settled".into() } else { "still_running".into() } },
            filesystem: None,
            cleanup: Cleanup { process_group: "verified".into(), temporary_root: "none" },
            limitations: vec![
                Limitation { code: "no_terminal".into(), message: NO_TERMINAL.into() },
                Limitation {
                    code: "job_object".into(),
                    message: "Every process the program started was ended with its Job Object, which the system empties when the run ends.".into(),
                },
            ],
            still_unknown: Vec::new(),
            truncated,
        })
    }

    /// The last `rows` lines the output would leave on a terminal of that height, with carriage
    /// returns and trailing spaces and blank lines removed, as the terminal capture reports them.
    pub fn screen(text: &str, rows: u16) -> Vec<String> {
        let mut lines: Vec<String> = text.lines().map(|l| l.rsplit('\r').next().unwrap_or(l).trim_end().to_string()).collect();
        while lines.last().is_some_and(String::is_empty) {
            lines.pop();
        }
        let keep = usize::from(rows.max(1));
        lines.split_off(lines.len().saturating_sub(keep))
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn the_screen_keeps_the_last_rows_as_a_terminal_would() {
            assert_eq!(screen("a\r\nb  \r\nhalf\rdone\n\n\n", 24), ["a", "b", "done"]);
            assert_eq!(screen("1\n2\n3\n4\n", 2), ["3", "4"]);
            assert!(screen("", 24).is_empty());
        }

        #[test]
        #[cfg_attr(not(windows), ignore)]
        fn a_windows_program_is_captured_through_pipes() {
            let spec = |args: &[&str], timeout_ms: u64| Spec {
                executable: "cmd.exe".into(),
                args: args.iter().map(Into::into).collect(),
                cwd: None,
                env: vec![("CRAFT_TEST_WORD".into(), "first".into())],
                terminal: Terminal::default(),
                events: Vec::new(),
                timeout: Duration::from_millis(timeout_ms),
                idle_timeout: Duration::from_millis(timeout_ms),
                settle: Duration::ZERO,
                finalization: Duration::ZERO,
                observation_paths: Vec::new(),
                limits: Limits::default(),
                sandbox: SandboxRequest::Off,
            };
            let never: Cancel = std::sync::Arc::new(|| false);
            let only_errors = capture(spec(&["/c", "echo oops 1>&2 & exit 2"], 10_000), never.clone()).unwrap();
            assert_eq!(only_errors.terminal.lines, ["oops"], "no blank line before error output alone");
            let c = capture(spec(&["/c", "echo %CRAFT_TEST_WORD% & exit 3"], 10_000), never.clone()).unwrap();
            assert_eq!((c.exit.reason.as_str(), c.exit.code), ("exited", Some(3)));
            assert_eq!(c.terminal.lines, ["first"]);
            assert_eq!(c.manifest.pty_backend, "pipes");
            assert!(c.limitations.iter().any(|l| l.code == "no_terminal"));
            // Still running at its deadline: a result, not an error, and nothing is left running.
            let slow = capture(spec(&["/c", "echo started & ping -n 30 127.0.0.1 >nul"], 1500), never.clone()).unwrap();
            assert_eq!(slow.exit.reason, "timeout");
            assert!(slow.terminal.lines.iter().any(|l| l.contains("started")), "{:?}", slow.terminal.lines);
            let mut with_input = spec(&["/c", "echo x"], 5000);
            with_input.events.push(Event { at_ms: 10, kind: EventKind::Input { data: b"y\n".to_vec(), sensitive: false } });
            assert_eq!(capture(with_input, never).unwrap_err().code, ErrorCode::FeatureMissing, "typed input needs a terminal");
        }
    }
}

/// Capped byte buffer shared with the reader thread.
#[cfg(unix)]
struct Capped {
    data: Vec<u8>,
    cap: usize,
    observed: usize,
    truncated: bool,
}

#[cfg(unix)]
impl Capped {
    fn new(cap: usize) -> Self {
        Capped { data: Vec::new(), cap, observed: 0, truncated: false }
    }

    fn push(&mut self, bytes: &[u8]) {
        self.observed = self.observed.saturating_add(bytes.len());
        let room = self.cap.saturating_sub(self.data.len());
        if bytes.len() > room {
            self.truncated = true;
        }
        if let Some(part) = bytes.get(..room.min(bytes.len())) {
            self.data.extend_from_slice(part);
        }
    }
}

// --------------------------------------------------------------------------------------------
// Filesystem snapshots (pure; shared across platforms)

/// Snapshot the observation paths. Records path, type, size and sha256 (never file contents).
pub fn snapshot(paths: &[PathBuf], limits: &Limits, cancel: &Cancel) -> (Vec<Root>, Vec<FileState>, bool) {
    let mut roots = Vec::new();
    let mut states: BTreeMap<String, FileState> = BTreeMap::new();
    let mut truncated = false;
    let mut file_budget = limits.file_bytes;
    let mut count = 0usize;
    for (idx, path) in paths.iter().enumerate() {
        let alias = format!("root_{idx}");
        let mut exhausted = true;
        // Depth-first with an explicit stack; never follow symlinks.
        let mut stack: Vec<(PathBuf, usize)> = vec![(path.clone(), 0)];
        while let Some((p, depth)) = stack.pop() {
            if cancel() {
                exhausted = false;
                break;
            }
            let meta = match std::fs::symlink_metadata(&p) {
                Ok(m) => m,
                Err(_) => continue,
            };
            let ft = meta.file_type();
            let display = p.display().to_string();
            if ft.is_symlink() {
                let target = std::fs::read_link(&p).ok().map(|t| t.display().to_string());
                states.insert(display.clone(), FileState { path: display, kind: "symlink", size: meta.len(), sha256: None, symlink_target: target });
            } else if ft.is_dir() {
                states.insert(display.clone(), FileState { path: display, kind: "directory", size: 0, sha256: None, symlink_target: None });
                if depth >= limits.watch_depth {
                    truncated = true;
                    exhausted = false;
                    continue;
                }
                match std::fs::read_dir(&p) {
                    Ok(entries) => {
                        let mut names: Vec<PathBuf> = entries.flatten().map(|e| e.path()).collect();
                        names.sort();
                        for child in names {
                            stack.push((child, depth.saturating_add(1)));
                        }
                    }
                    Err(_) => {
                        exhausted = false;
                    }
                }
            } else if ft.is_file() {
                count = count.saturating_add(1);
                if count > limits.files {
                    truncated = true;
                    exhausted = false;
                    continue;
                }
                let size = meta.len();
                let sha = if size <= file_budget {
                    file_budget = file_budget.saturating_sub(size);
                    hash_file(&p)
                } else {
                    truncated = true;
                    None
                };
                states.insert(display.clone(), FileState { path: display, kind: "file", size, sha256: sha, symlink_target: None });
            } else {
                states.insert(display.clone(), FileState { path: display, kind: "other", size: meta.len(), sha256: None, symlink_target: None });
            }
        }
        roots.push(Root { alias, path: path.display().to_string(), exhausted });
    }
    (roots, states.into_values().collect(), truncated)
}

fn hash_file(path: &std::path::Path) -> Option<String> {
    use std::io::Read as _;
    let mut f = std::fs::File::open(path).ok()?;
    let mut hasher = <sha2::Sha256 as sha2::Digest>::new();
    let mut buf = vec![0u8; 64 * 1024];
    loop {
        match f.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => {
                if let Some(part) = buf.get(..n) {
                    sha2::Digest::update(&mut hasher, part);
                }
            }
            Err(_) => return None,
        }
    }
    Some(hex::encode(sha2::Digest::finalize(hasher)))
}

/// Compute per-path effects between two snapshots.
pub fn effects(before: &[FileState], after: &[FileState], roots_exhausted: bool) -> Vec<Effect> {
    let bmap: BTreeMap<&str, &FileState> = before.iter().map(|f| (f.path.as_str(), f)).collect();
    let amap: BTreeMap<&str, &FileState> = after.iter().map(|f| (f.path.as_str(), f)).collect();
    let mut out = Vec::new();
    for (path, a) in &amap {
        match bmap.get(path) {
            None => out.push(Effect { path: (*path).to_string(), change: if roots_exhausted { "created" } else { "unknown" }, size: Some(a.size) }),
            Some(b) => {
                let changed = b.size != a.size || b.kind != a.kind || b.symlink_target != a.symlink_target;
                // A file left unhashed (over the hashing budget, or unreadable) may have been
                // rewritten at the same size, so equal sizes don't make it unchanged (#229).
                let change = if changed || (b.sha256.is_some() && a.sha256.is_some() && b.sha256 != a.sha256) {
                    "modified"
                } else if a.kind == "file" && (b.sha256.is_none() || a.sha256.is_none()) {
                    "unknown"
                } else {
                    "unchanged"
                };
                out.push(Effect { path: (*path).to_string(), change, size: Some(a.size) });
            }
        }
    }
    for (path, b) in &bmap {
        if !amap.contains_key(path) {
            out.push(Effect { path: (*path).to_string(), change: if roots_exhausted { "deleted" } else { "unknown" }, size: Some(b.size) });
        }
    }
    out.sort_by(|x, y| x.path.cmp(&y.path));
    out
}

#[cfg(test)]
mod effect_tests {
    use super::*;

    /// #229: a same-size rewrite of a file neither snapshot hashed isn't known to be unchanged.
    #[test]
    fn an_unhashed_file_of_the_same_size_is_unknown() {
        let file = |sha: Option<&str>| FileState { path: "data.bin".into(), kind: "file", size: 10, sha256: sha.map(str::to_string), symlink_target: None };
        let link = |to: &str| FileState { path: "l".into(), kind: "symlink", size: 1, sha256: None, symlink_target: Some(to.into()) };
        let change = |b: FileState, a: FileState| effects(&[b], &[a], true).first().map(|e| e.change);
        assert_eq!(change(file(None), file(None)), Some("unknown"));
        assert_eq!(change(file(Some("aa")), file(None)), Some("unknown"));
        assert_eq!(change(file(Some("aa")), file(Some("aa"))), Some("unchanged"));
        assert_eq!(change(file(Some("aa")), file(Some("bb"))), Some("modified"));
        assert_eq!(change(file(None), FileState { size: 11, ..file(None) }), Some("modified"));
        assert_eq!(change(link("a"), link("a")), Some("unchanged"));
        assert_eq!(change(link("a"), link("b")), Some("modified"), "a symlink pointed elsewhere at the same length");
    }
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
mod unix {
    use super::*;
    use nix::sys::signal::{Signal, killpg};
    use nix::unistd::Pid;
    use portable_pty::{CommandBuilder, PtySize, native_pty_system};
    use std::io::{Read, Write};

    fn to_err(context: &str, e: impl std::fmt::Display) -> ToolError {
        ToolError::new(ErrorCode::RecordingFailed, format!("{context}: {e}"))
    }

    fn send_group(pid: i32, sig: Signal) -> bool {
        // pid is the session/group leader; its pgid equals its pid, so kill the group.
        killpg(Pid::from_raw(pid), sig).is_ok()
    }

    pub fn capture(spec: Spec, cancel: Cancel) -> Result<Capture, ToolError> {
        spec.terminal.validate()?;
        for w in spec.events.windows(2) {
            if let [a, b] = w
                && a.at_ms > b.at_ms
            {
                return Err(ToolError::invalid("walkthrough events must be ordered by at_ms"));
            }
        }

        let run_id = run_id();
        let started_at = now_unix_ms();
        let exe_sha = super::hash_file(std::path::Path::new(&spec.executable));

        // Sandbox discovery.
        let bwrap = crate::which::which("bwrap");
        let (sandbox, program, pre_args) = match spec.sandbox {
            SandboxRequest::Off => (
                Sandbox { available: bwrap.is_some(), used: false, kind: "none", reason: Some("sandbox not requested".into()) },
                spec.executable.clone(),
                Vec::new(),
            ),
            SandboxRequest::IfAvailable => match &bwrap {
                Some(path) => {
                    let args: Vec<OsString> =
                        ["--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--die-with-parent", "--unshare-pid", "--"]
                            .iter()
                            .map(OsString::from)
                            .collect();
                    (Sandbox { available: true, used: true, kind: "bubblewrap", reason: None }, path.clone().into_os_string(), args)
                }
                None => (
                    Sandbox { available: false, used: false, kind: "none", reason: Some("bubblewrap (bwrap) is not installed".into()) },
                    spec.executable.clone(),
                    Vec::new(),
                ),
            },
        };

        // Snapshot the filesystem before running.
        let fs_before = if spec.observation_paths.is_empty() { None } else { Some(snapshot(&spec.observation_paths, &spec.limits, &cancel)) };

        let pty = native_pty_system();
        let size = PtySize { rows: spec.terminal.rows, cols: spec.terminal.cols, pixel_width: 0, pixel_height: 0 };
        let pair = pty.openpty(size).map_err(|e| to_err("opening a pseudo-terminal", e))?;

        let mut cmd = CommandBuilder::new(&program);
        for a in &pre_args {
            cmd.arg(a);
        }
        if !pre_args.is_empty() {
            cmd.arg(&spec.executable);
        }
        for a in &spec.args {
            cmd.arg(a);
        }
        if let Some(cwd) = &spec.cwd {
            cmd.cwd(cwd);
        }
        for (k, v) in &spec.env {
            cmd.env(k, v);
        }
        cmd.env(RUN_ID_ENV, &run_id);
        cmd.env("TERM", "xterm-256color");

        let portable_pty::PtyPair { master, slave } = pair;
        let mut child = slave.spawn_command(cmd).map_err(|e| to_err("starting the program", e))?;
        // Drop the slave so the reader sees EOF when the child and our writer are gone.
        drop(slave);
        let leader_pid = child.process_id();

        let mut writer = master.take_writer().map_err(|e| to_err("opening the terminal input", e))?;
        let mut reader = master.try_clone_reader().map_err(|e| to_err("opening the terminal output", e))?;

        let buf = Arc::new(Mutex::new(Capped::new(spec.limits.output_bytes)));
        let parser = Arc::new(Mutex::new(vt100::Parser::new(spec.terminal.rows, spec.terminal.cols, spec.terminal.scrollback)));
        let last_output = Arc::new(AtomicU64::new(0));
        let start = Instant::now();

        let r_buf = buf.clone();
        let r_parser = parser.clone();
        let r_last = last_output.clone();
        let reader_thread = std::thread::Builder::new()
            .name("capture-reader".into())
            .spawn(move || {
                let mut chunk = vec![0u8; 64 * 1024];
                loop {
                    match reader.read(&mut chunk) {
                        Ok(0) => break,
                        Ok(n) => {
                            r_last.store(u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX), Ordering::Relaxed);
                            if let Some(part) = chunk.get(..n) {
                                r_buf.lock().unwrap_or_else(PoisonError::into_inner).push(part);
                                r_parser.lock().unwrap_or_else(PoisonError::into_inner).process(part);
                            }
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                        Err(_) => break,
                    }
                }
            })
            .map_err(|e| to_err("starting the output reader", e))?;

        // Event timeline, ordered.
        let mut pending: std::collections::VecDeque<Event> = spec.events.iter().cloned().collect();
        let mut event_outcomes: Vec<EventOutcome> = Vec::new();

        let mut exit_code: Option<i32> = None;
        let mut exit_signal: Option<String> = None;
        let mut finalized_with: Option<String> = None;

        // Main supervision loop; breaks with the stop reason.
        let reason: String = loop {
            // Dispatch any events whose time has come.
            let elapsed_ms = u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX);
            while pending.front().is_some_and(|e| e.at_ms <= elapsed_ms) {
                if let Some(ev) = pending.pop_front() {
                    let (kind, outcome, detail) = dispatch(&ev, &mut writer, master.as_ref(), leader_pid);
                    event_outcomes.push(EventOutcome { at_ms: ev.at_ms, sent_at_ms: elapsed_ms, kind, outcome, detail });
                }
            }

            match child.try_wait() {
                Ok(Some(status)) => {
                    if status.success() {
                        exit_code = Some(0);
                    } else {
                        exit_code = Some(i32::try_from(status.exit_code()).unwrap_or(-1));
                    }
                    break "exited".into();
                }
                Ok(None) => {}
                Err(e) => {
                    exit_signal = Some(format!("wait failed: {e}"));
                    break "exited".into();
                }
            }

            if cancel() {
                break "cancelled".into();
            }
            if start.elapsed() >= spec.timeout {
                break "timeout".into();
            }
            let last = last_output.load(Ordering::Relaxed);
            if elapsed_ms.saturating_sub(last) >= u64::try_from(spec.idle_timeout.as_millis()).unwrap_or(u64::MAX) {
                break "idle_timeout".into();
            }

            std::thread::sleep(Duration::from_millis(10));
        };
        // Teardown: kill the whole process group, including any helper that outlived a normal leader exit.
        if let Some(pid) = leader_pid.and_then(|p| i32::try_from(p).ok()) {
            if group_alive(pid) && spec.finalization > Duration::ZERO {
                send_group(pid, Signal::SIGTERM);
                finalized_with = Some("SIGTERM".into());
                // Wait for the whole group, not just the leader: a helper can outlive it (#230).
                // Reaping the leader as we go keeps a zombie from counting as alive.
                let deadline = Instant::now() + spec.finalization;
                while Instant::now() < deadline {
                    let _ = child.try_wait();
                    if !group_alive(pid) {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(10));
                }
            }
            let _ = child.try_wait();
            if group_alive(pid) {
                send_group(pid, Signal::SIGKILL);
                finalized_with = Some("SIGKILL".into());
            }
        }
        if reason != "exited" {
            let _ = child.kill();
        }

        // Reap the child (bounded).
        let reap_deadline = Instant::now() + Duration::from_secs(2);
        loop {
            match child.try_wait() {
                Ok(Some(status)) => {
                    if exit_code.is_none() && exit_signal.is_none() {
                        exit_code = Some(i32::try_from(status.exit_code()).unwrap_or(-1));
                    }
                    break;
                }
                _ => {
                    if Instant::now() >= reap_deadline {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis(10));
                }
            }
        }

        // Close our writer and master so the reader gets EOF, then join it (bounded).
        drop(writer);
        drop(master);
        let join_deadline = Instant::now() + Duration::from_secs(2);
        while !reader_thread.is_finished() && Instant::now() < join_deadline {
            std::thread::sleep(Duration::from_millis(5));
        }
        let reader_done = reader_thread.is_finished();
        if reader_done {
            let _ = reader_thread.join();
        }

        // Settlement: confirm the group is gone.
        let settlement = settle(leader_pid, spec.settle);

        // Snapshot after.
        let fs_after = if spec.observation_paths.is_empty() { None } else { Some(snapshot(&spec.observation_paths, &spec.limits, &cancel)) };
        let filesystem = match (fs_before, fs_after) {
            (Some((roots, before, t1)), Some((_, after, t2))) => {
                let exhausted = roots.iter().all(|r| r.exhausted);
                let fx = effects(&before, &after, exhausted);
                Some(Filesystem { roots, before, after, effects: fx, file_list_cut_short: t1 || t2 })
            }
            _ => None,
        };

        // Build the terminal grid from the final screen.
        let grid = {
            let p = parser.lock().unwrap_or_else(PoisonError::into_inner);
            let screen = p.screen();
            let (crow, ccol) = screen.cursor_position();
            let (rows, cols) = screen.size();
            let mut lines = Vec::new();
            for row in 0..rows {
                let text = screen.contents_between(row, 0, row, cols);
                lines.push(text.trim_end_matches(' ').to_string());
            }
            let b = buf.lock().unwrap_or_else(PoisonError::into_inner);
            TerminalGrid {
                columns: cols,
                rows,
                cursor_row: crow,
                cursor_col: ccol,
                alternate_screen: screen.alternate_screen(),
                lines,
                output_bytes: b.observed,
                output_truncated: b.truncated,
            }
        };

        let output_truncated = grid.output_truncated;

        let mut limitations = vec![Limitation {
            code: "capture_is_observational".into(),
            message: "A capture shows one run under one set of inputs; other inputs may behave differently.".into(),
        }];
        let mut residual = Vec::new();
        if !reader_done {
            limitations.push(Limitation {
                code: "output_reader_not_drained".into(),
                message: "A descendant kept the terminal open; output may be incomplete.".into(),
            });
            residual.push(Residual { scope: "terminal".into(), reason: "output pipe held open after exit".into() });
        }
        if output_truncated {
            limitations.push(Limitation { code: "output_truncated".into(), message: "Terminal output exceeded the byte limit and was cut short.".into() });
        }
        let cleanup_ok = settlement.status != "still_running";
        if !cleanup_ok {
            residual.push(Residual { scope: "process".into(), reason: "a process in the group was still alive at the settlement deadline".into() });
        }

        Ok(Capture {
            manifest: Manifest {
                platform: std::env::consts::OS.into(),
                architecture: std::env::consts::ARCH.into(),
                pty_backend: "portable-pty",
                started_at_unix_ms: started_at,
                completed_at_unix_ms: now_unix_ms(),
                run_id,
                executable_name: std::path::Path::new(&spec.executable).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
                executable_sha256: exe_sha,
                argument_count: spec.args.len(),
                sandbox,
            },
            terminal: grid,
            events: event_outcomes,
            exit: ExitRecord { code: exit_code, signal: exit_signal, reason, leader_pid, finalized_with },
            settlement,
            filesystem,
            cleanup: Cleanup { process_group: if cleanup_ok { "verified".into() } else { "incomplete".into() }, temporary_root: "not_required" },
            limitations,
            still_unknown: residual,
            truncated: output_truncated,
        })
    }

    fn dispatch(ev: &Event, writer: &mut Box<dyn Write + Send>, master: &dyn portable_pty::MasterPty, leader: Option<u32>) -> (String, String, Option<String>) {
        match &ev.kind {
            EventKind::Input { data, sensitive } => {
                let kind = "input".to_string();
                match writer.write_all(data).and_then(|_| writer.flush()) {
                    Ok(()) => (kind, "dispatched".into(), if *sensitive { Some("<redacted-input>".into()) } else { None }),
                    Err(e) => (kind, "failed".into(), Some(e.to_string())),
                }
            }
            EventKind::Resize { cols, rows } => {
                let size = PtySize { rows: *rows, cols: *cols, pixel_width: 0, pixel_height: 0 };
                match master.resize(size) {
                    Ok(()) => ("resize".into(), "dispatched".into(), None),
                    Err(e) => ("resize".into(), "failed".into(), Some(e.to_string())),
                }
            }
            EventKind::Signal(sig) => {
                let signal = match sig {
                    Sig::Int => Signal::SIGINT,
                    Sig::Term => Signal::SIGTERM,
                    Sig::Kill => Signal::SIGKILL,
                };
                let detail = Some(sig.as_str().to_string());
                match leader.and_then(|p| i32::try_from(p).ok()) {
                    Some(pid) if send_group(pid, signal) => ("signal".into(), "dispatched".into(), detail),
                    Some(_) => ("signal".into(), "program_exited".into(), detail),
                    None => ("signal".into(), "program_exited".into(), detail),
                }
            }
        }
    }

    /// Whether any process of the group led by `pid` is left (signal 0 probes without delivering).
    fn group_alive(pid: i32) -> bool {
        killpg(Pid::from_raw(pid), None).is_ok()
    }

    /// Poll the process group until it is empty or the settle deadline passes.
    fn settle(leader: Option<u32>, settle: Duration) -> Settlement {
        let pid = match leader.and_then(|p| i32::try_from(p).ok()) {
            Some(p) => p,
            None => return Settlement { status: "settled".into() },
        };
        let deadline = Instant::now() + settle;
        loop {
            if !group_alive(pid) {
                return Settlement { status: "settled".into() };
            }
            if Instant::now() >= deadline {
                return Settlement { status: "still_running".into() };
            }
            std::thread::sleep(Duration::from_millis(20));
        }
    }
}

#[cfg(all(test, any(target_os = "linux", target_os = "macos")))]
mod tests {
    use super::*;

    fn no_cancel() -> Cancel {
        Arc::new(|| false)
    }

    fn sh_available() -> bool {
        crate::which::which("sh").is_some()
    }

    #[test]
    fn captures_echo_output() {
        if !sh_available() {
            return;
        }
        let spec = Spec {
            executable: "/bin/sh".into(),
            args: vec!["-c".into(), "echo hello world".into()],
            cwd: None,
            env: Vec::new(),
            terminal: Terminal::default(),
            events: Vec::new(),
            timeout: Duration::from_secs(5),
            idle_timeout: Duration::from_secs(5),
            settle: Duration::from_millis(200),
            finalization: Duration::ZERO,
            observation_paths: Vec::new(),
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let cap = capture(spec, no_cancel()).unwrap();
        assert_eq!(cap.exit.reason, "exited");
        assert_eq!(cap.exit.code, Some(0));
        assert!(cap.terminal.lines.iter().any(|l| l.contains("hello world")), "{} bytes: {:?}", cap.terminal.output_bytes, cap.terminal.lines);
        assert_eq!(cap.manifest.run_id.len(), 32);
        assert!(!cap.manifest.run_id.is_empty());
    }

    #[test]
    fn wall_timeout_kills_and_settles() {
        if !sh_available() {
            return;
        }
        let spec = Spec {
            executable: "/bin/sh".into(),
            args: vec!["-c".into(), "sleep 30".into()],
            cwd: None,
            env: Vec::new(),
            terminal: Terminal::default(),
            events: Vec::new(),
            timeout: Duration::from_millis(300),
            idle_timeout: Duration::from_secs(30),
            settle: Duration::from_millis(500),
            finalization: Duration::ZERO,
            observation_paths: Vec::new(),
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let t = Instant::now();
        let cap = capture(spec, no_cancel()).unwrap();
        assert!(t.elapsed() < Duration::from_secs(5));
        assert_eq!(cap.exit.reason, "timeout");
        assert_eq!(cap.cleanup.process_group, "verified");
    }

    /// #230: with a grace period, the leader exits on SIGTERM; a helper that ignores it used to
    /// be left running because only the leader was waited for.
    #[test]
    fn graceful_timeout_kills_a_helper_that_outlives_the_leader() {
        if !sh_available() {
            return;
        }
        let script = "/bin/sh -c 'trap \"\" TERM HUP; exec /bin/sleep 12' & exec /bin/sleep 12";
        let spec = Spec {
            executable: "/bin/sh".into(),
            args: vec!["-c".into(), script.into()],
            cwd: None,
            env: Vec::new(),
            terminal: Terminal::default(),
            events: Vec::new(),
            timeout: Duration::from_millis(500),
            idle_timeout: Duration::from_secs(30),
            settle: Duration::from_millis(500),
            finalization: Duration::from_millis(500),
            observation_paths: Vec::new(),
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let cap = capture(spec, no_cancel()).unwrap();
        assert_eq!(cap.exit.reason, "timeout");
        assert_eq!(cap.settlement.status, "settled");
        assert_eq!(cap.cleanup.process_group, "verified");
        assert_eq!(cap.exit.finalized_with.as_deref(), Some("SIGKILL"), "the helper needed SIGKILL");
    }

    /// #361: when the leader exits normally after starting a helper in its process group,
    /// teardown still stops the surviving group member before returning.
    #[test]
    fn normal_exit_kills_a_helper_that_outlives_the_leader() {
        if !sh_available() {
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let ready = dir.path().join("helper.pid");
        let script = "sh -c 'trap \"\" HUP; echo $$ >\"$1\"; exec sleep 8' _ \"$1\" </dev/null >/dev/null 2>&1 & while [ ! -s \"$1\" ]; do sleep 0.02; done";
        let spec = Spec {
            executable: "/bin/sh".into(),
            args: vec!["-c".into(), script.into(), "leader".into(), ready.into_os_string()],
            cwd: Some(dir.path().to_path_buf()),
            env: Vec::new(),
            terminal: Terminal::default(),
            events: Vec::new(),
            timeout: Duration::from_secs(5),
            idle_timeout: Duration::from_secs(5),
            settle: Duration::from_millis(500),
            finalization: Duration::ZERO,
            observation_paths: Vec::new(),
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let cap = capture(spec, no_cancel()).unwrap();
        let group = i32::try_from(cap.exit.leader_pid.unwrap()).unwrap();
        assert_eq!(cap.exit.reason, "exited");
        assert_eq!(cap.exit.code, Some(0));
        assert_eq!(cap.settlement.status, "settled");
        assert_eq!(cap.cleanup.process_group, "verified");
        assert!(nix::sys::signal::killpg(nix::unistd::Pid::from_raw(group), None).is_err());
    }

    #[test]
    fn input_event_is_echoed() {
        if !sh_available() {
            return;
        }
        let spec = Spec {
            executable: "/bin/cat".into(),
            args: Vec::new(),
            cwd: None,
            env: Vec::new(),
            terminal: Terminal::default(),
            events: vec![
                Event { at_ms: 50, kind: EventKind::Input { data: b"ping\n".to_vec(), sensitive: false } },
                Event { at_ms: 200, kind: EventKind::Signal(Sig::Term) },
            ],
            timeout: Duration::from_secs(5),
            idle_timeout: Duration::from_secs(5),
            settle: Duration::from_millis(300),
            finalization: Duration::ZERO,
            observation_paths: Vec::new(),
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let cap = capture(spec, no_cancel()).unwrap();
        assert!(cap.terminal.lines.iter().any(|l| l.contains("ping")), "{:?}", cap.terminal.lines);
        assert!(cap.events.iter().any(|e| e.kind == "input" && e.outcome == "dispatched"));
    }

    #[test]
    fn filesystem_effects_detect_a_new_file() {
        if !sh_available() {
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let watch = dir.path().join("watch");
        std::fs::create_dir(&watch).unwrap();
        std::fs::write(watch.join("existing.txt"), b"old").unwrap();
        let script = format!("echo new > {}/created.txt", watch.display());
        let spec = Spec {
            executable: "/bin/sh".into(),
            args: vec!["-c".into(), script.into()],
            cwd: None,
            env: Vec::new(),
            terminal: Terminal::default(),
            events: Vec::new(),
            timeout: Duration::from_secs(5),
            idle_timeout: Duration::from_secs(5),
            settle: Duration::from_millis(200),
            finalization: Duration::ZERO,
            observation_paths: vec![watch.clone()],
            limits: Limits::default(),
            sandbox: SandboxRequest::Off,
        };
        let cap = capture(spec, no_cancel()).unwrap();
        let fs = cap.filesystem.expect("filesystem snapshot");
        assert!(fs.effects.iter().any(|e| e.path.ends_with("created.txt") && e.change == "created"), "{:?}", fs.effects);
        assert!(fs.effects.iter().any(|e| e.path.ends_with("existing.txt") && e.change == "unchanged"));
    }

    #[test]
    fn snapshot_records_hashes_not_contents() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("a.txt"), b"secret bytes").unwrap();
        let (_roots, states, _t) = snapshot(&[dir.path().to_path_buf()], &Limits::default(), &no_cancel());
        let file = states.iter().find(|f| f.path.ends_with("a.txt")).unwrap();
        assert_eq!(file.kind, "file");
        assert_eq!(file.size, 12);
        assert_eq!(file.sha256.as_deref(), Some(sha256_hex(b"secret bytes").as_str()));
    }
}
