//! Owned processes: the only way Craft Anything runs another program.
//!
//! ```no_run
//! use craft_anything_platform::process::Process;
//! use std::time::Duration;
//! let out = Process::new("git").args(["--version"]).timeout(Duration::from_secs(5)).run_checked()?;
//! println!("{}", out.stdout_text());
//! # Ok::<(), craft_anything_evidence::ToolError>(())
//! ```
//!
//! Guarantees:
//! - stdin is closed, fed from bytes we own, or a pipe the caller writes to; never inherited;
//! - a wall-clock deadline always applies (default 2 minutes) plus an optional idle deadline
//!   (no output for that long);
//! - stdout and stderr are drained on their own threads and capped, so pipes never fill;
//! - on timeout, cancel or drop the whole process group (Unix) or Job Object (Windows) is killed;
//! - a missing program, a non-zero exit (with [`Process::run_checked`]) or a timeout comes back as a
//!   [`ToolError`] with a plain-English remediation.
//!
//! Never call [`Process::run`] on a UI thread: it blocks until the child finishes or a deadline hits.
//! Use [`Process::spawn`] and poll [`RunningProcess::try_result`] instead.

use crate::sync::Mutex;
use craft_anything_evidence::{ErrorCode, ToolError};
use process_wrap::std::{ChildWrapper, CommandWrap};
use std::ffi::{OsStr, OsString};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::{ChildStdin, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{Receiver, RecvTimeoutError, TryRecvError};
use std::sync::{Arc, PoisonError};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

/// Returns true when the caller wants the run stopped.
pub type Cancel = Arc<dyn Fn() -> bool + Send + Sync>;
/// Receives each complete output line (without the line ending), lossily decoded as UTF-8.
pub type LineSink = Arc<dyn Fn(&str) + Send + Sync>;

/// What the child's stdin is connected to.
#[derive(Debug, Clone, Default)]
pub enum StdinMode {
    /// Closed: a child that tries to read gets end-of-file immediately and never waits at a prompt.
    #[default]
    Closed,
    /// These bytes are written, then the pipe is closed.
    Bytes(Vec<u8>),
    /// A pipe the caller writes to via [`RunningProcess::take_stdin`] (long-lived children).
    Piped,
}

/// Default wall-clock deadline.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);
/// Default stdout cap.
pub const DEFAULT_STDOUT_CAP: usize = 16 * 1024 * 1024;
/// Default stderr cap.
pub const DEFAULT_STDERR_CAP: usize = 1024 * 1024;
/// How long to wait for the output threads after the child exits (an escaped grandchild may hold
/// the pipe open; we stop waiting rather than hang).
const DRAIN_GRACE: Duration = Duration::from_secs(2);
/// Longest partial line kept before it is delivered anyway.
const MAX_LINE: usize = 1024 * 1024;

/// A program to run, built fluently.
#[derive(Clone)]
pub struct Process {
    program: OsString,
    args: Vec<OsString>,
    env: Vec<(OsString, Option<OsString>)>,
    env_clear: bool,
    cwd: Option<PathBuf>,
    stdin: StdinMode,
    wall: Duration,
    idle: Option<Duration>,
    stdout_cap: usize,
    stderr_cap: usize,
    cancel: Option<Cancel>,
    on_stdout: Option<LineSink>,
    on_stderr: Option<LineSink>,
    label: Option<String>,
    remediation: Option<String>,
    hands_off: bool,
}

impl std::fmt::Debug for Process {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Args may contain prompts; env may contain secrets. Show the program only.
        f.debug_struct("Process").field("program", &self.program).field("args", &self.args.len()).field("timeout", &self.wall).finish()
    }
}

/// What a finished run produced.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Output {
    /// Exit code, when the child exited normally.
    pub code: Option<i32>,
    pub success: bool,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub stdout_truncated: bool,
    pub stderr_truncated: bool,
    pub duration: Duration,
}

impl Output {
    pub fn stdout_text(&self) -> String {
        String::from_utf8_lossy(&self.stdout).into_owned()
    }

    pub fn stderr_text(&self) -> String {
        String::from_utf8_lossy(&self.stderr).into_owned()
    }
}

impl Process {
    pub fn new(program: impl AsRef<OsStr>) -> Self {
        Process {
            program: program.as_ref().to_owned(),
            args: Vec::new(),
            env: Vec::new(),
            env_clear: false,
            cwd: None,
            stdin: StdinMode::Closed,
            wall: DEFAULT_TIMEOUT,
            idle: None,
            stdout_cap: DEFAULT_STDOUT_CAP,
            stderr_cap: DEFAULT_STDERR_CAP,
            cancel: None,
            on_stdout: None,
            on_stderr: None,
            label: None,
            remediation: None,
            hands_off: false,
        }
    }

    pub fn arg(mut self, a: impl AsRef<OsStr>) -> Self {
        self.args.push(a.as_ref().to_owned());
        self
    }

    pub fn args<I, S>(mut self, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        self.args.extend(args.into_iter().map(|a| a.as_ref().to_owned()));
        self
    }

    pub fn env(mut self, k: impl AsRef<OsStr>, v: impl AsRef<OsStr>) -> Self {
        self.env.push((k.as_ref().to_owned(), Some(v.as_ref().to_owned())));
        self
    }

    pub fn env_remove(mut self, k: impl AsRef<OsStr>) -> Self {
        self.env.push((k.as_ref().to_owned(), None));
        self
    }

    /// Start from an empty environment (then add what the child needs with [`Process::env`]).
    pub fn env_clear(mut self) -> Self {
        self.env_clear = true;
        self
    }

    pub fn cwd(mut self, dir: impl Into<PathBuf>) -> Self {
        self.cwd = Some(dir.into());
        self
    }

    pub fn stdin(mut self, mode: StdinMode) -> Self {
        self.stdin = mode;
        self
    }

    pub fn stdin_bytes(self, bytes: impl Into<Vec<u8>>) -> Self {
        self.stdin(StdinMode::Bytes(bytes.into()))
    }

    /// Wall-clock deadline for the whole run.
    pub fn timeout(mut self, d: Duration) -> Self {
        self.wall = d;
        self
    }

    /// The program starts the real work in another process and exits (browsers do this on
    /// Windows). Its exiting cleanly doesn't end the run: the group lives on until kill, cancel,
    /// drop or the deadline, then all of it is stopped. A failed exit still ends the run at once.
    pub fn hands_off(mut self) -> Self {
        self.hands_off = true;
        self
    }

    /// Kill the child when it prints nothing for this long.
    pub fn idle_timeout(mut self, d: Duration) -> Self {
        self.idle = Some(d);
        self
    }

