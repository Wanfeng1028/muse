//! Android apps with built-in parsers: the APK (manifest from binary XML, permissions,
//! components, signing certificates, DEX files, native libraries), DEX classes and methods with a
//! smali-like bytecode listing, cross-DEX references, compiled resources per locale, and whether
//! the optional external decoders (JADX for Java source, Apktool) are available.

use super::artifact_tools::{fresh_temp_dir, rel_to};
use super::native_common::{page, spec};
use super::static_input::{self, Input, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{
    Authority, Confidence, Coverage, CoverageStatus, Environment, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex,
};
use craft_anything_formats::{apk_sign, arsc, axml, der, dex, dex_ops, verify, zip};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::time::Duration;

// Flutter/Dart snapshots and the JEB client live in submodules.
pub mod flutter;
pub mod jeb;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Android;
    let e = Effects::EVIDENCE;
    let mut v = vec![
        spec(
            "android_package_show",
            "Android app package",
            "Read an APK with built-in parsers: the manifest (package, versions, SDK levels, permissions, components with exported state and intent filters, application flags) decoded from binary XML, signing certificates (v1 PKCS#7 files and the v2/v3 signing block; signatures and content digests are verified, but not whether the certificate is one you trust), DEX files and native libraries per ABI.",
            "See what an Android app is called, what it asks permission for, its screens and services, and who signed it.",
            Android,
            e,
            Requires::Nothing,
            schema_of::<PackageParams>,
            android_package_show,
        ),
        spec(
            "android_classes_find",
            "Find Android classes",
            "Search the classes defined in an APK's DEX files (or a bare .dex) by name; an empty query lists every class. Paged (offset/limit).",
            "Find the pieces of code inside an Android app by name.",
            Android,
            e,
            Requires::Nothing,
            schema_of::<SearchParams>,
            android_classes_find,
        ),
        spec(
            "android_class_show",
            "Android class",
            "One class from an APK or .dex: superclass, interfaces, access flags, source file, annotations, fields and methods with Java-style signatures and overload indexes.",
            "Look inside one piece of an Android app's code.",
            Android,
            e,
            Requires::Nothing,
            schema_of::<ClassParams>,
            android_class_show,
        ),
        spec(
            "android_method_show",
            "Android method bytecode",
            "A method's Dalvik bytecode as a smali-like listing with registers, resolved strings, types, fields and methods, branch targets, switch and array payloads and try/catch handlers (built-in decoder). With java_source=true and JADX installed, also attaches JADX's Java decompilation of the class.",
            "Read the instructions of one function in an Android app.",
            Android,
            e.union(Effects::LAUNCHES_PROCESS).union(Effects::WRITES_FILESYSTEM),
            Requires::Nothing,
            schema_of::<MethodParams>,
            android_method_show,
        ),
        spec(
            "android_class_users_find",
            "Who uses this Android class?",
            "Every instruction in every DEX file of an APK that calls, reads, writes, creates, casts to or loads a class (or only calls one of its methods when method_name is given), with the calling method and code offset. Paged.",
            "Find every place in an Android app that uses a piece of code.",
            Android,
            e,
            Requires::Nothing,
            schema_of::<ReferencesParams>,
            android_class_users_find,
        ),
        spec(
            "android_resources_read",
            "Android resources",
            "Decode resources.arsc with the built-in parser: packages, resource types and their configurations (locale, density, night mode, SDK…), every entry with typed values and style bags, string resources per locale; optionally decode compiled res/*.xml files to text. Paged.",
            "See an Android app's text in every language, its colours, styles and layouts.",
            Android,
            e,
            Requires::Nothing,
            schema_of::<ResourcesParams>,
            android_resources_read,
        ),
        spec(
            "android_components_list",
            "Android app components",
            "The activities, activity aliases, services, receivers and providers an APK's manifest declares: exported state and where it comes from, permissions, intent filters (actions, categories, data), and a plain reachable_from_outside flag with who_can_reach (any_app, apps_with_permission or own_app_only), following the manifest's implicit export rules for its targetSdk. Filter by kind or reachable_only; paged. Reads the manifest only; components an app registers while running aren't in it.",
            "See which parts of an Android app other apps can start or talk to.",
            Android,
            e | Effects::CARRIES_TARGET_CONTENT,
            Requires::Nothing,
            schema_of::<ComponentsParams>,
            android_components_list,
        ),
        spec(
            "engines_apktool_check",
            "Is Apktool available?",
            "Report whether Apktool is installed (Settings path, managed engine store, then PATH) and its version. Craft Anything's built-in resource and manifest decoders need nothing installed; Apktool is optional.",
            "Check whether the optional Apktool helper is installed.",
            Android,
            e.union(Effects::LAUNCHES_PROCESS),
            Requires::Nothing,
            schema_of::<ClientParams>,
            engines_apktool_check,
        ),
    ];
    v.extend(flutter::specs());
    v.extend(jeb::specs());
    v
}

// ---------------------------------------------------------------------------------------------
// Params

