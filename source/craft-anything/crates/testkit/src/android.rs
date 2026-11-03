//! Synthetic Android fixtures: a DEX writer, a binary XML (AXML) writer, a resource table
//! (ARSC) writer, DER certificates and PKCS#7 blobs, an APK Signing Block, and a small "Notes"
//! APK built from them, so tests can check exact facts.
//!
//! The DEX writer emits ids in creation order (not sorted as a real compiler would), leaves the
//! SHA-1 signature field zero and writes no map list; the Adler-32 checksum is correct.

use crate::electron::zip_stored;

pub const PACKAGE: &str = "com.example.notes";
pub const HELLO: &str = "Hello, Craft!";

// ---------------------------------------------------------------------------------------------
// Little-endian helpers

fn u16le(v: &mut Vec<u8>, x: u16) {
    v.extend_from_slice(&x.to_le_bytes());
}
fn u32le(v: &mut Vec<u8>, x: u32) {
    v.extend_from_slice(&x.to_le_bytes());
}
fn uleb(v: &mut Vec<u8>, mut x: u32) {
    loop {
        let b = (x & 0x7f) as u8;
        x >>= 7;
        if x == 0 {
            v.push(b);
            break;
        }
        v.push(b | 0x80);
    }
}
fn sleb(v: &mut Vec<u8>, mut x: i32) {
    loop {
        let b = (x & 0x7f) as u8;
        x >>= 7;
        let done = (x == 0 && b & 0x40 == 0) || (x == -1 && b & 0x40 != 0);
        v.push(if done { b } else { b | 0x80 });
        if done {
            break;
        }
    }
}
fn align4(v: &mut Vec<u8>) {
    while !v.len().is_multiple_of(4) {
        v.push(0);
    }
}

// ---------------------------------------------------------------------------------------------
// DER

pub fn der(tag: u8, content: &[u8]) -> Vec<u8> {
    let mut v = vec![tag];
    let n = content.len();
    if n < 0x80 {
        v.push(n as u8);
    } else if n < 0x100 {
        v.extend_from_slice(&[0x81, n as u8]);
    } else {
        v.extend_from_slice(&[0x82, (n >> 8) as u8, n as u8]);
    }
    v.extend_from_slice(content);
    v
}

pub fn der_oid(dotted: &str) -> Vec<u8> {
    let parts: Vec<u64> = dotted.split('.').map(|p| p.parse().unwrap()).collect();
    let mut c = vec![(parts[0] * 40 + parts[1]) as u8];
    for &p in &parts[2..] {
        let mut stack = vec![(p & 0x7f) as u8];
        let mut x = p >> 7;
        while x > 0 {
            stack.push(((x & 0x7f) as u8) | 0x80);
            x >>= 7;
        }
        stack.reverse();
        c.extend(stack);
    }
    der(0x06, &c)
}

fn seq(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x30, &parts.concat())
}
fn set(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x31, &parts.concat())
}

fn dn(cn: &str, o: &str) -> Vec<u8> {
    seq(&[set(&[seq(&[der_oid("2.5.4.3"), der(0x0c, cn.as_bytes())])]), set(&[seq(&[der_oid("2.5.4.10"), der(0x0c, o.as_bytes())])])])
}

/// A self-signed-looking X.509 v3 certificate (the signature bytes are fake).
pub fn certificate_der(cn: &str, o: &str) -> Vec<u8> {
    let alg = seq(&[der_oid("1.2.840.113549.1.1.11"), der(0x05, &[])]);
    let tbs = seq(&[
        der(0xa0, &der(0x02, &[2])),
        der(0x02, &[1, 2, 3, 4, 5]),
        alg.clone(),
        dn(cn, o),
        seq(&[der(0x17, b"250101000000Z"), der(0x17, b"350101000000Z")]),
        dn(cn, o),
        seq(&[seq(&[der_oid("1.2.840.113549.1.1.1"), der(0x05, &[])]), der(0x03, &[0, 1, 2, 3])]),
    ]);
    seq(&[tbs, alg, der(0x03, &[0, 0xaa, 0xbb])])
}

/// A PKCS#7 SignedData wrapping `cert`, like `META-INF/CERT.RSA`.
pub fn pkcs7_der(cert: &[u8]) -> Vec<u8> {
    let sd = seq(&[der(0x02, &[1]), set(&[]), seq(&[der_oid("1.2.840.113549.1.7.1")]), der(0xa0, cert), set(&[])]);
    seq(&[der_oid("1.2.840.113549.1.7.2"), der(0xa0, &sd)])
}

// ---------------------------------------------------------------------------------------------
// DEX

#[derive(Debug, Clone, Default)]
pub struct TrySpec {
    pub start: u32,
    pub count: u16,
    /// (type idx, handler address)
    pub handlers: Vec<(u32, u32)>,
    pub catch_all: Option<u32>,
}

#[derive(Debug, Clone, Default)]
pub struct CodeSpec {
    pub registers: u16,
    pub ins: u16,
    pub outs: u16,
    pub insns: Vec<u16>,
    pub tries: Vec<TrySpec>,
}

#[derive(Debug, Clone)]
pub struct MethodSpec {
    pub method: u32,
    pub access: u32,
    pub code: Option<CodeSpec>,
}

