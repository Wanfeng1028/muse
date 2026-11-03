//! Member walkers for Unix archives: tar (v7, ustar, GNU long names and base-256 sizes, pax path
//! overrides) and cpio (newc, crc and portable odc). They list members and where their data
//! lies; nothing is extracted here, and no input can make them panic or loop forever.

use crate::bytes::Reader;
use serde::Serialize;

/// What a member is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MemberKind {
    File,
    Dir,
    Symlink,
    Hardlink,
    Device,
    Fifo,
    Other,
}

/// One archive member.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Member {
    pub name: String,
    pub kind: MemberKind,
    pub size: u64,
    /// Where the member's data starts, relative to the archive start.
    pub data_offset: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub link_target: Option<String>,
    pub mode: u32,
}

/// The members of an archive.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Listing {
    /// `tar`, `cpio-newc`, `cpio-crc` or `cpio-odc`.
    pub format: &'static str,
    pub members: Vec<Member>,
    /// Bytes from the archive start to the end of its last structure (end marker included).
    pub length: u64,
    /// True when the end-of-archive marker was reached.
    pub complete: bool,
    /// True when `max_members` stopped the walk.
    pub truncated: bool,
    pub warnings: Vec<String>,
}

const BLOCK: usize = 512;
const MAX_NAME: usize = 4096;

fn trim_field(f: &[u8]) -> &[u8] {
    let end = f.iter().position(|&b| b == 0).unwrap_or(f.len());
    f.get(..end).unwrap_or(&[])
}

fn text(f: &[u8]) -> String {
    String::from_utf8_lossy(trim_field(f)).into_owned()
}

/// An octal number field (spaces and NULs around it are ignored); GNU base-256 when the high bit
/// of the first byte is set.
fn octal(f: &[u8]) -> Option<u64> {
    if let Some((&first, rest)) = f.split_first()
        && first & 0x80 != 0
    {
        let mut v = u64::from(first & 0x7f);
        for &b in rest {
            v = v.checked_mul(256)?.checked_add(u64::from(b))?;
        }
        return Some(v);
    }
    let s: Vec<u8> = f.iter().copied().filter(|&b| b != 0 && b != b' ').collect();
    if s.is_empty() {
        return Some(0);
    }
    let mut v = 0u64;
    for b in s {
        if !(b'0'..=b'7').contains(&b) {
            return None;
        }
        v = v.checked_mul(8)?.checked_add(u64::from(b - b'0'))?;
    }
    Some(v)
}

/// True when a 512-byte block is a tar header with a correct checksum.
pub fn tar_header_ok(h: &[u8]) -> bool {
    let Some(h) = h.get(..BLOCK) else { return false };
    let Some(stored) = h.get(148..156).and_then(octal) else { return false };
    let mut unsigned = 0u64;
    let mut signed = 0i64;
    for (i, &b) in h.iter().enumerate() {
        let v = if (148..156).contains(&i) { b' ' } else { b };
        unsigned += u64::from(v);
        signed += i64::from(v as i8);
    }
    // An all-zero block sums to 256 (the blank checksum field) and is the end marker, not a header.
    unsigned != 256 && (stored == unsigned || i64::try_from(stored).is_ok_and(|s| s == signed))
}

fn round_up(v: u64, to: u64) -> Option<u64> {
    let r = v % to;
    if r == 0 { Some(v) } else { v.checked_add(to - r) }
}

