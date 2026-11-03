//! Programs and game files that carry other files inside one file: one seam for reading them.
//! A reader says whether a file is its kind, lists what's inside and hands back one member's bytes.
//! Add a kind with a [`PackedFormat`] implementation and one line in [`READERS`]. No I/O and no
//! execution: readers only look at the bytes they're given.

use crate::common::FormatError;
use crate::decompress;
use serde::Serialize;
use serde_json::Value;

/// Most members one listing keeps; a reader sets `truncated` when it stops here.
pub const MAX_ENTRIES: usize = 200_000;

/// One file carried inside a packed file.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct PackedEntry {
    /// The member's path inside the packed file, as the file names it.
    pub path: String,
    /// Where its stored bytes start in the packed file.
    pub offset: u64,
    /// How many bytes it takes up in the packed file.
    pub stored_size: u64,
    /// Its size once unpacked, when the file says.
    pub size: Option<u64>,
    /// How it's stored.
    pub compression: Compression,
    /// What the file says this member is (reader-specific; `None` when it doesn't say).
    pub kind: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Compression {
    None,
    Deflate,
    Zlib,
    Gzip,
    Zstd,
    /// Stored in a way we can list but not read back (encrypted, or an unknown method).
    Unreadable,
}

/// What a reader found in a packed file.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct PackedListing {
    /// Reader-specific facts: versions, flags, entry point.
    pub facts: Value,
    pub entries: Vec<PackedEntry>,
    /// Things the person should know about this listing (a damaged part, a limit reached).
    pub notes: Vec<String>,
    /// True when a limit stopped the listing before its end.
    pub truncated: bool,
}

/// A kind of packed file.
pub trait PackedFormat: Sync {
    /// Stable id, in results and the `format` parameter.
    fn id(&self) -> &'static str;
    /// What people call it.
    fn title(&self) -> &'static str;
    /// Cheap check of the bytes. A yes may still fail in `list`; a no means another reader gets it.
    fn detect(&self, data: &[u8]) -> bool;
    /// What's inside.
    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError>;
    /// One member's bytes, unpacked, at most `max_bytes`.
    fn read(&self, data: &[u8], entry: &PackedEntry, max_bytes: u64) -> Result<Vec<u8>, FormatError> {
        read_stored(data, entry, max_bytes)
    }
}

/// Every reader, most specific first: the first whose `detect` says yes reads the file.
pub static READERS: &[&dyn PackedFormat] = &[
    &crate::bun_program::BunProgram,
    &crate::node_sea::NodeSea,
    &crate::dotnet_bundle::DotnetBundle,
    &crate::godot_pck::GodotPck,
    &crate::pyinstaller::PyInstaller,
];

/// The reader for these bytes, if any.
pub fn detect(data: &[u8]) -> Option<&'static dyn PackedFormat> {
    READERS.iter().copied().find(|r| r.detect(data))
}

/// The reader with this id, if any.
pub fn by_id(id: &str) -> Option<&'static dyn PackedFormat> {
    READERS.iter().copied().find(|r| r.id() == id)
}

/// A member's stored bytes, range-checked.
pub fn stored_bytes<'a>(data: &'a [u8], entry: &PackedEntry) -> Result<&'a [u8], FormatError> {
    let bad = || FormatError::Truncated(format!("{} lies outside the file", entry.path));
    let start = usize::try_from(entry.offset).map_err(|_| bad())?;
    let len = usize::try_from(entry.stored_size).map_err(|_| bad())?;
    let end = start.checked_add(len).ok_or_else(bad)?;
    data.get(start..end).ok_or_else(bad)
}

/// Read a member by its `compression`, stopping at `max_bytes`.
pub fn read_stored(data: &[u8], entry: &PackedEntry, max_bytes: u64) -> Result<Vec<u8>, FormatError> {
    let raw = stored_bytes(data, entry)?;
    let too_large = || FormatError::TooLarge(format!("{} unpacks past {max_bytes} bytes", entry.path));
    if entry.size.is_some_and(|s| s > max_bytes) {
        return Err(too_large());
    }
    let cap = usize::try_from(max_bytes).unwrap_or(usize::MAX);
    let inflate = |r: Result<Vec<u8>, miniz_oxide::inflate::DecompressError>| {
        r.map_err(|e| match e.status {
            miniz_oxide::inflate::TINFLStatus::HasMoreOutput => too_large(),
            _ => FormatError::Malformed(format!("the compressed data of {} is damaged", entry.path)),
        })
    };
    match entry.compression {
        Compression::None if raw.len() as u64 > max_bytes => Err(too_large()),
        Compression::None => Ok(raw.to_vec()),
        Compression::Deflate => inflate(miniz_oxide::inflate::decompress_to_vec_with_limit(raw, cap)),
        Compression::Zlib => inflate(miniz_oxide::inflate::decompress_to_vec_zlib_with_limit(raw, cap)),
        Compression::Gzip => {
            let body = gzip_body(raw).ok_or_else(|| FormatError::Malformed(format!("the gzip header of {} is damaged", entry.path)))?;
            inflate(miniz_oxide::inflate::decompress_to_vec_with_limit(body, cap))
        }
        Compression::Zstd => decompress::zstd(raw, max_bytes).map_err(|e| FormatError::Malformed(format!("{}: {e}", entry.path))),
        Compression::Unreadable => Err(FormatError::Unsupported(format!("{} is stored in a way we can't read back", entry.path))),
    }
}