#[derive(Debug, Clone, Default)]
pub struct ClassSpec {
    pub class: u32,
    pub access: u32,
    pub superclass: u32,
    pub interfaces: Vec<u32>,
    pub source_file: u32,
    pub annotations: Vec<u32>,
    pub static_fields: Vec<(u32, u32)>,
    pub instance_fields: Vec<(u32, u32)>,
    pub direct: Vec<MethodSpec>,
    pub virtuals: Vec<MethodSpec>,
}

#[derive(Debug, Clone, Default)]
pub struct DexBuilder {
    strings: Vec<String>,
    types: Vec<u32>,
    protos: Vec<(u32, u32, Vec<u32>)>,
    fields: Vec<(u32, u32, u32)>,
    methods: Vec<(u32, u32, u32)>,
    pub classes: Vec<ClassSpec>,
}

impl DexBuilder {
    pub fn string(&mut self, s: &str) -> u32 {
        if let Some(i) = self.strings.iter().position(|x| x == s) {
            return i as u32;
        }
        self.strings.push(s.to_string());
        (self.strings.len() - 1) as u32
    }

    pub fn ty(&mut self, desc: &str) -> u32 {
        let s = self.string(desc);
        if let Some(i) = self.types.iter().position(|&x| x == s) {
            return i as u32;
        }
        self.types.push(s);
        (self.types.len() - 1) as u32
    }

    pub fn proto(&mut self, ret: &str, params: &[&str]) -> u32 {
        let short = |d: &str| if d.starts_with('L') || d.starts_with('[') { 'L' } else { d.chars().next().unwrap() };
        let shorty: String = std::iter::once(short(ret)).chain(params.iter().map(|p| short(p))).collect();
        let s = self.string(&shorty);
        let r = self.ty(ret);
        let ps: Vec<u32> = params.iter().map(|p| self.ty(p)).collect();
        if let Some(i) = self.protos.iter().position(|p| p.1 == r && p.2 == ps) {
            return i as u32;
        }
        self.protos.push((s, r, ps));
        (self.protos.len() - 1) as u32
    }

    pub fn field(&mut self, cls: &str, ty: &str, name: &str) -> u32 {
        let c = self.ty(cls);
        let t = self.ty(ty);
        let n = self.string(name);
        if let Some(i) = self.fields.iter().position(|&f| f == (c, t, n)) {
            return i as u32;
        }
        self.fields.push((c, t, n));
        (self.fields.len() - 1) as u32
    }

    pub fn method(&mut self, cls: &str, name: &str, ret: &str, params: &[&str]) -> u32 {
        let c = self.ty(cls);
        let p = self.proto(ret, params);
        let n = self.string(name);
        if let Some(i) = self.methods.iter().position(|&m| m == (c, p, n)) {
            return i as u32;
        }
        self.methods.push((c, p, n));
        (self.methods.len() - 1) as u32
    }

