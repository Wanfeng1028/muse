//! ELF details `object` leaves to us: program headers, the dynamic section, mitigations, and
//! core-file notes (registers, signal, mapped files) for crash inspection.

use crate::binary::{Arch, Binary, Export, Import, MAX_IMPORTS, MAX_SYMBOLS, Symbol, SymbolKind, demangle};
use crate::bytes::Reader;
use crate::{FormatError, hex_addr};
use object::Object;
use serde::Serialize;
use serde_json::json;
use std::collections::BTreeMap;

const MAX_PHDRS: usize = 4096;
const MAX_DYN: usize = 65_536;
const MAX_NOTES: usize = 100_000;

/// Endian/class-aware reads over an ELF image.
#[derive(Clone, Copy)]
struct E<'a> {
    r: Reader<'a>,
    is64: bool,
    le: bool,
}

impl<'a> E<'a> {
    fn new(data: &'a [u8]) -> Result<Self, FormatError> {
        if !data.starts_with(b"\x7fELF") {
            return Err(FormatError::Malformed("no ELF magic".into()));
        }
        let r = Reader::new(data);
        let class = r.u8(4).ok_or_else(|| FormatError::Truncated("ELF ident".into()))?;
        let enc = r.u8(5).ok_or_else(|| FormatError::Truncated("ELF ident".into()))?;
        if !matches!(class, 1 | 2) || !matches!(enc, 1 | 2) {
            return Err(FormatError::Malformed("bad ELF class or data encoding".into()));
        }
        Ok(E { r, is64: class == 2, le: enc == 1 })
    }
    fn u16(&self, off: usize) -> Option<u16> {
        if self.le { self.r.u16_le(off) } else { self.r.u16_be(off) }
    }
    fn u32(&self, off: usize) -> Option<u32> {
        if self.le { self.r.u32_le(off) } else { self.r.u32_be(off) }
    }
    fn u64(&self, off: usize) -> Option<u64> {
        if self.le { self.r.u64_le(off) } else { self.r.u64_be(off) }
    }
    fn word(&self, off: usize) -> Option<u64> {
        if self.is64 { self.u64(off) } else { self.u32(off).map(u64::from) }
    }
    fn word_size(&self) -> usize {
        if self.is64 { 8 } else { 4 }
    }
}

/// One program header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ProgramHeader {
    pub kind: String,
    pub flags: String,
    pub offset: u64,
    #[serde(with = "hex_addr")]
    pub vaddr: u64,
    pub file_size: u64,
    pub mem_size: u64,
    pub align: u64,
    #[serde(skip)]
    pub p_type: u32,
    #[serde(skip)]
    pub p_flags: u32,
}

fn phdr_name(t: u32) -> String {
    match t {
        0 => "NULL".into(),
        1 => "LOAD".into(),
        2 => "DYNAMIC".into(),
        3 => "INTERP".into(),
        4 => "NOTE".into(),
        5 => "SHLIB".into(),
        6 => "PHDR".into(),
        7 => "TLS".into(),
        0x6474_e550 => "GNU_EH_FRAME".into(),
        0x6474_e551 => "GNU_STACK".into(),
        0x6474_e552 => "GNU_RELRO".into(),
        0x6474_e553 => "GNU_PROPERTY".into(),
        0x7000_0001 => "ARM_EXIDX".into(),
        other => format!("{other:#x}"),
    }
}

fn perm_string(f: u32) -> String {
    format!("{}{}{}", if f & 4 != 0 { 'r' } else { '-' }, if f & 2 != 0 { 'w' } else { '-' }, if f & 1 != 0 { 'x' } else { '-' })
}

/// The program headers of an ELF file.
pub fn program_headers(data: &[u8]) -> Result<Vec<ProgramHeader>, FormatError> {
    let e = E::new(data)?;
    let (phoff, phentsize, phnum) = if e.is64 { (e.u64(32), e.u16(54), e.u16(56)) } else { (e.u32(28).map(u64::from), e.u16(42), e.u16(44)) };
    let phoff = usize::try_from(phoff.ok_or_else(|| FormatError::Truncated("ELF header".into()))?).map_err(|_| FormatError::Malformed("phoff".into()))?;
    let phentsize = usize::from(phentsize.unwrap_or(0));
    let phnum = usize::from(phnum.unwrap_or(0)).min(MAX_PHDRS);
    let min = if e.is64 { 56 } else { 32 };
    if phnum > 0 && phentsize < min {
        return Err(FormatError::Malformed("program header entry too small".into()));
    }
    let mut out = Vec::new();
    for i in 0..phnum {
        // The fields below sit within `phentsize` bytes of `o`, so their offsets can't overflow either.
        let Some(o) = i.checked_mul(phentsize).and_then(|x| x.checked_add(phoff)).filter(|&o| o.checked_add(phentsize).is_some()) else { break };
        let ph = if e.is64 {
            (e.u32(o), e.u32(o + 4), e.u64(o + 8), e.u64(o + 16), e.u64(o + 32), e.u64(o + 40), e.u64(o + 48))
        } else {
            (
                e.u32(o),
                e.u32(o + 24),
                e.u32(o + 4).map(u64::from),
                e.u32(o + 8).map(u64::from),
                e.u32(o + 16).map(u64::from),
                e.u32(o + 20).map(u64::from),
                e.u32(o + 28).map(u64::from),
            )
        };
        let (Some(t), Some(f), Some(off), Some(va), Some(fs), Some(ms), Some(al)) = ph else { break };
        out.push(ProgramHeader {
            kind: phdr_name(t),
            flags: perm_string(f),
            offset: off,
            vaddr: va,
            file_size: fs,
            mem_size: ms,
            align: al,
            p_type: t,
            p_flags: f,
        });
    }
    Ok(out)
}

fn dyn_name(tag: u64) -> String {
    match tag {
        0 => "NULL",
        1 => "NEEDED",
        2 => "PLTRELSZ",
        3 => "PLTGOT",
        4 => "HASH",
        5 => "STRTAB",
        6 => "SYMTAB",
        7 => "RELA",
        8 => "RELASZ",
        9 => "RELAENT",
        10 => "STRSZ",
        11 => "SYMENT",
        12 => "INIT",
        13 => "FINI",
        14 => "SONAME",
        15 => "RPATH",
        16 => "SYMBOLIC",
        17 => "REL",
        18 => "RELSZ",
        19 => "RELENT",
        20 => "PLTREL",
        21 => "DEBUG",
        22 => "TEXTREL",
        23 => "JMPREL",
        24 => "BIND_NOW",
        25 => "INIT_ARRAY",
        26 => "FINI_ARRAY",
        27 => "INIT_ARRAYSZ",
        28 => "FINI_ARRAYSZ",
        29 => "RUNPATH",
        30 => "FLAGS",
        0x6fff_fef5 => "GNU_HASH",
        0x6fff_fffb => "FLAGS_1",
        0x6fff_fff0 => "VERSYM",
        0x6fff_fffe => "VERNEED",
        0x6fff_ffff => "VERNEEDNUM",
        _ => return format!("{tag:#x}"),
    }
    .into()
}

