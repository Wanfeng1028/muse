//! Flutter and Dart ahead-of-time (AOT) snapshots: a small little-endian ELF32/ELF64 reader for
//! the dynamic symbol table (from section headers, or from `PT_DYNAMIC` when the image has none),
//! GNU build ids, Dart snapshot headers (magic, length, kind, version hash, features), snapshot
//! hash scans, version and toolchain strings, and a byte-level scan of the isolate snapshot for
//! `package:`/`dart:` URIs and identifier tokens.
//!
//! The string pool is a byte scan, not a deserialisation of the snapshot's object clusters, and
//! no snapshot hash is ever mapped to an SDK version: a version is reported only when the binary
//! states it.

use crate::bytes::Reader;
use crate::{FormatError, hex_addr};
use serde::Serialize;
use std::collections::HashSet;

/// Dart snapshot magic (`0xdcdcf5f5` little-endian).
pub const SNAPSHOT_MAGIC: [u8; 4] = [0xf5, 0xf5, 0xdc, 0xdc];

/// The four symbols a Dart AOT library exports.
pub const DART_SYMBOLS: [(&str, &str); 4] = [
    ("_kDartVmSnapshotData", "vm-data"),
    ("_kDartVmSnapshotInstructions", "vm-instructions"),
    ("_kDartIsolateSnapshotData", "isolate-data"),
    ("_kDartIsolateSnapshotInstructions", "isolate-instructions"),
];

const MAX_PHDRS: usize = 4096;
const MAX_SYMBOL_SCAN: u64 = 4_000_000;
const MAX_NAME: usize = 4096;
const MAX_REGION: usize = 64 << 20;

const PT_LOAD: u32 = 1;
const PT_NOTE: u32 = 4;
const SHT_DYNSYM: u32 = 11;
const SHT_NOTE: u32 = 7;

/// One dynamic symbol of interest.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ElfSymbol {
    pub name: String,
    #[serde(with = "hex_addr")]
    pub value: u64,
    pub size: u64,
    /// Where the symbol's bytes start in the file, when a `PT_LOAD` maps it.
    pub file_offset: Option<u64>,
}

/// What the ELF reader found.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DartElf {
    pub bits: u8,
    pub machine: u16,
    pub architecture: &'static str,
    pub has_section_headers: bool,
    /// `section-headers`, `dynamic-segment` or `none`.
    pub symbol_source: &'static str,
    /// How the symbol count was established: `section-size`, `DT_HASH`, `DT_GNU_HASH`, `estimated` or `none`.
    pub symbol_count_source: &'static str,
    pub dynamic_symbol_count: u64,
    /// The `_kDart*` symbols that were found.
    pub dart_symbols: Vec<ElfSymbol>,
    pub build_id: Option<String>,
    pub warnings: Vec<String>,
}

/// A Dart snapshot header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SnapshotHeader {
    pub offset: u64,
    /// The length field as stored.
    pub length: u64,
    pub kind: u64,
    /// full, full-core, full-jit, full-aot, none, invalid or unknown (Dart 2.14+ numbering).
    pub kind_name: &'static str,
    pub hash: Option<String>,
    pub features: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DartSnapshot {
    pub symbol: String,
    pub role: &'static str,
    pub present: bool,
    pub symbol_info: Option<ElfSymbol>,
    pub header: Option<SnapshotHeader>,
}

/// URIs and identifier-like tokens seen in the isolate snapshot bytes.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct StringPool {
    pub uris: Vec<String>,
    pub tokens: Vec<String>,
    pub uris_truncated: bool,
    pub tokens_truncated: bool,
    pub scanned_bytes: u64,
}

