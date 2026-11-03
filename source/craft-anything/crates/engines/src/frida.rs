//! A safe adapter around the Frida command-line tools (`frida`, `frida-ps`, `frida-ls-devices`).
//!
//! This is **not** a native binding: every operation shells out to the Frida CLI through
//! [`craft_anything_platform::process`] with a deadline, closed stdin and capped output, so a hung
//! or chatty session can never lock Craft Anything up. The companion CLIs (`frida-ps`,
//! `frida-ls-devices`) are found next to the located `frida` binary.
//!
//! Remote-device authentication (token, certificate, origin) is accepted only to be forwarded to
//! the CLI as process arguments. It is never logged, returned, or placed in evidence.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::{Cancel, Output, Process};
use serde::Serialize;
use std::ffi::{OsStr, OsString};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Default deadline for a quick Frida query (listing devices or processes).
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(60);
pub const DEFAULT_IDLE: Duration = Duration::from_secs(30);
pub const MAX_LINES: usize = 200_000;
pub const MAX_LINE: usize = 64 * 1024;

/// How to reach a Frida device. The remote half carries secrets and is never serialized.
#[derive(Debug, Clone, Default)]
pub struct Selector {
    pub device_id: Option<String>,
    pub remote: Option<Remote>,
}

/// A remote frida-server. All fields except `address` are authentication material that must never
/// be returned to a caller or written to evidence.
#[derive(Debug, Clone)]
pub struct Remote {
    pub address: String,
    pub token: Option<String>,
    pub certificate: Option<String>,
    pub origin: Option<String>,
    pub keepalive_interval: Option<u32>,
}

impl Selector {
    /// True when the caller gave exactly one of `device_id` / `remote`.
    pub fn is_specified(&self) -> bool {
        self.device_id.is_some() ^ self.remote.is_some()
    }

    /// Build the device-selection CLI arguments. Returns an error if neither or both are set, or if
    /// a value fails validation.
    pub fn args(&self) -> Result<Vec<OsString>, ToolError> {
        match (&self.device_id, &self.remote) {
            (Some(id), None) => {
                validate_device_id(id)?;
                Ok(vec![OsStr::new("-D").into(), OsStr::new(id).into()])
            }
            (None, Some(r)) => {
                validate_address(&r.address)?;
                let mut v = vec![OsStr::new("-H").to_owned(), OsStr::new(&r.address).to_owned()];
                if let Some(t) = &r.token {
                    v.push(OsStr::new("--token").into());
                    v.push(OsStr::new(t).into());
                }
                if let Some(c) = &r.certificate {
                    v.push(OsStr::new("--certificate").into());
                    v.push(OsStr::new(c).into());
                }
                if let Some(o) = &r.origin {
                    v.push(OsStr::new("--origin").into());
                    v.push(OsStr::new(o).into());
                }
                if let Some(k) = r.keepalive_interval {
                    v.push(OsStr::new("--keepalive-interval").into());
                    v.push(OsString::from(k.to_string()));
                }
                Ok(v)
            }
            (None, None) => Err(ToolError::invalid("a device is required: pass device_id or remote")
                .with_remediation("List devices with frida_devices_find, then pass its device_id (e.g. \"usb\", \"local\") or a remote address.")),
            (Some(_), Some(_)) => Err(ToolError::invalid("pass only one of device_id or remote, not both")),
        }
    }
}

fn validate_device_id(id: &str) -> Result<(), ToolError> {
    let ok = !id.is_empty() && id.len() <= 256 && id.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b':' | b'-'));
    if ok { Ok(()) } else { Err(ToolError::invalid(format!("not a valid frida device id: {id:?}"))) }
}

fn validate_address(addr: &str) -> Result<(), ToolError> {
    // host[:port]; letters, digits, dots, dashes, colon for port and IPv6-in-brackets.
    let ok = !addr.is_empty() && addr.len() <= 256 && addr.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'-' | b':' | b'[' | b']'));
    if ok { Ok(()) } else { Err(ToolError::invalid(format!("not a valid remote address: {addr:?}"))) }
}

/// A configured handle to the Frida CLI.
#[derive(Clone)]
pub struct Frida {
    path: PathBuf,
    wall: Duration,
    idle: Option<Duration>,
    cancel: Option<Cancel>,
}