/// Map a virtual address to a file offset using PT_LOAD headers.
fn va_to_off(phdrs: &[ProgramHeader], va: u64) -> Option<u64> {
    phdrs.iter().filter(|p| p.p_type == 1).find(|p| va >= p.vaddr && va - p.vaddr < p.file_size).and_then(|p| p.offset.checked_add(va - p.vaddr))
}

/// The (tag, value) pairs of the dynamic section, up to its `DT_NULL`.
fn dynamic_entries(e: &E<'_>, phdrs: &[ProgramHeader]) -> Vec<(u64, u64)> {
    let mut out = Vec::new();
    let Some(d) = phdrs.iter().find(|p| p.p_type == 2) else { return out };
    let ent = 2 * e.word_size();
    let n = usize::try_from(d.file_size).unwrap_or(0) / ent;
    let start = usize::try_from(d.offset).unwrap_or(usize::MAX);
    for i in 0..n.min(MAX_DYN) {
        let Some(o) = i.checked_mul(ent).and_then(|x| start.checked_add(x)) else { break };
        let (Some(tag), Some(val)) = (e.word(o), o.checked_add(e.word_size()).and_then(|v| e.word(v))) else { break };
        if tag == 0 {
            break;
        }
        out.push((tag, val));
    }
    out
}

/// Add ELF facts to a parsed binary: image base, interpreter, needed libraries, RELRO, NX, PIE.
pub fn enrich(data: &[u8], file: &object::File<'_>, b: &mut Binary) {
    let Ok(e) = E::new(data) else { return };
    let phdrs = match program_headers(data) {
        Ok(p) => p,
        Err(err) => {
            b.warnings.push(format!("program headers: {err}"));
            Vec::new()
        }
    };
    let e_type = e.u16(16).unwrap_or(0);
    if let Some(base) = phdrs.iter().filter(|p| p.p_type == 1).map(|p| p.vaddr).min() {
        b.image_base = base;
    }
    let dyns = dynamic_entries(&e, &phdrs);
    let strtab = dyns.iter().find(|(t, _)| *t == 5).and_then(|(_, v)| va_to_off(&phdrs, *v));
    let dstr = |v: u64| -> Option<String> {
        let off = usize::try_from(strtab?.checked_add(v)?).ok()?;
        e.r.cstr(off, 4096)
    };
    let mut flags = 0u64;
    let mut flags1 = 0u64;
    let mut bind_now = false;
    let mut dyn_json = Vec::new();
    for (tag, val) in &dyns {
        match tag {
            1 => {
                if let Some(s) = dstr(*val) {
                    b.libraries.push(s);
                }
            }
            14 => {
                if let Some(s) = dstr(*val) {
                    b.info.insert("soname".into(), s);
                }
            }
            15 => {
                if let Some(s) = dstr(*val) {
                    b.info.insert("rpath".into(), s);
                }
            }
            29 => {
                if let Some(s) = dstr(*val) {
                    b.info.insert("runpath".into(), s);
                }
            }
            24 => bind_now = true,
            30 => flags = *val,
            0x6fff_fffb => flags1 = *val,
            _ => {}
        }
        if dyn_json.len() < 512 {
            dyn_json.push(json!({"tag": dyn_name(*tag), "value": format!("{val:#x}")}));
        }
    }
    bind_now |= flags & 0x8 != 0 || flags1 & 0x1 != 0;
    let interp = phdrs.iter().find(|p| p.p_type == 3).and_then(|p| e.r.cstr(usize::try_from(p.offset).ok()?, usize::try_from(p.file_size).ok()?.min(4096)));
    if let Some(i) = &interp {
        b.info.insert("interpreter".into(), i.clone());
    }
    // Mitigations.
    b.mitigations.nx = Some(phdrs.iter().find(|p| p.p_type == 0x6474_e551).is_some_and(|p| p.p_flags & 1 == 0));
    let relro = phdrs.iter().any(|p| p.p_type == 0x6474_e552);
    b.mitigations.relro = Some(
        match (relro, bind_now) {
            (false, _) => "none",
            (true, false) => "partial",
            (true, true) => "full",
        }
        .into(),
    );
    if e_type == 3 {
        let pie = interp.is_some() || flags1 & 0x0800_0000 != 0;
        b.mitigations.pie = Some(pie);
        if pie {
            b.kind = "executable";
        }
    } else if e_type == 2 {
        b.mitigations.pie = Some(false);
    }
    // Compiler identification from .comment.
    if let Some(sec) = b.sections.iter().find(|s| s.name == ".comment")
        && let Some(off) = sec.file_offset.and_then(|o| usize::try_from(o).ok())
    {
        let n = usize::try_from(sec.file_size).unwrap_or(0).min(4096);
        if let Some(bytes) = data.get(off..off.saturating_add(n)) {
            let parts: Vec<String> = bytes.split(|&c| c == 0).filter(|p| !p.is_empty()).map(|p| String::from_utf8_lossy(p).into_owned()).collect();
            if !parts.is_empty() {
                b.info.insert("compiler".into(), parts.join("; "));
            }
        }
    }
    let _ = file.architecture();
    b.details = json!({
        "elf_type": match e_type { 1 => "REL", 2 => "EXEC", 3 => "DYN", 4 => "CORE", _ => "OTHER" },
        "program_headers": phdrs,
        "dynamic": dyn_json,
        "dt_flags": format!("{flags:#x}"),
        "dt_flags_1": format!("{flags1:#x}"),
    });
    // With no section headers `object` finds no symbols; the dynamic section still points at them.
    if b.sections.is_empty()
        && let Some(ds) = dynamic_symbols(data, b)
    {
        add_dynamic_symbols(b, ds);
    }
}

