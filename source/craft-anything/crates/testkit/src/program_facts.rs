//! Samples for the program-reading tools: a PE with delay-loaded, bound and ordinal imports and
//! forwarded exports; a genuinely signed PE; an ELF shared library with symbol versions; ELF
//! programs made of chosen functions; GGUF and safetensors headers.

use crate::android::{der, der_oid};
use crate::crypto::{rsa_sign_sha256, self_signed_rsa, sha256};
use crate::{Buf, pe64};

const FACTS_RVA: u32 = 0x6000;
const FACTS_SIZE: usize = 0x800;
const OPT: usize = 0x84 + 20;
const DIRS: usize = OPT + 112;

fn set_dir(pe: &mut [u8], index: usize, rva: u32, size: u32) {
    let o = DIRS + index * 8;
    pe[o..o + 4].copy_from_slice(&rva.to_le_bytes());
    pe[o + 4..o + 8].copy_from_slice(&size.to_le_bytes());
}

/// A PE32+ library: `KERNEL32.dll` (a named and an ordinal import), `USER32.dll` (bound),
/// `VERSION.dll` (delay-loaded, named and ordinal), and exports starting at ordinal 5: `Alpha`,
/// `Beta` (forwarded to `NTDLL.RtlBeta`), a gap, and an ordinal-only entry.
pub fn pe_facts() -> Vec<u8> {
    let r = FACTS_RVA;
    let mut s = Buf::with_len(FACTS_SIZE);
    // Import directory.
    s.u32(0x00, r + 0x100);
    s.u32(0x0c, r + 0x300);
    s.u32(0x10, r + 0x180);
    s.u32(0x14, r + 0x140);
    s.u32(0x18, 0xffff_ffff);
    s.u32(0x20, r + 0x320);
    s.u32(0x24, r + 0x1c0);
    // Lookup tables.
    s.u64(0x100, u64::from(r) + 0x340);
    s.u64(0x108, (1 << 63) | 42);
    s.u64(0x140, u64::from(r) + 0x360);
    // Delay-load directory.
    s.u32(0x80, 1);
    s.u32(0x84, r + 0x380);
    s.u32(0x8c, r + 0x200);
    s.u32(0x90, r + 0x240);
    s.u64(0x240, u64::from(r) + 0x3a0);
    s.u64(0x248, (1 << 63) | 9);
    // Names.
    s.put(0x300, b"KERNEL32.dll\0");
    s.put(0x320, b"USER32.dll\0");
    s.u16(0x340, 7);
    s.put(0x342, b"CreateFileW\0");
    s.u16(0x360, 3);
    s.put(0x362, b"MessageBoxW\0");
    s.put(0x380, b"VERSION.dll\0");
    s.put(0x3a2, b"GetFileVersionInfoW\0");
    // Bound import directory.
    s.u32(0x400, 0x5000_0000);
    s.u16(0x404, 0x10);
    s.put(0x410, b"USER32.dll\0");
    // Export directory.
    s.u32(0x500 + 12, r + 0x6c0);
    s.u32(0x500 + 16, 5);
    s.u32(0x500 + 20, 4);
    s.u32(0x500 + 24, 2);
    s.u32(0x500 + 28, r + 0x580);
    s.u32(0x500 + 32, r + 0x5a0);
    s.u32(0x500 + 36, r + 0x5b0);
    s.u32(0x580, 0x1000 + crate::x64::HELPER as u32);
    s.u32(0x584, r + 0x600);
    s.u32(0x58c, 0x1000 + crate::x64::MAIN as u32);
    s.u32(0x5a0, r + 0x640);
    s.u32(0x5a4, r + 0x650);
    s.u16(0x5b0, 0);
    s.u16(0x5b2, 1);
    s.put(0x600, b"NTDLL.RtlBeta\0");
    s.put(0x640, b"Alpha\0");
    s.put(0x650, b"Beta\0");
    s.put(0x6c0, b"facts.dll\0");

    let mut pe = pe64();
    while pe.len() % 0x200 != 0 {
        pe.push(0);
    }
    let raw = pe.len() as u32;
    pe.extend_from_slice(&s.into_vec());
    // A fifth section; the header area has room for it.
    let coff = 0x84;
    pe[coff + 2..coff + 4].copy_from_slice(&5u16.to_le_bytes());
    let sh = OPT + 240 + 4 * 40;
    pe[sh..sh + 6].copy_from_slice(b".facts");
    pe[sh + 8..sh + 12].copy_from_slice(&(FACTS_SIZE as u32).to_le_bytes());
    pe[sh + 12..sh + 16].copy_from_slice(&r.to_le_bytes());
    pe[sh + 16..sh + 20].copy_from_slice(&(FACTS_SIZE as u32).to_le_bytes());
    pe[sh + 20..sh + 24].copy_from_slice(&raw.to_le_bytes());
    pe[sh + 36..sh + 40].copy_from_slice(&0x4000_0040u32.to_le_bytes());
    set_dir(&mut pe, 0, r + 0x500, 0x200);
    set_dir(&mut pe, 1, r, 60);
    set_dir(&mut pe, 11, r + 0x400, 0x20);
    set_dir(&mut pe, 13, r + 0x80, 64);
    pe
}

