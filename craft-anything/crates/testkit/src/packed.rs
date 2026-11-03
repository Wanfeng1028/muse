//! Synthetic single-file programs: native carriers with a named section, note or resource, and the
//! Bun, Node, .NET and PyInstaller payloads that go in them, plus marshal and `.pyc` writers.

/// Marshal writers for the values the readers look at.
pub mod marshal {
    pub fn none() -> Vec<u8> {
        vec![b'N']
    }

    pub fn int(v: i32) -> Vec<u8> {
        let mut o = vec![b'i'];
        o.extend(v.to_le_bytes());
        o
    }

    pub fn string(s: &str) -> Vec<u8> {
        let mut o = vec![b'u'];
        o.extend((s.len() as i32).to_le_bytes());
        o.extend(s.as_bytes());
        o
    }

    pub fn bytes(b: &[u8]) -> Vec<u8> {
        let mut o = vec![b's'];
        o.extend((b.len() as i32).to_le_bytes());
        o.extend(b);
        o
    }

    pub fn tuple(items: Vec<Vec<u8>>) -> Vec<u8> {
        let mut o = vec![b'('];
        o.extend((items.len() as i32).to_le_bytes());
        o.extend(items.concat());
        o
    }

    pub fn list(items: Vec<Vec<u8>>) -> Vec<u8> {
        let mut o = vec![b'['];
        o.extend((items.len() as i32).to_le_bytes());
        o.extend(items.concat());
        o
    }

    pub fn dict(pairs: Vec<(Vec<u8>, Vec<u8>)>) -> Vec<u8> {
        let mut o = vec![b'{'];
        for (k, v) in pairs {
            o.extend(k);
            o.extend(v);
        }
        o.push(b'0');
        o
    }

    /// A 3.8-layout code object with the given bytes as its constants.
    pub fn code_38_raw(consts: &[u8]) -> Vec<u8> {
        let mut o = vec![b'c'];
        for v in [0i32, 0, 0, 0, 1, 0] {
            o.extend(v.to_le_bytes());
        }
        o.extend(bytes(&[0; 4]));
        o.extend(consts);
        o.extend(tuple(vec![]));
        for _ in 0..3 {
            o.extend(tuple(vec![]));
        }
        o.extend(string("f"));
        o.extend(string("m"));
        o.extend(1i32.to_le_bytes());
        o.extend(bytes(b""));
        o
    }
}

use marshal as m;

fn consts_of(strings: &[&str], children: &[Vec<u8>]) -> Vec<u8> {
    let mut items: Vec<Vec<u8>> = strings.iter().map(|s| m::string(s)).collect();
    items.extend(children.iter().cloned());
    items.push(m::none());
    m::tuple(items)
}

/// A code object as Python 3.8 to 3.10 store it.
pub fn code_38(name: &str, file: &str, line: i32, names: &[&str], strings: &[&str], children: &[Vec<u8>]) -> Vec<u8> {
    let mut o = vec![b'c'];
    for v in [1i32, 0, 0, 2, 3, 64] {
        o.extend(v.to_le_bytes());
    }
    o.extend(m::bytes(&[0; 4]));
    o.extend(consts_of(strings, children));
    o.extend(m::tuple(names.iter().map(|n| m::string(n)).collect()));
    for _ in 0..3 {
        o.extend(m::tuple(vec![]));
    }
    o.extend(m::string(file));
    o.extend(m::string(name));
    o.extend(line.to_le_bytes());
    o.extend(m::bytes(b"\x01\x02"));
    o
}

/// A code object as Python 3.11 to 3.13 store it.
pub fn code_311(name: &str, qualname: &str, file: &str, line: i32, names: &[&str], strings: &[&str], children: &[Vec<u8>]) -> Vec<u8> {
    let mut o = vec![b'c'];
    for v in [1i32, 0, 0, 3, 64] {
        o.extend(v.to_le_bytes());
    }
    o.extend(m::bytes(&[0; 4]));
    o.extend(consts_of(strings, children));
    o.extend(m::tuple(names.iter().map(|n| m::string(n)).collect()));
    o.extend(m::tuple(vec![]));
    o.extend(m::bytes(b""));
    o.extend(m::string(file));
    o.extend(m::string(name));
    o.extend(m::string(qualname));
    o.extend(line.to_le_bytes());
    o.extend(m::bytes(b"\x01\x02"));
    o.extend(m::bytes(b""));
    o
}

