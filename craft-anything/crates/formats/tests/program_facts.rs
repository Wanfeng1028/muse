//! Imports, exports, dynamic symbols, signature blocks and AI model headers, from synthetic files
//! and from every damaged form of them.
#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::indexing_slicing)]

use craft_anything_formats::authenticode::{self, HashStatus};
use craft_anything_formats::pe::{self, ImportKind};
use craft_anything_formats::verify::Verified;
use craft_anything_formats::{ai_model, elf, parse_binary};
use craft_anything_testkit::program_facts as pf;

const OPT: usize = 0x84 + 20;
const DIRS: usize = OPT + 112;

fn set_dir(pe: &mut [u8], index: usize, rva: u32, size: u32) {
    let o = DIRS + index * 8;
    pe[o..o + 4].copy_from_slice(&rva.to_le_bytes());
    pe[o + 4..o + 8].copy_from_slice(&size.to_le_bytes());
}

#[test]
fn imports_with_delay_bound_and_ordinals() {
    let d = pf::pe_facts();
    let h = pe::headers(&d).unwrap();
    let t = pe::import_table(&d, &h);
    assert!(t.warnings.is_empty() && !t.truncated, "{t:?}");
    let find = |n: &str| t.rows.iter().find(|r| r.name.as_deref() == Some(n)).unwrap();
    let create = find("CreateFileW");
    assert_eq!((create.library.as_str(), create.kind, create.hint, create.bound), ("KERNEL32.dll", ImportKind::Normal, Some(7), false));
    assert!(find("MessageBoxW").bound);
    let delayed = find("GetFileVersionInfoW");
    assert_eq!((delayed.library.as_str(), delayed.kind), ("VERSION.dll", ImportKind::Delay));
    assert_eq!(delayed.slot_va, Some(pe::headers(&d).unwrap().image_base + 0x6200));
    let by_ordinal: Vec<_> = t.rows.iter().filter(|r| r.ordinal.is_some()).map(|r| (r.library.as_str(), r.kind, r.ordinal)).collect();
    assert_eq!(by_ordinal, vec![("KERNEL32.dll", ImportKind::Normal, Some(42)), ("VERSION.dll", ImportKind::Delay, Some(9))]);
    assert_eq!(t.bound_modules[0].name, "USER32.dll");
    assert_eq!(t.bound_modules[0].timestamp, 0x5000_0000);
}

#[test]
fn delay_imports_reach_the_program_model() {
    let b = parse_binary(&pf::pe_facts()).unwrap();
    assert!(b.libraries.iter().any(|l| l == "VERSION.dll"), "{:?}", b.libraries);
    assert!(b.import_slots.iter().any(|s| s.name == "GetFileVersionInfoW"));
    assert!(b.imports.iter().any(|i| i.name == "VERSION#9" && i.ordinal == Some(9)));
}

#[test]
fn old_style_delay_descriptors_hold_addresses() {
    // Attributes bit 0 clear means virtual addresses; a 64-bit base can't fit them, so nothing
    // is misread and the reader says the table is out of reach.
    let mut d = pf::pe_facts();
    let h = pe::headers(&d).unwrap();
    let off = h.rva_to_offset(0x6080).unwrap();
    d[off] = 0;
    let t = pe::import_table(&d, &pe::headers(&d).unwrap());
    assert!(t.rows.iter().all(|r| r.kind != ImportKind::Delay));
    assert!(t.warnings.iter().any(|w| w.contains("delay-load")), "{:?}", t.warnings);
}

#[test]
fn a_bound_table_without_names_is_said_not_guessed() {
    let mut d = pf::pe_facts();
    let h = pe::headers(&d).unwrap();
    // USER32's OriginalFirstThunk at descriptor 1.
    let off = h.rva_to_offset(0x6014).unwrap();
    d[off..off + 4].fill(0);
    let t = pe::import_table(&d, &pe::headers(&d).unwrap());
    assert!(t.rows.iter().all(|r| r.library != "USER32.dll"));
    assert!(t.warnings.iter().any(|w| w.contains("USER32.dll")));
}