/// `pe` with one `WIN_CERTIFICATE` holding `payload` at the (eight-byte aligned) end of the file.
pub fn pe_with_certificate(pe: &[u8], cert_type: u16, payload: &[u8]) -> Vec<u8> {
    let mut out = pe.to_vec();
    while out.len() % 8 != 0 {
        out.push(0);
    }
    let offset = out.len() as u32;
    let length = 8 + payload.len() as u32;
    out.extend_from_slice(&length.to_le_bytes());
    out.extend_from_slice(&0x0200u16.to_le_bytes());
    out.extend_from_slice(&cert_type.to_le_bytes());
    out.extend_from_slice(payload);
    while out.len() % 8 != 0 {
        out.push(0);
    }
    let size = out.len() as u32 - offset;
    set_dir(&mut out, 4, offset, size);
    out
}

/// The file hash Authenticode signs, worked out here on its own so that a test of the reader
/// doesn't compare it with itself: everything except the checksum, the security directory entry
/// and the table.
fn authenticode_sha256(padded_pe: &[u8]) -> [u8; 32] {
    let checksum = OPT + 64;
    let entry = DIRS + 4 * 8;
    let mut v = Vec::new();
    v.extend_from_slice(&padded_pe[..checksum]);
    v.extend_from_slice(&padded_pe[checksum + 4..entry]);
    v.extend_from_slice(&padded_pe[entry + 8..]);
    sha256(&v)
}

fn seq(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x30, &parts.concat())
}

fn set(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x31, &parts.concat())
}

/// A PKCS#7 block signing `file_digest` as Authenticode does, with the shared RSA key.
pub fn authenticode_block(file_digest: &[u8; 32], cn: &str, o: &str, with_timestamp: bool) -> Vec<u8> {
    let sha256_alg = seq(&[der_oid("2.16.840.1.101.3.4.2.1"), der(0x05, &[])]);
    let spc = "1.3.6.1.4.1.311.2.1.4";
    let attribute = seq(&[der_oid("1.3.6.1.4.1.311.2.1.15")]);
    let digest_info = seq(&[sha256_alg.clone(), der(0x04, file_digest)]);
    let indirect_value = [attribute, digest_info].concat();
    let indirect = der(0x30, &indirect_value);
    let content_type = seq(&[der_oid("1.2.840.113549.1.9.3"), set(&[der_oid(spc)])]);
    let message_digest = seq(&[der_oid("1.2.840.113549.1.9.4"), set(&[der(0x04, &sha256(&indirect_value))])]);
    let attrs = [content_type, message_digest].concat();
    let signature = rsa_sign_sha256(&der(0x31, &attrs));
    let name = seq(&[set(&[seq(&[der_oid("2.5.4.3"), der(0x0c, cn.as_bytes())])]), set(&[seq(&[der_oid("2.5.4.10"), der(0x0c, o.as_bytes())])])]);
    let mut signer = vec![
        der(0x02, &[1]),
        seq(&[name, der(0x02, &[1, 2, 3, 4, 5])]),
        sha256_alg.clone(),
        der(0xa0, &attrs),
        seq(&[der_oid("1.2.840.113549.1.1.1"), der(0x05, &[])]),
        der(0x04, &signature),
    ];
    if with_timestamp {
        signer.push(der(0xa1, &seq(&[der_oid("1.3.6.1.4.1.311.3.3.1"), set(&[der(0x05, &[])])])));
    }
    let encap = seq(&[der_oid(spc), der(0xa0, &indirect)]);
    let signed = seq(&[der(0x02, &[1]), set(&[sha256_alg]), encap, der(0xa0, &self_signed_rsa(cn, o)), set(&[seq(&signer)])]);
    seq(&[der_oid("1.2.840.113549.1.7.2"), der(0xa0, &signed)])
}

