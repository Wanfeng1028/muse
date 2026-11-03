//! Unreal Engine 4 cooked textures: a package's `.uasset` (summary, names, imports, exports) and
//! a Texture2D export's data (in the `.uexp`), with its mips inline or in a `.ubulk`/`.uptnl`.
//!
//! Read as observed in games cooked with Unreal 4.26–4.27 (package file version -7, versioned or
//! not):
//! - the summary: tag, version numbers, custom versions, the header size (where the `.uexp`'s
//!   bytes start in the combined file), folder name, package flags, the name table, gatherable
//!   text, the export and import tables;
//! - a name: a string and two 16-bit hashes; an import: 28 bytes; an export: 104 bytes, with the
//!   serial size and offset of its data;
//! - a Texture2D export's data: tagged properties (name, type, size, index, a type-specific
//!   header, an optional guid, the value) until `None`; a guid flag; two strip-flag pairs; the
//!   cooked flag; then for each pixel format: its name, a 64-bit skip offset, the full size, the
//!   slice count, the format string, the first mip and the mips: each a cooked flag, bulk data (flags,
//!   count, size on disk, offset — 64-bit counts with flag 0x2000; the bytes follow unless the
//!   payload is elsewhere) and its own size; then a "virtual" flag and the next format name.
//!
//! Packages written without property names (unversioned properties) and Unreal 5 packages are
//! refused: reading them needs the game's own type layouts.

use crate::common::FormatError;
use crate::pixels::Layout;
use serde::Serialize;

/// Longest string accepted.
const MAX_STRING: usize = 4096;
/// Package flag: properties are written without names.
const UNVERSIONED_PROPERTIES: u32 = 0x2000;
/// Package flag: editor-only data was left out (every cooked package).
const EDITOR_ONLY_FILTERED: u32 = 0x8000_0000;
/// Bulk data flags.
const PAYLOAD_AT_END: u32 = 0x1;
const ZLIB: u32 = 0x2;
const UNUSED: u32 = 0x20;
const SEPARATE_FILE: u32 = 0x100;
const OPTIONAL: u32 = 0x800;
const SIZE_64: u32 = 0x2000;

/// One export.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Export {
    pub name: String,
    /// Its class's name (`Texture2D`, `Material`, …).
    pub class: String,
    /// Where its data is in the `.uasset` and `.uexp` taken as one file, and how long.
    pub serial_offset: u64,
    pub serial_size: u64,
}

/// What a package's `.uasset` says.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Package {
    /// The `.uasset`'s length: the `.uexp`'s bytes count from here.
    pub header_size: u64,
    pub names: Vec<String>,
    pub exports: Vec<Export>,
}

/// Where a mip's pixels are.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub enum MipData {
    /// In the export's own bytes: (start, length).
    Inline(usize, usize),
    /// In the package's `.ubulk` or `.uptnl` (`extension`), at an offset.
    File { extension: &'static str, offset: u64, length: u64 },
    /// Not stored here (stripped, compressed or unused).
    Missing,
}

/// One mip level.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Mip {
    pub width: u32,
    pub height: u32,
    pub data: MipData,
}

/// A Texture2D export.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Texture {
    /// The full size (the largest mip stored can be smaller when the game was cooked with a bias).
    pub width: u32,
    pub height: u32,
    /// Unreal's pixel format, e.g. `PF_DXT5`.
    pub pixel_format: String,
    pub mips: Vec<Mip>,
}

