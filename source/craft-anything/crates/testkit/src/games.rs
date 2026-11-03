//! Game archive fixtures.

fn fstring(s: &str) -> Vec<u8> {
    let mut v = ((s.len() + 1) as i32).to_le_bytes().to_vec();
    v.extend_from_slice(s.as_bytes());
    v.push(0);
    v
}

/// A zlib stream holding `data` in stored (uncompressed) deflate blocks: valid zlib without a
/// compressor.
pub fn zlib_stored(data: &[u8]) -> Vec<u8> {
    let mut out = vec![0x78, 0x01];
    let chunks: Vec<&[u8]> = if data.is_empty() { vec![&[]] } else { data.chunks(0xffff).collect() };
    for (i, chunk) in chunks.iter().enumerate() {
        out.push(u8::from(i + 1 == chunks.len()));
        let len = chunk.len() as u16;
        out.extend_from_slice(&len.to_le_bytes());
        out.extend_from_slice(&(!len).to_le_bytes());
        out.extend_from_slice(chunk);
    }
    let (mut a, mut b) = (1u32, 0u32);
    for &x in data {
        a = (a + u32::from(x)) % 65521;
        b = (b + a) % 65521;
    }
    out.extend_from_slice(&((b << 16) | a).to_be_bytes());
    out
}

/// A small Unreal pak, version 11: `(directory, name, contents, zlib)`, mounted at `../../../`.
/// Each file's record comes before its data, as in a real pak; a zlib file is one compression
/// block. The index has packed entries and a full directory index.
pub fn unreal_pak(files: &[(&str, &str, &[u8], bool)]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut encoded = Vec::new();
    let mut dirs: Vec<(&str, Vec<(&str, i32)>)> = Vec::new();
    for (dir, name, data, zlib) in files {
        let offset = out.len() as u32;
        let stored = if *zlib { zlib_stored(data) } else { data.to_vec() };
        // The record: offset (relative, so 0), size, uncompressed size, method, hash, (one block,
        // from the record's start), flags, block size.
        out.extend_from_slice(&0u64.to_le_bytes());
        out.extend_from_slice(&(stored.len() as u64).to_le_bytes());
        out.extend_from_slice(&(data.len() as u64).to_le_bytes());
        out.extend_from_slice(&u32::from(*zlib).to_le_bytes());
        out.extend_from_slice(&[0u8; 20]);
        if *zlib {
            let record = 24 + 4 + 20 + 4 + 16 + 1 + 4;
            out.extend_from_slice(&1i32.to_le_bytes());
            out.extend_from_slice(&(record as u64).to_le_bytes());
            out.extend_from_slice(&((record + stored.len()) as u64).to_le_bytes());
        }
        out.push(0);
        out.extend_from_slice(&65536u32.to_le_bytes());
        out.extend_from_slice(&stored);
        let at = encoded.len() as i32;
        // Offset and sizes fit in 32 bits; a zlib file is method 1 with one 64 KiB block.
        let bits = if *zlib { (1u32 << 31) | (1 << 30) | (1 << 29) | (1 << 23) | (1 << 6) | (65536 >> 11) } else { (1u32 << 31) | (1 << 30) };
        encoded.extend_from_slice(&bits.to_le_bytes());
        encoded.extend_from_slice(&offset.to_le_bytes());
        encoded.extend_from_slice(&(data.len() as u32).to_le_bytes());
        if *zlib {
            encoded.extend_from_slice(&(stored.len() as u32).to_le_bytes());
        }
        match dirs.iter_mut().find(|(d, _)| d == dir) {
            Some((_, names)) => names.push((name, at)),
            None => dirs.push((dir, vec![(name, at)])),
        }
    }
    let directory_offset = out.len() as u64;
    let mut directory = (dirs.len() as i32).to_le_bytes().to_vec();
    for (dir, names) in &dirs {
        directory.extend(fstring(dir));
        directory.extend_from_slice(&(names.len() as i32).to_le_bytes());
        for (name, at) in names {
            directory.extend(fstring(name));
            directory.extend_from_slice(&at.to_le_bytes());
        }
    }
    out.extend_from_slice(&directory);
    let index_offset = out.len() as u64;
    let mut index = fstring("../../../");
    index.extend_from_slice(&(files.len() as i32).to_le_bytes());
    index.extend_from_slice(&0u64.to_le_bytes()); // path hash seed
    index.extend_from_slice(&0u32.to_le_bytes()); // no path hash index
    index.extend_from_slice(&1u32.to_le_bytes()); // a full directory index
    index.extend_from_slice(&directory_offset.to_le_bytes());
    index.extend_from_slice(&(directory.len() as u64).to_le_bytes());
    index.extend_from_slice(&[0u8; 20]);
    index.extend_from_slice(&(encoded.len() as i32).to_le_bytes());
    index.extend_from_slice(&encoded);
    index.extend_from_slice(&0i32.to_le_bytes()); // no plain entries
    out.extend_from_slice(&index);
    // The footer: key GUID, encrypted-index flag, magic, version, index place, hash, method names.
    out.extend_from_slice(&[0u8; 16]);
    out.push(0);
    out.extend_from_slice(&0x5A6F_12E1u32.to_le_bytes());
    out.extend_from_slice(&11i32.to_le_bytes());
    out.extend_from_slice(&index_offset.to_le_bytes());
    out.extend_from_slice(&(index.len() as u64).to_le_bytes());
    out.extend_from_slice(&[0u8; 20]);
    for name in ["Zlib", "", "", "", ""] {
        let mut n = name.as_bytes().to_vec();
        n.resize(32, 0);
        out.extend_from_slice(&n);
    }
    out
}

