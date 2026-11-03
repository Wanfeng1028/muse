//! Firmware images: a signature scan that recognises common containers, compression streams,
//! filesystems, boot images and executables (each hit checked against its header so random
//! bytes rarely match), an entropy map, and a layout summary (what is covered, the gaps, and
//! high-entropy spans nothing explains). Also streaming gzip/zlib inflation with output caps.
//!
//! Pure and bounded: no I/O, no panics, every offset and length from the input is checked.

use crate::bytes::Reader;
use crate::common::entropy;
use miniz_oxide::inflate::stream::{InflateState, inflate as mz_inflate};
use miniz_oxide::{DataFormat, MZError, MZFlush, MZStatus};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Largest input the scanner accepts.
pub const MAX_INPUT: u64 = 512 << 20;

// ---------------------------------------------------------------------------------------------
// Checksums

const fn crc_table() -> [u32; 256] {
    let mut t = [0u32; 256];
    let mut i = 0;
    while i < 256 {
        let mut c = i as u32;
        let mut k = 0;
        while k < 8 {
            c = if c & 1 != 0 { 0xedb8_8320 ^ (c >> 1) } else { c >> 1 };
            k += 1;
        }
        t[i] = c;
        i += 1;
    }
    t
}

static CRC_TABLE: [u32; 256] = crc_table();

/// Raw reflected CRC-32 update (no pre/post inversion). `crc32` = `!crc32_raw(!0, data)`.
pub fn crc32_raw(mut crc: u32, data: &[u8]) -> u32 {
    for &b in data {
        let idx = ((crc ^ u32::from(b)) & 0xff) as usize;
        crc = CRC_TABLE.get(idx).copied().unwrap_or(0) ^ (crc >> 8);
    }
    crc
}

/// CRC-32 (IEEE, as in gzip, ZIP and PNG).
pub fn crc32(data: &[u8]) -> u32 {
    !crc32_raw(!0, data)
}

/// Big-endian (non-reflected) CRC-32 is not needed; xxHash32 is, for LZ4 frame headers.
fn xxh32(data: &[u8], seed: u32) -> u32 {
    const P1: u32 = 2_654_435_761;
    const P2: u32 = 2_246_822_519;
    const P3: u32 = 3_266_489_917;
    const P4: u32 = 668_265_263;
    const P5: u32 = 374_761_393;
    let r = Reader::new(data);
    let round = |acc: u32, v: u32| acc.wrapping_add(v.wrapping_mul(P2)).rotate_left(13).wrapping_mul(P1);
    let len = data.len();
    let mut i = 0usize;
    let mut h = if len >= 16 {
        let (mut v1, mut v2, mut v3, mut v4) = (seed.wrapping_add(P1).wrapping_add(P2), seed.wrapping_add(P2), seed, seed.wrapping_sub(P1));
        while i + 16 <= len {
            v1 = round(v1, r.u32_le(i).unwrap_or(0));
            v2 = round(v2, r.u32_le(i + 4).unwrap_or(0));
            v3 = round(v3, r.u32_le(i + 8).unwrap_or(0));
            v4 = round(v4, r.u32_le(i + 12).unwrap_or(0));
            i += 16;
        }
        v1.rotate_left(1).wrapping_add(v2.rotate_left(7)).wrapping_add(v3.rotate_left(12)).wrapping_add(v4.rotate_left(18))
    } else {
        seed.wrapping_add(P5)
    };
    h = h.wrapping_add(len as u32);
    while i + 4 <= len {
        h = h.wrapping_add(r.u32_le(i).unwrap_or(0).wrapping_mul(P3)).rotate_left(17).wrapping_mul(P4);
        i += 4;
    }
    while i < len {
        h = h.wrapping_add(u32::from(r.u8(i).unwrap_or(0)).wrapping_mul(P5)).rotate_left(11).wrapping_mul(P1);
        i += 1;
    }
    h ^= h >> 15;
    h = h.wrapping_mul(P2);
    h ^= h >> 13;
    h = h.wrapping_mul(P3);
    h ^= h >> 16;
    h
}

// ---------------------------------------------------------------------------------------------
// Inflation

/// Why inflating stopped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum InflateError {
    #[error("the compressed stream is damaged")]
    Corrupt,
    #[error("the compressed stream ends early")]
    Truncated,
    #[error("the output would exceed the size limit")]
    TooLarge,
}

/// The result of inflating a DEFLATE or zlib stream.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Inflated {
    /// Compressed bytes consumed (including the zlib header and checksum).
    pub consumed: usize,
    pub produced: u64,
    pub crc32: u32,
    /// The output, when asked for.
    pub data: Option<Vec<u8>>,
}

/// Inflate a raw DEFLATE (`zlib = false`) or zlib stream, producing at most `max_out` bytes.
/// zlib checksums are verified. The output is kept only when `keep` is true.
pub fn inflate(input: &[u8], zlib: bool, max_out: u64, keep: bool) -> Result<Inflated, InflateError> {
    let mut state = InflateState::new_boxed(if zlib { DataFormat::Zlib } else { DataFormat::Raw });
    let mut buf = vec![0u8; 64 * 1024];
    let mut pos = 0usize;
    let mut produced = 0u64;
    let mut crc = !0u32;
    let mut kept = Vec::new();
    loop {
        let rest = input.get(pos..).unwrap_or(&[]);
        let res = mz_inflate(&mut state, rest, &mut buf, MZFlush::None);
        pos = pos.saturating_add(res.bytes_consumed);
        let out = buf.get(..res.bytes_written).unwrap_or(&[]);
        produced = produced.saturating_add(out.len() as u64);
        if produced > max_out {
            return Err(InflateError::TooLarge);
        }
        crc = crc32_raw(crc, out);
        if keep {
            kept.extend_from_slice(out);
        }
        match res.status {
            Ok(MZStatus::StreamEnd) => {
                return Ok(Inflated { consumed: pos, produced, crc32: !crc, data: if keep { Some(kept) } else { None } });
            }
            Ok(MZStatus::Ok) => {
                if res.bytes_consumed == 0 && res.bytes_written == 0 {
                    return Err(if pos >= input.len() { InflateError::Truncated } else { InflateError::Corrupt });
                }
            }
            Ok(MZStatus::NeedDict) => return Err(InflateError::Corrupt),
            Err(MZError::Buf) => {
                if res.bytes_written == 0 {
                    return Err(if pos >= input.len() { InflateError::Truncated } else { InflateError::Corrupt });
                }
            }
            Err(_) => return Err(InflateError::Corrupt),
        }
    }
}

/// A parsed gzip member header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct GzipHeader {
    pub header_len: usize,
    pub original_name: Option<String>,
    pub comment: Option<String>,
    pub mtime: u32,
    pub os: u8,
}

/// Parse a gzip member header (`1f 8b 08`, reserved flag bits clear).
pub fn gzip_header(data: &[u8]) -> Option<GzipHeader> {
    let r = Reader::new(data);
    if r.slice(0, 3)? != [0x1f, 0x8b, 8] {
        return None;
    }
    let flg = r.u8(3)?;
    if flg & 0xe0 != 0 {
        return None;
    }
    let mtime = r.u32_le(4)?;
    let xfl = r.u8(8)?;
    let os = r.u8(9)?;
    if !matches!(xfl, 0 | 2 | 4) || (os > 13 && os != 255) {
        return None;
    }
    let mut pos = 10usize;
    if flg & 4 != 0 {
        let xlen = usize::from(r.u16_le(pos)?);
        pos = pos.checked_add(2 + xlen)?;
    }
    let cstring = |pos: &mut usize| -> Option<String> {
        let rest = data.get(*pos..)?;
        let end = rest.iter().take(1024).position(|&b| b == 0)?;
        let s = String::from_utf8_lossy(rest.get(..end)?).into_owned();
        *pos = pos.checked_add(end + 1)?;
        Some(s)
    };
    let original_name = if flg & 8 != 0 { Some(cstring(&mut pos)?) } else { None };
    let comment = if flg & 16 != 0 { Some(cstring(&mut pos)?) } else { None };
    if flg & 2 != 0 {
        pos = pos.checked_add(2)?;
    }
    if pos > data.len() {
        return None;
    }
    Some(GzipHeader { header_len: pos, original_name, comment, mtime, os })
}

/// Decompress one gzip member: (output, bytes consumed including the trailer). The CRC and size
/// in the trailer are checked.
pub fn gunzip(data: &[u8], max_out: u64) -> Result<(Vec<u8>, usize), InflateError> {
    let h = gzip_header(data).ok_or(InflateError::Corrupt)?;
    let body = data.get(h.header_len..).ok_or(InflateError::Truncated)?;
    let inf = inflate(body, false, max_out, true)?;
    let r = Reader::new(data);
    let t = h.header_len.checked_add(inf.consumed).ok_or(InflateError::Corrupt)?;
    let (Some(crc), Some(isize)) = (r.u32_le(t), r.u32_le(t + 4)) else { return Err(InflateError::Truncated) };
    if crc != inf.crc32 || isize != inf.produced as u32 {
        return Err(InflateError::Corrupt);
    }
    Ok((inf.data.unwrap_or_default(), t + 8))
}

// ---------------------------------------------------------------------------------------------
// Regions

