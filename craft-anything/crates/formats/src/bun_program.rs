//! Programs made with `bun build --compile`: a module graph inside the executable. The graph ends
//! in a fixed trailer, with an offsets block in front of it pointing at a table of modules.
//!
//! Bun doesn't record which layout it wrote and the layout has changed between versions, so a
//! layout is accepted only when exactly one known shape fits every record; anything else is an error
//! that says so.

use crate::bytes::Reader;
use crate::common::FormatError;
use crate::packed::{Compression, MAX_ENTRIES, PackedEntry, PackedFormat, PackedListing};
use crate::packed_carrier::{self, Span};
use serde_json::json;
use std::collections::BTreeMap;

const TRAILER: &[u8] = b"\n---- Bun! ----\n";
/// Bun's own names for the folder its modules appear in: the Unix form, then the Windows forms.
const VIRTUAL_ROOTS: &[&str] = &["/$bunfs/", "B:/~BUN/", "B:\\~BUN\\"];
/// Known sizes of a module record. 36: name, contents, source map, bytecode and four enum bytes;
/// 52 adds module info and the bytecode's origin path.
const RECORD_SIZES: &[usize] = &[52, 36];
/// Known sizes of the offsets block. 24: the older form with no exec-argv; 32: exec-argv and flags.
const OFFSETS_SIZES: &[usize] = &[32, 24];
/// Longest module name, and most name text one listing keeps: records can share one long string.
const MAX_NAME: u32 = 4096;
const MAX_NAME_TEXT: u64 = 64 << 20;
/// The numbered loaders we can name (Bun's own order). Others are shown as their number.
const LOADERS: &[&str] = &[
    "jsx",
    "js",
    "ts",
    "tsx",
    "css",
    "file",
    "json",
    "jsonc",
    "toml",
    "wasm",
    "napi",
    "base64",
    "dataurl",
    "text",
    "bunsh",
    "sqlite",
    "sqlite_embedded",
    "html",
    "yaml",
];

/// The reader.
pub struct BunProgram;

/// Where the graph sits and how we found it.
#[derive(Debug, Clone, Copy)]
struct Graph {
    /// First byte of the graph (the origin of every pointer in it), when the carrier states it.
    start: Option<usize>,
    /// Position just past the trailer.
    end: usize,
    carrier: &'static str,
}

fn carrier_sections(data: &[u8]) -> Vec<(Span, &'static str)> {
    let macho = packed_carrier::sections(data, "__bun", &["__BUN"]).into_iter().map(|s| (s, "macho_section"));
    let other = packed_carrier::sections(data, ".bun", &[]).into_iter().map(|s| {
        let label = if data.starts_with(b"MZ") { "pe_section" } else { "elf_section" };
        (s, label)
    });
    macho.chain(other).collect()
}

/// A section holds a length (8 bytes now, 4 in older builds) and then the graph, ending in the trailer.
fn graph_in_section(data: &[u8], s: Span, carrier: &'static str) -> Option<Graph> {
    let r = Reader::new(data);
    let declared = [(8usize, r.u64_le(s.start)), (4, r.u32_le(s.start).map(u64::from))];
    for (head, len) in declared {
        let Some(len) = len.and_then(|l| usize::try_from(l).ok()) else { continue };
        let Some(total) = head.checked_add(len).filter(|t| *t <= s.len) else { continue };
        let Some(end) = s.start.checked_add(total) else { continue };
        let Some(trailer_at) = end.checked_sub(TRAILER.len()) else { continue };
        if len >= TRAILER.len() && data.get(trailer_at..end) == Some(TRAILER) {
            return Some(Graph { start: Some(s.start + head), end, carrier });
        }
    }
    None
}

/// A graph on the very end of the file, or followed by the 8-byte footer some Linux builds add.
fn appended_end(data: &[u8]) -> Option<usize> {
    if data.ends_with(TRAILER) {
        return Some(data.len());
    }
    let cut = data.len().checked_sub(8)?;
    data.get(..cut)?.ends_with(TRAILER).then_some(cut)
}

/// A pointer into the graph: offset and length.
#[derive(Debug, Clone, Copy, Default)]
struct Ptr {
    off: u32,
    len: u32,
}

impl Ptr {
    fn at(r: &Reader<'_>, pos: usize) -> Option<Ptr> {
        Some(Ptr { off: r.u32_le(pos)?, len: r.u32_le(pos.checked_add(4)?)? })
    }

