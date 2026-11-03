//! Synthetic firmware images and the Unix archive / compression containers inside them.
//!
//! [`image`] lays out, at known offsets: a legacy boot-loader image header wrapping a gzip'd
//! kernel-like blob, a squashfs superblock region, a tar archive, a cpio (newc) archive, a ZIP,
//! an ext2 filesystem, 0xff erase padding and high-entropy noise.

/// CRC-32 (IEEE).
pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for &b in data {
        crc ^= u32::from(b);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb8_8320 & (crc & 1).wrapping_neg());
        }
    }
    !crc
}

fn adler32(data: &[u8]) -> u32 {
    let (mut a, mut b) = (1u32, 0u32);
    for &x in data {
        a = (a + u32::from(x)) % 65521;
        b = (b + a) % 65521;
    }
    (b << 16) | a
}

/// Raw DEFLATE made of stored blocks (valid, uncompressed).
pub fn deflate_stored(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    let chunks: Vec<&[u8]> = if data.is_empty() { vec![&[][..]] } else { data.chunks(65_535).collect() };
    let n = chunks.len();
    for (i, c) in chunks.into_iter().enumerate() {
        out.push(u8::from(i + 1 == n));
        let len = c.len() as u16;
        out.extend_from_slice(&len.to_le_bytes());
        out.extend_from_slice(&(!len).to_le_bytes());
        out.extend_from_slice(c);
    }
    out
}

/// A gzip member (stored blocks) with an optional original file name.
pub fn gzip(data: &[u8], name: Option<&str>) -> Vec<u8> {
    let mut out = vec![0x1f, 0x8b, 8, if name.is_some() { 8 } else { 0 }, 0, 0, 0, 0, 0, 3];
    if let Some(n) = name {
        out.extend_from_slice(n.as_bytes());
        out.push(0);
    }
    out.extend_from_slice(&deflate_stored(data));
    out.extend_from_slice(&crc32(data).to_le_bytes());
    out.extend_from_slice(&(data.len() as u32).to_le_bytes());
    out
}

/// A zlib stream (stored blocks).
pub fn zlib(data: &[u8]) -> Vec<u8> {
    let mut out = vec![0x78, 0x01];
    out.extend_from_slice(&deflate_stored(data));
    out.extend_from_slice(&adler32(data).to_be_bytes());
    out
}

// ---------------------------------------------------------------------------------------------
// Known-good compressed fixtures for the decompressors (built with the reference encoders:
// `xz`, `xz -F lzma`, `bzip2`, `zstd`). The decoders are decode-only, so these are embedded.

