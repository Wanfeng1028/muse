//! Shared objects with no section headers, as NAS and router firmware ships them: one `PT_LOAD`
//! (addresses equal file offsets), a `PT_DYNAMIC` with `DT_SYMTAB`, `DT_STRTAB`, `DT_STRSZ`,
//! `DT_SYMENT` and one hash table, an imported `puts` and one global function per name given.
//! Any class and byte order, so a big-endian MIPS ELF32 is covered too.

use crate::flutter::SymbolTable;

/// How many bytes each function body takes (its first byte is an x86 `ret`).
pub const BODY_SIZE: u64 = 16;

struct W {
    big: bool,
    is64: bool,
}

impl W {
    fn put(&self, v: &mut [u8], at: usize, size: usize, x: u64) {
        let b = if self.big { x.to_be_bytes() } else { x.to_le_bytes() };
        let b = if self.big { &b[8 - size..] } else { &b[..size] };
        v[at..at + size].copy_from_slice(b);
    }
    fn push(&self, v: &mut Vec<u8>, size: usize, x: u64) {
        let at = v.len();
        v.resize(at + size, 0);
        self.put(v, at, size, x);
    }
    fn word(&self) -> usize {
        if self.is64 { 8 } else { 4 }
    }
}

fn align(v: &mut Vec<u8>, a: usize) {
    while !v.len().is_multiple_of(a) {
        v.push(0);
    }
}

/// Build the file. Function `i` is a [`BODY_SIZE`]-byte body, in order, from a 16-byte aligned
/// start. `table` picks `DT_HASH` or `DT_GNU_HASH`; there are never section headers.
pub fn sectionless_elf(is64: bool, big: bool, functions: &[&str], table: SymbolTable) -> Vec<u8> {
    let w = W { big, is64 };
    let sym_size = if is64 { 24 } else { 16 };
    let mut f = vec![0u8; 0x100];
    let dynstr_off = f.len();
    f.push(0);
    let mut names = Vec::new();
    for n in std::iter::once("puts").chain(functions.iter().copied()) {
        names.push(f.len() - dynstr_off);
        f.extend_from_slice(n.as_bytes());
        f.push(0);
    }
    let dynstr_size = f.len() - dynstr_off;
    align(&mut f, 16);
    let mut bodies = Vec::new();
    for _ in functions {
        bodies.push(f.len() as u64);
        f.push(0xc3);
        f.extend(std::iter::repeat_n(0x90u8, BODY_SIZE as usize - 1));
    }
    align(&mut f, 8);
    let dynsym_off = f.len();
    let nsyms = functions.len() + 2;
    // (name, info, shndx, value, size): the null symbol, the import, then the functions.
    let mut rows: Vec<(u64, u8, u16, u64, u64)> = vec![(0, 0, 0, 0, 0), (names[0] as u64, 0x12, 0, 0, 0)];
    for (i, body) in bodies.iter().enumerate() {
        rows.push((names[i + 1] as u64, 0x12, 1, *body, BODY_SIZE));
    }
    for (name, info, shndx, value, size) in rows {
        if is64 {
            w.push(&mut f, 4, name);
            f.extend_from_slice(&[info, 0]);
            w.push(&mut f, 2, u64::from(shndx));
            w.push(&mut f, 8, value);
            w.push(&mut f, 8, size);
        } else {
            w.push(&mut f, 4, name);
            w.push(&mut f, 4, value);
            w.push(&mut f, 4, size);
            f.extend_from_slice(&[info, 0]);
            w.push(&mut f, 2, u64::from(shndx));
        }
    }
    // DT_HASH: one bucket, nchain = the symbol count.
    align(&mut f, 8);
    let hash_off = f.len();
    for v in [1u64, nsyms as u64, 0] {
        w.push(&mut f, 4, v);
    }
    f.extend(std::iter::repeat_n(0u8, 4 * nsyms));
    // DT_GNU_HASH: one bucket starting at the first function (the import sits before it).
    align(&mut f, 8);
    let gnu_off = f.len();
    for v in [1u64, 2, 1, 6] {
        w.push(&mut f, 4, v);
    }
    w.push(&mut f, w.word(), u64::MAX);
    w.push(&mut f, 4, 2);
    for i in 0..functions.len() {
        let last = i + 1 == functions.len();
        w.push(&mut f, 4, 0x1234_5670 | u64::from(last));
    }
    // .dynamic
    align(&mut f, 8);
    let dyn_off = f.len();
    let mut dynv: Vec<(u64, u64)> = vec![(5, dynstr_off as u64), (6, dynsym_off as u64), (10, dynstr_size as u64), (11, sym_size)];
    match table {
        SymbolTable::Sections | SymbolTable::DynamicHash => dynv.push((4, hash_off as u64)),
        SymbolTable::DynamicGnuHash => dynv.push((0x6fff_fef5, gnu_off as u64)),
    }
    dynv.push((0, 0));
    for (t, v) in dynv {
        w.push(&mut f, w.word(), t);
        w.push(&mut f, w.word(), v);
    }
    let dyn_size = (f.len() - dyn_off) as u64;
    let total = f.len() as u64;
    // ELF header and two program headers: LOAD (read, execute) and DYNAMIC.
    f[0..4].copy_from_slice(b"\x7fELF");
    f[4] = if is64 { 2 } else { 1 };
    f[5] = if big { 2 } else { 1 };
    f[6] = 1;
    let machine = match (is64, big) {
        (true, false) => 62,
        (false, false) => 3,
        (false, true) => 8,
        (true, true) => 21,
    };
    w.put(&mut f, 16, 2, 3);
    w.put(&mut f, 18, 2, machine);
    w.put(&mut f, 20, 4, 1);
    let (phoff, phent, ehsize) = if is64 { (64, 56, 64) } else { (52, 32, 52) };
    if is64 {
        w.put(&mut f, 32, 8, phoff);
        w.put(&mut f, 52, 2, ehsize);
        w.put(&mut f, 54, 2, phent);
        w.put(&mut f, 56, 2, 2);
        w.put(&mut f, 58, 2, 64);
    } else {
        w.put(&mut f, 28, 4, phoff);
        w.put(&mut f, 40, 2, ehsize);
        w.put(&mut f, 42, 2, phent);
        w.put(&mut f, 44, 2, 2);
        w.put(&mut f, 46, 2, 40);
    }
    for (i, (ty, flags, off, size)) in [(1u64, 5u64, 0u64, total), (2, 6, dyn_off as u64, dyn_size)].into_iter().enumerate() {
        let p = phoff as usize + i * phent as usize;
        w.put(&mut f, p, 4, ty);
        if is64 {
            w.put(&mut f, p + 4, 4, flags);
            for (d, x) in [(8, off), (16, off), (24, off), (32, size), (40, size), (48, 8)] {
                w.put(&mut f, p + d, 8, x);
            }
        } else {
            for (d, x) in [(4, off), (8, off), (12, off), (16, size), (20, size), (24, flags), (28, 4)] {
                w.put(&mut f, p + d, 4, x);
            }
        }
    }
    f
}
