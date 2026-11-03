//! Synthetic samples for the format tools that need no open target: Go programs (ELF with inline build
//! information and a Go 1.20 function table; Mach-O with pointer-encoded build information and a
//! Go 1.16 table that must be found by scanning), a hand-assembled WebAssembly module, and EVM
//! runtime bytecode with a compiler-style selector dispatcher and a metadata tail.

use crate::Buf;

pub const GO_VERSION: &str = "go1.21.5";
/// Function names and their offsets from the start of the text section.
pub const GO_FUNCS: &[(&str, u64)] = &[("main.main", 0x00), ("main.helper", 0x40), ("runtime.gopark", 0x80), ("github.com/acme/lib.(*Client).Do", 0xc0)];
/// Address of `.text` in the ELF sample.
pub const GO_TEXT_VA: u64 = 0x40_1000;

const SENTINEL_START: [u8; 16] = [0x30, 0x77, 0xaf, 0x0c, 0x92, 0x74, 0x08, 0x02, 0x41, 0xe1, 0xc1, 0x07, 0xe6, 0xd6, 0x18, 0xe6];
const SENTINEL_END: [u8; 16] = [0xf9, 0x32, 0x43, 0x31, 0x86, 0x18, 0x20, 0x72, 0x00, 0x82, 0x42, 0x10, 0x41, 0x16, 0xd8, 0xf2];

/// The module text both samples embed (between the sentinels).
pub fn go_module_text() -> String {
    [
        "path\texample.com/hello",
        "mod\texample.com/hello\t(devel)\t",
        "dep\tgithub.com/acme/lib\tv1.2.3\th1:abc=",
        "dep\tgolang.org/x/text\tv0.14.0\th1:def=",
        "=>\t../local/text\t\t",
        "build\t-compiler=gc",
        "build\t-ldflags=\"-s -w \\\"x\\\"\"",
        "build\tCGO_ENABLED=0",
        "build\tGOARCH=amd64",
        "",
    ]
    .join("\n")
}

fn uvarint(mut v: u64, out: &mut Vec<u8>) {
    loop {
        let b = (v & 0x7f) as u8;
        v >>= 7;
        if v == 0 {
            out.push(b);
            return;
        }
        out.push(b | 0x80);
    }
}

fn sentinelled(text: &str) -> Vec<u8> {
    let mut m = SENTINEL_START.to_vec();
    m.extend_from_slice(text.as_bytes());
    m.extend_from_slice(&SENTINEL_END);
    m
}

/// A Go 1.18+ inline build information block.
pub fn go_buildinfo_inline(version: &str, text: &str) -> Vec<u8> {
    let mut b = b"\xff Go buildinf:".to_vec();
    b.push(8);
    b.push(2);
    b.resize(32, 0);
    uvarint(version.len() as u64, &mut b);
    b.extend_from_slice(version.as_bytes());
    let m = sentinelled(text);
    uvarint(m.len() as u64, &mut b);
    b.extend_from_slice(&m);
    b
}

/// A Go 1.20+ function table (little-endian, 8-byte pointers) for functions at `text_start + off`.
pub fn pclntab_120(text_start: u64, funcs: &[(&str, u64)]) -> Vec<u8> {
    let mut names = Vec::new();
    let mut name_offs = Vec::new();
    for (n, _) in funcs {
        name_offs.push(names.len() as u32);
        names.extend_from_slice(n.as_bytes());
        names.push(0);
    }
    let header = 72usize;
    let funcname = header;
    let mut functab = funcname + names.len();
    functab = (functab + 7) & !7;
    let nf = funcs.len();
    let ftab_size = (nf + 1) * 8;
    let funcs_start = ftab_size; // relative to functab
    let func_size = 40usize;
    let total = functab + ftab_size + nf * func_size;
    let mut b = Buf::with_len(total);
    b.put(0, &[0xf1, 0xff, 0xff, 0xff, 0, 0, 1, 8]);
    b.u64(8, nf as u64);
    b.u64(16, 0);
    b.u64(24, text_start);
    b.u64(32, funcname as u64);
    b.u64(40, 0);
    b.u64(48, 0);
    b.u64(56, 0);
    b.u64(64, functab as u64);
    b.put(funcname, &names);
    for (i, (_, off)) in funcs.iter().enumerate() {
        let fo = funcs_start + i * func_size;
        b.u32(functab + i * 8, *off as u32);
        b.u32(functab + i * 8 + 4, fo as u32);
        b.u32(functab + fo, *off as u32);
        b.u32(functab + fo + 4, name_offs[i]);
    }
    b.u32(functab + nf * 8, 0x100);
    b.into_vec()
}