#[test]
fn exports_with_forwarders_gaps_and_ordinals() {
    let d = pf::pe_facts();
    let h = pe::headers(&d).unwrap();
    let t = pe::export_table(&d, &h).unwrap();
    assert_eq!(t.dll_name.as_deref(), Some("facts.dll"));
    assert_eq!((t.ordinal_base, t.declared_functions, t.declared_names), (5, 4, 2));
    assert_eq!(t.entries.len(), 3, "the empty slot is left out: {:?}", t.entries);
    assert_eq!((t.entries[0].ordinal, t.entries[0].name.as_deref(), t.entries[0].forwarder.as_deref()), (5, Some("Alpha"), None));
    assert_eq!((t.entries[1].ordinal, t.entries[1].name.as_deref(), t.entries[1].forwarder.as_deref()), (6, Some("Beta"), Some("NTDLL.RtlBeta")));
    assert_eq!((t.entries[2].ordinal, t.entries[2].name.as_deref()), (8, None));
    assert!(
        pe::export_table(&d, &{
            let mut n = pe::headers(&d).unwrap();
            n.data_dirs[0] = (0, 0);
            n
        })
        .is_none()
    );
}

#[test]
fn hostile_export_counts_stop_at_the_end_of_the_file() {
    for (funcs, names) in [(u32::MAX, u32::MAX), (u32::MAX, 0), (0, u32::MAX), (0x7fff_ffff, 0x7fff_ffff)] {
        let mut d = pf::pe_facts();
        let off = pe::headers(&d).unwrap().rva_to_offset(0x6500).unwrap();
        d[off + 20..off + 24].copy_from_slice(&funcs.to_le_bytes());
        d[off + 24..off + 28].copy_from_slice(&names.to_le_bytes());
        d[off + 16..off + 20].copy_from_slice(&u32::MAX.to_le_bytes());
        let t = pe::export_table(&d, &pe::headers(&d).unwrap()).unwrap();
        assert!(t.entries.len() <= 200_000);
        assert!(t.truncated, "{funcs:#x} {names:#x}");
    }
}

#[test]
fn hostile_directory_offsets_do_not_panic() {
    for rva in [u32::MAX, u32::MAX - 1, u32::MAX - 19, 0x8000_0000, 0x7fff_ffff, 0x6000 + 0x7fc] {
        for size in [u32::MAX, 0xffff_fff0, 8] {
            let mut d = pf::pe_facts();
            for dir in [0, 1, 4, 11, 13] {
                set_dir(&mut d, dir, rva, size);
            }
            let h = pe::headers(&d).unwrap();
            let _ = pe::import_table(&d, &h);
            let _ = pe::export_table(&d, &h);
            let _ = authenticode::certificate_table(&d, &h);
            let _ = parse_binary(&d);
        }
    }
}

#[test]
fn a_descriptor_loop_hits_the_row_cap() {
    // Every descriptor points at one long lookup table: the walk must stop at its cap.
    let mut d = pf::pe_facts();
    let h = pe::headers(&d).unwrap();
    let start = h.rva_to_offset(0x6000).unwrap();
    let thunks = 0x7000u32;
    let mut extra = Vec::new();
    for _ in 0..4000 {
        extra.extend_from_slice(&((1u64 << 63) | 1).to_le_bytes());
    }
    extra.extend_from_slice(&[0u8; 8]);
    let extra_raw = d.len() as u32;
    d.extend_from_slice(&extra);
    // A sixth section holds the table.
    let coff = 0x84;
    d[coff + 2..coff + 4].copy_from_slice(&6u16.to_le_bytes());
    let sh = OPT + 240 + 5 * 40;
    d[sh + 8..sh + 12].copy_from_slice(&(extra.len() as u32).to_le_bytes());
    d[sh + 12..sh + 16].copy_from_slice(&thunks.to_le_bytes());
    d[sh + 16..sh + 20].copy_from_slice(&(extra.len() as u32).to_le_bytes());
    d[sh + 20..sh + 24].copy_from_slice(&extra_raw.to_le_bytes());
    // Fill .facts with descriptors that all use it (0x800 / 20 = 102 of them, 408,000 rows wanted).
    let name = 0x6300u32;
    for i in 0..102 {
        let o = start + i * 20;
        d[o..o + 4].copy_from_slice(&thunks.to_le_bytes());
        d[o + 4..o + 8].fill(0);
        d[o + 12..o + 16].copy_from_slice(&name.to_le_bytes());
        d[o + 16..o + 20].copy_from_slice(&thunks.to_le_bytes());
    }
    let t = pe::import_table(&d, &pe::headers(&d).unwrap());
    assert_eq!(t.rows.len(), 200_000, "102 descriptors of 4,000 rows each ask for 408,000");
    assert!(t.truncated);
}