    pub fn stdout_cap(mut self, bytes: usize) -> Self {
        self.stdout_cap = bytes;
        self
    }

    pub fn stderr_cap(mut self, bytes: usize) -> Self {
        self.stderr_cap = bytes;
        self
    }

    /// Stop (and kill the process group) as soon as `f` returns true.
    pub fn cancel_when(mut self, f: impl Fn() -> bool + Send + Sync + 'static) -> Self {
        self.cancel = Some(Arc::new(f));
        self
    }

    pub fn cancel(mut self, c: Cancel) -> Self {
        self.cancel = Some(c);
        self
    }

    /// Stream stdout line by line (the output is still captured, up to the cap).
    pub fn on_stdout_line(mut self, f: impl Fn(&str) + Send + Sync + 'static) -> Self {
        self.on_stdout = Some(Arc::new(f));
        self
    }

    pub fn on_stderr_line(mut self, f: impl Fn(&str) + Send + Sync + 'static) -> Self {
        self.on_stderr = Some(Arc::new(f));
        self
    }

    /// Display name for error messages (defaults to the program's file name).
    pub fn label(mut self, l: impl Into<String>) -> Self {
        self.label = Some(l.into());
        self
    }

    /// What to tell the user when the program is missing.
    pub fn remediation(mut self, r: impl Into<String>) -> Self {
        self.remediation = Some(r.into());
        self
    }

    fn display(&self) -> String {
        self.label.clone().unwrap_or_else(|| {
            std::path::Path::new(&self.program)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| self.program.to_string_lossy().into_owned())
        })
    }

    /// Run to completion (blocking this thread). A non-zero exit is returned as `Ok` with
    /// `success == false`; use [`Process::run_checked`] to turn it into an error.
    pub fn run(self) -> Result<Output, ToolError> {
        let running = self.spawn()?;
        running.wait()
    }

    /// Run to completion; a non-zero exit becomes an `program_failed` error with the stderr tail.
    pub fn run_checked(self) -> Result<Output, ToolError> {
        let name = self.display();
        let command = printable_command(&self.program, &self.args);
        let out = self.run()?;
        if out.success { Ok(out) } else { Err(nonzero_error_with(&name, &out, Some(&command))) }
    }

    /// Start the child and supervise it on a background thread.
    pub fn spawn(self) -> Result<RunningProcess, ToolError> {
        let name = self.display();
        let (program, lead) = crate::which::launch_target(&self.program);
        let mut wrap = CommandWrap::with_new(&program, |cmd| {
            cmd.args(&lead).args(&self.args);
            if self.env_clear {
                cmd.env_clear();
            } else {
                use_search_path(cmd);
            }
            for (k, v) in &self.env {
                match v {
                    Some(v) => cmd.env(k, v),
                    None => cmd.env_remove(k),
                };
            }
            if let Some(dir) = &self.cwd {
                cmd.current_dir(dir);
            }
            cmd.stdin(match self.stdin {
                StdinMode::Closed => Stdio::null(),
                StdinMode::Bytes(_) | StdinMode::Piped => Stdio::piped(),
            });
            cmd.stdout(Stdio::piped());
            cmd.stderr(Stdio::piped());
        });
        #[cfg(unix)]
        wrap.wrap(process_wrap::std::ProcessGroup::leader());
        // A console program started from the windowed app would open a console window; its
        // output is piped here, so it never needs one.
        #[cfg(windows)]
        wrap.wrap(process_wrap::std::JobObject).wrap(process_wrap::std::CreationFlags(windows::Win32::System::Threading::CREATE_NO_WINDOW));
        let mut child = wrap.spawn().map_err(|e| spawn_error(&name, &self.program, e, self.remediation.as_deref()))?;
        let pid = child.id();
        let start = Instant::now();
        let activity = Arc::new(AtomicU64::new(0));

        let mut stdin_pipe = child.stdin().take();
        let mut user_stdin = None;
        match &self.stdin {
            StdinMode::Bytes(bytes) => {
                if let Some(mut pipe) = stdin_pipe.take() {
                    let bytes = bytes.clone();
                    let _ = std::thread::Builder::new().name("proc-stdin".into()).spawn(move || {
                        let _ = pipe.write_all(&bytes);
                        let _ = pipe.flush();
                        // dropping closes the pipe
                    });
                }
            }
            StdinMode::Piped => user_stdin = stdin_pipe.take(),
            StdinMode::Closed => {}
        }

        let out_buf = Arc::new(Mutex::new(Capped::new(self.stdout_cap)));
        let err_buf = Arc::new(Mutex::new(Capped::new(self.stderr_cap)));
        let mut readers = Vec::new();
        if let Some(r) = child.stdout().take() {
            readers.push(spawn_reader(r, out_buf.clone(), self.on_stdout.clone(), activity.clone(), start));
        }
        if let Some(r) = child.stderr().take() {
            readers.push(spawn_reader(r, err_buf.clone(), self.on_stderr.clone(), activity.clone(), start));
        }

        let kill = Arc::new(AtomicBool::new(false));
        let (tx, rx) = std::sync::mpsc::channel();
        let sup = Supervisor {
            child,
            name: name.clone(),
            start,
            wall: self.wall,
            idle: self.idle,
            hands_off: self.hands_off,
            cancel: self.cancel.clone(),
            kill: kill.clone(),
            activity,
            readers,
            out_buf,
            err_buf,
        };
        let spawned = std::thread::Builder::new().name(format!("proc-{name}")).spawn(move || {
            let r = sup.run();
            let _ = tx.send(r);
        });
        if let Err(e) = spawned {
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("Could not start a thread to watch {name}: {e}")));
        }
        Ok(RunningProcess { pid, name, stdin: user_stdin, kill, rx, result: None, hands_off: self.hands_off })
    }
}

/// The child gets [`search_path`](crate::which::search_path), which is also where a bare program
/// name is looked up on Unix, so an app opened from the Dock starts what a shell would.
fn use_search_path(cmd: &mut std::process::Command) {
    if let Some(p) = crate::which::search_path() {
        cmd.env("PATH", p);
    }
}

fn spawn_error(name: &str, program: &OsStr, e: std::io::Error, remediation: Option<&str>) -> ToolError {
    match e.kind() {
        std::io::ErrorKind::NotFound => ToolError::new(ErrorCode::EngineMissing, format!("{name} isn't installed or isn't on your PATH."))
            .with_remediation(remediation.map(str::to_string).unwrap_or_else(|| format!("Install {name}, or set its full path in Settings.")))
            .with_details(serde_json::json!({"program": program.to_string_lossy(), "reason": "not_found"})),
        std::io::ErrorKind::PermissionDenied => ToolError::new(ErrorCode::NoPermission, format!("{name} could not be started: permission denied."))
            .with_remediation("Check that the file is executable and that you're allowed to run it."),
        _ => ToolError::new(ErrorCode::ProgramFailed, format!("{name} could not be started: {e}")),
    }
}