/// Put symbols read from `PT_DYNAMIC` into the binary's symbols, imports and exports.
fn add_dynamic_symbols(b: &mut Binary, ds: DynamicSymbols) {
    b.warnings.extend(ds.warnings.into_iter().map(|w| format!("dynamic symbols: {w}")));
    b.symbols_truncated |= ds.truncated;
    for (s, defined) in ds.exports.iter().map(|s| (s, true)).chain(ds.imports.iter().map(|s| (s, false))) {
        if b.symbols.len() >= MAX_SYMBOLS {
            b.symbols_truncated = true;
            break;
        }
        let kind = match s.kind {
            "function" | "ifunc" => SymbolKind::Function,
            "object" | "tls" | "common" => SymbolKind::Data,
            _ => SymbolKind::Other,
        };
        b.symbols.push(Symbol {
            name: s.name.clone(),
            demangled: demangle(&s.name),
            addr: s.addr,
            size: s.size,
            kind,
            global: s.binding != "weak",
            weak: s.binding == "weak",
            defined,
            dynamic: true,
        });
    }
    b.exports.extend(ds.exports.iter().take(MAX_IMPORTS).map(|s| Export { name: s.name.clone(), addr: s.addr }));
    let room = MAX_IMPORTS.saturating_sub(b.imports.len());
    b.imports.extend(ds.imports.into_iter().take(room).map(|s| Import { name: s.name, library: s.library, ordinal: None, slot: None }));
}

// ---------------------------------------------------------------------------------------------
// Dynamic symbols with their versions

/// Most dynamic symbols read from one file.
const MAX_DYNSYMS: usize = 400_000;
/// Most version definitions or needs read from one file.
const MAX_VERSIONS: usize = 65_536;

/// One symbol of the dynamic symbol table.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DynSymbol {
    pub name: String,
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub size: u64,
    /// function, object, tls, ifunc, common, other
    pub kind: &'static str,
    /// global, weak, unique
    pub binding: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    /// The library a needed version belongs to (`.gnu.version_r`).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub library: Option<String>,
}

/// The dynamic symbol table, split into what the file offers and what it needs.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct DynamicSymbols {
    pub exports: Vec<DynSymbol>,
    pub imports: Vec<DynSymbol>,
    /// A cap or the end of the file stopped the walk.
    pub truncated: bool,
    pub warnings: Vec<String>,
}

fn section_bytes<'a>(data: &'a [u8], b: &Binary, name: &str) -> Option<&'a [u8]> {
    let s = b.sections.iter().find(|s| s.name == name)?;
    let off = usize::try_from(s.file_offset?).ok()?;
    let len = usize::try_from(s.file_size).ok()?;
    data.get(off..off.checked_add(len)?)
}

fn str_at(strs: &[u8], off: u32) -> Option<String> {
    let rest = strs.get(off as usize..)?;
    // Only the capped part is searched: a table with no NUL would otherwise be read to its end for
    // every symbol.
    let rest = rest.get(..rest.len().min(4096))?;
    let end = rest.iter().position(|&b| b == 0).unwrap_or(rest.len());
    Some(String::from_utf8_lossy(rest.get(..end)?).into_owned())
}

/// Version definitions: index → name.
fn version_defs(e: &E<'_>, base: usize, strs: &[u8]) -> BTreeMap<u16, String> {
    let mut out = BTreeMap::new();
    let mut pos = 0usize;
    for _ in 0..MAX_VERSIONS {
        let Some(at) = base.checked_add(pos) else { break };
        let (Some(ndx), Some(aux), Some(next)) = (e.u16(at.saturating_add(4)), e.u32(at.saturating_add(12)), e.u32(at.saturating_add(16))) else { break };
        if let Some(name) = at.checked_add(aux as usize).and_then(|a| e.u32(a)).and_then(|n| str_at(strs, n)) {
            out.insert(ndx & 0x7fff, name);
        }
        if next == 0 {
            break;
        }
        let Some(p) = pos.checked_add(next as usize) else { break };
        pos = p;
    }
    out
}

/// Version needs by index: (name, library).
type Needs = BTreeMap<u16, (String, String)>;

/// Version needs: index → (name, library).
fn version_needs(e: &E<'_>, base: usize, strs: &[u8]) -> Needs {
    let mut out = BTreeMap::new();
    let mut pos = 0usize;
    let mut budget = MAX_VERSIONS;
    while budget > 0 {
        budget -= 1;
        let Some(at) = base.checked_add(pos) else { break };
        let (Some(cnt), Some(file), Some(aux), Some(next)) =
            (e.u16(at.saturating_add(2)), e.u32(at.saturating_add(4)), e.u32(at.saturating_add(8)), e.u32(at.saturating_add(12)))
        else {
            break;
        };
        let library = str_at(strs, file).unwrap_or_default();
        let Some(mut a) = at.checked_add(aux as usize) else { break };
        for _ in 0..cnt {
            if budget == 0 {
                break;
            }
            budget -= 1;
            let (Some(other), Some(name), Some(anext)) = (e.u16(a.saturating_add(6)), e.u32(a.saturating_add(8)), e.u32(a.saturating_add(12))) else { break };
            if let Some(n) = str_at(strs, name) {
                out.insert(other & 0x7fff, (n, library.clone()));
            }
            if anext == 0 {
                break;
            }
            let Some(na) = a.checked_add(anext as usize) else { break };
            a = na;
        }
        if next == 0 {
            break;
        }
        let Some(p) = pos.checked_add(next as usize) else { break };
        pos = p;
    }
    out
}

/// Where the dynamic symbol table sits, as `PT_DYNAMIC` describes it (no section headers needed).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DynTable {
    /// File offset of the symbol table.
    pub symtab: u64,
    /// How many entries it has.
    pub count: u64,
    /// File offset of the string table.
    pub strtab: u64,
    /// `DT_STRSZ`; 0 when the file doesn't say.
    pub strsz: u64,
    /// How `count` was found: `DT_HASH`, `DT_GNU_HASH` or `estimated`.
    pub count_source: &'static str,
}

/// The result of [`dynamic_table`].
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct DynTableScan {
    pub table: Option<DynTable>,
    pub warnings: Vec<String>,
}

const DT_HASH: u64 = 4;
const DT_STRTAB: u64 = 5;
const DT_SYMTAB: u64 = 6;
const DT_STRSZ: u64 = 10;
const DT_SYMENT: u64 = 11;
const DT_GNU_HASH: u64 = 0x6fff_fef5;
const DT_VERSYM: u64 = 0x6fff_fff0;
const DT_VERDEF: u64 = 0x6fff_fffc;
const DT_VERNEED: u64 = 0x6fff_fffe;
/// Most symbols a `DT_GNU_HASH` chain walk counts.
const MAX_HASH_SYMS: u64 = 4_000_000;

