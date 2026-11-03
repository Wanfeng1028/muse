//! Shared pieces of the native-format parsers: the error type, hex address serialisation,
//! entropy and bounded byte search.

/// Why a parser gave up. Never a panic: every malformed input ends here.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum FormatError {
    #[error("the file ends early ({0})")]
    Truncated(String),
    #[error("the file is malformed ({0})")]
    Malformed(String),
    #[error("not supported: {0}")]
    Unsupported(String),
    #[error("too large: {0}")]
    TooLarge(String),
}

/// Serialise addresses as `0x…` strings (agents and people read hex).
pub mod hex_addr {
    use serde::Serializer;

    pub fn serialize<S: Serializer>(v: &u64, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&format!("{v:#x}"))
    }

    pub mod opt {
        use serde::Serializer;

        pub fn serialize<S: Serializer>(v: &Option<u64>, s: S) -> Result<S::Ok, S::Error> {
            match v {
                Some(v) => s.serialize_str(&format!("{v:#x}")),
                None => s.serialize_none(),
            }
        }
    }

    pub mod vec {
        use serde::Serializer;
        use serde::ser::SerializeSeq;

        pub fn serialize<S: Serializer>(v: &[u64], s: S) -> Result<S::Ok, S::Error> {
            let mut seq = s.serialize_seq(Some(v.len()))?;
            for a in v {
                seq.serialize_element(&format!("{a:#x}"))?;
            }
            seq.end()
        }
    }
}

/// Shannon entropy in bits per byte (0..=8); 0 for empty input.
pub fn entropy(data: &[u8]) -> f32 {
    if data.is_empty() {
        return 0.0;
    }
    let mut counts = [0u64; 256];
    for &b in data {
        if let Some(c) = counts.get_mut(usize::from(b)) {
            *c += 1;
        }
    }
    let n = data.len() as f64;
    let e: f64 = counts
        .iter()
        .filter(|&&c| c > 0)
        .map(|&c| {
            let p = c as f64 / n;
            -p * p.log2()
        })
        .sum();
    if e.is_finite() { e as f32 } else { 0.0 }
}

/// Find `needle` in `hay`, looking at no more than `limit` bytes of `hay`.
pub fn find_bytes(hay: &[u8], needle: &[u8], limit: usize) -> Option<usize> {
    let hay = hay.get(..limit.min(hay.len()))?;
    let (&first, rest) = needle.split_first()?;
    let mut i = 0usize;
    while let Some(p) = hay.get(i..).and_then(|h| h.iter().position(|&b| b == first)) {
        let at = i + p;
        if hay.get(at + 1..at + 1 + rest.len()) == Some(rest) {
            return Some(at);
        }
        i = at + 1;
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn entropy_and_search() {
        assert_eq!(entropy(&[]), 0.0);
        assert_eq!(entropy(&[7; 100]), 0.0);
        let all: Vec<u8> = (0..=255).collect();
        assert!((entropy(&all) - 8.0).abs() < 0.001);
        assert_eq!(find_bytes(b"abcabd", b"abd", 100), Some(3));
        assert_eq!(find_bytes(b"abcabd", b"abd", 4), None);
        assert_eq!(find_bytes(b"abc", b"", 10), None);
    }
}