fn tail(bytes: &[u8], n: usize) -> String {
    let start = bytes.len().saturating_sub(n);
    String::from_utf8_lossy(bytes.get(start..).unwrap_or_default()).into_owned()
}

/// Longest argument shown whole in [`printable_command`]; longer ones are usually prompts or
/// generated data.
const MAX_SHOWN_ARG: usize = 200;
/// Lines of a failed program's output shown in its error.
const SHOWN_OUTPUT_LINES: usize = 15;
const SHOWN_OUTPUT_LINE_CHARS: usize = 300;

/// A command as a person could type it, for errors and logs. Values of secret-looking flags are
/// masked and very long arguments left out (each says what it replaced), so it's safe to show.
pub fn printable_command<S: AsRef<OsStr>>(program: &OsStr, args: &[S]) -> String {
    let mut words = vec![shell_word(&program.to_string_lossy())];
    let mut mask_next = false;
    for arg in args {
        let arg = arg.as_ref().to_string_lossy();
        let secret_flag = arg.starts_with('-') && is_secret_name(arg.split('=').next().unwrap_or_default());
        words.push(if mask_next {
            "<hidden>".to_string()
        } else if let (true, Some((flag, _))) = (secret_flag, arg.split_once('=')) {
            format!("{}=<hidden>", shell_word(flag))
        } else if arg.chars().count() > MAX_SHOWN_ARG {
            format!("<{} characters left out>", arg.chars().count())
        } else {
            shell_word(&arg)
        });
        mask_next = secret_flag && !arg.contains('=');
    }
    words.join(" ")
}

fn is_secret_name(flag: &str) -> bool {
    let flag = flag.to_ascii_lowercase();
    ["token", "secret", "password", "passwd", "api-key", "api_key", "apikey", "credential"].iter().any(|s| flag.contains(s))
}

fn shell_word(s: &str) -> String {
    if !s.is_empty() && s.chars().all(|c| c.is_ascii_alphanumeric() || "-_./=:@%+,\\".contains(c)) {
        return s.to_string();
    }
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// The last lines of what a program printed, each cut to a readable length.
pub fn output_excerpt(text: &str) -> String {
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    let from = lines.len().saturating_sub(SHOWN_OUTPUT_LINES);
    lines
        .get(from..)
        .unwrap_or_default()
        .iter()
        .map(|l| {
            if l.chars().count() > SHOWN_OUTPUT_LINE_CHARS {
                format!("{}…", l.chars().take(SHOWN_OUTPUT_LINE_CHARS).collect::<String>())
            } else {
                l.to_string()
            }
        })
        .collect::<Vec<_>>()
        .join("\n")
}

/// The line of a program's output that says what went wrong: the last one, or, when a crash ends
/// with a stack trace, the line above its frames (a trace can be longer than what's shown, and
/// Node.js prints its version after it).
fn headline(text: &str) -> String {
    let lines: Vec<&str> = text.lines().map(str::trim).filter(|l| !l.is_empty()).collect();
    let above_trace = lines.iter().rposition(|l| is_stack_frame(l)).and_then(|last| {
        let frames_start = lines.get(..=last).unwrap_or_default().iter().rposition(|l| !is_stack_frame(l))?;
        lines.get(frames_start)
    });
    above_trace.or(lines.last()).map(|l| l.to_string()).unwrap_or_default()
}

/// A stack frame: `at f (/app/chunk.js:96:6417)`, `at node:internal/main:28:49`,
/// `at com.x.Y.m(Y.java:12)`, or Java's `... 3 more`.
fn is_stack_frame(line: &str) -> bool {
    let at_line =
        line.starts_with("at ") && line.trim_end_matches(')').rsplit(':').next().is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit()));
    at_line || (line.starts_with("... ") && line.ends_with(" more"))
}

/// The error for a non-zero exit, with the last part of stderr (or stdout) for context.
pub fn nonzero_error(name: &str, out: &Output) -> ToolError {
    nonzero_error_with(name, out, None)
}

/// [`nonzero_error`], also saying what was run so the person can run it themselves.
pub fn nonzero_error_with(name: &str, out: &Output, command: Option<&str>) -> ToolError {
    let code = out.code.map(|c| c.to_string()).unwrap_or_else(|| "a signal".into());
    let stderr_tail = tail(&out.stderr, 2000);
    let context = if stderr_tail.trim().is_empty() { tail(&out.stdout, 2000) } else { stderr_tail };
    let first_line = headline(&String::from_utf8_lossy(if out.stderr.iter().all(u8::is_ascii_whitespace) { &out.stdout } else { &out.stderr }));
    let msg =
        if first_line.is_empty() { format!("{name} stopped with exit code {code}.") } else { format!("{name} stopped with exit code {code}: {first_line}") };
    let excerpt = output_excerpt(&context);
    let mut said = if excerpt.is_empty() { format!("{name} printed nothing.") } else { format!("What {name} printed last:\n{excerpt}") };
    if let Some(command) = command {
        said.push_str(&format!("\n\nTo try it yourself, run:\n{command}"));
    }
    ToolError::new(ErrorCode::ProgramFailed, msg)
        .with_remediation(said)
        .with_details(serde_json::json!({"exit_code": out.code, "output_tail": context, "command": command}))
}

/// A child being supervised on a background thread. Dropping it kills the child.
pub struct RunningProcess {
    pid: u32,
    name: String,
    stdin: Option<ChildStdin>,
    kill: Arc<AtomicBool>,
    rx: Receiver<Result<Output, ToolError>>,
    result: Option<Result<Output, ToolError>>,
    hands_off: bool,
}

impl std::fmt::Debug for RunningProcess {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RunningProcess").field("pid", &self.pid).field("name", &self.name).finish()
    }
}

impl RunningProcess {
    pub fn pid(&self) -> u32 {
        self.pid
    }

    /// The stdin pipe when spawned with [`StdinMode::Piped`]. Drop it to close stdin.
    pub fn take_stdin(&mut self) -> Option<ChildStdin> {
        self.stdin.take()
    }

    /// Ask the supervisor to kill the whole process group now. It happens on the supervisor's
    /// thread: when the caller may exit right after, use [`RunningProcess::kill_and_wait`].
    pub fn kill(&self) {
        self.kill.store(true, Ordering::SeqCst);
    }

    /// Kill the whole process group and wait (at most `d`) until the supervisor confirms it's gone.
    /// Returns whether it confirmed in time.
    pub fn kill_and_wait(&mut self, d: Duration) -> bool {
        self.kill();
        self.pull(Some(d));
        self.result.is_some()
    }

