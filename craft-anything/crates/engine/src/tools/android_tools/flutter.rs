//! Flutter builds: which Flutter libraries an APK ships per ABI, the Dart snapshot version hash,
//! stated Dart versions and toolchains (`android_flutter_identify`), and a look inside a Dart AOT
//! library: snapshot symbols and headers plus the app's package URIs and identifier tokens
//! (`android_dart_snapshot_show`). Built-in parsers only.

use crate::target::MAX_TARGET_BYTES;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::tools::native_common::{page, spec};
use crate::tools::static_input::{Input, builder, format_err, load};
use craft_anything_evidence::{Authority, Confidence, Coverage, ErrorCode, Limitation, Location, ToolError, sha256_hex};
use craft_anything_formats::{dart, zip};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Most bytes read from one library.
const MAX_LIBRARY: u64 = 256 << 20;
/// Most bytes read from all libraries together.
const MAX_CUMULATIVE: u64 = 768 << 20;
const MAX_CANDIDATES: usize = 64;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "android_flutter_identify",
            "Identify a Flutter build",
            "For an APK (or one Flutter library): which ABIs ship libapp.so/libflutter.so, the Dart snapshot version hash (null with candidates when libraries disagree), Dart versions and toolchains the binaries state, GNU build ids, and the size and SHA-256 of each libflutter.so. Built-in parser.",
            "Check whether an Android app is built with Flutter and which engine build it uses.",
            Toolset::Android,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<IdentifyParams>,
            android_flutter_identify,
        ),
        spec(
            "android_dart_snapshot_show",
            "Inspect a Dart AOT snapshot",
            "Read a Flutter app's compiled Dart library (libapp.so, from an APK or directly): the dynamic symbols for the VM and isolate snapshots (from section headers or, for stripped images, PT_DYNAMIC with DT_HASH/DT_GNU_HASH), snapshot headers (kind, version hash, features), and a byte scan of the isolate snapshot for package:/dart: URIs and identifier tokens (tokens paged with offset/limit).",
            "Peek inside a Flutter app's compiled Dart code to see its packages and names.",
            Toolset::Android,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<DartAotParams>,
            android_dart_snapshot_show,
        ),
    ]
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct IdentifyParams {
    /// Absolute path of an APK (or a libapp.so / libflutter.so); the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

fn d_limit() -> usize {
    500
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DartAotParams {
    /// Absolute path of an APK or a libapp.so; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// ABI folder to read from an APK (e.g. arm64-v8a); by default arm64-v8a, x86_64, x86, then armeabi-v7a.
    #[serde(default)]
    pub abi: Option<String>,
    /// First identifier token of the page.
    #[serde(default)]
    pub offset: usize,
    /// Identifier tokens per page (1..=2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

/// One Flutter library found in a package.
struct Lib {
    abi: String,
    role: &'static str,
    entry: Option<zip::ZipEntry>,
}

/// The Flutter libraries in the input and whether it is a package (ZIP).
fn libraries(input: &Input) -> Result<(Vec<Lib>, bool), ToolError> {
    let data = &input.bytes[..];
    if zip::looks_like_zip(data) {
        let z = zip::parse(data, 200_000).map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("Couldn't read this package: {e}")))?;
        let mut libs: Vec<Lib> = Vec::new();
        for e in z.entries {
            if let Some((abi, role)) = dart::flutter_library(&e.name).map(|(a, r)| (a.to_string(), r)) {
                libs.push(Lib { abi, role, entry: Some(e) });
            }
        }
        libs.sort_by(|a, b| (dart::abi_rank(&a.abi), &a.abi, a.role).cmp(&(dart::abi_rank(&b.abi), &b.abi, b.role)));
        Ok((libs, true))
    } else if data.starts_with(b"\x7fELF") {
        let role = if input.name.to_ascii_lowercase().contains("flutter") { "libflutter" } else { "libapp" };
        Ok((vec![Lib { abi: "unknown".into(), role, entry: None }], false))
    } else {
        Err(ToolError::unsupported(format!("{} is neither an APK nor an ELF library", input.name))
            .with_remediation("Pass an Android package (.apk) or a Flutter library such as lib/arm64-v8a/libapp.so."))
    }
}

fn read_lib(input: &Input, lib: &Lib, budget: &mut u64) -> Result<Vec<u8>, String> {
    match &lib.entry {
        None => Ok(input.bytes.to_vec()),
        Some(e) => {
            if e.uncompressed_size > MAX_LIBRARY {
                return Err(format!("{} is {} bytes; the per-library limit is {MAX_LIBRARY}", e.name, e.uncompressed_size));
            }
            if e.uncompressed_size > *budget {
                return Err(format!("{}: the {MAX_CUMULATIVE}-byte reading budget is used up", e.name));
            }
            let b = zip::read_entry(&input.bytes, e, MAX_LIBRARY).map_err(|err| format!("{}: {err}", e.name))?;
            *budget = budget.saturating_sub(b.len() as u64);
            Ok(b)
        }
    }
}

fn android_flutter_identify(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: IdentifyParams = parse_params(params)?;
    let input = load(ctx, p.path.as_deref(), MAX_TARGET_BYTES)?;
    let (libs, _) = libraries(&input)?;
    let mut budget = MAX_CUMULATIVE;
    let mut abis: BTreeMap<String, serde_json::Map<String, Value>> = BTreeMap::new();
    let mut hashes: Vec<String> = Vec::new();
    let mut hashes_truncated = false;
    let mut versions: Vec<String> = Vec::new();
    let mut toolchains: Vec<String> = Vec::new();
    let mut skipped = Vec::new();
    for (i, lib) in libs.iter().enumerate() {
        ctx.cancel.check()?;
        ctx.report(Some(i as f32 / libs.len().max(1) as f32), format!("reading {} for {}", lib.role, lib.abi));
        let bytes = match read_lib(&input, lib, &mut budget) {
            Ok(b) => b,
            Err(r) => {
                skipped.push(json!({"abi": lib.abi, "library": lib.role, "reason": r}));
                continue;
            }
        };
        let scan = dart::scan_library(&bytes, MAX_CANDIDATES);
        for h in &scan.snapshot_hashes {
            if !hashes.contains(h) {
                if hashes.len() < MAX_CANDIDATES {
                    hashes.push(h.clone());
                } else {
                    hashes_truncated = true;
                }
            }
        }
        hashes_truncated |= scan.hashes_truncated;
        for v in &scan.dart_versions {
            if !versions.contains(v) {
                versions.push(v.clone());
            }
        }
        for t in &scan.toolchains {
            if !toolchains.contains(t) {
                toolchains.push(t.clone());
            }
        }
        let mut info = json!({
            "path": lib.entry.as_ref().map(|e| e.name.clone()).unwrap_or_else(|| input.name.clone()),
            "size": bytes.len(),
            "sha256": sha256_hex(&bytes),
            "build_id": scan.build_id,
        });
        if lib.role == "libapp" {
            info["snapshot_hashes"] = json!(scan.snapshot_hashes);
            info["snapshot_occurrences"] = json!(scan.snapshot_occurrences);
        } else {
            info["dart_versions"] = json!(scan.dart_versions);
            info["toolchains"] = json!(scan.toolchains);
        }
        abis.entry(lib.abi.clone()).or_default().insert(lib.role.to_string(), info);
    }
    let detected = libs.iter().any(|l| l.role == "libapp");
    let snapshot_hash = if hashes.len() == 1 && !hashes_truncated { hashes.first().cloned() } else { None };
    let preferred = libs.iter().find(|l| l.role == "libapp").map(|l| l.abi.clone());
    let abi_list: Vec<Value> = abis.iter().map(|(abi, m)| json!({"abi": abi, "libapp": m.get("libapp"), "libflutter": m.get("libflutter")})).collect();
    let summary = if detected {
        format!(
            "Flutter app: libapp.so for {} ABI(s){}; snapshot hash {}{}.",
            abis.values().filter(|m| m.contains_key("libapp")).count(),
            preferred.as_deref().map(|a| format!(" (preferred {a})")).unwrap_or_default(),
            snapshot_hash.as_deref().unwrap_or(if hashes.is_empty() { "not found" } else { "ambiguous" }),
            versions.first().map(|v| format!("; Dart {v}")).unwrap_or_default()
        )
    } else if libs.is_empty() {
        format!("No Flutter libraries (lib/<abi>/libapp.so or libflutter.so) in {}.", input.name)
    } else {
        "libflutter.so is present but no libapp.so: the Flutter engine ships without compiled app code here.".to_string()
    };
    let mut lims = vec![
        Limitation::new(
            "no_version_table",
            "Dart and Flutter versions are reported only when a binary states them; snapshot hashes are not mapped to SDK versions.",
        ),
        Limitation::new(
            "absence_not_proof",
            "Not finding a library or string here does not prove the app lacks it (it may be downloaded, split or obfuscated).",
        ),
    ];
    if !hashes.is_empty() && snapshot_hash.is_none() {
        lims.push(Limitation::new("ambiguous_snapshot_hash", format!("{} different snapshot hashes were found; see snapshot_hash_candidates", hashes.len())));
    }
    if !skipped.is_empty() {
        lims.push(Limitation::new("libraries_skipped", format!("{} librar(ies) were not read; see skipped", skipped.len())));
    }
    let examined = libs.len().saturating_sub(skipped.len()) as u64;
    let ev = builder(ctx, "android_flutter_identify", input.subject.clone(), json!({"path": input.path}))
        .result(json!({
            "flutter_detected": detected,
            "preferred_abi": preferred,
            "snapshot_hash": snapshot_hash,
            "snapshot_hash_candidates": hashes,
            "candidates_truncated": hashes_truncated,
            "dart_versions": versions,
            "toolchains": toolchains,
            "abis": abi_list,
            "skipped": skipped,
        }))
        .summary(summary)
        .confidence(if detected { Confidence::Observed } else { Confidence::Inferred })
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(if skipped.is_empty() { Coverage::complete(examined) } else { Coverage::page(examined, libs.len() as u64, 0) })
        .location(Location::new("path", input.path.display().to_string()))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn valid_abi(a: &str) -> bool {
    (2..=16).contains(&a.len()) && a.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

fn android_dart_snapshot_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DartAotParams = parse_params(params)?;
    if let Some(a) = &p.abi
        && !valid_abi(a)
    {
        return Err(ToolError::invalid(format!("abi {a:?} must be 2-16 characters of a-z, 0-9, _ or -")));
    }
    if !(1..=2000).contains(&p.limit) {
        return Err(ToolError::invalid("limit must be 1..=2000"));
    }
    let input = load(ctx, p.path.as_deref(), MAX_TARGET_BYTES)?;
    let (libs, is_package) = libraries(&input)?;
    let apps: Vec<&Lib> = libs.iter().filter(|l| l.role == "libapp" || !is_package).collect();
    let chosen = match &p.abi {
        Some(a) if is_package => apps.iter().find(|l| &l.abi == a).copied().ok_or_else(|| {
            ToolError::invalid(format!("no lib/{a}/libapp.so in {}", input.name))
                .with_details(json!({"available_abis": apps.iter().map(|l| l.abi.clone()).collect::<Vec<_>>()}))
                .with_remediation("Pick one of available_abis, or omit abi.")
        })?,
        _ => apps.first().copied().ok_or_else(|| {
            ToolError::new(ErrorCode::NotSupported, format!("{} has no Flutter app library (lib/<abi>/libapp.so)", input.name))
                .with_remediation("Run android_flutter_identify to check whether this is a Flutter app.")
        })?,
    };
    let mut budget = MAX_CUMULATIVE;
    let bytes = read_lib(&input, chosen, &mut budget).map_err(|r| ToolError::new(ErrorCode::OverLimit, r))?;
    ctx.cancel.check()?;
    let aot = dart::inspect_aot(&bytes, 500, 2000).map_err(|e| format_err(e, "an ELF library"))?;
    // The engine library next to it often states the Dart version.
    let mut versions = aot.dart_versions.clone();
    if versions.is_empty()
        && let Some(fl) = libs.iter().find(|l| l.role == "libflutter" && l.abi == chosen.abi)
        && let Ok(fb) = read_lib(&input, fl, &mut budget)
    {
        versions = dart::scan_library(&fb, 4).dart_versions;
    }
    let lib_path = chosen.entry.as_ref().map(|e| e.name.clone()).unwrap_or_else(|| input.name.clone());
    let (tokens, cov) = page(&aot.string_pool.tokens, p.offset, p.limit);
    let feature_list: Vec<&str> = aot.features.as_deref().map(|f| f.split_whitespace().collect()).unwrap_or_default();
    let present = aot.snapshots.iter().filter(|s| s.present).count();
    let summary = format!(
        "{lib_path} ({}-bit {}): {present}/4 Dart snapshot symbols via {}; {}; snapshot hash {}; {} package/dart URIs, {} identifier tokens.",
        aot.elf.bits,
        aot.elf.architecture,
        aot.elf.symbol_source,
        if aot.complete { "complete FullAOT snapshot" } else { "incomplete or non-AOT snapshot" },
        aot.snapshot_hash.as_deref().unwrap_or("unknown"),
        aot.string_pool.uris.len(),
        aot.string_pool.tokens.len()
    );
    let mut lims = vec![
        Limitation::new(
            "string_pool_byte_scan",
            "URIs and tokens come from a byte scan of the isolate snapshot, not from decoding its object pool; classes, functions and their code are not recovered.",
        ),
        Limitation::new("no_version_table", "The snapshot hash is not mapped to an SDK version; dart_versions lists only what the binaries state."),
        Limitation::new("header_layout", "Snapshot kinds use the Dart 2.14+ numbering; complete requires FullAOT (kind 3) for both data snapshots."),
    ];
    if aot.string_pool.uris_truncated || aot.string_pool.tokens_truncated {
        lims.push(Limitation::new("string_pool_capped", "The scan keeps at most 500 URIs and 2000 tokens."));
    }
    lims.extend(aot.warnings.iter().chain(aot.elf.warnings.iter()).map(|w| Limitation::new("parse_warning", w.clone())));
    let ev = builder(ctx, "android_dart_snapshot_show", input.subject.clone(), json!({"path": input.path, "abi": p.abi, "offset": p.offset, "limit": p.limit}))
        .result(json!({
            "library": lib_path,
            "abi": chosen.abi,
            "elf": aot.elf,
            "snapshots": aot.snapshots,
            "complete": aot.complete,
            "snapshot_hash": aot.snapshot_hash,
            "features": aot.features,
            "feature_list": feature_list,
            "dart_versions": versions,
            "uris": aot.string_pool.uris,
            "uris_truncated": aot.string_pool.uris_truncated,
            "tokens_total": aot.string_pool.tokens.len(),
            "tokens_truncated": aot.string_pool.tokens_truncated,
            "tokens": tokens,
            "scanned_bytes": aot.string_pool.scanned_bytes,
        }))
        .summary(summary)
        .confidence(if aot.complete { Confidence::Observed } else { Confidence::Inferred })
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", input.path.display().to_string()).with_label(lib_path))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

#[cfg(test)]
mod tests {
    use crate::Engine;
    use crate::tools::native_common::test_support::{call, call_err};
    use craft_anything_testkit::flutter as fx;
    use serde_json::json;

    #[test]
    fn identifies_a_flutter_apk() {
        let e = Engine::new(crate::testing::session());
        let apk = craft_anything_testkit::temp_file("app.apk", &fx::flutter_apk());
        let v = call(&e, "android_flutter_identify", json!({"path": apk}));
        let r = &v["result"];
        assert_eq!(r["flutter_detected"], true);
        assert_eq!(r["preferred_abi"], "arm64-v8a");
        assert_eq!(r["snapshot_hash"], fx::SNAPSHOT_HASH);
        assert_eq!(r["dart_versions"][0], fx::DART_VERSION);
        assert_eq!(r["abis"].as_array().unwrap().len(), 2);
        assert_eq!(r["abis"][0]["libflutter"]["build_id"], fx::BUILD_ID_HEX);
        assert_eq!(r["abis"][0]["libflutter"]["sha256"].as_str().unwrap().len(), 64);
        let plain = craft_anything_testkit::temp_file("plain.apk", &fx::plain_apk());
        let v = call(&e, "android_flutter_identify", json!({"path": plain}));
        assert_eq!(v["result"]["flutter_detected"], false);
        assert!(v["result"]["snapshot_hash"].is_null());
    }

    #[test]
    fn inspects_dart_aot_from_apk_and_elf() {
        let e = Engine::new(crate::testing::session());
        let apk = craft_anything_testkit::temp_file("app.apk", &fx::flutter_apk());
        let v = call(&e, "android_dart_snapshot_show", json!({"path": apk}));
        let r = &v["result"];
        assert_eq!(r["abi"], "arm64-v8a");
        assert_eq!(r["complete"], true);
        assert_eq!(r["dart_versions"][0], fx::DART_VERSION);
        assert!(r["uris"].as_array().unwrap().iter().any(|u| u == "package:notes_app/main.dart"));
        let v = call(&e, "android_dart_snapshot_show", json!({"path": apk, "abi": "armeabi-v7a", "limit": 1}));
        assert_eq!(v["result"]["elf"]["symbol_source"], "dynamic-segment");
        assert_eq!(v["result"]["tokens"].as_array().unwrap().len(), 1);
        assert_eq!(v["coverage"]["status"], "partial");
        let so = craft_anything_testkit::temp_file("libapp.so", &fx::libapp_so(fx::SymbolTable::DynamicHash));
        let v = call(&e, "android_dart_snapshot_show", json!({"path": so}));
        assert_eq!(v["result"]["snapshot_hash"], fx::SNAPSHOT_HASH);
        assert!(call_err(&e, "android_dart_snapshot_show", json!({"path": apk, "abi": "mips"})).message.contains("no lib/mips"));
        assert!(call_err(&e, "android_dart_snapshot_show", json!({"path": apk, "abi": "BAD!"})).message.contains("abi"));
        let plain = craft_anything_testkit::temp_file("plain.apk", &fx::plain_apk());
        call_err(&e, "android_dart_snapshot_show", json!({"path": plain}));
    }

    #[test]
    fn damaged_packages_never_panic() {
        let e = Engine::new(crate::testing::session());
        let apk = fx::flutter_apk();
        for (i, m) in craft_anything_testkit::mutations(&apk).into_iter().enumerate().step_by(7) {
            let p = craft_anything_testkit::temp_file(&format!("m{i}.apk"), &m);
            let _ = e.call("android_flutter_identify", json!({"path": p}), crate::CallOptions::new(crate::Caller::Cli));
            let _ = e.call("android_dart_snapshot_show", json!({"path": p}), crate::CallOptions::new(crate::Caller::Cli));
        }
    }
}
