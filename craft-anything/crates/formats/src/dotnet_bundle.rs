//! .NET single-file programs: an apphost with the assemblies and native files added to its end, and
//! a manifest listing them. The apphost carries a fixed 32-byte marker preceded by the manifest's
//! file offset, which stays zero in a host that wasn't bundled.

use crate::bytes::Reader;
use crate::common::{FormatError, find_bytes};
use crate::packed::{Compression, MAX_ENTRIES, PackedEntry, PackedFormat, PackedListing};
use serde_json::json;

const SIGNATURE: [u8; 32] = [
    0x8b, 0x12, 0x02, 0xb9, 0x6a, 0x61, 0x20, 0x38, 0x72, 0x7b, 0x93, 0x02, 0x14, 0xd7, 0xa0, 0x32, 0x13, 0xf5, 0xb9, 0xe6, 0xef, 0xae, 0x33, 0x18, 0xee, 0x3b,
    0x2d, 0xce, 0x24, 0xb3, 0x6a, 0xae,
];
/// Markers looked at before giving up (real files have one).
const MAX_MARKERS: usize = 16;
/// Longest member path or bundle id.
const MAX_STRING: usize = 64 * 1024;
/// The manifest versions that were released: .NET Core 3 (1), .NET 5 (2), .NET 6 and later (6).
const KNOWN_MAJORS: &[u32] = &[1, 2, 6];
/// The smallest a manifest entry can be, with a one-byte path length.
const MIN_ENTRY: usize = 8 + 8 + 1 + 1;
/// What the type byte means, by its value.
const FILE_TYPES: &[&str] = &["unknown", "assembly", "native_binary", "deps_json", "runtime_config_json", "symbols"];

/// The reader.
pub struct DotnetBundle;

/// The file offset of the manifest, from the first marker whose offset points inside the file.
fn header_offset(data: &[u8]) -> Option<usize> {
    let r = Reader::new(data);
    let mut from = 0usize;
    for _ in 0..MAX_MARKERS {
        let rest = data.get(from..)?;
        let at = from.checked_add(find_bytes(rest, &SIGNATURE, rest.len())?)?;
        let offset = at.checked_sub(8).and_then(|o| r.u64_le(o)).unwrap_or(0);
        if offset != 0
            && let Some(o) = usize::try_from(offset).ok().filter(|o| *o < data.len())
        {
            return Some(o);
        }
        from = at.checked_add(SIGNATURE.len())?;
    }
    None
}

struct Cursor<'a> {
    r: Reader<'a>,
    pos: usize,
}

impl Cursor<'_> {
    fn advance(&mut self, n: usize) -> Option<usize> {
        let at = self.pos;
        self.pos = at.checked_add(n)?;
        Some(at)
    }

    fn u8(&mut self) -> Option<u8> {
        let at = self.advance(1)?;
        self.r.u8(at)
    }

    fn u32(&mut self) -> Option<u32> {
        let at = self.advance(4)?;
        self.r.u32_le(at)
    }

    fn u64(&mut self) -> Option<u64> {
        let at = self.advance(8)?;
        self.r.u64_le(at)
    }

    /// A size or offset, stored as a signed 64-bit number that can't be negative.
    fn size(&mut self) -> Option<u64> {
        self.u64().filter(|v| i64::try_from(*v).is_ok())
    }

    /// A string with a 7-bit-encoded length in front.
    fn string(&mut self) -> Option<String> {
        let mut len = 0usize;
        for i in 0..5u32 {
            let b = self.u8()?;
            len |= usize::from(b & 0x7f).checked_shl(i * 7)?;
            if b & 0x80 == 0 {
                if len > MAX_STRING {
                    return None;
                }
                let at = self.advance(len)?;
                return Some(String::from_utf8_lossy(self.r.slice(at, len)?).into_owned());
            }
        }
        None
    }
}

fn read_entry(c: &mut Cursor<'_>, major: u32) -> Option<PackedEntry> {
    let offset = c.size()?;
    let size = c.size()?;
    let compressed = if major >= 6 { c.size()? } else { 0 };
    let kind = c.u8()?;
    let path = c.string()?;
    let kind = FILE_TYPES.get(usize::from(kind)).map_or_else(|| format!("type_{kind}"), |s| (*s).to_string());
    let (stored_size, compression) = if compressed > 0 { (compressed, Compression::Deflate) } else { (size, Compression::None) };
    Some(PackedEntry { path, offset, stored_size, size: Some(size), compression, kind: Some(kind) })
}