    fn pull(&mut self, block: Option<Duration>) {
        if self.result.is_some() {
            return;
        }
        let got = match block {
            None => match self.rx.try_recv() {
                Ok(r) => Some(r),
                Err(TryRecvError::Empty) => None,
                Err(TryRecvError::Disconnected) => Some(Err(ToolError::internal(format!("lost track of {}", self.name)))),
            },
            Some(d) => match self.rx.recv_timeout(d) {
                Ok(r) => Some(r),
                Err(RecvTimeoutError::Timeout) => None,
                Err(RecvTimeoutError::Disconnected) => Some(Err(ToolError::internal(format!("lost track of {}", self.name)))),
            },
        };
        self.result = got;
    }

    /// Non-blocking: the result once the child has finished.
    pub fn try_result(&mut self) -> Option<&Result<Output, ToolError>> {
        self.pull(None);
        self.result.as_ref()
    }

    pub fn is_finished(&mut self) -> bool {
        self.try_result().is_some()
    }

    /// Block until the child finishes (the wall deadline still applies).
    pub fn wait(mut self) -> Result<Output, ToolError> {
        self.stdin = None;
        loop {
            self.pull(Some(Duration::from_millis(200)));
            if let Some(r) = self.result.take() {
                return r;
            }
        }
    }

    /// Block for at most `d`; `None` if it is still running.
    pub fn wait_timeout(&mut self, d: Duration) -> Option<&Result<Output, ToolError>> {
        self.pull(Some(d));
        self.result.as_ref()
    }
}

impl Drop for RunningProcess {
    fn drop(&mut self) {
        self.kill.store(true, Ordering::SeqCst);
        // A handed-off group outlives its launcher, so nothing else would stop it if the caller
        // exits next (a CLI run ends right after the tool): wait until it's gone.
        if self.hands_off {
            self.pull(Some(Duration::from_secs(5)));
        }
    }
}

struct Capped {
    data: Vec<u8>,
    cap: usize,
    truncated: bool,
}

impl Capped {
    fn new(cap: usize) -> Self {
        Capped { data: Vec::new(), cap, truncated: false }
    }

    fn push(&mut self, bytes: &[u8]) {
        let room = self.cap.saturating_sub(self.data.len());
        if bytes.len() > room {
            self.truncated = true;
        }
        if let Some(part) = bytes.get(..room.min(bytes.len())) {
            self.data.extend_from_slice(part);
        }
    }
}

fn millis_since(start: Instant) -> u64 {
    u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn spawn_reader<R: Read + Send + 'static>(
    mut r: R,
    buf: Arc<Mutex<Capped>>,
    sink: Option<LineSink>,
    activity: Arc<AtomicU64>,
    start: Instant,
) -> Option<JoinHandle<()>> {
    std::thread::Builder::new()
        .name("proc-reader".into())
        .spawn(move || {
            let mut chunk = vec![0u8; 64 * 1024];
            let mut line: Vec<u8> = Vec::new();
            loop {
                let n = match r.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(n) => n,
                    Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                    Err(_) => break,
                };
                activity.store(millis_since(start), Ordering::Relaxed);
                let data = chunk.get(..n).unwrap_or_default();
                buf.lock().unwrap_or_else(PoisonError::into_inner).push(data);
                if let Some(sink) = &sink {
                    for &b in data {
                        if b == b'\n' {
                            emit_line(sink, &mut line);
                        } else {
                            line.push(b);
                            if line.len() >= MAX_LINE {
                                emit_line(sink, &mut line);
                            }
                        }
                    }
                }
            }
            if let Some(sink) = &sink
                && !line.is_empty()
            {
                emit_line(sink, &mut line);
            }
        })
        .ok()
}

fn emit_line(sink: &LineSink, line: &mut Vec<u8>) {
    if line.last() == Some(&b'\r') {
        line.pop();
    }
    let text = String::from_utf8_lossy(line);
    // A misbehaving sink must not take the reader thread (and the pipe drain) down with it.
    let _ = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| sink(&text)));
    line.clear();
}

struct Supervisor {
    child: Box<dyn ChildWrapper>,
    name: String,
    start: Instant,
    wall: Duration,
    idle: Option<Duration>,
    hands_off: bool,
    cancel: Option<Cancel>,
    kill: Arc<AtomicBool>,
    activity: Arc<AtomicU64>,
    readers: Vec<Option<JoinHandle<()>>>,
    out_buf: Arc<Mutex<Capped>>,
    err_buf: Arc<Mutex<Capped>>,
}

enum Stop {
    Exited(std::process::ExitStatus),
    Wall,
    Idle,
    Cancelled,
    WaitFailed(std::io::Error),
}

impl Supervisor {
    fn run(mut self) -> Result<Output, ToolError> {
        let stop = self.watch();
        if !matches!(stop, Stop::Exited(_)) {
            let _ = self.child.start_kill();
            let _ = self.child.kill();
        } else {
            // The leader exited; take any leftover group members with it so they can't hold the pipes.
            let _ = self.child.start_kill();
        }
        self.drain();
        let duration = self.start.elapsed();
        let (stdout, stdout_truncated) = take(&self.out_buf);
        let (stderr, stderr_truncated) = take(&self.err_buf);
        let partial = || serde_json::json!({"stdout_tail": tail(&stdout, 2000), "stderr_tail": tail(&stderr, 2000)});
        match stop {
            Stop::Exited(status) => Ok(Output { code: status.code(), success: status.success(), stdout, stderr, stdout_truncated, stderr_truncated, duration }),
            Stop::Wall => Err(ToolError::new(ErrorCode::TimedOut, format!("{} took longer than {} s and was stopped.", self.name, self.wall.as_secs()))
                .with_remediation("Try a smaller job, or raise the time limit in Settings.")
                .with_details(serde_json::json!({"deadline": "wall", "timeout_ms": self.wall.as_millis() as u64, "partial": partial()}))),
            Stop::Idle => {
                let secs = self.idle.map(|d| d.as_secs()).unwrap_or_default();
                Err(ToolError::new(ErrorCode::TimedOut, format!("{} printed nothing for {secs} s and was stopped.", self.name))
                    .with_remediation("It may be waiting for input or stuck; run it by hand to check.")
                    .with_details(serde_json::json!({"deadline": "idle", "idle_timeout_ms": self.idle.map(|d| d.as_millis() as u64), "partial": partial()})))
            }
            Stop::Cancelled => Err(ToolError::cancelled().with_details(serde_json::json!({"partial": partial()}))),
            Stop::WaitFailed(e) => Err(ToolError::new(ErrorCode::ProgramFailed, format!("Lost track of {}: {e}", self.name))),
        }
    }