/// Plaintext of [`XZ_FIXTURE`] and [`LZMA_FIXTURE`].
pub const XZ_PLAIN: &[u8] = b"Hello, xz compression world!\n";
/// Alias of [`XZ_PLAIN`] (same plaintext).
pub const LZMA_PLAIN: &[u8] = XZ_PLAIN;
/// An xz stream of [`XZ_PLAIN`].
pub const XZ_FIXTURE: &[u8] = &[
    0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00, 0x00, 0x04, 0xe6, 0xd6, 0xb4, 0x46, 0x02, 0x00, 0x21, 0x01, 0x16, 0x00, 0x00, 0x00, 0x74, 0x2f, 0xe5, 0xa3, 0x01, 0x00,
    0x1c, 0x48, 0x65, 0x6c, 0x6c, 0x6f, 0x2c, 0x20, 0x78, 0x7a, 0x20, 0x63, 0x6f, 0x6d, 0x70, 0x72, 0x65, 0x73, 0x73, 0x69, 0x6f, 0x6e, 0x20, 0x77, 0x6f, 0x72,
    0x6c, 0x64, 0x21, 0x0a, 0x00, 0x00, 0x00, 0x00, 0x1d, 0x5f, 0x47, 0xab, 0x2a, 0x4c, 0xd2, 0xb2, 0x00, 0x01, 0x35, 0x1d, 0x44, 0x1b, 0xb1, 0xe1, 0x1f, 0xb6,
    0xf3, 0x7d, 0x01, 0x00, 0x00, 0x00, 0x00, 0x04, 0x59, 0x5a,
];
/// A standalone LZMA (`.lzma`) stream of [`LZMA_PLAIN`].
pub const LZMA_FIXTURE: &[u8] = &[
    0x5d, 0x00, 0x00, 0x80, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00, 0x24, 0x19, 0x49, 0x98, 0x6f, 0x16, 0x02, 0x8d, 0x08, 0x8f, 0x5f, 0x2b,
    0x82, 0x6e, 0xf8, 0x5d, 0x46, 0x1d, 0xf0, 0x12, 0x1a, 0x71, 0x82, 0x75, 0x7e, 0xed, 0x63, 0xe7, 0x48, 0x4b, 0x7b, 0x6f, 0x27, 0xff, 0xfe, 0xbe, 0x48, 0x00,
];
/// Plaintext of [`BZIP2_FIXTURE`].
pub const BZIP2_PLAIN: &[u8] = b"Hello, bzip2!\n";
/// A bzip2 stream of [`BZIP2_PLAIN`].
pub const BZIP2_FIXTURE: &[u8] = &[
    0x42, 0x5a, 0x68, 0x39, 0x31, 0x41, 0x59, 0x26, 0x53, 0x59, 0x04, 0xad, 0x5a, 0x6b, 0x00, 0x00, 0x02, 0xdd, 0x80, 0x00, 0x10, 0x60, 0x04, 0x10, 0x00, 0x00,
    0x40, 0x12, 0x24, 0xc0, 0x10, 0x20, 0x00, 0x22, 0x00, 0x03, 0x42, 0x01, 0xa0, 0x05, 0x67, 0xde, 0x89, 0xa1, 0xa0, 0x80, 0xf1, 0x77, 0x24, 0x53, 0x85, 0x09,
    0x00, 0x4a, 0xd5, 0xa6, 0xb0,
];
/// Plaintext of [`ZSTD_FIXTURE`].
pub const ZSTD_PLAIN: &[u8] = b"Hello, zstd!\n";
/// A Zstandard frame of [`ZSTD_PLAIN`].
pub const ZSTD_FIXTURE: &[u8] = &[
    0x28, 0xb5, 0x2f, 0xfd, 0x24, 0x0d, 0x69, 0x00, 0x00, 0x48, 0x65, 0x6c, 0x6c, 0x6f, 0x2c, 0x20, 0x7a, 0x73, 0x74, 0x64, 0x21, 0x0a, 0x41, 0xb4, 0x53, 0xb2,
];

fn tar_header(name: &str, typeflag: u8, size: usize, link: &str) -> Vec<u8> {
    let mut h = vec![0u8; 512];
    let n = name.as_bytes();
    h[..n.len().min(100)].copy_from_slice(&n[..n.len().min(100)]);
    h[100..108].copy_from_slice(b"0000644\0");
    h[108..116].copy_from_slice(b"0000000\0");
    h[116..124].copy_from_slice(b"0000000\0");
    h[124..136].copy_from_slice(format!("{size:011o}\0").as_bytes());
    h[136..148].copy_from_slice(b"00000000000\0");
    h[156] = typeflag;
    let l = link.as_bytes();
    h[157..157 + l.len().min(100)].copy_from_slice(&l[..l.len().min(100)]);
    h[257..263].copy_from_slice(b"ustar\0");
    h[263..265].copy_from_slice(b"00");
    h[148..156].copy_from_slice(b"        ");
    let sum: u32 = h.iter().map(|&b| u32::from(b)).sum();
    h[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
    h
}

fn pad512(v: &mut Vec<u8>) {
    while v.len() % 512 != 0 {
        v.push(0);
    }
}

/// A tar entry for [`tar_entries`]: (name, typeflag, data, link target).
pub type TarEntry<'a> = (&'a str, u8, &'a [u8], &'a str);

