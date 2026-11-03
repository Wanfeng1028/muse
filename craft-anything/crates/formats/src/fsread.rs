//! Read-only readers for the filesystems a firmware image commonly carries: romfs, cramfs,
//! SquashFS (v4, the common gzip/xz/zstd/lzma cases), ext2/3/4 (a minimal reader), and a
//! best-effort JFFS2 node scan. Each reader lists entries and, for regular files, recovers their
//! bytes. Everything is strictly bounded (entries, recursion depth, per-file and total bytes) and
//! never panics or loops forever on a corrupt or cyclic image.
//!
//! These complement the signature scan in [`crate::firmware`]: the scanner recognises a filesystem
//! region; these readers unpack what is inside it.

use serde::Serialize;

pub mod cramfs;
pub mod extfs;
pub mod jffs2;
pub mod romfs;
pub mod squashfs;

/// What an entry is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum FsKind {
    File,
    Dir,
    Symlink,
    Other,
}

/// One entry recovered from a filesystem. For regular files, `data` holds the file's bytes when
/// they were recovered within the byte budget.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FsEntry {
    /// Path relative to the filesystem root, using `/` separators and no leading slash.
    pub path: String,
    pub kind: FsKind,
    pub size: u64,
    /// Target of a symlink, when known.
    pub symlink_target: Option<String>,
    /// Regular-file bytes, present when recovered; `None` for directories, symlinks, specials, or
    /// a file skipped for size/corruption (see `warnings`).
    #[serde(skip)]
    pub data: Option<Vec<u8>>,
}

impl FsEntry {
    fn dir(path: String) -> Self {
        FsEntry { path, kind: FsKind::Dir, size: 0, symlink_target: None, data: None }
    }
    fn symlink(path: String, target: String) -> Self {
        FsEntry { path, kind: FsKind::Symlink, size: target.len() as u64, symlink_target: Some(target), data: None }
    }
    fn file(path: String, size: u64, data: Option<Vec<u8>>) -> Self {
        FsEntry { path, kind: FsKind::File, size, symlink_target: None, data }
    }
}

/// Limits every reader honours.
#[derive(Debug, Clone, Copy)]
pub struct Limits {
    /// Most entries listed.
    pub max_entries: usize,
    /// Deepest directory nesting walked.
    pub max_depth: usize,
    /// Longest single path component kept.
    pub max_name: usize,
    /// Most file bytes materialised in total (across all files).
    pub max_total_bytes: u64,
    /// Most bytes materialised for any one file.
    pub max_file_bytes: u64,
}

impl Default for Limits {
    fn default() -> Self {
        Limits { max_entries: 200_000, max_depth: 64, max_name: 255, max_total_bytes: 512 << 20, max_file_bytes: 256 << 20 }
    }
}

/// What a reader recovered.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct FsImage {
    pub format: &'static str,
    pub entries: Vec<FsEntry>,
    pub warnings: Vec<String>,
    /// True when the whole directory tree was walked within the limits.
    pub complete: bool,
    /// Bytes of file data materialised.
    pub bytes: u64,
}

impl FsImage {
    fn new(format: &'static str) -> Self {
        FsImage { format, entries: Vec::new(), warnings: Vec::new(), complete: true, bytes: 0 }
    }
    fn warn(&mut self, msg: impl Into<String>) {
        if self.warnings.len() < 256 {
            self.warnings.push(msg.into());
        }
    }
}

/// Dispatch to the reader for a scanner region `kind` (`squashfs`, `cramfs`, `romfs`, `ext2`,
/// `ext3`, `ext4`, `jffs2`). `None` for kinds with no reader.
pub fn read(kind: &str, data: &[u8], limits: &Limits) -> Option<FsImage> {
    match kind {
        "squashfs" => Some(squashfs::read(data, limits)),
        "cramfs" => Some(cramfs::read(data, limits)),
        "romfs" => Some(romfs::read(data, limits)),
        "ext2" | "ext3" | "ext4" => Some(extfs::read(data, limits)),
        "jffs2" => Some(jffs2::read(data, limits)),
        _ => None,
    }
}

/// Join a parent path and a child component with `/` (no leading slash at the root).
pub(crate) fn join(parent: &str, name: &str) -> String {
    if parent.is_empty() { name.to_string() } else { format!("{parent}/{name}") }
}

/// True for the `.`/`..` directory entries, which readers skip.
pub(crate) fn is_dot(name: &str) -> bool {
    name == "." || name == ".."
}
