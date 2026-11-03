//! A minimal read-only ext2/3/4 reader: the superblock, block-group descriptors (32- or 64-byte),
//! inodes, directory entries, and regular-file data via either classic block pointers
//! (direct/indirect/double-indirect) or ext4 extent trees (depth 0 and 1). It extracts regular
//! files, directories and fast symlinks from the root inode down, strictly bounded.
//!
//! Deliberately NOT handled (reported in warnings): triple-indirect blocks, inline data, directory
//! HTree index specifics (directories are read as linear entry lists, which is layout-compatible),
//! encryption, and 64-bit block numbers beyond the low 32 bits. These make a file appear as
//! unrecovered rather than producing wrong bytes.

use super::{FsEntry, FsImage, Limits, is_dot, join};
use crate::bytes::Reader;

struct Sb {
    block_size: u64,
    inodes_per_group: u32,
    inode_size: u64,
    desc_size: u64,
    incompat: u32,
    kind: &'static str,
}

fn superblock(data: &[u8]) -> Option<Sb> {
    let r = Reader::new(data);
    let s = 1024usize;
    if r.u16_le(s + 56)? != 0xef53 {
        return None;
    }
    let log = r.u32_le(s + 24)?;
    if log > 6 {
        return None;
    }
    let block_size = 1024u64 << log;
    let inodes_per_group = r.u32_le(s + 40)?;
    let rev = r.u32_le(s + 76)?;
    let inode_size = if rev >= 1 { u64::from(r.u16_le(s + 88)?) } else { 128 };
    let incompat = r.u32_le(s + 96)?;
    let compat = r.u32_le(s + 92)?;
    let desc_size = if incompat & 0x80 != 0 { u64::from(r.u16_le(s + 0xfe).filter(|&v| v >= 32)?) } else { 32 };
    if inodes_per_group == 0 || inode_size < 128 {
        return None;
    }
    let kind = if incompat & (0x40 | 0x80 | 0x200) != 0 {
        "ext4"
    } else if compat & 0x4 != 0 {
        "ext3"
    } else {
        "ext2"
    };
    Some(Sb { block_size, inodes_per_group, inode_size, desc_size, incompat, kind })
}

/// Byte offset of the group-descriptor table: the block after the one holding the superblock.
fn gdt_offset(block_size: u64) -> u64 {
    if block_size == 1024 { 2048 } else { block_size }
}

/// Byte offset of inode `ino` (1-based).
fn inode_offset(data: &[u8], sb: &Sb, ino: u32) -> Option<u64> {
    let group = (ino.checked_sub(1)?) / sb.inodes_per_group;
    let index = u64::from((ino - 1) % sb.inodes_per_group);
    let desc = gdt_offset(sb.block_size).checked_add(u64::from(group).checked_mul(sb.desc_size)?)?;
    let r = Reader::new(data);
    let table_lo = r.u32_le(usize::try_from(desc).ok()?.checked_add(8)?)?;
    let table_hi = if sb.desc_size >= 64 { r.u32_le(usize::try_from(desc).ok()?.checked_add(40)?).unwrap_or(0) } else { 0 };
    let table = u64::from(table_lo) | (u64::from(table_hi) << 32);
    table.checked_mul(sb.block_size)?.checked_add(index.checked_mul(sb.inode_size)?)
}

/// Read a block (physical number) into `out`, bounded; missing/zero blocks contribute zeros.
fn block_bytes<'a>(data: &'a [u8], sb: &Sb, block: u64) -> Option<&'a [u8]> {
    let start = usize::try_from(block.checked_mul(sb.block_size)?).ok()?;
    let end = start.checked_add(usize::try_from(sb.block_size).ok()?)?;
    data.get(start..end)
}

/// Collect the physical block numbers for logical blocks 0..n of an inode, via block pointers or
/// an extent tree. Unmapped logical blocks are `None` (sparse → zeros).
fn file_block_map(data: &[u8], sb: &Sb, inode_off: u64, flags: u32, nblocks: u64, img: &mut FsImage) -> Vec<Option<u64>> {
    let r = Reader::new(data);
    let ib = usize::try_from(inode_off).ok().and_then(|o| o.checked_add(40));
    let Some(ib) = ib else { return Vec::new() };
    let n = usize::try_from(nblocks.min(1 << 20)).unwrap_or(0);
    let mut map = vec![None; n];
    if flags & 0x8_0000 != 0 {
        // ext4 extent tree rooted in i_block.
        extents(data, sb, ib, &mut map, 0, img);
    } else {
        // Classic indirect block pointers.
        let per = (sb.block_size / 4).max(1);
        let mut logical = 0u64;
        let set = |logical: &mut u64, phys: u32, map: &mut Vec<Option<u64>>| {
            if let Ok(i) = usize::try_from(*logical)
                && i < map.len()
                && phys != 0
            {
                map[i] = Some(u64::from(phys));
            }
            *logical += 1;
        };
        for i in 0..12 {
            if let Some(p) = r.u32_le(ib + i * 4) {
                set(&mut logical, p, &mut map);
            }
        }
        // Single indirect.
        if let Some(ind) = r.u32_le(ib + 48).filter(|&p| p != 0) {
            read_indirect(data, sb, u64::from(ind), 1, per, &mut logical, &mut map);
        }
        // Double indirect.
        if let Some(dind) = r.u32_le(ib + 52).filter(|&p| p != 0) {
            read_indirect(data, sb, u64::from(dind), 2, per, &mut logical, &mut map);
        }
        if r.u32_le(ib + 56).is_some_and(|p| p != 0) {
            img.warn("ext: triple-indirect blocks are not followed");
            img.complete = false;
        }
    }
    map
}