/// A version-8 Unreal IoStore table of contents (`.utoc`) with container `flags` (1 compressed,
/// 2 encrypted, 4 signed, 8 indexed): three chunks, four 64 KiB blocks (two Oodle, one stored, one
/// Oodle), and a directory index naming `Game/Maps/A.uasset`, `Game/Maps/A.ubulk` and
/// `Game/B.uasset` under `../../../`. `maps_sibling` is the Maps directory's next sibling
/// (`u32::MAX` for none; pointing back up makes a loop).
pub fn unreal_utoc(flags: u8, maps_sibling: u32) -> Vec<u8> {
    const NONE: u32 = u32::MAX;
    let mut dir = fstring("../../../");
    let u32s = |v: &mut Vec<u8>, xs: &[u32]| xs.iter().for_each(|x| v.extend_from_slice(&x.to_le_bytes()));
    // Directories: root, Game, Maps.
    dir.extend_from_slice(&3i32.to_le_bytes());
    u32s(&mut dir, &[NONE, 1, NONE, NONE]);
    u32s(&mut dir, &[0, 2, NONE, 2]);
    u32s(&mut dir, &[1, NONE, maps_sibling, 0]);
    // Files: A.uasset -> A.ubulk, B.uasset.
    dir.extend_from_slice(&3i32.to_le_bytes());
    u32s(&mut dir, &[2, 1, 0]);
    u32s(&mut dir, &[3, NONE, 1]);
    u32s(&mut dir, &[4, NONE, 2]);
    dir.extend_from_slice(&5i32.to_le_bytes());
    for s in ["Game", "Maps", "A.uasset", "A.ubulk", "B.uasset"] {
        dir.extend(fstring(s));
    }

    let mut t = b"-==--==--==--==-".to_vec();
    t.push(8);
    t.extend_from_slice(&[0; 3]);
    for v in [144u32, 3, 4, 12, 1, 32, 65536, dir.len() as u32, 1] {
        t.extend_from_slice(&v.to_le_bytes());
    }
    t.extend_from_slice(&7u64.to_le_bytes()); // container id
    t.extend_from_slice(&[0; 16]); // key guid
    t.push(flags);
    t.extend_from_slice(&[0; 3]);
    t.extend_from_slice(&1u32.to_le_bytes()); // one perfect hash seed
    t.extend_from_slice(&u64::MAX.to_le_bytes()); // partition size
    t.extend_from_slice(&0u32.to_le_bytes()); // none outside the perfect hash
    t.extend_from_slice(&[0; 4 + 40]);
    assert_eq!(t.len(), 144);
    t.extend_from_slice(&[0; 3 * 12]); // chunk ids
    // Chunks: 100 000 bytes at 0, 5 bytes at 131072 (block 2), 10 bytes at 196608 (block 3).
    for (o, l) in [(0u64, 100_000u64), (131_072, 5), (196_608, 10)] {
        t.extend_from_slice(&o.to_be_bytes()[3..]);
        t.extend_from_slice(&l.to_be_bytes()[3..]);
    }
    t.extend_from_slice(&0i32.to_le_bytes()); // the seed
    for (off, comp, unc) in [(0u64, 30_000u32, 65_536u32), (30_000, 20_000, 34_464), (50_000, 5, 5), (50_005, 8, 10)] {
        t.extend_from_slice(&off.to_le_bytes()[..5]);
        t.extend_from_slice(&comp.to_le_bytes()[..3]);
        t.extend_from_slice(&unc.to_le_bytes()[..3]);
        t.push(if comp == unc { 0 } else { 1 });
    }
    let mut oodle = b"Oodle".to_vec();
    oodle.resize(32, 0);
    t.extend_from_slice(&oodle);
    if flags & 4 != 0 {
        t.extend_from_slice(&20i32.to_le_bytes());
        t.extend_from_slice(&[0; 40]);
        t.extend_from_slice(&[0; 4 * 20]);
    }
    t.extend_from_slice(&dir);
    t.extend_from_slice(&[0; 3 * 33]); // chunk metas (not read)
    t
}

