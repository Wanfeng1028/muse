//! A Rizin debug session: one owned `rizin -d` process (stdin piped, stderr folded into stdout so
//! messages stay in order, output drained on a thread, killed with its process group when closed
//! or dropped). Rizin has no machine interface, so each command is followed by `echo <marker>`
//! and its output is every line before the marker. The engine's rizin session tools keep sessions
//! by id and turn results into evidence.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::sync::Mutex;
use craft_anything_platform::{Process, RunningProcess, StdinMode};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::VecDeque;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::ChildStdin;
use std::sync::{Arc, PoisonError};
use std::time::{Duration, Instant};

/// Unread lines kept per session; older ones are dropped.
const MAX_PENDING: usize = 200_000;
/// Text returned per command.
const MAX_TEXT: usize = 1 << 20;
/// How long Rizin gets to start the program and print its first lines.
const START_WAIT: Duration = Duration::from_secs(60);

/// Lines read from Rizin, waiting to be consumed.
#[derive(Default)]
struct Pending {
    lines: VecDeque<String>,
    dropped: u64,
}

/// What one command (or the output since the last one) produced.
#[derive(Debug, Default, Serialize)]
pub struct Collected {
    pub output: String,
    /// Lines Rizin marked as errors (`ERROR: …`), also left in `output`.
    pub errors: Vec<String>,
    /// More than 1 MiB of text arrived; the rest was dropped.
    pub truncated: bool,
}

impl Collected {
    fn append(&mut self, other: Collected) {
        for line in other.output.lines() {
            self.push(line);
        }
        self.truncated |= other.truncated;
    }

    fn push(&mut self, line: &str) {
        if self.output.len() + line.len() + 1 > MAX_TEXT {
            self.truncated = true;
            return;
        }
        self.output.push_str(line);
        self.output.push('\n');
        if let Some(e) = line.strip_prefix("ERROR: ")
            && self.errors.len() < 200
        {
            self.errors.push(e.to_string());
        }
    }
}

/// What the session debugs.
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Target {
    /// A program Rizin started (stopped before its first instruction).
    Program { path: PathBuf, args: Vec<String> },
    /// A running process Rizin attached to.
    Process { pid: u32 },
}

/// One running Rizin.
pub struct RizinSession {
    pub target: Target,
    pub rizin: PathBuf,
    proc: RunningProcess,
    stdin: Option<ChildStdin>,
    pending: Arc<Mutex<Pending>>,
    next_token: u64,
    /// The marker of a command that hadn't finished when its caller stopped waiting.
    busy: Option<String>,
    /// Output of a command that outlasted its wait, kept for [`RizinSession::take_output`].
    late: Collected,
    pub started: Instant,
}

/// The command line that starts Rizin's debugger on `target`.
pub fn start_args(target: &Target) -> Vec<String> {
    let mut a: Vec<String> = vec!["-N".into(), "-1".into(), "-T".into()];
    for set in ["scr.interactive=false", "scr.prompt=false", "scr.color=0", "scr.utf8=false", "scr.pager=", "scr.breaklines=false"] {
        a.extend(["-e".to_string(), set.to_string()]);
    }
    match target {
        Target::Program { path, args } => {
            // Arguments after the file go to the program.
            a.extend(["-d".into(), path.display().to_string()]);
            a.extend(args.iter().cloned());
        }
        Target::Process { pid } => a.extend(["-d".into(), pid.to_string()]),
    }
    a
}

/// Refuse a command line that would break the session: more than one line (which would run
/// outside the marker protocol) or visual mode, which waits for keys.
pub fn check_command(cmd: &str) -> Result<&str, ToolError> {
    let cmd = cmd.trim();
    if cmd.is_empty() {
        return Err(ToolError::invalid("command is empty"));
    }
    if cmd.contains(['\n', '\r', '\0']) {
        return Err(ToolError::invalid("send one command line at a time (no line breaks); chain commands with `;` instead"));
    }
    if cmd.starts_with('V') || cmd == "v" {
        return Err(ToolError::invalid("visual mode waits for keystrokes and isn't available here; use the plain commands"));
    }
    Ok(cmd)
}