/// The result of reading a Dart AOT library (`libapp.so`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DartAot {
    pub elf: DartElf,
    pub snapshots: Vec<DartSnapshot>,
    /// True when all four symbols resolve, both data headers are FullAOT and their hashes agree.
    pub complete: bool,
    pub snapshot_hash: Option<String>,
    pub features: Option<String>,
    pub string_pool: StringPool,
    /// Dart versions the binary states about itself.
    pub dart_versions: Vec<String>,
    pub warnings: Vec<String>,
}

/// Facts about one library (libapp.so or libflutter.so) for build identification.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct LibraryScan {
    /// Distinct version hashes found after snapshot magics, in order of first appearance.
    pub snapshot_hashes: Vec<String>,
    pub snapshot_occurrences: u64,
    pub hashes_truncated: bool,
    pub dart_versions: Vec<String>,
    pub toolchains: Vec<String>,
    pub build_id: Option<String>,
}

#[derive(Debug, Clone, Copy)]
struct Ph {
    ty: u32,
    offset: u64,
    vaddr: u64,
    filesz: u64,
}

#[derive(Debug, Clone, Copy)]
struct Sh {
    ty: u32,
    offset: u64,
    size: u64,
    link: u32,
    entsize: u64,
}

struct Elf<'a> {
    r: Reader<'a>,
    is64: bool,
    phdrs: Vec<Ph>,
    shdrs: Vec<Sh>,
}

fn arch_name(machine: u16) -> &'static str {
    match machine {
        3 => "x86",
        40 => "arm",
        62 => "x86_64",
        183 => "arm64",
        243 => "riscv",
        _ => "unknown",
    }
}

fn to_usize(v: u64) -> Option<usize> {
    usize::try_from(v).ok()
}

