//! Node.js single executable applications: a blob of the main script, its optional code cache and
//! assets, injected as a section (Mach-O), note (ELF) or resource (PE), or kept as a bare file while
//! it's being prepared.
//!
//! The blob names nothing about its own layout beyond its flags, and Node has changed the layout
//! over time, so a layout is accepted only when it accounts for every byte of the blob.

use crate::common::{FormatError, find_bytes};
use crate::packed::{Compression, MAX_ENTRIES, PackedEntry, PackedFormat, PackedListing};
use crate::packed_carrier::{self, Span};
use serde_json::json;

const MAGIC: [u8; 4] = 0x0143_da20u32.to_le_bytes();
const RESOURCE: &str = "NODE_SEA_BLOB";
/// Text an injected program flips the end of. The hash is Node's published value.
const FUSE: &[u8] = b"NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2:";
/// How many items a count in the blob may claim.
const MAX_COUNT: u64 = 1 << 20;

const FLAG_NO_WARNING: u32 = 1;
const FLAG_SNAPSHOT: u32 = 1 << 1;
const FLAG_CODE_CACHE: u32 = 1 << 2;
const FLAG_ASSETS: u32 = 1 << 3;
const FLAG_EXEC_ARGV: u32 = 1 << 4;
const KNOWN_FLAGS: u32 = FLAG_NO_WARNING | FLAG_SNAPSHOT | FLAG_CODE_CACHE | FLAG_ASSETS | FLAG_EXEC_ARGV;

/// The reader.
pub struct NodeSea;

/// One known shape of the blob's front.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Layout {
    label: &'static str,
    /// A byte after the flags saying how exec arguments extend.
    extension_byte: bool,
    /// The main script's path comes before its code.
    code_path: bool,
}

const LAYOUTS: &[Layout] = &[
    Layout { label: "with_exec_argv_extension", extension_byte: true, code_path: true },
    Layout { label: "with_code_path", extension_byte: false, code_path: true },
    Layout { label: "code_only", extension_byte: false, code_path: false },
];

/// A range of the blob, relative to the file.
#[derive(Debug, Clone, Copy)]
struct Part {
    start: usize,
    len: usize,
}

struct Cursor<'a> {
    blob: &'a [u8],
    pos: usize,
    base: usize,
}

impl Cursor<'_> {
    fn number(&mut self) -> Option<u64> {
        let b: [u8; 8] = self.blob.get(self.pos..self.pos.checked_add(8)?)?.try_into().ok()?;
        self.pos += 8;
        Some(u64::from_le_bytes(b))
    }

    fn part(&mut self) -> Option<Part> {
        let len = usize::try_from(self.number()?).ok()?;
        let at = self.pos;
        let end = at.checked_add(len)?;
        if end > self.blob.len() {
            return None;
        }
        self.pos = end;
        Some(Part { start: self.base.checked_add(at)?, len })
    }

    fn count(&mut self) -> Option<usize> {
        let n = self.number()?;
        if n > MAX_COUNT {
            return None;
        }
        usize::try_from(n).ok()
    }
}

/// A blob read with one layout.
#[derive(Debug)]
struct Parsed {
    layout: Layout,
    flags: u32,
    extension: Option<u8>,
    code_path: Option<Part>,
    code: Part,
    code_cache: Option<Part>,
    assets: Vec<(Part, Part)>,
    exec_argv: Vec<Part>,
    trailing_zeros: usize,
}

