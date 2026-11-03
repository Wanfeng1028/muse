//! Godot packs (`.pck`): the file table of a pack on its own, or of one carried at the end of the
//! game's program (the last 12 bytes are the pack's size and `GDPC`).
//!
//! Layouts read, all little-endian, starting with `GDPC`, the format, and the engine's
//! major.minor.patch:
//! - format 1 (Godot 3): 16 reserved words, then the file count and the table straight after.
//!   Offsets count from the start of the whole file.
//! - format 2 (Godot 4 up to 4.4): pack flags, file base, 16 reserved words, then the file count
//!   and the table. Offsets count from the file base (itself from the pack's start when the flags
//!   say so).
//! - format 3 (Godot 4.5 on): pack flags, file base, the table's offset from the pack's start. The
//!   file count and table are there, and the file base always counts from the pack's start.
//!
//! A later format, or pack flags we don't know, gives the header with a note: its table isn't
//! guessed at. Nothing is ever decrypted: an encrypted table leaves no names to list, and an
//! encrypted member is listed as unreadable.

use crate::bytes::Reader;
use crate::common::FormatError;
use crate::packed::{Compression, MAX_ENTRIES, PackedEntry, PackedFormat, PackedListing};
use serde::Serialize;
use serde_json::json;

pub const MAGIC: &[u8; 4] = b"GDPC";
/// Bytes at the end of a program that say a pack is carried: its size, then [`MAGIC`].
pub const TRAILER_SIZE: u64 = 12;
/// Enough bytes at a pack's start for [`header`] to read any format's header.
pub const HEADER_READ: usize = 104;

const PACK_DIR_ENCRYPTED: u32 = 1;
const PACK_RELATIVE_BASE: u32 = 1 << 1;
const PACK_SPARSE: u32 = 1 << 2;
const PACK_KNOWN: u32 = PACK_DIR_ENCRYPTED | PACK_RELATIVE_BASE | PACK_SPARSE;
const FILE_ENCRYPTED: u32 = 1;
const FILE_REMOVAL: u32 = 1 << 1;
const FILE_KNOWN: u32 = FILE_ENCRYPTED | FILE_REMOVAL;
/// A longer path than any file system takes: past this, the table is damaged.
const MAX_PATH: u32 = 1 << 16;

/// The header of a pack.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Header {
    /// Pack format (Godot 3 wrote 1; Godot 4 wrote 2, then 3).
    pub format: u32,
    /// The Godot version that wrote it.
    pub engine_version: String,
    /// Raw pack flags (0 for format 1, which has none).
    pub flags: u32,
    /// Raw file base from the header (0 for format 1).
    pub file_base: u64,
    /// Where the file count and table start, from the pack's start. `None` for a format not read.
    pub directory_offset: Option<u64>,
}

impl Header {
    pub fn directory_encrypted(&self) -> bool {
        self.flags & PACK_DIR_ENCRYPTED != 0
    }

    /// Where offset 0 of a member is, in the whole file, for a pack starting at `start`.
    fn member_base(&self, start: u64) -> Option<u64> {
        let relative = self.format >= 3 || self.flags & PACK_RELATIVE_BASE != 0;
        if relative { start.checked_add(self.file_base) } else { Some(self.file_base) }
    }
}

/// One line of a pack's file table.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Member {
    /// The path without Godot's `res://`.
    pub path: String,
    /// Where its bytes start in the whole file. `None` when the table's numbers overflow.
    pub offset: Option<u64>,
    pub size: u64,
    /// The MD5 the table declares, as hex; `None` when it's all zeros (not set).
    pub md5: Option<String>,
    /// Raw file flags (0 for format 1).
    pub flags: u32,
}

impl Member {
    pub fn encrypted(&self) -> bool {
        self.flags & FILE_ENCRYPTED != 0
    }

    /// A patch's mark that this path is removed: it has no bytes.
    pub fn removal(&self) -> bool {
        self.flags & FILE_REMOVAL != 0
    }
}