/// A 16-byte-header `.pyc` around `body`.
pub fn pyc(magic: u16, flags: u32, rest: [u8; 8], body: &[u8]) -> Vec<u8> {
    let mut o = magic.to_le_bytes().to_vec();
    o.extend([0x0d, 0x0a]);
    o.extend(flags.to_le_bytes());
    o.extend(rest);
    o.extend(body);
    o
}

fn zlib(b: &[u8]) -> Vec<u8> {
    miniz_oxide::deflate::compress_to_vec_zlib(b, 6)
}

// ---------------------------------------------------------------------------------------------
// Carriers.

/// A thin 64-bit Mach-O with `payload` in one section.
pub fn macho_section(segment: &str, section: &str, payload: &[u8]) -> Vec<u8> {
    let off = 0x1000usize;
    let mut o = Vec::new();
    for v in [0xfeed_facfu32, 0x0100_000c, 0, 2, 1, 72 + 80, 0, 0] {
        o.extend(v.to_le_bytes());
    }
    o.extend(0x19u32.to_le_bytes());
    o.extend((72u32 + 80).to_le_bytes());
    let mut name = [0u8; 16];
    name[..segment.len()].copy_from_slice(segment.as_bytes());
    o.extend(name);
    for v in [0x1_0000_0000u64, payload.len() as u64, off as u64, payload.len() as u64] {
        o.extend(v.to_le_bytes());
    }
    for v in [1u32, 1, 1, 0] {
        o.extend(v.to_le_bytes());
    }
    let mut sect = [0u8; 16];
    sect[..section.len()].copy_from_slice(section.as_bytes());
    o.extend(sect);
    o.extend(name);
    for v in [0x1_0000_0000u64, payload.len() as u64] {
        o.extend(v.to_le_bytes());
    }
    for v in [off as u32, 0, 0, 0, 0, 0, 0, 0] {
        o.extend(v.to_le_bytes());
    }
    o.resize(off, 0);
    o.extend(payload);
    o
}

/// A universal Mach-O holding these slices.
pub fn macho_universal(slices: &[Vec<u8>]) -> Vec<u8> {
    let mut o = 0xcafe_babeu32.to_be_bytes().to_vec();
    o.extend((slices.len() as u32).to_be_bytes());
    let mut at = 0x4000usize;
    for s in slices {
        for v in [0x0100_000cu32, 0, at as u32, s.len() as u32, 14] {
            o.extend(v.to_be_bytes());
        }
        at += s.len().div_ceil(0x4000) * 0x4000;
    }
    for s in slices {
        o.resize(o.len().div_ceil(0x4000).max(1) * 0x4000, 0);
        o.extend(s);
    }
    o
}

fn elf_header(phnum: u16, shoff: u64, shnum: u16, shstrndx: u16) -> Vec<u8> {
    let mut o = vec![0x7f, b'E', b'L', b'F', 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0];
    o.extend(3u16.to_le_bytes());
    o.extend(62u16.to_le_bytes());
    o.extend(1u32.to_le_bytes());
    o.extend(0u64.to_le_bytes());
    o.extend(if phnum > 0 { 64u64 } else { 0 }.to_le_bytes());
    o.extend(shoff.to_le_bytes());
    o.extend(0u32.to_le_bytes());
    for v in [64u16, 56, phnum, 64, shnum, shstrndx] {
        o.extend(v.to_le_bytes());
    }
    o
}

/// A 64-bit ELF with `payload` in a section called `name`.
pub fn elf_section(name: &str, payload: &[u8]) -> Vec<u8> {
    let mut strtab = vec![0u8];
    let name_at = strtab.len() as u32;
    strtab.extend(name.as_bytes());
    strtab.push(0);
    let strtab_name = strtab.len() as u32;
    strtab.extend(b".shstrtab\0");
    let data_off = 64u64;
    let str_off = data_off + payload.len() as u64;
    let shoff = str_off + strtab.len() as u64;
    let mut o = elf_header(0, shoff, 3, 2);
    o.extend(payload);
    o.extend(&strtab);
    o.extend([0u8; 64]);
    let section = |name: u32, kind: u32, off: u64, size: u64| {
        let mut s = Vec::new();
        s.extend(name.to_le_bytes());
        s.extend(kind.to_le_bytes());
        for v in [0u64, 0, off, size] {
            s.extend(v.to_le_bytes());
        }
        s.extend([0u8; 8]);
        s.extend(1u64.to_le_bytes());
        s.extend(0u64.to_le_bytes());
        s
    };
    o.extend(section(name_at, 1, data_off, payload.len() as u64));
    o.extend(section(strtab_name, 3, str_off, strtab.len() as u64));
    o
}