/// [`pe_facts`] genuinely signed by "Craft Signer".
pub fn signed_pe() -> Vec<u8> {
    let mut pe = pe_facts();
    while pe.len() % 8 != 0 {
        pe.push(0);
    }
    let digest = authenticode_sha256(&pe);
    pe_with_certificate(&pe, 2, &authenticode_block(&digest, "Craft Signer", "Craft Org", true))
}

/// A little-endian ELF64 shared library exporting `alpha@LIB_1.0`, `beta@LIB_2.0` (weak data) and
/// a hidden symbol, and needing `puts@GLIBC_2.2.5` from `libc.so.6`.
pub fn elf_versioned_library() -> Vec<u8> {
    let mut strs = vec![0u8];
    let mut add = |s: &str| {
        let at = strs.len() as u32;
        strs.extend_from_slice(s.as_bytes());
        strs.push(0);
        at
    };
    let (alpha, beta, hidden, puts, libc, glibc, v1, v2) =
        (add("alpha"), add("beta"), add("hidden_fn"), add("puts"), add("libc.so.6"), add("GLIBC_2.2.5"), add("LIB_1.0"), add("LIB_2.0"));
    // name, info, other, shndx, value, size
    let syms: [(u32, u8, u8, u16, u64, u64); 5] =
        [(0, 0, 0, 0, 0, 0), (alpha, 0x12, 0, 1, 0x1000, 16), (beta, 0x21, 0, 1, 0x1010, 8), (hidden, 0x12, 2, 1, 0x1020, 4), (puts, 0x12, 0, 0, 0, 0)];
    let mut dynsym = Vec::new();
    for s in syms {
        dynsym.extend_from_slice(&s.0.to_le_bytes());
        dynsym.push(s.1);
        dynsym.push(s.2);
        dynsym.extend_from_slice(&s.3.to_le_bytes());
        dynsym.extend_from_slice(&s.4.to_le_bytes());
        dynsym.extend_from_slice(&s.5.to_le_bytes());
    }
    let versym: Vec<u8> = [0u16, 2, 3 | 0x8000, 1, 4].iter().flat_map(|v| v.to_le_bytes()).collect();
    let mut verdef = Buf::with_len(56);
    for (i, (ndx, name, next)) in [(2u16, v1, 28u32), (3, v2, 0)].iter().enumerate() {
        let o = i * 28;
        verdef.u16(o, 1);
        verdef.u16(o + 4, *ndx);
        verdef.u16(o + 6, 1);
        verdef.u32(o + 12, 20);
        verdef.u32(o + 16, *next);
        verdef.u32(o + 20, *name);
    }
    let mut verneed = Buf::with_len(32);
    verneed.u16(0, 1);
    verneed.u16(2, 1);
    verneed.u32(4, libc);
    verneed.u32(8, 16);
    verneed.u16(16 + 6, 4);
    verneed.u32(16 + 8, glibc);
    elf_from_sections(&[
        (".text", 1, 6, vec![0xc3; 0x30], 0, 0),
        (".dynsym", 11, 2, dynsym, 3, 24),
        (".dynstr", 3, 2, strs, 0, 0),
        (".gnu.version", 0x6fff_ffff, 2, versym, 2, 2),
        (".gnu.version_d", 0x6fff_fffd, 2, verdef.into_vec(), 3, 0),
        (".gnu.version_r", 0x6fff_fffe, 2, verneed.into_vec(), 3, 0),
    ])
}

