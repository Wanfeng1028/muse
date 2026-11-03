//! A safe adapter around the user's `adb` (Android Debug Bridge).
//!
//! Everything here runs `adb` through [`craft_anything_platform::process`]: stdin closed, wall and
//! idle deadlines, capped output drained on threads, and the process group killed on timeout, cancel
//! or drop. Nothing user-supplied is ever interpolated into a shell string:
//!
//! - serials, package names, settings namespaces and keys, intent actions and components are checked
//!   against strict allowlisted patterns and passed to `adb` as separate argv items;
//! - device-side paths and extra values are single-quoted with [`quote_device`] before being placed
//!   in the one string `adb shell` forwards to the device shell.
//!
//! Parsers turn `adb` output into typed structures; they are bounded (line count and line length are
//! capped) and never panic on hostile output.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::{Cancel, Output, Process};
use serde::Serialize;
use std::ffi::OsStr;
use std::path::PathBuf;
use std::time::Duration;

/// Default wall-clock deadline for a quick adb command.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(60);
/// Default idle deadline (no output for this long ends the run).
pub const DEFAULT_IDLE: Duration = Duration::from_secs(30);
/// Cap on output bytes read from a single adb command.
pub const DEFAULT_STDOUT_CAP: usize = 16 * 1024 * 1024;
/// Most lines any parser will look at (hostile or huge output is truncated, never unbounded).
pub const MAX_LINES: usize = 200_000;
/// Longest single line a parser inspects.
pub const MAX_LINE: usize = 64 * 1024;

/// A configured handle to one `adb` executable.
#[derive(Clone)]
pub struct Adb {
    path: PathBuf,
    wall: Duration,
    idle: Option<Duration>,
    stdout_cap: usize,
    cancel: Option<Cancel>,
}

impl Adb {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Adb { path: path.into(), wall: DEFAULT_TIMEOUT, idle: Some(DEFAULT_IDLE), stdout_cap: DEFAULT_STDOUT_CAP, cancel: None }
    }

    pub fn timeout(mut self, d: Duration) -> Self {
        self.wall = d;
        self
    }

    pub fn idle_timeout(mut self, d: Duration) -> Self {
        self.idle = Some(d);
        self
    }

    pub fn no_idle_timeout(mut self) -> Self {
        self.idle = None;
        self
    }

    pub fn stdout_cap(mut self, bytes: usize) -> Self {
        self.stdout_cap = bytes;
        self
    }

    pub fn cancel(mut self, c: Cancel) -> Self {
        self.cancel = Some(c);
        self
    }

    pub fn path(&self) -> &PathBuf {
        &self.path
    }

    fn base(&self) -> Process {
        let mut p = Process::new(&self.path)
            .timeout(self.wall)
            .stdout_cap(self.stdout_cap)
            .stderr_cap(256 * 1024)
            .label("adb")
            .remediation("Install Android platform-tools (adb), or set its path in Settings → Engines (or run engines_install).");
        if let Some(idle) = self.idle {
            p = p.idle_timeout(idle);
        }
        if let Some(c) = &self.cancel {
            p = p.cancel(c.clone());
        }
        p
    }

    /// Run `adb <args>` to completion. A non-zero exit is returned as `Ok` with `success == false`.
    pub fn run<I, S>(&self, args: I) -> Result<Output, ToolError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        self.base().args(args).run()
    }

    /// Run `adb <args>`; a non-zero exit becomes an error with the stderr tail.
    pub fn run_checked<I, S>(&self, args: I) -> Result<Output, ToolError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        self.base().args(args).run_checked()
    }

    /// `adb version`, first line (e.g. "Android Debug Bridge version 1.0.41").
    pub fn version(&self) -> Result<String, ToolError> {
        let out = self.run(["version"])?;
        if !out.success && out.stdout.is_empty() {
            return Err(adb_failed("adb version", &out));
        }
        Ok(out.stdout_text().lines().map(str::trim).find(|l| !l.is_empty()).unwrap_or_default().to_string())
    }

    /// `adb devices -l`, parsed.
    pub fn devices(&self) -> Result<Vec<Device>, ToolError> {
        let out = self.run(["devices", "-l"])?;
        if !out.success && out.stdout.is_empty() {
            return Err(adb_failed("adb devices", &out));
        }
        Ok(parse_devices(&out.stdout_text()))
    }

    /// A device-side shell command. `line` must already be safe (fixed verbs plus [`quote_device`]
    /// for any user value); it is forwarded to the device shell as a single `adb shell` argument.
    pub fn shell(&self, serial: &str, line: &str) -> Result<Output, ToolError> {
        self.run([OsStr::new("-s"), OsStr::new(serial), OsStr::new("shell"), OsStr::new(line)])
    }

    /// `adb exec-out <line>`: like [`Adb::shell`] but with no on-device PTY (binary-safe stdout).
    pub fn exec_out(&self, serial: &str, line: &str) -> Result<Output, ToolError> {
        self.run([OsStr::new("-s"), OsStr::new(serial), OsStr::new("exec-out"), OsStr::new(line)])
    }

    /// A non-shell adb subcommand aimed at one serial (`pull`, `push`, `install`, `uninstall`…).
    pub fn targeted<I, S>(&self, serial: &str, args: I) -> Result<Output, ToolError>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<OsStr>,
    {
        let mut v: Vec<std::ffi::OsString> = vec![OsStr::new("-s").to_owned(), OsStr::new(serial).to_owned()];
        v.extend(args.into_iter().map(|a| a.as_ref().to_owned()));
        self.run(v)
    }
}