    pub fn build(self) -> Vec<u8> {
        let ns = self.strings.len();
        let nt = self.types.len();
        let np = self.protos.len();
        let nf = self.fields.len();
        let nm = self.methods.len();
        let nc = self.classes.len();
        let string_ids = 0x70;
        let type_ids = string_ids + ns * 4;
        let proto_ids = type_ids + nt * 4;
        let field_ids = proto_ids + np * 12;
        let method_ids = field_ids + nf * 8;
        let class_defs = method_ids + nm * 8;
        let mut data_start = class_defs + nc * 32;
        data_start = (data_start + 3) & !3;
        let mut d: Vec<u8> = Vec::new();
        let at = |d: &Vec<u8>| (data_start + d.len()) as u32;
        // type lists
        let tl = |d: &mut Vec<u8>, list: &[u32]| -> u32 {
            if list.is_empty() {
                return 0;
            }
            align4(d);
            let o = at(d);
            u32le(d, list.len() as u32);
            for &t in list {
                u16le(d, t as u16);
            }
            o
        };
        let proto_params: Vec<u32> = self.protos.iter().map(|p| tl(&mut d, &p.2)).collect();
        let class_ifaces: Vec<u32> = self.classes.iter().map(|c| tl(&mut d, &c.interfaces)).collect();
        // string data
        let mut string_offs = Vec::new();
        for s in &self.strings {
            string_offs.push(at(&d));
            uleb(&mut d, s.encode_utf16().count() as u32);
            for ch in s.chars() {
                let c = ch as u32;
                if c == 0 {
                    d.extend_from_slice(&[0xc0, 0x80]);
                } else if c < 0x80 {
                    d.push(c as u8);
                } else if c < 0x800 {
                    d.extend_from_slice(&[0xc0 | (c >> 6) as u8, 0x80 | (c & 0x3f) as u8]);
                } else {
                    d.extend_from_slice(&[0xe0 | (c >> 12) as u8, 0x80 | ((c >> 6) & 0x3f) as u8, 0x80 | (c & 0x3f) as u8]);
                }
            }
            d.push(0);
        }
        // code items, class data, annotations
        let mut class_data_offs = Vec::new();
        let mut annot_offs = Vec::new();
        for c in &self.classes {
            let code_off = |d: &mut Vec<u8>, m: &MethodSpec| -> u32 {
                let Some(code) = &m.code else { return 0 };
                align4(d);
                let o = at(d);
                u16le(d, code.registers);
                u16le(d, code.ins);
                u16le(d, code.outs);
                u16le(d, code.tries.len() as u16);
                u32le(d, 0);
                u32le(d, code.insns.len() as u32);
                for &i in &code.insns {
                    u16le(d, i);
                }
                if !code.tries.is_empty() {
                    if code.insns.len() % 2 == 1 {
                        u16le(d, 0);
                    }
                    let mut list = Vec::new();
                    uleb(&mut list, code.tries.len() as u32);
                    let mut offs = Vec::new();
                    for t in &code.tries {
                        offs.push(list.len() as u16);
                        let n = t.handlers.len() as i32;
                        sleb(&mut list, if t.catch_all.is_some() { -n } else { n });
                        for &(ty, addr) in &t.handlers {
                            uleb(&mut list, ty);
                            uleb(&mut list, addr);
                        }
                        if let Some(a) = t.catch_all {
                            uleb(&mut list, a);
                        }
                    }
                    for (t, off) in code.tries.iter().zip(offs) {
                        u32le(d, t.start);
                        u16le(d, t.count);
                        u16le(d, off);
                    }
                    d.extend_from_slice(&list);
                }
                o
            };
            let mut direct = c.direct.clone();
            direct.sort_by_key(|m| m.method);
            let mut virtuals = c.virtuals.clone();
            virtuals.sort_by_key(|m| m.method);
            let direct_offs: Vec<u32> = direct.iter().map(|m| code_off(&mut d, m)).collect();
            let virtual_offs: Vec<u32> = virtuals.iter().map(|m| code_off(&mut d, m)).collect();
            let cd = at(&d);
            let mut sf = c.static_fields.clone();
            sf.sort();
            let mut inf = c.instance_fields.clone();
            inf.sort();
            uleb(&mut d, sf.len() as u32);
            uleb(&mut d, inf.len() as u32);
            uleb(&mut d, direct.len() as u32);
            uleb(&mut d, virtuals.len() as u32);
            for list in [&sf, &inf] {
                let mut prev = 0;
                for &(f, a) in list.iter() {
                    uleb(&mut d, f - prev);
                    uleb(&mut d, a);
                    prev = f;
                }
            }
            for (list, offs) in [(&direct, &direct_offs), (&virtuals, &virtual_offs)] {
                let mut prev = 0;
                for (m, &o) in list.iter().zip(offs.iter()) {
                    uleb(&mut d, m.method - prev);
                    uleb(&mut d, m.access);
                    uleb(&mut d, o);
                    prev = m.method;
                }
            }
            class_data_offs.push(cd);
            if c.annotations.is_empty() {
                annot_offs.push(0);
            } else {
                let mut items = Vec::new();
                for &t in &c.annotations {
                    items.push(at(&d));
                    d.push(1); // runtime visibility
                    uleb(&mut d, t);
                    uleb(&mut d, 0);
                }
                align4(&mut d);
                let set_off = at(&d);
                u32le(&mut d, items.len() as u32);
                for i in items {
                    u32le(&mut d, i);
                }
                let dir = at(&d);
                u32le(&mut d, set_off);
                u32le(&mut d, 0);
                u32le(&mut d, 0);
                u32le(&mut d, 0);
                annot_offs.push(dir);
            }
        }
        align4(&mut d);
        let file_size = data_start + d.len();
        let mut out = vec![0u8; data_start];
        out[..8].copy_from_slice(b"dex\n035\0");
        let put = |out: &mut Vec<u8>, off: usize, v: u32| out[off..off + 4].copy_from_slice(&v.to_le_bytes());
        put(&mut out, 32, file_size as u32);
        put(&mut out, 36, 0x70);
        put(&mut out, 40, 0x1234_5678);
        for (i, (n, o)) in [(ns, string_ids), (nt, type_ids), (np, proto_ids), (nf, field_ids), (nm, method_ids), (nc, class_defs)].iter().enumerate() {
            put(&mut out, 56 + i * 8, *n as u32);
            put(&mut out, 60 + i * 8, if *n == 0 { 0 } else { *o as u32 });
        }
        put(&mut out, 104, d.len() as u32);
        put(&mut out, 108, data_start as u32);
        for (i, o) in string_offs.iter().enumerate() {
            put(&mut out, string_ids + i * 4, *o);
        }
        for (i, t) in self.types.iter().enumerate() {
            put(&mut out, type_ids + i * 4, *t);
        }
        for (i, p) in self.protos.iter().enumerate() {
            put(&mut out, proto_ids + i * 12, p.0);
            put(&mut out, proto_ids + i * 12 + 4, p.1);
            put(&mut out, proto_ids + i * 12 + 8, proto_params[i]);
        }
        for (i, (c, t, n)) in self.fields.iter().enumerate() {
            out[field_ids + i * 8..field_ids + i * 8 + 2].copy_from_slice(&(*c as u16).to_le_bytes());
            out[field_ids + i * 8 + 2..field_ids + i * 8 + 4].copy_from_slice(&(*t as u16).to_le_bytes());
            put(&mut out, field_ids + i * 8 + 4, *n);
        }
        for (i, (c, p, n)) in self.methods.iter().enumerate() {
            out[method_ids + i * 8..method_ids + i * 8 + 2].copy_from_slice(&(*c as u16).to_le_bytes());
            out[method_ids + i * 8 + 2..method_ids + i * 8 + 4].copy_from_slice(&(*p as u16).to_le_bytes());
            put(&mut out, method_ids + i * 8 + 4, *n);
        }
        for (i, c) in self.classes.iter().enumerate() {
            let o = class_defs + i * 32;
            for (k, v) in [c.class, c.access, c.superclass, class_ifaces[i], c.source_file, annot_offs[i], class_data_offs[i], 0].iter().enumerate() {
                put(&mut out, o + k * 4, *v);
            }
        }
        out.extend_from_slice(&d);
        let sum = adler32(&out[12..]);
        put(&mut out, 8, sum);
        out
    }
}