impl Frida {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Frida { path: path.into(), wall: DEFAULT_TIMEOUT, idle: Some(DEFAULT_IDLE), cancel: None }
    }

    pub fn timeout(mut self, d: Duration) -> Self {
        self.wall = d;
        self
    }

    pub fn idle_timeout(mut self, d: Duration) -> Self {
        self.idle = Some(d);
        self
    }

    pub fn cancel(mut self, c: Cancel) -> Self {
        self.cancel = Some(c);
        self
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// A sibling CLI (`frida-ps`, `frida-ls-devices`) next to the located `frida`, keeping the same
    /// extension (e.g. `.exe`) as the main binary.
    pub fn sibling(&self, stem: &str) -> PathBuf {
        let ext = self.path.extension();
        let name = match ext {
            Some(e) => format!("{stem}.{}", e.to_string_lossy()),
            None => stem.to_string(),
        };
        match self.path.parent() {
            Some(dir) => dir.join(name),
            None => PathBuf::from(name),
        }
    }

    fn proc(&self, program: &Path, remediation: &str) -> Process {
        let mut p =
            Process::new(program).timeout(self.wall).stdout_cap(8 * 1024 * 1024).stderr_cap(512 * 1024).label("frida").remediation(remediation.to_string());
        if let Some(idle) = self.idle {
            p = p.idle_timeout(idle);
        }
        if let Some(c) = &self.cancel {
            p = p.cancel(c.clone());
        }
        p
    }

    /// `frida --version`.
    pub fn version(&self) -> Result<String, ToolError> {
        let out = self.proc(&self.path, INSTALL).arg("--version").run()?;
        Ok(out.stdout_text().lines().map(str::trim).find(|l| !l.is_empty()).unwrap_or_default().to_string())
    }

    /// `frida-ls-devices`, parsed.
    pub fn list_devices(&self, selector: Option<&Selector>) -> Result<Vec<FridaDevice>, ToolError> {
        // frida-ls-devices has no -H flag, so a remote address can't be listed with it; report the
        // remote as a single device instead, the way frida-ps/frida take -H. The entry is made up
        // from the address: nothing is contacted here, so a typo still "finds" a device.
        if let Some(sel) = selector
            && let Some(r) = &sel.remote
        {
            validate_address(&r.address)?;
            return Ok(vec![FridaDevice {
                device_id: r.address.clone(),
                kind: "remote".into(),
                name: format!("Remote ({}) (not contacted; frida-ps -H checks it)", r.address),
            }]);
        }
        let prog = self.sibling("frida-ls-devices");
        let args: Vec<OsString> = Vec::new();
        // On Windows this tool crashes without a real console, then hangs instead of exiting.
        #[cfg(windows)]
        {
            if !prog.is_file() {
                return Err(ToolError::new(ErrorCode::EngineMissing, "frida-ls-devices isn't next to frida.").with_remediation(INSTALL));
            }
            let (text, code) = craft_anything_platform::capture::console_text(&prog, &args, self.wall, self.cancel.clone())?;
            if code != Some(0) {
                let last = text.lines().rev().map(str::trim).find(|l| !l.is_empty()).unwrap_or("no output");
                return Err(ToolError::new(ErrorCode::ProgramFailed, format!("frida-ls-devices failed: {last}")));
            }
            Ok(parse_devices(&text))
        }
        #[cfg(not(windows))]
        {
            let out = self.proc(&prog, INSTALL).args(args).run()?;
            if !out.success && out.stdout.is_empty() {
                return Err(cli_failed("frida-ls-devices", &out));
            }
            Ok(parse_devices(&out.stdout_text()))
        }
    }

    /// `frida-ps` for the selected device, parsed.
    pub fn list_processes(&self, selector: &Selector) -> Result<Vec<FridaProcess>, ToolError> {
        let prog = self.sibling("frida-ps");
        let args = selector.args()?;
        // `-ai` lists installed applications with identifiers; it degrades to processes on devices
        // that don't support it. We ask for applications first; failing that, plain processes.
        let app_out = self
            .proc(&prog, INSTALL)
            .args({
                let mut a = args.clone();
                a.push(OsStr::new("-ai").into());
                a
            })
            .run()?;
        if app_out.success && !app_out.stdout.is_empty() {
            let apps = parse_processes(&app_out.stdout_text());
            if !apps.is_empty() {
                return Ok(apps);
            }
        }
        let out = self.proc(&prog, INSTALL).args(args).run()?;
        if !out.success && out.stdout.is_empty() {
            return Err(cli_failed("frida-ps", &out));
        }
        Ok(parse_processes(&out.stdout_text()))
    }

    /// Attach to `pid` (or spawn `program`), load `script_file`, and run for up to the configured
    /// wall deadline, capturing the script's console/`send` output line by line. Returns the raw
    /// [`Output`]; the caller turns captured lines into evidence. `-q` runs in quiet batch mode and
    /// closed stdin makes the REPL exit instead of waiting for input.
    pub fn run_script(&self, selector: &Selector, attach: &Attach, script_file: &Path) -> Result<Output, ToolError> {
        let mut args = selector.args()?;
        match attach {
            Attach::Pid(pid) => {
                args.push(OsStr::new("-p").into());
                args.push(OsString::from(pid.to_string()));
            }
            Attach::Spawn { program, argv } => {
                args.push(OsStr::new("-f").into());
                args.push(program.as_os_str().to_owned());
                for a in argv {
                    args.push(OsString::from(a));
                }
            }
        }
        args.push(OsStr::new("-l").into());
        args.push(script_file.as_os_str().to_owned());
        args.push(OsStr::new("-q").into());
        self.proc(&self.path, INSTALL).args(args).run()
    }
}