/// The error for an adb command that produced nothing usable.
fn adb_failed(what: &str, out: &Output) -> ToolError {
    let tail = {
        let s = out.stderr_text();
        let n = s.chars().count();
        s.chars().skip(n.saturating_sub(1500)).collect::<String>()
    };
    let msg = tail.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("no output").trim().to_string();
    ToolError::new(ErrorCode::ProgramFailed, format!("{what} failed: {msg}"))
        .with_remediation(format!(
            "Check the device is connected and authorised (`adb devices`). What adb printed last:\n{}",
            craft_anything_platform::process::output_excerpt(&tail)
        ))
        .with_details(serde_json::json!({"exit_code": out.code, "stderr_tail": tail}))
}

// ------------------------------------------------------------------------------------------------
// Validation (strict allowlists; reject anything that could change the meaning of a command line)

/// A serial: letters, digits and `.`, `_`, `:`, `-` (covers `emulator-5554`, IP:port, USB ids).
pub fn validate_serial(s: &str) -> Result<&str, ToolError> {
    let ok = !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b':' | b'-'));
    if ok {
        Ok(s)
    } else {
        Err(ToolError::invalid(format!("not a valid device serial: {s:?}"))
            .with_remediation("List device serials with adb_devices_find; a serial looks like emulator-5554 or 0123456789ABCDEF."))
    }
}

/// An Android package name: dot-separated segments of letters, digits and `_`.
pub fn validate_package(s: &str) -> Result<&str, ToolError> {
    let segments: Vec<&str> = s.split('.').collect();
    let ok = !s.is_empty()
        && s.len() <= 255
        && !segments.is_empty()
        && segments.iter().all(|seg| !seg.is_empty() && seg.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_'));
    if ok {
        Ok(s)
    } else {
        Err(ToolError::invalid(format!("not a valid package name: {s:?}"))
            .with_remediation("A package name looks like com.example.app; list them with adb_apps_list."))
    }
}

/// A loose search term for package filtering: letters, digits and `.`, `_`, `-`.
pub fn validate_query(s: &str) -> Result<&str, ToolError> {
    let ok = !s.is_empty() && s.len() <= 255 && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'));
    if ok {
        Ok(s)
    } else {
        Err(ToolError::invalid(format!("not a valid search term: {s:?}")).with_remediation("Use letters, digits, dots, underscores or dashes."))
    }
}

/// A `getprop`/`settings` key, or an intent action/category: letters, digits and `.`, `_`.
pub fn validate_dotted_key<'a>(s: &'a str, what: &str) -> Result<&'a str, ToolError> {
    let ok = !s.is_empty() && s.len() <= 255 && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_'));
    if ok { Ok(s) } else { Err(ToolError::invalid(format!("not a valid {what}: {s:?}"))) }
}