/// Walk a tar archive. `None` when the first block is not a valid header.
pub fn tar(data: &[u8], max_members: usize) -> Option<Listing> {
    let r = Reader::new(data);
    if !tar_header_ok(r.slice(0, BLOCK)?) {
        return None;
    }
    let mut out = Listing { format: "tar", ..Listing::default() };
    let mut pos = 0usize;
    let mut long_name: Option<String> = None;
    let mut long_link: Option<String> = None;
    let mut pax_path: Option<String> = None;
    let mut pax_link: Option<String> = None;
    let mut pax_size: Option<u64> = None;
    // Every iteration advances by at least one block, so the walk is bounded by the input size.
    loop {
        let Some(h) = r.slice(pos, BLOCK) else {
            out.warnings.push(format!("archive ends inside a header at {pos:#x}"));
            out.length = data.len() as u64;
            break;
        };
        if h.iter().all(|&b| b == 0) {
            // End of archive: one or two zero blocks.
            let second = r.slice(pos + BLOCK, BLOCK).is_some_and(|b| b.iter().all(|&x| x == 0));
            out.length = (pos + if second { 2 * BLOCK } else { BLOCK }) as u64;
            out.complete = true;
            break;
        }
        if !tar_header_ok(h) {
            out.warnings.push(format!("invalid header checksum at {pos:#x}; stopping"));
            out.length = pos as u64;
            break;
        }
        let typeflag = h.get(156).copied().unwrap_or(0);
        let Some(mut size) = h.get(124..136).and_then(octal) else {
            out.warnings.push(format!("unreadable size at {pos:#x}"));
            out.length = pos as u64;
            break;
        };
        if let Some(s) = pax_size.take()
            && !matches!(typeflag, b'x' | b'g' | b'L' | b'K')
        {
            size = s;
        }
        let data_off = pos + BLOCK;
        let Some(next) = round_up(size, BLOCK as u64).and_then(|s| u64::try_from(data_off).ok()?.checked_add(s)).and_then(|n| usize::try_from(n).ok()) else {
            out.warnings.push(format!("size overflows at {pos:#x}"));
            out.length = pos as u64;
            break;
        };
        let body = r.slice(data_off, usize::try_from(size).unwrap_or(usize::MAX));
        match typeflag {
            b'L' | b'K' => {
                let v = body.map(|b| text(b.get(..MAX_NAME.min(b.len())).unwrap_or(&[])));
                if typeflag == b'L' {
                    long_name = v;
                } else {
                    long_link = v;
                }
            }
            b'x' => {
                if let Some(b) = body {
                    for (k, v) in pax_records(b) {
                        match k.as_str() {
                            "path" => pax_path = Some(v),
                            "linkpath" => pax_link = Some(v),
                            "size" => pax_size = v.parse().ok(),
                            _ => {}
                        }
                    }
                }
            }
            b'g' => {}
            _ => {
                let ustar = h.get(257..262) == Some(b"ustar");
                let base = text(h.get(0..100).unwrap_or(&[]));
                let prefix = if ustar { text(h.get(345..500).unwrap_or(&[])) } else { String::new() };
                let joined = if prefix.is_empty() { base } else { format!("{prefix}/{base}") };
                let name = pax_path.take().or(long_name.take()).unwrap_or(joined);
                let link = pax_link.take().or(long_link.take()).or_else(|| Some(text(h.get(157..257).unwrap_or(&[])))).filter(|l| !l.is_empty());
                let kind = match typeflag {
                    b'0' | 0 | b'7' => {
                        if name.ends_with('/') {
                            MemberKind::Dir
                        } else {
                            MemberKind::File
                        }
                    }
                    b'1' => MemberKind::Hardlink,
                    b'2' => MemberKind::Symlink,
                    b'3' | b'4' => MemberKind::Device,
                    b'5' => MemberKind::Dir,
                    b'6' => MemberKind::Fifo,
                    _ => MemberKind::Other,
                };
                let mode = h.get(100..108).and_then(octal).and_then(|m| u32::try_from(m).ok()).unwrap_or(0);
                if body.is_none() && kind == MemberKind::File {
                    out.warnings.push(format!("{name}: data runs past the end of the input"));
                }
                if out.members.len() >= max_members {
                    out.truncated = true;
                    out.length = pos as u64;
                    break;
                }
                out.members.push(Member {
                    name,
                    kind,
                    size,
                    data_offset: data_off as u64,
                    link_target: if matches!(kind, MemberKind::Symlink | MemberKind::Hardlink) { link } else { None },
                    mode,
                });
            }
        }
        if next > data.len() {
            out.length = data.len() as u64;
            out.warnings.push("archive ends early (no end-of-archive marker)".into());
            break;
        }
        pos = next;
    }
    Some(out)
}

