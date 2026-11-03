//! A direct Mach-O load-command reader (thin slices, either byte order): the header, every load
//! command with decoded details, linked libraries with their versions, run-path entries, the
//! code-signature range, build versions, encryption info and section locations. Used for
//! inspection, code-signature and dynamic-linker resolution work.

use crate::FormatError;
use crate::bytes::Reader;
use crate::macho::{cpu_name, fat_slices, load_command_name};
use serde::Serialize;
use serde_json::{Value as Json, json};

const MAX_CMDS: usize = 8192;
const MAX_CMD_BYTES: usize = 16 << 20;
const MAX_SECTIONS: usize = 4096;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Header {
    pub is64: bool,
    pub big_endian: bool,
    pub cputype: u32,
    pub cpusubtype: u32,
    pub arch: String,
    pub filetype: u32,
    pub filetype_name: &'static str,
    pub ncmds: u32,
    pub sizeofcmds: u32,
    pub flags: u32,
    pub flag_names: Vec<&'static str>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct DylibRef {
    /// load, weak, reexport, lazy, upward
    pub kind: &'static str,
    pub name: String,
    pub current_version: String,
    pub compatibility_version: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BuildVersion {
    pub platform: String,
    pub minos: String,
    pub sdk: Option<String>,
    pub tools: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Encryption {
    pub cryptoff: u32,
    pub cryptsize: u32,
    pub cryptid: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SectionRef {
    pub segname: String,
    pub sectname: String,
    pub addr: u64,
    pub size: u64,
    pub offset: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct LoadCommand {
    pub index: usize,
    pub cmd: String,
    pub offset: usize,
    pub size: u32,
    pub detail: Json,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct MachoDeps {
    pub header: Header,
    pub commands: Vec<LoadCommand>,
    pub dylibs: Vec<DylibRef>,
    pub id_dylib: Option<DylibRef>,
    pub rpaths: Vec<String>,
    pub dyld_environment: Vec<String>,
    pub uuid: Option<String>,
    pub build_versions: Vec<BuildVersion>,
    pub source_version: Option<String>,
    pub encryption: Option<Encryption>,
    /// (dataoff, datasize) of LC_CODE_SIGNATURE, relative to the slice.
    pub code_signature: Option<(u32, u32)>,
    pub entry_offset: Option<u64>,
    pub sections: Vec<SectionRef>,
    pub segments: Vec<Json>,
    pub warnings: Vec<String>,
}

/// One architecture slice of a (possibly universal) file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Slice {
    pub arch: String,
    pub cputype: u32,
    pub cpusubtype: u32,
    pub offset: u64,
    pub size: u64,
    pub align: Option<u32>,
    pub universal: bool,
}

struct E<'a> {
    r: Reader<'a>,
    be: bool,
}

impl E<'_> {
    fn u32(&self, o: usize) -> Option<u32> {
        if self.be { self.r.u32_be(o) } else { self.r.u32_le(o) }
    }
    fn u64(&self, o: usize) -> Option<u64> {
        if self.be { self.r.u64_be(o) } else { self.r.u64_le(o) }
    }
}

/// True for a thin Mach-O magic in either byte order.
pub fn is_thin(data: &[u8]) -> bool {
    matches!(data.get(..4), Some([0xfe, 0xed, 0xfa, 0xce | 0xcf]) | Some([0xce | 0xcf, 0xfa, 0xed, 0xfe]))
}

/// True for a universal (fat) magic.
pub fn is_fat(data: &[u8]) -> bool {
    matches!(data.get(..4), Some([0xca, 0xfe, 0xba, 0xbe | 0xbf]))
}

/// The slices of a thin or universal file.
pub fn slices(data: &[u8]) -> Result<Vec<Slice>, FormatError> {
    if is_fat(data) {
        return Ok(fat_slices(data)?
            .into_iter()
            .map(|s| Slice {
                arch: s.arch,
                cputype: s.cputype,
                cpusubtype: s.cpusubtype,
                offset: s.offset,
                size: s.size,
                align: Some(s.align),
                universal: true,
            })
            .collect());
    }
    let h = header(data)?;
    Ok(vec![Slice { arch: h.arch, cputype: h.cputype, cpusubtype: h.cpusubtype, offset: 0, size: data.len() as u64, align: None, universal: false }])
}

/// The bytes of one slice.
pub fn slice_bytes<'a>(data: &'a [u8], s: &Slice) -> Option<&'a [u8]> {
    let off = usize::try_from(s.offset).ok()?;
    let size = usize::try_from(s.size).ok()?;
    data.get(off..off.checked_add(size)?)
}