#[test]
fn every_prefix_of_every_pe_is_safe() {
    let signed = pf::signed_pe();
    for n in (0..signed.len()).step_by(7).chain(signed.len().saturating_sub(64)..signed.len()) {
        let cut = &signed[..n];
        if let Ok(h) = pe::headers(cut) {
            let _ = pe::import_table(cut, &h);
            let _ = pe::export_table(cut, &h);
            let _ = authenticode::certificate_table(cut, &h);
        }
        let _ = parse_binary(cut);
    }
    for sample in craft_anything_testkit::mutations(&pf::pe_facts()) {
        if let Ok(h) = pe::headers(&sample) {
            let _ = pe::import_table(&sample, &h);
            let _ = pe::export_table(&sample, &h);
        }
    }
}

#[test]
fn a_genuine_signature_checks_out() {
    let d = pf::signed_pe();
    let h = pe::headers(&d).unwrap();
    let t = authenticode::certificate_table(&d, &h).unwrap();
    assert!(t.within_file && t.warnings.is_empty(), "{t:?}");
    assert_eq!(t.entries.len(), 1);
    assert_eq!(t.entries[0].certificate_type, 2);
    let s = t.entries[0].signature.as_ref().unwrap();
    assert!(s.parsed);
    assert_eq!(s.file_hash, HashStatus::Matches, "{:?}", s.file_hash_note);
    assert_eq!(s.signature_check, Verified::Valid, "{:?}", s.notes);
    assert_eq!(s.file_digest, s.computed_file_digest);
    assert_eq!(s.file_digest_algorithm.as_deref(), Some("sha256"));
    assert_eq!(s.digest_algorithm.as_deref(), Some("sha256"));
    let signer = s.signer.as_ref().unwrap();
    assert!(signer.subject.contains("Craft Signer"), "{}", signer.subject);
    assert!(!signer.not_before.is_empty() && !signer.serial.is_empty());
    assert_eq!(s.signer_count, 1);
    assert_eq!(s.unsigned_attributes, vec!["RFC 3161 timestamp"]);
    assert!(s.chain.as_ref().is_some_and(|c| c.trusted_root.is_none()), "no trust store is consulted");
}

#[test]
fn a_changed_file_no_longer_matches_its_signature() {
    let mut d = pf::signed_pe();
    let h = pe::headers(&d).unwrap();
    let code = h.rva_to_offset(0x1000).unwrap();
    d[code] ^= 0xff;
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    let s = t.entries[0].signature.as_ref().unwrap();
    assert_eq!(s.file_hash, HashStatus::Differs);
    assert_eq!(s.signature_check, Verified::Valid, "the signature itself still covers what it signed");
}

#[test]
fn the_excluded_fields_do_not_change_the_hash() {
    // The checksum may change after signing without touching the signature.
    let mut d = pf::signed_pe();
    d[OPT + 64] ^= 0xff;
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    assert_eq!(t.entries[0].signature.as_ref().unwrap().file_hash, HashStatus::Matches);
}

#[test]
fn a_forged_block_fails_its_own_signature() {
    let plain = pf::pe_facts();
    let mut block = pf::authenticode_block(&[7u8; 32], "Craft Signer", "Craft Org", false);
    // Flip a byte of the signature value at the end of the block.
    let last = block.len() - 1;
    block[last] ^= 0xff;
    let d = pf::pe_with_certificate(&plain, 2, &block);
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    let s = t.entries[0].signature.as_ref().unwrap();
    assert_eq!(s.file_hash, HashStatus::Differs);
    assert!(!s.signature_check.is_valid());
}