/// A 64-bit ELF with `desc` in a `PT_NOTE` segment whose note is owned by `owner`, after another note.
pub fn elf_note(owner: &str, desc: &[u8]) -> Vec<u8> {
    let note = |owner: &str, desc: &[u8]| {
        let mut n = Vec::new();
        n.extend((owner.len() as u32 + 1).to_le_bytes());
        n.extend((desc.len() as u32).to_le_bytes());
        n.extend(1u32.to_le_bytes());
        n.extend(owner.as_bytes());
        n.push(0);
        n.resize(n.len().div_ceil(4) * 4, 0);
        n.extend(desc);
        n.resize(n.len().div_ceil(4) * 4, 0);
        n
    };
    let body = [note("GNU", &[1, 2, 3, 4, 5]), note(owner, desc)].concat();
    let mut o = elf_header(1, 0, 0, 0);
    o.extend(4u32.to_le_bytes());
    o.extend(4u32.to_le_bytes());
    for v in [120u64, 0, 0, body.len() as u64, body.len() as u64, 4] {
        o.extend(v.to_le_bytes());
    }
    o.extend(body);
    o
}

fn pe_with_section(name: &str, rva: u32, data: &[u8], resource_dir: Option<(u32, u32)>) -> Vec<u8> {
    let mut o = vec![0u8; 0x80];
    o[0] = b'M';
    o[1] = b'Z';
    o[0x3c] = 0x80;
    o.extend(b"PE\0\0");
    o.extend(0x8664u16.to_le_bytes());
    o.extend(1u16.to_le_bytes());
    o.extend([0u8; 12]);
    o.extend(240u16.to_le_bytes());
    o.extend(0x22u16.to_le_bytes());
    let mut opt = vec![0u8; 240];
    opt[0] = 0x0b;
    opt[1] = 0x02;
    opt[32..36].copy_from_slice(&0x1000u32.to_le_bytes());
    opt[36..40].copy_from_slice(&0x200u32.to_le_bytes());
    opt[56..60].copy_from_slice(&0x10_0000u32.to_le_bytes());
    opt[60..64].copy_from_slice(&0x400u32.to_le_bytes());
    opt[108..112].copy_from_slice(&16u32.to_le_bytes());
    if let Some((dir_rva, size)) = resource_dir {
        opt[112 + 16..112 + 20].copy_from_slice(&dir_rva.to_le_bytes());
        opt[112 + 20..112 + 24].copy_from_slice(&size.to_le_bytes());
    }
    o.extend(opt);
    let mut n = [0u8; 8];
    n[..name.len()].copy_from_slice(name.as_bytes());
    o.extend(n);
    for v in [data.len() as u32, rva, data.len() as u32, 0x400, 0, 0, 0] {
        o.extend(v.to_le_bytes());
    }
    o.extend(0x4000_0040u32.to_le_bytes());
    o.resize(0x400, 0);
    o.extend(data);
    o
}

/// A 64-bit PE with `payload` in a section called `name`.
pub fn pe_section(name: &str, payload: &[u8]) -> Vec<u8> {
    pe_with_section(name, 0x1000, payload, None)
}

/// A 64-bit PE with `payload` as an `RT_RCDATA` resource called `name`.
pub fn pe_rcdata(name: &str, payload: &[u8]) -> Vec<u8> {
    let rva = 0x1000u32;
    let dir = |named: u16, ids: u16| {
        let mut d = vec![0u8; 12];
        d.extend(named.to_le_bytes());
        d.extend(ids.to_le_bytes());
        d
    };
    let mut r = Vec::new();
    r.extend(dir(0, 1));
    r.extend(10u32.to_le_bytes());
    r.extend(0x8000_0018u32.to_le_bytes());
    r.extend(dir(1, 0));
    let name_at: u32 = 0x60;
    r.extend((0x8000_0000 | name_at).to_le_bytes());
    r.extend(0x8000_0030u32.to_le_bytes());
    r.extend(dir(0, 1));
    r.extend(0x409u32.to_le_bytes());
    r.extend(0x48u32.to_le_bytes());
    let data_at = 0x100u32;
    r.extend((rva + data_at).to_le_bytes());
    r.extend((payload.len() as u32).to_le_bytes());
    r.extend([0u8; 8]);
    r.resize(name_at as usize, 0);
    r.extend((name.encode_utf16().count() as u16).to_le_bytes());
    for u in name.encode_utf16() {
        r.extend(u.to_le_bytes());
    }
    r.resize(data_at as usize, 0);
    r.extend(payload);
    let size = r.len() as u32;
    pe_with_section(".rsrc", rva, &r, Some((rva, size)))
}

