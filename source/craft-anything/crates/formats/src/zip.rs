//! ZIP archives (also APK, JAR, IPA, MSIX, HAP…): central directory listing and bounded entry reads.
//!
//! Only the central directory is trusted for the listing. Entry data is located through the local
//! header, decompressed with a hard output cap, and checked against the recorded CRC-32. Stored and
//! deflated entries are supported; anything else (and encrypted entries) is reported, not read.

use crate::bytes::Reader;

/// Biggest tail we search for the end-of-central-directory record (64 KiB comment + record).
const EOCD_SEARCH: usize = 22 + 0xffff;

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ZipError {
    #[error("not a ZIP archive (no end-of-central-directory record)")]
    NotZip,
    #[error("ZIP is truncated: {0}")]
    Truncated(&'static str),
    #[error("ZIP is corrupt: {0}")]
    Corrupt(String),
    #[error("unsupported ZIP feature: {0}")]
    Unsupported(String),
    #[error("entry is larger than the {0}-byte limit")]
    TooLarge(u64),
    #[error("CRC-32 mismatch (expected {expected:08x}, found {found:08x})")]
    CrcMismatch { expected: u32, found: u32 },
}

/// One central-directory entry.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct ZipEntry {
    /// Entry name as stored (forward slashes). Decoded lossily when not valid UTF-8.
    pub name: String,
    pub method: u16,
    pub flags: u16,
    pub crc32: u32,
    pub compressed_size: u64,
    pub uncompressed_size: u64,
    /// Offset of the local header, already adjusted for any prepended data.
    pub local_header_offset: u64,
    pub is_dir: bool,
    pub encrypted: bool,
}

impl ZipEntry {
    /// Human name of the compression method.
    pub fn method_name(&self) -> &'static str {
        match self.method {
            0 => "stored",
            8 => "deflate",
            9 => "deflate64",
            12 => "bzip2",
            14 => "lzma",
            93 => "zstd",
            95 => "xz",
            99 => "aes",
            _ => "other",
        }
    }
}

/// The parsed central directory.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize)]
pub struct ZipArchive {
    pub entries: Vec<ZipEntry>,
    /// Entries the directory declares (may exceed `entries.len()` when truncated).
    pub declared_entries: u64,
    /// True when `max_entries` stopped the listing early.
    pub truncated: bool,
    pub zip64: bool,
    /// Bytes before the archive proper (self-extracting stubs).
    pub prefix_bytes: u64,
}

/// True when the bytes start like a ZIP (local header or empty archive).
pub fn looks_like_zip(data: &[u8]) -> bool {
    data.starts_with(b"PK\x03\x04") || data.starts_with(b"PK\x05\x06") || data.starts_with(b"PK\x07\x08")
}