/// A pack's header and what could be read of its table.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Pack {
    pub header: Header,
    /// Where the pack starts in the file (above 0 when it's carried by a program).
    pub start: u64,
    /// Whether a program carries it.
    pub embedded: bool,
    /// The file count the pack declares, when it could be read.
    pub declared_files: Option<u32>,
    /// Whether the table was read (not when it's encrypted or its layout isn't known).
    pub table_read: bool,
    pub members: Vec<Member>,
    pub truncated: bool,
    pub notes: Vec<String>,
}

/// Where a program's trailer says its pack starts, from the file's last bytes (`tail`, at least
/// [`TRAILER_SIZE`]) and the file's length. The caller still checks for [`MAGIC`] there.
pub fn trailer_start(tail: &[u8], file_len: u64) -> Option<u64> {
    let at = tail.len().checked_sub(TRAILER_SIZE as usize)?;
    let r = Reader::new(tail);
    if r.slice(at.checked_add(8)?, 4)? != MAGIC {
        return None;
    }
    file_len.checked_sub(TRAILER_SIZE)?.checked_sub(r.u64_le(at)?)
}

/// Where a pack starts in `data` and whether it's carried by a program; `None` when there's none.
pub fn find(data: &[u8]) -> Option<(usize, bool)> {
    if data.starts_with(MAGIC) {
        return Some((0, false));
    }
    let start = usize::try_from(trailer_start(data, data.len() as u64)?).ok()?;
    data.get(start..)?.starts_with(MAGIC).then_some((start, true))
}

/// The header at the start of `pack` (the bytes from the pack's start; [`HEADER_READ`] is enough).
pub fn header(pack: &[u8]) -> Result<Header, FormatError> {
    if !pack.starts_with(MAGIC) {
        return Err(FormatError::Malformed("no GDPC mark at the pack's start".into()));
    }
    let r = Reader::new(pack);
    let short = |what: &str| FormatError::Truncated(format!("the pack's header stops before {what}"));
    let word = |at: usize, what: &str| r.u32_le(at).ok_or_else(|| short(what));
    let format = word(4, "its format")?;
    let engine_version = format!("{}.{}.{}", word(8, "its version")?, word(12, "its version")?, word(16, "its version")?);
    let (flags, file_base, directory_offset) = match format {
        1 => (0, 0, Some(84)),
        2 => (word(20, "its flags")?, r.u64_le(24).ok_or_else(|| short("its file base"))?, Some(96)),
        3 => {
            let directory = r.u64_le(32).ok_or_else(|| short("its table's offset"))?;
            (word(20, "its flags")?, r.u64_le(24).ok_or_else(|| short("its file base"))?, Some(directory))
        }
        _ => (0, 0, None),
    };
    Ok(Header { format, engine_version, flags, file_base, directory_offset })
}

/// Read a pack from a whole file's bytes.
pub fn parse(data: &[u8]) -> Result<Pack, FormatError> {
    let (start, embedded) = find(data).ok_or_else(|| FormatError::Malformed("this file has no Godot pack".into()))?;
    let bytes = data.get(start..).unwrap_or_default();
    let header = header(bytes)?;
    let mut pack =
        Pack { header, start: start as u64, embedded, declared_files: None, table_read: false, members: Vec::new(), truncated: false, notes: Vec::new() };
    let Some(directory) = pack.header.directory_offset else {
        pack.notes.push(format!(
            "This pack uses format {}, whose file table isn't known here, so only its header was read (formats 1 to 3 are).",
            pack.header.format
        ));
        return Ok(pack);
    };
    let at = usize::try_from(directory).ok();
    pack.declared_files = at.and_then(|a| Reader::new(bytes).u32_le(a));
    let Some(count) = pack.declared_files else {
        return Err(FormatError::Truncated("the pack's file count lies outside the file".into()));
    };
    let unknown = pack.header.flags & !PACK_KNOWN;
    if unknown != 0 {
        pack.notes.push(format!("This pack sets flags not known here ({unknown:#x}), so its file table wasn't read; it may not mean what it seems to."));
        return Ok(pack);
    }
    if pack.header.flags & PACK_SPARSE != 0 {
        pack.notes.push(format!(
            "This pack is a sparse bundle declaring {count} file(s): only its header was read, because its members aren't stored like a plain pack's."
        ));
        return Ok(pack);
    }
    if pack.header.directory_encrypted() {
        pack.notes.push(format!(
            "This pack's file table is encrypted with the game's own key, so its {count} declared file(s) can't be named. Keys aren't searched for or guessed."
        ));
        return Ok(pack);
    }
    pack.table_read = true;
    read_table(bytes, data.len() as u64, at.unwrap_or_default().saturating_add(4), count, &mut pack);
    Ok(pack)
}

