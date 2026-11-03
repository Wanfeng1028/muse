//! Turning game textures' stored pixels into RGBA: uncompressed layouts and the 4×4 block formats
//! (DXT1/BC1, DXT5/BC3, BC4, BC5, BC6H and BC7). Shared by the Unity and Unreal readers; rows come out in the
//! order they're stored (Unity stores the bottom row first, Unreal the top).

use crate::bptc;
use crate::common::FormatError;

/// How a texture's pixels are laid out.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Layout {
    /// Alpha only (shown as white with that alpha).
    Alpha8,
    /// One grey channel.
    R8,
    Rgb24,
    Rgba32,
    Argb32,
    Bgra32,
    Rgb565,
    Rgba4444,
    Argb4444,
    Dxt1,
    Dxt5,
    /// One channel in blocks (shown as grey).
    Bc4,
    /// Two channels in blocks, usually a normal map (blue is rebuilt from red and green).
    Bc5,
    /// High dynamic range RGB in blocks (unsigned half floats), tone-mapped to 8-bit sRGB.
    Bc6h,
    /// BC6H with signed half floats.
    Bc6hSigned,
    Bc7,
}

/// Bytes of a `width`×`height` picture in `layout`.
pub fn size(layout: Layout, width: u32, height: u32) -> Option<usize> {
    let (w, h) = (width as usize, height as usize);
    let blocks = w.div_ceil(4).checked_mul(h.div_ceil(4))?;
    match layout {
        Layout::Alpha8 | Layout::R8 => w.checked_mul(h),
        Layout::Rgb565 | Layout::Rgba4444 | Layout::Argb4444 => w.checked_mul(h)?.checked_mul(2),
        Layout::Rgb24 => w.checked_mul(h)?.checked_mul(3),
        Layout::Rgba32 | Layout::Argb32 | Layout::Bgra32 => w.checked_mul(h)?.checked_mul(4),
        Layout::Dxt1 | Layout::Bc4 => blocks.checked_mul(8),
        Layout::Dxt5 | Layout::Bc5 | Layout::Bc6h | Layout::Bc6hSigned | Layout::Bc7 => blocks.checked_mul(16),
    }
}

fn expand5(v: u16) -> u8 {
    let v = (v & 31) as u8;
    (v << 3) | (v >> 2)
}

fn expand6(v: u16) -> u8 {
    let v = (v & 63) as u8;
    (v << 2) | (v >> 4)
}

fn rgb565(v: u16) -> [u8; 4] {
    [expand5(v >> 11), expand6(v >> 5), expand5(v), 255]
}

fn nibbles(v: u16, order: [u32; 4]) -> [u8; 4] {
    order.map(|shift| ((v >> shift) & 15) as u8 * 17)
}

/// The four colours of a DXT colour block; `punch` allows the transparent fourth (DXT1 only).
fn dxt_colours(b: &[u8; 8], punch: bool) -> [[u8; 4]; 4] {
    let (c0, c1) = (u16::from_le_bytes([b[0], b[1]]), u16::from_le_bytes([b[2], b[3]]));
    let (p, q) = (rgb565(c0), rgb565(c1));
    let mix = |a: u8, b: u8, wa: u16, wb: u16| ((u16::from(a) * wa + u16::from(b) * wb) / (wa + wb)) as u8;
    let blend = |wa: u16, wb: u16| [mix(p[0], q[0], wa, wb), mix(p[1], q[1], wa, wb), mix(p[2], q[2], wa, wb), 255];
    if c0 > c1 || !punch { [p, q, blend(2, 1), blend(1, 2)] } else { [p, q, blend(1, 1), [0, 0, 0, 0]] }
}

/// The 16 texels of a DXT colour block, row by row.
fn dxt_texels(b: &[u8; 8], punch: bool) -> [[u8; 4]; 16] {
    let colours = dxt_colours(b, punch);
    let bits = u32::from_le_bytes([b[4], b[5], b[6], b[7]]);
    std::array::from_fn(|k| colours[((bits >> (2 * k)) & 3) as usize])
}

/// The 16 values of an 8-byte single-channel block (DXT5's alpha, BC4, each half of BC5).
fn channel_block(b: &[u8; 8]) -> [u8; 16] {
    let (a0, a1) = (u16::from(b[0]), u16::from(b[1]));
    let values: [u8; 8] = if a0 > a1 {
        std::array::from_fn(|i| match i {
            0 => a0 as u8,
            1 => a1 as u8,
            i => (((8 - i as u16) * a0 + (i as u16 - 1) * a1) / 7) as u8,
        })
    } else {
        std::array::from_fn(|i| match i {
            0 => a0 as u8,
            1 => a1 as u8,
            6 => 0,
            7 => 255,
            i => (((6 - i as u16) * a0 + (i as u16 - 1) * a1) / 5) as u8,
        })
    };
    let bits = b.iter().skip(2).rev().fold(0u64, |n, x| (n << 8) | u64::from(*x));
    std::array::from_fn(|k| values[((bits >> (3 * k)) & 7) as usize])
}