/// Parse the central directory, keeping at most `max_entries`.
pub fn parse(data: &[u8], max_entries: usize) -> Result<ZipArchive, ZipError> {
    let r = Reader::new(data);
    let eocd = find_eocd(data).ok_or(ZipError::NotZip)?;
    let mut total = u64::from(r.u16_le(eocd + 10).ok_or(ZipError::Truncated("end record"))?);
    let mut cd_size = u64::from(r.u32_le(eocd + 12).ok_or(ZipError::Truncated("end record"))?);
    let mut cd_offset = u64::from(r.u32_le(eocd + 16).ok_or(ZipError::Truncated("end record"))?);
    let mut zip64 = false;
    let mut eocd_record_start = eocd as u64;
    if total == 0xffff || cd_size == 0xffff_ffff || cd_offset == 0xffff_ffff {
        // ZIP64 locator sits right before the classic record.
        if let Some(loc) = eocd.checked_sub(20)
            && r.slice(loc, 4) == Some(b"PK\x06\x07")
        {
            let rec = r.u64_le(loc + 8).ok_or(ZipError::Truncated("zip64 locator"))?;
            let rec = usize::try_from(rec).map_err(|_| ZipError::Corrupt("zip64 record offset".into()))?;
            if r.slice(rec, 4) == Some(b"PK\x06\x06") {
                total = r.u64_le(rec + 32).ok_or(ZipError::Truncated("zip64 record"))?;
                cd_size = r.u64_le(rec + 40).ok_or(ZipError::Truncated("zip64 record"))?;
                cd_offset = r.u64_le(rec + 48).ok_or(ZipError::Truncated("zip64 record"))?;
                zip64 = true;
                eocd_record_start = rec as u64;
            }
        }
    }
    // Self-extracting archives: the directory sits later than it claims by the stub length.
    let expected_end = cd_offset.checked_add(cd_size).ok_or_else(|| ZipError::Corrupt("directory bounds overflow".into()))?;
    let prefix = eocd_record_start.saturating_sub(expected_end);
    let start = usize::try_from(cd_offset.saturating_add(prefix)).map_err(|_| ZipError::Corrupt("directory offset".into()))?;
    let mut entries = Vec::new();
    let mut pos = start;
    let mut truncated = false;
    let mut seen = 0u64;
    while seen < total {
        if entries.len() >= max_entries {
            truncated = true;
            break;
        }
        if r.slice(pos, 4) != Some(b"PK\x01\x02") {
            if entries.is_empty() {
                return Err(ZipError::Corrupt(format!("no central directory header at offset {pos}")));
            }
            truncated = true;
            break;
        }
        let flags = r.u16_le(pos + 8).ok_or(ZipError::Truncated("directory entry"))?;
        let method = r.u16_le(pos + 10).ok_or(ZipError::Truncated("directory entry"))?;
        let crc32 = r.u32_le(pos + 16).ok_or(ZipError::Truncated("directory entry"))?;
        let mut csize = u64::from(r.u32_le(pos + 20).ok_or(ZipError::Truncated("directory entry"))?);
        let mut usize_ = u64::from(r.u32_le(pos + 24).ok_or(ZipError::Truncated("directory entry"))?);
        let name_len = usize::from(r.u16_le(pos + 28).ok_or(ZipError::Truncated("directory entry"))?);
        let extra_len = usize::from(r.u16_le(pos + 30).ok_or(ZipError::Truncated("directory entry"))?);
        let comment_len = usize::from(r.u16_le(pos + 32).ok_or(ZipError::Truncated("directory entry"))?);
        let mut local = u64::from(r.u32_le(pos + 42).ok_or(ZipError::Truncated("directory entry"))?);
        let name_bytes = r.slice(pos + 46, name_len).ok_or(ZipError::Truncated("entry name"))?;
        let extra = r.slice(pos + 46 + name_len, extra_len).unwrap_or(&[]);
        // ZIP64 extended information extra field.
        let mut x = 0usize;
        let er = Reader::new(extra);
        while let (Some(id), Some(len)) = (er.u16_le(x), er.u16_le(x + 2)) {
            let body = x + 4;
            if id == 0x0001 {
                let mut f = body;
                if usize_ == 0xffff_ffff
                    && let Some(v) = er.u64_le(f)
                {
                    usize_ = v;
                    f += 8;
                }
                if csize == 0xffff_ffff
                    && let Some(v) = er.u64_le(f)
                {
                    csize = v;
                    f += 8;
                }
                if local == 0xffff_ffff
                    && let Some(v) = er.u64_le(f)
                {
                    local = v;
                }
                break;
            }
            x = body + usize::from(len);
        }
        let name = String::from_utf8_lossy(name_bytes).replace('\\', "/");
        entries.push(ZipEntry {
            is_dir: name.ends_with('/'),
            name,
            method,
            flags,
            crc32,
            compressed_size: csize,
            uncompressed_size: usize_,
            local_header_offset: local.saturating_add(prefix),
            encrypted: flags & 1 != 0,
        });
        seen += 1;
        pos = pos.checked_add(46 + name_len + extra_len + comment_len).ok_or_else(|| ZipError::Corrupt("directory overflow".into()))?;
    }
    Ok(ZipArchive { entries, declared_entries: total, truncated, zip64, prefix_bytes: prefix })
}

fn find_eocd(data: &[u8]) -> Option<usize> {
    if data.len() < 22 {
        return None;
    }
    let from = data.len().saturating_sub(EOCD_SEARCH);
    let tail = data.get(from..)?;
    // Search backwards so a stray signature in the comment can't shadow the real record.
    let mut i = tail.len().checked_sub(22)?;
    loop {
        if tail.get(i..i + 4) == Some(b"PK\x05\x06") {
            return Some(from + i);
        }
        if i == 0 {
            return None;
        }
        i -= 1;
    }
}