impl<'a> Elf<'a> {
    fn parse(data: &'a [u8]) -> Result<Elf<'a>, FormatError> {
        let r = Reader::new(data);
        if r.slice(0, 4) != Some(b"\x7fELF") {
            return Err(FormatError::Malformed("not an ELF file".into()));
        }
        let is64 = match r.u8(4) {
            Some(1) => false,
            Some(2) => true,
            _ => return Err(FormatError::Malformed("unknown ELF class".into())),
        };
        if r.u8(5) != Some(1) {
            return Err(FormatError::Unsupported("big-endian ELF (Flutter libraries are little-endian)".into()));
        }
        let t = || FormatError::Truncated("ELF header".into());
        let (phoff, shoff, phentsize, phnum, shentsize, shnum) = if is64 {
            (
                r.u64_le(32).ok_or_else(t)?,
                r.u64_le(40).ok_or_else(t)?,
                r.u16_le(54).ok_or_else(t)?,
                r.u16_le(56).ok_or_else(t)?,
                r.u16_le(58).ok_or_else(t)?,
                r.u16_le(60).ok_or_else(t)?,
            )
        } else {
            (
                u64::from(r.u32_le(28).ok_or_else(t)?),
                u64::from(r.u32_le(32).ok_or_else(t)?),
                r.u16_le(42).ok_or_else(t)?,
                r.u16_le(44).ok_or_else(t)?,
                r.u16_le(46).ok_or_else(t)?,
                r.u16_le(48).ok_or_else(t)?,
            )
        };
        let mut phdrs = Vec::new();
        let want_ph = if is64 { 56 } else { 32 };
        if phnum > 0 && usize::from(phentsize) >= want_ph {
            for i in 0..usize::from(phnum).min(MAX_PHDRS) {
                // An entry that starts past the end can't be read, and its field offsets (`o + 32`) could overflow.
                let Some(o) = to_usize(phoff).and_then(|p| p.checked_add(i.checked_mul(usize::from(phentsize))?)).filter(|&o| o < data.len()) else { break };
                let ph = if is64 {
                    (r.u32_le(o), r.u64_le(o + 8), r.u64_le(o + 16), r.u64_le(o + 32))
                } else {
                    (r.u32_le(o), r.u32_le(o + 4).map(u64::from), r.u32_le(o + 8).map(u64::from), r.u32_le(o + 16).map(u64::from))
                };
                let (Some(ty), Some(offset), Some(vaddr), Some(filesz)) = ph else { break };
                phdrs.push(Ph { ty, offset, vaddr, filesz });
            }
        }
        let mut shdrs = Vec::new();
        let want_sh = if is64 { 64 } else { 40 };
        if shnum > 0 && shoff != 0 && usize::from(shentsize) >= want_sh {
            for i in 0..usize::from(shnum) {
                let Some(o) = to_usize(shoff).and_then(|p| p.checked_add(i.checked_mul(usize::from(shentsize))?)).filter(|&o| o < data.len()) else { break };
                let sh = if is64 {
                    (r.u32_le(o + 4), r.u64_le(o + 24), r.u64_le(o + 32), r.u32_le(o + 40), r.u64_le(o + 56))
                } else {
                    (r.u32_le(o + 4), r.u32_le(o + 16).map(u64::from), r.u32_le(o + 20).map(u64::from), r.u32_le(o + 24), r.u32_le(o + 36).map(u64::from))
                };
                let (Some(ty), Some(offset), Some(size), Some(link), Some(entsize)) = sh else { break };
                shdrs.push(Sh { ty, offset, size, link, entsize });
            }
        }
        Ok(Elf { r, is64, phdrs, shdrs })
    }

    fn va_to_off(&self, va: u64) -> Option<u64> {
        self.phdrs.iter().filter(|p| p.ty == PT_LOAD).find_map(|p| {
            let rel = va.checked_sub(p.vaddr)?;
            if rel < p.filesz { p.offset.checked_add(rel) } else { None }
        })
    }

    fn sym_size(&self) -> u64 {
        if self.is64 { 24 } else { 16 }
    }

    /// (name offset, value, size, shndx) of symbol `i` in a table at `off`.
    fn sym(&self, off: u64, i: u64) -> Option<(u32, u64, u64, u16)> {
        let o = to_usize(off.checked_add(i.checked_mul(self.sym_size())?)?)?;
        let r = self.r;
        if self.is64 {
            Some((r.u32_le(o)?, r.u64_le(o.checked_add(8)?)?, r.u64_le(o.checked_add(16)?)?, r.u16_le(o.checked_add(6)?)?))
        } else {
            Some((r.u32_le(o)?, u64::from(r.u32_le(o.checked_add(4)?)?), u64::from(r.u32_le(o.checked_add(8)?)?), r.u16_le(o.checked_add(14)?)?))
        }
    }

    fn name_at(&self, strtab: u64, strsz: u64, name: u32) -> Option<String> {
        if u64::from(name) >= strsz {
            return None;
        }
        let o = to_usize(strtab.checked_add(u64::from(name))?)?;
        let max = to_usize(strsz - u64::from(name)).unwrap_or(MAX_NAME).min(MAX_NAME);
        self.r.cstr(o, max)
    }

    fn notes(&self, off: u64, size: u64, out: &mut Option<String>) {
        let mut pos = 0u64;
        let r = self.r;
        while pos.saturating_add(12) <= size {
            let Some(o) = off.checked_add(pos).and_then(to_usize) else { return };
            let (Some(namesz), Some(descsz), Some(ty)) = (r.u32_le(o), r.u32_le(o.saturating_add(4)), r.u32_le(o.saturating_add(8))) else { return };
            let name_pad = (u64::from(namesz) + 3) & !3;
            let desc_pad = (u64::from(descsz) + 3) & !3;
            let name = r.slice(o.saturating_add(12), namesz as usize);
            let desc_off = 12u64.saturating_add(name_pad);
            if ty == 3
                && name == Some(b"GNU\0")
                && (1..=64).contains(&descsz)
                && let Some(d) = to_usize(off.saturating_add(pos).saturating_add(desc_off)).and_then(|d| r.slice(d, descsz as usize))
            {
                *out = Some(d.iter().map(|b| format!("{b:02x}")).collect());
                return;
            }
            let next = desc_off.saturating_add(desc_pad);
            pos = pos.saturating_add(next);
        }
    }

    fn build_id(&self) -> Option<String> {
        let mut out = None;
        for p in self.phdrs.iter().filter(|p| p.ty == PT_NOTE) {
            self.notes(p.offset, p.filesz.min(1 << 20), &mut out);
            if out.is_some() {
                return out;
            }
        }
        for s in self.shdrs.iter().filter(|s| s.ty == SHT_NOTE) {
            self.notes(s.offset, s.size.min(1 << 20), &mut out);
            if out.is_some() {
                return out;
            }
        }
        None
    }
}

/// Read the dynamic symbol table and build id of a little-endian ELF, keeping the `_kDart*` symbols.
pub fn parse_elf(data: &[u8]) -> Result<DartElf, FormatError> {
    let elf = Elf::parse(data)?;
    let r = elf.r;
    let machine = r.u16_le(18).unwrap_or(0);
    let mut warnings = Vec::new();
    // (symtab offset, count, strtab offset, strtab size)
    let mut table: Option<(u64, u64, u64, u64)> = None;
    let mut symbol_source = "none";
    let mut count_source = "none";
    if let Some(ds) = elf.shdrs.iter().find(|s| s.ty == SHT_DYNSYM) {
        let ent = if ds.entsize == 0 { elf.sym_size() } else { ds.entsize };
        if ent == elf.sym_size() {
            if let Some(st) = usize::try_from(ds.link).ok().and_then(|l| elf.shdrs.get(l)) {
                table = Some((ds.offset, ds.size / ent, st.offset, st.size));
                symbol_source = "section-headers";
                count_source = "section-size";
            } else {
                warnings.push("the dynamic symbol section links to a missing string table".into());
            }
        } else {
            warnings.push(format!("unexpected dynamic symbol entry size {}", ds.entsize));
        }
    }
    if table.is_none() {
        let scan = crate::elf::dynamic_table(data);
        warnings.extend(scan.warnings);
        if let Some(t) = scan.table {
            table = Some((t.symtab, t.count, t.strtab, t.strsz));
            symbol_source = "dynamic-segment";
            count_source = t.count_source;
        }
    }
    let mut dart_symbols = Vec::new();
    let mut total = 0u64;
    if let Some((symtab, count, strtab, strsz)) = table {
        if count > MAX_SYMBOL_SCAN {
            warnings.push(format!("{count} symbols declared; only the first {MAX_SYMBOL_SCAN} were read"));
        }
        for i in 0..count.min(MAX_SYMBOL_SCAN) {
            let Some((name, value, size, shndx)) = elf.sym(symtab, i) else {
                warnings.push(format!("the symbol table ends early at entry {i}"));
                break;
            };
            total += 1;
            if shndx == 0 {
                continue;
            }
            // A missing DT_STRSZ leaves the string table unbounded (names are still capped).
            let strsz = if strsz == 0 { u64::MAX.saturating_sub(strtab) } else { strsz };
            let Some(n) = elf.name_at(strtab, strsz, name) else { continue };
            if DART_SYMBOLS.iter().any(|(s, _)| *s == n) && !dart_symbols.iter().any(|d: &ElfSymbol| d.name == n) {
                dart_symbols.push(ElfSymbol { name: n, value, size, file_offset: elf.va_to_off(value) });
            }
        }
    }
    Ok(DartElf {
        bits: if elf.is64 { 64 } else { 32 },
        machine,
        architecture: arch_name(machine),
        has_section_headers: !elf.shdrs.is_empty(),
        symbol_source,
        symbol_count_source: count_source,
        dynamic_symbol_count: total,
        dart_symbols,
        build_id: elf.build_id(),
        warnings,
    })
}

fn kind_name(kind: u64) -> &'static str {
    match kind {
        0 => "full",
        1 => "full-core",
        2 => "full-jit",
        3 => "full-aot",
        4 => "none",
        5 => "invalid",
        _ => "unknown",
    }
}

