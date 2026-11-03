//! Electron fuses: the build-time switches Electron stores as a small "fuse wire" inside its main
//! executable (Windows/Linux) or the Electron Framework binary (macOS). The wire follows a public
//! sentinel string: one version byte, one length byte, then one byte per fuse (`0` disabled,
//! `1` enabled, `r` removed). Files are streamed, never loaded whole, and never modified or run.

use super::native_common::{hex, params_json, spec};
use super::static_input::builder;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Location, Subject, ToolError};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "js_electron_fuses_show",
        "Electron fuses",
        "Read the Electron fuse wire from a packaged Electron app without running it: pass the main executable (Windows .exe, Linux binary), the macOS .app bundle or Electron Framework binary, or the app's folder. Reports each wire's file offset, version and declared length, and every fuse by index with its name (RunAsNode, EnableCookieEncryption, EnableNodeOptionsEnvironmentVariable, EnableNodeCliInspectArguments, EnableEmbeddedAsarIntegrityValidation, OnlyLoadAppFromAsar, LoadBrowserProcessSpecificV8Snapshot, GrantFileProtocolExtraPrivileges, WasmTrapHandlers), state (enabled, disabled, removed), raw byte, what that state means for security, and whether it is the hardened setting. No sentinel means the fuse state is unknown.",
        "See which security switches (fuses) an Electron app was built with.",
        Toolset::Javascript,
        Effects::EVIDENCE,
        Requires::Nothing,
        schema_of::<FuseParams>,
        js_electron_fuses_show,
    )]
}

/// The publicly documented marker that precedes the fuse wire.
const SENTINEL: &[u8] = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX";
/// Most wires reported per file (a universal binary has one per slice).
const MAX_WIRES: usize = 16;
/// Most files examined in a folder.
const MAX_FILES: usize = 32;
const CHUNK: usize = 8 << 20;

