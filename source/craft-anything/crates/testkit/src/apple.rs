//! Synthetic Apple fixtures: property lists (XML and binary), keyed archives, NIB archives, a
//! compiled asset catalog (BOM), signed Mach-O files and an `.app` bundle with `@rpath`
//! frameworks.

use crate::Buf;

/// A property-list value for building fixtures.
#[derive(Debug, Clone, PartialEq)]
pub enum P {
    Dict(Vec<(String, P)>),
    Array(Vec<P>),
    Str(String),
    Int(i64),
    Real(f64),
    Bool(bool),
    /// Seconds since 2001-01-01.
    Date(f64),
    Data(Vec<u8>),
    Uid(u64),
}

pub fn s(v: &str) -> P {
    P::Str(v.to_string())
}

pub fn dict(items: Vec<(&str, P)>) -> P {
    P::Dict(items.into_iter().map(|(k, v)| (k.to_string(), v)).collect())
}

/// A small Info.plist-like dictionary exercising every value type.
pub fn sample_plist() -> P {
    dict(vec![
        ("CFBundleIdentifier", s("com.example.notes")),
        ("CFBundleExecutable", s("Notes")),
        ("Count", P::Int(-42)),
        ("Flag", P::Bool(true)),
        ("Pi", P::Real(3.5)),
        ("When", P::Date(86_400.0)),
        ("Blob", P::Data(vec![0, 1, 2])),
        ("Nested", dict(vec![("List", P::Array(vec![s("one"), s("two & <three>"), P::Int(3)]))])),
    ])
}

fn esc(t: &str) -> String {
    t.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}

fn b64(d: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for c in d.chunks(3) {
        let n = (u32::from(c[0]) << 16) | (u32::from(*c.get(1).unwrap_or(&0)) << 8) | u32::from(*c.get(2).unwrap_or(&0));
        out.push(T[(n >> 18) as usize & 63] as char);
        out.push(T[(n >> 12) as usize & 63] as char);
        out.push(if c.len() > 1 { T[(n >> 6) as usize & 63] as char } else { '=' });
        out.push(if c.len() > 2 { T[n as usize & 63] as char } else { '=' });
    }
    out
}

fn xml_value(v: &P, out: &mut String) {
    match v {
        P::Dict(d) => {
            out.push_str("<dict>\n");
            for (k, v) in d {
                out.push_str(&format!("<key>{}</key>", esc(k)));
                xml_value(v, out);
            }
            out.push_str("</dict>\n");
        }
        P::Array(a) => {
            out.push_str("<array>\n");
            for v in a {
                xml_value(v, out);
            }
            out.push_str("</array>\n");
        }
        P::Str(t) => out.push_str(&format!("<string>{}</string>\n", esc(t))),
        P::Int(i) => out.push_str(&format!("<integer>{i}</integer>\n")),
        P::Real(r) => out.push_str(&format!("<real>{r}</real>\n")),
        P::Bool(true) => out.push_str("<true/>\n"),
        P::Bool(false) => out.push_str("<false/>\n"),
        P::Date(_) => out.push_str("<date>2001-01-02T00:00:00Z</date>\n"),
        P::Data(d) => out.push_str(&format!("<data>{}</data>\n", b64(d))),
        P::Uid(u) => out.push_str(&format!("<dict><key>CF$UID</key><integer>{u}</integer></dict>\n")),
    }
}

/// An XML property list.
pub fn to_xml(v: &P) -> String {
    let mut out = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\">\n",
    );
    xml_value(v, &mut out);
    out.push_str("</plist>\n");
    out
}

fn count_marker(hi: u8, n: usize, out: &mut Vec<u8>) {
    if n < 15 {
        out.push((hi << 4) | n as u8);
    } else {
        out.push((hi << 4) | 0xf);
        out.push(0x12);
        out.extend_from_slice(&(n as u32).to_be_bytes());
    }
}