impl PackedFormat for DotnetBundle {
    fn id(&self) -> &'static str {
        "dotnet_bundle"
    }

    fn title(&self) -> &'static str {
        ".NET single-file bundle"
    }

    fn detect(&self, data: &[u8]) -> bool {
        header_offset(data).is_some()
    }

    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError> {
        let at = header_offset(data).ok_or_else(|| FormatError::Malformed("no .NET bundle marker with a manifest offset; this host isn't bundled".into()))?;
        let short = || FormatError::Truncated("the .NET bundle manifest".into());
        let mut c = Cursor { r: Reader::new(data), pos: at };
        let major = c.u32().ok_or_else(short)?;
        let minor = c.u32().ok_or_else(short)?;
        if !KNOWN_MAJORS.contains(&major) {
            return Err(FormatError::Unsupported(format!("a .NET bundle manifest of version {major}.{minor}, which isn't one we know (1, 2 and 6)")));
        }
        let declared = c.u32().and_then(|n| i32::try_from(n).ok()).ok_or_else(|| FormatError::Malformed("a negative file count in the manifest".into()))?;
        let declared = usize::try_from(declared).map_err(|_| FormatError::Malformed("a negative file count in the manifest".into()))?;
        let bundle_id = c.string().ok_or_else(short)?;
        let mut members = json!(null);
        let mut flags = None;
        if major >= 2 {
            let (deps_at, deps_size, config_at, config_size) = (c.size(), c.size(), c.size(), c.size());
            members = json!({
                "deps_json": {"offset": deps_at.ok_or_else(short)?, "size": deps_size.ok_or_else(short)?},
                "runtime_config_json": {"offset": config_at.ok_or_else(short)?, "size": config_size.ok_or_else(short)?},
            });
            flags = Some(c.u64().ok_or_else(short)?);
        }
        let left = data.len().saturating_sub(c.pos);
        if declared > left / MIN_ENTRY {
            return Err(FormatError::Malformed(format!("the manifest claims {declared} files, more than the {left} bytes after it can hold")));
        }
        let mut entries = Vec::new();
        let mut notes = Vec::new();
        let mut damaged = false;
        for i in 0..declared.min(MAX_ENTRIES) {
            match read_entry(&mut c, major) {
                Some(e) => entries.push(e),
                None => {
                    notes.push(format!("The manifest is damaged at file {i} of {declared}, so the files after it aren't listed."));
                    damaged = true;
                    break;
                }
            }
        }
        let outside = entries.iter().filter(|e| e.offset.checked_add(e.stored_size).is_none_or(|end| end > data.len() as u64)).count();
        if outside > 0 {
            notes.push(format!("{outside} listed file(s) lie past the end of this file, so they can't be read."));
        }
        if minor != 0 {
            notes.push(format!("This manifest is version {major}.{minor}; we read it as {major}.0."));
        }
        let compressed = entries.iter().filter(|e| e.compression == Compression::Deflate).count();
        let facts = json!({
            "manifest_offset": at,
            "manifest_version": format!("{major}.{minor}"),
            "generation": match major { 1 => ".NET Core 3", 2 => ".NET 5", _ => ".NET 6 or later" },
            "bundle_id": bundle_id,
            "files": declared,
            "compressed_files": compressed,
            "flags": flags,
            "well_known_files": members,
        });
        Ok(PackedListing { facts, truncated: damaged || declared > entries.len(), entries, notes })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packed;
    use craft_anything_testkit::packed::{DOTNET_SIGNATURE, dotnet_bundle, dotnet_sample};

    #[test]
    fn the_signature_is_the_same_on_both_sides() {
        assert_eq!(SIGNATURE, DOTNET_SIGNATURE);
    }

    #[test]
    fn a_v6_bundle_lists_and_reads() {
        let data = dotnet_sample();
        assert!(DotnetBundle.detect(&data));
        let l = DotnetBundle.list(&data).unwrap();
        assert_eq!(l.entries.len(), 3);
        assert_eq!(l.facts["manifest_version"], "6.0");
        assert_eq!(l.facts["bundle_id"], "bundle-id-1");
        assert_eq!(l.facts["compressed_files"], 1);
        assert_eq!(l.facts["flags"], 1);
        let dll = &l.entries[0];
        assert_eq!((dll.path.as_str(), dll.kind.as_deref(), dll.compression, dll.size), ("App.dll", Some("assembly"), Compression::Deflate, Some(200)));
        assert!(dll.stored_size < 200);
        assert_eq!(DotnetBundle.read(&data, dll, 1000).unwrap(), [0x5a; 200]);
        assert_eq!(l.entries[1].kind.as_deref(), Some("deps_json"));
        assert_eq!(DotnetBundle.read(&data, &l.entries[2], 100).unwrap(), b"native");
        assert!(!l.truncated && l.notes.is_empty());
    }

    #[test]
    fn older_manifests_read() {
        for major in [1u32, 2] {
            let data = dotnet_bundle(major, &[("App.dll", 1, &[7u8; 100])]);
            let l = DotnetBundle.list(&data).unwrap();
            assert_eq!(l.facts["manifest_version"], format!("{major}.0"));
            assert_eq!(l.entries[0].compression, Compression::None);
            assert_eq!(DotnetBundle.read(&data, &l.entries[0], 1000).unwrap(), [7u8; 100]);
        }
        assert_eq!(DotnetBundle.list(&dotnet_bundle(1, &[])).unwrap().facts["flags"], serde_json::Value::Null);
    }

    #[test]
    fn unknown_versions_are_refused() {
        for major in [0u32, 3, 7, u32::MAX] {
            let mut data = dotnet_sample();
            let at = header_offset(&data).unwrap();
            data[at..at + 4].copy_from_slice(&major.to_le_bytes());
            assert!(matches!(DotnetBundle.list(&data), Err(FormatError::Unsupported(_))), "{major}");
        }
    }

    #[test]
    fn a_host_that_was_not_bundled_is_not_detected() {
        let mut host = b"MZ apphost ".to_vec();
        host.extend(0u64.to_le_bytes());
        host.extend(SIGNATURE);
        host.extend([0u8; 64]);
        assert!(!DotnetBundle.detect(&host));
        assert!(DotnetBundle.list(&host).is_err());
        assert!(!DotnetBundle.detect(b"plain file"));
        // A marker at the very start has no offset in front of it.
        assert!(!DotnetBundle.detect(&SIGNATURE));
    }

    #[test]
    fn a_marker_with_a_stray_offset_is_skipped_for_the_real_one() {
        let good = dotnet_sample();
        let mut data = u64::MAX.to_le_bytes().to_vec();
        data.extend(SIGNATURE);
        let shift = data.len() as u64;
        let at = header_offset(&good).unwrap();
        let mut shifted = good.clone();
        let sig_at = find_bytes(&good, &SIGNATURE, good.len()).unwrap();
        shifted[sig_at - 8..sig_at].copy_from_slice(&(at as u64 + shift).to_le_bytes());
        data.extend(shifted);
        assert_eq!(header_offset(&data), Some(at + shift as usize));
    }

    #[test]
    fn a_damaged_manifest_lists_what_came_before() {
        let data = dotnet_sample();
        let at = header_offset(&data).unwrap();
        let first_entry = at + 12 + 12 + 5 * 8;
        // The second entry's offset becomes negative.
        let second = first_entry + 8 + 8 + 8 + 1 + 1 + "App.dll".len();
        let mut d = data.clone();
        d[second..second + 8].copy_from_slice(&u64::MAX.to_le_bytes());
        let l = DotnetBundle.list(&d).unwrap();
        assert_eq!(l.entries.len(), 1);
        assert!(l.truncated);
        assert!(l.notes[0].contains("damaged"));
    }

    #[test]
    fn a_member_past_the_end_is_named_and_refuses_to_read() {
        let data = dotnet_sample();
        let at = header_offset(&data).unwrap();
        let first_entry = at + 12 + 12 + 5 * 8;
        let mut d = data.clone();
        d[first_entry..first_entry + 8].copy_from_slice(&(i64::MAX as u64).to_le_bytes());
        let l = DotnetBundle.list(&d).unwrap();
        assert!(l.notes.iter().any(|n| n.contains("past the end")));
        assert!(DotnetBundle.read(&d, &l.entries[0], 1000).is_err());
    }

    #[test]
    fn a_huge_file_count_is_refused_before_any_allocation() {
        let data = dotnet_sample();
        let at = header_offset(&data).unwrap();
        for n in [i32::MAX as u32, u32::MAX, 0x8000_0000] {
            let mut d = data.clone();
            d[at + 8..at + 12].copy_from_slice(&n.to_le_bytes());
            assert!(matches!(DotnetBundle.list(&d), Err(FormatError::Malformed(_))), "{n}");
        }
    }

    #[test]
    fn truncation_at_every_length_never_panics() {
        let full = dotnet_sample();
        for len in 0..full.len() {
            let d = &full[..len];
            let _ = DotnetBundle.detect(d);
            if let Ok(l) = DotnetBundle.list(d) {
                for e in &l.entries {
                    let _ = DotnetBundle.read(d, e, 1000);
                }
            }
        }
    }

    #[test]
    fn corrupt_fields_never_panic() {
        let full = dotnet_sample();
        let at = header_offset(&full).unwrap();
        for pos in at..full.len() {
            for v in [0xffu8, 0x80, 0] {
                let mut d = full.clone();
                d[pos] = v;
                if let Ok(l) = DotnetBundle.list(&d) {
                    for e in &l.entries {
                        let _ = DotnetBundle.read(&d, e, 1000);
                    }
                }
            }
        }
    }

    #[test]
    fn long_strings_and_bad_length_prefixes_are_handled() {
        let long = "p".repeat(300);
        let data = dotnet_bundle(6, &[(&long, 1, b"x")]);
        assert_eq!(DotnetBundle.list(&data).unwrap().entries[0].path, long);
        let mut c = Cursor { r: Reader::new(&[0xff; 16]), pos: 0 };
        assert!(c.string().is_none(), "a length prefix longer than five bytes");
    }

    #[test]
    fn reads_stop_at_their_limit() {
        let data = dotnet_sample();
        let l = DotnetBundle.list(&data).unwrap();
        assert!(matches!(DotnetBundle.read(&data, &l.entries[0], 10), Err(FormatError::TooLarge(_))));
    }

    #[test]
    fn it_is_the_reader_for_these_files() {
        assert_eq!(packed::detect(&dotnet_sample()).map(|r| r.id()), Some("dotnet_bundle"));
    }
}