#[test]
fn certificate_tables_that_lie() {
    let plain = pf::pe_facts();
    assert!(authenticode::certificate_table(&plain, &pe::headers(&plain).unwrap()).is_none());

    // Past the end of the file.
    let mut d = plain.clone();
    let past = d.len() as u32 + 0x1000;
    set_dir(&mut d, 4, past, 0x100);
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    assert!(!t.within_file && t.entries.is_empty() && !t.warnings.is_empty());

    // Starting in the file, ending far past it.
    let mut d = plain.clone();
    set_dir(&mut d, 4, 0x400, u32::MAX);
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    assert!(!t.within_file);

    // A signature whose table runs past the file is never hash-checked.
    let good = pf::signed_pe();
    let h = pe::headers(&good).unwrap();
    let (off, size) = h.data_dirs[4];
    let mut d = good.clone();
    set_dir(&mut d, 4, off, size + 64);
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    assert!(!t.within_file);
    if let Some(s) = t.entries.first().and_then(|e| e.signature.as_ref()) {
        assert_eq!(s.file_hash, HashStatus::NotChecked);
    }

    // Lengths too small, too big, and not PKCS#7.
    for length in [0u32, 7, u32::MAX] {
        let mut d = pf::pe_with_certificate(&plain, 2, b"not a signature");
        let off = pe::headers(&d).unwrap().data_dirs[4].0 as usize;
        d[off..off + 4].copy_from_slice(&length.to_le_bytes());
        let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
        assert!(t.entries.is_empty() && !t.warnings.is_empty());
    }
    let d = pf::pe_with_certificate(&plain, 2, b"not a signature");
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    let s = t.entries[0].signature.as_ref().unwrap();
    assert!(!s.parsed && s.signer.is_none() && !s.signature_check.is_valid());
    let d = pf::pe_with_certificate(&plain, 1, b"an old X.509 entry");
    let t = authenticode::certificate_table(&d, &pe::headers(&d).unwrap()).unwrap();
    assert!(t.entries[0].signature.is_none());
    assert_eq!(t.entries[0].type_name, "X.509 certificate");
}

#[test]
fn a_table_overlapping_the_headers_is_not_hashed() {
    let good = pf::signed_pe();
    let (_, size) = pe::headers(&good).unwrap().data_dirs[4];
    let mut d = good.clone();
    set_dir(&mut d, 4, 8, size);
    let h = pe::headers(&d).unwrap();
    assert!(authenticode::file_hash(&d, &h, craft_anything_formats::verify::Digest::Sha256).is_err());
}

#[test]
fn elf_dynamic_symbols_with_versions() {
    let d = pf::elf_versioned_library();
    let b = parse_binary(&d).unwrap();
    let s = elf::dynamic_symbols(&d, &b).unwrap();
    assert!(!s.truncated);
    let names: Vec<_> = s.exports.iter().map(|e| e.name.as_str()).collect();
    assert_eq!(names, vec!["alpha", "beta"], "the hidden symbol isn't offered to other programs");
    assert_eq!((s.exports[0].version.as_deref(), s.exports[0].binding, s.exports[0].kind, s.exports[0].addr), (Some("LIB_1.0"), "global", "function", 0x1000));
    assert_eq!((s.exports[1].version.as_deref(), s.exports[1].binding, s.exports[1].kind), (Some("LIB_2.0"), "weak", "object"));
    assert_eq!(s.imports.len(), 1);
    assert_eq!(
        (s.imports[0].name.as_str(), s.imports[0].version.as_deref(), s.imports[0].library.as_deref()),
        ("puts", Some("GLIBC_2.2.5"), Some("libc.so.6"))
    );
}

#[test]
fn damaged_elf_symbols_do_not_panic() {
    let d = pf::elf_versioned_library();
    for n in 0..d.len() {
        let cut = &d[..n];
        if let Ok(b) = parse_binary(cut) {
            let _ = elf::dynamic_symbols(cut, &b);
        }
        // The model of the whole file against the cut bytes: tables end early.
        if n % 13 == 0 {
            let b = parse_binary(&d).unwrap();
            let _ = elf::dynamic_symbols(cut, &b);
        }
    }
    let b = parse_binary(&d).unwrap();
    for sample in craft_anything_testkit::mutations(&d) {
        let _ = elf::dynamic_symbols(&sample, &b);
    }
    // A version chain that loops or walks off the end.
    let mut looped = d.clone();
    let off = b.sections.iter().find(|s| s.name == ".gnu.version_d").unwrap().file_offset.unwrap() as usize;
    looped[off + 16..off + 20].copy_from_slice(&u32::MAX.to_le_bytes());
    let _ = elf::dynamic_symbols(&looped, &b);
    let off = b.sections.iter().find(|s| s.name == ".gnu.version_r").unwrap().file_offset.unwrap() as usize;
    let mut looped = d.clone();
    looped[off + 2..off + 4].copy_from_slice(&u16::MAX.to_le_bytes());
    looped[off + 8..off + 12].copy_from_slice(&u32::MAX.to_le_bytes());
    let _ = elf::dynamic_symbols(&looped, &b);
}