/// A binary (`bplist00`) property list. Objects are not deduplicated.
pub fn to_bplist(v: &P) -> Vec<u8> {
    // Flatten into an object list, children after parents.
    let mut objs: Vec<Vec<u8>> = Vec::new();
    fn add(v: &P, objs: &mut Vec<Vec<u8>>) -> usize {
        let idx = objs.len();
        objs.push(Vec::new());
        let mut out = Vec::new();
        match v {
            P::Dict(d) => {
                let keys: Vec<usize> = d.iter().map(|(k, _)| add(&P::Str(k.clone()), objs)).collect();
                let vals: Vec<usize> = d.iter().map(|(_, v)| add(v, objs)).collect();
                count_marker(0xd, d.len(), &mut out);
                for r in keys.iter().chain(vals.iter()) {
                    out.extend_from_slice(&(*r as u16).to_be_bytes());
                }
            }
            P::Array(a) => {
                let refs: Vec<usize> = a.iter().map(|v| add(v, objs)).collect();
                count_marker(0xa, a.len(), &mut out);
                for r in refs {
                    out.extend_from_slice(&(r as u16).to_be_bytes());
                }
            }
            P::Str(t) => {
                if t.is_ascii() {
                    count_marker(0x5, t.len(), &mut out);
                    out.extend_from_slice(t.as_bytes());
                } else {
                    let u: Vec<u16> = t.encode_utf16().collect();
                    count_marker(0x6, u.len(), &mut out);
                    for c in u {
                        out.extend_from_slice(&c.to_be_bytes());
                    }
                }
            }
            P::Int(i) => {
                out.push(0x13);
                out.extend_from_slice(&i.to_be_bytes());
            }
            P::Real(r) => {
                out.push(0x23);
                out.extend_from_slice(&r.to_bits().to_be_bytes());
            }
            P::Bool(b) => out.push(if *b { 0x09 } else { 0x08 }),
            P::Date(d) => {
                out.push(0x33);
                out.extend_from_slice(&d.to_bits().to_be_bytes());
            }
            P::Data(d) => {
                count_marker(0x4, d.len(), &mut out);
                out.extend_from_slice(d);
            }
            P::Uid(u) => {
                out.push(0x83);
                out.extend_from_slice(&(*u as u32).to_be_bytes());
            }
        }
        objs[idx] = out;
        idx
    }
    add(v, &mut objs);
    let mut out = b"bplist00".to_vec();
    let mut offsets = Vec::new();
    for o in &objs {
        offsets.push(out.len() as u32);
        out.extend_from_slice(o);
    }
    let table = out.len();
    for o in &offsets {
        out.extend_from_slice(&o.to_be_bytes());
    }
    out.extend_from_slice(&[0, 0, 0, 0, 0, 0, 4, 2]);
    out.extend_from_slice(&(objs.len() as u64).to_be_bytes());
    out.extend_from_slice(&0u64.to_be_bytes());
    out.extend_from_slice(&(table as u64).to_be_bytes());
    out
}

fn class_entry(name: &str) -> P {
    dict(vec![("$classname", s(name)), ("$classes", P::Array(vec![s(name), s("NSObject")]))])
}

/// A keyed archive: a `NoteDocument` with a title, an `NSArray` of tags and a reference to itself.
pub fn keyed_archive_value() -> P {
    dict(vec![
        ("$version", P::Int(100_000)),
        ("$archiver", s("NSKeyedArchiver")),
        ("$top", dict(vec![("root", P::Uid(1))])),
        (
            "$objects",
            P::Array(vec![
                s("$null"),
                dict(vec![("title", P::Uid(2)), ("tags", P::Uid(3)), ("owner", P::Uid(1)), ("count", P::Int(2)), ("$class", P::Uid(7))]),
                s("Groceries"),
                dict(vec![("NS.objects", P::Array(vec![P::Uid(4), P::Uid(5)])), ("$class", P::Uid(6))]),
                s("food"),
                s("weekly"),
                class_entry("NSArray"),
                class_entry("NoteDocument"),
            ]),
        ),
    ])
}

/// [`keyed_archive_value`] as a binary plist.
pub fn keyed_archive() -> Vec<u8> {
    to_bplist(&keyed_archive_value())
}

/// A value in a NIB archive fixture.
#[derive(Debug, Clone)]
pub enum NV {
    Obj(u32),
    Bytes(Vec<u8>),
    Int(i64),
    Bool(bool),
    F64(f64),
    Nil,
}

fn nib_varint(mut v: u64, out: &mut Vec<u8>) {
    loop {
        let b = (v & 0x7f) as u8;
        v >>= 7;
        if v == 0 {
            out.push(b | 0x80);
            return;
        }
        out.push(b);
    }
}

