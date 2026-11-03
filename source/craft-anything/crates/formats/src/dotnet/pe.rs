//! The PE layer under a .NET assembly: COFF and optional headers, sections, RVA mapping, and the
//! CLI (COR20) header from data directory 14.

use crate::FormatError;
use crate::bytes::Reader;
use serde::Serialize;

const MAX_SECTIONS: usize = 96;

/// One PE section header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PeSection {
    pub name: String,
    pub virtual_address: u32,
    pub virtual_size: u32,
    pub raw_offset: u32,
    pub raw_size: u32,
    pub characteristics: u32,
}

/// An RVA and size pair from a data directory.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize)]
pub struct DataDir {
    pub rva: u32,
    pub size: u32,
}

impl DataDir {
    pub fn is_empty(&self) -> bool {
        self.rva == 0 || self.size == 0
    }
}

/// The CLI header (ECMA-335 II.25.3.3).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct CliHeader {
    pub cb: u32,
    pub major_runtime_version: u16,
    pub minor_runtime_version: u16,
    pub metadata: DataDir,
    pub flags: u32,
    pub entry_point_token: u32,
    pub resources: DataDir,
    pub strong_name_signature: DataDir,
    pub code_manager_table: DataDir,
    pub vtable_fixups: DataDir,
    pub export_address_table_jumps: DataDir,
    pub managed_native_header: DataDir,
}

pub const COMIMAGE_FLAGS_ILONLY: u32 = 0x1;
pub const COMIMAGE_FLAGS_32BITREQUIRED: u32 = 0x2;
pub const COMIMAGE_FLAGS_IL_LIBRARY: u32 = 0x4;
pub const COMIMAGE_FLAGS_STRONGNAMESIGNED: u32 = 0x8;
pub const COMIMAGE_FLAGS_NATIVE_ENTRYPOINT: u32 = 0x10;
pub const COMIMAGE_FLAGS_TRACKDEBUGDATA: u32 = 0x10000;
pub const COMIMAGE_FLAGS_32BITPREFERRED: u32 = 0x20000;

impl CliHeader {
    /// Names of the set flags.
    pub fn flag_names(&self) -> Vec<&'static str> {
        let mut v = Vec::new();
        for (bit, name) in [
            (COMIMAGE_FLAGS_ILONLY, "il-only"),
            (COMIMAGE_FLAGS_32BITREQUIRED, "32bit-required"),
            (COMIMAGE_FLAGS_IL_LIBRARY, "il-library"),
            (COMIMAGE_FLAGS_STRONGNAMESIGNED, "strong-name-signed"),
            (COMIMAGE_FLAGS_NATIVE_ENTRYPOINT, "native-entry-point"),
            (COMIMAGE_FLAGS_TRACKDEBUGDATA, "track-debug-data"),
            (COMIMAGE_FLAGS_32BITPREFERRED, "32bit-preferred"),
        ] {
            if self.flags & bit != 0 {
                v.push(name);
            }
        }
        v
    }
}

/// The parts of a PE image a managed reader needs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PeImage {
    pub machine: u16,
    pub characteristics: u16,
    /// 0x10b (PE32) or 0x20b (PE32+).
    pub optional_magic: u16,
    pub subsystem: u16,
    pub dll_characteristics: u16,
    pub sections: Vec<PeSection>,
    pub cli_directory: DataDir,
    pub cli: CliHeader,
    /// True when the managed native header carries the ReadyToRun signature `RTR`.
    pub ready_to_run: bool,
    pub ready_to_run_version: Option<(u16, u16)>,
}

impl PeImage {
    /// The file offset of an RVA, refusing addresses outside every section's raw data or covered
    /// by more than one section.
    pub fn rva_to_offset(&self, rva: u32) -> Option<usize> {
        let mut found = None;
        for s in &self.sections {
            let span = s.virtual_size.max(s.raw_size);
            let end = s.virtual_address.checked_add(span)?;
            if rva >= s.virtual_address && rva < end {
                if found.is_some() {
                    return None;
                }
                let delta = rva.checked_sub(s.virtual_address)?;
                if delta >= s.raw_size {
                    return None;
                }
                found = Some(usize::try_from(s.raw_offset.checked_add(delta)?).ok()?);
            }
        }
        found
    }

