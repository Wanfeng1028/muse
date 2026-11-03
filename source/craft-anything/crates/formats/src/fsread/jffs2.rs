//! A best-effort JFFS2 reader (little-endian). JFFS2 is a log-structured flash filesystem with no
//! central tables, so we scan every node (magic `0x1985`), collect directory entries and inode
//! data nodes, keep the highest version of each, and reassemble files. This is PARTIAL by nature:
//! CRCs are not enforced, and only no-compression, zero and zlib data nodes are decoded (rtime,
//! rubin, lzo are reported, not decoded). Big-endian images are detected but not read.

use super::{FsEntry, FsImage, FsKind, Limits, join};
use crate::bytes::Reader;
use std::collections::BTreeMap;

const DIRENT: u16 = 0xe001;
const INODE: u16 = 0xe002;

struct Dirent {
    version: u32,
    ino: u32,
    dtype: u8,
    name: String,
}

struct DataNode {
    version: u32,
    offset: u32,
    dsize: u32,
    compr: u8,
    data: Vec<u8>,
}

struct Inode {
    isize: u32,
    isize_version: u32,
    nodes: Vec<DataNode>,
}

pub fn read(data: &[u8], limits: &Limits) -> FsImage {
    let mut img = FsImage::new("jffs2");
    let r = Reader::new(data);
    if r.u16_le(0) == Some(0x8519) {
        img.warn("big-endian JFFS2 is not read");
        img.complete = false;
        return img;
    }
    img.warn("JFFS2 recovery is best-effort: node scan, latest version wins, limited compression");
    // Collect dirents keyed by (parent inode, name) and inode data keyed by inode number.
    let mut dirents: BTreeMap<(u32, String), Dirent> = BTreeMap::new();
    let mut inodes: BTreeMap<u32, Inode> = BTreeMap::new();
    let mut pos = 0usize;
    let mut nodes = 0usize;
    while pos + 12 <= data.len() {
        if nodes > 2_000_000 {
            img.complete = false;
            break;
        }
        let Some(magic) = r.u16_le(pos) else { break };
        if magic != 0x1985 {
            // Skip 0xff erase padding / zeros to the next aligned node, else give up.
            let skip = data.get(pos..).map(|s| s.iter().take(1 << 20).take_while(|&&b| b == 0xff || b == 0).count()).unwrap_or(0);
            if skip == 0 {
                break;
            }
            pos = (pos + skip + 3) & !3;
            continue;
        }
        let nodetype = r.u16_le(pos + 2).unwrap_or(0);
        let totlen = r.u32_le(pos + 4).unwrap_or(0) as usize;
        if !(12..=(8 << 20)).contains(&totlen) {
            break;
        }
        nodes += 1;
        match nodetype {
            DIRENT => {
                if let Some(d) = parse_dirent(&r, data, pos, limits) {
                    let key = (d.1, d.0.name.clone());
                    let keep = dirents.get(&key).map(|e| d.0.version >= e.version).unwrap_or(true);
                    if keep {
                        dirents.insert(key, d.0);
                    }
                }
            }
            INODE => {
                if let Some((ino, node, isize)) = parse_inode(&r, data, pos) {
                    let e = inodes.entry(ino).or_insert(Inode { isize: 0, isize_version: 0, nodes: Vec::new() });
                    if node.version >= e.isize_version {
                        e.isize = isize;
                        e.isize_version = node.version;
                    }
                    if e.nodes.len() < 100_000 {
                        e.nodes.push(node);
                    }
                }
            }
            _ => {}
        }
        pos = match pos.checked_add((totlen + 3) & !3) {
            Some(n) if n > pos => n,
            _ => break,
        };
    }
    // Build the tree from the root inode (1).
    let mut children: BTreeMap<u32, Vec<&Dirent>> = BTreeMap::new();
    for ((pino, _), d) in &dirents {
        if d.ino != 0 {
            children.entry(*pino).or_default().push(d);
        }
    }
    let mut seen = Vec::new();
    build(&children, &inodes, 1, "", limits, &mut img, 0, &mut seen);
    img
}

/// Returns (dirent, parent inode).
fn parse_dirent(r: &Reader, data: &[u8], pos: usize, limits: &Limits) -> Option<(Dirent, u32)> {
    let pino = r.u32_le(pos + 12)?;
    let version = r.u32_le(pos + 16)?;
    let ino = r.u32_le(pos + 20)?;
    let nsize = usize::from(r.u8(pos + 28)?).min(limits.max_name.max(1));
    let dtype = r.u8(pos + 29)?;
    let name = data.get(pos + 40..pos + 40 + nsize).map(|b| String::from_utf8_lossy(b).into_owned())?;
    Some((Dirent { version, ino, dtype, name }, pino))
}