/// How many symbols a `DT_GNU_HASH` table at file offset `off` covers: past the last bucket's
/// start, to the end of its chain.
fn gnu_hash_count(e: &E<'_>, off: u64) -> Option<u64> {
    let o = usize::try_from(off).ok()?;
    let nbuckets = u64::from(e.u32(o)?);
    let symoffset = u64::from(e.u32(o.checked_add(4)?)?);
    let bloom_size = u64::from(e.u32(o.checked_add(8)?)?);
    if nbuckets > (1 << 24) || bloom_size > (1 << 24) {
        return None;
    }
    let buckets = off.checked_add(16)?.checked_add(bloom_size.checked_mul(e.word_size() as u64)?)?;
    let mut max = 0u64;
    for i in 0..nbuckets {
        let b = u64::from(e.u32(usize::try_from(buckets.checked_add(i * 4)?).ok()?)?);
        max = max.max(b);
    }
    if max < symoffset {
        return Some(symoffset);
    }
    let chains = buckets.checked_add(nbuckets * 4)?;
    let mut idx = max;
    loop {
        let v = e.u32(usize::try_from(chains.checked_add(idx.checked_sub(symoffset)?.checked_mul(4)?)?).ok()?)?;
        idx = idx.checked_add(1)?;
        if v & 1 == 1 || idx > MAX_HASH_SYMS {
            return Some(idx);
        }
    }
}

/// Find the dynamic symbol table through `PT_DYNAMIC`: `DT_SYMTAB` and `DT_STRTAB`, with the
/// entry count from `DT_HASH`, else `DT_GNU_HASH`, else estimated from where the string table
/// starts (with a warning). For images whose section headers were removed.
pub fn dynamic_table(data: &[u8]) -> DynTableScan {
    let mut scan = DynTableScan::default();
    let Ok(e) = E::new(data) else { return scan };
    let Ok(phdrs) = program_headers(data) else { return scan };
    let dynv = dynamic_entries(&e, &phdrs);
    let get = |tag: u64| dynv.iter().find(|(t, _)| *t == tag).map(|(_, v)| *v);
    let (Some(symtab), Some(strtab)) = (get(DT_SYMTAB).and_then(|v| va_to_off(&phdrs, v)), get(DT_STRTAB).and_then(|v| va_to_off(&phdrs, v))) else {
        return scan;
    };
    let sym_size = e.sym_size();
    let syment = get(DT_SYMENT).unwrap_or(sym_size);
    if syment != sym_size {
        scan.warnings.push(format!("unexpected DT_SYMENT {syment}"));
        return scan;
    }
    let mut found: Option<(u64, &'static str)> = None;
    if let Some(n) = get(DT_HASH).and_then(|v| va_to_off(&phdrs, v)).and_then(|o| usize::try_from(o).ok()).and_then(|o| e.u32(o.checked_add(4)?)) {
        found = Some((u64::from(n), "DT_HASH"));
    }
    if found.is_none()
        && let Some(n) = get(DT_GNU_HASH).and_then(|v| va_to_off(&phdrs, v)).and_then(|o| gnu_hash_count(&e, o))
    {
        found = Some((n, "DT_GNU_HASH"));
    }
    if found.is_none() && strtab > symtab {
        found = Some(((strtab - symtab) / sym_size, "estimated"));
        scan.warnings.push("no hash table: the symbol count was estimated from the table layout".into());
    }
    if let Some((count, count_source)) = found {
        scan.table = Some(DynTable { symtab, count, strtab, strsz: get(DT_STRSZ).unwrap_or(0), count_source });
    }
    scan
}

/// One raw symbol table entry.
struct RawSym {
    name: u32,
    info: u8,
    other: u8,
    shndx: u16,
    value: u64,
    size: u64,
}

fn raw_sym(e: &E<'_>, at: usize) -> Option<RawSym> {
    let f = |d: usize| at.checked_add(d);
    Some(if e.is64 {
        RawSym { name: e.u32(at)?, info: e.r.u8(f(4)?)?, other: e.r.u8(f(5)?)?, shndx: e.u16(f(6)?)?, value: e.u64(f(8)?)?, size: e.u64(f(16)?)? }
    } else {
        RawSym {
            name: e.u32(at)?,
            info: e.r.u8(f(12)?)?,
            other: e.r.u8(f(13)?)?,
            shndx: e.u16(f(14)?)?,
            value: u64::from(e.u32(f(4)?)?),
            size: u64::from(e.u32(f(8)?)?),
        }
    })
}

impl E<'_> {
    /// Bytes in one symbol table entry.
    fn sym_size(&self) -> u64 {
        if self.is64 { 24 } else { 16 }
    }
}

/// Read `.dynsym` with its version tables; with no such section, the table `PT_DYNAMIC` points
/// at, with its version tables. `None` when the file isn't ELF or has neither.
pub fn dynamic_symbols(data: &[u8], b: &Binary) -> Option<DynamicSymbols> {
    let e = E::new(data).ok()?;
    let ent = usize::try_from(e.sym_size()).ok()?;
    let (Some(syms), Some(strs)) = (section_bytes(data, b, ".dynsym"), section_bytes(data, b, ".dynstr")) else {
        return segment_dynamic_symbols(data, &e);
    };
    let off_of = |name: &str| b.sections.iter().find(|s| s.name == name).and_then(|s| s.file_offset).and_then(|o| usize::try_from(o).ok());
    let defs = off_of(".gnu.version_d").map(|o| version_defs(&e, o, strs)).unwrap_or_default();
    let needs = off_of(".gnu.version_r").map(|o| version_needs(&e, o, strs)).unwrap_or_default();
    let versym = off_of(".gnu.version");
    let syms_off = off_of(".dynsym")?;
    let mut out = DynamicSymbols::default();
    read_dynsyms(&e, (syms_off, syms.len() / ent), strs, versym, &defs, &needs, &mut out);
    Some(out)
}

/// [`dynamic_symbols`] for a file without section headers.
fn segment_dynamic_symbols(data: &[u8], e: &E<'_>) -> Option<DynamicSymbols> {
    let scan = dynamic_table(data);
    let t = scan.table?;
    let phdrs = program_headers(data).ok()?;
    let dynv = dynamic_entries(e, &phdrs);
    let off_of = |tag: u64| dynv.iter().find(|(t, _)| *t == tag).and_then(|(_, v)| va_to_off(&phdrs, *v)).and_then(|o| usize::try_from(o).ok());
    // A string table with no DT_STRSZ runs to the end of the file (each name is capped).
    let strs = data.get(usize::try_from(t.strtab).ok()?..)?;
    let strs = if t.strsz == 0 { strs } else { strs.get(..usize::try_from(t.strsz).unwrap_or(usize::MAX).min(strs.len()))? };
    let defs = off_of(DT_VERDEF).map(|o| version_defs(e, o, strs)).unwrap_or_default();
    let needs = off_of(DT_VERNEED).map(|o| version_needs(e, o, strs)).unwrap_or_default();
    let ent = usize::try_from(e.sym_size()).ok()?;
    let symtab = usize::try_from(t.symtab).ok()?;
    // The count comes from the file's own tables: only the entries that lie inside the file are read.
    let room = data.len().saturating_sub(symtab) / ent;
    let count = usize::try_from(t.count).unwrap_or(usize::MAX);
    let mut out = DynamicSymbols { warnings: scan.warnings, ..DynamicSymbols::default() };
    if count > room {
        out.truncated = true;
        out.warnings.push(format!("the symbol table ends early: {room} of {count} entries are in the file"));
    }
    read_dynsyms(e, (symtab, count.min(room)), strs, off_of(DT_VERSYM), &defs, &needs, &mut out);
    Some(out)
}

