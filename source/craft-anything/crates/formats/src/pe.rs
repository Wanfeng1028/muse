//! PE details: headers, imports with their IAT slots, unwind-table function starts, TLS
//! callbacks, the Rich header, mitigations, and the resource tree (icons, version info,
//! manifest).

use crate::binary::{Binary, Import, ImportSlot};
use crate::bytes::Reader;
use crate::{FormatError, hex_addr};
use serde::Serialize;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};

const MAX_IMPORT_DESCRIPTORS: usize = 4096;
const MAX_THUNKS: usize = 65_536;
const MAX_UNWIND: usize = 500_000;
/// Most imported functions kept from one file, across every library.
const MAX_IMPORT_ROWS: usize = 200_000;
/// Most exported entries kept from one file.
const MAX_EXPORTS: usize = 200_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PeSection {
    pub name: String,
    pub virtual_size: u32,
    pub rva: u32,
    pub raw_size: u32,
    pub raw_offset: u32,
    pub characteristics: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeHeaders {
    pub pe_offset: usize,
    pub machine: u16,
    pub timestamp: u32,
    pub characteristics: u16,
    pub pe32_plus: bool,
    pub image_base: u64,
    pub entry_rva: u32,
    pub subsystem: u16,
    pub dll_characteristics: u16,
    pub linker: (u8, u8),
    pub data_dirs: Vec<(u32, u32)>,
    pub sections: Vec<PeSection>,
}

impl PeHeaders {
    /// RVA → file offset through the section table (headers map 1:1).
    pub fn rva_to_offset(&self, rva: u32) -> Option<usize> {
        for s in &self.sections {
            let size = s.virtual_size.max(s.raw_size);
            if rva >= s.rva && rva - s.rva < size {
                let delta = rva - s.rva;
                if delta >= s.raw_size {
                    return None;
                }
                return usize::try_from(s.raw_offset.checked_add(delta)?).ok();
            }
        }
        let first = self.sections.iter().map(|s| s.raw_offset).filter(|o| *o > 0).min().unwrap_or(u32::MAX);
        if rva < first { usize::try_from(rva).ok() } else { None }
    }

    pub fn dir(&self, i: usize) -> Option<(u32, u32)> {
        self.data_dirs.get(i).copied().filter(|(rva, size)| *rva != 0 && *size != 0)
    }
}

/// True when bytes start with MZ and point at a `PE\0\0` signature.
pub fn has_pe_header(data: &[u8]) -> bool {
    let r = Reader::new(data);
    r.u32_le(0x3c).and_then(|o| r.slice(o as usize, 4)) == Some(b"PE\0\0")
}

/// Parse the DOS stub pointer, COFF header, optional header and section table.
pub fn headers(data: &[u8]) -> Result<PeHeaders, FormatError> {
    let r = Reader::new(data);
    if !data.starts_with(b"MZ") {
        return Err(FormatError::Malformed("no MZ signature".into()));
    }
    let pe = r.u32_le(0x3c).ok_or_else(|| FormatError::Truncated("DOS header".into()))? as usize;
    if r.slice(pe, 4) != Some(b"PE\0\0") {
        return Err(FormatError::Malformed("no PE signature".into()));
    }
    let coff = pe + 4;
    let t = |o: Option<u16>| o.ok_or_else(|| FormatError::Truncated("COFF header".into()));
    let machine = t(r.u16_le(coff))?;
    let nsections = usize::from(t(r.u16_le(coff + 2))?);
    let timestamp = r.u32_le(coff + 4).unwrap_or(0);
    let opt_size = usize::from(t(r.u16_le(coff + 16))?);
    let characteristics = t(r.u16_le(coff + 18))?;
    let opt = coff + 20;
    let magic = r.u16_le(opt).ok_or_else(|| FormatError::Truncated("optional header".into()))?;
    let pe32_plus = match magic {
        0x20b => true,
        0x10b => false,
        m => return Err(FormatError::Malformed(format!("optional header magic {m:#x}"))),
    };
    let image_base = if pe32_plus { r.u64_le(opt + 24) } else { r.u32_le(opt + 28).map(u64::from) }.unwrap_or(0);
    let (dd, count_off) = if pe32_plus { (opt + 112, opt + 108) } else { (opt + 96, opt + 92) };
    let count = (r.u32_le(count_off).unwrap_or(0) as usize).min(16);
    let data_dirs = (0..count).map(|i| (r.u32_le(dd + i * 8).unwrap_or(0), r.u32_le(dd + i * 8 + 4).unwrap_or(0))).collect();
    let sh = opt + opt_size;
    let mut sections = Vec::new();
    for i in 0..nsections.min(96) {
        let o = sh + i * 40;
        let Some(name) = r.slice(o, 8) else { break };
        let name = String::from_utf8_lossy(name.split(|&c| c == 0).next().unwrap_or(&[])).into_owned();
        sections.push(PeSection {
            name,
            virtual_size: r.u32_le(o + 8).unwrap_or(0),
            rva: r.u32_le(o + 12).unwrap_or(0),
            raw_size: r.u32_le(o + 16).unwrap_or(0),
            raw_offset: r.u32_le(o + 20).unwrap_or(0),
            characteristics: r.u32_le(o + 36).unwrap_or(0),
        });
    }
    Ok(PeHeaders {
        pe_offset: pe,
        machine,
        timestamp,
        characteristics,
        pe32_plus,
        image_base,
        entry_rva: r.u32_le(opt + 16).unwrap_or(0),
        subsystem: r.u16_le(opt + 68).unwrap_or(0),
        dll_characteristics: r.u16_le(opt + 70).unwrap_or(0),
        linker: (r.u8(opt + 2).unwrap_or(0), r.u8(opt + 3).unwrap_or(0)),
        data_dirs,
        sections,
    })
}

pub fn subsystem_name(s: u16) -> &'static str {
    match s {
        1 => "native",
        2 => "windows-gui",
        3 => "windows-console",
        7 => "posix-console",
        9 => "windows-ce",
        10 => "efi-application",
        11 => "efi-boot-driver",
        12 => "efi-runtime-driver",
        14 => "xbox",
        16 => "windows-boot",
        _ => "unknown",
    }
}

