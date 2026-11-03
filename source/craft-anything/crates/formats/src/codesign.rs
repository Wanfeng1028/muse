//! Code-signature superblobs (the data `LC_CODE_SIGNATURE` points at): code directories with
//! their identity, flags, slot counts and cdhash; requirement sets decoded to readable requirement
//! text; entitlements (XML plist and DER); and the CMS signature wrapper. Nothing here verifies a
//! signature cryptographically.

use crate::FormatError;
use crate::bytes::Reader;
use crate::plist;
use serde::Serialize;
use serde_json::Value as Json;
use sha2::Digest as _;

const SUPERBLOB: u32 = 0xfade_0cc0;
const CODEDIRECTORY: u32 = 0xfade_0c02;
const REQUIREMENTS: u32 = 0xfade_0c01;
const REQUIREMENT: u32 = 0xfade_0c00;
const ENTITLEMENTS: u32 = 0xfade_7171;
const DER_ENTITLEMENTS: u32 = 0xfade_7172;
const BLOBWRAPPER: u32 = 0xfade_0b01;
const MAX_BLOBS: usize = 64;
const MAX_EXPR_DEPTH: usize = 64;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CodeDirectory {
    pub slot: u32,
    pub offset: usize,
    pub length: u32,
    pub version: String,
    pub flags: u32,
    pub flag_names: Vec<&'static str>,
    pub identifier: Option<String>,
    pub team_id: Option<String>,
    pub hash_type: String,
    pub hash_size: u8,
    /// Offset of code slot 0's hash inside the code directory.
    pub hash_offset: u32,
    pub platform: u8,
    pub page_size: u64,
    pub special_slots: u32,
    pub code_slots: u32,
    pub code_limit: u64,
    pub exec_segment: Option<Json>,
    pub runtime_version: Option<String>,
    /// The cdhash: the code directory hashed with its own hash type, truncated to 20 bytes.
    pub cdhash: Option<String>,
    /// The full digest, hex.
    pub cd_digest: Option<String>,
    /// Hashes of special slots that are present (non-zero): slot number → hex.
    pub special_hashes: Vec<(i64, String)>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Requirement {
    /// host, guest, designated, library, plugin
    pub kind: String,
    pub text: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct BlobIndex {
    pub slot: u32,
    pub slot_name: String,
    pub magic: String,
    pub offset: u32,
    pub length: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Signature {
    pub length: u32,
    pub blobs: Vec<BlobIndex>,
    pub code_directories: Vec<CodeDirectory>,
    pub requirements: Vec<Requirement>,
    /// Entitlements XML as normalised JSON.
    pub entitlements: Option<Json>,
    pub entitlements_xml: Option<String>,
    pub der_entitlements_bytes: Option<usize>,
    pub cms_signature_bytes: Option<usize>,
    /// True when the CMS blob is empty or absent (ad-hoc signing).
    pub ad_hoc: bool,
    pub warnings: Vec<String>,
}

fn slot_name(s: u32) -> String {
    match s {
        0 => "CodeDirectory".into(),
        1 => "Info.plist".into(),
        2 => "Requirements".into(),
        3 => "ResourceDirectory".into(),
        4 => "Application".into(),
        5 => "Entitlements".into(),
        7 => "DER Entitlements".into(),
        0x1000..=0x1004 => format!("Alternate CodeDirectory {}", s - 0x1000),
        0x10000 => "CMS Signature".into(),
        other => format!("slot {other:#x}"),
    }
}

const CD_FLAGS: &[(u32, &str)] = &[
    (0x1, "host"),
    (0x2, "adhoc"),
    (0x4, "force-hard"),
    (0x8, "force-kill"),
    (0x10, "force-expiration"),
    (0x20, "restrict"),
    (0x40, "enforcement"),
    (0x80, "library-validation"),
    (0x200, "allowed-entitlements"),
    (0x800, "installer"),
    (0x1_0000, "runtime"),
    (0x2_0000, "linker-signed"),
];

fn hash_name(t: u8) -> &'static str {
    match t {
        1 => "sha1",
        2 => "sha256",
        3 => "sha256-truncated",
        4 => "sha384",
        _ => "unknown",
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// SHA-1 (only for cdhashes of legacy code directories).
pub fn sha1(data: &[u8]) -> [u8; 20] {
    let mut h: [u32; 5] = [0x6745_2301, 0xefcd_ab89, 0x98ba_dcfe, 0x1032_5476, 0xc3d2_e1f0];
    let bit_len = (data.len() as u64).wrapping_mul(8);
    let mut msg = data.to_vec();
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());
    for chunk in msg.as_chunks::<64>().0 {
        let mut w = [0u32; 80];
        for (i, word) in chunk.as_chunks::<4>().0.iter().enumerate() {
            if let Some(slot) = w.get_mut(i) {
                *slot = u32::from_be_bytes(*word);
            }
        }
        for i in 16..80 {
            let v = (w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]).rotate_left(1);
            w[i] = v;
        }
        let [mut a, mut b, mut c, mut d, mut e] = h;
        for (i, wi) in w.iter().enumerate() {
            let (f, k) = match i {
                0..=19 => ((b & c) | (!b & d), 0x5a82_7999),
                20..=39 => (b ^ c ^ d, 0x6ed9_eba1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1b_bcdc),
                _ => (b ^ c ^ d, 0xca62_c1d6),
            };
            let t = a.rotate_left(5).wrapping_add(f).wrapping_add(e).wrapping_add(k).wrapping_add(*wi);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = t;
        }
        h = [h[0].wrapping_add(a), h[1].wrapping_add(b), h[2].wrapping_add(c), h[3].wrapping_add(d), h[4].wrapping_add(e)];
    }
    let mut out = [0u8; 20];
    for (i, v) in h.iter().enumerate() {
        if let Some(dst) = out.get_mut(i * 4..i * 4 + 4) {
            dst.copy_from_slice(&v.to_be_bytes());
        }
    }
    out
}

fn digest(t: u8, data: &[u8]) -> Option<Vec<u8>> {
    match t {
        1 => Some(sha1(data).to_vec()),
        2 | 3 => Some(sha2::Sha256::digest(data).to_vec()),
        4 => Some(sha2::Sha384::digest(data).to_vec()),
        _ => None,
    }
}

/// Parse a code-signature superblob.
pub fn parse(data: &[u8]) -> Result<Signature, FormatError> {
    let r = Reader::new(data);
    let magic = r.u32_be(0).ok_or_else(|| FormatError::Truncated("superblob header".into()))?;
    if magic != SUPERBLOB {
        return Err(FormatError::Malformed(format!("superblob magic {magic:#x}")));
    }
    let length = r.u32_be(4).ok_or_else(|| FormatError::Truncated("superblob header".into()))?;
    let count = r.u32_be(8).ok_or_else(|| FormatError::Truncated("superblob header".into()))? as usize;
    let mut sig = Signature {
        length,
        blobs: Vec::new(),
        code_directories: Vec::new(),
        requirements: Vec::new(),
        entitlements: None,
        entitlements_xml: None,
        der_entitlements_bytes: None,
        cms_signature_bytes: None,
        ad_hoc: true,
        warnings: Vec::new(),
    };
    if length as usize > data.len() {
        sig.warnings.push(format!("superblob says {length} bytes but only {} are present", data.len()));
    }
    if count > MAX_BLOBS {
        sig.warnings.push(format!("{count} blobs listed; reading {MAX_BLOBS}"));
    }
    for i in 0..count.min(MAX_BLOBS) {
        let (Some(slot), Some(off)) = (r.u32_be(12 + i * 8), r.u32_be(16 + i * 8)) else {
            sig.warnings.push("blob index cut short".into());
            break;
        };
        let o = off as usize;
        let bmagic = r.u32_be(o);
        let blen = r.u32_be(o + 4);
        sig.blobs.push(BlobIndex { slot, slot_name: slot_name(slot), magic: bmagic.map(|m| format!("{m:#x}")).unwrap_or_default(), offset: off, length: blen });
        let (Some(bmagic), Some(blen)) = (bmagic, blen) else {
            sig.warnings.push(format!("blob {i} lies outside the signature"));
            continue;
        };
        let Some(blob) = r.slice(o, blen as usize) else {
            sig.warnings.push(format!("blob {i} ({}) runs past the end", slot_name(slot)));
            continue;
        };
        match bmagic {
            CODEDIRECTORY => match code_directory(blob, slot, o) {
                Ok(cd) => sig.code_directories.push(cd),
                Err(e) => sig.warnings.push(format!("code directory: {e}")),
            },
            REQUIREMENTS => requirements(blob, &mut sig),
            ENTITLEMENTS => {
                let xml = blob.get(8..).unwrap_or(&[]);
                sig.entitlements_xml = Some(String::from_utf8_lossy(xml).into_owned());
                match plist::parse(xml) {
                    Ok(v) => sig.entitlements = Some(v.to_json()),
                    Err(e) => sig.warnings.push(format!("entitlements plist: {e}")),
                }
            }
            DER_ENTITLEMENTS => sig.der_entitlements_bytes = Some(blob.len().saturating_sub(8)),
            BLOBWRAPPER => {
                let n = blob.len().saturating_sub(8);
                sig.cms_signature_bytes = Some(n);
                if n > 0 {
                    sig.ad_hoc = false;
                }
            }
            other => sig.warnings.push(format!("unrecognised blob magic {other:#x} in slot {}", slot_name(slot))),
        }
    }
    if sig.code_directories.iter().any(|c| c.flags & 0x2 == 0) && sig.cms_signature_bytes.unwrap_or(0) > 0 {
        sig.ad_hoc = false;
    }
    Ok(sig)
}

fn code_directory(b: &[u8], slot: u32, offset: usize) -> Result<CodeDirectory, FormatError> {
    let r = Reader::new(b);
    let t = |what: &str| FormatError::Truncated(format!("code directory {what}"));
    let length = r.u32_be(4).ok_or_else(|| t("length"))?;
    let version = r.u32_be(8).ok_or_else(|| t("version"))?;
    let flags = r.u32_be(12).ok_or_else(|| t("flags"))?;
    let hash_off = r.u32_be(16).ok_or_else(|| t("hash offset"))? as usize;
    let ident_off = r.u32_be(20).ok_or_else(|| t("identifier offset"))? as usize;
    let special = r.u32_be(24).ok_or_else(|| t("slots"))?;
    let code = r.u32_be(28).ok_or_else(|| t("slots"))?;
    let code_limit32 = r.u32_be(32).ok_or_else(|| t("code limit"))?;
    let hash_size = r.u8(36).ok_or_else(|| t("hash size"))?;
    let hash_type = r.u8(37).ok_or_else(|| t("hash type"))?;
    let platform = r.u8(38).unwrap_or(0);
    let page_log = r.u8(39).unwrap_or(0);
    let team_off = if version >= 0x20200 { r.u32_be(48).map(|v| v as usize).filter(|&v| v != 0) } else { None };
    let code_limit64 = if version >= 0x20300 { r.u64_be(56).filter(|&v| v != 0) } else { None };
    let exec_segment = if version >= 0x20400 {
        match (r.u64_be(64), r.u64_be(72), r.u64_be(80)) {
            (Some(base), Some(limit), Some(fl)) => Some(serde_json::json!({"base": base, "limit": limit, "flags": fl, "main_binary": fl & 1 != 0})),
            _ => None,
        }
    } else {
        None
    };
    let runtime_version = if version >= 0x20500 { r.u32_be(88).filter(|&v| v != 0).map(crate::macho_deps::version) } else { None };
    let ident = if ident_off > 0 && ident_off < b.len() { r.cstr(ident_off, 1024) } else { None };
    let team_id = team_off.filter(|&o| o < b.len()).and_then(|o| r.cstr(o, 256));
    let (cdhash, cd_digest) = match digest(hash_type, b) {
        Some(d) => (Some(hex(d.get(..20).unwrap_or(&d))), Some(hex(&d))),
        None => (None, None),
    };
    let mut special_hashes = Vec::new();
    let hs = usize::from(hash_size);
    if hs > 0 && hs <= 64 {
        for i in 1..=special.min(16) as usize {
            let Some(at) = hash_off.checked_sub(i.saturating_mul(hs)) else { break };
            if let Some(h) = r.slice(at, hs)
                && h.iter().any(|&x| x != 0)
            {
                special_hashes.push((-(i as i64), hex(h)));
            }
        }
    }
    Ok(CodeDirectory {
        slot,
        offset,
        length,
        version: format!("{version:#x}"),
        flags,
        flag_names: CD_FLAGS.iter().filter(|(bit, _)| flags & bit != 0).map(|(_, n)| *n).collect(),
        identifier: ident,
        team_id,
        hash_type: hash_name(hash_type).into(),
        hash_size,
        hash_offset: hash_off as u32,
        platform,
        page_size: if page_log == 0 || page_log > 32 { 0 } else { 1u64 << page_log },
        special_slots: special,
        code_slots: code,
        code_limit: code_limit64.unwrap_or(u64::from(code_limit32)),
        exec_segment,
        runtime_version,
        cdhash,
        cd_digest,
        special_hashes,
    })
}

fn req_kind(t: u32) -> String {
    match t {
        1 => "host".into(),
        2 => "guest".into(),
        3 => "designated".into(),
        4 => "library".into(),
        5 => "plugin".into(),
        o => format!("type-{o}"),
    }
}

fn requirements(b: &[u8], sig: &mut Signature) {
    let r = Reader::new(b);
    let count = r.u32_be(8).unwrap_or(0) as usize;
    for i in 0..count.min(16) {
        let (Some(ty), Some(off)) = (r.u32_be(12 + i * 8), r.u32_be(16 + i * 8)) else { break };
        let o = off as usize;
        let res = (|| -> Result<String, String> {
            if r.u32_be(o) != Some(REQUIREMENT) {
                return Err("bad requirement magic".into());
            }
            let len = r.u32_be(o + 4).ok_or("truncated")? as usize;
            let blob = r.slice(o, len).ok_or("requirement runs past the end")?;
            let rr = Reader::new(blob);
            if rr.u32_be(8) != Some(1) {
                return Err("not an expression requirement".into());
            }
            let mut p = Expr { r: rr, pos: 12 };
            p.expr(0).map(|(t, _)| t)
        })();
        match res {
            Ok(text) => sig.requirements.push(Requirement { kind: req_kind(ty), text: Some(text), error: None }),
            Err(e) => sig.requirements.push(Requirement { kind: req_kind(ty), text: None, error: Some(e) }),
        }
    }
}

/// Requirement-expression decoder. Returns text plus a precedence class (0 atom, 1 and, 2 or).
struct Expr<'a> {
    r: Reader<'a>,
    pos: usize,
}

impl Expr<'_> {
    fn u32(&mut self) -> Result<u32, String> {
        let v = self.r.u32_be(self.pos).ok_or("expression cut short")?;
        self.pos += 4;
        Ok(v)
    }

    fn data(&mut self) -> Result<Vec<u8>, String> {
        let n = self.u32()? as usize;
        let d = self.r.slice(self.pos, n).ok_or("expression data cut short")?.to_vec();
        self.pos = self.pos.checked_add(n.div_ceil(4).saturating_mul(4)).ok_or("overflow")?;
        Ok(d)
    }

    fn string(&mut self) -> Result<String, String> {
        Ok(quote(&String::from_utf8_lossy(&self.data()?)))
    }

    fn slot(&mut self) -> Result<String, String> {
        let s = self.u32()? as i32;
        Ok(match s {
            0 => "leaf".into(),
            -1 => "root".into(),
            n => n.to_string(),
        })
    }

    fn matcher(&mut self) -> Result<String, String> {
        let op = self.u32()?;
        let val = |p: &mut Self| p.string();
        Ok(match op {
            0 => " /* exists */".into(),
            1 => format!(" = {}", val(self)?),
            2 => format!(" ~ {}", val(self)?),
            3 => format!(" = {}*", val(self)?),
            4 => format!(" = *{}", val(self)?),
            5 => format!(" < {}", val(self)?),
            6 => format!(" > {}", val(self)?),
            7 => format!(" <= {}", val(self)?),
            8 => format!(" >= {}", val(self)?),
            9..=13 => {
                let t = self.r.u64_be(self.pos).ok_or("date cut short")?;
                self.pos += 8;
                let rel = ["=", "<", ">", "<=", ">="].get((op - 9) as usize).copied().unwrap_or("=");
                format!(" {rel} timestamp {t}")
            }
            14 => " /* absent */".into(),
            o => return Err(format!("unknown match operator {o}")),
        })
    }

    fn expr(&mut self, depth: usize) -> Result<(String, u8), String> {
        if depth > MAX_EXPR_DEPTH {
            return Err("requirement nests too deeply".into());
        }
        let op = self.u32()? & 0x00ff_ffff;
        Ok(match op {
            0 => ("never".into(), 0),
            1 => ("always".into(), 0),
            2 => (format!("identifier {}", self.string()?), 0),
            3 => ("anchor apple".into(), 0),
            4 => {
                let slot = self.slot()?;
                (format!("certificate {slot} = H\"{}\"", hex(&self.data()?)), 0)
            }
            5 => {
                let k = self.string()?;
                (format!("info[{}] = {}", unquote(&k), self.string()?), 0)
            }
            6 | 7 => {
                let (a, pa) = self.expr(depth + 1)?;
                let (b, pb) = self.expr(depth + 1)?;
                let me = if op == 6 { 1 } else { 2 };
                let wrap = |t: String, p: u8| if p > me { format!("({t})") } else { t };
                (format!("{} {} {}", wrap(a, pa), if op == 6 { "and" } else { "or" }, wrap(b, pb)), me)
            }
            8 => (format!("cdhash H\"{}\"", hex(&self.data()?)), 0),
            9 => {
                let (a, pa) = self.expr(depth + 1)?;
                (if pa > 0 { format!("! ({a})") } else { format!("! {a}") }, 0)
            }
            10 => {
                let k = self.string()?;
                (format!("info[{}]{}", unquote(&k), self.matcher()?), 0)
            }
            11 => {
                let slot = self.slot()?;
                let k = self.string()?;
                (format!("certificate {slot}[{}]{}", unquote(&k), self.matcher()?), 0)
            }
            12 => (format!("certificate {} trusted", self.slot()?), 0),
            13 => ("anchor trusted".into(), 0),
            14 | 17 => {
                let slot = self.slot()?;
                let oid = oid_text(&self.data()?);
                let what = if op == 14 { "field" } else { "policy" };
                (format!("certificate {slot}[{what}.{oid}]{}", self.matcher()?), 0)
            }
            15 => ("anchor apple generic".into(), 0),
            16 => {
                let k = self.string()?;
                (format!("entitlement[{}]{}", unquote(&k), self.matcher()?), 0)
            }
            18 => (format!("anchor {}", unquote(&self.string()?)), 0),
            19 => (format!("({})", unquote(&self.string()?)), 0),
            20 => (format!("platform = {}", self.u32()?), 0),
            21 => ("notarized".into(), 0),
            22 => {
                let slot = self.slot()?;
                let k = self.string()?;
                (format!("certificate {slot}[timestamp.{}]{}", unquote(&k), self.matcher()?), 0)
            }
            23 => ("legacy".into(), 0),
            o => return Err(format!("unknown requirement operator {o}")),
        })
    }
}