/// Broad family of a recognised region.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Family {
    Compression,
    Archive,
    Filesystem,
    BootImage,
    DeviceTree,
    Executable,
    Crypto,
}

/// What extraction can do with a region.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Unpack {
    /// A gzip or zlib stream we can decompress.
    Decompress,
    /// An archive whose members we can list and write (zip, tar, cpio).
    Members,
    /// A wrapper whose payload(s) we can split out (boot images).
    Payload,
    /// A filesystem whose files we can list and extract (see [`crate::fsread`]).
    Filesystem,
    /// Only carved as raw bytes.
    Carve,
}

/// One recognised region.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Region {
    pub offset: u64,
    /// Bytes the region spans, when its format states or implies it (clamped to the input).
    pub length: Option<u64>,
    pub kind: &'static str,
    pub family: Family,
    pub description: String,
    /// `high` when a checksum or full structure walk confirmed it, `medium` for header checks only.
    pub confidence: &'static str,
    pub unpack: Unpack,
    pub details: Value,
}

impl Region {
    pub fn end(&self) -> Option<u64> {
        self.length.and_then(|l| self.offset.checked_add(l))
    }
}

/// Scan limits.
#[derive(Debug, Clone)]
pub struct ScanOptions {
    pub max_regions: usize,
    /// Most header validations attempted per signature (keeps hostile inputs fast).
    pub max_probes_per_kind: usize,
    /// Most bytes inflated in total while measuring gzip/zlib streams.
    pub inflate_budget: u64,
}

impl Default for ScanOptions {
    fn default() -> Self {
        ScanOptions { max_regions: 2000, max_probes_per_kind: 20_000, inflate_budget: 256 << 20 }
    }
}

/// What a scan found.
#[derive(Debug, Clone, Default, PartialEq, Serialize)]
pub struct ScanResult {
    pub regions: Vec<Region>,
    /// True when `max_regions` stopped the scan.
    pub truncated: bool,
    /// True when the caller asked to stop.
    pub cancelled: bool,
    /// Signatures whose probe budget ran out (later hits of them were not checked).
    pub probes_exhausted: Vec<&'static str>,
    pub warnings: Vec<String>,
}

struct Scanner<'a> {
    data: &'a [u8],
    r: Reader<'a>,
    probes: BTreeMap<&'static str, usize>,
    opts: &'a ScanOptions,
    inflate_left: u64,
    exhausted: Vec<&'static str>,
}

#[allow(clippy::too_many_arguments)]
fn reg(
    offset: usize,
    length: Option<u64>,
    kind: &'static str,
    family: Family,
    description: String,
    confidence: &'static str,
    unpack: Unpack,
    details: Value,
) -> Region {
    Region { offset: offset as u64, length, kind, family, description, confidence, unpack, details }
}

/// Clamp a declared length to the available bytes; reports whether it was cut.
fn clamp(declared: u64, off: usize, total: usize) -> (u64, bool) {
    let avail = total.saturating_sub(off) as u64;
    if declared > avail { (avail, true) } else { (declared, false) }
}

fn cstr_field(b: Option<&[u8]>) -> String {
    let b = b.unwrap_or(&[]);
    let end = b.iter().position(|&c| c == 0).unwrap_or(b.len());
    String::from_utf8_lossy(b.get(..end).unwrap_or(&[])).trim().to_string()
}

impl<'a> Scanner<'a> {
    /// Count one probe of `kind`; false once its budget is spent.
    fn probe(&mut self, kind: &'static str) -> bool {
        let n = self.probes.entry(kind).or_insert(0);
        *n += 1;
        if *n > self.opts.max_probes_per_kind {
            if !self.exhausted.contains(&kind) {
                self.exhausted.push(kind);
            }
            return false;
        }
        true
    }

    fn at(&self, i: usize, m: &[u8]) -> bool {
        self.r.slice(i, m.len()) == Some(m)
    }

    fn try_at(&mut self, i: usize) -> Option<Region> {
        let b = self.r.u8(i)?;
        match b {
            0x1f if self.at(i, &[0x1f, 0x8b, 8]) => self.gzip(i),
            0x78 => self.zlib(i),
            0xfd if self.at(i, b"\xfd7zXZ\0") => self.xz(i),
            0x5d => self.lzma(i),
            b'B' if self.at(i, b"BZh") => self.bzip2(i),
            0x28 if self.at(i, &[0x28, 0xb5, 0x2f, 0xfd]) => self.zstd(i),
            0x28 if self.at(i, &[0x28, 0xcd, 0x3d, 0x45]) => self.cramfs(i, true),
            0x45 if self.at(i, &[0x45, 0x3d, 0xcd, 0x28]) => self.cramfs(i, false),
            0x04 if self.at(i, &[0x04, 0x22, 0x4d, 0x18]) => self.lz4(i),
            b'P' if self.at(i, b"PK\x03\x04") => self.zip(i),
            b'7' if self.at(i, &[0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]) => self.sevenz(i),
            b'R' if self.at(i, b"Rar!\x1a\x07") => self.rar(i),
            b'M' if self.at(i, b"MSCF") => self.cab(i),
            b'M' if self.at(i, b"MZ") => self.pe(i),
            b'0' if self.at(i, b"07070") => self.cpio(i),
            b'h' if self.at(i, b"hsqs") => self.squashfs(i, false),
            b's' if self.at(i, b"sqsh") => self.squashfs(i, true),
            b'-' if self.at(i, b"-rom1fs-") => self.romfs(i),
            b'-' if self.at(i, b"-----BEGIN ") => self.pem(i),
            0x85 if self.at(i, &[0x85, 0x19]) => self.jffs2(i, false),
            0x19 if self.at(i, &[0x19, 0x85]) => self.jffs2(i, true),
            b'U' if self.at(i, b"UBI#") => self.ubi(i),
            0x31 if self.at(i, &[0x31, 0x18, 0x10, 0x06]) => self.ubifs(i),
            0xeb | 0xe9 if i.is_multiple_of(512) => self.fat(i),
            0x27 if self.at(i, &[0x27, 0x05, 0x19, 0x56]) => self.uimage(i),
            0xd0 if self.at(i, &[0xd0, 0x0d, 0xfe, 0xed]) => self.fdt(i),
            b'A' if self.at(i, b"ANDROID!") => self.android_boot(i),
            0x7f if self.at(i, b"\x7fELF") => self.elf(i),
            0xfe | 0xce | 0xcf => self.macho(i),
            _ => None,
        }
    }

    /// Magics found after their region's start: tar (`ustar` at +257), ext (superblock magic at
    /// +0x438), ISO 9660 (`CD001` at +0x8001).
    fn try_backref(&mut self, i: usize) -> Option<Region> {
        match self.r.u8(i)? {
            b'u' if self.at(i, b"ustar") => self.tar(i.checked_sub(257)?),
            0x53 if self.at(i, &[0x53, 0xef]) => self.ext(i.checked_sub(0x438)?),
            b'C' if self.at(i, b"CD001") => self.iso(i.checked_sub(0x8001)?),
            _ => None,
        }
    }

    fn gzip(&mut self, i: usize) -> Option<Region> {
        if !self.probe("gzip") {
            return None;
        }
        let rest = self.data.get(i..)?;
        let h = gzip_header(rest)?;
        let body = rest.get(h.header_len..)?;
        let cap = self.inflate_left.min(64 << 20);
        let mut details = json!({"original_name": h.original_name, "mtime": h.mtime, "os": h.os});
        match inflate(body, false, cap, false) {
            Ok(inf) => {
                self.inflate_left = self.inflate_left.saturating_sub(inf.produced);
                let t = h.header_len.checked_add(inf.consumed)?;
                let r = Reader::new(rest);
                let ok = r.u32_le(t) == Some(inf.crc32) && r.u32_le(t + 4) == Some(inf.produced as u32);
                details["decompressed_size"] = json!(inf.produced);
                details["crc_ok"] = json!(ok);
                if !ok {
                    return None;
                }
                Some(reg(
                    i,
                    Some((t + 8) as u64),
                    "gzip",
                    Family::Compression,
                    format!("gzip stream, {} bytes when decompressed", inf.produced),
                    "high",
                    Unpack::Decompress,
                    details,
                ))
            }
            Err(InflateError::TooLarge) => {
                self.inflate_left = self.inflate_left.saturating_sub(cap);
                details["note"] = json!("stream too large to measure during the scan");
                Some(reg(i, None, "gzip", Family::Compression, "gzip stream (length not measured)".into(), "medium", Unpack::Decompress, details))
            }
            Err(_) => None,
        }
    }

    fn zlib(&mut self, i: usize) -> Option<Region> {
        let cmf = self.r.u8(i)?;
        let flg = self.r.u8(i + 1)?;
        if !matches!(flg, 0x01 | 0x5e | 0x9c | 0xda) || (u16::from(cmf) * 256 + u16::from(flg)) % 31 != 0 || flg & 0x20 != 0 {
            return None;
        }
        if !self.probe("zlib") || self.inflate_left == 0 {
            return None;
        }
        let cap = self.inflate_left.min(64 << 20);
        let inf = inflate(self.data.get(i..)?, true, cap, false).ok()?;
        self.inflate_left = self.inflate_left.saturating_sub(inf.produced);
        // Tiny streams match random bytes too easily.
        if inf.produced < 16 {
            return None;
        }
        Some(reg(
            i,
            Some(inf.consumed as u64),
            "zlib",
            Family::Compression,
            format!("zlib stream, {} bytes when decompressed", inf.produced),
            "high",
            Unpack::Decompress,
            json!({"decompressed_size": inf.produced, "checksum_ok": true}),
        ))
    }

