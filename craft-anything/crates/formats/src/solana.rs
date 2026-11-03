//! Solana sBPF program files: ELF64 little-endian objects whose machine type is `EM_BPF` (247).
//!
//! This is a focused, self-contained ELF64-LE reader (not the generic `object` path) that pulls
//! out exactly what an sBPF analysis needs: the machine type and `e_flags` (to guess the sBPF
//! version), the entrypoint, the sections (`.text`, `.rodata`, relocation sections), the symbol
//! tables (including `.dynsym`), the relocations with their Solana relocation-type names, and the
//! syscalls — Solana resolves helper calls by the murmur3-32 hash of the syscall symbol name, so
//! we implement that hash and map the known names to their hashes.
//!
//! Honest limits: no account-model or runtime semantics, and no Anchor IDL unless one is supplied
//! separately as a sidecar. Nothing here executes code or panics on hostile input.

use crate::bytes::Reader;
use crate::{FormatError, hex_addr};
use serde::Serialize;

/// ELF machine type for (classic and Solana) BPF.
pub const EM_BPF: u16 = 247;
/// Largest program we read into memory (64 MiB).
pub const MAX_INPUT: usize = 64 << 20;

const MAX_SECTIONS: usize = 4096;
const MAX_SYMBOLS: usize = 400_000;
const MAX_RELOCS: usize = 400_000;

/// MurmurHash3 x86 32-bit, as Solana uses it (seed 0) to hash syscall symbol names.
pub fn murmur3_32(data: &[u8], seed: u32) -> u32 {
    const C1: u32 = 0xcc9e_2d51;
    const C2: u32 = 0x1b87_3593;
    let mut h = seed;
    let nblocks = data.len() / 4;
    for i in 0..nblocks {
        let base = i * 4;
        let k = u32::from_le_bytes([
            data.get(base).copied().unwrap_or(0),
            data.get(base + 1).copied().unwrap_or(0),
            data.get(base + 2).copied().unwrap_or(0),
            data.get(base + 3).copied().unwrap_or(0),
        ]);
        let k = k.wrapping_mul(C1).rotate_left(15).wrapping_mul(C2);
        h ^= k;
        h = h.rotate_left(13).wrapping_mul(5).wrapping_add(0xe654_6b64);
    }
    let tail = data.get(nblocks * 4..).unwrap_or(&[]);
    let mut k1 = 0u32;
    if let Some(&b) = tail.get(2) {
        k1 ^= u32::from(b) << 16;
    }
    if let Some(&b) = tail.get(1) {
        k1 ^= u32::from(b) << 8;
    }
    if let Some(&b) = tail.first() {
        k1 ^= u32::from(b);
        k1 = k1.wrapping_mul(C1).rotate_left(15).wrapping_mul(C2);
        h ^= k1;
    }
    h ^= data.len() as u32;
    h ^= h >> 16;
    h = h.wrapping_mul(0x85eb_ca6b);
    h ^= h >> 13;
    h = h.wrapping_mul(0xc2b2_ae35);
    h ^= h >> 16;
    h
}

/// Publicly documented Solana runtime syscalls (BPF loader helper functions). Function names are
/// the stable ABI; Solana hashes them with [`murmur3_32`] (seed 0) at the call site.
pub const KNOWN_SYSCALLS: &[&str] = &[
    "abort",
    "sol_panic_",
    "sol_log_",
    "sol_log_64_",
    "sol_log_compute_units_",
    "sol_log_pubkey",
    "sol_log_data",
    "sol_create_program_address",
    "sol_try_find_program_address",
    "sol_sha256",
    "sol_keccak256",
    "sol_secp256k1_recover",
    "sol_blake3",
    "sol_poseidon",
    "sol_get_clock_sysvar",
    "sol_get_epoch_schedule_sysvar",
    "sol_get_fees_sysvar",
    "sol_get_rent_sysvar",
    "sol_get_last_restart_slot",
    "sol_get_epoch_rewards_sysvar",
    "sol_get_sysvar",
    "sol_get_epoch_stake",
    "sol_memcpy_",
    "sol_memmove_",
    "sol_memcmp_",
    "sol_memset_",
    "sol_invoke_signed_c",
    "sol_invoke_signed_rust",
    "sol_set_return_data",
    "sol_get_return_data",
    "sol_get_processed_sibling_instruction",
    "sol_get_stack_height",
    "sol_curve_validate_point",
    "sol_curve_group_op",
    "sol_curve_multiscalar_mul",
    "sol_curve_pairing_map",
    "sol_alt_bn128_group_op",
    "sol_alt_bn128_compression",
    "sol_big_mod_exp",
    "sol_remaining_compute_units",
];