#[test]
fn gguf_header_reads_in_both_versions() {
    for version in [2, 3] {
        let d = pf::gguf_header(version);
        let size = d.len() as u64 + 0x100000;
        let r = ai_model::parse(&d, size).unwrap();
        assert_eq!(r.version, Some(version));
        assert_eq!(r.architecture.as_deref(), Some("llama"));
        assert_eq!(r.name.as_deref(), Some("Tiny"));
        assert_eq!(r.file_type.as_deref(), Some("mostly Q4_K medium"));
        assert_eq!(r.quantization.as_deref(), Some("Q4_K"));
        assert_eq!((r.declared_tensors, r.tensors_read), (3, 3));
        assert_eq!(r.parameters, 1000 * 256 + 256 * 256 + 256);
        assert_eq!(r.parameters_by_type.get("F32"), Some(&256));
        assert_eq!(r.tensors[0].shape, vec![1000, 256]);
        assert_eq!(r.tensors[2].data_bytes, Some(1024));
        assert!(r.tensors[0].data_bytes.is_none(), "a block format has no per-element size");
        assert!(r.complete && r.tensors_past_end == 0, "{r:?}");
        assert_eq!(r.header_bytes, d.len() as u64);
        let tokens = r.metadata.iter().find(|m| m.key == "tokenizer.ggml.tokens").unwrap();
        assert_eq!((tokens.value_type.as_str(), tokens.count, tokens.shortened), ("array<string>", Some(10), true));
        assert_eq!(tokens.value.as_array().unwrap().len(), 8);
    }
}

#[test]
fn gguf_refuses_what_it_does_not_read() {
    let mut d = pf::gguf_header(3);
    d[4] = 1;
    assert!(matches!(ai_model::parse(&d, d.len() as u64), Err(craft_anything_formats::FormatError::Unsupported(_))));
    d[4] = 99;
    assert!(ai_model::parse(&d, d.len() as u64).is_err());
    assert!(ai_model::parse(b"nonsense data here", 18).is_err());
}

#[test]
fn big_endian_gguf_reads() {
    let mut d = b"GGUF".to_vec();
    d.extend_from_slice(&3u32.to_be_bytes());
    d.extend_from_slice(&1u64.to_be_bytes());
    d.extend_from_slice(&1u64.to_be_bytes());
    d.extend_from_slice(&20u64.to_be_bytes());
    d.extend_from_slice(b"general.architecture");
    d.extend_from_slice(&8u32.to_be_bytes());
    d.extend_from_slice(&3u64.to_be_bytes());
    d.extend_from_slice(b"gpt");
    d.extend_from_slice(&1u64.to_be_bytes());
    d.extend_from_slice(b"t");
    d.extend_from_slice(&1u32.to_be_bytes());
    d.extend_from_slice(&5u64.to_be_bytes());
    d.extend_from_slice(&0u32.to_be_bytes());
    d.extend_from_slice(&0u64.to_be_bytes());
    let r = ai_model::parse(&d, 1000).unwrap();
    assert_eq!((r.architecture.as_deref(), r.parameters, r.complete), (Some("gpt"), 5, true));
}

#[test]
fn every_prefix_of_a_gguf_is_safe_and_honest() {
    let d = pf::gguf_header(3);
    for n in 0..d.len() {
        for size in [n as u64, d.len() as u64, u64::MAX] {
            match ai_model::parse(&d[..n], size) {
                Ok(r) => {
                    assert!(!r.complete, "a cut at {n} can't be complete");
                    assert!(!r.warnings.is_empty());
                }
                Err(_) => assert!(n < 25),
            }
        }
    }
    // Told the file is longer: says the limit stopped it. Told this is all: says it's damaged.
    let cut = &d[..d.len() / 2];
    assert!(ai_model::parse(cut, d.len() as u64).unwrap().warnings[0].contains("first"));
    assert!(ai_model::parse(cut, cut.len() as u64).unwrap().warnings[0].contains("cut short"));
    for sample in craft_anything_testkit::mutations(&d) {
        let _ = ai_model::parse(&sample, sample.len() as u64);
    }
}