fn hash_at(data: &[u8], off: usize) -> Option<String> {
    let h = Reader::new(data).slice(off, 32)?;
    if h.iter().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b)) { Some(String::from_utf8_lossy(h).into_owned()) } else { None }
}

/// Read a snapshot header at `off` (needs the magic there).
pub fn snapshot_header(data: &[u8], off: usize) -> Option<SnapshotHeader> {
    let r = Reader::new(data);
    if r.slice(off, 4)? != SNAPSHOT_MAGIC {
        return None;
    }
    let length = r.u64_le(off.checked_add(4)?)?;
    let kind = r.u64_le(off.checked_add(12)?)?;
    let hash = hash_at(data, off.checked_add(20)?);
    let features =
        off.checked_add(52).and_then(|f| r.cstr(f, 1024)).filter(|s| !s.is_empty() && s.chars().all(|c| c.is_ascii_graphic() || c == ' ') && hash.is_some());
    Some(SnapshotHeader { offset: off as u64, length, kind, kind_name: kind_name(kind), hash, features })
}

/// Every offset where the snapshot magic appears.
fn magic_offsets(data: &[u8], max: usize) -> Vec<usize> {
    let mut out = Vec::new();
    let mut i = 0usize;
    while out.len() < max {
        let Some(p) = data.get(i..).and_then(|d| d.iter().position(|&b| b == 0xf5)) else { break };
        let at = i.saturating_add(p);
        if data.get(at..at.saturating_add(4)) == Some(&SNAPSHOT_MAGIC[..]) {
            out.push(at);
        }
        i = at.saturating_add(1);
    }
    out
}