/// The known syscall whose murmur3 hash equals `hash`, if any.
pub fn syscall_by_hash(hash: u32) -> Option<&'static str> {
    KNOWN_SYSCALLS.iter().copied().find(|n| murmur3_32(n.as_bytes(), 0) == hash)
}

/// Solana / BPF ELF relocation type name.
pub fn reloc_type_name(t: u32) -> &'static str {
    match t {
        0 => "R_BPF_NONE",
        1 => "R_BPF_64_64",
        2 => "R_BPF_64_ABS64",
        3 => "R_BPF_64_ABS32",
        4 => "R_BPF_64_NODYLD32",
        8 => "R_BPF_64_RELATIVE",
        10 => "R_BPF_64_32",
        _ => "R_BPF_UNKNOWN",
    }
}

fn section_type_name(t: u32) -> &'static str {
    match t {
        0 => "NULL",
        1 => "PROGBITS",
        2 => "SYMTAB",
        3 => "STRTAB",
        4 => "RELA",
        5 => "HASH",
        6 => "DYNAMIC",
        7 => "NOTE",
        8 => "NOBITS",
        9 => "REL",
        11 => "DYNSYM",
        _ => "OTHER",
    }
}

fn machine_name(m: u16) -> &'static str {
    match m {
        0 => "none",
        3 => "x86",
        40 => "arm",
        62 => "x86_64",
        183 => "arm64",
        243 => "riscv",
        EM_BPF => "bpf",
        _ => "other",
    }
}

