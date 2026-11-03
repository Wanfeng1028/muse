//! Firmware images with the built-in engine: a signature scan of recognised regions with an
//! entropy map (`firmware_regions_list`), and carving/unpacking those regions into a fresh
//! folder, recursively and within strict limits (`firmware_image_extract`).

use super::artifact_tools::{create_absent_dir, safe_components, write_new_file};
use super::native_common::{page, spec};
use super::static_input::{builder, load};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Confidence, Coverage, CoverageStatus, ErrorCode, Limitation, Location, ToolError, sha256_hex};
use craft_anything_formats::firmware::{self as fw, Region, ScanOptions, Unpack};
use craft_anything_formats::fsread::{self, FsKind, Limits};
use craft_anything_formats::{decompress, tarcpio, zip};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::path::Path;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "firmware_regions_list",
            "Firmware regions",
            "Signature scan of a firmware image or disk dump with the built-in engine: compression streams (gzip, zlib, xz, LZMA, bzip2, Zstandard, LZ4), archives (ZIP, tar, cpio, 7z, RAR, CAB), filesystems (squashfs, cramfs, romfs, JFFS2, UBI/UBIFS, ext2/3/4, FAT, ISO 9660), boot images (legacy boot-loader images, Android boot), device trees/FIT, executables (ELF, PE, Mach-O) and PEM blocks, each checked against its header; plus an entropy map, coverage, gaps and unexplained high-entropy spans. Regions are paged (offset/limit); range limits the scan to part of the file.",
            "Find out what is packed inside a firmware image: compressed parts, filesystems, archives and programs.",
            Toolset::Formats,
            Effects::EVIDENCE,
            Requires::Nothing,
            schema_of::<RegionsParams>,
            firmware_regions_list,
        ),
        spec(
            "firmware_image_extract",
            "Extract firmware",
            "Carve every recognised region of a firmware image into a new folder (output_directory must not exist yet), decompress gzip/zlib/xz/LZMA/bzip2/Zstandard streams, unpack ZIP, tar and cpio members and boot-image payloads, list and extract files from squashfs, cramfs, romfs, ext2/3/4 and (best-effort) JFFS2 filesystems, and repeat on what comes out up to max_depth levels. Bounded by max_output_bytes and max_output_files; never overwrites; members or filesystem paths that would escape the folder and links are refused. Writes manifest.json listing every output with its SHA-256 and how it was unpacked.",
            "Unpack a firmware image into a folder so you can look at the files inside.",
            Toolset::Formats,
            Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM),
            Requires::Nothing,
            schema_of::<ExtractParams>,
            firmware_image_extract,
        ),
    ]
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ByteRange {
    /// First byte of the range.
    pub offset: u64,
    /// Bytes in the range (cut to the end of the file).
    pub length: u64,
}

