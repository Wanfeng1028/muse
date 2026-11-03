//! Test helpers and synthetic sample builders.
//!
//! Every builder writes a tiny but valid container around the same hand-assembled program, so
//! tests can check exact addresses, names and strings:
//!
//! - `main` loads a string, calls the imported `puts` through a pointer slot, calls `helper(5)`
//!   and `dispatch(1)`, and returns the sum;
//! - `helper` has a guarded loop (`if (n > 0) do { … } while (n > 0)`);
//! - `hidden` has a frame prologue but no caller and no symbol (found by prologue scan or
//!   Mach-O function starts); it loads the string `open_settings_panel`;
//! - `dispatch` is a three-way switch through a relative jump table.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::indexing_slicing, clippy::type_complexity, clippy::manual_is_multiple_of)]

pub mod android;
pub mod apple;
pub mod crypto;
pub mod electron;
pub mod firmware;
pub mod flutter;
pub mod formats;
pub mod games;
pub mod java;
pub mod managed;
pub mod packed;
pub mod pcap;
pub mod program_facts;
pub mod sbpf;
pub mod sectionless;
pub mod sqlite;
pub mod wasm_plugin;

/// Offsets of the functions inside the x86-64 code blob.
pub mod x64 {
    pub const MAIN: u64 = 0x00;
    pub const HELPER: u64 = 0x40;
    pub const HIDDEN: u64 = 0x60;
    pub const DISPATCH: u64 = 0x70;
    pub const CODE_SIZE: usize = 0xa0;
}

/// Offsets inside the read-only data blob.
pub mod rodata {
    pub const HELLO: u64 = 0x00;
    pub const SECRET: u64 = 0x10;
    pub const TABLE: u64 = 0x30;
    pub const SIZE: usize = 0x40;
}

pub const HELLO: &str = "Hello, Craft!";
pub const SECRET: &str = "open_settings_panel";

/// Little byte buffer with positioned writes.
#[derive(Debug, Default, Clone)]
pub struct Buf(pub Vec<u8>);

impl Buf {
    pub fn with_len(n: usize) -> Self {
        Buf(vec![0; n])
    }
    fn grow(&mut self, end: usize) {
        if self.0.len() < end {
            self.0.resize(end, 0);
        }
    }
    pub fn put(&mut self, off: usize, b: &[u8]) {
        self.grow(off + b.len());
        self.0[off..off + b.len()].copy_from_slice(b);
    }
    pub fn u8(&mut self, off: usize, v: u8) {
        self.put(off, &[v]);
    }
    pub fn u16(&mut self, off: usize, v: u16) {
        self.put(off, &v.to_le_bytes());
    }
    pub fn u32(&mut self, off: usize, v: u32) {
        self.put(off, &v.to_le_bytes());
    }
    pub fn u64(&mut self, off: usize, v: u64) {
        self.put(off, &v.to_le_bytes());
    }
    pub fn u32be(&mut self, off: usize, v: u32) {
        self.put(off, &v.to_be_bytes());
    }
    pub fn into_vec(self) -> Vec<u8> {
        self.0
    }
}

fn rel32(from_next: u64, to: u64) -> [u8; 4] {
    ((to as i64 - from_next as i64) as i32).to_le_bytes()
}

/// The x86-64 program. `code_va` is where the blob loads, `rodata_va` where [`rodata_blob`] loads,
/// `slot_va` the address of the pointer slot holding `puts`.
pub fn x86_64_code(code_va: u64, rodata_va: u64, slot_va: u64) -> Vec<u8> {
    let mut c = vec![0xccu8; x64::CODE_SIZE];
    let at = |c: &mut Vec<u8>, off: u64, b: &[u8]| c[off as usize..off as usize + b.len()].copy_from_slice(b);
    // main
    let m = x64::MAIN;
    at(&mut c, m, &[0x55, 0x48, 0x89, 0xe5, 0x48, 0x83, 0xec, 0x10]);
    at(&mut c, m + 8, &[0x48, 0x8d, 0x3d]);
    at(&mut c, m + 11, &rel32(code_va + m + 15, rodata_va + rodata::HELLO));
    at(&mut c, m + 15, &[0xff, 0x15]);
    at(&mut c, m + 17, &rel32(code_va + m + 21, slot_va));
    at(&mut c, m + 21, &[0xbf, 5, 0, 0, 0, 0xe8]);
    at(&mut c, m + 27, &rel32(code_va + m + 31, code_va + x64::HELPER));
    at(&mut c, m + 31, &[0x89, 0x45, 0xfc, 0xbf, 1, 0, 0, 0, 0xe8]);
    at(&mut c, m + 40, &rel32(code_va + m + 44, code_va + x64::DISPATCH));
    at(&mut c, m + 44, &[0x03, 0x45, 0xfc, 0xc9, 0xc3]);
    // helper
    let h = x64::HELPER;
    at(&mut c, h, &[0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x85, 0xff, 0x7e, 0x09, 0x01, 0xf8, 0x83, 0xef, 0x01, 0x85, 0xff, 0x7f, 0xf7, 0x5d, 0xc3]);
    // hidden
    let x = x64::HIDDEN;
    at(&mut c, x, &[0x55, 0x48, 0x89, 0xe5, 0x48, 0x8d, 0x05]);
    at(&mut c, x + 7, &rel32(code_va + x + 11, rodata_va + rodata::SECRET));
    at(&mut c, x + 11, &[0x5d, 0xc3]);
    // dispatch
    let d = x64::DISPATCH;
    at(&mut c, d, &[0x83, 0xff, 0x02, 0x77, 0x24, 0x89, 0xff, 0x48, 0x8d, 0x05]);
    at(&mut c, d + 0x0a, &rel32(code_va + d + 0x0e, rodata_va + rodata::TABLE));
    at(&mut c, d + 0x0e, &[0x48, 0x63, 0x0c, 0xb8, 0x48, 0x01, 0xc1, 0xff, 0xe1]);
    at(&mut c, d + 0x17, &[0xb8, 10, 0, 0, 0, 0xc3, 0xb8, 20, 0, 0, 0, 0xc3, 0xb8, 30, 0, 0, 0, 0xc3, 0x31, 0xc0, 0xc3]);
    c
}

