//! Unreal Engine `.pak` archives: the footer, the index and the file list.
//!
//! A pak ends with a footer (`FPakInfo`): from version 7 an encryption key GUID, from version 4 an
//! "index is encrypted" byte, then the magic `0x5A6F12E1`, the version, the index offset, size and
//! SHA-1, from version 8 the compression method names (32 bytes each). The index starts with the
//! mount point. Up to version 9 it lists every file as a name plus an entry. From version 10 the
//! entries are packed into a bit-encoded buffer and the names live in a separate "full directory
//! index" (directory → file → where its entry is), which this module reads too.
//!
//! Everything here works on byte slices the caller read from the file (the footer is the last
//! [`FOOTER_READ`] bytes; the index and directory index are read at the offsets the earlier steps
//! give), so a many-gigabyte pak never has to be in memory. Encrypted indexes are reported, not
//! decrypted: that needs the game's own AES key.

use crate::common::FormatError;
use serde::Serialize;

/// `FPakInfo::PakFile_Magic`.
pub const MAGIC: u32 = 0x5A6F_12E1;
/// How many bytes from the end of the file hold any footer version (the largest is 222).
pub const FOOTER_READ: usize = 256;
/// The newest index layout this module reads.
pub const MAX_VERSION: i32 = 11;
/// Longest string (mount point, directory or file name) accepted, in characters.
const MAX_STRING: usize = 4096;

/// The pak's footer.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Footer {
    pub version: i32,
    pub index_offset: u64,
    pub index_size: u64,
    /// The index (and directory index) is AES-encrypted.
    pub encrypted_index: bool,
    /// The key's GUID (all zero when the default key, or none, is used), from version 7.
    pub encryption_key_guid: Option<String>,
    /// Compression method names by index (index 0 means "none"; these are 1, 2, …), from version 8.
    pub compression_methods: Vec<String>,
    /// How many method name slots the footer has: 4 in the first version-8 paks (Unreal 4.22),
    /// whose entries store the method index in one byte, else 5.
    #[serde(skip)]
    pub method_slots: usize,
}

/// One file in the pak.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Entry {
    /// The full path: the mount point, its directory and its name.
    pub path: String,
    /// Where the file's record starts in the pak.
    pub offset: u64,
    /// Bytes stored (compressed size when compressed).
    pub size: u64,
    pub uncompressed_size: u64,
    /// "none", a method name from the footer, or `method <n>` when the footer doesn't name it.
    pub compression: String,
    pub encrypted: bool,
    /// Where a stored file's bytes start in the pak (after the record that repeats its entry).
    #[serde(skip)]
    pub data_start: u64,
    /// A compressed file's blocks, as (start, end) positions in the pak.
    #[serde(skip)]
    pub blocks: Vec<(u64, u64)>,
}

/// What the index says.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Index {
    pub mount_point: String,
    /// Files the index counts (also those whose names aren't kept).
    pub file_count: u64,
    /// From version 10: where the names are kept, when they are. `None` when this pak keeps
    /// only hashed names (or is older, where names are in the index itself).
    pub directory_index: Option<(u64, u64)>,
    /// Files listed with their names (older paks: all of them; newer: once the directory index is read).
    pub entries: Vec<Entry>,
    /// From version 10: the packed entries the directory index points into.
    #[serde(skip)]
    pub encoded: Vec<u8>,
    /// From version 10: entries that didn't fit the packed form.
    #[serde(skip)]
    pub plain: Vec<Entry>,
}

/// A bounds-checked little-endian cursor (shared with [`crate::unreal_iostore`]).
pub(crate) struct Cur<'a> {
    data: &'a [u8],
    pos: usize,
}