/// A Unity serialized file (format 22, little-endian, Windows 64-bit, no type trees) written by
/// `unity_version`, holding `objects` as (class id, bytes) with path ids 1, 2, …, and pointing at
/// one external file.
pub fn unity_serialized_file(unity_version: &str, objects: &[(i32, Vec<u8>)]) -> Vec<u8> {
    let le32 = |v: &mut Vec<u8>, x: u32| v.extend_from_slice(&x.to_le_bytes());
    let mut classes: Vec<i32> = Vec::new();
    for (class, _) in objects {
        if !classes.contains(class) {
            classes.push(*class);
        }
    }
    let mut meta = unity_version.as_bytes().to_vec();
    meta.push(0);
    le32(&mut meta, 19);
    meta.push(0); // no type trees
    le32(&mut meta, classes.len() as u32);
    for class in &classes {
        meta.extend_from_slice(&class.to_le_bytes());
        meta.push(0); // not stripped
        meta.extend_from_slice(&(if *class == 114 { 0i16 } else { -1 }).to_le_bytes());
        if *class == 114 {
            meta.extend_from_slice(&[9; 16]); // script id
        }
        meta.extend_from_slice(&[0; 16]); // type hash
    }
    le32(&mut meta, objects.len() as u32);
    let mut start = 0u64;
    for (i, (class, data)) in objects.iter().enumerate() {
        while (48 + meta.len()) % 4 != 0 {
            meta.push(0);
        }
        meta.extend_from_slice(&(i as u64 + 1).to_le_bytes());
        meta.extend_from_slice(&start.to_le_bytes());
        le32(&mut meta, data.len() as u32);
        le32(&mut meta, classes.iter().position(|c| c == class).unwrap_or(0) as u32);
        start += (data.len() as u64).div_ceil(8) * 8;
    }
    le32(&mut meta, 0); // script references
    le32(&mut meta, 1); // one external
    meta.push(0);
    meta.extend_from_slice(&[0; 16 + 4]);
    meta.extend_from_slice(b"library/unity default resources\0");
    le32(&mut meta, 0); // reference types
    meta.push(0); // user information

    let data_offset = (48 + meta.len() as u64).div_ceil(16) * 16;
    let file_size = data_offset + start;
    let mut out = Vec::new();
    out.extend_from_slice(&[0; 8]);
    out.extend_from_slice(&22u32.to_be_bytes());
    out.extend_from_slice(&[0; 4]);
    out.extend_from_slice(&[0, 0, 0, 0]); // little-endian, reserved
    out.extend_from_slice(&(meta.len() as u32).to_be_bytes());
    out.extend_from_slice(&file_size.to_be_bytes());
    out.extend_from_slice(&data_offset.to_be_bytes());
    out.extend_from_slice(&[0; 8]);
    out.extend_from_slice(&meta);
    out.resize(data_offset as usize, 0);
    for (_, data) in objects {
        out.extend_from_slice(data);
        out.resize(out.len().div_ceil(8) * 8, 0);
    }
    assert_eq!(out.len() as u64, file_size);
    out
}