fn read_indirect(data: &[u8], sb: &Sb, block: u64, level: u8, per: u64, logical: &mut u64, map: &mut Vec<Option<u64>>) {
    if *logical as usize >= map.len() {
        return;
    }
    let Some(b) = block_bytes(data, sb, block) else { return };
    let r = Reader::new(b);
    for i in 0..per {
        let Some(off) = usize::try_from(i.saturating_mul(4)).ok() else { break };
        let Some(ptr) = r.u32_le(off) else { break };
        if ptr == 0 {
            *logical += if level == 1 { 1 } else { per };
            continue;
        }
        if level == 1 {
            if let Ok(idx) = usize::try_from(*logical)
                && idx < map.len()
            {
                map[idx] = Some(u64::from(ptr));
            }
            *logical += 1;
        } else {
            read_indirect(data, sb, u64::from(ptr), level - 1, per, logical, map);
        }
        if *logical as usize >= map.len() {
            return;
        }
    }
}

fn extents(data: &[u8], sb: &Sb, node_off: usize, map: &mut Vec<Option<u64>>, depth_guard: u8, img: &mut FsImage) {
    if depth_guard > 8 {
        return;
    }
    let r = Reader::new(data);
    if r.u16_le(node_off) != Some(0xf30a) {
        img.warn("ext4: bad extent header");
        img.complete = false;
        return;
    }
    let entries = r.u16_le(node_off + 2).unwrap_or(0).min(340);
    let depth = r.u16_le(node_off + 6).unwrap_or(0);
    for i in 0..entries as usize {
        let e = node_off + 12 + i * 12;
        if depth == 0 {
            let logical = r.u32_le(e).unwrap_or(0);
            let raw_len = r.u16_le(e + 4).unwrap_or(0);
            let start_hi = r.u16_le(e + 6).unwrap_or(0);
            let start_lo = r.u32_le(e + 8).unwrap_or(0);
            let phys = u64::from(start_lo) | (u64::from(start_hi) << 32);
            let unwritten = raw_len > 32768; // uninitialised extents
            let len = if unwritten { raw_len - 32768 } else { raw_len };
            for k in 0..u64::from(len) {
                if let Ok(idx) = usize::try_from(u64::from(logical).saturating_add(k))
                    && idx < map.len()
                {
                    map[idx] = if unwritten { None } else { Some(phys.saturating_add(k)) };
                }
            }
        } else {
            let leaf_lo = r.u32_le(e + 4).unwrap_or(0);
            let leaf_hi = r.u16_le(e + 8).unwrap_or(0);
            let leaf = u64::from(leaf_lo) | (u64::from(leaf_hi) << 32);
            if let Some(off) = usize::try_from(leaf.saturating_mul(sb.block_size)).ok().filter(|&o| o + 12 <= data.len()) {
                extents(data, sb, off, map, depth_guard + 1, img);
            }
        }
    }
}

fn file_data(data: &[u8], sb: &Sb, inode_off: u64, flags: u32, size: u64, limits: &Limits, img: &mut FsImage) -> Option<Vec<u8>> {
    if size == 0 {
        return Some(Vec::new());
    }
    if size > limits.max_file_bytes || img.bytes.saturating_add(size) > limits.max_total_bytes {
        img.warn("ext: file skipped (size budget)");
        img.complete = false;
        return None;
    }
    let nblocks = size.div_ceil(sb.block_size);
    let map = file_block_map(data, sb, inode_off, flags, nblocks, img);
    let mut out = Vec::with_capacity(usize::try_from(size).unwrap_or(0));
    for phys in &map {
        match phys {
            Some(p) => match block_bytes(data, sb, *p) {
                Some(b) => out.extend_from_slice(b),
                None => out.resize(out.len() + usize::try_from(sb.block_size).unwrap_or(0), 0),
            },
            None => out.resize(out.len().saturating_add(usize::try_from(sb.block_size).unwrap_or(0)), 0),
        }
    }
    out.truncate(usize::try_from(size).unwrap_or(0));
    img.bytes = img.bytes.saturating_add(out.len() as u64);
    Some(out)
}