// ---------------------------------------------------------------------------------------------
// Bun.

/// One module of a Bun graph.
#[derive(Clone)]
pub struct BunModule<'a> {
    pub name: &'a str,
    pub contents: &'a [u8],
    pub sourcemap: &'a [u8],
    pub bytecode: &'a [u8],
    pub encoding: u8,
    pub loader: u8,
    pub format: u8,
    pub side: u8,
}

/// A JavaScript module as `bun build --compile` stores one.
pub fn bun_module<'a>(name: &'a str, contents: &'a [u8]) -> BunModule<'a> {
    BunModule { name, contents, sourcemap: b"", bytecode: b"", encoding: 1, loader: 1, format: 1, side: 0 }
}

fn bun_put(o: &mut Vec<u8>, b: &[u8]) -> (u32, u32) {
    let at = o.len() as u32;
    o.extend(b);
    o.push(0);
    (at, b.len() as u32)
}

/// A Bun graph, from its first byte to the end of its trailer, with `record` bytes per module
/// (36 or 52) and an offsets block of `offsets` bytes (24 or 32).
pub fn bun_graph(modules: &[BunModule<'_>], entry: u32, exec_argv: &str, record: usize, offsets: usize) -> Vec<u8> {
    let mut o = Vec::new();
    let mut table = Vec::new();
    for md in modules {
        let name = bun_put(&mut o, md.name.as_bytes());
        let contents = bun_put(&mut o, md.contents);
        let sourcemap = if md.sourcemap.is_empty() { (0, 0) } else { bun_put(&mut o, md.sourcemap) };
        let bytecode = if md.bytecode.is_empty() { (0, 0) } else { bun_put(&mut o, md.bytecode) };
        for (a, b) in [name, contents, sourcemap, bytecode] {
            table.extend(a.to_le_bytes());
            table.extend(b.to_le_bytes());
        }
        if record == 52 {
            let origin = bun_put(&mut o, md.name.as_bytes());
            table.extend([0u8; 8]);
            table.extend(origin.0.to_le_bytes());
            table.extend(origin.1.to_le_bytes());
        }
        table.extend([md.encoding, md.loader, md.format, md.side]);
    }
    let argv = bun_put(&mut o, exec_argv.as_bytes());
    let table_at = o.len() as u32;
    o.extend(&table);
    let byte_count = o.len() as u64;
    o.extend(byte_count.to_le_bytes());
    o.extend(table_at.to_le_bytes());
    o.extend((table.len() as u32).to_le_bytes());
    o.extend(entry.to_le_bytes());
    if offsets == 32 {
        o.extend(argv.0.to_le_bytes());
        o.extend(argv.1.to_le_bytes());
        o.extend(7u32.to_le_bytes());
    } else {
        o.extend([0u8; 4]);
    }
    o.extend(b"\n---- Bun! ----\n");
    o
}

/// The sample graph every Bun test starts from.
pub fn bun_sample() -> Vec<u8> {
    bun_graph(
        &[
            BunModule { sourcemap: b"map-bytes", bytecode: b"code-bytes", ..bun_module("/$bunfs/root/app.js", b"console.log('app')") },
            BunModule { encoding: 0, loader: 5, format: 0, side: 1, ..bun_module("/$bunfs/root/logo.png", b"\x89PNG") },
        ],
        0,
        "--smol",
        52,
        32,
    )
}

/// A graph as Bun's section holds it, behind its 8-byte length.
pub fn bun_section_payload(graph: &[u8]) -> Vec<u8> {
    let mut o = (graph.len() as u64).to_le_bytes().to_vec();
    o.extend(graph);
    o
}

/// A program with a graph appended to its end.
pub fn bun_appended(graph: &[u8]) -> Vec<u8> {
    let mut o = b"\x7fELF program bytes".to_vec();
    o.extend(graph);
    o
}

// ---------------------------------------------------------------------------------------------
// Node.

/// What goes into a Node single-executable blob. Flags follow from what's set.
#[derive(Default, Clone)]
pub struct SeaBlob<'a> {
    pub code_path: &'a str,
    pub code: &'a [u8],
    pub code_cache: Option<&'a [u8]>,
    pub assets: &'a [(&'a str, &'a [u8])],
    pub exec_argv: &'a [&'a str],
    pub snapshot: bool,
}