/// A Unity 2022.3 serialized file ([`unity_serialized_file`]): a GameObject "Player", a Texture2D
/// "Grass", a MonoBehaviour "PlayerController" and a Transform, path ids 1-4.
pub fn unity_assets() -> Vec<u8> {
    let le32 = |v: &mut Vec<u8>, x: u32| v.extend_from_slice(&x.to_le_bytes());
    let named = |v: &mut Vec<u8>, s: &str| {
        v.extend_from_slice(&(s.len() as u32).to_le_bytes());
        v.extend_from_slice(s.as_bytes());
        while v.len() % 4 != 0 {
            v.push(0);
        }
    };
    let mut player = Vec::new();
    le32(&mut player, 1); // one component
    player.extend_from_slice(&[0; 4]);
    player.extend_from_slice(&4u64.to_le_bytes());
    le32(&mut player, 0); // layer
    named(&mut player, "Player");
    let mut grass = Vec::new();
    named(&mut grass, "Grass");
    grass.extend_from_slice(&[7; 12]);
    let mut behaviour = vec![0; 12];
    behaviour.extend_from_slice(&[1, 0, 0, 0]);
    behaviour.extend_from_slice(&[0; 12]);
    named(&mut behaviour, "PlayerController");
    unity_serialized_file("2022.3.62f1", &[(1, player), (28, grass), (114, behaviour), (4, vec![0u8; 40])])
}

/// `data` as one LZ4 block of literals only (valid LZ4, no compressor needed).
pub fn lz4_literals(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::new();
    if data.len() < 15 {
        out.push((data.len() as u8) << 4);
    } else {
        out.push(0xf0);
        let mut left = data.len() - 15;
        while left >= 255 {
            out.push(255);
            left -= 255;
        }
        out.push(left as u8);
    }
    out.extend_from_slice(data);
    out
}

/// A UnityFS bundle (format 8, Unity 2022.3, LZ4 block table, 16-byte padding): one stored data
/// block holding the serialized file `CAB-0123456789abcdef` ([`unity_assets`]) and a 5-byte `.resS`.
pub fn unity_bundle() -> Vec<u8> {
    unity_bundle_with(&unity_assets(), b"resS!")
}

/// A UnityFS bundle like [`unity_bundle`] holding `assets` as `CAB-0123456789abcdef` and `ress` as
/// `CAB-0123456789abcdef.resS`.
pub fn unity_bundle_with(assets: &[u8], ress: &[u8]) -> Vec<u8> {
    unity_bundle_files(&[("CAB-0123456789abcdef", assets, true), ("CAB-0123456789abcdef.resS", ress, false)])
}

/// A UnityFS bundle like [`unity_bundle`] holding `files`: `(path, bytes, serialized)`.
pub fn unity_bundle_files(files: &[(&str, &[u8], bool)]) -> Vec<u8> {
    let data: Vec<u8> = files.iter().flat_map(|(_, bytes, _)| bytes.iter().copied()).collect();
    let mut table = vec![0u8; 16]; // the data's hash
    table.extend_from_slice(&1i32.to_be_bytes());
    table.extend_from_slice(&(data.len() as u32).to_be_bytes());
    table.extend_from_slice(&(data.len() as u32).to_be_bytes());
    table.extend_from_slice(&0u16.to_be_bytes()); // stored
    table.extend_from_slice(&(files.len() as i32).to_be_bytes());
    let mut offset = 0u64;
    for (path, bytes, serialized) in files {
        table.extend_from_slice(&offset.to_be_bytes());
        table.extend_from_slice(&(bytes.len() as u64).to_be_bytes());
        table.extend_from_slice(&if *serialized { 4u32 } else { 0 }.to_be_bytes());
        table.extend_from_slice(path.as_bytes());
        table.push(0);
        offset += bytes.len() as u64;
    }
    let packed = lz4_literals(&table);
    let mut out = b"UnityFS\0".to_vec();
    out.extend_from_slice(&8u32.to_be_bytes());
    out.extend_from_slice(b"5.x.x\0");
    out.extend_from_slice(b"2022.3.62f1\0");
    let size_at = out.len();
    out.extend_from_slice(&0u64.to_be_bytes());
    out.extend_from_slice(&(packed.len() as u32).to_be_bytes());
    out.extend_from_slice(&(table.len() as u32).to_be_bytes());
    out.extend_from_slice(&(2u32 | 0x40 | 0x200).to_be_bytes()); // LZ4 table, combined, padded data
    out.resize(out.len().div_ceil(16) * 16, 0);
    out.extend_from_slice(&packed);
    out.resize(out.len().div_ceil(16) * 16, 0);
    out.extend_from_slice(&data);
    let total = out.len() as u64;
    out[size_at..size_at + 8].copy_from_slice(&total.to_be_bytes());
    out
}