/// Pick a slice by architecture name (with fallbacks arm64e→arm64, x86_64h→x86_64), or the
/// preferred one (arm64, then x86_64, then the first).
pub fn pick_slice(slices: &[Slice], arch: Option<&str>) -> Option<Slice> {
    match arch {
        Some(a) => {
            let fallback = match a {
                "arm64e" => Some("arm64"),
                "x86_64h" => Some("x86_64"),
                _ => None,
            };
            slices.iter().find(|s| s.arch == a).or_else(|| fallback.and_then(|f| slices.iter().find(|s| s.arch == f))).cloned()
        }
        None => slices.iter().find(|s| s.arch == "arm64").or_else(|| slices.iter().find(|s| s.arch == "x86_64")).or_else(|| slices.first()).cloned(),
    }
}

fn filetype_name(t: u32) -> &'static str {
    match t {
        1 => "object",
        2 => "execute",
        3 => "fvmlib",
        4 => "core",
        5 => "preload",
        6 => "dylib",
        7 => "dylinker",
        8 => "bundle",
        9 => "dylib-stub",
        10 => "dsym",
        11 => "kext-bundle",
        12 => "fileset",
        _ => "unknown",
    }
}

const FLAGS: &[(u32, &str)] = &[
    (0x1, "NOUNDEFS"),
    (0x4, "DYLDLINK"),
    (0x10, "PREBOUND"),
    (0x20, "SPLIT_SEGS"),
    (0x80, "TWOLEVEL"),
    (0x2000, "SUBSECTIONS_VIA_SYMBOLS"),
    (0x8000, "WEAK_DEFINES"),
    (0x1_0000, "BINDS_TO_WEAK"),
    (0x2_0000, "ALLOW_STACK_EXECUTION"),
    (0x20_0000, "PIE"),
    (0x80_0000, "HAS_TLV_DESCRIPTORS"),
    (0x100_0000, "NO_HEAP_EXECUTION"),
    (0x200_0000, "APP_EXTENSION_SAFE"),
    (0x8000_0000, "DYLIB_IN_CACHE"),
];

pub fn platform_name(p: u32) -> String {
    match p {
        1 => "macos",
        2 => "ios",
        3 => "tvos",
        4 => "watchos",
        5 => "bridgeos",
        6 => "mac-catalyst",
        7 => "ios-simulator",
        8 => "tvos-simulator",
        9 => "watchos-simulator",
        10 => "driverkit",
        11 => "visionos",
        12 => "visionos-simulator",
        other => return format!("platform-{other}"),
    }
    .into()
}

/// `xxxx.yy.zz` nibble-packed version.
pub fn version(v: u32) -> String {
    format!("{}.{}.{}", v >> 16, (v >> 8) & 0xff, v & 0xff)
}