#[allow(clippy::too_many_arguments)]
fn walk(data: &[u8], sb: &Sb, ino: u32, parent: &str, limits: &Limits, img: &mut FsImage, depth: usize, seen: &mut Vec<u32>) {
    if depth > limits.max_depth || seen.len() > limits.max_entries {
        img.complete = false;
        return;
    }
    if seen.contains(&ino) {
        return;
    }
    seen.push(ino);
    let Some(inode_off) = inode_offset(data, sb, ino) else { return };
    let r = Reader::new(data);
    let io = usize::try_from(inode_off).ok().filter(|&o| o.checked_add(128).is_some_and(|end| end <= data.len()));
    let Some(io) = io else { return };
    let size = u64::from(r.u32_le(io + 4).unwrap_or(0)) | (u64::from(r.u32_le(io + 108).unwrap_or(0)) << 32);
    let flags = r.u32_le(io + 32).unwrap_or(0);
    if flags & 0x1000_0000 != 0 {
        img.warn(format!("{parent}: inline-data inode not read"));
        img.complete = false;
    }
    // Read the directory's data (a run of entry blocks) and parse entries.
    let dir_bytes = file_data(data, sb, inode_off, flags, size, &Limits { max_file_bytes: 64 << 20, ..*limits }, img).unwrap_or_default();
    let mut pos = 0usize;
    while pos + 8 <= dir_bytes.len() {
        if img.entries.len() >= limits.max_entries {
            img.complete = false;
            return;
        }
        let dr = Reader::new(&dir_bytes);
        let child = dr.u32_le(pos).unwrap_or(0);
        let rec_len = dr.u16_le(pos + 4).unwrap_or(0) as usize;
        let name_len = dr.u8(pos + 6).unwrap_or(0) as usize;
        let ftype = dr.u8(pos + 7).unwrap_or(0);
        if rec_len < 8 || pos + rec_len > dir_bytes.len() {
            break;
        }
        if child != 0 && name_len > 0 && name_len <= limits.max_name {
            let name = String::from_utf8_lossy(dir_bytes.get(pos + 8..pos + 8 + name_len).unwrap_or(&[])).into_owned();
            if !is_dot(&name) {
                let path = join(parent, &name);
                child_entry(data, sb, child, ftype, path, limits, img, depth, seen);
            }
        }
        pos += rec_len;
    }
}

#[allow(clippy::too_many_arguments)]
fn child_entry(data: &[u8], sb: &Sb, ino: u32, ftype: u8, path: String, limits: &Limits, img: &mut FsImage, depth: usize, seen: &mut Vec<u32>) {
    // ftype: 1=file, 2=dir, 7=symlink (when the filetype feature is on); fall back to i_mode.
    let Some(io) = inode_offset(data, sb, ino).and_then(|o| usize::try_from(o).ok()).filter(|&o| o.checked_add(128).is_some_and(|end| end <= data.len()))
    else {
        return;
    };
    let r = Reader::new(data);
    let mode = r.u16_le(io).unwrap_or(0) & 0xf000;
    let is_dir = ftype == 2 || mode == 0x4000;
    let is_link = ftype == 7 || mode == 0xa000;
    if is_dir {
        img.entries.push(FsEntry::dir(path.clone()));
        walk(data, sb, ino, &path, limits, img, depth + 1, seen);
    } else if is_link {
        let size = u64::from(r.u32_le(io + 4).unwrap_or(0));
        // Fast symlink: target stored inline in i_block when size < 60.
        let target = if size < 60 {
            String::from_utf8_lossy(data.get(io + 40..io + 40 + size as usize).unwrap_or(&[])).into_owned()
        } else {
            let flags = r.u32_le(io + 32).unwrap_or(0);
            file_data(data, sb, io as u64, flags, size, limits, img).map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default()
        };
        img.entries.push(FsEntry::symlink(path, target));
    } else {
        let size = u64::from(r.u32_le(io + 4).unwrap_or(0)) | (u64::from(r.u32_le(io + 108).unwrap_or(0)) << 32);
        let flags = r.u32_le(io + 32).unwrap_or(0);
        let bytes = file_data(data, sb, io as u64, flags, size, limits, img);
        img.entries.push(FsEntry::file(path, size, bytes));
    }
}

