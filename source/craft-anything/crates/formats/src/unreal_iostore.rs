//! Unreal Engine IoStore containers: the `.utoc` table of contents beside each `.ucas` data file.
//!
//! The TOC starts with a 144-byte header (magic `-==--==--==--==-`, version, counts, the
//! compression block size, the directory index size, container flags). Then, in order: a 12-byte
//! chunk id per chunk, a 10-byte offset-and-length per chunk (two 40-bit big-endian numbers), from
//! version 4 the perfect-hash seeds and from 5 the chunks outside the perfect hash, the 12-byte
//! compression blocks, the compression method names, for signed containers the signatures, and
//! (from version 2, when indexed) the directory index: the mount point, a tree of directories and
//! files whose names live in a string table, each file pointing at its chunk.
//!
//! An encrypted container's directory index is encrypted too: it is reported, not decrypted.

use crate::common::FormatError;
use crate::unreal_pak::Cur;
use serde::Serialize;

/// The TOC's first 16 bytes.
pub const MAGIC: &[u8; 16] = b"-==--==--==--==-";
/// Bytes of the TOC header.
pub const HEADER_SIZE: usize = 144;
/// The newest TOC version this module reads.
pub const MAX_VERSION: u8 = 8;
/// "No entry" in the directory index.
const NONE: u32 = u32::MAX;

/// What the container's flags say.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub struct Flags {
    pub compressed: bool,
    pub encrypted: bool,
    pub signed: bool,
    pub indexed: bool,
}

/// The TOC header.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Header {
    pub version: u8,
    pub chunk_count: u32,
    pub block_count: u32,
    pub block_size: u32,
    pub directory_index_size: u32,
    pub partition_count: u32,
    pub partition_size: u64,
    pub flags: Flags,
    /// The key's GUID, when one is named (all zero otherwise).
    pub encryption_key_guid: String,
    #[serde(skip)]
    method_count: u32,
    #[serde(skip)]
    method_length: u32,
    #[serde(skip)]
    hash_seeds: u32,
    #[serde(skip)]
    without_hash: u32,
}

/// A compression block: where it is in the `.ucas`, its sizes and its method (0 is none).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Block {
    pub offset: u64,
    pub compressed_size: u32,
    pub uncompressed_size: u32,
    pub method: u8,
}

/// One file the directory index names.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct File {
    /// The mount point, its directories and its name.
    pub path: String,
    /// Bytes once uncompressed.
    pub size: u64,
    /// Bytes stored in the `.ucas` (its blocks' compressed sizes).
    pub stored_size: u64,
    /// The first block's method: "none", a name from the TOC, or `method <n>`.
    pub compression: String,
    /// The chunk it points at.
    pub chunk: u32,
}

/// The table of contents.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Toc {
    pub header: Header,
    /// Offset (in the uncompressed stream) and length of each chunk.
    pub chunks: Vec<(u64, u64)>,
    pub blocks: Vec<Block>,
    pub methods: Vec<String>,
    /// The directory index as stored (encrypted when the container is).
    pub directory_index: Vec<u8>,
}

/// Read the 144-byte header.
pub fn header(data: &[u8]) -> Result<Header, FormatError> {
    let mut c = Cur::new(data);
    if c.take(16, "magic")? != MAGIC {
        return Err(FormatError::Malformed("not an IoStore table of contents".into()));
    }
    let version = c.u8("version")?;
    if version == 0 || version > MAX_VERSION {
        return Err(FormatError::Unsupported(format!("IoStore version {version}")));
    }
    c.take(3, "reserved")?;
    let header_size = c.u32("header size")?;
    if header_size as usize != HEADER_SIZE {
        return Err(FormatError::Malformed(format!("a {header_size}-byte header")));
    }
    let chunk_count = c.u32("chunk count")?;
    let block_count = c.u32("block count")?;
    let block_entry_size = c.u32("block entry size")?;
    if block_entry_size != 12 {
        return Err(FormatError::Unsupported(format!("{block_entry_size}-byte compression blocks")));
    }
    let method_count = c.u32("method count")?;
    let method_length = c.u32("method name length")?;
    let block_size = c.u32("compression block size")?;
    let directory_index_size = c.u32("directory index size")?;
    let partition_count = c.u32("partition count")?;
    c.u64("container id")?;
    let encryption_key_guid = c.take(16, "key guid")?.iter().map(|b| format!("{b:02x}")).collect();
    let bits = c.u8("container flags")?;
    c.take(3, "reserved")?;
    let hash_seeds = c.u32("perfect hash seeds")?;
    let partition_size = c.u64("partition size")?;
    let without_hash = c.u32("chunks without perfect hash")?;
    let flags = Flags { compressed: bits & 1 != 0, encrypted: bits & 2 != 0, signed: bits & 4 != 0, indexed: bits & 8 != 0 };
    Ok(Header {
        version,
        chunk_count,
        block_count,
        block_size,
        directory_index_size,
        partition_count,
        partition_size,
        flags,
        encryption_key_guid,
        method_count,
        method_length,
        hash_seeds: if version >= 4 { hash_seeds } else { 0 },
        without_hash: if version >= 5 { without_hash } else { 0 },
    })
}

