//! A synthetic .NET assembly writer: a PE32 DLL with a CLI header, IL method bodies (tiny and
//! fat, with locals and a finally clause), an embedded resource and ECMA-335 metadata
//! (`#~`, `#Strings`, `#US`, `#GUID`, `#Blob`).
//!
//! The sample (`Sample.dll`, assembly `Sample` 1.2.3.4, TargetFramework `.NETCoreApp,Version=v8.0`):
//!
//! ```text
//! namespace Sample {
//!   public class Calculator {
//!     private int _total;
//!     public int Add(int a, int b) => a + b;            // v2: a - b
//!     public void Accumulate(int x) { _total += x; Console.WriteLine("hi"); try { Add(1, 2); } finally {} }
//!     public static T Identity<T>(T value) => value;
//!     public Calculator() {}
//!     public int Multiply(int a, int b) => a * b;       // v2 only
//!     public class Options { public bool Verbose; }
//!   }
//!   public static class NativeMethods {
//!     [DllImport("craft", SetLastError = true)] public static extern int helper(int n);
//!     [DllImport("craft", EntryPoint = "missing_fn", CharSet = Ansi)] public static extern void MissingFn();   // v1 only
//!     [MethodImpl(InternalCall)] public static extern long GetTicks();
//!   }
//! }
//! ```

use std::collections::BTreeMap;

pub const ASSEMBLY_NAME: &str = "Sample";
pub const TFM: &str = ".NETCoreApp,Version=v8.0";
pub const NATIVE_MODULE: &str = "craft";

#[derive(Default)]
struct Heaps {
    strings: Vec<u8>,
    blob: Vec<u8>,
    us: Vec<u8>,
    guid: Vec<u8>,
}

fn compressed(n: usize) -> Vec<u8> {
    if n < 0x80 {
        vec![n as u8]
    } else if n < 0x4000 {
        vec![0x80 | (n >> 8) as u8, n as u8]
    } else {
        vec![0xc0 | (n >> 24) as u8, (n >> 16) as u8, (n >> 8) as u8, n as u8]
    }
}

fn ser_string(s: &str) -> Vec<u8> {
    let mut v = compressed(s.len());
    v.extend_from_slice(s.as_bytes());
    v
}

impl Heaps {
    fn new() -> Self {
        Heaps { strings: vec![0], blob: vec![0], us: vec![0], guid: Vec::new() }
    }

    fn s(&mut self, x: &str) -> u32 {
        if x.is_empty() {
            return 0;
        }
        let at = self.strings.len() as u32;
        self.strings.extend_from_slice(x.as_bytes());
        self.strings.push(0);
        at
    }

    fn b(&mut self, data: &[u8]) -> u32 {
        if data.is_empty() {
            return 0;
        }
        let at = self.blob.len() as u32;
        self.blob.extend(compressed(data.len()));
        self.blob.extend_from_slice(data);
        at
    }

    fn u(&mut self, s: &str) -> u32 {
        let at = self.us.len() as u32;
        let units: Vec<u16> = s.encode_utf16().collect();
        self.us.extend(compressed(units.len() * 2 + 1));
        for u in units {
            self.us.extend_from_slice(&u.to_le_bytes());
        }
        self.us.push(0);
        at
    }
}

/// Column widths for the tables the sample uses (small tables: 2-byte indexes). `3` marks a
/// heap index, written with 2 or 4 bytes depending on the heap-size flags.
fn widths(table: u8) -> &'static [usize] {
    match table {
        0x00 => &[2, 3, 3, 3, 3],
        0x01 => &[2, 3, 3],
        0x02 => &[4, 3, 3, 2, 2, 2],
        0x04 => &[2, 3, 3],
        0x05 => &[2],
        0x06 => &[4, 2, 2, 3, 3, 2],
        0x08 => &[2, 2, 3],
        0x0a => &[2, 3, 3],
        0x0c => &[2, 2, 3],
        0x11 => &[3],
        0x1a => &[3],
        0x1c => &[2, 2, 3, 2],
        0x20 => &[4, 2, 2, 2, 2, 4, 3, 3, 3],
        0x23 => &[2, 2, 2, 2, 4, 3, 3, 3, 3],
        0x28 => &[4, 4, 3, 2],
        0x29 => &[2, 2],
        0x2a => &[2, 2, 2, 3],
        _ => panic!("table {table:#x} not supported by the writer"),
    }
}

