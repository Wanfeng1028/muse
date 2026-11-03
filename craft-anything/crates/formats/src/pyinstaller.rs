//! PyInstaller programs: a bootloader with an archive (the CArchive) at its end, found from a cookie
//! at the archive's end. One member is usually a PYZ, a second archive holding the program's Python
//! modules, whose table is marshalled; its modules are listed too, under `<pyz>.modules/`.
//!
//! Modules in a PYZ are stored as bare marshalled code, so taking one out puts the `.pyc` header in
//! front of it, which is what other tools expect.

use crate::bytes::Reader;
use crate::common::FormatError;
use crate::packed::{Compression, MAX_ENTRIES, PackedEntry, PackedFormat, PackedListing, read_stored};
use crate::pyc::{self, Value};
use serde_json::{Value as Json, json};

const MAGIC: [u8; 8] = *b"MEI\x0c\x0b\x0a\x0b\x0e";
const COOKIE_OLD: usize = 24;
const COOKIE_NEW: usize = 88;
/// Cookies looked at from the end of the file. The bootloader holds a copy of the magic too.
const MAX_CANDIDATES: usize = 64;
/// The fixed part of a table entry, in front of its name.
const ENTRY_HEAD: usize = 18;
/// Longest table entry.
const MAX_ENTRY: usize = 64 * 1024;
/// PYZ members whose stored bytes are checked for a zlib header to spot encryption.
const SAMPLE: usize = 8;
/// Longest module name, and most name text one PYZ keeps: its table can share one long string.
const MAX_NAME: usize = 4096;
const MAX_NAME_TEXT: usize = 64 << 20;
/// In front of a PYZ module's magic number in its kind.
const PYZ_KIND: &str = "pyz_module magic=";
/// What each type code in the table means.
const TYPE_CODES: &[(u8, &str)] = &[
    (b'b', "binary"),
    (b'z', "pyz_archive"),
    (b'Z', "zip_archive"),
    (b'm', "module"),
    (b'M', "package"),
    (b's', "script"),
    (b'x', "data"),
    (b'o', "runtime_option"),
    (b'd', "dependency"),
    (b'l', "splash"),
    (b'n', "symlink"),
];

/// The reader.
pub struct PyInstaller;

#[derive(Debug, Clone, PartialEq, Eq)]
struct Cookie {
    /// Where the archive starts in the file.
    start: usize,
    toc_at: usize,
    toc_len: usize,
    python: i32,
    /// The Python library it runs on (new cookies only).
    library: Option<String>,
    size: usize,
}

fn cookie_at(data: &[u8], at: usize, size: usize) -> Option<Cookie> {
    let r = Reader::new(data);
    let end = at.checked_add(size).filter(|e| *e <= data.len())?;
    let archive = usize::try_from(r.u32_be(at.checked_add(8)?)?).ok()?;
    let toc_at = usize::try_from(r.u32_be(at.checked_add(12)?)?).ok()?;
    let toc_len = usize::try_from(r.u32_be(at.checked_add(16)?)?).ok()?;
    let python = i32::from_be_bytes(r.u32_be(at.checked_add(20)?)?.to_be_bytes());
    let start = end.checked_sub(archive)?;
    if toc_at.checked_add(toc_len)?.checked_add(size)? > archive || !(10..=4000).contains(&python) {
        return None;
    }
    let library = if size == COOKIE_NEW {
        let raw = data.get(at.checked_add(24)?..end)?;
        let n = raw.iter().position(|b| *b == 0)?;
        let (name, rest) = raw.split_at(n);
        if name.is_empty() || !name.iter().all(|b| b.is_ascii_graphic()) || rest.iter().any(|b| *b != 0) {
            return None;
        }
        Some(String::from_utf8_lossy(name).into_owned())
    } else {
        None
    };
    Some(Cookie { start, toc_at, toc_len, python, library, size })
}

