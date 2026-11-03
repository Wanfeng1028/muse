//! A connected Android phone or emulator, through the user's `adb`.
//!
//! Every tool runs `adb` via [`craft_anything_platform::process`] (closed stdin, wall and idle
//! deadlines, capped output, process-group kill on timeout/cancel/drop) and returns an [`Evidence`]
//! record on the authority of an [`Authority::OutsideService`] (the device). Serials, package
//! names, settings keys, intent actions and components are validated against strict allowlists;
//! device paths and extra values are single-quoted before they reach the device shell. Device-paths
//! never become part of a host shell string — adb arguments are passed as argv.
//!
//! Tools that write to the device (`push`, `install`, `uninstall`, `start`, `stop`) carry
//! [`Effects::MUTATES_DEVICE`] and are consent-gated; tools that write to the host carry
//! [`Effects::WRITES_FILESYSTEM`]. When adb isn't installed every tool (except `engines_adb_check`,
//! which reports exactly that) returns a clear `EngineMissing`; when the device is missing or
//! unauthorised they return `NotFound` / `NoPermission`. Nothing ever hangs.

use super::artifact_tools::{UnlessWritten, create_absent_dir};
use super::native_common::spec;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::adb::{self, Adb, Device};
use craft_anything_evidence::{Authority, Confidence, Coverage, Environment, ErrorCode, Evidence, EvidenceBuilder, Limitation, Location, Subject, ToolError};
use craft_anything_platform::fs::write_atomic;
use craft_anything_platform::process::{Cancel, Output};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::sync::Arc;
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Adb;
    // Base effects for a read-only device query: records evidence, runs adb, talks to the device
    // over adb's socket.
    let read = Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS | Effects::ACCESSES_NETWORK;
    let host_write = read | Effects::WRITES_FILESYSTEM;
    let device_write = read | Effects::MUTATES_DEVICE; // MUTATES_DEVICE → consent-gated
    let eng = Requires::Engine("adb");
    vec![
        spec(
            "engines_adb_check",
            "Is adb available?",
            "Report whether Android platform-tools (adb) is installed (Settings path, the managed engine store, then PATH) and its version. Contacts no device. Needs nothing installed to answer.",
            "Check whether the helper that talks to Android phones is installed.",
            Adb,
            Effects::MUTATES_SESSION | Effects::LAUNCHES_PROCESS,
            Requires::Nothing,
            schema_of::<Empty>,
            engines_adb_check,
        ),
        spec(
            "adb_devices_find",
            "Connected devices",
            "List phones and emulators attached to adb (`adb devices -l`): serial, connection state (device, unauthorized, offline…), product, model and transport id.",
            "See which Android phones or emulators are plugged in.",
            Adb,
            read,
            eng,
            schema_of::<Empty>,
            adb_devices_find,
        ),
        spec(
            "adb_device_show",
            "Device details",
            "Read a whitelist of device properties with `getprop` (manufacturer, brand, model, Android version and SDK level, security patch, CPU ABIs, build fingerprint/type). The full property set is parsed and counted; a bounded sample is attached.",
            "Find out what phone this is and which Android version it runs.",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_device_show,
        ),
        spec(
            "adb_apps_list",
            "Installed apps",
            "List installed package names with `pm list packages`. Scope all (default), third_party (-3) or system (-s).",
            "List the apps installed on the phone.",
            Adb,
            read,
            eng,
            schema_of::<ListPackagesParams>,
            adb_apps_list,
        ),
        spec(
            "adb_log_read",
            "Device log",
            "Read a bounded tail of the device log with `logcat -d` (dump and exit, never follow). count 1..10000 (default 500), buffer main|system|radio|events|crash (default main), optional pid filter. Lines are parsed into timestamp, pid, tid, level, tag and message.",
            "Read recent messages the phone printed, so you can see what an app is doing.",
            Adb,
            read,
            eng,
            schema_of::<LogcatParams>,
            adb_log_read,
        ),
        spec(
            "adb_app_show",
            "App details on device",
            "Inspect one installed package with `dumpsys package <name>`: version name/code, userId, install and update times, data and code paths, declared and granted permissions. Key fields are parsed; a bounded raw tail is attached for the rest.",
            "Look at one installed app's version, permissions and where it lives on the phone.",
            Adb,
            read,
            eng,
            schema_of::<PackageParams>,
            adb_app_show,
        ),
        spec(
            "adb_running_processes_list",
            "Running processes",
            "List running processes with `ps -A`, parsed into user, pid, ppid and name using the column header.",
            "See what is running on the phone right now.",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_running_processes_list,
        ),
        spec(
            "adb_folder_list",
            "Device folder",
            "List a folder on the device with `ls -la` (the path is single-quoted for the device shell). Raw lines are kept; a best-effort parse of name, size and permissions is attached.",
            "Look at the files in a folder on the phone.",
            Adb,
            read,
            eng,
            schema_of::<DirectoryParams>,
            adb_folder_list,
        ),
        spec(
            "adb_device_features_list",
            "Device features",
            "List hardware and software features the device reports with `pm list features`.",
            "See what the phone's hardware can do (camera, NFC, sensors…).",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_device_features_list,
        ),
        spec(
            "adb_system_services_list",
            "System services",
            "List registered system services with `service list`: index, name and the AIDL interface each exposes.",
            "See the phone's built-in system services.",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_system_services_list,
        ),
        spec(
            "adb_display_show",
            "Display info",
            "Read display state with `dumpsys display`. Key lines (display ids, real size, density, state) are surfaced; a bounded raw tail is attached.",
            "Find out about the phone's screen size and density.",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_display_show,
        ),
        spec(
            "adb_window_show",
            "Window / focus info",
            "Read window-manager state with `dumpsys window`. Focused window and app, and current activity lines are surfaced; a bounded raw tail is attached.",
            "See which app and screen is in front on the phone.",
            Adb,
            read,
            eng,
            schema_of::<SerialParams>,
            adb_window_show,
        ),
        spec(
            "adb_setting_get",
            "Read a setting",
            "Read one settings value with `settings get <namespace> <key>`. namespace system|secure|global; key is validated.",
            "Read one of the phone's settings.",
            Adb,
            read,
            eng,
            schema_of::<SettingParams>,
            adb_setting_get,
        ),
        spec(
            "adb_apps_find",
            "Find an app",
            "Find installed packages whose name contains a search term with `pm list packages <query>`.",
            "Search the phone's apps by name.",
            Adb,
            read,
            eng,
            schema_of::<ResolveParams>,
            adb_apps_find,
        ),
        spec(
            "adb_app_download",
            "Copy an app off the phone",
            "Copy an installed app's APK file(s) to a host folder: resolve paths with `pm path`, then `adb pull` each. output_directory must be absolute and must not exist yet; it is created fresh.",
            "Copy an app's installer file from the phone to your computer.",
            Adb,
            host_write,
            eng,
            schema_of::<PullPackageParams>,
            adb_app_download,
        ),
        spec(
            "adb_file_download",
            "Copy a file off the phone",
            "Copy a file or folder from the device to a host folder with `adb pull`. output_directory must be absolute and fresh.",
            "Copy a file from the phone to your computer.",
            Adb,
            host_write,
            eng,
            schema_of::<PullFileParams>,
            adb_file_download,
        ),
        spec(
            "adb_screenshot_take",
            "Screenshot",
            "Take a screenshot with `exec-out screencap -p` and write screen.png to a fresh host folder. output_directory must be absolute and must not exist yet.",
            "Take a picture of what's on the phone's screen.",
            Adb,
            host_write,
            eng,
            schema_of::<OutputDirParams>,
            adb_screenshot_take,
        ),
        spec(
            "adb_bugreport_save",
            "Bug report",
            "Collect a full bug report with `adb bugreport` into a fresh host folder (this can take minutes). output_directory must be absolute and must not exist yet.",
            "Gather a big diagnostic report from the phone (takes a while).",
            Adb,
            host_write,
            eng,
            schema_of::<OutputDirParams>,
            adb_bugreport_save,
        ),
        spec(
            "adb_file_upload",
            "Copy a file to the phone",
            "Copy a host file to the device with `adb push`. local_path is an absolute host file; device_path is an absolute device path. With overwrite=false the tool refuses if the device path already exists. Changes the device.",
            "Copy a file from your computer onto the phone.",
            Adb,
            device_write,
            eng,
            schema_of::<PushParams>,
            adb_file_upload,
        ),
        spec(
            "adb_app_install",
            "Install an app",
            "Install an APK on the device with `adb install` (replace=true adds -r). apk_path is an absolute host file. Changes the device.",
            "Install an app onto the phone from an installer file.",
            Adb,
            device_write,
            eng,
            schema_of::<InstallParams>,
            adb_app_install,
        ),
        spec(
            "adb_app_remove",
            "Remove an app",
            "Uninstall a package with `adb uninstall`. Changes the device.",
            "Remove an app from the phone.",
            Adb,
            device_write,
            eng,
            schema_of::<PackageParams>,
            adb_app_remove,
        ),
        spec(
            "adb_app_launch",
            "Launch an app",
            "Launch a package's default activity with `monkey -p <pkg> -c android.intent.category.LAUNCHER 1`. Changes the device (starts an app).",
            "Open an app on the phone.",
            Adb,
            device_write,
            eng,
            schema_of::<PackageParams>,
            adb_app_launch,
        ),
        spec(
            "adb_activity_open",
            "Start an activity",
            "Start an activity with `am start`: action (validated), optional data_uri (single-quoted), optional component (pkg/.Activity), and as many as 16 extras, each a text, true/false, whole or decimal number value. Changes the device.",
            "Open a specific screen in an app on the phone.",
            Adb,
            device_write,
            eng,
            schema_of::<ActivityParams>,
            adb_activity_open,
        ),
        spec(
            "adb_app_force_stop",
            "Force-stop an app",
            "Force-stop a package with `am force-stop`. Changes the device.",
            "Make an app on the phone stop running.",
            Adb,
            device_write,
            eng,
            schema_of::<PackageParams>,
            adb_app_force_stop,
        ),
    ]
}