    /// Whether it lies inside `limit` bytes of graph.
    fn fits(&self, limit: u64) -> bool {
        u64::from(self.off) + u64::from(self.len) <= limit
    }

    fn bytes<'a>(&self, data: &'a [u8], start: usize) -> Option<&'a [u8]> {
        let from = start.checked_add(usize::try_from(self.off).ok()?)?;
        data.get(from..from.checked_add(usize::try_from(self.len).ok()?)?)
    }
}

#[derive(Debug, Clone, Copy)]
struct Offsets {
    byte_count: u64,
    modules: Ptr,
    entry_point: u32,
    exec_argv: Ptr,
    flags: Option<u32>,
    start: usize,
}

/// Read the offsets block, assuming it's `size` bytes long, and check it agrees with the carrier.
fn read_offsets(data: &[u8], g: &Graph, size: usize) -> Option<Offsets> {
    let r = Reader::new(data);
    let at = g.end.checked_sub(TRAILER.len())?.checked_sub(size)?;
    let byte_count = r.u64_le(at)?;
    let count = usize::try_from(byte_count).ok()?;
    let start = at.checked_sub(count)?;
    if g.start.is_some_and(|known| known != start) {
        return None;
    }
    let modules = Ptr::at(&r, at.checked_add(8)?)?;
    if !modules.fits(byte_count) {
        return None;
    }
    let entry_point = r.u32_le(at.checked_add(16)?)?;
    let (exec_argv, flags) = if size >= 32 { (Ptr::at(&r, at.checked_add(20)?)?, r.u32_le(at.checked_add(28)?)) } else { (Ptr::default(), None) };
    if !exec_argv.fits(byte_count) {
        return None;
    }
    Some(Offsets { byte_count, modules, entry_point, exec_argv, flags, start })
}

/// One module record.
#[derive(Debug, Clone)]
struct Module {
    name: String,
    contents: Ptr,
    sourcemap: Ptr,
    bytecode: Ptr,
    encoding: u8,
    loader: u8,
    format: u8,
    side: u8,
}

/// Read the table at this record size. `None` when any record doesn't fit that shape.
fn read_modules(data: &[u8], o: &Offsets, record: usize) -> Option<Vec<Module>> {
    let table = o.modules.bytes(data, o.start)?;
    if table.is_empty() || !table.len().is_multiple_of(record) {
        return None;
    }
    let tail_at = record.checked_sub(4)?;
    let mut out = Vec::new();
    let mut name_text = 0u64;
    for raw in table.chunks_exact(record).take(MAX_ENTRIES) {
        let r = Reader::new(raw);
        for i in 0..tail_at / 8 {
            if !Ptr::at(&r, i * 8)?.fits(o.byte_count) {
                return None;
            }
        }
        let name = Ptr::at(&r, 0)?;
        name_text += u64::from(name.len);
        if name.len == 0 || name.len > MAX_NAME || name_text > MAX_NAME_TEXT {
            return None;
        }
        let name = std::str::from_utf8(name.bytes(data, o.start)?).ok()?;
        if name.chars().any(char::is_control) {
            return None;
        }
        let [encoding, loader, format, side] = *raw.get(tail_at..)? else { return None };
        if encoding > 2 || format > 2 || side > 1 {
            return None;
        }
        out.push(Module {
            name: name.to_string(),
            contents: Ptr::at(&r, 8)?,
            sourcemap: Ptr::at(&r, 16)?,
            bytecode: Ptr::at(&r, 24)?,
            encoding,
            loader,
            format,
            side,
        });
    }
    Some(out)
}