/// Read the table's lines from `at` until the count, a limit, or the first line that doesn't fit.
fn read_table(bytes: &[u8], file_len: u64, mut at: usize, count: u32, pack: &mut Pack) {
    let r = Reader::new(bytes);
    let base = pack.header.member_base(pack.start);
    let with_flags = pack.header.format >= 2;
    for i in 0..count {
        if pack.members.len() >= MAX_ENTRIES {
            pack.truncated = true;
            pack.notes.push(format!("Stopped at {MAX_ENTRIES} files; the pack declares {count}."));
            return;
        }
        let Some((member, next)) = table_line(&r, at, base, with_flags) else {
            pack.truncated = true;
            pack.notes.push(format!("The file table stops being readable at line {} of the {count} declared.", u64::from(i) + 1));
            return;
        };
        pack.members.push(member);
        at = next;
    }
    let outside = pack.members.iter().filter(|m| m.offset.and_then(|o| o.checked_add(m.size)).is_none_or(|end| end > file_len)).count();
    if outside > 0 {
        pack.notes.push(format!("{outside} file(s) in the table lie outside this file."));
    }
}

/// One table line and where the next starts.
fn table_line(r: &Reader<'_>, at: usize, base: Option<u64>, with_flags: bool) -> Option<(Member, usize)> {
    let len = r.u32_le(at)?;
    if len > MAX_PATH {
        return None;
    }
    let path_at = at.checked_add(4)?;
    let raw = r.slice(path_at, len as usize)?;
    let text = String::from_utf8_lossy(raw.split(|b| *b == 0).next().unwrap_or_default());
    let after = path_at.checked_add(len as usize)?;
    let offset = r.u64_le(after)?;
    let size = r.u64_le(after.checked_add(8)?)?;
    let md5 = r.slice(after.checked_add(16)?, 16)?;
    let mut next = after.checked_add(32)?;
    let mut flags = 0;
    if with_flags {
        flags = r.u32_le(next)?;
        next = next.checked_add(4)?;
    }
    let path = text.strip_prefix("res://").unwrap_or(&text).to_string();
    let md5 = md5.iter().any(|b| *b != 0).then(|| md5.iter().map(|b| format!("{b:02x}")).collect());
    Some((Member { path, offset: base.and_then(|b| b.checked_add(offset)), size, md5, flags }, next))
}

/// How a member reads in a listing: what the table says about it, as short text.
fn member_kind(m: &Member) -> Option<String> {
    if m.removal() {
        return Some("removal record".into());
    }
    match (m.encrypted(), &m.md5) {
        (true, Some(md5)) => Some(format!("encrypted, md5 {md5}")),
        (true, None) => Some("encrypted".into()),
        (false, Some(md5)) => Some(format!("md5 {md5}")),
        (false, None) => None,
    }
}

/// The [`PackedFormat`] reader for Godot packs.
pub struct GodotPck;