const DIR_NAMES: [&str; 16] = [
    "export",
    "import",
    "resource",
    "exception",
    "security",
    "basereloc",
    "debug",
    "architecture",
    "globalptr",
    "tls",
    "load_config",
    "bound_import",
    "iat",
    "delay_import",
    "clr_runtime",
    "reserved",
];

/// One import with its IAT slot.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PeImport {
    pub library: String,
    pub name: Option<String>,
    pub ordinal: Option<u16>,
    pub slot_va: u64,
}

/// Walk the import directory: every imported function and the IAT slot the loader fills.
pub fn imports(data: &[u8], h: &PeHeaders) -> Vec<PeImport> {
    let mut table = ImportTable::default();
    normal_imports(data, h, &mut table);
    table.rows.into_iter().map(|row| PeImport { library: row.library, name: row.name, ordinal: row.ordinal, slot_va: row.slot_va.unwrap_or(0) }).collect()
}

/// How a program links to an imported function.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ImportKind {
    /// Through the import directory: the loader resolves it when the program starts.
    Normal,
    /// Through the delay-load directory: resolved the first time it is called.
    Delay,
}

impl ImportKind {
    pub fn name(self) -> &'static str {
        match self {
            ImportKind::Normal => "normal",
            ImportKind::Delay => "delay",
        }
    }
}

/// One imported function, by name or by ordinal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ImportRow {
    pub library: String,
    pub kind: ImportKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ordinal: Option<u16>,
    /// The linker's guess at where the name sits in the library's export table.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hint: Option<u16>,
    /// The pointer slot the loader (or delay-load helper) fills.
    #[serde(with = "hex_addr::opt", skip_serializing_if = "Option::is_none")]
    pub slot_va: Option<u64>,
    /// The file records addresses already resolved against one version of the library.
    pub bound: bool,
}

/// A library the bound import directory says this file was pre-resolved against.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BoundModule {
    pub name: String,
    pub timestamp: u32,
    pub forwarders: Vec<String>,
}

/// Everything the import, delay-load and bound import directories say.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct ImportTable {
    pub rows: Vec<ImportRow>,
    pub bound_modules: Vec<BoundModule>,
    /// A cap stopped the walk: more rows may exist.
    pub truncated: bool,
    pub warnings: Vec<String>,
}

fn thunk_at(r: &Reader<'_>, h: &PeHeaders, off: usize) -> Option<u64> {
    if h.pe32_plus { r.u64_le(off) } else { r.u32_le(off).map(u64::from) }
}

/// One thunk as a row's name, hint and ordinal. `name_rva` turns the thunk's value into an RVA.
fn thunk_target(r: &Reader<'_>, h: &PeHeaders, v: u64, name_rva: impl Fn(u64) -> Option<u32>) -> (Option<String>, Option<u16>, Option<u16>) {
    let by_ordinal = if h.pe32_plus { v & (1 << 63) != 0 } else { v & (1 << 31) != 0 };
    if by_ordinal {
        return (None, None, Some((v & 0xffff) as u16));
    }
    let Some(off) = name_rva(v).and_then(|rva| h.rva_to_offset(rva)) else { return (None, None, None) };
    let hint = r.u16_le(off);
    let name = off.checked_add(2).and_then(|o| r.cstr(o, 512));
    (name, hint, None)
}