/// The ELF `e_machine` of an ELF64/ELF32 image, or `None` when the bytes are not ELF.
pub fn elf_machine(data: &[u8]) -> Option<u16> {
    if !data.starts_with(b"\x7fELF") {
        return None;
    }
    let r = Reader::new(data);
    match r.u8(5)? {
        1 => r.u16_le(18), // little-endian
        2 => r.u16_be(18), // big-endian
        _ => None,
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SbpfSection {
    pub name: String,
    pub kind: &'static str,
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub file_offset: u64,
    pub size: u64,
    pub read: bool,
    pub write: bool,
    pub exec: bool,
    /// Loaded into memory (SHF_ALLOC).
    pub alloc: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SbpfSymbol {
    pub name: String,
    #[serde(with = "hex_addr")]
    pub value: u64,
    pub size: u64,
    /// `function`, `object`, `section`, `file`, `notype`.
    pub kind: &'static str,
    pub global: bool,
    pub defined: bool,
    /// From `.dynsym` rather than `.symtab`.
    pub dynamic: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SbpfReloc {
    #[serde(with = "hex_addr")]
    pub offset: u64,
    pub type_id: u32,
    pub type_name: &'static str,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub symbol: String,
    pub addend: i64,
    /// For a symbol-relative call, the murmur3 hash Solana would place at the call site.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub symbol_hash: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Syscall {
    pub name: String,
    pub hash: u32,
    /// True when `name` is one of the documented runtime syscalls.
    pub known: bool,
    /// Call-site file offsets (from relocations), if any were found.
    #[serde(with = "hex_addr::vec")]
    pub call_sites: Vec<u64>,
}

/// What [`inspect`] returns.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SolanaProgram {
    pub e_machine: u16,
    pub machine_name: &'static str,
    /// True only when the machine type is `EM_BPF` (247).
    pub is_sbpf: bool,
    pub e_type: u16,
    pub e_flags: u32,
    /// `sbpf_v1` or `sbpf_v2` — our guess from `e_flags`.
    pub sbpf_version: &'static str,
    pub version_note: String,
    #[serde(with = "hex_addr")]
    pub entry: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub entry_symbol: Option<String>,
    pub sections: Vec<SbpfSection>,
    /// Convenience: the `.text` section's byte range, so callers can slice the code out.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<TextRange>,
    pub symbols: Vec<SbpfSymbol>,
    pub relocations: Vec<SbpfReloc>,
    pub syscalls: Vec<Syscall>,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct TextRange {
    #[serde(with = "hex_addr")]
    pub addr: u64,
    pub file_offset: u64,
    pub size: u64,
}

struct RawSection {
    name: String,
    name_idx: u32,
    sh_type: u32,
    sh_flags: u64,
    sh_addr: u64,
    sh_offset: u64,
    sh_size: u64,
    sh_link: u32,
    sh_entsize: u64,
}

/// Parse a Solana / classic-eBPF ELF. Returns the structure even when the machine type is not
/// `EM_BPF` (with `is_sbpf == false`) so callers can give a clean "not an sBPF program" message.
pub fn inspect(data: &[u8]) -> Result<SolanaProgram, FormatError> {
    if data.len() > MAX_INPUT {
        return Err(FormatError::TooLarge(format!("{} bytes", data.len())));
    }
    if !data.starts_with(b"\x7fELF") {
        return Err(FormatError::Malformed("not an ELF file".into()));
    }
    let r = Reader::new(data);
    let class = r.u8(4).ok_or_else(|| FormatError::Truncated("ELF ident".into()))?;
    let enc = r.u8(5).ok_or_else(|| FormatError::Truncated("ELF ident".into()))?;
    if class != 2 {
        // Solana sBPF is always ELF64. Report the machine so the tool can explain.
        let e_machine = elf_machine(data).unwrap_or(0);
        return Ok(not_sbpf(e_machine));
    }
    if enc != 1 {
        let e_machine = r.u16_be(18).unwrap_or(0);
        return Ok(not_sbpf(e_machine));
    }

    let e_type = r.u16_le(16).ok_or_else(|| FormatError::Truncated("e_type".into()))?;
    let e_machine = r.u16_le(18).ok_or_else(|| FormatError::Truncated("e_machine".into()))?;
    let e_entry = r.u64_le(24).ok_or_else(|| FormatError::Truncated("e_entry".into()))?;
    let e_shoff = r.u64_le(40).ok_or_else(|| FormatError::Truncated("e_shoff".into()))?;
    let e_flags = r.u32_le(48).ok_or_else(|| FormatError::Truncated("e_flags".into()))?;
    let e_shentsize = r.u16_le(58).unwrap_or(64);
    let e_shnum = usize::from(r.u16_le(60).unwrap_or(0)).min(MAX_SECTIONS);
    let e_shstrndx = usize::from(r.u16_le(62).unwrap_or(0));

    let mut warnings = Vec::new();
    if e_machine != EM_BPF {
        warnings.push(format!("e_machine is {} ({}), not EM_BPF (247)", e_machine, machine_name(e_machine)));
    }
    let (sbpf_version, version_note) = sbpf_version_from_flags(e_flags);

    // Section headers.
    let shentsize = usize::from(e_shentsize).max(64);
    let shoff = usize::try_from(e_shoff).unwrap_or(usize::MAX);
    let mut raw_sections: Vec<RawSection> = Vec::new();
    // First pass: read the header fields; names come from the string table afterwards.
    for i in 0..e_shnum {
        let Some(o) = i.checked_mul(shentsize).and_then(|x| x.checked_add(shoff)) else { break };
        let (Some(name_idx), Some(sh_type), Some(sh_flags), Some(sh_addr), Some(sh_offset), Some(sh_size), Some(sh_link), Some(sh_entsize)) =
            (r.u32_le(o), r.u32_le(o + 4), r.u64_le(o + 8), r.u64_le(o + 16), r.u64_le(o + 24), r.u64_le(o + 32), r.u32_le(o + 40), r.u64_le(o + 56))
        else {
            break;
        };
        raw_sections.push(RawSection { name: String::new(), name_idx, sh_type, sh_flags, sh_addr, sh_offset, sh_size, sh_link, sh_entsize });
    }
    // The section-name string table, then fill in each section's name.
    let shstr = raw_sections.get(e_shstrndx).and_then(|s| str_table(data, s.sh_offset, s.sh_size));
    for s in &mut raw_sections {
        s.name = shstr.as_ref().and_then(|tab| read_str(tab, s.name_idx)).unwrap_or_default();
    }

    let sections: Vec<SbpfSection> = raw_sections
        .iter()
        .map(|s| SbpfSection {
            name: s.name.clone(),
            kind: section_type_name(s.sh_type),
            addr: s.sh_addr,
            file_offset: s.sh_offset,
            size: s.sh_size,
            read: true,
            write: s.sh_flags & 0x1 != 0, // SHF_WRITE
            exec: s.sh_flags & 0x4 != 0,  // SHF_EXECINSTR
            alloc: s.sh_flags & 0x2 != 0, // SHF_ALLOC
        })
        .collect();

    let text = raw_sections
        .iter()
        .find(|s| s.name == ".text")
        .or_else(|| raw_sections.iter().find(|s| s.sh_flags & 0x4 != 0 && s.sh_type == 1))
        .map(|s| TextRange { addr: s.sh_addr, file_offset: s.sh_offset, size: s.sh_size });

    // Symbols: read every SYMTAB and DYNSYM; their sh_link names the matching string table.
    let mut symbols: Vec<SbpfSymbol> = Vec::new();
    for s in &raw_sections {
        if s.sh_type != 2 && s.sh_type != 11 {
            continue;
        }
        let dynamic = s.sh_type == 11;
        let strtab = raw_sections.get(s.sh_link as usize).and_then(|st| str_table(data, st.sh_offset, st.sh_size));
        let entsize = if s.sh_entsize >= 24 { s.sh_entsize as usize } else { 24 };
        let count = (s.sh_size as usize) / entsize;
        let base = usize::try_from(s.sh_offset).unwrap_or(usize::MAX);
        for i in 0..count.min(MAX_SYMBOLS) {
            let Some(o) = i.checked_mul(entsize).and_then(|x| x.checked_add(base)) else { break };
            let (Some(st_name), Some(st_info), Some(st_shndx), Some(st_value), Some(st_size)) =
                (r.u32_le(o), r.u8(o + 4), r.u16_le(o + 6), r.u64_le(o + 8), r.u64_le(o + 16))
            else {
                break;
            };
            let name = strtab.as_ref().and_then(|t| read_str(t, st_name)).unwrap_or_default();
            if name.is_empty() && st_value == 0 && st_name == 0 {
                continue; // the null symbol
            }
            let kind = match st_info & 0x0f {
                1 => "object",
                2 => "function",
                3 => "section",
                4 => "file",
                _ => "notype",
            };
            symbols.push(SbpfSymbol { name, value: st_value, size: st_size, kind, global: (st_info >> 4) != 0, defined: st_shndx != 0, dynamic });
            if symbols.len() >= MAX_SYMBOLS {
                break;
            }
        }
    }

    // Relocations: SHT_RELA (24 bytes) and SHT_REL (16 bytes). sh_link names the symbol table.
    let mut relocations: Vec<SbpfReloc> = Vec::new();
    for s in &raw_sections {
        let is_rela = s.sh_type == 4;
        let is_rel = s.sh_type == 9;
        if !is_rela && !is_rel {
            continue;
        }
        let symtab = raw_sections.get(s.sh_link as usize);
        let strtab = symtab.and_then(|st| raw_sections.get(st.sh_link as usize)).and_then(|st| str_table(data, st.sh_offset, st.sh_size));
        let symtab_off = symtab.map(|st| st.sh_offset).unwrap_or(0);
        let symtab_ent = symtab.map(|st| if st.sh_entsize >= 24 { st.sh_entsize as usize } else { 24 }).unwrap_or(24);
        let entsize = if is_rela { 24usize } else { 16 };
        let count = (s.sh_size as usize) / entsize;
        let base = usize::try_from(s.sh_offset).unwrap_or(usize::MAX);
        for i in 0..count.min(MAX_RELOCS) {
            let Some(o) = i.checked_mul(entsize).and_then(|x| x.checked_add(base)) else { break };
            let (Some(r_offset), Some(r_info)) = (r.u64_le(o), r.u64_le(o + 8)) else { break };
            let addend = if is_rela { r.u64_le(o + 16).map(|v| v as i64).unwrap_or(0) } else { 0 };
            let sym_idx = (r_info >> 32) as usize;
            let type_id = (r_info & 0xffff_ffff) as u32;
            // Resolve the referenced symbol name from the relocation's symbol table.
            let sym_name = {
                let so = usize::try_from(symtab_off).ok().and_then(|b| sym_idx.checked_mul(symtab_ent).and_then(|x| x.checked_add(b)));
                so.and_then(|so| r.u32_le(so)).and_then(|n| strtab.as_ref().and_then(|t| read_str(t, n))).unwrap_or_default()
            };
            let symbol_hash = (!sym_name.is_empty()).then(|| murmur3_32(sym_name.as_bytes(), 0));
            relocations.push(SbpfReloc { offset: r_offset, type_id, type_name: reloc_type_name(type_id), symbol: sym_name, addend, symbol_hash });
            if relocations.len() >= MAX_RELOCS {
                break;
            }
        }
    }

    // Syscalls: undefined symbols that are called, plus any name matching the known registry.
    // We group call sites by symbol name from the relocations.
    let mut syscalls: Vec<Syscall> = Vec::new();
    {
        use std::collections::BTreeMap;
        let defined: std::collections::BTreeSet<&str> = symbols.iter().filter(|s| s.defined).map(|s| s.name.as_str()).collect();
        let mut by_name: BTreeMap<String, Vec<u64>> = BTreeMap::new();
        for rel in &relocations {
            if rel.symbol.is_empty() {
                continue;
            }
            // A call relocation to an undefined symbol is a syscall/helper reference.
            let is_call_reloc = matches!(rel.type_id, 10); // R_BPF_64_32 patches a call immediate
            let undefined = !defined.contains(rel.symbol.as_str());
            if is_call_reloc && (undefined || KNOWN_SYSCALLS.contains(&rel.symbol.as_str())) {
                by_name.entry(rel.symbol.clone()).or_default().push(rel.offset);
            }
        }
        // Also list undefined FUNC dynamic symbols that look like syscalls even without a reloc.
        for s in &symbols {
            if !s.defined && (s.name.starts_with("sol_") || KNOWN_SYSCALLS.contains(&s.name.as_str())) {
                by_name.entry(s.name.clone()).or_default();
            }
        }
        for (name, sites) in by_name {
            let hash = murmur3_32(name.as_bytes(), 0);
            syscalls.push(Syscall { known: KNOWN_SYSCALLS.contains(&name.as_str()), name, hash, call_sites: sites });
        }
    }

    // Entry symbol: a defined symbol at e_entry, else a symbol named "entrypoint".
    let entry_symbol = symbols
        .iter()
        .find(|s| s.defined && s.value == e_entry && s.kind == "function")
        .or_else(|| symbols.iter().find(|s| s.name == "entrypoint"))
        .map(|s| s.name.clone());

    match text {
        Some(t) => {
            let end = usize::try_from(t.file_offset).ok().and_then(|s| usize::try_from(t.size).ok().and_then(|l| s.checked_add(l)));
            if end.is_none_or(|e| e > data.len()) {
                warnings.push(format!(".text section at {:#x} ({} bytes) extends past end of file ({} bytes)", t.file_offset, t.size, data.len()));
            }
        }
        None => warnings.push("no .text (executable PROGBITS) section found".into()),
    }

    Ok(SolanaProgram {
        e_machine,
        machine_name: machine_name(e_machine),
        is_sbpf: e_machine == EM_BPF,
        e_type,
        e_flags,
        sbpf_version,
        version_note,
        entry: e_entry,
        entry_symbol,
        sections,
        text,
        symbols,
        relocations,
        syscalls,
        warnings,
    })
}

/// Our sBPF version guess from `e_flags`, and a note explaining it. `0` is the original dialect;
/// anything non-zero we treat as v2+. Solana has used more than one flag convention, so the note
/// states exactly what we saw.
pub fn sbpf_version_from_flags(flags: u32) -> (&'static str, String) {
    if flags == 0 {
        ("sbpf_v1", "e_flags is 0: assuming the original sBPF v1 dialect.".to_string())
    } else {
        ("sbpf_v2", format!("e_flags is {flags:#x} (non-zero): assuming a newer sBPF (v2+) dialect; opcode meanings can differ between Solana sBPF versions."))
    }
}

fn not_sbpf(e_machine: u16) -> SolanaProgram {
    SolanaProgram {
        e_machine,
        machine_name: machine_name(e_machine),
        is_sbpf: false,
        e_type: 0,
        e_flags: 0,
        sbpf_version: "n/a",
        version_note: "not an ELF64 little-endian BPF object".to_string(),
        entry: 0,
        entry_symbol: None,
        sections: Vec::new(),
        text: None,
        symbols: Vec::new(),
        relocations: Vec::new(),
        syscalls: Vec::new(),
        warnings: vec![format!("machine type {} ({}) is not EM_BPF, or the file is not ELF64 LE", e_machine, machine_name(e_machine))],
    }
}

/// Read a string-table section's bytes, bounded.
fn str_table(data: &[u8], off: u64, size: u64) -> Option<Vec<u8>> {
    let start = usize::try_from(off).ok()?;
    let len = usize::try_from(size).ok()?.min(16 << 20);
    data.get(start..start.checked_add(len)?).map(|s| s.to_vec())
}

/// A NUL-terminated string at `idx` within a string table.
fn read_str(table: &[u8], idx: u32) -> Option<String> {
    let start = usize::try_from(idx).ok()?;
    let rest = table.get(start..)?;
    let end = rest.iter().position(|&b| b == 0).unwrap_or(rest.len());
    Some(String::from_utf8_lossy(rest.get(..end)?).into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn murmur_matches_known_vectors() {
        // Standard MurmurHash3 x86_32 test vectors (seed 0).
        assert_eq!(murmur3_32(b"", 0), 0);
        assert_eq!(murmur3_32(b"hello", 0), 0x248b_fa47);
        assert_eq!(murmur3_32(b"The quick brown fox jumps over the lazy dog", 0), 0x2e4f_f723);
    }

    #[test]
    fn syscall_hash_round_trips() {
        let h = murmur3_32(b"sol_log_", 0);
        assert_eq!(syscall_by_hash(h), Some("sol_log_"));
        assert_eq!(syscall_by_hash(0xffff_fffe), None);
    }

    #[test]
    fn version_from_flags() {
        assert_eq!(sbpf_version_from_flags(0).0, "sbpf_v1");
        assert_eq!(sbpf_version_from_flags(0x20).0, "sbpf_v2");
    }

    #[test]
    fn rejects_non_elf() {
        assert!(inspect(b"not elf").is_err());
        assert_eq!(elf_machine(b"nope"), None);
    }

    #[test]
    fn non_bpf_elf_is_marked() {
        // A minimal x86_64 ELF64 header.
        let mut b = vec![0u8; 64];
        b[..4].copy_from_slice(b"\x7fELF");
        b[4] = 2; // ELF64
        b[5] = 1; // LE
        b[16] = 2; // ET_EXEC
        b[18] = 62; // EM_X86_64
        let p = inspect(&b).unwrap();
        assert!(!p.is_sbpf);
        assert_eq!(p.e_machine, 62);
    }

    #[test]
    fn parses_the_fixture() {
        let elf = craft_anything_testkit::sbpf::program();
        let p = inspect(&elf).unwrap();
        assert!(p.is_sbpf);
        assert_eq!(p.e_machine, EM_BPF);
        assert_eq!(p.sbpf_version, "sbpf_v1");
        assert_eq!(p.entry, craft_anything_testkit::sbpf::TEXT_VADDR);
        assert_eq!(p.entry_symbol.as_deref(), Some("entrypoint"));
        // .text section is present and executable.
        let text = p.text.expect("text range");
        assert_eq!(text.addr, craft_anything_testkit::sbpf::TEXT_VADDR);
        assert_eq!(text.size, 24);
        assert!(p.sections.iter().any(|s| s.name == ".text" && s.exec));
        // The sol_log_ relocation resolves to a syscall.
        assert_eq!(p.relocations.len(), 1);
        assert_eq!(p.relocations[0].type_name, "R_BPF_64_32");
        assert_eq!(p.relocations[0].symbol, "sol_log_");
        let sc = p.syscalls.iter().find(|s| s.name == "sol_log_").expect("sol_log_ syscall");
        assert!(sc.known);
        assert_eq!(sc.hash, murmur3_32(b"sol_log_", 0));
        assert_eq!(sc.call_sites, vec![craft_anything_testkit::sbpf::TEXT_VADDR + 8]);
    }

    #[test]
    fn hostile_inputs_never_panic() {
        for len in 0..300usize {
            let junk: Vec<u8> = (0..len).map(|i| (i.wrapping_mul(131) ^ 0x7f) as u8).collect();
            let _ = inspect(&junk);
            let _ = elf_machine(&junk);
            let _ = murmur3_32(&junk, 0);
        }
        let mut elf = vec![0u8; 128];
        elf[..4].copy_from_slice(b"\x7fELF");
        elf[4] = 2;
        elf[5] = 1;
        elf[18] = 247;
        // Garbage section offsets must not panic.
        elf[40] = 0xff;
        elf[60] = 0xff; // huge shnum (capped)
        let _ = inspect(&elf);
    }
}