/// A ustar archive from raw entries; names longer than 100 bytes get a GNU long-name record.
pub fn tar_entries(entries: &[TarEntry<'_>]) -> Vec<u8> {
    let mut out = Vec::new();
    for (name, flag, data, link) in entries {
        if name.len() > 100 {
            let mut long = name.as_bytes().to_vec();
            long.push(0);
            out.extend(tar_header("././@LongLink", b'L', long.len(), ""));
            out.extend_from_slice(&long);
            pad512(&mut out);
        }
        out.extend(tar_header(name, *flag, data.len(), link));
        out.extend_from_slice(data);
        pad512(&mut out);
    }
    out.extend(vec![0u8; 1024]);
    out
}

/// A ustar archive of files (names ending in `/` become folders).
pub fn tar(files: &[(&str, &[u8])]) -> Vec<u8> {
    let e: Vec<TarEntry<'_>> = files.iter().map(|(n, d)| (*n, if n.ends_with('/') { b'5' } else { b'0' }, *d, "")).collect();
    tar_entries(&e)
}

/// A cpio newc archive from (name, data, mode). Symlinks (mode 0o120000) store the target as data.
pub fn cpio_newc(files: &[(&str, &[u8], u32)]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut push = |name: &str, data: &[u8], mode: u32, ino: u32| {
        let hdr = format!(
            "070701{ino:08x}{mode:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}{:08x}",
            0,
            0,
            1,
            0,
            data.len(),
            0,
            0,
            0,
            0,
            name.len() + 1,
            0
        );
        out.extend_from_slice(hdr.as_bytes());
        out.extend_from_slice(name.as_bytes());
        out.push(0);
        while out.len() % 4 != 0 {
            out.push(0);
        }
        out.extend_from_slice(data);
        while out.len() % 4 != 0 {
            out.push(0);
        }
    };
    for (i, (n, d, m)) in files.iter().enumerate() {
        push(n, d, *m, i as u32 + 1);
    }
    push("TRAILER!!!", b"", 0, 0);
    out
}

/// A legacy boot-loader image header (64 bytes, big-endian) around `payload`.
pub fn uimage(payload: &[u8], comp: u8, name: &str) -> Vec<u8> {
    let mut h = vec![0u8; 64];
    h[0..4].copy_from_slice(&0x2705_1956u32.to_be_bytes());
    h[8..12].copy_from_slice(&0x6000_0000u32.to_be_bytes());
    h[12..16].copy_from_slice(&(payload.len() as u32).to_be_bytes());
    h[16..20].copy_from_slice(&0x8000_8000u32.to_be_bytes());
    h[20..24].copy_from_slice(&0x8000_8000u32.to_be_bytes());
    h[24..28].copy_from_slice(&crc32(payload).to_be_bytes());
    h[28] = 5; // Linux
    h[29] = 2; // ARM
    h[30] = 2; // kernel
    h[31] = comp;
    let n = name.as_bytes();
    h[32..32 + n.len().min(32)].copy_from_slice(&n[..n.len().min(32)]);
    let c = crc32(&h);
    h[4..8].copy_from_slice(&c.to_be_bytes());
    h.extend_from_slice(payload);
    h
}

/// A squashfs 4.0 superblock padded to `bytes_used` (no real inode tables).
pub fn squashfs(bytes_used: usize) -> Vec<u8> {
    let mut s = vec![0u8; bytes_used.max(96)];
    s[0..4].copy_from_slice(b"hsqs");
    s[4..8].copy_from_slice(&3u32.to_le_bytes());
    s[12..16].copy_from_slice(&131_072u32.to_le_bytes());
    s[20..22].copy_from_slice(&1u16.to_le_bytes());
    s[22..24].copy_from_slice(&17u16.to_le_bytes());
    s[26..28].copy_from_slice(&1u16.to_le_bytes());
    s[28..30].copy_from_slice(&4u16.to_le_bytes());
    s[40..48].copy_from_slice(&(bytes_used as u64).to_le_bytes());
    s
}

/// An ext2 filesystem image with a valid superblock and `blocks` 1 KiB blocks (otherwise empty).
pub fn ext2(blocks: u32) -> Vec<u8> {
    let mut v = vec![0u8; blocks as usize * 1024];
    let sb = 1024;
    v[sb..sb + 4].copy_from_slice(&16u32.to_le_bytes());
    v[sb + 4..sb + 8].copy_from_slice(&blocks.to_le_bytes());
    v[sb + 20..sb + 24].copy_from_slice(&1u32.to_le_bytes());
    v[sb + 24..sb + 28].copy_from_slice(&0u32.to_le_bytes());
    v[sb + 32..sb + 36].copy_from_slice(&8192u32.to_le_bytes());
    v[sb + 40..sb + 44].copy_from_slice(&16u32.to_le_bytes());
    v[sb + 56..sb + 58].copy_from_slice(&0xef53u16.to_le_bytes());
    v[sb + 58..sb + 60].copy_from_slice(&1u16.to_le_bytes());
    v[sb + 60..sb + 62].copy_from_slice(&1u16.to_le_bytes());
    v[sb + 76..sb + 80].copy_from_slice(&1u32.to_le_bytes());
    v[sb + 120..sb + 126].copy_from_slice(b"rootfs");
    v
}

/// A small, walkable romfs image: root holds `etc/` (with `hostname`) and `readme.txt`. The
/// header checksum is computed so the signature scanner also accepts it.
pub fn romfs_image() -> Vec<u8> {
    fn be(v: &mut Vec<u8>, x: u32) {
        v.extend_from_slice(&x.to_be_bytes());
    }
    fn pad16(v: &mut Vec<u8>) {
        while v.len() % 16 != 0 {
            v.push(0);
        }
    }
    let mut v = Vec::new();
    v.extend_from_slice(b"-rom1fs-");
    be(&mut v, 160); // full size
    be(&mut v, 0); // checksum placeholder
    v.extend_from_slice(b"craft\0");
    pad16(&mut v); // volume name → 32
    // etc/ dir @32: next = 64 | type-1(dir); spec = 112 (first child: hostname)
    be(&mut v, 64 | 1);
    be(&mut v, 112);
    be(&mut v, 0);
    be(&mut v, 0);
    v.extend_from_slice(b"etc\0");
    pad16(&mut v); // → 64
    // readme.txt @64: next = 0 | type-2(file); size 11
    be(&mut v, 2);
    be(&mut v, 0);
    be(&mut v, 11);
    be(&mut v, 0);
    v.extend_from_slice(b"readme.txt\0");
    pad16(&mut v); // → 96
    v.extend_from_slice(b"hello romfs");
    pad16(&mut v); // → 112
    // hostname @112 (child of etc): next = 0 | type-2; size 13
    be(&mut v, 2);
    be(&mut v, 0);
    be(&mut v, 13);
    be(&mut v, 0);
    v.extend_from_slice(b"hostname\0");
    pad16(&mut v); // → 144
    v.extend_from_slice(b"craft-router\n");
    pad16(&mut v); // → 160
    // Checksum: the first min(size,512) bytes sum to zero as big-endian words.
    let sum = v.as_chunks::<4>().0.iter().fold(0u32, |a, w| a.wrapping_add(u32::from_be_bytes(*w)));
    v[12..16].copy_from_slice(&sum.wrapping_neg().to_be_bytes());
    v
}

/// A small, walkable little-endian cramfs image: root holds `hello.txt` and `dir/` (with
/// `dir/inner`). File data is zlib-compressed in 4 KiB blocks, as cramfs requires.
pub fn cramfs_image() -> Vec<u8> {
    fn ino(v: &mut Vec<u8>, mode: u16, size: usize, namelen_units: u32, offset_bytes: usize) {
        v.extend_from_slice(&mode.to_le_bytes());
        v.extend_from_slice(&0u16.to_le_bytes()); // uid
        v.extend_from_slice(&((size as u32) & 0x00ff_ffff).to_le_bytes());
        v.extend_from_slice(&((((offset_bytes as u32) / 4) << 6) | namelen_units).to_le_bytes());
    }
    fn name(v: &mut Vec<u8>, s: &str, units: usize) {
        let mut b = s.as_bytes().to_vec();
        b.resize(units * 4, 0);
        v.extend_from_slice(&b);
    }
    let hello = b"Hello from cramfs!\n";
    let inner = b"nested";
    let hz = zlib(hello);
    let iz = zlib(inner);
    let hello_ptr = 136usize;
    let hello_end = hello_ptr + 4 + hz.len();
    let inner_ptr = (hello_end + 3) & !3;
    let inner_end = inner_ptr + 4 + iz.len();
    let total = inner_end;
    let mut v = Vec::new();
    v.extend_from_slice(&0x28cd_3d45u32.to_le_bytes()); // magic
    v.extend_from_slice(&(total as u32).to_le_bytes()); // size
    v.extend_from_slice(&0u32.to_le_bytes()); // flags
    v.extend_from_slice(&0u32.to_le_bytes()); // future
    v.extend_from_slice(b"Compressed ROMFS"); // signature (16)
    v.extend_from_slice(&0u32.to_le_bytes()); // fsid.crc
    v.extend_from_slice(&0u32.to_le_bytes()); // fsid.edition
    v.extend_from_slice(&0u32.to_le_bytes()); // fsid.blocks
    v.extend_from_slice(&3u32.to_le_bytes()); // fsid.files
    let mut nm = b"craft".to_vec();
    nm.resize(16, 0);
    v.extend_from_slice(&nm); // name[16] → 64
    ino(&mut v, 0x41ed, 40, 0, 76); // root dir inode → 76
    ino(&mut v, 0x81a4, hello.len(), 3, hello_ptr); // hello.txt → 88
    name(&mut v, "hello.txt", 3); // → 100
    ino(&mut v, 0x41ed, 20, 1, 116); // dir → 112
    name(&mut v, "dir", 1); // → 116
    ino(&mut v, 0x81a4, inner.len(), 2, inner_ptr); // inner → 128
    name(&mut v, "inner", 2); // → 136
    v.extend_from_slice(&(hello_end as u32).to_le_bytes()); // hello block ptr
    v.extend_from_slice(&hz);
    while v.len() < inner_ptr {
        v.push(0);
    }
    v.extend_from_slice(&(inner_end as u32).to_le_bytes()); // inner block ptr
    v.extend_from_slice(&iz);
    v
}

/// A small, walkable ext2/ext4 image (1 KiB blocks, one block group): root holds `hello.txt` and
/// `sub/` (with `sub/note`). With `extents`, inodes use an ext4 extent tree and the EXTENTS
/// feature bit; otherwise classic ext2 direct block pointers.
pub fn ext_image(extents: bool) -> Vec<u8> {
    const BS: usize = 1024;
    let blocks = 11usize;
    let mut v = vec![0u8; blocks * BS];
    let w32 = |v: &mut [u8], off: usize, x: u32| v[off..off + 4].copy_from_slice(&x.to_le_bytes());
    let w16 = |v: &mut [u8], off: usize, x: u16| v[off..off + 2].copy_from_slice(&x.to_le_bytes());
    // Superblock @1024.
    let sb = 1024;
    w32(&mut v, sb, 16); // inodes_count
    w32(&mut v, sb + 4, blocks as u32); // blocks_count_lo
    w32(&mut v, sb + 24, 0); // log_block_size → 1024
    w32(&mut v, sb + 32, 8192); // blocks_per_group
    w32(&mut v, sb + 40, 16); // inodes_per_group
    w16(&mut v, sb + 56, 0xef53); // magic
    w16(&mut v, sb + 58, 1); // state
    w16(&mut v, sb + 60, 1); // errors
    w32(&mut v, sb + 76, 1); // rev_level
    w32(&mut v, sb + 84, 11); // first_ino
    w16(&mut v, sb + 88, 128); // inode_size
    w32(&mut v, sb + 96, if extents { 0x40 } else { 0 }); // feature_incompat (EXTENTS)
    v[sb + 120..sb + 126].copy_from_slice(b"rootfs");
    // Group descriptor @2048: inode table at block 5.
    w32(&mut v, 2048 + 8, 5);
    // Inode writer: 1-based inode number → byte offset 5120 + (ino-1)*128.
    let ino_off = |ino: usize| 5120 + (ino - 1) * 128;
    let set_blocks = |v: &mut [u8], io: usize, data_block: u32, extents: bool| {
        if extents {
            w32(v, io + 32, 0x8_0000); // i_flags = EXTENTS_FL
            w16(v, io + 40, 0xf30a); // eh_magic
            w16(v, io + 42, 1); // eh_entries
            w16(v, io + 44, 4); // eh_max
            w16(v, io + 46, 0); // eh_depth
            w32(v, io + 48, 0); // eh_generation
            w32(v, io + 52, 0); // ee_block (logical 0)
            w16(v, io + 56, 1); // ee_len
            w16(v, io + 58, 0); // ee_start_hi
            w32(v, io + 60, data_block); // ee_start_lo
        } else {
            w32(v, io + 40, data_block); // i_block[0]
        }
    };
    // inode 2: root dir → block 7.
    let r = ino_off(2);
    w16(&mut v, r, 0x41ed);
    w32(&mut v, r + 4, 1024);
    set_blocks(&mut v, r, 7, extents);
    // inode 11: hello.txt → block 8.
    let h = ino_off(11);
    w16(&mut v, h, 0x81a4);
    w32(&mut v, h + 4, 22);
    set_blocks(&mut v, h, 8, extents);
    // inode 12: sub dir → block 9.
    let s = ino_off(12);
    w16(&mut v, s, 0x41ed);
    w32(&mut v, s + 4, 1024);
    set_blocks(&mut v, s, 9, extents);
    // inode 13: note → block 10.
    let n = ino_off(13);
    w16(&mut v, n, 0x81a4);
    w32(&mut v, n + 4, 11);
    set_blocks(&mut v, n, 10, extents);
    // Directory entry writer.
    let dirent = |v: &mut [u8], at: usize, ino: u32, rec: u16, ftype: u8, name: &str| {
        w32(v, at, ino);
        w16(v, at + 4, rec);
        v[at + 6] = name.len() as u8;
        v[at + 7] = ftype;
        v[at + 8..at + 8 + name.len()].copy_from_slice(name.as_bytes());
    };
    // Root dir block 7 (offset 7168).
    let rd = 7 * BS;
    dirent(&mut v, rd, 2, 12, 2, ".");
    dirent(&mut v, rd + 12, 2, 12, 2, "..");
    dirent(&mut v, rd + 24, 11, 20, 1, "hello.txt");
    dirent(&mut v, rd + 44, 12, (BS - 44) as u16, 2, "sub");
    // hello.txt data block 8.
    v[8 * BS..8 * BS + 22].copy_from_slice(b"Hello ext filesystem!\n");
    // sub dir block 9.
    let sd = 9 * BS;
    dirent(&mut v, sd, 12, 12, 2, ".");
    dirent(&mut v, sd + 12, 2, 12, 2, "..");
    dirent(&mut v, sd + 24, 13, (BS - 24) as u16, 1, "note");
    // note data block 10.
    v[10 * BS..10 * BS + 11].copy_from_slice(b"nested note");
    v
}

/// Contents of `readme` in [`squashfs_image`].
pub const SQUASHFS_README: &[u8] = b"This is the squashfs readme.\n";

/// A small, walkable SquashFS 4.0 image with uncompressed metadata and data blocks (the reader
/// also handles gzip/xz/zstd): root holds `readme` and `etc/` (with `etc/motd`).
pub fn squashfs_image() -> Vec<u8> {
    squashfs_image_with_extended_directories(false, false)
}

/// The same tree with independently selectable basic or extended root and nested directory inodes.
/// The nested directory's listing starts at a nonzero offset, distinct from its parent inode number.
pub fn squashfs_image_with_extended_directories(extended_root: bool, extended_nested: bool) -> Vec<u8> {
    fn u16(v: &mut Vec<u8>, x: u16) {
        v.extend_from_slice(&x.to_le_bytes());
    }
    fn u32(v: &mut Vec<u8>, x: u32) {
        v.extend_from_slice(&x.to_le_bytes());
    }
    let readme = SQUASHFS_README;
    let motd = b"welcome\n";
    let r = readme.len();
    let readme_start = 96u32;
    let motd_start = 96 + r as u32;
    let inode_table = 96 + r as u64 + motd.len() as u64;

    // Inode metadata block (decompressed). Order: readme(0), motd(36), etc(72), then root.
    let mut inodes = Vec::new();
    // readme: basic file (type 2)
    u16(&mut inodes, 2);
    u16(&mut inodes, 0x81a4);
    u16(&mut inodes, 0);
    u16(&mut inodes, 0);
    u32(&mut inodes, 0); // mtime
    u32(&mut inodes, 3); // inode number
    u32(&mut inodes, readme_start);
    u32(&mut inodes, 0xffff_ffff); // no fragment
    u32(&mut inodes, 0); // block offset
    u32(&mut inodes, r as u32); // file size
    u32(&mut inodes, (r as u32) | 0x0100_0000); // one uncompressed data block
    // motd: basic file
    u16(&mut inodes, 2);
    u16(&mut inodes, 0x81a4);
    u16(&mut inodes, 0);
    u16(&mut inodes, 0);
    u32(&mut inodes, 0);
    u32(&mut inodes, 4);
    u32(&mut inodes, motd_start);
    u32(&mut inodes, 0xffff_ffff);
    u32(&mut inodes, 0);
    u32(&mut inodes, motd.len() as u32);
    u32(&mut inodes, (motd.len() as u32) | 0x0100_0000);
    fn directory(out: &mut Vec<u8>, extended: bool, number: u32, links: u32, size: u16, offset: u16) {
        u16(out, if extended { 8 } else { 1 });
        u16(out, 0x41ed);
        u16(out, 0);
        u16(out, 0);
        u32(out, 0); // mtime
        u32(out, number);
        if extended {
            u32(out, links);
            u32(out, u32::from(size));
            u32(out, 0); // start_block
            u32(out, 1); // parent inode
            u16(out, 0); // no directory indexes
            u16(out, offset);
            u32(out, u32::MAX); // no xattrs
        } else {
            u32(out, 0); // start_block
            u32(out, links);
            u16(out, size);
            u16(out, offset);
            u32(out, 1); // parent inode
        }
    }
    directory(&mut inodes, extended_nested, 2, 2, 27, 37);
    let root_ref = inodes.len() as u64;
    directory(&mut inodes, extended_root, 1, 3, 40, 0);

    // Directory metadata block (decompressed): root listing @0, etc listing @37.
    let mut dirs = Vec::new();
    // root listing: header (count=1) + etc + readme
    u32(&mut dirs, 1); // count (entries-1)
    u32(&mut dirs, 0); // start_block (inode table block location)
    u32(&mut dirs, 1); // base inode number
    u16(&mut dirs, 72); // entry etc: offset into inode block
    dirs.extend_from_slice(&1i16.to_le_bytes()); // inode delta
    u16(&mut dirs, 1); // type dir
    u16(&mut dirs, 2); // size = name_len-1
    dirs.extend_from_slice(b"etc");
    u16(&mut dirs, 0); // entry readme: offset
    dirs.extend_from_slice(&2i16.to_le_bytes());
    u16(&mut dirs, 2); // type file
    u16(&mut dirs, 5); // name_len-1
    dirs.extend_from_slice(b"readme");
    // etc listing: header (count=0) + motd
    u32(&mut dirs, 0);
    u32(&mut dirs, 0);
    u32(&mut dirs, 2);
    u16(&mut dirs, 36); // entry motd: offset
    dirs.extend_from_slice(&2i16.to_le_bytes());
    u16(&mut dirs, 2);
    u16(&mut dirs, 3); // "motd" len-1
    dirs.extend_from_slice(b"motd");

    let dir_table = inode_table + 2 + inodes.len() as u64;
    let id_table = dir_table + 2 + dirs.len() as u64;
    let id_block = id_table + 8;
    let bytes_used = id_block + 2 + 4;

    let mut v = Vec::new();
    v.extend_from_slice(b"hsqs");
    u32(&mut v, 4); // inode count
    u32(&mut v, 0); // mtime
    u32(&mut v, 131_072); // block size
    u32(&mut v, 0); // fragment count
    u16(&mut v, 1); // compression = gzip (unused; all blocks uncompressed)
    u16(&mut v, 17); // block log
    u16(&mut v, 0); // flags
    u16(&mut v, 1); // id count
    u16(&mut v, 4); // version major
    u16(&mut v, 0); // version minor
    v.extend_from_slice(&root_ref.to_le_bytes()); // root inode ref (block 0)
    v.extend_from_slice(&bytes_used.to_le_bytes());
    v.extend_from_slice(&id_table.to_le_bytes());
    v.extend_from_slice(&u64::MAX.to_le_bytes()); // xattr
    v.extend_from_slice(&inode_table.to_le_bytes());
    v.extend_from_slice(&dir_table.to_le_bytes());
    v.extend_from_slice(&u64::MAX.to_le_bytes()); // fragment table
    v.extend_from_slice(&u64::MAX.to_le_bytes()); // lookup table
    debug_assert_eq!(v.len(), 96);
    // Data blocks.
    v.extend_from_slice(readme);
    v.extend_from_slice(motd);
    debug_assert_eq!(v.len() as u64, inode_table);
    // Inode metadata block (uncompressed).
    u16(&mut v, (inodes.len() as u16) | 0x8000);
    v.extend_from_slice(&inodes);
    debug_assert_eq!(v.len() as u64, dir_table);
    // Directory metadata block (uncompressed).
    u16(&mut v, (dirs.len() as u16) | 0x8000);
    v.extend_from_slice(&dirs);
    debug_assert_eq!(v.len() as u64, id_table);
    // ID table: one u64 pointer → an id metadata block of one u32 (id 0).
    v.extend_from_slice(&id_block.to_le_bytes());
    u16(&mut v, 4 | 0x8000);
    u32(&mut v, 0);
    v
}

/// A small best-effort JFFS2 image (little-endian, uncompressed data): root holds `config/` with
/// `config/settings`. CRC fields are zero (the reader scans by magic and length).
pub fn jffs2_image() -> Vec<u8> {
    fn u16(v: &mut Vec<u8>, x: u16) {
        v.extend_from_slice(&x.to_le_bytes());
    }
    fn u32(v: &mut Vec<u8>, x: u32) {
        v.extend_from_slice(&x.to_le_bytes());
    }
    fn pad4(v: &mut Vec<u8>) {
        while v.len() % 4 != 0 {
            v.push(0);
        }
    }
    fn dirent(v: &mut Vec<u8>, pino: u32, ino: u32, version: u32, dtype: u8, name: &str) {
        u16(v, 0x1985);
        u16(v, 0xe001);
        u32(v, 40 + name.len() as u32); // totlen
        u32(v, 0); // hdr_crc
        u32(v, pino);
        u32(v, version);
        u32(v, ino);
        u32(v, 0); // mctime
        v.push(name.len() as u8); // nsize
        v.push(dtype);
        v.extend_from_slice(&[0, 0]); // unused
        u32(v, 0); // node_crc
        u32(v, 0); // name_crc
        v.extend_from_slice(name.as_bytes());
        pad4(v);
    }
    fn inode(v: &mut Vec<u8>, ino: u32, version: u32, data: &[u8]) {
        u16(v, 0x1985);
        u16(v, 0xe002);
        u32(v, 68 + data.len() as u32); // totlen
        u32(v, 0); // hdr_crc
        u32(v, ino);
        u32(v, version);
        u32(v, 0o100644); // mode
        u16(v, 0); // uid
        u16(v, 0); // gid
        u32(v, data.len() as u32); // isize
        u32(v, 0); // atime
        u32(v, 0); // mtime
        u32(v, 0); // ctime
        u32(v, 0); // offset
        u32(v, data.len() as u32); // csize
        u32(v, data.len() as u32); // dsize
        v.push(0); // compr = none
        v.push(0); // usercompr
        u16(v, 0); // flags
        u32(v, 0); // data_crc
        u32(v, 0); // node_crc
        v.extend_from_slice(data);
        pad4(v);
    }
    let mut v = Vec::new();
    dirent(&mut v, 1, 2, 1, 4, "config"); // root → config (dir, ino 2)
    dirent(&mut v, 2, 3, 1, 8, "settings"); // config → settings (file, ino 3)
    inode(&mut v, 3, 1, b"key=value\n");
    v
}

/// Where each part of [`image`] lies.
#[derive(Debug, Clone)]
pub struct FirmwareLayout {
    pub uimage: (usize, usize),
    pub gzip: (usize, usize),
    pub squashfs: (usize, usize),
    pub tar: (usize, usize),
    pub cpio: (usize, usize),
    pub zip: (usize, usize),
    pub ext2: (usize, usize),
    pub noise: (usize, usize),
}

/// The kernel-like payload inside the boot image.
pub const KERNEL_TEXT: &[u8] = b"Linux version 5.10.0-craft (builder@example) #1 SMP PREEMPT\nconsole=ttyS0,115200 root=/dev/mtdblock2\n";

fn align_ff(v: &mut Vec<u8>, to: usize) {
    while v.len() % to != 0 {
        v.push(0xff);
    }
}

/// A synthetic firmware image and its layout.
pub fn image() -> (Vec<u8>, FirmwareLayout) {
    let mut v = Vec::new();
    let mut kernel = KERNEL_TEXT.repeat(20);
    kernel.extend_from_slice(&crate::noise(7, 512));
    let gz = gzip(&kernel, Some("vmlinux"));
    let u = uimage(&gz, 1, "Craft Linux-5.10");
    let uimage_r = (0, u.len());
    let gzip_r = (64, gz.len());
    v.extend_from_slice(&u);
    align_ff(&mut v, 0x1000);
    let sq = squashfs(0x1000);
    let squashfs_r = (v.len(), sq.len());
    v.extend_from_slice(&sq);
    let t = tar(&[("etc/", b""), ("etc/hostname", b"craft-router\n"), ("etc/init.d/rcS", b"#!/bin/sh\nmount -a\n")]);
    let tar_r = (v.len(), t.len());
    v.extend_from_slice(&t);
    align_ff(&mut v, 0x200);
    let c = cpio_newc(&[("init", b"#!/bin/sh\nexec /sbin/init\n", 0o100755), ("sbin", b"", 0o040755)]);
    let cpio_r = (v.len(), c.len());
    v.extend_from_slice(&c);
    align_ff(&mut v, 0x200);
    let z = crate::electron::zip_stored(&[("config/settings.json", b"{\"wifi\":true}"), ("README.txt", b"hello firmware")]);
    let zip_r = (v.len(), z.len());
    v.extend_from_slice(&z);
    align_ff(&mut v, 0x1000);
    let e = ext2(64);
    let ext2_r = (v.len(), e.len());
    v.extend_from_slice(&e);
    let n = crate::noise(0xf1a5, 8192);
    let noise_r = (v.len(), n.len());
    v.extend_from_slice(&n);
    v.extend(std::iter::repeat_n(0xffu8, 4096));
    (v, FirmwareLayout { uimage: uimage_r, gzip: gzip_r, squashfs: squashfs_r, tar: tar_r, cpio: cpio_r, zip: zip_r, ext2: ext2_r, noise: noise_r })
}