    fn watch(&mut self) -> Stop {
        let mut tick = Duration::from_millis(2);
        // A launcher that handed off cleanly: the group keeps running until we're told to stop.
        let mut handed_off = None;
        loop {
            if handed_off.is_none() {
                match self.child.try_wait() {
                    Ok(Some(status)) if self.hands_off && status.success() => handed_off = Some(status),
                    Ok(Some(status)) => return Stop::Exited(status),
                    Ok(None) => {}
                    Err(e) => return Stop::WaitFailed(e),
                }
            }
            if self.kill.load(Ordering::SeqCst) || self.cancel.as_ref().is_some_and(|c| c()) {
                return handed_off.map_or(Stop::Cancelled, Stop::Exited);
            }
            let elapsed = self.start.elapsed();
            if elapsed >= self.wall {
                return Stop::Wall;
            }
            if let Some(idle) = self.idle {
                let last = Duration::from_millis(self.activity.load(Ordering::Relaxed));
                if elapsed.saturating_sub(last) >= idle {
                    return Stop::Idle;
                }
            }
            std::thread::sleep(tick);
            tick = (tick * 2).min(Duration::from_millis(25));
        }
    }

    fn drain(&mut self) {
        let deadline = Instant::now() + DRAIN_GRACE;
        for h in self.readers.drain(..).flatten() {
            while !h.is_finished() && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(5));
            }
            if h.is_finished() {
                let _ = h.join();
            } else {
                log::warn!("{}: output pipe still held open after exit; not waiting for it", self.name);
            }
        }
    }
}

fn take(buf: &Arc<Mutex<Capped>>) -> (Vec<u8>, bool) {
    let mut g = buf.lock().unwrap_or_else(PoisonError::into_inner);
    (std::mem::take(&mut g.data), g.truncated)
}

/// A program started in its own window that is meant to outlive us: a finished game, an
/// installer, an engine's editor. Fire-and-forget, by design without a deadline (the person
/// closes it), so it is *not* a [`Process`]: nothing is captured, nothing is killed.
///
/// What it still guarantees: stdin, stdout and stderr are the null device (nothing waits at a
/// prompt, no pipe can fill), the child is reaped on a background thread when it exits (no zombie
/// on Unix), and a missing program comes back as a [`ToolError`] with a remediation. It never
/// blocks: [`Launch::start`] returns as soon as the child exists. Only start one on the person's
/// click.
///
/// ```no_run
/// use craft_anything_platform::process::Launch;
/// Launch::new("/path/to/game").cwd("/path/to").hide_console().start()?;
/// # Ok::<(), craft_anything_evidence::ToolError>(())
/// ```
#[derive(Debug, Clone)]
pub struct Launch {
    program: OsString,
    args: Vec<OsString>,
    cwd: Option<PathBuf>,
    hide_console: bool,
    log: Option<PathBuf>,
    label: Option<String>,
    remediation: Option<String>,
}

impl Launch {
    pub fn new(program: impl AsRef<OsStr>) -> Self {
        Launch { program: program.as_ref().to_owned(), args: Vec::new(), cwd: None, hide_console: false, log: None, label: None, remediation: None }
    }

    pub fn arg(mut self, a: impl AsRef<OsStr>) -> Self {
        self.args.push(a.as_ref().to_owned());
        self
    }

    pub fn args<I, S>(mut self, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        self.args.extend(args.into_iter().map(|a| a.as_ref().to_owned()));
        self
    }

    pub fn cwd(mut self, dir: impl Into<PathBuf>) -> Self {
        self.cwd = Some(dir.into());
        self
    }

    /// Windows: no extra console window behind a console-subsystem program (a game built as a
    /// console app). No effect on GUI programs or other systems.
    pub fn hide_console(mut self) -> Self {
        self.hide_console = true;
        self
    }

    /// Write what the program prints (output and errors) to this file, replacing it. A file, not
    /// a pipe: the program keeps running after we exit, and writing to a pipe nobody reads would
    /// fail (or stop it).
    pub fn log_to(mut self, file: impl Into<PathBuf>) -> Self {
        self.log = Some(file.into());
        self
    }

    /// The name used in messages (defaults to the program's file name).
    pub fn label(mut self, l: impl Into<String>) -> Self {
        self.label = Some(l.into());
        self
    }

    /// What to tell the person when the program is missing.
    pub fn remediation(mut self, r: impl Into<String>) -> Self {
        self.remediation = Some(r.into());
        self
    }

    fn display(&self) -> String {
        self.label.clone().unwrap_or_else(|| {
            std::path::Path::new(&self.program)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_else(|| self.program.to_string_lossy().into_owned())
        })
    }

    /// Start the program and return at once; returns its process id.
    pub fn start(self) -> Result<u32, ToolError> {
        self.start_watched().map(|l| l.pid())
    }

    /// Start the program and return at once, with a handle that tells when it ends and can stop
    /// it. Dropping the handle leaves the program running.
    pub fn start_watched(self) -> Result<Launched, ToolError> {
        let name = self.display();
        let mut cmd = std::process::Command::new(&self.program);
        cmd.args(&self.args).stdin(Stdio::null());
        use_search_path(&mut cmd);
        match &self.log {
            Some(path) => {
                let out = std::fs::File::create(path).map_err(|e| ToolError::io(path.display(), e))?;
                let err = out.try_clone().map_err(|e| ToolError::io(path.display(), e))?;
                cmd.stdout(out).stderr(err);
            }
            None => {
                cmd.stdout(Stdio::null()).stderr(Stdio::null());
            }
        }
        if let Some(dir) = &self.cwd {
            cmd.current_dir(dir);
        }
        #[cfg(windows)]
        if self.hide_console {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let child = cmd.spawn().map_err(|e| spawn_error(&name, &self.program, e, self.remediation.as_deref()))?;
        let launched = Launched { pid: child.id(), started: Instant::now(), state: Arc::new(Mutex::new(LaunchState { child: Some(child), ended: None })) };
        // Reap it when it closes. If no thread can be made the child still runs (and `ended`
        // stays unknown); on Unix it stays a zombie until we exit, which is harmless.
        let watched = launched.clone();
        let _ = std::thread::Builder::new().name(format!("launched-{name}")).spawn(move || {
            while watched.poll().is_none() {
                std::thread::sleep(LAUNCH_POLL);
            }
            if let Some(Ended { code: Some(c), .. }) = watched.ended()
                && c != 0
            {
                log::info!("{name} closed with exit code {c}");
            }
        });
        Ok(launched)
    }
}

/// How often a launched program is checked for having ended.
const LAUNCH_POLL: Duration = Duration::from_millis(250);

/// A program started with [`Launch::start_watched`]. Clones share the same program.
#[derive(Debug, Clone)]
pub struct Launched {
    pid: u32,
    started: Instant,
    state: Arc<Mutex<LaunchState>>,
}

#[derive(Debug)]
struct LaunchState {
    child: Option<std::process::Child>,
    ended: Option<Ended>,
}

/// How a launched program ended.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Ended {
    /// Its exit code; none when it was stopped by a signal or couldn't be read.
    pub code: Option<i32>,
    /// How long it ran.
    pub after: Duration,
}