/// The last sound cookie in the file, the newer form preferred where both fit.
fn find_cookie(data: &[u8]) -> Option<Cookie> {
    let mut end = data.len();
    for _ in 0..MAX_CANDIDATES {
        let at = rfind(data.get(..end)?)?;
        if let Some(c) = cookie_at(data, at, COOKIE_NEW).or_else(|| cookie_at(data, at, COOKIE_OLD)) {
            return Some(c);
        }
        end = at;
    }
    None
}

fn rfind(hay: &[u8]) -> Option<usize> {
    let mut end = hay.len();
    while let Some(p) = hay.get(..end)?.iter().rposition(|b| *b == MAGIC[0]) {
        if hay.get(p..p.checked_add(MAGIC.len())?) == Some(&MAGIC[..]) {
            return Some(p);
        }
        end = p;
    }
    None
}

/// "3.12" from the number in the cookie, which is 312 now and was 27 in old files.
fn python_label(v: i32) -> String {
    if v >= 100 { format!("{}.{}", v / 100, v % 100) } else { format!("{}.{}", v / 10, v % 10) }
}

struct Member {
    entry: PackedEntry,
    type_code: u8,
}

/// Read the table of contents. `Err` names what stopped it, with the members before that kept.
fn read_table(data: &[u8], c: &Cookie) -> (Vec<Member>, Option<String>) {
    let r = Reader::new(data);
    let mut out = Vec::new();
    let Some(table) = c.start.checked_add(c.toc_at) else { return (out, Some("the table lies outside the file".into())) };
    let mut pos = 0usize;
    while pos < c.toc_len {
        if out.len() >= MAX_ENTRIES {
            return (out, Some(format!("the listing stopped at {MAX_ENTRIES} members")));
        }
        let Some(at) = table.checked_add(pos) else { break };
        let read = (|| {
            let len = usize::try_from(r.u32_be(at)?).ok()?;
            if !(ENTRY_HEAD..=MAX_ENTRY).contains(&len) || pos.checked_add(len)? > c.toc_len {
                return None;
            }
            let offset = u64::from(r.u32_be(at + 4)?);
            let stored_size = u64::from(r.u32_be(at + 8)?);
            let size = u64::from(r.u32_be(at + 12)?);
            let flag = r.u8(at + 16)?;
            let type_code = r.u8(at + 17)?;
            let name = r.slice(at + ENTRY_HEAD, len - ENTRY_HEAD)?;
            let end = name.iter().position(|b| *b == 0).unwrap_or(name.len());
            let path = String::from_utf8_lossy(name.get(..end)?).into_owned();
            let compression = match flag {
                0 => Compression::None,
                1 => Compression::Zlib,
                _ => Compression::Unreadable,
            };
            let kind = TYPE_CODES
                .iter()
                .find(|(t, _)| *t == type_code)
                .map_or_else(|| format!("type_{}", char::from(type_code).escape_default()), |(_, k)| (*k).to_string());
            let offset = (c.start as u64).checked_add(offset)?;
            Some((Member { entry: PackedEntry { path, offset, stored_size, size: Some(size), compression, kind: Some(kind) }, type_code }, len))
        })();
        match read {
            Some((m, len)) => {
                out.push(m);
                pos += len;
            }
            None => return (out, Some(format!("the table is damaged at byte {pos} of {}", c.toc_len))),
        }
    }
    (out, None)
}

/// One module in a PYZ.
struct PyzModule {
    name: String,
    kind: i64,
    at: u64,
    len: u64,
}

fn pyz_item(name: &Value, info: &Value) -> Option<PyzModule> {
    let Value::Str(name) = name else { return None };
    if name.len() > MAX_NAME {
        return None;
    }
    let Value::Seq(fields) = info else { return None };
    let number = |i: usize| match fields.get(i).map(|f| &f.value) {
        Some(Value::Int(v)) => Some(*v),
        _ => None,
    };
    Some(PyzModule { name: name.clone(), kind: number(0)?, at: u64::try_from(number(1)?).ok()?, len: u64::try_from(number(2)?).ok()? })
}