/// Addresses of the three switch cases inside `dispatch`.
pub fn dispatch_cases(code_va: u64) -> [u64; 3] {
    let d = code_va + x64::DISPATCH;
    [d + 0x17, d + 0x1d, d + 0x23]
}

/// Strings and the relative jump table used by `dispatch`.
pub fn rodata_blob(code_va: u64, rodata_va: u64) -> Vec<u8> {
    let mut b = Buf::with_len(rodata::SIZE);
    b.put(rodata::HELLO as usize, HELLO.as_bytes());
    b.put(rodata::SECRET as usize, SECRET.as_bytes());
    let table = rodata_va + rodata::TABLE;
    for (i, case) in dispatch_cases(code_va).iter().enumerate() {
        b.u32(rodata::TABLE as usize + i * 4, (*case as i64 - table as i64) as i32 as u32);
    }
    b.into_vec()
}

/// AArch64 program: `main` loads a string with adrp/add, calls `puts` through a GOT slot with
/// adrp/ldr/blr, then `bl helper`; `helper` is `cbz`-guarded.
pub mod a64 {
    pub const MAIN: u64 = 0x00;
    pub const HELPER: u64 = 0x40;
    pub const CODE_SIZE: usize = 0x60;
}

fn adrp(pc: u64, target: u64, rd: u32) -> u32 {
    let imm = ((target & !0xfff) as i64 - (pc & !0xfff) as i64) >> 12;
    let immlo = (imm & 3) as u32;
    let immhi = ((imm >> 2) & 0x7ffff) as u32;
    0x9000_0000 | (immlo << 29) | (immhi << 5) | rd
}

pub fn aarch64_code(code_va: u64, rodata_va: u64, slot_va: u64) -> Vec<u8> {
    let mut words = [0xd503201fu32; a64::CODE_SIZE / 4]; // nop
    let str_va = rodata_va + rodata::HELLO;
    let m = (a64::MAIN / 4) as usize;
    words[m] = 0xa9bf7bfd; // stp x29, x30, [sp, #-16]!
    words[m + 1] = 0x910003fd; // mov x29, sp
    words[m + 2] = adrp(code_va + 8, str_va, 0);
    words[m + 3] = 0x9100_0000 | (((str_va & 0xfff) as u32) << 10); // add x0, x0, #lo12
    words[m + 4] = adrp(code_va + 0x10, slot_va, 16);
    words[m + 5] = 0xf940_0000 | ((((slot_va & 0xfff) / 8) as u32) << 10) | (16 << 5) | 16; // ldr x16, [x16, #lo12]
    words[m + 6] = 0xd63f_0200; // blr x16
    words[m + 7] = 0x5280_00a0; // mov w0, #5
    words[m + 8] = 0x9400_0000 | (((a64::HELPER - 0x20) / 4) as u32 & 0x3ff_ffff); // bl helper
    words[m + 9] = 0xa8c17bfd; // ldp x29, x30, [sp], #16
    words[m + 10] = 0xd65f03c0; // ret
    let h = (a64::HELPER / 4) as usize;
    words[h] = 0x3400_0060; // cbz w0, +12
    words[h + 1] = 0x1100_0400; // add w0, w0, #1
    words[h + 2] = 0xd65f03c0; // ret
    words[h + 3] = 0x5280_0000; // mov w0, #0
    words[h + 4] = 0xd65f03c0; // ret
    words.iter().flat_map(|w| w.to_le_bytes()).collect()
}

// ---------------------------------------------------------------------------------------------
// ELF

pub const ELF_BASE: u64 = 0x400000;
pub const ELF_TEXT_OFF: u64 = 0x180;
pub const ELF_RODATA_OFF: u64 = 0x240;
pub const ELF_DATA_VBASE: u64 = 0x600000;

/// Addresses of an ELF sample.
#[derive(Debug, Clone, Copy)]
pub struct ElfLayout {
    pub code_va: u64,
    pub rodata_va: u64,
    pub got_va: u64,
    pub entry: u64,
}

/// Which program an ELF sample carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ElfArch {
    X86_64,
    Aarch64,
}