impl RizinSession {
    /// Start Rizin's debugger on `target` and return once it has printed its start-up lines.
    pub fn start(rizin: &Path, target: Target, cancelled: &dyn Fn() -> bool) -> Result<(Self, Collected), ToolError> {
        let pending = Arc::new(Mutex::new(Pending::default()));
        let sink = pending.clone();
        let push = move |l: &str| {
            let mut p = sink.lock().unwrap_or_else(PoisonError::into_inner);
            if p.lines.len() >= MAX_PENDING {
                p.lines.pop_front();
                p.dropped += 1;
            }
            p.lines.push_back(l.trim_end_matches(['\r', '\n']).to_string());
        };
        let push_err = push.clone();
        let mut proc = Process::new(rizin)
            .args(start_args(&target))
            .stdin(StdinMode::Piped)
            // A debugging session can sit idle for a long time; closing it or the session end stops it.
            .timeout(Duration::from_secs(8 * 3600))
            .stdout_cap(1 << 20)
            .stderr_cap(1 << 20)
            .on_stdout_line(push)
            .on_stderr_line(push_err)
            .label("rizin")
            .remediation("Install Rizin and set its path in Settings → Engines.")
            .spawn()?;
        let stdin = proc.take_stdin().ok_or_else(|| ToolError::internal("Rizin started without a stdin pipe"))?;
        let mut s = RizinSession {
            target,
            rizin: rizin.to_path_buf(),
            proc,
            stdin: Some(stdin),
            pending,
            next_token: 0,
            busy: None,
            late: Collected::default(),
            started: Instant::now(),
        };
        let (c, timed_out) = s.run_marked(None, START_WAIT, cancelled)?;
        if s.proc.is_finished() {
            let why = c.errors.first().cloned().unwrap_or_else(|| c.output.trim().to_string());
            return Err(ToolError::new(ErrorCode::NotFound, format!("Rizin exited while starting the debugger: {why}"))
                .with_remediation("Check the program path or process id, and that this account may debug it."));
        }
        if timed_out {
            s.kill();
            return Err(ToolError::new(ErrorCode::TimedOut, "Rizin didn't finish starting the debugger in time"));
        }
        Ok((s, c))
    }