pub fn read(data: &[u8], limits: &Limits) -> FsImage {
    let Some(sb) = superblock(data) else {
        let mut img = FsImage::new("ext");
        img.warn("not an ext2/3/4 superblock");
        img.complete = false;
        return img;
    };
    let mut img = FsImage::new(sb.kind);
    if sb.incompat & 0x1_0000 != 0 {
        img.warn("filesystem is encrypted; file contents are not decrypted");
        img.complete = false;
    }
    let mut seen = Vec::new();
    walk(data, &sb, 2, "", limits, &mut img, 0, &mut seen);
    img
}

#[cfg(test)]
mod tests {
    use super::*;

    fn check(extents: bool) {
        let img = read(&craft_anything_testkit::firmware::ext_image(extents), &Limits::default());
        assert!(img.complete, "extents={extents}: {:?}", img.warnings);
        assert_eq!(img.entries.iter().find(|e| e.path == "hello.txt").unwrap().data.as_deref(), Some(b"Hello ext filesystem!\n".as_slice()));
        assert!(img.entries.iter().any(|e| e.path == "sub" && e.kind == super::super::FsKind::Dir));
        assert_eq!(img.entries.iter().find(|e| e.path == "sub/note").unwrap().data.as_deref(), Some(b"nested note".as_slice()));
    }

    #[test]
    fn reads_ext2_block_pointers() {
        check(false);
    }

    #[test]
    fn reads_ext4_extents() {
        check(true);
    }

    #[test]
    fn unwritten_ext4_extents_read_as_zeros() {
        let mut base = craft_anything_testkit::firmware::ext_image(true);
        // Inode 11 ("hello.txt", 22 bytes) starts at 5120 + (11 - 1) * 128 = 6400; its first extent's ee_len is at +56.
        base[6456..6458].copy_from_slice(&32769u16.to_le_bytes());
        let img = read(&base, &Limits::default());
        assert!(img.complete, "{:?}", img.warnings);
        let hello = img.entries.iter().find(|e| e.path == "hello.txt").expect("hello.txt entry");
        assert_eq!(hello.size, 22);
        assert_eq!(hello.data.as_deref(), Some([0u8; 22].as_slice()));
        assert_eq!(img.entries.iter().find(|e| e.path == "sub/note").unwrap().data.as_deref(), Some(b"nested note".as_slice()));
    }

    /// Switch to 64-bit group descriptors and send `group`'s inode table to the last
    /// 1 KiB block of the address space, so an inode there starts within 128 bytes of `usize::MAX`.
    fn point_table_at_the_end(img: &mut [u8], group: usize) {
        img[1024 + 96..1024 + 100].copy_from_slice(&0x80u32.to_le_bytes()); // incompat: 64-bit
        img[1024 + 0xfe..1024 + 0x100].copy_from_slice(&64u16.to_le_bytes()); // descriptor size
        let d = 2048 + group * 64;
        img[d + 8..d + 12].copy_from_slice(&u32::MAX.to_le_bytes());
        img[d + 40..d + 44].copy_from_slice(&0x003f_ffffu32.to_le_bytes());
    }

    #[test]
    fn root_inode_at_the_end_of_the_address_space_is_refused() {
        let mut base = craft_anything_testkit::firmware::ext_image(false);
        base[1024 + 88..1024 + 90].copy_from_slice(&1000u16.to_le_bytes()); // inode size
        point_table_at_the_end(&mut base, 0);
        let img = read(&base, &Limits::default());
        assert!(img.entries.is_empty(), "{:?}", img.entries);
    }

    #[test]
    fn child_inode_at_the_end_of_the_address_space_is_skipped() {
        let mut base = craft_anything_testkit::firmware::ext_image(false);
        point_table_at_the_end(&mut base, 1);
        // Point "hello.txt" at inode 24: group 1, slot 7, which starts 128 bytes before the end.
        let at = base.windows(9).position(|w| w == b"hello.txt").expect("the fixture lists hello.txt");
        base[at - 8..at - 4].copy_from_slice(&24u32.to_le_bytes());
        let img = read(&base, &Limits::default());
        assert!(img.entries.iter().all(|e| e.path != "hello.txt"), "{:?}", img.entries);
        assert!(img.entries.iter().any(|e| e.path == "sub"), "the rest of the directory is still read");
    }

    #[test]
    fn hostile_never_panics() {
        let base = craft_anything_testkit::firmware::ext_image(false);
        for m in craft_anything_testkit::mutations(&base) {
            let _ = read(&m, &Limits::default());
        }
        for len in (0..base.len()).step_by(7) {
            let _ = read(&base[..len], &Limits::default());
        }
        for seed in 0..16 {
            let _ = read(&craft_anything_testkit::noise(seed, 4096), &Limits::default());
        }
    }
}