/// The deflate stream after a gzip header.
fn gzip_body(raw: &[u8]) -> Option<&[u8]> {
    if raw.get(..3)? != [0x1f, 0x8b, 8] {
        return None;
    }
    let flags = *raw.get(3)?;
    let mut pos = 10usize;
    if flags & 4 != 0 {
        let extra = u16::from_le_bytes([*raw.get(pos)?, *raw.get(pos + 1)?]) as usize;
        pos = pos.checked_add(2)?.checked_add(extra)?;
    }
    for bit in [8u8, 16] {
        if flags & bit != 0 {
            pos = pos.checked_add(raw.get(pos..)?.iter().position(|b| *b == 0)?)?.checked_add(1)?;
        }
    }
    if flags & 2 != 0 {
        pos = pos.checked_add(2)?;
    }
    raw.get(pos..)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(offset: u64, stored_size: u64, compression: Compression) -> PackedEntry {
        PackedEntry { path: "a".into(), offset, stored_size, size: None, compression, kind: None }
    }

    #[test]
    fn stored_ranges_are_checked() {
        let data = b"hello world";
        assert_eq!(read_stored(data, &entry(6, 5, Compression::None), 100).unwrap(), b"world");
        assert!(read_stored(data, &entry(6, 6, Compression::None), 100).is_err());
        assert!(read_stored(data, &entry(u64::MAX, 2, Compression::None), 100).is_err());
        assert!(read_stored(data, &entry(1, u64::MAX, Compression::None), 100).is_err());
    }

    #[test]
    fn limits_hold_for_every_method() {
        let body = vec![7u8; 4096];
        let z = miniz_oxide::deflate::compress_to_vec_zlib(&body, 6);
        assert_eq!(read_stored(&z, &entry(0, z.len() as u64, Compression::Zlib), 4096).unwrap(), body);
        assert!(matches!(read_stored(&z, &entry(0, z.len() as u64, Compression::Zlib), 100), Err(FormatError::TooLarge(_))));
        let d = miniz_oxide::deflate::compress_to_vec(&body, 6);
        assert_eq!(read_stored(&d, &entry(0, d.len() as u64, Compression::Deflate), 4096).unwrap(), body);
        assert!(matches!(read_stored(&body, &entry(0, 4096, Compression::None), 100), Err(FormatError::TooLarge(_))));
        let mut declared = entry(0, 4096, Compression::None);
        declared.size = Some(u64::MAX);
        assert!(matches!(read_stored(&body, &declared, 8192), Err(FormatError::TooLarge(_))));
    }

    #[test]
    fn gzip_members_skip_every_optional_header_field() {
        let body = b"inside".to_vec();
        let mut g = vec![0x1f, 0x8b, 8, 4 | 8 | 16 | 2, 0, 0, 0, 0, 0, 0];
        g.extend([2, 0, 9, 9]);
        g.extend(b"name\0");
        g.extend(b"comment\0");
        g.extend([0, 0]);
        g.extend(miniz_oxide::deflate::compress_to_vec(&body, 6));
        assert_eq!(read_stored(&g, &entry(0, g.len() as u64, Compression::Gzip), 100).unwrap(), body);
        assert!(read_stored(b"\x1f\x8b\x08\x04", &entry(0, 4, Compression::Gzip), 100).is_err());
    }

    #[test]
    fn damaged_and_unreadable_members_are_errors_not_panics() {
        assert!(read_stored(b"not zlib", &entry(0, 8, Compression::Zlib), 100).is_err());
        assert!(read_stored(b"not zstd", &entry(0, 8, Compression::Zstd), 100).is_err());
        assert!(matches!(read_stored(b"x", &entry(0, 1, Compression::Unreadable), 100), Err(FormatError::Unsupported(_))));
    }
}