    fn xz(&mut self, i: usize) -> Option<Region> {
        if !self.probe("xz") {
            return None;
        }
        let flags = self.r.slice(i + 6, 2)?;
        if self.r.u32_le(i + 8)? != crc32(flags) {
            return None;
        }
        // Find the stream footer: CRC32(backward size + flags), backward size, flags, "YZ".
        let mut length = None;
        let limit = self.data.len().min(i.saturating_add(512 << 20));
        let mut p = i + 12;
        while p + 2 <= limit {
            let Some(rel) = self.data.get(p..limit).and_then(|s| s.windows(2).position(|w| w == b"YZ")) else { break };
            let at = p + rel;
            if let Some(start) = at.checked_sub(10)
                && self.r.slice(at - 2, 2) == Some(flags)
                && self.r.slice(start + 4, 6).map(crc32) == self.r.u32_le(start)
            {
                length = Some((at + 2 - i) as u64);
                break;
            }
            p = at + 1;
        }
        let check = match flags.get(1).map(|f| f & 0x0f) {
            Some(0) => "none",
            Some(1) => "crc32",
            Some(4) => "crc64",
            Some(10) => "sha256",
            _ => "other",
        };
        Some(reg(
            i,
            length,
            "xz",
            Family::Compression,
            "xz stream".into(),
            "high",
            Unpack::Decompress,
            json!({"check": check, "footer_found": length.is_some()}),
        ))
    }

    fn lzma(&mut self, i: usize) -> Option<Region> {
        let dict = self.r.u32_le(i + 1)?;
        let size = self.r.u64_le(i + 5)?;
        // Classic .lzma: props 0x5d, power-of-two dictionary, sane size, range coder starts with 0.
        if !dict.is_power_of_two() || !(1 << 16..=1 << 26).contains(&dict) || self.r.u8(i + 13)? != 0 {
            return None;
        }
        if size != u64::MAX && size > 1 << 32 {
            return None;
        }
        if !self.probe("lzma") {
            return None;
        }
        Some(reg(
            i,
            None,
            "lzma",
            Family::Compression,
            "LZMA stream (header only)".into(),
            "medium",
            Unpack::Decompress,
            json!({"dictionary_size": dict, "uncompressed_size": if size == u64::MAX { Value::Null } else { json!(size) }}),
        ))
    }

    fn bzip2(&mut self, i: usize) -> Option<Region> {
        let level = self.r.u8(i + 3)?;
        if !(b'1'..=b'9').contains(&level) {
            return None;
        }
        let block = self.r.slice(i + 4, 6)?;
        if block != [0x31, 0x41, 0x59, 0x26, 0x53, 0x59] && block != [0x17, 0x72, 0x45, 0x38, 0x50, 0x90] {
            return None;
        }
        if !self.probe("bzip2") {
            return None;
        }
        Some(reg(
            i,
            None,
            "bzip2",
            Family::Compression,
            format!("bzip2 stream, block size {}00k", level - b'0'),
            "high",
            Unpack::Decompress,
            json!({"block_size_100k": level - b'0'}),
        ))
    }

    fn zstd(&mut self, i: usize) -> Option<Region> {
        let fhd = self.r.u8(i + 4)?;
        if fhd & 0x08 != 0 || !self.probe("zstd") {
            return None;
        }
        let single = fhd & 0x20 != 0;
        let did = [0usize, 1, 2, 4].get(usize::from(fhd & 3)).copied()?;
        let fcs = match fhd >> 6 {
            0 => usize::from(single),
            1 => 2,
            2 => 4,
            _ => 8,
        };
        let mut p = i + 5 + usize::from(!single) + did + fcs;
        let mut blocks = 0usize;
        loop {
            let b0 = self.r.u8(p)?;
            let b1 = self.r.u8(p + 1)?;
            let b2 = self.r.u8(p + 2)?;
            let hdr = u32::from(b0) | u32::from(b1) << 8 | u32::from(b2) << 16;
            let last = hdr & 1 != 0;
            let ty = (hdr >> 1) & 3;
            let size = (hdr >> 3) as usize;
            if size > 128 * 1024 {
                return None;
            }
            p = p.checked_add(3)?;
            p = p.checked_add(match ty {
                0 | 2 => size,
                1 => 1,
                _ => return None,
            })?;
            blocks += 1;
            if p > self.data.len() || blocks > 1_000_000 {
                return None;
            }
            if last {
                break;
            }
        }
        if fhd & 0x04 != 0 {
            p = p.checked_add(4)?;
        }
        if p > self.data.len() {
            return None;
        }
        Some(reg(
            i,
            Some((p - i) as u64),
            "zstd",
            Family::Compression,
            format!("Zstandard frame, {blocks} block(s)"),
            "high",
            Unpack::Decompress,
            json!({"blocks": blocks}),
        ))
    }

    fn lz4(&mut self, i: usize) -> Option<Region> {
        let flg = self.r.u8(i + 4)?;
        let bd = self.r.u8(i + 5)?;
        if flg >> 6 != 1 || flg & 0x02 != 0 || bd & 0x8f != 0 || (bd >> 4) & 7 < 4 || !self.probe("lz4") {
            return None;
        }
        let mut desc_len = 2usize;
        if flg & 0x08 != 0 {
            desc_len += 8;
        }
        if flg & 0x01 != 0 {
            desc_len += 4;
        }
        let desc = self.r.slice(i + 4, desc_len)?;
        if self.r.u8(i + 4 + desc_len)? != ((xxh32(desc, 0) >> 8) & 0xff) as u8 {
            return None;
        }
        let block_checksum = flg & 0x10 != 0;
        let mut p = i + 4 + desc_len + 1;
        let mut blocks = 0usize;
        loop {
            let sz = self.r.u32_le(p)?;
            p = p.checked_add(4)?;
            if sz == 0 {
                break;
            }
            let len = (sz & 0x7fff_ffff) as usize;
            if len > 4 << 20 {
                return None;
            }
            p = p.checked_add(len + if block_checksum { 4 } else { 0 })?;
            blocks += 1;
            if p > self.data.len() || blocks > 1_000_000 {
                return None;
            }
        }
        if flg & 0x04 != 0 {
            p = p.checked_add(4)?;
        }
        Some(reg(
            i,
            Some(clamp((p - i) as u64, i, self.data.len()).0),
            "lz4",
            Family::Compression,
            format!("LZ4 frame, {blocks} block(s)"),
            "high",
            Unpack::Carve,
            json!({"blocks": blocks}),
        ))
    }

    fn zip(&mut self, i: usize) -> Option<Region> {
        let ver = self.r.u16_le(i + 4)?;
        let method = self.r.u16_le(i + 8)?;
        let name_len = usize::from(self.r.u16_le(i + 26)?);
        if ver > 100 || !matches!(method, 0 | 1 | 6 | 8 | 9 | 12 | 14 | 93 | 95 | 98 | 99) || name_len == 0 || name_len > 1024 || !self.probe("zip") {
            return None;
        }
        let name = String::from_utf8_lossy(self.r.slice(i + 30, name_len)?).into_owned();
        // The end-of-central-directory record bounds the archive.
        let limit = self.data.len();
        let mut p = i + 30;
        let mut end = None;
        while p < limit {
            let Some(rel) = self.data.get(p..limit).and_then(|s| s.windows(4).position(|w| w == b"PK\x05\x06")) else { break };
            let at = p + rel;
            if let Some(cl) = self.r.u16_le(at + 20)
                && let (Some(cd_size), Some(cd_off)) = (self.r.u32_le(at + 12), self.r.u32_le(at + 16))
                && (cd_off as usize).checked_add(cd_size as usize).is_some_and(|e| i.checked_add(e).is_some_and(|x| x <= at))
            {
                end = at.checked_add(22 + usize::from(cl)).filter(|e| *e <= limit);
                if end.is_some() {
                    break;
                }
            }
            p = at + 1;
        }
        let mut details = json!({"first_entry": name});
        let (length, conf) = match end {
            Some(e) => {
                let ok = crate::zip::parse(self.data.get(i..e)?, 100_000).ok();
                if let Some(z) = &ok {
                    details["entries"] = json!(z.entries.len());
                }
                ((e - i) as u64, if ok.is_some() { "high" } else { "medium" })
            }
            None => {
                let csize = u64::from(self.r.u32_le(i + 18)?);
                let extra = u64::from(self.r.u16_le(i + 28)?);
                details["note"] = json!("no end-of-central-directory record; length covers the first entry only");
                (clamp(30 + name_len as u64 + extra + csize, i, limit).0, "medium")
            }
        };
        Some(reg(i, Some(length), "zip", Family::Archive, format!("ZIP archive, first entry {name:?}"), conf, Unpack::Members, details))
    }