/// A 40-bit big-endian number.
fn be40(b: &[u8]) -> u64 {
    b.iter().take(5).fold(0, |n, x| (n << 8) | u64::from(*x))
}

/// Read the whole table of contents (the `.utoc` file).
pub fn toc(data: &[u8]) -> Result<Toc, FormatError> {
    let header = header(data)?;
    let mut c = Cur::new(data);
    c.take(HEADER_SIZE, "header")?;
    let n = header.chunk_count as usize;
    if n.saturating_mul(22) > data.len() {
        return Err(FormatError::Malformed(format!("{n} chunks don't fit")));
    }
    c.take(n * 12, "chunk ids")?;
    let chunks = c.take(n * 10, "chunk offsets")?.as_chunks::<10>().0.iter().map(|e| (be40(&e[..5]), be40(&e[5..]))).collect();
    c.take(header.hash_seeds as usize * 4, "perfect hash seeds")?;
    c.take(header.without_hash as usize * 4, "chunks without perfect hash")?;
    let blocks = c
        .take((header.block_count as usize).saturating_mul(12), "compression blocks")?
        .as_chunks::<12>()
        .0
        .iter()
        .map(|b| Block {
            offset: u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], 0, 0, 0]),
            compressed_size: u32::from_le_bytes([b[5], b[6], b[7], 0]),
            uncompressed_size: u32::from_le_bytes([b[8], b[9], b[10], 0]),
            method: b[11],
        })
        .collect();
    // A block names its method in one byte, so only the first 255 names can be used; the rest are
    // skipped, never collected (a zero name length would otherwise read billions of empty names).
    let named = header.method_count.min(u32::from(u8::MAX));
    let methods = (0..named)
        .map(|_| c.take(header.method_length as usize, "compression method").map(|b| String::from_utf8_lossy(b).trim_end_matches('\0').to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    c.take(((header.method_count - named) as usize).saturating_mul(header.method_length as usize), "compression methods")?;
    if header.flags.signed {
        let hash = c.count("signature size", 2)?;
        c.take(hash * 2, "signatures")?;
        c.take((header.block_count as usize).saturating_mul(20), "block signatures")?;
    }
    let directory_index = if header.version >= 2 && header.flags.indexed && header.directory_index_size > 0 {
        c.take(header.directory_index_size as usize, "directory index")?.to_vec()
    } else {
        Vec::new()
    };
    Ok(Toc { header, chunks, blocks, methods, directory_index })
}

impl Toc {
    fn method(&self, index: u8) -> String {
        match index {
            0 => "none".into(),
            n => self.methods.get(n as usize - 1).cloned().unwrap_or_else(|| format!("method {n}")),
        }
    }

    /// The stored size and first method of a chunk's blocks.
    fn stored(&self, chunk: usize) -> (u64, String) {
        let Some(&(offset, length)) = self.chunks.get(chunk) else { return (0, "none".into()) };
        let size = u64::from(self.header.block_size.max(1));
        let first = (offset / size) as usize;
        let count = length.div_ceil(size) as usize;
        let blocks = self.blocks.get(first..first.saturating_add(count).min(self.blocks.len())).unwrap_or_default();
        (blocks.iter().map(|b| u64::from(b.compressed_size)).sum(), blocks.first().map_or_else(|| "none".into(), |b| self.method(b.method)))
    }
}

/// List the files the (decrypted) directory index names, up to `limit`. The second value counts
/// them all.
pub fn files(toc: &Toc, limit: usize) -> Result<(String, Vec<File>, usize), FormatError> {
    if toc.header.flags.encrypted {
        return Err(FormatError::Unsupported("the directory index is encrypted with the game's AES key".into()));
    }
    if !toc.header.flags.indexed || toc.header.version < 2 {
        return Ok((String::new(), Vec::new(), 0));
    }
    let mut c = Cur::new(&toc.directory_index);
    let mount = c.string("mount point")?;
    let dirs = (0..c.count("directories", 16)?)
        .map(|_| Ok([c.u32("name")?, c.u32("first child")?, c.u32("next sibling")?, c.u32("first file")?]))
        .collect::<Result<Vec<_>, FormatError>>()?;
    let file_entries =
        (0..c.count("files", 12)?).map(|_| Ok([c.u32("name")?, c.u32("next file")?, c.u32("chunk")?])).collect::<Result<Vec<_>, FormatError>>()?;
    let strings = (0..c.count("names", 4)?).map(|_| c.string("name")).collect::<Result<Vec<_>, _>>()?;
    let name = |i: u32| strings.get(i as usize).map(String::as_str);

    let mut out = Vec::new();
    let mut total = 0;
    // Depth-first from the root (directory 0); every directory and file is visited at most once,
    // so a damaged index can't loop.
    let mut stack = if dirs.is_empty() { Vec::new() } else { vec![(0u32, mount.clone())] };
    let (mut seen_dirs, mut seen_files) = (vec![false; dirs.len()], vec![false; file_entries.len()]);
    while let Some((d, path)) = stack.pop() {
        let Some(seen) = seen_dirs.get_mut(d as usize).filter(|s| !**s) else { continue };
        *seen = true;
        let [_, first_child, _, first_file] = dirs[d as usize];
        let mut f = first_file;
        while f != NONE {
            let Some(seen) = seen_files.get_mut(f as usize).filter(|s| !**s) else { break };
            *seen = true;
            let [n, next, chunk] = file_entries[f as usize];
            total += 1;
            if out.len() < limit {
                let (stored_size, compression) = toc.stored(chunk as usize);
                let size = toc.chunks.get(chunk as usize).map_or(0, |c| c.1);
                out.push(File { path: format!("{path}{}", name(n).unwrap_or("?")), size, stored_size, compression, chunk });
            }
            f = next;
        }
        let mut child = first_child;
        let mut guard = 0;
        while child != NONE && (child as usize) < dirs.len() && guard < dirs.len() {
            guard += 1;
            stack.push((child, format!("{path}{}/", name(dirs[child as usize][0]).unwrap_or("?"))));
            child = dirs[child as usize][2];
        }
    }
    Ok((mount, out, total))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample(flags: u8) -> Vec<u8> {
        craft_anything_testkit::games::unreal_utoc(flags, NONE)
    }

    #[test]
    fn lists_a_version_8_container() {
        for flags in [0x9, 0xd] {
            let toc = toc(&sample(flags)).unwrap();
            assert_eq!((toc.header.version, toc.header.chunk_count, toc.header.block_size, toc.header.flags.signed), (8, 3, 65536, flags == 0xd));
            assert_eq!(toc.methods, ["Oodle"]);
            let (mount, files, total) = files(&toc, 10).unwrap();
            assert_eq!((mount.as_str(), total), ("../../../", 3));
            let rows: Vec<(&str, u64, u64, &str)> = files.iter().map(|f| (f.path.as_str(), f.size, f.stored_size, f.compression.as_str())).collect();
            assert_eq!(
                rows,
                [
                    ("../../../Game/B.uasset", 10, 8, "Oodle"),
                    ("../../../Game/Maps/A.uasset", 100_000, 50_000, "Oodle"),
                    ("../../../Game/Maps/A.ubulk", 5, 5, "none"),
                ]
            );
            assert_eq!(super::files(&toc, 1).unwrap().1.len(), 1, "never more than asked for");
        }
        let unindexed = toc(&sample(0x1)).unwrap();
        assert_eq!(files(&unindexed, 10).unwrap(), (String::new(), Vec::new(), 0));
    }

    #[test]
    fn refuses_what_it_cannot_read() {
        let mut encrypted = sample(0xb);
        let t = toc(&encrypted).unwrap();
        assert!(matches!(files(&t, 10), Err(FormatError::Unsupported(_))));
        encrypted[16] = 99;
        assert!(matches!(header(&encrypted), Err(FormatError::Unsupported(_))), "unknown version");
        assert!(header(b"-==--==--==--==-").is_err(), "too short");
        assert!(header(&[0; 144]).is_err(), "no magic");
        // Garbage after a good header never panics.
        let good = sample(0x9);
        for cut in (HEADER_SIZE..good.len()).step_by(7) {
            if let Ok(t) = toc(&good[..cut]) {
                let _ = files(&t, 10);
            }
        }
        // A directory that loops back to its parent is visited once.
        for sibling in [1, 2, 7] {
            let t = toc(&craft_anything_testkit::games::unreal_utoc(0x9, sibling)).unwrap();
            assert_eq!(files(&t, 10).unwrap().2, 3, "sibling {sibling}");
        }
    }

    #[test]
    fn a_huge_count_of_empty_method_names_is_not_collected() {
        let mut d = sample(0x9);
        d[36..40].copy_from_slice(&0x8000_0000u32.to_le_bytes());
        d[40..44].copy_from_slice(&0u32.to_le_bytes());
        let t = toc(&d).unwrap();
        assert_eq!(t.methods.len(), 255);
        // Names past the 255 a block can point at are skipped, so the directory index still reads.
        // The sample's one 32-byte name (after the header, chunks, seed and blocks) is taken out.
        let mut d = sample(0x9);
        assert_eq!(&d[262..267], b"Oodle");
        d.drain(262..294);
        d[36..40].copy_from_slice(&300u32.to_le_bytes());
        d[40..44].copy_from_slice(&0u32.to_le_bytes());
        assert_eq!(files(&toc(&d).unwrap(), 10).unwrap().2, 3);
        // More names than the file holds is refused, not read past the end.
        let mut d = sample(0x9);
        d[36..40].copy_from_slice(&300u32.to_le_bytes());
        d[40..44].copy_from_slice(&32u32.to_le_bytes());
        assert!(toc(&d).is_err());
    }
}