// ------------------------------------------------------------------------------------------------
// Params

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct Empty {}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SerialParams {
    /// Device serial from adb_devices_find (e.g. emulator-5554).
    serial: String,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum PackageScope {
    #[default]
    All,
    ThirdParty,
    System,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ListPackagesParams {
    serial: String,
    #[serde(default)]
    scope: PackageScope,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum LogBuffer {
    #[default]
    Main,
    System,
    Radio,
    Events,
    Crash,
}

impl LogBuffer {
    fn name(self) -> &'static str {
        match self {
            LogBuffer::Main => "main",
            LogBuffer::System => "system",
            LogBuffer::Radio => "radio",
            LogBuffer::Events => "events",
            LogBuffer::Crash => "crash",
        }
    }
}

fn default_count() -> u32 {
    500
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct LogcatParams {
    serial: String,
    /// Number of recent lines (1..10000).
    #[serde(default = "default_count")]
    count: u32,
    #[serde(default)]
    buffer: LogBuffer,
    /// Only lines from this process id.
    #[serde(default)]
    pid: Option<u32>,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PackageParams {
    serial: String,
    /// Package name (e.g. com.example.app).
    package: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct DirectoryParams {
    serial: String,
    /// Absolute device path (e.g. /sdcard/Download).
    device_path: String,
}

#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum SettingNamespace {
    #[default]
    System,
    Secure,
    Global,
}

impl SettingNamespace {
    fn name(self) -> &'static str {
        match self {
            SettingNamespace::System => "system",
            SettingNamespace::Secure => "secure",
            SettingNamespace::Global => "global",
        }
    }
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct SettingParams {
    serial: String,
    #[serde(default)]
    namespace: SettingNamespace,
    /// Setting key (e.g. screen_brightness).
    key: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ResolveParams {
    serial: String,
    /// Substring to match against package names.
    query: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct OutputDirParams {
    serial: String,
    /// Absolute host folder that must not exist yet; it is created fresh.
    output_directory: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PullPackageParams {
    serial: String,
    package: String,
    output_directory: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PullFileParams {
    serial: String,
    device_path: String,
    output_directory: String,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct PushParams {
    serial: String,
    /// Absolute host file to copy.
    local_path: String,
    /// Absolute destination path on the device.
    device_path: String,
    /// Refuse if the device path already exists (default false → adb push overwrites).
    #[serde(default)]
    overwrite: bool,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct InstallParams {
    serial: String,
    /// Absolute host APK file.
    apk_path: String,
    /// Reinstall keeping data (adb install -r).
    #[serde(default = "default_true")]
    replace: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
enum ExtraType {
    String,
    Boolean,
    Int,
    Long,
    Float,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct Extra {
    key: String,
    #[serde(rename = "type")]
    ty: ExtraType,
    value: String,
}

#[derive(Debug, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct ActivityParams {
    serial: String,
    /// Intent action, e.g. android.intent.action.VIEW.
    #[serde(default)]
    action: Option<String>,
    /// Data URI (-d), single-quoted for the device shell.
    #[serde(default)]
    data_uri: Option<String>,
    /// Explicit component (-n), e.g. com.example.app/.MainActivity.
    #[serde(default)]
    component: Option<String>,
    /// Up to 16 typed intent extras.
    #[serde(default)]
    extras: Vec<Extra>,
}

// ------------------------------------------------------------------------------------------------
// Shared plumbing

/// Build an adb handle for the active settings, wiring cancellation and progress-friendly deadlines.
fn adb_for(ctx: &Ctx<'_>) -> Result<Adb, ToolError> {
    let s = &ctx.session.settings;
    let path = craft_anything_engines::locate("adb", &s.engines.tools, &s.engine_store_dir()).ok_or_else(|| {
        ToolError::new(ErrorCode::EngineMissing, "Android platform-tools (adb) isn't installed.")
            .with_remediation("Install it from Settings → Engines, or run engines_install with engine \"adb\".")
    })?;
    Ok(Adb::new(path).cancel(cancel_of(ctx)))
}

fn cancel_of(ctx: &Ctx<'_>) -> Cancel {
    let c = ctx.cancel.clone();
    Arc::new(move || c.is_cancelled())
}

fn device_env(ctx: &Ctx<'_>) -> Environment {
    Environment {
        clean_room: ctx.session.clean_room(),
        engine: "adb".into(),
        engine_version: None,
        host: craft_anything_evidence::host_triple(),
        language_id: None,
    }
}

fn device_subject(serial: &str) -> Subject {
    Subject { kind: "device".into(), sha256: None, name: Some(serial.to_string()) }
}

/// Start a device evidence record on the authority of the external service (the device).
fn dev_ev(ctx: &Ctx<'_>, op: &str, serial: &str, params: Value) -> EvidenceBuilder {
    EvidenceBuilder::new(op, device_subject(serial), device_env(ctx)).params(params).authority(Authority::OutsideService).confidence(Confidence::Observed)
}

/// Confirm the serial names a device that is present and online; otherwise a clear, never-hanging
/// error.
fn ensure_online(adb: &Adb, serial: &str) -> Result<Device, ToolError> {
    let devices = adb.devices()?;
    match devices.iter().find(|d| d.serial == serial) {
        Some(d) if d.is_online() => Ok(d.clone()),
        Some(d) if d.state == "unauthorized" => Err(ToolError::new(ErrorCode::NoPermission, format!("Device {serial} has not authorised this computer."))
            .with_remediation("On the phone, accept the \"Allow USB debugging\" prompt, then try again.")),
        Some(d) => Err(ToolError::new(ErrorCode::NotFound, format!("Device {serial} is {}, not ready.", d.state))
            .with_remediation("Wait for it to come online (unlock it / reconnect it), then try again.")),
        None => {
            let serials: Vec<&str> = devices.iter().map(|d| d.serial.as_str()).collect();
            Err(ToolError::new(ErrorCode::NotFound, format!("No device with serial {serial} is connected."))
                .with_remediation("List connected devices with adb_devices_find and use one of their serials.")
                .with_details(json!({"connected": serials})))
        }
    }
}

/// stdout of an `adb shell` command, or an error when nothing usable came back.
fn shell_text(adb: &Adb, serial: &str, line: &str, what: &str) -> Result<String, ToolError> {
    let out = adb.shell(serial, line)?;
    usable(out, what)
}

fn usable(out: Output, what: &str) -> Result<String, ToolError> {
    if out.success || !out.stdout.is_empty() {
        return Ok(out.stdout_text());
    }
    Err(exec_error(what, &out))
}

/// Build the "command produced nothing usable" error from a finished run.
fn exec_error(what: &str, out: &Output) -> ToolError {
    let tail = tail_text(&out.stderr_text());
    let msg = tail.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("no output").trim().to_string();
    ToolError::new(ErrorCode::ProgramFailed, format!("{what} failed: {msg}"))
        .with_remediation(format!("What adb printed last:\n{}", craft_anything_platform::process::output_excerpt(&tail)))
        .with_details(json!({"exit_code": out.code, "stderr_tail": tail}))
}

fn tail_text(s: &str) -> String {
    let n = s.chars().count();
    s.chars().skip(n.saturating_sub(2000)).collect()
}

/// The validated serial from params.
fn serial_of(s: &str) -> Result<&str, ToolError> {
    adb::validate_serial(s)
}

fn done(e: Evidence) -> Result<ToolOutput, ToolError> {
    Ok(ToolOutput::evidence(e))
}

/// A limitation noting that large text output is summarised, with a bounded raw tail attached.
fn passthrough_limitation(cmd: &str) -> Limitation {
    Limitation::new(
        "dumpsys_passthrough",
        format!("Only key fields of `{cmd}` are parsed; the rest is attached as a bounded raw tail (first ~16 KiB), not structured."),
    )
}

/// Keep at most `max` bytes of text (for raw-tail attachments).
fn clip(s: &str, max: usize) -> (String, bool) {
    if s.len() <= max {
        (s.to_string(), false)
    } else {
        let cut = s.char_indices().take_while(|(i, _)| *i < max).last().map(|(i, c)| i + c.len_utf8()).unwrap_or(0);
        (s.get(..cut).unwrap_or("").to_string(), true)
    }
}

// ------------------------------------------------------------------------------------------------
// Tools

fn engines_adb_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _: Empty = parse_params(params)?;
    let s = &ctx.session.settings;
    let found = craft_anything_engines::locate("adb", &s.engines.tools, &s.engine_store_dir());
    let mut lims = Vec::new();
    let (version, error) = match &found {
        Some(path) => match Adb::new(path.clone()).cancel(cancel_of(ctx)).timeout(Duration::from_secs(20)).version() {
            Ok(v) if !v.is_empty() => (Some(v), None),
            Ok(_) => (None, Some("adb did not report a version".to_string())),
            Err(e) => (None, Some(e.message)),
        },
        None => (None, None),
    };
    if let Some(e) = &error {
        lims.push(Limitation::new("version_probe_failed", format!("adb was found but reporting its version failed: {e}")));
    }
    let available = found.is_some() && error.is_none();
    let summary = match (&found, &version) {
        (Some(p), Some(v)) => format!("adb is available: {v} at {}.", p.display()),
        (Some(p), None) => format!("adb was found at {} but did not report a version.", p.display()),
        (None, _) => "adb is not installed. Install it from Settings → Engines, or run engines_install with engine \"adb\".".into(),
    };
    let e = EvidenceBuilder::new("engines_adb_check", Subject { kind: "engine".into(), sha256: None, name: Some("adb".into()) }, device_env(ctx))
        .params(json!({}))
        .authority(Authority::OurRun)
        .confidence(Confidence::Observed)
        .result(json!({
            "available": available,
            "path": found,
            "version": version,
            "error": error,
            "remediation": if available { None } else { Some("Install Android platform-tools, or run engines_install with engine \"adb\".") },
        }))
        .summary(summary)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_devices_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _: Empty = parse_params(params)?;
    let adb = adb_for(ctx)?;
    let devices = adb.devices()?;
    let online = devices.iter().filter(|d| d.is_online()).count();
    let summary = format!("{} device(s) attached, {online} online.", devices.len());
    let locations: Vec<Location> = devices.iter().map(|d| Location::new("device", &d.serial).with_label(d.state.clone())).collect();
    let e = EvidenceBuilder::new("adb_devices_find", Subject { kind: "engine".into(), sha256: None, name: Some("adb".into()) }, device_env(ctx))
        .params(json!({}))
        .authority(Authority::OutsideService)
        .confidence(Confidence::Observed)
        .result(json!({"devices": devices, "count": devices.len(), "online": online}))
        .summary(summary)
        .locations(locations)
        .coverage(Coverage::complete(devices.len() as u64))
        .build()?;
    done(e)
}

fn adb_device_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SerialParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, "getprop", "getprop")?;
    let props = adb::parse_getprop(&text);
    let mut whitelist = serde_json::Map::new();
    for key in adb::DEVICE_PROP_WHITELIST {
        if let Some(prop) = props.iter().find(|pr| pr.key == *key) {
            whitelist.insert((*key).to_string(), Value::String(prop.value.clone()));
        }
    }
    let model = whitelist.get("ro.product.model").and_then(Value::as_str).unwrap_or("?");
    let release = whitelist.get("ro.build.version.release").and_then(Value::as_str).unwrap_or("?");
    let sdk = whitelist.get("ro.build.version.sdk").and_then(Value::as_str).unwrap_or("?");
    let summary = format!("{model}, Android {release} (API {sdk}); {} properties read.", props.len());
    // Attach a bounded sample of all properties so nothing silently disappears.
    let sample: Vec<_> = props.iter().take(2000).collect();
    let e = dev_ev(ctx, "adb_device_show", serial, json!({"serial": serial}))
        .result(json!({"device": whitelist, "property_count": props.len(), "properties": sample}))
        .summary(summary)
        .coverage(Coverage::complete(props.len() as u64))
        .build()?;
    done(e)
}

fn adb_apps_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListPackagesParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let flag = match p.scope {
        PackageScope::All => "",
        PackageScope::ThirdParty => " -3",
        PackageScope::System => " -s",
    };
    let text = shell_text(&adb, serial, &format!("pm list packages{flag}"), "pm list packages")?;
    let pkgs = adb::parse_packages(&text);
    let e = dev_ev(ctx, "adb_apps_list", serial, json!({"serial": serial, "scope": p.scope}))
        .result(json!({"packages": pkgs, "count": pkgs.len(), "scope": p.scope}))
        .summary(format!("{} package(s).", pkgs.len()))
        .coverage(Coverage::complete(pkgs.len() as u64))
        .build()?;
    done(e)
}

fn adb_log_read(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: LogcatParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    if !(1..=10000).contains(&p.count) {
        return Err(ToolError::invalid("count must be between 1 and 10000"));
    }
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    // Build host-side argv (no device shell): logcat is an adb subcommand.
    let mut args: Vec<String> = vec![
        "-s".into(),
        serial.into(),
        "logcat".into(),
        "-d".into(),
        "-b".into(),
        p.buffer.name().into(),
        "-v".into(),
        "threadtime".into(),
        "-t".into(),
        p.count.to_string(),
    ];
    if let Some(pid) = p.pid {
        args.push("--pid".into());
        args.push(pid.to_string());
    }
    let out = adb.run(&args)?;
    let text = usable(out, "logcat")?;
    let lines = adb::parse_logcat(&text);
    let e = dev_ev(ctx, "adb_log_read", serial, json!({"serial": serial, "count": p.count, "buffer": p.buffer, "pid": p.pid}))
        .result(json!({"lines": lines, "count": lines.len(), "buffer": p.buffer.name(), "pid": p.pid}))
        .summary(format!("{} log line(s) from the {} buffer.", lines.len(), p.buffer.name()))
        .coverage(Coverage::complete(lines.len() as u64))
        .build()?;
    done(e)
}

/// Whether `dumpsys package <name>` describes `package`: it has that package's `Package [name]`
/// block. Android answers a missing one with "Unable to find package: <name>", which names it too (#235).
fn package_found(text: &str, package: &str) -> bool {
    text.contains(&format!("Package [{package}]"))
}

fn adb_app_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PackageParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let package = adb::validate_package(&p.package)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, &format!("dumpsys package {package}"), "dumpsys package")?;
    if !package_found(&text, package) {
        return Err(ToolError::new(ErrorCode::NotFound, format!("Package {package} is not installed on {serial}."))
            .with_remediation("List installed packages with adb_apps_list."));
    }
    let fields = grep_fields(
        &text,
        &[
            "versionName=",
            "versionCode=",
            "userId=",
            "firstInstallTime=",
            "lastUpdateTime=",
            "dataDir=",
            "codePath=",
            "primaryCpuAbi=",
            "targetSdk=",
            "minSdk=",
        ],
    );
    let perms = grep_section(&text, "requested permissions:", 400);
    let granted = grep_section(&text, "install permissions:", 400);
    let (raw, truncated) = clip(&text, 16 * 1024);
    let e = dev_ev(ctx, "adb_app_show", serial, json!({"serial": serial, "package": package}))
        .result(json!({
            "package": package,
            "fields": fields,
            "requested_permissions": perms,
            "install_permissions": granted,
            "raw_tail": raw,
            "raw_truncated": truncated,
        }))
        .summary(format!("Package {package}: {} field(s) parsed.", fields.len()))
        .limitation(passthrough_limitation("dumpsys package"))
        .location(Location::new("package", package))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_running_processes_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SerialParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, "ps -A", "ps -A")?;
    let rows = adb::parse_ps(&text);
    let e = dev_ev(ctx, "adb_running_processes_list", serial, json!({"serial": serial}))
        .result(json!({"processes": rows, "count": rows.len()}))
        .summary(format!("{} process(es).", rows.len()))
        .coverage(Coverage::complete(rows.len() as u64))
        .build()?;
    done(e)
}

fn adb_folder_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DirectoryParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let path = adb::validate_device_path(&p.device_path)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let line = format!("ls -la {}", adb::quote_device(path));
    let out = adb.shell(serial, &line)?;
    let text = out.stdout_text();
    let entries = parse_ls(&text);
    let (raw, truncated) = clip(&text, 16 * 1024);
    let summary = if out.success || !entries.is_empty() {
        format!("{} entries in {path}.", entries.len())
    } else {
        format!("Could not list {path} (it may not exist or be readable).")
    };
    let e = dev_ev(ctx, "adb_folder_list", serial, json!({"serial": serial, "device_path": path}))
        .result(json!({"path": path, "entries": entries, "count": entries.len(), "raw_tail": raw, "raw_truncated": truncated, "exit_code": out.code}))
        .summary(summary)
        .location(Location::new("path", path))
        .coverage(Coverage::complete(entries.len() as u64))
        .build()?;
    done(e)
}

fn adb_device_features_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SerialParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, "pm list features", "pm list features")?;
    let feats = adb::parse_features(&text);
    let e = dev_ev(ctx, "adb_device_features_list", serial, json!({"serial": serial}))
        .result(json!({"features": feats, "count": feats.len()}))
        .summary(format!("{} feature(s).", feats.len()))
        .coverage(Coverage::complete(feats.len() as u64))
        .build()?;
    done(e)
}

fn adb_system_services_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SerialParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, "service list", "service list")?;
    let svcs = adb::parse_services(&text);
    let e = dev_ev(ctx, "adb_system_services_list", serial, json!({"serial": serial}))
        .result(json!({"services": svcs, "count": svcs.len()}))
        .summary(format!("{} system service(s).", svcs.len()))
        .coverage(Coverage::complete(svcs.len() as u64))
        .build()?;
    done(e)
}