impl PackedFormat for GodotPck {
    fn id(&self) -> &'static str {
        "godot_pck"
    }

    fn title(&self) -> &'static str {
        "Godot pack"
    }

    fn detect(&self, data: &[u8]) -> bool {
        find(data).is_some()
    }

    fn list(&self, data: &[u8]) -> Result<PackedListing, FormatError> {
        let pack = parse(data)?;
        let encrypted = pack.members.iter().filter(|m| m.encrypted()).count();
        let removals = pack.members.iter().filter(|m| m.removal()).count();
        let mut notes = pack.notes.clone();
        if encrypted > 0 {
            notes.push(format!(
                "{encrypted} file(s) are encrypted with the game's own key: listed, but they can't be read. Keys aren't searched for or guessed."
            ));
        }
        if removals > 0 {
            notes.push(format!("{removals} line(s) only mark a path as removed by a patch, so they have no bytes."));
        }
        if pack.members.iter().any(|m| m.md5.is_some()) {
            notes.push("The MD5 of each file is what the pack declares; it isn't checked here.".into());
        }
        let facts = json!({
            "pack_format": pack.header.format,
            "engine_version": pack.header.engine_version,
            "pack_start": pack.start,
            "embedded_in_program": pack.embedded,
            "flags": pack.header.flags,
            "file_table_encrypted": pack.header.directory_encrypted(),
            "file_table_read": pack.table_read,
            "file_base": pack.header.file_base,
            "file_table_offset": pack.header.directory_offset,
            "declared_files": pack.declared_files,
            "encrypted_files": encrypted,
            "removal_records": removals,
        });
        let entries = pack.members.iter().map(to_entry).collect();
        Ok(PackedListing { facts, entries, notes, truncated: pack.truncated })
    }
}