/// A dynamically linked ELF64 executable importing `puts` from libc.so.6.
/// With `symbols`, `.symtab` names main, helper and dispatch (never `hidden`).
pub fn elf64(arch: ElfArch, symbols: bool) -> (Vec<u8>, ElfLayout) {
    let code_size = match arch {
        ElfArch::X86_64 => x64::CODE_SIZE,
        ElfArch::Aarch64 => a64::CODE_SIZE,
    } as u64;
    let interp = b"/lib64/ld-linux-x86-64.so.2\0";
    let interp_off = 0x160u64;
    let text_off = ELF_TEXT_OFF;
    let rodata_off = ELF_RODATA_OFF;
    let dynsym_off = 0x280u64;
    let dynstr_off = 0x2b0u64;
    let dynstr = b"\0puts\0libc.so.6\0";
    let rela_off = 0x2c0u64;
    let text_end = 0x2d8u64;
    let dynamic_off = 0x2e0u64;
    let got_off = 0x380u64;
    let data_end = 0x388u64;
    let symtab_off = 0x390u64;
    let code_va = ELF_BASE + text_off;
    let rodata_va = ELF_BASE + rodata_off;
    let got_va = ELF_DATA_VBASE + got_off;
    let dynamic_va = ELF_DATA_VBASE + dynamic_off;
    let mut b = Buf::with_len(symtab_off as usize);
    let code = match arch {
        ElfArch::X86_64 => x86_64_code(code_va, rodata_va, got_va),
        ElfArch::Aarch64 => aarch64_code(code_va, rodata_va, got_va),
    };
    b.put(interp_off as usize, interp);
    b.put(text_off as usize, &code);
    b.put(rodata_off as usize, &rodata_blob(code_va, rodata_va));
    // .dynsym: null, puts (FUNC GLOBAL UND)
    let ds = dynsym_off as usize + 24;
    b.u32(ds, 1);
    b.u8(ds + 4, 0x12);
    b.put(dynstr_off as usize, dynstr);
    // .rela.dyn: R_X86_64_GLOB_DAT (6) / R_AARCH64_GLOB_DAT (1025) for puts at the GOT slot
    let rtype: u64 = if arch == ElfArch::X86_64 { 6 } else { 1025 };
    b.u64(rela_off as usize, got_va);
    b.u64(rela_off as usize + 8, (1 << 32) | rtype);
    // .dynamic
    let dynamic: [(u64, u64); 10] = [
        (1, 6),                     // DT_NEEDED libc.so.6
        (5, ELF_BASE + dynstr_off), // DT_STRTAB
        (6, ELF_BASE + dynsym_off), // DT_SYMTAB
        (10, dynstr.len() as u64),  // DT_STRSZ
        (11, 24),                   // DT_SYMENT
        (7, ELF_BASE + rela_off),   // DT_RELA
        (8, 24),                    // DT_RELASZ
        (9, 24),                    // DT_RELAENT
        (0x6fff_fffb, 0x0800_0001), // DT_FLAGS_1: NOW | PIE
        (0, 0),
    ];
    for (i, (t, v)) in dynamic.iter().enumerate() {
        b.u64(dynamic_off as usize + i * 16, *t);
        b.u64(dynamic_off as usize + i * 16 + 8, *v);
    }
    // .symtab / .strtab
    let mut strtab = b"\0".to_vec();
    let mut syms: Vec<(u32, u64, u64)> = Vec::new();
    if symbols {
        let list: &[(&str, u64, u64)] = match arch {
            ElfArch::X86_64 => &[("main", x64::MAIN, 0x31), ("helper", x64::HELPER, 0x15), ("dispatch", x64::DISPATCH, 0x2c)],
            ElfArch::Aarch64 => &[("main", a64::MAIN, 0x2c), ("helper", a64::HELPER, 0x14)],
        };
        for (n, off, size) in list {
            syms.push((strtab.len() as u32, code_va + off, *size));
            strtab.extend_from_slice(n.as_bytes());
            strtab.push(0);
        }
    }
    let mut pos = symtab_off as usize;
    let symtab_start = pos;
    if symbols {
        pos += 24; // null symbol
        for (name, value, size) in &syms {
            b.u32(pos, *name);
            b.u8(pos + 4, 0x12); // GLOBAL FUNC
            b.u16(pos + 6, 2); // .text section index
            b.u64(pos + 8, *value);
            b.u64(pos + 16, *size);
            pos += 24;
        }
    }
    let symtab_size = pos - symtab_start;
    let strtab_off = pos;
    if symbols {
        b.put(pos, &strtab);
        pos += strtab.len();
    }
    // .shstrtab
    let names = ["", ".interp", ".text", ".rodata", ".dynsym", ".dynstr", ".rela.dyn", ".dynamic", ".got", ".symtab", ".strtab", ".shstrtab"];
    let mut shstr = Vec::new();
    let mut name_off = Vec::new();
    for n in names {
        name_off.push(shstr.len() as u32);
        shstr.extend_from_slice(n.as_bytes());
        shstr.push(0);
    }
    let shstr_off = pos;
    b.put(pos, &shstr);
    pos += shstr.len();
    let shoff = (pos + 7) & !7;
    // section headers: (name idx, type, flags, addr, off, size, link, info, align, entsize)
    let mut shdrs: Vec<(usize, u32, u64, u64, u64, u64, u32, u32, u64, u64)> = vec![
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (1, 1, 2, ELF_BASE + interp_off, interp_off, interp.len() as u64, 0, 0, 1, 0),
        (2, 1, 6, code_va, text_off, code_size, 0, 0, 16, 0),
        (3, 1, 2, rodata_va, rodata_off, rodata::SIZE as u64, 0, 0, 16, 0),
        (4, 11, 2, ELF_BASE + dynsym_off, dynsym_off, 48, 5, 1, 8, 24),
        (5, 3, 2, ELF_BASE + dynstr_off, dynstr_off, dynstr.len() as u64, 0, 0, 1, 0),
        (6, 4, 2, ELF_BASE + rela_off, rela_off, 24, 4, 0, 8, 24),
        (7, 6, 3, dynamic_va, dynamic_off, 160, 5, 0, 8, 16),
        (8, 1, 3, got_va, got_off, 8, 0, 0, 8, 8),
    ];
    if symbols {
        shdrs.push((9, 2, 0, 0, symtab_start as u64, symtab_size as u64, 10, 1, 8, 24));
        shdrs.push((10, 3, 0, 0, strtab_off as u64, strtab.len() as u64, 0, 0, 1, 0));
    }
    shdrs.push((11, 3, 0, 0, shstr_off as u64, shstr.len() as u64, 0, 0, 1, 0));
    let shstrndx = shdrs.len() - 1;
    for (i, s) in shdrs.iter().enumerate() {
        let o = shoff + i * 64;
        b.u32(o, name_off[s.0]);
        b.u32(o + 4, s.1);
        b.u64(o + 8, s.2);
        b.u64(o + 16, s.3);
        b.u64(o + 24, s.4);
        b.u64(o + 32, s.5);
        b.u32(o + 40, s.6);
        b.u32(o + 44, s.7);
        b.u64(o + 48, s.8);
        b.u64(o + 56, s.9);
    }
    // ELF header
    let machine: u16 = if arch == ElfArch::X86_64 { 62 } else { 183 };
    b.put(0, b"\x7fELF\x02\x01\x01");
    b.u16(16, 2); // ET_EXEC
    b.u16(18, machine);
    b.u32(20, 1);
    let entry = code_va;
    b.u64(24, entry);
    b.u64(32, 0x40); // phoff
    b.u64(40, shoff as u64);
    b.u16(52, 64);
    b.u16(54, 56);
    b.u16(56, 5); // phnum
    b.u16(58, 64);
    b.u16(60, shdrs.len() as u16);
    b.u16(62, shstrndx as u16);
    // program headers: (type, flags, off, vaddr, filesz, memsz, align)
    let phdrs: [(u32, u32, u64, u64, u64, u64, u64); 5] = [
        (3, 4, interp_off, ELF_BASE + interp_off, interp.len() as u64, interp.len() as u64, 1), // PT_INTERP
        (1, 5, 0, ELF_BASE, text_end, text_end, 0x1000),                                        // PT_LOAD r-x
        (1, 6, dynamic_off, dynamic_va, data_end - dynamic_off, data_end - dynamic_off, 0x1000), // PT_LOAD rw-
        (2, 6, dynamic_off, dynamic_va, 160, 160, 8),                                           // PT_DYNAMIC
        (0x6474e551, 6, 0, 0, 0, 0, 16),                                                        // PT_GNU_STACK rw-
    ];
    for (i, p) in phdrs.iter().enumerate() {
        let o = 0x40 + i * 56;
        b.u32(o, p.0);
        b.u32(o + 4, p.1);
        b.u64(o + 8, p.2);
        b.u64(o + 16, p.3);
        b.u64(o + 24, p.3);
        b.u64(o + 32, p.4);
        b.u64(o + 40, p.5);
        b.u64(o + 48, p.6);
    }
    (b.into_vec(), ElfLayout { code_va, rodata_va, got_va, entry })
}

