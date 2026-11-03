//! A tiny but valid Solana sBPF ELF: an ELF64 little-endian `EM_BPF` object whose `.text` holds
//! `mov64 r1, 0`, a `call` to the `sol_log_` syscall (by its murmur3 hash), and `exit`; with an
//! `entrypoint` symbol, an undefined `sol_log_` dynamic symbol, and a `.rela.text` relocation
//! (R_BPF_64_32) at the call site. Lets tests check decode, function/CFG discovery and syscall
//! mapping against exact addresses and names.

use crate::Buf;

/// Virtual address the `.text` section loads at.
pub const TEXT_VADDR: u64 = 0x1000;
/// The one syscall the program calls.
pub const SYSCALL: &str = "sol_log_";

/// MurmurHash3 x86 32-bit (seed 0) — the same hash Solana uses for syscall names. Kept here so
/// the fixture stays dependency-free; the parser computes it independently and must agree.
pub fn murmur3_32(data: &[u8], mut seed: u32) -> u32 {
    const C1: u32 = 0xcc9e_2d51;
    const C2: u32 = 0x1b87_3593;
    let h = &mut seed;
    let nblocks = data.len() / 4;
    for i in 0..nblocks {
        let k = u32::from_le_bytes([data[i * 4], data[i * 4 + 1], data[i * 4 + 2], data[i * 4 + 3]]);
        let k = k.wrapping_mul(C1).rotate_left(15).wrapping_mul(C2);
        *h ^= k;
        *h = h.rotate_left(13).wrapping_mul(5).wrapping_add(0xe654_6b64);
    }
    let tail = &data[nblocks * 4..];
    let mut k1 = 0u32;
    if tail.len() >= 3 {
        k1 ^= u32::from(tail[2]) << 16;
    }
    if tail.len() >= 2 {
        k1 ^= u32::from(tail[1]) << 8;
    }
    if !tail.is_empty() {
        k1 ^= u32::from(tail[0]);
        k1 = k1.wrapping_mul(C1).rotate_left(15).wrapping_mul(C2);
        *h ^= k1;
    }
    *h ^= data.len() as u32;
    *h ^= *h >> 16;
    *h = h.wrapping_mul(0x85eb_ca6b);
    *h ^= *h >> 13;
    *h = h.wrapping_mul(0xc2b2_ae35);
    *h ^= *h >> 16;
    *h
}

fn ins(op: u8, dst: u8, src: u8, off: i16, imm: i32) -> [u8; 8] {
    let mut b = [0u8; 8];
    b[0] = op;
    b[1] = (src << 4) | (dst & 0x0f);
    b[2..4].copy_from_slice(&off.to_le_bytes());
    b[4..8].copy_from_slice(&imm.to_le_bytes());
    b
}

/// The three-instruction program bytes (24 bytes): `mov64 r1,0`, `call sol_log_`, `exit`.
pub fn text_bytes() -> Vec<u8> {
    let hash = murmur3_32(SYSCALL.as_bytes(), 0) as i32;
    let mut c = Vec::new();
    c.extend_from_slice(&ins(0xb7, 1, 0, 0, 0)); // slot0: mov64 r1, 0
    c.extend_from_slice(&ins(0x85, 0, 0, 0, hash)); // slot1: call sol_log_ (hash)
    c.extend_from_slice(&ins(0x95, 0, 0, 0, 0)); // slot2: exit
    c
}

