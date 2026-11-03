//! Unity Texture2D objects: where a picture's pixels are, and turning them into RGBA.
//!
//! The fields after the name, in order, by Unity version (observed on games built with Unity
//! 2017.4 through 6000.0, without type trees):
//! - a fallback format (2017.3 up to 6000, where it went), a downscale flag, from 2020.2 an
//!   "alpha optional" flag, aligned to 4;
//! - width, height, the image size, from 2020.1 the number of stripped mips, the pixel format and
//!   the mip count;
//! - flags (readable; from 2020.1 preprocessed; from 2019.3 ignore the mip limit; from 2018.2
//!   streaming mips), aligned; from 2022.2 the mipmap limit group's name and one more 4-byte
//!   field; from 2018.2 the streaming priority (it can be negative);
//! - the image count, the dimension (2 for a plain texture), six sampling settings, the lightmap
//!   format and the colour space;
//! - from 2020.2 a platform blob;
//! - the pixels when they're inside the object, else where they're streamed from: an offset (64
//!   bits from 2020.1), a size and a file path (a `.resS` file, or `archive:/…` inside a bundle).
//!
//! The result is checked (a 2D texture, at least one image, a sensible size) so a layout this
//! module doesn't know is refused rather than read wrong. Pixel rows are stored bottom first.

use crate::common::FormatError;
use crate::pixels::{self, Layout};
use crate::unity_serialized::{Cur, version_numbers};
use serde::Serialize;

/// The oldest Unity version whose texture layout is read.
pub const MIN_VERSION: (u32, u32) = (2017, 3);
/// The largest picture side accepted.
const MAX_SIDE: i32 = 16384;

/// Where streamed pixels are.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct StreamRef {
    pub path: String,
    pub offset: u64,
    pub size: u32,
}

/// A texture's description.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Texture {
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub format: i32,
    pub mip_count: i32,
    /// The pixels when they're inside the object: where they start in its bytes, and how many.
    #[serde(skip)]
    pub inline: Option<(usize, usize)>,
    /// Where the pixels are when they're streamed from another file.
    pub stream: Option<StreamRef>,
}

fn string(c: &mut Cur, what: &str) -> Result<String, FormatError> {
    let n = c.count(what, 1)?;
    let s = String::from_utf8_lossy(c.take(n, what)?).into_owned();
    c.align4()?;
    Ok(s)
}

/// Read a Texture2D object's bytes (`object`), from a file written by `unity_version`.
pub fn parse(object: &[u8], unity_version: &str, big_endian: bool) -> Result<Texture, FormatError> {
    let v = version_numbers(unity_version).ok_or_else(|| FormatError::Malformed(format!("Unity version {unity_version:?}")))?;
    if v < MIN_VERSION {
        return Err(FormatError::Unsupported(format!("textures from Unity {unity_version} (before 2017.3)")));
    }
    let at = |major: u32, minor: u32| v >= (major, minor);
    let unknown = || FormatError::Unsupported(format!("this texture's layout (Unity {unity_version}) isn't one that's read here"));
    let mut c = Cur { data: object, pos: 0, big: big_endian };
    let name = string(&mut c, "name")?;
    if !at(6000, 0) {
        c.i32("fallback format")?;
    }
    c.u8("downscale fallback")?;
    if at(2020, 2) {
        c.u8("alpha channel optional")?;
    }
    c.align4()?;
    let (width, height) = (c.i32("width")?, c.i32("height")?);
    c.i32("image size")?;
    if at(2020, 1) {
        c.i32("mips stripped")?;
    }
    let format = c.i32("format")?;
    let mip_count = c.i32("mip count")?;
    let flags = 1 + usize::from(at(2020, 1)) + usize::from(at(2019, 3)) + usize::from(at(2018, 2));
    c.take(flags, "flags")?;
    c.align4()?;
    if at(2022, 2) {
        string(&mut c, "mipmap limit group")?;
        c.i32("2022.2 field")?;
    }
    if at(2018, 2) {
        c.i32("streaming priority")?;
    }
    let (images, dimension) = (c.i32("image count")?, c.i32("dimension")?);
    if width == 0 || height == 0 {
        return Err(FormatError::Unsupported(format!("an empty texture ({width}×{height}; the game fills it while it runs)")));
    }
    if images < 1 || dimension != 2 || !(1..=MAX_SIDE).contains(&width) || !(1..=MAX_SIDE).contains(&height) {
        return Err(unknown());
    }
    // Filter mode, anisotropy, mip bias and three wrap modes; the lightmap format; the colour space.
    c.take(6 * 4 + 4 + 4, "texture settings")?;
    if at(2020, 2) {
        let n = c.count("platform blob", 1)?;
        c.take(n, "platform blob")?;
        c.align4()?;
    }
    let size = c.count("image data", 1)?;
    let start = c.pos;
    c.take(size, "image data")?;
    c.align4()?;
    let offset = if at(2020, 1) { c.u64("stream offset")? } else { u64::from(c.u32("stream offset")?) };
    let stream_size = c.u32("stream size")?;
    let path = string(&mut c, "stream path")?;
    let stream = (stream_size > 0 && !path.is_empty()).then_some(StreamRef { path, offset, size: stream_size });
    let inline = (size > 0).then_some((start, size));
    if inline.is_none() && stream.is_none() {
        return Err(unknown());
    }
    Ok(Texture { name, width: width.unsigned_abs(), height: height.unsigned_abs(), format, mip_count, inline, stream })
}