    fn sevenz(&mut self, i: usize) -> Option<Region> {
        if self.r.u8(i + 6)? != 0 || !self.probe("7z") {
            return None;
        }
        let hdr = self.r.slice(i + 12, 20)?;
        if self.r.u32_le(i + 8)? != crc32(hdr) {
            return None;
        }
        let off = self.r.u64_le(i + 12)?;
        let size = self.r.u64_le(i + 20)?;
        let len = off.checked_add(size)?.checked_add(32)?;
        let (len, cut) = clamp(len, i, self.data.len());
        Some(reg(i, Some(len), "7z", Family::Archive, "7-Zip archive".into(), "high", Unpack::Carve, json!({"truncated": cut})))
    }

    fn rar(&mut self, i: usize) -> Option<Region> {
        let v = match self.r.u8(i + 6)? {
            0 => 4,
            1 if self.r.u8(i + 7)? == 0 => 5,
            _ => return None,
        };
        if !self.probe("rar") {
            return None;
        }
        Some(reg(i, None, "rar", Family::Archive, format!("RAR {v} archive"), "medium", Unpack::Carve, json!({"version": v})))
    }

    fn cab(&mut self, i: usize) -> Option<Region> {
        let size = self.r.u32_le(i + 8)?;
        if self.r.u32_le(i + 4)? != 0 || self.r.u8(i + 25)? != 1 || self.r.u8(i + 24)? != 3 || size < 36 || !self.probe("cab") {
            return None;
        }
        let files = self.r.u16_le(i + 28)?;
        let (len, cut) = clamp(u64::from(size), i, self.data.len());
        Some(reg(
            i,
            Some(len),
            "cab",
            Family::Archive,
            format!("Cabinet archive, {files} file(s)"),
            "medium",
            Unpack::Carve,
            json!({"files": files, "truncated": cut}),
        ))
    }

    fn tar(&mut self, start: usize) -> Option<Region> {
        if !self.probe("tar") {
            return None;
        }
        let rest = self.data.get(start..)?;
        if !crate::tarcpio::tar_header_ok(rest) {
            return None;
        }
        let l = crate::tarcpio::tar(rest, 1_000_000)?;
        let first = l.members.first().map(|m| m.name.clone()).unwrap_or_default();
        Some(reg(
            start,
            Some(l.length.max(512)),
            "tar",
            Family::Archive,
            format!("tar archive, {} member(s), first {first:?}", l.members.len()),
            "high",
            Unpack::Members,
            json!({"members": l.members.len(), "complete": l.complete}),
        ))
    }

    fn cpio(&mut self, i: usize) -> Option<Region> {
        if !matches!(self.r.u8(i + 5)?, b'1' | b'2' | b'7') || !self.probe("cpio") {
            return None;
        }
        let l = crate::tarcpio::cpio(self.data.get(i..)?, 1_000_000)?;
        if l.members.is_empty() && !l.complete {
            return None;
        }
        Some(reg(
            i,
            Some(l.length),
            l.format,
            Family::Archive,
            format!("cpio archive ({}), {} member(s)", l.format.trim_start_matches("cpio-"), l.members.len()),
            if l.complete { "high" } else { "medium" },
            Unpack::Members,
            json!({"members": l.members.len(), "complete": l.complete}),
        ))
    }

    fn squashfs(&mut self, i: usize, be: bool) -> Option<Region> {
        let r = self.r;
        let u16f = |o: usize| if be { r.u16_be(i + o) } else { r.u16_le(i + o) };
        let u32f = |o: usize| if be { r.u32_be(i + o) } else { r.u32_le(i + o) };
        let major = u16f(28)?;
        let block_size = u32f(12)?;
        let block_log = u16f(22)?;
        let comp = u16f(20)?;
        if !(2..=4).contains(&major) || !self.probe("squashfs") {
            return None;
        }
        let (used, conf) = if major == 4 {
            if !(12..=20).contains(&block_log) || 1u32.checked_shl(u32::from(block_log)) != Some(block_size) || !(1..=6).contains(&comp) {
                return None;
            }
            let used = if be { self.r.u64_be(i + 40)? } else { self.r.u64_le(i + 40)? };
            (Some(used), "high")
        } else {
            // Version 3 keeps a 64-bit bytes_used at +63; version 2 a 32-bit one at +8.
            let used = if major == 3 { if be { self.r.u64_be(i + 63) } else { self.r.u64_le(i + 63) } } else { u32f(8).map(u64::from) };
            (used, "medium")
        };
        let compression = match comp {
            1 => "gzip",
            2 => "lzma",
            3 => "lzo",
            4 => "xz",
            5 => "lz4",
            6 => "zstd",
            _ => "unknown",
        };
        let used = used.filter(|u| *u >= 96)?;
        let (len, cut) = clamp(used, i, self.data.len());
        Some(reg(
            i,
            Some(len),
            "squashfs",
            Family::Filesystem,
            format!("squashfs {major}.x filesystem ({}-endian, {compression})", if be { "big" } else { "little" }),
            conf,
            Unpack::Filesystem,
            json!({"version": major, "block_size": block_size, "compression": if major == 4 { compression } else { "unknown" }, "inodes": u32f(4), "bytes_used": used, "truncated": cut}),
        ))
    }

    fn cramfs(&mut self, i: usize, be: bool) -> Option<Region> {
        if !self.at(i + 16, b"Compressed ROMFS") || !self.probe("cramfs") {
            return None;
        }
        let size = if be { self.r.u32_be(i + 4)? } else { self.r.u32_le(i + 4)? };
        let (len, cut) = clamp(u64::from(size), i, self.data.len());
        let name = cstr_field(self.r.slice(i + 48, 16));
        Some(reg(
            i,
            Some(len),
            "cramfs",
            Family::Filesystem,
            format!("cramfs filesystem {name:?}"),
            "high",
            Unpack::Filesystem,
            json!({"name": name, "truncated": cut}),
        ))
    }

    fn romfs(&mut self, i: usize) -> Option<Region> {
        let size = self.r.u32_be(i + 8)?;
        if size < 32 || !self.probe("romfs") {
            return None;
        }
        // The first 512 bytes (or the whole image if smaller) sum to zero as big-endian words.
        let n = (size.min(512) as usize) & !3;
        let words = self.r.slice(i, n)?;
        let sum = words.as_chunks::<4>().0.iter().fold(0u32, |a, w| a.wrapping_add(u32::from_be_bytes(*w)));
        if sum != 0 {
            return None;
        }
        let name = cstr_field(self.r.slice(i + 16, 64));
        let (len, cut) = clamp(u64::from(size), i, self.data.len());
        Some(reg(
            i,
            Some(len),
            "romfs",
            Family::Filesystem,
            format!("romfs filesystem {name:?}"),
            "high",
            Unpack::Filesystem,
            json!({"volume": name, "truncated": cut}),
        ))
    }

    fn pem(&mut self, i: usize) -> Option<Region> {
        let line = self.r.slice(i + 11, 64)?;
        let end = line.windows(5).position(|w| w == b"-----")?;
        let label = std::str::from_utf8(line.get(..end)?).ok()?;
        if label.is_empty() || !label.bytes().all(|b| b.is_ascii_uppercase() || b == b' ' || b.is_ascii_digit()) || !self.probe("pem") {
            return None;
        }
        let footer = format!("-----END {label}-----");
        let limit = self.data.len().min(i.saturating_add(1 << 20));
        let rel = self.data.get(i..limit)?.windows(footer.len()).position(|w| w == footer.as_bytes())?;
        let len = rel + footer.len();
        let private = label.contains("PRIVATE");
        let kind = if private {
            "pem-private-key"
        } else if label.contains("CERTIFICATE") {
            "pem-certificate"
        } else {
            "pem"
        };
        Some(reg(
            i,
            Some(len as u64),
            kind,
            Family::Crypto,
            format!("PEM block \"{label}\"{}", if private { " (key material not shown)" } else { "" }),
            "high",
            Unpack::Carve,
            json!({"label": label}),
        ))
    }

    fn jffs2(&mut self, i: usize, be: bool) -> Option<Region> {
        if !self.probe("jffs2") {
            return None;
        }
        let u16f = |o: usize| if be { self.r.u16_be(o) } else { self.r.u16_le(o) };
        let u32f = |o: usize| if be { self.r.u32_be(o) } else { self.r.u32_le(o) };
        let node_ok = |p: usize| -> Option<u32> {
            if u16f(p)? != 0x1985 {
                return None;
            }
            let nt = u16f(p + 2)?;
            if !matches!(nt & 0x0fff, 1..=9) {
                return None;
            }
            let tot = u32f(p + 4)?;
            if !(12..=1 << 20).contains(&tot) {
                return None;
            }
            let crc = u32f(p + 8)?;
            (crc32_raw(0, self.r.slice(p, 8)?) == crc).then_some(tot)
        };
        node_ok(i)?;
        let mut p = i;
        let mut nodes = 0usize;
        let mut end = i;
        while nodes < 1_000_000 {
            if let Some(tot) = node_ok(p) {
                nodes += 1;
                p = p.checked_add((tot as usize).checked_add(3)? & !3)?;
                end = p.min(self.data.len());
                continue;
            }
            // Skip erase padding (0xff) and alignment zeroes between nodes.
            let pad = self.data.get(p..)?.iter().take(1 << 20).take_while(|&&b| b == 0xff || b == 0).count();
            if pad == 0 || p + pad >= self.data.len() {
                break;
            }
            let next = (p + pad) & !3;
            if next <= p || node_ok(next).is_none() {
                break;
            }
            p = next;
        }
        Some(reg(
            i,
            Some((end - i) as u64),
            "jffs2",
            Family::Filesystem,
            format!("JFFS2 filesystem ({}-endian), {nodes} node(s)", if be { "big" } else { "little" }),
            "high",
            Unpack::Filesystem,
            json!({"nodes": nodes}),
        ))
    }