/// A Go 1.16 function table (little-endian, 8-byte pointers).
pub fn pclntab_116(text_start: u64, funcs: &[(&str, u64)]) -> Vec<u8> {
    let mut names = Vec::new();
    let mut name_offs = Vec::new();
    for (n, _) in funcs {
        name_offs.push(names.len() as u32);
        names.extend_from_slice(n.as_bytes());
        names.push(0);
    }
    let header = 64usize;
    let funcname = header;
    let functab = (funcname + names.len() + 7) & !7;
    let nf = funcs.len();
    let ftab_size = (nf + 1) * 16;
    let func_size = 48usize;
    let total = functab + ftab_size + nf * func_size;
    let mut b = Buf::with_len(total);
    b.put(0, &[0xfa, 0xff, 0xff, 0xff, 0, 0, 1, 8]);
    b.u64(8, nf as u64);
    b.u64(24, funcname as u64);
    b.u64(56, functab as u64);
    b.put(funcname, &names);
    for (i, (_, off)) in funcs.iter().enumerate() {
        let fo = ftab_size + i * func_size;
        b.u64(functab + i * 16, text_start + off);
        b.u64(functab + i * 16 + 8, fo as u64);
        b.u64(functab + fo, text_start + off);
        b.u32(functab + fo + 8, name_offs[i]);
    }
    b.u64(functab + nf * 16, text_start + 0x100);
    b.into_vec()
}

/// A Go-like ELF64 x86-64 program: `.text`, `.gopclntab` (Go 1.20 layout), `.go.buildinfo`
/// (inline encoding).
pub fn go_elf() -> Vec<u8> {
    let pcln = pclntab_120(GO_TEXT_VA, GO_FUNCS);
    let bi = go_buildinfo_inline(GO_VERSION, &go_module_text());
    let text_off = 0x1000usize;
    let pcln_off = 0x1100usize;
    let bi_off = 0x3000usize;
    let shstr_off = bi_off + bi.len();
    let shstr = b"\0.text\0.gopclntab\0.go.buildinfo\0.shstrtab\0";
    let sh_off = (shstr_off + shstr.len() + 7) & !7;
    let mut b = Buf::with_len(sh_off + 5 * 64);
    b.put(0, b"\x7fELF\x02\x01\x01");
    b.u16(16, 2);
    b.u16(18, 62);
    b.u32(20, 1);
    b.u64(24, GO_TEXT_VA);
    b.u64(32, 0x40);
    b.u64(40, sh_off as u64);
    b.u16(52, 64);
    b.u16(54, 56);
    b.u16(56, 2);
    b.u16(58, 64);
    b.u16(60, 5);
    b.u16(62, 4);
    // PT_LOAD r-x: text + pclntab
    let ph = |b: &mut Buf, at: usize, flags: u32, off: usize, va: u64, size: usize| {
        b.u32(at, 1);
        b.u32(at + 4, flags);
        b.u64(at + 8, off as u64);
        b.u64(at + 16, va);
        b.u64(at + 24, va);
        b.u64(at + 32, size as u64);
        b.u64(at + 40, size as u64);
        b.u64(at + 48, 0x1000);
    };
    ph(&mut b, 0x40, 5, text_off, GO_TEXT_VA, pcln_off + pcln.len() - text_off);
    ph(&mut b, 0x40 + 56, 6, bi_off, 0x40_3000, bi.len());
    b.put(text_off, &[0xc3; 0x100]);
    b.put(pcln_off, &pcln);
    b.put(bi_off, &bi);
    b.put(shstr_off, shstr);
    let sh = |b: &mut Buf, i: usize, name: u32, ty: u32, flags: u64, addr: u64, off: usize, size: usize| {
        let at = sh_off + i * 64;
        b.u32(at, name);
        b.u32(at + 4, ty);
        b.u64(at + 8, flags);
        b.u64(at + 16, addr);
        b.u64(at + 24, off as u64);
        b.u64(at + 32, size as u64);
        b.u64(at + 48, 1);
    };
    sh(&mut b, 1, 1, 1, 6, GO_TEXT_VA, text_off, 0x100);
    sh(&mut b, 2, 7, 1, 2, GO_TEXT_VA + (pcln_off - text_off) as u64, pcln_off, pcln.len());
    sh(&mut b, 3, 18, 1, 3, 0x40_3000, bi_off, bi.len());
    sh(&mut b, 4, 32, 3, 0, 0, shstr_off, shstr.len());
    b.into_vec()
}

