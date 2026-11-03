//! cramfs (`Compressed ROMFS`, magic `0x28cd3d45`): a compressed read-only filesystem. Little
//! -endian only (the rare big-endian variant is reported, not read). Inodes are 12 bytes; a
//! directory's children sit consecutively in its data span; a regular file's data is a run of
//! zlib-compressed 4 KiB blocks preceded by their end-offset pointers. Bounded against cycles,
//! huge sizes and corrupt offsets.

use super::{FsEntry, FsImage, FsKind, Limits, join};
use crate::bytes::Reader;

const BLK: usize = 4096;

struct Inode {
    mode: u16,
    size: usize,
    namelen: usize,
    offset: usize,
}

fn inode_at(r: &Reader, off: usize) -> Option<Inode> {
    let mode = r.u16_le(off)?;
    let sz = r.u32_le(off + 4)?;
    let no = r.u32_le(off + 8)?;
    Some(Inode { mode, size: (sz & 0x00ff_ffff) as usize, namelen: ((no & 0x3f) as usize) * 4, offset: ((no >> 6) as usize) * 4 })
}

pub fn read(data: &[u8], limits: &Limits) -> FsImage {
    let mut img = FsImage::new("cramfs");
    let r = Reader::new(data);
    if r.u32_le(0) != Some(0x28cd_3d45) {
        if r.u32_be(0) == Some(0x28cd_3d45) {
            img.warn("big-endian cramfs is not read");
        } else {
            img.warn("not a cramfs image");
        }
        img.complete = false;
        return img;
    }
    let Some(root) = inode_at(&r, 64) else {
        img.warn("root inode unreadable");
        img.complete = false;
        return img;
    };
    walk(data, root.offset, root.size, "", limits, &mut img, 0);
    img
}

fn trim(name: &[u8]) -> String {
    let end = name.iter().position(|&b| b == 0).unwrap_or(name.len());
    String::from_utf8_lossy(name.get(..end).unwrap_or(&[])).into_owned()
}

fn walk(data: &[u8], dir_off: usize, dir_size: usize, parent: &str, limits: &Limits, img: &mut FsImage, depth: usize) {
    if depth > limits.max_depth {
        img.warn("directory nesting limit reached");
        img.complete = false;
        return;
    }
    let r = Reader::new(data);
    let Some(end) = dir_off.checked_add(dir_size) else { return };
    let mut pos = dir_off;
    while pos + 12 <= end && pos + 12 <= data.len() {
        if img.entries.len() >= limits.max_entries {
            img.complete = false;
            return;
        }
        let Some(ino) = inode_at(&r, pos) else { break };
        let name_off = pos + 12;
        let Some(name_bytes) = r.slice(name_off, ino.namelen.min(limits.max_name.max(1))) else { break };
        let name = trim(name_bytes);
        let advance = 12usize.checked_add(ino.namelen);
        let Some(advance) = advance.filter(|&a| a > 12) else { break };
        let path = if name.is_empty() { parent.to_string() } else { join(parent, &name) };
        let typ = ino.mode & 0xf000;
        if !name.is_empty() {
            match typ {
                0x4000 => {
                    img.entries.push(FsEntry::dir(path.clone()));
                    walk(data, ino.offset, ino.size, &path, limits, img, depth + 1);
                }
                0x8000 => {
                    let bytes = file_data(data, &ino, limits, img);
                    img.entries.push(FsEntry::file(path, ino.size as u64, bytes));
                }
                0xa000 => {
                    let target = file_data(data, &ino, limits, img).map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default();
                    img.entries.push(FsEntry::symlink(path, target));
                }
                _ => img.entries.push(FsEntry { path, kind: FsKind::Other, size: ino.size as u64, symlink_target: None, data: None }),
            }
        }
        pos = match pos.checked_add(advance) {
            Some(n) if n > pos => n,
            _ => break,
        };
    }
}

/// Decompress a regular file's (or symlink's) zlib block run.
fn file_data(data: &[u8], ino: &Inode, limits: &Limits, img: &mut FsImage) -> Option<Vec<u8>> {
    if ino.size == 0 {
        return Some(Vec::new());
    }
    if ino.size as u64 > limits.max_file_bytes || img.bytes.saturating_add(ino.size as u64) > limits.max_total_bytes {
        img.warn("file skipped (size budget)");
        img.complete = false;
        return None;
    }
    let r = Reader::new(data);
    let nblocks = ino.size.div_ceil(BLK);
    let mut out = Vec::with_capacity(ino.size);
    let mut block_start = ino.offset.checked_add(nblocks.checked_mul(4)?)?;
    for i in 0..nblocks {
        let end = r.u32_le(ino.offset.checked_add(i.checked_mul(4)?)?)? as usize;
        if end < block_start || end > data.len() {
            img.warn("corrupt cramfs block pointer");
            img.complete = false;
            return None;
        }
        let comp = data.get(block_start..end)?;
        match crate::firmware::inflate(comp, true, BLK as u64, true) {
            Ok(inf) => out.extend_from_slice(&inf.data.unwrap_or_default()),
            Err(_) => {
                img.warn("cramfs block did not inflate");
                img.complete = false;
                return None;
            }
        }
        block_start = end;
    }
    out.truncate(ino.size);
    img.bytes = img.bytes.saturating_add(out.len() as u64);
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_small_image() {
        let img = read(&craft_anything_testkit::firmware::cramfs_image(), &Limits::default());
        assert!(img.complete, "{:?}", img.warnings);
        assert_eq!(img.entries.iter().find(|e| e.path == "hello.txt").unwrap().data.as_deref(), Some(b"Hello from cramfs!\n".as_slice()));
        assert!(img.entries.iter().any(|e| e.path == "dir" && e.kind == FsKind::Dir));
        assert_eq!(img.entries.iter().find(|e| e.path == "dir/inner").unwrap().data.as_deref(), Some(b"nested".as_slice()));
    }

    #[test]
    fn hostile_never_panics() {
        let base = craft_anything_testkit::firmware::cramfs_image();
        for m in craft_anything_testkit::mutations(&base) {
            let _ = read(&m, &Limits::default());
        }
        for len in 0..base.len().min(400) {
            let _ = read(&base[..len], &Limits::default());
        }
    }
}
