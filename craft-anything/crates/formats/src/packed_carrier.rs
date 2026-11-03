//! Where native programs keep a payload: named sections (Mach-O, ELF, PE), ELF notes and PE
//! resources. Shared by the readers in [`crate::packed`].

use crate::bytes::Reader;
use crate::pe;
use object::read::macho::{FatArch, MachOFatFile32, MachOFatFile64};
use object::{FileKind, Object, ObjectSection};

/// A byte range of the file.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct Span {
    pub start: usize,
    pub len: usize,
}

impl Span {
    fn checked(start: u64, len: u64, file: usize) -> Option<Span> {
        let start = usize::try_from(start).ok()?;
        let len = usize::try_from(len).ok()?;
        (start.checked_add(len)? <= file).then_some(Span { start, len })
    }

    pub fn bytes<'a>(&self, data: &'a [u8]) -> Option<&'a [u8]> {
        data.get(self.start..self.start.checked_add(self.len)?)
    }
}

/// Which slices a file has: itself, or each slice of a universal Mach-O.
fn slices(data: &[u8]) -> Vec<(usize, &[u8])> {
    let fat: Option<Vec<(u64, u64)>> = match FileKind::parse(data) {
        Ok(FileKind::MachOFat32) => MachOFatFile32::parse(data).ok().map(|f| f.arches().iter().map(FatArch::file_range).collect()),
        Ok(FileKind::MachOFat64) => MachOFatFile64::parse(data).ok().map(|f| f.arches().iter().map(FatArch::file_range).collect()),
        _ => None,
    };
    match fat {
        Some(ranges) => ranges
            .into_iter()
            .take(32)
            .filter_map(|(off, size)| {
                let s = Span::checked(off, size, data.len())?;
                Some((s.start, s.bytes(data)?))
            })
            .collect(),
        None => vec![(0, data)],
    }
}

/// Sections with this name (and, on Mach-O, one of these segments), in every slice of the file.
pub(crate) fn sections(data: &[u8], name: &str, segments: &[&str]) -> Vec<Span> {
    let mut out = Vec::new();
    for (base, slice) in slices(data) {
        let Ok(file) = object::File::parse(slice) else { continue };
        for s in file.sections() {
            if s.name().ok() != Some(name) {
                continue;
            }
            if !segments.is_empty() && !s.segment_name().ok().flatten().is_some_and(|seg| segments.contains(&seg)) {
                continue;
            }
            let Some((off, size)) = s.file_range() else { continue };
            let Some(off) = off.checked_add(base as u64) else { continue };
            out.extend(Span::checked(off, size, data.len()));
        }
    }
    out
}

/// Most notes walked in one file, across all its `PT_NOTE` segments. Headers can all point at the
/// same segment, so a small file could otherwise make this do (and keep) billions of them.
const MAX_NOTES_WALKED: usize = 100_000;

/// Notes owned by `owner` in an ELF file's `PT_NOTE` segments, which is where a running program
/// looks for them.
pub(crate) fn elf_notes(data: &[u8], owner: &str) -> Vec<Span> {
    let r = Reader::new(data);
    if !data.starts_with(b"\x7fELF") {
        return Vec::new();
    }
    let big = r.u8(5) == Some(2);
    let u16_at = |o: usize| if big { r.u16_be(o) } else { r.u16_le(o) };
    let u32_at = |o: usize| if big { r.u32_be(o) } else { r.u32_le(o) };
    let u64_at = |o: usize| if big { r.u64_be(o) } else { r.u64_le(o) };
    let wide = r.u8(4) == Some(2);
    let (phoff, phentsize, phnum) = if wide {
        (u64_at(32).and_then(|v| usize::try_from(v).ok()), u16_at(54), u16_at(56))
    } else {
        (u32_at(28).and_then(|v| usize::try_from(v).ok()), u16_at(42), u16_at(44))
    };
    let (Some(phoff), Some(phentsize), Some(phnum)) = (phoff, phentsize, phnum) else { return Vec::new() };
    if usize::from(phentsize) < if wide { 56 } else { 32 } {
        return Vec::new();
    }
    let mut out = Vec::new();
    let mut budget = MAX_NOTES_WALKED;
    for i in 0..usize::from(phnum) {
        let Some(ph) = usize::from(phentsize).checked_mul(i).and_then(|o| o.checked_add(phoff)) else { break };
        if u32_at(ph) != Some(4) {
            continue;
        }
        let range = if wide {
            ph.checked_add(8).and_then(u64_at).zip(ph.checked_add(32).and_then(u64_at))
        } else {
            ph.checked_add(4).and_then(u32_at).map(u64::from).zip(ph.checked_add(16).and_then(u32_at).map(u64::from))
        };
        let Some(span) = range.and_then(|(off, size)| Span::checked(off, size, data.len())) else { continue };
        walk_notes(data, span, owner, big, &mut budget, &mut out);
    }
    out
}

