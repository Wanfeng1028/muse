//! Synthetic Flutter samples: an AArch64 `libapp.so` exporting the four Dart snapshot symbols
//! (with section headers, or section-stripped with only `PT_DYNAMIC` + `DT_HASH`/`DT_GNU_HASH`),
//! a `libflutter.so` carrying a Dart version string, a toolchain string and a GNU build id, and an
//! APK holding them.

pub const SNAPSHOT_HASH: &str = "8ee4ef7a67df9845fba331734198a953";
pub const FEATURES: &str = "product no-code_coverage arm64 android compressed-pointers null-safety";
pub const DART_VERSION: &str = "3.4.0 (stable) (Mon Jun 3 2024) on \"android_arm64\"";
pub const TOOLCHAIN: &str = "Android (11349228, +pgo, based on r487747e) clang version 17.0.2";
pub const BUILD_ID: [u8; 20] = [0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67, 0x89, 0x10, 0x32, 0x54, 0x76, 0x98, 0xba, 0xdc, 0xfe, 0x11, 0x22, 0x33, 0x44];
pub const BUILD_ID_HEX: &str = "abcdef01234567891032547698badcfe11223344";

/// How `libapp_so` exposes its dynamic symbols.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SymbolTable {
    /// Section headers with `.dynsym` (and `DT_HASH` too).
    Sections,
    /// No section headers; `PT_DYNAMIC` with `DT_HASH`.
    DynamicHash,
    /// No section headers; `PT_DYNAMIC` with `DT_GNU_HASH` only.
    DynamicGnuHash,
}

/// A Dart snapshot header followed by `body`.
pub fn snapshot(kind: u64, body: &[u8]) -> Vec<u8> {
    let mut v = vec![0xf5, 0xf5, 0xdc, 0xdc];
    let mut rest = Vec::new();
    rest.extend_from_slice(&kind.to_le_bytes());
    rest.extend_from_slice(SNAPSHOT_HASH.as_bytes());
    rest.extend_from_slice(FEATURES.as_bytes());
    rest.push(0);
    rest.extend_from_slice(body);
    v.extend_from_slice(&((rest.len() + 8) as u64).to_le_bytes());
    v.extend_from_slice(&rest);
    v
}

fn align(v: &mut Vec<u8>, a: usize) {
    while !v.len().is_multiple_of(a) {
        v.push(0);
    }
}

fn put_u16(v: &mut [u8], off: usize, x: u16) {
    v[off..off + 2].copy_from_slice(&x.to_le_bytes());
}
fn put_u32(v: &mut [u8], off: usize, x: u32) {
    v[off..off + 4].copy_from_slice(&x.to_le_bytes());
}
fn put_u64(v: &mut [u8], off: usize, x: u64) {
    v[off..off + 8].copy_from_slice(&x.to_le_bytes());
}