/// Parse pax extended header records (`<len> <key>=<value>\n`).
fn pax_records(b: &[u8]) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let mut i = 0usize;
    while i < b.len() && out.len() < 256 {
        let rest = b.get(i..).unwrap_or(&[]);
        let Some(sp) = rest.iter().position(|&c| c == b' ') else { break };
        let Some(len) = std::str::from_utf8(rest.get(..sp).unwrap_or(&[])).ok().and_then(|s| s.parse::<usize>().ok()) else { break };
        if len <= sp + 1 {
            break;
        }
        let Some(rec) = rest.get(sp + 1..len) else { break };
        let rec = rec.strip_suffix(b"\n").unwrap_or(rec);
        if let Some(eq) = rec.iter().position(|&c| c == b'=') {
            let k = String::from_utf8_lossy(rec.get(..eq).unwrap_or(&[])).into_owned();
            let v = String::from_utf8_lossy(rec.get(eq + 1..).unwrap_or(&[])).into_owned();
            out.push((k, v));
        }
        i += len;
    }
    out
}

fn hex_field(f: &[u8]) -> Option<u64> {
    let s = std::str::from_utf8(f).ok()?;
    u64::from_str_radix(s, 16).ok()
}

fn oct_field(f: &[u8]) -> Option<u64> {
    let s = std::str::from_utf8(f).ok()?;
    u64::from_str_radix(s, 8).ok()
}

fn mode_kind(mode: u32) -> MemberKind {
    match mode & 0o170_000 {
        0o100_000 => MemberKind::File,
        0o040_000 => MemberKind::Dir,
        0o120_000 => MemberKind::Symlink,
        0o020_000 | 0o060_000 => MemberKind::Device,
        0o010_000 => MemberKind::Fifo,
        _ => MemberKind::Other,
    }
}

/// Walk a cpio archive (newc `070701`, crc `070702`, odc `070707`). `None` when the first header
/// is not one of these.
pub fn cpio(data: &[u8], max_members: usize) -> Option<Listing> {
    let r = Reader::new(data);
    let format = match r.slice(0, 6)? {
        b"070701" => "cpio-newc",
        b"070702" => "cpio-crc",
        b"070707" => "cpio-odc",
        _ => return None,
    };
    let odc = format == "cpio-odc";
    let mut out = Listing { format, ..Listing::default() };
    let mut pos = 0usize;
    let align = |v: usize| if odc { Some(v) } else { v.checked_add(3).map(|x| x & !3) };
    loop {
        let hdr_len = if odc { 76 } else { 110 };
        let Some(h) = r.slice(pos, hdr_len) else {
            out.warnings.push(format!("archive ends inside a header at {pos:#x}"));
            out.length = data.len() as u64;
            break;
        };
        if h.get(..6) != r.slice(0, 6) {
            out.warnings.push(format!("bad header magic at {pos:#x}; stopping"));
            out.length = pos as u64;
            break;
        }
        let fields = if odc {
            (h.get(18..24).and_then(oct_field), h.get(59..65).and_then(oct_field), h.get(65..76).and_then(oct_field))
        } else {
            (h.get(14..22).and_then(hex_field), h.get(94..102).and_then(hex_field), h.get(54..62).and_then(hex_field))
        };
        let (Some(mode), Some(namesize), Some(filesize)) = fields else {
            out.warnings.push(format!("unreadable header fields at {pos:#x}"));
            out.length = pos as u64;
            break;
        };
        let namesize = usize::try_from(namesize).unwrap_or(usize::MAX);
        if namesize == 0 || namesize > MAX_NAME {
            out.warnings.push(format!("implausible name size at {pos:#x}"));
            out.length = pos as u64;
            break;
        }
        let Some(name_bytes) = r.slice(pos + hdr_len, namesize) else {
            out.warnings.push(format!("name runs past the end at {pos:#x}"));
            out.length = data.len() as u64;
            break;
        };
        let name = text(name_bytes);
        let Some(data_off) = (pos + hdr_len).checked_add(namesize).and_then(align) else { break };
        let size = usize::try_from(filesize).unwrap_or(usize::MAX);
        let Some(next) = data_off.checked_add(size).and_then(align) else {
            out.warnings.push(format!("size overflows at {pos:#x}"));
            out.length = pos as u64;
            break;
        };
        if name == "TRAILER!!!" {
            out.length = next.min(data.len()) as u64;
            out.complete = true;
            break;
        }
        let mode = u32::try_from(mode).unwrap_or(0);
        let kind = mode_kind(mode);
        let link_target = if kind == MemberKind::Symlink { r.slice(data_off, size.min(MAX_NAME)).map(text) } else { None };
        if out.members.len() >= max_members {
            out.truncated = true;
            out.length = pos as u64;
            break;
        }
        out.members.push(Member { name, kind, size: filesize, data_offset: data_off as u64, link_target, mode });
        if next > data.len() {
            out.warnings.push("archive ends early (no trailer)".into());
            out.length = data.len() as u64;
            break;
        }
        pos = next;
    }
    Some(out)
}

