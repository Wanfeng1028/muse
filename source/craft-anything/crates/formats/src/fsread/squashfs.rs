//! A minimal read-only SquashFS v4.0 reader (little-endian), covering the common cases: gzip, xz,
//! zstd and lzma compression (and uncompressed blocks), basic and extended directory/file inodes,
//! data blocks and tail fragments. It walks the tree from the root inode and extracts regular files
//! and fast symlinks. Bounded against cycles, huge sizes and corrupt references.
//!
//! NOT handled (reported in warnings): lzo and lz4 compression, xattrs, and SquashFS versions other
//! than 4.0. These make affected files appear unrecovered rather than producing wrong bytes.

use super::{FsEntry, FsImage, FsKind, Limits, join};
use crate::bytes::Reader;
use std::collections::BTreeMap;

const META_MAX: usize = 8192;

struct Sb {
    block_size: u32,
    compression: u16,
    inode_table: u64,
    dir_table: u64,
    frag_table: u64,
    id_table: u64,
    root_ref: u64,
    frag_count: u32,
}

fn superblock(data: &[u8]) -> Option<Sb> {
    let r = Reader::new(data);
    if r.slice(0, 4) != Some(b"hsqs") || r.u16_le(28)? != 4 {
        return None;
    }
    let block_size = r.u32_le(12)?;
    let block_log = r.u16_le(22)?;
    if 1u32.checked_shl(u32::from(block_log)) != Some(block_size) || !(12..=20).contains(&block_log) {
        return None;
    }
    Some(Sb {
        block_size,
        compression: r.u16_le(20)?,
        frag_count: r.u32_le(16)?,
        root_ref: r.u64_le(32)?,
        inode_table: r.u64_le(64)?,
        dir_table: r.u64_le(72)?,
        frag_table: r.u64_le(80)?,
        id_table: r.u64_le(48)?,
    })
}

/// Decompress a metadata or data block with the superblock's compressor, capped at `max`.
fn decompress(comp: u16, block: &[u8], max: u64) -> Option<Vec<u8>> {
    match comp {
        1 => crate::firmware::inflate(block, true, max, true).ok().and_then(|i| i.data),
        2 => crate::decompress::lzma(block, max).ok(),
        4 => crate::decompress::xz(block, max).ok(),
        6 => crate::decompress::zstd(block, max).ok(),
        _ => None,
    }
}

/// A decompressed metadata region plus a map from each metadata block's start (relative to the
/// region start) to its position in the decompressed buffer.
struct Meta {
    data: Vec<u8>,
    map: BTreeMap<u32, usize>,
}

impl Meta {
    fn read(data: &[u8], start: u64, end: u64, comp: u16, warnings: &mut FsImage) -> Meta {
        let mut out = Vec::new();
        let mut map = BTreeMap::new();
        let (Ok(mut pos), Ok(end)) = (usize::try_from(start), usize::try_from(end)) else {
            return Meta { data: out, map };
        };
        let end = end.min(data.len());
        let mut guard = 0usize;
        while pos + 2 <= end {
            guard += 1;
            if guard > 100_000 || out.len() > 64 << 20 {
                break;
            }
            map.insert((pos as u64 - start) as u32, out.len());
            let r = Reader::new(data);
            let Some(hdr) = r.u16_le(pos) else { break };
            let uncompressed = hdr & 0x8000 != 0;
            let len = usize::from(hdr & 0x7fff);
            let Some(block) = data.get(pos + 2..pos + 2 + len) else { break };
            if uncompressed {
                out.extend_from_slice(block);
            } else if let Some(d) = decompress(comp, block, META_MAX as u64) {
                out.extend_from_slice(&d);
            } else {
                warnings.warn("squashfs: a metadata block did not decompress");
                warnings.complete = false;
                break;
            }
            pos += 2 + len;
        }
        Meta { data: out, map }
    }

    /// Resolve a metadata reference `(block_location << 16) | offset` to a decompressed position.
    fn at(&self, reference: u64) -> Option<usize> {
        let block = (reference >> 16) as u32;
        let off = (reference & 0xffff) as usize;
        self.map.get(&block).and_then(|&base| base.checked_add(off))
    }
}