fn adler32(data: &[u8]) -> u32 {
    let (mut a, mut b) = (1u32, 0u32);
    for &x in data {
        a = (a + u32::from(x)) % 65521;
        b = (b + a) % 65521;
    }
    (b << 16) | a
}

const MAIN: &str = "Lcom/example/notes/MainActivity;";
const UTIL: &str = "Lcom/example/notes/Util;";
const STRING: &str = "Ljava/lang/String;";

/// `classes.dex` of the Notes app: `MainActivity` (constructor, `onCreate`, `run`, `pick` with a
/// packed switch inside a try/catch) and `Util` (two `log` overloads printing through
/// `System.out`).
pub fn notes_dex() -> Vec<u8> {
    let mut b = DexBuilder::default();
    let activity = b.ty("Landroid/app/Activity;");
    let main = b.ty(MAIN);
    let runnable = b.ty("Ljava/lang/Runnable;");
    let deprecated = b.ty("Ljava/lang/Deprecated;");
    let rte = b.ty("Ljava/lang/RuntimeException;");
    let object = b.ty("Ljava/lang/Object;");
    let util = b.ty(UTIL);
    let tag = b.field(MAIN, STRING, "TAG");
    let count = b.field(MAIN, "I", "count");
    let out = b.field("Ljava/lang/System;", "Ljava/io/PrintStream;", "out");
    let super_init = b.method("Landroid/app/Activity;", "<init>", "V", &[]);
    let super_create = b.method("Landroid/app/Activity;", "onCreate", "V", &["Landroid/os/Bundle;"]);
    let init = b.method(MAIN, "<init>", "V", &[]);
    let on_create = b.method(MAIN, "onCreate", "V", &["Landroid/os/Bundle;"]);
    let run = b.method(MAIN, "run", "V", &[]);
    let pick = b.method(MAIN, "pick", "I", &["I"]);
    let log_s = b.method(UTIL, "log", "V", &[STRING]);
    let log_i = b.method(UTIL, "log", "V", &["I"]);
    let println = b.method("Ljava/io/PrintStream;", "println", "V", &[STRING]);
    let hello = b.string(HELLO);
    let main_src = b.string("MainActivity.java");
    let util_src = b.string("Util.java");
    let code = |registers, ins, outs, insns: Vec<u16>| Some(CodeSpec { registers, ins, outs, insns, tries: vec![] });
    b.classes.push(ClassSpec {
        class: main,
        access: 0x1,
        superclass: activity,
        interfaces: vec![runnable],
        source_file: main_src,
        annotations: vec![deprecated],
        static_fields: vec![(tag, 0x1a)],
        instance_fields: vec![(count, 0x2)],
        direct: vec![MethodSpec { method: init, access: 0x10001, code: code(1, 1, 1, vec![0x1070, super_init as u16, 0x0000, 0x000e]) }],
        virtuals: vec![
            MethodSpec {
                method: on_create,
                access: 0x1,
                code: code(3, 2, 2, vec![0x001a, hello as u16, 0x1071, log_s as u16, 0x0000, 0x206f, super_create as u16, 0x0021, 0x000e]),
            },
            MethodSpec { method: run, access: 0x1, code: code(1, 1, 1, vec![0x7012, 0x1071, log_i as u16, 0x0000, 0x000e]) },
            MethodSpec {
                method: pick,
                access: 0x1,
                code: Some(CodeSpec {
                    registers: 3,
                    ins: 2,
                    outs: 0,
                    insns: vec![0x022b, 10, 0, 0x0012, 0x000f, 0x1012, 0x000f, 0x2012, 0x000f, 0x0000, 0x0100, 2, 1, 0, 5, 0, 7, 0],
                    tries: vec![TrySpec { start: 0, count: 3, handlers: vec![(rte, 3)], catch_all: Some(3) }],
                }),
            },
        ],
    });
    b.classes.push(ClassSpec {
        class: util,
        access: 0x11,
        superclass: object,
        source_file: util_src,
        direct: vec![
            MethodSpec { method: log_s, access: 0x9, code: code(2, 1, 2, vec![0x0062, out as u16, 0x206e, println as u16, 0x0010, 0x000e]) },
            MethodSpec { method: log_i, access: 0x9, code: code(1, 1, 0, vec![0x000e]) },
        ],
        ..ClassSpec::default()
    });
    b.build()
}

/// `classes2.dex`: `extra.Helper.go()` calls `Util.log(String)` across DEX files.
pub fn helper_dex() -> Vec<u8> {
    let mut b = DexBuilder::default();
    let helper = b.ty("Lcom/example/notes/extra/Helper;");
    let object = b.ty("Ljava/lang/Object;");
    let go = b.method("Lcom/example/notes/extra/Helper;", "go", "V", &[]);
    let log_s = b.method(UTIL, "log", "V", &[STRING]);
    let s = b.string("from helper");
    b.classes.push(ClassSpec {
        class: helper,
        access: 0x1,
        superclass: object,
        source_file: u32::MAX,
        direct: vec![MethodSpec {
            method: go,
            access: 0x9,
            code: Some(CodeSpec { registers: 1, ins: 0, outs: 1, insns: vec![0x001a, s as u16, 0x1071, log_s as u16, 0x0000, 0x000e], tries: vec![] }),
        }],
        ..ClassSpec::default()
    });
    b.build()
}