impl Launched {
    pub fn pid(&self) -> u32 {
        self.pid
    }

    /// How long ago it started.
    pub fn running_for(&self) -> Duration {
        self.started.elapsed()
    }

    /// How it ended, once it has (as last seen; the watcher looks every 250 ms).
    pub fn ended(&self) -> Option<Ended> {
        self.state.lock().unwrap_or_else(PoisonError::into_inner).ended
    }

    pub fn is_running(&self) -> bool {
        self.ended().is_none()
    }

    /// Look now whether it has ended.
    fn poll(&self) -> Option<Ended> {
        let mut st = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        if st.ended.is_none()
            && let Some(child) = st.child.as_mut()
        {
            let done = match child.try_wait() {
                Ok(Some(status)) => Some(status.code()),
                Ok(None) => None,
                // It can't be watched any more: say it ended rather than show it running forever.
                Err(_) => Some(None),
            };
            if let Some(code) = done {
                st.ended = Some(Ended { code, after: self.started.elapsed() });
                st.child = None;
            }
        }
        st.ended
    }

    /// Wait up to `d` for it to end; how it ended, if it did.
    pub fn wait_timeout(&self, d: Duration) -> Option<Ended> {
        let deadline = Instant::now() + d;
        loop {
            if let Some(e) = self.poll() {
                return Some(e);
            }
            let left = deadline.saturating_duration_since(Instant::now());
            if left.is_zero() {
                return None;
            }
            std::thread::sleep(left.min(Duration::from_millis(50)));
        }
    }

    /// Stop it (the program itself; what it started on its own may stay). Returns once it has
    /// ended, or false if it couldn't be stopped.
    pub fn stop(&self) -> bool {
        let mut st = self.state.lock().unwrap_or_else(PoisonError::into_inner);
        if st.ended.is_some() {
            return true;
        }
        let Some(child) = st.child.as_mut() else { return false };
        let _ = child.kill();
        match child.wait() {
            Ok(status) => {
                st.ended = Some(Ended { code: status.code(), after: self.started.elapsed() });
                st.child = None;
                true
            }
            Err(_) => false,
        }
    }
}

/// The system's "open this" program: Explorer on Windows, `open` on macOS, `xdg-open` elsewhere.
pub fn system_opener() -> &'static str {
    if cfg!(windows) {
        "explorer"
    } else if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    }
}

/// Start this program again, for a restart: the caller then closes itself.
pub fn start_another_copy() -> Result<u32, ToolError> {
    let exe = std::env::current_exe().map_err(|e| ToolError::new(ErrorCode::FileError, format!("Couldn't find this program to restart it: {e}")))?;
    Launch::new(exe).start()
}

/// Show a file or folder with the system's default handler (a folder opens in the file manager).
/// Fire-and-forget, like [`Launch`].
pub fn open_path(path: impl AsRef<std::path::Path>) -> Result<(), ToolError> {
    let opener = system_opener();
    let remediation =
        if opener == "xdg-open" { "Install xdg-utils (it provides xdg-open), or open the location by hand." } else { "Open the location by hand." };
    Launch::new(opener).arg(native_path(path.as_ref())).remediation(remediation).start().map(|_| ())
}

/// A path the way the system's own programs read it. On Windows, forward slashes become
/// backslashes and a `\\?\` prefix is dropped: Explorer reads `D:/a/b` (or `\\?\D:\a\b`) as
/// nothing and opens Documents instead. Elsewhere the path is unchanged.
pub fn native_path(path: &std::path::Path) -> std::ffi::OsString {
    if cfg!(windows) { windows_form(&path.to_string_lossy()).into() } else { path.as_os_str().to_owned() }
}

fn windows_form(p: &str) -> String {
    let p = p.replace('/', "\\");
    if let Some(unc) = p.strip_prefix(r"\\?\UNC\") {
        format!(r"\\{unc}")
    } else if let Some(rest) = p.strip_prefix(r"\\?\") {
        rest.to_string()
    } else {
        p
    }
}

#[cfg(test)]
mod launch_tests {
    use super::*;

    #[cfg(windows)]
    #[test]
    #[ignore = "stand-in invoked by launch_does_not_hold_callers_output_pipes"]
    fn pipe_launcher_stand_in() {
        if std::env::var_os("PIPE_TEST_DIR").is_none() {
            return;
        }
        let exe = std::env::current_exe().unwrap();
        let launch = Launch::new(exe).args(["--ignored", "--exact", "process::launch_tests::pipe_sleeper_stand_in"]).hide_console();
        let launch = if std::env::var_os("PIPE_TEST_LOG").is_some() { launch.log_to("run.log") } else { launch };
        launch.start_watched().unwrap();
    }

    #[cfg(windows)]
    #[test]
    #[ignore = "stand-in invoked by pipe_launcher_stand_in"]
    fn pipe_sleeper_stand_in() {
        if std::env::var_os("PIPE_TEST_DIR").is_none() {
            return;
        }
        std::fs::write("started", b"ready").unwrap();
        std::thread::sleep(Duration::from_secs(6));
        std::fs::write("finished", b"done").unwrap();
    }