fn to_entry(m: &Member) -> PackedEntry {
    let readable = m.flags & !FILE_KNOWN == 0 && !m.encrypted() && !m.removal() && m.offset.is_some();
    PackedEntry {
        path: m.path.clone(),
        offset: m.offset.unwrap_or(u64::MAX),
        stored_size: m.size,
        size: Some(m.size),
        compression: if readable { Compression::None } else { Compression::Unreadable },
        kind: member_kind(m),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::games::{GodotFile, godot_embedded, godot_pck, godot_pck_at};

    fn plain(path: &'static str, data: &'static [u8]) -> GodotFile<'static> {
        GodotFile { path, data, flags: 0, md5: [0xab; 16] }
    }

    fn files() -> Vec<GodotFile<'static>> {
        vec![plain("res://project.binary", b"settings"), plain("res://scenes/main.tscn", b"[gd_scene]"), plain("icon.png", b"\x89PNG")]
    }

    #[test]
    fn every_format_lists_and_reads_back() {
        for format in [1, 2, 3] {
            let pck = godot_pck(format, 2, &files());
            assert!(GodotPck.detect(&pck));
            let l = GodotPck.list(&pck).unwrap();
            assert_eq!(l.facts["pack_format"], format);
            assert_eq!(l.facts["engine_version"], ["3.5.3", "4.4.1", "4.6.1"][format as usize - 1]);
            assert_eq!(l.facts["embedded_in_program"], false);
            assert_eq!(l.facts["declared_files"], 3);
            assert!(!l.truncated);
            let paths: Vec<&str> = l.entries.iter().map(|e| e.path.as_str()).collect();
            assert_eq!(paths, ["project.binary", "scenes/main.tscn", "icon.png"], "format {format}");
            assert_eq!(GodotPck.read(&pck, &l.entries[1], 100).unwrap(), b"[gd_scene]");
            assert_eq!(l.entries[0].kind.as_deref(), Some("md5 abababababababababababababababab"));
            assert_eq!(l.entries[0].compression, Compression::None);
        }
    }

    #[test]
    fn a_pack_carried_by_a_program_is_found_from_its_trailer() {
        for format in [1, 2, 3] {
            let exe = godot_embedded(&[0x7f; 777], &godot_pck_at(format, 2, 777, &files()));
            assert!(GodotPck.detect(&exe));
            let l = GodotPck.list(&exe).unwrap();
            assert_eq!(l.facts["embedded_in_program"], true);
            assert_eq!(l.facts["pack_start"], 777);
            assert_eq!(GodotPck.read(&exe, &l.entries[0], 100).unwrap(), b"settings", "format {format}");
        }
    }

    #[test]
    fn a_file_base_without_the_relative_flag_counts_from_the_files_start() {
        let exe = godot_embedded(&[0x7f; 64], &godot_pck(2, 0, &files()));
        let (start, _) = find(&exe).unwrap();
        let p = parse(&exe).unwrap();
        // The builder wrote its base for a pack at the file's start, so it's 64 too short here:
        // the base is used as written, and doesn't get the pack's start added.
        assert_eq!(p.members[0].offset.unwrap() + start as u64, member_at(&exe, b"settings"));
    }

    fn member_at(hay: &[u8], needle: &[u8]) -> u64 {
        hay.windows(needle.len()).position(|w| w == needle).unwrap() as u64
    }

    #[test]
    fn encrypted_flags_are_reported_and_never_read() {
        let mut list = files();
        list[1].flags = FILE_ENCRYPTED;
        let pck = godot_pck(2, 2, &list);
        let l = GodotPck.list(&pck).unwrap();
        assert_eq!(l.entries[1].compression, Compression::Unreadable);
        assert_eq!(l.entries[1].kind.as_deref(), Some("encrypted, md5 abababababababababababababababab"));
        assert_eq!(l.facts["encrypted_files"], 1);
        assert!(l.notes.iter().any(|n| n.contains("encrypted")));
        assert!(matches!(GodotPck.read(&pck, &l.entries[1], 100), Err(FormatError::Unsupported(_))));
        assert_eq!(GodotPck.read(&pck, &l.entries[0], 100).unwrap(), b"settings");
    }

    #[test]
    fn an_encrypted_table_gives_the_header_and_a_note() {
        for format in [2, 3] {
            let pck = godot_pck(format, 2 | PACK_DIR_ENCRYPTED, &files());
            let l = GodotPck.list(&pck).unwrap();
            assert!(l.entries.is_empty());
            assert_eq!(l.facts["file_table_encrypted"], true);
            assert_eq!(l.facts["file_table_read"], false);
            assert_eq!(l.facts["declared_files"], 3);
            assert!(l.notes.iter().any(|n| n.contains("encrypted") && n.contains('3')));
        }
    }

    #[test]
    fn removal_records_and_unknown_file_flags_have_no_readable_bytes() {
        let mut list = files();
        list[0].flags = FILE_REMOVAL;
        list[2].flags = 1 << 9;
        let pck = godot_pck(2, 2, &list);
        let l = GodotPck.list(&pck).unwrap();
        assert_eq!(l.entries[0].kind.as_deref(), Some("removal record"));
        assert_eq!(l.entries[0].compression, Compression::Unreadable);
        assert_eq!(l.entries[2].compression, Compression::Unreadable);
        assert_eq!(l.facts["removal_records"], 1);
    }

    #[test]
    fn a_later_format_or_unknown_flags_are_named_and_not_guessed_at() {
        let mut later = godot_pck(3, 2, &files());
        later[4] = 4;
        let l = GodotPck.list(&later).unwrap();
        assert!(l.entries.is_empty());
        assert_eq!(l.facts["pack_format"], 4);
        assert!(l.notes[0].contains("format 4"));
        let l = GodotPck.list(&godot_pck(3, 2 | (1 << 7), &files())).unwrap();
        assert!(l.entries.is_empty());
        assert!(l.notes[0].contains("not known"));
        let l = GodotPck.list(&godot_pck(3, 2 | PACK_SPARSE, &files())).unwrap();
        assert!(l.entries.is_empty());
        assert!(l.notes[0].contains("sparse"));
    }

    #[test]
    fn every_cut_short_prefix_is_handled() {
        for format in [1, 2, 3] {
            let pck = godot_pck(format, 2, &files());
            for n in 0..pck.len() {
                let _ = GodotPck.detect(&pck[..n]);
                if let Ok(l) = GodotPck.list(&pck[..n]) {
                    for e in &l.entries {
                        let _ = GodotPck.read(&pck[..n], e, 1 << 20);
                    }
                }
                let _ = header(&pck[..n]);
                let _ = trailer_start(&pck[..n], n as u64);
            }
            let exe = godot_embedded(&[1; 40], &pck);
            for n in 0..exe.len() {
                let _ = GodotPck.list(&exe[..n]);
            }
        }
    }

    #[test]
    fn a_table_cut_short_keeps_what_it_read_and_says_so() {
        let mut pck = godot_pck(2, 2, &files());
        // Declare far more files than there are: the walk stops at the end of the file.
        pck[96..100].copy_from_slice(&u32::MAX.to_le_bytes());
        let l = GodotPck.list(&pck).unwrap();
        assert!(l.truncated);
        assert_eq!(l.facts["declared_files"], u64::from(u32::MAX));
        assert!(l.notes.iter().any(|n| n.contains("stops being readable")));
        assert!(!l.entries.is_empty() && l.entries.len() < 1000);
    }

    #[test]
    fn huge_numbers_do_not_overflow() {
        // A trailer whose size is larger than the file.
        let mut exe = vec![0u8; 32];
        exe.extend_from_slice(&u64::MAX.to_le_bytes());
        exe.extend_from_slice(MAGIC);
        assert!(!GodotPck.detect(&exe));
        // A trailer pointing at the start of nothing.
        assert_eq!(trailer_start(&exe, 3), None);

        // A table offset and a file base near the top of the range.
        let mut pck = godot_pck(3, 2, &files());
        pck[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(GodotPck.list(&pck).is_err());
        let mut pck = godot_pck(3, 2, &files());
        pck[24..32].copy_from_slice(&(u64::MAX - 1).to_le_bytes());
        let l = GodotPck.list(&pck).unwrap();
        assert!(l.notes.iter().any(|n| n.contains("outside this file")));
        for e in &l.entries {
            assert!(GodotPck.read(&pck, e, 100).is_err());
        }

        // A member offset and size at the top: listed, unreadable, no panic.
        let mut pck = godot_pck(1, 0, &[plain("a", b"data")]);
        let line = 96; // after the count, the path's length and its padded bytes
        pck[line..line + 8].copy_from_slice(&u64::MAX.to_le_bytes());
        pck[line + 8..line + 16].copy_from_slice(&u64::MAX.to_le_bytes());
        let l = GodotPck.list(&pck).unwrap();
        assert_eq!(l.entries.len(), 1);
        assert!(GodotPck.read(&pck, &l.entries[0], u64::MAX).is_err());

        // A path length past the file.
        let mut pck = godot_pck(1, 0, &[plain("a", b"data")]);
        pck[88..92].copy_from_slice(&u32::MAX.to_le_bytes());
        let l = GodotPck.list(&pck).unwrap();
        assert!(l.entries.is_empty() && l.truncated);
    }

    #[test]
    fn a_program_without_a_pack_is_left_alone() {
        assert!(!GodotPck.detect(b"\x7fELF and more bytes than a trailer needs"));
        assert!(GodotPck.list(b"\x7fELF and more bytes than a trailer needs").is_err());
        assert!(!GodotPck.detect(b""));
        // The trailer mark alone isn't enough: GDPC must be where it points.
        let mut exe = vec![0u8; 64];
        exe.extend_from_slice(&16u64.to_le_bytes());
        exe.extend_from_slice(MAGIC);
        assert!(!GodotPck.detect(&exe));
    }

    #[test]
    fn hostile_paths_are_only_text_here() {
        let pck = godot_pck(2, 2, &[plain("res://../../evil", b"x"), plain("\u{1F3AE}/ok", b"y")]);
        let l = GodotPck.list(&pck).unwrap();
        assert_eq!(l.entries[0].path, "../../evil", "taking files out refuses it, not the listing");
        assert_eq!(l.entries[1].path, "\u{1F3AE}/ok");
    }

    #[test]
    fn it_is_registered_in_the_packed_seam() {
        let pck = godot_pck(2, 2, &files());
        assert_eq!(crate::packed::detect(&pck).map(|r| r.id()), Some("godot_pck"));
        assert_eq!(crate::packed::by_id("godot_pck").map(|r| r.title()), Some("Godot pack"));
    }
}
