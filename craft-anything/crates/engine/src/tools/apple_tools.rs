//! Apple tools with built-in parsers: Mach-O structure and slices, code signatures, property
//! lists, Swift demangling, compiled Interface Builder documents, keyed archives, asset catalogs
//! and dynamic-library resolution inside app bundles. No Apple tooling is needed, so all of it
//! works on any host.

use super::artifact_tools::{WalkOptions, rel_to, walk_dir};
use super::native_common::{page, spec};
use super::static_input::{self, Input, builder, format_err};
use crate::target::TargetKind;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, ErrorCode, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_formats::{car, codesign, keyed_archive, macho_deps, nib, plist, swift_demangle, verify};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::Digest as _;
use std::collections::{BTreeMap, BTreeSet, HashSet, VecDeque};
use std::path::{Component, Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Apple;
    let e = Effects::EVIDENCE;
    let n = Requires::Nothing;
    vec![
        spec(
            "apple_macho_show",
            "Mach-O structure",
            "Header, architecture slices, every load command (libraries with versions, run paths, UUID, build versions, encryption, code-signature range, entry point, segments) plus a page of imports and exports of a Mach-O file or an app bundle's executable. Built-in parser; uses the active target unless path is given.",
            "See how a Mac or iPhone program is put together and which libraries it needs.",
            Apple,
            e,
            n,
            schema_of::<MachoParams>,
            apple_macho_show,
        ),
        spec(
            "apple_signature_show",
            "Code signature",
            "Decode a Mach-O code signature: code directories (identifier, team id, flags, hash type, slot counts, cdhash), page and special-slot hashes re-computed and compared, requirements as text, entitlements, and whether a CMS signature is present. The CMS signature itself is not verified.",
            "See who signed a Mac or iPhone program and what it is allowed to do.",
            Apple,
            e,
            n,
            schema_of::<MachoParams>,
            apple_signature_show,
        ),
        spec(
            "apple_plist_show",
            "Property list",
            "Read a property list (XML or binary) as normalised JSON: a .plist file, an app bundle's Info.plist, or the Info.plist embedded in a Mach-O executable. Uses the active target unless path is given.",
            "Read an Apple settings file (plist), such as an app's Info.plist.",
            Apple,
            e | Effects::CARRIES_TARGET_CONTENT,
            n,
            schema_of::<PathParams>,
            apple_plist_show,
        ),
        spec(
            "apple_slices_list",
            "Architectures",
            "List the architecture slices of a thin or universal Mach-O (CPU type and subtype, offset, size, alignment, file type).",
            "See which kinds of processor a Mac or iPhone program runs on.",
            Apple,
            e,
            n,
            schema_of::<PathParams>,
            apple_slices_list,
        ),
        spec(
            "apple_swift_symbols_demangle",
            "Demangle Swift symbols",
            "Turn mangled Swift symbol names into readable declarations, in order, each marked demangled, unchanged (not a Swift name) or invalid. Built-in demangler; no target needed.",
            "Turn scrambled Swift names into readable ones.",
            Apple,
            e,
            n,
            schema_of::<DemangleParams>,
            apple_swift_symbols_demangle,
        ),
        spec(
            "apple_nib_decode",
            "Interface Builder documents",
            "Decode compiled nib and storyboard files (NIB archives and keyed-archive nibs; .nib, .storyboardc and whole app bundles) into object graphs: objects with classes and values, outlet and action connections, and the view hierarchy. Bounded by max_documents, max_objects and max_connections.",
            "See the screens, buttons and their wiring inside an app's interface files.",
            Apple,
            e,
            n,
            schema_of::<IbParams>,
            apple_nib_decode,
        ),
        spec(
            "apple_archive_decode",
            "Keyed archive",
            "Read an NSKeyedArchiver property list: archiver, $top entries, the object table (paged) and the object graph below a root with references resolved (cycles and repeats become $ref).",
            "Unpack saved app data written by Apple's object archiver.",
            Apple,
            e,
            n,
            schema_of::<KeyedArchiveParams>,
            apple_archive_decode,
        ),
        spec(
            "apple_assets_list",
            "Asset catalog",
            "Read a compiled asset catalog (Assets.car): BOM blocks and variables, catalog header, key format, facet names, appearances and a page of renditions (name, size, scale, pixel format, layout). Image pixels are not decoded.",
            "List the images and colours packed into an app.",
            Apple,
            e,
            n,
            schema_of::<AssetCatalogParams>,
            apple_assets_list,
        ),
        spec(
            "apple_dylibs_resolve",
            "Library resolution",
            "Follow how the dynamic linker would find every library an app bundle's programs load: @executable_path, @loader_path and @rpath chains, load-once, weak links and architecture slices, with outcomes resolved, system, unresolved or undetermined and findings such as skipped-rpath-entry. Never follows links out of the bundle.",
            "Check that an app's built-in libraries can all be found, and how.",
            Apple,
            e,
            n,
            schema_of::<DylibParams>,
            apple_dylibs_resolve,
        ),
    ]
}

const MAX_FILE: u64 = 1 << 30;