fn is_text(b: u8) -> bool {
    (0x20..0x7f).contains(&b)
}

/// Printable strings that contain `tag`; with `after_tag`, only the text after the tag.
fn tagged_strings(data: &[u8], tag: &[u8], after_tag: bool, max: usize) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut i = 0usize;
    let mut hits = 0usize;
    while out.len() < max && hits < 10_000 {
        let Some(at) = data.get(i..).and_then(|d| crate::find_bytes(d, tag, d.len())).map(|p| p.saturating_add(i)) else { break };
        hits += 1;
        let mut start = at;
        if !after_tag {
            while start > 0 && at - start < 512 && data.get(start - 1).copied().is_some_and(is_text) {
                start -= 1;
            }
        } else {
            start = at.saturating_add(tag.len());
        }
        let mut end = at.saturating_add(tag.len());
        while end.saturating_sub(start) < 1024 && data.get(end).copied().is_some_and(is_text) {
            end += 1;
        }
        if let Some(s) = data.get(start..end) {
            let s = String::from_utf8_lossy(s).trim().to_string();
            if !s.is_empty() && !out.contains(&s) {
                out.push(s);
            }
        }
        i = end.max(at.saturating_add(1));
    }
    out
}

/// Scan one library for snapshot hashes, Dart version strings, toolchain strings and its build id.
pub fn scan_library(data: &[u8], max_candidates: usize) -> LibraryScan {
    let mut out = LibraryScan::default();
    for off in magic_offsets(data, 100_000) {
        out.snapshot_occurrences += 1;
        if let Some(h) = off.checked_add(20).and_then(|o| hash_at(data, o))
            && !out.snapshot_hashes.contains(&h)
        {
            if out.snapshot_hashes.len() >= max_candidates {
                out.hashes_truncated = true;
            } else {
                out.snapshot_hashes.push(h);
            }
        }
    }
    out.dart_versions = tagged_strings(data, b"Dart VM version:", true, 16);
    out.toolchains = tagged_strings(data, b"clang version", false, 16);
    out.build_id = parse_elf(data).ok().and_then(|e| e.build_id);
    out
}