/// A Go-like Mach-O 64 (x86-64) program with pointer-encoded build information (Go 1.17) in
/// `__DATA,__go_buildinfo` and a Go 1.16 function table hidden in `__TEXT,__rodata`.
pub fn go_macho() -> Vec<u8> {
    const BASE: u64 = 0x1_0000_0000;
    let text_va = BASE + 0x1000;
    let pcln = pclntab_116(text_va, GO_FUNCS);
    assert!(pcln.len() < 0x800);
    let mut b = Buf::with_len(0x3000);
    // __DATA contents at file 0x2000 / VA BASE+0x2000.
    let data_va = BASE + 0x2000;
    let version = b"go1.17.13";
    let module = sentinelled(&go_module_text());
    let mut d = Buf::with_len(0x1000);
    d.put(0, b"\xff Go buildinf:");
    d.u8(14, 8);
    d.u8(15, 0);
    d.u64(16, data_va + 0x40); // -> version string header
    d.u64(24, data_va + 0x50); // -> module string header
    d.u64(0x40, data_va + 0x80);
    d.u64(0x48, version.len() as u64);
    d.u64(0x50, data_va + 0x100);
    d.u64(0x58, module.len() as u64);
    d.put(0x80, version);
    d.put(0x100, &module);
    b.put(0x2000, &d.into_vec());
    b.put(0x1000, &[0xc3; 0x100]);
    b.put(0x1800, &pcln);
    // Load commands.
    let mut at = 32usize;
    let mut ncmds = 0u32;
    let seg = |b: &mut Buf, at: &mut usize, name: &str, vm: u64, vmsize: u64, off: u64, fsize: u64, prot: u32, sects: &[(&str, u64, u64, u32)]| {
        let size = 72 + 80 * sects.len();
        b.u32(*at, 0x19);
        b.u32(*at + 4, size as u32);
        b.put(*at + 8, name.as_bytes());
        b.u64(*at + 24, vm);
        b.u64(*at + 32, vmsize);
        b.u64(*at + 40, off);
        b.u64(*at + 48, fsize);
        b.u32(*at + 56, prot);
        b.u32(*at + 60, prot);
        b.u32(*at + 64, sects.len() as u32);
        for (i, (sname, addr, ssize, soff)) in sects.iter().enumerate() {
            let s = *at + 72 + 80 * i;
            b.put(s, sname.as_bytes());
            b.put(s + 16, name.as_bytes());
            b.u64(s + 32, *addr);
            b.u64(s + 40, *ssize);
            b.u32(s + 48, *soff);
        }
        *at += size;
    };
    seg(&mut b, &mut at, "__PAGEZERO", 0, BASE, 0, 0, 0, &[]);
    ncmds += 1;
    seg(&mut b, &mut at, "__TEXT", BASE, 0x2000, 0, 0x2000, 5, &[("__text", text_va, 0x100, 0x1000), ("__rodata", BASE + 0x1800, pcln.len() as u64, 0x1800)]);
    ncmds += 1;
    seg(&mut b, &mut at, "__DATA", data_va, 0x1000, 0x2000, 0x1000, 3, &[("__go_buildinfo", data_va, 0x200 + module.len() as u64, 0x2000)]);
    ncmds += 1;
    b.put(0, &[0xcf, 0xfa, 0xed, 0xfe]);
    b.u32(4, 0x0100_0007);
    b.u32(8, 3);
    b.u32(12, 2);
    b.u32(16, ncmds);
    b.u32(20, (at - 32) as u32);
    b.into_vec()
}