/// Read `count` symbols of the table at `syms_off` into `out`, naming each from `strs` and its
/// version from the version tables.
fn read_dynsyms(
    e: &E<'_>,
    (syms_off, count): (usize, usize),
    strs: &[u8],
    versym: Option<usize>,
    defs: &BTreeMap<u16, String>,
    needs: &Needs,
    out: &mut DynamicSymbols,
) {
    let ent = e.sym_size() as usize;
    if count > MAX_DYNSYMS {
        out.truncated = true;
        out.warnings.push(format!("only the first {MAX_DYNSYMS} of {count} dynamic symbols were read"));
    }
    for i in 0..count.min(MAX_DYNSYMS) {
        let Some(RawSym { name, info, other, shndx, value, size }) = i.checked_mul(ent).and_then(|d| syms_off.checked_add(d)).and_then(|at| raw_sym(e, at))
        else {
            break;
        };
        let binding = match info >> 4 {
            1 => "global",
            2 => "weak",
            10 => "unique",
            _ => continue,
        };
        let kind = match info & 0xf {
            0 | 2 => "function",
            1 => "object",
            5 => "common",
            6 => "tls",
            10 => "ifunc",
            3 | 4 => continue,
            _ => "other",
        };
        let Some(text) = str_at(strs, name).filter(|t| !t.is_empty()) else { continue };
        let index = versym.and_then(|v| v.checked_add(i.checked_mul(2)?)).and_then(|v| e.u16(v)).map(|v| v & 0x7fff);
        let defined = shndx != 0;
        let (version, library) = match index {
            Some(ix) if ix >= 2 => {
                if defined {
                    (defs.get(&ix).cloned(), None)
                } else {
                    needs.get(&ix).cloned().map_or((None, None), |(v, l)| (Some(v), Some(l)))
                }
            }
            _ => (None, None),
        };
        let row = DynSymbol { name: text, addr: value, size, kind, binding, version, library };
        if defined {
            // Hidden and internal symbols aren't visible to other programs.
            if !matches!(other & 3, 1 | 2) {
                out.exports.push(row);
            }
        } else {
            out.imports.push(row);
        }
    }
}

/// Name of an ELF dynamic relocation type.
pub fn reloc_name(arch: object::Architecture, t: u32) -> String {
    use object::Architecture as A;
    let n = match (arch, t) {
        (A::X86_64, 1) => "R_X86_64_64",
        (A::X86_64, 2) => "R_X86_64_PC32",
        (A::X86_64, 5) => "R_X86_64_COPY",
        (A::X86_64, 6) => "R_X86_64_GLOB_DAT",
        (A::X86_64, 7) => "R_X86_64_JUMP_SLOT",
        (A::X86_64, 8) => "R_X86_64_RELATIVE",
        (A::X86_64, 16) => "R_X86_64_DTPMOD64",
        (A::X86_64, 17) => "R_X86_64_DTPOFF64",
        (A::X86_64, 18) => "R_X86_64_TPOFF64",
        (A::X86_64, 37) => "R_X86_64_IRELATIVE",
        (A::Aarch64, 257) => "R_AARCH64_ABS64",
        (A::Aarch64, 1024) => "R_AARCH64_COPY",
        (A::Aarch64, 1025) => "R_AARCH64_GLOB_DAT",
        (A::Aarch64, 1026) => "R_AARCH64_JUMP_SLOT",
        (A::Aarch64, 1027) => "R_AARCH64_RELATIVE",
        (A::Aarch64, 1030) => "R_AARCH64_TLS_TPREL64",
        (A::Aarch64, 1031) => "R_AARCH64_TLSDESC",
        (A::Aarch64, 1032) => "R_AARCH64_IRELATIVE",
        (A::I386, 1) => "R_386_32",
        (A::I386, 2) => "R_386_PC32",
        (A::I386, 5) => "R_386_COPY",
        (A::I386, 6) => "R_386_GLOB_DAT",
        (A::I386, 7) => "R_386_JUMP_SLOT",
        (A::I386, 8) => "R_386_RELATIVE",
        (A::Arm, 2) => "R_ARM_ABS32",
        (A::Arm, 21) => "R_ARM_GLOB_DAT",
        (A::Arm, 22) => "R_ARM_JUMP_SLOT",
        (A::Arm, 23) => "R_ARM_RELATIVE",
        _ => return format!("type_{t}"),
    };
    n.into()
}