fn adb_display_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    dumpsys_tool(ctx, params, "display", &["mDisplayId", "DisplayDeviceInfo", "real ", "density", "mState", "FLAG_"])
}

fn adb_window_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    dumpsys_tool(ctx, params, "window", &["mCurrentFocus", "mFocusedApp", "mDisplayFrames", "imeLayeringTarget", "mInputMethodTarget"])
}

fn dumpsys_tool(ctx: &mut Ctx<'_>, params: Value, what: &'static str, needles: &[&str]) -> Result<ToolOutput, ToolError> {
    let p: SerialParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, &format!("dumpsys {what}"), &format!("dumpsys {what}"))?;
    let key_lines = grep_lines(&text, needles, 200);
    let (raw, truncated) = clip(&text, 16 * 1024);
    let op = if what == "display" { "adb_display_show" } else { "adb_window_show" };
    let e = dev_ev(ctx, op, serial, json!({"serial": serial}))
        .result(json!({"key_lines": key_lines, "raw_tail": raw, "raw_truncated": truncated}))
        .summary(format!("dumpsys {what}: {} key line(s).", key_lines.len()))
        .limitation(passthrough_limitation(&format!("dumpsys {what}")))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_setting_get(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SettingParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let key = adb::validate_dotted_key(&p.key, "setting key")?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let ns = p.namespace.name();
    let text = shell_text(&adb, serial, &format!("settings get {ns} {key}"), "settings get")?;
    let value = text.trim();
    let value = if value == "null" { Value::Null } else { Value::String(value.to_string()) };
    let e = dev_ev(ctx, "adb_setting_get", serial, json!({"serial": serial, "namespace": ns, "key": key}))
        .result(json!({"namespace": ns, "key": key, "value": value}))
        .summary(format!("{ns}/{key} = {value}"))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_apps_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ResolveParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let query = adb::validate_query(&p.query)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let text = shell_text(&adb, serial, &format!("pm list packages {}", adb::quote_device(query)), "pm list packages")?;
    let pkgs = adb::parse_packages(&text);
    let e = dev_ev(ctx, "adb_apps_find", serial, json!({"serial": serial, "query": query}))
        .result(json!({"query": query, "packages": pkgs, "count": pkgs.len()}))
        .summary(format!("{} package(s) match {query:?}.", pkgs.len()))
        .coverage(Coverage::complete(pkgs.len() as u64))
        .build()?;
    done(e)
}