    /// The bytes of a data directory, when fully inside the file.
    pub fn dir_bytes<'a>(&self, data: &'a [u8], d: DataDir) -> Option<&'a [u8]> {
        if d.is_empty() {
            return None;
        }
        let off = self.rva_to_offset(d.rva)?;
        Reader::new(data).slice(off, usize::try_from(d.size).ok()?)
    }

    pub fn machine_name(&self) -> String {
        machine_name(self.machine)
    }

    /// Where the runtime will run this assembly: `anycpu` (the native size of the machine),
    /// `anycpu-prefer-32`, `x86`, or the machine name for a PE that is CPU-specific.
    pub fn dotnet_arch(&self) -> String {
        let m = self.machine_name();
        let flags = self.cli.flags;
        if m != "x86" || flags & COMIMAGE_FLAGS_ILONLY == 0 {
            return m;
        }
        match (flags & COMIMAGE_FLAGS_32BITREQUIRED != 0, flags & COMIMAGE_FLAGS_32BITPREFERRED != 0) {
            (false, _) => "anycpu".into(),
            (true, true) => "anycpu-prefer-32".into(),
            (true, false) => "x86".into(),
        }
    }
}

/// Plain name of a COFF machine value, undoing the operating-system override some precompiled
/// images apply to it.
pub fn machine_name(m: u16) -> String {
    let base = |v: u16| match v {
        0x14c => Some("x86"),
        0x8664 => Some("x64"),
        0xaa64 => Some("arm64"),
        0x1c4 => Some("arm"),
        0x200 => Some("ia64"),
        _ => None,
    };
    if let Some(n) = base(m) {
        return n.to_string();
    }
    for (os, os_name) in [(0x4644u16, "apple"), (0xadc4, "freebsd"), (0x7b79, "linux"), (0x1993, "netbsd")] {
        if let Some(n) = base(m ^ os) {
            return format!("{n}-{os_name}");
        }
    }
    format!("machine-{m:#06x}")
}

fn dd(r: &Reader<'_>, off: usize) -> DataDir {
    DataDir { rva: r.u32_le(off).unwrap_or(0), size: r.u32_le(off.saturating_add(4)).unwrap_or(0) }
}