fn uri_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'/' | b'-' | b':' | b'$' | b'+')
}

/// Scan bytes for `package:`/`dart:` URIs and identifier tokens.
pub fn string_pool(data: &[u8], max_uris: usize, max_tokens: usize) -> StringPool {
    let mut pool = StringPool { scanned_bytes: data.len() as u64, ..StringPool::default() };
    let mut seen_uri = HashSet::new();
    let mut seen_tok = HashSet::new();
    let mut i = 0usize;
    let n = data.len();
    while i < n {
        if !data.get(i).copied().is_some_and(is_text) {
            i += 1;
            continue;
        }
        let start = i;
        while i < n && data.get(i).copied().is_some_and(is_text) {
            i += 1;
        }
        let Some(run) = data.get(start..i) else { break };
        if run.len() < 3 {
            continue;
        }
        let mut has_uri = false;
        for prefix in [&b"package:"[..], &b"dart:"[..]] {
            let mut j = 0usize;
            while let Some(p) = run.get(j..).and_then(|r| crate::find_bytes(r, prefix, r.len())) {
                let at = j + p;
                let mut end = at + prefix.len();
                while end < run.len() && run.get(end).copied().is_some_and(uri_char) {
                    end += 1;
                }
                let body_ok = run.get(at + prefix.len()).is_some_and(|b| b.is_ascii_alphabetic() || *b == b'_');
                if body_ok && end - at <= 512 {
                    has_uri = true;
                    let u = String::from_utf8_lossy(run.get(at..end).unwrap_or_default()).into_owned();
                    if seen_uri.insert(u.clone()) {
                        if pool.uris.len() < max_uris {
                            pool.uris.push(u);
                        } else {
                            pool.uris_truncated = true;
                        }
                    }
                }
                j = end.max(at + 1);
            }
        }
        if has_uri {
            continue;
        }
        for tok in run.split(|b| !(b.is_ascii_alphanumeric() || *b == b'_' || *b == b'$')) {
            if !(3..=64).contains(&tok.len()) || !tok.first().is_some_and(|b| b.is_ascii_alphabetic() || *b == b'_') {
                continue;
            }
            // Mostly letters: skip hex blobs and noise.
            let letters = tok.iter().filter(|b| b.is_ascii_alphabetic()).count();
            if letters * 2 < tok.len() {
                continue;
            }
            let t = String::from_utf8_lossy(tok).into_owned();
            if seen_tok.insert(t.clone()) {
                if pool.tokens.len() < max_tokens {
                    pool.tokens.push(t);
                } else {
                    pool.tokens_truncated = true;
                }
            }
        }
    }
    pool
}