/// A bounds-checked little-endian cursor.
struct Cur<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> Cur<'a> {
    fn take(&mut self, n: usize, what: &str) -> Result<&'a [u8], FormatError> {
        let end = self.pos.checked_add(n).filter(|e| *e <= self.data.len()).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
        let s = self.data.get(self.pos..end).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
        self.pos = end;
        Ok(s)
    }
    fn arr<const N: usize>(&mut self, what: &str) -> Result<[u8; N], FormatError> {
        let mut a = [0; N];
        a.copy_from_slice(self.take(N, what)?);
        Ok(a)
    }
    fn u8(&mut self, what: &str) -> Result<u8, FormatError> {
        Ok(self.arr::<1>(what)?[0])
    }
    fn i32(&mut self, what: &str) -> Result<i32, FormatError> {
        Ok(i32::from_le_bytes(self.arr(what)?))
    }
    fn u32(&mut self, what: &str) -> Result<u32, FormatError> {
        Ok(u32::from_le_bytes(self.arr(what)?))
    }
    fn i64(&mut self, what: &str) -> Result<i64, FormatError> {
        Ok(i64::from_le_bytes(self.arr(what)?))
    }
    /// A non-negative count that fits what's left (`min_each` bytes each).
    fn count(&mut self, what: &str, min_each: usize) -> Result<usize, FormatError> {
        let n = usize::try_from(self.i32(what)?).map_err(|_| FormatError::Malformed(format!("negative {what}")))?;
        if n.saturating_mul(min_each.max(1)) > self.data.len().saturating_sub(self.pos) {
            return Err(FormatError::Malformed(format!("{what} {n} doesn't fit")));
        }
        Ok(n)
    }
    /// An `FString`: a signed length with its terminating NUL; negative means UTF-16.
    fn string(&mut self, what: &str) -> Result<String, FormatError> {
        let n = self.i32(what)?;
        let chars = n.unsigned_abs() as usize;
        if chars > MAX_STRING {
            return Err(FormatError::Malformed(format!("{what} is {chars} characters long")));
        }
        let s = if n >= 0 {
            String::from_utf8_lossy(self.take(chars, what)?).into_owned()
        } else {
            String::from_utf16_lossy(&self.take(chars * 2, what)?.as_chunks::<2>().0.iter().map(|c| u16::from_le_bytes(*c)).collect::<Vec<_>>())
        };
        Ok(s.trim_end_matches('\0').to_string())
    }
}

/// A name-table entry by index (the name's number is ignored).
fn name<'n>(names: &'n [String], c: &mut Cur, what: &str) -> Result<&'n str, FormatError> {
    let i = c.i32(what)?;
    c.i32(what)?;
    usize::try_from(i).ok().and_then(|i| names.get(i)).map(String::as_str).ok_or_else(|| FormatError::Malformed(format!("{what} names entry {i}")))
}

/// Read a cooked package's `.uasset`.
pub fn package(uasset: &[u8]) -> Result<Package, FormatError> {
    let mut c = Cur { data: uasset, pos: 0 };
    if c.u32("tag")? != 0x9E2A_83C1 {
        return Err(FormatError::Malformed("not an Unreal package".into()));
    }
    let legacy = c.i32("legacy version")?;
    match legacy {
        -7 => {}
        -8 | -9 => return Err(FormatError::Unsupported("Unreal 5 packages".into())),
        v => return Err(FormatError::Unsupported(format!("Unreal packages of file version {v} (before Unreal 4.26)"))),
    }
    c.i32("UE3 version")?;
    c.i32("UE4 version")?;
    c.i32("licensee version")?;
    let customs = c.count("custom versions", 20)?;
    c.take(customs * 20, "custom versions")?;
    let header_size = u64::try_from(c.i32("header size")?).map_err(|_| FormatError::Malformed("negative header size".into()))?;
    c.string("folder name")?;
    let flags = c.u32("package flags")?;
    if flags & UNVERSIONED_PROPERTIES != 0 {
        return Err(FormatError::Unsupported("packages written without property names (unversioned properties)".into()));
    }
    let (name_count, name_offset) = (c.count("names", 9)?, c.i32("name offset")?);
    if flags & EDITOR_ONLY_FILTERED == 0 {
        c.string("localization id")?;
    }
    c.i64("gatherable text")?;
    let (export_count, export_offset) = (c.count("exports", 104)?, c.i32("export offset")?);
    let (import_count, import_offset) = (c.count("imports", 28)?, c.i32("import offset")?);
    let at = |offset: i32, what: &str| {
        usize::try_from(offset).ok().filter(|o| *o <= uasset.len()).ok_or_else(|| FormatError::Malformed(format!("{what} offset {offset}")))
    };

    let mut c = Cur { data: uasset, pos: at(name_offset, "name")? };
    let mut names = Vec::with_capacity(name_count);
    for _ in 0..name_count {
        names.push(c.string("name")?);
        c.take(4, "name hashes")?;
    }
    let mut c = Cur { data: uasset, pos: at(import_offset, "import")? };
    let mut imports = Vec::with_capacity(import_count);
    for _ in 0..import_count {
        c.take(16, "import class")?;
        c.i32("import outer")?;
        imports.push(name(&names, &mut c, "import name")?.to_string());
    }
    let mut c = Cur { data: uasset, pos: at(export_offset, "export")? };
    let mut exports = Vec::with_capacity(export_count);
    for _ in 0..export_count {
        let class = c.i32("export class")?;
        c.take(12, "export super, template and outer")?;
        let export_name = name(&names, &mut c, "export name")?.to_string();
        c.u32("object flags")?;
        let serial_size = u64::try_from(c.i64("serial size")?).map_err(|_| FormatError::Malformed("negative serial size".into()))?;
        let serial_offset = u64::try_from(c.i64("serial offset")?).map_err(|_| FormatError::Malformed("negative serial offset".into()))?;
        c.take(104 - 44, "export flags and dependencies")?;
        // A negative class is an import: -1 is the first.
        let class = usize::try_from(-i64::from(class) - 1).ok().and_then(|i| imports.get(i)).cloned().unwrap_or_default();
        exports.push(Export { name: export_name, class, serial_offset, serial_size });
    }
    Ok(Package { header_size, names, exports })
}