    fn ubi(&mut self, i: usize) -> Option<Region> {
        if self.r.u8(i + 4)? != 1 || !self.probe("ubi") {
            return None;
        }
        let hdr_ok = |p: usize| self.r.slice(p, 60).map(|h| crc32_raw(!0, h)) == self.r.u32_be(p + 60) && self.at(p, b"UBI#");
        if !hdr_ok(i) {
            return None;
        }
        let vid = self.r.u32_be(i + 16)?;
        let data_off = self.r.u32_be(i + 20)?;
        // The erase-block size is the distance to the next EC header.
        let mut stride = None;
        let mut p = i + 64;
        while p < self.data.len().min(i.saturating_add(4 << 20)) {
            let Some(rel) = self.data.get(p..).and_then(|s| s.windows(4).position(|w| w == b"UBI#")) else { break };
            let at = p + rel;
            if hdr_ok(at) {
                stride = Some(at - i);
                break;
            }
            p = at + 1;
        }
        let mut blocks = 1usize;
        let mut end = None;
        if let Some(s) = stride {
            let mut q = i;
            while hdr_ok(q) && blocks < 1_000_000 {
                q = q.checked_add(s)?;
                if hdr_ok(q) {
                    blocks += 1;
                } else {
                    break;
                }
            }
            end = Some(clamp((blocks * s) as u64, i, self.data.len()).0);
        }
        Some(reg(
            i,
            end,
            "ubi",
            Family::Filesystem,
            format!("UBI image, {blocks} erase block(s){}", stride.map(|s| format!(" of {s} bytes")).unwrap_or_default()),
            "high",
            Unpack::Carve,
            json!({"vid_header_offset": vid, "data_offset": data_off, "erase_block_size": stride, "erase_blocks": blocks}),
        ))
    }

    fn ubifs(&mut self, i: usize) -> Option<Region> {
        let len = self.r.u32_le(i + 16)?;
        let node_type = self.r.u8(i + 20)?;
        if node_type != 6 || !(24..=8192).contains(&len) || !self.probe("ubifs") {
            return None;
        }
        let body = self.r.slice(i + 8, len as usize - 8)?;
        if crc32_raw(!0, body) != self.r.u32_le(i + 4)? {
            return None;
        }
        let min_io = self.r.u32_le(i + 32);
        let leb = self.r.u32_le(i + 36)?;
        let leb_cnt = self.r.u32_le(i + 40)?;
        let total = u64::from(leb).checked_mul(u64::from(leb_cnt))?;
        let (l, cut) = clamp(total, i, self.data.len());
        Some(reg(
            i,
            Some(l),
            "ubifs",
            Family::Filesystem,
            format!("UBIFS filesystem, {leb_cnt} LEBs of {leb} bytes"),
            "high",
            Unpack::Carve,
            json!({"min_io_size": min_io, "leb_size": leb, "leb_count": leb_cnt, "truncated": cut}),
        ))
    }

    fn ext(&mut self, start: usize) -> Option<Region> {
        let sb = start.checked_add(1024)?;
        let inodes = self.r.u32_le(sb)?;
        let blocks_lo = self.r.u32_le(sb + 4)?;
        let log = self.r.u32_le(sb + 24)?;
        let bpg = self.r.u32_le(sb + 32)?;
        let ipg = self.r.u32_le(sb + 40)?;
        let state = self.r.u16_le(sb + 58)?;
        let errors = self.r.u16_le(sb + 60)?;
        let rev = self.r.u32_le(sb + 76)?;
        if inodes == 0
            || blocks_lo == 0
            || log > 6
            || bpg == 0
            || ipg == 0
            || ipg > inodes
            || !(1..=7).contains(&state)
            || !(1..=3).contains(&errors)
            || rev > 1
        {
            return None;
        }
        let block = 1024u64 << log;
        if u64::from(bpg) > block * 8 || !self.probe("ext") {
            return None;
        }
        let compat = self.r.u32_le(sb + 92)?;
        let incompat = self.r.u32_le(sb + 96)?;
        let hi = if incompat & 0x80 != 0 { self.r.u32_le(sb + 0x150).unwrap_or(0) } else { 0 };
        let blocks = u64::from(blocks_lo) | u64::from(hi) << 32;
        let kind = if incompat & (0x40 | 0x80 | 0x200) != 0 {
            "ext4"
        } else if compat & 0x4 != 0 {
            "ext3"
        } else {
            "ext2"
        };
        let name = cstr_field(self.r.slice(sb + 120, 16));
        let (len, cut) = clamp(blocks.checked_mul(block)?, start, self.data.len());
        Some(reg(
            start,
            Some(len),
            kind,
            Family::Filesystem,
            format!("{kind} filesystem {name:?}, {blocks} blocks of {block} bytes"),
            "high",
            Unpack::Filesystem,
            json!({"volume_name": name, "block_size": block, "blocks": blocks, "inodes": inodes, "truncated": cut}),
        ))
    }

    fn fat(&mut self, i: usize) -> Option<Region> {
        let b0 = self.r.u8(i)?;
        if b0 == 0xeb && self.r.u8(i + 2)? != 0x90 {
            return None;
        }
        if self.r.u16_le(i + 510)? != 0xaa55 {
            return None;
        }
        let bps = self.r.u16_le(i + 11)?;
        let spc = self.r.u8(i + 13)?;
        let reserved = self.r.u16_le(i + 14)?;
        let fats = self.r.u8(i + 16)?;
        let media = self.r.u8(i + 21)?;
        if !matches!(bps, 512 | 1024 | 2048 | 4096) || !spc.is_power_of_two() || reserved == 0 || !matches!(fats, 1 | 2) || (media < 0xf8 && media != 0xf0) {
            return None;
        }
        if !self.probe("fat") {
            return None;
        }
        let small = self.r.u16_le(i + 19)?;
        let sectors = if small != 0 { u32::from(small) } else { self.r.u32_le(i + 32)? };
        if sectors == 0 {
            return None;
        }
        let kind = if self.at(i + 82, b"FAT32") {
            "fat32"
        } else if self.at(i + 54, b"FAT16") {
            "fat16"
        } else if self.at(i + 54, b"FAT12") {
            "fat12"
        } else {
            "fat"
        };
        let label_off = if kind == "fat32" { 71 } else { 43 };
        let label = cstr_field(self.r.slice(i + label_off, 11));
        let (len, cut) = clamp(u64::from(sectors) * u64::from(bps), i, self.data.len());
        Some(reg(
            i,
            Some(len),
            kind,
            Family::Filesystem,
            format!("{} filesystem {label:?}", kind.to_uppercase()),
            "medium",
            Unpack::Carve,
            json!({"label": label, "bytes_per_sector": bps, "sectors": sectors, "truncated": cut}),
        ))
    }

    fn iso(&mut self, start: usize) -> Option<Region> {
        let pvd = start.checked_add(0x8000)?;
        if self.r.u8(pvd)? != 1 || self.r.u8(pvd + 6)? != 1 || !self.probe("iso9660") {
            return None;
        }
        let blocks = self.r.u32_le(pvd + 80)?;
        let bsize = self.r.u16_le(pvd + 128)?;
        if !matches!(bsize, 512 | 1024 | 2048) || blocks == 0 {
            return None;
        }
        let vol = cstr_field(self.r.slice(pvd + 40, 32));
        let (len, cut) = clamp(u64::from(blocks) * u64::from(bsize), start, self.data.len());
        Some(reg(
            start,
            Some(len),
            "iso9660",
            Family::Filesystem,
            format!("ISO 9660 volume {vol:?}"),
            "high",
            Unpack::Carve,
            json!({"volume_id": vol, "block_size": bsize, "blocks": blocks, "truncated": cut}),
        ))
    }

    fn uimage(&mut self, i: usize) -> Option<Region> {
        if !self.probe("uimage") {
            return None;
        }
        let mut h = self.r.slice(i, 64)?.to_vec();
        let hcrc = self.r.u32_be(i + 4)?;
        h.get_mut(4..8)?.copy_from_slice(&[0; 4]);
        if crc32(&h) != hcrc {
            return None;
        }
        let size = self.r.u32_be(i + 12)?;
        let load = self.r.u32_be(i + 16)?;
        let ep = self.r.u32_be(i + 20)?;
        let dcrc = self.r.u32_be(i + 24)?;
        let (os, arch, ty, comp) = (self.r.u8(i + 28)?, self.r.u8(i + 29)?, self.r.u8(i + 30)?, self.r.u8(i + 31)?);
        let name = cstr_field(self.r.slice(i + 32, 32));
        let data_ok = self.r.slice(i + 64, size as usize).map(|d| crc32(d) == dcrc);
        let comp_name = match comp {
            0 => "none",
            1 => "gzip",
            2 => "bzip2",
            3 => "lzma",
            4 => "lzo",
            5 => "lz4",
            6 => "zstd",
            _ => "unknown",
        };
        let os_name = match os {
            5 => "linux",
            17 => "u-boot",
            _ => "other",
        };
        let arch_name = match arch {
            2 => "arm",
            3 => "x86",
            5 => "mips",
            7 => "powerpc",
            22 => "arm64",
            26 => "riscv",
            _ => "other",
        };
        let type_name = match ty {
            1 => "standalone",
            2 => "kernel",
            3 => "ramdisk",
            4 => "multi",
            5 => "firmware",
            6 => "script",
            8 => "flat_dt",
            _ => "other",
        };
        let (len, cut) = clamp(64 + u64::from(size), i, self.data.len());
        Some(reg(
            i,
            Some(len),
            "uimage",
            Family::BootImage,
            format!("legacy boot-loader image {name:?}: {os_name} {arch_name} {type_name}, {comp_name}, {size} bytes"),
            "high",
            Unpack::Payload,
            json!({"name": name, "os": os_name, "architecture": arch_name, "image_type": type_name, "compression": comp_name, "data_size": size, "load_address": format!("{load:#x}"), "entry_point": format!("{ep:#x}"), "data_crc_ok": data_ok, "truncated": cut}),
        ))
    }