pub fn read(data: &[u8], limits: &Limits) -> FsImage {
    let Some(sb) = superblock(data) else {
        let mut img = FsImage::new("squashfs");
        img.warn("not a SquashFS 4.0 image");
        img.complete = false;
        return img;
    };
    let mut img = FsImage::new("squashfs");
    if matches!(sb.compression, 3 | 5) {
        img.warn("squashfs uses lzo/lz4 compression, which is not supported");
        img.complete = false;
    }
    // Directory table ends at the first following table.
    let dir_end = [sb.frag_table, sb.id_table].into_iter().filter(|&t| t > sb.dir_table && t != u64::MAX).min().unwrap_or(sb.dir_table);
    let inodes = Meta::read(data, sb.inode_table, sb.dir_table, sb.compression, &mut img);
    let dirs = Meta::read(data, sb.dir_table, dir_end, sb.compression, &mut img);
    let mut seen: Vec<u64> = Vec::new();
    walk(data, &sb, &inodes, &dirs, sb.root_ref, "", limits, &mut img, 0, &mut seen);
    img
}

#[allow(clippy::too_many_arguments)]
fn walk(data: &[u8], sb: &Sb, inodes: &Meta, dirs: &Meta, inode_ref: u64, parent: &str, limits: &Limits, img: &mut FsImage, depth: usize, seen: &mut Vec<u64>) {
    if depth > limits.max_depth || img.entries.len() >= limits.max_entries {
        img.complete = false;
        return;
    }
    if seen.contains(&inode_ref) {
        return;
    }
    seen.push(inode_ref);
    let Some(pos) = inodes.at(inode_ref) else { return };
    let r = Reader::new(&inodes.data);
    let Some(itype) = r.u16_le(pos) else { return };
    // Directory inode (basic=1, extended=8).
    let (start_block, size, offset) = match itype {
        1 => (r.u32_le(pos + 16), r.u16_le(pos + 24).map(u32::from), r.u16_le(pos + 26)),
        8 => (r.u32_le(pos + 24), r.u32_le(pos + 20), r.u16_le(pos + 34)),
        _ => return,
    };
    let (Some(start_block), Some(size), Some(offset)) = (start_block, size, offset) else { return };
    // The directory listing lives at (start_block, offset) in the directory table, `size`-3 bytes.
    let Some(dstart) = dirs.at((u64::from(start_block) << 16) | u64::from(offset)) else { return };
    let listing_len = size.saturating_sub(3) as usize;
    let Some(end) = dstart.checked_add(listing_len) else { return };
    let listing = dirs.data.get(dstart..end.min(dirs.data.len())).unwrap_or(&[]);
    parse_dir(data, sb, inodes, dirs, listing, parent, limits, img, depth, seen);
}

#[allow(clippy::too_many_arguments)]
fn parse_dir(
    data: &[u8],
    sb: &Sb,
    inodes: &Meta,
    dirs: &Meta,
    listing: &[u8],
    parent: &str,
    limits: &Limits,
    img: &mut FsImage,
    depth: usize,
    seen: &mut Vec<u64>,
) {
    let r = Reader::new(listing);
    let mut pos = 0usize;
    while pos + 12 <= listing.len() {
        let count = r.u32_le(pos).unwrap_or(0);
        let block_start = r.u32_le(pos + 4).unwrap_or(0);
        pos += 12;
        if count >= 256 {
            break;
        }
        for _ in 0..=count {
            if img.entries.len() >= limits.max_entries {
                img.complete = false;
                return;
            }
            let Some(entry_off) = r.u16_le(pos) else { return };
            let name_len = r.u16_le(pos + 6).map(|v| usize::from(v) + 1).unwrap_or(0);
            let etype = r.u16_le(pos + 4).unwrap_or(0);
            let name = listing.get(pos + 8..pos + 8 + name_len).map(|b| String::from_utf8_lossy(b).into_owned()).unwrap_or_default();
            pos += 8 + name_len;
            if name.is_empty() || name_len > limits.max_name {
                continue;
            }
            let child_ref = (u64::from(block_start) << 16) | u64::from(entry_off);
            let path = join(parent, &name);
            // Entry type: 1=dir, 2=file, 3=symlink (and 8/9/10 extended variants).
            match etype {
                1 | 8 => {
                    img.entries.push(FsEntry::dir(path.clone()));
                    walk(data, sb, inodes, dirs, child_ref, &path, limits, img, depth + 1, seen);
                }
                2 | 9 => {
                    let bytes = inodes.at(child_ref).and_then(|p| file_bytes(data, sb, &inodes.data, p, limits, img));
                    let size = bytes.as_ref().map(|b| b.len() as u64).unwrap_or(0);
                    img.entries.push(FsEntry::file(path, size, bytes));
                }
                3 | 10 => {
                    let target = inodes.at(child_ref).and_then(|p| symlink_target(&inodes.data, p)).unwrap_or_default();
                    img.entries.push(FsEntry::symlink(path, target));
                }
                _ => img.entries.push(FsEntry { path, kind: FsKind::Other, size: 0, symlink_target: None, data: None }),
            }
        }
    }
}