/// The modules in a PYZ's table: a list of pairs now, a dict in older versions. At most `room`
/// are kept, and the second value says how many the table holds.
fn pyz_table(table: &Value, room: usize) -> Option<(Vec<PyzModule>, usize)> {
    let pairs: Vec<(&Value, &Value)> = match table {
        Value::Seq(items) => items
            .iter()
            .map(|item| match &item.value {
                Value::Seq(pair) => Some((&pair.first()?.value, &pair.get(1)?.value)),
                _ => None,
            })
            .collect::<Option<_>>()?,
        Value::Dict(pairs) => pairs.iter().map(|(k, v)| (&k.value, &v.value)).collect(),
        _ => return None,
    };
    let mut modules = Vec::new();
    let mut name_text = 0usize;
    for (name, info) in pairs.iter().take(room) {
        let m = pyz_item(name, info)?;
        name_text = name_text.saturating_add(m.name.len());
        if name_text > MAX_NAME_TEXT {
            return None;
        }
        modules.push(m);
    }
    Some((modules, pairs.len()))
}

/// What a PYZ gave the listing.
struct PyzRead {
    magic: u16,
    entries: Vec<PackedEntry>,
    /// How many modules its table holds, which may be more than `entries`.
    total: usize,
    encrypted: bool,
}

fn looks_zlib(b: &[u8]) -> bool {
    matches!(b, [a, c, ..] if a & 0x0f == 8 && (u16::from(*a) * 256 + u16::from(*c)).is_multiple_of(31))
}

/// The dotted module name as a path: packages hold an `__init__`.
fn module_path(pyz: &str, name: &str, is_package: bool) -> String {
    let inner = name.replace('.', "/");
    if is_package { format!("{pyz}.modules/{inner}/__init__.pyc") } else { format!("{pyz}.modules/{inner}.pyc") }
}

fn read_pyz(data: &[u8], member: &PackedEntry, room: usize, key_seen: bool) -> Result<PyzRead, String> {
    if member.compression != Compression::None {
        return Err("it is itself compressed, which we don't unpack to list".into());
    }
    let base = usize::try_from(member.offset).map_err(|_| "it lies outside the file".to_string())?;
    let len = usize::try_from(member.stored_size).map_err(|_| "it lies outside the file".to_string())?;
    let end = base.checked_add(len).ok_or("it lies outside the file")?;
    let pyz = data.get(base..end).ok_or("it lies outside the file")?;
    let r = Reader::new(pyz);
    if pyz.get(..4) != Some(b"PYZ\0") {
        return Err("it doesn't start with the PYZ magic number".into());
    }
    let magic = r.u16_le(4).filter(|_| pyz.get(6..8) == Some(&[0x0d, 0x0a])).ok_or("it has no Python magic number")?;
    let toc_at = r.u32_be(8).and_then(|v| usize::try_from(v).ok()).ok_or("its header ends early")?;
    let body = pyz.get(toc_at..).ok_or("its table lies outside it")?;
    let table = pyc::read_value(body, None).map_err(|e| format!("its table couldn't be read: {e}"))?;
    let (modules, total) = pyz_table(&table.value, room).ok_or("its table isn't the shape we know")?;
    let key_inside = modules.iter().any(|m| m.name.contains("crypto_key"));
    let in_range = |m: &PyzModule| m.at.checked_add(m.len).is_some_and(|e| e <= len as u64);
    let samples: Vec<&[u8]> =
        modules.iter().filter(|m| in_range(m) && m.len >= 2).take(SAMPLE).filter_map(|m| pyz.get(usize::try_from(m.at).ok()?..)).collect();
    let unzipped = !samples.is_empty() && samples.iter().all(|b| !looks_zlib(b));
    let encrypted = key_seen || key_inside || unzipped;
    let kind = format!("{PYZ_KIND}{magic:04x}");
    let entries = modules
        .iter()
        .map(|m| PackedEntry {
            path: module_path(&member.path, &m.name, matches!(m.kind, 1 | 3)),
            offset: member.offset.saturating_add(m.at),
            stored_size: m.len,
            size: None,
            compression: if encrypted { Compression::Unreadable } else { Compression::Zlib },
            kind: Some(kind.clone()),
        })
        .collect();
    Ok(PyzRead { magic, entries, total, encrypted })
}