/// How a script run attaches to its target.
#[derive(Debug, Clone)]
pub enum Attach {
    Pid(u32),
    Spawn { program: PathBuf, argv: Vec<String> },
}

const INSTALL: &str = "Install Frida (for example `pipx install frida-tools`), or set its path in Settings → Engines.";

fn cli_failed(what: &str, out: &Output) -> ToolError {
    let tail = {
        let s = out.stderr_text();
        let n = s.chars().count();
        s.chars().skip(n.saturating_sub(1500)).collect::<String>()
    };
    let msg = tail.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("no output").trim().to_string();
    ToolError::new(ErrorCode::ProgramFailed, format!("{what} failed: {msg}"))
        .with_remediation(format!(
            "Check the device is reachable and frida-server is running on it. What Frida printed last:\n{}",
            craft_anything_platform::process::output_excerpt(&tail)
        ))
        .with_details(serde_json::json!({"exit_code": out.code, "stderr_tail": tail}))
}

/// A device from `frida-ls-devices`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FridaDevice {
    pub device_id: String,
    pub kind: String,
    pub name: String,
}

/// Parse the `frida-ls-devices` table (`Id  Type  Name`, with a `----` separator row).
pub fn parse_devices(text: &str) -> Vec<FridaDevice> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line);
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with("----") {
            continue;
        }
        // Columns are at least two spaces apart; a name has single spaces in it. A later column
        // (newer versions add the device's OS) isn't part of the name.
        let mut it = trimmed.split("  ").map(str::trim).filter(|c| !c.is_empty());
        let Some(first) = it.next() else { continue };
        let Some(second) = it.next() else { continue };
        if first.eq_ignore_ascii_case("id") && second.eq_ignore_ascii_case("type") {
            continue; // header
        }
        let name = it.next().unwrap_or_default().to_string();
        out.push(FridaDevice { device_id: first.to_string(), kind: second.to_string(), name });
    }
    out
}

/// A process from `frida-ps`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FridaProcess {
    pub pid: u32,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub identifier: Option<String>,
}