fn halves(b: &[u8; 16]) -> ([u8; 8], [u8; 8]) {
    let mut first = [0u8; 8];
    let mut second = [0u8; 8];
    for (i, x) in b.iter().enumerate() {
        if i < 8 {
            first[i] = *x;
        } else {
            second[i - 8] = *x;
        }
    }
    (first, second)
}

fn dxt5(b: &[u8; 16]) -> [[u8; 4]; 16] {
    let (alpha, colour) = halves(b);
    let mut texels = dxt_texels(&colour, false);
    for (t, a) in texels.iter_mut().zip(channel_block(&alpha)) {
        t[3] = a;
    }
    texels
}

fn bc4(b: &[u8; 8]) -> [[u8; 4]; 16] {
    channel_block(b).map(|r| [r, r, r, 255])
}

fn bc5(b: &[u8; 16]) -> [[u8; 4]; 16] {
    let (red, green) = halves(b);
    let (r, g) = (channel_block(&red), channel_block(&green));
    std::array::from_fn(|k| {
        // A unit normal's z from its x and y, each stored as 0..255 for -1..1.
        let (x, y) = (f32::from(r[k]) / 127.5 - 1.0, f32::from(g[k]) / 127.5 - 1.0);
        let z = (1.0 - x * x - y * y).max(0.0).sqrt();
        [r[k], g[k], ((z + 1.0) * 127.5) as u8, 255]
    })
}

/// Place 4×4 blocks (left to right, then row by row) into a `w`×`h` RGBA picture.
fn blocks(out: &mut [u8], w: usize, h: usize, texels: impl Iterator<Item = [[u8; 4]; 16]>) {
    let across = w.div_ceil(4);
    for (i, block) in texels.enumerate() {
        let (bx, by) = (i % across, i / across);
        for (k, p) in block.iter().enumerate() {
            let (x, y) = (bx * 4 + k % 4, by * 4 + k / 4);
            if x < w && y < h {
                let at = (y * w + x) * 4;
                if let Some(dst) = out.get_mut(at..at + 4) {
                    dst.copy_from_slice(p);
                }
            }
        }
    }
}

/// Decode a `width`×`height` picture (`data` starts with it) into RGBA, rows in stored order.
pub fn decode(layout: Layout, width: u32, height: u32, data: &[u8]) -> Result<Vec<u8>, FormatError> {
    let need = size(layout, width, height).ok_or_else(|| FormatError::TooLarge(format!("a {width}×{height} picture")))?;
    let data = data.get(..need).ok_or_else(|| FormatError::Truncated(format!("{} bytes of pixels, {need} needed", data.len())))?;
    let (w, h) = (width as usize, height as usize);
    if w == 0 || h == 0 {
        return Err(FormatError::Malformed("an empty picture".into()));
    }
    let mut out = vec![0u8; w * h * 4];
    let mut put = |px: &mut dyn Iterator<Item = [u8; 4]>| {
        for (dst, p) in out.as_chunks_mut::<4>().0.iter_mut().zip(px) {
            *dst = p;
        }
    };
    let u16s = |d: &[u8]| -> Vec<u16> { d.as_chunks::<2>().0.iter().map(|b| u16::from_le_bytes(*b)).collect() };
    match layout {
        Layout::Alpha8 => put(&mut data.iter().map(|a| [255, 255, 255, *a])),
        Layout::R8 => put(&mut data.iter().map(|r| [*r, *r, *r, 255])),
        Layout::Rgb24 => put(&mut data.as_chunks::<3>().0.iter().map(|[r, g, b]| [*r, *g, *b, 255])),
        Layout::Rgba32 => put(&mut data.as_chunks::<4>().0.iter().copied()),
        Layout::Argb32 => put(&mut data.as_chunks::<4>().0.iter().map(|[a, r, g, b]| [*r, *g, *b, *a])),
        Layout::Bgra32 => put(&mut data.as_chunks::<4>().0.iter().map(|[b, g, r, a]| [*r, *g, *b, *a])),
        Layout::Rgb565 => put(&mut u16s(data).into_iter().map(rgb565)),
        Layout::Rgba4444 => put(&mut u16s(data).into_iter().map(|v| nibbles(v, [12, 8, 4, 0]))),
        Layout::Argb4444 => put(&mut u16s(data).into_iter().map(|v| nibbles(v, [8, 4, 0, 12]))),
        Layout::Dxt1 => blocks(&mut out, w, h, data.as_chunks::<8>().0.iter().map(|b| dxt_texels(b, true))),
        Layout::Dxt5 => blocks(&mut out, w, h, data.as_chunks::<16>().0.iter().map(dxt5)),
        Layout::Bc4 => blocks(&mut out, w, h, data.as_chunks::<8>().0.iter().map(bc4)),
        Layout::Bc5 => blocks(&mut out, w, h, data.as_chunks::<16>().0.iter().map(bc5)),
        Layout::Bc6h => blocks(&mut out, w, h, data.as_chunks::<16>().0.iter().map(|b| bptc::bc6h(b, false))),
        Layout::Bc6hSigned => blocks(&mut out, w, h, data.as_chunks::<16>().0.iter().map(|b| bptc::bc6h(b, true))),
        Layout::Bc7 => blocks(&mut out, w, h, data.as_chunks::<16>().0.iter().map(bptc::bc7)),
    }
    Ok(out)
}