impl<'a> Cur<'a> {
    pub(crate) fn new(data: &'a [u8]) -> Self {
        Cur { data, pos: 0 }
    }
    pub(crate) fn take(&mut self, n: usize, what: &str) -> Result<&'a [u8], FormatError> {
        let end = self.pos.checked_add(n).filter(|e| *e <= self.data.len()).ok_or_else(|| FormatError::Truncated(what.to_string()))?;
        let s = &self.data[self.pos..end];
        self.pos = end;
        Ok(s)
    }
    pub(crate) fn u8(&mut self, what: &str) -> Result<u8, FormatError> {
        Ok(self.take(1, what)?[0])
    }
    pub(crate) fn u32(&mut self, what: &str) -> Result<u32, FormatError> {
        let b = self.take(4, what)?;
        Ok(u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
    }
    pub(crate) fn i32(&mut self, what: &str) -> Result<i32, FormatError> {
        Ok(self.u32(what)? as i32)
    }
    pub(crate) fn u64(&mut self, what: &str) -> Result<u64, FormatError> {
        let b = self.take(8, what)?;
        Ok(u64::from_le_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]]))
    }
    /// A count that must be non-negative and plausible for what's left (`min_each` bytes each).
    pub(crate) fn count(&mut self, what: &str, min_each: usize) -> Result<usize, FormatError> {
        let n = self.i32(what)?;
        let n = usize::try_from(n).map_err(|_| FormatError::Malformed(format!("negative {what}")))?;
        if n.saturating_mul(min_each.max(1)) > self.data.len() - self.pos {
            return Err(FormatError::Malformed(format!("{what} {n} doesn't fit")));
        }
        Ok(n)
    }
    /// An `FString`: a signed length with its terminating NUL; negative means UTF-16.
    pub(crate) fn string(&mut self, what: &str) -> Result<String, FormatError> {
        let n = self.i32(what)?;
        let chars = n.unsigned_abs() as usize;
        if chars > MAX_STRING {
            return Err(FormatError::Malformed(format!("{what} is {chars} characters long")));
        }
        let s = if n >= 0 {
            String::from_utf8_lossy(self.take(chars, what)?).into_owned()
        } else {
            let b = self.take(chars * 2, what)?;
            String::from_utf16_lossy(&b.as_chunks::<2>().0.iter().map(|c| u16::from_le_bytes(*c)).collect::<Vec<_>>())
        };
        Ok(s.trim_end_matches('\0').to_string())
    }
}

/// Find and read the footer in the last bytes of a pak (`tail`, at most [`FOOTER_READ`]) of a
/// file `file_len` bytes long.
pub fn footer(tail: &[u8], file_len: u64) -> Result<Footer, FormatError> {
    let magic = MAGIC.to_le_bytes();
    if tail.len() < 4 + 4 + 8 + 8 + 20 {
        return Err(FormatError::Truncated("footer".into()));
    }
    // The last plausible footer: a known version whose index lies inside the file.
    for at in (0..tail.len().saturating_sub(4 + 4 + 8 + 8 + 20) + 1).rev() {
        if tail[at..at + 4] != magic {
            continue;
        }
        let mut c = Cur::new(&tail[at + 4..]);
        let version = c.i32("version")?;
        let (index_offset, index_size) = (c.u64("index offset")?, c.u64("index size")?);
        if !(1..=MAX_VERSION).contains(&version) || index_offset.checked_add(index_size).is_none_or(|end| end > file_len) {
            continue;
        }
        c.take(20, "index hash")?;
        let encrypted_index = version >= 4 && at >= 1 && tail[at - 1] != 0;
        let encryption_key_guid = (version >= 7 && at >= 17).then(|| tail[at - 17..at - 1].iter().map(|b| format!("{b:02x}")).collect::<String>());
        let mut compression_methods = Vec::new();
        let mut method_slots = 0;
        if version >= 8 {
            if version == 9 {
                // The "frozen index" flag.
                c.take(1, "frozen index flag")?;
            }
            while let Ok(name) = c.take(32, "compression method") {
                method_slots += 1;
                let name = String::from_utf8_lossy(name).trim_end_matches('\0').to_string();
                if !name.is_empty() {
                    compression_methods.push(name);
                }
            }
        }
        return Ok(Footer { version, index_offset, index_size, encrypted_index, encryption_key_guid, compression_methods, method_slots });
    }
    Err(FormatError::Malformed("no Unreal pak footer at the end of the file".into()))
}