fn normal_imports(data: &[u8], h: &PeHeaders, out: &mut ImportTable) {
    let r = Reader::new(data);
    let Some((rva, _)) = h.dir(1) else { return };
    let Some(start) = h.rva_to_offset(rva) else {
        out.warnings.push(format!("the import directory at RVA {rva:#x} is outside the file"));
        return;
    };
    let thunk_size = if h.pe32_plus { 8usize } else { 4 };
    for d in 0..MAX_IMPORT_DESCRIPTORS {
        let Some(desc) = d.checked_mul(20).and_then(|o| start.checked_add(o)) else { break };
        let (Some(oft), Some(stamp), Some(name_rva), Some(ft)) =
            (r.u32_le(desc), r.u32_le(desc.saturating_add(4)), r.u32_le(desc.saturating_add(12)), r.u32_le(desc.saturating_add(16)))
        else {
            break;
        };
        if oft == 0 && name_rva == 0 && ft == 0 {
            break;
        }
        let library = h.rva_to_offset(name_rva).and_then(|o| r.cstr(o, 256)).unwrap_or_default();
        let bound = stamp != 0;
        if bound && oft == 0 {
            // A bound table with no lookup table: the slots hold addresses, not names.
            out.warnings.push(format!("{library} is bound and has no lookup table, so its function names can't be read"));
            continue;
        }
        let lookup = if oft != 0 { oft } else { ft };
        let Some(first) = h.rva_to_offset(lookup) else { continue };
        for i in 0..MAX_THUNKS {
            if out.rows.len() >= MAX_IMPORT_ROWS {
                out.truncated = true;
                return;
            }
            let Some(t) = i.checked_mul(thunk_size).and_then(|o| first.checked_add(o)) else { break };
            let Some(v) = thunk_at(&r, h, t) else { break };
            if v == 0 {
                break;
            }
            let (name, hint, ordinal) = thunk_target(&r, h, v, |v| u32::try_from(v & 0x7fff_ffff).ok());
            let slot_va = h.image_base.wrapping_add(u64::from(ft)).wrapping_add((i * thunk_size) as u64);
            out.rows.push(ImportRow { library: library.clone(), kind: ImportKind::Normal, name, ordinal, hint, slot_va: Some(slot_va), bound });
        }
    }
}

/// An RVA held in a delay-load descriptor: old linkers wrote virtual addresses instead.
fn delay_rva(field: u32, rva_based: bool, image_base: u64) -> Option<u32> {
    if rva_based { Some(field) } else { u64::from(field).checked_sub(image_base).and_then(|v| u32::try_from(v).ok()) }
}

fn delay_imports(data: &[u8], h: &PeHeaders, out: &mut ImportTable) {
    let r = Reader::new(data);
    let Some((rva, _)) = h.dir(13) else { return };
    let Some(start) = h.rva_to_offset(rva) else {
        out.warnings.push(format!("the delay-load directory at RVA {rva:#x} is outside the file"));
        return;
    };
    let thunk_size = if h.pe32_plus { 8usize } else { 4 };
    for d in 0..MAX_IMPORT_DESCRIPTORS {
        let Some(desc) = d.checked_mul(32).and_then(|o| start.checked_add(o)) else { break };
        let (Some(attrs), Some(name_f), Some(iat_f), Some(int_f)) =
            (r.u32_le(desc), r.u32_le(desc.saturating_add(4)), r.u32_le(desc.saturating_add(12)), r.u32_le(desc.saturating_add(16)))
        else {
            break;
        };
        if name_f == 0 && iat_f == 0 && int_f == 0 {
            break;
        }
        let rva_based = attrs & 1 != 0;
        let conv = |f: u32| delay_rva(f, rva_based, h.image_base);
        let library = conv(name_f).and_then(|n| h.rva_to_offset(n)).and_then(|o| r.cstr(o, 256)).unwrap_or_default();
        let Some(first) = conv(int_f).and_then(|n| h.rva_to_offset(n)) else {
            out.warnings.push(format!("the delay-load name table of {library} is outside the file"));
            continue;
        };
        let iat = conv(iat_f);
        for i in 0..MAX_THUNKS {
            if out.rows.len() >= MAX_IMPORT_ROWS {
                out.truncated = true;
                return;
            }
            let Some(t) = i.checked_mul(thunk_size).and_then(|o| first.checked_add(o)) else { break };
            let Some(v) = thunk_at(&r, h, t) else { break };
            if v == 0 {
                break;
            }
            let (name, hint, ordinal) = thunk_target(&r, h, v, |v| {
                if rva_based { u32::try_from(v & 0x7fff_ffff).ok() } else { v.checked_sub(h.image_base).and_then(|x| u32::try_from(x).ok()) }
            });
            let slot_va = iat.map(|a| h.image_base.wrapping_add(u64::from(a)).wrapping_add((i * thunk_size) as u64));
            out.rows.push(ImportRow { library: library.clone(), kind: ImportKind::Delay, name, ordinal, hint, slot_va, bound: false });
        }
    }
}