/// The raw (possibly compressed) bytes of an entry.
pub fn raw_entry_data<'a>(data: &'a [u8], e: &ZipEntry) -> Result<&'a [u8], ZipError> {
    let r = Reader::new(data);
    let off = usize::try_from(e.local_header_offset).map_err(|_| ZipError::Corrupt("local header offset".into()))?;
    if r.slice(off, 4) != Some(b"PK\x03\x04") {
        return Err(ZipError::Corrupt(format!("no local header for {}", e.name)));
    }
    let n = usize::from(r.u16_le(off + 26).ok_or(ZipError::Truncated("local header"))?);
    let x = usize::from(r.u16_le(off + 28).ok_or(ZipError::Truncated("local header"))?);
    let start = off.checked_add(30 + n + x).ok_or(ZipError::Truncated("local header"))?;
    let len = usize::try_from(e.compressed_size).map_err(|_| ZipError::TooLarge(e.compressed_size))?;
    r.slice(start, len).ok_or(ZipError::Truncated("entry data"))
}

/// Read and decompress one entry, refusing to produce more than `max_bytes`.
pub fn read_entry(data: &[u8], e: &ZipEntry, max_bytes: u64) -> Result<Vec<u8>, ZipError> {
    if e.encrypted {
        return Err(ZipError::Unsupported(format!("{} is encrypted", e.name)));
    }
    if e.uncompressed_size > max_bytes {
        return Err(ZipError::TooLarge(max_bytes));
    }
    let raw = raw_entry_data(data, e)?;
    let cap = usize::try_from(max_bytes).unwrap_or(usize::MAX);
    let out = match e.method {
        0 => raw.to_vec(),
        8 => miniz_oxide::inflate::decompress_to_vec_with_limit(raw, cap).map_err(|err| match err.status {
            miniz_oxide::inflate::TINFLStatus::HasMoreOutput => ZipError::TooLarge(max_bytes),
            _ => ZipError::Corrupt(format!("deflate stream for {} is damaged", e.name)),
        })?,
        93 => crate::decompress::zstd(raw, max_bytes).map_err(|err| ZipError::Corrupt(format!("zstd stream for {} is damaged: {err}", e.name)))?,
        m => return Err(ZipError::Unsupported(format!("compression method {m} ({}) for {}", e.method_name(), e.name))),
    };
    let found = crc32(&out);
    if found != e.crc32 {
        return Err(ZipError::CrcMismatch { expected: e.crc32, found });
    }
    Ok(out)
}