    // Documents a known gap (#207): a started program inherits the caller's output pipes, so the
    // caller's command doesn't return until the program exits. Run it with `--ignored` to see it fail.
    #[cfg(windows)]
    #[test]
    #[ignore = "known gap, see #207: started programs inherit the caller's output pipes"]
    fn launch_does_not_hold_callers_output_pipes() {
        use std::os::windows::process::CommandExt;

        let mut held_open = false;
        for log_to_file in [false, true] {
            let dir = tempfile::tempdir().unwrap();
            // This process is the CLI stand-in: its real standard handles are pipes.
            let mut cmd = std::process::Command::new(std::env::current_exe().unwrap());
            cmd.args(["--ignored", "--exact", "process::launch_tests::pipe_launcher_stand_in"])
                .current_dir(dir.path())
                .env("PIPE_TEST_DIR", dir.path())
                .env_remove("PIPE_TEST_LOG")
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .creation_flags(0x0800_0000);
            if log_to_file {
                cmd.env("PIPE_TEST_LOG", "1");
            }
            let started = Instant::now();
            let mut launcher = cmd.spawn().unwrap();
            let stdout = launcher.stdout.take().unwrap();
            let stderr = launcher.stderr.take().unwrap();
            let mut receivers = Vec::new();
            for (name, mut pipe) in [("stdout", Box::new(stdout) as Box<dyn Read + Send>), ("stderr", Box::new(stderr) as Box<dyn Read + Send>)] {
                let (tx, rx) = std::sync::mpsc::channel();
                receivers.push((name, rx));
                std::thread::spawn(move || {
                    let mut bytes = Vec::new();
                    pipe.read_to_end(&mut bytes).unwrap();
                    let _ = tx.send(started.elapsed());
                });
            }
            let status = launcher.wait().unwrap();
            let launcher_after = started.elapsed();
            println!("log_to_file={log_to_file}: launcher returned after {launcher_after:?}");
            let eof: Vec<_> = receivers.iter().map(|(name, rx)| (*name, rx.recv_timeout(Duration::from_secs(3)))).collect();
            let child_still_running = !dir.path().join("finished").exists();
            // Let the stand-in finish even on assertion failure; no detached test is left behind.
            let deadline = Instant::now() + Duration::from_secs(15);
            while !dir.path().join("finished").exists() && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(25));
            }
            assert!(status.success(), "launcher failed: {status}");
            assert!(launcher_after < Duration::from_secs(3), "launcher itself did not return promptly");
            assert!(dir.path().join("started").exists(), "stand-in never started");
            assert!(dir.path().join("finished").exists(), "stand-in did not finish");
            for (name, result) in eof {
                match result {
                    Ok(elapsed) => {
                        println!("log_to_file={log_to_file}: {name} EOF after {elapsed:?}");
                        held_open |= elapsed >= Duration::from_secs(3);
                    }
                    Err(error) => {
                        println!("log_to_file={log_to_file}: {name} pipe held open after launcher returned: {error:?}");
                        held_open = true;
                    }
                }
            }
            held_open |= !child_still_running;
        }
        assert!(!held_open, "caller pipe held open after launcher returned");
    }

    #[test]
    fn a_missing_program_is_a_tool_error_with_remediation() {
        let e = Launch::new("craft-anything-no-such-program-xyz").remediation("Install it.").start().unwrap_err();
        assert_eq!(e.code, ErrorCode::EngineMissing);
        assert_eq!(e.remediation.as_deref(), Some("Install it."));
        assert!(e.message.contains("craft-anything-no-such-program-xyz"), "{}", e.message);
    }

    #[test]
    fn a_short_program_starts_and_returns_at_once() {
        let l = if cfg!(windows) { Launch::new("cmd").args(["/C", "exit 3"]).hide_console() } else { Launch::new("sh").args(["-c", "exit 3"]) };
        let start = Instant::now();
        assert!(l.cwd(std::env::temp_dir()).label("test").start().is_ok());
        assert!(start.elapsed() < Duration::from_secs(5));
    }

    fn shell(script: &str) -> Launch {
        if cfg!(windows) { Launch::new("cmd").args(["/C", script]).hide_console() } else { Launch::new("sh").args(["-c", script]) }
    }

    #[test]
    fn a_watched_program_says_how_it_ended_and_what_it_printed() {
        let dir = tempfile::tempdir().unwrap();
        let log = dir.path().join("run.log");
        let l = shell("echo out-line && echo err-line 1>&2 && exit 3").cwd(dir.path()).log_to(&log).start_watched().unwrap();
        let ended = l.wait_timeout(Duration::from_secs(20)).expect("it ended");
        assert_eq!(ended.code, Some(3));
        assert!(!l.is_running());
        let text = std::fs::read_to_string(&log).unwrap();
        assert!(text.contains("out-line") && text.contains("err-line"), "{text}");
    }

    #[test]
    fn a_watched_program_can_be_stopped() {
        let script = if cfg!(windows) { "ping -n 30 127.0.0.1 > NUL" } else { "sleep 30" };
        let l = shell(script).start_watched().unwrap();
        assert!(l.wait_timeout(Duration::from_millis(300)).is_none(), "it should still be running");
        assert!(l.is_running());
        assert!(l.stop());
        assert!(!l.is_running());
        assert!(l.ended().unwrap().after < Duration::from_secs(20));
    }

    fn exits_with(code: u8) -> Process {
        let code = format!("exit {code}");
        if cfg!(windows) { Process::new("cmd").args(["/C", &code]) } else { Process::new("sh").args(["-c", &code]) }
    }

    #[test]
    fn a_launcher_that_hands_off_keeps_its_group_until_stopped() {
        // Plain: a clean exit ends the run.
        assert!(exits_with(0).run().unwrap().success);
        // Handing off: the launcher's clean exit doesn't, so the browser it started lives on.
        let mut p = exits_with(0).hands_off().spawn().unwrap();
        assert!(p.wait_timeout(Duration::from_millis(500)).is_none(), "a clean hand-off ended the run");
        assert!(p.kill_and_wait(Duration::from_secs(5)));
        assert!(p.wait().unwrap().success);
        // A launcher that fails still ends the run at once.
        let mut p = exits_with(3).hands_off().spawn().unwrap();
        let out = p.wait_timeout(Duration::from_secs(5)).unwrap().as_ref().unwrap();
        assert_eq!(out.code, Some(3));
    }

    #[test]
    fn paths_for_explorer_use_backslashes_and_no_verbatim_prefix() {
        // Project folders are kept as `D:/Projects/Craft Anything\name`; Explorer opened
        // Documents for those instead of the folder.
        assert_eq!(windows_form(r"D:/Projects/Craft Anything\notepad"), r"D:\Projects\Craft Anything\notepad");
        assert_eq!(windows_form(r"\\?\D:\Projects\x"), r"D:\Projects\x");
        assert_eq!(windows_form(r"\\?\UNC\server\share\x"), r"\\server\share\x");
        assert_eq!(windows_form(r"\\server/share"), r"\\server\share");
        assert_eq!(windows_form(r"C:\Already\fine"), r"C:\Already\fine");
    }

    #[test]
    fn the_opener_matches_the_system() {
        let o = system_opener();
        if cfg!(windows) {
            assert_eq!(o, "explorer");
        } else if cfg!(target_os = "macos") {
            assert_eq!(o, "open");
        } else {
            assert_eq!(o, "xdg-open");
        }
    }
}

#[cfg(test)]
mod error_tests {
    use super::*;

