//! Pictures of a running program's window, for studying how an app or game looks while it runs
//! (and comparing a rebuild with it). Uses the operating system's own capture through `xcap`, on
//! Windows and macOS; elsewhere it says it isn't available yet.

use craft_anything_evidence::{ErrorCode, ToolError};

/// Whether this system can picture a window: Windows and macOS for now (ROADMAP R2.4).
pub const SUPPORTED: bool = cfg!(any(windows, target_os = "macos"));

/// Why it can't, where it can't.
pub fn unsupported() -> ToolError {
    ToolError::new(ErrorCode::FeatureMissing, "Picturing a program's window works on Windows and macOS, not on this system yet.")
        .with_remediation("Add pictures of the original yourself (screenshots) instead.")
}

/// A window's picture: 8-bit RGBA, row by row.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WindowShot {
    pub title: String,
    pub app: String,
    pub width: u32,
    pub height: u32,
    pub rgba: Vec<u8>,
}

/// Picture the largest visible window that belongs to `pid`, or (when none does, as with a
/// launcher that starts the real program) to a process whose name matches `app_name`.
#[cfg(any(windows, target_os = "macos"))]
pub fn capture_window(pid: u32, app_name: Option<&str>) -> Result<WindowShot, ToolError> {
    let windows = xcap::Window::all().map_err(|e| ToolError::new(ErrorCode::FeatureMissing, format!("Can't list windows on this computer: {e}")))?;
    let usable = |w: &xcap::Window| !w.is_minimized().unwrap_or(true) && w.width().unwrap_or(0) > 32 && w.height().unwrap_or(0) > 32;
    let area = |w: &xcap::Window| u64::from(w.width().unwrap_or(0)) * u64::from(w.height().unwrap_or(0));
    let by_pid = windows.iter().filter(|w| usable(w) && w.pid().ok() == Some(pid)).max_by_key(|w| area(w));
    let chosen = by_pid.or_else(|| {
        let want = app_name?.to_ascii_lowercase();
        windows.iter().filter(|w| usable(w) && w.app_name().is_ok_and(|n| n.to_ascii_lowercase().contains(&want))).max_by_key(|w| area(w))
    });
    let Some(w) = chosen else {
        return Err(ToolError::new(ErrorCode::NotFound, "The program didn't show a window to picture.")
            .with_remediation("Give it longer to start (wait_secs), or check that it opens a window."));
    };
    let img = w.capture_image().map_err(|e| ToolError::new(ErrorCode::ProgramFailed, format!("Couldn't picture the window: {e}")))?;
    Ok(WindowShot {
        title: w.title().unwrap_or_default(),
        app: w.app_name().unwrap_or_default(),
        width: img.width(),
        height: img.height(),
        rgba: img.into_raw(),
    })
}

/// Linux and the BSDs: not built in yet (ROADMAP R2.4).
#[cfg(not(any(windows, target_os = "macos")))]
pub fn capture_window(_pid: u32, _app_name: Option<&str>) -> Result<WindowShot, ToolError> {
    Err(unsupported())
}