fn symlink_target(idata: &[u8], pos: usize) -> Option<String> {
    let r = Reader::new(idata);
    let len = r.u32_le(pos + 20)? as usize;
    idata.get(pos + 24..pos + 24 + len.min(4096)).map(|b| String::from_utf8_lossy(b).into_owned())
}

/// Read a regular file's bytes: its data blocks (from the archive body) plus any tail fragment.
fn file_bytes(data: &[u8], sb: &Sb, idata: &[u8], pos: usize, limits: &Limits, img: &mut FsImage) -> Option<Vec<u8>> {
    let r = Reader::new(idata);
    let itype = r.u16_le(pos)?;
    // Regular file inode (basic=2, extended=9).
    let (blocks_start, fragment, frag_offset, file_size, list_off) = match itype {
        2 => (u64::from(r.u32_le(pos + 16)?), r.u32_le(pos + 20)?, r.u32_le(pos + 24)?, u64::from(r.u32_le(pos + 28)?), pos + 32),
        9 => {
            let xattr = r.u32_le(pos + 52)?;
            if xattr != 0xffff_ffff {
                img.warn("squashfs: extended inode xattrs are not supported");
                img.complete = false;
            }
            (r.u64_le(pos + 16)?, r.u32_le(pos + 44)?, r.u32_le(pos + 48)?, r.u64_le(pos + 24)?, pos + 56)
        }
        _ => return None,
    };
    if file_size > limits.max_file_bytes || img.bytes.saturating_add(file_size) > limits.max_total_bytes {
        img.warn("squashfs: file skipped (size budget)");
        img.complete = false;
        return None;
    }
    let bs = u64::from(sb.block_size);
    let has_fragment = fragment != 0xffff_ffff;
    let full_blocks = if has_fragment { (file_size / bs) as usize } else { file_size.div_ceil(bs.max(1)) as usize };
    let mut out = Vec::with_capacity(usize::try_from(file_size).unwrap_or(0));
    let mut data_pos = blocks_start;
    for i in 0..full_blocks.min(1 << 20) {
        let Some(bsize) = r.u32_le(list_off + i * 4) else {
            img.warn("squashfs: file block list not read");
            img.complete = false;
            return None;
        };
        let uncompressed = bsize & 0x0100_0000 != 0;
        let len = (bsize & 0x00ff_ffff) as usize;
        if len == 0 {
            // Sparse block.
            out.resize(out.len().saturating_add(sb.block_size as usize), 0);
            continue;
        }
        let start = usize::try_from(data_pos).ok()?;
        let block = data.get(start..start.checked_add(len)?)?;
        if uncompressed {
            out.extend_from_slice(block);
        } else {
            match decompress(sb.compression, block, bs) {
                Some(d) => out.extend_from_slice(&d),
                None => {
                    img.warn("squashfs: a data block did not decompress");
                    img.complete = false;
                    return None;
                }
            }
        }
        data_pos = data_pos.checked_add(len as u64)?;
    }
    if has_fragment {
        match fragment_bytes(data, sb, fragment, img) {
            Some(frag) => {
                let tail = file_size.saturating_sub(out.len() as u64) as usize;
                let o = frag_offset as usize;
                let Some(slice) = frag.get(o..o.checked_add(tail)?) else {
                    img.warn("squashfs: fragment not read");
                    img.complete = false;
                    return None;
                };
                out.extend_from_slice(slice);
            }
            None => {
                img.warn("squashfs: fragment not read");
                img.complete = false;
                return None;
            }
        }
    }
    out.truncate(usize::try_from(file_size).unwrap_or(0));
    img.bytes = img.bytes.saturating_add(out.len() as u64);
    Some(out)
}