    /// Run one command line, as typed at Rizin's prompt, and wait up to `timeout` for it. The
    /// flag is true when it was still running at the deadline (or `cancelled` said so): it keeps
    /// running, and the next command waits for it first.
    pub fn command(&mut self, cmd: &str, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<(Collected, bool), ToolError> {
        let cmd = check_command(cmd)?.to_string();
        let deadline = Instant::now() + timeout;
        if self.busy.is_some() {
            // The earlier command's late output goes to the session's status, not to this command.
            let (earlier, timed_out) = self.wait_busy(deadline, cancelled)?;
            self.late.append(earlier);
            if timed_out {
                return Err(ToolError::new(ErrorCode::TimedOut, "Rizin is still running the previous command")
                    .with_remediation("Wait and try again, check native_rizin_session_show, or close the session."));
            }
        }
        self.run_marked(Some(&cmd), deadline.saturating_duration_since(Instant::now()), cancelled)
    }

    /// Send `cmd` (if any) and a marker, then collect lines until the marker.
    fn run_marked(&mut self, cmd: Option<&str>, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<(Collected, bool), ToolError> {
        self.next_token += 1;
        let marker = format!("__craft_anything_{}_{:x}__", self.next_token, self.started.elapsed().as_nanos());
        let stdin = self.stdin.as_mut().ok_or_else(|| ToolError::new(ErrorCode::NotFound, "this Rizin session has ended"))?;
        let mut text = String::new();
        if let Some(c) = cmd {
            text.push_str(c);
            text.push('\n');
        }
        text.push_str(&format!("echo {marker}\n"));
        stdin.write_all(text.as_bytes()).and_then(|_| stdin.flush()).map_err(|e| {
            ToolError::new(ErrorCode::NotFound, format!("could not talk to Rizin: {e}")).with_remediation("Close this session and start a new one.")
        })?;
        self.busy = Some(marker);
        self.wait_busy(Instant::now() + timeout, cancelled)
    }

    /// Collect lines until the pending marker (or the deadline, or Rizin exiting).
    fn wait_busy(&mut self, deadline: Instant, cancelled: &dyn Fn() -> bool) -> Result<(Collected, bool), ToolError> {
        let mut c = Collected::default();
        let Some(marker) = self.busy.clone() else { return Ok((c, false)) };
        loop {
            if self.drain(&mut c, Some(&marker)) {
                self.busy = None;
                return Ok((c, false));
            }
            if self.proc.is_finished() {
                // Whatever it printed before exiting.
                self.drain(&mut c, None);
                self.busy = None;
                self.stdin = None;
                return Ok((c, false));
            }
            if Instant::now() >= deadline || cancelled() {
                return Ok((c, true));
            }
            std::thread::sleep(Duration::from_millis(15));
        }
    }

    /// Move pending lines into `c`; with a marker, stop at it (leaving later lines queued) and
    /// say whether it was seen.
    fn drain(&mut self, c: &mut Collected, until: Option<&str>) -> bool {
        let mut p = self.pending.lock().unwrap_or_else(PoisonError::into_inner);
        while let Some(line) = p.lines.pop_front() {
            if until.is_some_and(|m| line.trim() == m) {
                return true;
            }
            c.push(&line);
        }
        false
    }

    /// Everything that arrived outside a command (late output of one that timed out, messages
    /// from the debugged program), and how many lines were dropped so far.
    pub fn take_output(&mut self) -> (Collected, u64) {
        let mut c = std::mem::take(&mut self.late);
        if self.busy.is_some() {
            if let Ok((more, _)) = self.wait_busy(Instant::now(), &|| false) {
                c.append(more);
            }
        } else {
            self.drain(&mut c, None);
        }
        let dropped = self.pending.lock().unwrap_or_else(PoisonError::into_inner).dropped;
        (c, dropped)
    }

    pub fn is_finished(&mut self) -> bool {
        self.proc.is_finished()
    }

    /// Stop Rizin and anything it started.
    pub fn kill(&self) {
        self.proc.kill();
    }

    /// Whether Rizin is alive, what it debugs, whether a command is still running, the uptime.
    pub fn status(&mut self) -> Value {
        let alive = !self.proc.is_finished();
        json!({
            "rizin": self.rizin,
            "rizin_pid": self.proc.pid(),
            "alive": alive,
            "target": self.target,
            "busy": alive && self.busy.is_some(),
            "uptime_seconds": self.started.elapsed().as_secs(),
        })
    }

    /// Ask Rizin to quit (killing a program it started), then stop it and anything left. True
    /// when it exited on its own.
    pub fn close(mut self) -> bool {
        let graceful = !self.proc.is_finished() && self.busy.is_none() && {
            if let Some(stdin) = self.stdin.as_mut() {
                let _ = stdin.write_all(b"q!!\n").and_then(|_| stdin.flush());
            }
            self.stdin = None;
            self.proc.wait_timeout(Duration::from_secs(3)).is_some()
        };
        self.proc.kill_and_wait(Duration::from_secs(3));
        graceful
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn start_line_and_command_checks() {
        let a = start_args(&Target::Program { path: PathBuf::from("/x/prog"), args: vec!["--fast".into(), "two words".into()] });
        assert_eq!(a.iter().filter(|x| *x == "-e").count(), 6);
        let tail: Vec<&str> = a.iter().map(String::as_str).skip_while(|x| *x != "-d").collect();
        assert_eq!(tail, ["-d", "/x/prog", "--fast", "two words"]);
        let p = start_args(&Target::Process { pid: 42 });
        assert_eq!(p.last().map(String::as_str), Some("42"));
        assert!(p.contains(&"-1".to_string()) && p.contains(&"-N".to_string()));

        assert_eq!(check_command("  dr rip "), Ok("dr rip"));
        assert!(check_command("db main; dc").is_ok());
        assert!(check_command("dc\nq").is_err());
        assert!(check_command("").is_err());
        assert!(check_command("V").is_err() && check_command("Vpp").is_err() && check_command("v").is_err());
    }

    #[test]
    fn errors_are_picked_out_and_text_is_capped() {
        let mut c = Collected::default();
        c.push("rip = 0x1");
        c.push("ERROR: No such register");
        assert_eq!(c.errors, ["No such register"]);
        assert_eq!(c.output, "rip = 0x1\nERROR: No such register\n");
        let big = "x".repeat(MAX_TEXT);
        c.push(&big);
        assert!(c.truncated && c.output.len() < MAX_TEXT);
    }
}