/// Write a `NIBArchive` from (class, values) objects.
pub fn nib_write(objects: &[(&str, Vec<(&str, NV)>)]) -> Vec<u8> {
    let mut keys: Vec<String> = Vec::new();
    let mut classes: Vec<String> = Vec::new();
    let mut objs = Vec::new();
    let mut vals = Vec::new();
    let mut nvals = 0u64;
    for (class, values) in objects {
        let ci = classes.iter().position(|c| c == class).unwrap_or_else(|| {
            classes.push(class.to_string());
            classes.len() - 1
        });
        nib_varint(ci as u64, &mut objs);
        nib_varint(nvals, &mut objs);
        nib_varint(values.len() as u64, &mut objs);
        for (k, v) in values {
            let ki = keys.iter().position(|x| x == k).unwrap_or_else(|| {
                keys.push(k.to_string());
                keys.len() - 1
            });
            nib_varint(ki as u64, &mut vals);
            match v {
                NV::Obj(o) => {
                    vals.push(10);
                    vals.extend_from_slice(&o.to_le_bytes());
                }
                NV::Bytes(b) => {
                    vals.push(8);
                    nib_varint(b.len() as u64, &mut vals);
                    vals.extend_from_slice(b);
                }
                NV::Int(i) => {
                    vals.push(3);
                    vals.extend_from_slice(&i.to_le_bytes());
                }
                NV::Bool(b) => vals.push(if *b { 4 } else { 5 }),
                NV::F64(f) => {
                    vals.push(7);
                    vals.extend_from_slice(&f.to_bits().to_le_bytes());
                }
                NV::Nil => vals.push(9),
            }
            nvals += 1;
        }
    }
    let mut kbytes = Vec::new();
    for k in &keys {
        nib_varint(k.len() as u64, &mut kbytes);
        kbytes.extend_from_slice(k.as_bytes());
    }
    let mut cbytes = Vec::new();
    for c in &classes {
        nib_varint(c.len() as u64 + 1, &mut cbytes);
        nib_varint(0, &mut cbytes);
        cbytes.extend_from_slice(c.as_bytes());
        cbytes.push(0);
    }
    let header = 50usize;
    let o_obj = header;
    let o_key = o_obj + objs.len();
    let o_val = o_key + kbytes.len();
    let o_cls = o_val + vals.len();
    let mut out = b"NIBArchive".to_vec();
    for v in [1u32, 10, objects.len() as u32, o_obj as u32, keys.len() as u32, o_key as u32, nvals as u32, o_val as u32, classes.len() as u32, o_cls as u32] {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out.extend(objs);
    out.extend(kbytes);
    out.extend(vals);
    out.extend(cbytes);
    out
}

fn bytes(t: &str) -> NV {
    NV::Bytes(t.as_bytes().to_vec())
}

/// A compiled view nib: a `UIView` with a `UILabel` and a `UIButton`, an outlet `titleLabel`
/// (owner → label) and an action `save:` (button → owner).
pub fn nib_archive() -> Vec<u8> {
    nib_write(&[
        ("NSObject", vec![("UINibTopLevelObjectsKey", NV::Obj(1)), ("UINibConnectionsKey", NV::Obj(8))]),
        ("NSArray", vec![("UINibEncoderEmptyKey", NV::Obj(2)), ("UINibEncoderEmptyKey", NV::Obj(9))]),
        ("UIView", vec![("UISubviews", NV::Obj(3)), ("UIOpaque", NV::Bool(true)), ("UIAlpha", NV::F64(1.0))]),
        ("NSArray", vec![("UINibEncoderEmptyKey", NV::Obj(4)), ("UINibEncoderEmptyKey", NV::Obj(5))]),
        ("UILabel", vec![("UIText", NV::Obj(6)), ("UITag", NV::Int(7))]),
        ("UIButton", vec![("UIEnabled", NV::Bool(true)), ("UINil", NV::Nil)]),
        ("NSString", vec![("NS.bytes", bytes("Hello"))]),
        ("NSString", vec![("NS.bytes", bytes("titleLabel"))]),
        ("NSArray", vec![("UINibEncoderEmptyKey", NV::Obj(10)), ("UINibEncoderEmptyKey", NV::Obj(11))]),
        ("UIProxyObject", vec![("UIProxiedObjectIdentifier", NV::Obj(12))]),
        ("UIRuntimeOutletConnection", vec![("UILabel", NV::Obj(7)), ("UISource", NV::Obj(9)), ("UIDestination", NV::Obj(4))]),
        ("UIRuntimeEventConnection", vec![("UILabel", NV::Obj(13)), ("UISource", NV::Obj(5)), ("UIDestination", NV::Obj(9)), ("UIEventMask", NV::Int(64))]),
        ("NSString", vec![("NS.bytes", bytes("IBFilesOwner"))]),
        ("NSString", vec![("NS.bytes", bytes("save:"))]),
    ])
}

/// A keyed-archive nib with one outlet connector (`window`: owner → NSWindow).
pub fn keyed_nib() -> Vec<u8> {
    to_bplist(&dict(vec![
        ("$version", P::Int(100_000)),
        ("$archiver", s("NSKeyedArchiver")),
        ("$top", dict(vec![("IB.objectdata", P::Uid(1))])),
        (
            "$objects",
            P::Array(vec![
                s("$null"),
                dict(vec![("NSConnections", P::Uid(2)), ("$class", P::Uid(8))]),
                dict(vec![("NS.objects", P::Array(vec![P::Uid(3)])), ("$class", P::Uid(9))]),
                dict(vec![("NSLabel", P::Uid(4)), ("NSSource", P::Uid(5)), ("NSDestination", P::Uid(6)), ("$class", P::Uid(10))]),
                s("window"),
                dict(vec![("NSClassName", P::Uid(7)), ("$class", P::Uid(11))]),
                dict(vec![("NSWindowTitle", P::Uid(7)), ("$class", P::Uid(12))]),
                s("AppDelegate"),
                class_entry("NSIBObjectData"),
                class_entry("NSMutableArray"),
                class_entry("NSNibOutletConnector"),
                class_entry("NSCustomObject"),
                class_entry("NSWindow"),
            ]),
        ),
    ]))
}

// ---------------------------------------------------------------------------------------------
// Mach-O load commands and code signatures

fn pad8(v: &mut Vec<u8>) {
    while v.len() % 8 != 0 {
        v.push(0);
    }
}

fn finish_cmd(mut v: Vec<u8>) -> Vec<u8> {
    pad8(&mut v);
    let n = v.len() as u32;
    v[4..8].copy_from_slice(&n.to_le_bytes());
    v
}

/// A dylib load command (`LC_LOAD_DYLIB` 0xc, `LC_ID_DYLIB` 0xd, `LC_LOAD_WEAK_DYLIB` 0x80000018…).
pub fn lc_dylib(cmd: u32, name: &str) -> Vec<u8> {
    let mut v = Vec::new();
    v.extend_from_slice(&cmd.to_le_bytes());
    v.extend_from_slice(&0u32.to_le_bytes());
    v.extend_from_slice(&24u32.to_le_bytes());
    v.extend_from_slice(&2u32.to_le_bytes());
    v.extend_from_slice(&0x0001_0203u32.to_le_bytes());
    v.extend_from_slice(&0x0001_0000u32.to_le_bytes());
    v.extend_from_slice(name.as_bytes());
    v.push(0);
    finish_cmd(v)
}

pub fn lc_rpath(path: &str) -> Vec<u8> {
    let mut v = Vec::new();
    v.extend_from_slice(&0x8000_001cu32.to_le_bytes());
    v.extend_from_slice(&0u32.to_le_bytes());
    v.extend_from_slice(&12u32.to_le_bytes());
    v.extend_from_slice(path.as_bytes());
    v.push(0);
    finish_cmd(v)
}

pub fn lc_uuid() -> Vec<u8> {
    let mut v = vec![0x1b, 0, 0, 0, 24, 0, 0, 0];
    v.extend_from_slice(&[0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff]);
    v
}

/// `LC_BUILD_VERSION`: macOS 13.0, SDK 14.0, one tool (ld 907.0).
pub fn lc_build_version() -> Vec<u8> {
    let mut v = Vec::new();
    for x in [0x32u32, 32, 1, 0x000d_0000, 0x000e_0000, 1, 3, 0x038b_0000] {
        v.extend_from_slice(&x.to_le_bytes());
    }
    v
}

fn requirement_expr() -> Vec<u8> {
    fn data(v: &mut Vec<u8>, d: &[u8]) {
        v.extend_from_slice(&(d.len() as u32).to_be_bytes());
        v.extend_from_slice(d);
        while v.len() % 4 != 0 {
            v.push(0);
        }
    }
    let mut e = Vec::new();
    let op = |e: &mut Vec<u8>, o: u32| e.extend_from_slice(&o.to_be_bytes());
    op(&mut e, 6); // and
    op(&mut e, 2); // identifier
    data(&mut e, b"com.example.notes");
    op(&mut e, 6);
    op(&mut e, 15); // anchor apple generic
    op(&mut e, 6);
    op(&mut e, 14); // certificate generic
    e.extend_from_slice(&1i32.to_be_bytes());
    data(&mut e, &[0x2a, 0x86, 0x48, 0x86, 0xf7, 0x63, 0x64, 0x06, 0x02, 0x06]);
    op(&mut e, 0); // exists
    op(&mut e, 11); // certificate field
    e.extend_from_slice(&0i32.to_be_bytes());
    data(&mut e, b"subject.OU");
    op(&mut e, 1); // equal
    data(&mut e, b"ABCDE12345");
    e
}

fn be(v: &mut Vec<u8>, x: u32) {
    v.extend_from_slice(&x.to_be_bytes());
}

/// A code-signature superblob: code directory (sha256, runtime, team ABCDE12345, identifier
/// com.example.notes), a designated requirement, entitlements and a 4-byte CMS blob.
/// The primary CodeDirectory blob (magic `0xfade0c02`): sha256 hashes, identifier
/// `com.example.notes`, team `ABCDE12345`, the hardened-runtime flag, one non-zero special slot
/// and one code-page hash.
pub fn code_directory_blob() -> Vec<u8> {
    let ident = b"com.example.notes\0";
    let team = b"ABCDE12345\0";
    let header = 96usize;
    let ident_off = header;
    let team_off = ident_off + ident.len();
    let nspecial = 5usize;
    let hash_off = team_off + team.len() + nspecial * 32;
    let mut cd = Vec::new();
    for x in [0xfade_0c02u32, 0, 0x20500, 0x1_0000, hash_off as u32, ident_off as u32, nspecial as u32, 1, 0x1000] {
        be(&mut cd, x);
    }
    cd.extend_from_slice(&[32, 2, 0, 12]);
    be(&mut cd, 0); // spare2
    be(&mut cd, 0); // scatter
    be(&mut cd, team_off as u32);
    be(&mut cd, 0); // spare3
    cd.extend_from_slice(&0u64.to_be_bytes()); // codeLimit64
    cd.extend_from_slice(&0u64.to_be_bytes()); // execSegBase
    cd.extend_from_slice(&0x1000u64.to_be_bytes());
    cd.extend_from_slice(&1u64.to_be_bytes());
    be(&mut cd, 0x000d_0000); // runtime
    be(&mut cd, 0);
    assert_eq!(cd.len(), header);
    cd.extend_from_slice(ident);
    cd.extend_from_slice(team);
    // special slots -5..-1: only -5 (entitlements) non-zero
    let mut special = vec![0u8; nspecial * 32];
    special[..32].fill(0xee);
    cd.extend_from_slice(&special);
    cd.extend_from_slice(&[0xab; 32]);
    let n = cd.len() as u32;
    cd[4..8].copy_from_slice(&n.to_be_bytes());
    cd
}

pub fn code_signature_blob() -> Vec<u8> {
    let cd = code_directory_blob();
    // Requirements.
    let expr = requirement_expr();
    let mut req = Vec::new();
    be(&mut req, 0xfade_0c00);
    be(&mut req, (12 + expr.len()) as u32);
    be(&mut req, 1);
    req.extend_from_slice(&expr);
    let mut reqs = Vec::new();
    be(&mut reqs, 0xfade_0c01);
    be(&mut reqs, (20 + req.len()) as u32);
    be(&mut reqs, 1);
    be(&mut reqs, 3);
    be(&mut reqs, 20);
    reqs.extend_from_slice(&req);
    // Entitlements.
    let xml = to_xml(&dict(vec![("com.apple.security.app-sandbox", P::Bool(true)), ("com.apple.security.network.client", P::Bool(true))]));
    let mut ents = Vec::new();
    be(&mut ents, 0xfade_7171);
    be(&mut ents, (8 + xml.len()) as u32);
    ents.extend_from_slice(xml.as_bytes());
    let mut cms = Vec::new();
    be(&mut cms, 0xfade_0b01);
    be(&mut cms, 12);
    cms.extend_from_slice(&[0x30, 0x80, 0, 0]);
    assemble_superblob(&[(0u32, cd), (2, reqs), (5, ents), (0x10000, cms)])
}

/// Assemble a code-signature superblob (`0xfade0cc0`) from `(slot, blob)` pairs.
pub fn assemble_superblob(blobs: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut off = 12 + 8 * blobs.len();
    let mut sb = Vec::new();
    be(&mut sb, 0xfade_0cc0);
    be(&mut sb, 0);
    be(&mut sb, blobs.len() as u32);
    for (slot, b) in blobs {
        be(&mut sb, *slot);
        be(&mut sb, off as u32);
        off += b.len();
    }
    for (_, b) in blobs {
        sb.extend_from_slice(b);
    }
    let n = sb.len() as u32;
    sb[4..8].copy_from_slice(&n.to_be_bytes());
    sb
}

/// A code-signature superblob whose CMS (`BlobWrapper`, slot `0x10000`) carries a genuine detached
/// PKCS#7 over the CodeDirectory, signed by the self-signed RSA key in [`crate::crypto`]. Returns
/// the superblob; the embedded CMS verifies against the CodeDirectory round-trip.
pub fn code_signature_blob_cms() -> Vec<u8> {
    let cd = code_directory_blob();
    let cms_der = crate::crypto::cms_detached_rsa(&cd, "Craft Signer", "Craft Org");
    let mut cms = Vec::new();
    be(&mut cms, 0xfade_0b01);
    be(&mut cms, (8 + cms_der.len()) as u32);
    cms.extend_from_slice(&cms_der);
    assemble_superblob(&[(0u32, cd), (0x10000, cms)])
}

/// A 64-bit Mach-O with an `LC_CODE_SIGNATURE` pointing at [`code_signature_blob_cms`]: a real,
/// CMS-signed code signature that verifies cryptographically against its CodeDirectory.
pub fn macho_cms_signed() -> Vec<u8> {
    let mut m = crate::macho64();
    while m.len() % 16 != 0 {
        m.push(0);
    }
    let sig_off = m.len();
    let sig = code_signature_blob_cms();
    let mut cs = vec![0x1d, 0, 0, 0, 16, 0, 0, 0];
    cs.extend_from_slice(&(sig_off as u32).to_le_bytes());
    cs.extend_from_slice(&(sig.len() as u32).to_le_bytes());
    let mut m = add_load_commands(m, &[lc_uuid(), lc_build_version(), cs]);
    m.extend_from_slice(&sig);
    m
}

/// Append load commands to a 64-bit Mach-O (there must be room before its first section data).
pub fn add_load_commands(mut m: Vec<u8>, cmds: &[Vec<u8>]) -> Vec<u8> {
    let ncmds = u32::from_le_bytes(m[16..20].try_into().unwrap());
    let size = u32::from_le_bytes(m[20..24].try_into().unwrap()) as usize;
    let mut pos = 32 + size;
    for c in cmds {
        m[pos..pos + c.len()].copy_from_slice(c);
        pos += c.len();
    }
    m[16..20].copy_from_slice(&(ncmds + cmds.len() as u32).to_le_bytes());
    m[20..24].copy_from_slice(&((pos - 32) as u32).to_le_bytes());
    m
}

/// [`crate::macho64`] with a UUID, build version, run path, a weak `@rpath` framework and an
/// `LC_CODE_SIGNATURE` pointing at [`code_signature_blob`] appended to the file.
pub fn macho_signed() -> Vec<u8> {
    let mut m = crate::macho64();
    while m.len() % 16 != 0 {
        m.push(0);
    }
    let sig_off = m.len();
    let sig = code_signature_blob();
    let mut cs = vec![0x1d, 0, 0, 0, 16, 0, 0, 0];
    cs.extend_from_slice(&(sig_off as u32).to_le_bytes());
    cs.extend_from_slice(&(sig.len() as u32).to_le_bytes());
    let mut m = add_load_commands(
        m,
        &[lc_uuid(), lc_build_version(), lc_rpath("@executable_path/../Frameworks"), lc_dylib(0x8000_0018, "@rpath/Extras.framework/Extras"), cs],
    );
    m.extend_from_slice(&sig);
    m
}

/// A minimal 64-bit Mach-O: header, the given load commands, and optionally one `__TEXT` segment
/// whose sections hold the given bytes.
pub fn macho_min(cputype: u32, filetype: u32, cmds: &[Vec<u8>], sections: &[(&str, &[u8])]) -> Vec<u8> {
    let mut all: Vec<Vec<u8>> = cmds.to_vec();
    let seg_size = 72 + 80 * sections.len();
    let cmds_size: usize = all.iter().map(Vec::len).sum::<usize>() + if sections.is_empty() { 0 } else { seg_size };
    let mut data_off = (32 + cmds_size + 15) & !15;
    if !sections.is_empty() {
        let mut seg = Buf::with_len(seg_size);
        seg.u32(0, 0x19);
        seg.u32(4, seg_size as u32);
        seg.put(8, b"__TEXT");
        seg.u64(24, 0x1_0000_0000);
        seg.u64(32, 0x4000);
        seg.u64(48, 0x4000);
        seg.u32(56, 5);
        seg.u32(60, 5);
        seg.u32(64, sections.len() as u32);
        for (i, (name, bytes)) in sections.iter().enumerate() {
            let o = 72 + i * 80;
            seg.put(o, name.as_bytes());
            seg.put(o + 16, b"__TEXT");
            seg.u64(o + 32, 0x1_0000_0000 + data_off as u64);
            seg.u64(o + 40, bytes.len() as u64);
            seg.u32(o + 48, data_off as u32);
            data_off = (data_off + bytes.len() + 15) & !15;
        }
        all.insert(0, seg.into_vec());
    }
    let mut b = Buf::default();
    b.u32(0, 0xfeed_facf);
    b.u32(4, cputype);
    b.u32(8, 0);
    b.u32(12, filetype);
    b.u32(16, all.len() as u32);
    b.u32(20, cmds_size as u32);
    b.u32(24, 0x0020_0085);
    let mut pos = 32;
    for c in &all {
        b.put(pos, c);
        pos += c.len();
    }
    let mut off = (32 + cmds_size + 15) & !15;
    for (_, bytes) in sections {
        b.put(off, bytes);
        off = (off + bytes.len() + 15) & !15;
    }
    if b.0.len() < 64 {
        b.0.resize(64, 0);
    }
    b.into_vec()
}

pub const CPU_ARM64: u32 = 0x0100_000c;
pub const CPU_X86_64: u32 = 0x0100_0007;

/// A thin arm64 executable with an embedded `__TEXT,__info_plist`.
pub fn macho_with_info_plist() -> Vec<u8> {
    let plist = to_xml(&sample_plist());
    macho_min(CPU_ARM64, 2, &[lc_dylib(0xc, "/usr/lib/libSystem.B.dylib")], &[("__info_plist", plist.as_bytes())])
}

/// A universal binary: [`crate::macho64`] (x86_64) and an arm64 executable.
pub fn macho_universal() -> Vec<u8> {
    crate::macho_fat(&[crate::macho64(), macho_min(CPU_ARM64, 2, &[lc_dylib(0xc, "/usr/lib/libSystem.B.dylib")], &[])])
}

// ---------------------------------------------------------------------------------------------
// Asset catalogs (BOM)

/// Builds a BOM store: numbered blocks plus named variables.
#[derive(Debug, Default)]
pub struct BomWriter {
    blocks: Vec<Vec<u8>>,
    vars: Vec<(String, u32)>,
}

impl BomWriter {
    pub fn new() -> Self {
        BomWriter { blocks: vec![Vec::new()], vars: Vec::new() }
    }
    pub fn block(&mut self, b: Vec<u8>) -> u32 {
        self.blocks.push(b);
        (self.blocks.len() - 1) as u32
    }
    pub fn var(&mut self, name: &str, b: Vec<u8>) -> u32 {
        let id = self.block(b);
        self.vars.push((name.to_string(), id));
        id
    }
    /// A one-leaf tree holding (key, value) pairs.
    pub fn tree(&mut self, name: &str, entries: Vec<(Vec<u8>, Vec<u8>)>) {
        let mut leaf = Vec::new();
        leaf.extend_from_slice(&1u16.to_be_bytes());
        leaf.extend_from_slice(&(entries.len() as u16).to_be_bytes());
        leaf.extend_from_slice(&0u32.to_be_bytes());
        leaf.extend_from_slice(&0u32.to_be_bytes());
        let mut ids = Vec::new();
        for (k, v) in entries {
            let vi = self.block(v);
            let ki = self.block(k);
            ids.push((vi, ki));
        }
        for (vi, ki) in ids {
            leaf.extend_from_slice(&vi.to_be_bytes());
            leaf.extend_from_slice(&ki.to_be_bytes());
        }
        let leaf_id = self.block(leaf);
        let mut t = b"tree".to_vec();
        for x in [1u32, leaf_id, 4096, 0] {
            t.extend_from_slice(&x.to_be_bytes());
        }
        t.push(0);
        self.var(name, t);
    }
    pub fn finish(self) -> Vec<u8> {
        let mut out = vec![0u8; 512];
        let mut addrs = Vec::new();
        for b in &self.blocks {
            addrs.push((out.len() as u32, b.len() as u32));
            out.extend_from_slice(b);
        }
        let index_off = out.len();
        out.extend_from_slice(&(addrs.len() as u32).to_be_bytes());
        for (a, l) in &addrs {
            out.extend_from_slice(&a.to_be_bytes());
            out.extend_from_slice(&l.to_be_bytes());
        }
        let index_len = out.len() - index_off;
        let vars_off = out.len();
        out.extend_from_slice(&(self.vars.len() as u32).to_be_bytes());
        for (n, id) in &self.vars {
            out.extend_from_slice(&id.to_be_bytes());
            out.push(n.len() as u8);
            out.extend_from_slice(n.as_bytes());
        }
        let vars_len = out.len() - vars_off;
        out[..8].copy_from_slice(b"BOMStore");
        for (i, x) in [1u32, addrs.len() as u32, index_off as u32, index_len as u32, vars_off as u32, vars_len as u32].iter().enumerate() {
            out[8 + i * 4..12 + i * 4].copy_from_slice(&x.to_be_bytes());
        }
        out
    }
}

fn csi(name: &str, w: u32, h: u32, scale: u32, fmt: &[u8; 4], layout: u16) -> Vec<u8> {
    let mut b = Buf::with_len(184);
    b.put(0, b"ISTC");
    b.u32(4, 1);
    b.u32(8, 0);
    b.u32(12, w);
    b.u32(16, h);
    b.u32(20, scale);
    b.u32(24, u32::from_be_bytes(*fmt));
    b.u32(28, 1);
    b.u32(32, 0);
    b.u16(36, layout);
    b.put(40, name.as_bytes());
    b.u32(180, 0);
    b.into_vec()
}

/// A minimal `Assets.car`: CAR header, key format (scale, idiom, identifier), facets AppIcon and
/// Logo, and one rendition for each.
pub fn assets_car() -> Vec<u8> {
    let mut w = BomWriter::new();
    let mut hdr = Buf::with_len(436);
    hdr.put(0, b"RATC");
    hdr.u32(4, 975);
    hdr.u32(8, 17);
    hdr.u32(12, 1_700_000_000);
    hdr.u32(16, 2);
    hdr.put(20, b"@(#)PROGRAM:CoreUI  PROJECT:CoreUI-1");
    hdr.put(148, b"IBCocoaTouchImageCatalogTool-1");
    hdr.u32(424, 2);
    w.var("CARHEADER", hdr.into_vec());
    let mut kf = Buf::with_len(24);
    kf.put(0, b"tmfk");
    kf.u32(8, 3);
    kf.u32(12, 12);
    kf.u32(16, 15);
    kf.u32(20, 17);
    w.var("KEYFORMAT", kf.into_vec());
    let facet = |id: u16| {
        let mut b = Buf::with_len(10);
        b.u16(4, 1);
        b.u16(6, 17);
        b.u16(8, id);
        b.into_vec()
    };
    w.tree("FACETKEYS", vec![(b"AppIcon".to_vec(), facet(1001)), (b"Logo".to_vec(), facet(1002))]);
    let key = |scale: u16, ident: u16| {
        let mut b = Buf::with_len(6);
        b.u16(0, scale);
        b.u16(2, 0);
        b.u16(4, ident);
        b.into_vec()
    };
    w.tree("RENDITIONS", vec![(key(1, 1001), csi("AppIcon.png", 16, 16, 100, b"JPEG", 10)), (key(2, 1002), csi("Logo@2x.png", 64, 32, 200, b"ARGB", 10))]);
    w.finish()
}

// ---------------------------------------------------------------------------------------------
// App bundle

fn write(p: &std::path::Path, bytes: &[u8]) {
    std::fs::create_dir_all(p.parent().unwrap()).unwrap();
    std::fs::write(p, bytes).unwrap();
}

/// Write `Notes.app` under `root` and return its path. The executable searches two run paths
/// (the first is absent), links a framework through `@rpath`, a missing library, a missing weak
/// library and (on Unix) a symbolic link that escapes the bundle. The framework links `Bar.dylib`
/// twice (through `@rpath` and `@loader_path`). A plug-in bundle links through
/// `@executable_path`; `Unused.dylib` is never loaded.
pub fn write_app_bundle(root: &std::path::Path) -> std::path::PathBuf {
    let app = root.join("Notes.app");
    let c = app.join("Contents");
    write(&c.join("Info.plist"), to_xml(&dict(vec![("CFBundleExecutable", s("Notes")), ("CFBundleIdentifier", s("com.example.notes"))])).as_bytes());
    let exe = macho_min(
        CPU_ARM64,
        2,
        &[
            lc_rpath("@executable_path/../Missing"),
            lc_rpath("@executable_path/../Frameworks"),
            lc_dylib(0xc, "/usr/lib/libSystem.B.dylib"),
            lc_dylib(0xc, "@rpath/Foo.framework/Versions/A/Foo"),
            lc_dylib(0xc, "@rpath/Gone.dylib"),
            lc_dylib(0x8000_0018, "@rpath/Optional.dylib"),
            lc_dylib(0xc, "@rpath/Evil.dylib"),
        ],
        &[],
    );
    write(&c.join("MacOS/Notes"), &exe);
    let framework = macho_min(
        CPU_ARM64,
        6,
        &[
            lc_dylib(0xd, "@rpath/Foo.framework/Versions/A/Foo"),
            lc_rpath("@loader_path/../../.."),
            lc_dylib(0xc, "@rpath/Bar.dylib"),
            lc_dylib(0xc, "@loader_path/../../../Bar.dylib"),
            lc_dylib(0xc, "/System/Library/Frameworks/Foundation.framework/Versions/C/Foundation"),
        ],
        &[],
    );
    write(&c.join("Frameworks/Foo.framework/Versions/A/Foo"), &framework);
    let bar = macho_min(CPU_ARM64, 6, &[lc_dylib(0xd, "@rpath/Bar.dylib"), lc_dylib(0xc, "/usr/lib/libSystem.B.dylib")], &[]);
    write(&c.join("Frameworks/Bar.dylib"), &bar);
    let unused = macho_min(CPU_ARM64, 6, &[lc_dylib(0xd, "@rpath/Unused.dylib")], &[]);
    write(&c.join("Frameworks/Unused.dylib"), &unused);
    let plugin = macho_min(CPU_ARM64, 8, &[lc_dylib(0xc, "@executable_path/../Frameworks/Bar.dylib")], &[]);
    write(&c.join("PlugIns/Helper.bundle/Contents/MacOS/Helper"), &plugin);
    write(&c.join("Resources/readme.txt"), b"not a program");
    #[cfg(unix)]
    {
        let outside = root.join("outside.dylib");
        write(&outside, &unused);
        std::os::unix::fs::symlink(&outside, c.join("Frameworks/Evil.dylib")).unwrap();
    }
    app
}
