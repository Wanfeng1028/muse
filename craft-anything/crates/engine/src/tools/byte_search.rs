//! Byte-pattern search over a whole file: hex signatures with `??` wildcards and/or text in UTF-8
//! and UTF-16LE. Matches are listed by file offset; for native programs each also gets its virtual
//! address and containing section. Read-only, bounded and paged.

use super::native_common::{hex, image, params_json, select_document, spec};
use super::static_input::{self, builder};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, Limitation, Location, ToolError};
use craft_anything_formats::Binary;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "native_bytes_find",
        "Search for bytes",
        "Find every place a byte signature or a piece of text occurs in a file (an absolute path, or the active target). `pattern` is hex byte pairs with `??` for any byte (spaces optional, e.g. `48 8B ?? 24`); `text` is searched as UTF-8 and/or UTF-16LE. Matches are ordered by file offset and paged (offset/limit); for ELF, PE and Mach-O programs each match also carries its virtual address and containing section when the bytes are mapped. Overlapping matches are all reported. Counting stops at 100000 matches.",
        "Find where a byte pattern or a word appears inside a file.",
        Toolset::Native,
        Effects::EVIDENCE,
        Requires::Nothing,
        schema_of::<SearchBytesParams>,
        native_bytes_find,
    )]
}

/// Most matches counted before the search stops.
const MAX_MATCHES: usize = 100_000;
/// Longest pattern accepted, in bytes.
const MAX_PATTERN: usize = 1024;
/// Bytes of each match echoed back.
const ECHO: usize = 64;