/// Skip the tagged properties up to `None`.
fn skip_properties(c: &mut Cur, names: &[String]) -> Result<(), FormatError> {
    for _ in 0..10_000 {
        let property = name(names, c, "property name")?;
        if property == "None" {
            return Ok(());
        }
        let kind = name(names, c, "property type")?;
        let size = c.count("property size", 1).map_err(|_| FormatError::Malformed(format!("{property}'s size")))?;
        c.i32("array index")?;
        let header = match kind {
            "StructProperty" => 8 + 16,
            "BoolProperty" => 1,
            "ByteProperty" | "EnumProperty" | "ArrayProperty" | "SetProperty" => 8,
            "MapProperty" => 16,
            _ => 0,
        };
        c.take(header, "property header")?;
        if c.u8("property guid flag")? != 0 {
            c.take(16, "property guid")?;
        }
        c.take(size, "property value")?;
    }
    Err(FormatError::Malformed("too many properties".into()))
}

/// Read a Texture2D export's data (`data`: its `serial_size` bytes).
pub fn texture(data: &[u8], names: &[String]) -> Result<Texture, FormatError> {
    let mut c = Cur { data, pos: 0 };
    skip_properties(&mut c, names)?;
    if c.i32("guid flag")? != 0 {
        c.take(16, "guid")?;
    }
    c.take(4, "strip flags")?;
    if c.i32("cooked")? == 0 {
        return Err(FormatError::Unsupported("an editor (uncooked) texture".into()));
    }
    let format_name = name(names, &mut c, "pixel format name")?;
    if format_name == "None" {
        return Err(FormatError::Malformed("no platform data".into()));
    }
    c.i64("skip offset")?;
    let (width, height) = (c.i32("width")?, c.i32("height")?);
    let packed = c.u32("slices")?;
    let pixel_format = c.string("pixel format")?;
    if packed & (1 << 30) != 0 {
        c.take(8, "optional data")?;
    }
    c.i32("first mip")?;
    let count = c.count("mips", 28)?;
    let mut mips = Vec::with_capacity(count);
    for _ in 0..count {
        c.i32("mip cooked")?;
        let flags = c.u32("bulk flags")?;
        let (_, on_disk) = if flags & SIZE_64 != 0 {
            (c.i64("element count")?, c.i64("size on disk")?)
        } else {
            (i64::from(c.i32("element count")?), i64::from(c.i32("size on disk")?))
        };
        let offset = c.i64("bulk offset")?;
        let on_disk = u64::try_from(on_disk).map_err(|_| FormatError::Malformed("negative mip size".into()))?;
        let elsewhere = flags & (PAYLOAD_AT_END | SEPARATE_FILE | UNUSED) != 0;
        let mut data = MipData::Missing;
        if !elsewhere {
            let start = c.pos;
            c.take(on_disk as usize, "mip pixels")?;
            if flags & ZLIB == 0 {
                data = MipData::Inline(start, on_disk as usize);
            }
        } else if flags & SEPARATE_FILE != 0 && flags & (UNUSED | ZLIB) == 0 {
            let extension = if flags & OPTIONAL != 0 { "uptnl" } else { "ubulk" };
            data = MipData::File { extension, offset: u64::try_from(offset).unwrap_or(u64::MAX), length: on_disk };
        }
        let (w, h) = (c.i32("mip width")?, c.i32("mip height")?);
        c.i32("mip depth")?;
        mips.push(Mip { width: w.unsigned_abs(), height: h.unsigned_abs(), data });
    }
    if !(1..=16384).contains(&width) || !(1..=16384).contains(&height) || mips.iter().any(|m| m.width == 0 || m.height == 0) {
        return Err(FormatError::Unsupported("this texture's layout isn't one that's read here".into()));
    }
    Ok(Texture { width: width.unsigned_abs(), height: height.unsigned_abs(), pixel_format, mips })
}