fn bound_modules(data: &[u8], h: &PeHeaders, out: &mut ImportTable) {
    let r = Reader::new(data);
    let Some((rva, size)) = h.dir(11) else { return };
    let Some(start) = h.rva_to_offset(rva) else {
        out.warnings.push(format!("the bound import directory at RVA {rva:#x} is outside the file"));
        return;
    };
    let size = size as usize;
    let mut pos = 0usize;
    while pos < size && out.bound_modules.len() < MAX_IMPORT_DESCRIPTORS {
        let Some(at) = start.checked_add(pos) else { break };
        let (Some(stamp), Some(name_off), Some(refs)) = (r.u32_le(at), r.u16_le(at.saturating_add(4)), r.u16_le(at.saturating_add(6))) else { break };
        if stamp == 0 && name_off == 0 {
            break;
        }
        let name_of = |o: u16| start.checked_add(usize::from(o)).and_then(|p| r.cstr(p, 256)).unwrap_or_default();
        let mut forwarders = Vec::new();
        for i in 0..usize::from(refs) {
            let Some(f) = (i + 1).checked_mul(8).and_then(|o| at.checked_add(o)) else { break };
            let Some(o) = r.u16_le(f.saturating_add(4)) else { break };
            forwarders.push(name_of(o));
        }
        out.bound_modules.push(BoundModule { name: name_of(name_off), timestamp: stamp, forwarders });
        pos = pos.saturating_add((usize::from(refs) + 1) * 8);
    }
}

/// Read the import, delay-load and bound import directories.
pub fn import_table(data: &[u8], h: &PeHeaders) -> ImportTable {
    let mut out = ImportTable::default();
    normal_imports(data, h, &mut out);
    delay_imports(data, h, &mut out);
    bound_modules(data, h, &mut out);
    out
}

/// One exported entry: by ordinal, with a name when it has one, and either code or a forwarder.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PeExport {
    pub ordinal: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    pub rva: u32,
    /// `OTHER.Name` or `OTHER.#12`: the entry is another library's, and holds no code here.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub forwarder: Option<String>,
}

/// The export directory.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct ExportTable {
    pub dll_name: Option<String>,
    pub timestamp: u32,
    pub ordinal_base: u32,
    pub declared_functions: u32,
    pub declared_names: u32,
    pub entries: Vec<PeExport>,
    /// A cap or the end of the file stopped the walk: more entries may exist.
    pub truncated: bool,
    pub warnings: Vec<String>,
}

/// Read the export directory; `None` when the file has none.
pub fn export_table(data: &[u8], h: &PeHeaders) -> Option<ExportTable> {
    let (dir_rva, dir_size) = h.dir(0)?;
    let r = Reader::new(data);
    let mut out = ExportTable::default();
    let Some(d) = h.rva_to_offset(dir_rva) else {
        out.warnings.push(format!("the export directory at RVA {dir_rva:#x} is outside the file"));
        out.truncated = true;
        return Some(out);
    };
    let field = |o: usize| d.checked_add(o).and_then(|p| r.u32_le(p));
    let (Some(name_rva), Some(base), Some(nfuncs), Some(nnames), Some(funcs), Some(names), Some(ords)) =
        (field(12), field(16), field(20), field(24), field(28), field(32), field(36))
    else {
        out.warnings.push("the export directory runs past the end of the file".into());
        out.truncated = true;
        return Some(out);
    };
    out.timestamp = field(4).unwrap_or(0);
    out.ordinal_base = base;
    out.declared_functions = nfuncs;
    out.declared_names = nnames;
    out.dll_name = h.rva_to_offset(name_rva).and_then(|o| r.cstr(o, 512));

    // Names first: each points at a slot of the function table.
    let mut named: BTreeMap<u32, Vec<String>> = BTreeMap::new();
    if let (Some(nt), Some(ot)) = (h.rva_to_offset(names), h.rva_to_offset(ords)) {
        let mut bad_ordinal = 0u32;
        for i in 0..(nnames as usize).min(MAX_EXPORTS) {
            let (Some(n), Some(o)) = (i.checked_mul(4).and_then(|x| nt.checked_add(x)), i.checked_mul(2).and_then(|x| ot.checked_add(x))) else { break };
            let (Some(n), Some(o)) = (r.u32_le(n), r.u16_le(o)) else {
                out.truncated = true;
                break;
            };
            if u32::from(o) >= nfuncs {
                bad_ordinal = bad_ordinal.saturating_add(1);
                continue;
            }
            let Some(text) = h.rva_to_offset(n).and_then(|p| r.cstr(p, 1024)) else { continue };
            named.entry(u32::from(o)).or_default().push(text);
        }
        if bad_ordinal > 0 {
            out.warnings.push(format!("{bad_ordinal} name(s) point past the function table"));
        }
    } else if nnames != 0 {
        out.warnings.push("the export name tables are outside the file, so only ordinals are listed".into());
    }
    if (nnames as usize) > MAX_EXPORTS {
        out.truncated = true;
    }

    let Some(ft) = h.rva_to_offset(funcs) else {
        if nfuncs != 0 {
            out.warnings.push("the export function table is outside the file".into());
            out.truncated = true;
        }
        return Some(out);
    };
    let dir_end = u64::from(dir_rva).saturating_add(u64::from(dir_size));
    for i in 0..nfuncs {
        if out.entries.len() >= MAX_EXPORTS {
            out.truncated = true;
            break;
        }
        let Some(at) = (i as usize).checked_mul(4).and_then(|x| ft.checked_add(x)) else { break };
        let Some(rva) = r.u32_le(at) else {
            out.warnings.push(format!("the export function table ends after {i} of {nfuncs} entries"));
            out.truncated = true;
            break;
        };
        if rva == 0 {
            continue;
        }
        let ordinal = u64::from(base).saturating_add(u64::from(i));
        let forwarder =
            (u64::from(rva) >= u64::from(dir_rva) && u64::from(rva) < dir_end).then(|| h.rva_to_offset(rva).and_then(|o| r.cstr(o, 512)).unwrap_or_default());
        match named.remove(&i) {
            Some(list) => {
                for name in list {
                    out.entries.push(PeExport { ordinal, name: Some(name), rva, forwarder: forwarder.clone() });
                }
            }
            None => out.entries.push(PeExport { ordinal, name: None, rva, forwarder }),
        }
    }
    Some(out)
}