/// A Unity Texture2D object's bytes (little-endian) as `unity_version` writes it, `width`×`height`
/// in pixel `format`, with its pixels `inline` or streamed from `(path, offset, size)`.
pub fn unity_texture2d(
    unity_version: &str,
    name: &str,
    width: i32,
    height: i32,
    format: i32,
    inline: Option<&[u8]>,
    stream: Option<(&str, u64, u32)>,
) -> Vec<u8> {
    let mut parts = unity_version.split('.').map(|p| p.parse::<u32>().unwrap_or(0));
    let v = (parts.next().unwrap_or(0), parts.next().unwrap_or(0));
    let at = |major: u32, minor: u32| v >= (major, minor);
    let mut out = Vec::new();
    let align = |out: &mut Vec<u8>| out.resize(out.len().div_ceil(4) * 4, 0);
    let int = |out: &mut Vec<u8>, x: i32| out.extend_from_slice(&x.to_le_bytes());
    let string = |out: &mut Vec<u8>, s: &str| {
        out.extend_from_slice(&(s.len() as i32).to_le_bytes());
        out.extend_from_slice(s.as_bytes());
        out.resize(out.len().div_ceil(4) * 4, 0);
    };
    string(&mut out, name);
    if !at(6000, 0) {
        int(&mut out, 4); // fallback format
    }
    out.push(0); // downscale fallback
    if at(2020, 2) {
        out.push(1); // alpha optional
    }
    align(&mut out);
    let pixels = inline.map_or_else(|| stream.map_or(0, |s| s.2 as i32), |d| d.len() as i32);
    for x in [width, height, pixels] {
        int(&mut out, x);
    }
    if at(2020, 1) {
        int(&mut out, 0); // mips stripped
    }
    int(&mut out, format);
    int(&mut out, 1); // mip count
    out.push(1); // readable
    for flag in [at(2020, 1), at(2019, 3), at(2018, 2)] {
        if flag {
            out.push(0);
        }
    }
    align(&mut out);
    if at(2022, 2) {
        string(&mut out, ""); // mipmap limit group
        int(&mut out, 0);
    }
    if at(2018, 2) {
        int(&mut out, -92); // streaming priority (it can be negative)
    }
    for x in [1, 2, 1, 1, 0, 1, 1, 1, 6, 1] {
        int(&mut out, x); // images, dimension, sampling settings, lightmap format, colour space
    }
    if at(2020, 2) {
        int(&mut out, 0); // platform blob
    }
    let data = inline.unwrap_or_default();
    int(&mut out, data.len() as i32);
    out.extend_from_slice(data);
    align(&mut out);
    let (path, offset, size) = stream.unwrap_or(("", 0, 0));
    if at(2020, 1) {
        out.extend_from_slice(&offset.to_le_bytes());
    } else {
        out.extend_from_slice(&(offset as u32).to_le_bytes());
    }
    out.extend_from_slice(&size.to_le_bytes());
    string(&mut out, path);
    out
}