impl PackedFormat for PyInstaller {
    fn id(&self) -> &'static str {
        "pyinstaller"
    }

    fn title(&self) -> &'static str {
        "PyInstaller program"
    }

    fn detect(&self, data: &[u8]) -> bool {
        find_cookie(data).is_some()
    }

    /// List CArchive members and nested PYZ module entries with archive metadata.
    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError> {
        let cookie = find_cookie(data)
            .ok_or_else(|| FormatError::Malformed("no sound PyInstaller cookie (its magic, sizes and Python version must all agree)".into()))?;
        let (members, stopped) = read_table(data, &cookie);
        let mut notes = Vec::new();
        let mut truncated = false;
        if let Some(why) = stopped {
            notes.push(format!("{}, so the members after it aren't listed.", capitalise(&why)));
            truncated = true;
        }
        let key_seen = members.iter().any(|m| matches!(m.type_code, b'm' | b'M' | b's') && m.entry.path.contains("crypto_key"));
        let scripts: Vec<&str> = members.iter().filter(|m| m.type_code == b's').map(|m| m.entry.path.as_str()).collect();
        let entry_scripts: Vec<&str> = scripts.iter().copied().filter(|s| !s.starts_with("pyi_rth_") && !s.starts_with("pyiboot")).collect();
        let options: Vec<&str> = members.iter().filter(|m| m.type_code == b'o').map(|m| m.entry.path.as_str()).collect();
        let mut pyz_facts: Vec<Json> = Vec::new();
        let mut any_encrypted = key_seen;
        let mut nested = Vec::new();
        for m in members.iter().filter(|m| m.type_code == b'z') {
            let room = MAX_ENTRIES.saturating_sub(members.len()).saturating_sub(nested.len());
            match read_pyz(data, &m.entry, room, key_seen) {
                Ok(read) => {
                    any_encrypted |= read.encrypted;
                    pyz_facts.push(json!({
                        "path": m.entry.path,
                        "modules": read.total,
                        "python": pyc::release_for_magic(read.magic).map(|r| r.version),
                        "magic": read.magic,
                        "encrypted": read.encrypted,
                    }));
                    truncated |= read.total > read.entries.len();
                    nested.extend(read.entries);
                }
                Err(why) => {
                    notes.push(format!("The modules in {} aren't listed: {why}.", m.entry.path));
                    pyz_facts.push(json!({"path": m.entry.path, "modules": Json::Null}));
                }
            }
        }
        if any_encrypted {
            notes.push(
                "The program's Python modules look encrypted (PyInstaller's --key), so their names are listed but they can't be read back here.".to_string(),
            );
        }
        if members.iter().any(|m| m.type_code == b's') {
            notes.push(
                "Scripts are stored as bare marshalled code with no .pyc header; formats_bytecode_show reads one taken out when given its python_version."
                    .to_string(),
            );
        }
        let facts = json!({
            "archive_offset": cookie.start,
            "cookie_bytes": cookie.size,
            "python_number": cookie.python,
            "python": python_label(cookie.python),
            "python_library": cookie.library,
            "members": members.len(),
            "entry_scripts": entry_scripts,
            "scripts": scripts,
            "runtime_options": options,
            "pyz_archives": pyz_facts,
            "encrypted_modules": any_encrypted,
        });
        let mut entries: Vec<PackedEntry> = members.into_iter().map(|m| m.entry).collect();
        entries.extend(nested);
        Ok(PackedListing { facts, entries, notes, truncated })
    }

    /// Extract a CArchive member or PYZ module within `max_bytes`, including any `.pyc` header.
    fn read(&self, data: &[u8], entry: &PackedEntry, max_bytes: u64) -> Result<Vec<u8>, FormatError> {
        const PYC_HEADER_BYTES: u64 = 16;
        let magic = entry.kind.as_deref().and_then(|k| k.strip_prefix(PYZ_KIND)).and_then(|m| u16::from_str_radix(m, 16).ok());
        let body_limit = match magic {
            Some(_) => max_bytes.checked_sub(PYC_HEADER_BYTES).ok_or_else(|| FormatError::TooLarge(format!("{} needs a .pyc header", entry.path)))?,
            None => max_bytes,
        };
        let body = read_stored(data, entry, body_limit)?;
        match magic {
            Some(magic) => Ok(pyc::wrap_marshal(magic, &body)),
            None => Ok(body),
        }
    }
}

