//! Unity asset bundles in the UnityFS format (`*.bundle`, `data.unity3d`, Addressables).
//!
//! A big-endian header: `UnityFS\0`, the format version, the Unity version and revision strings,
//! the bundle's size, the compressed and uncompressed sizes of the block table and flags (the low
//! six bits are its compression: 0 none, 1 LZMA, 2 LZ4, 3 LZ4HC; 0x80 puts it at the end of the
//! file; 0x200 pads the data to 16 bytes). From format 7 the block table starts on 16 bytes. The
//! block table holds a hash, the data blocks (their sizes and compression) and the nodes: the
//! files inside the bundle, by offset and size in the uncompressed data, with a path each.

use crate::common::FormatError;
use crate::decompress;
use serde::Serialize;

/// The first 8 bytes.
pub const MAGIC: &[u8; 8] = b"UnityFS\0";
/// Bytes enough for any header.
pub const HEADER_READ: usize = 256;
/// The largest block table accepted, uncompressed.
const MAX_TABLE: u32 = 64 << 20;

/// What the header says.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Header {
    pub format_version: u32,
    pub unity_version: String,
    pub unity_revision: String,
    pub size: u64,
    pub flags: u32,
    /// Where the block table is and its sizes.
    pub table_offset: u64,
    pub table_size: u32,
    pub table_uncompressed_size: u32,
    /// Where the data blocks start.
    pub data_offset: u64,
}

/// A data block.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Block {
    pub uncompressed_size: u32,
    pub compressed_size: u32,
    /// The low six bits: its compression.
    pub flags: u16,
}

/// A file inside the bundle.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Node {
    pub path: String,
    /// Where it is in the uncompressed data, and its size.
    pub offset: u64,
    pub size: u64,
    /// 4 marks a serialized file (the bundle's objects).
    pub flags: u32,
}

/// A compression's name by its number.
pub fn compression_name(n: u32) -> &'static str {
    match n {
        0 => "none",
        1 => "LZMA",
        2 => "LZ4",
        3 => "LZ4HC",
        _ => "unknown",
    }
}

fn cstr(data: &[u8], pos: &mut usize, what: &str) -> Result<String, FormatError> {
    let rest = data.get(*pos..).unwrap_or_default();
    let n = rest.iter().take(256).position(|b| *b == 0).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
    let s = String::from_utf8_lossy(&rest[..n]).into_owned();
    *pos += n + 1;
    Ok(s)
}

fn be<const N: usize>(data: &[u8], pos: &mut usize, what: &str) -> Result<[u8; N], FormatError> {
    let b = data.get(*pos..*pos + N).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
    *pos += N;
    let mut a = [0; N];
    a.copy_from_slice(b);
    Ok(a)
}

/// Read the header (the first [`HEADER_READ`] bytes) of a bundle `file_len` bytes long.
pub fn header(data: &[u8], file_len: u64) -> Result<Header, FormatError> {
    if !data.starts_with(MAGIC) {
        return Err(FormatError::Malformed("not a UnityFS bundle".into()));
    }
    let mut pos = MAGIC.len();
    let format_version = u32::from_be_bytes(be(data, &mut pos, "format version")?);
    let unity_version = cstr(data, &mut pos, "Unity version")?;
    let unity_revision = cstr(data, &mut pos, "Unity revision")?;
    let size = u64::from_be_bytes(be(data, &mut pos, "size")?);
    let table_size = u32::from_be_bytes(be(data, &mut pos, "block table size")?);
    let table_uncompressed_size = u32::from_be_bytes(be(data, &mut pos, "block table size")?);
    let flags = u32::from_be_bytes(be(data, &mut pos, "flags")?);
    if !(6..=8).contains(&format_version) {
        return Err(FormatError::Unsupported(format!("UnityFS format {format_version}")));
    }
    let mut at = pos as u64;
    if format_version >= 7 {
        at = at.div_ceil(16) * 16;
    }
    let (table_offset, mut data_offset) =
        if flags & 0x80 != 0 { (file_len.saturating_sub(u64::from(table_size)), at) } else { (at, at + u64::from(table_size)) };
    if flags & 0x200 != 0 {
        data_offset = data_offset.div_ceil(16) * 16;
    }
    if table_offset + u64::from(table_size) > file_len || table_uncompressed_size > MAX_TABLE {
        return Err(FormatError::Malformed("the block table doesn't fit the file".into()));
    }
    Ok(Header { format_version, unity_version, unity_revision, size, flags, table_offset, table_size, table_uncompressed_size, data_offset })
}