/// A cooked Unreal 4.27 texture package (`.uasset`, `.uexp`) named `name` in `pixel_format`: one
/// Texture2D export with tagged properties, its first mip optionally in the `.ubulk`
/// (`(width, height, length)` at offset 0), then a `width`×`height` mip with `pixels` inline.
pub fn unreal_texture_package(name: &str, pixel_format: &str, width: i32, height: i32, pixels: &[u8], ubulk: Option<(i32, i32, i32)>) -> (Vec<u8>, Vec<u8>) {
    let names = [
        "None",
        "Texture2D",
        "/Script/Engine",
        "Class",
        "ImportedSize",
        "StructProperty",
        "IntPoint",
        "LODBias",
        "IntProperty",
        "LODGroup",
        "ByteProperty",
        "TextureGroup",
        "TEXTUREGROUP_UI",
        pixel_format,
        name,
    ];
    let idx = |n: &str| names.iter().position(|x| *x == n).unwrap_or(0) as i32;
    let i32s = |v: &mut Vec<u8>, xs: &[i32]| xs.iter().for_each(|x| v.extend_from_slice(&x.to_le_bytes()));
    let fname = |v: &mut Vec<u8>, n: &str| i32s(v, &[idx(n), 0]);
    let fstring = |v: &mut Vec<u8>, s: &str| {
        v.extend_from_slice(&((s.len() + 1) as i32).to_le_bytes());
        v.extend_from_slice(s.as_bytes());
        v.push(0);
    };

    // The export's data: properties, then the cooked platform data.
    let mut d = Vec::new();
    fname(&mut d, "ImportedSize");
    fname(&mut d, "StructProperty");
    i32s(&mut d, &[8, 0]);
    fname(&mut d, "IntPoint");
    d.extend_from_slice(&[0; 16]);
    d.push(0);
    i32s(&mut d, &[width, height]);
    fname(&mut d, "LODBias");
    fname(&mut d, "IntProperty");
    i32s(&mut d, &[4, 0]);
    d.push(0);
    i32s(&mut d, &[0]);
    fname(&mut d, "LODGroup");
    fname(&mut d, "ByteProperty");
    i32s(&mut d, &[8, 0]);
    fname(&mut d, "TextureGroup");
    d.push(0);
    fname(&mut d, "TEXTUREGROUP_UI");
    fname(&mut d, "None");
    i32s(&mut d, &[0]); // no guid
    d.extend_from_slice(&[1, 0, 1, 0]); // strip flags
    i32s(&mut d, &[1]); // cooked
    fname(&mut d, pixel_format);
    d.extend_from_slice(&0i64.to_le_bytes()); // skip offset
    let (full_w, full_h) = ubulk.map_or((width, height), |b| (b.0, b.1));
    i32s(&mut d, &[full_w, full_h, 1]);
    fstring(&mut d, pixel_format);
    i32s(&mut d, &[0, 1 + i32::from(ubulk.is_some())]);
    if let Some((w, h, len)) = ubulk {
        i32s(&mut d, &[1, 0x10501, len, len]);
        d.extend_from_slice(&0i64.to_le_bytes());
        i32s(&mut d, &[w, h, 1]);
    }
    i32s(&mut d, &[1, 0x48, pixels.len() as i32, pixels.len() as i32]);
    d.extend_from_slice(&0i64.to_le_bytes());
    d.extend_from_slice(pixels);
    i32s(&mut d, &[width, height, 1]);
    i32s(&mut d, &[0]); // not virtual
    fname(&mut d, "None");

    // The .uasset: summary, names, one import (the class), one export.
    let summary_len = 4 * 6 + 4 + (4 + 5) + 4 + 4 * 2 + 8 + 4 * 2 + 4 * 2 + 4 * 2;
    let mut name_table = Vec::new();
    for n in names {
        fstring(&mut name_table, n);
        name_table.extend_from_slice(&[0; 4]);
    }
    let name_offset = summary_len as i32;
    let import_offset = name_offset + name_table.len() as i32;
    let export_offset = import_offset + 28;
    let header_size = export_offset + 104;
    let mut u = Vec::new();
    u.extend_from_slice(&0x9E2A_83C1u32.to_le_bytes());
    i32s(&mut u, &[-7, 0, 0, 0, 0, header_size]);
    fstring(&mut u, "None");
    u.extend_from_slice(&0x8000_0000u32.to_le_bytes());
    i32s(&mut u, &[names.len() as i32, name_offset, 0, 0, 1, export_offset, 1, import_offset, 0, 0]);
    assert_eq!(u.len(), summary_len);
    u.extend_from_slice(&name_table);
    fname(&mut u, "/Script/Engine");
    fname(&mut u, "Class");
    i32s(&mut u, &[0]);
    fname(&mut u, "Texture2D");
    i32s(&mut u, &[-1, 0, 0, 0]);
    fname(&mut u, name);
    i32s(&mut u, &[0]);
    u.extend_from_slice(&(d.len() as i64).to_le_bytes());
    u.extend_from_slice(&i64::from(header_size).to_le_bytes());
    u.extend_from_slice(&[0; 60]);
    assert_eq!(u.len(), header_size as usize);
    d.extend_from_slice(&0x9E2A_83C1u32.to_le_bytes());
    (u, d)
}

