//! A GDB session over the machine interface (GDB/MI): one owned `gdb` process (stdin piped,
//! output drained on threads, killed with its process group when closed or dropped), driven with
//! MI commands, `-interpreter-exec console` for any console command, while results come back as
//! structured records. The engine's GDB tools keep sessions by id and turn results into evidence.

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

/// Unread MI lines kept per session; older ones are dropped.
const MAX_PENDING: usize = 200_000;
/// Text returned per command.
const MAX_TEXT: usize = 1 << 20;

/// MI lines read from GDB's stdout, waiting to be consumed.
#[derive(Default)]
struct Pending {
    lines: VecDeque<String>,
    dropped: u64,
}

/// What one command (or the output since the last one) produced.
#[derive(Debug, Default, Serialize)]
pub struct Collected {
    pub console: String,
    pub log: String,
    pub target_output: String,
    pub events: Vec<Value>,
    /// The result class: done, running, error, exit.
    pub result: Option<String>,
    pub error: Option<String>,
    /// More than 1 MiB of text arrived; the rest was dropped.
    pub truncated: bool,
}

impl Collected {
    fn push(dst: &mut String, s: &str, truncated: &mut bool) {
        if dst.len() + s.len() > MAX_TEXT {
            *truncated = true;
        } else {
            dst.push_str(s);
        }
    }
}

/// One running GDB.
pub struct GdbSession {
    pub program: Option<PathBuf>,
    pub gdb: PathBuf,
    proc: RunningProcess,
    stdin: Option<ChildStdin>,
    pending: Arc<Mutex<Pending>>,
    next_token: u64,
    /// not_started, stopped, running, exited
    pub state: &'static str,
    pub last_stop: Option<Value>,
    pub started: Instant,
}

// ---------------------------------------------------------------------------------------------
// GDB/MI

/// Decode an MI C-string (`"text\n"`) into plain text.
fn unquote(s: &str) -> String {
    let inner = s.strip_prefix('"').and_then(|x| x.strip_suffix('"')).unwrap_or(s);
    let mut out = String::with_capacity(inner.len());
    let mut it = inner.chars().peekable();
    while let Some(c) = it.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match it.next() {
            Some('n') => out.push('\n'),
            Some('t') => out.push('\t'),
            Some('r') => out.push('\r'),
            Some('e') => out.push('\u{1b}'),
            Some(d @ '0'..='7') => {
                let mut v = d.to_digit(8).unwrap_or(0);
                for _ in 0..2 {
                    match it.peek().and_then(|c| c.to_digit(8)) {
                        Some(x) => {
                            v = v * 8 + x;
                            it.next();
                        }
                        None => break,
                    }
                }
                out.push(char::from_u32(v).unwrap_or('?'));
            }
            Some(other) => out.push(other),
            None => out.push('\\'),
        }
    }
    out
}

/// Quote a console command as an MI C-string.
fn quote(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
}

/// `key="value"` pairs at the top level of an MI record body (nested tuples kept as raw text).
fn fields(body: &str) -> serde_json::Map<String, Value> {
    let mut m = serde_json::Map::new();
    let b = body.as_bytes();
    let mut i = 0usize;
    while i < b.len() {
        let Some(eq) = body.get(i..).and_then(|r| r.find('=')).map(|e| i + e) else { break };
        let key = body.get(i..eq).unwrap_or("").trim_start_matches(',').to_string();
        let mut j = eq + 1;
        let start = j;
        let (mut depth, mut in_str, mut esc) = (0i32, false, false);
        while j < b.len() {
            let c = b.get(j).copied().unwrap_or(b',');
            if in_str {
                if esc {
                    esc = false;
                } else if c == b'\\' {
                    esc = true;
                } else if c == b'"' {
                    in_str = false;
                }
            } else {
                match c {
                    b'"' => in_str = true,
                    b'{' | b'[' => depth += 1,
                    b'}' | b']' => depth -= 1,
                    b',' if depth == 0 => break,
                    _ => {}
                }
            }
            j += 1;
        }
        let raw = body.get(start..j).unwrap_or("");
        let v = if raw.starts_with('"') { Value::String(unquote(raw)) } else { Value::String(raw.to_string()) };
        if !key.is_empty() {
            m.insert(key, v);
        }
        i = j + 1;
    }
    m
}

/// The token-prefixed result class of a line (`12^done,...` → (12, "done", body)).
fn result_record(line: &str) -> Option<(Option<u64>, &str, &str)> {
    let digits = line.bytes().take_while(u8::is_ascii_digit).count();
    let rest = line.get(digits..)?.strip_prefix('^')?;
    let token = line.get(..digits).and_then(|t| t.parse().ok());
    let (class, body) = rest.split_once(',').unwrap_or((rest, ""));
    Some((token, class, body))
}