fn adb_app_download(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PullPackageParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let package = adb::validate_package(&p.package)?;
    let outdir = create_absent_dir(&p.output_directory)?;
    let made = UnlessWritten::new(&outdir);
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(300)).idle_timeout(Duration::from_secs(120));
    ensure_online(&adb, serial)?;
    let path_text = shell_text(&adb, serial, &format!("pm path {package}"), "pm path")?;
    let device_paths: Vec<String> = path_text
        .lines()
        .filter_map(|l| l.trim().strip_prefix("package:"))
        .map(|s| s.trim().to_string())
        .filter(|s| adb::validate_device_path(s).is_ok())
        .collect();
    if device_paths.is_empty() {
        return Err(ToolError::new(ErrorCode::NotFound, format!("Could not find APK paths for {package} on {serial}."))
            .with_remediation("Check the package is installed with adb_apps_list."));
    }
    let mut pulled = Vec::new();
    for dp in &device_paths {
        ctx.cancel.check()?;
        let out = adb.targeted(serial, ["pull", dp.as_str(), &outdir.to_string_lossy()])?;
        if !out.success {
            return Err(pull_error(dp, &out));
        }
        pulled.push(dp.clone());
    }
    let written = list_dir_names(&outdir);
    let e = dev_ev(ctx, "adb_app_download", serial, json!({"serial": serial, "package": package, "output_directory": outdir.to_string_lossy()}))
        .result(json!({"package": package, "device_paths": device_paths, "pulled": pulled, "output_directory": outdir, "files": written}))
        .summary(format!("Pulled {} APK file(s) for {package} to {}.", pulled.len(), outdir.display()))
        .authority(Authority::OutsideService)
        .location(Location::new("path", outdir.to_string_lossy()))
        .limitation(Limitation::new(
            "not_verified",
            "The pulled APKs are copied as-is; their signatures are not verified by this tool (use android_package_show).",
        ))
        .coverage(Coverage::complete(pulled.len() as u64))
        .build()?;
    made.keep();
    done(e)
}