fn walk_notes(data: &[u8], seg: Span, owner: &str, big: bool, budget: &mut usize, out: &mut Vec<Span>) {
    let r = Reader::new(data);
    let u32_at = |o: usize| if big { r.u32_be(o) } else { r.u32_le(o) };
    let end = seg.start.saturating_add(seg.len);
    let mut at = seg.start;
    let up4 = |n: usize| n.checked_add(3).map(|v| v & !3);
    while at.checked_add(12).is_some_and(|e| e <= end) {
        let Some(left) = budget.checked_sub(1) else { return };
        *budget = left;
        let (Some(namesz), Some(descsz)) = (u32_at(at), at.checked_add(4).and_then(u32_at)) else { return };
        let (Ok(namesz), Ok(descsz)) = (usize::try_from(namesz), usize::try_from(descsz)) else { return };
        let name_at = at + 12;
        let Some(desc_at) = up4(namesz).and_then(|n| name_at.checked_add(n)) else { return };
        let Some(next) = up4(descsz).and_then(|n| desc_at.checked_add(n)) else { return };
        if desc_at.checked_add(descsz).is_none_or(|e| e > end) {
            return;
        }
        let name = data.get(name_at..name_at.saturating_add(namesz)).map(|n| n.strip_suffix(&[0]).unwrap_or(n));
        if name == Some(owner.as_bytes()) {
            out.push(Span { start: desc_at, len: descsz });
        }
        at = next;
    }
}