// ---------------------------------------------------------------------------------------------
// WebAssembly

fn leb(mut v: u32, out: &mut Vec<u8>) {
    loop {
        let b = (v & 0x7f) as u8;
        v >>= 7;
        if v == 0 {
            out.push(b);
            return;
        }
        out.push(b | 0x80);
    }
}

fn name(s: &str, out: &mut Vec<u8>) {
    leb(s.len() as u32, out);
    out.extend_from_slice(s.as_bytes());
}

fn section(id: u8, body: &[u8], out: &mut Vec<u8>) {
    out.push(id);
    leb(body.len() as u32, out);
    out.extend_from_slice(body);
}

fn custom(sname: &str, body: &[u8], out: &mut Vec<u8>) {
    let mut c = Vec::new();
    name(sname, &mut c);
    c.extend_from_slice(body);
    section(0, &c, out);
}

/// A small valid module: imports `env.log(i32)`, defines `add(i32,i32)->i32` and `_start`,
/// one memory, one mutable global, one data segment, exports `add`, `memory` and `_start`, and
/// carries `name`, `producers` and `sourceMappingURL` custom sections.
pub fn wasm_module() -> Vec<u8> {
    let mut m = b"\0asm\x01\0\0\0".to_vec();
    section(1, &[3, 0x60, 2, 0x7f, 0x7f, 1, 0x7f, 0x60, 0, 0, 0x60, 1, 0x7f, 0], &mut m);
    let mut imp = vec![1];
    name("env", &mut imp);
    name("log", &mut imp);
    imp.extend_from_slice(&[0, 2]);
    section(2, &imp, &mut m);
    section(3, &[2, 0, 1], &mut m);
    section(5, &[1, 0, 1], &mut m);
    section(6, &[1, 0x7f, 1, 0x41, 42, 0x0b], &mut m);
    let mut exp = vec![3];
    name("add", &mut exp);
    exp.extend_from_slice(&[0, 1]);
    name("memory", &mut exp);
    exp.extend_from_slice(&[2, 0]);
    name("_start", &mut exp);
    exp.extend_from_slice(&[0, 2]);
    section(7, &exp, &mut m);
    let add = [0u8, 0x20, 0, 0x20, 1, 0x6a, 0x0b];
    let start = [0u8, 0x41, 7, 0x10, 0, 0x0b];
    let mut code = vec![2, add.len() as u8];
    code.extend_from_slice(&add);
    code.push(start.len() as u8);
    code.extend_from_slice(&start);
    section(10, &code, &mut m);
    section(11, &[1, 0, 0x41, 0, 0x0b, 2, b'h', b'i'], &mut m);
    // name section
    let mut n = Vec::new();
    let mut module_name = Vec::new();
    name("demo", &mut module_name);
    n.push(0);
    leb(module_name.len() as u32, &mut n);
    n.extend_from_slice(&module_name);
    let mut fnames = vec![3];
    for (i, f) in ["log", "add", "_start"].iter().enumerate() {
        leb(i as u32, &mut fnames);
        name(f, &mut fnames);
    }
    n.push(1);
    leb(fnames.len() as u32, &mut n);
    n.extend_from_slice(&fnames);
    custom("name", &n, &mut m);
    let mut p = vec![2];
    name("language", &mut p);
    p.push(1);
    name("Rust", &mut p);
    name("", &mut p);
    name("processed-by", &mut p);
    p.push(1);
    name("rustc", &mut p);
    name("1.80.0", &mut p);
    custom("producers", &p, &mut m);
    let mut s = Vec::new();
    name("demo.wasm.map", &mut s);
    custom("sourceMappingURL", &s, &mut m);
    let mut tf = vec![1, b'+'];
    name("mutable-globals", &mut tf);
    custom("target_features", &tf, &mut m);
    m
}