fn d_max_regions() -> usize {
    2000
}
fn d_block() -> usize {
    4096
}
fn d_limit() -> usize {
    200
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RegionsParams {
    /// Absolute path of the image; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Only scan this part of the file (offsets stay relative to the whole file).
    #[serde(default)]
    pub range: Option<ByteRange>,
    /// Most regions recorded (1..=100000, default 2000).
    #[serde(default = "d_max_regions")]
    pub max_regions: usize,
    /// Entropy block size in bytes (256..=1048576, default 4096). Grows when the map would exceed 4096 blocks.
    #[serde(default = "d_block")]
    pub entropy_block: usize,
    /// First region of the page.
    #[serde(default)]
    pub offset: usize,
    /// Regions per page (1..=5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

fn d_depth() -> u32 {
    3
}
fn d_out_bytes() -> u64 {
    256 << 20
}
fn d_out_files() -> usize {
    10_000
}
fn d_list() -> usize {
    500
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExtractParams {
    /// Absolute path of the image; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Absolute path of a folder that does not exist yet; it is created (its parent must exist).
    pub output_directory: String,
    /// Only extract from this part of the file.
    #[serde(default)]
    pub range: Option<ByteRange>,
    /// Nested unpacking levels (1..=10, default 3).
    #[serde(default = "d_depth")]
    pub max_depth: u32,
    /// Most bytes written in total (up to 512 MiB, default 256 MiB).
    #[serde(default = "d_out_bytes")]
    pub max_output_bytes: u64,
    /// Most files written (1..=100000, default 10000).
    #[serde(default = "d_out_files")]
    pub max_output_files: usize,
    /// Outputs listed in the evidence (the manifest always lists all of them; 1..=5000, default 500).
    #[serde(default = "d_list")]
    pub limit: usize,
}

/// Apply an optional range to the input: (slice, base offset).
fn apply_range(data: &[u8], range: Option<ByteRange>) -> Result<(&[u8], u64), ToolError> {
    let Some(r) = range else { return Ok((data, 0)) };
    let start = usize::try_from(r.offset)
        .ok()
        .filter(|s| *s < data.len())
        .ok_or_else(|| ToolError::invalid(format!("range.offset {:#x} is past the end of the file ({} bytes)", r.offset, data.len())))?;
    let len = usize::try_from(r.length).unwrap_or(usize::MAX).min(data.len() - start);
    if len == 0 {
        return Err(ToolError::invalid("range.length is 0"));
    }
    Ok((data.get(start..start + len).unwrap_or(&[]), r.offset))
}

fn region_json(r: &Region, base: u64) -> Value {
    let off = r.offset.saturating_add(base);
    let mut v = serde_json::to_value(r).unwrap_or(Value::Null);
    if let Value::Object(m) = &mut v {
        m.insert("offset".into(), json!(off));
        m.insert("offset_hex".into(), json!(format!("{off:#x}")));
        m.insert("end_hex".into(), json!(r.end().map(|e| format!("{:#x}", e.saturating_add(base)))));
    }
    v
}

fn scan_limitations() -> Vec<Limitation> {
    vec![
        Limitation::new(
            "signature_scan",
            "Regions are found by known signatures checked against their headers; formats we don't know, encrypted or vendor-specific containers are not recognised, and absence of a region is not proof.",
        ),
        Limitation::new(
            "nested_hidden",
            "Content inside a region of confirmed length (for example the compressed kernel inside a boot image) is not listed here; firmware_image_extract unpacks and scans it.",
        ),
        Limitation::new(
            "entropy_heuristic",
            "Entropy classes (text, code-or-data, compressed-or-encrypted, padding) are statistical hints, not proof of content.",
        ),
    ]
}

fn firmware_regions_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RegionsParams = parse_params(params)?;
    if !(1..=100_000).contains(&p.max_regions) {
        return Err(ToolError::invalid("max_regions must be 1..=100000"));
    }
    if !(256..=1 << 20).contains(&p.entropy_block) {
        return Err(ToolError::invalid("entropy_block must be 256..=1048576"));
    }
    let input = load(ctx, p.path.as_deref(), fw::MAX_INPUT)?;
    let (data, base) = apply_range(&input.bytes, p.range)?;
    ctx.report(None, format!("Scanning {} ({} bytes)", input.name, data.len()));
    let cancel = ctx.cancel.clone();
    let scan = fw::scan(data, &ScanOptions { max_regions: p.max_regions, ..ScanOptions::default() }, &|| cancel.is_cancelled());
    if scan.cancelled {
        return Err(ToolError::cancelled());
    }
    let (entropy, block) = fw::entropy_map(data, p.entropy_block, 4096);
    let lay = fw::layout(data, &scan.regions, &entropy, 500);
    let regions: Vec<Value> = scan.regions.iter().map(|r| region_json(r, base)).collect();
    let (page_items, cov) = page(&regions, p.offset, p.limit);
    let mut by_kind: BTreeMap<&str, usize> = BTreeMap::new();
    let mut by_family: BTreeMap<String, usize> = BTreeMap::new();
    for r in &scan.regions {
        *by_kind.entry(r.kind).or_default() += 1;
        *by_family.entry(serde_json::to_value(r.family).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_default()).or_default() += 1;
    }
    let shift =
        |s: &fw::Span| json!({"offset": s.offset.saturating_add(base), "offset_hex": format!("{:#x}", s.offset.saturating_add(base)), "length": s.length});
    let mean = if entropy.is_empty() { 0.0 } else { entropy.iter().map(|b| f64::from(b.entropy)).sum::<f64>() / entropy.len() as f64 };
    let mut classes: BTreeMap<&str, usize> = BTreeMap::new();
    for b in &entropy {
        *classes.entry(b.class).or_default() += 1;
    }
    let blocks: Vec<Value> = entropy.iter().map(|b| json!({"offset": b.offset.saturating_add(base), "entropy": b.entropy, "class": b.class})).collect();
    let summary = format!(
        "{}: {} region(s) ({}); {:.1}% of {} bytes recognised; {} unexplained high-entropy span(s).",
        input.name,
        scan.regions.len(),
        if by_kind.is_empty() { "none".to_string() } else { by_kind.iter().map(|(k, n)| format!("{n} {k}")).collect::<Vec<_>>().join(", ") },
        lay.recognised_percent,
        data.len(),
        lay.high_entropy_unrecognised.len()
    );
    let mut lims = scan_limitations();
    if scan.truncated {
        lims.push(Limitation::new("truncated", format!("stopped at max_regions={}; scan a smaller range or raise the limit", p.max_regions)));
    }
    for w in &scan.warnings {
        lims.push(Limitation::new("probe_budget", w.clone()));
    }
    if block != p.entropy_block {
        lims.push(Limitation::new("entropy_block_grown", format!("entropy block grown to {block} bytes to keep the map at 4096 blocks or fewer")));
    }
    let locations: Vec<Location> = scan
        .regions
        .iter()
        .skip(p.offset)
        .take(p.limit.clamp(1, 50))
        .map(|r| Location::new("file_offset", format!("{:#x}", r.offset.saturating_add(base))).with_label(r.kind))
        .collect();
    let ev = builder(
        ctx,
        "firmware_regions_list",
        input.subject.clone(),
        json!({"path": p.path, "range": p.range, "max_regions": p.max_regions, "entropy_block": p.entropy_block, "offset": p.offset, "limit": p.limit}),
    )
    .result(json!({
        "path": input.path,
        "size": input.bytes.len(),
        "scanned": {"offset": base, "length": data.len()},
        "regions_total": regions.len(),
        "by_kind": by_kind,
        "by_family": by_family,
        "regions": page_items,
        "layout": {
            "total_bytes": lay.total_bytes,
            "recognised_bytes": lay.recognised_bytes,
            "recognised_percent": lay.recognised_percent,
            "unknown_length_regions": lay.unknown_length_regions,
            "gaps": lay.gaps.iter().map(shift).collect::<Vec<_>>(),
            "high_entropy_unrecognised": lay.high_entropy_unrecognised.iter().map(shift).collect::<Vec<_>>(),
            "spans_truncated": lay.spans_truncated,
        },
        "entropy": {"block_size": block, "mean": (mean * 1000.0).round() / 1000.0, "classes": classes, "blocks": blocks},
        "truncated": scan.truncated,
        "probes_exhausted": scan.probes_exhausted,
    }))
    .summary(summary)
    .confidence(Confidence::Derived)
    .limitations(lims)
    .coverage(cov)
    .locations(locations)
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// Extraction

/// Data waiting to be scanned: where its carvings go and how deep it sits.
struct Job {
    data: Vec<u8>,
    /// Folder (relative components) that receives what is carved from this data.
    dir: Vec<String>,
    /// 0 = the input; each unpacking adds one.
    level: u32,
    /// Relative path of the file this data was written to, or `<input>`.
    parent: String,
    /// Offset added to region offsets (the range start for the input, 0 below).
    base: u64,
}

struct Writer<'a> {
    root: &'a Path,
    files: usize,
    bytes: u64,
    max_files: usize,
    max_bytes: u64,
    outputs: Vec<Value>,
    skipped: Vec<Value>,
    truncated: bool,
    max_level: u32,
}

impl Writer<'_> {
    fn remaining(&self) -> u64 {
        self.max_bytes.saturating_sub(self.bytes)
    }

    fn skip(&mut self, what: &str, reason: impl Into<String>) {
        if self.skipped.len() < 2000 {
            self.skipped.push(json!({"path": what, "reason": reason.into()}));
        }
    }

    /// Write one output; false when it was skipped (limits, name clash, unsafe path).
    fn write(&mut self, rel: &[String], data: &[u8], meta: Value, level: u32) -> bool {
        let shown = rel.join("/");
        if self.files >= self.max_files || data.len() as u64 > self.remaining() {
            self.truncated = true;
            self.skip(&shown, "output file or byte limit reached");
            return false;
        }
        match write_new_file(self.root, rel, data) {
            Ok(_) => {
                self.files += 1;
                self.bytes += data.len() as u64;
                self.max_level = self.max_level.max(level);
                let mut m = meta;
                if let Value::Object(o) = &mut m {
                    o.insert("path".into(), json!(shown));
                    o.insert("size".into(), json!(data.len()));
                    o.insert("sha256".into(), json!(sha256_hex(data)));
                    o.insert("level".into(), json!(level));
                }
                self.outputs.push(m);
                true
            }
            Err(e) => {
                self.skip(&shown, e);
                false
            }
        }
    }
}

/// Unpacked output: (relative path, bytes, action, folder for what is carved out of it).
type Produced = (Vec<String>, Vec<u8>, &'static str, Vec<String>);

fn child(dir: &[String], name: String) -> Vec<String> {
    let mut v = dir.to_vec();
    v.push(name);
    v
}

/// A member or embedded name as one safe path component (its last component), or a fallback.
fn safe_leaf(name: &str, fallback: &str) -> String {
    safe_components(name).ok().and_then(|c| c.last().cloned()).filter(|s| s.len() <= 200).unwrap_or_else(|| fallback.to_string())
}

fn firmware_image_extract(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExtractParams = parse_params(params)?;
    if !(1..=10).contains(&p.max_depth) {
        return Err(ToolError::invalid("max_depth must be 1..=10"));
    }
    if p.max_output_bytes == 0 || p.max_output_bytes > 512 << 20 {
        return Err(ToolError::invalid("max_output_bytes must be 1..=536870912 (512 MiB)"));
    }
    if !(1..=100_000).contains(&p.max_output_files) {
        return Err(ToolError::invalid("max_output_files must be 1..=100000"));
    }
    let input = load(ctx, p.path.as_deref(), fw::MAX_INPUT)?;
    let (data, base) = apply_range(&input.bytes, p.range)?;
    let out = create_absent_dir(&p.output_directory)?;
    ctx.report(None, format!("Extracting {} into {}", input.name, out.display()));
    let mut w = Writer {
        root: &out,
        files: 0,
        bytes: 0,
        max_files: p.max_output_files,
        max_bytes: p.max_output_bytes,
        outputs: Vec::new(),
        skipped: Vec::new(),
        truncated: false,
        max_level: 0,
    };
    let mut not_unpacked: BTreeMap<&'static str, usize> = BTreeMap::new();
    let mut deeper_than_limit = 0usize;
    let mut jobs = vec![Job { data: data.to_vec(), dir: Vec::new(), level: 0, parent: "<input>".into(), base }];
    let mut scanned = 0usize;
    let mut scan_truncated = false;
    while let Some(job) = jobs.pop() {
        ctx.cancel.check()?;
        scanned += 1;
        let cancel = ctx.cancel.clone();
        let scan = fw::scan(&job.data, &ScanOptions::default(), &|| cancel.is_cancelled());
        if scan.cancelled {
            return Err(ToolError::cancelled());
        }
        scan_truncated |= scan.truncated;
        let regions = scan.regions;
        for (k, r) in regions.iter().enumerate() {
            ctx.cancel.check()?;
            let start = usize::try_from(r.offset).unwrap_or(usize::MAX);
            let next_start = regions.get(k + 1).and_then(|n| usize::try_from(n.offset).ok()).unwrap_or(job.data.len());
            let end = r.end().and_then(|e| usize::try_from(e).ok()).unwrap_or(next_start).min(job.data.len());
            let Some(slice) = job.data.get(start..end) else { continue };
            let label = format!("{:x}-{}", r.offset.saturating_add(job.base), r.kind);
            let meta = |action: &str| json!({"kind": r.kind, "action": action, "offset": r.offset.saturating_add(job.base), "parent": job.parent, "length_known": r.length.is_some()});
            // Data that is exactly one region is already a file on disk; don't write it twice.
            let whole = job.level > 0 && start == 0 && end == job.data.len();
            if !whole {
                w.write(&child(&job.dir, format!("{label}.bin")), slice, meta("carved"), job.level.max(1));
            }
            if r.unpack == Unpack::Carve {
                *not_unpacked.entry(r.kind).or_default() += 1;
                continue;
            }
            let level = job.level + 1;
            if level > p.max_depth {
                deeper_than_limit += 1;
                continue;
            }
            // When this data is exactly the region, its folder already belongs to it.
            let sub = if whole { job.dir.clone() } else { child(&job.dir, format!("{label}.extracted")) };
            let parent_rel = if whole { job.parent.clone() } else { format!("{}/{label}.bin", job.dir.join("/")).trim_start_matches('/').to_string() };
            let mut produced: Vec<Produced> = Vec::new();
            match (r.unpack, r.kind) {
                (Unpack::Decompress, "gzip") => match fw::gunzip(slice, w.remaining()) {
                    Ok((d, _)) => {
                        let name = fw::gzip_header(slice)
                            .and_then(|h| h.original_name)
                            .map(|n| safe_leaf(&n, "decompressed.bin"))
                            .unwrap_or_else(|| "decompressed.bin".into());
                        produced.push((child(&sub, name), d, "decompressed", sub.clone()));
                    }
                    Err(e) => w.skip(&format!("{label}.extracted"), e.to_string()),
                },
                (Unpack::Decompress, "xz") => {
                    decompress_into(&mut produced, &sub, decompress::xz(slice, w.remaining()).map_err(|e| e.to_string()), &mut w, &label)
                }
                (Unpack::Decompress, "lzma") => {
                    decompress_into(&mut produced, &sub, decompress::lzma(slice, w.remaining()).map_err(|e| e.to_string()), &mut w, &label)
                }
                (Unpack::Decompress, "bzip2") => {
                    decompress_into(&mut produced, &sub, decompress::bzip2(slice, w.remaining()).map_err(|e| e.to_string()), &mut w, &label)
                }
                (Unpack::Decompress, "zstd") => {
                    decompress_into(&mut produced, &sub, decompress::zstd(slice, w.remaining()).map_err(|e| e.to_string()), &mut w, &label)
                }
                (Unpack::Decompress, _) => match fw::inflate(slice, true, w.remaining(), true) {
                    Ok(inf) => produced.push((child(&sub, "decompressed.bin".into()), inf.data.unwrap_or_default(), "decompressed", sub.clone())),
                    Err(e) => w.skip(&format!("{label}.extracted"), e.to_string()),
                },
                (Unpack::Filesystem, kind) => {
                    let limits = Limits { max_total_bytes: w.remaining(), max_file_bytes: w.remaining(), ..Limits::default() };
                    match fsread::read(kind, slice, &limits) {
                        Some(fsimg) => {
                            for wmsg in &fsimg.warnings {
                                w.skip(&format!("{label}.extracted"), format!("{kind}: {wmsg}"));
                            }
                            let mut wrote_any = false;
                            for e in &fsimg.entries {
                                ctx.cancel.check()?;
                                if e.kind != FsKind::File {
                                    if e.kind == FsKind::Symlink {
                                        w.skip(&format!("{label}.extracted/{}", e.path), "symlink not created");
                                    }
                                    continue;
                                }
                                let Some(d) = &e.data else {
                                    w.skip(&format!("{label}.extracted/{}", e.path), "file data not recovered");
                                    continue;
                                };
                                match safe_components(&e.path) {
                                    Ok(c) => {
                                        let mut rel = sub.clone();
                                        rel.extend(c.iter().cloned());
                                        produced.push((rel, d.clone(), "filesystem-file", member_dir(&sub, &c)));
                                        wrote_any = true;
                                    }
                                    Err(why) => w.skip(&format!("{label}.extracted/{}", e.path), format!("refused: {why}")),
                                }
                            }
                            if !wrote_any && fsimg.entries.iter().all(|e| e.kind != FsKind::File) {
                                *not_unpacked.entry(r.kind).or_default() += 1;
                            }
                        }
                        None => *not_unpacked.entry(r.kind).or_default() += 1,
                    }
                }
                (Unpack::Members, "zip") => match zip::parse(slice, p.max_output_files.saturating_mul(2)) {
                    Ok(z) => {
                        for e in z.entries.iter().filter(|e| !e.is_dir) {
                            ctx.cancel.check()?;
                            match (safe_components(&e.name), zip::read_entry(slice, e, w.remaining())) {
                                (Ok(c), Ok(d)) => {
                                    let mut rel = sub.clone();
                                    rel.extend(c.iter().cloned());
                                    let scan_dir = member_dir(&sub, &c);
                                    produced.push((rel, d, "member", scan_dir));
                                }
                                (Err(why), _) => w.skip(&format!("{label}.extracted/{}", e.name), format!("refused: {why}")),
                                (_, Err(err)) => w.skip(&format!("{label}.extracted/{}", e.name), err.to_string()),
                            }
                        }
                    }
                    Err(e) => w.skip(&format!("{label}.extracted"), e.to_string()),
                },
                (Unpack::Members, kind) => {
                    let listing = if kind == "tar" { tarcpio::tar(slice, p.max_output_files) } else { tarcpio::cpio(slice, p.max_output_files) };
                    match listing {
                        Some(l) => {
                            for m in &l.members {
                                ctx.cancel.check()?;
                                let shown = format!("{label}.extracted/{}", m.name);
                                match m.kind {
                                    tarcpio::MemberKind::Dir => continue,
                                    tarcpio::MemberKind::File => {}
                                    other => {
                                        w.skip(
                                            &shown,
                                            format!(
                                                "{} not created",
                                                serde_json::to_value(other).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_default()
                                            ),
                                        );
                                        continue;
                                    }
                                }
                                let c = match safe_components(&m.name) {
                                    Ok(c) => c,
                                    Err(why) => {
                                        w.skip(&shown, format!("refused: {why}"));
                                        continue;
                                    }
                                };
                                let Some(d) = tarcpio::member_data(slice, m) else {
                                    w.skip(&shown, "member data runs past the end of the archive");
                                    continue;
                                };
                                let mut rel = sub.clone();
                                rel.extend(c.iter().cloned());
                                produced.push((rel, d.to_vec(), "member", member_dir(&sub, &c)));
                            }
                        }
                        None => w.skip(&format!("{label}.extracted"), "archive header unreadable"),
                    }
                }
                (Unpack::Payload, "uimage") => {
                    let size = r.details.get("data_size").and_then(Value::as_u64).unwrap_or(0);
                    if let Some(d) = slice.get(64..).map(|s| s.get(..usize::try_from(size).unwrap_or(usize::MAX).min(s.len())).unwrap_or(s)) {
                        produced.push((child(&sub, "payload.bin".into()), d.to_vec(), "payload", sub.clone()));
                    }
                }
                (Unpack::Payload, _) => {
                    for (name, off, len) in boot_parts(r, slice) {
                        if let Some(d) = slice.get(off..off.saturating_add(len)) {
                            produced.push((child(&sub, name.into()), d.to_vec(), "payload", sub.clone()));
                        }
                    }
                }
                _ => {}
            }
            for (rel, d, action, scan_dir) in produced {
                let mut m = meta(action);
                if let Value::Object(o) = &mut m {
                    o.insert("parent".into(), json!(parent_rel));
                    if action != "carved" {
                        o.insert("offset".into(), Value::Null);
                    }
                }
                let shown = rel.join("/");
                if w.write(&rel, &d, m, level) && !d.is_empty() {
                    jobs.push(Job { data: d, dir: scan_dir, level, parent: shown, base: 0 });
                }
            }
        }
    }
    let manifest = json!({"input": input.path, "sha256": input.subject.sha256, "range": p.range, "max_depth": p.max_depth, "outputs": w.outputs, "skipped": w.skipped, "not_unpacked": not_unpacked});
    let manifest_bytes = serde_json::to_vec_pretty(&manifest).map_err(|e| ToolError::internal(e.to_string()))?;
    let manifest_path = write_new_file(&out, &["manifest.json".to_string()], &manifest_bytes)
        .map_err(|e| ToolError::new(ErrorCode::FileError, format!("could not write manifest.json: {e}")))?;
    let total = w.outputs.len();
    let listed: Vec<&Value> = w.outputs.iter().take(p.limit.clamp(1, 5000)).collect();
    let mut by_action: BTreeMap<String, usize> = BTreeMap::new();
    for o in &w.outputs {
        *by_action.entry(o.get("action").and_then(Value::as_str).unwrap_or("").to_string()).or_default() += 1;
    }
    let summary = format!(
        "Wrote {} file(s), {} bytes, from {} into {} ({}); {} level(s) deep{}.",
        w.files,
        w.bytes,
        input.name,
        out.display(),
        by_action.iter().map(|(k, n)| format!("{n} {k}")).collect::<Vec<_>>().join(", "),
        w.max_level,
        if w.skipped.is_empty() { String::new() } else { format!("; {} skipped", w.skipped.len()) }
    );
    let mut lims = scan_limitations();
    if !not_unpacked.is_empty() {
        lims.push(Limitation::new(
            "carved_only",
            format!(
                "Carved as raw bytes but not unpacked (the built-in engine has no reader for their contents): {}.",
                not_unpacked.iter().map(|(k, n)| format!("{k} ×{n}")).collect::<Vec<_>>().join(", ")
            ),
        ));
    }
    lims.push(Limitation::new(
        "unknown_length_carves",
        "Regions whose length the format doesn't state are carved up to the next region or the end of the data.",
    ));
    if deeper_than_limit > 0 {
        lims.push(Limitation::new(
            "max_depth",
            format!("{deeper_than_limit} region(s) at the depth limit were carved but not unpacked; raise max_depth to go further."),
        ));
    }
    if w.truncated {
        lims.push(Limitation::new("truncated", "The output byte or file limit stopped extraction; raise max_output_bytes or max_output_files."));
    }
    if scan_truncated {
        lims.push(Limitation::new(
            "truncated",
            format!("A scan stopped at max_regions={}; extract smaller ranges to recover omitted regions.", ScanOptions::default().max_regions),
        ));
    }
    let truncated = w.truncated || scan_truncated;
    let complete = !truncated && w.skipped.is_empty() && deeper_than_limit == 0;
    let ev = builder(
        ctx,
        "firmware_image_extract",
        input.subject.clone(),
        json!({"path": p.path, "output_directory": p.output_directory, "range": p.range, "max_depth": p.max_depth, "max_output_bytes": p.max_output_bytes, "max_output_files": p.max_output_files}),
    )
    .result(json!({
        "output_directory": out,
        "manifest": manifest_path,
        "files_written": w.files,
        "bytes_written": w.bytes,
        "levels": w.max_level,
        "data_scanned": scanned,
        "by_action": by_action,
        "outputs_total": total,
        "outputs": listed,
        "skipped": w.skipped,
        "not_unpacked": not_unpacked,
        "truncated": truncated,
    }))
    .summary(summary)
    .confidence(Confidence::Observed)
    .limitations(lims)
    .coverage(Coverage { status: if complete { CoverageStatus::Complete } else { CoverageStatus::Partial }, examined: Some(total as u64), total: None, next_offset: None })
    .location(Location::new("path", out.display().to_string()).with_label("output folder"))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

/// Push a decompressed stream as `decompressed.bin`, or record why it could not be decompressed.
fn decompress_into(produced: &mut Vec<Produced>, sub: &[String], result: Result<Vec<u8>, String>, w: &mut Writer<'_>, label: &str) {
    match result {
        Ok(d) => produced.push((child(sub, "decompressed.bin".into()), d, "decompressed", sub.to_vec())),
        Err(e) => w.skip(&format!("{label}.extracted"), e),
    }
}

/// Folder that receives what is carved out of an unpacked member: `<member>.extracted` beside it.
fn member_dir(sub: &[String], comps: &[String]) -> Vec<String> {
    let mut v = sub.to_vec();
    if let Some((last, parents)) = comps.split_last() {
        v.extend(parents.iter().cloned());
        v.push(format!("{last}.extracted"));
    }
    v
}

/// The kernel, ramdisk and second-stage parts of an Android boot image: (name, offset, length).
fn boot_parts(r: &Region, slice: &[u8]) -> Vec<(&'static str, usize, usize)> {
    let get = |k: &str| r.details.get(k).and_then(Value::as_u64).and_then(|v| usize::try_from(v).ok()).unwrap_or(0);
    let page = get("page_size").max(1);
    let align = |v: usize| v.div_ceil(page).saturating_mul(page);
    let kernel = get("kernel_size");
    let ramdisk = get("ramdisk_size");
    let second = get("second_size");
    let k_off = page;
    let r_off = k_off.saturating_add(align(kernel));
    let s_off = r_off.saturating_add(align(ramdisk));
    [("kernel.bin", k_off, kernel), ("ramdisk.bin", r_off, ramdisk), ("second.bin", s_off, second)]
        .into_iter()
        .filter(|(_, o, l)| *l > 0 && o.checked_add(*l).is_some_and(|e| e <= slice.len()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_testkit::firmware as fx;
    use serde_json::json;
    use std::path::PathBuf;

    fn fresh_out(tag: &str) -> PathBuf {
        let d = tempfile::tempdir().unwrap().keep();
        d.join(format!("out-{tag}"))
    }

    #[test]
    fn inspects_regions_with_paging_and_range() {
        let (img, l) = fx::image();
        let p = craft_anything_testkit::temp_file("fw.bin", &img);
        let e = Engine::new(crate::testing::session());
        let v = call(&e, "firmware_regions_list", json!({"path": p}));
        let res = &v["result"];
        assert_eq!(res["regions_total"], 6, "{}", res["by_kind"]);
        assert_eq!(res["by_kind"]["uimage"], 1);
        assert_eq!(res["regions"][0]["kind"], "uimage");
        assert_eq!(res["regions"][0]["details"]["name"], "Craft Linux-5.10");
        assert!(res["layout"]["high_entropy_unrecognised"].as_array().unwrap().iter().any(|s| s["offset"] == l.noise.0));
        assert!(!res["entropy"]["blocks"].as_array().unwrap().is_empty());
        let page = call(&e, "firmware_regions_list", json!({"path": p, "offset": 1, "limit": 2}));
        assert_eq!(page["coverage"]["next_offset"], 3);
        assert_eq!(page["result"]["regions"].as_array().unwrap().len(), 2);
        let ranged = call(&e, "firmware_regions_list", json!({"path": p, "range": {"offset": l.tar.0, "length": l.tar.1 + l.cpio.1 + 0x200}}));
        let kinds: Vec<_> =
            ranged["result"]["regions"].as_array().unwrap().iter().map(|r| (r["kind"].as_str().unwrap().to_string(), r["offset"].as_u64().unwrap())).collect();
        assert!(kinds.contains(&("tar".into(), l.tar.0 as u64)), "{kinds:?}");
        assert!(kinds.contains(&("cpio-newc".into(), l.cpio.0 as u64)), "{kinds:?}");
        assert!(call_err(&e, "firmware_regions_list", json!({"path": p, "entropy_block": 1})).message.contains("entropy_block"));
        assert!(call_err(&e, "firmware_regions_list", json!({"path": p, "range": {"offset": 1u64 << 40, "length": 1}})).message.contains("past the end"));
        assert!(call_err(&e, "firmware_regions_list", json!({"path": "relative.bin"})).message.contains("absolute"));
    }

    #[test]
    fn decompresses_xz_lzma_bzip2_zstd() {
        let e = Engine::new(crate::testing::session());
        for (name, fixture, plain) in [
            ("xz", fx::XZ_FIXTURE, fx::XZ_PLAIN),
            ("lzma", fx::LZMA_FIXTURE, fx::LZMA_PLAIN),
            ("bzip2", fx::BZIP2_FIXTURE, fx::BZIP2_PLAIN),
            ("zstd", fx::ZSTD_FIXTURE, fx::ZSTD_PLAIN),
        ] {
            let p = craft_anything_testkit::temp_file(&format!("{name}.bin"), fixture);
            let out = fresh_out(name);
            let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out}));
            let got = std::fs::read(out.join(format!("0-{name}.extracted/decompressed.bin")))
                .unwrap_or_else(|_| panic!("{name}: {}", serde_json::to_string_pretty(&v["result"]).unwrap()));
            assert_eq!(got, plain, "{name}");
            std::fs::remove_dir_all(&out).unwrap();
        }
    }

    #[test]
    fn extracts_filesystems() {
        let e = Engine::new(crate::testing::session());
        let cases: Vec<(&str, Vec<u8>, &str, &[u8])> = vec![
            ("romfs", fx::romfs_image(), "etc/hostname", b"craft-router\n"),
            ("cramfs", fx::cramfs_image(), "dir/inner", b"nested"),
            ("ext2", fx::ext_image(false), "sub/note", b"nested note"),
            ("ext4", fx::ext_image(true), "hello.txt", b"Hello ext filesystem!\n"),
            ("squashfs", fx::squashfs_image(), "etc/motd", b"welcome\n"),
        ];
        for (kind, img, path, content) in cases {
            let p = craft_anything_testkit::temp_file(&format!("{kind}.bin"), &img);
            let out = fresh_out(&format!("fs-{kind}"));
            let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out}));
            // The region lands at offset 0; ext images report as ext2/ext4 by their feature bits.
            let region_kind = v["result"]["outputs"].as_array().unwrap().iter().find_map(|o| {
                let pp = o["path"].as_str()?;
                pp.strip_suffix(&format!(".extracted/{path}")).map(|s| s.to_string())
            });
            let dir = region_kind.unwrap_or_else(|| panic!("{kind}: no output for {path} in {}", serde_json::to_string_pretty(&v["result"]).unwrap()));
            let got = std::fs::read(out.join(format!("{dir}.extracted/{path}"))).unwrap();
            assert_eq!(got, content, "{kind}");
            std::fs::remove_dir_all(&out).unwrap();
        }
    }

    #[test]
    fn extracts_recursively_and_never_overwrites() {
        let (img, l) = fx::image();
        let p = craft_anything_testkit::temp_file("fw.bin", &img);
        let e = Engine::new(crate::testing::session());
        let out = fresh_out("a");
        let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out}));
        let res = &v["result"];
        // uImage payload → gzip → kernel text.
        let kernel = out.join("0-uimage.extracted/vmlinux");
        let k = std::fs::read(&kernel).unwrap_or_else(|_| panic!("{}", serde_json::to_string_pretty(&res["outputs"]).unwrap()));
        assert!(k.starts_with(fx::KERNEL_TEXT));
        assert_eq!(std::fs::read(out.join(format!("{:x}-tar.extracted/etc/hostname", l.tar.0))).unwrap(), b"craft-router\n");
        assert_eq!(std::fs::read(out.join(format!("{:x}-cpio-newc.extracted/init", l.cpio.0))).unwrap(), b"#!/bin/sh\nexec /sbin/init\n");
        assert_eq!(std::fs::read(out.join(format!("{:x}-zip.extracted/config/settings.json", l.zip.0))).unwrap(), b"{\"wifi\":true}");
        assert_eq!(std::fs::metadata(out.join(format!("{:x}-ext2.bin", l.ext2.0))).unwrap().len(), l.ext2.1 as u64);
        let manifest: serde_json::Value = serde_json::from_slice(&std::fs::read(out.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(manifest["outputs"].as_array().unwrap().len(), res["outputs_total"].as_u64().unwrap() as usize);
        assert!(manifest["outputs"].as_array().unwrap().iter().all(|o| o["sha256"].as_str().unwrap().len() == 64));
        assert_eq!(res["not_unpacked"]["squashfs"], 1);
        assert!(res["levels"].as_u64().unwrap() >= 2);
        assert!(v["limitations"].as_array().unwrap().iter().any(|x| x["code"] == "carved_only"));
        // The folder now exists: a second run must refuse rather than overwrite.
        let err = call_err(&e, "firmware_image_extract", json!({"path": p, "output_directory": out}));
        assert!(err.message.contains("already exists"));
        assert!(call_err(&e, "firmware_image_extract", json!({"path": p, "output_directory": "rel/out"})).message.contains("absolute"));
        std::fs::remove_dir_all(&out).unwrap();
    }

    #[test]
    fn extraction_reports_a_scan_cap_as_partial_coverage() {
        let mut elf = vec![0; 121];
        elf[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        for (offset, value) in [(16, 2u16), (18, 62), (52, 64), (54, 56), (56, 1), (58, 64)] {
            elf[offset..offset + 2].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(20, 1u32), (64, 1), (68, 5)] {
            elf[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
        }
        for (offset, value) in [(24, 0x400078u64), (32, 64), (80, 0x400000), (88, 0x400000), (96, 121), (104, 121), (112, 4096)] {
            elf[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
        }
        elf[120] = 0xc3;
        let root = tempfile::tempdir().unwrap();
        let input = root.path().join("many-elf.bin");
        std::fs::write(&input, elf.repeat(2001)).unwrap();
        let e = Engine::new(crate::testing::session());
        let listing = call(&e, "firmware_regions_list", json!({"path": input, "max_regions": 2002, "limit": 5000}));
        assert_eq!(listing["result"]["regions_total"], 2001);
        assert_eq!(listing["result"]["truncated"], false);
        let out = root.path().join("out");
        let v = call(&e, "firmware_image_extract", json!({"path": input, "output_directory": out, "limit": 1}));
        assert_eq!(v["result"]["files_written"], 2000);
        assert_eq!(v["result"]["bytes_written"], 242000);
        assert_eq!(v["result"]["skipped"], json!([]));
        assert_eq!(v["result"]["outputs"].as_array().unwrap().len(), 1);
        let manifest: serde_json::Value = serde_json::from_slice(&std::fs::read(out.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(manifest["outputs"].as_array().unwrap().len(), 2000);
        assert_eq!(std::fs::read_dir(&out).unwrap().count(), 2001);
        assert_eq!(std::fs::read(out.join(format!("{:x}-elf.bin", 1999 * 121))).unwrap(), elf);
        assert!(!out.join(format!("{:x}-elf.bin", 2000 * 121)).exists());
        assert_eq!(v["result"]["truncated"], true);
        assert_eq!(v["coverage"]["status"], "partial");
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "truncated" && l["message"].as_str().unwrap().contains("2000")));
        let ranged_out = root.path().join("ranged-out");
        let ranged = call(
            &e,
            "firmware_image_extract",
            json!({"path": input, "output_directory": ranged_out, "range": {"offset": 2000 * 121, "length": 121}, "limit": 1}),
        );
        assert_eq!(ranged["result"]["files_written"], 1);
        assert_eq!(ranged["result"]["truncated"], false);
        assert_eq!(ranged["coverage"]["status"], "complete");
        assert_eq!(std::fs::read(ranged_out.join(format!("{:x}-elf.bin", 2000 * 121))).unwrap(), elf);
    }

    #[test]
    fn depth_and_caps_are_honoured() {
        let (img, _) = fx::image();
        let p = craft_anything_testkit::temp_file("fw.bin", &img);
        let e = Engine::new(crate::testing::session());
        let out = fresh_out("depth");
        let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out, "max_depth": 1}));
        assert!(out.join("0-uimage.extracted/payload.bin").exists());
        assert!(!out.join("0-uimage.extracted/vmlinux").exists());
        assert!(v["limitations"].as_array().unwrap().iter().any(|x| x["code"] == "max_depth"));
        let out2 = fresh_out("caps");
        let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out2, "max_output_files": 3}));
        assert_eq!(v["result"]["files_written"], 3);
        assert_eq!(v["result"]["truncated"], true);
        assert_eq!(v["coverage"]["status"], "partial");
        let out3 = fresh_out("bytes");
        let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out3, "max_output_bytes": 4096}));
        assert!(v["result"]["bytes_written"].as_u64().unwrap() <= 4096);
        assert!(call_err(&e, "firmware_image_extract", json!({"path": p, "output_directory": fresh_out("x"), "max_depth": 11})).message.contains("max_depth"));
        for d in [out, out2, out3] {
            std::fs::remove_dir_all(d).unwrap();
        }
    }

    #[test]
    fn slip_and_links_are_refused() {
        let t = fx::tar_entries(&[
            ("../../escape.txt", b'0', b"x", ""),
            ("/etc/abs", b'0', b"y", ""),
            ("link", b'2', b"", "/etc/passwd"),
            ("ok/fine.txt", b'0', b"fine", ""),
        ]);
        let z = craft_anything_testkit::electron::zip_stored(&[("../zip-escape", b"z"), ("good.txt", b"g")]);
        let c = fx::cpio_newc(&[("../cpio-escape", b"c", 0o100644), ("sym", b"/bin/sh", 0o120777), ("keep", b"k", 0o100644)]);
        let mut img = t.clone();
        while !img.len().is_multiple_of(512) {
            img.push(0);
        }
        let z_off = img.len();
        img.extend_from_slice(&z);
        img.extend(vec![0u8; 512 - img.len() % 512]);
        let c_off = img.len();
        img.extend_from_slice(&c);
        let p = craft_anything_testkit::temp_file("evil.bin", &img);
        let e = Engine::new(crate::testing::session());
        let out = fresh_out("slip");
        let v = call(&e, "firmware_image_extract", json!({"path": p, "output_directory": out}));
        assert_eq!(std::fs::read(out.join("0-tar.extracted/ok/fine.txt")).unwrap(), b"fine");
        assert_eq!(std::fs::read(out.join(format!("{z_off:x}-zip.extracted/good.txt"))).unwrap(), b"g");
        assert_eq!(std::fs::read(out.join(format!("{c_off:x}-cpio-newc.extracted/keep"))).unwrap(), b"k");
        let skipped = v["result"]["skipped"].as_array().unwrap();
        assert!(skipped.len() >= 6, "{skipped:?}");
        assert!(!out.parent().unwrap().join("escape.txt").exists());
        assert!(!out.join("0-tar.extracted/link").exists());
        assert!(!out.join(format!("{c_off:x}-cpio-newc.extracted/sym")).exists());
        let all: Vec<_> = walk(&out);
        assert!(all.iter().all(|f| f.starts_with(&out)));
        std::fs::remove_dir_all(&out).unwrap();
    }

    fn walk(d: &std::path::Path) -> Vec<PathBuf> {
        let mut v = Vec::new();
        for e in std::fs::read_dir(d).unwrap().flatten() {
            let p = e.path();
            assert!(!e.file_type().unwrap().is_symlink());
            if p.is_dir() {
                v.extend(walk(&p));
            } else {
                v.push(p);
            }
        }
        v
    }

    #[test]
    fn damaged_images_never_panic() {
        let (img, _) = fx::image();
        let e = Engine::new(crate::testing::session());
        for (k, m) in craft_anything_testkit::mutations(&img).into_iter().enumerate().step_by(9) {
            let p = craft_anything_testkit::temp_file("m.bin", &m);
            let _ = e.call("firmware_regions_list", json!({"path": p}), crate::CallOptions::new(crate::Caller::Mcp));
            let out = fresh_out(&format!("m{k}"));
            let _ = e.call(
                "firmware_image_extract",
                json!({"path": p, "output_directory": out, "max_output_bytes": 1 << 20}),
                crate::CallOptions::new(crate::Caller::Mcp),
            );
            let _ = std::fs::remove_dir_all(&out);
        }
    }
}