/// Returns (inode number, data node, isize at this version).
fn parse_inode(r: &Reader, data: &[u8], pos: usize) -> Option<(u32, DataNode, u32)> {
    let ino = r.u32_le(pos + 12)?;
    let version = r.u32_le(pos + 16)?;
    let isize = r.u32_le(pos + 28)?;
    let offset = r.u32_le(pos + 44)?;
    let csize = r.u32_le(pos + 48)? as usize;
    let dsize = r.u32_le(pos + 52)?;
    let compr = r.u8(pos + 56)?;
    let data = data.get(pos + 68..pos + 68 + csize.min(8 << 20))?.to_vec();
    Some((ino, DataNode { version, offset, dsize, compr, data }, isize))
}

#[allow(clippy::too_many_arguments)]
fn build(
    children: &BTreeMap<u32, Vec<&Dirent>>,
    inodes: &BTreeMap<u32, Inode>,
    dir_ino: u32,
    parent: &str,
    limits: &Limits,
    img: &mut FsImage,
    depth: usize,
    seen: &mut Vec<u32>,
) {
    if depth > limits.max_depth || img.entries.len() >= limits.max_entries || seen.contains(&dir_ino) {
        if depth > limits.max_depth {
            img.complete = false;
        }
        return;
    }
    seen.push(dir_ino);
    let Some(kids) = children.get(&dir_ino) else { return };
    for d in kids {
        if img.entries.len() >= limits.max_entries {
            img.complete = false;
            return;
        }
        let path = join(parent, &d.name);
        match d.dtype {
            4 => {
                img.entries.push(FsEntry::dir(path.clone()));
                build(children, inodes, d.ino, &path, limits, img, depth + 1, seen);
            }
            8 => {
                let bytes = inodes.get(&d.ino).and_then(|i| reassemble(i, limits, img));
                let size = bytes.as_ref().map(|b| b.len() as u64).unwrap_or(0);
                img.entries.push(FsEntry::file(path, size, bytes));
            }
            10 => {
                let target = inodes.get(&d.ino).and_then(|i| reassemble(i, limits, img)).map(|b| String::from_utf8_lossy(&b).into_owned()).unwrap_or_default();
                img.entries.push(FsEntry::symlink(path, target));
            }
            _ => img.entries.push(FsEntry { path, kind: FsKind::Other, size: 0, symlink_target: None, data: None }),
        }
    }
}

/// Reassemble a file from its data nodes (applied in version order), bounded by `isize`.
fn reassemble(inode: &Inode, limits: &Limits, img: &mut FsImage) -> Option<Vec<u8>> {
    let size = inode.isize as usize;
    if inode.isize as u64 > limits.max_file_bytes || img.bytes.saturating_add(inode.isize as u64) > limits.max_total_bytes {
        img.warn("jffs2: file skipped (size budget)");
        img.complete = false;
        return None;
    }
    let mut out = vec![0u8; size];
    let mut ordered: Vec<&DataNode> = inode.nodes.iter().collect();
    ordered.sort_by_key(|n| n.version);
    for node in ordered {
        let chunk = match node.compr {
            0 => node.data.clone(),
            1 => vec![0u8; node.dsize as usize],
            6 => match crate::firmware::inflate(&node.data, true, u64::from(node.dsize), true) {
                Ok(i) => i.data.unwrap_or_default(),
                Err(_) => {
                    img.warn("jffs2: a zlib data node did not inflate");
                    img.complete = false;
                    continue;
                }
            },
            _ => {
                img.warn("jffs2: a data node uses an unsupported compression (rtime/rubin/lzo)");
                img.complete = false;
                continue;
            }
        };
        let off = node.offset as usize;
        let end = off.saturating_add(chunk.len()).min(out.len());
        if off < out.len()
            && let Some(dst) = out.get_mut(off..end)
        {
            dst.copy_from_slice(chunk.get(..end - off).unwrap_or(&[]));
        }
    }
    img.bytes = img.bytes.saturating_add(out.len() as u64);
    Some(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_small_image() {
        let img = read(&craft_anything_testkit::firmware::jffs2_image(), &Limits::default());
        assert!(img.entries.iter().any(|e| e.path == "config" && e.kind == FsKind::Dir), "{:?}", img.entries);
        assert_eq!(img.entries.iter().find(|e| e.path == "config/settings").unwrap().data.as_deref(), Some(b"key=value\n".as_slice()));
    }

    #[test]
    fn hostile_never_panics() {
        let base = craft_anything_testkit::firmware::jffs2_image();
        for m in craft_anything_testkit::mutations(&base) {
            let _ = read(&m, &Limits::default());
        }
        for len in 0..base.len() {
            let _ = read(&base[..len], &Limits::default());
        }
        for seed in 0..16 {
            let _ = read(&craft_anything_testkit::noise(seed, 400), &Limits::default());
        }
    }
}