fn capitalise(s: &str) -> String {
    let mut c = s.chars();
    c.next().map_or_else(String::new, |f| f.to_uppercase().chain(c).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::packed;
    use craft_anything_testkit::packed::{code_311, pyinstaller, pyinstaller_sample, pyz};

    fn find<'a>(l: &'a PackedListing, path: &str) -> &'a PackedEntry {
        l.entries.iter().find(|e| e.path == path).unwrap_or_else(|| panic!("{path} isn't listed"))
    }

    #[test]
    fn a_new_program_lists_and_reads() {
        let data = pyinstaller_sample();
        assert!(PyInstaller.detect(&data));
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.facts["python"], "3.12");
        assert_eq!(l.facts["python_library"], "Python.dll");
        assert_eq!(l.facts["cookie_bytes"], 88);
        assert_eq!(l.facts["entry_scripts"][0], "main");
        assert_eq!(l.facts["runtime_options"][0], "pyi-runtime-tmpdir");
        assert_eq!(l.facts["encrypted_modules"], false);
        assert_eq!(find(&l, "main").kind.as_deref(), Some("script"));
        assert_eq!(find(&l, "main").compression, Compression::Zlib);
        assert_eq!(PyInstaller.read(&data, find(&l, "struct"), 1000).unwrap(), [0xaa; 100]);
        assert_eq!(PyInstaller.read(&data, find(&l, "libz.so.1"), 1000).unwrap(), b"native");
        assert!(!l.truncated);
    }

    #[test]
    fn pyz_modules_are_listed_and_read_as_pyc_files() {
        let data = pyinstaller_sample();
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.facts["pyz_archives"][0]["modules"], 2);
        assert_eq!(l.facts["pyz_archives"][0]["python"], "3.12");
        let util = find(&l, "PYZ-00.pyz.modules/pkg/util.pyc");
        let bytes = PyInstaller.read(&data, util, 10_000).unwrap();
        let file = pyc::read_pyc(&bytes).unwrap();
        assert_eq!(file.header.version, Some("3.12"));
        assert_eq!(file.code.unwrap().root.filename, "pkg/util.py");
        find(&l, "PYZ-00.pyz.modules/pkg/__init__.pyc");
        // The PYZ itself is there too, and its folder doesn't collide with it.
        find(&l, "PYZ-00.pyz");
    }

    #[test]
    fn the_old_cookie_and_an_old_dict_table_read() {
        let code = code_311("m", "m", "f.py", 1, &[], &[], &[]);
        let z = pyz(3425, &[("a", 0, &code)], true, true);
        let data = pyinstaller(&[("main", b's', b"x", false), ("PYZ.pyz", b'z', &z, false)], false, 27);
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.facts["cookie_bytes"], 24);
        assert_eq!(l.facts["python"], "2.7");
        assert_eq!(l.facts["python_library"], Json::Null);
        assert_eq!(l.entries.len(), 3);
        find(&l, "PYZ.pyz.modules/a.pyc");
    }

    #[test]
    fn data_after_the_archive_is_allowed() {
        // A signature appended after the archive, as signing does on Windows.
        let mut data = pyinstaller_sample();
        data.extend([0u8; 512]);
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(PyInstaller.read(&data, find(&l, "libz.so.1"), 100).unwrap(), b"native");
    }

    /// Verify that code/module crypto_key markers flag encryption while data members do not.
    #[test]
    fn encrypted_modules_are_flagged_and_listed_but_not_read() {
        // A key module in the archive.
        let code = code_311("m", "m", "f.py", 1, &[], &[], &[]);
        let z = pyz(3531, &[("a", 0, &code)], false, true);
        let data = pyinstaller(&[("pyi_crypto_key", b'm', b"k", false), ("PYZ.pyz", b'z', &z, false)], true, 312);
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.facts["encrypted_modules"], true);
        assert!(l.notes.iter().any(|n| n.contains("encrypted")));
        let a = find(&l, "PYZ.pyz.modules/a.pyc");
        assert_eq!(a.compression, Compression::Unreadable);
        assert!(matches!(PyInstaller.read(&data, a, 1000), Err(FormatError::Unsupported(_))));

        // Members that aren't zlib, with no key to be seen.
        let z = pyz(3531, &[("a", 0, &[0xee; 40])], false, false);
        let data = pyinstaller(&[("PYZ.pyz", b'z', &z, false)], true, 312);
        assert_eq!(PyInstaller.list(&data).unwrap().facts["pyz_archives"][0]["encrypted"], true);

        // An ordinary data member named crypto_key.txt does not mark unencrypted PYZ modules unreadable.
        let z = pyz(3531, &[("a", 0, &code)], false, true);
        let data = pyinstaller(&[("crypto_key.txt", b'x', b"plain", false), ("PYZ.pyz", b'z', &z, false)], true, 312);
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.facts["encrypted_modules"], false);
        let a = find(&l, "PYZ.pyz.modules/a.pyc");
        assert_eq!(a.compression, Compression::Zlib);
        assert!(pyc::read_pyc(&PyInstaller.read(&data, a, 1000).unwrap()).unwrap().code.is_some());
    }

    #[test]
    fn a_damaged_pyz_keeps_the_outer_listing_and_says_why() {
        for bad in [&b"PYZ\0"[..], b"not a pyz at all", b"PYZ\0\xcb\x0d\x0d\x0a\xff\xff\xff\xff"] {
            let data = pyinstaller(&[("main", b's', b"x", false), ("PYZ.pyz", b'z', bad, false)], true, 312);
            let l = PyInstaller.list(&data).unwrap();
            assert_eq!(l.entries.len(), 2);
            assert!(l.notes.iter().any(|n| n.contains("aren't listed")), "{:?}", l.notes);
        }
    }

    #[test]
    fn a_bootloader_alone_is_not_detected() {
        assert!(!PyInstaller.detect(b"\x7fELF bootloader holding MEI\x0c\x0b\x0a\x0b\x0e and nothing else after it, nothing"));
        assert!(!PyInstaller.detect(b"plain file"));
        assert!(PyInstaller.list(b"plain file").is_err());
    }

    #[test]
    fn hostile_names_stay_in_the_listing_for_the_writer_to_refuse() {
        let data = pyinstaller(&[("../../evil", b'x', b"x", false)], true, 312);
        assert_eq!(PyInstaller.list(&data).unwrap().entries[0].path, "../../evil");
        let z = pyz(3531, &[("....evil", 0, &[0x78, 0x9c])], false, false);
        let data = pyinstaller(&[("PYZ.pyz", b'z', &z, false)], true, 312);
        assert!(PyInstaller.list(&data).unwrap().entries.iter().any(|e| e.path.contains("//")));
    }

    #[test]
    fn truncation_at_every_length_never_panics() {
        let full = pyinstaller_sample();
        for len in 0..full.len() {
            let d = &full[..len];
            let _ = PyInstaller.detect(d);
            if let Ok(l) = PyInstaller.list(d) {
                for e in &l.entries {
                    let _ = PyInstaller.read(d, e, 10_000);
                }
            }
        }
    }

    #[test]
    fn corrupt_cookie_fields_never_panic() {
        let full = pyinstaller_sample();
        let at = rfind(&full).unwrap();
        for field in [8usize, 12, 16, 20] {
            for v in [u32::MAX, 0x8000_0000, 0, 1] {
                let mut d = full.clone();
                d[at + field..at + field + 4].copy_from_slice(&v.to_be_bytes());
                let _ = PyInstaller.list(&d);
            }
        }
    }

    #[test]
    fn corrupt_tables_and_members_never_panic() {
        let full = pyinstaller_sample();
        let cookie = find_cookie(&full).unwrap();
        // Every byte from the PYZ's start (which holds its table) through the archive's table.
        let toc_end = cookie.start + cookie.toc_at + cookie.toc_len;
        let from = full.len().saturating_sub(1200).max(cookie.start);
        for at in from..toc_end {
            for v in [0xffu8, 0x7f, 0] {
                let mut d = full.clone();
                d[at] = v;
                if let Ok(l) = PyInstaller.list(&d) {
                    for e in &l.entries {
                        let _ = PyInstaller.read(&d, e, 10_000);
                    }
                }
            }
        }
    }

    #[test]
    fn a_damaged_table_keeps_what_came_before_and_says_so() {
        let full = pyinstaller_sample();
        let cookie = find_cookie(&full).unwrap();
        let mut d = full.clone();
        // The first entry is 18 + 16 bytes; the second's length becomes nonsense.
        let second = cookie.start + cookie.toc_at + 34;
        d[second..second + 4].copy_from_slice(&u32::MAX.to_be_bytes());
        let l = PyInstaller.list(&d).unwrap();
        assert!(l.truncated);
        assert_eq!(l.entries.len(), 1);
        assert!(l.notes[0].contains("damaged"));
    }

    #[test]
    fn a_table_sharing_a_huge_name_is_refused_before_copying_it() {
        let long = "n".repeat(MAX_NAME + 1);
        let z = pyz(3531, &[(&long, 0, b"\x78\x9c")], false, false);
        let data = pyinstaller(&[("PYZ.pyz", b'z', &z, false)], true, 312);
        let l = PyInstaller.list(&data).unwrap();
        assert_eq!(l.entries.len(), 1);
        assert!(l.notes.iter().any(|n| n.contains("isn't the shape")), "{:?}", l.notes);
    }

    #[test]
    fn a_table_past_the_room_left_keeps_what_fits_and_says_so() {
        let table = pyc::read_value(
            &craft_anything_testkit::packed::marshal::list(vec![
                craft_anything_testkit::packed::marshal::tuple(vec![
                    craft_anything_testkit::packed::marshal::string("a"),
                    craft_anything_testkit::packed::marshal::tuple(vec![craft_anything_testkit::packed::marshal::int(0); 3]),
                ]);
                3
            ]),
            None,
        )
        .unwrap();
        let (kept, total) = pyz_table(&table.value, 2).unwrap();
        assert_eq!((kept.len(), total), (2, 3));
    }

    /// Verify that `read` enforces `max_bytes` including the 16-byte `.pyc` header for PYZ modules.
    #[test]
    fn reads_stop_at_their_limit() {
        let data = pyinstaller_sample();
        let l = PyInstaller.list(&data).unwrap();
        assert!(matches!(PyInstaller.read(&data, find(&l, "struct"), 10), Err(FormatError::TooLarge(_))));
        let util = find(&l, "PYZ-00.pyz.modules/pkg/util.pyc");
        let full = PyInstaller.read(&data, util, 10_000).unwrap();
        assert!(matches!(PyInstaller.read(&data, util, 15), Err(FormatError::TooLarge(_))));
        assert!(matches!(PyInstaller.read(&data, util, (full.len() - 1) as u64), Err(FormatError::TooLarge(_))));
        assert_eq!(PyInstaller.read(&data, util, full.len() as u64).unwrap(), full);
    }

    #[test]
    fn it_is_the_reader_for_these_files() {
        assert_eq!(packed::detect(&pyinstaller_sample()).map(|r| r.id()), Some("pyinstaller"));
    }
}