/// Fold one MI line into `c`, updating the session's state.
fn absorb(line: &str, s: &mut GdbSession, c: &mut Collected) {
    let line = line.trim_end();
    if let Some((_, class, body)) = result_record(line) {
        c.result = Some(class.to_string());
        if class == "error" {
            c.error = fields(body).get("msg").and_then(Value::as_str).map(str::to_string);
        }
        return;
    }
    let Some(first) = line.chars().next() else { return };
    let rest = line.get(1..).unwrap_or("");
    match first {
        '~' => Collected::push(&mut c.console, &unquote(rest), &mut c.truncated),
        '&' => Collected::push(&mut c.log, &unquote(rest), &mut c.truncated),
        '@' => Collected::push(&mut c.target_output, &unquote(rest), &mut c.truncated),
        '*' | '=' => {
            let (class, body) = rest.split_once(',').unwrap_or((rest, ""));
            match class {
                "running" => s.state = "running",
                "stopped" => {
                    let f = Value::Object(fields(body));
                    s.state = if f.get("reason").and_then(Value::as_str).is_some_and(|r| r.starts_with("exited")) { "exited" } else { "stopped" };
                    s.last_stop = Some(f);
                }
                "thread-group-exited" => s.state = "exited",
                _ => {}
            }
            if c.events.len() < 1000 {
                c.events.push(json!({"kind": if first == '*' { "exec" } else { "notify" }, "class": class, "fields": fields(body)}));
            }
        }
        _ if line.starts_with("(gdb)") => {}
        _ => Collected::push(&mut c.target_output, &format!("{line}\n"), &mut c.truncated),
    }
}

/// Take every pending line; stop early (returning the rest to the queue) once `until` matches.
fn drain(s: &mut GdbSession, c: &mut Collected, until: &mut dyn FnMut(&str, &mut GdbSession) -> bool) -> bool {
    let lines: Vec<String> = {
        let mut p = s.pending.lock().unwrap_or_else(PoisonError::into_inner);
        p.lines.drain(..).collect()
    };
    let mut it = lines.into_iter();
    while let Some(l) = it.next() {
        absorb(&l, s, c);
        if until(&l, s) {
            let rest: Vec<String> = it.collect();
            let mut p = s.pending.lock().unwrap_or_else(PoisonError::into_inner);
            for (i, r) in rest.into_iter().enumerate() {
                p.lines.insert(i, r);
            }
            return true;
        }
    }
    false
}

/// Record the result class; `^running` means we keep waiting for a stop.
fn c_result(class: &str, sess: &mut GdbSession, waiting_for_stop: &mut bool) {
    match class {
        "running" => {
            sess.state = "running";
            *waiting_for_stop = true;
        }
        "exit" => sess.state = "exited",
        _ => {}
    }
}

impl GdbSession {
    /// Start GDB (machine interface, no init files, auto-loaded scripts and pagination off) with
    /// `program` loaded (not run), optionally a core file and the program's arguments.
    pub fn start(gdb: &Path, program: Option<&PathBuf>, core: Option<&PathBuf>, args: &[String]) -> Result<Self, ToolError> {
        let mut a: Vec<String> = vec!["-nx".into(), "-q".into(), "--interpreter=mi".into()];
        for set in ["set auto-load off", "set pagination off", "set confirm off", "set width 0", "set height 0", "set debuginfod enabled off"] {
            a.extend(["-iex".to_string(), set.to_string()]);
        }
        if let Some(c) = core {
            a.push(format!("--core={}", c.display()));
        }
        if let Some(p) = program {
            if args.is_empty() {
                a.push(p.display().to_string());
            } else {
                a.push("--args".into());
                a.push(p.display().to_string());
                a.extend(args.iter().cloned());
            }
        }
        let pending = Arc::new(Mutex::new(Pending::default()));
        let sink = pending.clone();
        let push = move |l: &str| {
            let mut p = sink.lock().unwrap_or_else(PoisonError::into_inner);
            if p.lines.len() >= MAX_PENDING {
                p.lines.pop_front();
                p.dropped += 1;
            }
            p.lines.push_back(l.to_string());
        };
        let push_err = push.clone();
        let mut proc = Process::new(gdb)
            .args(&a)
            .env("DEBUGINFOD_URLS", "")
            .stdin(StdinMode::Piped)
            // A debugging session can sit idle for a long time; closing it or the session end stops it.
            .timeout(Duration::from_secs(8 * 3600))
            .stdout_cap(1 << 20)
            .stderr_cap(1 << 20)
            .on_stdout_line(push)
            .on_stderr_line(move |l| push_err(&format!("&{}", quote(&format!("{l}\n")))))
            .label("gdb")
            .remediation("Install GDB and set its path in Settings → Engines.")
            .spawn()?;
        let stdin = proc.take_stdin().ok_or_else(|| ToolError::internal("GDB started without a stdin pipe"))?;
        Ok(GdbSession {
            program: program.cloned(),
            gdb: gdb.to_path_buf(),
            proc,
            stdin: Some(stdin),
            pending,
            next_token: 0,
            state: if core.is_some() { "stopped" } else { "not_started" },
            last_stop: None,
            started: Instant::now(),
        })
    }