fn sea_string(o: &mut Vec<u8>, b: &[u8]) {
    o.extend((b.len() as u64).to_le_bytes());
    o.extend(b);
}

/// A blob as Node writes it. `layout` is 3 with the exec-argv-extension byte (Node 24), 2 without it,
/// 1 without it and without a code path.
pub fn sea_blob(b: &SeaBlob<'_>, layout: u8) -> Vec<u8> {
    let mut flags = 1u32;
    flags |= u32::from(b.snapshot) << 1;
    flags |= u32::from(b.code_cache.is_some()) << 2;
    flags |= u32::from(!b.assets.is_empty()) << 3;
    flags |= u32::from(!b.exec_argv.is_empty()) << 4;
    let mut o = 0x0143_da20u32.to_le_bytes().to_vec();
    o.extend(flags.to_le_bytes());
    if layout >= 3 {
        o.push(1);
    }
    if layout >= 2 {
        sea_string(&mut o, b.code_path.as_bytes());
    }
    sea_string(&mut o, b.code);
    if let Some(c) = b.code_cache {
        sea_string(&mut o, c);
    }
    if !b.assets.is_empty() {
        o.extend((b.assets.len() as u64).to_le_bytes());
        for (k, v) in b.assets {
            sea_string(&mut o, k.as_bytes());
            sea_string(&mut o, v);
        }
    }
    if !b.exec_argv.is_empty() {
        o.extend((b.exec_argv.len() as u64).to_le_bytes());
        for a in b.exec_argv {
            sea_string(&mut o, a.as_bytes());
        }
    }
    o
}

/// The sample blob every Node test starts from.
pub fn sea_sample() -> Vec<u8> {
    sea_blob(
        &SeaBlob {
            code_path: "/work/hello.js",
            code: b"console.log('sea')",
            code_cache: Some(b"cache"),
            assets: &[("a.txt", b"asset a"), ("dir/b.bin", b"asset b")],
            exec_argv: &["--no-warnings"],
            snapshot: false,
        },
        3,
    )
}

// ---------------------------------------------------------------------------------------------
// .NET.

/// The marker a .NET apphost carries, preceded by the bundle header's offset.
pub const DOTNET_SIGNATURE: [u8; 32] = [
    0x8b, 0x12, 0x02, 0xb9, 0x6a, 0x61, 0x20, 0x38, 0x72, 0x7b, 0x93, 0x02, 0x14, 0xd7, 0xa0, 0x32, 0x13, 0xf5, 0xb9, 0xe6, 0xef, 0xae, 0x33, 0x18, 0xee, 0x3b,
    0x2d, 0xce, 0x24, 0xb3, 0x6a, 0xae,
];

fn dotnet_string(o: &mut Vec<u8>, s: &str) {
    let mut n = s.len();
    while n >= 0x80 {
        o.push((n as u8 & 0x7f) | 0x80);
        n >>= 7;
    }
    o.push(n as u8);
    o.extend(s.as_bytes());
}

/// A bundled apphost. Members are (path, type byte, contents); with `major` 6 a member at least 64
/// bytes long is compressed.
pub fn dotnet_bundle(major: u32, files: &[(&str, u8, &[u8])]) -> Vec<u8> {
    let mut o = b"MZ apphost ".to_vec();
    o.extend(0u64.to_le_bytes());
    let header_slot = o.len() - 8;
    o.extend(DOTNET_SIGNATURE);
    let mut table = Vec::new();
    for (path, kind, body) in files {
        let at = o.len() as u64;
        let compressed = major >= 6 && body.len() >= 64;
        let stored = if compressed { miniz_oxide::deflate::compress_to_vec(body, 6) } else { body.to_vec() };
        o.extend(&stored);
        table.extend(at.to_le_bytes());
        table.extend((body.len() as u64).to_le_bytes());
        if major >= 6 {
            table.extend((if compressed { stored.len() as u64 } else { 0 }).to_le_bytes());
        }
        table.push(*kind);
        dotnet_string(&mut table, path);
    }
    let header_at = o.len() as u64;
    o[header_slot..header_slot + 8].copy_from_slice(&header_at.to_le_bytes());
    o.extend(major.to_le_bytes());
    o.extend(0u32.to_le_bytes());
    o.extend((files.len() as i32).to_le_bytes());
    dotnet_string(&mut o, "bundle-id-1");
    if major >= 2 {
        for v in [0u64, 0, 0, 0, 1] {
            o.extend(v.to_le_bytes());
        }
    }
    o.extend(table);
    o
}