/// A Linux x86-64 core file: one thread that died of SIGSEGV at `fault_addr` with `rip`, plus
/// the process name and two mapped files.
pub fn elf64_core(rip: u64, fault_addr: u64) -> Vec<u8> {
    fn note(out: &mut Vec<u8>, name: &[u8], ty: u32, desc: &[u8]) {
        out.extend_from_slice(&((name.len() + 1) as u32).to_le_bytes());
        out.extend_from_slice(&(desc.len() as u32).to_le_bytes());
        out.extend_from_slice(&ty.to_le_bytes());
        out.extend_from_slice(name);
        out.push(0);
        while out.len() % 4 != 0 {
            out.push(0);
        }
        out.extend_from_slice(desc);
        while out.len() % 4 != 0 {
            out.push(0);
        }
    }
    let mut notes = Vec::new();
    // NT_PRSTATUS
    let mut pr = Buf::with_len(336);
    pr.u32(0, 11); // si_signo
    pr.u16(12, 11); // pr_cursig
    pr.u32(32, 4242); // pid
    pr.u32(36, 1);
    let regs_off = 112;
    for i in 0..27 {
        pr.u64(regs_off + i * 8, 0x1000 + i as u64);
    }
    pr.u64(regs_off + 16 * 8, rip); // rip
    pr.u64(regs_off + 19 * 8, 0x7ffd_0000_1000); // rsp
    note(&mut notes, b"CORE", 1, &pr.into_vec());
    // NT_PRPSINFO
    let mut ps = Buf::with_len(136);
    ps.u32(24, 4242);
    ps.put(40, b"crashy");
    ps.put(56, b"./crashy --boom");
    note(&mut notes, b"CORE", 3, &ps.into_vec());
    // NT_SIGINFO
    let mut si = Buf::with_len(128);
    si.u32(0, 11);
    si.u32(8, 1); // SEGV_MAPERR
    si.u64(16, fault_addr);
    note(&mut notes, b"CORE", 0x5349_4749, &si.into_vec());
    // NT_FILE
    let mut f = Buf::default();
    f.u64(0, 2);
    f.u64(8, 0x1000);
    f.u64(16, 0x400000);
    f.u64(24, 0x401000);
    f.u64(32, 0);
    f.u64(40, 0x7f00_0000_0000);
    f.u64(48, 0x7f00_0002_0000);
    f.u64(56, 0);
    let mut fv = f.into_vec();
    fv.extend_from_slice(b"/usr/bin/crashy\0/usr/lib/libc.so.6\0");
    note(&mut notes, b"CORE", 0x4649_4c45, &fv);
    let mut b = Buf::with_len(0x40 + 2 * 56);
    b.put(0, b"\x7fELF\x02\x01\x01");
    b.u16(16, 4); // ET_CORE
    b.u16(18, 62);
    b.u32(20, 1);
    b.u64(32, 0x40);
    b.u16(52, 64);
    b.u16(54, 56);
    b.u16(56, 2);
    let notes_off = 0x40 + 2 * 56;
    // PT_NOTE
    b.u32(0x40, 4);
    b.u64(0x40 + 8, notes_off as u64);
    b.u64(0x40 + 32, notes.len() as u64);
    b.u64(0x40 + 40, notes.len() as u64);
    b.u64(0x40 + 48, 4);
    // PT_LOAD with a little memory
    let load_off = notes_off + notes.len();
    b.u32(0x78, 1);
    b.u32(0x78 + 4, 5);
    b.u64(0x78 + 8, load_off as u64);
    b.u64(0x78 + 16, 0x400000);
    b.u64(0x78 + 32, 0x100);
    b.u64(0x78 + 40, 0x1000);
    b.u64(0x78 + 48, 0x1000);
    let mut out = b.into_vec();
    out.extend_from_slice(&notes);
    out.extend_from_slice(&[0x90; 0x100]);
    out
}

// ---------------------------------------------------------------------------------------------
// PE

pub const PE_BASE: u64 = 0x1_4000_0000;
pub const PE_TEXT_RVA: u64 = 0x1000;
pub const PE_RDATA_RVA: u64 = 0x2000;
pub const PE_IAT_RVA: u64 = 0x2160;