/// One file of a test Godot pack.
pub struct GodotFile<'a> {
    pub path: &'a str,
    pub data: &'a [u8],
    /// Raw file flags (format 2 and later).
    pub flags: u32,
    pub md5: [u8; 16],
}

/// A Godot pack on its own, as written by Godot 3.5.3 (format 1), 4.4.1 (2) or 4.6.1 (3).
pub fn godot_pck(format: u32, pack_flags: u32, files: &[GodotFile<'_>]) -> Vec<u8> {
    godot_pck_at(format, pack_flags, 0, files)
}

/// [`godot_pck`] for a pack that will sit `start` bytes into its file: format 1's offsets count
/// from the file's start.
pub fn godot_pck_at(format: u32, pack_flags: u32, start: u64, files: &[GodotFile<'_>]) -> Vec<u8> {
    let word = |v: &mut Vec<u8>, n: u32| v.extend_from_slice(&n.to_le_bytes());
    let header_size: u64 = match format {
        1 => 84,
        2 => 96,
        _ => 104,
    };
    let table_size: u64 = files.iter().map(|f| 4 + (f.path.len().div_ceil(4) * 4) as u64 + 32 + u64::from(format >= 2) * 4).sum::<u64>() + 4;
    // Format 3 keeps its table after the files; the others before them.
    let data_start = if format >= 3 { header_size } else { header_size + table_size };
    let mut table = Vec::new();
    word(&mut table, files.len() as u32);
    let mut rel = 0u64;
    for f in files {
        let pad = f.path.len().div_ceil(4) * 4;
        word(&mut table, pad as u32);
        table.extend_from_slice(f.path.as_bytes());
        table.resize(table.len() + pad - f.path.len(), 0);
        let offset = if format == 1 { start + data_start + rel } else { rel };
        table.extend_from_slice(&offset.to_le_bytes());
        table.extend_from_slice(&(f.data.len() as u64).to_le_bytes());
        table.extend_from_slice(&f.md5);
        if format >= 2 {
            word(&mut table, f.flags);
        }
        rel += f.data.len() as u64;
    }
    let mut out = b"GDPC".to_vec();
    word(&mut out, format);
    let version: [u32; 3] = match format {
        1 => [3, 5, 3],
        2 => [4, 4, 1],
        _ => [4, 6, 1],
    };
    version.iter().for_each(|n| word(&mut out, *n));
    if format >= 2 {
        word(&mut out, pack_flags);
        out.extend_from_slice(&data_start.to_le_bytes());
    }
    if format >= 3 {
        out.extend_from_slice(&(data_start + rel).to_le_bytes());
    }
    out.resize(header_size as usize, 0);
    if format < 3 {
        out.extend_from_slice(&table);
    }
    files.iter().for_each(|f| out.extend_from_slice(f.data));
    if format >= 3 {
        out.extend_from_slice(&table);
    }
    out
}

/// A program carrying a pack: its bytes, the pack, the pack's size and `GDPC`.
pub fn godot_embedded(program: &[u8], pack: &[u8]) -> Vec<u8> {
    let mut out = program.to_vec();
    out.extend_from_slice(pack);
    out.extend_from_slice(&(pack.len() as u64).to_le_bytes());
    out.extend_from_slice(b"GDPC");
    out
}

/// The shape of a test IL2CPP metadata file.
pub struct Il2cppSample {
    pub version: i32,
    pub header_size: u32,
    /// 88 from version 27 on; 92 for later 24.x files.
    pub type_size: usize,
    /// 32, or 36 with a return-parameter token.
    pub method_size: usize,
}

/// A `global-metadata.dat` with two images (mscorlib.dll: `<Module>`; Assembly-CSharp.dll:
/// Game.Enemy, Game.Player), four methods (Enemy.Update; Player..ctor, Player.Update,
/// Player.TakeDamage), seven fields and three string literals ("Hello, player", "Game over", "").
pub fn il2cpp_metadata(s: &Il2cppSample) -> Vec<u8> {
    let mut strings = Vec::new();
    let mut name = |text: &str| {
        let at = strings.len() as u32;
        strings.extend_from_slice(text.as_bytes());
        strings.push(0);
        at
    };
    let empty = name("");
    let images_named = [name("mscorlib.dll"), name("Assembly-CSharp.dll")];
    let game = name("Game");
    let types_named = [(name("<Module>"), empty), (name("Enemy"), game), (name("Player"), game)];
    let methods_named = [name("Update"), name(".ctor"), name("Update"), name("TakeDamage")];

    let put = |rec: &mut [u8], at: usize, v: u32| rec[at..at + 4].copy_from_slice(&v.to_le_bytes());
    let put16 = |rec: &mut [u8], at: usize, v: u16| rec[at..at + 2].copy_from_slice(&v.to_le_bytes());

    let (mut literals, mut literal_data) = (Vec::new(), Vec::new());
    for text in ["Hello, player", "Game over", ""] {
        literals.extend_from_slice(&(text.len() as u32).to_le_bytes());
        literals.extend_from_slice(&(literal_data.len() as u32).to_le_bytes());
        literal_data.extend_from_slice(text.as_bytes());
    }

    // Offsets in a method record: the token and what follows move on by a return-parameter token.
    let shift = s.method_size - 32;
    let mut methods = Vec::new();
    for (i, (named, owner, params, flags)) in [(0usize, 1u32, 0u16, 0x81u16), (1, 2, 0, 0x1886), (2, 2, 0, 0x81), (3, 2, 2, 0x86)].iter().enumerate() {
        let mut rec = vec![0u8; s.method_size];
        put(&mut rec, 0, methods_named[*named]);
        put(&mut rec, 4, *owner);
        put(&mut rec, 20 + shift, 0x0600_0001 + i as u32);
        put16(&mut rec, 24 + shift, *flags);
        put16(&mut rec, 30 + shift, *params);
        methods.extend_from_slice(&rec);
    }

    // Offsets in a type record: a later 24.x type also has its by-reference type index.
    let older = usize::from(s.type_size == 92) * 4;
    let mut types = Vec::new();
    for (i, (start, count, fields, flags)) in [(-1i32, 0u16, 0u16, 0u32), (0, 1, 2, 1), (1, 3, 5, 0x0010_0001)].iter().enumerate() {
        let mut rec = vec![0u8; s.type_size];
        put(&mut rec, 0, types_named[i].0);
        put(&mut rec, 4, types_named[i].1);
        put(&mut rec, 28 + older, *flags);
        put(&mut rec, 36 + older, *start as u32);
        put16(&mut rec, 64 + older, *count);
        put16(&mut rec, 68 + older, *fields);
        put(&mut rec, 84 + older, 0x0200_0001 + i as u32);
        types.extend_from_slice(&rec);
    }

    let mut images = Vec::new();
    for (i, (start, count)) in [(0u32, 1u32), (1, 2)].iter().enumerate() {
        let mut rec = vec![0u8; 40];
        put(&mut rec, 0, images_named[i]);
        put(&mut rec, 4, i as u32);
        put(&mut rec, 8, *start);
        put(&mut rec, 12, *count);
        put(&mut rec, 24, u32::MAX);
        put(&mut rec, 28, 0x2000_0000 + i as u32);
        images.extend_from_slice(&rec);
    }
    let assemblies = vec![0u8; 136];

    // The header's sections, in its order; those not read here stay empty.
    let parts: [(usize, &[u8]); 7] = [(0, &literals), (1, &literal_data), (2, &strings), (5, &methods), (19, &types), (20, &images), (21, &assemblies)];
    let mut out = vec![0u8; s.header_size as usize];
    out[0..4].copy_from_slice(&0xFAB1_1BAFu32.to_le_bytes());
    out[4..8].copy_from_slice(&s.version.to_le_bytes());
    for i in 0..22 {
        let at = 8 + i * 8;
        match parts.iter().find(|(which, _)| *which == i) {
            Some((_, bytes)) => {
                let offset = out.len() as u32;
                out[at..at + 4].copy_from_slice(&offset.to_le_bytes());
                out[at + 4..at + 8].copy_from_slice(&(bytes.len() as u32).to_le_bytes());
                out.extend_from_slice(bytes);
            }
            None => {
                let offset = out.len() as u32;
                out[at..at + 4].copy_from_slice(&offset.to_le_bytes());
            }
        }
    }
    out
}