/// CRC-32 (IEEE, as used by ZIP and PNG).
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in data {
        crc ^= u32::from(b);
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Minimal stored-only ZIP writer for tests.
    pub(crate) fn build(files: &[(&str, &[u8])]) -> Vec<u8> {
        let mut out = Vec::new();
        let mut cd = Vec::new();
        for (name, body) in files {
            let off = out.len() as u32;
            let crc = crc32(body);
            out.extend_from_slice(b"PK\x03\x04");
            out.extend_from_slice(&[20, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
            out.extend_from_slice(&crc.to_le_bytes());
            out.extend_from_slice(&(body.len() as u32).to_le_bytes());
            out.extend_from_slice(&(body.len() as u32).to_le_bytes());
            out.extend_from_slice(&(name.len() as u16).to_le_bytes());
            out.extend_from_slice(&0u16.to_le_bytes());
            out.extend_from_slice(name.as_bytes());
            out.extend_from_slice(body);
            cd.extend_from_slice(b"PK\x01\x02");
            cd.extend_from_slice(&[20, 0, 20, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
            cd.extend_from_slice(&crc.to_le_bytes());
            cd.extend_from_slice(&(body.len() as u32).to_le_bytes());
            cd.extend_from_slice(&(body.len() as u32).to_le_bytes());
            cd.extend_from_slice(&(name.len() as u16).to_le_bytes());
            cd.extend_from_slice(&[0; 12]);
            cd.extend_from_slice(&off.to_le_bytes());
            cd.extend_from_slice(name.as_bytes());
        }
        let cd_off = out.len() as u32;
        out.extend_from_slice(&cd);
        out.extend_from_slice(b"PK\x05\x06\0\0\0\0");
        out.extend_from_slice(&(files.len() as u16).to_le_bytes());
        out.extend_from_slice(&(files.len() as u16).to_le_bytes());
        out.extend_from_slice(&(cd.len() as u32).to_le_bytes());
        out.extend_from_slice(&cd_off.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out
    }

    #[test]
    fn lists_and_reads_stored_entries() {
        let z = build(&[("a.txt", b"hello"), ("dir/b.js", b"console.log(1)")]);
        let a = parse(&z, 100).unwrap();
        assert_eq!(a.entries.len(), 2);
        assert_eq!(a.entries[1].name, "dir/b.js");
        assert_eq!(read_entry(&z, &a.entries[0], 100).unwrap(), b"hello");
        assert!(matches!(read_entry(&z, &a.entries[1], 3), Err(ZipError::TooLarge(3))));
    }

    #[test]
    fn zstandard_members_are_read_with_their_limits_and_checks() {
        // A raw Zstandard frame holding "hello zip" (single segment, one raw block).
        let body = b"hello zip";
        let mut frame = vec![0x28, 0xb5, 0x2f, 0xfd, 0x20, body.len() as u8];
        let block_header = ((body.len() as u32) << 3) | 1;
        frame.extend(&block_header.to_le_bytes()[..3]);
        frame.extend(body);
        let mut file = vec![0u8; 30];
        file[..4].copy_from_slice(b"PK\x03\x04");
        file.extend(&frame);
        let mut e = ZipEntry {
            name: "x".into(),
            method: 93,
            flags: 0,
            crc32: crc32(body),
            compressed_size: frame.len() as u64,
            uncompressed_size: body.len() as u64,
            local_header_offset: 0,
            is_dir: false,
            encrypted: false,
        };
        assert_eq!(read_entry(&file, &e, 100).unwrap(), body);
        assert!(matches!(read_entry(&file, &e, 3), Err(ZipError::TooLarge(3))));
        e.crc32 ^= 1;
        assert!(matches!(read_entry(&file, &e, 100), Err(ZipError::CrcMismatch { .. })));
    }

    #[test]
    fn deflate_round_trip_and_crc_check() {
        let body = b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa".repeat(20);
        let comp = miniz_oxide::deflate::compress_to_vec(&body, 6);
        let e = ZipEntry {
            name: "x".into(),
            method: 8,
            flags: 0,
            crc32: crc32(&body),
            compressed_size: comp.len() as u64,
            uncompressed_size: body.len() as u64,
            local_header_offset: 0,
            is_dir: false,
            encrypted: false,
        };
        let mut z = b"PK\x03\x04".to_vec();
        z.extend_from_slice(&[0; 26]);
        z.extend_from_slice(&comp);
        assert_eq!(read_entry(&z, &e, 1 << 20).unwrap(), body);
        // A lying uncompressed size can't make us exceed the cap.
        let liar = ZipEntry { uncompressed_size: 10, ..e.clone() };
        assert!(matches!(read_entry(&z, &liar, 10), Err(ZipError::TooLarge(10))));
        let bad = ZipEntry { crc32: 1, ..e };
        assert!(matches!(read_entry(&z, &bad, 1 << 20), Err(ZipError::CrcMismatch { .. })));
    }

    #[test]
    fn hostile_inputs_do_not_panic() {
        let z = build(&[("a", b"1"), ("b", b"22")]);
        for cut in 0..z.len() {
            if let Ok(a) = parse(&z[..cut], 10) {
                for e in &a.entries {
                    let _ = read_entry(&z[..cut], e, 100);
                }
            }
        }
        for i in 0..z.len() {
            let mut m = z.clone();
            m[i] ^= 0xff;
            if let Ok(a) = parse(&m, 10) {
                for e in &a.entries {
                    let _ = read_entry(&m, e, 100);
                }
            }
        }
        assert_eq!(parse(b"", 1), Err(ZipError::NotZip));
    }

    #[test]
    fn crc_known_value() {
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    }
}