/// An ELF64 file from `(name, type, flags, bytes, link, entsize)` sections. `.text` loads at 0x1000.
fn elf_from_sections(sections: &[(&str, u32, u64, Vec<u8>, u32, u64)]) -> Vec<u8> {
    let mut b = Buf::with_len(0x1000);
    let mut placed = Vec::new();
    let mut pos = 0x1000usize;
    for s in sections {
        pos = (pos + 15) & !15;
        b.put(pos, &s.3);
        placed.push(pos);
        pos += s.3.len();
    }
    let mut shstr = vec![0u8];
    let mut names = Vec::new();
    for s in sections {
        names.push(shstr.len() as u32);
        shstr.extend_from_slice(s.0.as_bytes());
        shstr.push(0);
    }
    let shstr_name = shstr.len() as u32;
    shstr.extend_from_slice(b".shstrtab\0");
    pos = (pos + 15) & !15;
    let shstr_off = pos;
    b.put(pos, &shstr);
    pos += shstr.len();
    let shoff = (pos + 7) & !7;
    for (i, s) in sections.iter().enumerate() {
        let o = shoff + (i + 1) * 64;
        b.u32(o, names[i]);
        b.u32(o + 4, s.1);
        b.u64(o + 8, s.2);
        b.u64(o + 16, placed[i] as u64);
        b.u64(o + 24, placed[i] as u64);
        b.u64(o + 32, s.3.len() as u64);
        b.u32(o + 40, s.4);
        b.u64(o + 48, 8);
        b.u64(o + 56, s.5);
    }
    let last = shoff + (sections.len() + 1) * 64;
    b.u32(last, shstr_name);
    b.u32(last + 4, 3);
    b.u64(last + 24, shstr_off as u64);
    b.u64(last + 32, shstr.len() as u64);
    b.u64(last + 56, 0);
    b.put(0, b"\x7fELF\x02\x01\x01");
    b.u16(16, 3);
    b.u16(18, 62);
    b.u32(20, 1);
    b.u64(24, 0x1000);
    b.u64(32, 0x40);
    b.u64(40, shoff as u64);
    b.u16(52, 64);
    b.u16(54, 56);
    b.u16(56, 1);
    b.u16(58, 64);
    b.u16(60, sections.len() as u16 + 2);
    b.u16(62, sections.len() as u16 + 1);
    // One PT_LOAD mapping the whole file at its own offsets.
    let len = b.0.len() as u64;
    b.u32(0x40, 1);
    b.u32(0x44, 7);
    b.u64(0x40 + 32, len);
    b.u64(0x40 + 40, len);
    b.u64(0x40 + 48, 0x1000);
    b.into_vec()
}

/// A function body for [`elf_with_functions`]: frame setup, `mov eax, value`, some padding work
/// and a return. Two bodies with one `value` are byte for byte the same.
pub fn plain_body(value: u32) -> Vec<u8> {
    let mut c = vec![0x55, 0x48, 0x89, 0xe5, 0xb8];
    c.extend_from_slice(&value.to_le_bytes());
    c.extend_from_slice(&[0x83, 0xc0, 0x01, 0x83, 0xc0, 0x02, 0x83, 0xc0, 0x03, 0x5d, 0xc3]);
    c
}

/// A body calling the function that is `callee_offset` bytes into `.text`, from `at` bytes into it.
pub fn calling_body(at: usize, callee_offset: usize, value: u32) -> Vec<u8> {
    let mut c = vec![0x55, 0x48, 0x89, 0xe5, 0xb8];
    c.extend_from_slice(&value.to_le_bytes());
    c.push(0xe8);
    let next = at + c.len() + 4;
    c.extend_from_slice(&((callee_offset as i64 - next as i64) as i32).to_le_bytes());
    c.extend_from_slice(&[0x83, 0xc0, 0x01, 0x83, 0xc0, 0x02, 0x5d, 0xc3]);
    c
}

/// An ELF64 x86-64 program of exactly these functions, each 16-byte aligned, named in `.symtab`
/// unless its name is empty. `.text` loads at 0x1000; `layout` gives each function's offset.
pub fn elf_with_functions(funcs: &[(&str, Vec<u8>)]) -> Vec<u8> {
    let offsets = layout(funcs.iter().map(|f| f.1.len()));
    let mut text = Vec::new();
    for (i, f) in funcs.iter().enumerate() {
        text.resize(offsets[i], 0xcc);
        text.extend_from_slice(&f.1);
    }
    let mut strs = vec![0u8];
    let mut syms = vec![0u8; 24];
    let text_addr = 0x1000u64;
    for (i, f) in funcs.iter().enumerate() {
        if f.0.is_empty() {
            continue;
        }
        let at = strs.len() as u32;
        strs.extend_from_slice(f.0.as_bytes());
        strs.push(0);
        syms.extend_from_slice(&at.to_le_bytes());
        syms.push(0x12);
        syms.push(0);
        syms.extend_from_slice(&1u16.to_le_bytes());
        syms.extend_from_slice(&(text_addr + offsets[i] as u64).to_le_bytes());
        syms.extend_from_slice(&(f.1.len() as u64).to_le_bytes());
    }
    elf_from_sections(&[(".text", 1, 6, text, 0, 0), (".symtab", 2, 0, syms, 3, 24), (".strtab", 3, 0, strs, 0, 0)])
}