// ---------------------------------------------------------------------------------------------
// String pools, AXML, ARSC

/// A string pool chunk (UTF-16, or UTF-8 when `utf8`).
pub fn string_pool(strings: &[&str], utf8: bool) -> Vec<u8> {
    let mut data = Vec::new();
    let mut offs = Vec::new();
    for s in strings {
        offs.push(data.len() as u32);
        if utf8 {
            let n16 = s.encode_utf16().count();
            data.push(n16 as u8);
            data.push(s.len() as u8);
            data.extend_from_slice(s.as_bytes());
            data.push(0);
        } else {
            let units: Vec<u16> = s.encode_utf16().collect();
            u16le(&mut data, units.len() as u16);
            for u in units {
                u16le(&mut data, u);
            }
            u16le(&mut data, 0);
        }
    }
    align4(&mut data);
    let strings_start = 28 + 4 * strings.len();
    let mut v = Vec::new();
    u16le(&mut v, 0x0001);
    u16le(&mut v, 28);
    u32le(&mut v, (strings_start + data.len()) as u32);
    u32le(&mut v, strings.len() as u32);
    u32le(&mut v, 0);
    u32le(&mut v, if utf8 { 1 << 8 } else { 0 });
    u32le(&mut v, strings_start as u32);
    u32le(&mut v, 0);
    for o in offs {
        u32le(&mut v, o);
    }
    v.extend_from_slice(&data);
    v
}

/// An attribute value in a binary XML element.
#[derive(Debug, Clone, Copy)]
pub enum AxVal<'a> {
    Str(&'a str),
    Bool(bool),
    Int(i32),
    Hex(u32),
    Ref(u32),
}

#[derive(Debug, Clone)]
pub struct AxAttr<'a> {
    pub name: &'a str,
    /// Android framework attribute (namespaced, with its resource id).
    pub res_id: Option<u32>,
    pub val: AxVal<'a>,
}

#[derive(Debug, Clone)]
pub enum AxNode<'a> {
    Start(&'a str, Vec<AxAttr<'a>>),
    End(&'a str),
}

const NS: &str = "http://schemas.android.com/apk/res/android";

/// Shorthand for an `android:` attribute.
pub fn a<'a>(name: &'a str, res_id: u32, val: AxVal<'a>) -> AxAttr<'a> {
    AxAttr { name, res_id: Some(res_id), val }
}