/// Read a Dart AOT library: symbols, snapshot headers, string pool, stated versions.
pub fn inspect_aot(data: &[u8], max_uris: usize, max_tokens: usize) -> Result<DartAot, FormatError> {
    let elf = parse_elf(data)?;
    let mut warnings = Vec::new();
    let mut snapshots = Vec::new();
    for (name, role) in DART_SYMBOLS {
        let sym = elf.dart_symbols.iter().find(|s| s.name == name).cloned();
        let header = sym.as_ref().and_then(|s| s.file_offset).and_then(to_usize).and_then(|o| snapshot_header(data, o));
        if sym.is_some() && header.is_none() && role.ends_with("data") {
            warnings.push(format!("{name} does not start with a snapshot header"));
        }
        snapshots.push(DartSnapshot { symbol: name.to_string(), role, present: sym.is_some(), symbol_info: sym, header });
    }
    let data_headers: Vec<&SnapshotHeader> = snapshots.iter().filter(|s| s.role.ends_with("data")).filter_map(|s| s.header.as_ref()).collect();
    let hashes: Vec<&String> = data_headers.iter().filter_map(|h| h.hash.as_ref()).collect();
    let snapshot_hash = match hashes.first() {
        Some(h) if hashes.iter().all(|x| x == h) => Some((*h).clone()),
        Some(_) => {
            warnings.push("the VM and isolate snapshots carry different version hashes".into());
            None
        }
        None => None,
    };
    let complete = snapshots.iter().all(|s| s.present) && data_headers.len() == 2 && data_headers.iter().all(|h| h.kind == 3) && snapshot_hash.is_some();
    let features = data_headers.iter().find_map(|h| h.features.clone());
    // The isolate data region holds the app's strings.
    let iso = snapshots.iter().find(|s| s.role == "isolate-data");
    let region = iso.and_then(|s| {
        let sym = s.symbol_info.as_ref()?;
        let start = to_usize(sym.file_offset?)?;
        let len = if sym.size > 0 { to_usize(sym.size)? } else { s.header.as_ref().and_then(|h| to_usize(h.length.saturating_add(4))).unwrap_or(MAX_REGION) };
        let end = start.saturating_add(len.min(MAX_REGION)).min(data.len());
        data.get(start..end)
    });
    let string_pool = match region {
        Some(r) => string_pool(r, max_uris, max_tokens),
        None => {
            warnings.push("no isolate snapshot data to scan for strings".into());
            StringPool::default()
        }
    };
    let dart_versions = tagged_strings(data, b"Dart VM version:", true, 16);
    Ok(DartAot { elf, snapshots, complete, snapshot_hash, features, string_pool, dart_versions, warnings })
}

/// `lib/<abi>/<file>.so` → (abi, file stem) for `libapp` and `libflutter`.
pub fn flutter_library(path: &str) -> Option<(&str, &'static str)> {
    let rest = path.strip_prefix("lib/")?;
    let (abi, file) = rest.split_once('/')?;
    if abi.is_empty() || file.contains('/') {
        return None;
    }
    match file {
        "libapp.so" => Some((abi, "libapp")),
        "libflutter.so" => Some((abi, "libflutter")),
        _ => None,
    }
}