/// One node of a version resource (`VS_VERSIONINFO` and its children).
fn version_node(key: &str, value: Option<&[u8]>, value_is_text: bool, children: &[Vec<u8>]) -> Vec<u8> {
    let mut b = vec![0u8; 6];
    for u in key.encode_utf16() {
        b.extend_from_slice(&u.to_le_bytes());
    }
    b.extend_from_slice(&[0, 0]);
    while b.len() % 4 != 0 {
        b.push(0);
    }
    let mut value_len = 0u16;
    if let Some(v) = value {
        value_len = if value_is_text { (v.len() / 2) as u16 } else { v.len() as u16 };
        b.extend_from_slice(v);
        while b.len() % 4 != 0 {
            b.push(0);
        }
    }
    for c in children {
        b.extend_from_slice(c);
        while b.len() % 4 != 0 {
            b.push(0);
        }
    }
    let len = b.len() as u16;
    b[0..2].copy_from_slice(&len.to_le_bytes());
    b[2..4].copy_from_slice(&value_len.to_le_bytes());
    b[4..6].copy_from_slice(&(u16::from(value_is_text)).to_le_bytes());
    b
}

fn utf16z(s: &str) -> Vec<u8> {
    let mut v: Vec<u8> = s.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
    v.extend_from_slice(&[0, 0]);
    v
}

/// A version resource with CompanyName, ProductName and FileVersion 1.2.3.4.
pub fn version_resource() -> Vec<u8> {
    let mut fixed = Buf::with_len(52);
    fixed.u32(0, 0xfeef04bd);
    fixed.u32(4, 0x10000);
    fixed.u32(8, 0x0001_0002); // 1.2
    fixed.u32(12, 0x0003_0004); // .3.4
    fixed.u32(16, 0x0001_0002);
    fixed.u32(20, 0x0003_0004);
    let s = |k: &str, v: &str| version_node(k, Some(&utf16z(v)), true, &[]);
    let table = version_node("040904b0", None, true, &[s("CompanyName", "Craft Test"), s("ProductName", "Craft Sample"), s("FileVersion", "1.2.3.4")]);
    let sfi = version_node("StringFileInfo", None, true, &[table]);
    version_node("VS_VERSION_INFO", Some(&fixed.into_vec()), false, &[sfi])
}

/// Resource section: an icon, its group, and a version block. `rva` is where it loads.
fn rsrc_section(rva: u32) -> Vec<u8> {
    // Layout: root dir @0 (3 entries) → per type dir @0x28,0x40,0x58 (1 entry) → lang dirs
    // @0x70,0x88,0xa0 (1 entry) → data entries @0xb8,0xc8,0xd8 → data @0x100…
    let mut b = Buf::with_len(0x100);
    let dir = |b: &mut Buf, off: usize, n_ids: u16| {
        b.u16(off + 14, n_ids);
    };
    let types = [3u32, 14, 16];
    dir(&mut b, 0, 3);
    for (i, t) in types.iter().enumerate() {
        let type_dir = 0x28 + i * 0x18;
        let lang_dir = 0x70 + i * 0x18;
        let data_entry = 0xb8 + i * 0x10;
        b.u32(16 + i * 8, *t);
        b.u32(16 + i * 8 + 4, 0x8000_0000 | type_dir as u32);
        dir(&mut b, type_dir, 1);
        b.u32(type_dir + 16, 1);
        b.u32(type_dir + 20, 0x8000_0000 | lang_dir as u32);
        dir(&mut b, lang_dir, 1);
        b.u32(lang_dir + 16, 0x409);
        b.u32(lang_dir + 20, data_entry as u32);
    }
    let mut icon = Buf::with_len(40);
    icon.u32(0, 40);
    icon.u32(4, 16);
    icon.u32(8, 32);
    icon.u16(12, 1);
    icon.u16(14, 32);
    let icon = icon.into_vec();
    let mut group = Buf::with_len(20);
    group.u16(2, 1);
    group.u16(4, 1);
    group.u8(6, 16);
    group.u8(7, 16);
    group.u16(10, 1);
    group.u16(12, 32);
    group.u32(14, icon.len() as u32);
    group.u16(18, 1);
    let group = group.into_vec();
    let version = version_resource();
    let mut off = 0x100usize;
    for (i, data) in [icon, group, version].iter().enumerate() {
        let entry = 0xb8 + i * 0x10;
        b.u32(entry, rva + off as u32);
        b.u32(entry + 4, data.len() as u32);
        b.put(off, data);
        off = (off + data.len() + 7) & !7;
    }
    b.into_vec()
}

/// [`pe64`] with another subsystem in its header: 2 for a windowed program, 3 (its own) for a
/// console one.
pub fn pe64_subsystem(subsystem: u16) -> Vec<u8> {
    let mut pe = pe64();
    // e_lfanew (0x80) + "PE\0\0" + the COFF header, then Subsystem at offset 68 of the optional header.
    if let Some(field) = pe.get_mut(0x80 + 4 + 20 + 68..0x80 + 4 + 20 + 70) {
        field.copy_from_slice(&subsystem.to_le_bytes());
    }
    pe
}