/// Build the whole ELF file.
pub fn program() -> Vec<u8> {
    let text = text_bytes();
    let text_off = 0x40usize;
    let text_size = text.len();

    // .dynstr: "\0sol_log_\0entrypoint\0"
    let mut dynstr = vec![0u8];
    let sol_name_idx = dynstr.len() as u32;
    dynstr.extend_from_slice(b"sol_log_\0");
    let entry_name_idx = dynstr.len() as u32;
    dynstr.extend_from_slice(b"entrypoint\0");

    let dynstr_off = 0x60usize;
    let dynsym_off = 0x80usize; // 8-aligned
    // .dynsym: [null, sol_log_ (UND, FUNC GLOBAL), entrypoint (FUNC GLOBAL @ TEXT_VADDR, shndx 1)]
    let dynsym_size = 3 * 24;
    let rela_off = dynsym_off + dynsym_size; // 0xc8 → bump to 8-aligned 0xc8 already /8
    let rela_off = (rela_off + 7) & !7;
    let rela_size = 24usize; // one Elf64_Rela

    // .shstrtab
    let sh_names = ["", ".text", ".dynstr", ".dynsym", ".rela.text", ".shstrtab"];
    let mut shstr = Vec::new();
    let mut shstr_idx = Vec::new();
    for n in sh_names {
        shstr_idx.push(shstr.len() as u32);
        shstr.extend_from_slice(n.as_bytes());
        shstr.push(0);
    }
    let shstr_off = rela_off + rela_size;
    let shoff = (shstr_off + shstr.len() + 7) & !7;

    let mut b = Buf::with_len(shoff + 6 * 64);

    // ELF header.
    b.put(0, b"\x7fELF\x02\x01\x01\0\0\0\0\0\0\0\0\0");
    b.u16(16, 3); // ET_DYN (Solana programs are typically shared objects)
    b.u16(18, 247); // EM_BPF
    b.u32(20, 1); // EV_CURRENT
    b.u64(24, TEXT_VADDR); // e_entry
    b.u64(32, 0); // e_phoff (none)
    b.u64(40, shoff as u64); // e_shoff
    b.u32(48, 0); // e_flags = 0 → sbpf_v1
    b.u16(52, 64); // e_ehsize
    b.u16(54, 56); // e_phentsize
    b.u16(56, 0); // e_phnum
    b.u16(58, 64); // e_shentsize
    b.u16(60, 6); // e_shnum
    b.u16(62, 5); // e_shstrndx

    // Section bodies.
    b.put(text_off, &text);
    b.put(dynstr_off, &dynstr);

    // .dynsym entries.
    let sym = |b: &mut Buf, o: usize, name: u32, info: u8, shndx: u16, value: u64, size: u64| {
        b.u32(o, name);
        b.u8(o + 4, info);
        b.u8(o + 5, 0);
        b.u16(o + 6, shndx);
        b.u64(o + 8, value);
        b.u64(o + 16, size);
    };
    sym(&mut b, dynsym_off, 0, 0, 0, 0, 0); // null
    sym(&mut b, dynsym_off + 24, sol_name_idx, 0x12, 0, 0, 0); // sol_log_: GLOBAL FUNC UND
    sym(&mut b, dynsym_off + 48, entry_name_idx, 0x12, 1, TEXT_VADDR, text_size as u64); // entrypoint

    // .rela.text: patch the call immediate at slot1 (text + 8) against sol_log_ (sym 1), type 10.
    b.u64(rela_off, TEXT_VADDR + 8); // r_offset
    b.u64(rela_off + 8, (1u64 << 32) | 10); // r_info: sym 1, R_BPF_64_32
    b.u64(rela_off + 16, 0); // addend

    b.put(shstr_off, &shstr);

    // Section headers: (name_idx, type, flags, addr, off, size, link, info, align, entsize)
    let shdrs: [(usize, u32, u64, u64, u64, u64, u32, u32, u64, u64); 6] = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),                                         // NULL
        (1, 1, 0x6, TEXT_VADDR, text_off as u64, text_size as u64, 0, 0, 8, 0), // .text ALLOC|EXEC
        (2, 3, 0, 0, dynstr_off as u64, dynstr.len() as u64, 0, 0, 1, 0),       // .dynstr
        (3, 11, 0, 0, dynsym_off as u64, dynsym_size as u64, 2, 1, 8, 24),      // .dynsym (link=.dynstr)
        (4, 4, 0, 0, rela_off as u64, rela_size as u64, 3, 1, 8, 24),           // .rela.text (link=.dynsym, info=.text)
        (5, 3, 0, 0, shstr_off as u64, shstr.len() as u64, 0, 0, 1, 0),         // .shstrtab
    ];
    for (i, s) in shdrs.iter().enumerate() {
        let o = shoff + i * 64;
        b.u32(o, shstr_idx[s.0]);
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

    b.into_vec()
}