fn extra_name(cmd: u32) -> String {
    let n = load_command_name(cmd);
    if !n.starts_with("0x") {
        return n;
    }
    match cmd {
        0x3 => "LC_SYMSEG",
        0x4 => "LC_THREAD",
        0xf => "LC_ID_DYLINKER",
        0x12 => "LC_SUB_FRAMEWORK",
        0x13 => "LC_SUB_UMBRELLA",
        0x14 => "LC_SUB_CLIENT",
        0x15 => "LC_SUB_LIBRARY",
        0x16 => "LC_TWOLEVEL_HINTS",
        0x27 => "LC_DYLD_ENVIRONMENT",
        0x2b => "LC_DYLIB_CODE_SIGN_DRS",
        0x2d => "LC_LINKER_OPTION",
        0x2e => "LC_LINKER_OPTIMIZATION_HINT",
        0x2f => "LC_VERSION_MIN_TVOS",
        0x30 => "LC_VERSION_MIN_WATCHOS",
        0x31 => "LC_NOTE",
        0x35 => "LC_FILESET_ENTRY",
        0x36 => "LC_ATOM_INFO",
        0x8000_0023 => "LC_LOAD_UPWARD_DYLIB",
        _ => return n,
    }
    .into()
}

fn header_of(e: &E<'_>, is64: bool) -> Result<Header, FormatError> {
    let get = |o| e.u32(o).ok_or_else(|| FormatError::Truncated("Mach-O header".into()));
    let cputype = get(4)?;
    let cpusubtype = get(8)?;
    let filetype = get(12)?;
    let flags = get(24)?;
    if is64 && e.r.len() < 32 {
        return Err(FormatError::Truncated("Mach-O header".into()));
    }
    Ok(Header {
        is64,
        big_endian: e.be,
        cputype,
        cpusubtype,
        arch: cpu_name(cputype, cpusubtype),
        filetype,
        filetype_name: filetype_name(filetype),
        ncmds: get(16)?,
        sizeofcmds: get(20)?,
        flags,
        flag_names: FLAGS.iter().filter(|(b, _)| flags & b != 0).map(|(_, n)| *n).collect(),
    })
}

fn endian(data: &[u8]) -> Result<(bool, bool), FormatError> {
    match data.get(..4) {
        Some([0xcf, 0xfa, 0xed, 0xfe]) => Ok((true, false)),
        Some([0xce, 0xfa, 0xed, 0xfe]) => Ok((false, false)),
        Some([0xfe, 0xed, 0xfa, 0xcf]) => Ok((true, true)),
        Some([0xfe, 0xed, 0xfa, 0xce]) => Ok((false, true)),
        Some(_) => Err(FormatError::Malformed("not a thin Mach-O file".into())),
        None => Err(FormatError::Truncated("Mach-O magic".into())),
    }
}

/// Just the header of a thin slice.
pub fn header(data: &[u8]) -> Result<Header, FormatError> {
    let (is64, be) = endian(data)?;
    header_of(&E { r: Reader::new(data), be }, is64)
}