/// Write a binary XML document with the android namespace declared on the root.
pub fn axml(nodes: &[AxNode<'_>]) -> Vec<u8> {
    let mut strings: Vec<String> = Vec::new();
    let mut ids: Vec<u32> = Vec::new();
    for n in nodes {
        if let AxNode::Start(_, attrs) = n {
            for at in attrs {
                if let Some(id) = at.res_id
                    && !strings.iter().any(|s| s == at.name)
                {
                    strings.push(at.name.to_string());
                    ids.push(id);
                }
            }
        }
    }
    let intern = |s: &str, strings: &mut Vec<String>| -> u32 {
        if let Some(i) = strings.iter().position(|x| x == s) {
            return i as u32;
        }
        strings.push(s.to_string());
        (strings.len() - 1) as u32
    };
    let prefix = intern("android", &mut strings);
    let uri = intern(NS, &mut strings);
    let mut body = Vec::new();
    let ns_chunk = |t: u16| {
        let mut c = Vec::new();
        u16le(&mut c, t);
        u16le(&mut c, 16);
        u32le(&mut c, 24);
        u32le(&mut c, 1);
        u32le(&mut c, u32::MAX);
        u32le(&mut c, prefix);
        u32le(&mut c, uri);
        c
    };
    body.extend(ns_chunk(0x0100));
    for (line, n) in nodes.iter().enumerate() {
        match n {
            AxNode::Start(name, attrs) => {
                let nidx = intern(name, &mut strings);
                let mut c = Vec::new();
                u16le(&mut c, 0x0102);
                u16le(&mut c, 16);
                u32le(&mut c, (36 + 20 * attrs.len()) as u32);
                u32le(&mut c, line as u32 + 2);
                u32le(&mut c, u32::MAX);
                u32le(&mut c, u32::MAX);
                u32le(&mut c, nidx);
                u16le(&mut c, 20);
                u16le(&mut c, 20);
                u16le(&mut c, attrs.len() as u16);
                u16le(&mut c, 0);
                u16le(&mut c, 0);
                u16le(&mut c, 0);
                for at in attrs {
                    let an = intern(at.name, &mut strings);
                    let (raw, ty, data) = match at.val {
                        AxVal::Str(s) => {
                            let i = intern(s, &mut strings);
                            (i, 0x03u8, i)
                        }
                        AxVal::Bool(b) => (u32::MAX, 0x12, if b { u32::MAX } else { 0 }),
                        AxVal::Int(i) => (u32::MAX, 0x10, i as u32),
                        AxVal::Hex(h) => (u32::MAX, 0x11, h),
                        AxVal::Ref(r) => (u32::MAX, 0x01, r),
                    };
                    u32le(&mut c, if at.res_id.is_some() { uri } else { u32::MAX });
                    u32le(&mut c, an);
                    u32le(&mut c, raw);
                    u16le(&mut c, 8);
                    c.push(0);
                    c.push(ty);
                    u32le(&mut c, data);
                }
                body.extend(c);
            }
            AxNode::End(name) => {
                let nidx = intern(name, &mut strings);
                let mut c = Vec::new();
                u16le(&mut c, 0x0103);
                u16le(&mut c, 16);
                u32le(&mut c, 24);
                u32le(&mut c, line as u32 + 2);
                u32le(&mut c, u32::MAX);
                u32le(&mut c, u32::MAX);
                u32le(&mut c, nidx);
                body.extend(c);
            }
        }
    }
    body.extend(ns_chunk(0x0101));
    let refs: Vec<&str> = strings.iter().map(String::as_str).collect();
    let pool = string_pool(&refs, false);
    let mut map = Vec::new();
    u16le(&mut map, 0x0180);
    u16le(&mut map, 8);
    u32le(&mut map, (8 + 4 * ids.len()) as u32);
    for id in &ids {
        u32le(&mut map, *id);
    }
    let mut out = Vec::new();
    u16le(&mut out, 0x0003);
    u16le(&mut out, 8);
    u32le(&mut out, (8 + pool.len() + map.len() + body.len()) as u32);
    out.extend(pool);
    out.extend(map);
    out.extend(body);
    out
}

/// The Notes app's `AndroidManifest.xml`.
pub fn manifest_axml() -> Vec<u8> {
    use AxNode::{End, Start};
    use AxVal::*;
    let name = |v| a("name", 0x0101_0003, Str(v));
    axml(&[
        Start(
            "manifest",
            vec![
                AxAttr { name: "package", res_id: None, val: Str(PACKAGE) },
                a("versionCode", 0x0101_021b, Int(42)),
                a("versionName", 0x0101_021c, Str("1.2.3")),
            ],
        ),
        Start("uses-sdk", vec![a("minSdkVersion", 0x0101_020c, Int(24)), a("targetSdkVersion", 0x0101_0270, Int(34))]),
        End("uses-sdk"),
        Start("uses-permission", vec![name("android.permission.INTERNET")]),
        End("uses-permission"),
        Start("uses-permission", vec![name("android.permission.CAMERA")]),
        End("uses-permission"),
        Start("permission", vec![name("com.example.notes.permission.SYNC"), a("protectionLevel", 0x0101_0009, Hex(2))]),
        End("permission"),
        Start(
            "application",
            vec![
                name(".NotesApp"),
                a("label", 0x0101_0001, Ref(0x7f01_0000)),
                a("debuggable", 0x0101_000f, Bool(true)),
                a("allowBackup", 0x0101_0280, Bool(false)),
            ],
        ),
        Start("activity", vec![name(".MainActivity"), a("exported", 0x0101_0010, Bool(true))]),
        Start("intent-filter", vec![]),
        Start("action", vec![name("android.intent.action.MAIN")]),
        End("action"),
        Start("category", vec![name("android.intent.category.LAUNCHER")]),
        End("category"),
        Start("data", vec![a("scheme", 0x0101_0027, Str("notes")), a("host", 0x0101_0028, Str("open"))]),
        End("data"),
        End("intent-filter"),
        End("activity"),
        Start("service", vec![name(".SyncService"), a("exported", 0x0101_0010, Bool(false))]),
        End("service"),
        Start(
            "provider",
            vec![
                name("androidx.core.content.FileProvider"),
                a("authorities", 0x0101_0018, Str("com.example.notes.files")),
                a("exported", 0x0101_0010, Bool(false)),
            ],
        ),
        End("provider"),
        End("application"),
        End("manifest"),
    ])
}

/// `res/layout/main.xml`: a LinearLayout with one TextView showing `@string/greeting`.
pub fn layout_axml() -> Vec<u8> {
    use AxNode::{End, Start};
    axml(&[
        Start("LinearLayout", vec![a("orientation", 0x0101_00c4, AxVal::Int(1))]),
        Start("TextView", vec![a("text", 0x0101_014f, AxVal::Ref(0x7f01_0001))]),
        End("TextView"),
        End("LinearLayout"),
    ])
}

fn config(lang: &[u8; 2], density: u16, ui_mode: u8, sdk: u16) -> Vec<u8> {
    let mut c = vec![0u8; 64];
    c[0] = 64;
    if lang != b"\0\0" {
        c[8..10].copy_from_slice(lang);
    }
    c[14..16].copy_from_slice(&density.to_le_bytes());
    c[24..26].copy_from_slice(&sdk.to_le_bytes());
    c[29] = ui_mode;
    c
}

fn type_spec(id: u8, entries: u32) -> Vec<u8> {
    let mut c = Vec::new();
    u16le(&mut c, 0x0202);
    u16le(&mut c, 16);
    u32le(&mut c, 16 + 4 * entries);
    c.push(id);
    c.push(0);
    u16le(&mut c, 0);
    u32le(&mut c, entries);
    for _ in 0..entries {
        u32le(&mut c, 0);
    }
    c
}

/// A type chunk from already-encoded entries.
fn type_chunk(id: u8, cfg: &[u8], entries: &[Vec<u8>]) -> Vec<u8> {
    let header = 20 + cfg.len();
    let start = header + 4 * entries.len();
    let mut offs = Vec::new();
    let mut body = Vec::new();
    for e in entries {
        offs.push(body.len() as u32);
        body.extend_from_slice(e);
    }
    let mut c = Vec::new();
    u16le(&mut c, 0x0201);
    u16le(&mut c, header as u16);
    u32le(&mut c, (start + body.len()) as u32);
    c.push(id);
    c.push(0);
    u16le(&mut c, 0);
    u32le(&mut c, entries.len() as u32);
    u32le(&mut c, start as u32);
    c.extend_from_slice(cfg);
    for o in offs {
        u32le(&mut c, o);
    }
    c.extend(body);
    c
}

fn simple_entry(key: u32, ty: u8, data: u32) -> Vec<u8> {
    let mut e = Vec::new();
    u16le(&mut e, 8);
    u16le(&mut e, 0);
    u32le(&mut e, key);
    u16le(&mut e, 8);
    e.push(0);
    e.push(ty);
    u32le(&mut e, data);
    e
}

/// `resources.arsc`: `string/app_name` and `string/greeting` in the default locale and French,
/// and one `style/AppTheme` bag (night, xhdpi, v21) with a parent and a colour item.
pub fn resources_arsc() -> Vec<u8> {
    let global = string_pool(&["Notes", "Hello", "Notes FR", "Bonjour"], true);
    let types = string_pool(&["string", "style"], false);
    let keys = string_pool(&["app_name", "greeting", "AppTheme"], false);
    let mut bag = Vec::new();
    u16le(&mut bag, 16);
    u16le(&mut bag, 1);
    u32le(&mut bag, 2);
    u32le(&mut bag, 0x0103_0005);
    u32le(&mut bag, 1);
    u32le(&mut bag, 0x7f03_0000);
    u16le(&mut bag, 8);
    bag.push(0);
    bag.push(0x1c);
    u32le(&mut bag, 0xff33_6699);
    let mut chunks = Vec::new();
    chunks.extend(type_spec(1, 2));
    chunks.extend(type_chunk(1, &config(b"\0\0", 0, 0, 0), &[simple_entry(0, 3, 0), simple_entry(1, 3, 1)]));
    chunks.extend(type_chunk(1, &config(b"fr", 0, 0, 0), &[simple_entry(0, 3, 2), simple_entry(1, 3, 3)]));
    chunks.extend(type_spec(2, 1));
    chunks.extend(type_chunk(2, &config(b"\0\0", 320, 0x20, 21), &[bag]));
    let header = 288usize;
    let mut pkg = Vec::new();
    u16le(&mut pkg, 0x0200);
    u16le(&mut pkg, header as u16);
    u32le(&mut pkg, (header + types.len() + keys.len() + chunks.len()) as u32);
    u32le(&mut pkg, 0x7f);
    let mut name = [0u16; 128];
    for (i, u) in PACKAGE.encode_utf16().enumerate() {
        name[i] = u;
    }
    for u in name {
        u16le(&mut pkg, u);
    }
    u32le(&mut pkg, header as u32);
    u32le(&mut pkg, 2);
    u32le(&mut pkg, (header + types.len()) as u32);
    u32le(&mut pkg, 3);
    u32le(&mut pkg, 0);
    pkg.extend(types);
    pkg.extend(keys);
    pkg.extend(chunks);
    let mut out = Vec::new();
    u16le(&mut out, 0x0002);
    u16le(&mut out, 12);
    u32le(&mut out, (12 + global.len() + pkg.len()) as u32);
    u32le(&mut out, 1);
    out.extend(global);
    out.extend(pkg);
    out
}

// ---------------------------------------------------------------------------------------------
// APK Signing Block and the APK

fn lp(b: &[u8]) -> Vec<u8> {
    let mut v = (b.len() as u32).to_le_bytes().to_vec();
    v.extend_from_slice(b);
    v
}

fn signer(v3: bool, cert: &[u8]) -> Vec<u8> {
    let mut digest = 0x0103u32.to_le_bytes().to_vec();
    digest.extend(lp(&[0xaa; 32]));
    let mut signed = lp(&lp(&digest));
    signed.extend(lp(&lp(cert)));
    if v3 {
        signed.extend(24u32.to_le_bytes());
        signed.extend(0x7fff_ffffu32.to_le_bytes());
    }
    signed.extend(lp(&[]));
    let mut sig = 0x0103u32.to_le_bytes().to_vec();
    sig.extend(lp(&[0x55; 16]));
    let mut s = lp(&signed);
    if v3 {
        s.extend(24u32.to_le_bytes());
        s.extend(0x7fff_ffffu32.to_le_bytes());
    }
    s.extend(lp(&lp(&sig)));
    s.extend(lp(&[1, 2, 3, 4]));
    lp(&lp(&s))
}

/// An APK Signing Block with a v2 signer, a v3 signer and a padding pair.
pub fn signing_block(cert: &[u8]) -> Vec<u8> {
    let mut pairs = Vec::new();
    for (id, value) in [(0x7109_871au32, signer(false, cert)), (0xf053_68c0, signer(true, cert)), (0x4272_6577, vec![0; 12])] {
        pairs.extend(((value.len() + 4) as u64).to_le_bytes());
        pairs.extend(id.to_le_bytes());
        pairs.extend(value);
    }
    let size = (pairs.len() + 8 + 16) as u64;
    let mut out = size.to_le_bytes().to_vec();
    out.extend(pairs);
    out.extend(size.to_le_bytes());
    out.extend(b"APK Sig Block 42");
    out
}

/// Insert `block` between the last entry and the central directory of a ZIP from `zip_stored`.
pub fn with_signing_block(zip: &[u8], block: &[u8]) -> Vec<u8> {
    let eocd = zip.len() - 22;
    let cd = u32::from_le_bytes(zip[eocd + 16..eocd + 20].try_into().unwrap()) as usize;
    let mut out = zip[..cd].to_vec();
    out.extend_from_slice(block);
    out.extend_from_slice(&zip[cd..]);
    let e = out.len() - 22;
    out[e + 16..e + 20].copy_from_slice(&((cd + block.len()) as u32).to_le_bytes());
    out
}

/// The Notes APK: manifest, two DEX files, resources, a layout, native libraries for two ABIs,
/// a v1 signature file and a v2/v3 signing block.
pub fn notes_apk() -> Vec<u8> {
    let cert = certificate_der("Craft Test", "Craft Org");
    let manifest = manifest_axml();
    let dex = notes_dex();
    let dex2 = helper_dex();
    let arsc = resources_arsc();
    let layout = layout_axml();
    let p7 = pkcs7_der(&cert);
    let zip = zip_stored(&[
        ("AndroidManifest.xml", &manifest),
        ("classes.dex", &dex),
        ("classes2.dex", &dex2),
        ("resources.arsc", &arsc),
        ("res/layout/main.xml", &layout),
        ("lib/arm64-v8a/libnotes.so", b"\x7fELF\x02\x01\x01 arm64 placeholder"),
        ("lib/x86_64/libnotes.so", b"\x7fELF\x02\x01\x01 x86_64 placeholder"),
        ("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n\r\n"),
        ("META-INF/CERT.RSA", &p7),
    ]);
    with_signing_block(&zip, &signing_block(&cert))
}

// ---------------------------------------------------------------------------------------------
// A genuinely-signed APK (v1 JAR + v2/v3), for signature-verification tests.

use crate::crypto;

const SIGN_CN: &str = "Craft Signer";
const SIGN_O: &str = "Craft Org";

/// A v2 + v3 signing block carrying a real RSA signature over a real content digest.
fn real_signing_block(content_digest: &[u8; 32], tamper_sig: bool) -> Vec<u8> {
    let mut pairs = Vec::new();
    for (id, value) in [
        (0x7109_871au32, crypto::apk_rsa_signer(false, SIGN_CN, SIGN_O, content_digest, tamper_sig)),
        (0xf053_68c0, crypto::apk_rsa_signer(true, SIGN_CN, SIGN_O, content_digest, tamper_sig)),
        (0x4272_6577, vec![0; 12]),
    ] {
        pairs.extend(((value.len() + 4) as u64).to_le_bytes());
        pairs.extend(id.to_le_bytes());
        pairs.extend(value);
    }
    let size = (pairs.len() + 8 + 16) as u64;
    let mut out = size.to_le_bytes().to_vec();
    out.extend(pairs);
    out.extend(size.to_le_bytes());
    out.extend(b"APK Sig Block 42");
    out
}

/// Build the JAR (v1) `META-INF` files for `entries`: a MANIFEST.MF with per-file SHA-256 digests,
/// a CERT.SF with the whole-manifest digest, and a CERT.RSA (detached PKCS#7 over CERT.SF).
fn v1_files(entries: &[(&str, &[u8])]) -> Vec<(String, Vec<u8>)> {
    let mut mf = b"Manifest-Version: 1.0\r\nCreated-By: craft-anything-testkit\r\n\r\n".to_vec();
    for (name, body) in entries {
        mf.extend_from_slice(format!("Name: {name}\r\nSHA-256-Digest: {}\r\n\r\n", crypto::base64(&crypto::sha256(body))).as_bytes());
    }
    let sf =
        format!("Signature-Version: 1.0\r\nCreated-By: craft-anything-testkit\r\nSHA-256-Digest-Manifest: {}\r\n\r\n", crypto::base64(&crypto::sha256(&mf)))
            .into_bytes();
    let rsa = crypto::cms_detached_rsa(&sf, SIGN_CN, SIGN_O);
    vec![("META-INF/MANIFEST.MF".into(), mf), ("META-INF/CERT.SF".into(), sf), ("META-INF/CERT.RSA".into(), rsa)]
}

/// A fully-signed APK: a valid AndroidManifest, one DEX, resources, a real JAR (v1) signature and a
/// real v2/v3 signing block. With `tamper`, a content byte is flipped after signing so every
/// digest check must fail (the signatures themselves stay well-formed).
pub fn signed_apk(tamper: bool) -> Vec<u8> {
    let manifest = manifest_axml();
    let dex = notes_dex();
    let arsc = resources_arsc();
    let signed_entries: Vec<(&str, &[u8])> = vec![("AndroidManifest.xml", &manifest), ("classes.dex", &dex), ("resources.arsc", &arsc)];
    let v1 = v1_files(&signed_entries);
    let mut entries: Vec<(&str, &[u8])> = signed_entries.clone();
    for (n, b) in &v1 {
        entries.push((n.as_str(), b.as_slice()));
    }
    let zip = zip_stored(&entries);
    let eocd = zip.len() - 22;
    let cd_off = u32::from_le_bytes(zip[eocd + 16..eocd + 20].try_into().unwrap()) as usize;
    let digest = crypto::apk_content_digest_sha256(&zip, cd_off);
    let mut apk = with_signing_block(&zip, &real_signing_block(&digest, false));
    if tamper {
        // Flip a byte inside the first local-file entry (AndroidManifest data), breaking the
        // content digest (v2/v3) and the per-file digest (v1) without touching any signature.
        apk[60] ^= 0xff;
    }
    apk
}