fn d_limit() -> usize {
    100
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum TextEncoding {
    Utf8,
    Utf16le,
    /// Both UTF-8 and UTF-16LE (default).
    #[default]
    Both,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SearchBytesParams {
    /// Absolute path of the file to search; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Open document (id or name) to search instead of the active one; ignored with path.
    #[serde(default)]
    pub document: Option<String>,
    /// Hex byte pairs with `??` wildcards, e.g. "48 8B ?? 24 ?? 00".
    #[serde(default)]
    pub pattern: Option<String>,
    /// Text to find (exact, case-sensitive).
    #[serde(default)]
    pub text: Option<String>,
    /// How `text` is encoded in the file: utf8, utf16le or both (default).
    #[serde(default)]
    pub encoding: TextEncoding,
    /// First match of the page (0-based).
    #[serde(default)]
    pub offset: usize,
    /// Matches per page (1–1000, default 100).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

/// One byte of a signature: `None` matches anything.
type Pat = Vec<Option<u8>>;

/// Parse hex byte pairs and `??` wildcards (whitespace ignored).
fn parse_pattern(s: &str) -> Result<Pat, ToolError> {
    let compact: Vec<char> = s.chars().filter(|c| !c.is_whitespace()).collect();
    let bad = || ToolError::invalid(format!("pattern {s:?} is not hex byte pairs with ?? wildcards")).with_remediation("Write it like \"48 8B ?? 24\".");
    if compact.is_empty() || !compact.len().is_multiple_of(2) {
        return Err(bad());
    }
    let mut out = Vec::with_capacity(compact.len() / 2);
    for pair in compact.chunks(2) {
        let (a, b) = match pair {
            [a, b] => (*a, *b),
            _ => return Err(bad()),
        };
        if a == '?' && b == '?' {
            out.push(None);
        } else {
            let (Some(h), Some(l)) = (a.to_digit(16), b.to_digit(16)) else { return Err(bad()) };
            out.push(Some((h * 16 + l) as u8));
        }
    }
    if out.iter().all(Option::is_none) {
        return Err(ToolError::invalid("the pattern needs at least one concrete byte, not only ?? wildcards"));
    }
    if out.len() > MAX_PATTERN {
        return Err(ToolError::invalid(format!("the pattern is {} bytes; the limit is {MAX_PATTERN}", out.len())));
    }
    Ok(out)
}

/// Start offsets of every (overlapping) match of `pat` in `data`, up to `cap`. `None` when the
/// cap stopped the scan. Anchors on the first concrete byte so the inner loop is a byte search.
fn find_all(data: &[u8], pat: &Pat, cap: usize, cancelled: &dyn Fn() -> bool) -> (Vec<usize>, bool) {
    let mut hits = Vec::new();
    let Some((anchor, Some(first))) = pat.iter().enumerate().find(|(_, b)| b.is_some()).map(|(i, b)| (i, *b)) else {
        return (hits, false);
    };
    let mut i = anchor;
    let mut scanned_since_check = 0usize;
    while let Some(p) = data.get(i..).and_then(|h| h.iter().position(|&b| b == first)) {
        scanned_since_check += p + 1;
        if scanned_since_check > (8 << 20) {
            scanned_since_check = 0;
            if cancelled() {
                return (hits, true);
            }
        }
        let at = i + p;
        let start = at - anchor;
        let ok = data.get(start..start + pat.len()).is_some_and(|w| w.iter().zip(pat).all(|(b, m)| m.is_none_or(|m| m == *b)));
        if ok {
            if hits.len() >= cap {
                return (hits, true);
            }
            hits.push(start);
        }
        i = at + 1;
    }
    (hits, false)
}

#[derive(Debug, Serialize)]
struct Hit {
    file_offset: u64,
    file_offset_hex: String,
    /// pattern, utf8 or utf16le
    matched: &'static str,
    length: usize,
    bytes: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    address: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    section: Option<String>,
}

fn native_bytes_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SearchBytesParams = parse_params(params)?;
    let mut needles: Vec<(&'static str, Pat)> = Vec::new();
    if let Some(pt) = p.pattern.as_deref().filter(|s| !s.trim().is_empty()) {
        needles.push(("pattern", parse_pattern(pt)?));
    }
    if let Some(t) = p.text.as_deref().filter(|s| !s.is_empty()) {
        if t.len() > MAX_PATTERN {
            return Err(ToolError::invalid(format!("text is {} bytes; the limit is {MAX_PATTERN}", t.len())));
        }
        if p.encoding != TextEncoding::Utf16le {
            needles.push(("utf8", t.bytes().map(Some).collect()));
        }
        if p.encoding != TextEncoding::Utf8 {
            needles.push(("utf16le", t.encode_utf16().flat_map(u16::to_le_bytes).map(Some).collect()));
        }
    }
    if needles.is_empty() {
        return Err(ToolError::invalid("give pattern (hex with ?? wildcards) or text to search for"));
    }
    if p.path.is_none() {
        select_document(ctx, &p.document)?;
    }
    let input = static_input::load(ctx, p.path.as_deref(), static_input::DEFAULT_MAX_BYTES)?;
    ctx.report(None, format!("Searching {} ({} bytes)", input.name, input.bytes.len()));

    // Address mapping for native programs: the cached image for the active target, a fresh parse for a path.
    let cached = if p.path.is_none() { image(ctx).ok() } else { None };
    let parsed = if cached.is_none() { craft_anything_formats::parse_binary(&input.bytes).ok() } else { None };
    let bin: Option<&Binary> = cached.as_ref().map(|i| &i.0.bin).or(parsed.as_ref());

    let cancel = ctx.cancel.clone();
    let mut hits: Vec<(usize, usize, &'static str)> = Vec::new();
    let mut capped = false;
    for (what, pat) in &needles {
        let room = MAX_MATCHES.saturating_sub(hits.len());
        let (found, stopped) = find_all(&input.bytes, pat, room, &|| cancel.is_cancelled());
        ctx.cancel.check()?;
        capped |= stopped;
        hits.extend(found.into_iter().map(|o| (o, pat.len(), *what)));
    }
    hits.sort_unstable();

    let limit = p.limit.clamp(1, 1000);
    let rows: Vec<Hit> = hits
        .iter()
        .skip(p.offset)
        .take(limit)
        .map(|&(off, len, matched)| {
            let va = bin.and_then(|b| b.offset_to_va(off as u64));
            Hit {
                file_offset: off as u64,
                file_offset_hex: hex(off as u64),
                matched,
                length: len,
                bytes: input.bytes.get(off..off + len.min(ECHO)).map(hex::encode).unwrap_or_default(),
                address: va.map(hex),
                section: va.and_then(|a| bin.and_then(|b| b.section_at(a))).map(|s| s.name.clone()),
            }
        })
        .collect();
    let mut cov = Coverage::page(rows.len() as u64, hits.len() as u64, p.offset as u64);
    if capped {
        cov.status = CoverageStatus::Partial;
        cov.total = None;
    }

    let what = needles.iter().map(|(w, _)| *w).collect::<Vec<_>>().join(" + ");
    let summary = format!(
        "{}{} match(es) for {what} in {}{}.",
        if capped { "at least " } else { "" },
        hits.len(),
        input.name,
        if rows.is_empty() { String::new() } else { format!("; showing {} from #{}", rows.len(), p.offset) }
    );
    let mut lims = vec![Limitation::new(
        "file_bytes_only",
        "The file's bytes are searched as stored: compressed, encrypted or packed regions and data built at run time are not seen, so no match is not proof of absence.",
    )];
    if bin.is_none() {
        lims.push(Limitation::new("no_addresses", "This file is not a readable ELF, PE or Mach-O program, so matches carry file offsets only."));
    } else {
        lims.push(Limitation::new("unmapped_regions", "Matches in headers, overlays or debug data that are not loaded into memory have no virtual address."));
    }
    if capped {
        lims.push(Limitation::new("match_cap", format!("Counting stopped at {MAX_MATCHES} matches; use a more specific pattern.")));
    }
    let mut b = builder(ctx, "native_bytes_find", input.subject.clone(), params_json(&p))
        .result(json!({
            "path": input.path,
            "file_size": input.bytes.len(),
            "searched_for": needles.iter().map(|(w, pat)| json!({"kind": w, "length": pat.len()})).collect::<Vec<_>>(),
            "total_matches": hits.len(),
            "match_cap_reached": capped,
            "native_container": bin.map(|b| b.format),
            "offset": p.offset,
            "limit": limit,
            "matches": rows,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(cov);
    for &(off, _, _) in hits.iter().skip(p.offset).take(8) {
        b = b.location(Location::new("file_offset", hex(off as u64)));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err, engine_with};
    use super::{find_all, parse_pattern};
    use crate::Engine;
    use craft_anything_testkit as tk;
    use serde_json::json;

    #[test]
    fn pattern_parsing() {
        assert_eq!(parse_pattern("48 8b ?? 24").unwrap(), vec![Some(0x48), Some(0x8b), None, Some(0x24)]);
        assert_eq!(parse_pattern("488B??").unwrap().len(), 3);
        assert!(parse_pattern("?? ??").is_err());
        assert!(parse_pattern("4").is_err());
        assert!(parse_pattern("zz").is_err());
        assert!(parse_pattern("").is_err());
    }

    #[test]
    fn wildcards_and_overlaps() {
        let data = b"\x00\xaa\xaa\xaa\x01\xaa\x02\xaa";
        let (h, capped) = find_all(data, &parse_pattern("aa aa").unwrap(), 100, &|| false);
        assert_eq!(h, vec![1, 2]);
        assert!(!capped);
        let (h, _) = find_all(data, &parse_pattern("?? aa ?? aa").unwrap(), 100, &|| false);
        assert_eq!(h, vec![0, 2, 4]);
        let (h, capped) = find_all(data, &parse_pattern("aa").unwrap(), 2, &|| false);
        assert_eq!(h.len(), 2);
        assert!(capped);
        // A pattern longer than the data, or hanging off the end, never matches.
        let (h, _) = find_all(b"\xaa", &parse_pattern("aa bb").unwrap(), 10, &|| false);
        assert!(h.is_empty());
    }

    #[test]
    fn finds_text_with_addresses_in_a_native_target() {
        let (elf, l) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let v = call(&e, "native_bytes_find", json!({"text": tk::HELLO, "encoding": "utf8"}));
        let r = &v["result"];
        assert_eq!(r["total_matches"], 1);
        let m = &r["matches"][0];
        assert_eq!(m["file_offset"], tk::ELF_RODATA_OFF);
        assert_eq!(m["address"], format!("{:#x}", l.rodata_va));
        assert_eq!(m["section"], ".rodata");
        assert_eq!(m["matched"], "utf8");
    }

    #[test]
    fn utf16_paging_and_errors_on_a_path() {
        let mut data = b"xx".to_vec();
        for _ in 0..3 {
            data.extend("Hi!".encode_utf16().flat_map(u16::to_le_bytes));
            data.extend(b"Hi!");
        }
        let p = tk::temp_file("blob.bin", &data);
        let e = Engine::new(crate::testing::session());
        let v = call(&e, "native_bytes_find", json!({"path": p, "text": "Hi!", "limit": 2, "offset": 1}));
        assert_eq!(v["result"]["total_matches"], 6);
        assert_eq!(v["result"]["matches"].as_array().unwrap().len(), 2);
        assert_eq!(v["coverage"]["next_offset"], 3);
        assert!(v["result"]["native_container"].is_null());
        let v = call(&e, "native_bytes_find", json!({"path": p, "pattern": "48 00 ?? 00 21 00"}));
        assert_eq!(v["result"]["total_matches"], 3);
        assert_eq!(v["result"]["matches"][0]["file_offset"], 2);
        call_err(&e, "native_bytes_find", json!({"path": p}));
        call_err(&e, "native_bytes_find", json!({"path": p, "pattern": "?? ??"}));
    }
}