#[test]
fn gguf_huge_counts_end_where_the_bytes_end() {
    for count in [u64::MAX, u64::MAX / 2, 1 << 40] {
        // Huge declared tensor and metadata counts.
        let mut d = pf::gguf_header(3);
        d[8..16].copy_from_slice(&count.to_le_bytes());
        let r = ai_model::parse(&d, d.len() as u64).unwrap();
        assert_eq!(r.declared_tensors, count);
        assert!(!r.complete && r.tensors.len() == 3);
        let mut d = pf::gguf_header(3);
        d[16..24].copy_from_slice(&count.to_le_bytes());
        let r = ai_model::parse(&d, d.len() as u64).unwrap();
        assert!(!r.complete);

        // A key length, an array of fixed-size values, an array of strings and a nested array.
        let mut kv = b"GGUF".to_vec();
        kv.extend_from_slice(&3u32.to_le_bytes());
        kv.extend_from_slice(&0u64.to_le_bytes());
        kv.extend_from_slice(&1u64.to_le_bytes());
        let mut long = kv.clone();
        long.extend_from_slice(&count.to_le_bytes());
        assert!(!ai_model::parse(&long, long.len() as u64).unwrap().complete);
        for elem in [4u32, 8, 9, 200] {
            let mut a = kv.clone();
            a.extend_from_slice(&1u64.to_le_bytes());
            a.push(b'k');
            a.extend_from_slice(&9u32.to_le_bytes());
            a.extend_from_slice(&elem.to_le_bytes());
            a.extend_from_slice(&count.to_le_bytes());
            assert!(!ai_model::parse(&a, a.len() as u64).unwrap().complete, "{elem}");
        }
    }
}

#[test]
fn gguf_nesting_is_bounded() {
    let mut d = b"GGUF".to_vec();
    d.extend_from_slice(&3u32.to_le_bytes());
    d.extend_from_slice(&0u64.to_le_bytes());
    d.extend_from_slice(&1u64.to_le_bytes());
    d.extend_from_slice(&1u64.to_le_bytes());
    d.push(b'k');
    d.extend_from_slice(&9u32.to_le_bytes());
    for _ in 0..100_000 {
        d.extend_from_slice(&9u32.to_le_bytes());
        d.extend_from_slice(&1u64.to_le_bytes());
    }
    assert!(!ai_model::parse(&d, d.len() as u64).unwrap().complete);
}

#[test]
fn gguf_shapes_that_overflow_and_tensors_past_the_end() {
    let mut d = b"GGUF".to_vec();
    d.extend_from_slice(&3u32.to_le_bytes());
    d.extend_from_slice(&2u64.to_le_bytes());
    d.extend_from_slice(&0u64.to_le_bytes());
    for (name, offset) in [("huge", 0u64), ("far", u64::MAX)] {
        d.extend_from_slice(&(name.len() as u64).to_le_bytes());
        d.extend_from_slice(name.as_bytes());
        d.extend_from_slice(&2u32.to_le_bytes());
        d.extend_from_slice(&u64::MAX.to_le_bytes());
        d.extend_from_slice(&u64::MAX.to_le_bytes());
        d.extend_from_slice(&0u32.to_le_bytes());
        d.extend_from_slice(&offset.to_le_bytes());
    }
    let r = ai_model::parse(&d, d.len() as u64).unwrap();
    assert_eq!(r.parameters, u64::MAX);
    assert_eq!(r.tensors_past_end, 2);
    assert!(r.warnings.iter().any(|w| w.contains("past what a number")));
    assert!(r.warnings.iter().any(|w| w.contains("more data than the file holds")));
}

#[test]
fn safetensors_reads() {
    let d = pf::safetensors_file(pf::SAFETENSORS_HEADER, 32);
    let r = ai_model::parse(&d, d.len() as u64).unwrap();
    assert_eq!(r.format, ai_model::ModelFormat::Safetensors);
    assert_eq!(r.architecture.as_deref(), Some("tiny-net"));
    assert_eq!((r.parameters, r.tensors_read, r.declared_tensors), (14, 2, 2));
    assert_eq!(r.tensors[0].name, "a.weight");
    assert_eq!(r.tensors[0].shape, vec![2, 3]);
    assert_eq!(r.tensors[1].dtype, "U8");
    assert_eq!(r.tensors[1].data_offset, 24);
    assert!(r.quantization.is_none());
    assert!(r.complete && r.warnings.is_empty(), "{:?}", r.warnings);
    assert_eq!(r.metadata.len(), 2);
    assert_eq!(r.header_bytes, 8 + pf::SAFETENSORS_HEADER.len() as u64);
}