pub(crate) fn pull_error(path: &str, out: &Output) -> ToolError {
    ToolError::new(ErrorCode::ProgramFailed, format!("adb pull of {path} failed: {}", tail_text(&out.stderr_text()).trim())).with_remediation(format!(
        "Check the device path exists and is readable. To try it yourself, run:\nadb pull {}",
        craft_anything_platform::process::printable_command(std::ffi::OsStr::new(path), &[] as &[&str])
    ))
}

fn adb_file_download(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PullFileParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let path = adb::validate_device_path(&p.device_path)?;
    let outdir = create_absent_dir(&p.output_directory)?;
    let made = UnlessWritten::new(&outdir);
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(300)).idle_timeout(Duration::from_secs(120));
    ensure_online(&adb, serial)?;
    let out = adb.targeted(serial, ["pull", path, &outdir.to_string_lossy()])?;
    if !out.success {
        return Err(pull_error(path, &out));
    }
    let files = list_dir_names(&outdir);
    let e = dev_ev(ctx, "adb_file_download", serial, json!({"serial": serial, "device_path": path, "output_directory": outdir.to_string_lossy()}))
        .result(json!({"device_path": path, "output_directory": outdir, "files": files}))
        .summary(format!("Pulled {path} to {}.", outdir.display()))
        .authority(Authority::OutsideService)
        .location(Location::new("path", outdir.to_string_lossy()))
        .coverage(Coverage::complete(files.len() as u64))
        .build()?;
    made.keep();
    done(e)
}