/// `RT_RCDATA` resources of a PE file called `name`.
pub(crate) fn pe_resources(data: &[u8], name: &str) -> Vec<Span> {
    if !data.starts_with(b"MZ") || !pe::has_pe_header(data) {
        return Vec::new();
    }
    let Ok(res) = pe::parse_resources(data, 4096) else { return Vec::new() };
    res.entries
        .iter()
        .filter(|e| e.name == name && e.type_name == pe::resource_type_name(10))
        .filter_map(|e| Span::checked(e.file_offset?, u64::from(e.size), data.len()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::packed as kit;

    /// A 64-bit ELF whose headers all point at one segment of `notes` empty notes owned by `OWN`.
    fn elf_of_repeated_notes(phentsize: u16, phnum: u16, notes: usize) -> Vec<u8> {
        let note: Vec<u8> = [&4u32.to_le_bytes()[..], &0u32.to_le_bytes(), &1u32.to_le_bytes(), b"OWN\0"].concat();
        let seg_at = 64 + usize::from(phentsize).max(56) * usize::from(phnum);
        let mut d = vec![0u8; seg_at];
        d[..6].copy_from_slice(&[0x7f, b'E', b'L', b'F', 2, 1]);
        d[32..40].copy_from_slice(&64u64.to_le_bytes());
        d[54..56].copy_from_slice(&phentsize.to_le_bytes());
        d[56..58].copy_from_slice(&phnum.to_le_bytes());
        for i in 0..usize::from(phnum) {
            let ph = 64 + usize::from(phentsize) * i;
            d[ph..ph + 4].copy_from_slice(&4u32.to_le_bytes());
            d[ph + 8..ph + 16].copy_from_slice(&(seg_at as u64).to_le_bytes());
            d[ph + 32..ph + 40].copy_from_slice(&((note.len() * notes) as u64).to_le_bytes());
        }
        for _ in 0..notes {
            d.extend_from_slice(&note);
        }
        d
    }

    #[test]
    fn a_small_elf_cant_make_the_note_walk_run_away() {
        assert_eq!(elf_notes(&elf_of_repeated_notes(56, 1, 3), "OWN").len(), 3, "the fixture is a sound file");
        assert!(elf_notes(&elf_of_repeated_notes(0, 65535, 1000), "OWN").is_empty(), "headers with no size all read the same bytes");
        assert!(elf_notes(&elf_of_repeated_notes(8, 100, 1000), "OWN").is_empty(), "headers can't overlap");
        let many = elf_notes(&elf_of_repeated_notes(56, 500, 2000), "OWN");
        assert_eq!(many.len(), MAX_NOTES_WALKED, "500 headers over one segment stop at the limit");
    }

    #[test]
    fn sections_are_found_in_each_carrier() {
        let macho = kit::macho_section("__BUN", "__bun", b"payload");
        let s = sections(&macho, "__bun", &["__BUN"]);
        assert_eq!(s.len(), 1);
        assert_eq!(s[0].bytes(&macho), Some(&b"payload"[..]));
        assert!(sections(&macho, "__bun", &["__OTHER"]).is_empty());

        let elf = kit::elf_section(".bun", b"payload");
        assert_eq!(sections(&elf, ".bun", &[])[0].bytes(&elf), Some(&b"payload"[..]));

        let pe = kit::pe_section(".bun", b"payload");
        assert_eq!(&sections(&pe, ".bun", &[])[0].bytes(&pe).unwrap()[..7], b"payload");
    }

    #[test]
    fn a_universal_file_gives_offsets_in_the_whole_file() {
        let one = kit::macho_section("__BUN", "__bun", b"payload");
        let fat = kit::macho_universal(&[one]);
        let s = sections(&fat, "__bun", &["__BUN"]);
        assert_eq!(s[0].bytes(&fat), Some(&b"payload"[..]));
        assert!(s[0].start > 0x4000);
    }

    #[test]
    fn notes_and_resources_are_found() {
        let elf = kit::elf_note("OWNER", b"note body");
        assert_eq!(elf_notes(&elf, "OWNER")[0].bytes(&elf), Some(&b"note body"[..]));
        assert!(elf_notes(&elf, "NOBODY").is_empty());

        let pe = kit::pe_rcdata("BLOB", b"resource body");
        assert_eq!(pe_resources(&pe, "BLOB")[0].bytes(&pe), Some(&b"resource body"[..]));
        assert!(pe_resources(&pe, "OTHER").is_empty());
    }

    #[test]
    fn damaged_carriers_find_nothing_and_never_panic() {
        let carriers = [
            kit::macho_section("__BUN", "__bun", b"payload"),
            kit::elf_section(".bun", b"payload"),
            kit::elf_note("OWNER", b"note"),
            kit::pe_rcdata("BLOB", b"res"),
        ];
        for c in &carriers {
            for len in (0..c.len()).step_by(7) {
                let d = &c[..len];
                let _ = sections(d, "__bun", &["__BUN"]);
                let _ = sections(d, ".bun", &[]);
                let _ = elf_notes(d, "OWNER");
                let _ = pe_resources(d, "BLOB");
            }
            for at in 0..c.len().min(400) {
                let mut d = c.clone();
                d[at] = 0xff;
                let _ = elf_notes(&d, "OWNER");
                let _ = pe_resources(&d, "BLOB");
                let _ = sections(&d, ".bun", &[]);
            }
        }
    }
}