/// Read with this layout. `None` unless the layout accounts for every byte (bar trailing zeros,
/// which a carrier's padding can add).
fn parse_with(blob: &[u8], base: usize, flags: u32, layout: Layout) -> Option<Parsed> {
    let mut c = Cursor { blob, pos: 8, base };
    let mut extension = None;
    if layout.extension_byte {
        let e = *blob.get(c.pos)?;
        if e > 2 {
            return None;
        }
        extension = Some(e);
        c.pos += 1;
    }
    let code_path = if layout.code_path { Some(c.part()?) } else { None };
    let code = c.part()?;
    let code_cache = if flags & FLAG_CODE_CACHE != 0 { Some(c.part()?) } else { None };
    let mut assets = Vec::new();
    if flags & FLAG_ASSETS != 0 {
        for _ in 0..c.count()? {
            let key = c.part()?;
            assets.push((key, c.part()?));
        }
    }
    let mut exec_argv = Vec::new();
    if flags & FLAG_EXEC_ARGV != 0 {
        for _ in 0..c.count()? {
            exec_argv.push(c.part()?);
        }
    }
    let rest = blob.get(c.pos..)?;
    if rest.iter().any(|b| *b != 0) {
        return None;
    }
    Some(Parsed { layout, flags, extension, code_path, code, code_cache, assets, exec_argv, trailing_zeros: rest.len() })
}

fn parse_blob(blob: &[u8], base: usize) -> Result<Parsed, FormatError> {
    let flags_raw: [u8; 4] = blob.get(4..8).and_then(|b| b.try_into().ok()).ok_or_else(|| FormatError::Truncated("the Node blob header".into()))?;
    let flags = u32::from_le_bytes(flags_raw);
    if flags & !KNOWN_FLAGS != 0 {
        return Err(FormatError::Unsupported(format!("Node blob flags {flags:#x} include some we don't know, so its layout can't be trusted")));
    }
    let mut fits = LAYOUTS.iter().filter_map(|l| parse_with(blob, base, flags, *l));
    match (fits.next(), fits.next()) {
        (Some(one), None) => Ok(one),
        (Some(_), Some(_)) => Err(FormatError::Unsupported("more than one known Node blob layout fits this file".into())),
        (None, _) => {
            Err(FormatError::Unsupported("no known Node blob layout accounts for every byte of this file; it's damaged or from a version we don't know".into()))
        }
    }
}

/// Where the blob is, and how it's carried.
fn locate(data: &[u8]) -> Option<(Span, &'static str)> {
    if data.starts_with(&MAGIC) {
        return Some((Span { start: 0, len: data.len() }, "bare_blob"));
    }
    let good = |s: &Span| s.bytes(data).is_some_and(|b| b.starts_with(&MAGIC));
    packed_carrier::sections(data, "__NODE_SEA_BLOB", &["NODE_SEA", "__NODE_SEA"])
        .into_iter()
        .find(good)
        .map(|s| (s, "macho_section"))
        .or_else(|| packed_carrier::elf_notes(data, RESOURCE).into_iter().find(good).map(|s| (s, "elf_note")))
        .or_else(|| packed_carrier::sections(data, RESOURCE, &[]).into_iter().find(good).map(|s| (s, "elf_section")))
        .or_else(|| packed_carrier::pe_resources(data, RESOURCE).into_iter().find(good).map(|s| (s, "pe_resource")))
}

fn text(data: &[u8], p: Part) -> String {
    data.get(p.start..p.start.saturating_add(p.len)).map(|b| String::from_utf8_lossy(b).into_owned()).unwrap_or_default()
}

fn entry(path: String, p: Part, kind: &str) -> PackedEntry {
    let len = p.len as u64;
    PackedEntry { path, offset: p.start as u64, stored_size: len, size: Some(len), compression: Compression::None, kind: Some(kind.to_string()) }
}

/// Whether the fuse in the program around the blob says a blob was injected.
fn fuse_state(data: &[u8], blob: Span) -> Option<bool> {
    let before = data.get(..blob.start)?;
    let after = data.get(blob.start.checked_add(blob.len)?..)?;
    [before, after].iter().find_map(|part| {
        let at = find_bytes(part, FUSE, part.len())?;
        match part.get(at.checked_add(FUSE.len())?)? {
            b'0' => Some(false),
            b'1' => Some(true),
            _ => None,
        }
    })
}