/// The sample bundle every .NET test starts from.
pub fn dotnet_sample() -> Vec<u8> {
    dotnet_bundle(6, &[("App.dll", 1, &[0x5a; 200]), ("App.deps.json", 3, b"{}"), ("sub/native.so", 2, b"native")])
}

// ---------------------------------------------------------------------------------------------
// PyInstaller.

/// The magic in front of a PyInstaller cookie.
pub const MEI_MAGIC: [u8; 8] = *b"MEI\x0c\x0b\x0a\x0b\x0e";

/// One member of a CArchive: name, type code, contents, compress it or not.
pub type MeiMember<'a> = (&'a str, u8, &'a [u8], bool);

/// A program with a CArchive at its end. `new_cookie` picks the 88-byte cookie over the 24-byte one.
pub fn pyinstaller(members: &[MeiMember<'_>], new_cookie: bool, pyver: i32) -> Vec<u8> {
    let prefix = b"\x7fELF bootloader with its own copy of MEI\x0c\x0b\x0a\x0b\x0e inside".to_vec();
    let mut pkg = Vec::new();
    let mut toc = Vec::new();
    for (name, kind, body, compress) in members {
        let stored = if *compress { zlib(body) } else { body.to_vec() };
        let at = pkg.len() as u32;
        pkg.extend(&stored);
        let padded = (name.len() + 1).div_ceil(16) * 16;
        toc.extend(((18 + padded) as u32).to_be_bytes());
        toc.extend(at.to_be_bytes());
        toc.extend((stored.len() as u32).to_be_bytes());
        toc.extend((body.len() as u32).to_be_bytes());
        toc.push(u8::from(*compress));
        toc.push(*kind);
        toc.extend(name.as_bytes());
        toc.resize(toc.len() + padded - name.len(), 0);
    }
    let toc_at = pkg.len() as u32;
    pkg.extend(&toc);
    let cookie = if new_cookie { 88 } else { 24 };
    let total = (pkg.len() + cookie) as u32;
    pkg.extend(MEI_MAGIC);
    pkg.extend(total.to_be_bytes());
    pkg.extend(toc_at.to_be_bytes());
    pkg.extend((toc.len() as u32).to_be_bytes());
    pkg.extend(pyver.to_be_bytes());
    if new_cookie {
        let mut lib = [0u8; 64];
        lib[..10].copy_from_slice(b"Python.dll");
        pkg.extend(lib);
    }
    [prefix, pkg].concat()
}

/// A PYZ archive holding marshalled code for `(module, kind, code)`, its table a list of pairs or,
/// as older versions wrote it, a dict.
pub fn pyz(magic: u16, modules: &[(&str, i32, &[u8])], as_dict: bool, compress: bool) -> Vec<u8> {
    let mut o = b"PYZ\0".to_vec();
    o.extend(magic.to_le_bytes());
    o.extend([0x0d, 0x0a]);
    o.extend([0u8; 8]);
    let mut items = Vec::new();
    for (name, kind, code) in modules {
        let stored = if compress { zlib(code) } else { code.to_vec() };
        let at = o.len() as i32;
        o.extend(&stored);
        items.push((name.to_string(), m::tuple(vec![m::int(*kind), m::int(at), m::int(stored.len() as i32)])));
    }
    let toc_at = o.len() as i32;
    o[8..12].copy_from_slice(&toc_at.to_be_bytes());
    if as_dict {
        o.extend(m::dict(items.into_iter().map(|(n, v)| (m::string(&n), v)).collect()));
    } else {
        o.extend(m::list(items.into_iter().map(|(n, v)| m::tuple(vec![m::string(&n), v])).collect()));
    }
    o
}

/// The sample program every PyInstaller test starts from: Python 3.12, a script, a library and a PYZ.
pub fn pyinstaller_sample() -> Vec<u8> {
    let code = code_311("<module>", "<module>", "pkg/util.py", 1, &["os"], &["util doc"], &[]);
    let pyz = pyz(3531, &[("pkg", 1, &code), ("pkg.util", 0, &code)], false, true);
    pyinstaller(
        &[
            ("struct", b'm', &[0xaa; 100], true),
            ("main", b's', &code, true),
            ("libz.so.1", b'b', b"native", false),
            ("PYZ-00.pyz", b'z', &pyz, false),
            ("pyi-runtime-tmpdir", b'o', b"", false),
        ],
        true,
        312,
    )
}