/// JavaScript glue that loads the module.
pub const WASM_GLUE: &str =
    "const imports = { env: { log: (x) => console.log(x) } };\nfetch(\"./demo.wasm\").then(r => WebAssembly.instantiateStreaming(r, imports));\n";

// ---------------------------------------------------------------------------------------------
// EVM

/// Selectors in the dispatcher sample; the third is payable.
pub const EVM_SELECTORS: [u32; 3] = [0xa905_9cbb, 0x70a0_8231, 0xd0e3_0db0];

/// Runtime bytecode with a compiler-style dispatcher, a fallback that reverts, two non-payable
/// functions (CALLVALUE check), one payable function, and a CBOR metadata tail (ipfs + solc 0.8.19).
/// Returns (bytecode, jump destinations of the three functions).
pub fn evm_runtime() -> (Vec<u8>, [usize; 3]) {
    let mut c: Vec<u8> = vec![0x60, 0x80, 0x60, 0x40, 0x52];
    // if calldatasize < 4 goto fallback
    c.extend_from_slice(&[0x60, 0x04, 0x36, 0x10, 0x61, 0, 0]);
    let fb_patch = c.len() - 2;
    c.push(0x57);
    c.extend_from_slice(&[0x60, 0x00, 0x35, 0x60, 0xe0, 0x1c]);
    let mut patches = Vec::new();
    for sel in EVM_SELECTORS {
        c.push(0x80);
        c.push(0x63);
        c.extend_from_slice(&sel.to_be_bytes());
        c.extend_from_slice(&[0x14, 0x61, 0, 0]);
        patches.push(c.len() - 2);
        c.push(0x57);
    }
    let fallback = c.len();
    c.extend_from_slice(&[0x5b, 0x60, 0x00, 0x80, 0xfd]);
    let mut dests = [0usize; 3];
    for (i, dest) in dests.iter_mut().enumerate() {
        *dest = c.len();
        if i < 2 {
            // JUMPDEST CALLVALUE DUP1 ISZERO PUSH2 ok JUMPI PUSH1 0 DUP1 REVERT JUMPDEST POP STOP
            c.extend_from_slice(&[0x5b, 0x34, 0x80, 0x15, 0x61, 0, 0]);
            let ok_patch = c.len() - 2;
            c.extend_from_slice(&[0x57, 0x60, 0x00, 0x80, 0xfd]);
            let ok = c.len();
            c.extend_from_slice(&[0x5b, 0x50, 0x00]);
            c[ok_patch..ok_patch + 2].copy_from_slice(&(ok as u16).to_be_bytes());
        } else {
            c.extend_from_slice(&[0x5b, 0x60, 0x01, 0x60, 0x00, 0x55, 0x00]);
        }
    }
    c[fb_patch..fb_patch + 2].copy_from_slice(&(fallback as u16).to_be_bytes());
    for (p, d) in patches.iter().zip(dests) {
        c[*p..*p + 2].copy_from_slice(&(d as u16).to_be_bytes());
    }
    c.push(0xfe);
    let mut meta = vec![0xa2, 0x64, b'i', b'p', b'f', b's', 0x58, 0x22, 0x12, 0x20];
    meta.extend((0..32u8).map(|i| i.wrapping_mul(7)));
    meta.extend_from_slice(&[0x64, b's', b'o', b'l', b'c', 0x43, 0x00, 0x08, 0x13]);
    let len = meta.len() as u16;
    c.extend_from_slice(&meta);
    c.extend_from_slice(&len.to_be_bytes());
    (c, dests)
}

/// Bytecode as `0x`-prefixed lowercase hex.
pub fn to_hex(b: &[u8]) -> String {
    let mut s = String::from("0x");
    for x in b {
        s.push_str(&format!("{x:02x}"));
    }
    s
}