fn adb_screenshot_take(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OutputDirParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let outdir = create_absent_dir(&p.output_directory)?;
    let made = UnlessWritten::new(&outdir);
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(60));
    ensure_online(&adb, serial)?;
    let out = adb.exec_out(serial, "screencap -p")?;
    if !out.success && out.stdout.is_empty() {
        return Err(exec_error("screencap", &out));
    }
    if out.stdout.len() < 8 || out.stdout.get(1..4) != Some(b"PNG") {
        return Err(ToolError::new(ErrorCode::GarbledOutput, "The screenshot did not come back as a PNG.")
            .with_remediation("Some devices block screen capture; try again or capture it on the device."));
    }
    let file = outdir.join("screen.png");
    write_atomic(&file, &out.stdout)?;
    let e = dev_ev(ctx, "adb_screenshot_take", serial, json!({"serial": serial, "output_directory": outdir.to_string_lossy()}))
        .result(json!({"file": file, "bytes": out.stdout.len()}))
        .summary(format!("Saved a {}-byte screenshot to {}.", out.stdout.len(), file.display()))
        .authority(Authority::OutsideService)
        .location(Location::new("path", file.to_string_lossy()))
        .coverage(Coverage::complete(1))
        .build()?;
    made.keep();
    done(e)
}

fn adb_bugreport_save(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OutputDirParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let outdir = create_absent_dir(&p.output_directory)?;
    let made = UnlessWritten::new(&outdir);
    // Bug reports can take minutes; keep a generous wall deadline but an idle deadline so a truly
    // stuck run still ends.
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(600)).idle_timeout(Duration::from_secs(180));
    ensure_online(&adb, serial)?;
    ctx.report(None, "collecting a bug report (this can take a few minutes)");
    let out = adb.targeted(serial, ["bugreport", &outdir.to_string_lossy()])?;
    let files = list_dir_names(&outdir);
    if !out.success && files.is_empty() {
        return Err(exec_error("bugreport", &out));
    }
    let e = dev_ev(ctx, "adb_bugreport_save", serial, json!({"serial": serial, "output_directory": outdir.to_string_lossy()}))
        .result(json!({"output_directory": outdir, "files": files, "stdout_tail": tail_text(&out.stdout_text())}))
        .summary(format!("Collected a bug report ({} file(s)) in {}.", files.len(), outdir.display()))
        .authority(Authority::OutsideService)
        .location(Location::new("path", outdir.to_string_lossy()))
        .coverage(Coverage::complete(files.len() as u64))
        .build()?;
    made.keep();
    done(e)
}

fn adb_file_upload(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PushParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let local = super::artifact_tools::abs_path(&p.local_path, "local_path")?;
    if !local.is_file() {
        return Err(ToolError::invalid(format!("{} is not a file", local.display())));
    }
    let device_path = adb::validate_device_path(&p.device_path)?;
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(300)).idle_timeout(Duration::from_secs(120));
    ensure_online(&adb, serial)?;
    if !p.overwrite {
        // `test -e PATH && echo EXISTS`
        let probe = shell_text(&adb, serial, &format!("( [ -e {} ] && echo EXISTS ) || echo ABSENT", adb::quote_device(device_path)), "test -e")?;
        if probe.contains("EXISTS") {
            return Err(ToolError::new(ErrorCode::BadInput, format!("{device_path} already exists on the device."))
                .with_remediation("Pass overwrite=true to replace it, or choose a different device path."));
        }
    }
    let out = adb.targeted(serial, ["push", &local.to_string_lossy(), device_path])?;
    if !out.success {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("adb push failed: {}", tail_text(&out.stderr_text()).trim()))
            .with_remediation("Check the destination folder exists and is writable on the device."));
    }
    let e = dev_ev(
        ctx,
        "adb_file_upload",
        serial,
        json!({"serial": serial, "local_path": local.to_string_lossy(), "device_path": device_path, "overwrite": p.overwrite}),
    )
    .result(json!({"local_path": local, "device_path": device_path, "stdout_tail": tail_text(&out.stdout_text())}))
    .summary(format!("Pushed {} to {device_path}.", local.display()))
    .limitation(Limitation::new("device_changed", "This wrote a file onto the device."))
    .location(Location::new("path", device_path))
    .coverage(Coverage::complete(1))
    .build()?;
    done(e)
}

fn adb_app_install(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InstallParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let apk = super::artifact_tools::abs_path(&p.apk_path, "apk_path")?;
    if !apk.is_file() {
        return Err(ToolError::invalid(format!("{} is not a file", apk.display())));
    }
    let adb = adb_for(ctx)?.timeout(Duration::from_secs(300)).idle_timeout(Duration::from_secs(120));
    ensure_online(&adb, serial)?;
    let apk_s = apk.to_string_lossy().into_owned();
    let args: Vec<&str> = if p.replace { vec!["install", "-r", &apk_s] } else { vec!["install", &apk_s] };
    let out = adb.targeted(serial, args)?;
    let combined = format!("{}{}", out.stdout_text(), out.stderr_text());
    if !out.success || !combined.contains("Success") {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("adb install failed: {}", tail_text(&combined).trim()))
            .with_remediation("The APK may be incompatible, unsigned for this device, or already installed; see the message."));
    }
    let e = dev_ev(ctx, "adb_app_install", serial, json!({"serial": serial, "apk_path": apk_s, "replace": p.replace}))
        .result(json!({"apk_path": apk, "replace": p.replace, "output": tail_text(&combined)}))
        .summary(format!("Installed {}.", apk.display()))
        .limitation(Limitation::new("device_changed", "This installed an app onto the device."))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_app_remove(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PackageParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let package = adb::validate_package(&p.package)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let out = adb.targeted(serial, ["uninstall", package])?;
    let combined = format!("{}{}", out.stdout_text(), out.stderr_text());
    if !out.success || !combined.contains("Success") {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("adb uninstall failed: {}", tail_text(&combined).trim()))
            .with_remediation("The app may not be installed, or may be a protected system app."));
    }
    let e = dev_ev(ctx, "adb_app_remove", serial, json!({"serial": serial, "package": package}))
        .result(json!({"package": package, "output": tail_text(&combined)}))
        .summary(format!("Uninstalled {package}."))
        .limitation(Limitation::new("device_changed", "This removed an app from the device."))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_app_launch(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PackageParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let package = adb::validate_package(&p.package)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let line = format!("monkey -p {package} -c android.intent.category.LAUNCHER 1");
    let out = adb.shell(serial, &line)?;
    let combined = format!("{}{}", out.stdout_text(), out.stderr_text());
    if combined.contains("No activities found") || combined.contains("Error") {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("Could not launch {package}: {}", tail_text(&combined).trim()))
            .with_remediation("The app may have no launcher activity; use adb_activity_open with an explicit component."));
    }
    let e = dev_ev(ctx, "adb_app_launch", serial, json!({"serial": serial, "package": package}))
        .result(json!({"package": package, "output": tail_text(&combined)}))
        .summary(format!("Launched {package}."))
        .limitation(Limitation::new("device_changed", "This started an app on the device."))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