/// A PE32+ console program importing `puts` from msvcrt.dll, exporting `helper`, with an icon
/// and a version resource.
pub fn pe64() -> Vec<u8> {
    let code_va = PE_BASE + PE_TEXT_RVA;
    let rdata_va = PE_BASE + PE_RDATA_RVA;
    let iat_va = PE_BASE + PE_IAT_RVA;
    let mut b = Buf::with_len(0x400);
    b.put(0, b"MZ");
    b.u32(0x3c, 0x80);
    b.put(0x80, b"PE\0\0");
    let coff = 0x84;
    b.u16(coff, 0x8664);
    b.u16(coff + 2, 4);
    b.u32(coff + 4, 0x6000_0000);
    b.u16(coff + 16, 240);
    b.u16(coff + 18, 0x22);
    let opt = coff + 20;
    b.u16(opt, 0x20b);
    b.u32(opt + 4, 0x200); // SizeOfCode
    b.u32(opt + 16, (PE_TEXT_RVA + x64::MAIN) as u32); // entry
    b.u32(opt + 20, PE_TEXT_RVA as u32);
    b.u64(opt + 24, PE_BASE);
    b.u32(opt + 32, 0x1000);
    b.u32(opt + 36, 0x200);
    b.u16(opt + 40, 6);
    b.u16(opt + 48, 6);
    b.u32(opt + 56, 0x5000); // SizeOfImage
    b.u32(opt + 60, 0x400); // SizeOfHeaders
    b.u16(opt + 68, 3); // console
    b.u16(opt + 70, 0x8160);
    b.u64(opt + 72, 0x100000);
    b.u64(opt + 80, 0x1000);
    b.u64(opt + 88, 0x100000);
    b.u64(opt + 96, 0x1000);
    b.u32(opt + 108, 16);
    let dd = opt + 112;
    let rsrc = rsrc_section(0x4000);
    b.u32(dd, 0x21a0); // export
    b.u32(dd + 4, 0x60);
    b.u32(dd + 8, 0x2100); // import
    b.u32(dd + 12, 40);
    b.u32(dd + 16, 0x4000); // resource
    b.u32(dd + 20, rsrc.len() as u32);
    b.u32(dd + 12 * 8, PE_IAT_RVA as u32); // IAT
    b.u32(dd + 12 * 8 + 4, 16);
    let sh = opt + 240;
    let rsrc_raw = (rsrc.len() as u32 + 0x1ff) & !0x1ff;
    let secs: [(&[u8], u32, u32, u32, u32, u32); 4] = [
        (b".text", 0x200, 0x1000, 0x200, 0x400, 0x6000_0020),
        (b".rdata", 0x200, 0x2000, 0x200, 0x600, 0x4000_0040),
        (b".data", 0x200, 0x3000, 0x200, 0x800, 0xc000_0040),
        (b".rsrc", rsrc.len() as u32, 0x4000, rsrc_raw, 0xa00, 0x4000_0040),
    ];
    for (i, s) in secs.iter().enumerate() {
        let o = sh + i * 40;
        b.put(o, s.0);
        b.u32(o + 8, s.1);
        b.u32(o + 12, s.2);
        b.u32(o + 16, s.3);
        b.u32(o + 20, s.4);
        b.u32(o + 36, s.5);
    }
    b.put(0x400, &x86_64_code(code_va, rdata_va, iat_va));
    let mut rd = Buf::with_len(0x200);
    rd.put(0, &rodata_blob(code_va, rdata_va));
    // import descriptor
    rd.u32(0x100, 0x2140); // OriginalFirstThunk
    rd.u32(0x10c, 0x2190); // Name
    rd.u32(0x110, PE_IAT_RVA as u32); // FirstThunk
    rd.u64(0x140, 0x2180);
    rd.u64(0x160, 0x2180);
    rd.put(0x182, b"puts\0");
    rd.put(0x190, b"msvcrt.dll\0");
    // export directory
    rd.u32(0x1a0 + 12, 0x21e0); // Name
    rd.u32(0x1a0 + 16, 1); // Base
    rd.u32(0x1a0 + 20, 1);
    rd.u32(0x1a0 + 24, 1);
    rd.u32(0x1a0 + 28, 0x21d0);
    rd.u32(0x1a0 + 32, 0x21d4);
    rd.u32(0x1a0 + 36, 0x21d8);
    rd.u32(0x1d0, (PE_TEXT_RVA + x64::HELPER) as u32);
    rd.u32(0x1d4, 0x21f0);
    rd.u16(0x1d8, 0);
    rd.put(0x1e0, b"craft.exe\0");
    rd.put(0x1f0, b"helper\0");
    b.put(0x600, &rd.into_vec());
    b.put(0x800, &[0u8; 0x200]);
    let mut rs = rsrc;
    rs.resize(rsrc_raw as usize, 0);
    b.put(0xa00, &rs);
    b.into_vec()
}

// ---------------------------------------------------------------------------------------------
// Mach-O

pub const MACHO_BASE: u64 = 0x1_0000_0000;
pub const MACHO_TEXT_OFF: u64 = 0x600;
pub const MACHO_CSTRING_OFF: u64 = 0x6a0;
pub const OBJC_CLASS: &str = "CAWidget";
pub const OBJC_SELECTOR: &str = "tapButton:";
pub const OBJC_PROTOCOL: &str = "CADelegate";