/// Bytes of the record written before each file's data (its entry again), for a file with
/// `blocks` compression blocks.
fn record_size(footer: &Footer, compressed: bool, blocks: usize) -> u64 {
    let method = if footer.version == 8 && footer.method_slots == 4 { 1 } else { 4 };
    let mut n = 8 * 3 + method + 20;
    if footer.version <= 1 {
        n += 8;
    }
    if footer.version >= 3 {
        if compressed {
            n += 4 + 16 * blocks as u64;
        }
        n += 1 + 4;
    }
    n
}

fn method_name(footer: &Footer, index: u32) -> String {
    match index {
        0 => "none".into(),
        n => footer.compression_methods.get(n as usize - 1).cloned().unwrap_or_else(|| format!("method {n}")),
    }
}

/// An entry as written before version 10 (and in the "plain" list from 10 on).
fn plain_entry(c: &mut Cur, footer: &Footer, path: String) -> Result<Entry, FormatError> {
    let offset = c.u64("entry offset")?;
    let size = c.u64("entry size")?;
    let uncompressed_size = c.u64("entry uncompressed size")?;
    let compression = if footer.version >= 8 {
        let index = if footer.version == 8 && footer.method_slots == 4 { u32::from(c.u8("compression method")?) } else { c.u32("compression method")? };
        method_name(footer, index)
    } else {
        // Before 8: flags (1 zlib, 2 gzip, 4 custom; higher bits are hints).
        match c.u32("compression flags")? & 0x0f {
            0 => "none".into(),
            f if f & 1 != 0 => "zlib".into(),
            f if f & 2 != 0 => "gzip".into(),
            _ => "custom".into(),
        }
    };
    if footer.version <= 1 {
        c.u64("timestamp")?;
    }
    c.take(20, "entry hash")?;
    let compressed = compression != "none";
    let mut encrypted = false;
    let mut blocks = Vec::new();
    if footer.version >= 3 {
        if compressed {
            for _ in 0..c.count("compression blocks", 16)? {
                blocks.push((c.u64("block start")?, c.u64("block end")?));
            }
        }
        encrypted = c.u8("entry flags")? & 1 != 0;
        c.u32("compression block size")?;
    }
    // From version 5 block positions count from the entry's record; before, from the file's start.
    let base = if footer.version >= 5 { offset } else { 0 };
    let blocks = blocks.into_iter().map(|(s, e)| (base.saturating_add(s), base.saturating_add(e))).collect::<Vec<_>>();
    let data_start = offset.saturating_add(record_size(footer, compressed, blocks.len()));
    Ok(Entry { path, offset, size, uncompressed_size, compression, encrypted, data_start, blocks })
}

/// Join a mount point, a directory and a name with single slashes.
fn join(mount: &str, dir: &str, name: &str) -> String {
    let mut p = mount.to_string();
    for part in [dir, name] {
        let part = part.trim_start_matches('/');
        if part.is_empty() {
            continue;
        }
        if !p.is_empty() && !p.ends_with('/') {
            p.push('/');
        }
        p.push_str(part);
    }
    p
}

/// Read the (decrypted) index. Before version 10 it lists every file; from 10 it holds the
/// packed entries and where the directory index is, which [`directory`] then reads.
pub fn index(data: &[u8], footer: &Footer) -> Result<Index, FormatError> {
    if footer.encrypted_index {
        return Err(FormatError::Unsupported("the index is encrypted with the game's AES key".into()));
    }
    let mut c = Cur::new(data);
    let mount_point = c.string("mount point")?;
    let file_count = c.count("file count", 1)? as u64;
    if footer.version < 10 {
        let mut entries = Vec::with_capacity(file_count as usize);
        for _ in 0..file_count {
            let name = c.string("file name")?;
            entries.push(plain_entry(&mut c, footer, join(&mount_point, "", &name))?);
        }
        return Ok(Index { mount_point, file_count, directory_index: None, entries, encoded: Vec::new(), plain: Vec::new() });
    }
    c.u64("path hash seed")?;
    if c.u32("has path hash index")? != 0 {
        c.take(8 + 8 + 20, "path hash index")?;
    }
    let directory_index = if c.u32("has full directory index")? != 0 {
        let (offset, size) = (c.u64("directory index offset")?, c.u64("directory index size")?);
        c.take(20, "directory index hash")?;
        Some((offset, size))
    } else {
        None
    };
    let encoded_len = c.count("packed entries size", 1)?;
    let encoded = c.take(encoded_len, "packed entries")?.to_vec();
    let plain_count = c.count("plain entries", 8 + 8 + 8 + 4 + 20 + 1 + 4)?;
    let mut plain = Vec::with_capacity(plain_count);
    for _ in 0..plain_count {
        plain.push(plain_entry(&mut c, footer, String::new())?);
    }
    Ok(Index { mount_point, file_count, directory_index, entries: Vec::new(), encoded, plain })
}