    #[test]
    fn a_crash_is_named_by_its_error_not_its_last_stack_frame() {
        let bun = "error: No provider is set up\n      at loadConfig (/$bunfs/root/chunk-qqmzrn42.js:12:40)\n      at <anonymous> (/$bunfs/root/chunk-qqmzrn42.js:96:6417)\n";
        assert_eq!(headline(bun), "error: No provider is set up");
        let mut node = String::from("/app/cli.js:10\n    throw new Error(\"x\");\n    ^\n\nError: Not signed in\n");
        for i in 0..100 {
            node.push_str(&format!("    at step{i} (/app/cli.js:{i}:1)\n"));
        }
        node.push_str("    at node:internal/main/run_main_module:28:49\n\nNode.js v20.11.0\n");
        assert_eq!(headline(&node), "Error: Not signed in", "found above a trace longer than the excerpt, footer skipped");
        let java = "Exception in thread \"main\" java.lang.IllegalStateException: outer\n\tat a.B.c(B.java:3)\nCaused by: java.io.IOException: disk full\n\tat a.B.d(B.java:9)\n\t... 3 more\n";
        assert_eq!(headline(java), "Caused by: java.io.IOException: disk full");
        // No trace: the last line, even one that starts with "at".
        assert_eq!(headline("warming up\nat least one file is needed\n\n"), "at least one file is needed");
        assert_eq!(headline("  \n"), "");
        let out = Output {
            code: Some(1),
            success: false,
            stdout: Vec::new(),
            stderr: bun.into(),
            stdout_truncated: false,
            stderr_truncated: false,
            duration: Duration::ZERO,
        };
        assert_eq!(nonzero_error("OpenCode", &out).message, "OpenCode stopped with exit code 1: error: No provider is set up");
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;

    #[test]
    fn captures_output_and_exit_code() {
        let out = Process::new("sh").args(["-c", "echo hello; echo oops >&2; exit 3"]).run().unwrap();
        assert_eq!(out.code, Some(3));
        assert!(!out.success);
        assert_eq!(out.stdout_text(), "hello\n");
        assert_eq!(out.stderr_text(), "oops\n");
        let err = Process::new("sh").args(["-c", "echo bad thing >&2; exit 1"]).run_checked().unwrap_err();
        let help = err.remediation.clone().unwrap();
        assert!(help.contains("bad thing") && help.contains("sh -c 'echo bad thing >&2; exit 1'"), "says what it printed and what ran: {help}");
        assert!(!help.contains("by hand"), "{help}");
        assert_eq!(err.code, ErrorCode::ProgramFailed);
        assert!(err.message.contains("bad thing"), "{}", err.message);
    }

    #[test]
    fn missing_program_is_a_clear_error() {
        let err = Process::new("no-such-program-craft-xyz").run().unwrap_err();
        assert_eq!(err.code, ErrorCode::EngineMissing);
        assert!(err.remediation.is_some());
    }

    #[test]
    fn stdin_is_closed_so_readers_get_eof() {
        // `cat` would wait forever on an inherited terminal; with stdin closed it exits at once.
        let out = Process::new("cat").timeout(Duration::from_secs(5)).run().unwrap();
        assert!(out.success);
        assert!(out.stdout.is_empty());
    }

    #[test]
    fn stdin_bytes_are_fed_then_closed() {
        let out = Process::new("cat").stdin_bytes(b"abc\ndef".to_vec()).run().unwrap();
        assert_eq!(out.stdout_text(), "abc\ndef");
    }

    #[test]
    fn wall_timeout_kills_the_whole_group() {
        let dir = tempfile::tempdir().unwrap();
        let marker = dir.path().join("survived");
        let script = format!("(sleep 1; touch {}) & sleep 30", marker.display());
        let t = Instant::now();
        let err = Process::new("sh").args(["-c", &script]).timeout(Duration::from_millis(300)).run().unwrap_err();
        assert_eq!(err.code, ErrorCode::TimedOut);
        assert!(t.elapsed() < Duration::from_secs(5));
        std::thread::sleep(Duration::from_millis(1300));
        assert!(!marker.exists(), "background grandchild should have been killed with the group");
    }

    #[test]
    fn idle_timeout_fires_when_silent() {
        let err = Process::new("sh").args(["-c", "echo start; sleep 30"]).idle_timeout(Duration::from_millis(300)).run().unwrap_err();
        assert_eq!(err.code, ErrorCode::TimedOut);
        assert_eq!(err.details.as_ref().unwrap()["deadline"], "idle");
        assert!(err.details.unwrap()["partial"]["stdout_tail"].as_str().unwrap().contains("start"));
    }

    #[test]
    fn output_is_capped_and_pipes_never_fill() {
        // 4 MiB of output into a 1 KiB cap must neither block nor grow memory.
        let out = Process::new("sh").args(["-c", "head -c 4194304 /dev/zero"]).stdout_cap(1024).run().unwrap();
        assert!(out.success);
        assert_eq!(out.stdout.len(), 1024);
        assert!(out.stdout_truncated);
    }

    #[test]
    fn cancel_stops_the_run() {
        let flag = Arc::new(AtomicBool::new(false));
        let f2 = flag.clone();
        let h = std::thread::spawn(move || Process::new("sleep").arg("30").cancel_when(move || f2.load(Ordering::SeqCst)).run());
        std::thread::sleep(Duration::from_millis(100));
        flag.store(true, Ordering::SeqCst);
        let err = h.join().unwrap().unwrap_err();
        assert_eq!(err.code, ErrorCode::Cancelled);
    }

    #[test]
    fn streams_lines_and_supports_piped_stdin() {
        let seen = Arc::new(Mutex::new(Vec::<String>::new()));
        let s2 = seen.clone();
        let mut p = Process::new("cat").stdin(StdinMode::Piped).on_stdout_line(move |l| s2.lock().unwrap().push(l.to_string())).spawn().unwrap();
        let mut stdin = p.take_stdin().unwrap();
        stdin.write_all(b"one\r\ntwo\n").unwrap();
        drop(stdin);
        let out = p.wait().unwrap();
        assert!(out.success);
        assert_eq!(*seen.lock().unwrap(), vec!["one".to_string(), "two".to_string()]);
    }

    #[test]
    fn dropping_a_running_process_kills_it() {
        let count = Arc::new(AtomicUsize::new(0));
        let c2 = count.clone();
        let mut p = Process::new("sh")
            .args(["-c", "while true; do echo x; sleep 0.05; done"])
            .on_stdout_line(move |_| {
                c2.fetch_add(1, Ordering::SeqCst);
            })
            .spawn()
            .unwrap();
        assert!(p.wait_timeout(Duration::from_millis(300)).is_none());
        drop(p);
        std::thread::sleep(Duration::from_millis(300));
        let after = count.load(Ordering::SeqCst);
        std::thread::sleep(Duration::from_millis(300));
        assert_eq!(count.load(Ordering::SeqCst), after, "child kept printing after drop");
    }
}