fn pad4(v: &mut Vec<u8>) {
    while !v.len().is_multiple_of(4) {
        v.push(0);
    }
}

fn tiny(code: &[u8]) -> Vec<u8> {
    let mut v = vec![((code.len() as u8) << 2) | 2];
    v.extend_from_slice(code);
    v
}

/// Build the sample assembly. `version` 1 or 2 (2 changes `Add`, adds `Multiply`, drops `MissingFn`).
pub fn managed_assembly(version: u8) -> Vec<u8> {
    build(version, false, false)
}

/// The sample with an uncompressed `#-` tables stream whose method lists go through a MethodPtr
/// table (identity order).
pub fn managed_assembly_with_ptr_tables(version: u8) -> Vec<u8> {
    build(version, false, true)
}

/// The same sample with 4-byte heap indexes and the extra-data flag (HeapSizes `0x47`).
pub fn managed_assembly_wide_heaps(version: u8) -> Vec<u8> {
    build(version, true, false)
}

fn build(version: u8, wide: bool, ptr: bool) -> Vec<u8> {
    let v2 = version >= 2;
    let mut h = Heaps::new();
    let mut tables: BTreeMap<u8, Vec<Vec<u32>>> = BTreeMap::new();
    let mut add = |t: u8, row: Vec<u32>| tables.entry(t).or_default().push(row);

    // Method bodies, laid out after the 72-byte CLI header at .text+0x48.
    const TEXT_RVA: u32 = 0x2000;
    let mut bodies: Vec<u8> = Vec::new();
    let body_base = TEXT_RVA + 0x48;
    let put_body = |b: Vec<u8>, bodies: &mut Vec<u8>| -> u32 {
        pad4(bodies);
        let rva = body_base + bodies.len() as u32;
        bodies.extend(b);
        rva
    };
    let add_rva = put_body(tiny(&[0x03, 0x04, if v2 { 0x59 } else { 0x58 }, 0x2a]), &mut bodies);
    // Accumulate: fat header, one local, a finally clause.
    let mut acc_code = vec![0x02, 0x02, 0x7b, 1, 0, 0, 4, 0x03, 0x58, 0x7d, 1, 0, 0, 4, 0x72, 1, 0, 0, 0x70, 0x28, 1, 0, 0, 0x0a];
    acc_code.extend([0x02, 0x17, 0x18, 0x28, 1, 0, 0, 6, 0x0a, 0xde, 0x01, 0xdc, 0x2a]);
    assert_eq!(acc_code.len(), 37);
    let mut acc = Vec::new();
    acc.extend_from_slice(&0x301bu16.to_le_bytes());
    acc.extend_from_slice(&3u16.to_le_bytes());
    acc.extend_from_slice(&(acc_code.len() as u32).to_le_bytes());
    acc.extend_from_slice(&0x1100_0001u32.to_le_bytes());
    acc.extend_from_slice(&acc_code);
    pad4(&mut acc);
    acc.extend([0x01, 16, 0, 0]);
    acc.extend_from_slice(&2u16.to_le_bytes());
    acc.extend_from_slice(&24u16.to_le_bytes());
    acc.push(11);
    acc.extend_from_slice(&35u16.to_le_bytes());
    acc.push(1);
    acc.extend_from_slice(&0u32.to_le_bytes());
    let acc_rva = put_body(acc, &mut bodies);
    let identity_rva = put_body(tiny(&[0x02, 0x2a]), &mut bodies);
    let ctor_rva = put_body(tiny(&[0x02, 0x28, 2, 0, 0, 0x0a, 0x2a]), &mut bodies);
    let mul_rva = put_body(tiny(&[0x03, 0x04, 0x5a, 0x2a]), &mut bodies);
    pad4(&mut bodies);
    let res_rva = body_base + bodies.len() as u32;
    let mut resources = 5u32.to_le_bytes().to_vec();
    resources.extend_from_slice(b"hello");
    pad4(&mut resources);

    // Module and references.
    let n = h.s("Sample.dll");
    h.guid.extend_from_slice(&[0x11; 16]);
    add(0x00, vec![0, n, 1, 0, 0]);
    let object = h.s("Object");
    let system = h.s("System");
    add(0x01, vec![(1 << 2) | 2, object, system]);
    let console = h.s("Console");
    add(0x01, vec![(2 << 2) | 2, console, system]);
    let tfa = h.s("TargetFrameworkAttribute");
    let versioning = h.s("System.Runtime.Versioning");
    add(0x01, vec![(1 << 2) | 2, tfa, versioning]);

    // Methods (rows in order) and their params.
    struct M {
        name: &'static str,
        flags: u32,
        impl_flags: u32,
        rva: u32,
        sig: Vec<u8>,
        params: Vec<&'static str>,
    }
    let mut calc_methods = vec![
        M { name: "Add", flags: 0x86, impl_flags: 0, rva: add_rva, sig: vec![0x20, 2, 0x08, 0x08, 0x08], params: vec!["a", "b"] },
        M { name: "Accumulate", flags: 0x86, impl_flags: 0, rva: acc_rva, sig: vec![0x20, 1, 0x01, 0x08], params: vec!["x"] },
        M { name: "Identity", flags: 0x96, impl_flags: 0, rva: identity_rva, sig: vec![0x10, 1, 1, 0x1e, 0, 0x1e, 0], params: vec!["value"] },
        M { name: ".ctor", flags: 0x1886, impl_flags: 0, rva: ctor_rva, sig: vec![0x20, 0, 0x01], params: vec![] },
    ];
    if v2 {
        calc_methods.push(M { name: "Multiply", flags: 0x86, impl_flags: 0, rva: mul_rva, sig: vec![0x20, 2, 0x08, 0x08, 0x08], params: vec!["a", "b"] });
    }
    let mut native_methods = vec![M { name: "helper", flags: 0x2096, impl_flags: 0x80, rva: 0, sig: vec![0, 1, 0x08, 0x08], params: vec!["n"] }];
    if !v2 {
        native_methods.push(M { name: "MissingFn", flags: 0x2096, impl_flags: 0x80, rva: 0, sig: vec![0, 0, 0x01], params: vec![] });
    }
    native_methods.push(M { name: "GetTicks", flags: 0x96, impl_flags: 0x1000, rva: 0, sig: vec![0, 0, 0x0a], params: vec![] });

    let calc_first = 1u32;
    let native_first = calc_first + calc_methods.len() as u32;
    let total_methods = native_first + native_methods.len() as u32 - 1;
    let mut param_row = 1u32;
    let mut method_rows = Vec::new();
    for m in calc_methods.iter().chain(native_methods.iter()) {
        let name = h.s(m.name);
        let sig = h.b(&m.sig);
        method_rows.push(vec![m.rva, m.impl_flags, m.flags, name, sig, param_row]);
        for (i, p) in m.params.iter().enumerate() {
            let pn = h.s(p);
            add(0x08, vec![0, i as u32 + 1, pn]);
            param_row += 1;
        }
    }
    for (i, r) in method_rows.into_iter().enumerate() {
        add(0x06, r);
        if ptr {
            add(0x05, vec![i as u32 + 1]);
        }
    }

    // Types.
    let module_name = h.s("<Module>");
    add(0x02, vec![0, module_name, 0, 0, 1, 1]);
    let calc = h.s("Calculator");
    let sample = h.s("Sample");
    add(0x02, vec![0x0010_0001, calc, sample, (1 << 2) | 1, 1, calc_first]);
    let nm = h.s("NativeMethods");
    add(0x02, vec![0x181, nm, sample, (1 << 2) | 1, 2, native_first]);
    let opts = h.s("Options");
    add(0x02, vec![0x2, opts, 0, (1 << 2) | 1, 2, total_methods + 1]);

    // Fields.
    let total = h.s("_total");
    let fsig = h.b(&[0x06, 0x08]);
    add(0x04, vec![0x1, total, fsig]);
    let verbose = h.s("Verbose");
    let bsig = h.b(&[0x06, 0x02]);
    add(0x04, vec![0x6, verbose, bsig]);

    // Member references.
    let wl = h.s("WriteLine");
    let wls = h.b(&[0, 1, 0x01, 0x0e]);
    add(0x0a, vec![(2 << 3) | 1, wl, wls]);
    let ctor = h.s(".ctor");
    let ctor_sig = h.b(&[0x20, 0, 0x01]);
    add(0x0a, vec![(1 << 3) | 1, ctor, ctor_sig]);
    let tfa_sig = h.b(&[0x20, 1, 0x01, 0x0e]);
    add(0x0a, vec![(3 << 3) | 1, ctor, tfa_sig]);

    // [assembly: TargetFramework(".NETCoreApp,Version=v8.0", FrameworkDisplayName = ".NET 8.0")]
    let mut ca = vec![1, 0];
    ca.extend(ser_string(TFM));
    ca.extend([1, 0, 0x54, 0x0e]);
    ca.extend(ser_string("FrameworkDisplayName"));
    ca.extend(ser_string(".NET 8.0"));
    let cab = h.b(&ca);
    add(0x0c, vec![(1 << 5) | 14, (3 << 3) | 3, cab]);

    let locals = h.b(&[0x07, 1, 0x08]);
    add(0x11, vec![locals]);
    let craft = h.s(NATIVE_MODULE);
    add(0x1a, vec![craft]);
    let helper = h.s("helper");
    add(0x1c, vec![0x0140, (native_first << 1) | 1, helper, 1]);
    if !v2 {
        let missing = h.s("missing_fn");
        add(0x1c, vec![0x0102, ((native_first + 1) << 1) | 1, missing, 1]);
    }
    let asm = h.s(ASSEMBLY_NAME);
    add(0x20, vec![0x8004, 1, 2, 3, 4, 0, 0, asm, 0]);
    let token_blob = h.b(&[0xb0, 0x3f, 0x5f, 0x7f, 0x11, 0xd5, 0x0a, 0x3a]);
    let sr = h.s("System.Runtime");
    add(0x23, vec![8, 0, 0, 0, 0, token_blob, sr, 0, 0]);
    let sc = h.s("System.Console");
    add(0x23, vec![8, 0, 0, 0, 0, token_blob, sc, 0, 0]);
    let resn = h.s("Sample.Strings.resources");
    add(0x28, vec![0, 1, resn, 0]);
    add(0x29, vec![4, 2]);
    let tname = h.s("T");
    add(0x2a, vec![0, 0, (3 << 1) | 1, tname]);
    h.u("hi");

    // #~ stream.
    let mut ts = vec![0, 0, 0, 0, 2, 0, if wide { 0x47 } else { 0 }, 1];
    let valid: u64 = tables.keys().fold(0, |m, &t| m | (1u64 << t));
    ts.extend_from_slice(&valid.to_le_bytes());
    ts.extend_from_slice(&0u64.to_le_bytes());
    for rows in tables.values() {
        ts.extend_from_slice(&(rows.len() as u32).to_le_bytes());
    }
    if wide {
        ts.extend_from_slice(&0xdead_beefu32.to_le_bytes());
    }
    for (&t, rows) in &tables {
        for row in rows {
            assert_eq!(row.len(), widths(t).len(), "table {t:#x}");
            for (v, w) in row.iter().zip(widths(t)) {
                let w = if *w == 3 { if wide { 4 } else { 2 } } else { *w };
                if w == 2 {
                    ts.extend_from_slice(&(*v as u16).to_le_bytes());
                } else {
                    ts.extend_from_slice(&v.to_le_bytes());
                }
            }
        }
    }
    pad4(&mut ts);
    for heap in [&mut h.strings, &mut h.blob, &mut h.us, &mut h.guid] {
        pad4(heap);
    }

    // Metadata root.
    let streams: [(&str, &Vec<u8>); 5] =
        [(if ptr { "#-" } else { "#~" }, &ts), ("#Strings", &h.strings), ("#US", &h.us), ("#GUID", &h.guid), ("#Blob", &h.blob)];
    let mut header_len = 16 + 12 + 4;
    for (name, _) in &streams {
        header_len += 8 + (name.len() + 1).div_ceil(4) * 4;
    }
    let mut md = Vec::new();
    md.extend_from_slice(b"BSJB");
    md.extend_from_slice(&1u16.to_le_bytes());
    md.extend_from_slice(&1u16.to_le_bytes());
    md.extend_from_slice(&0u32.to_le_bytes());
    md.extend_from_slice(&12u32.to_le_bytes());
    md.extend_from_slice(b"v4.0.30319\0\0");
    md.extend_from_slice(&0u16.to_le_bytes());
    md.extend_from_slice(&(streams.len() as u16).to_le_bytes());
    let mut off = header_len;
    for (name, data) in &streams {
        md.extend_from_slice(&(off as u32).to_le_bytes());
        md.extend_from_slice(&(data.len() as u32).to_le_bytes());
        let mut nb = name.as_bytes().to_vec();
        nb.push(0);
        pad4(&mut nb);
        md.extend(nb);
        off += data.len();
    }
    assert_eq!(md.len(), header_len);
    for (_, data) in &streams {
        md.extend_from_slice(data);
    }

    // .text: CLI header, bodies, resources, metadata.
    let md_rva = res_rva + resources.len() as u32;
    let mut text = Vec::new();
    text.extend_from_slice(&72u32.to_le_bytes());
    text.extend_from_slice(&2u16.to_le_bytes());
    text.extend_from_slice(&5u16.to_le_bytes());
    text.extend_from_slice(&md_rva.to_le_bytes());
    text.extend_from_slice(&(md.len() as u32).to_le_bytes());
    text.extend_from_slice(&1u32.to_le_bytes()); // ILONLY
    text.extend_from_slice(&0u32.to_le_bytes()); // entry point (a library)
    text.extend_from_slice(&res_rva.to_le_bytes());
    text.extend_from_slice(&(resources.len() as u32).to_le_bytes());
    text.resize(72, 0);
    text.extend(bodies);
    text.extend(resources);
    text.extend(md);
    let raw_size = text.len().div_ceil(0x200) * 0x200;

    let mut f = vec![0u8; 0x200];
    f[0] = b'M';
    f[1] = b'Z';
    f[0x3c..0x40].copy_from_slice(&0x80u32.to_le_bytes());
    f[0x80..0x84].copy_from_slice(b"PE\0\0");
    let coff = 0x84;
    f[coff..coff + 2].copy_from_slice(&0x14cu16.to_le_bytes());
    f[coff + 2..coff + 4].copy_from_slice(&1u16.to_le_bytes());
    f[coff + 16..coff + 18].copy_from_slice(&224u16.to_le_bytes());
    f[coff + 18..coff + 20].copy_from_slice(&0x2102u16.to_le_bytes());
    let opt = coff + 20;
    f[opt..opt + 2].copy_from_slice(&0x10bu16.to_le_bytes());
    f[opt + 28..opt + 32].copy_from_slice(&0x40_0000u32.to_le_bytes());
    f[opt + 32..opt + 36].copy_from_slice(&0x2000u32.to_le_bytes());
    f[opt + 36..opt + 40].copy_from_slice(&0x200u32.to_le_bytes());
    f[opt + 56..opt + 60].copy_from_slice(&(TEXT_RVA + 0x2000 * (raw_size as u32).div_ceil(0x2000)).to_le_bytes());
    f[opt + 60..opt + 64].copy_from_slice(&0x200u32.to_le_bytes());
    f[opt + 68..opt + 70].copy_from_slice(&3u16.to_le_bytes());
    f[opt + 92..opt + 96].copy_from_slice(&16u32.to_le_bytes());
    let dd14 = opt + 96 + 14 * 8;
    f[dd14..dd14 + 4].copy_from_slice(&TEXT_RVA.to_le_bytes());
    f[dd14 + 4..dd14 + 8].copy_from_slice(&72u32.to_le_bytes());
    let sec = opt + 224;
    f[sec..sec + 5].copy_from_slice(b".text");
    f[sec + 8..sec + 12].copy_from_slice(&(text.len() as u32).to_le_bytes());
    f[sec + 12..sec + 16].copy_from_slice(&TEXT_RVA.to_le_bytes());
    f[sec + 16..sec + 20].copy_from_slice(&(raw_size as u32).to_le_bytes());
    f[sec + 20..sec + 24].copy_from_slice(&0x200u32.to_le_bytes());
    f[sec + 36..sec + 40].copy_from_slice(&0x6000_0020u32.to_le_bytes());
    text.resize(raw_size, 0);
    f.extend(text);
    f
}

/// Decompiled-looking C# for the v1 sample, with one deliberate mismatch (`Add` takes `long`) and
/// one extra method (`Reset`) so reconstruction checks have something to find.
pub const RECONSTRUCTION_CS: &str = r#"
// Reconstructed by hand for tests.
using System;
using System.Runtime.InteropServices;

namespace Sample
{
    public class Calculator
    {
        private int _total;

        public int Add(long a, int b) { return (int)a + b; }

        public void Accumulate(int x)
        {
            _total += x;
            Console.WriteLine("hi { not a brace");
            try { Add(1, 2); } finally { }
        }

        public static T Identity<T>(T value) => value;

        public Calculator() { }

        public void Reset() { _total = 0; }

        public class Options
        {
            public bool Verbose;
        }
    }

    public static class NativeMethods
    {
        [DllImport("craft", SetLastError = true)]
        public static extern int helper(int n);

        [DllImport("craft", EntryPoint = "missing_fn", CharSet = CharSet.Ansi)]
        public static extern void MissingFn();

        [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.InternalCall)]
        public static extern long GetTicks();
    }
}
"#;