/// Read every load command of a thin slice.
pub fn parse_thin(data: &[u8]) -> Result<MachoDeps, FormatError> {
    let (is64, be) = endian(data)?;
    let e = E { r: Reader::new(data), be };
    let header = header_of(&e, is64)?;
    let start = if is64 { 32usize } else { 28 };
    let limit = start.saturating_add((header.sizeofcmds as usize).min(MAX_CMD_BYTES)).min(data.len());
    let mut out = MachoDeps {
        header,
        commands: Vec::new(),
        dylibs: Vec::new(),
        id_dylib: None,
        rpaths: Vec::new(),
        dyld_environment: Vec::new(),
        uuid: None,
        build_versions: Vec::new(),
        source_version: None,
        encryption: None,
        code_signature: None,
        entry_offset: None,
        sections: Vec::new(),
        segments: Vec::new(),
        warnings: Vec::new(),
    };
    if (out.header.sizeofcmds as usize) > data.len().saturating_sub(start) {
        out.warnings.push("sizeofcmds runs past the end of the file".into());
    }
    let mut pos = start;
    let ncmds = out.header.ncmds as usize;
    if ncmds > MAX_CMDS {
        out.warnings.push(format!("{ncmds} load commands; reading the first {MAX_CMDS}"));
    }
    for index in 0..ncmds.min(MAX_CMDS) {
        let (Some(cmd), Some(size)) = (e.u32(pos), e.u32(pos + 4)) else {
            out.warnings.push(format!("load command {index} is cut short"));
            break;
        };
        let sz = size as usize;
        if sz < 8 || pos.saturating_add(sz) > data.len() {
            out.warnings.push(format!("load command {index} has a bad size {size}; stopped"));
            break;
        }
        let str_at = |field: usize| -> Option<String> {
            let o = e.u32(pos + field)? as usize;
            if o < 8 || o >= sz {
                return None;
            }
            e.r.cstr(pos + o, sz - o)
        };
        let dylib = |kind: &'static str| -> Option<DylibRef> {
            Some(DylibRef {
                kind,
                name: str_at(8)?,
                current_version: version(e.u32(pos + 16).unwrap_or(0)),
                compatibility_version: version(e.u32(pos + 20).unwrap_or(0)),
            })
        };
        let name = extra_name(cmd);
        let detail = match cmd {
            0xc | 0x20 | 0x8000_0018 | 0x8000_001f | 0x8000_0023 => {
                let kind = match cmd {
                    0xc => "load",
                    0x20 => "lazy",
                    0x8000_0018 => "weak",
                    0x8000_001f => "reexport",
                    _ => "upward",
                };
                match dylib(kind) {
                    Some(d) => {
                        let j = json!({"name": d.name, "current_version": d.current_version, "compatibility_version": d.compatibility_version});
                        out.dylibs.push(d);
                        j
                    }
                    None => json!({"error": "unreadable name"}),
                }
            }
            0xd => match dylib("id") {
                Some(d) => {
                    let j = json!({"name": d.name, "current_version": d.current_version});
                    out.id_dylib = Some(d);
                    j
                }
                None => json!({"error": "unreadable name"}),
            },
            0xe | 0xf | 0x27 | 0x12 | 0x13 | 0x14 | 0x15 => {
                let s = str_at(8);
                if cmd == 0x27
                    && let Some(v) = &s
                {
                    out.dyld_environment.push(v.clone());
                }
                json!({"name": s})
            }
            0x8000_001c => {
                let s = str_at(8);
                if let Some(v) = &s {
                    out.rpaths.push(v.clone());
                }
                json!({"path": s})
            }
            0x1b => {
                let u = e.r.slice(pos + 8, 16).map(|b| {
                    let h: String = b.iter().map(|x| format!("{x:02X}")).collect();
                    format!(
                        "{}-{}-{}-{}-{}",
                        h.get(0..8).unwrap_or(""),
                        h.get(8..12).unwrap_or(""),
                        h.get(12..16).unwrap_or(""),
                        h.get(16..20).unwrap_or(""),
                        h.get(20..32).unwrap_or("")
                    )
                });
                out.uuid = u.clone();
                json!({"uuid": u})
            }
            0x32 => {
                let ntools = e.u32(pos + 20).unwrap_or(0) as usize;
                let tools: Vec<String> = (0..ntools.min(32))
                    .filter_map(|i| {
                        let t = e.u32(pos + 24 + i * 8)?;
                        let v = e.u32(pos + 28 + i * 8)?;
                        let n = match t {
                            1 => "clang",
                            2 => "swift",
                            3 => "ld",
                            4 => "lld",
                            _ => "tool",
                        };
                        Some(format!("{n} {}", version(v)))
                    })
                    .collect();
                let b = BuildVersion {
                    platform: platform_name(e.u32(pos + 8).unwrap_or(0)),
                    minos: version(e.u32(pos + 12).unwrap_or(0)),
                    sdk: Some(version(e.u32(pos + 16).unwrap_or(0))),
                    tools,
                };
                let j = serde_json::to_value(&b).unwrap_or(Json::Null);
                out.build_versions.push(b);
                j
            }
            0x24 | 0x25 | 0x2f | 0x30 => {
                let platform = match cmd {
                    0x24 => "macos",
                    0x25 => "ios",
                    0x2f => "tvos",
                    _ => "watchos",
                };
                let b = BuildVersion {
                    platform: platform.into(),
                    minos: version(e.u32(pos + 8).unwrap_or(0)),
                    sdk: Some(version(e.u32(pos + 12).unwrap_or(0))),
                    tools: Vec::new(),
                };
                let j = serde_json::to_value(&b).unwrap_or(Json::Null);
                out.build_versions.push(b);
                j
            }
            0x2a => {
                let v = e.u64(pos + 8).unwrap_or(0);
                let s = format!("{}.{}.{}.{}.{}", v >> 40, (v >> 30) & 0x3ff, (v >> 20) & 0x3ff, (v >> 10) & 0x3ff, v & 0x3ff);
                out.source_version = Some(s.clone());
                json!({"version": s})
            }
            0x21 | 0x2c => {
                let enc = Encryption { cryptoff: e.u32(pos + 8).unwrap_or(0), cryptsize: e.u32(pos + 12).unwrap_or(0), cryptid: e.u32(pos + 16).unwrap_or(0) };
                let j = json!({"cryptoff": enc.cryptoff, "cryptsize": enc.cryptsize, "cryptid": enc.cryptid, "encrypted": enc.cryptid != 0});
                out.encryption = Some(enc);
                j
            }
            0x1d | 0x26 | 0x29 | 0x2b | 0x1e | 0x2e | 0x8000_0033 | 0x8000_0034 => {
                let (off, size) = (e.u32(pos + 8).unwrap_or(0), e.u32(pos + 12).unwrap_or(0));
                if cmd == 0x1d {
                    out.code_signature = Some((off, size));
                }
                json!({"dataoff": off, "datasize": size})
            }
            0x8000_0028 => {
                let off = e.u64(pos + 8);
                out.entry_offset = off;
                json!({"entryoff": off, "stacksize": e.u64(pos + 16)})
            }
            0x2 => json!({"symoff": e.u32(pos + 8), "nsyms": e.u32(pos + 12), "stroff": e.u32(pos + 16), "strsize": e.u32(pos + 20)}),
            0x22 | 0x8000_0022 => json!({
                "rebase_size": e.u32(pos + 12), "bind_size": e.u32(pos + 20), "weak_bind_size": e.u32(pos + 28),
                "lazy_bind_size": e.u32(pos + 36), "export_size": e.u32(pos + 44)
            }),
            0x19 | 0x1 => {
                let wide = cmd == 0x19;
                let segname = e.r.cstr(pos + 8, 16).unwrap_or_default();
                let (vmaddr, vmsize, fileoff, filesize) = if wide {
                    (e.u64(pos + 24), e.u64(pos + 32), e.u64(pos + 40), e.u64(pos + 48))
                } else {
                    (e.u32(pos + 24).map(u64::from), e.u32(pos + 28).map(u64::from), e.u32(pos + 32).map(u64::from), e.u32(pos + 36).map(u64::from))
                };
                let (prot_o, ns_o, sh, shsize) = if wide { (60usize, 64usize, 72usize, 80usize) } else { (44, 48, 56, 68) };
                let initprot = e.u32(pos + prot_o).unwrap_or(0);
                let nsects = e.u32(pos + ns_o).unwrap_or(0) as usize;
                let mut names = Vec::new();
                for i in 0..nsects.min(256) {
                    let o = pos + sh + i * shsize;
                    if o + shsize > pos + sz || out.sections.len() >= MAX_SECTIONS {
                        break;
                    }
                    let (addr, size, offset) = if wide {
                        (e.u64(o + 32), e.u64(o + 40), e.u32(o + 48))
                    } else {
                        (e.u32(o + 32).map(u64::from), e.u32(o + 36).map(u64::from), e.u32(o + 40))
                    };
                    let s = SectionRef {
                        segname: e.r.cstr(o + 16, 16).unwrap_or_default(),
                        sectname: e.r.cstr(o, 16).unwrap_or_default(),
                        addr: addr.unwrap_or(0),
                        size: size.unwrap_or(0),
                        offset: offset.unwrap_or(0),
                    };
                    names.push(s.sectname.clone());
                    out.sections.push(s);
                }
                let prot =
                    |p: u32| format!("{}{}{}", if p & 1 != 0 { "r" } else { "-" }, if p & 2 != 0 { "w" } else { "-" }, if p & 4 != 0 { "x" } else { "-" });
                let j = json!({
                    "segname": segname, "vmaddr": vmaddr.map(|v| format!("{v:#x}")), "vmsize": vmsize, "fileoff": fileoff,
                    "filesize": filesize, "initprot": prot(initprot), "sections": names,
                });
                out.segments.push(j.clone());
                j
            }
            _ => Json::Null,
        };
        out.commands.push(LoadCommand { index, cmd: name, offset: pos, size, detail });
        pos = match pos.checked_add(sz) {
            Some(p) => p,
            None => break,
        };
    }
    if pos > limit {
        out.warnings.push("load commands run past sizeofcmds".into());
    }
    Ok(out)
}