fn label(names: &[&'static str], v: u8) -> String {
    names.get(usize::from(v)).map_or_else(|| v.to_string(), |s| (*s).to_string())
}

/// The module's path without Bun's virtual folder, so it can be taken out into a real one.
fn inner_path(name: &str) -> String {
    VIRTUAL_ROOTS.iter().find_map(|root| name.strip_prefix(root)).unwrap_or(name).to_string()
}

fn unrecognised(what: &str) -> FormatError {
    FormatError::Unsupported(format!("a Bun module graph, but {what}; its layout isn't one we know, and we won't guess at it"))
}

fn locate(data: &[u8]) -> Result<Graph, FormatError> {
    let sections = carrier_sections(data);
    for (s, carrier) in &sections {
        if let Some(g) = graph_in_section(data, *s, carrier) {
            return Ok(g);
        }
    }
    if !sections.is_empty() {
        return Err(unrecognised("the section holding it doesn't end in the trailer after its stated length"));
    }
    match appended_end(data) {
        Some(end) => Ok(Graph { start: None, end, carrier: "appended" }),
        None => Err(FormatError::Malformed("no Bun section and no trailer at the end of the file".into())),
    }
}

impl PackedFormat for BunProgram {
    fn id(&self) -> &'static str {
        "bun_program"
    }

    fn title(&self) -> &'static str {
        "Bun program"
    }

    fn detect(&self, data: &[u8]) -> bool {
        if appended_end(data).is_some() {
            return true;
        }
        // Bun's runtime carries an empty section of this name, so a stated length must be there too.
        carrier_sections(data).iter().any(|(s, _)| Reader::new(data).u32_le(s.start).is_some_and(|n| n != 0))
    }

    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError> {
        let g = locate(data)?;
        let candidates: Vec<(usize, Offsets)> = OFFSETS_SIZES.iter().filter_map(|size| read_offsets(data, &g, *size).map(|o| (*size, o))).collect();
        if candidates.is_empty() {
            return Err(unrecognised("no known offsets block fits in front of its trailer"));
        }
        let mut fits = Vec::new();
        for (size, o) in &candidates {
            for record in RECORD_SIZES {
                if let Some(modules) = read_modules(data, o, *record) {
                    fits.push((*size, *o, *record, modules));
                }
            }
        }
        if fits.len() > 1 {
            return Err(unrecognised("more than one known shape fits its module table"));
        }
        let Some((offsets_size, o, record, modules)) = fits.pop() else {
            return Err(unrecognised("no known record shape fits its module table"));
        };
        let total = usize::try_from(o.modules.len).unwrap_or(usize::MAX) / record;
        let graph_start = o.start as u64;
        let mut loaders: BTreeMap<String, usize> = BTreeMap::new();
        let (mut with_map, mut with_code) = (0usize, 0usize);
        let mut entries = Vec::with_capacity(modules.len());
        for m in &modules {
            let loader = label(LOADERS, m.loader);
            *loaders.entry(loader.clone()).or_default() += 1;
            with_map += usize::from(m.sourcemap.len > 0);
            with_code += usize::from(m.bytecode.len > 0);
            let kind = format!(
                "loader={loader} format={} encoding={} side={} sourcemap_bytes={} bytecode_bytes={}",
                label(&["none", "esm", "cjs"], m.format),
                label(&["binary", "latin1", "utf16le"], m.encoding),
                label(&["server", "client"], m.side),
                m.sourcemap.len,
                m.bytecode.len,
            );
            let size = u64::from(m.contents.len);
            entries.push(PackedEntry {
                path: inner_path(&m.name),
                offset: graph_start.saturating_add(u64::from(m.contents.off)),
                stored_size: size,
                size: Some(size),
                compression: Compression::None,
                kind: Some(kind),
            });
        }
        let entry_point = usize::try_from(o.entry_point).ok().and_then(|i| modules.get(i)).map(|m| inner_path(&m.name));
        let exec_argv = o.exec_argv.bytes(data, o.start).map(|b| String::from_utf8_lossy(b).into_owned()).filter(|s| !s.is_empty());
        let mut notes = Vec::new();
        if entry_point.is_none() {
            notes.push(format!("The graph names module {} as its entry point, which isn't in its table.", o.entry_point));
        }
        if with_map + with_code > 0 {
            notes.push(format!(
                "{with_map} module(s) carry a source map and {with_code} carry bytecode; each member's kind gives the sizes. They're Bun's own stored forms and aren't taken out as files."
            ));
        }
        if carrier_sections(data).len() > 1 {
            notes.push("This file holds more than one graph (a universal program has one per slice); this lists the first.".to_string());
        }
        if with_code > 0 {
            notes.push("A module with bytecode may run from it rather than from its text; the bytecode isn't decoded here.".to_string());
        }
        let facts = json!({
            "carrier": g.carrier,
            "graph_offset": graph_start,
            "graph_bytes": o.byte_count,
            "record_bytes": record,
            "offsets_block_bytes": offsets_size,
            "modules": total,
            "entry_point": entry_point,
            "exec_argv": exec_argv,
            "flags": o.flags,
            "loaders": loaders,
            "modules_with_sourcemap": with_map,
            "modules_with_bytecode": with_code,
        });
        Ok(PackedListing { facts, truncated: total > entries.len(), entries, notes })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packed;
    use craft_anything_testkit::packed::{self as kit, BunModule, bun_appended, bun_graph, bun_module, bun_sample, bun_section_payload};

    fn check_sample(data: &[u8]) -> PackedListing {
        let listing = BunProgram.list(data).unwrap();
        assert_eq!(listing.entries.len(), 2);
        let app = &listing.entries[0];
        assert_eq!(app.path, "root/app.js");
        assert_eq!(BunProgram.read(data, app, 1000).unwrap(), b"console.log('app')");
        assert_eq!(app.kind.as_deref(), Some("loader=js format=esm encoding=latin1 side=server sourcemap_bytes=9 bytecode_bytes=10"));
        let logo = &listing.entries[1];
        assert_eq!(logo.path, "root/logo.png");
        assert_eq!(BunProgram.read(data, logo, 1000).unwrap(), b"\x89PNG");
        assert_eq!(logo.kind.as_deref(), Some("loader=file format=none encoding=binary side=client sourcemap_bytes=0 bytecode_bytes=0"));
        assert_eq!(listing.facts["entry_point"], "root/app.js");
        assert_eq!(listing.facts["exec_argv"], "--smol");
        assert_eq!(listing.facts["flags"], 7);
        assert_eq!(listing.facts["modules_with_sourcemap"], 1);
        assert_eq!(listing.facts["loaders"]["js"], 1);
        assert!(!listing.truncated);
        listing
    }

    #[test]
    fn every_carrier_reads() {
        let payload = bun_section_payload(&bun_sample());
        for (file, carrier) in [
            (kit::macho_section("__BUN", "__bun", &payload), "macho_section"),
            (kit::macho_universal(&[kit::macho_section("__BUN", "__bun", &payload)]), "macho_section"),
            (kit::elf_section(".bun", &payload), "elf_section"),
            (kit::pe_section(".bun", &payload), "pe_section"),
            (bun_appended(&bun_sample()), "appended"),
        ] {
            assert!(BunProgram.detect(&file), "{carrier}");
            assert_eq!(check_sample(&file).facts["carrier"], carrier);
        }
    }

    #[test]
    fn an_appended_graph_with_a_footer_reads() {
        let mut file = bun_appended(&bun_sample());
        let total = file.len() as u64;
        file.extend(total.to_le_bytes());
        assert!(BunProgram.detect(&file));
        check_sample(&file);
    }

    #[test]
    fn a_section_with_a_short_length_and_padding_reads() {
        // A section padded past the graph, as PE file alignment does, and a 4-byte length.
        let graph = bun_sample();
        let mut payload = (graph.len() as u32).to_le_bytes().to_vec();
        payload.extend(&graph);
        payload.resize(payload.len() + 300, 0);
        check_sample(&kit::pe_section(".bun", &payload));
    }

    #[test]
    fn the_older_layouts_read() {
        let modules = [bun_module("/$bunfs/root/a.js", b"aaa")];
        for (record, offsets) in [(36, 32), (36, 24), (52, 24)] {
            let graph = bun_graph(&modules, 0, "", record, offsets);
            let listing = BunProgram.list(&bun_appended(&graph)).unwrap();
            assert_eq!(listing.facts["record_bytes"], record);
            assert_eq!(listing.facts["offsets_block_bytes"], offsets);
            assert_eq!(listing.entries[0].path, "root/a.js");
        }
    }

    #[test]
    fn a_table_that_divides_by_both_sizes_picks_the_shape_that_fits() {
        // 9 records of 52 bytes is also exactly 13 of 36.
        let names: Vec<String> = (0..9).map(|i| format!("/$bunfs/root/m{i}.js")).collect();
        let modules: Vec<BunModule<'_>> = names.iter().map(|n| bun_module(n, b"x")).collect();
        let listing = BunProgram.list(&bun_appended(&bun_graph(&modules, 8, "", 52, 32))).unwrap();
        assert_eq!(listing.facts["record_bytes"], 52);
        assert_eq!(listing.entries.len(), 9);
        assert_eq!(listing.facts["entry_point"], "root/m8.js");
    }

    #[test]
    fn windows_names_and_unknown_loaders_are_handled() {
        let modules = [BunModule { loader: 200, ..bun_module("B:\\~BUN\\root\\a.js", b"aaa") }];
        let listing = BunProgram.list(&bun_appended(&bun_graph(&modules, 0, "", 52, 32))).unwrap();
        assert_eq!(listing.entries[0].path, "root\\a.js");
        assert!(listing.entries[0].kind.as_deref().unwrap().starts_with("loader=200 "));
    }

    #[test]
    fn unknown_shapes_are_refused_with_a_clear_error() {
        // A record size nothing fits: 40 bytes per record.
        let mut graph = b"/$bunfs/root/a.js\0".to_vec();
        let table_at = graph.len() as u32;
        graph.extend(0u32.to_le_bytes());
        graph.extend(17u32.to_le_bytes());
        graph.extend([0u8; 36]);
        let count = graph.len() as u64;
        graph.extend(count.to_le_bytes());
        graph.extend(table_at.to_le_bytes());
        graph.extend(40u32.to_le_bytes());
        graph.extend([0u8; 12]);
        graph.extend(TRAILER);
        match BunProgram.list(&graph) {
            Err(FormatError::Unsupported(why)) => assert!(why.contains("won't guess"), "{why}"),
            other => panic!("expected a refusal, got {other:?}"),
        }
        // A module with an enum value outside any known set.
        let m = [BunModule { encoding: 9, ..bun_module("/$bunfs/a", b"x") }];
        assert!(matches!(BunProgram.list(&bun_appended(&bun_graph(&m, 0, "", 52, 32))), Err(FormatError::Unsupported(_))));
        // A section whose length doesn't lead to a trailer.
        let elf = kit::elf_section(".bun", &bun_section_payload(b"not a graph at all"));
        assert!(matches!(BunProgram.list(&elf), Err(FormatError::Unsupported(_))));
    }

    #[test]
    fn the_runtime_without_a_graph_is_not_detected() {
        let elf = kit::elf_section(".bun", &[0u8; 64]);
        assert!(!BunProgram.detect(&elf));
        assert!(!BunProgram.detect(b"plain file"));
        assert!(!BunProgram.detect(b"code quoting the trailer \n---- Bun! ----\n and carrying on"));
    }

    #[test]
    fn truncation_at_every_length_never_panics() {
        let appended = bun_appended(&bun_sample());
        let section = kit::macho_section("__BUN", "__bun", &bun_section_payload(&bun_sample()));
        for full in [&appended, &section] {
            for len in 0..full.len() {
                let d = &full[..len];
                let _ = BunProgram.detect(d);
                if let Ok(l) = BunProgram.list(d) {
                    for e in &l.entries {
                        let _ = BunProgram.read(d, e, 1000);
                    }
                }
            }
        }
    }

    #[test]
    fn corrupt_lengths_and_offsets_never_panic() {
        let full = bun_appended(&bun_sample());
        let block = full.len() - TRAILER.len() - 32;
        for at in (0..32).step_by(4) {
            for v in [u32::MAX, u32::MAX - 1, 0x8000_0000, 0] {
                let mut d = full.clone();
                d[block + at..block + at + 4].copy_from_slice(&v.to_le_bytes());
                let _ = BunProgram.list(&d);
            }
        }
        let mut huge = full.clone();
        huge[block..block + 8].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(BunProgram.list(&huge).is_err());
        // Every byte of every record.
        let table_len = 2 * 52;
        for at in 0..table_len {
            let mut d = full.clone();
            d[block - table_len + at] = 0xff;
            if let Ok(l) = BunProgram.list(&d) {
                for e in &l.entries {
                    let _ = BunProgram.read(&d, e, 1 << 20);
                }
            }
        }
    }

    #[test]
    fn a_universal_file_says_it_lists_the_first_graph() {
        let slice = kit::macho_section("__BUN", "__bun", &bun_section_payload(&bun_sample()));
        let l = BunProgram.list(&kit::macho_universal(&[slice.clone(), slice])).unwrap();
        assert!(l.notes.iter().any(|n| n.contains("more than one graph")));
    }

    #[test]
    fn records_sharing_a_huge_name_are_refused_before_copying_it() {
        let long = format!("/$bunfs/{}", "n".repeat(MAX_NAME as usize));
        let graph = bun_graph(&[bun_module(&long, b"x")], 0, "", 52, 32);
        assert!(matches!(BunProgram.list(&bun_appended(&graph)), Err(FormatError::Unsupported(_))));
    }

    #[test]
    fn a_read_stops_at_its_limit() {
        let data = bun_appended(&bun_sample());
        let listing = BunProgram.list(&data).unwrap();
        assert!(matches!(BunProgram.read(&data, &listing.entries[0], 3), Err(FormatError::TooLarge(_))));
    }

    #[test]
    fn it_is_the_reader_for_these_files() {
        assert_eq!(packed::detect(&bun_appended(&bun_sample())).map(|r| r.id()), Some("bun_program"));
        assert_eq!(packed::by_id("bun_program").map(|r| r.title()), Some("Bun program"));
    }
}