/// A component name `package/.Activity` or `package/com.pkg.Activity`.
pub fn validate_component(s: &str) -> Result<&str, ToolError> {
    let mut parts = s.splitn(2, '/');
    let pkg = parts.next().unwrap_or("");
    let cls = parts.next().unwrap_or("");
    let pkg_ok = validate_package(pkg).is_ok();
    let cls_body = cls.strip_prefix('.').unwrap_or(cls);
    let cls_ok = !cls.is_empty() && cls_body.split('.').all(|seg| !seg.is_empty() && seg.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_'));
    if pkg_ok && cls_ok {
        Ok(s)
    } else {
        Err(ToolError::invalid(format!("not a valid component: {s:?}")).with_remediation("A component looks like com.example.app/.MainActivity."))
    }
}

/// An absolute device path: must start with `/`, no NUL or newline, bounded length.
pub fn validate_device_path(s: &str) -> Result<&str, ToolError> {
    let ok = s.starts_with('/') && s.len() <= 4096 && !s.bytes().any(|b| b == 0 || b == b'\n' || b == b'\r');
    if ok {
        Ok(s)
    } else {
        Err(ToolError::invalid(format!("not a valid device path: {s:?}"))
            .with_remediation("Pass an absolute path on the device, e.g. /sdcard/Download/file.txt."))
    }
}

/// Single-quote a value for the device shell (`'` becomes `'\''`). Safe for any byte that already
/// passed path validation.
pub fn quote_device(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('\'');
    for ch in s.chars() {
        if ch == '\'' {
            out.push_str("'\\''");
        } else {
            out.push(ch);
        }
    }
    out.push('\'');
    out
}

// ------------------------------------------------------------------------------------------------
// Typed structures + parsers

/// One attached device from `adb devices -l`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Device {
    pub serial: String,
    /// `device`, `unauthorized`, `offline`, `no permissions`, `recovery`, `bootloader`, …
    pub state: String,
    pub product: Option<String>,
    pub model: Option<String>,
    pub device: Option<String>,
    pub transport_id: Option<String>,
}

impl Device {
    pub fn is_online(&self) -> bool {
        self.state == "device"
    }
}

pub fn parse_devices(text: &str) -> Vec<Device> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line).trim();
        if line.is_empty() || line.starts_with("List of devices") || line.starts_with('*') || line.starts_with("adb ") {
            continue;
        }
        let mut it = line.split_whitespace();
        let Some(serial) = it.next() else { continue };
        let Some(state) = it.next() else { continue };
        let mut dev = Device { serial: serial.to_string(), state: state.to_string(), product: None, model: None, device: None, transport_id: None };
        for tok in it {
            if let Some((k, v)) = tok.split_once(':') {
                match k {
                    "product" => dev.product = Some(v.to_string()),
                    "model" => dev.model = Some(v.to_string()),
                    "device" => dev.device = Some(v.to_string()),
                    "transport_id" => dev.transport_id = Some(v.to_string()),
                    _ => {}
                }
            }
        }
        out.push(dev);
    }
    out
}

/// One `getprop` property.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Property {
    pub key: String,
    pub value: String,
}

/// Parse `getprop` output lines of the form `[key]: [value]`.
pub fn parse_getprop(text: &str) -> Vec<Property> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line);
        // [key]: [value]
        let Some(rest) = line.trim().strip_prefix('[') else { continue };
        let Some((key, rest)) = rest.split_once("]:") else { continue };
        let value = rest.trim().strip_prefix('[').and_then(|r| r.strip_suffix(']')).unwrap_or("").to_string();
        out.push(Property { key: key.to_string(), value });
    }
    out
}

/// Keys surfaced by `adb_device_show` (a small, non-sensitive whitelist).
pub const DEVICE_PROP_WHITELIST: &[&str] = &[
    "ro.product.manufacturer",
    "ro.product.brand",
    "ro.product.model",
    "ro.product.name",
    "ro.product.device",
    "ro.product.cpu.abi",
    "ro.product.cpu.abilist",
    "ro.build.version.release",
    "ro.build.version.sdk",
    "ro.build.version.security_patch",
    "ro.build.fingerprint",
    "ro.build.type",
    "ro.build.tags",
    "ro.hardware",
    "ro.board.platform",
    "ro.boot.hardware",
    "ro.debuggable",
    "ro.secure",
];

/// Parse `pm list packages` output lines of the form `package:<name>` (ignores any `=installer`).
pub fn parse_packages(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line).trim();
        if let Some(name) = line.strip_prefix("package:") {
            let name = name.split_whitespace().next().unwrap_or(name);
            let name = name.split('=').next().unwrap_or(name);
            if !name.is_empty() {
                out.push(name.to_string());
            }
        }
    }
    out
}

/// Parse `pm list features` output lines of the form `feature:<name>`.
pub fn parse_features(text: &str) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line).trim();
        if let Some(name) = line.strip_prefix("feature:")
            && !name.is_empty()
        {
            out.push(name.to_string());
        }
    }
    out
}

/// One service from `service list`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Service {
    pub index: Option<u32>,
    pub name: String,
    pub interface: Option<String>,
}

