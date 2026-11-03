//! Running JADX (the Android/Java decompiler, an external program) on one class.

use craft_anything_evidence::ToolError;
use craft_anything_platform::cancel::CancelToken;
use craft_anything_platform::process::{Output, Process};
use std::path::Path;
use std::time::Duration;

/// Decompile one class (`class_java`, dotted, `$` for inner classes) of `input` (an APK, DEX or
/// JAR) into `out`, resources skipped. The caller finds `<Outer>.java` under `out`.
pub fn run_single_class(jadx: &Path, input: &Path, class_java: &str, out: &Path, cancel: CancelToken) -> Result<Output, ToolError> {
    Process::new(jadx)
        .args(["--no-res", "--quiet", "--single-class", class_java, "-d"])
        .arg(out)
        .arg(input)
        .timeout(Duration::from_secs(180))
        .idle_timeout(Duration::from_secs(120))
        .stdout_cap(1 << 20)
        .stderr_cap(1 << 20)
        .cancel_when(move || cancel.is_cancelled())
        .label("jadx")
        .run()
}