    fn fdt(&mut self, i: usize) -> Option<Region> {
        let total = self.r.u32_be(i + 4)?;
        let st = self.r.u32_be(i + 8)?;
        let strs = self.r.u32_be(i + 12)?;
        let rsv = self.r.u32_be(i + 16)?;
        let ver = self.r.u32_be(i + 20)?;
        let last = self.r.u32_be(i + 24)?;
        if total < 40 || st >= total || strs > total || rsv >= total || !(1..=17).contains(&last) || ver < last || ver > 20 || !self.probe("fdt") {
            return None;
        }
        let blob = self.r.slice(i, total as usize);
        let fit = blob.is_some_and(|b| crate::find_bytes(b, b"images\0", b.len()).is_some() && crate::find_bytes(b, b"configurations\0", b.len()).is_some());
        let (len, cut) = clamp(u64::from(total), i, self.data.len());
        let kind = if fit { "fit" } else { "fdt" };
        Some(reg(
            i,
            Some(len),
            kind,
            Family::DeviceTree,
            if fit { "flattened image tree (FIT)".into() } else { format!("flattened device tree, version {ver}") },
            "high",
            Unpack::Carve,
            json!({"version": ver, "total_size": total, "truncated": cut}),
        ))
    }

    fn android_boot(&mut self, i: usize) -> Option<Region> {
        if !self.probe("android-boot") {
            return None;
        }
        let kernel = u64::from(self.r.u32_le(i + 8)?);
        let hv = self.r.u32_le(i + 40)?;
        let align = |v: u64, p: u64| v.div_ceil(p).checked_mul(p);
        let (page, ramdisk, second, extra) = if hv >= 3 {
            if hv > 4 {
                return None;
            }
            (4096u64, u64::from(self.r.u32_le(i + 12)?), 0u64, 0u64)
        } else {
            let page = u64::from(self.r.u32_le(i + 36)?);
            if !matches!(page, 2048 | 4096 | 8192 | 16384) {
                return None;
            }
            let ramdisk = u64::from(self.r.u32_le(i + 16)?);
            let second = u64::from(self.r.u32_le(i + 24)?);
            let mut extra = 0u64;
            if hv >= 1 {
                extra += align(u64::from(self.r.u32_le(i + 1632).unwrap_or(0)), page)?;
            }
            if hv >= 2 {
                extra += align(u64::from(self.r.u32_le(i + 1648).unwrap_or(0)), page)?;
            }
            (page, ramdisk, second, extra)
        };
        if kernel == 0 || kernel > 1 << 30 || ramdisk > 1 << 30 || second > 1 << 30 {
            return None;
        }
        let total = page.checked_add(align(kernel, page)?)?.checked_add(align(ramdisk, page)?)?.checked_add(align(second, page)?)?.checked_add(extra)?;
        let (len, cut) = clamp(total, i, self.data.len());
        Some(reg(
            i,
            Some(len),
            "android-boot",
            Family::BootImage,
            format!("Android boot image v{hv}: kernel {kernel} bytes, ramdisk {ramdisk} bytes"),
            "high",
            Unpack::Payload,
            json!({"header_version": hv, "page_size": page, "kernel_size": kernel, "ramdisk_size": ramdisk, "second_size": second, "truncated": cut}),
        ))
    }

    fn elf(&mut self, i: usize) -> Option<Region> {
        let class = self.r.u8(i + 4)?;
        let dat = self.r.u8(i + 5)?;
        if !matches!(class, 1 | 2) || !matches!(dat, 1 | 2) || self.r.u8(i + 6)? != 1 || !self.probe("elf") {
            return None;
        }
        let be = dat == 2;
        let u16f = |o: usize| if be { self.r.u16_be(i + o) } else { self.r.u16_le(i + o) };
        let u32f = |o: usize| if be { self.r.u32_be(i.checked_add(o)?) } else { self.r.u32_le(i.checked_add(o)?) };
        let u64f = |o: usize| if be { self.r.u64_be(i.checked_add(o)?) } else { self.r.u64_le(i.checked_add(o)?) };
        let wide = class == 2;
        let word = |o: usize| if wide { u64f(o) } else { u32f(o).map(u64::from) };
        let ty = u16f(16)?;
        let machine = u16f(18)?;
        if !(1..=4).contains(&ty) {
            return None;
        }
        let (phoff, shoff) = if wide { (word(32)?, word(40)?) } else { (word(28)?, word(32)?) };
        let (phentsize, phnum, shentsize, shnum) =
            if wide { (u16f(54)?, u16f(56)?, u16f(58)?, u16f(60)?) } else { (u16f(42)?, u16f(44)?, u16f(46)?, u16f(48)?) };
        let mut end = u64::from(if wide { 64u16 } else { 52 });
        end = end.max(phoff.saturating_add(u64::from(phentsize) * u64::from(phnum)));
        end = end.max(shoff.saturating_add(u64::from(shentsize) * u64::from(shnum)));
        for k in 0..usize::from(phnum).min(256) {
            let Some(p) = usize::try_from(phoff).ok().and_then(|o| o.checked_add(k * usize::from(phentsize))) else { break };
            let (off, filesz) = if wide { (word(p + 8), word(p + 32)) } else { (word(p + 4), word(p + 16)) };
            if let (Some(o), Some(s)) = (off, filesz) {
                end = end.max(o.saturating_add(s));
            }
        }
        for k in 0..usize::from(shnum).min(4096) {
            let Some(p) = usize::try_from(shoff).ok().and_then(|o| o.checked_add(k * usize::from(shentsize))) else { break };
            let sh_type = u32f(p + 4);
            let (off, size) = if wide { (word(p + 24), word(p + 32)) } else { (word(p + 16), word(p + 20)) };
            if sh_type != Some(8)
                && let (Some(o), Some(s)) = (off, size)
            {
                end = end.max(o.saturating_add(s));
            }
        }
        let (len, cut) = clamp(end, i, self.data.len());
        let arch = match machine {
            3 => "x86",
            8 => "mips",
            20 => "powerpc",
            40 => "arm",
            62 => "x86_64",
            183 => "arm64",
            243 => "riscv",
            _ => "other",
        };
        let tyn = ["", "relocatable", "executable", "shared object", "core"].get(usize::from(ty)).copied().unwrap_or("");
        Some(reg(
            i,
            Some(len),
            "elf",
            Family::Executable,
            format!("ELF{} {arch} {tyn} ({}-endian)", if wide { 64 } else { 32 }, if be { "big" } else { "little" }),
            if cut { "medium" } else { "high" },
            Unpack::Carve,
            json!({"bits": if wide { 64 } else { 32 }, "architecture": arch, "machine": machine, "type": tyn, "truncated": cut}),
        ))
    }

    fn pe(&mut self, i: usize) -> Option<Region> {
        let lfanew = self.r.u32_le(i + 0x3c)? as usize;
        if !(0x40..=0x1000).contains(&lfanew) || !self.at(i + lfanew, b"PE\0\0") || !self.probe("pe") {
            return None;
        }
        let pe = i + lfanew;
        let machine = self.r.u16_le(pe + 4)?;
        let nsec = usize::from(self.r.u16_le(pe + 6)?);
        let opt_size = usize::from(self.r.u16_le(pe + 20)?);
        let opt = pe + 24;
        let magic = self.r.u16_le(opt)?;
        let dirs = match magic {
            0x10b => opt + 96,
            0x20b => opt + 112,
            _ => return None,
        };
        let mut end = u64::from(self.r.u32_le(opt + 60).unwrap_or(0));
        let sec = opt.checked_add(opt_size)?;
        for k in 0..nsec.min(96) {
            let s = sec + k * 40;
            if let (Some(raw), Some(ptr)) = (self.r.u32_le(s + 16), self.r.u32_le(s + 20)) {
                end = end.max(u64::from(ptr) + u64::from(raw));
            }
        }
        // The certificate table's "address" is a file offset.
        if let (Some(c), Some(cs)) = (self.r.u32_le(dirs + 4 * 8), self.r.u32_le(dirs + 4 * 8 + 4))
            && c != 0
        {
            end = end.max(u64::from(c) + u64::from(cs));
        }
        let (len, cut) = clamp(end, i, self.data.len());
        let arch = match machine {
            0x14c => "x86",
            0x8664 => "x86_64",
            0x1c0 | 0x1c4 => "arm",
            0xaa64 => "arm64",
            _ => "other",
        };
        Some(reg(
            i,
            Some(len),
            "pe",
            Family::Executable,
            format!("PE {} executable ({arch})", if magic == 0x20b { "32+" } else { "32" }),
            "high",
            Unpack::Carve,
            json!({"machine": machine, "architecture": arch, "sections": nsec, "truncated": cut}),
        ))
    }