/// Decode one packed entry (version 10 on) at `at` in the packed buffer.
fn packed_entry(encoded: &[u8], at: usize, footer: &Footer, path: String) -> Result<Entry, FormatError> {
    let mut c = Cur::new(encoded);
    c.take(at, "packed entry position")?;
    // Bits: 31 offset fits 32 bits, 30 uncompressed size fits, 29 size fits, 28-23 compression
    // method, 22 encrypted, 21-6 compression block count, 5-0 block size (0x3f: a u32 follows).
    let bits = c.u32("packed entry")?;
    if bits & 0x3f == 0x3f {
        c.u32("compression block size")?;
    }
    let mut num = |fits: bool, what: &str| -> Result<u64, FormatError> { if fits { c.u32(what).map(u64::from) } else { c.u64(what) } };
    let offset = num(bits & (1 << 31) != 0, "entry offset")?;
    let uncompressed_size = num(bits & (1 << 30) != 0, "entry uncompressed size")?;
    let method = (bits >> 23) & 0x3f;
    let size = if method != 0 { num(bits & (1 << 29) != 0, "entry size")? } else { uncompressed_size };
    let encrypted = bits & (1 << 22) != 0;
    let count = ((bits >> 6) & 0xffff) as usize;
    let data_start = offset.saturating_add(record_size(footer, method != 0, count));
    // One unencrypted block is the whole stored size; otherwise each block's size follows,
    // and encrypted blocks are padded to 16 bytes.
    let mut blocks = Vec::with_capacity(count.min(encoded.len() / 4));
    if count == 1 && !encrypted {
        blocks.push((data_start, data_start.saturating_add(size)));
    } else {
        let mut start = data_start;
        for _ in 0..count {
            let len = u64::from(c.u32("compression block")?);
            blocks.push((start, start.saturating_add(len)));
            start = start.saturating_add(if encrypted { len.div_ceil(16) * 16 } else { len });
        }
    }
    Ok(Entry { path, offset, size, uncompressed_size, compression: method_name(footer, method), encrypted, data_start, blocks })
}