/// Decoded Rich header entries: (product id, build, count).
pub fn rich_header(data: &[u8], pe_offset: usize) -> Option<Vec<(u16, u16, u32)>> {
    let r = Reader::new(data);
    let region = data.get(0x40..pe_offset.min(data.len()))?;
    let rich = region.windows(4).position(|w| w == b"Rich")? + 0x40;
    let key = r.u32_le(rich + 4)?;
    // Walk back to "DanS".
    let mut pos = rich;
    let mut start = None;
    while pos >= 0x44 {
        pos -= 4;
        if r.u32_le(pos)? ^ key == 0x536e_6144 {
            start = Some(pos);
            break;
        }
    }
    let start = start?;
    let mut out = Vec::new();
    let mut o = start + 16;
    while o + 8 <= rich && out.len() < 256 {
        let id = r.u32_le(o)? ^ key;
        let count = r.u32_le(o + 4)? ^ key;
        out.push(((id >> 16) as u16, (id & 0xffff) as u16, count));
        o += 8;
    }
    Some(out)
}

/// Add PE facts: imports with IAT slots, mitigations, unwind-table function starts, TLS
/// callbacks, subsystem and data directories.
pub fn enrich(data: &[u8], b: &mut Binary) {
    let h = match headers(data) {
        Ok(h) => h,
        Err(e) => {
            b.warnings.push(format!("PE headers: {e}"));
            return;
        }
    };
    b.image_base = h.image_base;
    b.entry = if h.entry_rva != 0 { Some(h.image_base.wrapping_add(u64::from(h.entry_rva))) } else { None };
    if h.characteristics & 0x2000 != 0 {
        b.kind = "shared-library";
    }
    let r = Reader::new(data);
    // Imports (ours carry IAT slots and ordinals).
    let imps = imports(data, &h);
    if !imps.is_empty() {
        b.imports.clear();
        let mut libs = BTreeSet::new();
        for i in &imps {
            let name = i.name.clone().unwrap_or_else(|| format!("{}#{}", i.library.trim_end_matches(".dll").trim_end_matches(".DLL"), i.ordinal.unwrap_or(0)));
            libs.insert(i.library.clone());
            b.import_slots.push(ImportSlot { addr: i.slot_va, name: name.clone(), library: Some(i.library.clone()), kind: "slot" });
            b.imports.push(Import { name, library: Some(i.library.clone()), ordinal: i.ordinal, slot: Some(i.slot_va) });
        }
        b.libraries = libs.into_iter().collect();
    }
    // Delay-loaded imports: calls go through their own slots, so they get names too.
    let mut delayed = ImportTable::default();
    delay_imports(data, &h, &mut delayed);
    for i in delayed.rows {
        let name = i.name.clone().unwrap_or_else(|| format!("{}#{}", i.library.trim_end_matches(".dll").trim_end_matches(".DLL"), i.ordinal.unwrap_or(0)));
        if !b.libraries.contains(&i.library) {
            b.libraries.push(i.library.clone());
        }
        if let Some(slot) = i.slot_va {
            b.import_slots.push(ImportSlot { addr: slot, name: name.clone(), library: Some(i.library.clone()), kind: "slot" });
        }
        b.imports.push(Import { name, library: Some(i.library), ordinal: i.ordinal, slot: i.slot_va });
    }
    // Mitigations.
    let dc = h.dll_characteristics;
    b.mitigations.pie = Some(dc & 0x40 != 0);
    b.mitigations.nx = Some(dc & 0x100 != 0);
    b.mitigations.high_entropy_va = Some(dc & 0x20 != 0);
    b.mitigations.control_flow_guard = Some(dc & 0x4000 != 0);
    b.mitigations.no_seh = Some(dc & 0x400 != 0);
    // Exception table → function starts (x64 and ARM64).
    if let Some((rva, size)) = h.dir(3)
        && let Some(off) = h.rva_to_offset(rva)
    {
        let ent = if h.machine == 0xaa64 { 8 } else { 12 };
        let n = (size as usize / ent).min(MAX_UNWIND);
        for i in 0..n {
            let Some(begin) = r.u32_le(off + i * ent) else { break };
            if begin != 0 {
                b.function_starts.push(h.image_base.wrapping_add(u64::from(begin)));
            }
        }
    }
    // TLS callbacks run before the entry point.
    if let Some((rva, _)) = h.dir(9)
        && let Some(off) = h.rva_to_offset(rva)
    {
        let cb_va = if h.pe32_plus { r.u64_le(off + 24) } else { r.u32_le(off + 12).map(u64::from) };
        if let Some(cb_va) = cb_va.filter(|v| *v >= h.image_base) {
            let mut list = Vec::new();
            for i in 0..64u64 {
                let rva = cb_va - h.image_base + i * if h.pe32_plus { 8 } else { 4 };
                let Some(o) = u32::try_from(rva).ok().and_then(|r| h.rva_to_offset(r)) else { break };
                let v = if h.pe32_plus { r.u64_le(o) } else { r.u32_le(o).map(u64::from) };
                match v {
                    Some(v) if v != 0 => list.push(v),
                    _ => break,
                }
            }
            if !list.is_empty() {
                b.info.insert("tls_callbacks".into(), list.iter().map(|v| format!("{v:#x}")).collect::<Vec<_>>().join(", "));
                b.function_starts.extend(list);
            }
        }
    }
    if h.dir(14).is_some() {
        b.info.insert("dotnet".into(), "CLR header present (.NET assembly)".into());
    }
    b.info.insert("subsystem".into(), subsystem_name(h.subsystem).into());
    b.info.insert("timestamp".into(), h.timestamp.to_string());
    b.info.insert("linker_version".into(), format!("{}.{}", h.linker.0, h.linker.1));
    let rich = rich_header(data, h.pe_offset);
    if rich.is_some() {
        b.info.insert("rich_header".into(), "present (built with Microsoft tools)".into());
    }
    let dirs: Vec<_> = h
        .data_dirs
        .iter()
        .enumerate()
        .filter(|(_, (rva, size))| *rva != 0 || *size != 0)
        .map(|(i, (rva, size))| json!({"name": DIR_NAMES.get(i).copied().unwrap_or("?"), "rva": format!("{rva:#x}"), "size": size}))
        .collect();
    let secs: Vec<_> = h.sections.iter().map(|s| json!({"name": s.name, "characteristics": format!("{:#x}", s.characteristics)})).collect();
    b.details = json!({
        "machine": format!("{:#x}", h.machine),
        "pe32_plus": h.pe32_plus,
        "characteristics": format!("{:#x}", h.characteristics),
        "dll_characteristics": format!("{dc:#x}"),
        "subsystem": subsystem_name(h.subsystem),
        "data_directories": dirs,
        "sections": secs,
        "rich_header": rich.map(|v| v.into_iter().map(|(p, bld, c)| json!({"product": p, "build": bld, "count": c})).collect::<Vec<_>>()),
    });
}