/// A Mach-O 64-bit x86-64 executable importing `_puts` from libSystem, with an Objective-C
/// class `CAWidget` (method `tapButton:` implemented by `hidden`) and a protocol `CADelegate`.
pub fn macho64() -> Vec<u8> {
    let code_va = MACHO_BASE + MACHO_TEXT_OFF;
    // __cstring holds HELLO@0, SECRET@0x10 (shared rodata layout) then the ObjC names after the
    // jump table area, so the string offsets match the other containers.
    let cstr_va = MACHO_BASE + MACHO_CSTRING_OFF;
    let data_va = MACHO_BASE + 0x1000;
    let got_va = data_va;
    let mut b = Buf::with_len(0x2000);
    b.put(MACHO_TEXT_OFF as usize, &x86_64_code(code_va, cstr_va, got_va));
    // rodata blob (strings + jump table) lives in __cstring + first part of __const
    let ro = rodata_blob(code_va, cstr_va);
    b.put(MACHO_CSTRING_OFF as usize, &ro);
    // ObjC names after the blob, inside __cstring
    let names_off = MACHO_CSTRING_OFF as usize + rodata::SIZE;
    let class_name_va = MACHO_BASE + names_off as u64;
    b.put(names_off, b"CAWidget\0");
    let sel_va = class_name_va + 0x10;
    b.put(names_off + 0x10, b"tapButton:\0");
    let types_va = class_name_va + 0x20;
    b.put(names_off + 0x20, b"v24@0:8@16\0");
    let proto_name_va = class_name_va + 0x30;
    b.put(names_off + 0x30, b"CADelegate\0");
    let cstring_size = 0x80u64;
    // __DATA contents
    let classlist = 0x1008usize;
    let protolist = 0x1010usize;
    let class_t = 0x1018usize;
    let class_ro = 0x1040usize;
    let methods = 0x1088usize;
    let protocol_t = 0x10a8usize;
    let va = |off: usize| MACHO_BASE + off as u64;
    b.u64(classlist, va(class_t));
    b.u64(protolist, va(protocol_t));
    b.u64(class_t + 32, va(class_ro)); // data
    b.u32(class_ro + 8, 8); // instanceSize
    b.u64(class_ro + 0x18, class_name_va);
    b.u64(class_ro + 0x20, va(methods));
    b.u32(methods, 24);
    b.u32(methods + 4, 1);
    b.u64(methods + 8, sel_va);
    b.u64(methods + 16, types_va);
    b.u64(methods + 24, code_va + x64::HIDDEN);
    b.u64(protocol_t + 8, proto_name_va);
    b.u32(protocol_t + 64, 72);
    // __LINKEDIT: symbols, strings, indirect symbols, function starts
    let linkedit = 0x2000usize;
    let mut le = Buf::default();
    let mut strs = b" \0".to_vec();
    let mut nlist = Vec::new();
    for (n, ty, sect, desc, value) in [
        ("_main", 0x0fu8, 1u8, 0u16, code_va + x64::MAIN),
        ("_helper", 0x0f, 1, 0, code_va + x64::HELPER),
        ("_dispatch", 0x0f, 1, 0, code_va + x64::DISPATCH),
        ("_puts", 0x01, 0, 0x0100, 0),
    ] {
        let mut e = Buf::with_len(16);
        e.u32(0, strs.len() as u32);
        e.u8(4, ty);
        e.u8(5, sect);
        e.u16(6, desc);
        e.u64(8, value);
        nlist.extend_from_slice(&e.into_vec());
        strs.extend_from_slice(n.as_bytes());
        strs.push(0);
    }
    let symoff = linkedit;
    le.put(0, &nlist);
    let stroff = symoff + nlist.len();
    le.put(nlist.len(), &strs);
    let indoff = (stroff + strs.len() + 3) & !3;
    le.u32(indoff - linkedit, 3); // _puts is symbol 3
    let fsoff = indoff + 4;
    // function starts: uleb deltas from __TEXT start
    let starts: Vec<u8> = vec![0x80, 0x0c, 0x40, 0x20, 0x10, 0x00];
    le.put(fsoff - linkedit, &starts);
    let le_bytes = le.into_vec();
    let le_size = le_bytes.len();
    b.put(linkedit, &le_bytes);
    // load commands
    let mut cmds = Buf::default();
    let mut ncmds = 0u32;
    let mut pos = 0usize;
    let seg = |cmds: &mut Buf,
               pos: &mut usize,
               name: &str,
               vmaddr: u64,
               vmsize: u64,
               fileoff: u64,
               filesize: u64,
               prot: u32,
               sects: &[(&str, &str, u64, u64, u32, u32)]| {
        let start = *pos;
        cmds.u32(start, 0x19);
        cmds.u32(start + 4, (72 + 80 * sects.len()) as u32);
        cmds.put(start + 8, name.as_bytes());
        cmds.u64(start + 24, vmaddr);
        cmds.u64(start + 32, vmsize);
        cmds.u64(start + 40, fileoff);
        cmds.u64(start + 48, filesize);
        cmds.u32(start + 56, prot);
        cmds.u32(start + 60, prot);
        cmds.u32(start + 64, sects.len() as u32);
        for (i, (sname, segname, addr, size, flags, reserved1)) in sects.iter().enumerate() {
            let o = start + 72 + i * 80;
            cmds.put(o, sname.as_bytes());
            cmds.put(o + 16, segname.as_bytes());
            cmds.u64(o + 32, *addr);
            cmds.u64(o + 40, *size);
            cmds.u32(o + 48, (*addr - MACHO_BASE) as u32);
            cmds.u32(o + 64, *flags);
            cmds.u32(o + 68, *reserved1);
        }
        *pos += 72 + 80 * sects.len();
    };
    seg(&mut cmds, &mut pos, "__PAGEZERO", 0, MACHO_BASE, 0, 0, 0, &[]);
    ncmds += 1;
    seg(
        &mut cmds,
        &mut pos,
        "__TEXT",
        MACHO_BASE,
        0x1000,
        0,
        0x1000,
        5,
        &[("__text", "__TEXT", code_va, x64::CODE_SIZE as u64, 0x8000_0400, 0), ("__cstring", "__TEXT", cstr_va, cstring_size, 0x2, 0)],
    );
    ncmds += 1;
    seg(
        &mut cmds,
        &mut pos,
        "__DATA",
        data_va,
        0x1000,
        0x1000,
        0x1000,
        3,
        &[
            ("__got", "__DATA", got_va, 8, 0x6, 0),
            ("__objc_classlist", "__DATA", va(classlist), 8, 0x1000_0000, 0),
            ("__objc_protolist", "__DATA", va(protolist), 8, 0, 0),
            ("__objc_data", "__DATA", va(class_t), 40, 0, 0),
            ("__objc_const", "__DATA", va(class_ro), (protocol_t + 72 - class_ro) as u64, 0, 0),
        ],
    );
    ncmds += 1;
    seg(&mut cmds, &mut pos, "__LINKEDIT", MACHO_BASE + 0x2000, 0x1000, 0x2000, le_size as u64, 1, &[]);
    ncmds += 1;
    // LC_SYMTAB
    cmds.u32(pos, 0x2);
    cmds.u32(pos + 4, 24);
    cmds.u32(pos + 8, symoff as u32);
    cmds.u32(pos + 12, 4);
    cmds.u32(pos + 16, stroff as u32);
    cmds.u32(pos + 20, strs.len() as u32);
    pos += 24;
    ncmds += 1;
    // LC_DYSYMTAB
    cmds.u32(pos, 0xb);
    cmds.u32(pos + 4, 80);
    cmds.u32(pos + 16, 0); // iextdefsym
    cmds.u32(pos + 20, 3); // nextdefsym
    cmds.u32(pos + 24, 3); // iundefsym
    cmds.u32(pos + 28, 1); // nundefsym
    cmds.u32(pos + 56, indoff as u32);
    cmds.u32(pos + 60, 1);
    pos += 80;
    ncmds += 1;
    // LC_MAIN
    cmds.u32(pos, 0x8000_0028);
    cmds.u32(pos + 4, 24);
    cmds.u64(pos + 8, MACHO_TEXT_OFF + x64::MAIN);
    pos += 24;
    ncmds += 1;
    // LC_LOAD_DYLIB
    let dylib = b"/usr/lib/libSystem.B.dylib\0";
    let dl_size = (24 + dylib.len() + 7) & !7;
    cmds.u32(pos, 0xc);
    cmds.u32(pos + 4, dl_size as u32);
    cmds.u32(pos + 8, 24);
    cmds.put(pos + 24, dylib);
    pos += dl_size;
    ncmds += 1;
    // LC_FUNCTION_STARTS
    cmds.u32(pos, 0x26);
    cmds.u32(pos + 4, 16);
    cmds.u32(pos + 8, fsoff as u32);
    cmds.u32(pos + 12, starts.len() as u32);
    pos += 16;
    ncmds += 1;
    let cmd_bytes = cmds.into_vec();
    b.u32(0, 0xfeed_facf);
    b.u32(4, 0x0100_0007);
    b.u32(8, 3);
    b.u32(12, 2);
    b.u32(16, ncmds);
    b.u32(20, pos as u32);
    b.u32(24, 0x0020_0085);
    b.put(32, &cmd_bytes[..pos]);
    let mut out = b.into_vec();
    out.truncate(linkedit + le_size);
    out
}