impl PackedFormat for NodeSea {
    fn id(&self) -> &'static str {
        "node_sea"
    }

    fn title(&self) -> &'static str {
        "Node.js single executable"
    }

    fn detect(&self, data: &[u8]) -> bool {
        locate(data).is_some()
    }

    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError> {
        let (span, carrier) = locate(data).ok_or_else(|| FormatError::Malformed("no Node blob section, note or resource holding its magic number".into()))?;
        let blob = span.bytes(data).ok_or_else(|| FormatError::Truncated("the Node blob".into()))?;
        let p = parse_blob(blob, span.start)?;
        let code_path = p.code_path.map(|c| text(data, c));
        let snapshot = p.flags & FLAG_SNAPSHOT != 0;
        let mut entries = Vec::new();
        if snapshot {
            entries.push(entry("main/snapshot.blob".into(), p.code, "snapshot"));
        } else {
            // The stored path is often absolute; its last part is enough to name the file.
            let base = code_path.as_deref().and_then(|c| c.rsplit(['/', '\\']).next()).filter(|c| !c.is_empty() && *c != "..").unwrap_or("main.js");
            entries.push(entry(format!("main/{base}"), p.code, "main_script"));
        }
        if let Some(cache) = p.code_cache {
            entries.push(entry("main/code_cache.bin".into(), cache, "code_cache"));
        }
        let room = MAX_ENTRIES.saturating_sub(entries.len());
        for (key, value) in p.assets.iter().take(room) {
            entries.push(entry(format!("assets/{}", text(data, *key)), *value, "asset"));
        }
        let exec_argv: Vec<String> = p.exec_argv.iter().map(|a| text(data, *a)).collect();
        let mut notes = Vec::new();
        if snapshot {
            notes.push("The main program is a V8 startup snapshot, not source text; it's taken out as it is and isn't decoded.".to_string());
        }
        if p.code_cache.is_some() {
            notes.push("The code cache is V8's compiled form of the main script; it's taken out as it is and isn't decoded.".to_string());
        }
        if p.trailing_zeros > 0 {
            notes.push(format!("{} zero byte(s) follow the blob's last field, which a carrier's padding can add.", p.trailing_zeros));
        }
        if packed_carrier::sections(data, "__NODE_SEA_BLOB", &["NODE_SEA", "__NODE_SEA"]).len() > 1 {
            notes.push("This file holds more than one blob (a universal program has one per slice); this lists the first.".to_string());
        }
        let fuse_injected = if carrier == "bare_blob" { None } else { fuse_state(data, span) };
        let facts = json!({
            "carrier": carrier,
            "blob_offset": span.start,
            "blob_bytes": span.len,
            "layout": p.layout.label,
            "flags": p.flags,
            "experimental_warning_disabled": p.flags & FLAG_NO_WARNING != 0,
            "uses_snapshot": snapshot,
            "uses_code_cache": p.code_cache.is_some(),
            "exec_argv_extension": p.extension,
            "code_path": code_path,
            "assets": p.assets.len(),
            "exec_argv": exec_argv,
            "fuse_says_injected": fuse_injected,
        });
        Ok(PackedListing { facts, truncated: p.assets.len() > room, entries, notes })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packed;
    use craft_anything_testkit::packed::{self as kit, SeaBlob, sea_blob, sea_sample};

    fn check_sample(data: &[u8]) -> PackedListing {
        let l = NodeSea.list(data).unwrap();
        let paths: Vec<&str> = l.entries.iter().map(|e| e.path.as_str()).collect();
        assert_eq!(paths, ["main/hello.js", "main/code_cache.bin", "assets/a.txt", "assets/dir/b.bin"]);
        assert_eq!(NodeSea.read(data, &l.entries[0], 100).unwrap(), b"console.log('sea')");
        assert_eq!(NodeSea.read(data, &l.entries[1], 100).unwrap(), b"cache");
        assert_eq!(NodeSea.read(data, &l.entries[3], 100).unwrap(), b"asset b");
        assert_eq!(l.entries[0].kind.as_deref(), Some("main_script"));
        assert_eq!(l.entries[2].kind.as_deref(), Some("asset"));
        assert_eq!(l.facts["code_path"], "/work/hello.js");
        assert_eq!(l.facts["exec_argv"][0], "--no-warnings");
        assert_eq!(l.facts["uses_code_cache"], true);
        assert_eq!(l.facts["experimental_warning_disabled"], true);
        assert_eq!(l.facts["layout"], "with_exec_argv_extension");
        assert!(!l.truncated);
        l
    }

    #[test]
    fn every_carrier_reads() {
        let blob = sea_sample();
        for (file, carrier) in [
            (blob.clone(), "bare_blob"),
            (kit::macho_section("NODE_SEA", "__NODE_SEA_BLOB", &blob), "macho_section"),
            (kit::macho_section("__NODE_SEA", "__NODE_SEA_BLOB", &blob), "macho_section"),
            (kit::macho_universal(&[kit::macho_section("NODE_SEA", "__NODE_SEA_BLOB", &blob)]), "macho_section"),
            (kit::elf_note("NODE_SEA_BLOB", &blob), "elf_note"),
            (kit::elf_section("NODE_SEA_BLOB", &blob), "elf_section"),
            (kit::pe_rcdata("NODE_SEA_BLOB", &blob), "pe_resource"),
        ] {
            assert!(NodeSea.detect(&file), "{carrier}");
            assert_eq!(check_sample(&file).facts["carrier"], carrier);
        }
    }

    #[test]
    fn a_blob_written_by_node_24_reads() {
        // The bytes `node --experimental-sea-config` wrote, for a config with two assets and an argument.
        let mut b = vec![0x20, 0xda, 0x43, 0x01, 0x19, 0, 0, 0, 1];
        let string = |b: &mut Vec<u8>, s: &[u8]| {
            b.extend((s.len() as u64).to_le_bytes());
            b.extend(s);
        };
        string(&mut b, b"hello.js");
        string(&mut b, b"console.log(\"hello sea\");\n");
        b.extend(2u64.to_le_bytes());
        string(&mut b, b"a1.txt");
        string(&mut b, b"asset one");
        string(&mut b, b"dir/b.txt");
        string(&mut b, b"console.log(\"hello sea\");\n");
        b.extend(1u64.to_le_bytes());
        string(&mut b, b"--no-warnings");
        let l = NodeSea.list(&b).unwrap();
        assert_eq!(l.entries.len(), 3);
        assert_eq!(l.entries[1].path, "assets/a1.txt");
        assert_eq!(l.facts["exec_argv_extension"], 1);
    }

    #[test]
    fn the_older_layouts_read() {
        let plain = SeaBlob { code_path: "app.js", code: b"code", ..Default::default() };
        let two = NodeSea.list(&sea_blob(&plain, 2)).unwrap();
        assert_eq!(two.facts["layout"], "with_code_path");
        assert_eq!(two.entries[0].path, "main/app.js");
        let one = NodeSea.list(&sea_blob(&plain, 1)).unwrap();
        assert_eq!(one.facts["layout"], "code_only");
        assert_eq!(one.entries[0].path, "main/main.js");
        assert_eq!(NodeSea.read(&sea_blob(&plain, 1), &one.entries[0], 100).unwrap(), b"code");
    }

    #[test]
    fn a_snapshot_is_named_and_noted() {
        let blob = sea_blob(&SeaBlob { code_path: "app.js", code: b"snapshot bytes", snapshot: true, ..Default::default() }, 3);
        let l = NodeSea.list(&blob).unwrap();
        assert_eq!(l.entries[0].kind.as_deref(), Some("snapshot"));
        assert_eq!(l.entries[0].path, "main/snapshot.blob");
        assert!(l.notes.iter().any(|n| n.contains("snapshot")));
    }

    #[test]
    fn padding_is_allowed_and_said_but_other_trailing_bytes_are_refused() {
        let mut padded = sea_sample();
        padded.extend([0u8; 12]);
        let l = NodeSea.list(&padded).unwrap();
        assert!(l.notes.iter().any(|n| n.contains("12 zero")));
        let mut extra = sea_sample();
        extra.extend(b"more");
        assert!(matches!(NodeSea.list(&extra), Err(FormatError::Unsupported(_))));
    }

    #[test]
    fn unknown_flags_are_refused() {
        let mut blob = sea_sample();
        blob[7] = 0x80;
        assert!(matches!(NodeSea.list(&blob), Err(FormatError::Unsupported(why)) if why.contains("flags")));
    }

    #[test]
    fn a_node_program_without_a_blob_is_not_detected() {
        assert!(!NodeSea.detect(&kit::elf_section(".text", b"NODE_SEA_BLOB and the fuse text")));
        assert!(!NodeSea.detect(&kit::elf_note("NODE_SEA_BLOB", b"no magic here")));
        assert!(!NodeSea.detect(b"plain file"));
        assert!(!NodeSea.detect(&kit::pe_rcdata("OTHER", &sea_sample())));
    }

    #[test]
    fn the_fuse_is_reported() {
        let blob = sea_sample();
        let mut file = kit::elf_note("NODE_SEA_BLOB", &blob);
        file.extend(FUSE);
        file.push(b'1');
        assert_eq!(NodeSea.list(&file).unwrap().facts["fuse_says_injected"], true);
        assert_eq!(NodeSea.list(&blob).unwrap().facts["fuse_says_injected"], serde_json::Value::Null);
    }

    #[test]
    fn hostile_asset_paths_stay_in_the_listing_for_the_writer_to_refuse() {
        let blob = sea_blob(&SeaBlob { code_path: "..", code: b"c", assets: &[("../../evil", b"x")], ..Default::default() }, 3);
        let l = NodeSea.list(&blob).unwrap();
        assert_eq!(l.entries[0].path, "main/main.js");
        assert_eq!(l.entries[1].path, "assets/../../evil");
    }

    #[test]
    fn truncation_at_every_length_never_panics() {
        let blob = sea_sample();
        for full in [
            blob.clone(),
            kit::elf_note("NODE_SEA_BLOB", &blob),
            kit::pe_rcdata("NODE_SEA_BLOB", &blob),
            kit::macho_section("NODE_SEA", "__NODE_SEA_BLOB", &blob),
        ] {
            for len in 0..full.len() {
                let d = &full[..len];
                let _ = NodeSea.detect(d);
                if let Ok(l) = NodeSea.list(d) {
                    for e in &l.entries {
                        let _ = NodeSea.read(d, e, 1000);
                    }
                }
            }
        }
    }

    #[test]
    fn corrupt_lengths_never_panic() {
        let blob = sea_sample();
        for at in 8..blob.len().saturating_sub(8) {
            for v in [u64::MAX, u64::MAX - 7, i64::MAX as u64, 1 << 40] {
                let mut d = blob.clone();
                d[at..at + 8].copy_from_slice(&v.to_le_bytes());
                if let Ok(l) = NodeSea.list(&d) {
                    for e in &l.entries {
                        let _ = NodeSea.read(&d, e, 1000);
                    }
                }
            }
        }
    }

    #[test]
    fn a_universal_file_says_it_lists_the_first_blob() {
        let slice = kit::macho_section("NODE_SEA", "__NODE_SEA_BLOB", &sea_sample());
        let l = NodeSea.list(&kit::macho_universal(&[slice.clone(), slice])).unwrap();
        assert!(l.notes.iter().any(|n| n.contains("more than one blob")));
    }

    #[test]
    fn a_read_stops_at_its_limit() {
        let blob = sea_sample();
        let l = NodeSea.list(&blob).unwrap();
        assert!(matches!(NodeSea.read(&blob, &l.entries[0], 3), Err(FormatError::TooLarge(_))));
    }

    #[test]
    fn it_is_the_reader_for_these_files() {
        assert_eq!(packed::detect(&sea_sample()).map(|r| r.id()), Some("node_sea"));
    }
}