/// Resolve and decompress a fragment block.
fn fragment_bytes(data: &[u8], sb: &Sb, index: u32, img: &mut FsImage) -> Option<Vec<u8>> {
    if index >= sb.frag_count {
        return None;
    }
    let r = Reader::new(data);
    // The fragment table start is an array of u64 metadata-block pointers.
    let per_block = META_MAX / 16; // fragment entries per metadata block
    let which = (index as usize) / per_block;
    let within = (index as usize) % per_block;
    let ptr_off = usize::try_from(sb.frag_table).ok()?.checked_add(which.checked_mul(8)?)?;
    let meta_block = r.u64_le(ptr_off)?;
    let mut tmp = FsImage::new("squashfs");
    // Decompress just this one metadata block.
    let mstart = usize::try_from(meta_block).ok()?;
    let hdr = r.u16_le(mstart)?;
    let uncompressed = hdr & 0x8000 != 0;
    let len = usize::from(hdr & 0x7fff);
    let block = data.get(mstart + 2..mstart + 2 + len)?;
    let meta = if uncompressed { block.to_vec() } else { decompress(sb.compression, block, META_MAX as u64)? };
    let _ = &mut tmp;
    let e = within.checked_mul(16)?;
    let mr = Reader::new(&meta);
    let frag_start = mr.u64_le(e)?;
    let frag_size = mr.u32_le(e + 8)?;
    let comp = frag_size & 0x0100_0000 == 0;
    let flen = (frag_size & 0x00ff_ffff) as usize;
    let fstart = usize::try_from(frag_start).ok()?;
    let fblock = data.get(fstart..fstart.checked_add(flen)?)?;
    if comp {
        decompress(sb.compression, fblock, u64::from(sb.block_size)).or_else(|| {
            img.complete = false;
            None
        })
    } else {
        Some(fblock.to_vec())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_small_image() {
        let img = read(&craft_anything_testkit::firmware::squashfs_image(), &Limits::default());
        assert!(img.complete, "{:?}", img.warnings);
        assert_eq!(img.entries.iter().find(|e| e.path == "readme").unwrap().data.as_deref(), Some(craft_anything_testkit::firmware::SQUASHFS_README));
        assert!(img.entries.iter().any(|e| e.path == "etc" && e.kind == FsKind::Dir));
        assert_eq!(img.entries.iter().find(|e| e.path == "etc/motd").unwrap().data.as_deref(), Some(b"welcome\n".as_slice()));
    }

    #[test]
    fn reads_extended_regular_file_inodes() {
        let sb = Sb { block_size: 4096, compression: 1, inode_table: 0, dir_table: 0, frag_table: 0, id_table: 0, root_ref: 0, frag_count: 0 };
        let body = b"extended file payload";
        let mut data = vec![0u8; 96];
        data.extend_from_slice(body);
        let mut idata = Vec::new();
        idata.extend_from_slice(&9u16.to_le_bytes());
        idata.extend_from_slice(&0o644u16.to_le_bytes());
        idata.resize(16, 0);
        idata.extend_from_slice(&96u64.to_le_bytes());
        idata.extend_from_slice(&(body.len() as u64).to_le_bytes());
        idata.extend_from_slice(&0u64.to_le_bytes());
        idata.extend_from_slice(&2u32.to_le_bytes());
        idata.extend_from_slice(&0xffff_ffffu32.to_le_bytes());
        idata.extend_from_slice(&0u32.to_le_bytes());
        idata.extend_from_slice(&0xffff_ffffu32.to_le_bytes());
        idata.extend_from_slice(&((body.len() as u32) | 0x0100_0000).to_le_bytes());
        let mut img = FsImage::new("squashfs");
        let got = file_bytes(&data, &sb, &idata, 0, &Limits::default(), &mut img);
        assert_eq!(got.as_deref(), Some(body.as_slice()));
        assert!(img.complete, "{:?}", img.warnings);

        let mut bad_frag = idata.clone();
        bad_frag[44..48].copy_from_slice(&0u32.to_le_bytes());
        let mut fail_img = FsImage::new("squashfs");
        assert!(file_bytes(&data, &sb, &bad_frag, 0, &Limits::default(), &mut fail_img).is_none());
        assert!(!fail_img.complete);
    }

    #[test]
    fn hostile_never_panics() {
        let base = craft_anything_testkit::firmware::squashfs_image();
        for m in craft_anything_testkit::mutations(&base) {
            let _ = read(&m, &Limits::default());
        }
        for len in (0..base.len()).step_by(5) {
            let _ = read(&base[..len], &Limits::default());
        }
        for seed in 0..16 {
            let _ = read(&craft_anything_testkit::noise(seed, 2048), &Limits::default());
        }
    }
}