/// A universal (fat) Mach-O holding the given thin slices (cputype taken from each slice).
pub fn macho_fat(slices: &[Vec<u8>]) -> Vec<u8> {
    let mut b = Buf::with_len(8 + 20 * slices.len());
    b.u32be(0, 0xcafe_babe);
    b.u32be(4, slices.len() as u32);
    let mut off = 0x1000usize;
    for (i, s) in slices.iter().enumerate() {
        let cputype = s.get(4..8).map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]])).unwrap_or(0);
        let sub = s.get(8..12).map(|c| u32::from_le_bytes([c[0], c[1], c[2], c[3]])).unwrap_or(0);
        let e = 8 + i * 20;
        b.u32be(e, cputype);
        b.u32be(e + 4, sub);
        b.u32be(e + 8, off as u32);
        b.u32be(e + 12, s.len() as u32);
        b.u32be(e + 16, 12);
        b.put(off, s);
        off = (off + s.len() + 0xfff) & !0xfff;
    }
    b.into_vec()
}

// ---------------------------------------------------------------------------------------------
// DOS

/// A DOS .COM program (loads at 0x100): prints "Hi$" with int 21h/09h and exits with 4Ch.
pub fn dos_com() -> Vec<u8> {
    // mov ah,9 ; mov dx,0x10c ; int 21h ; mov ax,4c00h ; int 21h ; "Hi$"
    let mut v = vec![0xb4, 0x09, 0xba, 0x0c, 0x01, 0xcd, 0x21, 0xb8, 0x00, 0x4c, 0xcd, 0x21];
    v.extend_from_slice(b"Hi$");
    v
}

/// A DOS MZ executable with two relocations; entry CS:IP = 0000:0000.
pub fn dos_mz() -> Vec<u8> {
    let code = dos_com();
    let header_paras = 4usize; // 64 bytes
    let total = header_paras * 16 + code.len();
    let mut b = Buf::with_len(total);
    b.put(0, b"MZ");
    b.u16(2, (total % 512) as u16);
    b.u16(4, total.div_ceil(512) as u16);
    b.u16(6, 2); // relocations
    b.u16(8, header_paras as u16);
    b.u16(10, 0x10);
    b.u16(12, 0xffff);
    b.u16(14, 0); // ss
    b.u16(16, 0x100); // sp
    b.u16(20, 0); // ip
    b.u16(22, 0); // cs
    b.u16(24, 0x1c); // lfarlc
    b.u16(0x1c, 0x0003);
    b.u16(0x1e, 0x0000);
    b.u16(0x20, 0x0008);
    b.u16(0x22, 0x0000);
    b.put(header_paras * 16, &code);
    b.into_vec()
}

/// Deterministic pseudo-random bytes (xorshift) for fuzz-like loops.
pub fn noise(seed: u64, len: usize) -> Vec<u8> {
    let mut x = seed.wrapping_mul(0x9e37_79b9_7f4a_7c15) | 1;
    (0..len)
        .map(|_| {
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            x as u8
        })
        .collect()
}

/// Every way to damage a sample used by robustness tests: truncations at many lengths and
/// single-byte corruptions spread across the file.
pub fn mutations(sample: &[u8]) -> Vec<Vec<u8>> {
    let mut out = Vec::new();
    let n = sample.len();
    let step = (n / 64).max(1);
    let mut len = 0;
    while len < n {
        out.push(sample[..len].to_vec());
        len += step;
    }
    for (i, seed) in (0..n).step_by(step).zip(1u64..) {
        let mut m = sample.to_vec();
        let noise = noise(seed, 8);
        for (j, v) in noise.iter().enumerate() {
            if let Some(b) = m.get_mut(i + j) {
                *b = *v;
            }
        }
        out.push(m);
        let mut m = sample.to_vec();
        if let Some(b) = m.get_mut(i) {
            *b = 0xff;
        }
        out.push(m);
    }
    out
}

/// Write bytes to a fresh temporary file and return its path (tests only).
pub fn temp_file(name: &str, bytes: &[u8]) -> std::path::PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("craft-anything-testkit-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let p = dir.join(name);
    std::fs::write(&p, bytes).unwrap();
    p
}