/// The offsets [`elf_with_functions`] gives bodies of these lengths.
pub fn layout(lengths: impl Iterator<Item = usize>) -> Vec<usize> {
    let mut out = Vec::new();
    let mut pos = 0usize;
    for len in lengths {
        pos = (pos + 15) & !15;
        out.push(pos);
        pos += len;
    }
    out
}

fn gg_str(v: &mut Vec<u8>, s: &str) {
    v.extend_from_slice(&(s.len() as u64).to_le_bytes());
    v.extend_from_slice(s.as_bytes());
}

fn gg_kv_str(v: &mut Vec<u8>, k: &str, s: &str) {
    gg_str(v, k);
    v.extend_from_slice(&8u32.to_le_bytes());
    gg_str(v, s);
}

fn gg_kv_u32(v: &mut Vec<u8>, k: &str, n: u32) {
    gg_str(v, k);
    v.extend_from_slice(&4u32.to_le_bytes());
    v.extend_from_slice(&n.to_le_bytes());
}

fn gg_tensor(v: &mut Vec<u8>, name: &str, shape: &[u64], ty: u32, offset: u64) {
    gg_str(v, name);
    v.extend_from_slice(&(shape.len() as u32).to_le_bytes());
    for d in shape {
        v.extend_from_slice(&d.to_le_bytes());
    }
    v.extend_from_slice(&ty.to_le_bytes());
    v.extend_from_slice(&offset.to_le_bytes());
}

/// The header of a GGUF file: a "llama" model called "Tiny", mostly Q4_K, with a token list, two
/// quantized tensors and one F32 tensor. Returns the header bytes; no tensor data follows.
pub fn gguf_header(version: u32) -> Vec<u8> {
    let mut v = b"GGUF".to_vec();
    v.extend_from_slice(&version.to_le_bytes());
    v.extend_from_slice(&3u64.to_le_bytes());
    v.extend_from_slice(&5u64.to_le_bytes());
    gg_kv_str(&mut v, "general.architecture", "llama");
    gg_kv_str(&mut v, "general.name", "Tiny");
    gg_kv_u32(&mut v, "general.file_type", 15);
    gg_kv_u32(&mut v, "llama.context_length", 2048);
    gg_str(&mut v, "tokenizer.ggml.tokens");
    v.extend_from_slice(&9u32.to_le_bytes());
    v.extend_from_slice(&8u32.to_le_bytes());
    v.extend_from_slice(&10u64.to_le_bytes());
    for i in 0..10 {
        gg_str(&mut v, &format!("tok{i}"));
    }
    gg_tensor(&mut v, "tok_embeddings.weight", &[1000, 256], 12, 0);
    gg_tensor(&mut v, "layers.0.weight", &[256, 256], 12, 0x40000);
    gg_tensor(&mut v, "norm.weight", &[256], 0, 0x60000);
    v
}

/// A safetensors file with its header and `data_len` bytes of zeroed tensor data.
pub fn safetensors_file(header_json: &str, data_len: usize) -> Vec<u8> {
    let mut v = (header_json.len() as u64).to_le_bytes().to_vec();
    v.extend_from_slice(header_json.as_bytes());
    v.resize(v.len() + data_len, 0);
    v
}

/// A header naming two tensors (24 + 8 bytes of data) and some metadata.
pub const SAFETENSORS_HEADER: &str = r#"{"__metadata__":{"format":"pt","modelspec.architecture":"tiny-net"},"a.weight":{"dtype":"F32","shape":[2,3],"data_offsets":[0,24]},"b.bias":{"dtype":"U8","shape":[8],"data_offsets":[24,32]}}"#;