    fn macho(&mut self, i: usize) -> Option<Region> {
        let m = self.r.u32_be(i)?;
        let (be, wide) = match m {
            0xfeed_face => (true, false),
            0xfeed_facf => (true, true),
            0xcefa_edfe => (false, false),
            0xcffa_edfe => (false, true),
            _ => return None,
        };
        let r = self.r;
        let u32f = |o: usize| if be { r.u32_be(o) } else { r.u32_le(o) };
        let u64f = |o: usize| if be { r.u64_be(o) } else { r.u64_le(o) };
        let cpu = u32f(i + 4)?;
        let ftype = u32f(i + 12)?;
        let ncmds = u32f(i + 16)? as usize;
        let sizeofcmds = u32f(i + 20)? as usize;
        if !matches!(cpu, 7 | 0x0100_0007 | 12 | 0x0100_000c | 0x0200_000c | 18 | 0x0100_0012)
            || !(1..=12).contains(&ftype)
            || ncmds == 0
            || ncmds > 4096
            || sizeofcmds > 16 << 20
        {
            return None;
        }
        if !self.probe("macho") {
            return None;
        }
        let mut p = i + if wide { 32 } else { 28 };
        let mut end = p.saturating_sub(i).saturating_add(sizeofcmds) as u64;
        for _ in 0..ncmds {
            let (Some(cmd), Some(sz)) = (u32f(p), u32f(p + 4)) else { break };
            match cmd {
                0x1 => {
                    if let (Some(o), Some(s)) = (u32f(p + 32), u32f(p + 36)) {
                        end = end.max(u64::from(o) + u64::from(s));
                    }
                }
                0x19 => {
                    if let (Some(o), Some(s)) = (u64f(p + 40), u64f(p + 48)) {
                        end = end.max(o.saturating_add(s));
                    }
                }
                0x1d => {
                    if let (Some(o), Some(s)) = (u32f(p + 8), u32f(p + 12)) {
                        end = end.max(u64::from(o) + u64::from(s));
                    }
                }
                _ => {}
            }
            if sz < 8 {
                break;
            }
            p = p.checked_add(sz as usize)?;
        }
        let (len, cut) = clamp(end, i, self.data.len());
        let arch = crate::macho::cpu_name(cpu, 0);
        Some(reg(
            i,
            Some(len),
            "macho",
            Family::Executable,
            format!("Mach-O {arch} ({}-bit)", if wide { 64 } else { 32 }),
            "high",
            Unpack::Carve,
            json!({"architecture": arch, "file_type": ftype, "truncated": cut}),
        ))
    }
}

/// Scan `data` for recognised regions. `stop` is polled every MiB; when it returns true the scan
/// ends early with `cancelled` set. A region with a confirmed length hides its interior from the
/// scan (nested content is found by scanning the region again after extraction).
pub fn scan(data: &[u8], opts: &ScanOptions, stop: &dyn Fn() -> bool) -> ScanResult {
    let mut s = Scanner { data, r: Reader::new(data), probes: BTreeMap::new(), opts, inflate_left: opts.inflate_budget, exhausted: Vec::new() };
    let mut out = ScanResult::default();
    let mut skip_until = 0usize;
    let mut i = 0usize;
    while i < data.len() {
        if i.is_multiple_of(1 << 20) && stop() {
            out.cancelled = true;
            break;
        }
        let found = s.try_backref(i).filter(|r| r.offset as usize >= skip_until).or_else(|| s.try_at(i));
        if let Some(r) = found {
            if out.regions.len() >= opts.max_regions {
                out.truncated = true;
                break;
            }
            let start = r.offset as usize;
            if start < i {
                // A back-referenced region swallows anything found inside it so far.
                out.regions.retain(|x| (x.offset as usize) < start);
            }
            if r.confidence == "high"
                && let Some(end) = r.end().and_then(|e| usize::try_from(e).ok())
                && end > i
            {
                skip_until = skip_until.max(end);
            }
            out.regions.push(r);
        }
        i = if skip_until > i { skip_until } else { i + 1 };
    }
    out.regions.sort_by_key(|r| r.offset);
    out.probes_exhausted = s.exhausted;
    if !out.probes_exhausted.is_empty() {
        out.warnings.push(format!("probe budget spent for: {} (later candidates were not checked)", out.probes_exhausted.join(", ")));
    }
    out
}

// ---------------------------------------------------------------------------------------------
// Entropy and layout

/// One block of the entropy map.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct EntropyBlock {
    pub offset: u64,
    pub length: u64,
    /// Bits per byte, 0..=8.
    pub entropy: f32,
    /// `padding`, `text`, `sparse`, `code-or-data` or `compressed-or-encrypted`.
    pub class: &'static str,
}

/// Classify a block by entropy and content.
pub fn classify_block(b: &[u8]) -> (f32, &'static str) {
    let e = (entropy(b) * 1000.0).round() / 1000.0;
    let class = if b.first().is_some_and(|f| b.iter().all(|x| x == f)) {
        "padding"
    } else if b.iter().filter(|&&c| c == b'\n' || c == b'\t' || c == b'\r' || (0x20..0x7f).contains(&c)).count() * 100 >= b.len() * 95 {
        "text"
    } else if e >= 7.2 {
        "compressed-or-encrypted"
    } else if e < 2.0 {
        "sparse"
    } else {
        "code-or-data"
    };
    (e, class)
}

/// Entropy per block. The block size grows (doubling) until at most `max_blocks` blocks cover
/// the input; the block size actually used is returned.
pub fn entropy_map(data: &[u8], block: usize, max_blocks: usize) -> (Vec<EntropyBlock>, usize) {
    let mut bs = block.max(1);
    while data.len().div_ceil(bs) > max_blocks.max(1) {
        bs = bs.saturating_mul(2);
    }
    let out = data
        .chunks(bs)
        .enumerate()
        .map(|(k, c)| {
            let (e, class) = classify_block(c);
            EntropyBlock { offset: (k * bs) as u64, length: c.len() as u64, entropy: e, class }
        })
        .collect();
    (out, bs)
}

/// A byte span.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Span {
    pub offset: u64,
    pub length: u64,
}

/// How the recognised regions cover the input.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Layout {
    pub total_bytes: u64,
    /// Bytes inside regions with a known length.
    pub recognised_bytes: u64,
    pub recognised_percent: f32,
    pub unknown_length_regions: usize,
    /// Spans no region of known length covers (padding-only spans are left out).
    pub gaps: Vec<Span>,
    /// Unrecognised spans whose entropy looks compressed or encrypted.
    pub high_entropy_unrecognised: Vec<Span>,
    pub spans_truncated: bool,
}