fn d_limit() -> usize {
    200
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PathParams {
    /// Absolute path of a file or app bundle; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MachoParams {
    /// Absolute path of a Mach-O file or app bundle; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Slice of a universal binary (arm64, arm64e, x86_64, …); arm64, then x86_64, then the first when omitted.
    #[serde(default)]
    pub architecture: Option<String>,
    /// First import/export of the page.
    #[serde(default)]
    pub offset: usize,
    /// Imports and exports per page (1–5000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DemangleParams {
    /// Mangled names, one per entry (1–10000; single line, no NUL).
    pub symbols: Vec<String>,
}

fn d_docs() -> usize {
    64
}
fn d_objects() -> usize {
    20_000
}
fn d_conns() -> usize {
    40_000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct IbParams {
    /// Absolute path of a .nib file, .nib or .storyboardc folder, or app bundle; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Most documents decoded (1–64).
    #[serde(default = "d_docs")]
    pub max_documents: usize,
    /// Most objects listed across documents (1–20000).
    #[serde(default = "d_objects")]
    pub max_objects: usize,
    /// Most connections listed across documents (1–40000).
    #[serde(default = "d_conns")]
    pub max_connections: usize,
}

fn d_ka_limit() -> usize {
    20_000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct KeyedArchiveParams {
    /// Absolute path of the archive; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// $top entry to project (default: "root", else the first).
    #[serde(default)]
    pub root: Option<String>,
    /// First row of the object table page.
    #[serde(default)]
    pub offset: usize,
    /// Object rows per page (1–20000).
    #[serde(default = "d_ka_limit")]
    pub limit: usize,
}

fn d_car_limit() -> usize {
    1000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AssetCatalogParams {
    /// Absolute path of Assets.car or an app bundle containing one; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// First rendition of the page.
    #[serde(default)]
    pub offset: usize,
    /// Renditions per page (1–10000).
    #[serde(default = "d_car_limit")]
    pub limit: usize,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DyldArch {
    Arm64,
    Arm64e,
    #[serde(rename = "x86_64")]
    X86_64,
}

impl DyldArch {
    fn name(self) -> &'static str {
        match self {
            DyldArch::Arm64 => "arm64",
            DyldArch::Arm64e => "arm64e",
            DyldArch::X86_64 => "x86_64",
        }
    }
}

fn d_images() -> usize {
    2000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DylibParams {
    /// Absolute path of an app bundle (or a Mach-O inside one); the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Extra folders searched for absolute install names outside the bundle (like a system root).
    #[serde(default)]
    pub roots: Vec<String>,
    /// Architecture slice to follow; each entry program's preferred slice when omitted.
    #[serde(default)]
    pub architecture: Option<DyldArch>,
    /// Most images loaded and examined (1–20000).
    #[serde(default = "d_images")]
    pub max_images: usize,
}

// ---------------------------------------------------------------------------------------------
// Inputs

/// The path a tool works on: `path`, or the active target's path.
fn input_path(ctx: &Ctx<'_>, path: Option<&str>) -> Result<PathBuf, ToolError> {
    match path {
        Some(p) => super::artifact_tools::abs_path(p, "path"),
        None => Ok(ctx.session.active().map_err(|e| e.with_remediation("Open a target first, or pass path."))?.target.path.clone()),
    }
}

fn read_plist_file(p: &Path) -> Option<plist::Value> {
    let meta = std::fs::metadata(p).ok()?;
    if !meta.is_file() || meta.len() > 64 << 20 {
        return None;
    }
    plist::parse(&std::fs::read(p).ok()?).ok()
}

/// The Info.plist of a bundle folder (macOS `Contents/Info.plist`, iOS `Info.plist`, framework
/// `Resources/Info.plist`).
fn bundle_info_plist(dir: &Path) -> Option<PathBuf> {
    [dir.join("Contents/Info.plist"), dir.join("Info.plist"), dir.join("Resources/Info.plist"), dir.join("Versions/Current/Resources/Info.plist")]
        .into_iter()
        .find(|p| p.is_file())
}

/// A bundle's main executable.
fn bundle_executable(dir: &Path) -> Option<PathBuf> {
    let exe_name =
        bundle_info_plist(dir).and_then(|p| read_plist_file(&p)).and_then(|v| v.get("CFBundleExecutable").and_then(plist::Value::as_str).map(str::to_string));
    let stem = dir.file_stem().map(|s| s.to_string_lossy().into_owned());
    let names: Vec<String> = exe_name.into_iter().chain(stem).collect();
    for n in &names {
        if !safe_name(n) {
            continue;
        }
        for c in [dir.join("Contents/MacOS").join(n), dir.join(n), dir.join("Versions/Current").join(n)] {
            if c.is_file() {
                return Some(c);
            }
        }
    }
    None
}

fn safe_name(n: &str) -> bool {
    !n.is_empty() && !n.contains('/') && !n.contains('\\') && n != ".." && n != "."
}

/// A Mach-O input: a file, or a bundle folder's executable.
fn macho_input(ctx: &Ctx<'_>, path: Option<&str>) -> Result<Input, ToolError> {
    let p = input_path(ctx, path)?;
    if p.is_dir() {
        let exe = bundle_executable(&p).ok_or_else(|| {
            ToolError::invalid(format!("{} is a folder without a bundle executable", p.display()))
                .with_remediation("Pass an .app/.framework bundle with an Info.plist naming CFBundleExecutable, or the Mach-O file itself.")
        })?;
        return static_input::load_path(&exe.to_string_lossy(), MAX_FILE);
    }
    if path.is_none() {
        return static_input::load(ctx, None, MAX_FILE);
    }
    static_input::load_path(&p.to_string_lossy(), MAX_FILE)
}

fn not_macho(name: &str) -> ToolError {
    ToolError::new(ErrorCode::NotSupported, format!("{name} is not a Mach-O file"))
        .with_remediation("Run triage to see what it is; Mach-O tools need a Mac or iPhone program.")
}

/// All slices, the chosen one, its bytes and its load commands.
type SliceOf<'a> = (Vec<macho_deps::Slice>, macho_deps::Slice, &'a [u8], macho_deps::MachoDeps);

/// The chosen slice's bytes and its load commands.
fn slice_of<'a>(inp: &'a Input, arch: Option<&str>) -> Result<SliceOf<'a>, ToolError> {
    let data: &[u8] = &inp.bytes;
    if !macho_deps::is_thin(data) && !macho_deps::is_fat(data) {
        return Err(not_macho(&inp.name));
    }
    let slices = macho_deps::slices(data).map_err(|e| format_err(e, "a Mach-O file"))?;
    let pick = macho_deps::pick_slice(&slices, arch).ok_or_else(|| {
        ToolError::invalid(format!("no {} slice; this file has {}", arch.unwrap_or("?"), slices.iter().map(|s| s.arch.as_str()).collect::<Vec<_>>().join(", ")))
            .with_remediation("Pass one of the listed architectures, or omit architecture.")
    })?;
    let bytes = macho_deps::slice_bytes(data, &pick).ok_or_else(|| ToolError::new(ErrorCode::NotSupported, "the slice lies outside the file"))?;
    let deps = macho_deps::parse_thin(bytes).map_err(|e| format_err(e, "a Mach-O slice"))?;
    Ok((slices, pick, bytes, deps))
}

fn loc(inp: &Input) -> Location {
    Location::new("path", inp.path.display().to_string())
}

// ---------------------------------------------------------------------------------------------
// apple_macho_show / apple_slices_list

fn apple_macho_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MachoParams = parse_params(params)?;
    let inp = macho_input(ctx, p.path.as_deref())?;
    let (slices, pick, bytes, deps) = slice_of(&inp, p.architecture.as_deref())?;
    let mut lims = vec![Limitation::new("static_only", "Read from the file only; nothing was loaded or run.")];
    let bin = match craft_anything_formats::parse_binary(bytes) {
        Ok(b) => Some(b),
        Err(e) => {
            lims.push(Limitation::new("symbols_unavailable", format!("imports and exports could not be read: {e}")));
            None
        }
    };
    let (imports, exports, n_imp, n_exp) = match &bin {
        Some(b) => {
            let (i, ci) = page(&b.imports, p.offset, p.limit);
            let (x, cx) = page(&b.exports, p.offset, p.limit);
            let _ = (ci, cx);
            (i, x, b.imports.len(), b.exports.len())
        }
        None => (Vec::new(), Vec::new(), 0, 0),
    };
    let total = n_imp.max(n_exp);
    let limit = p.limit.clamp(1, super::native_common::MAX_LIMIT);
    let coverage = Coverage::page(imports.len().max(exports.len()) as u64, total as u64, p.offset as u64);
    if !deps.warnings.is_empty() {
        lims.push(Limitation::new("load_command_warnings", deps.warnings.join("; ")));
    }
    if deps.encryption.as_ref().is_some_and(|e| e.cryptid != 0) {
        lims.push(Limitation::new("encrypted", "The code segment is encrypted (cryptid ≠ 0); code-level analysis of this slice will see ciphertext."));
    }
    let summary = format!(
        "{} {} ({}{}), {} load commands, {} libraries, {} run paths, {} imports, {} exports{}.",
        deps.header.filetype_name,
        inp.name,
        pick.arch,
        if slices.len() > 1 { format!(", 1 of {} slices", slices.len()) } else { String::new() },
        deps.commands.len(),
        deps.dylibs.len(),
        deps.rpaths.len(),
        n_imp,
        n_exp,
        if deps.code_signature.is_some() { ", code-signed" } else { ", no code signature" }
    );
    let ev = builder(ctx, "apple_macho_show", inp.subject.clone(), json!({"path": inp.path, "architecture": pick.arch, "offset": p.offset, "limit": limit}))
        .result(json!({
            "path": inp.path,
            "slices": slices,
            "selected": pick,
            "header": deps.header,
            "uuid": deps.uuid,
            "build_versions": deps.build_versions,
            "source_version": deps.source_version,
            "encryption": deps.encryption,
            "install_name": deps.id_dylib,
            "libraries": deps.dylibs,
            "rpaths": deps.rpaths,
            "dyld_environment": deps.dyld_environment,
            "code_signature": deps.code_signature.map(|(o, s)| json!({"offset": o, "size": s})),
            "entry_offset": deps.entry_offset,
            "segments": deps.segments,
            "load_commands": deps.commands.iter().take(4096).collect::<Vec<_>>(),
            "imports_total": n_imp,
            "exports_total": n_exp,
            "imports": imports,
            "exports": exports,
            "mitigations": bin.as_ref().map(|b| &b.mitigations),
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(coverage)
        .location(loc(&inp))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn apple_slices_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PathParams = parse_params(params)?;
    let inp = macho_input(ctx, p.path.as_deref())?;
    let data: &[u8] = &inp.bytes;
    if !macho_deps::is_thin(data) && !macho_deps::is_fat(data) {
        return Err(not_macho(&inp.name));
    }
    let slices = macho_deps::slices(data).map_err(|e| format_err(e, "a Mach-O file"))?;
    let rows: Vec<Value> = slices
        .iter()
        .map(|s| {
            let h = macho_deps::slice_bytes(data, s).and_then(|b| macho_deps::header(b).ok());
            json!({
                "architecture": s.arch, "cputype": format!("{:#x}", s.cputype), "cpusubtype": format!("{:#x}", s.cpusubtype),
                "offset": s.offset, "size": s.size, "align": s.align.map(|a| 1u64.checked_shl(a).unwrap_or(0)),
                "file_type": h.as_ref().map(|h| h.filetype_name), "bits": h.as_ref().map(|h| if h.is64 { 64 } else { 32 }),
            })
        })
        .collect();
    let universal = slices.first().is_some_and(|s| s.universal);
    let summary = format!(
        "{} is {} with {}: {}.",
        inp.name,
        if universal { "a universal binary" } else { "a thin Mach-O" },
        if slices.len() == 1 { "1 slice".to_string() } else { format!("{} slices", slices.len()) },
        slices.iter().map(|s| s.arch.as_str()).collect::<Vec<_>>().join(", ")
    );
    let ev = builder(ctx, "apple_slices_list", inp.subject.clone(), json!({"path": inp.path}))
        .result(json!({"path": inp.path, "universal": universal, "slices": rows}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .coverage(Coverage::complete(slices.len() as u64))
        .location(loc(&inp))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// apple_signature_show

fn hash_with(t: &str, data: &[u8]) -> Option<Vec<u8>> {
    match t {
        "sha1" => Some(codesign::sha1(data).to_vec()),
        "sha256" | "sha256-truncated" => Some(sha2::Sha256::digest(data).to_vec()),
        "sha384" => Some(sha2::Sha384::digest(data).to_vec()),
        _ => None,
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// Re-hash code pages and special slots and compare with the code directory.
fn check_hashes(slice: &[u8], sig_bytes: &[u8], sig: &codesign::Signature, cd: &codesign::CodeDirectory, bundle: Option<&Path>) -> Value {
    let hs = usize::from(cd.hash_size);
    if hs == 0 || hs > 64 || cd.page_size == 0 {
        return json!({"checked": false, "reason": "unsupported hash size or page size"});
    }
    let base = cd.offset.saturating_add(cd.hash_offset as usize);
    let page = usize::try_from(cd.page_size).unwrap_or(4096);
    let limit = usize::try_from(cd.code_limit).unwrap_or(usize::MAX).min(slice.len());
    let mut matched = 0u64;
    let mut mismatched = Vec::new();
    let mut missing = 0u64;
    let pages = (cd.code_slots as usize).min(4_000_000);
    for i in 0..pages {
        let start = i.saturating_mul(page);
        if start >= limit {
            missing += 1;
            continue;
        }
        let end = start.saturating_add(page).min(limit);
        let (Some(data), Some(stored)) = (slice.get(start..end), sig_bytes.get(base.saturating_add(i * hs)..base.saturating_add(i * hs + hs))) else {
            missing += 1;
            continue;
        };
        match hash_with(&cd.hash_type, data) {
            Some(h) if h.get(..hs) == Some(stored) => matched += 1,
            Some(_) => {
                if mismatched.len() < 64 {
                    mismatched.push(i);
                }
            }
            None => return json!({"checked": false, "reason": format!("hash type {} not supported", cd.hash_type)}),
        }
    }
    // Special slots: -1 Info.plist, -2 requirements, -5 entitlements, -7 DER entitlements.
    let blob_for = |slot: u32| -> Option<&[u8]> {
        let b = sig.blobs.iter().find(|b| b.slot == slot)?;
        sig_bytes.get(b.offset as usize..(b.offset as usize).checked_add(b.length? as usize)?)
    };
    let mut special = Vec::new();
    for (slot, what) in [(1i64, "info-plist"), (2, "requirements"), (5, "entitlements"), (7, "der-entitlements"), (3, "resources")] {
        if slot > i64::from(cd.special_slots) {
            continue;
        }
        let stored = sig_bytes.get(base.saturating_sub(slot as usize * hs)..base.saturating_sub(slot as usize * hs).saturating_add(hs));
        let Some(stored) = stored else { continue };
        let zero = stored.iter().all(|&x| x == 0);
        let actual: Option<Vec<u8>> = match slot {
            2 | 5 | 7 => blob_for(slot as u32).map(<[u8]>::to_vec),
            1 => bundle.and_then(bundle_info_plist).and_then(|p| std::fs::read(p).ok()),
            3 => bundle
                .map(|b| b.join("Contents/_CodeSignature/CodeResources"))
                .filter(|p| p.is_file())
                .or_else(|| bundle.map(|b| b.join("_CodeSignature/CodeResources")).filter(|p| p.is_file()))
                .and_then(|p| std::fs::read(p).ok()),
            _ => None,
        };
        let status = match (&actual, zero) {
            (None, true) => "absent",
            (None, false) => "not-checked",
            (Some(a), _) => match hash_with(&cd.hash_type, a) {
                Some(h) if h.get(..hs) == Some(stored) => "matches",
                Some(_) => "mismatch",
                None => "not-checked",
            },
        };
        special.push(json!({"slot": -slot, "what": what, "status": status, "stored": hex(stored)}));
    }
    json!({"checked": true, "pages": pages, "pages_matched": matched, "pages_mismatched": mismatched, "pages_unchecked": missing, "special_slots": special})
}

fn apple_signature_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MachoParams = parse_params(params)?;
    let bundle = input_path(ctx, p.path.as_deref()).ok().filter(|b| b.is_dir());
    let inp = macho_input(ctx, p.path.as_deref())?;
    let (_, pick, bytes, deps) = slice_of(&inp, p.architecture.as_deref())?;
    let base = builder(ctx, "apple_signature_show", inp.subject.clone(), json!({"path": inp.path, "architecture": pick.arch}))
        .authority(Authority::OriginalFiles)
        .location(loc(&inp))
        .limitation(Limitation::new(
            "authenticity_scope",
            "Authenticity is verified cryptographically (the CMS signature over the signed attributes, that the signed messageDigest covers the CodeDirectory, and the certificate chain's internal links); certificate revocation (OCSP/CRL), signing-time validity against a trusted timestamp, and full Apple notarization/policy evaluation are NOT checked.",
        ));
    let Some((off, size)) = deps.code_signature else {
        let ev = base
            .result(json!({"path": inp.path, "architecture": pick.arch, "signed": false}))
            .summary(format!("{} ({}) has no LC_CODE_SIGNATURE: it is unsigned.", inp.name, pick.arch))
            .confidence(Confidence::Observed)
            .coverage(Coverage::complete(1))
            .build()?;
        return Ok(ToolOutput::evidence(ev));
    };
    let sig_bytes = bytes.get(off as usize..(off as usize).saturating_add(size as usize).min(bytes.len())).ok_or_else(|| {
        ToolError::new(ErrorCode::NotSupported, "the code signature lies outside the file").with_remediation("The file may be truncated; check it is complete.")
    })?;
    let sig = codesign::parse(sig_bytes).map_err(|e| format_err(e, "a code signature"))?;
    let checks: Vec<Value> = sig
        .code_directories
        .iter()
        .map(|cd| json!({"slot": cd.slot, "hash_type": cd.hash_type, "result": check_hashes(bytes, sig_bytes, &sig, cd, bundle.as_deref())}))
        .collect();
    let primary = sig.code_directories.iter().find(|c| c.slot == 0).or_else(|| sig.code_directories.first());
    let mismatches: u64 = checks.iter().map(|c| c["result"]["pages_mismatched"].as_array().map_or(0, |a| a.len() as u64)).sum();
    let special_bad =
        checks.iter().flat_map(|c| c["result"]["special_slots"].as_array().cloned().unwrap_or_default()).filter(|s| s["status"] == "mismatch").count();
    let ents = sig.entitlements.as_ref().and_then(Value::as_object).map(|o| o.len()).unwrap_or(0);
    // Authenticity: verify the CMS signature over the CodeDirectory (vs integrity, the page hashes above).
    let cms_verification = if sig.ad_hoc {
        None
    } else {
        let cms_bytes = sig.blobs.iter().find(|b| b.slot == 0x1_0000).and_then(|b| {
            let o = b.offset as usize;
            let len = b.length? as usize;
            sig_bytes.get(o.checked_add(8)?..o.checked_add(len)?)
        });
        let cd_bytes = primary.and_then(|cd| sig_bytes.get(cd.offset..cd.offset.checked_add(cd.length as usize)?));
        match (cms_bytes, cd_bytes) {
            (Some(cms), Some(cd)) => verify::verify_macho_cms(cms, cd),
            _ => None,
        }
    };
    let cms_note = match &cms_verification {
        Some(v) if v.authenticated && v.chain.trusted_root.is_some() => {
            format!("; CMS signature VALID, binds the code directory, chain to {}", v.chain.trusted_root.unwrap_or(""))
        }
        Some(v) if v.authenticated => "; CMS signature VALID and binds the code directory (chain not verified to a trusted root)".to_string(),
        Some(v) if v.signature_valid.is_valid() && !v.binds_code_directory => "; CMS signature valid but does NOT bind this code directory".to_string(),
        Some(_) => "; CMS signature did NOT verify".to_string(),
        None if !sig.ad_hoc => "; CMS signature present but not checked".to_string(),
        None => String::new(),
    };
    let summary = format!(
        "{} ({}) is {}signed{}{}; {} code director{}, {} requirement(s), {} entitlement(s){}{}.",
        inp.name,
        pick.arch,
        if sig.ad_hoc { "ad-hoc " } else { "" },
        primary.and_then(|c| c.identifier.as_ref()).map(|i| format!(" as {i}")).unwrap_or_default(),
        primary.and_then(|c| c.team_id.as_ref()).map(|t| format!(" (team {t})")).unwrap_or_default(),
        sig.code_directories.len(),
        if sig.code_directories.len() == 1 { "y" } else { "ies" },
        sig.requirements.len(),
        ents,
        if mismatches > 0 || special_bad > 0 { format!("; {mismatches} page hash(es) and {special_bad} special slot(s) do NOT match") } else { String::new() },
        cms_note,
    );
    let mut lims = Vec::new();
    if !sig.warnings.is_empty() {
        lims.push(Limitation::new("signature_warnings", sig.warnings.join("; ")));
    }
    if sig.der_entitlements_bytes.is_some() {
        lims.push(Limitation::new("der_entitlements", "DER-encoded entitlements are present; their size is reported, the XML form is decoded."));
    }
    let ev = base
        .result(json!({
            "path": inp.path, "architecture": pick.arch, "signed": true, "ad_hoc": sig.ad_hoc,
            "signature_offset": off, "signature_size": size,
            "blobs": sig.blobs, "code_directories": sig.code_directories, "hash_checks": checks,
            "requirements": sig.requirements, "entitlements": sig.entitlements,
            "der_entitlements_bytes": sig.der_entitlements_bytes, "cms_signature_bytes": sig.cms_signature_bytes,
            "cms_verification": cms_verification,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitations(lims)
        .coverage(Coverage::complete(sig.blobs.len() as u64))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// apple_plist_show

fn plist_subject(bytes: &[u8], name: &str) -> Subject {
    Subject { kind: "plist".into(), sha256: Some(sha256_hex(bytes)), name: Some(name.to_string()) }
}

fn apple_plist_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PathParams = parse_params(params)?;
    let path = input_path(ctx, p.path.as_deref())?;
    let (bytes, source, file): (Vec<u8>, &str, PathBuf) = if path.is_dir() {
        let f = bundle_info_plist(&path).ok_or_else(|| {
            ToolError::invalid(format!("{} has no Info.plist", path.display())).with_remediation("Pass the plist file itself, or an .app/.framework bundle.")
        })?;
        let b = static_input::load_path(&f.to_string_lossy(), 64 << 20)?;
        (b.bytes.to_vec(), "bundle-info-plist", f)
    } else {
        let inp = if p.path.is_some() { static_input::load_path(&path.to_string_lossy(), MAX_FILE)? } else { static_input::load(ctx, None, MAX_FILE)? };
        let data: &[u8] = &inp.bytes;
        if macho_deps::is_thin(data) || macho_deps::is_fat(data) {
            let slices = macho_deps::slices(data).map_err(|e| format_err(e, "a Mach-O file"))?;
            let found = slices.iter().find_map(|s| {
                let b = macho_deps::slice_bytes(data, s)?;
                let d = macho_deps::parse_thin(b).ok()?;
                d.section_bytes(b, "__TEXT", "__info_plist").map(<[u8]>::to_vec)
            });
            let b = found.ok_or_else(|| {
                ToolError::new(ErrorCode::NotSupported, format!("{} has no embedded __TEXT,__info_plist section", inp.name))
                    .with_remediation("Most app executables keep Info.plist beside them in the bundle; pass the bundle folder instead.")
            })?;
            (b, "embedded-info-plist", inp.path.clone())
        } else {
            (inp.bytes.to_vec(), "file", inp.path.clone())
        }
    };
    let v = plist::parse(&bytes).map_err(|e| format_err(e, "a property list"))?;
    let format = if bytes.starts_with(b"bplist") { "binary" } else { "xml" };
    let is_ka = keyed_archive::is_keyed_archive(&v);
    let keys: Vec<String> = match &v {
        plist::Value::Dict(d) => d.iter().map(|(k, _)| k.clone()).collect(),
        _ => Vec::new(),
    };
    let name = file.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let summary = format!(
        "{name} ({format} plist{}) with {} top-level key(s){}.",
        if source == "file" { String::new() } else { format!(", {source}") },
        keys.len(),
        v.get("CFBundleIdentifier").and_then(plist::Value::as_str).map(|i| format!("; bundle id {i}")).unwrap_or_default()
    );
    let mut b = builder(ctx, "apple_plist_show", plist_subject(&bytes, &name), json!({"path": file}))
        .result(json!({"path": file, "source": source, "format": format, "keyed_archive": is_ka, "top_level_keys": keys, "plist": v.to_json()}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", file.display().to_string()));
    if is_ka {
        b = b.limitation(Limitation::new("keyed_archive", "This is an NSKeyedArchiver archive; apple_archive_decode resolves its object references."));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// apple_swift_symbols_demangle

fn apple_swift_symbols_demangle(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DemangleParams = parse_params(params)?;
    if p.symbols.is_empty() || p.symbols.len() > 10_000 {
        return Err(ToolError::invalid("symbols must hold 1–10000 names"));
    }
    if let Some((i, _)) = p.symbols.iter().enumerate().find(|(_, s)| s.contains('\0') || s.contains('\n') || s.contains('\r')) {
        return Err(ToolError::invalid(format!("symbol {i} contains a NUL or line break")).with_remediation("Pass one single-line name per entry."));
    }
    let rows: Vec<swift_demangle::Demangled> = p.symbols.iter().map(|s| swift_demangle::demangle(s)).collect();
    let count = |st: swift_demangle::Status| rows.iter().filter(|r| r.status == st).count();
    let (d, u, i) = (count(swift_demangle::Status::Demangled), count(swift_demangle::Status::Unchanged), count(swift_demangle::Status::Invalid));
    let joined = p.symbols.join("\n");
    let subject = Subject { kind: "symbols".into(), sha256: Some(sha256_hex(joined.as_bytes())), name: Some(format!("{} symbol(s)", p.symbols.len())) };
    let mut b = builder(ctx, "apple_swift_symbols_demangle", subject, json!({"symbols": p.symbols}))
        .result(json!({"results": rows, "demangled": d, "unchanged": u, "invalid": i}))
        .summary(format!("{d} demangled, {u} unchanged (not Swift), {i} invalid."))
        .confidence(Confidence::Derived)
        .authority(Authority::Reasoning)
        .coverage(Coverage::complete(rows.len() as u64));
    if i > 0 {
        b = b.limitation(Limitation::new(
            "partial_grammar",
            "The built-in demangler covers common manglings; specialisations, opaque types, some thunks and concurrency types are reported invalid rather than guessed.",
        ));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// apple_nib_decode

fn is_nib_path(rel: &str) -> bool {
    let lower = rel.to_ascii_lowercase();
    if lower.ends_with(".nib") {
        return true;
    }
    let mut parts = lower.rsplit('/');
    let file = parts.next().unwrap_or("");
    let parent = parts.next().unwrap_or("");
    parent.ends_with(".nib") && (file == "runtime.nib" || file.starts_with("objects") || file.starts_with("keyedobjects")) && !file.ends_with(".plist")
}

fn apple_nib_decode(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: IbParams = parse_params(params)?;
    if !(1..=64).contains(&p.max_documents) || !(1..=20_000).contains(&p.max_objects) || !(1..=40_000).contains(&p.max_connections) {
        return Err(ToolError::invalid("max_documents must be 1–64, max_objects 1–20000, max_connections 1–40000"));
    }
    let root = input_path(ctx, p.path.as_deref())?;
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    let mut storyboards = Vec::new();
    let mut truncated = false;
    if root.is_dir() {
        let skip = |_: &str| false;
        let walked = walk_dir(&root, &WalkOptions { max_files: 50_000, max_depth: 24, skip_dir: &skip, gitignore: false, include_hidden: false }, &ctx.cancel)?;
        truncated |= walked.truncated;
        for f in &walked.files {
            if is_nib_path(&f.rel) {
                // A .nib folder holding several variants: keep the first one only.
                let parent_nib = f.rel.rsplit_once('/').map(|(d, _)| d.to_ascii_lowercase()).filter(|d| d.ends_with(".nib"));
                if let Some(d) = parent_nib
                    && files.iter().any(|(r, _)| r.to_ascii_lowercase().starts_with(&format!("{d}/")))
                {
                    continue;
                }
                files.push((f.rel.clone(), f.abs.clone()));
            }
            if f.rel.to_ascii_lowercase().ends_with("info.plist")
                && f.abs.parent().and_then(Path::extension).is_some_and(|e| e.eq_ignore_ascii_case("storyboardc"))
                && let Some(v) = read_plist_file(&f.abs)
            {
                storyboards.push(json!({
                    "path": f.rel,
                    "entry_point": v.get("UIStoryboardDesignatedEntryPointIdentifier").map(plist::Value::to_json),
                    "view_controllers": v.get("UIViewControllerIdentifiersToNibNames").map(plist::Value::to_json),
                }));
            }
        }
    } else {
        let name = root.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        files.push((name, root.clone()));
    }
    if files.is_empty() {
        return Err(ToolError::new(ErrorCode::NotSupported, format!("no compiled nib files under {}", root.display()))
            .with_remediation("Pass a .nib file, a .storyboardc folder or an app bundle with compiled interface files."));
    }
    let total_docs = files.len();
    let mut docs = Vec::new();
    let mut objects_left = p.max_objects;
    let mut conns_left = p.max_connections;
    let mut total_objects = 0usize;
    let mut total_conns = 0usize;
    let mut failures = Vec::new();
    let mut hasher = sha2::Sha256::new();
    for (rel, abs) in files.iter().take(p.max_documents) {
        ctx.cancel.check()?;
        let bytes = match static_input::load_path(&abs.to_string_lossy(), 64 << 20) {
            Ok(b) => b.bytes,
            Err(e) => {
                failures.push(json!({"path": rel, "error": e.message}));
                continue;
            }
        };
        hasher.update(&bytes[..]);
        match nib::parse(&bytes) {
            Ok(doc) => {
                let g = nib::graph(&doc, objects_left, conns_left);
                objects_left = objects_left.saturating_sub(g.objects.len());
                conns_left = conns_left.saturating_sub(g.connections.len());
                total_objects += g.objects_total;
                total_conns += g.connections_total;
                docs.push(json!({
                    "path": rel, "encoding": doc.encoding, "coder_version": doc.coder_version,
                    "object_count": g.objects_total, "connection_count": g.connections_total,
                    "class_counts": g.class_counts, "root_objects": g.root_objects,
                    "connections": g.connections, "hierarchy": g.hierarchy, "objects": g.objects, "warnings": doc.warnings,
                }));
            }
            Err(e) => failures.push(json!({"path": rel, "error": e.to_string()})),
        }
    }
    let listed_objects = p.max_objects - objects_left;
    let listed_conns = p.max_connections - conns_left;
    let mut lims = vec![Limitation::new(
        "compiled_form",
        "Compiled documents keep runtime objects only; design-time names, constraints' intent and comments are not recoverable.",
    )];
    let capped = total_docs > p.max_documents || listed_objects < total_objects || listed_conns < total_conns || truncated;
    if capped {
        lims.push(Limitation::new(
            "truncated",
            "A document, object or connection limit (or the folder walk limit) cut the listing short; raise the max_* parameters.",
        ));
    }
    if !failures.is_empty() {
        lims.push(Limitation::new("unreadable_documents", format!("{} document(s) could not be decoded", failures.len())));
    }
    let digest = hex(&hasher.finalize());
    let name = root.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let summary = format!(
        "{} interface document(s) decoded from {name}: {total_objects} objects, {total_conns} connections{}.",
        docs.len(),
        if failures.is_empty() { String::new() } else { format!(", {} unreadable", failures.len()) }
    );
    let ev = builder(
        ctx,
        "apple_nib_decode",
        Subject { kind: "interface-builder".into(), sha256: Some(digest), name: Some(name) },
        json!({"path": root, "max_documents": p.max_documents, "max_objects": p.max_objects, "max_connections": p.max_connections}),
    )
    .result(json!({"path": root, "documents_total": total_docs, "documents": docs, "storyboards": storyboards, "failures": failures}))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(if capped {
        Coverage { status: CoverageStatus::Partial, examined: Some(docs.len() as u64), total: Some(total_docs as u64), next_offset: None }
    } else {
        Coverage::complete(docs.len() as u64)
    })
    .location(Location::new("path", root.display().to_string()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// apple_archive_decode

fn apple_archive_decode(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: KeyedArchiveParams = parse_params(params)?;
    if !(1..=20_000).contains(&p.limit) {
        return Err(ToolError::invalid("limit must be 1–20000"));
    }
    let inp = static_input::load(ctx, p.path.as_deref(), 256 << 20)?;
    let v = plist::parse(&inp.bytes).map_err(|e| format_err(e, "a property list"))?;
    let a = keyed_archive::from_plist(&v).map_err(|e| format_err(e, "a keyed archive"))?;
    let (root_name, root) = a.root(p.root.as_deref()).ok_or_else(|| {
        ToolError::invalid(format!(
            "no $top entry {:?}; entries are {}",
            p.root.as_deref().unwrap_or("root"),
            a.top.iter().map(|(k, _)| k.as_str()).collect::<Vec<_>>().join(", ")
        ))
    })?;
    let tree = a.project(root);
    let rows = a.rows();
    let total = rows.len();
    let page_rows: Vec<&keyed_archive::ObjectRow> = rows.iter().skip(p.offset).take(p.limit).collect();
    let mut classes: BTreeMap<String, usize> = BTreeMap::new();
    for r in &rows {
        if let Some(c) = &r.class {
            *classes.entry(c.clone()).or_insert(0) += 1;
        }
    }
    let summary = format!(
        "{} archive by {} with {} objects; root \"{root_name}\" is {}.",
        inp.name,
        if a.archiver.is_empty() { "an unnamed archiver" } else { a.archiver.as_str() },
        total,
        a.class_of(root).unwrap_or_else(|| "a plain value".into())
    );
    let mut b = builder(ctx, "apple_archive_decode", inp.subject.clone(), json!({"path": inp.path, "root": root_name, "offset": p.offset, "limit": p.limit}))
        .result(json!({
            "path": inp.path, "archiver": a.archiver, "version": a.version.map(plist::int_json),
            "top": a.top.iter().map(|(k, v)| json!({"name": k, "object": v})).collect::<Vec<_>>(),
            "root": root_name, "root_object": root, "tree": tree, "class_counts": classes,
            "objects_total": total, "objects": page_rows,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .coverage(Coverage::page(page_rows.len() as u64, total as u64, p.offset as u64))
        .location(loc(&inp));
    if a.archiver != "NSKeyedArchiver" {
        b = b.limitation(Limitation::new("archiver", format!("archiver is {:?}, not NSKeyedArchiver; the projection may not fit", a.archiver)));
    }
    b = b.limitation(Limitation::new("expanded_once", "Each object is expanded once in the tree; repeats and cycles appear as {\"$ref\": index}."));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// apple_assets_list

fn find_car(dir: &Path) -> Option<PathBuf> {
    [dir.join("Contents/Resources/Assets.car"), dir.join("Assets.car"), dir.join("Resources/Assets.car")].into_iter().find(|p| p.is_file())
}

fn apple_assets_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AssetCatalogParams = parse_params(params)?;
    if !(1..=10_000).contains(&p.limit) {
        return Err(ToolError::invalid("limit must be 1–10000"));
    }
    let path = input_path(ctx, p.path.as_deref())?;
    let inp = if path.is_dir() {
        let f = find_car(&path)
            .ok_or_else(|| ToolError::invalid(format!("no Assets.car in {}", path.display())).with_remediation("Pass the Assets.car file itself."))?;
        static_input::load_path(&f.to_string_lossy(), 512 << 20)?
    } else if p.path.is_some() {
        static_input::load_path(&path.to_string_lossy(), 512 << 20)?
    } else {
        static_input::load(ctx, None, 512 << 20)?
    };
    if !car::is_bom(&inp.bytes) {
        return Err(ToolError::new(ErrorCode::NotSupported, format!("{} is not a BOM store (asset catalogs start with BOMStore)", inp.name)));
    }
    let c = car::parse(&inp.bytes).map_err(|e| format_err(e, "an asset catalog"))?;
    let total = c.renditions.len();
    let page_r: Vec<&car::Rendition> = c.renditions.iter().skip(p.offset).take(p.limit).collect();
    let mut by_format: BTreeMap<String, usize> = BTreeMap::new();
    for r in &c.renditions {
        *by_format.entry(r.pixel_format.clone().unwrap_or_else(|| "unknown".into())).or_insert(0) += 1;
    }
    let mut lims = vec![Limitation::new("pixels_not_decoded", "Rendition headers are read; image, colour and data payloads are not decoded or exported.")];
    lims.push(Limitation::new("best_effort_names", "Attribute and layout names follow the observed format and may not match every catalog version."));
    if !c.warnings.is_empty() {
        lims.push(Limitation::new("catalog_warnings", c.warnings.iter().take(20).cloned().collect::<Vec<_>>().join("; ")));
    }
    let summary = format!(
        "{}: {} facet(s), {} rendition(s){}.",
        inp.name,
        c.facets.len(),
        total,
        c.header.as_ref().map(|h| format!(", schema {} storage {}", h.schema_version, h.storage_version)).unwrap_or_default()
    );
    let ev = builder(ctx, "apple_assets_list", inp.subject.clone(), json!({"path": inp.path, "offset": p.offset, "limit": p.limit}))
        .result(json!({
            "path": inp.path, "bom": c.bom, "header": c.header, "extended_metadata": c.extended_metadata,
            "key_format": c.key_format, "facets": c.facets, "appearances": c.appearances,
            "renditions_total": total, "renditions_by_pixel_format": by_format, "renditions": page_r,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::page(page_r.len() as u64, total as u64, p.offset as u64))
        .location(loc(&inp))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// apple_dylibs_resolve

/// Lexically normalise `..` and `.` (no file-system access).
fn normalize(p: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in p.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

fn is_system(name: &str) -> bool {
    name.starts_with("/usr/lib/") || name.starts_with("/System/") || name.starts_with("/Library/Apple/")
}

/// An image waiting to be loaded: path, inherited run paths (text, defining folder), wanted slice.
type Pending = (PathBuf, Vec<(String, PathBuf)>, Option<String>);

struct Img {
    path: PathBuf,
    deps: macho_deps::MachoDeps,
    arch: String,
}

#[derive(Default)]
struct Trace {
    images: Vec<Value>,
    loaded: BTreeSet<PathBuf>,
    findings: Vec<Value>,
    counts: BTreeMap<&'static str, usize>,
}

struct Resolver<'a> {
    bundle: PathBuf,
    bundle_canon: PathBuf,
    roots: Vec<PathBuf>,
    arch: Option<&'a str>,
    max_images: usize,
    bytes_read: u64,
}

enum Probe {
    Found(PathBuf),
    Absent,
    Escapes(PathBuf),
}

impl Resolver<'_> {
    fn rel(&self, p: &Path) -> String {
        rel_to(&self.bundle, p)
    }

    fn inside(&self, canon: &Path) -> bool {
        canon.starts_with(&self.bundle_canon) || self.roots.iter().any(|r| std::fs::canonicalize(r).is_ok_and(|rc| canon.starts_with(rc)))
    }

    fn probe(&self, cand: &Path) -> Probe {
        match std::fs::canonicalize(cand) {
            Ok(c) if !c.is_file() => Probe::Absent,
            Ok(c) if self.inside(&c) => Probe::Found(normalize(cand)),
            Ok(c) => Probe::Escapes(c),
            Err(_) => Probe::Absent,
        }
    }

    fn load(&mut self, path: &Path, want: Option<&str>) -> Result<Img, String> {
        let meta = std::fs::metadata(path).map_err(|e| e.to_string())?;
        if meta.len() > 1 << 30 || self.bytes_read.saturating_add(meta.len()) > 8 << 30 {
            return Err("size budget reached".into());
        }
        self.bytes_read += meta.len();
        let data = std::fs::read(path).map_err(|e| e.to_string())?;
        if !macho_deps::is_thin(&data) && !macho_deps::is_fat(&data) {
            return Err("not a Mach-O file".into());
        }
        let slices = macho_deps::slices(&data).map_err(|e| e.to_string())?;
        let pick = macho_deps::pick_slice(&slices, want.or(self.arch)).ok_or_else(|| {
            format!("no {} slice (has {})", want.or(self.arch).unwrap_or("?"), slices.iter().map(|s| s.arch.as_str()).collect::<Vec<_>>().join(", "))
        })?;
        let bytes = macho_deps::slice_bytes(&data, &pick).ok_or("slice outside the file")?;
        let deps = macho_deps::parse_thin(bytes).map_err(|e| e.to_string())?;
        Ok(Img { path: path.to_path_buf(), deps, arch: pick.arch })
    }

    /// Expand one load path (or run path) to candidate paths.
    fn expand(&self, name: &str, exe_dir: &Path, loader_dir: &Path) -> Option<PathBuf> {
        if let Some(r) = name.strip_prefix("@executable_path") {
            Some(normalize(&exe_dir.join(r.trim_start_matches('/'))))
        } else if let Some(r) = name.strip_prefix("@loader_path") {
            Some(normalize(&loader_dir.join(r.trim_start_matches('/'))))
        } else if name.starts_with('/') {
            Some(PathBuf::from(name))
        } else {
            None
        }
    }

    fn absolute_candidates(&self, abs: &Path) -> Vec<PathBuf> {
        let mut v = Vec::new();
        if abs.starts_with(&self.bundle) {
            v.push(abs.to_path_buf());
        }
        let stripped = abs.strip_prefix("/").unwrap_or(abs);
        for r in &self.roots {
            v.push(normalize(&r.join(stripped)));
        }
        v
    }

    /// Trace one entry program (an executable or a plug-in bundle hosted by `exe`).
    fn trace(&mut self, entry: &Path, exe: &Path, t: &mut Trace, cancel: &crate::tool::CancelToken) -> Result<(), ToolError> {
        let exe_dir = exe.parent().map(Path::to_path_buf).unwrap_or_default();
        // (image path, run-path chain [(rpath text, defining image dir)])
        let mut queue: VecDeque<Pending> = VecDeque::new();
        queue.push_back((entry.to_path_buf(), Vec::new(), None));
        while let Some((path, chain, want_arch)) = queue.pop_front() {
            cancel.check()?;
            if !t.loaded.insert(path.clone()) {
                continue;
            }
            if t.loaded.len() > self.max_images {
                t.findings.push(json!({"finding": "image-limit-reached", "detail": format!("stopped after {} images", self.max_images)}));
                return Ok(());
            }
            let img = match self.load(&path, want_arch.as_deref()) {
                Ok(i) => i,
                Err(e) => {
                    t.images.push(json!({"path": self.rel(&path), "error": e}));
                    continue;
                }
            };
            let loader_dir = img.path.parent().map(Path::to_path_buf).unwrap_or_default();
            // This image's run paths come first, then those of the images that loaded it.
            let mut rpaths: Vec<(String, PathBuf)> = img.deps.rpaths.iter().map(|r| (r.clone(), loader_dir.clone())).collect();
            rpaths.extend(chain.iter().cloned());
            let mut deps_out = Vec::new();
            for d in &img.deps.dylibs {
                let weak = d.kind == "weak";
                let mut candidates = Vec::new();
                let mut outcome = "unresolved";
                let mut resolved: Option<PathBuf> = None;
                let mut via = None;
                let mut absent_before = Vec::new();
                if is_system(&d.name) {
                    outcome = "system";
                } else if let Some(rest) = d.name.strip_prefix("@rpath/") {
                    if rpaths.is_empty() {
                        t.findings.push(json!({"finding": "rpath-without-run-paths", "image": self.rel(&img.path), "dependency": d.name}));
                    }
                    for (rp, def_dir) in &rpaths {
                        let Some(base) = self.expand(rp, &exe_dir, def_dir) else {
                            candidates.push(json!({"rpath": rp, "path": null, "status": "relative-run-path"}));
                            continue;
                        };
                        let cands = if base.is_absolute() && !rp.starts_with('@') {
                            self.absolute_candidates(&base.join(rest))
                        } else {
                            vec![normalize(&base.join(rest))]
                        };
                        for c in cands {
                            match self.probe(&c) {
                                Probe::Found(f) => {
                                    candidates.push(json!({"rpath": rp, "path": self.rel(&c), "status": "present"}));
                                    if resolved.is_none() {
                                        resolved = Some(f);
                                        via = Some(rp.clone());
                                    }
                                }
                                Probe::Absent => {
                                    candidates.push(json!({"rpath": rp, "path": self.rel(&c), "status": "absent"}));
                                    if resolved.is_none() {
                                        absent_before.push(self.rel(&c));
                                    }
                                }
                                Probe::Escapes(to) => {
                                    candidates.push(json!({"rpath": rp, "path": self.rel(&c), "status": "escapes-bundle"}));
                                    t.findings.push(json!({"finding": "symlink-escapes-bundle", "image": self.rel(&img.path), "dependency": d.name, "target": to.display().to_string()}));
                                }
                            }
                        }
                        if resolved.is_some() {
                            break;
                        }
                    }
                    if resolved.is_some() {
                        outcome = "resolved";
                        if !absent_before.is_empty() {
                            t.findings
                                .push(json!({"finding": "skipped-rpath-entry", "image": self.rel(&img.path), "dependency": d.name, "absent": absent_before}));
                        }
                    }
                } else if let Some(base) = self.expand(&d.name, &exe_dir, &loader_dir) {
                    let cands = if d.name.starts_with('@') { vec![base] } else { self.absolute_candidates(&base) };
                    if cands.is_empty() {
                        outcome = "undetermined";
                    }
                    for c in cands {
                        match self.probe(&c) {
                            Probe::Found(f) => {
                                candidates.push(json!({"path": self.rel(&c), "status": "present"}));
                                resolved = Some(f);
                                outcome = "resolved";
                                break;
                            }
                            Probe::Absent => candidates.push(json!({"path": self.rel(&c), "status": "absent"})),
                            Probe::Escapes(to) => {
                                candidates.push(json!({"path": self.rel(&c), "status": "escapes-bundle"}));
                                t.findings.push(json!({"finding": "symlink-escapes-bundle", "image": self.rel(&img.path), "dependency": d.name, "target": to.display().to_string()}));
                            }
                        }
                    }
                } else {
                    outcome = "undetermined";
                    t.findings.push(json!({"finding": "relative-install-name", "image": self.rel(&img.path), "dependency": d.name}));
                }
                if outcome == "unresolved" && weak {
                    outcome = "unresolved-weak";
                }
                *t.counts.entry(outcome).or_insert(0) += 1;
                if let Some(r) = &resolved {
                    let mut next_chain = rpaths.clone();
                    next_chain.truncate(256);
                    queue.push_back((r.clone(), next_chain, Some(img.arch.clone())));
                }
                deps_out.push(json!({
                    "name": d.name, "kind": d.kind, "outcome": outcome,
                    "resolved_path": resolved.as_ref().map(|r| self.rel(r)), "via_rpath": via,
                    "candidates": candidates,
                }));
            }
            t.images.push(json!({
                "path": self.rel(&img.path), "architecture": img.arch, "file_type": img.deps.header.filetype_name,
                "install_name": img.deps.id_dylib.as_ref().map(|d| d.name.clone()), "rpaths": img.deps.rpaths,
                "executable_path": self.rel(exe), "dependencies": deps_out,
            }));
        }
        Ok(())
    }
}

fn apple_dylibs_resolve(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DylibParams = parse_params(params)?;
    if !(1..=20_000).contains(&p.max_images) {
        return Err(ToolError::invalid("max_images must be 1–20000"));
    }
    let start = input_path(ctx, p.path.as_deref())?;
    if p.path.is_none() && ctx.session.active().is_ok_and(|t| !matches!(t.target.kind, TargetKind::Directory | TargetKind::MachO | TargetKind::MachOFat)) {
        return Err(ToolError::invalid("the active target is not an app bundle or Mach-O").with_remediation("Pass path to an .app bundle."));
    }
    let start = normalize(&start);
    // The bundle: the folder itself, or the nearest enclosing .app/.framework/.appex.
    let bundle = if start.is_dir() {
        start.clone()
    } else {
        start
            .ancestors()
            .skip(1)
            .find(|a| a.extension().is_some_and(|e| e == "app" || e == "framework" || e == "appex" || e == "xpc"))
            .map(Path::to_path_buf)
            .or_else(|| start.parent().map(Path::to_path_buf))
            .unwrap_or_default()
    };
    let bundle_canon = std::fs::canonicalize(&bundle).map_err(|e| ToolError::io(bundle.display(), e))?;
    let main_exe = if start.is_dir() {
        bundle_executable(&bundle).ok_or_else(|| {
            ToolError::invalid(format!("{} has no bundle executable", bundle.display()))
                .with_remediation("Pass an .app bundle with an Info.plist, or the Mach-O inside it.")
        })?
    } else {
        start.clone()
    };
    let mut roots = Vec::new();
    for r in &p.roots {
        roots.push(super::artifact_tools::abs_path(r, "roots entry")?);
    }
    let mut res = Resolver { bundle: bundle.clone(), bundle_canon, roots, arch: p.architecture.map(DyldArch::name), max_images: p.max_images, bytes_read: 0 };
    let mut t = Trace::default();
    res.trace(&main_exe, &main_exe, &mut t, &ctx.cancel)?;
    // Other programs in the bundle: executables (their own @executable_path) and plug-in bundles (hosted by the main executable).
    let skip = |_: &str| false;
    let walked = walk_dir(&bundle, &WalkOptions { max_files: 20_000, max_depth: 32, skip_dir: &skip, gitignore: false, include_hidden: false }, &ctx.cancel)?;
    let mut machos = Vec::new();
    for f in &walked.files {
        let mut head = [0u8; 32];
        let ok = std::fs::File::open(&f.abs).and_then(|mut fh| std::io::Read::read(&mut fh, &mut head)).unwrap_or(0) >= 32;
        if !ok || !(macho_deps::is_thin(&head) || macho_deps::is_fat(&head)) {
            continue;
        }
        let ft = if macho_deps::is_thin(&head) {
            macho_deps::header(&head).ok().map(|h| h.filetype)
        } else {
            std::fs::read(&f.abs).ok().and_then(|data| {
                let slices = macho_deps::slices(&data).ok()?;
                let pick = macho_deps::pick_slice(&slices, res.arch)?;
                let bytes = macho_deps::slice_bytes(&data, &pick)?;
                macho_deps::header(bytes).ok().map(|h| h.filetype)
            })
        };
        machos.push((normalize(&f.abs), ft));
    }
    let entries: Vec<(PathBuf, Option<u32>)> = machos.iter().filter(|(p, ft)| !t.loaded.contains(p) && matches!(ft, Some(2) | Some(8))).cloned().collect();
    let mut seen_entries = HashSet::new();
    for (path, ft) in entries {
        if t.loaded.contains(&path) || !seen_entries.insert(path.clone()) {
            continue;
        }
        let exe = if ft == Some(8) { main_exe.clone() } else { path.clone() };
        res.trace(&path, &exe, &mut t, &ctx.cancel)?;
    }
    let unreferenced: Vec<String> = machos.iter().filter(|(p, _)| !t.loaded.contains(p)).map(|(p, _)| res.rel(p)).collect();
    let resolved = t.counts.get("resolved").copied().unwrap_or(0);
    let unresolved = t.counts.get("unresolved").copied().unwrap_or(0);
    let summary = format!(
        "{} image(s) traced from {}: {resolved} resolved, {} system, {unresolved} unresolved, {} weak missing, {} undetermined; {} finding(s), {} Mach-O file(s) never loaded.",
        t.images.len(),
        res.rel(&main_exe),
        t.counts.get("system").copied().unwrap_or(0),
        t.counts.get("unresolved-weak").copied().unwrap_or(0),
        t.counts.get("undetermined").copied().unwrap_or(0),
        t.findings.len(),
        unreferenced.len()
    );
    let mut lims = vec![
        Limitation::new(
            "static_model",
            "A static model of the dynamic linker: environment variables (DYLD_*), the shared cache contents and runtime dlopen calls are not observed.",
        ),
        Limitation::new(
            "system_libraries",
            "Paths under /usr/lib and /System are reported as system: they normally live in the OS shared cache and are not checked on this host.",
        ),
    ];
    if walked.truncated {
        lims.push(Limitation::new("truncated", "The bundle walk hit its file or depth limit; some programs were not considered."));
    }
    let name = bundle.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let ev = builder(
        ctx,
        "apple_dylibs_resolve",
        Subject { kind: "bundle".into(), sha256: Some(sha256_hex(bundle.to_string_lossy().as_bytes())), name: Some(name) },
        json!({"path": start, "roots": p.roots, "architecture": p.architecture.map(DyldArch::name), "max_images": p.max_images}),
    )
    .result(json!({
        "bundle": bundle, "main_executable": res.rel(&main_exe), "images": t.images, "findings": t.findings,
        "outcomes": t.counts, "unreferenced_images": unreferenced,
    }))
    .summary(summary)
    .confidence(Confidence::Derived)
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(Coverage::complete(t.loaded.len() as u64))
    .location(Location::new("path", bundle.display().to_string()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err, engine_with};
    use crate::Engine;
    use craft_anything_testkit::apple as fx;
    use serde_json::json;

    fn tmp(name: &str, bytes: &[u8]) -> String {
        craft_anything_testkit::temp_file(name, bytes).to_string_lossy().into_owned()
    }

    #[test]
    fn macho_and_architectures() {
        let e = engine_with("signed", &fx::macho_signed());
        let r = call(&e, "apple_macho_show", json!({}));
        assert_eq!(r["result"]["selected"]["arch"], "x86_64");
        assert!(r["result"]["libraries"].as_array().unwrap().iter().any(|l| l["name"] == "@rpath/Extras.framework/Extras" && l["kind"] == "weak"));
        assert_eq!(r["result"]["rpaths"][0], "@executable_path/../Frameworks");
        assert_eq!(r["result"]["uuid"], "00112233-4455-6677-8899-AABBCCDDEEFF");
        assert!(r["result"]["imports"].as_array().unwrap().iter().any(|i| i.to_string().contains("puts")), "{}", r["result"]["imports"]);
        let u = tmp("universal", &fx::macho_universal());
        let a = call(&e, "apple_slices_list", json!({"path": u}));
        assert_eq!(a["result"]["universal"], true);
        assert_eq!(a["result"]["slices"].as_array().unwrap().len(), 2);
        let m = call(&e, "apple_macho_show", json!({"path": u, "architecture": "arm64e"}));
        assert_eq!(m["result"]["selected"]["arch"], "arm64");
        let err = call_err(&e, "apple_macho_show", json!({"path": u, "architecture": "i386"}));
        assert!(err.message.contains("x86_64"));
        let junk = tmp("junk.bin", b"not a program at all");
        assert!(call_err(&e, "apple_macho_show", json!({"path": junk})).message.contains("not a Mach-O"));
    }

    #[test]
    fn signature() {
        let e = engine_with("signed", &fx::macho_signed());
        let r = call(&e, "apple_signature_show", json!({}));
        let res = &r["result"];
        assert_eq!(res["signed"], true);
        assert_eq!(res["code_directories"][0]["identifier"], "com.example.notes");
        assert_eq!(res["code_directories"][0]["team_id"], "ABCDE12345");
        assert_eq!(res["entitlements"]["com.apple.security.network.client"], true);
        assert!(res["requirements"][0]["text"].as_str().unwrap().contains("anchor apple generic"));
        // The fixture's page hash is a placeholder: the recomputed hash must not match.
        assert_eq!(res["hash_checks"][0]["result"]["pages_mismatched"].as_array().unwrap().len(), 1);
        let special = res["hash_checks"][0]["result"]["special_slots"].as_array().unwrap();
        assert!(special.iter().any(|s| s["what"] == "entitlements" && s["status"] == "mismatch"));
        assert!(special.iter().any(|s| s["what"] == "requirements" && s["status"] == "mismatch"));
        assert!(special.iter().any(|s| s["what"] == "info-plist" && s["status"] == "absent"));
        assert!(r["summary"].as_str().unwrap().contains("do NOT match"));
        let unsigned = engine_with("plain", &craft_anything_testkit::macho64());
        let u = call(&unsigned, "apple_signature_show", json!({}));
        assert_eq!(u["result"]["signed"], false);
    }

    #[test]
    fn signature_cms_is_verified() {
        // A Mach-O whose CMS genuinely signs its CodeDirectory verifies cryptographically.
        let e = engine_with("cms", &fx::macho_cms_signed());
        let r = call(&e, "apple_signature_show", json!({}));
        let v = &r["result"]["cms_verification"];
        assert_eq!(v["signature_valid"]["status"], "valid", "{v}");
        assert_eq!(v["binds_code_directory"], true);
        assert_eq!(v["authenticated"], true);
        // The signer is self-signed and NOT a bundled Apple root, reported honestly.
        assert!(v["chain"]["trusted_root"].is_null());
        assert!(r["summary"].as_str().unwrap().contains("CMS signature VALID and binds"));
        // Tamper detection is covered at the formats layer (verify::tests::macho_cms_verifies_and_detects_tamper).
    }

    #[test]
    fn plists() {
        let e = Engine::new(crate::testing::session());
        let x = tmp("Info.plist", fx::to_xml(&fx::sample_plist()).as_bytes());
        let r = call(&e, "apple_plist_show", json!({"path": x}));
        assert_eq!(r["result"]["format"], "xml");
        assert_eq!(r["result"]["plist"]["CFBundleIdentifier"], "com.example.notes");
        let b = tmp("Info.bplist", &fx::to_bplist(&fx::sample_plist()));
        assert_eq!(call(&e, "apple_plist_show", json!({"path": b}))["result"]["format"], "binary");
        let m = tmp("exe", &fx::macho_with_info_plist());
        let r = call(&e, "apple_plist_show", json!({"path": m}));
        assert_eq!(r["result"]["source"], "embedded-info-plist");
        let dir = tempfile::tempdir().unwrap();
        let app = fx::write_app_bundle(dir.path());
        let r = call(&e, "apple_plist_show", json!({"path": app}));
        assert_eq!(r["result"]["source"], "bundle-info-plist");
        assert_eq!(r["result"]["plist"]["CFBundleExecutable"], "Notes");
        let ka = tmp("doc.archive", &fx::keyed_archive());
        assert_eq!(call(&e, "apple_plist_show", json!({"path": ka}))["result"]["keyed_archive"], true);
        assert!(call_err(&e, "apple_plist_show", json!({"path": "relative.plist"})).message.contains("absolute"));
    }

    #[test]
    fn demangle() {
        let e = Engine::new(crate::testing::session());
        let r = call(&e, "apple_swift_symbols_demangle", json!({"symbols": ["$s4main6WidgetCMa", "_main", "$s4mai"]}));
        let rows = r["result"]["results"].as_array().unwrap();
        assert_eq!(rows[0]["status"], "demangled");
        assert_eq!(rows[0]["demangled"], "type metadata accessor for main.Widget");
        assert_eq!(rows[1]["status"], "unchanged");
        assert_eq!(rows[2]["status"], "invalid");
        assert!(call_err(&e, "apple_swift_symbols_demangle", json!({"symbols": []})).message.contains("1–10000"));
        assert!(call_err(&e, "apple_swift_symbols_demangle", json!({"symbols": ["a\nb"]})).message.contains("line break"));
    }

    #[test]
    fn interface_builder_and_archives() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let sb = dir.path().join("Main.storyboardc");
        std::fs::create_dir_all(sb.join("UIViewController-abc.nib")).unwrap();
        std::fs::write(sb.join("UIViewController-abc.nib/runtime.nib"), fx::nib_archive()).unwrap();
        std::fs::write(sb.join("UIViewController-abc.nib/objects-13.0+.nib"), fx::nib_archive()).unwrap();
        std::fs::write(sb.join("Window.nib"), fx::keyed_nib()).unwrap();
        std::fs::write(
            sb.join("Info.plist"),
            fx::to_xml(&fx::dict(vec![
                ("UIStoryboardDesignatedEntryPointIdentifier", fx::s("abc")),
                ("UIViewControllerIdentifiersToNibNames", fx::dict(vec![("abc", fx::s("UIViewController-abc"))])),
            ])),
        )
        .unwrap();
        let r = call(&e, "apple_nib_decode", json!({"path": sb}));
        assert_eq!(r["result"]["documents"].as_array().unwrap().len(), 2, "{}", r["result"]);
        assert_eq!(r["result"]["storyboards"][0]["entry_point"], "abc");
        let docs = r["result"]["documents"].as_array().unwrap();
        let ui = docs.iter().find(|d| d["encoding"] == "nib-archive").unwrap();
        assert_eq!(ui["connection_count"], 2);
        let capped = call(&e, "apple_nib_decode", json!({"path": sb, "max_documents": 1, "max_objects": 1}));
        assert_eq!(capped["coverage"]["status"], "partial");
        assert!(call_err(&e, "apple_nib_decode", json!({"path": sb, "max_documents": 65})).message.contains("max_documents"));
        let ka = tmp("doc.archive", &fx::keyed_archive());
        let k = call(&e, "apple_archive_decode", json!({"path": ka, "limit": 3}));
        assert_eq!(k["result"]["tree"]["title"], "Groceries");
        assert_eq!(k["result"]["objects"].as_array().unwrap().len(), 3);
        assert_eq!(k["coverage"]["next_offset"], 3);
        assert!(call_err(&e, "apple_archive_decode", json!({"path": ka, "root": "nope"})).message.contains("root"));
    }

    #[test]
    fn asset_catalog() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let res = dir.path().join("X.app/Contents/Resources");
        std::fs::create_dir_all(&res).unwrap();
        std::fs::write(res.join("Assets.car"), fx::assets_car()).unwrap();
        let r = call(&e, "apple_assets_list", json!({"path": dir.path().join("X.app"), "limit": 1}));
        assert_eq!(r["result"]["renditions_total"], 2);
        assert_eq!(r["result"]["renditions"].as_array().unwrap().len(), 1);
        assert_eq!(r["result"]["facets"].as_array().unwrap().len(), 2);
        assert_eq!(r["coverage"]["next_offset"], 1);
    }

    #[test]
    fn dylib_resolution() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let app = fx::write_app_bundle(dir.path());
        let r = call(&e, "apple_dylibs_resolve", json!({"path": app}));
        let res = &r["result"];
        let images = res["images"].as_array().unwrap();
        let exe = images.iter().find(|i| i["path"] == "Contents/MacOS/Notes").unwrap();
        let dep = |n: &str| exe["dependencies"].as_array().unwrap().iter().find(|d| d["name"] == n).unwrap().clone();
        assert_eq!(dep("/usr/lib/libSystem.B.dylib")["outcome"], "system");
        let foo = dep("@rpath/Foo.framework/Versions/A/Foo");
        assert_eq!(foo["outcome"], "resolved");
        assert_eq!(foo["resolved_path"], "Contents/Frameworks/Foo.framework/Versions/A/Foo");
        assert_eq!(dep("@rpath/Gone.dylib")["outcome"], "unresolved");
        assert_eq!(dep("@rpath/Optional.dylib")["outcome"], "unresolved-weak");
        let findings = res["findings"].as_array().unwrap();
        assert!(findings.iter().any(|f| f["finding"] == "skipped-rpath-entry"));
        #[cfg(unix)]
        {
            assert_eq!(dep("@rpath/Evil.dylib")["outcome"], "unresolved");
            assert!(findings.iter().any(|f| f["finding"] == "symlink-escapes-bundle"));
        }
        // Bar is loaded once even though Foo names it twice; the plug-in resolves through @executable_path.
        assert_eq!(images.iter().filter(|i| i["path"] == "Contents/Frameworks/Bar.dylib").count(), 1);
        let plugin = images.iter().find(|i| i["path"] == "Contents/PlugIns/Helper.bundle/Contents/MacOS/Helper").unwrap();
        assert_eq!(plugin["dependencies"][0]["outcome"], "resolved");
        assert_eq!(res["unreferenced_images"], json!(["Contents/Frameworks/Unused.dylib"]));
        let foo_img = images.iter().find(|i| i["path"] == "Contents/Frameworks/Foo.framework/Versions/A/Foo").unwrap();
        assert_eq!(foo_img["dependencies"][0]["via_rpath"], "@loader_path/../../..");
        // Starting from the executable inside the bundle gives the same main image.
        let r2 = call(&e, "apple_dylibs_resolve", json!({"path": app.join("Contents/MacOS/Notes"), "architecture": "arm64e"}));
        assert_eq!(r2["result"]["main_executable"], "Contents/MacOS/Notes");
        // The bundle tools also accept the bundle folder.
        let m = call(&e, "apple_macho_show", json!({"path": app}));
        assert_eq!(m["result"]["selected"]["arch"], "arm64");
    }

    #[test]
    fn dylib_resolution_discovers_universal_helper() {
        let e = Engine::new(crate::testing::session());
        let dir = tempfile::tempdir().unwrap();
        let app = dir.path().join("UniversalHelper.app");
        let contents = app.join("Contents");
        std::fs::create_dir_all(contents.join("MacOS")).unwrap();
        std::fs::create_dir_all(contents.join("Helpers")).unwrap();
        std::fs::create_dir_all(contents.join("Frameworks")).unwrap();
        std::fs::write(contents.join("Info.plist"), fx::to_xml(&fx::dict(vec![("CFBundleExecutable", fx::s("Main"))]))).unwrap();

        let main = fx::macho_min(fx::CPU_ARM64, 2, &[], &[]);
        let helper = |cpu| fx::macho_min(cpu, 2, &[fx::lc_rpath("@executable_path/../Frameworks"), fx::lc_dylib(0xc, "@rpath/OnlyHelper.dylib")], &[]);
        let universal = craft_anything_testkit::macho_fat(&[helper(fx::CPU_ARM64), helper(fx::CPU_X86_64)]);
        let library = craft_anything_testkit::macho_fat(&[
            fx::macho_min(fx::CPU_ARM64, 6, &[fx::lc_dylib(0xd, "@rpath/OnlyHelper.dylib")], &[]),
            fx::macho_min(fx::CPU_X86_64, 6, &[fx::lc_dylib(0xd, "@rpath/OnlyHelper.dylib")], &[]),
        ]);
        std::fs::write(contents.join("MacOS/Main"), main).unwrap();
        std::fs::write(contents.join("Helpers/Worker"), universal).unwrap();
        std::fs::write(contents.join("Frameworks/OnlyHelper.dylib"), library).unwrap();

        let result = call(&e, "apple_dylibs_resolve", json!({"path": app, "architecture": "arm64"}));
        let images = result["result"]["images"].as_array().unwrap();
        let worker = images.iter().find(|image| image["path"] == "Contents/Helpers/Worker").unwrap();
        assert_eq!(worker["executable_path"], "Contents/Helpers/Worker");
        assert_eq!(worker["dependencies"][0]["outcome"], "resolved");
        assert_eq!(worker["dependencies"][0]["resolved_path"], "Contents/Frameworks/OnlyHelper.dylib");
    }
}