/// Version-1 fuses in wire order: (name, effect when enabled, effect when disabled, hardened state).
const FUSES_V1: &[(&str, &str, &str, Option<bool>)] = &[
    (
        "RunAsNode",
        "ELECTRON_RUN_AS_NODE is honoured: anyone who can start the app can make it run arbitrary JavaScript as plain Node.js under the app's identity.",
        "ELECTRON_RUN_AS_NODE is ignored; the app cannot be turned into a plain Node.js runner.",
        Some(false),
    ),
    (
        "EnableCookieEncryption",
        "The cookie store on disk is encrypted with an operating-system key.",
        "Cookies are stored on disk without Electron's OS-key encryption.",
        Some(true),
    ),
    (
        "EnableNodeOptionsEnvironmentVariable",
        "NODE_OPTIONS and NODE_EXTRA_CA_CERTS are honoured: the environment can preload code or add trusted certificate authorities.",
        "NODE_OPTIONS and NODE_EXTRA_CA_CERTS are ignored.",
        Some(false),
    ),
    (
        "EnableNodeCliInspectArguments",
        "--inspect / --inspect-brk and SIGUSR1 are honoured: a debugger can attach to the main process.",
        "Inspector flags are ignored, so a debugger cannot be attached to the main process with --inspect.",
        Some(false),
    ),
    (
        "EnableEmbeddedAsarIntegrityValidation",
        "app.asar is checked against a hash embedded in the app (macOS and Windows) before it is loaded.",
        "app.asar is loaded without integrity validation; edits to it are not detected.",
        Some(true),
    ),
    (
        "OnlyLoadAppFromAsar",
        "App code is loaded only from app.asar; an app/ folder or default_app.asar next to it is not used.",
        "Electron also looks for an app/ folder and default_app.asar, so code placed there can be loaded instead.",
        Some(true),
    ),
    (
        "LoadBrowserProcessSpecificV8Snapshot",
        "The main process starts from its own V8 snapshot (browser_v8_context_snapshot.bin).",
        "The main process uses the shared V8 snapshot.",
        None,
    ),
    (
        "GrantFileProtocolExtraPrivileges",
        "Pages loaded from file:// get privileges beyond what a normal browser gives them.",
        "file:// pages are treated like in a normal browser, without extra privileges.",
        Some(false),
    ),
    (
        "WasmTrapHandlers",
        "V8 may use signal handlers to catch out-of-bounds WebAssembly memory access (64-bit systems).",
        "WebAssembly bounds are checked explicitly instead of with signal handlers.",
        None,
    ),
];

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FuseParams {
    /// Absolute path of the Electron executable, macOS .app bundle, Electron Framework binary or app folder; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Debug, Serialize)]
struct Fuse {
    index: usize,
    name: Option<&'static str>,
    /// enabled, disabled, removed or unknown
    state: &'static str,
    raw_byte: u8,
    meaning: Option<&'static str>,
    /// Whether this is the more locked-down setting; null when neither is.
    hardened: Option<bool>,
}

#[derive(Debug, Serialize)]
struct Wire {
    file: PathBuf,
    sentinel_offset: u64,
    sentinel_offset_hex: String,
    wire_version: Option<u8>,
    declared_length: Option<u8>,
    fuses: Vec<Fuse>,
    /// The file ended before the declared number of fuse bytes.
    truncated: bool,
}

/// Decode the bytes that follow a sentinel.
fn decode_wire(file: &Path, at: u64, after: &[u8]) -> Wire {
    let version = after.first().copied();
    let len = after.get(1).copied();
    let body = after.get(2..2 + usize::from(len.unwrap_or(0))).or_else(|| after.get(2..)).unwrap_or(&[]);
    let fuses = body
        .iter()
        .enumerate()
        .map(|(index, &raw)| {
            let known = if version == Some(1) { FUSES_V1.get(index) } else { None };
            let state = match raw {
                b'1' => "enabled",
                b'0' => "disabled",
                b'r' => "removed",
                _ => "unknown",
            };
            let meaning = known.and_then(|k| match state {
                "enabled" => Some(k.1),
                "disabled" => Some(k.2),
                "removed" => Some("Removed from this build: the setting no longer exists and flipping the byte has no effect."),
                _ => None,
            });
            let hardened = known.and_then(|k| k.3).and_then(|want_on| match state {
                "enabled" => Some(want_on),
                "disabled" => Some(!want_on),
                _ => None,
            });
            Fuse { index, name: known.map(|k| k.0), state, raw_byte: raw, meaning, hardened }
        })
        .collect::<Vec<_>>();
    Wire {
        file: file.to_path_buf(),
        sentinel_offset: at,
        sentinel_offset_hex: hex(at),
        wire_version: version,
        declared_length: len,
        truncated: len.is_none_or(|n| fuses.len() < usize::from(n)),
        fuses,
    }
}

/// Every wire in `file`, streaming it in chunks so large executables never sit in memory.
fn scan_file(file: &Path, cancelled: &dyn Fn() -> bool) -> Result<Vec<Wire>, ToolError> {
    let mut f = std::fs::File::open(file).map_err(|e| ToolError::io(file.display(), e))?;
    let mut offsets = Vec::new();
    let mut buf = vec![0u8; CHUNK + SENTINEL.len()];
    let mut carry = 0usize;
    let mut base = 0u64; // file offset of buf[0]
    loop {
        if cancelled() {
            return Err(ToolError::cancelled());
        }
        let n = f.read(buf.get_mut(carry..).unwrap_or(&mut [])).map_err(|e| ToolError::io(file.display(), e))?;
        if n == 0 {
            break;
        }
        let filled = carry + n;
        let hay = buf.get(..filled).unwrap_or(&[]);
        let mut i = 0usize;
        while let Some(p) = craft_anything_formats::find_bytes(hay.get(i..).unwrap_or(&[]), SENTINEL, usize::MAX) {
            offsets.push(base + (i + p) as u64);
            i += p + 1;
            if offsets.len() >= MAX_WIRES {
                break;
            }
        }
        if offsets.len() >= MAX_WIRES {
            break;
        }
        // Keep the tail so a sentinel split across reads is still found.
        let keep = filled.min(SENTINEL.len() - 1);
        buf.copy_within(filled - keep..filled, 0);
        base += (filled - keep) as u64;
        carry = keep;
    }
    let mut wires = Vec::new();
    for at in offsets {
        let mut after = vec![0u8; 2 + 255];
        f.seek(SeekFrom::Start(at + SENTINEL.len() as u64)).map_err(|e| ToolError::io(file.display(), e))?;
        let mut got = 0usize;
        while got < after.len() {
            match f.read(after.get_mut(got..).unwrap_or(&mut [])) {
                Ok(0) => break,
                Ok(k) => got += k,
                Err(e) => return Err(ToolError::io(file.display(), e)),
            }
        }
        after.truncate(got);
        wires.push(decode_wire(file, at, &after));
    }
    Ok(wires)
}

/// The files to examine for a path: the file itself; for a macOS bundle or framework the
/// Electron Framework binary; for any other folder its top-level executables.
fn candidates(path: &Path) -> Vec<PathBuf> {
    if path.is_file() {
        return vec![path.to_path_buf()];
    }
    let fw =
        if path.extension().is_some_and(|e| e == "framework") { path.to_path_buf() } else { path.join("Contents/Frameworks/Electron Framework.framework") };
    if fw.is_dir() {
        let picks = [fw.join("Electron Framework"), fw.join("Versions/Current/Electron Framework"), fw.join("Versions/A/Electron Framework")];
        if let Some(p) = picks.into_iter().find(|p| p.is_file()) {
            return vec![p];
        }
    }
    let Ok(rd) = std::fs::read_dir(path) else { return Vec::new() };
    let mut out: Vec<PathBuf> = rd
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| {
            let exe_like = match p.extension().and_then(|e| e.to_str()) {
                None => true,
                Some(e) => e.eq_ignore_ascii_case("exe"),
            };
            exe_like && std::fs::metadata(p).is_ok_and(|m| m.is_file() && m.len() >= 1 << 20)
        })
        .collect();
    out.sort();
    out.truncate(MAX_FILES);
    out
}