/// Pixel formats by id.
const FORMATS: &[(i32, &str)] = &[
    (1, "Alpha8"),
    (2, "ARGB4444"),
    (3, "RGB24"),
    (4, "RGBA32"),
    (5, "ARGB32"),
    (7, "RGB565"),
    (9, "R16"),
    (10, "DXT1"),
    (12, "DXT5"),
    (13, "RGBA4444"),
    (14, "BGRA32"),
    (15, "RHalf"),
    (16, "RGHalf"),
    (17, "RGBAHalf"),
    (18, "RFloat"),
    (19, "RGFloat"),
    (20, "RGBAFloat"),
    (24, "BC6H"),
    (25, "BC7"),
    (26, "BC4"),
    (27, "BC5"),
    (28, "DXT1Crunched"),
    (29, "DXT5Crunched"),
    (62, "RG16"),
    (63, "R8"),
];

/// A pixel format's name, or `format <id>`.
pub fn format_name(id: i32) -> String {
    FORMATS.iter().find(|(f, _)| *f == id).map_or_else(|| format!("format {id}"), |(_, n)| (*n).to_string())
}

/// How a Unity pixel format is laid out, for the formats that are decoded.
fn layout(format: i32) -> Option<Layout> {
    Some(match format {
        1 => Layout::Alpha8,
        2 => Layout::Argb4444,
        3 => Layout::Rgb24,
        4 => Layout::Rgba32,
        5 => Layout::Argb32,
        7 => Layout::Rgb565,
        10 => Layout::Dxt1,
        12 => Layout::Dxt5,
        13 => Layout::Rgba4444,
        14 => Layout::Bgra32,
        24 => Layout::Bc6h,
        25 => Layout::Bc7,
        26 => Layout::Bc4,
        27 => Layout::Bc5,
        63 => Layout::R8,
        _ => return None,
    })
}

/// Bytes of the full-size picture (the first mip) in `format`, or None for a format not decoded.
pub fn mip0_size(format: i32, width: u32, height: u32) -> Option<usize> {
    pixels::size(layout(format)?, width, height)
}