/// Summarise coverage, gaps and unexplained high-entropy spans.
pub fn layout(data: &[u8], regions: &[Region], entropy: &[EntropyBlock], max_spans: usize) -> Layout {
    let total = data.len() as u64;
    let mut iv: Vec<(u64, u64)> = regions.iter().filter_map(|r| Some((r.offset, r.end()?.min(total)))).collect();
    iv.sort_unstable();
    let mut merged: Vec<(u64, u64)> = Vec::new();
    for (s, e) in iv {
        match merged.last_mut() {
            Some(last) if s <= last.1 => last.1 = last.1.max(e),
            _ => merged.push((s, e)),
        }
    }
    let recognised: u64 = merged.iter().map(|(s, e)| e - s).sum();
    let covered = |o: u64, l: u64| merged.iter().any(|(s, e)| *s <= o && o.saturating_add(l) <= *e);
    let mut gaps = Vec::new();
    let mut truncated = false;
    let mut cur = 0u64;
    for (s, e) in merged.iter().copied().chain(std::iter::once((total, total))) {
        if s > cur {
            let gap = data.get(cur as usize..s as usize).unwrap_or(&[]);
            let padding = gap.first().is_some_and(|f| (*f == 0 || *f == 0xff) && gap.iter().all(|x| x == f));
            if !padding {
                if gaps.len() < max_spans {
                    gaps.push(Span { offset: cur, length: s - cur });
                } else {
                    truncated = true;
                }
            }
        }
        cur = cur.max(e);
    }
    let mut hot: Vec<Span> = Vec::new();
    for b in entropy.iter().filter(|b| b.class == "compressed-or-encrypted" && !covered(b.offset, b.length)) {
        match hot.last_mut() {
            Some(h) if h.offset + h.length == b.offset => h.length += b.length,
            _ => {
                if hot.len() < max_spans {
                    hot.push(Span { offset: b.offset, length: b.length });
                } else {
                    truncated = true;
                }
            }
        }
    }
    Layout {
        total_bytes: total,
        recognised_bytes: recognised,
        recognised_percent: if total == 0 { 0.0 } else { ((recognised as f64 / total as f64) * 1000.0).round() as f32 / 10.0 },
        unknown_length_regions: regions.iter().filter(|r| r.length.is_none()).count(),
        gaps,
        high_entropy_unrecognised: hot,
        spans_truncated: truncated,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::firmware as fx;

    fn no_stop() -> bool {
        false
    }

    fn kinds(r: &ScanResult) -> Vec<(&'static str, u64)> {
        r.regions.iter().map(|x| (x.kind, x.offset)).collect()
    }

    #[test]
    fn checksums() {
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(xxh32(b"", 0), 0x02cc_5d05);
        assert_eq!(xxh32(b"abc", 0), 0x32d1_53ff);
        assert_eq!(xxh32(b"Nobody inspects the spammish repetition", 0), 0xe229_3b2f);
    }

    #[test]
    fn inflates_and_caps() {
        let data = b"hello hello hello firmware".repeat(10);
        let gz = fx::gzip(&data, Some("x.bin"));
        let (out, used) = gunzip(&gz, 1 << 20).unwrap();
        assert_eq!(out, data);
        assert_eq!(used, gz.len());
        assert_eq!(gunzip(&gz, 10), Err(InflateError::TooLarge));
        assert!(gunzip(&gz[..gz.len() - 6], 1 << 20).is_err());
        let z = fx::zlib(&data);
        let inf = inflate(&z, true, 1 << 20, true).unwrap();
        assert_eq!(inf.data.unwrap(), data);
        assert_eq!(inf.consumed, z.len());
        let mut bad = z.clone();
        let n = bad.len();
        bad[n - 1] ^= 1;
        assert!(inflate(&bad, true, 1 << 20, false).is_err());
        assert_eq!(gzip_header(&gz).unwrap().original_name.as_deref(), Some("x.bin"));
    }

    #[test]
    fn scans_the_synthetic_image() {
        let (img, l) = fx::image();
        let r = scan(&img, &ScanOptions::default(), &no_stop);
        let k = kinds(&r);
        assert!(k.contains(&("uimage", l.uimage.0 as u64)), "{k:?}");
        assert!(k.contains(&("squashfs", l.squashfs.0 as u64)), "{k:?}");
        assert!(k.contains(&("tar", l.tar.0 as u64)), "{k:?}");
        assert!(k.contains(&("cpio-newc", l.cpio.0 as u64)), "{k:?}");
        assert!(k.contains(&("zip", l.zip.0 as u64)), "{k:?}");
        assert!(k.contains(&("ext2", l.ext2.0 as u64)), "{k:?}");
        // The gzip'd kernel sits inside the boot image, so it is hidden from the top-level scan.
        assert!(!k.iter().any(|(kind, _)| *kind == "gzip"), "{k:?}");
        let by = |kind: &str| r.regions.iter().find(|x| x.kind == kind).unwrap();
        assert_eq!(by("uimage").length, Some(l.uimage.1 as u64));
        assert_eq!(by("uimage").details["data_crc_ok"], true);
        assert_eq!(by("tar").length, Some(l.tar.1 as u64));
        assert_eq!(by("cpio-newc").length, Some(l.cpio.1 as u64));
        assert_eq!(by("zip").length, Some(l.zip.1 as u64));
        assert_eq!(by("ext2").length, Some(l.ext2.1 as u64));
        assert_eq!(by("squashfs").length, Some(l.squashfs.1 as u64));
        assert_eq!(r.regions.len(), 6, "{k:?}");
        // Inside the boot image: the gzip stream.
        let inner = scan(&img[64..l.uimage.1], &ScanOptions::default(), &no_stop);
        assert_eq!(kinds(&inner), vec![("gzip", 0)]);
        let (ent, bs) = entropy_map(&img, 4096, 10_000);
        assert_eq!(bs, 4096);
        assert!(ent.iter().any(|b| b.class == "padding"));
        assert!(ent.iter().any(|b| b.class == "compressed-or-encrypted"));
        let lay = layout(&img, &r.regions, &ent, 100);
        assert!(lay.recognised_bytes > 0 && lay.recognised_percent < 100.0);
        assert!(
            lay.high_entropy_unrecognised.iter().any(|s| s.offset <= l.noise.0 as u64 + 4096 && s.offset + s.length >= (l.noise.0 + l.noise.1) as u64 - 4096)
        );
        assert!(lay.gaps.iter().any(|g| g.offset == (l.ext2.0 + l.ext2.1) as u64));
    }

    #[test]
    fn many_formats_are_recognised() {
        let mut v = vec![0u8; 64];
        let put = |b: &[u8], v: &mut Vec<u8>| -> u64 {
            while !v.len().is_multiple_of(512) {
                v.push(0);
            }
            let o = v.len() as u64;
            v.extend_from_slice(b);
            v.extend_from_slice(&[0u8; 64]);
            o
        };
        let z = put(&fx::zlib(&b"zlib payload text ".repeat(8)), &mut v);
        // A truncated, made-up key; the marker is split so secret scanners don't flag it.
        let pem = concat!(
            "-----BEGIN RSA ",
            "PRIVATE KEY-----\nMIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu\n-----END RSA ",
            "PRIVATE KEY-----\n"
        );
        let pem = put(pem.as_bytes(), &mut v);
        let mut fdt = vec![0u8; 0x60];
        fdt[0..4].copy_from_slice(&[0xd0, 0x0d, 0xfe, 0xed]);
        fdt[4..8].copy_from_slice(&0x60u32.to_be_bytes());
        fdt[8..12].copy_from_slice(&0x38u32.to_be_bytes());
        fdt[12..16].copy_from_slice(&0x50u32.to_be_bytes());
        fdt[16..20].copy_from_slice(&0x28u32.to_be_bytes());
        fdt[20..24].copy_from_slice(&17u32.to_be_bytes());
        fdt[24..28].copy_from_slice(&16u32.to_be_bytes());
        let f = put(&fdt, &mut v);
        let mut zs = vec![0x28, 0xb5, 0x2f, 0xfd, 0x20, 5];
        let hdr: u32 = 1 | (5 << 3);
        zs.extend_from_slice(&hdr.to_le_bytes()[..3]);
        zs.extend_from_slice(b"hello");
        let zst = put(&zs, &mut v);
        let r = scan(&v, &ScanOptions::default(), &no_stop);
        let k = kinds(&r);
        assert!(k.contains(&("zlib", z)), "{k:?}");
        assert!(k.contains(&("pem-private-key", pem)), "{k:?}");
        assert!(k.contains(&("fdt", f)), "{k:?}");
        assert!(k.contains(&("zstd", zst)), "{k:?}");
        let key = r.regions.iter().find(|x| x.kind == "pem-private-key").unwrap();
        let shown = serde_json::to_string(key).unwrap();
        assert!(!shown.contains("MIIB"), "key material must never be reported");
    }

    #[test]
    fn cancel_and_caps() {
        let (img, _) = fx::image();
        let r = scan(&img, &ScanOptions::default(), &|| true);
        assert!(r.cancelled && r.regions.is_empty());
        let r = scan(&img, &ScanOptions { max_regions: 2, ..ScanOptions::default() }, &no_stop);
        assert!(r.truncated && r.regions.len() == 2);
        let (blocks, bs) = entropy_map(&img, 256, 8);
        assert!(blocks.len() <= 8 && bs >= 256);
    }

    #[test]
    fn hostile_inputs_do_not_panic() {
        let (img, _) = fx::image();
        let small: Vec<u8> = img.iter().copied().take(0x3000).collect();
        for m in craft_anything_testkit::mutations(&img) {
            let r = scan(&m, &ScanOptions::default(), &no_stop);
            let (e, _) = entropy_map(&m, 4096, 1000);
            let _ = layout(&m, &r.regions, &e, 50);
        }
        for n in (0..small.len()).step_by(7) {
            let _ = scan(&small[..n], &ScanOptions::default(), &no_stop);
        }
        for seed in 0..40 {
            let n = craft_anything_testkit::noise(seed, 64 * 1024);
            let r = scan(&n, &ScanOptions::default(), &no_stop);
            assert!(r.regions.iter().all(|x| x.confidence == "medium" || x.end().is_some_and(|e| e <= n.len() as u64)));
        }
        // Magic-dense garbage: every signature's first bytes repeated.
        let mut dense = Vec::new();
        for m in [
            &b"\x1f\x8b\x08"[..],
            b"\xfd7zXZ\0",
            b"BZh9",
            b"PK\x03\x04",
            b"hsqs",
            b"UBI#",
            b"\x27\x05\x19\x56",
            b"\xd0\x0d\xfe\xed",
            b"ANDROID!",
            b"\x7fELF\x02\x01\x01",
            b"MZ",
            b"070701",
            b"ustar",
            b"\x53\xef",
            b"CD001",
            b"-----BEGIN A-----",
            b"\x85\x19",
            b"\x31\x18\x10\x06",
            b"\x28\xb5\x2f\xfd",
            b"\x04\x22\x4d\x18",
        ] {
            for _ in 0..50 {
                dense.extend_from_slice(m);
                dense.extend_from_slice(&craft_anything_testkit::noise(dense.len() as u64, 13));
            }
        }
        let _ = scan(&dense, &ScanOptions::default(), &no_stop);
        for g in craft_anything_testkit::mutations(&fx::gzip(b"abcdefgh", None)) {
            let _ = gunzip(&g, 1 << 16);
            let _ = gzip_header(&g);
        }
    }
}