/// Flip a `width`-wide RGBA picture upside down (Unity stores the bottom row first).
pub fn flip_rows(rgba: &[u8], width: u32) -> Vec<u8> {
    let row = (width as usize).saturating_mul(4).max(1);
    rgba.chunks(row).rev().flatten().copied().collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn uncompressed_layouts() {
        assert_eq!(decode(Layout::Rgba32, 1, 2, &[1, 2, 3, 4, 5, 6, 7, 8]).unwrap(), [1, 2, 3, 4, 5, 6, 7, 8], "stored order");
        assert_eq!(decode(Layout::Argb32, 1, 1, &[9, 1, 2, 3]).unwrap(), [1, 2, 3, 9]);
        assert_eq!(decode(Layout::Bgra32, 1, 1, &[3, 2, 1, 9]).unwrap(), [1, 2, 3, 9]);
        assert_eq!(decode(Layout::Rgb24, 1, 1, &[1, 2, 3]).unwrap(), [1, 2, 3, 255]);
        assert_eq!(decode(Layout::Alpha8, 1, 1, &[7]).unwrap(), [255, 255, 255, 7]);
        assert_eq!(decode(Layout::R8, 1, 1, &[7]).unwrap(), [7, 7, 7, 255]);
        assert_eq!(decode(Layout::Rgb565, 1, 1, &0xf800u16.to_le_bytes()).unwrap(), [255, 0, 0, 255]);
        assert_eq!(decode(Layout::Rgba4444, 1, 1, &0xf00fu16.to_le_bytes()).unwrap(), [255, 0, 0, 255]);
        assert_eq!(decode(Layout::Argb4444, 1, 1, &0xff00u16.to_le_bytes()).unwrap(), [255, 0, 0, 255]);
        assert_eq!(flip_rows(&[1, 1, 1, 1, 2, 2, 2, 2], 1), [2, 2, 2, 2, 1, 1, 1, 1]);
        assert!(matches!(decode(Layout::Rgba32, 2, 2, &[0; 15]), Err(FormatError::Truncated(_))));
        assert!(decode(Layout::Rgba32, 0, 1, &[]).is_err());
    }

    #[test]
    fn block_layouts() {
        // DXT1: colour 0 red, colour 1 blue; the first texel uses index 1, the rest index 0.
        let px = decode(Layout::Dxt1, 4, 4, &[0x00, 0xf8, 0x1f, 0x00, 0b01, 0, 0, 0]).unwrap();
        assert_eq!((&px[..4], &px[4..8]), (&[0, 0, 255, 255][..], &[255, 0, 0, 255][..]));
        // DXT5: alpha 255 → 0; the first texel index 1 (alpha 0), the rest index 0 (255).
        let mut b = vec![255, 0, 1, 0, 0, 0, 0, 0];
        b.extend_from_slice(&[0x00, 0xf8, 0x1f, 0x00, 0, 0, 0, 0]);
        let px = decode(Layout::Dxt5, 4, 4, &b).unwrap();
        assert_eq!((px[3], px[7]), (0, 255));
        // BC4: grey from one channel block; BC5: red and green, blue rebuilt (flat normal → 255).
        assert_eq!(&decode(Layout::Bc4, 4, 4, &[200, 10, 0, 0, 0, 0, 0, 0]).unwrap()[..4], &[200, 200, 200, 255]);
        let mut n = vec![128, 128, 0, 0, 0, 0, 0, 0];
        n.extend_from_slice(&[128, 128, 0, 0, 0, 0, 0, 0]);
        assert_eq!(&decode(Layout::Bc5, 4, 4, &n).unwrap()[..4], &[128, 128, 254, 255]);
        // 5×5 needs 4 blocks and is cropped.
        assert_eq!(decode(Layout::Dxt1, 5, 5, &[0; 32]).unwrap().len(), 5 * 5 * 4);
    }
}