fn js_electron_fuses_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: FuseParams = parse_params(params)?;
    let (path, subject) = match &p.path {
        Some(s) => {
            let pb = PathBuf::from(s);
            if !pb.is_absolute() {
                return Err(ToolError::invalid(format!("{s:?} is not an absolute path"))
                    .with_remediation("Pass the full path, for example C:\\Program Files\\App\\App.exe."));
            }
            if !pb.exists() {
                return Err(ToolError::invalid(format!("{s} does not exist")));
            }
            let name = pb.file_name().map(|n| n.to_string_lossy().into_owned());
            (pb, Subject { kind: "electron".into(), sha256: None, name })
        }
        None => {
            let t = &ctx.session.active().map_err(|e| e.with_remediation("Open the app first, or pass path."))?.target;
            (t.path.clone(), t.subject())
        }
    };
    let files = candidates(&path);
    if files.is_empty() {
        return Err(ToolError::invalid(format!("no executable to examine in {}", path.display()))
            .with_remediation("Pass the app's main executable, or a macOS .app bundle."));
    }
    let mut wires = Vec::new();
    let mut examined = Vec::new();
    for f in &files {
        ctx.report(None, format!("Looking for the fuse wire in {}", f.display()));
        let cancel = ctx.cancel.clone();
        wires.extend(scan_file(f, &|| cancel.is_cancelled())?);
        examined.push(f.clone());
    }

    let summary = match wires.first() {
        None => format!("No Electron fuse wire found in {} file(s): the fuse state is unknown (not an Electron build, or a very old one).", examined.len()),
        Some(w) => {
            let list: Vec<String> =
                w.fuses.iter().map(|f| format!("{} {}", f.name.map(str::to_string).unwrap_or_else(|| format!("fuse #{}", f.index)), f.state)).collect();
            let hardened = w.fuses.iter().filter(|f| f.hardened == Some(true)).count();
            let rated = w.fuses.iter().filter(|f| f.hardened.is_some()).count();
            format!(
                "Fuse wire v{} in {}: {}. {hardened} of {rated} security-relevant fuses are in the hardened state{}.",
                w.wire_version.unwrap_or(0),
                w.file.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(),
                list.join(", "),
                if wires.len() > 1 { format!(" ({} wires found in total)", wires.len()) } else { String::new() }
            )
        }
    };
    let mut lims =
        vec![Limitation::new("build_time_state", "Fuses are read from the file on disk; they show what the build allows, not what a running copy is doing.")];
    if wires.is_empty() {
        lims.push(Limitation::new("sentinel_missing", "Without the sentinel the fuse state is unknown; this is not proof that every fuse is at its default."));
    }
    if wires.iter().any(|w| w.wire_version != Some(1)) {
        lims.push(Limitation::new("unknown_wire_version", "A wire with a version other than 1 was found; its fuses keep their raw bytes but no names."));
    }
    if wires.len() > 1 {
        lims.push(Limitation::new(
            "several_wires",
            "More than one wire was found (for example one per slice of a universal macOS binary); each is listed with its file offset.",
        ));
    }
    let mut b = builder(ctx, "js_electron_fuses_show", subject, params_json(&p))
        .result(json!({"selected_path": path, "examined_files": examined, "sentinel_count": wires.len(), "wires": wires}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::complete(examined.len() as u64));
    for w in &wires {
        b = b.location(Location::new("file_offset", hex(w.sentinel_offset)).with_label(w.file.display().to_string()));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use super::SENTINEL;
    use crate::Engine;
    use serde_json::json;

    fn exe(wire: &[u8]) -> Vec<u8> {
        let mut d = vec![0x90u8; (1 << 20) + 5];
        d.extend(SENTINEL);
        d.extend(wire);
        d.extend(b"tail");
        d
    }

    #[test]
    fn reads_a_v1_wire_from_a_file_and_a_folder() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("App.exe", &exe(b"\x01\x09010110r01"));
        let v = call(&e, "js_electron_fuses_show", json!({"path": p}));
        let w = &v["result"]["wires"][0];
        assert_eq!(v["result"]["sentinel_count"], 1);
        assert_eq!(w["sentinel_offset"], (1 << 20) + 5);
        assert_eq!(w["wire_version"], 1);
        assert_eq!(w["declared_length"], 9);
        assert_eq!(w["truncated"], false);
        let f = w["fuses"].as_array().unwrap();
        assert_eq!(f.len(), 9);
        assert_eq!(f[0]["name"], "RunAsNode");
        assert_eq!(f[0]["state"], "disabled");
        assert_eq!(f[0]["hardened"], true);
        assert_eq!(f[3]["name"], "EnableNodeCliInspectArguments");
        assert_eq!(f[3]["state"], "enabled");
        assert_eq!(f[3]["hardened"], false);
        assert_eq!(f[6]["state"], "removed");
        assert!(f[6]["hardened"].is_null());
        assert_eq!(f[8]["name"], "WasmTrapHandlers");
        assert!(v["summary"].as_str().unwrap().contains("RunAsNode disabled"));

        // The folder holding the executable finds the same wire.
        let dir = p.parent().unwrap().to_string_lossy().into_owned();
        let v = call(&e, "js_electron_fuses_show", json!({"path": dir}));
        assert!(v["result"]["sentinel_count"].as_u64().unwrap() >= 1);
    }

    #[test]
    fn missing_sentinel_unknown_version_and_truncation() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("plain.bin", &[0u8; 64]);
        let v = call(&e, "js_electron_fuses_show", json!({"path": p}));
        assert_eq!(v["result"]["sentinel_count"], 0);
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "sentinel_missing"));

        let mut d = vec![0u8; 10];
        d.extend(SENTINEL);
        d.extend(b"\x02\x0501");
        let p = craft_anything_testkit::temp_file("v2.bin", &d);
        let v = call(&e, "js_electron_fuses_show", json!({"path": p}));
        let w = &v["result"]["wires"][0];
        assert_eq!(w["truncated"], true);
        assert!(w["fuses"][0]["name"].is_null());
        call_err(&e, "js_electron_fuses_show", json!({"path": "relative/app.exe"}));
    }
}