/// The data of a member, when it lies inside `data`.
pub fn member_data<'a>(data: &'a [u8], m: &Member) -> Option<&'a [u8]> {
    Reader::new(data).slice(usize::try_from(m.data_offset).ok()?, usize::try_from(m.size).ok()?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::firmware as fx;

    #[test]
    fn walks_tar() {
        let t = fx::tar(&[("etc/passwd", b"root:x:0:0\n"), ("bin/", b""), ("long/".repeat(30).as_str(), b"deep")]);
        let l = tar(&t, 100).unwrap();
        assert!(l.complete, "{:?}", l.warnings);
        assert_eq!(l.members.len(), 3);
        assert_eq!(l.members[0].name, "etc/passwd");
        assert_eq!(member_data(&t, &l.members[0]).unwrap(), b"root:x:0:0\n");
        assert_eq!(l.members[1].kind, MemberKind::Dir);
        assert!(l.members[2].name.starts_with("long/long/"));
        assert_eq!(l.length, t.len() as u64);
        let l2 = tar(&t, 1).unwrap();
        assert!(l2.truncated);
        assert_eq!(l2.members.len(), 1);
    }

    #[test]
    fn walks_cpio() {
        let c = fx::cpio_newc(&[("init", b"#!/bin/sh\n", 0o100755), ("dev", b"", 0o040755), ("sh", b"busybox", 0o120777)]);
        let l = cpio(&c, 100).unwrap();
        assert!(l.complete);
        assert_eq!(l.members.len(), 3);
        assert_eq!(member_data(&c, &l.members[0]).unwrap(), b"#!/bin/sh\n");
        assert_eq!(l.members[2].kind, MemberKind::Symlink);
        assert_eq!(l.members[2].link_target.as_deref(), Some("busybox"));
        assert_eq!(l.length, c.len() as u64);
    }

    #[test]
    fn octal_fields() {
        assert_eq!(octal(b"0000644 \0"), Some(0o644));
        assert_eq!(octal(b"  \0"), Some(0));
        assert_eq!(octal(b"9"), None);
        assert_eq!(octal(&[0x80, 0, 0, 1, 0]), Some(256));
        assert_eq!(octal(&[0xff; 12]), None);
    }

    #[test]
    fn hostile_archives_do_not_panic() {
        let t = fx::tar(&[("a", b"hello"), ("b/c", b"world")]);
        let c = fx::cpio_newc(&[("a", b"hello", 0o100644)]);
        for s in [&t, &c] {
            for m in craft_anything_testkit::mutations(s) {
                let _ = tar(&m, 10);
                let _ = cpio(&m, 10);
            }
            for n in 0..s.len().min(800) {
                let _ = tar(&s[..n], 10);
                let _ = cpio(&s[..n], 10);
            }
        }
        for seed in 0..50 {
            let n = craft_anything_testkit::noise(seed, 2048);
            let _ = tar(&n, 10);
            let _ = cpio(&n, 10);
        }
        assert!(pax_records(b"12 path=abc\n").len() == 1);
        assert!(pax_records(b"9999999999999999999999 x").is_empty());
    }
}