fn adb_activity_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ActivityParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    if p.extras.len() > 16 {
        return Err(ToolError::invalid("at most 16 extras are allowed"));
    }
    if p.action.is_none() && p.component.is_none() {
        return Err(ToolError::invalid("pass at least one of action or component"));
    }
    let mut line = String::from("am start -W");
    if let Some(a) = &p.action {
        let a = adb::validate_dotted_key(a, "intent action")?;
        line.push_str(&format!(" -a {a}"));
    }
    if let Some(c) = &p.component {
        let c = adb::validate_component(c)?;
        line.push_str(&format!(" -n {c}"));
    }
    if let Some(d) = &p.data_uri {
        if d.len() > 4096 || d.bytes().any(|b| b == 0 || b == b'\n' || b == b'\r') {
            return Err(ToolError::invalid("data_uri is too long or has control characters"));
        }
        line.push_str(&format!(" -d {}", adb::quote_device(d)));
    }
    for ex in &p.extras {
        let key = adb::validate_dotted_key(&ex.key, "extra key")?;
        let frag = extra_fragment(key, ex.ty, &ex.value)?;
        line.push(' ');
        line.push_str(&frag);
    }
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let out = adb.shell(serial, &line)?;
    let combined = format!("{}{}", out.stdout_text(), out.stderr_text());
    if combined.contains("Error:") || combined.contains("Exception") {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("am start failed: {}", tail_text(&combined).trim()))
            .with_remediation("Check the action, component and extras are valid for the target app."));
    }
    let e = dev_ev(
        ctx,
        "adb_activity_open",
        serial,
        json!({"serial": serial, "action": p.action, "component": p.component, "data_uri": p.data_uri, "extras_count": p.extras.len()}),
    )
    .result(json!({"output": tail_text(&combined)}))
    .summary("Started the activity.".to_string())
    .limitation(Limitation::new("device_changed", "This started an activity on the device."))
    .coverage(Coverage::complete(1))
    .build()?;
    done(e)
}

fn extra_fragment(key: &str, ty: ExtraType, value: &str) -> Result<String, ToolError> {
    Ok(match ty {
        ExtraType::String => format!("--es {key} {}", adb::quote_device(value)),
        ExtraType::Boolean => {
            let b: bool = value.parse().map_err(|_| ToolError::invalid(format!("extra {key}: expected true/false, got {value:?}")))?;
            format!("--ez {key} {b}")
        }
        ExtraType::Int => {
            let n: i32 = value.parse().map_err(|_| ToolError::invalid(format!("extra {key}: expected an int, got {value:?}")))?;
            format!("--ei {key} {n}")
        }
        ExtraType::Long => {
            let n: i64 = value.parse().map_err(|_| ToolError::invalid(format!("extra {key}: expected a long, got {value:?}")))?;
            format!("--el {key} {n}")
        }
        ExtraType::Float => {
            let n: f64 = value.parse().map_err(|_| ToolError::invalid(format!("extra {key}: expected a float, got {value:?}")))?;
            if !n.is_finite() {
                return Err(ToolError::invalid(format!("extra {key}: value must be finite")));
            }
            format!("--ef {key} {n}")
        }
    })
}

fn adb_app_force_stop(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PackageParams = parse_params(params)?;
    let serial = serial_of(&p.serial)?;
    let package = adb::validate_package(&p.package)?;
    let adb = adb_for(ctx)?;
    ensure_online(&adb, serial)?;
    let out = adb.shell(serial, &format!("am force-stop {package}"))?;
    let combined = format!("{}{}", out.stdout_text(), out.stderr_text());
    if combined.contains("Error") || combined.contains("Exception") {
        return Err(ToolError::new(ErrorCode::ProgramFailed, format!("am force-stop failed: {}", tail_text(&combined).trim())));
    }
    let e = dev_ev(ctx, "adb_app_force_stop", serial, json!({"serial": serial, "package": package}))
        .result(json!({"package": package}))
        .summary(format!("Force-stopped {package}."))
        .limitation(Limitation::new("device_changed", "This stopped an app on the device."))
        .coverage(Coverage::complete(1))
        .build()?;
    done(e)
}

// ------------------------------------------------------------------------------------------------
// Light parsers for text that is otherwise passed through

/// Pull `name=value` fields out of dumpsys-style text (first occurrence of each).
fn grep_fields(text: &str, keys: &[&str]) -> serde_json::Map<String, Value> {
    let mut out = serde_json::Map::new();
    for line in text.lines().take(adb::MAX_LINES) {
        let line = line.trim();
        for key in keys {
            if out.contains_key(key.trim_end_matches('=')) {
                continue;
            }
            if let Some(idx) = line.find(key) {
                let after = line.get(idx + key.len()..).unwrap_or("");
                let value = after.split_whitespace().next().unwrap_or("").to_string();
                if !value.is_empty() {
                    out.insert(key.trim_end_matches('=').to_string(), Value::String(value));
                }
            }
        }
    }
    out
}

/// Collect the indented lines of a named section (e.g. "requested permissions:").
fn grep_section(text: &str, header: &str, max: usize) -> Vec<String> {
    let mut out = Vec::new();
    let mut in_section = false;
    let mut base_indent = 0usize;
    for line in text.lines().take(adb::MAX_LINES) {
        let indent = line.len() - line.trim_start().len();
        if !in_section {
            if line.trim() == header || line.trim_start() == header {
                in_section = true;
                base_indent = indent;
            }
            continue;
        }
        if line.trim().is_empty() {
            continue;
        }
        if indent <= base_indent {
            break;
        }
        out.push(line.trim().to_string());
        if out.len() >= max {
            break;
        }
    }
    out
}

/// Lines containing any of the needles (bounded).
fn grep_lines(text: &str, needles: &[&str], max: usize) -> Vec<String> {
    let mut out = Vec::new();
    for line in text.lines().take(adb::MAX_LINES) {
        if needles.iter().any(|n| line.contains(n)) {
            out.push(line.trim().to_string());
            if out.len() >= max {
                break;
            }
        }
    }
    out
}

/// A parsed `ls -la` entry (best effort; the raw text is always kept by the caller).
#[derive(Debug, Serialize)]
struct LsEntry {
    perms: String,
    size: Option<u64>,
    name: String,
}