fn quote(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
}

fn unquote(s: &str) -> String {
    s.strip_prefix('"').and_then(|x| x.strip_suffix('"')).unwrap_or(s).to_string()
}

/// A DER object identifier as dotted text.
pub fn oid_text(d: &[u8]) -> String {
    let mut parts: Vec<u64> = Vec::new();
    let mut v = 0u64;
    for (i, &b) in d.iter().enumerate() {
        v = v.checked_shl(7).map(|x| x | u64::from(b & 0x7f)).unwrap_or(u64::MAX);
        if b & 0x80 == 0 {
            if parts.is_empty() && i < 8 {
                let first = if v < 80 { v / 40 } else { 2 };
                parts.push(first);
                parts.push(v - first * 40);
            } else {
                parts.push(v);
            }
            v = 0;
        }
        if parts.len() > 64 {
            break;
        }
    }
    parts.iter().map(u64::to_string).collect::<Vec<_>>().join(".")
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn sha1_vectors() {
        assert_eq!(hex(&sha1(b"abc")), "a9993e364706816aba3e25717850c26c9cd0d89d");
        assert_eq!(hex(&sha1(b"")), "da39a3ee5e6b4b0d3255bfef95601890afd80709");
        assert_eq!(oid_text(&[0x2a, 0x86, 0x48, 0x86, 0xf7, 0x63, 0x64, 0x06, 0x02, 0x06]), "1.2.840.113635.100.6.2.6");
    }

    #[test]
    fn parses_a_signature() {
        let blob = fx::code_signature_blob();
        let s = parse(&blob).unwrap();
        assert_eq!(s.code_directories.len(), 1);
        let cd = &s.code_directories[0];
        assert_eq!(cd.identifier.as_deref(), Some("com.example.notes"));
        assert_eq!(cd.team_id.as_deref(), Some("ABCDE12345"));
        assert_eq!(cd.hash_type, "sha256");
        assert!(cd.flag_names.contains(&"runtime"));
        assert_eq!(cd.cdhash.as_ref().unwrap().len(), 40);
        assert_eq!(cd.page_size, 4096);
        assert_eq!(cd.special_hashes.len(), 1);
        let req = s.requirements[0].text.as_ref().unwrap();
        assert_eq!(
            req,
            "identifier \"com.example.notes\" and anchor apple generic and certificate 1[field.1.2.840.113635.100.6.2.6] /* exists */ and certificate leaf[subject.OU] = \"ABCDE12345\""
        );
        assert_eq!(s.requirements[0].kind, "designated");
        assert_eq!(s.entitlements.as_ref().unwrap()["com.apple.security.app-sandbox"], true);
        assert_eq!(s.cms_signature_bytes, Some(4));
        assert!(!s.ad_hoc);
    }

    #[test]
    fn hostile_inputs() {
        let blob = fx::code_signature_blob();
        for m in craft_anything_testkit::mutations(&blob) {
            let _ = parse(&m);
        }
        for i in 0..blob.len() {
            let _ = parse(&blob[..i]);
        }
        for seed in 0..100 {
            let mut n = vec![0xfa, 0xde, 0x0c, 0xc0];
            n.extend(craft_anything_testkit::noise(seed, 200));
            let _ = parse(&n);
        }
    }
}