/// ABI preference for picking one library.
pub fn abi_rank(abi: &str) -> usize {
    match abi {
        "arm64-v8a" => 0,
        "x86_64" => 1,
        "x86" => 2,
        "armeabi-v7a" => 3,
        _ => 4,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::flutter as fx;

    #[test]
    fn reads_section_headers_and_snapshots() {
        let so = fx::libapp_so(fx::SymbolTable::Sections);
        let aot = inspect_aot(&so, 500, 2000).unwrap();
        assert_eq!(aot.elf.symbol_source, "section-headers");
        assert_eq!(aot.elf.dart_symbols.len(), 4);
        assert_eq!(aot.elf.architecture, "arm64");
        assert!(aot.complete, "{aot:?}");
        assert_eq!(aot.snapshot_hash.as_deref(), Some(fx::SNAPSHOT_HASH));
        assert_eq!(aot.features.as_deref(), Some(fx::FEATURES));
        assert!(aot.string_pool.uris.contains(&"package:notes_app/main.dart".to_string()));
        assert!(aot.string_pool.uris.contains(&"dart:core".to_string()));
        assert!(aot.string_pool.tokens.contains(&"NotesHomePage".to_string()));
        assert_eq!(aot.elf.build_id.as_deref(), Some(fx::BUILD_ID_HEX));
    }

    #[test]
    fn reads_section_stripped_images() {
        for (t, src) in [(fx::SymbolTable::DynamicHash, "DT_HASH"), (fx::SymbolTable::DynamicGnuHash, "DT_GNU_HASH")] {
            let so = fx::libapp_so(t);
            let aot = inspect_aot(&so, 500, 2000).unwrap();
            assert_eq!(aot.elf.symbol_source, "dynamic-segment");
            assert_eq!(aot.elf.symbol_count_source, src);
            assert_eq!(aot.elf.dynamic_symbol_count, 5);
            assert!(aot.complete, "{src}");
        }
    }

    #[test]
    fn scans_libflutter() {
        let s = scan_library(&fx::libflutter_so(), 64);
        assert_eq!(s.dart_versions, vec![fx::DART_VERSION.to_string()]);
        assert!(s.toolchains.iter().any(|t| t.contains("clang version 17")));
        assert_eq!(s.build_id.as_deref(), Some(fx::BUILD_ID_HEX));
        let a = scan_library(&fx::libapp_so(fx::SymbolTable::Sections), 64);
        assert_eq!(a.snapshot_hashes, vec![fx::SNAPSHOT_HASH.to_string()]);
        assert_eq!(a.snapshot_occurrences, 2);
    }

    #[test]
    fn library_paths() {
        assert_eq!(flutter_library("lib/arm64-v8a/libapp.so"), Some(("arm64-v8a", "libapp")));
        assert_eq!(flutter_library("lib/x86/libflutter.so"), Some(("x86", "libflutter")));
        assert_eq!(flutter_library("lib/x86/sub/libapp.so"), None);
        assert_eq!(flutter_library("assets/libapp.so"), None);
    }

    #[test]
    fn header_tables_at_the_top_of_the_address_space_are_skipped() {
        for is64 in [true, false] {
            let mut so = fx::libapp_so(fx::SymbolTable::Sections);
            // Where each table's offset is (64-bit at 32 and 40, 32-bit at 28 and 32), and a writer for it.
            let (ph, sh) = if is64 { (32, 40) } else { (28, 32) };
            let put = |so: &mut Vec<u8>, at: usize, v: u64| {
                if is64 {
                    so[at..at + 8].copy_from_slice(&v.to_le_bytes());
                } else {
                    so[at..at + 4].copy_from_slice(&(v as u32).to_le_bytes());
                }
            };
            if !is64 {
                // Read as 32-bit, the sample's header has no counts: give it one entry in each table.
                so[4] = 1;
                for (at, v) in [(42, 32u16), (44, 1), (46, 40), (48, 1)] {
                    so[at..at + 2].copy_from_slice(&v.to_le_bytes());
                }
            }
            // Inside the file, both tables are read, so the loops below really run.
            put(&mut so, ph, 64);
            put(&mut so, sh, 64);
            let elf = Elf::parse(&so).unwrap();
            assert!(!elf.phdrs.is_empty() && !elf.shdrs.is_empty(), "is64 {is64}");
            // A few bytes below the largest offset, `o + 8` would overflow (for 32-bit offsets, only
            // where `usize` is 32 bits; elsewhere this checks the bound).
            let top = if is64 { u64::MAX - 3 } else { u64::from(u32::MAX - 3) };
            put(&mut so, ph, top);
            put(&mut so, sh, top);
            let elf = Elf::parse(&so).unwrap();
            assert!(elf.phdrs.is_empty() && elf.shdrs.is_empty(), "is64 {is64}");
        }
    }

    #[test]
    fn hostile_inputs_do_not_panic() {
        for t in [fx::SymbolTable::Sections, fx::SymbolTable::DynamicHash, fx::SymbolTable::DynamicGnuHash] {
            let so = fx::libapp_so(t);
            for m in craft_anything_testkit::mutations(&so) {
                let _ = inspect_aot(&m, 50, 50);
                let _ = scan_library(&m, 4);
            }
            for len in 0..so.len().min(600) {
                let _ = inspect_aot(&so[..len], 10, 10);
            }
        }
        for seed in 0..64 {
            let mut n = craft_anything_testkit::noise(seed, 2048);
            let _ = string_pool(&n, 5, 5);
            n[..4].copy_from_slice(b"\x7fELF");
            n[4] = 2;
            n[5] = 1;
            let _ = inspect_aot(&n, 5, 5);
            n[4] = 1;
            let _ = inspect_aot(&n, 5, 5);
        }
    }
}