/// How an Unreal pixel format is laid out, for the formats that are decoded.
pub fn layout(pixel_format: &str) -> Option<Layout> {
    Some(match pixel_format {
        "PF_B8G8R8A8" => Layout::Bgra32,
        "PF_R8G8B8A8" => Layout::Rgba32,
        "PF_G8" | "PF_L8" => Layout::R8,
        "PF_A8" => Layout::Alpha8,
        "PF_DXT1" => Layout::Dxt1,
        "PF_DXT5" => Layout::Dxt5,
        "PF_BC4" => Layout::Bc4,
        "PF_BC5" => Layout::Bc5,
        "PF_BC6H" => Layout::Bc6h,
        "PF_BC7" => Layout::Bc7,
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::games::unreal_texture_package;

    #[test]
    fn reads_a_cooked_texture_package() {
        let (uasset, uexp) = unreal_texture_package("T_Icon", "PF_B8G8R8A8", 2, 2, &[1; 16], Some((4, 4, 64)));
        let p = package(&uasset).unwrap();
        assert_eq!(p.header_size, uasset.len() as u64);
        assert_eq!(p.exports.len(), 1);
        let e = &p.exports[0];
        assert_eq!((e.name.as_str(), e.class.as_str()), ("T_Icon", "Texture2D"));
        let start = (e.serial_offset - p.header_size) as usize;
        let t = texture(&uexp[start..start + e.serial_size as usize], &p.names).unwrap();
        assert_eq!((t.width, t.height, t.pixel_format.as_str()), (4, 4, "PF_B8G8R8A8"));
        assert_eq!(t.mips[0], Mip { width: 4, height: 4, data: MipData::File { extension: "ubulk", offset: 0, length: 64 } });
        let MipData::Inline(s, n) = t.mips[1].data else { panic!("{:?}", t.mips[1]) };
        assert_eq!((t.mips[1].width, &uexp[start + s..start + s + n]), (2, &[1u8; 16][..]));
        assert_eq!(layout(&t.pixel_format), Some(Layout::Bgra32));
        assert_eq!((layout("PF_BC7"), layout("PF_BC6H"), layout("PF_ASTC_4x4")), (Some(Layout::Bc7), Some(Layout::Bc6h), None));
    }

    #[test]
    fn refuses_what_it_cannot_read() {
        let (uasset, uexp) = unreal_texture_package("T", "PF_DXT1", 4, 4, &[0; 8], None);
        let mut ue5 = uasset.clone();
        ue5[4..8].copy_from_slice(&(-8i32).to_le_bytes());
        assert!(matches!(package(&ue5), Err(FormatError::Unsupported(m)) if m.contains("Unreal 5")));
        let mut old = uasset.clone();
        old[4..8].copy_from_slice(&(-6i32).to_le_bytes());
        assert!(matches!(package(&old), Err(FormatError::Unsupported(_))));
        assert!(package(b"not a package").is_err());
        for cut in 0..uasset.len() {
            let _ = package(&uasset[..cut]);
        }
        let p = package(&uasset).unwrap();
        let start = (p.exports[0].serial_offset - p.header_size) as usize;
        let data = &uexp[start..];
        for cut in 0..data.len() {
            let _ = texture(&data[..cut], &p.names);
        }
    }
}