/// A little-endian ELF64 AArch64 shared object. `symbols` are exported objects with their bytes;
/// `rodata` is extra content. Virtual addresses equal file offsets (one PT_LOAD).
pub fn elf_so(symbols: &[(&str, Vec<u8>)], rodata: &[u8], table: SymbolTable) -> Vec<u8> {
    let mut f = vec![0u8; 0x100];
    // .dynstr
    let dynstr_off = f.len();
    let mut name_offs = Vec::new();
    f.push(0);
    for (n, _) in symbols {
        name_offs.push(f.len() - dynstr_off);
        f.extend_from_slice(n.as_bytes());
        f.push(0);
    }
    let dynstr_size = f.len() - dynstr_off;
    align(&mut f, 8);
    let dynsym_off = f.len();
    f.extend_from_slice(&[0u8; 24]);
    let mut sym_fixups = Vec::new();
    for no in &name_offs {
        let at = f.len();
        let mut s = [0u8; 24];
        s[0..4].copy_from_slice(&(*no as u32).to_le_bytes());
        s[4] = 0x11; // GLOBAL OBJECT
        s[6..8].copy_from_slice(&1u16.to_le_bytes());
        f.extend_from_slice(&s);
        sym_fixups.push(at);
    }
    let nsyms = symbols.len() + 1;
    // DT_HASH
    align(&mut f, 8);
    let hash_off = f.len();
    for v in [1u32, nsyms as u32, 0] {
        f.extend_from_slice(&v.to_le_bytes());
    }
    f.extend(std::iter::repeat_n(0u8, 4 * nsyms));
    // DT_GNU_HASH
    align(&mut f, 8);
    let gnu_off = f.len();
    for v in [1u32, 1, 1, 6] {
        f.extend_from_slice(&v.to_le_bytes());
    }
    f.extend_from_slice(&u64::MAX.to_le_bytes());
    f.extend_from_slice(&1u32.to_le_bytes());
    for i in 0..symbols.len() {
        let last = i + 1 == symbols.len();
        let v: u32 = 0x1234_5670 | u32::from(last);
        f.extend_from_slice(&v.to_le_bytes());
    }
    // .dynamic
    align(&mut f, 8);
    let dyn_off = f.len();
    let mut dynv: Vec<(u64, u64)> = vec![(5, dynstr_off as u64), (6, dynsym_off as u64), (10, dynstr_size as u64), (11, 24)];
    match table {
        SymbolTable::Sections | SymbolTable::DynamicHash => dynv.push((4, hash_off as u64)),
        SymbolTable::DynamicGnuHash => dynv.push((0x6fff_fef5, gnu_off as u64)),
    }
    dynv.push((0, 0));
    for (t, v) in dynv {
        f.extend_from_slice(&t.to_le_bytes());
        f.extend_from_slice(&v.to_le_bytes());
    }
    let dyn_size = f.len() - dyn_off;
    // build-id note
    align(&mut f, 4);
    let note_off = f.len();
    f.extend_from_slice(&4u32.to_le_bytes());
    f.extend_from_slice(&20u32.to_le_bytes());
    f.extend_from_slice(&3u32.to_le_bytes());
    f.extend_from_slice(b"GNU\0");
    f.extend_from_slice(&BUILD_ID);
    let note_size = f.len() - note_off;
    f.extend_from_slice(rodata);
    // symbol payloads
    for (i, (_, body)) in symbols.iter().enumerate() {
        align(&mut f, 16);
        let at = f.len();
        f.extend_from_slice(body);
        let s = sym_fixups[i];
        put_u64(&mut f, s + 8, at as u64);
        put_u64(&mut f, s + 16, body.len() as u64);
    }
    // section headers
    let mut shoff = 0usize;
    let mut shnum = 0u16;
    if table == SymbolTable::Sections {
        let shstr_off = f.len();
        f.extend_from_slice(b"\0.dynsym\0.dynstr\0.note.gnu.build-id\0.shstrtab\0");
        let shstr_size = f.len() - shstr_off;
        align(&mut f, 8);
        shoff = f.len();
        // (name, type, offset, size, link, info, entsize)
        let secs: [(u32, u32, usize, usize, u32, u32, u64); 5] = [
            (0, 0, 0, 0, 0, 0, 0),
            (1, 11, dynsym_off, 24 * nsyms, 2, 1, 24),
            (9, 3, dynstr_off, dynstr_size, 0, 0, 0),
            (17, 7, note_off, note_size, 0, 0, 0),
            (36, 3, shstr_off, shstr_size, 0, 0, 0),
        ];
        for (name, ty, off, size, link, info, entsize) in secs {
            let mut s = [0u8; 64];
            s[0..4].copy_from_slice(&name.to_le_bytes());
            s[4..8].copy_from_slice(&ty.to_le_bytes());
            s[16..24].copy_from_slice(&(off as u64).to_le_bytes());
            s[24..32].copy_from_slice(&(off as u64).to_le_bytes());
            s[32..40].copy_from_slice(&(size as u64).to_le_bytes());
            s[40..44].copy_from_slice(&link.to_le_bytes());
            s[44..48].copy_from_slice(&info.to_le_bytes());
            s[56..64].copy_from_slice(&entsize.to_le_bytes());
            f.extend_from_slice(&s);
        }
        shnum = 5;
    }
    let total = f.len() as u64;
    // ELF header
    f[0..4].copy_from_slice(b"\x7fELF");
    f[4] = 2;
    f[5] = 1;
    f[6] = 1;
    put_u16(&mut f, 16, 3);
    put_u16(&mut f, 18, 183);
    put_u32(&mut f, 20, 1);
    put_u64(&mut f, 32, 64);
    put_u64(&mut f, 40, shoff as u64);
    put_u16(&mut f, 52, 64);
    put_u16(&mut f, 54, 56);
    put_u16(&mut f, 56, 3);
    put_u16(&mut f, 58, 64);
    put_u16(&mut f, 60, shnum);
    put_u16(&mut f, 62, if shnum > 0 { 4 } else { 0 });
    // program headers: LOAD, DYNAMIC, NOTE
    for (i, (ty, off, size)) in [(1u32, 0u64, total), (2, dyn_off as u64, dyn_size as u64), (4, note_off as u64, note_size as u64)].into_iter().enumerate() {
        let p = 64 + i * 56;
        put_u32(&mut f, p, ty);
        put_u32(&mut f, p + 4, 4);
        put_u64(&mut f, p + 8, off);
        put_u64(&mut f, p + 16, off);
        put_u64(&mut f, p + 24, off);
        put_u64(&mut f, p + 32, size);
        put_u64(&mut f, p + 40, size);
        put_u64(&mut f, p + 48, 8);
    }
    f
}