/// Parse `frida-ps` output. Columns are `PID  Name` or `PID  Name  Identifier`; the header and a
/// separator row are skipped.
pub fn parse_processes(text: &str) -> Vec<FridaProcess> {
    let mut out = Vec::new();
    for line in text.lines().take(MAX_LINES) {
        let line = line.get(..MAX_LINE.min(line.len())).unwrap_or(line);
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with("----") {
            continue;
        }
        let mut it = trimmed.split_whitespace();
        let Some(first) = it.next() else { continue };
        let Ok(pid) = first.parse::<u32>() else { continue }; // skips the "PID Name" header too
        let rest: Vec<&str> = it.collect();
        // When an identifier column exists it's the last whitespace-free token containing a dot.
        let (name, identifier) = match rest.split_last() {
            Some((last, head)) if !head.is_empty() && last.contains('.') && !last.contains(' ') => (head.join(" "), Some(last.to_string())),
            _ => (rest.join(" "), None),
        };
        out.push(FridaProcess { pid, name, identifier });
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selector_requires_exactly_one() {
        assert!(Selector::default().args().is_err());
        let both = Selector {
            device_id: Some("usb".into()),
            remote: Some(Remote { address: "127.0.0.1:27042".into(), token: None, certificate: None, origin: None, keepalive_interval: None }),
        };
        assert!(both.args().is_err());
        let one = Selector { device_id: Some("usb".into()), remote: None };
        assert_eq!(one.args().unwrap(), vec![OsString::from("-D"), OsString::from("usb")]);
    }

    #[test]
    fn remote_auth_is_forwarded_as_args() {
        let sel = Selector {
            device_id: None,
            remote: Some(Remote {
                address: "10.0.0.5:27042".into(),
                token: Some("secret".into()),
                certificate: Some("/tmp/c.pem".into()),
                origin: None,
                keepalive_interval: Some(15),
            }),
        };
        let args = sel.args().unwrap();
        assert!(args.contains(&OsString::from("-H")));
        assert!(args.contains(&OsString::from("--token")));
        assert!(args.contains(&OsString::from("--keepalive-interval")));
        // The Remote type is not Serialize, so auth cannot leak into evidence via serde_json.
    }

    #[test]
    fn sibling_keeps_extension() {
        assert_eq!(Frida::new("/opt/frida/bin/frida").sibling("frida-ps"), PathBuf::from("/opt/frida/bin/frida-ps"));
        assert_eq!(Frida::new("C:/frida/frida.exe").sibling("frida-ps"), PathBuf::from("C:/frida/frida-ps.exe"));
    }

    #[test]
    fn parses_devices_and_processes() {
        let devs =
            "Id              Type    Name\n--------------  ------  ------------\nlocal           local   Local System\nusb             usb     Pixel 5\n";
        let d = parse_devices(devs);
        assert_eq!(d.len(), 2);
        assert_eq!(d[0].device_id, "local");
        assert_eq!(d[1].name, "Pixel 5");

        let with_os = "Id     Type   Name          OS\n-----  -----  ------------  ----------\nlocal  local  Local System  Windows 11\n";
        assert_eq!(parse_devices(with_os)[0].name, "Local System");

        let ps = " PID  Name            Identifier\n----  --------------  ----------------\n1234  Example         com.example.app\n 56  init\n";
        let p = parse_processes(ps);
        assert_eq!(p.len(), 2);
        assert_eq!(p[0].pid, 1234);
        assert_eq!(p[0].identifier.as_deref(), Some("com.example.app"));
        assert_eq!(p[1].pid, 56);
        assert_eq!(p[1].name, "init");
        assert!(p[1].identifier.is_none());
    }

    #[cfg(unix)]
    #[test]
    fn a_device_without_applications_lists_its_processes() {
        // A stand-in for frida-ps that, like Windows, has processes but no applications.
        let dir = tempfile::tempdir().unwrap();
        let frida = {
            use std::os::unix::fs::PermissionsExt;
            let ps = dir.path().join("frida-ps");
            std::fs::write(&ps, "#!/bin/sh\ncase \"$*\" in *-a*) exit 0;; esac\nprintf '  PID  Name\\n----  ---------\\n   12  notes.exe\\n'\n").unwrap();
            std::fs::set_permissions(&ps, std::fs::Permissions::from_mode(0o755)).unwrap();
            dir.path().join("frida")
        };
        let selector = Selector { device_id: Some("local".into()), remote: None };
        let processes = Frida::new(frida).list_processes(&selector).unwrap();
        assert_eq!(processes.len(), 1, "{processes:?}");
        assert_eq!(processes[0].pid, 12);
    }

    #[test]
    fn a_remote_selector_lists_one_uncontacted_device() {
        // The remote branch answers from the address alone: a path that cannot run proves no
        // program is started.
        let frida = Frida::new("/nonexistent/definitely/not/frida");
        let selector = Selector {
            device_id: None,
            remote: Some(Remote { address: "10.0.0.5:27042".into(), token: None, certificate: None, origin: None, keepalive_interval: None }),
        };
        let devices = frida.list_devices(Some(&selector)).unwrap();
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].kind, "remote");
        assert_eq!(devices[0].device_id, "10.0.0.5:27042");
        assert!(devices[0].name.contains("not contacted"));
    }

    #[test]
    fn an_invalid_remote_address_is_refused() {
        let frida = Frida::new("/nonexistent/definitely/not/frida");
        let selector = Selector {
            device_id: None,
            remote: Some(Remote { address: "not an address!".into(), token: None, certificate: None, origin: None, keepalive_interval: None }),
        };
        let err = frida.list_devices(Some(&selector)).unwrap_err();
        assert_eq!(err.code, ErrorCode::BadInput);
    }

    #[test]
    fn missing_frida_is_provider_unavailable() {
        let frida = Frida::new("/nonexistent/definitely/not/frida");
        let err = frida.list_devices(None).unwrap_err();
        assert_eq!(err.code, ErrorCode::EngineMissing);
    }
}
