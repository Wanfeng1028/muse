//! Bounded, pure-Rust decompressors for the stream formats a firmware image commonly carries:
//! xz, standalone LZMA (`.lzma`), bzip2 and Zstandard. Each decoder caps its output at `max_out`
//! bytes (returning `TooLarge` rather than allocating without limit) and never panics on a corrupt
//! or truncated stream. gzip/zlib/zip live in `firmware`; these complete the set.
//!
//! All three backing crates (`lzma-rs`, `bzip2-rs`, `ruzstd`) are pure Rust and build for
//! `wasm32-unknown-unknown`.

use std::io::{self, Read, Write};

/// Why a decode stopped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum DecompressError {
    #[error("the compressed stream is damaged")]
    Corrupt,
    #[error("the compressed stream ends early")]
    Truncated,
    #[error("the output would exceed the size limit")]
    TooLarge,
}

/// A `Write` sink that collects at most `cap` bytes, then refuses the rest. The `exceeded` flag lets
/// the caller tell a size-limit stop from a genuine decode error.
struct CapWrite {
    buf: Vec<u8>,
    cap: usize,
    exceeded: bool,
}

impl CapWrite {
    fn new(cap: usize) -> Self {
        CapWrite { buf: Vec::new(), cap, exceeded: false }
    }
}