    /// Send one MI command and wait for its result (and, after `^running`, for the program to
    /// stop). The flag is true when `timeout` passed or `cancelled` said so first.
    pub fn exec(&mut self, mi: &str, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<(Collected, bool), ToolError> {
        self.next_token += 1;
        let token = self.next_token;
        let stdin = self.stdin.as_mut().ok_or_else(|| ToolError::new(ErrorCode::NotFound, "this GDB session has ended"))?;
        stdin.write_all(format!("{token}{mi}\n").as_bytes()).and_then(|_| stdin.flush()).map_err(|e| {
            ToolError::new(ErrorCode::NotFound, format!("could not talk to GDB: {e}")).with_remediation("Close this session and start a new one.")
        })?;
        let deadline = Instant::now() + timeout;
        let mut c = Collected::default();
        let mut got_result = false;
        let mut waiting_for_stop = false;
        loop {
            let finished = drain(self, &mut c, &mut |line, sess| {
                if let Some((Some(t), class, _)) = result_record(line)
                    && t == token
                {
                    got_result = true;
                    c_result(class, sess, &mut waiting_for_stop);
                }
                got_result && !waiting_for_stop || (waiting_for_stop && sess.state != "running")
            });
            if finished {
                break;
            }
            if self.proc.is_finished() {
                self.state = "exited";
                self.stdin = None;
                break;
            }
            if Instant::now() >= deadline || cancelled() {
                return Ok((c, true));
            }
            std::thread::sleep(Duration::from_millis(15));
        }
        Ok((c, false))
    }

    /// Run one console command line, as typed at GDB's prompt.
    pub fn console(&mut self, command: &str, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Result<(Collected, bool), ToolError> {
        self.exec(&format!("-interpreter-exec console {}", quote(command)), timeout, cancelled)
    }

    /// Everything that arrived since the last command, and how many lines were dropped so far.
    pub fn take_output(&mut self) -> (Collected, u64) {
        let mut c = Collected::default();
        drain(self, &mut c, &mut |_, _| false);
        let dropped = self.pending.lock().unwrap_or_else(PoisonError::into_inner).dropped;
        (c, dropped)
    }

    pub fn is_finished(&mut self) -> bool {
        self.proc.is_finished()
    }

    /// Stop GDB and anything it started.
    pub fn kill(&self) {
        self.proc.kill();
    }

    /// Whether GDB is alive, the program's state, the last stop and the uptime.
    pub fn status(&mut self) -> Value {
        let alive = !self.proc.is_finished();
        json!({
            "gdb": self.gdb,
            "gdb_pid": self.proc.pid(),
            "alive": alive,
            "program": self.program,
            "state": if alive { self.state } else { "exited" },
            "last_stop": self.last_stop,
            "uptime_seconds": self.started.elapsed().as_secs(),
        })
    }

    /// Ask GDB to exit, then stop it and anything it started. True when it exited on its own.
    pub fn close(mut self) -> bool {
        let graceful = !self.proc.is_finished() && {
            if let Some(stdin) = self.stdin.as_mut() {
                let _ = stdin.write_all(b"-gdb-exit\n").and_then(|_| stdin.flush());
            }
            self.stdin = None;
            self.proc.wait_timeout(Duration::from_secs(3)).is_some()
        };
        self.proc.kill();
        graceful
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mi_parsing() {
        assert_eq!(unquote(r#""Hello \"gdb\"\n\t\101""#), "Hello \"gdb\"\n\tA");
        assert_eq!(quote(r#"print "a\b""#), r#""print \"a\\b\"""#);
        assert_eq!(result_record("12^done,value=\"1\""), Some((Some(12), "done", "value=\"1\"")));
        assert_eq!(result_record("^error,msg=\"x\""), Some((None, "error", "msg=\"x\"")));
        assert_eq!(result_record("~\"text\""), None);
        let f = fields(r#"reason="breakpoint-hit",bkptno="1",frame={addr="0x1",func="main",args=[]},thread-id="1""#);
        assert_eq!(f.get("reason"), Some(&json!("breakpoint-hit")));
        assert_eq!(f.get("frame"), Some(&json!(r#"{addr="0x1",func="main",args=[]}"#)));
        assert_eq!(f.get("thread-id"), Some(&json!("1")));
        assert!(fields("").is_empty());
        assert!(fields("garbage,,=,{{").len() <= 2);
    }
}
