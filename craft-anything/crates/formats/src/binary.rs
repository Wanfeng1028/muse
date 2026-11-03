//! One model for every executable container: ELF, PE, Mach-O (thin or one slice of a universal
//! binary), COFF objects, DOS MZ/COM and raw machine code.
//!
//! The generic part comes from the `object` crate (sections, symbols, imports, exports); the
//! format modules ([`crate::elf`], [`crate::pe`], [`crate::macho`]) add what it doesn't cover:
//! import pointer slots, stubs, function starts, mitigations and format details.

use crate::{FormatError, hex_addr};
use object::{Object, ObjectSection, ObjectSegment, ObjectSymbol, ObjectSymbolTable};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

/// Caps on what we keep from one file.
pub const MAX_SYMBOLS: usize = 400_000;
pub const MAX_SECTIONS: usize = 4_096;
pub const MAX_RELOCATIONS: usize = 200_000;
pub const MAX_IMPORTS: usize = 100_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Format {
    Elf,
    Pe,
    MachO,
    Coff,
    DosMz,
    DosCom,
    Raw,
}

impl Format {
    pub fn plain(self) -> &'static str {
        match self {
            Format::Elf => "ELF (Linux, Android, BSD)",
            Format::Pe => "PE (Windows)",
            Format::MachO => "Mach-O (macOS, iOS)",
            Format::Coff => "COFF object file",
            Format::DosMz => "DOS MZ executable",
            Format::DosCom => "DOS .COM program",
            Format::Raw => "raw machine code",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Arch {
    /// 16-bit x86 (DOS).
    X86_16,
    X86,
    X86_64,
    Arm,
    Aarch64,
    Other,
}

impl Arch {
    pub fn name(self) -> &'static str {
        match self {
            Arch::X86_16 => "x86-16",
            Arch::X86 => "x86",
            Arch::X86_64 => "x86_64",
            Arch::Arm => "arm",
            Arch::Aarch64 => "arm64",
            Arch::Other => "other",
        }
    }

    pub fn from_name(s: &str) -> Option<Arch> {
        match s.to_ascii_lowercase().as_str() {
            "x86-16" | "x86_16" | "8086" => Some(Arch::X86_16),
            "x86" | "i386" | "i686" | "x86_32" => Some(Arch::X86),
            "x86_64" | "x86-64" | "amd64" | "x64" => Some(Arch::X86_64),
            "arm" | "armv7" | "arm32" | "thumb" => Some(Arch::Arm),
            "arm64" | "aarch64" | "arm64e" => Some(Arch::Aarch64),
            _ => None,
        }
    }

    pub fn pointer_size(self) -> u64 {
        match self {
            Arch::X86_16 => 2,
            Arch::X86 | Arch::Arm => 4,
            Arch::X86_64 | Arch::Aarch64 | Arch::Other => 8,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Section {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub segment: Option<String>,
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub size: u64,
    /// Absolute offset in the file (slices of a universal binary included); `None` for BSS.
    pub file_offset: Option<u64>,
    pub file_size: u64,
    pub read: bool,
    pub write: bool,
    pub exec: bool,
    /// code, data, rodata, bss, debug, metadata, other
    pub kind: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entropy: Option<f32>,
    /// Loaded into memory (ELF SHF_ALLOC); non-loaded sections have no address.
    pub alloc: bool,
}

impl Section {
    pub fn contains(&self, va: u64) -> bool {
        va >= self.addr && va - self.addr < self.size.max(1)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Segment {
    pub name: String,
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub size: u64,
    pub file_offset: u64,
    pub file_size: u64,
    pub read: bool,
    pub write: bool,
    pub exec: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SymbolKind {
    Function,
    Data,
    Section,
    File,
    Other,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Symbol {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub demangled: Option<String>,
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub size: u64,
    pub kind: SymbolKind,
    pub global: bool,
    pub weak: bool,
    pub defined: bool,
    /// From the dynamic symbol table (ELF `.dynsym`).
    pub dynamic: bool,
}

impl Symbol {
    /// The name people should see: demangled when we could.
    pub fn display(&self) -> &str {
        self.demangled.as_deref().unwrap_or(&self.name)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Import {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub library: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ordinal: Option<u16>,
    /// The pointer slot the loader fills (GOT/IAT entry), when known.
    #[serde(with = "hex_addr::opt", skip_serializing_if = "Option::is_none")]
    pub slot: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Export {
    pub name: String,
    #[serde(with = "hex_addr")]
    pub addr: u64,
}

/// A pointer slot (or a stub) that resolves to an imported function at run time.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ImportSlot {
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub library: Option<String>,
    /// `slot` (pointer the loader fills) or `stub` (code that jumps through one).
    pub kind: &'static str,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Relocation {
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub symbol: Option<String>,
    pub addend: i64,
}

/// Exploit mitigations. `None` means "doesn't apply or couldn't tell".
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Mitigations {
    /// Position independent (relocatable base).
    pub pie: Option<bool>,
    /// Data is not executable (NX/DEP).
    pub nx: Option<bool>,
    /// ELF RELRO: none, partial, full.
    pub relro: Option<String>,
    /// Stack protector (canary) in use.
    pub canary: Option<bool>,
    /// _FORTIFY_SOURCE checked functions in use.
    pub fortify: Option<bool>,
    /// PE: high-entropy ASLR.
    pub high_entropy_va: Option<bool>,
    /// PE: Control Flow Guard.
    pub control_flow_guard: Option<bool>,
    /// PE: SafeSEH / no SEH.
    pub no_seh: Option<bool>,
    /// Mach-O: has a code signature.
    pub code_signature: Option<bool>,
    /// Mach-O: encrypted (App Store FairPlay).
    pub encrypted: Option<bool>,
    /// No local symbols left.
    pub stripped: bool,
}

/// A parsed executable or object file.
#[derive(Debug, Clone, Serialize)]
pub struct Binary {
    pub format: Format,
    pub arch: Arch,
    /// The container's own architecture name (`x86_64`, `aarch64`, `mips`, …).
    pub arch_name: String,
    pub bits: u8,
    pub little_endian: bool,
    /// executable, shared-library, relocatable, core, unknown
    pub kind: &'static str,
    #[serde(with = "hex_addr::opt")]
    pub entry: Option<u64>,
    #[serde(with = "hex_addr")]
    pub image_base: u64,
    /// Offset of the analysed slice inside the file (non-zero for universal binaries).
    pub slice_offset: u64,
    pub sections: Vec<Section>,
    pub segments: Vec<Segment>,
    pub symbols: Vec<Symbol>,
    pub symbols_truncated: bool,
    pub imports: Vec<Import>,
    pub exports: Vec<Export>,
    pub libraries: Vec<String>,
    pub relocations: Vec<Relocation>,
    pub relocation_count: usize,
    pub import_slots: Vec<ImportSlot>,
    /// Function entry points the container lists (Mach-O function starts, PE unwind table).
    #[serde(with = "hex_addr::vec")]
    pub function_starts: Vec<u64>,
    pub mitigations: Mitigations,
    /// Format facts as strings: interpreter, soname, build id, uuid, PDB path, subsystem…
    pub info: BTreeMap<String, String>,
    /// Format-specific detail (program headers, load commands, data directories…).
    pub details: serde_json::Value,
    /// Things we noticed but tolerated.
    pub warnings: Vec<String>,
}

impl Binary {
    /// An empty model for code with no container.
    pub fn raw(arch: Arch, base: u64, len: u64, file_offset: u64) -> Binary {
        let bits = match arch {
            Arch::X86_16 => 16,
            Arch::X86 | Arch::Arm => 32,
            _ => 64,
        };
        Binary {
            format: Format::Raw,
            arch,
            arch_name: arch.name().into(),
            bits,
            little_endian: true,
            kind: "executable",
            entry: Some(base),
            image_base: base,
            slice_offset: 0,
            sections: vec![Section {
                name: "code".into(),
                segment: None,
                addr: base,
                size: len,
                file_offset: Some(file_offset),
                file_size: len,
                read: true,
                write: true,
                exec: true,
                kind: "code",
                entropy: None,
                alloc: true,
            }],
            segments: Vec::new(),
            symbols: Vec::new(),
            symbols_truncated: false,
            imports: Vec::new(),
            exports: Vec::new(),
            libraries: Vec::new(),
            relocations: Vec::new(),
            relocation_count: 0,
            import_slots: Vec::new(),
            function_starts: Vec::new(),
            mitigations: Mitigations::default(),
            info: BTreeMap::new(),
            details: serde_json::Value::Null,
            warnings: Vec::new(),
        }
    }

    /// The section holding `va` (sections with file bytes win over BSS).
    pub fn section_at(&self, va: u64) -> Option<&Section> {
        self.sections.iter().filter(|s| s.alloc && s.size > 0 && s.contains(va)).max_by_key(|s| (s.file_offset.is_some(), s.exec))
    }

    pub fn segment_at(&self, va: u64) -> Option<&Segment> {
        self.segments.iter().find(|s| va >= s.addr && va - s.addr < s.size)
    }

    pub fn is_exec(&self, va: u64) -> bool {
        match self.section_at(va) {
            Some(s) => s.exec,
            None => self.segment_at(va).is_some_and(|s| s.exec),
        }
    }

    /// Virtual address → absolute file offset, when the address is backed by file bytes.
    pub fn va_to_offset(&self, va: u64) -> Option<u64> {
        if let Some(s) = self.section_at(va)
            && let Some(off) = s.file_offset
        {
            let delta = va - s.addr;
            if delta < s.file_size {
                return off.checked_add(delta);
            }
        }
        let seg = self.segment_at(va)?;
        let delta = va - seg.addr;
        if delta < seg.file_size { seg.file_offset.checked_add(delta) } else { None }
    }

    /// Absolute file offset → virtual address.
    pub fn offset_to_va(&self, off: u64) -> Option<u64> {
        for s in self.sections.iter().filter(|s| s.alloc) {
            if let Some(fo) = s.file_offset
                && off >= fo
                && off - fo < s.file_size
            {
                return s.addr.checked_add(off - fo);
            }
        }
        self.segments.iter().find(|s| off >= s.file_offset && off - s.file_offset < s.file_size).and_then(|s| s.addr.checked_add(off - s.file_offset))
    }

    /// Up to `len` file-backed bytes at `va`, never crossing the end of its section or segment.
    pub fn read<'a>(&self, data: &'a [u8], va: u64, len: usize) -> Option<&'a [u8]> {
        let off = usize::try_from(self.va_to_offset(va)?).ok()?;
        let avail = self.backed_len(va)?;
        let n = len.min(usize::try_from(avail).unwrap_or(usize::MAX));
        let end = off.checked_add(n)?.min(data.len());
        data.get(off..end)
    }

    /// How many file-backed bytes follow `va` inside its section (or segment).
    pub fn backed_len(&self, va: u64) -> Option<u64> {
        if let Some(s) = self.section_at(va)
            && s.file_offset.is_some()
        {
            let delta = va - s.addr;
            if delta < s.file_size {
                return Some(s.file_size - delta);
            }
        }
        let seg = self.segment_at(va)?;
        let delta = va - seg.addr;
        if delta < seg.file_size { Some(seg.file_size - delta) } else { None }
    }

    /// Read a pointer-sized little/big-endian value at `va`.
    pub fn read_ptr(&self, data: &[u8], va: u64) -> Option<u64> {
        let n = if self.bits == 64 { 8 } else { 4 };
        let b = self.read(data, va, n)?;
        if b.len() != n {
            return None;
        }
        Some(match (n, self.little_endian) {
            (8, true) => u64::from_le_bytes(b.try_into().ok()?),
            (8, false) => u64::from_be_bytes(b.try_into().ok()?),
            (_, true) => u64::from(u32::from_le_bytes(b.try_into().ok()?)),
            (_, false) => u64::from(u32::from_be_bytes(b.try_into().ok()?)),
        })
    }

    /// Lowest and highest mapped address.
    pub fn address_range(&self) -> Option<(u64, u64)> {
        let it = self.sections.iter().filter(|s| s.alloc && s.size > 0).map(|s| (s.addr, s.addr.saturating_add(s.size)));
        let it2 = self.segments.iter().filter(|s| s.size > 0).map(|s| (s.addr, s.addr.saturating_add(s.size)));
        it.chain(it2).fold(None, |acc, (a, b)| match acc {
            None => Some((a, b)),
            Some((x, y)) => Some((x.min(a), y.max(b))),
        })
    }

    /// True when `va` lands inside any section or segment.
    pub fn is_mapped(&self, va: u64) -> bool {
        self.section_at(va).is_some() || self.segment_at(va).is_some()
    }

    /// Name of a defined function symbol at exactly `va`.
    pub fn symbol_at(&self, va: u64) -> Option<&Symbol> {
        self.symbols.iter().find(|s| s.defined && s.addr == va && s.kind == SymbolKind::Function)
    }
}

/// Demangle Rust (legacy and v0) names; other names are left alone.
pub fn demangle(name: &str) -> Option<String> {
    let trimmed = name.strip_prefix('_').filter(|n| n.starts_with("_ZN") || n.starts_with("_R")).unwrap_or(name);
    let d = rustc_demangle::try_demangle(trimmed).ok()?;
    let s = format!("{d:#}");
    if s == name { None } else { Some(s) }
}

/// Parse any supported container. Universal Mach-O files are parsed at their preferred slice
/// (arm64, then x86_64, then the first); use [`crate::macho::fat_slices`] to list them all.
pub fn parse_binary(data: &[u8]) -> Result<Binary, FormatError> {
    if data.len() < 4 {
        return Err(FormatError::Truncated("fewer than 4 bytes".into()));
    }
    if data.starts_with(&[0xca, 0xfe, 0xba, 0xbe]) || data.starts_with(&[0xca, 0xfe, 0xba, 0xbf]) {
        let slices = crate::macho::fat_slices(data)?;
        let pick = slices
            .iter()
            .find(|s| s.arch == "arm64")
            .or_else(|| slices.iter().find(|s| s.arch == "x86_64"))
            .or_else(|| slices.first())
            .ok_or_else(|| FormatError::Malformed("universal binary with no slices".into()))?;
        let off = usize::try_from(pick.offset).map_err(|_| FormatError::Malformed("slice offset".into()))?;
        let size = usize::try_from(pick.size).map_err(|_| FormatError::Malformed("slice size".into()))?;
        let slice = data.get(off..off.saturating_add(size)).ok_or_else(|| FormatError::Truncated("slice outside the file".into()))?;
        let mut b = parse_object(slice, pick.offset)?;
        b.info.insert("universal_slices".into(), slices.iter().map(|s| s.arch.clone()).collect::<Vec<_>>().join(", "));
        b.warnings.push(format!("universal binary with {} slices; analysing the {} slice", slices.len(), pick.arch));
        return Ok(b);
    }
    if data.starts_with(b"MZ") && !crate::pe::has_pe_header(data) {
        return crate::dos::mz_binary(data);
    }
    parse_object(data, 0)
}

fn sec_kind(k: object::SectionKind, exec: bool) -> &'static str {
    use object::SectionKind as K;
    match k {
        K::Text => "code",
        K::Data | K::Tls => "data",
        K::ReadOnlyData | K::ReadOnlyString | K::ReadOnlyDataWithRel => "rodata",
        K::UninitializedData | K::UninitializedTls | K::Common => "bss",
        K::Debug | K::DebugString => "debug",
        K::Metadata | K::Note | K::Linker | K::OtherString | K::Elf(_) => {
            if exec {
                "code"
            } else {
                "metadata"
            }
        }
        _ => {
            if exec {
                "code"
            } else {
                "other"
            }
        }
    }
}

fn section_perms(s: &object::Section<'_, '_>, k: object::SectionKind) -> (bool, bool, bool) {
    match s.flags() {
        object::SectionFlags::Elf { sh_flags } => (sh_flags & 2 != 0, sh_flags & 1 != 0, sh_flags & 4 != 0),
        object::SectionFlags::Coff { characteristics } => {
            (characteristics & 0x4000_0000 != 0, characteristics & 0x8000_0000 != 0, characteristics & 0x2000_0000 != 0 || characteristics & 0x20 != 0)
        }
        object::SectionFlags::MachO { flags } => {
            let exec = flags & 0x8000_0000 != 0 || flags & 0x400 != 0;
            (true, !matches!(k, object::SectionKind::Text | object::SectionKind::ReadOnlyData | object::SectionKind::ReadOnlyString), exec)
        }
        _ => (true, false, matches!(k, object::SectionKind::Text)),
    }
}

fn arch_of(a: object::Architecture) -> (Arch, String) {
    use object::Architecture as A;
    let arch = match a {
        A::I386 => Arch::X86,
        A::X86_64 | A::X86_64_X32 => Arch::X86_64,
        A::Arm => Arch::Arm,
        A::Aarch64 | A::Aarch64_Ilp32 => Arch::Aarch64,
        _ => Arch::Other,
    };
    (arch, format!("{a:?}").to_ascii_lowercase())
}

fn parse_object(data: &[u8], slice_offset: u64) -> Result<Binary, FormatError> {
    let file = object::File::parse(data).map_err(|e| FormatError::Malformed(e.to_string()))?;
    let (arch, arch_name) = arch_of(file.architecture());
    let format = match file.format() {
        object::BinaryFormat::Elf => Format::Elf,
        object::BinaryFormat::Pe => Format::Pe,
        object::BinaryFormat::MachO => Format::MachO,
        object::BinaryFormat::Coff => Format::Coff,
        other => return Err(FormatError::Unsupported(format!("{other:?} files"))),
    };
    let kind = match file.kind() {
        object::ObjectKind::Executable => "executable",
        object::ObjectKind::Dynamic => "shared-library",
        object::ObjectKind::Relocatable => "relocatable",
        object::ObjectKind::Core => "core",
        _ => "unknown",
    };
    let mut b = Binary::raw(arch, 0, 0, 0);
    b.format = format;
    b.arch_name = arch_name;
    b.bits = if file.is_64() { 64 } else { 32 };
    b.little_endian = file.is_little_endian();
    b.kind = kind;
    b.sections.clear();
    b.slice_offset = slice_offset;
    b.image_base = file.relative_address_base();
    b.entry = match file.entry() {
        0 => None,
        e => Some(e),
    };
    for s in file.sections().take(MAX_SECTIONS) {
        let name = s.name().unwrap_or("").to_string();
        let k = s.kind();
        let (read, write, exec) = section_perms(&s, k);
        let alloc = match s.flags() {
            object::SectionFlags::Elf { sh_flags } => sh_flags & 2 != 0,
            _ => true,
        };
        let file_range = s.file_range();
        let bss = matches!(k, object::SectionKind::UninitializedData | object::SectionKind::UninitializedTls | object::SectionKind::Common);
        let (file_offset, mut file_size) = match file_range {
            Some((o, n)) if !bss => (o.checked_add(slice_offset), n),
            _ => (None, 0),
        };
        // Never trust a size past the end of the data.
        if let Some(o) = file_offset {
            let avail = (data.len() as u64 + slice_offset).saturating_sub(o);
            if file_size > avail {
                b.warnings.push(format!("section {} claims {file_size} bytes but only {avail} are in the file", s.name().unwrap_or("?")));
                file_size = avail;
            }
        }
        let entropy = file_offset.and_then(|o| {
            let o = usize::try_from(o.checked_sub(slice_offset)?).ok()?;
            let n = usize::try_from(file_size).ok()?.min(16 << 20);
            data.get(o..o.checked_add(n)?).map(crate::entropy)
        });
        b.sections.push(Section {
            name,
            segment: s.segment_name().ok().flatten().map(String::from),
            addr: s.address(),
            size: s.size(),
            file_offset,
            file_size,
            read,
            write,
            exec,
            kind: sec_kind(k, exec),
            entropy,
            alloc,
        });
    }
    for (i, seg) in file.segments().enumerate().take(MAX_SECTIONS) {
        let (o, mut n) = seg.file_range();
        n = n.min((data.len() as u64).saturating_sub(o));
        let (read, write, exec) = match seg.flags() {
            object::SegmentFlags::Elf { p_flags } => (p_flags & 4 != 0, p_flags & 2 != 0, p_flags & 1 != 0),
            object::SegmentFlags::MachO { initprot, .. } => (initprot & 1 != 0, initprot & 2 != 0, initprot & 4 != 0),
            object::SegmentFlags::Coff { characteristics } => {
                (characteristics & 0x4000_0000 != 0, characteristics & 0x8000_0000 != 0, characteristics & 0x2000_0000 != 0)
            }
            _ => (true, false, false),
        };
        let name = seg.name().ok().flatten().map(String::from).unwrap_or_else(|| format!("LOAD{i}"));
        b.segments.push(Segment { name, addr: seg.address(), size: seg.size(), file_offset: o.saturating_add(slice_offset), file_size: n, read, write, exec });
    }
    if format == Format::MachO {
        for section in &mut b.sections {
            if let Some(segment) = b.segments.iter().find(|seg| {
                section.segment.as_deref() == Some(seg.name.as_str())
                    && section.addr.checked_sub(seg.addr).and_then(|offset| offset.checked_add(section.size)).is_some_and(|end| end <= seg.size)
            }) {
                section.read = segment.read;
                section.write = segment.write;
            }
        }
    }
    // PE sections double as segments in `object`; keep one list.
    if format == Format::Pe {
        b.segments.clear();
    }
    collect_symbols(&file, &mut b);
    // Imports and exports.
    match file.imports() {
        Ok(list) => {
            for imp in list.into_iter().take(MAX_IMPORTS) {
                let lib = String::from_utf8_lossy(imp.library()).into_owned();
                b.imports.push(Import {
                    name: String::from_utf8_lossy(imp.name()).into_owned(),
                    library: if lib.is_empty() { None } else { Some(lib) },
                    ordinal: None,
                    slot: None,
                });
            }
        }
        Err(e) => b.warnings.push(format!("imports: {e}")),
    }
    match file.exports() {
        Ok(list) => {
            for ex in list.into_iter().take(MAX_IMPORTS) {
                b.exports.push(Export { name: String::from_utf8_lossy(ex.name()).into_owned(), addr: ex.address() });
            }
        }
        Err(e) => b.warnings.push(format!("exports: {e}")),
    }
    if let Ok(Some(id)) = file.build_id() {
        b.info.insert("build_id".into(), id.iter().map(|x| format!("{x:02x}")).collect());
    }
    if let Ok(Some(uuid)) = file.mach_uuid() {
        b.info.insert("uuid".into(), uuid.iter().map(|x| format!("{x:02x}")).collect());
    }
    if let Ok(Some(pdb)) = file.pdb_info() {
        b.info.insert("pdb_path".into(), String::from_utf8_lossy(pdb.path()).into_owned());
    }
    // Format-specific enrichment.
    match format {
        Format::Elf => crate::elf::enrich(data, &file, &mut b),
        Format::Pe => crate::pe::enrich(data, &mut b),
        Format::MachO => crate::macho::enrich(data, &mut b),
        _ => {}
    }
    // Mach-O strip keeps the linker's `__mh_*_header`; it is not an internal name.
    let linker_header = |s: &Symbol| format == Format::MachO && s.name.starts_with("__mh_") && s.name.ends_with("_header");
    let local_syms = b.symbols.iter().filter(|s| !s.dynamic && s.defined && !linker_header(s)).count();
    b.mitigations.stripped = local_syms == 0;
    // Import slots also name the imports.
    let mut slot_of: BTreeMap<&str, u64> = BTreeMap::new();
    for s in &b.import_slots {
        if s.kind == "slot" {
            slot_of.entry(s.name.as_str()).or_insert(s.addr);
        }
    }
    let slots: Vec<Option<u64>> = b.imports.iter().map(|i| slot_of.get(i.name.as_str()).copied()).collect();
    for (imp, slot) in b.imports.iter_mut().zip(slots) {
        imp.slot = slot;
    }
    let canary_names = ["__stack_chk_fail", "___stack_chk_fail", "__security_check_cookie", "__stack_chk_guard", "___stack_chk_guard"];
    let has = |n: &str| b.imports.iter().any(|i| i.name == n) || b.symbols.iter().any(|s| s.name == n);
    if b.mitigations.canary.is_none() || b.mitigations.canary == Some(false) {
        b.mitigations.canary = Some(canary_names.iter().any(|n| has(n)));
    }
    if format == Format::Elf {
        let fortify = b.imports.iter().any(|i| i.name.starts_with("__") && i.name.ends_with("_chk") && i.name != "__stack_chk_fail");
        b.mitigations.fortify = Some(fortify);
    }
    b.function_starts.sort_unstable();
    b.function_starts.dedup();
    Ok(b)
}

fn sym_kind(k: object::SymbolKind) -> SymbolKind {
    match k {
        object::SymbolKind::Text => SymbolKind::Function,
        object::SymbolKind::Data | object::SymbolKind::Tls => SymbolKind::Data,
        object::SymbolKind::Section => SymbolKind::Section,
        object::SymbolKind::File => SymbolKind::File,
        _ => SymbolKind::Other,
    }
}

fn collect_symbols(file: &object::File<'_>, b: &mut Binary) {
    let mut seen: BTreeSet<(String, u64)> = BTreeSet::new();
    let mut push = |b: &mut Binary, s: &object::Symbol<'_, '_>, dynamic: bool| {
        let Ok(name) = s.name() else { return };
        if name.is_empty() {
            return;
        }
        let kind = sym_kind(s.kind());
        if matches!(kind, SymbolKind::Section | SymbolKind::File) {
            return;
        }
        if !seen.insert((name.to_string(), s.address())) {
            return;
        }
        if b.symbols.len() >= MAX_SYMBOLS {
            b.symbols_truncated = true;
            return;
        }
        b.symbols.push(Symbol {
            name: name.to_string(),
            demangled: demangle(name),
            addr: s.address(),
            size: s.size(),
            kind,
            global: s.is_global(),
            weak: s.is_weak(),
            defined: s.is_definition() || (!s.is_undefined() && s.address() != 0),
            dynamic,
        });
    };
    for s in file.symbols() {
        push(b, &s, false);
    }
    for s in file.dynamic_symbols() {
        push(b, &s, true);
    }
    // ELF dynamic relocations name GOT slots.
    if let (Some(relocs), Some(table)) = (file.dynamic_relocations(), file.dynamic_symbol_table()) {
        let mut n = 0usize;
        for (addr, r) in relocs {
            n += 1;
            let symbol = match r.target() {
                object::RelocationTarget::Symbol(idx) => {
                    table.symbol_by_index(idx).ok().and_then(|s| s.name().ok().map(String::from)).filter(|s| !s.is_empty())
                }
                _ => None,
            };
            let r_type = match r.flags() {
                object::RelocationFlags::Elf { r_type } => r_type,
                _ => 0,
            };
            let kind = crate::elf::reloc_name(file.architecture(), r_type);
            if let Some(name) = &symbol
                && (kind.ends_with("JUMP_SLOT") || kind.ends_with("GLOB_DAT"))
            {
                b.import_slots.push(ImportSlot { addr, name: name.clone(), library: None, kind: "slot" });
            }
            if b.relocations.len() < MAX_RELOCATIONS {
                b.relocations.push(Relocation { addr, kind: kind.to_string(), symbol, addend: r.addend() });
            }
        }
        b.relocation_count += n;
    }
    // Section relocations (object files).
    if file.kind() == object::ObjectKind::Relocatable {
        for sec in file.sections() {
            for (off, r) in sec.relocations() {
                b.relocation_count += 1;
                if b.relocations.len() >= MAX_RELOCATIONS {
                    continue;
                }
                let symbol = match r.target() {
                    object::RelocationTarget::Symbol(idx) => file.symbol_by_index(idx).ok().and_then(|s| s.name().ok().map(String::from)),
                    _ => None,
                };
                b.relocations.push(Relocation { addr: sec.address().saturating_add(off), kind: format!("{:?}", r.kind()), symbol, addend: r.addend() });
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn demangles_rust_names() {
        assert_eq!(demangle("_ZN4core9panicking5panic17h0123456789abcdefE").as_deref(), Some("core::panicking::panic"));
        assert_eq!(demangle("main"), None);
    }

    #[test]
    fn tiny_inputs_are_errors() {
        assert!(parse_binary(b"").is_err());
        assert!(parse_binary(b"\x7fEL").is_err());
        assert!(parse_binary(b"\x7fELF").is_err());
    }
}