/// The isolate snapshot body: a few app strings as a compiled app would carry them.
pub fn isolate_strings() -> Vec<u8> {
    let mut b = vec![0u8; 16];
    for s in ["package:notes_app/main.dart", "package:flutter/material.dart", "dart:core", "dart:async", "NotesHomePage", "_saveNote", "build"] {
        b.extend_from_slice(s.as_bytes());
        b.extend_from_slice(&[0, 0x13]);
    }
    b
}

/// A Flutter `libapp.so`.
pub fn libapp_so(table: SymbolTable) -> Vec<u8> {
    let symbols = vec![
        ("_kDartVmSnapshotData", snapshot(3, &[0u8; 32])),
        ("_kDartVmSnapshotInstructions", [0x1f, 0x20, 0x03, 0xd5].repeat(8)),
        ("_kDartIsolateSnapshotData", snapshot(3, &isolate_strings())),
        ("_kDartIsolateSnapshotInstructions", [0xc0, 0x03, 0x5f, 0xd6].repeat(8)),
    ];
    elf_so(&symbols, b"", table)
}

/// A `libflutter.so` stand-in with version and toolchain strings.
pub fn libflutter_so() -> Vec<u8> {
    let mut ro = Vec::new();
    ro.extend_from_slice(b"\0Dart VM version: ");
    ro.extend_from_slice(DART_VERSION.as_bytes());
    ro.push(0);
    ro.extend_from_slice(TOOLCHAIN.as_bytes());
    ro.push(0);
    ro.extend_from_slice(SNAPSHOT_HASH.as_bytes());
    ro.push(0);
    elf_so(&[("FlutterEngineRun", vec![0xc0, 0x03, 0x5f, 0xd6])], &ro, SymbolTable::Sections)
}

/// An APK with Flutter libraries for arm64-v8a and armeabi-v7a.
pub fn flutter_apk() -> Vec<u8> {
    let app = libapp_so(SymbolTable::Sections);
    let app_stripped = libapp_so(SymbolTable::DynamicGnuHash);
    let fl = libflutter_so();
    crate::electron::zip_stored(&[
        ("AndroidManifest.xml", b"\x03\x00\x08\x00"),
        ("classes.dex", b"dex\n035\0"),
        ("lib/arm64-v8a/libapp.so", &app),
        ("lib/arm64-v8a/libflutter.so", &fl),
        ("lib/armeabi-v7a/libapp.so", &app_stripped),
        ("lib/armeabi-v7a/libflutter.so", &fl),
    ])
}

/// An APK with no Flutter libraries.
pub fn plain_apk() -> Vec<u8> {
    crate::electron::zip_stored(&[("AndroidManifest.xml", b"\x03\x00\x08\x00"), ("lib/arm64-v8a/libnative.so", b"\x7fELF")])
}