#[test]
fn safetensors_bad_headers() {
    let size = |d: &[u8]| d.len() as u64;
    // Not JSON, and JSON that isn't an object.
    let d = pf::safetensors_file("{not json", 0);
    assert!(matches!(ai_model::parse(&d, size(&d)), Err(craft_anything_formats::FormatError::Malformed(_))));
    let d = pf::safetensors_file("{\"a\":", 0);
    assert!(ai_model::parse(&d, size(&d)).is_err());
    // A length past the file, and one that overflows.
    for n in [u64::MAX, u64::MAX - 7, 1 << 40] {
        let mut d = n.to_le_bytes().to_vec();
        d.extend_from_slice(b"{}");
        assert!(ai_model::parse(&d, size(&d)).is_err());
    }
    // A header longer than what was read.
    let d = pf::safetensors_file(pf::SAFETENSORS_HEADER, 32);
    assert!(matches!(ai_model::parse(&d[..20], size(&d)), Err(craft_anything_formats::FormatError::TooLarge(_))));
    // Entries that aren't tensors, or that don't add up.
    let d = pf::safetensors_file(
        r#"{"x":{"dtype":"F32"},"y":7,"z":{"dtype":"F32","shape":[4],"data_offsets":[8,4]},"w":{"dtype":"F32","shape":[4],"data_offsets":[0,4]},"v":{"dtype":"U8","shape":[1],"data_offsets":[0,9999]}}"#,
        8,
    );
    let r = ai_model::parse(&d, size(&d)).unwrap();
    assert!(!r.complete);
    assert_eq!(r.tensors_past_end, 1);
    assert!(r.warnings.iter().any(|w| w.contains("ends before it starts")));
    assert!(r.warnings.iter().any(|w| w.contains("don't fit")));
    // Shapes that overflow.
    let d = pf::safetensors_file(r#"{"o":{"dtype":"F64","shape":[18446744073709551615,18446744073709551615],"data_offsets":[0,8]}}"#, 8);
    assert_eq!(ai_model::parse(&d, size(&d)).unwrap().parameters, u64::MAX);
    // Deep JSON is refused by the JSON reader's own limit, not by the stack.
    let deep = format!("{{\"a\":{}{}}}", "[".repeat(100_000), "]".repeat(100_000));
    let d = pf::safetensors_file(&deep, 0);
    assert!(ai_model::parse(&d, size(&d)).is_err());
}

#[test]
fn every_prefix_of_a_safetensors_is_safe() {
    let d = pf::safetensors_file(pf::SAFETENSORS_HEADER, 32);
    for n in 0..d.len() {
        let _ = ai_model::parse(&d[..n], d.len() as u64);
        let _ = ai_model::parse(&d[..n], n as u64);
    }
    for sample in craft_anything_testkit::mutations(&d) {
        let _ = ai_model::parse(&sample, sample.len() as u64);
    }
}

#[test]
fn plain_counts() {
    assert_eq!(ai_model::plain_count(7_200_000_000), "7.2 billion");
    assert_eq!(ai_model::plain_count(1_500_000), "1.5 million");
    assert_eq!(ai_model::plain_count(2_500), "2.5 thousand");
    assert_eq!(ai_model::plain_count(12), "12");
    assert_eq!(ai_model::plain_count(3_000_000_000_000), "3.0 trillion");
}

#[test]
fn providers_follow_their_own_export_rule() {
    use craft_anything_formats::axml;
    use craft_anything_testkit::android::{AxAttr, AxNode, AxVal, a, axml as build};
    let doc = |target: i32| {
        let name = |v| a("name", 0x0101_0003, AxVal::Str(v));
        build(&[
            AxNode::Start("manifest", vec![AxAttr { name: "package", res_id: None, val: AxVal::Str("p") }]),
            AxNode::Start("uses-sdk", vec![a("targetSdkVersion", 0x0101_0270, AxVal::Int(target))]),
            AxNode::End("uses-sdk"),
            AxNode::Start("application", vec![]),
            AxNode::Start("provider", vec![name(".P"), a("authorities", 0x0101_0018, AxVal::Str("p.a"))]),
            AxNode::End("provider"),
            AxNode::End("application"),
            AxNode::End("manifest"),
        ])
    };
    let exported = |t| axml::manifest(&axml::parse(&doc(t)).unwrap()).components[0].exported;
    assert!(exported(16), "exported by default up to API 16");
    assert!(!exported(17));
}