/// Parse `service list` output (`  3  activity: [android.app.IActivityManager]`).
pub fn parse_services(text: &str) -> Vec<Service> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line).trim();
        if line.is_empty() || line.starts_with("Found ") {
            continue;
        }
        // "<index>\t<name>: [<interface>]" or "<index>  <name>: [<interface>]"
        let (index, rest) = match line.split_once(['\t', ' ']) {
            Some((idx, r)) => (idx.trim().parse::<u32>().ok(), r.trim()),
            None => (None, line),
        };
        let Some((name, iface)) = rest.split_once(':') else { continue };
        let interface = iface.trim().trim_start_matches('[').trim_end_matches(']').trim();
        out.push(Service { index, name: name.trim().to_string(), interface: if interface.is_empty() { None } else { Some(interface.to_string()) } });
    }
    out
}

/// One row from `ps -A`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ProcessRow {
    pub user: Option<String>,
    pub pid: Option<u32>,
    pub ppid: Option<u32>,
    pub name: String,
}

/// Parse `ps -A` output using the header to locate the PID/PPID/USER/NAME columns.
pub fn parse_ps(text: &str) -> Vec<ProcessRow> {
    let mut lines = text.lines().take(MAX_LINES);
    let Some(header) = lines.next() else { return Vec::new() };
    let cols: Vec<&str> = header.split_whitespace().collect();
    let find = |want: &str| cols.iter().position(|c| c.eq_ignore_ascii_case(want));
    let (user_i, pid_i, ppid_i) = (find("USER"), find("PID"), find("PPID"));
    // NAME / CMD / ARGS is usually the last column; take everything from there to end of line.
    let name_i = find("NAME").or_else(|| find("CMD")).or_else(|| find("ARGS")).unwrap_or(cols.len().saturating_sub(1));
    let mut out = Vec::new();
    for line in lines {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line);
        let fields: Vec<&str> = line.split_whitespace().collect();
        if fields.is_empty() {
            continue;
        }
        let at = |i: Option<usize>| i.and_then(|i| fields.get(i)).map(|s| s.to_string());
        let name = fields.get(name_i..).map(|s| s.join(" ")).filter(|s| !s.is_empty()).unwrap_or_else(|| fields.last().copied().unwrap_or("").to_string());
        out.push(ProcessRow {
            user: at(user_i),
            pid: pid_i.and_then(|i| fields.get(i)).and_then(|s| s.parse().ok()),
            ppid: ppid_i.and_then(|i| fields.get(i)).and_then(|s| s.parse().ok()),
            name,
        });
    }
    out
}

/// One parsed logcat line (`threadtime` format), with the raw line kept.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct LogLine {
    pub timestamp: Option<String>,
    pub pid: Option<u32>,
    pub tid: Option<u32>,
    pub level: Option<String>,
    pub tag: Option<String>,
    pub message: String,
    pub raw: String,
}

/// Parse `logcat -d` output (threadtime format: `MM-DD HH:MM:SS.mmm  PID  TID L Tag: msg`).
pub fn parse_logcat(text: &str) -> Vec<LogLine> {
    let mut out = Vec::new();
    for raw in text.lines().take(MAX_LINES) {
        let raw = raw.get(..MAX_LINE.min(raw.len())).unwrap_or(raw);
        if raw.trim().is_empty() || raw.starts_with("--------- beginning") {
            continue;
        }
        out.push(parse_logcat_line(raw));
    }
    out
}