/// Parse the PE headers and the CLI header. Fails when there is no CLI header.
pub fn parse_pe(data: &[u8]) -> Result<PeImage, FormatError> {
    let r = Reader::new(data);
    if r.slice(0, 2) != Some(b"MZ") {
        return Err(FormatError::Malformed("no MZ header".into()));
    }
    let pe = r.u32_le(0x3c).ok_or_else(|| FormatError::Truncated("DOS header".into()))? as usize;
    if r.slice(pe, 4) != Some(b"PE\0\0") {
        return Err(FormatError::Malformed("no PE signature".into()));
    }
    let coff = pe.checked_add(4).ok_or_else(|| FormatError::Malformed("PE offset".into()))?;
    let machine = r.u16_le(coff).ok_or_else(|| FormatError::Truncated("COFF header".into()))?;
    let nsec = usize::from(r.u16_le(coff.saturating_add(2)).ok_or_else(|| FormatError::Truncated("COFF header".into()))?);
    let opt_size = usize::from(r.u16_le(coff.saturating_add(16)).ok_or_else(|| FormatError::Truncated("COFF header".into()))?);
    let characteristics = r.u16_le(coff.saturating_add(18)).ok_or_else(|| FormatError::Truncated("COFF header".into()))?;
    let opt = coff.saturating_add(20);
    let magic = r.u16_le(opt).ok_or_else(|| FormatError::Truncated("optional header".into()))?;
    let (dirs, ndirs_off) = match magic {
        0x10b => (opt.saturating_add(96), opt.saturating_add(92)),
        0x20b => (opt.saturating_add(112), opt.saturating_add(108)),
        m => return Err(FormatError::Malformed(format!("unknown optional header magic {m:#x}"))),
    };
    let subsystem = r.u16_le(opt.saturating_add(68)).unwrap_or(0);
    let dll_characteristics = r.u16_le(opt.saturating_add(70)).unwrap_or(0);
    let ndirs = r.u32_le(ndirs_off).ok_or_else(|| FormatError::Truncated("optional header".into()))?;
    if ndirs <= 14 {
        return Err(FormatError::Unsupported("no CLI header: this is not a .NET assembly".into()));
    }
    let cli_directory = dd(&r, dirs.saturating_add(14 * 8));
    if cli_directory.is_empty() {
        return Err(FormatError::Unsupported("no CLI header: this is not a .NET assembly".into()));
    }
    if nsec > MAX_SECTIONS {
        return Err(FormatError::Malformed(format!("{nsec} sections")));
    }
    let sec_table = opt.checked_add(opt_size).ok_or_else(|| FormatError::Malformed("optional header size".into()))?;
    let mut sections = Vec::with_capacity(nsec);
    for i in 0..nsec {
        let o = sec_table.saturating_add(i * 40);
        let raw = r.slice(o, 40).ok_or_else(|| FormatError::Truncated("section table".into()))?;
        let name_bytes = raw.get(..8).unwrap_or(&[]);
        let end = name_bytes.iter().position(|&b| b == 0).unwrap_or(name_bytes.len());
        sections.push(PeSection {
            name: String::from_utf8_lossy(name_bytes.get(..end).unwrap_or(&[])).into_owned(),
            virtual_size: r.u32_le(o.saturating_add(8)).unwrap_or(0),
            virtual_address: r.u32_le(o.saturating_add(12)).unwrap_or(0),
            raw_size: r.u32_le(o.saturating_add(16)).unwrap_or(0),
            raw_offset: r.u32_le(o.saturating_add(20)).unwrap_or(0),
            characteristics: r.u32_le(o.saturating_add(36)).unwrap_or(0),
        });
    }
    let mut img = PeImage {
        machine,
        characteristics,
        optional_magic: magic,
        subsystem,
        dll_characteristics,
        sections,
        cli_directory,
        cli: CliHeader::default(),
        ready_to_run: false,
        ready_to_run_version: None,
    };
    let cli_off = img.rva_to_offset(cli_directory.rva).ok_or_else(|| FormatError::Malformed("the CLI header lies outside every section".into()))?;
    let c = r.slice(cli_off, 72).ok_or_else(|| FormatError::Truncated("CLI header".into()))?;
    let cr = Reader::new(c);
    img.cli = CliHeader {
        cb: cr.u32_le(0).unwrap_or(0),
        major_runtime_version: cr.u16_le(4).unwrap_or(0),
        minor_runtime_version: cr.u16_le(6).unwrap_or(0),
        metadata: dd(&cr, 8),
        flags: cr.u32_le(16).unwrap_or(0),
        entry_point_token: cr.u32_le(20).unwrap_or(0),
        resources: dd(&cr, 24),
        strong_name_signature: dd(&cr, 32),
        code_manager_table: dd(&cr, 40),
        vtable_fixups: dd(&cr, 48),
        export_address_table_jumps: dd(&cr, 56),
        managed_native_header: dd(&cr, 64),
    };
    if !img.cli.managed_native_header.is_empty()
        && let Some(off) = img.rva_to_offset(img.cli.managed_native_header.rva)
        && r.u32_le(off) == Some(0x0052_5452)
    {
        img.ready_to_run = true;
        img.ready_to_run_version = r.u16_le(off.saturating_add(4)).zip(r.u16_le(off.saturating_add(6)));
    }
    Ok(img)
}
