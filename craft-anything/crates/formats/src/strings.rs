//! Printable string extraction (ASCII/UTF-8 and UTF-16LE), bounded.

use serde::Serialize;

/// Longest string we keep (longer runs are cut and flagged).
pub const MAX_STRING_CHARS: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Encoding {
    Ascii,
    Utf8,
    Utf16le,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FoundString {
    /// Offset of the first byte, relative to the start of the scanned slice plus `base`.
    pub offset: u64,
    /// Length in bytes in the file.
    pub byte_len: u64,
    pub encoding: Encoding,
    pub text: String,
    pub truncated: bool,
}

fn printable(b: u8) -> bool {
    (0x20..0x7f).contains(&b) || b == b'\t' || b == b'\n' || b == b'\r'
}

/// Length of a valid multi-byte UTF-8 sequence starting at `i`, if any (2–4 bytes, non-control).
fn utf8_seq(data: &[u8], i: usize) -> Option<usize> {
    let b0 = *data.get(i)?;
    let n = match b0 {
        0xc2..=0xdf => 2,
        0xe0..=0xef => 3,
        0xf0..=0xf4 => 4,
        _ => return None,
    };
    let s = data.get(i..i + n)?;
    let ch = std::str::from_utf8(s).ok()?.chars().next()?;
    if ch.is_control() { None } else { Some(n) }
}

/// Extract strings of at least `min_len` characters. Offsets are `base + position`.
/// Stops after `max_count` strings.
pub fn extract(data: &[u8], base: u64, min_len: usize, max_count: usize) -> Vec<FoundString> {
    let min_len = min_len.max(2);
    let mut out = Vec::new();
    // Pass 1: ASCII / UTF-8 runs.
    let mut i = 0usize;
    while i < data.len() && out.len() < max_count {
        let start = i;
        let mut chars = 0usize;
        let mut multibyte = false;
        loop {
            match data.get(i) {
                Some(&b) if printable(b) => {
                    i += 1;
                    chars += 1;
                }
                Some(_) => match utf8_seq(data, i) {
                    Some(n) => {
                        i += n;
                        chars += 1;
                        multibyte = true;
                    }
                    None => break,
                },
                None => break,
            }
        }
        if chars >= min_len {
            push(&mut out, data, base, start, i, if multibyte { Encoding::Utf8 } else { Encoding::Ascii });
        }
        if i == start {
            i += 1;
        }
    }
    // Pass 2: UTF-16LE runs of ASCII-range characters (Windows resources and wide literals).
    let mut i = 0usize;
    while i + 1 < data.len() && out.len() < max_count {
        let run_start = i;
        let start = i;
        let mut chars = 0usize;
        while let (Some(&lo), Some(&hi)) = (data.get(i), data.get(i + 1)) {
            if hi == 0 && printable(lo) {
                chars += 1;
                i += 2;
            } else {
                break;
            }
        }
        // A unit right after printable ASCII is that string's last byte plus its NUL, not text.
        let mut start = start;
        if chars > 0 && start > 0 && data.get(start - 1).is_some_and(|&b| printable(b)) {
            start += 2;
            chars -= 1;
        }
        if chars >= min_len {
            let units: Vec<u16> = data.get(start..i).unwrap_or(&[]).as_chunks::<2>().0.iter().map(|c| u16::from_le_bytes(*c)).take(MAX_STRING_CHARS).collect();
            out.push(FoundString {
                offset: base + start as u64,
                byte_len: (i - start) as u64,
                encoding: Encoding::Utf16le,
                text: String::from_utf16_lossy(&units),
                truncated: chars > MAX_STRING_CHARS,
            });
            continue;
        }
        i = if i == run_start { run_start + 1 } else { i };
    }
    out.sort_by_key(|s| s.offset);
    out
}

fn push(out: &mut Vec<FoundString>, data: &[u8], base: u64, start: usize, end: usize, encoding: Encoding) {
    let bytes = data.get(start..end).unwrap_or(&[]);
    let text = String::from_utf8_lossy(bytes);
    let truncated = text.chars().count() > MAX_STRING_CHARS;
    let text: String = if truncated { text.chars().take(MAX_STRING_CHARS).collect() } else { text.into_owned() };
    out.push(FoundString { offset: base + start as u64, byte_len: (end - start) as u64, encoding, text, truncated });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_ascii_utf8_and_utf16() {
        let mut d = b"\x00\x01Hello, Craft!\x00ab\x00caf\xc3\xa9 ok\x00".to_vec();
        for c in "Wide text".encode_utf16() {
            d.extend_from_slice(&c.to_le_bytes());
        }
        d.extend_from_slice(&[0, 0]);
        let s = extract(&d, 0x1000, 4, 100);
        let texts: Vec<&str> = s.iter().map(|s| s.text.as_str()).collect();
        assert!(texts.contains(&"Hello, Craft!"), "{texts:?}");
        assert!(texts.contains(&"café ok"));
        assert!(texts.contains(&"Wide text"));
        assert!(!texts.contains(&"ab"));
        assert_eq!(s.iter().find(|s| s.text == "Hello, Craft!").unwrap().offset, 0x1002);
    }

    #[test]
    fn caps_hold() {
        let d = vec![b'a'; 10_000];
        let s = extract(&d, 0, 4, 10);
        assert_eq!(s.len(), 1);
        assert!(s[0].truncated);
        assert_eq!(extract(&craft_anything_testkit::noise(3, 5000), 0, 4, 3).len().min(3), extract(&craft_anything_testkit::noise(3, 5000), 0, 4, 3).len());
    }
}