// ---------------------------------------------------------------------------------------------
// Resources

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ResourceEntry {
    pub type_name: String,
    pub name: String,
    pub language: u32,
    #[serde(with = "hex_addr")]
    pub rva: u64,
    pub size: u32,
    pub file_offset: Option<u64>,
    pub codepage: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IconEntry {
    pub width: u32,
    pub height: u32,
    pub bit_count: u16,
    pub bytes: u32,
    pub icon_id: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct IconGroup {
    pub name: String,
    pub icons: Vec<IconEntry>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct VersionInfo {
    pub file_version: Option<String>,
    pub product_version: Option<String>,
    pub strings: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Resources {
    pub entries: Vec<ResourceEntry>,
    pub truncated: bool,
    pub icon_groups: Vec<IconGroup>,
    pub version: Option<VersionInfo>,
    pub manifest: Option<String>,
    pub warnings: Vec<String>,
}

pub fn resource_type_name(id: u32) -> String {
    match id {
        1 => "RT_CURSOR",
        2 => "RT_BITMAP",
        3 => "RT_ICON",
        4 => "RT_MENU",
        5 => "RT_DIALOG",
        6 => "RT_STRING",
        7 => "RT_FONTDIR",
        8 => "RT_FONT",
        9 => "RT_ACCELERATOR",
        10 => "RT_RCDATA",
        11 => "RT_MESSAGETABLE",
        12 => "RT_GROUP_CURSOR",
        14 => "RT_GROUP_ICON",
        16 => "RT_VERSION",
        17 => "RT_DLGINCLUDE",
        19 => "RT_PLUGPLAY",
        20 => "RT_VXD",
        21 => "RT_ANICURSOR",
        22 => "RT_ANIICON",
        23 => "RT_HTML",
        24 => "RT_MANIFEST",
        _ => return format!("#{id}"),
    }
    .into()
}

fn utf16_at(r: &Reader<'_>, off: usize, units: usize) -> Option<String> {
    let mut v = Vec::with_capacity(units.min(1024));
    for i in 0..units.min(4096) {
        v.push(r.u16_le(off + i * 2)?);
    }
    Some(String::from_utf16_lossy(&v))
}

/// Walk the resource directory (type → name → language), bounded by `max_entries`.
pub fn parse_resources(data: &[u8], max_entries: usize) -> Result<Resources, FormatError> {
    let h = headers(data)?;
    let mut res = Resources::default();
    let Some((rva, _size)) = h.dir(2) else { return Ok(res) };
    let base = h.rva_to_offset(rva).ok_or_else(|| FormatError::Malformed("resource directory is not in the file".into()))?;
    let r = Reader::new(data);
    let mut visited = BTreeSet::new();
    // (dir offset relative to base, depth, path)
    type Path = Vec<(Option<u32>, String)>;
    let mut stack: Vec<(usize, u8, Path)> = vec![(0, 0, Vec::new())];
    while let Some((dir, depth, path)) = stack.pop() {
        if !visited.insert(dir) || depth > 3 {
            res.warnings.push("resource directory loops or nests too deep; skipped a branch".into());
            continue;
        }
        let at = base.saturating_add(dir);
        let (Some(named), Some(ids)) = (r.u16_le(at + 12), r.u16_le(at + 14)) else {
            res.warnings.push("resource directory cut short".into());
            continue;
        };
        let n = usize::from(named) + usize::from(ids);
        for i in (0..n).rev() {
            let e = at + 16 + i * 8;
            let (Some(name), Some(target)) = (r.u32_le(e), r.u32_le(e + 4)) else { break };
            let label = if name & 0x8000_0000 != 0 {
                let so = base.saturating_add((name & 0x7fff_ffff) as usize);
                let len = usize::from(r.u16_le(so).unwrap_or(0));
                (None, utf16_at(&r, so + 2, len).unwrap_or_default())
            } else {
                (Some(name), name.to_string())
            };
            let mut p = path.clone();
            p.push(label);
            if target & 0x8000_0000 != 0 {
                stack.push(((target & 0x7fff_ffff) as usize, depth + 1, p));
            } else {
                if res.entries.len() >= max_entries {
                    res.truncated = true;
                    continue;
                }
                let de = base.saturating_add(target as usize);
                let (Some(drva), Some(dsize)) = (r.u32_le(de), r.u32_le(de + 4)) else { continue };
                let (type_id, type_label) = p.first().cloned().unwrap_or((None, String::new()));
                let type_name = match type_id {
                    Some(id) => resource_type_name(id),
                    None => type_label,
                };
                let name = p.get(1).map(|x| x.1.clone()).unwrap_or_default();
                let language = p.get(2).and_then(|x| x.0).unwrap_or(0);
                res.entries.push(ResourceEntry {
                    type_name,
                    name,
                    language,
                    rva: u64::from(drva),
                    size: dsize,
                    file_offset: h.rva_to_offset(drva).map(|o| o as u64),
                    codepage: r.u32_le(de + 8).unwrap_or(0),
                });
            }
        }
    }
    res.entries.sort_by(|a, b| (a.type_name.as_str(), a.name.as_str(), a.language).cmp(&(b.type_name.as_str(), b.name.as_str(), b.language)));
    // Decode the interesting ones.
    for e in &res.entries {
        let Some(off) = e.file_offset.and_then(|o| usize::try_from(o).ok()) else { continue };
        let Some(bytes) = data.get(off..off.saturating_add(e.size as usize).min(data.len())) else { continue };
        match e.type_name.as_str() {
            "RT_GROUP_ICON" => {
                let g = Reader::new(bytes);
                let count = usize::from(g.u16_le(4).unwrap_or(0)).min(256);
                let icons = (0..count)
                    .filter_map(|i| {
                        let o = 6 + i * 14;
                        let w = g.u8(o)?;
                        let hgt = g.u8(o + 1)?;
                        Some(IconEntry {
                            width: if w == 0 { 256 } else { u32::from(w) },
                            height: if hgt == 0 { 256 } else { u32::from(hgt) },
                            bit_count: g.u16_le(o + 6)?,
                            bytes: g.u32_le(o + 8)?,
                            icon_id: g.u16_le(o + 12)?,
                        })
                    })
                    .collect();
                res.icon_groups.push(IconGroup { name: e.name.clone(), icons });
            }
            "RT_VERSION" if res.version.is_none() => res.version = parse_version_info(bytes),
            "RT_MANIFEST" if res.manifest.is_none() => {
                let n = bytes.len().min(64 * 1024);
                res.manifest = Some(String::from_utf8_lossy(bytes.get(..n).unwrap_or(&[])).into_owned());
            }
            _ => {}
        }
    }
    Ok(res)
}

/// Decode a `VS_VERSIONINFO` block: fixed file/product versions and the string tables.
pub fn parse_version_info(bytes: &[u8]) -> Option<VersionInfo> {
    let r = Reader::new(bytes);
    let mut info = VersionInfo::default();
    walk_version(&r, 0, bytes.len(), 0, &mut info);
    if info.file_version.is_none() && info.strings.is_empty() { None } else { Some(info) }
}

fn align4(x: usize) -> usize {
    x.saturating_add(3) & !3
}

fn walk_version(r: &Reader<'_>, start: usize, end: usize, depth: u8, info: &mut VersionInfo) {
    if depth > 6 {
        return;
    }
    let mut pos = start;
    while pos + 6 <= end && info.strings.len() < 512 {
        let Some(len) = r.u16_le(pos).map(usize::from) else { return };
        if len < 6 {
            return;
        }
        let node_end = pos.saturating_add(len).min(end);
        let value_len = usize::from(r.u16_le(pos + 2).unwrap_or(0));
        let is_text = r.u16_le(pos + 4) == Some(1);
        // key
        let mut k = pos + 6;
        let mut key = Vec::new();
        while k + 2 <= node_end && key.len() < 256 {
            let Some(u) = r.u16_le(k) else { break };
            k += 2;
            if u == 0 {
                break;
            }
            key.push(u);
        }
        let key = String::from_utf16_lossy(&key);
        let value_off = align4(k);
        let value_bytes = if is_text { value_len * 2 } else { value_len };
        match key.as_str() {
            "VS_VERSION_INFO" => {
                if r.u32_le(value_off) == Some(0xfeef_04bd) {
                    let v = |ms: Option<u32>, ls: Option<u32>| -> Option<String> {
                        let (ms, ls) = (ms?, ls?);
                        Some(format!("{}.{}.{}.{}", ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff))
                    };
                    info.file_version = v(r.u32_le(value_off + 8), r.u32_le(value_off + 12));
                    info.product_version = v(r.u32_le(value_off + 16), r.u32_le(value_off + 20));
                }
                walk_version(r, align4(value_off + value_bytes), node_end, depth + 1, info);
            }
            "StringFileInfo" => walk_version(r, align4(value_off + value_bytes), node_end, depth + 1, info),
            "VarFileInfo" => {}
            _ if depth >= 2 && is_text && value_len > 0 => {
                let units = value_len.min((node_end.saturating_sub(value_off)) / 2);
                let v = utf16_at(r, value_off, units).unwrap_or_default();
                info.strings.insert(key, v.trim_end_matches('\0').to_string());
            }
            _ => walk_version(r, align4(value_off + value_bytes), node_end, depth + 1, info),
        }
        let next = align4(pos + len);
        if next <= pos {
            return;
        }
        pos = next;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn imports_carry_iat_slots() {
        let pe = craft_anything_testkit::pe64();
        let h = headers(&pe).unwrap();
        let imps = imports(&pe, &h);
        assert_eq!(imps.len(), 1);
        assert_eq!(imps[0].name.as_deref(), Some("puts"));
        assert_eq!(imps[0].library, "msvcrt.dll");
        assert_eq!(imps[0].slot_va, craft_anything_testkit::PE_BASE + craft_anything_testkit::PE_IAT_RVA);
    }

    #[test]
    fn resources_icons_and_version() {
        let pe = craft_anything_testkit::pe64();
        let res = parse_resources(&pe, 100).unwrap();
        assert_eq!(res.entries.len(), 3, "{:?}", res.entries);
        assert_eq!(res.icon_groups.len(), 1);
        assert_eq!(res.icon_groups[0].icons[0].width, 16);
        let v = res.version.unwrap();
        assert_eq!(v.file_version.as_deref(), Some("1.2.3.4"));
        assert_eq!(v.strings.get("CompanyName").map(String::as_str), Some("Craft Test"));
        assert_eq!(v.strings.get("ProductName").map(String::as_str), Some("Craft Sample"));
        let capped = parse_resources(&pe, 1).unwrap();
        assert!(capped.truncated);
    }

    #[test]
    fn damaged_pes_never_panic() {
        let pe = craft_anything_testkit::pe64();
        for m in craft_anything_testkit::mutations(&pe) {
            let _ = parse_resources(&m, 1000);
            if let Ok(h) = headers(&m) {
                let _ = imports(&m, &h);
            }
            let _ = crate::parse_binary(&m);
        }
    }
}