/// Decompress one piece of a bundle with compression `kind` (the low six bits of a flags field).
pub fn decompress(kind: u32, input: &[u8], out_len: u32) -> Result<Vec<u8>, FormatError> {
    let bad = |e: decompress::DecompressError| FormatError::Malformed(format!("a {} block: {e}", compression_name(kind)));
    match kind {
        0 => Ok(input.to_vec()),
        // Unity's LZMA is the 5 property bytes and the stream; the `.lzma` form adds the size.
        1 => {
            let props = input.get(..5).ok_or_else(|| FormatError::Truncated("LZMA properties".into()))?;
            let mut alone = props.to_vec();
            alone.extend_from_slice(&u64::from(out_len).to_le_bytes());
            alone.extend_from_slice(&input[5..]);
            decompress::lzma(&alone, u64::from(out_len)).map_err(bad)
        }
        2 | 3 => decompress::lz4_block(input, out_len as usize).map_err(bad),
        n => Err(FormatError::Unsupported(format!("compression {n}"))),
    }
}

/// Read the block table (`table` as stored in the file).
pub fn table(table: &[u8], h: &Header) -> Result<(Vec<Block>, Vec<Node>), FormatError> {
    let t = decompress(h.flags & 0x3f, table, h.table_uncompressed_size)?;
    let mut pos = 16; // the data's hash
    let count = |pos: &mut usize, what: &str, each: usize| -> Result<usize, FormatError> {
        let n = usize::try_from(i32::from_be_bytes(be(&t, pos, what)?)).map_err(|_| FormatError::Malformed(format!("negative {what}")))?;
        if n.saturating_mul(each) > t.len() {
            return Err(FormatError::Malformed(format!("{n} {what} don't fit")));
        }
        Ok(n)
    };
    let mut blocks = Vec::new();
    for _ in 0..count(&mut pos, "blocks", 10)? {
        let uncompressed_size = u32::from_be_bytes(be(&t, &mut pos, "block")?);
        let compressed_size = u32::from_be_bytes(be(&t, &mut pos, "block")?);
        let flags = u16::from_be_bytes(be(&t, &mut pos, "block")?);
        blocks.push(Block { uncompressed_size, compressed_size, flags });
    }
    let mut nodes = Vec::new();
    for _ in 0..count(&mut pos, "nodes", 21)? {
        let offset = u64::from_be_bytes(be(&t, &mut pos, "node")?);
        let size = u64::from_be_bytes(be(&t, &mut pos, "node")?);
        let flags = u32::from_be_bytes(be(&t, &mut pos, "node")?);
        let path = cstr(&t, &mut pos, "node path")?;
        nodes.push(Node { path, offset, size, flags });
    }
    Ok((blocks, nodes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_bundle_and_its_files() {
        let file = craft_anything_testkit::games::unity_bundle();
        let h = header(&file[..HEADER_READ.min(file.len())], file.len() as u64).unwrap();
        assert_eq!((h.format_version, h.unity_revision.as_str(), h.flags & 0x3f), (8, "2022.3.62f1", 2));
        let (blocks, nodes) = table(&file[h.table_offset as usize..(h.table_offset + u64::from(h.table_size)) as usize], &h).unwrap();
        assert_eq!(blocks.len(), 1);
        assert_eq!(h.data_offset + u64::from(blocks[0].compressed_size), file.len() as u64, "the data fills the rest");
        let rows: Vec<(&str, u64, u64, u32)> = nodes.iter().map(|n| (n.path.as_str(), n.offset, n.size, n.flags)).collect();
        let n = craft_anything_testkit::games::unity_assets().len() as u64;
        assert_eq!(rows, [("CAB-0123456789abcdef", 0, n, 4), ("CAB-0123456789abcdef.resS", n, 5, 0)]);
    }

    #[test]
    fn refuses_what_it_cannot_read() {
        let file = craft_anything_testkit::games::unity_bundle();
        assert!(header(b"UnityWeb\0", 100).is_err());
        let mut v5 = file.clone();
        v5[8..12].copy_from_slice(&5u32.to_be_bytes());
        assert!(matches!(header(&v5, v5.len() as u64), Err(FormatError::Unsupported(_))));
        assert!(header(&file, 40).is_err(), "a table past the end");
        let h = header(&file, file.len() as u64).unwrap();
        let t = &file[h.table_offset as usize..(h.table_offset + u64::from(h.table_size)) as usize];
        for cut in 0..t.len() {
            let _ = table(&t[..cut], &h);
        }
        assert!(decompress(9, b"x", 1).is_err());
    }
}