impl MachoDeps {
    /// The file bytes of a section, by segment and section name.
    pub fn section_bytes<'a>(&self, data: &'a [u8], seg: &str, sect: &str) -> Option<&'a [u8]> {
        let s = self.sections.iter().find(|s| s.segname == seg && s.sectname == sect)?;
        let off = s.offset as usize;
        data.get(off..off.checked_add(usize::try_from(s.size).ok()?)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn reads_load_commands() {
        let m = fx::macho_signed();
        let d = parse_thin(&m).unwrap();
        assert_eq!(d.header.arch, "x86_64");
        assert_eq!(d.header.filetype_name, "execute");
        assert!(d.header.flag_names.contains(&"PIE"));
        assert!(d.dylibs.iter().any(|l| l.name == "/usr/lib/libSystem.B.dylib"));
        assert!(d.dylibs.iter().any(|l| l.kind == "weak" && l.name == "@rpath/Extras.framework/Extras"));
        assert_eq!(d.rpaths, vec!["@executable_path/../Frameworks"]);
        assert_eq!(d.uuid.as_deref(), Some("00112233-4455-6677-8899-AABBCCDDEEFF"));
        assert_eq!(d.build_versions[0].platform, "macos");
        assert_eq!(d.build_versions[0].minos, "13.0.0");
        assert!(d.code_signature.is_some());
        assert!(d.sections.iter().any(|s| s.sectname == "__text"));
        let sl = slices(&fx::macho_universal()).unwrap();
        assert_eq!(sl.len(), 2);
        assert_eq!(pick_slice(&sl, Some("arm64e")).unwrap().arch, "arm64");
        assert!(pick_slice(&sl, Some("i386")).is_none());
        let plist = fx::macho_with_info_plist();
        let d = parse_thin(&plist).unwrap();
        let b = d.section_bytes(&plist, "__TEXT", "__info_plist").unwrap();
        assert!(b.starts_with(b"<?xml"));
    }

    #[test]
    fn hostile_inputs() {
        for s in [fx::macho_signed(), fx::macho_with_info_plist()] {
            for m in craft_anything_testkit::mutations(&s) {
                let _ = parse_thin(&m);
                let _ = slices(&m);
            }
            for i in 0..200.min(s.len()) {
                let _ = parse_thin(&s[..i]);
            }
        }
        for seed in 0..100 {
            let mut n = vec![0xcf, 0xfa, 0xed, 0xfe];
            n.extend(craft_anything_testkit::noise(seed, 300));
            let _ = parse_thin(&n);
            n[..4].copy_from_slice(&[0xfe, 0xed, 0xfa, 0xce]);
            let _ = parse_thin(&n);
        }
    }
}