fn parse_ls(text: &str) -> Vec<LsEntry> {
    let mut out = Vec::new();
    for line in text.lines().take(adb::MAX_LINES) {
        let line = line.trim();
        if line.is_empty() || line.starts_with("total ") {
            continue;
        }
        let fields: Vec<&str> = line.split_whitespace().collect();
        let Some(perms) = fields.first() else { continue };
        if perms.len() < 10 || !matches!(perms.as_bytes().first(), Some(b'-' | b'd' | b'l' | b'c' | b'b' | b'p' | b's')) {
            continue;
        }
        // toybox `ls -la`: perms links owner group size month day time name...
        let size = fields.get(4).and_then(|s| s.parse::<u64>().ok());
        let name = fields.get(7..).map(|s| s.join(" ")).filter(|s| !s.is_empty()).unwrap_or_default();
        out.push(LsEntry { perms: (*perms).to_string(), size, name });
    }
    out
}

fn list_dir_names(dir: &std::path::Path) -> Vec<String> {
    let mut out = Vec::new();
    if let Ok(rd) = std::fs::read_dir(dir) {
        for e in rd.flatten().take(10_000) {
            out.push(e.file_name().to_string_lossy().into_owned());
        }
    }
    out.sort();
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tools::native_common::test_support::call_err;
    use crate::{CallOptions, Caller, Engine, Session, Settings};

    /// An engine whose adb can never be located: an empty managed store and no override. In Deep
    /// mode, since Clean room refuses most adb tools before adb is looked for.
    fn engine_without_adb() -> (Engine, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let mut settings = Settings { deep_mode: true, ..Default::default() };
        settings.engines.store_dir = Some(dir.path().to_path_buf());
        settings.engines.tools = Default::default();
        (Engine::new(Session::new(settings)), dir)
    }

    fn adb_locatable(e: &Engine) -> bool {
        let s = e.session();
        craft_anything_engines::locate("adb", &s.settings.engines.tools, &s.settings.engine_store_dir()).is_some()
    }

    #[test]
    fn missing_adb_is_provider_unavailable() {
        let (e, _d) = engine_without_adb();
        // Only meaningful when adb is not on this machine's PATH either.
        if adb_locatable(&e) {
            return;
        }
        for id in ["adb_devices_find", "adb_device_show", "adb_log_read", "adb_file_download"] {
            let err = call_err(&e, id, json!({"serial": "emulator-5554", "device_path": "/sdcard", "output_directory": "/tmp/x", "count": 10}));
            assert_eq!(err.code, ErrorCode::EngineMissing, "{id} gave {:?}", err.code);
            assert!(err.remediation.is_some());
        }
    }

    /// #234: a call that fails before writing anything leaves no folder, so the same call can be
    /// tried again; a folder with something in it, or a kept one, stays.
    #[test]
    fn a_failed_call_leaves_its_output_folder_free() {
        let (e, d) = engine_without_adb();
        if !adb_locatable(&e) {
            for id in ["adb_screenshot_take", "adb_bugreport_save", "adb_file_download", "adb_app_download"] {
                let out = d.path().join(id);
                let args = json!({"serial": "emulator-5554", "package": "com.example.app", "device_path": "/sdcard/x", "output_directory": out});
                assert_eq!(call_err(&e, id, args.clone()).code, ErrorCode::EngineMissing, "{id}");
                assert!(!out.exists(), "{id} left {out:?} behind");
                assert_eq!(call_err(&e, id, args).code, ErrorCode::EngineMissing, "{id}: the retry was blocked");
            }
        }
        let (empty, written, kept) = (d.path().join("empty"), d.path().join("written"), d.path().join("kept"));
        for dir in [&empty, &written, &kept] {
            std::fs::create_dir(dir).unwrap();
        }
        std::fs::write(written.join("part"), b"x").unwrap();
        drop(UnlessWritten::new(&empty));
        drop(UnlessWritten::new(&written));
        UnlessWritten::new(&kept).keep();
        assert!(!empty.exists() && written.exists() && kept.exists());
    }

    #[test]
    fn inspect_client_never_needs_adb() {
        let (e, _d) = engine_without_adb();
        // engines_adb_check is Requires::Nothing: it answers even with no adb installed.
        let out = e.call("engines_adb_check", json!({}), CallOptions::new(Caller::Cli)).unwrap();
        let v = out.to_json();
        assert_eq!(v["result"]["available"], adb_locatable(&e));
    }

    #[test]
    fn bad_serial_is_rejected() {
        let (e, _d) = engine_without_adb();
        if adb_locatable(&e) {
            return;
        }
        // A hostile serial must be rejected regardless; when adb is missing the provider error
        // comes first, so test validation directly.
        assert!(adb::validate_serial("a; rm -rf /").is_err());
    }

    #[test]
    fn device_mutating_tools_need_consent() {
        // With adb present but no consent, a device-changing tool is refused before running.
        let (e, _d) = engine_without_adb();
        if !adb_locatable(&e) {
            // No adb → provider error precedes consent; the effect flags still mark it destructive.
            let spec = e.registry().get("adb_app_install").unwrap();
            assert!(spec.effects.needs_consent());
            assert!(e.registry().get("adb_activity_open").unwrap().effects.needs_consent());
            return;
        }
        let err = call_err(&e, "adb_app_install", json!({"serial": "emulator-5554", "apk_path": "/tmp/x.apk"}));
        assert!(matches!(err.code, ErrorCode::ConsentRequired | ErrorCode::NotFound | ErrorCode::EngineMissing));
    }

    /// #235: Android's reply for a missing package names it, and was read as the package.
    #[test]
    fn a_missing_package_is_not_found() {
        assert!(!package_found("Unable to find package: com.example.missing\n", "com.example.missing"));
        assert!(!package_found("Packages:\n  Package [com.example.other] (1a2b):\n", "com.example"));
        assert!(package_found("Packages:\n  Package [com.example.app] (1a2b3c):\n    versionName=1.0\n", "com.example.app"));
    }

    #[test]
    fn parsers_and_fragments() {
        let fields = grep_fields("  versionName=1.2.3 flags=0x1\n  versionCode=42 minSdk=21\n", &["versionName=", "versionCode=", "minSdk="]);
        assert_eq!(fields.get("versionName").and_then(Value::as_str), Some("1.2.3"));
        assert_eq!(fields.get("versionCode").and_then(Value::as_str), Some("42"));
        assert_eq!(fields.get("minSdk").and_then(Value::as_str), Some("21"));

        let ls = parse_ls("total 8\n-rw-rw-rw- 1 root root 1024 2024-01-01 12:00 file.txt\ndrwxr-xr-x 2 root root 4096 2024-01-01 12:00 dir\n");
        assert_eq!(ls.len(), 2);
        assert_eq!(ls[0].size, Some(1024));
        assert_eq!(ls[0].name, "file.txt");

        assert_eq!(extra_fragment("k", ExtraType::Boolean, "true").unwrap(), "--ez k true");
        assert_eq!(extra_fragment("k", ExtraType::Int, "5").unwrap(), "--ei k 5");
        assert!(extra_fragment("k", ExtraType::Int, "notnum").is_err());
        assert_eq!(extra_fragment("k", ExtraType::String, "a b").unwrap(), "--es k 'a b'");
    }
}