// ---------------------------------------------------------------------------------------------
// Core files

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Register {
    pub name: &'static str,
    #[serde(with = "hex_addr")]
    pub value: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CoreThread {
    pub pid: u32,
    pub signal: u16,
    pub registers: Vec<Register>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CoreProcess {
    pub pid: u32,
    pub ppid: u32,
    pub name: String,
    pub args: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SigInfo {
    pub signo: i32,
    pub name: &'static str,
    pub code: i32,
    pub errno: i32,
    #[serde(with = "hex_addr::opt")]
    pub fault_addr: Option<u64>,
    /// Plain-English meaning of the signal and code.
    pub meaning: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct MappedFile {
    #[serde(with = "hex_addr")]
    pub start: u64,
    #[serde(with = "hex_addr")]
    pub end: u64,
    pub file_offset: u64,
    pub path: String,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct NoteInfo {
    pub owner: String,
    pub kind: String,
    pub size: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CoreDump {
    pub arch: Arch,
    pub bits: u8,
    pub threads: Vec<CoreThread>,
    pub process: Option<CoreProcess>,
    pub signal: Option<SigInfo>,
    pub mapped_files: Vec<MappedFile>,
    pub auxv: Vec<(String, String)>,
    pub notes: Vec<NoteInfo>,
    pub memory_segments: Vec<ProgramHeader>,
    pub warnings: Vec<String>,
}

impl CoreDump {
    /// The crashing thread's program counter.
    pub fn pc(&self) -> Option<u64> {
        let t = self.threads.first()?;
        t.registers.iter().find(|r| matches!(r.name, "rip" | "pc" | "eip")).map(|r| r.value)
    }

    /// The mapped file (and offset in it) holding `addr`.
    pub fn locate(&self, addr: u64) -> Option<(&MappedFile, u64)> {
        let m = self.mapped_files.iter().find(|m| addr >= m.start && addr < m.end)?;
        Some((m, m.file_offset.saturating_add(addr - m.start)))
    }
}

const X64_REGS: [&str; 27] = [
    "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8", "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags", "rsp", "ss",
    "fs_base", "gs_base", "ds", "es", "fs", "gs",
];
const I386_REGS: [&str; 17] = ["ebx", "ecx", "edx", "esi", "edi", "ebp", "eax", "ds", "es", "fs", "gs", "orig_eax", "eip", "cs", "eflags", "esp", "ss"];
const A64_REGS: [&str; 34] = [
    "x0", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "x18", "x19", "x20", "x21", "x22",
    "x23", "x24", "x25", "x26", "x27", "x28", "x29", "x30", "sp", "pc", "pstate",
];

pub fn signal_name(n: i32) -> &'static str {
    match n {
        1 => "SIGHUP",
        2 => "SIGINT",
        3 => "SIGQUIT",
        4 => "SIGILL",
        5 => "SIGTRAP",
        6 => "SIGABRT",
        7 => "SIGBUS",
        8 => "SIGFPE",
        9 => "SIGKILL",
        10 => "SIGUSR1",
        11 => "SIGSEGV",
        12 => "SIGUSR2",
        13 => "SIGPIPE",
        14 => "SIGALRM",
        15 => "SIGTERM",
        24 => "SIGXCPU",
        25 => "SIGXFSZ",
        31 => "SIGSYS",
        _ => "unknown",
    }
}

fn signal_meaning(signo: i32, code: i32) -> String {
    match (signo, code) {
        (11, 1) => "Read or wrote memory that isn't mapped (often a null or dangling pointer).".into(),
        (11, 2) => "Touched memory it isn't allowed to (wrong permissions, e.g. writing read-only data).".into(),
        (11, _) => "Invalid memory access (segmentation fault).".into(),
        (6, _) => "The program aborted itself (a failed assertion, a detected corruption, or abort()).".into(),
        (4, _) => "Ran an invalid instruction (corrupted code, a trap like ud2, or the wrong CPU).".into(),
        (8, 1) | (8, 2) => "Integer division by zero or overflow.".into(),
        (8, _) => "Arithmetic error.".into(),
        (7, _) => "Bus error: misaligned access or a mapped file that shrank.".into(),
        (5, _) => "Hit a breakpoint or trap.".into(),
        (31, _) => "Made a forbidden system call (sandbox or seccomp).".into(),
        _ => format!("Stopped by {}.", signal_name(signo)),
    }
}

fn auxv_name(t: u64) -> String {
    match t {
        3 => "AT_PHDR",
        4 => "AT_PHENT",
        5 => "AT_PHNUM",
        6 => "AT_PAGESZ",
        7 => "AT_BASE",
        9 => "AT_ENTRY",
        15 => "AT_PLATFORM",
        16 => "AT_HWCAP",
        25 => "AT_RANDOM",
        31 => "AT_EXECFN",
        33 => "AT_SYSINFO_EHDR",
        _ => return format!("AT_{t}"),
    }
    .into()
}

/// Parse an ELF core file's notes and memory segments.
pub fn parse_core(data: &[u8]) -> Result<CoreDump, FormatError> {
    let e = E::new(data)?;
    if e.u16(16) != Some(4) {
        return Err(FormatError::Unsupported("not an ELF core file (e_type is not CORE)".into()));
    }
    let machine = e.u16(18).unwrap_or(0);
    let arch = match machine {
        62 => Arch::X86_64,
        3 => Arch::X86,
        183 => Arch::Aarch64,
        40 => Arch::Arm,
        _ => Arch::Other,
    };
    let phdrs = program_headers(data)?;
    let mut core = CoreDump {
        arch,
        bits: if e.is64 { 64 } else { 32 },
        threads: Vec::new(),
        process: None,
        signal: None,
        mapped_files: Vec::new(),
        auxv: Vec::new(),
        notes: Vec::new(),
        memory_segments: phdrs.iter().filter(|p| p.p_type == 1).cloned().collect(),
        warnings: Vec::new(),
    };
    let ws = e.word_size();
    for ph in phdrs.iter().filter(|p| p.p_type == 4) {
        let start = usize::try_from(ph.offset).map_err(|_| FormatError::Malformed("note offset".into()))?;
        let len = usize::try_from(ph.file_size).map_err(|_| FormatError::Malformed("note size".into()))?;
        let end = start.saturating_add(len).min(data.len());
        if start.saturating_add(len) > data.len() {
            core.warnings.push("a note segment runs past the end of the file; read what is there".into());
        }
        let mut pos = start;
        while pos.saturating_add(12) <= end && core.notes.len() < MAX_NOTES {
            let (Some(namesz), Some(descsz), Some(ty)) = (e.u32(pos), e.u32(pos + 4), e.u32(pos + 8)) else { break };
            let namesz = namesz as usize;
            let descsz = descsz as usize;
            let name_off = pos + 12;
            let desc_off = name_off.saturating_add(namesz.saturating_add(3) & !3);
            let next = desc_off.saturating_add(descsz.saturating_add(3) & !3);
            if desc_off.saturating_add(descsz) > end {
                core.warnings.push("a note is cut short; stopped reading notes".into());
                break;
            }
            let owner = e.r.cstr(name_off, namesz).unwrap_or_default();
            let desc = data.get(desc_off..desc_off + descsz).unwrap_or(&[]);
            let d = E { r: Reader::new(desc), ..e };
            let kind = match ty {
                1 => "NT_PRSTATUS".to_string(),
                2 => "NT_PRFPREG".into(),
                3 => "NT_PRPSINFO".into(),
                6 => "NT_AUXV".into(),
                0x5349_4749 => "NT_SIGINFO".into(),
                0x4649_4c45 => "NT_FILE".into(),
                0x202 => "NT_X86_XSTATE".into(),
                t => format!("{t:#x}"),
            };
            core.notes.push(NoteInfo { owner: owner.clone(), kind, size: descsz as u64 });
            if owner == "CORE" {
                match ty {
                    1 => {
                        let (pid_off, reg_off, names): (usize, usize, &[&'static str]) = match (arch, e.is64) {
                            (Arch::X86_64, true) => (32, 112, &X64_REGS),
                            (Arch::Aarch64, true) => (32, 112, &A64_REGS),
                            (Arch::X86, false) => (24, 72, &I386_REGS),
                            (_, true) => (32, 112, &[]),
                            (_, false) => (24, 72, &[]),
                        };
                        let registers =
                            names.iter().enumerate().filter_map(|(i, n)| d.word(reg_off + i * ws).map(|v| Register { name: n, value: v })).collect();
                        core.threads.push(CoreThread { pid: d.u32(pid_off).unwrap_or(0), signal: d.u16(12).unwrap_or(0), registers });
                    }
                    3 => {
                        let (pid, ppid, fname, args) = if e.is64 { (24, 28, 40, 56) } else { (12, 16, 28, 44) };
                        core.process = Some(CoreProcess {
                            pid: d.u32(pid).unwrap_or(0),
                            ppid: d.u32(ppid).unwrap_or(0),
                            name: d.r.cstr(fname, 16).unwrap_or_default(),
                            args: d.r.cstr(args, 80).unwrap_or_default().trim_end().to_string(),
                        });
                    }
                    0x5349_4749 => {
                        let signo = d.u32(0).unwrap_or(0) as i32;
                        let errno = d.u32(4).unwrap_or(0) as i32;
                        let code = d.u32(8).unwrap_or(0) as i32;
                        let fault = if matches!(signo, 4 | 7 | 8 | 11) { d.word(if e.is64 { 16 } else { 12 }) } else { None };
                        core.signal = Some(SigInfo { signo, name: signal_name(signo), code, errno, fault_addr: fault, meaning: signal_meaning(signo, code) });
                    }
                    0x4649_4c45 => {
                        let count = usize::try_from(d.word(0).unwrap_or(0)).unwrap_or(0).min(65_536);
                        let page = d.word(ws).unwrap_or(4096);
                        let table = 2 * ws;
                        let mut names_off = table.saturating_add(count.saturating_mul(3 * ws));
                        for i in 0..count {
                            let o = table + i * 3 * ws;
                            let (Some(s), Some(en), Some(po)) = (d.word(o), d.word(o + ws), d.word(o + 2 * ws)) else { break };
                            let path = d.r.cstr(names_off, 4096).unwrap_or_default();
                            names_off = names_off.saturating_add(path.len() + 1);
                            core.mapped_files.push(MappedFile { start: s, end: en, file_offset: po.saturating_mul(page), path });
                        }
                    }
                    6 => {
                        let mut o = 0;
                        while let (Some(t), Some(v)) = (d.word(o), d.word(o + ws)) {
                            if t == 0 || core.auxv.len() >= 256 {
                                break;
                            }
                            let value = if t == 31 || t == 15 { format!("{v:#x} (pointer to a string in the process)") } else { format!("{v:#x}") };
                            core.auxv.push((auxv_name(t), value));
                            o += 2 * ws;
                        }
                    }
                    _ => {}
                }
            }
            if next <= pos {
                break;
            }
            pos = next;
        }
    }
    if core.threads.is_empty() {
        core.warnings.push("no thread status (NT_PRSTATUS) note; registers are unknown".into());
    }
    if core.signal.is_none()
        && let Some(t) = core.threads.first()
        && t.signal != 0
    {
        let signo = i32::from(t.signal);
        core.signal = Some(SigInfo { signo, name: signal_name(signo), code: 0, errno: 0, fault_addr: None, meaning: signal_meaning(signo, 0) });
    }
    Ok(core)
}

#[cfg(test)]
mod tests {
    #[test]
    fn a_string_stops_at_its_nul_or_the_cap() {
        assert_eq!(super::str_at(b"ab\0cd\0", 3).as_deref(), Some("cd"));
        assert_eq!(super::str_at(b"ab\0", 9), None);
        assert_eq!(super::str_at(&vec![b'a'; 10_000], 0).map(|s| s.len()), Some(4096), "no NUL anywhere");
        let mut far = vec![b'a'; 5000];
        far.push(0);
        assert_eq!(super::str_at(&far, 0).map(|s| s.len()), Some(4096), "a NUL past the cap");
    }

    use super::*;

    #[test]
    fn core_notes_round_trip() {
        let core = craft_anything_testkit::elf64_core(0x401234, 0xdead);
        let c = parse_core(&core).unwrap();
        assert_eq!(c.arch, Arch::X86_64);
        assert_eq!(c.pc(), Some(0x401234));
        let s = c.signal.as_ref().unwrap();
        assert_eq!(s.name, "SIGSEGV");
        assert_eq!(s.fault_addr, Some(0xdead));
        assert_eq!(c.process.as_ref().unwrap().name, "crashy");
        assert_eq!(c.mapped_files.len(), 2);
        assert_eq!(c.mapped_files[1].path, "/usr/lib/libc.so.6");
        let (m, off) = c.locate(0x400010).unwrap();
        assert_eq!(m.path, "/usr/bin/crashy");
        assert_eq!(off, 0x10);
    }

    #[test]
    fn damaged_cores_never_panic() {
        let core = craft_anything_testkit::elf64_core(0x401234, 0xdead);
        for m in craft_anything_testkit::mutations(&core) {
            let _ = parse_core(&m);
        }
    }

    #[test]
    fn program_headers_and_mitigations() {
        let (elf, _) = craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true);
        let ph = program_headers(&elf).unwrap();
        assert!(ph.iter().any(|p| p.kind == "GNU_STACK"));
        let b = crate::parse_binary(&elf).unwrap();
        assert_eq!(b.mitigations.nx, Some(true));
        assert_eq!(b.mitigations.relro.as_deref(), Some("none"));
        assert_eq!(b.libraries, vec!["libc.so.6".to_string()]);
        assert_eq!(b.info.get("interpreter").map(String::as_str), Some("/lib64/ld-linux-x86-64.so.2"));
    }

    fn load(offset: u64, vaddr: u64, file_size: u64) -> ProgramHeader {
        ProgramHeader { kind: "LOAD".into(), flags: String::new(), offset, vaddr, file_size, mem_size: file_size, align: 0, p_type: 1, p_flags: 0 }
    }

    #[test]
    fn an_address_past_the_last_file_offset_maps_to_nothing() {
        assert_eq!(va_to_off(&[load(0x200, 0x1000, 0x100)], 0x1010), Some(0x210));
        assert_eq!(va_to_off(&[load(u64::MAX, 0x1000, 0x100)], 0x1000), Some(u64::MAX));
        assert_eq!(va_to_off(&[load(u64::MAX, 0x1000, 0x100)], 0x1001), None, "the offset would pass u64::MAX");
    }

    #[test]
    fn a_dynamic_string_table_in_a_load_segment_at_the_end_of_the_offsets_is_ignored() {
        // ELF64 with three program headers: a PT_LOAD at file offset u64::MAX, a PT_LOAD for the
        // whole file and a PT_DYNAMIC whose DT_STRTAB lies one byte into the first PT_LOAD.
        let mut d = vec![0u8; 64 + 3 * 56 + 32];
        let put = |d: &mut Vec<u8>, at: usize, bytes: &[u8]| d[at..at + bytes.len()].copy_from_slice(bytes);
        put(&mut d, 0, b"\x7fELF\x02\x01\x01");
        put(&mut d, 16, &3u16.to_le_bytes()); // ET_DYN
        put(&mut d, 18, &0x3eu16.to_le_bytes()); // x86-64
        put(&mut d, 20, &1u32.to_le_bytes());
        put(&mut d, 32, &64u64.to_le_bytes()); // e_phoff
        put(&mut d, 52, &64u16.to_le_bytes()); // e_ehsize
        put(&mut d, 54, &56u16.to_le_bytes()); // e_phentsize
        put(&mut d, 56, &3u16.to_le_bytes()); // e_phnum
        put(&mut d, 58, &64u16.to_le_bytes()); // e_shentsize
        let total = d.len() as u64;
        let dynamic = 64 + 3 * 56;
        for (i, (p_type, offset, vaddr, size)) in
            [(1u32, u64::MAX, 0x1000u64, 0x100u64), (1, 0, 0, total), (2, dynamic as u64, 0x5000, 32)].into_iter().enumerate()
        {
            let at = 64 + i * 56;
            put(&mut d, at, &p_type.to_le_bytes());
            put(&mut d, at + 8, &offset.to_le_bytes());
            put(&mut d, at + 16, &vaddr.to_le_bytes());
            put(&mut d, at + 32, &size.to_le_bytes()); // p_filesz
            put(&mut d, at + 40, &size.to_le_bytes()); // p_memsz
        }
        put(&mut d, dynamic, &5u64.to_le_bytes()); // DT_STRTAB
        put(&mut d, dynamic + 8, &0x1001u64.to_le_bytes());
        let b = crate::parse_binary(&d).expect("the header and program headers are valid");
        assert!(b.libraries.is_empty());
    }
}

#[cfg(test)]
mod sectionless_tests {
    use super::*;
    use crate::binary::SymbolKind;
    use craft_anything_testkit::flutter::SymbolTable;
    use craft_anything_testkit::sectionless::sectionless_elf;

    const NAMES: [&str; 3] = ["inflate", "deflate", "adler32"];
    const TABLES: [(SymbolTable, &str); 2] = [(SymbolTable::DynamicHash, "DT_HASH"), (SymbolTable::DynamicGnuHash, "DT_GNU_HASH")];

    #[test]
    fn symbols_come_from_the_dynamic_segment_in_every_class_and_byte_order() {
        for (is64, big) in [(true, false), (false, false), (false, true), (true, true)] {
            for (table, source) in TABLES {
                let d = sectionless_elf(is64, big, &NAMES, table);
                let b = crate::parse_binary(&d).unwrap();
                assert!(b.sections.is_empty(), "{is64} {big}");
                let scan = dynamic_table(&d);
                let t = scan.table.unwrap();
                assert_eq!((t.count, t.count_source), (5, source), "{is64} {big}");
                assert!(scan.warnings.is_empty());
                let funcs: Vec<_> = b.symbols.iter().filter(|s| s.defined && s.kind == SymbolKind::Function && s.dynamic).map(|s| s.name.as_str()).collect();
                assert_eq!(funcs, NAMES, "{is64} {big} {source}");
                let exports: Vec<_> = b.exports.iter().map(|e| e.name.as_str()).collect();
                assert_eq!(exports, NAMES);
                assert!(b.exports.iter().all(|e| e.addr != 0));
                assert_eq!(b.imports.iter().map(|i| i.name.as_str()).collect::<Vec<_>>(), ["puts"]);
                let ds = dynamic_symbols(&d, &b).unwrap();
                assert_eq!((ds.exports.len(), ds.imports.len()), (3, 1));
            }
        }
    }

    #[test]
    fn the_section_stripped_flutter_libraries_name_their_symbols() {
        for (table, source) in TABLES {
            let d = craft_anything_testkit::flutter::libapp_so(table);
            let b = crate::parse_binary(&d).unwrap();
            assert!(b.sections.is_empty());
            assert_eq!(dynamic_table(&d).table.unwrap().count_source, source);
            let mut names: Vec<_> = b.symbols.iter().filter(|s| s.dynamic && s.defined).map(|s| s.name.as_str()).collect();
            names.sort_unstable();
            assert_eq!(names, ["_kDartIsolateSnapshotData", "_kDartIsolateSnapshotInstructions", "_kDartVmSnapshotData", "_kDartVmSnapshotInstructions"]);
            assert_eq!(b.exports.len(), 4);
        }
    }

    #[test]
    fn a_damaged_sectionless_file_never_panics() {
        for (is64, big) in [(true, false), (false, true)] {
            for (table, _) in TABLES {
                let d = sectionless_elf(is64, big, &NAMES, table);
                for sample in craft_anything_testkit::mutations(&d) {
                    let _ = dynamic_table(&sample);
                    if let Ok(b) = crate::parse_binary(&sample) {
                        let _ = dynamic_symbols(&sample, &b);
                    }
                }
                for n in (0..d.len()).step_by(7) {
                    let _ = dynamic_table(&d[..n]);
                    let _ = crate::parse_binary(&d[..n]);
                }
            }
        }
    }

    #[test]
    fn a_symbol_count_past_the_end_of_the_file_reads_only_what_is_there() {
        let mut d = sectionless_elf(true, false, &NAMES, SymbolTable::DynamicHash);
        // Patch the DT_HASH table's nchain to the largest count.
        let hash = {
            let phdrs = program_headers(&d).unwrap();
            let e = E::new(&d).unwrap();
            let dynv = dynamic_entries(&e, &phdrs);
            va_to_off(&phdrs, dynv.iter().find(|(tag, _)| *tag == DT_HASH).unwrap().1).unwrap() as usize
        };
        d[hash + 4..hash + 8].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(dynamic_table(&d).table.unwrap().count, u64::from(u32::MAX));
        let b = crate::parse_binary(&d).unwrap();
        let ds = dynamic_symbols(&d, &b).unwrap();
        assert!(ds.truncated && !ds.warnings.is_empty());
        assert_eq!(ds.exports.len(), 3);
    }
}