/// Read the full directory index (version 10 on) and list every file with its name. `limit`
/// bounds how many are kept (the count of all is in [`Index::file_count`]).
pub fn directory(data: &[u8], footer: &Footer, index: &Index, limit: usize) -> Result<Vec<Entry>, FormatError> {
    let mut c = Cur::new(data);
    let mut out = Vec::new();
    let dirs = c.count("directories", 4 + 4)?;
    for _ in 0..dirs {
        let dir = c.string("directory name")?;
        let files = c.count("files", 4 + 4)?;
        for _ in 0..files {
            let name = c.string("file name")?;
            let at = c.i32("entry location")?;
            if out.len() >= limit {
                continue;
            }
            let path = join(&index.mount_point, &dir, &name);
            // Non-negative: a byte position in the packed entries; negative: -(n + 1) into the plain list.
            let entry = if at >= 0 {
                packed_entry(&index.encoded, at as usize, footer, path)?
            } else {
                let n = (-(i64::from(at)) - 1) as usize;
                match index.plain.get(n) {
                    Some(e) => Entry { path, ..e.clone() },
                    // A deleted or invalid record.
                    None => continue,
                }
            };
            out.push(entry);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fstring(s: &str) -> Vec<u8> {
        let mut v = ((s.len() + 1) as i32).to_le_bytes().to_vec();
        v.extend_from_slice(s.as_bytes());
        v.push(0);
        v
    }

    /// A version-11 footer after `body` (the index at `index_offset`, `index_size` bytes).
    fn footer_v11(index_offset: u64, index_size: u64, encrypted: bool) -> Vec<u8> {
        let mut f = vec![0u8; 16];
        f.push(u8::from(encrypted));
        f.extend_from_slice(&MAGIC.to_le_bytes());
        f.extend_from_slice(&11i32.to_le_bytes());
        f.extend_from_slice(&index_offset.to_le_bytes());
        f.extend_from_slice(&index_size.to_le_bytes());
        f.extend_from_slice(&[0u8; 20]);
        for name in ["Zlib", "Oodle", "", "", ""] {
            let mut n = name.as_bytes().to_vec();
            n.resize(32, 0);
            f.extend_from_slice(&n);
        }
        assert_eq!(f.len(), 221);
        f
    }

    #[test]
    fn reads_a_version_11_pak() {
        // Packed entries: a stored file (all 32-bit) and a zlib one with a u32 block size.
        let mut encoded = Vec::new();
        encoded.extend_from_slice(&((1u32 << 31) | (1 << 30)).to_le_bytes());
        encoded.extend_from_slice(&100u32.to_le_bytes());
        encoded.extend_from_slice(&5u32.to_le_bytes());
        let second = encoded.len() as i32;
        encoded.extend_from_slice(&((1u32 << 31) | (1 << 30) | (1 << 29) | (1 << 23) | (1 << 6) | 0x3f).to_le_bytes());
        encoded.extend_from_slice(&65536u32.to_le_bytes());
        encoded.extend_from_slice(&200u32.to_le_bytes());
        encoded.extend_from_slice(&4000u32.to_le_bytes());
        encoded.extend_from_slice(&900u32.to_le_bytes());

        let mut index = fstring("../../../");
        index.extend_from_slice(&3i32.to_le_bytes());
        index.extend_from_slice(&0u64.to_le_bytes());
        index.extend_from_slice(&0u32.to_le_bytes()); // no path hash index
        index.extend_from_slice(&1u32.to_le_bytes()); // a full directory index
        index.extend_from_slice(&5000u64.to_le_bytes());
        index.extend_from_slice(&64u64.to_le_bytes());
        index.extend_from_slice(&[0u8; 20]);
        index.extend_from_slice(&(encoded.len() as i32).to_le_bytes());
        index.extend_from_slice(&encoded);
        index.extend_from_slice(&1i32.to_le_bytes()); // one plain entry
        for v in [300u64, 7, 7] {
            index.extend_from_slice(&v.to_le_bytes());
        }
        index.extend_from_slice(&0u32.to_le_bytes());
        index.extend_from_slice(&[0u8; 20]);
        index.push(1); // encrypted
        index.extend_from_slice(&0u32.to_le_bytes());

        let mut dirs = 2i32.to_le_bytes().to_vec();
        dirs.extend(fstring("/"));
        dirs.extend_from_slice(&1i32.to_le_bytes());
        dirs.extend(fstring("Readme.txt"));
        dirs.extend_from_slice(&0i32.to_le_bytes());
        dirs.extend(fstring("Game/Maps/"));
        dirs.extend_from_slice(&2i32.to_le_bytes());
        dirs.extend(fstring("Level.umap"));
        dirs.extend_from_slice(&second.to_le_bytes());
        dirs.extend(fstring("Secret.uasset"));
        dirs.extend_from_slice(&(-1i32).to_le_bytes());

        let file_len = 6000;
        let f = footer(&footer_v11(1000, index.len() as u64, false), file_len).unwrap();
        assert_eq!((f.version, f.index_offset, f.encrypted_index), (11, 1000, false));
        assert_eq!(f.compression_methods, ["Zlib", "Oodle"]);
        assert_eq!(f.encryption_key_guid.as_deref(), Some("00000000000000000000000000000000"));

        let i = index_of(&index, &f);
        assert_eq!((i.mount_point.as_str(), i.file_count, i.directory_index), ("../../../", 3, Some((5000, 64))));
        let files = directory(&dirs, &f, &i, 10).unwrap();
        let rows: Vec<(&str, u64, u64, u64, &str, bool)> =
            files.iter().map(|e| (e.path.as_str(), e.offset, e.size, e.uncompressed_size, e.compression.as_str(), e.encrypted)).collect();
        assert_eq!(
            rows,
            [
                ("../../../Readme.txt", 100, 5, 5, "none", false),
                ("../../../Game/Maps/Level.umap", 200, 900, 4000, "Zlib", false),
                ("../../../Game/Maps/Secret.uasset", 300, 7, 7, "none", true),
            ]
        );
        assert_eq!(directory(&dirs, &f, &i, 1).unwrap().len(), 1, "never more than asked for");
        // A stored file's bytes follow its 53-byte record; one zlib block follows its 73-byte one.
        assert_eq!((files[0].data_start, files[0].blocks.clone()), (153, vec![]));
        assert_eq!((files[1].data_start, files[1].blocks.clone()), (273, vec![(273, 1173)]));
    }

    fn index_of(index: &[u8], f: &Footer) -> Index {
        super::index(index, f).unwrap()
    }

    #[test]
    fn reads_an_older_index_with_names() {
        // Version 8 (Unreal 4.22): names and entries together; a 4-name footer.
        let mut index = fstring("../../../Game/");
        index.extend_from_slice(&1i32.to_le_bytes());
        index.extend(fstring("Content/Paks/a.bin"));
        for v in [64u64, 10, 20] {
            index.extend_from_slice(&v.to_le_bytes());
        }
        index.push(1); // compression method 1, one byte in a 4.22 pak
        index.extend_from_slice(&[0u8; 20]);
        index.extend_from_slice(&1i32.to_le_bytes()); // one block, from the record's start
        index.extend_from_slice(&70u64.to_le_bytes());
        index.extend_from_slice(&80u64.to_le_bytes());
        index.push(0);
        index.extend_from_slice(&65536u32.to_le_bytes());

        let mut tail = vec![0u8; 16];
        tail.push(0);
        tail.extend_from_slice(&MAGIC.to_le_bytes());
        tail.extend_from_slice(&8i32.to_le_bytes());
        tail.extend_from_slice(&0u64.to_le_bytes());
        tail.extend_from_slice(&(index.len() as u64).to_le_bytes());
        tail.extend_from_slice(&[0u8; 20]);
        let mut zlib = b"Zlib".to_vec();
        zlib.resize(32, 0);
        tail.extend_from_slice(&zlib);
        tail.extend_from_slice(&[0u8; 96]);
        let f = footer(&tail, 4096).unwrap();
        assert_eq!((f.version, f.compression_methods.clone(), f.method_slots), (8, vec!["Zlib".to_string()], 4));
        let i = super::index(&index, &f).unwrap();
        assert_eq!(i.entries.len(), 1);
        // The record: 3 sizes, a one-byte method, the hash, one block, flags and block size.
        let record = 24 + 1 + 20 + 4 + 16 + 1 + 4;
        assert_eq!(
            i.entries[0],
            Entry {
                path: "../../../Game/Content/Paks/a.bin".into(),
                offset: 64,
                size: 10,
                uncompressed_size: 20,
                compression: "Zlib".into(),
                encrypted: false,
                data_start: 64 + record,
                blocks: vec![(134, 144)],
            }
        );
    }

    #[test]
    fn refuses_what_it_cannot_read() {
        assert!(footer(&[0u8; 256], 1 << 20).is_err(), "no magic");
        // A footer whose index would lie outside the file isn't taken.
        assert!(footer(&footer_v11(1 << 40, 10, false), 4096).is_err());
        let f = footer(&footer_v11(0, 10, true), 4096).unwrap();
        assert!(f.encrypted_index);
        assert!(matches!(super::index(b"anything", &f), Err(FormatError::Unsupported(_))));
        // A huge count is refused before anything is allocated.
        let mut bad = fstring("../../../");
        bad.extend_from_slice(&i32::MAX.to_le_bytes());
        let f = footer(&footer_v11(0, 10, false), 4096).unwrap();
        assert!(super::index(&bad, &f).is_err());
        // Garbage never panics.
        for n in 0..64 {
            let junk: Vec<u8> = (0..n * 7).map(|i| (i * 31 + n) as u8).collect();
            let _ = super::index(&junk, &f);
            let _ = footer(&junk, 1 << 20);
        }
    }
}