impl Write for CapWrite {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        if self.buf.len().saturating_add(data.len()) > self.cap {
            self.exceeded = true;
            return Err(io::Error::other("output size limit reached"));
        }
        self.buf.extend_from_slice(data);
        Ok(data.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn cap_of(max_out: u64) -> usize {
    usize::try_from(max_out).unwrap_or(usize::MAX)
}

/// Read a `Read` source into a `Vec`, capped at `cap` bytes.
fn read_capped(mut src: impl Read, cap: usize) -> Result<Vec<u8>, DecompressError> {
    let mut out = Vec::new();
    let mut chunk = [0u8; 64 * 1024];
    loop {
        match src.read(&mut chunk) {
            Ok(0) => return Ok(out),
            Ok(n) => {
                let slice = chunk.get(..n).unwrap_or(&[]);
                if out.len().saturating_add(slice.len()) > cap {
                    return Err(DecompressError::TooLarge);
                }
                out.extend_from_slice(slice);
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => return Err(DecompressError::Corrupt),
        }
    }
}

/// Decompress an xz stream, producing at most `max_out` bytes.
pub fn xz(input: &[u8], max_out: u64) -> Result<Vec<u8>, DecompressError> {
    let mut out = CapWrite::new(cap_of(max_out));
    let mut cursor = io::Cursor::new(input);
    match lzma_rs::xz_decompress(&mut cursor, &mut out) {
        Ok(()) => Ok(out.buf),
        Err(_) if out.exceeded => Err(DecompressError::TooLarge),
        Err(lzma_rs::error::Error::HeaderTooShort(_)) => Err(DecompressError::Truncated),
        Err(_) => Err(DecompressError::Corrupt),
    }
}

/// Decompress a standalone LZMA (`.lzma`, `0x5d` props) stream, producing at most `max_out` bytes.
pub fn lzma(input: &[u8], max_out: u64) -> Result<Vec<u8>, DecompressError> {
    let mut out = CapWrite::new(cap_of(max_out));
    let mut cursor = io::Cursor::new(input);
    match lzma_rs::lzma_decompress(&mut cursor, &mut out) {
        Ok(()) => Ok(out.buf),
        Err(_) if out.exceeded => Err(DecompressError::TooLarge),
        Err(lzma_rs::error::Error::HeaderTooShort(_)) => Err(DecompressError::Truncated),
        Err(_) => Err(DecompressError::Corrupt),
    }
}

/// Decompress a bzip2 stream, producing at most `max_out` bytes.
pub fn bzip2(input: &[u8], max_out: u64) -> Result<Vec<u8>, DecompressError> {
    read_capped(bzip2_rs::DecoderReader::new(input), cap_of(max_out))
}

/// Decompress a Zstandard stream, producing at most `max_out` bytes.
pub fn zstd(input: &[u8], max_out: u64) -> Result<Vec<u8>, DecompressError> {
    let decoder = ruzstd::decoding::StreamingDecoder::new(input).map_err(|_| DecompressError::Corrupt)?;
    read_capped(decoder, cap_of(max_out))
}

/// Decompress one raw LZ4 block (no frame) that inflates to exactly `out_len` bytes, as Unity
/// bundles store them.
pub fn lz4_block(input: &[u8], out_len: usize) -> Result<Vec<u8>, DecompressError> {
    let mut out = Vec::with_capacity(out_len.min(64 << 20));
    let mut i = 0usize;
    let byte = |i: &mut usize| -> Result<u8, DecompressError> {
        let b = *input.get(*i).ok_or(DecompressError::Truncated)?;
        *i += 1;
        Ok(b)
    };
    // A 4-bit length of 15 continues in the following bytes, 255 at a time.
    let length = |i: &mut usize, base: u8| -> Result<usize, DecompressError> {
        let mut n = usize::from(base);
        if base == 15 {
            loop {
                let b = byte(i)?;
                n = n.checked_add(usize::from(b)).ok_or(DecompressError::Corrupt)?;
                if b != 255 {
                    break;
                }
            }
        }
        Ok(n)
    };
    while i < input.len() {
        let token = byte(&mut i)?;
        let literals = length(&mut i, token >> 4)?;
        let end = i.checked_add(literals).ok_or(DecompressError::Corrupt)?;
        let run = input.get(i..end).ok_or(DecompressError::Truncated)?;
        if out.len() + literals > out_len {
            return Err(DecompressError::TooLarge);
        }
        out.extend_from_slice(run);
        i = end;
        // The last sequence has literals only.
        if i >= input.len() {
            break;
        }
        let offset = usize::from(u16::from_le_bytes([byte(&mut i)?, byte(&mut i)?]));
        if offset == 0 || offset > out.len() {
            return Err(DecompressError::Corrupt);
        }
        let len = length(&mut i, token & 15)?.checked_add(4).ok_or(DecompressError::Corrupt)?;
        if out.len() + len > out_len {
            return Err(DecompressError::TooLarge);
        }
        // The match may overlap what it writes, so it's copied a byte at a time.
        let start = out.len() - offset;
        for k in 0..len {
            let b = out[start + k];
            out.push(b);
        }
    }
    if out.len() != out_len {
        return Err(DecompressError::Truncated);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::firmware as fx;

    #[test]
    fn lz4_blocks_with_literals_and_overlapping_matches() {
        // "abcabcabcabc!": 3 literals, a 9-byte match 3 back (overlapping), then "!".
        let block = [0x35, b'a', b'b', b'c', 3, 0, 0x10, b'!'];
        assert_eq!(lz4_block(&block, 13).unwrap(), b"abcabcabcabc!");
        // A long literal run uses the extra length bytes.
        let mut long = vec![0xf0, 5]; // 15 + 5 = 20 literals
        long.extend_from_slice(&[b'x'; 20]);
        assert_eq!(lz4_block(&long, 20).unwrap(), [b'x'; 20]);
        assert_eq!(lz4_block(&block, 12), Err(DecompressError::TooLarge));
        assert_eq!(lz4_block(&block, 14), Err(DecompressError::Truncated));
        assert_eq!(lz4_block(&[0x10, b'a', 9, 0], 10), Err(DecompressError::Corrupt), "a match before the start");
        for n in 0..64u8 {
            let junk: Vec<u8> = (0..n).map(|k| k.wrapping_mul(37).wrapping_add(n)).collect();
            let _ = lz4_block(&junk, 100);
        }
    }

    #[test]
    fn xz_round_trip() {
        let c = fx::XZ_FIXTURE;
        assert_eq!(xz(c, 1 << 20).unwrap(), fx::XZ_PLAIN);
        // A tiny cap reports TooLarge, never a partial lie.
        assert_eq!(xz(c, 4), Err(DecompressError::TooLarge));
        // Truncation never panics.
        for len in 0..c.len() {
            let _ = xz(&c[..len], 1 << 20);
        }
    }

    #[test]
    fn lzma_round_trip() {
        let c = fx::LZMA_FIXTURE;
        assert_eq!(lzma(c, 1 << 20).unwrap(), fx::LZMA_PLAIN);
        assert_eq!(lzma(c, 4), Err(DecompressError::TooLarge));
        for len in 0..c.len() {
            let _ = lzma(&c[..len], 1 << 20);
        }
    }

    #[test]
    fn bzip2_round_trip() {
        let c = fx::BZIP2_FIXTURE;
        assert_eq!(bzip2(c, 1 << 20).unwrap(), fx::BZIP2_PLAIN);
        assert_eq!(bzip2(c, 2), Err(DecompressError::TooLarge));
        for len in 0..c.len() {
            let _ = bzip2(&c[..len], 1 << 20);
        }
    }

    #[test]
    fn zstd_round_trip() {
        let c = fx::ZSTD_FIXTURE;
        assert_eq!(zstd(c, 1 << 20).unwrap(), fx::ZSTD_PLAIN);
        assert_eq!(zstd(c, 2), Err(DecompressError::TooLarge));
        for len in 0..c.len() {
            let _ = zstd(&c[..len], 1 << 20);
        }
    }

    #[test]
    fn garbage_never_panics() {
        for seed in 0..64u64 {
            let n = craft_anything_testkit::noise(seed, 400);
            let _ = xz(&n, 1 << 20);
            let _ = lzma(&n, 1 << 20);
            let _ = bzip2(&n, 1 << 20);
            let _ = zstd(&n, 1 << 20);
        }
    }
}
