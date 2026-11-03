//! Native platform services for Craft Anything: owned processes, file safety and program lookup.
//!
//! Every external program Craft Anything runs goes through [`process`]: stdin is closed or fed from
//! bytes we own, every run has wall and idle deadlines, output is capped and drained on threads,
//! and the whole process group (Unix) or Job Object (Windows) is killed on timeout, cancel or drop.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod cancel;
pub mod capture;
pub mod fs;
pub mod process;
pub mod serve;
pub mod standin_server;
pub mod sync;
pub mod which;
pub mod window;

pub use capture::{Capture, Event, EventKind, Sig, Spec as CaptureSpec};
pub use fs::{backup_once, write_atomic, write_atomic_private};
pub use process::{Cancel, Ended, Launch, Launched, LineSink, Output, Process, RunningProcess, StdinMode, open_path};
pub use which::{cli_file_name, self_cli_path, which, which_all};

/// Keep the computer from sleeping while the returned guard lives (dropping it stops the helper):
/// a clone that runs for hours must not be cut off by sleep, which would also trip every time
/// limit at once on waking. The screen may still turn off. `None` where there's no helper.
// shortcut: Windows (a PowerShell helper, since this workspace forbids unsafe FFI) and macOS
// (caffeinate) only; add `systemd-inhibit` for Linux when it's needed.
pub fn keep_awake() -> Option<RunningProcess> {
    // ES_CONTINUOUS | ES_SYSTEM_REQUIRED (0x80000001, in decimal: Windows PowerShell reads the hex
    // literal as a negative Int32), held by the helper's thread until it's stopped. Any failure
    // ends the helper, so it never runs without doing its job.
    const WINDOWS: &str = "$ErrorActionPreference = 'Stop'; $k = Add-Type -Name P -Namespace CraftAnything -PassThru -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint f);'; while ($true) { if ($k::SetThreadExecutionState(2147483649) -eq 0) { exit 1 }; Start-Sleep -Seconds 30 }";
    let p = if cfg!(windows) {
        Process::new("powershell").args(["-NoProfile", "-NonInteractive", "-Command", WINDOWS])
    } else if cfg!(target_os = "macos") {
        Process::new("caffeinate").arg("-i")
    } else {
        return None;
    };
    p.timeout(std::time::Duration::from_secs(7 * 24 * 3600)).label("keep awake").spawn().ok()
}

#[cfg(all(test, windows))]
mod tests {
    use std::time::Duration;

    #[test]
    fn keep_awake_holds_until_dropped() {
        let mut guard = crate::keep_awake().expect("the helper starts");
        // A script error (the Windows call failing to load) would end it within moments.
        assert!(guard.wait_timeout(Duration::from_secs(4)).is_none(), "still holding the computer awake");
        let pid = guard.pid();
        drop(guard);
        std::thread::sleep(Duration::from_millis(800));
        let listed = std::process::Command::new("tasklist")
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains(&pid.to_string()));
        assert_eq!(listed.ok(), Some(false), "dropping the guard stops the helper");
    }
}