fn d_true() -> bool {
    true
}
fn d_limit() -> usize {
    200
}
fn d_insn_limit() -> usize {
    2000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PackageParams {
    /// Absolute path of the APK; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Include the decoded manifest as XML text (default true).
    #[serde(default = "d_true")]
    pub include_manifest_xml: bool,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SearchParams {
    /// Absolute path of the APK or .dex; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Case-insensitive part of a class name (dotted or descriptor form). Empty lists every class.
    #[serde(default)]
    pub query: String,
    #[serde(default)]
    pub offset: usize,
    /// Classes per page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClassParams {
    #[serde(default)]
    pub path: Option<String>,
    /// `com.example.Main`, `com/example/Main` or `Lcom/example/Main;`.
    pub class_name: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MethodParams {
    #[serde(default)]
    pub path: Option<String>,
    pub class_name: String,
    pub method_name: String,
    /// Which overload (0-based, in declaration order) when the name is overloaded; 0 when omitted.
    #[serde(default)]
    pub overload_index: Option<usize>,
    /// Also ask JADX (if installed) for Java source of the class. Default false.
    #[serde(default)]
    pub java_source: bool,
    /// First instruction of the page.
    #[serde(default)]
    pub offset: usize,
    /// Instructions per page (1–5000, default 2000).
    #[serde(default = "d_insn_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReferencesParams {
    #[serde(default)]
    pub path: Option<String>,
    pub class_name: String,
    /// Only calls to methods with this name.
    #[serde(default)]
    pub method_name: Option<String>,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ResourcesParams {
    /// Absolute path of the APK or a resources.arsc file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Include string resources grouped by locale (default true).
    #[serde(default = "d_true")]
    pub with_strings: bool,
    /// Only this locale (`fr`, `es-rMX`; `default` for the unqualified one).
    #[serde(default)]
    pub locale: Option<String>,
    /// Only these locales, each with its own string table (`["de", "fr", "default"]`); adds to `locale`.
    #[serde(default)]
    pub only_locales: Vec<String>,
    /// Only entries of this resource type (`string`, `color`, `style`…).
    #[serde(default)]
    pub type_name: Option<String>,
    /// Compiled XML files inside the APK to decode to text (e.g. `res/layout/main.xml`), at most 16.
    #[serde(default)]
    pub xml_files: Vec<String>,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClientParams {}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ComponentsParams {
    /// Absolute path of the APK; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Only this kind: activity, activity-alias, service, receiver or provider.
    #[serde(default)]
    pub kind: Option<String>,
    /// Only components other apps can reach.
    #[serde(default)]
    pub reachable_only: bool,
    #[serde(default)]
    pub offset: usize,
    /// Rows per page (1..=5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

// ---------------------------------------------------------------------------------------------
// Loading

/// Biggest APK read.
const MAX_APK: u64 = 1 << 30;
/// Most strings listed per locale (the rest stay in the entries).
const MAX_LOCALE_STRINGS: usize = 5000;
/// Biggest single member decompressed.
const MAX_MEMBER: u64 = 256 << 20;
/// Most DEX bytes decompressed in total.
const MAX_DEX_TOTAL: u64 = 768 << 20;

struct Pkg {
    input: Input,
    zip: Option<zip::ZipArchive>,
    /// (name, bytes)
    dexes: Vec<(String, Vec<u8>)>,
    warnings: Vec<String>,
}

fn is_root_dex(name: &str) -> bool {
    name.strip_prefix("classes").and_then(|r| r.strip_suffix(".dex")).is_some_and(|n| n.chars().all(|c| c.is_ascii_digit()))
}

fn load_pkg(ctx: &Ctx<'_>, path: Option<&str>, want_dex: bool) -> Result<Pkg, ToolError> {
    let input = static_input::load(ctx, path, MAX_APK)?;
    let mut pkg = Pkg { zip: None, dexes: Vec::new(), warnings: Vec::new(), input };
    if dex::is_dex(&pkg.input.bytes) {
        pkg.dexes.push((pkg.input.name.clone(), pkg.input.bytes.to_vec()));
        return Ok(pkg);
    }
    if !zip::looks_like_zip(&pkg.input.bytes) {
        return Err(ToolError::unsupported(format!("{} is not an APK or DEX file", pkg.input.name))
            .with_remediation("Pass an .apk (or a classes.dex); run triage to see what this file is."));
    }
    let z =
        zip::parse(&pkg.input.bytes, 500_000).map_err(|e| ToolError::new(ErrorCode::NotSupported, format!("Couldn't read the APK's ZIP directory: {e}")))?;
    if want_dex {
        let mut total = 0u64;
        let mut names: Vec<&zip::ZipEntry> = z.entries.iter().filter(|e| is_root_dex(&e.name)).collect();
        // classes.dex, classes2.dex, classes3.dex … in load order.
        names.sort_by_key(|e| e.name.trim_start_matches("classes").trim_end_matches(".dex").parse::<u32>().unwrap_or(1));
        for e in names {
            ctx.cancel.check()?;
            if total.saturating_add(e.uncompressed_size) > MAX_DEX_TOTAL {
                pkg.warnings.push(format!("{} skipped: the DEX size budget ({MAX_DEX_TOTAL} bytes) is used up", e.name));
                continue;
            }
            match zip::read_entry(&pkg.input.bytes, e, MAX_MEMBER) {
                Ok(b) => {
                    total += b.len() as u64;
                    pkg.dexes.push((e.name.clone(), b));
                }
                Err(err) => pkg.warnings.push(format!("{}: {err}", e.name)),
            }
        }
    }
    pkg.zip = Some(z);
    Ok(pkg)
}

fn member(pkg: &Pkg, name: &str) -> Option<Result<Vec<u8>, String>> {
    let z = pkg.zip.as_ref()?;
    let e = z.entries.iter().find(|e| e.name == name)?;
    Some(zip::read_entry(&pkg.input.bytes, e, MAX_MEMBER).map_err(|e| e.to_string()))
}

fn parse_dexes(pkg: &Pkg) -> (Vec<(&str, dex::Dex<'_>)>, Vec<String>) {
    let mut out = Vec::new();
    let mut warnings = pkg.warnings.clone();
    for (name, bytes) in &pkg.dexes {
        match dex::parse(bytes) {
            Ok(d) => {
                warnings.extend(d.warnings.iter().map(|w| format!("{name}: {w}")));
                out.push((name.as_str(), d));
            }
            Err(e) => warnings.push(format!("{name}: {e}")),
        }
    }
    (out, warnings)
}

fn no_dex_error(pkg: &Pkg) -> ToolError {
    ToolError::new(ErrorCode::NotSupported, format!("{} has no readable classes*.dex", pkg.input.name))
        .with_remediation("Check the APK is complete; split APKs keep code in the base APK.")
}

fn warn_lims(warnings: &[String]) -> Vec<Limitation> {
    warnings.iter().take(50).map(|w| Limitation::new("parse_warning", w.clone())).collect()
}

fn ev(ctx: &Ctx<'_>, op: &str, pkg: &Pkg, params: Value) -> EvidenceBuilder {
    builder(ctx, op, pkg.input.subject.clone(), params)
        .authority(Authority::OriginalFiles)
        .location(Location::new("path", pkg.input.path.display().to_string()))
}

/// Find a class across the DEX files: (dex index, class def).
fn find_class<'a>(dexes: &'a [(&'a str, dex::Dex<'a>)], name: &str) -> Option<(usize, &'a dex::ClassDef)> {
    dexes.iter().enumerate().find_map(|(i, (_, d))| d.find_class(name).map(|c| (i, c)))
}

fn class_not_found(dexes: &[(&str, dex::Dex<'_>)], name: &str) -> ToolError {
    let simple = name.rsplit(['.', '/']).next().unwrap_or(name).trim_end_matches(';').to_ascii_lowercase();
    let mut similar = Vec::new();
    for (_, d) in dexes {
        for c in &d.classes {
            let n = dex::java_name(&d.class_name(c));
            if !simple.is_empty() && n.to_ascii_lowercase().contains(&simple) && similar.len() < 10 {
                similar.push(n);
            }
        }
    }
    ToolError::invalid(format!("No class {name} is defined in this package"))
        .with_remediation("Find the exact name with android_classes_find (classes from the Android framework are not inside the APK).")
        .with_details(json!({"reason": "class_not_found", "similar": similar}))
}

// ---------------------------------------------------------------------------------------------
// android_package_show

fn cert_json(der_bytes: &[u8]) -> Value {
    match der::certificate(der_bytes) {
        Some(c) => json!({
            "subject": c.subject, "issuer": c.issuer, "serial": c.serial, "not_before": c.not_before, "not_after": c.not_after,
            "signature_algorithm": c.signature_algorithm, "public_key_algorithm": c.public_key_algorithm, "version": c.version,
            "sha256": sha256_hex(der_bytes), "bytes": der_bytes.len(),
        }),
        None => json!({"sha256": sha256_hex(der_bytes), "bytes": der_bytes.len(), "error": "not a readable X.509 certificate"}),
    }
}

fn android_package_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PackageParams = parse_params(params)?;
    let pkg = load_pkg(ctx, p.path.as_deref(), true)?;
    let Some(z) = pkg.zip.as_ref() else {
        return Err(ToolError::unsupported(format!("{} is a bare DEX file, not an APK", pkg.input.name))
            .with_remediation("Use android_classes_find or android_class_show for DEX files."));
    };
    let mut warnings = pkg.warnings.clone();
    let mut lims = Vec::new();
    // Manifest
    let (manifest, manifest_xml) = match member(&pkg, "AndroidManifest.xml") {
        Some(Ok(b)) => match axml::parse(&b) {
            Ok(doc) => {
                warnings.extend(doc.warnings.iter().map(|w| format!("AndroidManifest.xml: {w}")));
                let xml = p.include_manifest_xml.then(|| doc.to_xml(256 * 1024));
                (Some(axml::manifest(&doc)), xml)
            }
            Err(e) => {
                warnings.push(format!("AndroidManifest.xml: {e}"));
                (None, None)
            }
        },
        Some(Err(e)) => {
            warnings.push(format!("AndroidManifest.xml: {e}"));
            (None, None)
        }
        None => {
            lims.push(Limitation::new(
                "no_manifest",
                "The archive has no AndroidManifest.xml at its root; it may not be an APK (or it is a split/bundle module).",
            ));
            (None, None)
        }
    };
    // Signing. A reader for a ZIP entry's uncompressed bytes (used by JAR v1 digest checks).
    let read_entry = |name: &str| -> Option<Vec<u8>> {
        let e = z.entries.iter().find(|e| e.name == name)?;
        zip::read_entry(&pkg.input.bytes, e, 16 << 20).ok()
    };
    let manifest_mf = read_entry("META-INF/MANIFEST.MF");
    let mut v1 = Vec::new();
    let mut v1_any_valid = false;
    for e in z.entries.iter().filter(|e| {
        let n = e.name.to_ascii_uppercase();
        n.starts_with("META-INF/") && !n.trim_start_matches("META-INF/").contains('/') && (n.ends_with(".RSA") || n.ends_with(".DSA") || n.ends_with(".EC"))
    }) {
        match zip::read_entry(&pkg.input.bytes, e, 4 << 20) {
            Ok(b) => {
                let certs: Vec<Value> = der::pkcs7_certificates(&b).into_iter().map(cert_json).collect();
                // The matching .SF file (same base name) is the signed content.
                let sf_name = {
                    let base = e.name.rsplit_once('.').map(|(s, _)| s).unwrap_or(&e.name);
                    format!("{base}.SF")
                };
                let sf = read_entry(&sf_name);
                let pkcs7 = sf.as_deref().and_then(|sf| verify::verify_pkcs7_detached(sf, &b));
                let integrity = match (&manifest_mf, &sf) {
                    (Some(mf), Some(sf)) => Some(verify::verify_jar_integrity(mf, sf, &read_entry)),
                    _ => None,
                };
                if pkcs7.as_ref().is_some_and(|p| p.signature_valid.is_valid())
                    && integrity.as_ref().is_some_and(|i| i.manifest_digest_matches == Some(true) && i.files_mismatched == 0 && i.files_matched > 0)
                {
                    v1_any_valid = true;
                }
                v1.push(json!({"file": e.name, "bytes": b.len(), "certificates": certs, "signature_file": sf_name, "pkcs7": pkcs7, "integrity": integrity}));
            }
            Err(err) => warnings.push(format!("{}: {err}", e.name)),
        }
    }
    let block = apk_sign::parse(&pkg.input.bytes);
    let mut schemes = Vec::new();
    if !v1.is_empty() {
        schemes.push("v1".to_string());
    }
    let mut any_scheme_verified = false;
    let block_json = block.as_ref().map(|b| {
        warnings.extend(b.warnings.iter().map(|w| format!("signing block: {w}")));
        for s in &b.signers {
            if !schemes.iter().any(|x| x == s.scheme) {
                schemes.push(s.scheme.to_string());
            }
        }
        json!({
            "offset": b.offset, "size": b.size, "entries": b.entries,
            "signers": b.signers.iter().map(|s| {
                let v = verify::verify_apk_signer(&pkg.input.bytes, b.offset, s);
                if v.verified {
                    any_scheme_verified = true;
                }
                json!({
                    "scheme": s.scheme, "digests": s.digests, "signature_algorithms": s.signature_algorithms,
                    "min_sdk": s.min_sdk, "max_sdk": s.max_sdk, "public_key_bytes": s.public_key_bytes,
                    "certificates": s.certificates.iter().map(|c| cert_json(c)).collect::<Vec<_>>(),
                    "verification": v,
                })
            }).collect::<Vec<_>>(),
        })
    });
    lims.push(Limitation::new(
        "verification_scope",
        "Signatures ARE verified cryptographically here (v2/v3 signature over the signed data plus a recomputed APK content digest; v1 PKCS#7 over the .SF plus MANIFEST.MF per-file digests). NOT checked: certificate revocation, v3 key-rotation lineage/proof-of-rotation, rollback protection, source-stamp, and whether the signing certificate is one you trust (the certificate SHA-256 fingerprint is reported so you can compare it yourself).",
    ));
    // DEX
    let dex_info: Vec<Value> = pkg
        .dexes
        .iter()
        .map(|(name, b)| match dex::parse(b) {
            Ok(d) => json!({
                "name": name, "bytes": b.len(), "sha256": sha256_hex(b), "version": d.header.version, "checksum_ok": d.header.checksum_ok,
                "classes": d.header.class_defs, "methods": d.header.method_ids, "fields": d.header.field_ids, "strings": d.header.string_ids,
            }),
            Err(e) => json!({"name": name, "bytes": b.len(), "sha256": sha256_hex(b), "error": e.to_string()}),
        })
        .collect();
    // Native libraries
    let mut libs: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for e in z.entries.iter().filter(|e| !e.is_dir) {
        let parts: Vec<&str> = e.name.split('/').collect();
        if let ["lib", abi, file] = parts.as_slice()
            && libs.values().map(Vec::len).sum::<usize>() < 10_000
        {
            libs.entry((*abi).to_string()).or_default().push(json!({"name": file, "bytes": e.uncompressed_size, "compression": e.method_name()}));
        }
    }
    let assets = z.entries.iter().filter(|e| e.name.starts_with("assets/")).count();
    let res_files = z.entries.iter().filter(|e| e.name.starts_with("res/")).count();
    let has_arsc = z.entries.iter().any(|e| e.name == "resources.arsc");
    let m = manifest.clone().unwrap_or_default();
    let sig_desc = if schemes.is_empty() {
        "no signature found".to_string()
    } else {
        let verified = any_scheme_verified || v1_any_valid;
        format!("scheme {} ({})", schemes.join(", "), if verified { "cryptographically VERIFIED" } else { "present but NOT verified" })
    };
    let summary = format!(
        "{} ({}, version {}, SDK {}–{}): {} permissions, {} components ({} exported), {} DEX file(s), native code for {}; signed with {}.",
        m.package.as_deref().unwrap_or("unknown package"),
        pkg.input.name,
        m.version_name.as_deref().unwrap_or("?"),
        m.min_sdk.as_deref().unwrap_or("?"),
        m.target_sdk.as_deref().unwrap_or("?"),
        m.uses_permissions.len(),
        m.components.len(),
        m.components.iter().filter(|c| c.exported).count(),
        pkg.dexes.len(),
        if libs.is_empty() { "no ABI".to_string() } else { libs.keys().cloned().collect::<Vec<_>>().join(", ") },
        sig_desc,
    );
    lims.extend(warn_lims(&warnings));
    let b = ev(ctx, "android_package_show", &pkg, json!({"path": p.path, "include_manifest_xml": p.include_manifest_xml}))
        .result(json!({
            "package": m.package, "version_code": m.version_code, "version_name": m.version_name,
            "min_sdk": m.min_sdk, "target_sdk": m.target_sdk, "max_sdk": m.max_sdk,
            "manifest": manifest, "manifest_xml": manifest_xml,
            "signing": {"schemes": schemes, "v1": v1, "signing_block": block_json},
            "dex": dex_info, "native_libraries": libs,
            "entries": z.entries.len(), "assets": assets, "res_files": res_files, "has_resources_arsc": has_arsc,
            "warnings": warnings,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::complete(z.entries.len() as u64));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// Classes

#[derive(Serialize)]
struct ClassRow {
    name: String,
    descriptor: String,
    dex: String,
    access: Vec<&'static str>,
    superclass: Option<String>,
    fields: usize,
    methods: usize,
}

const COMPONENT_KINDS: [&str; 5] = ["activity", "activity-alias", "service", "receiver", "provider"];

/// The permission that guards a component, its own or else the application's, and whether anything
/// does. A provider's separate read and write permissions count only when both are set.
fn component_guard<'a>(c: &'a axml::Component, m: &'a axml::Manifest) -> (Option<&'a String>, bool) {
    let permission = c.permission.as_ref().or(m.application.permission.as_ref());
    (permission, permission.is_some() || (c.read_permission.is_some() && c.write_permission.is_some()))
}

/// One component with what decides who can reach it, for `android_components_list`.
fn component_row(c: &axml::Component, m: &axml::Manifest, app_enabled: bool) -> Value {
    let export_source = match (c.exported_attribute, c.exported) {
        (Some(_), _) => "explicit",
        (None, true) if c.kind == "provider" => "default_for_old_target_sdk",
        (None, true) => "implied_by_intent_filter",
        (None, false) => "default_not_exported",
    };
    let (permission, guarded) = component_guard(c, m);
    let who_can_reach = match (c.exported, guarded) {
        (false, _) => "own_app_only",
        (true, true) => "apps_with_permission",
        (true, false) => "any_app",
    };
    let level = permission.and_then(|p| m.declared_permissions.iter().find(|d| d.name == *p)).and_then(|d| d.protection_level.clone());
    json!({
        "kind": c.kind,
        "name": c.name,
        "reachable_from_outside": c.exported,
        "who_can_reach": who_can_reach,
        "exported": c.exported,
        "exported_attribute": c.exported_attribute,
        "export_source": export_source,
        "permission": permission,
        "permission_from_application": c.permission.is_none() && permission.is_some(),
        "permission_protection_level": level,
        "read_permission": c.read_permission,
        "write_permission": c.write_permission,
        "enabled_attribute": c.enabled,
        "disabled_in_manifest": !app_enabled || c.enabled == Some(false),
        "authorities": c.authorities,
        "intent_filters": c.intent_filters,
    })
}

fn android_components_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ComponentsParams = parse_params(params)?;
    if let Some(k) = p.kind.as_deref()
        && !COMPONENT_KINDS.contains(&k)
    {
        return Err(ToolError::invalid(format!("kind must be one of {}", COMPONENT_KINDS.join(", "))));
    }
    let pkg = load_pkg(ctx, p.path.as_deref(), false)?;
    if pkg.zip.is_none() {
        return Err(
            ToolError::unsupported(format!("{} is a bare DEX file, which has no manifest", pkg.input.name)).with_remediation("Pass the .apk it came from.")
        );
    }
    let bytes = match member(&pkg, "AndroidManifest.xml") {
        Some(Ok(b)) => b,
        Some(Err(e)) => return Err(ToolError::new(ErrorCode::NotSupported, format!("Couldn't read AndroidManifest.xml: {e}"))),
        None => {
            return Err(ToolError::new(ErrorCode::NotFound, format!("{} has no AndroidManifest.xml", pkg.input.name))
                .with_remediation("Check it's an APK; run core_target_triage to see what it is."));
        }
    };
    let doc = axml::parse(&bytes).map_err(|e| format_err(e, "a binary AndroidManifest.xml"))?;
    let m = axml::manifest(&doc);
    let rows: Vec<Value> = m
        .components
        .iter()
        .filter(|c| p.kind.as_deref().is_none_or(|k| c.kind == k))
        .filter(|c| !p.reachable_only || c.exported)
        .map(|c| component_row(c, &m, m.application.enabled != Some(false)))
        .collect();
    let mut counts: BTreeMap<&str, (usize, usize)> = BTreeMap::new();
    for c in &m.components {
        let slot = counts.entry(c.kind.as_str()).or_insert((0, 0));
        slot.0 += 1;
        slot.1 += usize::from(c.exported);
    }
    let by_kind: BTreeMap<&str, Value> = counts.iter().map(|(k, (n, r))| (*k, json!({"total": n, "reachable_from_outside": r}))).collect();
    let reachable = m.components.iter().filter(|c| c.exported).count();
    let open = m.components.iter().filter(|c| c.exported && !component_guard(c, &m).1).count();
    let (items, cov) = page(&rows, p.offset, p.limit);

    let target = m.target_sdk.as_deref().and_then(|s| s.parse::<u32>().ok());
    let rule = match target {
        Some(t) => format!("This app targets SDK {t}. "),
        None => "The manifest states no targetSdk the reader could use, so the older rules were applied. ".to_string(),
    };
    let mut lims = vec![
        Limitation::new(
            "implicit_export_rules",
            format!(
                "{rule}With no android:exported value, a component with intent filters is exported below SDK 31 (from 31 on, Android refuses to install such an app), other components aren't, and a provider is exported up to SDK 16 regardless. The rule goes by the app's targetSdk as read here."
            ),
        ),
        Limitation::new(
            "manifest_only",
            "This reads the manifest alone: receivers registered while the app runs aren't in it, code can check callers itself, and a declared permission's strength depends on its protection level.",
        ),
    ];
    let unset_after_31 =
        target.is_some_and(|t| t >= 31) && m.components.iter().any(|c| c.exported_attribute.is_none() && !c.intent_filters.is_empty() && c.kind != "provider");
    if unset_after_31 {
        lims.push(Limitation::new(
            "missing_exported_attribute",
            "A component has intent filters and no android:exported value although the app targets SDK 31 or later. Android refuses to install that; it's shown here as not exported.",
        ));
    }
    if m.components.iter().any(|c| c.enabled == Some(false)) || m.application.enabled == Some(false) {
        lims.push(Limitation::new("disabled_components", "Components the manifest disables are still listed: the app can enable them while it runs."));
    }
    lims.extend(warn_lims(&doc.warnings));
    let summary =
        format!("{} component(s) in the manifest: {reachable} reachable from outside the app, {open} of those with no permission asked.", m.components.len());
    let e = ev(ctx, "android_components_list", &pkg, serde_json::to_value(&p).unwrap_or(Value::Null))
        .result(json!({
            "path": pkg.input.path,
            "package": m.package,
            "target_sdk": m.target_sdk,
            "min_sdk": m.min_sdk,
            "total": m.components.len(),
            "matching": rows.len(),
            "by_kind": by_kind,
            "reachable_from_outside": reachable,
            "reachable_with_no_permission": open,
            "components": items,
        }))
        .summary(summary)
        .confidence(if target.is_some() { Confidence::Observed } else { Confidence::Inferred })
        .target_content(true)
        .limitations(lims)
        .coverage(cov)
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn android_classes_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SearchParams = parse_params(params)?;
    let pkg = load_pkg(ctx, p.path.as_deref(), true)?;
    let (dexes, warnings) = parse_dexes(&pkg);
    if dexes.is_empty() {
        return Err(no_dex_error(&pkg));
    }
    let q = p.query.trim().to_ascii_lowercase();
    let mut rows = Vec::new();
    let mut total_classes = 0usize;
    for (name, d) in &dexes {
        for (i, c) in d.classes.iter().enumerate() {
            if i % 1024 == 0 {
                ctx.cancel.check()?;
            }
            total_classes += 1;
            let desc = d.class_name(c);
            let java = dex::java_name(&desc);
            if !q.is_empty() && !java.to_ascii_lowercase().contains(&q) && !desc.to_ascii_lowercase().contains(&q) {
                continue;
            }
            let cd = d.class_data(c);
            rows.push(ClassRow {
                name: java,
                descriptor: desc,
                dex: (*name).to_string(),
                access: dex::access_flags(c.access, "class"),
                superclass: (c.superclass_idx != dex::NO_INDEX).then(|| dex::java_name(&d.type_desc(c.superclass_idx))),
                fields: cd.static_fields.len() + cd.instance_fields.len(),
                methods: cd.direct_methods.len() + cd.virtual_methods.len(),
            });
        }
    }
    rows.sort_by(|a, b| a.name.cmp(&b.name));
    let (slice, cov) = page(&rows, p.offset, p.limit);
    let summary = format!(
        "{} of {} classes{} in {} DEX file(s); showing {}.",
        rows.len(),
        total_classes,
        if q.is_empty() { String::new() } else { format!(" match \"{}\"", p.query.trim()) },
        dexes.len(),
        slice.len()
    );
    let b = ev(ctx, "android_classes_find", &pkg, json!({"path": p.path, "query": p.query, "offset": p.offset, "limit": p.limit}))
        .result(json!({"query": p.query, "matches": rows.len(), "classes_total": total_classes, "dex_files": dexes.iter().map(|(n, _)| *n).collect::<Vec<_>>(), "classes": slice}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(warn_lims(&warnings))
        .coverage(cov);
    Ok(ToolOutput::evidence(b.build()?))
}

fn method_rows(d: &dex::Dex<'_>, cd: &dex::ClassData) -> Vec<Value> {
    let mut seen: BTreeMap<String, usize> = BTreeMap::new();
    let mut out = Vec::new();
    for (kind, list) in [("direct", &cd.direct_methods), ("virtual", &cd.virtual_methods)] {
        for m in list.iter().take(20_000) {
            let name = d.method_name(m.method_idx).to_string();
            let idx = seen.entry(name.clone()).or_insert(0);
            let code = d.code(m.code_off);
            out.push(json!({
                "name": name, "overload_index": *idx, "kind": kind,
                "signature": d.method_signature(m), "reference": d.method_ref(m.method_idx),
                "access": dex::access_flags(m.access, "method"),
                "code_units": code.as_ref().map(|c| c.insns.len()), "registers": code.as_ref().map(|c| c.registers),
                "try_blocks": code.as_ref().map(|c| c.tries.len()),
            }));
            *idx += 1;
        }
    }
    out
}

/// The methods named `name` in declaration order (direct first, then virtual).
fn overloads(d: &dex::Dex<'_>, cd: &dex::ClassData, name: &str) -> Vec<dex::EncodedMethod> {
    cd.direct_methods.iter().chain(&cd.virtual_methods).filter(|m| d.method_name(m.method_idx) == name).copied().collect()
}

fn android_class_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ClassParams = parse_params(params)?;
    let pkg = load_pkg(ctx, p.path.as_deref(), true)?;
    let (dexes, warnings) = parse_dexes(&pkg);
    if dexes.is_empty() {
        return Err(no_dex_error(&pkg));
    }
    let (di, c) = find_class(&dexes, &p.class_name).ok_or_else(|| class_not_found(&dexes, &p.class_name))?;
    let Some((dex_name, d)) = dexes.get(di) else { return Err(ToolError::internal("class index out of range")) };
    let cd = d.class_data(c);
    let fields: Vec<Value> = [("static", &cd.static_fields), ("instance", &cd.instance_fields)]
        .iter()
        .flat_map(|(kind, list)| {
            list.iter().take(20_000).map(move |f| {
                let id = d.fields.get(f.field_idx as usize);
                json!({
                    "name": id.map(|i| d.string(i.name_idx)).unwrap_or("?"),
                    "type": id.map(|i| dex::java_name(&d.type_desc(u32::from(i.type_or_proto)))).unwrap_or_default(),
                    "kind": kind, "access": dex::access_flags(f.access, "field"), "reference": d.field_ref(f.field_idx),
                })
            })
        })
        .collect();
    let methods = method_rows(d, &cd);
    let desc = d.class_name(c);
    let source = (c.source_file_idx != dex::NO_INDEX).then(|| d.string(c.source_file_idx).to_string());
    let summary = format!(
        "{} ({}) extends {}: {} fields, {} methods{}.",
        dex::java_name(&desc),
        dex_name,
        if c.superclass_idx == dex::NO_INDEX { "nothing".into() } else { dex::java_name(&d.type_desc(c.superclass_idx)) },
        fields.len(),
        methods.len(),
        source.as_deref().map(|s| format!(", from {s}")).unwrap_or_default()
    );
    let mut lims = warn_lims(&warnings);
    if !cd.complete {
        lims.push(Limitation::new("class_data_incomplete", "The class data could not be read completely; some members may be missing."));
    }
    let b = ev(ctx, "android_class_show", &pkg, json!({"path": p.path, "class_name": p.class_name}))
        .result(json!({
            "name": dex::java_name(&desc), "descriptor": desc, "dex": dex_name,
            "access": dex::access_flags(c.access, "class"),
            "superclass": (c.superclass_idx != dex::NO_INDEX).then(|| d.type_desc(c.superclass_idx)),
            "interfaces": d.interfaces(c), "source_file": source, "annotations": d.annotations(c),
            "fields": fields, "methods": methods,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("class", desc.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// android_method_show

#[derive(Serialize)]
struct InsnRow {
    offset: String,
    text: String,
    opcode: String,
    units: u32,
}

/// Java source of one class from JADX, or a reason it is missing. Never an error.
fn jadx_source(ctx: &Ctx<'_>, input: &Path, class_java: &str) -> (Value, Option<Limitation>) {
    let settings = &ctx.session.settings;
    let Some(jadx) = craft_anything_engines::locate("jadx", &settings.engines.tools, &settings.engine_store_dir()) else {
        return (
            json!({"status": "unavailable"}),
            Some(Limitation::new(
                "jadx_not_installed",
                "Java source was requested but JADX is not installed (Settings → Engines, the engine store, or PATH). The bytecode listing above is complete without it.",
            )),
        );
    };
    let out = match fresh_temp_dir("craft-anything-jadx") {
        Ok(o) => o,
        Err(e) => {
            return (json!({"status": "failed", "error": e.message}), Some(Limitation::new("jadx_failed", "Could not create a temporary folder for JADX.")));
        }
    };
    let run = craft_anything_engines::jadx::run_single_class(&jadx, input, class_java, &out, ctx.cancel.clone());
    let result = match run {
        Ok(o) if o.success => {
            let simple = class_java.rsplit('.').next().unwrap_or(class_java);
            let outer = simple.split('$').next().unwrap_or(simple);
            match find_file(&out, &format!("{outer}.java"), 0) {
                Some(f) => match std::fs::metadata(&f).map(|m| m.len()) {
                    Ok(n) if n <= 2 << 20 => match std::fs::read_to_string(&f) {
                        Ok(text) => (json!({"status": "ok", "engine": "jadx", "file": rel_to(&out, &f), "text": text}), None),
                        Err(e) => {
                            (json!({"status": "failed", "error": e.to_string()}), Some(Limitation::new("jadx_failed", "JADX's output could not be read.")))
                        }
                    },
                    _ => (
                        json!({"status": "failed", "error": "output larger than 2 MiB"}),
                        Some(Limitation::new("jadx_output_too_large", "JADX's output was larger than 2 MiB and was not attached.")),
                    ),
                },
                None => (
                    json!({"status": "failed", "error": "JADX produced no source file for this class", "stderr_tail": tail(&o.stderr_text())}),
                    Some(Limitation::new("jadx_no_output", "JADX ran but wrote no source for this class (older JADX versions lack --single-class).")),
                ),
            }
        }
        Ok(o) => (
            json!({"status": "failed", "exit_code": o.code, "stderr_tail": tail(&o.stderr_text())}),
            Some(Limitation::new("jadx_failed", "JADX exited with an error; see java_source.stderr_tail.")),
        ),
        Err(e) => (json!({"status": "failed", "error": e.message}), Some(Limitation::new("jadx_failed", format!("JADX could not run: {}", e.message)))),
    };
    let _ = std::fs::remove_dir_all(&out);
    result
}

fn tail(s: &str) -> String {
    let n = s.chars().count();
    s.chars().skip(n.saturating_sub(2000)).collect()
}

/// Find a file by name below `dir` (no symlinks, bounded depth and breadth).
fn find_file(dir: &Path, name: &str, depth: usize) -> Option<PathBuf> {
    if depth > 32 {
        return None;
    }
    let entries = std::fs::read_dir(dir).ok()?;
    for e in entries.flatten().take(10_000) {
        let Ok(ft) = e.file_type() else { continue };
        let p = e.path();
        if ft.is_file() && e.file_name().to_string_lossy() == name {
            return Some(p);
        }
        if ft.is_dir()
            && let Some(f) = find_file(&p, name, depth + 1)
        {
            return Some(f);
        }
    }
    None
}

fn android_method_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MethodParams = parse_params(params)?;
    let pkg = load_pkg(ctx, p.path.as_deref(), true)?;
    let (dexes, warnings) = parse_dexes(&pkg);
    if dexes.is_empty() {
        return Err(no_dex_error(&pkg));
    }
    let (di, c) = find_class(&dexes, &p.class_name).ok_or_else(|| class_not_found(&dexes, &p.class_name))?;
    let Some((dex_name, d)) = dexes.get(di) else { return Err(ToolError::internal("class index out of range")) };
    let cd = d.class_data(c);
    let ov = overloads(d, &cd, &p.method_name);
    if ov.is_empty() {
        let names: Vec<String> = cd.direct_methods.iter().chain(&cd.virtual_methods).take(200).map(|m| d.method_name(m.method_idx).to_string()).collect();
        return Err(ToolError::invalid(format!("{} has no method named {}", dex::java_name(&d.class_name(c)), p.method_name))
            .with_remediation("List the class's methods with android_class_show.")
            .with_details(json!({"reason": "method_not_found", "methods": names})));
    }
    let oi = p.overload_index.unwrap_or(0);
    let m = *ov.get(oi).ok_or_else(|| {
        ToolError::invalid(format!("overload_index {oi} is out of range; {} has {} overload(s)", p.method_name, ov.len()))
            .with_details(json!({"overloads": ov.iter().map(|m| d.method_signature(m)).collect::<Vec<_>>()}))
    })?;
    let mut lims = warn_lims(&warnings);
    if ov.len() > 1 && p.overload_index.is_none() {
        lims.push(Limitation::new(
            "overload_chosen",
            format!("{} has {} overloads; showing overload_index 0. Pass overload_index to pick another.", p.method_name, ov.len()),
        ));
    }
    let class_desc = d.class_name(c);
    let reference = d.method_ref(m.method_idx);
    let code = d.code(m.code_off);
    let (rows, tries, regs, complete) = match &code {
        Some(code) => {
            let (insns, complete) = dex_ops::decode(&code.insns, 200_000);
            let rows: Vec<InsnRow> = insns
                .iter()
                .map(|i| InsnRow { offset: format!("{:04x}", i.offset), text: d.format_insn(i), opcode: format!("{:#04x}", i.opcode), units: i.units })
                .collect();
            if !complete {
                lims.push(Limitation::new("listing_incomplete", "Decoding stopped at an instruction that runs past the end of the code."));
            }
            (rows, code.tries.clone(), Some((code.registers, code.ins, code.outs)), complete)
        }
        None => {
            lims.push(Limitation::new(
                "no_code",
                if m.access & 0x500 != 0 { "This method is abstract or native: it has no bytecode in the DEX file." } else { "This method has no code item." },
            ));
            (Vec::new(), Vec::new(), None, true)
        }
    };
    let (slice, cov) = page(&rows, p.offset, p.limit);
    let listing: String =
        slice.iter().filter_map(|r| Some(format!("{}: {}", r.get("offset")?.as_str()?, r.get("text")?.as_str()?))).collect::<Vec<_>>().join("\n");
    let mut env = Environment::builtin(ctx.session.clean_room());
    let java = if p.java_source {
        let (v, lim) = jadx_source(ctx, &pkg.input.path, &dex::java_name(&class_desc));
        if v.get("status").and_then(Value::as_str) == Some("ok") {
            env = Environment {
                clean_room: false,
                engine: "builtin+jadx".into(),
                engine_version: None,
                host: craft_anything_evidence::host_triple(),
                language_id: None,
            };
            lims.push(Limitation::new(
                "third_party_decompiler",
                "The Java source comes from JADX, a third-party decompiler; it is an interpretation, the bytecode listing is the evidence.",
            ));
        }
        lims.extend(lim);
        v
    } else {
        json!({"status": "not_requested"})
    };
    let summary = format!(
        "{} ({}): {} instructions{}{}.",
        reference,
        dex_name,
        rows.len(),
        if tries.is_empty() { String::new() } else { format!(", {} try block(s)", tries.len()) },
        if complete { "" } else { " (incomplete)" }
    );
    let b = EvidenceBuilder::new("android_method_show", pkg.input.subject.clone(), env)
        .params(json!({"path": p.path, "class_name": p.class_name, "method_name": p.method_name, "overload_index": oi, "java_source": p.java_source, "offset": p.offset, "limit": p.limit}))
        .authority(Authority::OriginalFiles)
        .result(json!({
            "class": class_desc, "dex": dex_name, "method": reference, "signature": d.method_signature(&m),
            "access": dex::access_flags(m.access, "method"), "overload_index": oi,
            "overloads": ov.iter().map(|m| d.method_signature(m)).collect::<Vec<_>>(),
            "registers": regs.map(|r| r.0), "ins": regs.map(|r| r.1), "outs": regs.map(|r| r.2),
            "tries": tries, "instructions_total": rows.len(), "instructions": slice, "listing": listing,
            "java_source": java,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", pkg.input.path.display().to_string()))
        .location(Location::new("method", reference));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// android_class_users_find

fn android_class_users_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ReferencesParams = parse_params(params)?;
    let pkg = load_pkg(ctx, p.path.as_deref(), true)?;
    let (dexes, warnings) = parse_dexes(&pkg);
    if dexes.is_empty() {
        return Err(no_dex_error(&pkg));
    }
    let desc = dex::to_descriptor(&p.class_name);
    const MAX_REFS: usize = 100_000;
    let mut rows = Vec::new();
    let mut truncated = false;
    for (name, d) in &dexes {
        ctx.cancel.check()?;
        let (refs, more) = dex::references(d, &desc, p.method_name.as_deref(), MAX_REFS.saturating_sub(rows.len()));
        truncated |= more;
        rows.extend(refs.into_iter().map(|r| json!({"dex": name, "caller": r.caller, "offset": format!("{:04x}", r.offset), "instruction": r.instruction, "kind": r.kind, "target": r.target})));
    }
    let defined_in = find_class(&dexes, &desc).and_then(|(i, _)| dexes.get(i).map(|(n, _)| (*n).to_string()));
    let callers: std::collections::BTreeSet<&str> = rows.iter().filter_map(|r| r.get("caller").and_then(Value::as_str)).collect();
    let (slice, cov) = page(&rows, p.offset, p.limit);
    let what = match &p.method_name {
        Some(m) => format!("{}.{m}", dex::java_name(&desc)),
        None => dex::java_name(&desc),
    };
    let summary = format!(
        "{} reference(s) to {what} from {} method(s) across {} DEX file(s){}.",
        rows.len(),
        callers.len(),
        dexes.len(),
        match &defined_in {
            Some(d) => format!("; defined in {d}"),
            None => "; not defined in this package (framework or library class)".into(),
        }
    );
    let mut lims = warn_lims(&warnings);
    lims.push(Limitation::new(
        "static_references_only",
        "Only direct bytecode references are found; reflection, JNI, string-built class names and code loaded at run time are not.",
    ));
    let mut cov = cov;
    if truncated {
        lims.push(Limitation::new("truncated", format!("stopped after {MAX_REFS} references")));
        cov.status = CoverageStatus::Partial;
    }
    let b = ev(ctx, "android_class_users_find", &pkg, json!({"path": p.path, "class_name": p.class_name, "method_name": p.method_name, "offset": p.offset, "limit": p.limit}))
        .result(json!({"class": desc, "method_name": p.method_name, "defined_in": defined_in, "references_total": rows.len(), "callers": callers.len(), "references": slice}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("class", desc.clone()));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// android_resources_read

fn android_resources_read(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ResourcesParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), MAX_APK)?;
    let is_arsc = input.bytes.get(..2) == Some(&[0x02, 0x00]);
    let pkg = if is_arsc { Pkg { input, zip: None, dexes: Vec::new(), warnings: Vec::new() } } else { load_pkg(ctx, p.path.as_deref(), false)? };
    let arsc_bytes: Vec<u8> = if is_arsc {
        pkg.input.bytes.to_vec()
    } else {
        match member(&pkg, "resources.arsc") {
            Some(Ok(b)) => b,
            Some(Err(e)) => return Err(ToolError::new(ErrorCode::NotSupported, format!("resources.arsc could not be read: {e}"))),
            None => {
                return Err(ToolError::unsupported(format!("{} has no resources.arsc", pkg.input.name))
                    .with_remediation("Some APKs (feature splits, resource-less libraries) carry no compiled resources."));
            }
        }
    };
    let table = arsc::parse(&arsc_bytes, arsc::Limits::default()).map_err(|e| format_err(e, "an Android resource table"))?;
    // The table names the unqualified locale "", people call it "default".
    let named = |l: &str| if l.is_empty() { "default".to_string() } else { l.to_string() };
    let wanted: BTreeSet<&str> = p.locale.iter().chain(&p.only_locales).map(|l| if l == "default" { "" } else { l.as_str() }).collect();
    let want = |l: &str| wanted.is_empty() || wanted.contains(l);
    let filtered: Vec<&arsc::Entry> =
        table.entries.iter().filter(|e| want(&e.locale)).filter(|e| p.type_name.as_deref().is_none_or(|t| e.type_name == t)).collect();
    let (slice, mut cov) = page(&filtered, p.offset, p.limit);
    let present: BTreeSet<&str> = table.entries.iter().map(|e| e.locale.as_str()).collect();
    let locales: Vec<String> = present.iter().map(|l| named(l)).collect();
    let not_found: Vec<String> = wanted.difference(&present).map(|l| named(l)).collect();
    let mut capped = Vec::new();
    let strings = if p.with_strings {
        let mut m = serde_json::Map::new();
        for (loc, list) in table.strings_by_locale() {
            if !want(&loc) {
                continue;
            }
            if list.len() > MAX_LOCALE_STRINGS {
                capped.push(named(&loc));
            }
            let obj: serde_json::Map<String, Value> = list.into_iter().take(MAX_LOCALE_STRINGS).map(|(k, v)| (k, Value::String(v))).collect();
            m.insert(named(&loc), Value::Object(obj));
        }
        Value::Object(m)
    } else {
        Value::Null
    };
    let mut lims = warn_lims(&table.warnings);
    if !capped.is_empty() {
        lims.push(Limitation::new(
            "strings_capped",
            format!("Only the first {MAX_LOCALE_STRINGS} strings of {} are listed; the rest are in entries (type_name string).", capped.join(", ")),
        ));
    }
    if !not_found.is_empty() {
        lims.push(Limitation::new("locales_not_found", format!("The app has no resources for {}.", not_found.join(", "))));
    }
    let mut xml = Vec::new();
    for f in p.xml_files.iter().take(16) {
        if is_arsc {
            lims.push(Limitation::new("xml_needs_apk", "xml_files can only be decoded from an APK, not a bare resources.arsc."));
            break;
        }
        match member(&pkg, f) {
            Some(Ok(b)) => match axml::parse(&b) {
                Ok(doc) => xml.push(json!({"path": f, "xml": doc.to_xml(256 * 1024), "warnings": doc.warnings})),
                Err(e) => xml.push(json!({"path": f, "error": e.to_string()})),
            },
            Some(Err(e)) => xml.push(json!({"path": f, "error": e})),
            None => xml.push(json!({"path": f, "error": "no such file in the APK"})),
        }
    }
    if p.xml_files.len() > 16 {
        lims.push(Limitation::new("xml_files_capped", "Only the first 16 xml_files were decoded."));
    }
    if table.truncated {
        lims.push(Limitation::new("truncated", "The table holds more entries than the decoder's limit; later entries are missing."));
        cov.status = CoverageStatus::Partial;
    }
    lims.push(Limitation::new("references_unresolved", "Values that point at other resources are shown as @0x… ids; look them up in this table's entries."));
    let summary = format!(
        "{} package(s), {} resource values in {} locale(s) ({}); showing {} entr{}.",
        table.packages.len(),
        table.entries.len(),
        locales.len(),
        locales.iter().take(12).cloned().collect::<Vec<_>>().join(", "),
        slice.len(),
        if slice.len() == 1 { "y" } else { "ies" }
    );
    let b = ev(
        ctx,
        "android_resources_read",
        &pkg,
        json!({"path": p.path, "with_strings": p.with_strings, "locale": p.locale, "only_locales": p.only_locales, "type_name": p.type_name, "xml_files": p.xml_files, "offset": p.offset, "limit": p.limit}),
    )
    .result(json!({
            "packages": table.packages, "global_strings": table.global_strings, "locales": locales, "locales_not_found": not_found,
            "entries_total": table.entries.len(), "entries_matching": filtered.len(), "entries": slice,
            "strings": strings, "xml": xml,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(cov);
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// engines_apktool_check

fn engines_apktool_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _p: ClientParams = parse_params(params)?;
    let settings = &ctx.session.settings;
    let found = craft_anything_engines::locate("apktool", &settings.engines.tools, &settings.engine_store_dir());
    let mut lims = Vec::new();
    let (version, error) = match &found {
        // A pinned install is apktool's jar, run with Java.
        Some(path) => match super::external_disasm_tools::program_for(ctx, path) {
            Err(e) => (None, Some(format!("{} (Apktool's jar runs on Java)", e.message))),
            Ok((exe, pre)) => {
                let cancel = ctx.cancel.clone();
                match craft_anything_platform::Process::new(&exe)
                    .args(&pre)
                    .arg("--version")
                    .timeout(Duration::from_secs(20))
                    .stdout_cap(64 * 1024)
                    .stderr_cap(64 * 1024)
                    .cancel_when(move || cancel.is_cancelled())
                    .label("apktool")
                    .run()
                {
                    Ok(o) if o.success => (o.stdout_text().lines().map(str::trim).find(|l| !l.is_empty()).map(str::to_string), None),
                    Ok(o) => (None, Some(format!("exited with {:?}: {}", o.code, tail(&o.stderr_text())))),
                    Err(e) => (None, Some(e.message)),
                }
            }
        },
        None => (None, None),
    };
    if let Some(e) = &error {
        lims.push(Limitation::new("version_probe_failed", format!("Apktool was found but `--version` failed: {e}")));
    }
    let available = found.is_some() && error.is_none();
    let summary = match (&found, &version) {
        (Some(p), Some(v)) => format!("Apktool {v} is available at {}. The built-in decoder is used by default and needs nothing installed.", p.display()),
        (Some(p), None) => format!("Apktool was found at {} but did not report a version. The built-in decoder works without it.", p.display()),
        (None, _) => "Apktool is not installed. That's fine: android_resources_read and android_package_show use Craft Anything's built-in decoders.".into(),
    };
    let b = builder(ctx, "engines_apktool_check", Subject { kind: "engine".into(), sha256: None, name: Some("apktool".into()) }, json!({}))
        .result(json!({
            "available": available, "path": found, "version": version, "error": error,
            "built_in_decoder": true, "default_decoder": "built-in",
            "remediation": if found.is_none() { Some("Optional: install Apktool and set its path in Settings → Engines.") } else { None },
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OurRun)
        .limitations(lims)
        .coverage(Coverage::complete(1));
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_testkit::android as fx;
    use serde_json::json;

    fn apk() -> String {
        craft_anything_testkit::temp_file("notes.apk", &fx::notes_apk()).to_string_lossy().into_owned()
    }

    /// An APK whose manifest targets `target`, with one component for each export rule.
    fn components_apk(target: i32) -> String {
        use fx::AxNode::{End, Start};
        use fx::AxVal::{Bool, Str};
        let name = |v| fx::a("name", 0x0101_0003, Str(v));
        let exported = |v| fx::a("exported", 0x0101_0010, Bool(v));
        let perm = |v| fx::a("permission", 0x0101_0006, Str(v));
        let filter_action = "android.intent.action.VIEW";
        let manifest = fx::axml(&[
            Start("manifest", vec![fx::AxAttr { name: "package", res_id: None, val: Str("com.example.c") }]),
            Start("uses-sdk", vec![fx::a("targetSdkVersion", 0x0101_0270, fx::AxVal::Int(target))]),
            End("uses-sdk"),
            Start("permission", vec![name("com.example.c.GUARD"), fx::a("protectionLevel", 0x0101_0009, fx::AxVal::Hex(2))]),
            End("permission"),
            Start("application", vec![]),
            // Explicitly open.
            Start("activity", vec![name(".Open"), exported(true)]),
            Start("intent-filter", vec![]),
            Start("action", vec![name(filter_action)]),
            End("action"),
            Start("category", vec![name("android.intent.category.BROWSABLE")]),
            End("category"),
            Start("data", vec![fx::a("scheme", 0x0101_0027, Str("https")), fx::a("host", 0x0101_0028, Str("example.com"))]),
            End("data"),
            End("intent-filter"),
            End("activity"),
            // Exported only by the old implicit rule.
            Start("receiver", vec![name(".Implied")]),
            Start("intent-filter", vec![]),
            Start("action", vec![name(filter_action)]),
            End("action"),
            End("intent-filter"),
            End("receiver"),
            // Exported, behind a permission.
            Start("service", vec![name(".Guarded"), exported(true), perm("com.example.c.GUARD")]),
            End("service"),
            // Private by default.
            Start("service", vec![name(".Private")]),
            End("service"),
            // A provider with neither value: open only for very old targets.
            Start("provider", vec![name(".Files"), fx::a("authorities", 0x0101_0018, Str("com.example.c.files"))]),
            End("provider"),
            // Disabled, but still listed.
            Start("activity", vec![name(".Off"), exported(true), fx::a("enabled", 0x0101_000e, Bool(false))]),
            End("activity"),
            End("application"),
            End("manifest"),
        ]);
        let zip = craft_anything_testkit::electron::zip_stored(&[("AndroidManifest.xml", &manifest)]);
        craft_anything_testkit::temp_file("c.apk", &zip).to_string_lossy().into_owned()
    }

    fn component<'a>(v: &'a serde_json::Value, name: &str) -> &'a serde_json::Value {
        v["result"]["components"].as_array().unwrap().iter().find(|c| c["name"] == name).unwrap_or_else(|| panic!("no {name}: {v}"))
    }

    #[test]
    fn a_permission_on_the_application_guards_its_components() {
        use fx::AxNode::{End, Start};
        use fx::AxVal::{Bool, Str};
        let name = |v| fx::a("name", 0x0101_0003, Str(v));
        let exported = fx::a("exported", 0x0101_0010, Bool(true));
        let perm = |v| fx::a("permission", 0x0101_0006, Str(v));
        let manifest = fx::axml(&[
            Start("manifest", vec![fx::AxAttr { name: "package", res_id: None, val: Str("com.example.c") }]),
            Start("application", vec![perm("com.example.c.APP")]),
            Start("activity", vec![name(".Plain"), exported.clone()]),
            End("activity"),
            Start("service", vec![name(".Own"), exported.clone(), perm("com.example.c.OWN")]),
            End("service"),
            End("application"),
            End("manifest"),
        ]);
        let zip = craft_anything_testkit::electron::zip_stored(&[("AndroidManifest.xml", &manifest)]);
        let path = craft_anything_testkit::temp_file("guarded.apk", &zip);
        let e = Engine::new(crate::testing::session());
        let v = call(&e, "android_components_list", json!({"path": path}));
        let plain = component(&v, "com.example.c.Plain");
        assert_eq!(
            (&plain["who_can_reach"], &plain["permission"], &plain["permission_from_application"]),
            (&json!("apps_with_permission"), &json!("com.example.c.APP"), &json!(true))
        );
        let own = component(&v, "com.example.c.Own");
        assert_eq!((&own["permission"], &own["permission_from_application"]), (&json!("com.example.c.OWN"), &json!(false)));
    }

    #[test]
    fn components_follow_the_export_rules_of_each_target_sdk() {
        let e = Engine::new(crate::testing::session());
        // A modern target: the implicit rule no longer exports anything.
        let v = call(&e, "android_components_list", json!({"path": components_apk(34)}));
        assert_eq!(v["confidence"], "observed");
        let open = component(&v, "com.example.c.Open");
        assert_eq!((&open["reachable_from_outside"], &open["who_can_reach"], &open["export_source"]), (&json!(true), &json!("any_app"), &json!("explicit")));
        let f = &open["intent_filters"][0];
        assert_eq!(f["actions"][0], "android.intent.action.VIEW");
        assert_eq!(f["categories"][0], "android.intent.category.BROWSABLE");
        assert_eq!(f["data"][0], "scheme=https host=example.com");
        assert_eq!(component(&v, "com.example.c.Implied")["reachable_from_outside"], false);
        let guarded = component(&v, "com.example.c.Guarded");
        assert_eq!((&guarded["who_can_reach"], &guarded["permission_protection_level"]), (&json!("apps_with_permission"), &json!("0x2")));
        let private = component(&v, "com.example.c.Private");
        assert_eq!((&private["who_can_reach"], &private["export_source"]), (&json!("own_app_only"), &json!("default_not_exported")));
        assert_eq!(component(&v, "com.example.c.Files")["reachable_from_outside"], false);
        assert_eq!(component(&v, "com.example.c.Off")["disabled_in_manifest"], true);
        assert_eq!(v["result"]["by_kind"]["service"]["total"], 2);
        let lims = v["limitations"].as_array().unwrap();
        for code in ["implicit_export_rules", "manifest_only", "missing_exported_attribute", "disabled_components"] {
            assert!(lims.iter().any(|l| l["code"] == code), "{code}: {lims:?}");
        }
        assert!(lims.iter().find(|l| l["code"] == "implicit_export_rules").unwrap().to_string().contains("SDK 34"));

        // Below 31 intent filters export; up to 16 providers do too.
        let v = call(&e, "android_components_list", json!({"path": components_apk(30)}));
        let implied = component(&v, "com.example.c.Implied");
        assert_eq!((&implied["reachable_from_outside"], &implied["export_source"]), (&json!(true), &json!("implied_by_intent_filter")));
        assert_eq!(component(&v, "com.example.c.Files")["reachable_from_outside"], false);
        let v = call(&e, "android_components_list", json!({"path": components_apk(16)}));
        let files = component(&v, "com.example.c.Files");
        assert_eq!((&files["reachable_from_outside"], &files["export_source"]), (&json!(true), &json!("default_for_old_target_sdk")));
    }

    #[test]
    fn components_filter_and_page() {
        let e = Engine::new(crate::testing::session());
        let p = components_apk(34);
        let v = call(&e, "android_components_list", json!({"path": p, "kind": "service"}));
        assert_eq!(v["result"]["matching"], 2);
        assert_eq!(v["result"]["total"], 6);
        let v = call(&e, "android_components_list", json!({"path": p, "reachable_only": true}));
        assert!(v["result"]["components"].as_array().unwrap().iter().all(|c| c["reachable_from_outside"] == true));
        assert_eq!(v["result"]["matching"], v["result"]["reachable_from_outside"]);
        let v = call(&e, "android_components_list", json!({"path": p, "limit": 2, "offset": 1}));
        assert_eq!(v["result"]["components"].as_array().unwrap().len(), 2);
        assert_eq!(v["coverage"]["next_offset"], 3);
        assert!(!call_err(&e, "android_components_list", json!({"path": p, "kind": "widget"})).message.is_empty());

        // The shared sample app works too; a bare DEX and an APK with no manifest don't.
        let v = call(&e, "android_components_list", json!({"path": apk()}));
        assert_eq!(v["result"]["total"], 3);
        let dex = craft_anything_testkit::temp_file("c.dex", &fx::notes_dex());
        assert!(call_err(&e, "android_components_list", json!({"path": dex})).message.contains("no manifest"));
        let zip = craft_anything_testkit::electron::zip_stored(&[("readme.txt", b"hi")]);
        let empty = craft_anything_testkit::temp_file("e.apk", &zip);
        assert!(call_err(&e, "android_components_list", json!({"path": empty})).message.contains("no AndroidManifest"));
        let zip = craft_anything_testkit::electron::zip_stored(&[("AndroidManifest.xml", b"junk")]);
        let bad = craft_anything_testkit::temp_file("b.apk", &zip);
        assert!(!call_err(&e, "android_components_list", json!({"path": bad})).message.is_empty());
    }

    #[test]
    fn package_facts() {
        let e = Engine::new(crate::testing::session());
        let v = call(&e, "android_package_show", json!({"path": apk()}));
        let r = &v["result"];
        assert_eq!(r["package"], "com.example.notes");
        assert_eq!(r["version_code"], "42");
        assert_eq!(r["manifest"]["uses_permissions"][1], "android.permission.CAMERA");
        assert_eq!(r["manifest"]["components"].as_array().unwrap().len(), 3);
        assert_eq!(r["signing"]["schemes"], json!(["v1", "v2", "v3"]));
        assert_eq!(r["signing"]["v1"][0]["certificates"][0]["subject"], "CN=Craft Test, O=Craft Org");
        let sha = &r["signing"]["v1"][0]["certificates"][0]["sha256"];
        assert_eq!(&r["signing"]["signing_block"]["signers"][0]["certificates"][0]["sha256"], sha);
        assert_eq!(r["dex"].as_array().unwrap().len(), 2);
        assert_eq!(r["dex"][0]["classes"], 2);
        assert_eq!(r["native_libraries"]["arm64-v8a"][0]["name"], "libnotes.so");
        assert!(r["manifest_xml"].as_str().unwrap().contains("<activity"));
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "verification_scope"));
        assert!(v["summary"].as_str().unwrap().contains("3 components (1 exported)"), "{}", v["summary"]);
        // notes_apk carries placeholder signatures, so they must report as NOT verified.
        assert_eq!(r["signing"]["signing_block"]["signers"][0]["verification"]["verified"], false);
        assert!(v["summary"].as_str().unwrap().contains("NOT verified"), "{}", v["summary"]);
    }

    #[test]
    fn signed_apk_signatures_verify() {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("signed.apk", &fx::signed_apk(false));
        let v = call(&e, "android_package_show", json!({"path": p}));
        let r = &v["result"];
        assert_eq!(r["signing"]["schemes"], json!(["v1", "v2", "v3"]));
        // Every v2/v3 signer verifies: signature valid AND recomputed content digest matches.
        for s in r["signing"]["signing_block"]["signers"].as_array().unwrap() {
            assert_eq!(s["verification"]["signature_valid"]["status"], "valid", "{s}");
            assert_eq!(s["verification"]["digest_matches"], true, "{s}");
            assert_eq!(s["verification"]["verified"], true, "{s}");
            assert_eq!(s["verification"]["certificate_sha256"].as_str().unwrap().len(), 64);
        }
        // The v1 JAR signature verifies too (PKCS#7 over the .SF, and MANIFEST.MF per-file digests).
        let v1 = &r["signing"]["v1"][0];
        assert_eq!(v1["pkcs7"]["signature_valid"]["status"], "valid", "{v1}");
        assert_eq!(v1["integrity"]["manifest_digest_matches"], true);
        assert_eq!(v1["integrity"]["files_mismatched"], 0);
        assert!(v1["integrity"]["files_matched"].as_u64().unwrap() >= 3);
        assert!(v["summary"].as_str().unwrap().contains("cryptographically VERIFIED"), "{}", v["summary"]);

        // A tampered APK: signatures stay well-formed but every content digest must fail.
        let bad = craft_anything_testkit::temp_file("bad.apk", &fx::signed_apk(true));
        let vb = call(&e, "android_package_show", json!({"path": bad}));
        let rb = &vb["result"];
        assert_eq!(rb["signing"]["signing_block"]["signers"][0]["verification"]["digest_matches"], false);
        assert_eq!(rb["signing"]["signing_block"]["signers"][0]["verification"]["verified"], false);
    }

    #[test]
    fn classes_methods_and_references() {
        let e = Engine::new(crate::testing::session());
        let path = apk();
        let s = call(&e, "android_classes_find", json!({"path": path, "query": "notes"}));
        assert_eq!(s["result"]["matches"], 3);
        let page = call(&e, "android_classes_find", json!({"path": path, "limit": 1}));
        assert_eq!(page["coverage"]["next_offset"], 1);
        let c = call(&e, "android_class_show", json!({"path": path, "class_name": "com.example.notes.Util"}));
        let methods = c["result"]["methods"].as_array().unwrap();
        assert_eq!(methods.len(), 2);
        assert_eq!(methods[1]["overload_index"], 1);
        let m = call(&e, "android_method_show", json!({"path": path, "class_name": "Lcom/example/notes/MainActivity;", "method_name": "onCreate"}));
        assert_eq!(m["result"]["instructions"][0]["text"], "const-string v0, \"Hello, Craft!\"");
        assert!(m["result"]["listing"].as_str().unwrap().contains("invoke-super {v1, v2}, Landroid/app/Activity;->onCreate(Landroid/os/Bundle;)V"));
        assert_eq!(m["result"]["java_source"]["status"], "not_requested");
        let ov = call(&e, "android_method_show", json!({"path": path, "class_name": "com.example.notes.Util", "method_name": "log", "overload_index": 1}));
        assert_eq!(ov["result"]["signature"], "public static void log(int)");
        let pick = call(&e, "android_method_show", json!({"path": path, "class_name": "com.example.notes.MainActivity", "method_name": "pick"}));
        assert_eq!(pick["result"]["tries"][0]["handlers"][0]["exception"], "Ljava/lang/RuntimeException;");
        let r = call(&e, "android_class_users_find", json!({"path": path, "class_name": "com.example.notes.Util", "method_name": "log"}));
        assert_eq!(r["result"]["references_total"], 3, "{}", r["result"]);
        assert!(
            r["result"]["references"]
                .as_array()
                .unwrap()
                .iter()
                .any(|x| x["dex"] == "classes2.dex" && x["caller"] == "Lcom/example/notes/extra/Helper;->go()V")
        );
        assert_eq!(r["result"]["defined_in"], "classes.dex");
        let err = call_err(&e, "android_class_show", json!({"path": path, "class_name": "com.example.Missing"}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::BadInput);
        let err = call_err(&e, "android_method_show", json!({"path": path, "class_name": "com.example.notes.Util", "method_name": "log", "overload_index": 5}));
        assert!(err.message.contains("out of range"));
        // A bare DEX works too.
        let dex = craft_anything_testkit::temp_file("classes.dex", &fx::notes_dex());
        let d = call(&e, "android_classes_find", json!({"path": dex}));
        assert_eq!(d["result"]["matches"], 2);
    }

    #[test]
    fn java_source_without_jadx_is_a_limitation() {
        let mut s = crate::testing::session();
        s.settings.engines.tools.jadx = Some("/nonexistent/jadx".into());
        s.settings.engines.store_dir = Some("/nonexistent-store".into());
        let e = Engine::new(s);
        let path = apk();
        let m = call(&e, "android_method_show", json!({"path": path, "class_name": "com.example.notes.Util", "method_name": "log", "java_source": true}));
        let status = m["result"]["java_source"]["status"].as_str().unwrap();
        // Either JADX is genuinely on PATH on this machine or it is reported as unavailable.
        assert!(status == "unavailable" || status == "ok" || status == "failed", "{status}");
        if status == "unavailable" {
            assert!(m["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "jadx_not_installed"));
        }
    }

    #[test]
    fn resources() {
        let e = Engine::new(crate::testing::session());
        let path = apk();
        let r = call(&e, "android_resources_read", json!({"path": path, "xml_files": ["res/layout/main.xml", "res/missing.xml"]}));
        assert_eq!(r["result"]["locales"], json!(["default", "fr"]));
        assert_eq!(r["result"]["strings"]["fr"]["greeting"], "Bonjour");
        assert_eq!(r["result"]["strings"]["default"]["app_name"], "Notes");
        assert!(r["result"]["xml"][0]["xml"].as_str().unwrap().contains("android:text=\"@0x7f010001\""));
        assert!(r["result"]["xml"][1]["error"].is_string());
        let fr = call(&e, "android_resources_read", json!({"path": path, "locale": "fr", "type_name": "string"}));
        assert_eq!(fr["result"]["entries_matching"], 2);
        assert!(fr["result"]["strings"].get("default").is_none());
        // several locales in one call, each its own table; one the app lacks is named
        let two = call(&e, "android_resources_read", json!({"path": path, "only_locales": ["default", "fr"], "type_name": "string"}));
        assert_eq!(two["result"]["strings"]["fr"]["greeting"], "Bonjour");
        assert_eq!(two["result"]["strings"]["default"]["app_name"], "Notes");
        assert_eq!(two["result"]["locales_not_found"], json!([]));
        let some = call(&e, "android_resources_read", json!({"path": path, "locale": "fr", "only_locales": ["de"]}));
        assert_eq!(some["result"]["strings"].as_object().unwrap().keys().collect::<Vec<_>>(), vec!["fr"]);
        assert_eq!(some["result"]["locales_not_found"], json!(["de"]));
        assert!(some["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "locales_not_found"));
        let arsc = craft_anything_testkit::temp_file("resources.arsc", &fx::resources_arsc());
        let a = call(&e, "android_resources_read", json!({"path": arsc, "type_name": "style"}));
        assert_eq!(a["result"]["entries"][0]["bag"][0]["value"], "#ff336699");
    }

    #[test]
    fn apktool_client_reports() {
        let mut s = crate::testing::session();
        s.settings.engines.store_dir = Some("/nonexistent-store".into());
        let e = Engine::new(s);
        let v = call(&e, "engines_apktool_check", json!({}));
        assert_eq!(v["result"]["built_in_decoder"], true);
    }

    #[test]
    fn hostile_packages_do_not_panic() {
        let e = Engine::new(crate::testing::session());
        let apk_bytes = fx::notes_apk();
        for (i, m) in craft_anything_testkit::mutations(&apk_bytes).into_iter().enumerate().step_by(3) {
            let p = craft_anything_testkit::temp_file(&format!("m{i}.apk"), &m);
            for (tool, params) in [
                ("android_package_show", json!({"path": p})),
                ("android_classes_find", json!({"path": p})),
                ("android_method_show", json!({"path": p, "class_name": "com.example.notes.MainActivity", "method_name": "pick"})),
                ("android_class_users_find", json!({"path": p, "class_name": "com.example.notes.Util"})),
                ("android_resources_read", json!({"path": p, "xml_files": ["res/layout/main.xml"]})),
            ] {
                let _ = e.call(tool, params, crate::CallOptions::new(crate::Caller::Mcp));
            }
        }
    }
}