/// Decode the full-size picture (`data` starts with it) into RGBA, top row first.
pub fn decode(format: i32, width: u32, height: u32, data: &[u8]) -> Result<Vec<u8>, FormatError> {
    let layout = layout(format).ok_or_else(|| FormatError::Unsupported(format!("{} textures", format_name(format))))?;
    // Stored bottom row first; pictures are read top row first.
    Ok(pixels::flip_rows(&pixels::decode(layout, width, height, data)?, width))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_texture_layouts_from_2017_to_unity_6() {
        for version in ["2017.4.9f1", "2018.4.36f1", "2019.4.21f1", "2020.3.39f1", "2022.3.62f2", "6000.0.59f2"] {
            let inline = craft_anything_testkit::games::unity_texture2d(version, "Checker", 2, 2, 4, Some(&[1; 16]), None);
            let t = parse(&inline, version, false).unwrap_or_else(|e| panic!("{version}: {e}"));
            assert_eq!((t.name.as_str(), t.width, t.height, t.format, t.stream.clone()), ("Checker", 2, 2, 4, None), "{version}");
            let (start, len) = t.inline.unwrap();
            assert_eq!(&inline[start..start + len], &[1; 16]);
            let streamed = craft_anything_testkit::games::unity_texture2d(version, "Block", 4, 4, 10, None, Some(("sharedassets0.assets.resS", 64, 8)));
            let t = parse(&streamed, version, false).unwrap();
            assert_eq!(t.stream, Some(StreamRef { path: "sharedassets0.assets.resS".into(), offset: 64, size: 8 }), "{version}");
        }
        let old = craft_anything_testkit::games::unity_texture2d("2017.4.9f1", "x", 2, 2, 4, Some(&[0; 16]), None);
        assert!(matches!(parse(&old, "5.6.7f1", false), Err(FormatError::Unsupported(_))));
        // A layout read wrong (here: as Unity 6) is refused, not misread.
        assert!(parse(&old, "6000.0.1f1", false).is_err());
        for cut in 0..old.len() {
            let _ = parse(&old[..cut], "2017.4.9f1", false);
        }
    }

    #[test]
    fn decodes_pixels_top_row_first() {
        // 1×2 RGBA32: the stored first row is the bottom one.
        assert_eq!(decode(4, 1, 2, &[1, 2, 3, 4, 5, 6, 7, 8]).unwrap(), [5, 6, 7, 8, 1, 2, 3, 4]);
        assert_eq!(decode(5, 1, 1, &[9, 1, 2, 3]).unwrap(), [1, 2, 3, 9], "ARGB");
        assert_eq!(decode(14, 1, 1, &[3, 2, 1, 9]).unwrap(), [1, 2, 3, 9], "BGRA");
        assert_eq!(decode(3, 1, 1, &[1, 2, 3]).unwrap(), [1, 2, 3, 255]);
        assert_eq!(decode(1, 1, 1, &[7]).unwrap(), [255, 255, 255, 7]);
        assert_eq!(decode(7, 1, 1, &0xf800u16.to_le_bytes()).unwrap(), [255, 0, 0, 255], "RGB565 red");
        // DXT1: colour 0 red, colour 1 blue, every texel index 0 except the first (index 1).
        let block = [0x00, 0xf8, 0x1f, 0x00, 0b01, 0, 0, 0];
        let px = decode(10, 4, 4, &block).unwrap();
        assert_eq!(&px[..4], &[255, 0, 0, 255], "top-left is stored row 3: index 0, red");
        assert_eq!(&px[48..52], &[0, 0, 255, 255], "bottom-left is the block's first texel: blue");
        // DXT5: alpha 255 → 0 over 8 steps; first texel index 1 (alpha 0), the rest index 0 (255).
        let mut block5 = vec![255, 0, 1, 0, 0, 0, 0, 0];
        block5.extend_from_slice(&[0x00, 0xf8, 0x1f, 0x00, 0, 0, 0, 0]);
        let px = decode(12, 4, 4, &block5).unwrap();
        assert_eq!((px[3], px[48 + 3]), (255, 0));
        // A 5×5 DXT1 picture needs 4 blocks and is cropped.
        assert_eq!(decode(10, 5, 5, &[0; 32]).unwrap().len(), 5 * 5 * 4);
        // BC7 and BC6H (Unity's is unsigned): a reserved block is all zero, and black.
        assert_eq!(decode(25, 4, 4, &[0; 16]).unwrap(), [0; 64]);
        assert!(decode(24, 4, 4, &[0b11111, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]).unwrap().as_chunks::<4>().0.iter().all(|p| *p == [0, 0, 0, 255]));
        assert!(matches!(decode(28, 4, 4, &[0; 16]), Err(FormatError::Unsupported(m)) if m.contains("DXT1Crunched")));
        assert!(matches!(decode(4, 2, 2, &[0; 15]), Err(FormatError::Truncated(_))));
    }
}