fn parse_logcat_line(raw: &str) -> LogLine {
    let mut line = LogLine { timestamp: None, pid: None, tid: None, level: None, tag: None, message: String::new(), raw: raw.to_string() };
    let toks: Vec<&str> = raw.split_whitespace().collect();
    // date time pid tid level tag: message
    let digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
    match (toks.first(), toks.get(1), toks.get(2), toks.get(3), toks.get(4)) {
        (Some(&date), Some(&time), Some(&pid), Some(&tid), Some(&level)) if digits(pid) && digits(tid) => {
            line.timestamp = Some(format!("{date} {time}"));
            line.pid = pid.parse().ok();
            line.tid = tid.parse().ok();
            line.level = Some(level.to_string());
            // Everything after the level token is "Tag: message".
            let rest: String = toks.get(5..).map(|s| s.join(" ")).unwrap_or_default();
            if let Some((tag, msg)) = rest.split_once(':') {
                line.tag = Some(tag.trim().to_string());
                line.message = msg.trim().to_string();
            } else {
                line.message = rest;
            }
        }
        _ => line.message = raw.trim().to_string(),
    }
    line
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serials_and_packages_are_validated() {
        assert!(validate_serial("emulator-5554").is_ok());
        assert!(validate_serial("0123456789ABCDEF").is_ok());
        assert!(validate_serial("192.168.0.2:5555").is_ok());
        assert!(validate_serial("a; rm -rf /").is_err());
        assert!(validate_serial("has space").is_err());
        assert!(validate_serial("").is_err());

        assert!(validate_package("com.example.app").is_ok());
        assert!(validate_package("com.example.app_2").is_ok());
        assert!(validate_package("com.example.app; evil").is_err());
        assert!(validate_package("../etc").is_err());
        assert!(validate_package("").is_err());
    }

    #[test]
    fn device_paths_and_quoting() {
        assert!(validate_device_path("/sdcard/Download/x.txt").is_ok());
        assert!(validate_device_path("relative/path").is_err());
        assert!(validate_device_path("/a\nb").is_err());
        assert_eq!(quote_device("/a/b c"), "'/a/b c'");
        assert_eq!(quote_device("it's"), "'it'\\''s'");
    }

    #[test]
    fn component_validation() {
        assert!(validate_component("com.example.app/.MainActivity").is_ok());
        assert!(validate_component("com.example.app/com.example.app.Main").is_ok());
        assert!(validate_component("com.example.app").is_err());
        assert!(validate_component("a b/.C").is_err());
    }

    #[test]
    fn parses_devices_listing() {
        let text = "List of devices attached\n\
            emulator-5554          device product:sdk_gphone_x86 model:sdk_gphone model:Android_SDK device:emu64x transport_id:1\n\
            0123456789ABCDEF       unauthorized\n\
            192.168.0.2:5555       offline\n";
        let d = parse_devices(text);
        assert_eq!(d.len(), 3);
        assert_eq!(d[0].serial, "emulator-5554");
        assert!(d[0].is_online());
        assert_eq!(d[0].transport_id.as_deref(), Some("1"));
        assert_eq!(d[1].state, "unauthorized");
        assert!(!d[2].is_online());
    }

    #[test]
    fn parses_getprop_packages_features_services() {
        let gp = "[ro.product.model]: [Pixel 5]\n[ro.build.version.sdk]: [34]\n[malformed line\n[empty]: []\n";
        let props = parse_getprop(gp);
        assert_eq!(props.len(), 3);
        assert_eq!(props[0].key, "ro.product.model");
        assert_eq!(props[0].value, "Pixel 5");
        assert_eq!(props[2].value, "");

        let pkgs = parse_packages("package:com.android.shell\npackage:com.example.app=com.android.vending\nnoise\n");
        assert_eq!(pkgs, vec!["com.android.shell".to_string(), "com.example.app".to_string()]);

        let feats = parse_features("feature:android.hardware.camera\nfeature:reqGlEsVersion=0x30000\n");
        assert_eq!(feats.len(), 2);

        let svcs = parse_services("Found 2 services:\n0\tactivity: [android.app.IActivityManager]\n1\tpackage: [android.content.pm.IPackageManager]\n");
        assert_eq!(svcs.len(), 2);
        assert_eq!(svcs[0].name, "activity");
        assert_eq!(svcs[0].interface.as_deref(), Some("android.app.IActivityManager"));
    }

    #[test]
    fn parses_ps_and_logcat() {
        let ps = "USER           PID  PPID     VSZ    RSS WCHAN            ADDR S NAME\n\
            root             1     0   10760   1200 0                   0 S init\n\
            u0_a123       4567   789 1234567  65432 0                   0 S com.example.app\n";
        let rows = parse_ps(ps);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[1].pid, Some(4567));
        assert_eq!(rows[1].ppid, Some(789));
        assert_eq!(rows[1].name, "com.example.app");
        assert_eq!(rows[1].user.as_deref(), Some("u0_a123"));

        let lc = "--------- beginning of main\n10-12 15:23:01.123  1234  1250 I ActivityManager: Start proc\nmalformed\n";
        let lines = parse_logcat(lc);
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0].pid, Some(1234));
        assert_eq!(lines[0].level.as_deref(), Some("I"));
        assert_eq!(lines[0].tag.as_deref(), Some("ActivityManager"));
        assert_eq!(lines[0].message, "Start proc");
        assert_eq!(lines[1].message, "malformed");
    }

    #[test]
    fn missing_adb_is_provider_unavailable() {
        let adb = Adb::new("/nonexistent/definitely/not/adb");
        let err = adb.devices().unwrap_err();
        assert_eq!(err.code, ErrorCode::EngineMissing);
        assert!(err.remediation.is_some());
    }
}
