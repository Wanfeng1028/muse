//! The APK Signing Block (signature schemes v2, v3 and v3.1): the id-value pairs that sit
//! between the last ZIP entry and the central directory, and the signers inside them
//! (certificates, digests, signature algorithms, SDK ranges). Signatures are NOT verified.

use crate::bytes::Reader;
use serde::Serialize;

const MAGIC: &[u8; 16] = b"APK Sig Block 42";
const MAX_PAIRS: usize = 256;
const MAX_ITEMS: usize = 64;
/// Most certificate bytes kept per certificate.
const MAX_CERT: usize = 64 * 1024;

pub const V2_ID: u32 = 0x7109_871a;
pub const V3_ID: u32 = 0xf053_68c0;
pub const V31_ID: u32 = 0x1b93_ad61;

/// What a block id means, when we know.
pub fn block_name(id: u32) -> &'static str {
    match id {
        V2_ID => "signature scheme v2",
        V3_ID => "signature scheme v3",
        V31_ID => "signature scheme v3.1",
        0x4272_6577 => "verity padding",
        0x6dff_800d => "source stamp v2",
        0x2b09_189e => "source stamp v1",
        0x2146_444e => "store metadata",
        0x504b_4453 => "dependency info",
        _ => "unknown",
    }
}

/// Name of a signature algorithm id.
pub fn algorithm_name(id: u32) -> &'static str {
    match id {
        0x0101 => "RSASSA-PSS with SHA2-256",
        0x0102 => "RSASSA-PSS with SHA2-512",
        0x0103 => "RSASSA-PKCS1-v1_5 with SHA2-256",
        0x0104 => "RSASSA-PKCS1-v1_5 with SHA2-512",
        0x0201 => "ECDSA with SHA2-256",
        0x0202 => "ECDSA with SHA2-512",
        0x0301 => "DSA with SHA2-256",
        0x0421 => "RSASSA-PKCS1-v1_5 with SHA2-256 (verity)",
        0x0423 => "ECDSA with SHA2-256 (verity)",
        0x0425 => "DSA with SHA2-256 (verity)",
        _ => "unknown",
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct BlockEntry {
    pub id: String,
    pub name: &'static str,
    pub size: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SignerDigest {
    pub algorithm: String,
    pub algorithm_name: &'static str,
    pub digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Signer {
    /// v2, v3 or v3.1.
    pub scheme: &'static str,
    /// Certificates (DER), first is the signer's.
    #[serde(skip)]
    pub certificates: Vec<Vec<u8>>,
    pub digests: Vec<SignerDigest>,
    pub signature_algorithms: Vec<String>,
    pub min_sdk: Option<u32>,
    pub max_sdk: Option<u32>,
    pub public_key_bytes: usize,
    /// The signer's public key (SubjectPublicKeyInfo, DER).
    #[serde(skip)]
    pub public_key: Vec<u8>,
    /// The exact signed-data bytes the signatures are computed over.
    #[serde(skip)]
    pub signed_data: Vec<u8>,
    /// Signatures present, as (algorithm id, signature bytes).
    #[serde(skip)]
    pub signatures: Vec<(u32, Vec<u8>)>,
    /// The digests (algorithm id, raw bytes) carried inside the signed data.
    #[serde(skip)]
    pub signed_digests: Vec<(u32, Vec<u8>)>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct SigningBlock {
    pub offset: u64,
    pub size: u64,
    pub entries: Vec<BlockEntry>,
    pub signers: Vec<Signer>,
    pub warnings: Vec<String>,
}

fn find_eocd(data: &[u8]) -> Option<usize> {
    let from = data.len().saturating_sub(22 + 0xffff);
    let mut i = data.len().checked_sub(22)?;
    while i >= from {
        if data.get(i..i + 4) == Some(b"PK\x05\x06") {
            return Some(i);
        }
        i = i.checked_sub(1)?;
    }
    None
}

struct Lp<'a> {
    data: &'a [u8],
}

impl<'a> Lp<'a> {
    fn at(&self, pos: usize) -> Option<(&'a [u8], usize)> {
        let r = Reader::new(self.data);
        let n = r.u32_le(pos)? as usize;
        let start = pos.checked_add(4)?;
        let s = r.slice(start, n)?;
        Some((s, start.checked_add(n)?))
    }

    /// Every length-prefixed item in a sequence.
    fn items(data: &'a [u8]) -> Vec<&'a [u8]> {
        let l = Lp { data };
        let mut out = Vec::new();
        let mut pos = 0;
        while pos < data.len() && out.len() < MAX_ITEMS {
            match l.at(pos) {
                Some((s, next)) => {
                    out.push(s);
                    pos = next;
                }
                None => break,
            }
        }
        out
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().take(128).map(|x| format!("{x:02x}")).collect()
}

fn parse_signer(scheme: &'static str, s: &[u8], warnings: &mut Vec<String>) -> Option<Signer> {
    let l = Lp { data: s };
    let r = Reader::new(s);
    let (signed, mut pos) = l.at(0)?;
    let mut min_sdk = None;
    let mut max_sdk = None;
    if scheme != "v2" {
        min_sdk = r.u32_le(pos);
        max_sdk = r.u32_le(pos + 4);
        pos += 8;
    }
    let mut signature_algorithms = Vec::new();
    let mut signatures = Vec::new();
    if let Some((sigs, next)) = l.at(pos) {
        for item in Lp::items(sigs) {
            // Each signature item: u32 algorithm id, then a length-prefixed signature.
            if let Some(id) = Reader::new(item).u32_le(0) {
                signature_algorithms.push(format!("{} ({id:#06x})", algorithm_name(id)));
                if let Some((sig, _)) = (Lp { data: item }).at(4) {
                    signatures.push((id, sig.to_vec()));
                }
            }
        }
        pos = next;
    }
    let public_key = l.at(pos).map(|(k, _)| k.to_vec()).unwrap_or_default();
    let public_key_bytes = public_key.len();
    // signed data: digests, certificates, [v3: min, max], attributes
    let sl = Lp { data: signed };
    let mut digests = Vec::new();
    let mut signed_digests = Vec::new();
    let mut certificates = Vec::new();
    if let Some((ds, next)) = sl.at(0) {
        for item in Lp::items(ds) {
            let ir = Reader::new(item);
            if let (Some(id), Some((d, _))) = (ir.u32_le(0), (Lp { data: item }).at(4)) {
                digests.push(SignerDigest { algorithm: format!("{id:#06x}"), algorithm_name: algorithm_name(id), digest: hex(d) });
                signed_digests.push((id, d.to_vec()));
            }
        }
        if let Some((cs, _)) = sl.at(next) {
            for c in Lp::items(cs) {
                if c.len() > MAX_CERT {
                    warnings.push(format!("a {scheme} certificate is {} bytes; skipped", c.len()));
                    continue;
                }
                certificates.push(c.to_vec());
            }
        }
    }
    Some(Signer {
        scheme,
        certificates,
        digests,
        signature_algorithms,
        min_sdk,
        max_sdk,
        public_key_bytes,
        public_key,
        signed_data: signed.to_vec(),
        signatures,
        signed_digests,
    })
}

/// Find and parse the APK Signing Block. `Ok(None)` when the APK has none (v1-only or unsigned).
pub fn parse(data: &[u8]) -> Option<SigningBlock> {
    let r = Reader::new(data);
    let eocd = find_eocd(data)?;
    let cd = r.u32_le(eocd + 16)? as usize;
    let magic_at = cd.checked_sub(16)?;
    if r.slice(magic_at, 16)? != MAGIC {
        return None;
    }
    let size_footer = r.u64_le(cd.checked_sub(24)?)?;
    let total = usize::try_from(size_footer).ok()?.checked_add(8)?;
    let start = cd.checked_sub(total)?;
    let mut block = SigningBlock { offset: start as u64, size: size_footer, ..SigningBlock::default() };
    if r.u64_le(start) != Some(size_footer) {
        block.warnings.push("the block's two size fields disagree".into());
    }
    let pairs_end = cd.checked_sub(24)?;
    let mut pos = start.checked_add(8)?;
    while pos < pairs_end && block.entries.len() < MAX_PAIRS {
        let Some(len) = r.u64_le(pos).and_then(|l| usize::try_from(l).ok()) else { break };
        let Some(next) = pos.checked_add(8).and_then(|p| p.checked_add(len)) else { break };
        if len < 4 || next > pairs_end {
            block.warnings.push(format!("malformed id-value pair at offset {pos}"));
            break;
        }
        let Some(id) = r.u32_le(pos + 8) else { break };
        block.entries.push(BlockEntry { id: format!("{id:#010x}"), name: block_name(id), size: len as u64 - 4 });
        let scheme = match id {
            V2_ID => Some("v2"),
            V3_ID => Some("v3"),
            V31_ID => Some("v3.1"),
            _ => None,
        };
        if let (Some(scheme), Some(value)) = (scheme, r.slice(pos + 12, len - 4)) {
            // value: length-prefixed sequence of length-prefixed signers
            if let Some((signers, _)) = (Lp { data: value }).at(0) {
                for s in Lp::items(signers) {
                    match parse_signer(scheme, s, &mut block.warnings) {
                        Some(sg) => block.signers.push(sg),
                        None => block.warnings.push(format!("a {scheme} signer could not be read")),
                    }
                }
            }
        }
        pos = next;
    }
    Some(block)
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::android as fx;

    #[test]
    fn reads_v2_and_v3_signers() {
        let apk = fx::notes_apk();
        let b = parse(&apk).unwrap();
        assert!(b.warnings.is_empty(), "{:?}", b.warnings);
        assert_eq!(b.entries.len(), 3);
        assert_eq!(b.entries[0].name, "signature scheme v2");
        assert_eq!(b.entries[1].name, "signature scheme v3");
        assert_eq!(b.signers.len(), 2);
        let v2 = &b.signers[0];
        assert_eq!(v2.scheme, "v2");
        assert_eq!(v2.certificates.len(), 1);
        assert_eq!(crate::der::certificate(&v2.certificates[0]).unwrap().subject, "CN=Craft Test, O=Craft Org");
        assert_eq!(v2.digests[0].algorithm_name, "RSASSA-PKCS1-v1_5 with SHA2-256");
        assert_eq!(v2.digests[0].digest, "aa".repeat(32));
        let v3 = &b.signers[1];
        assert_eq!((v3.min_sdk, v3.max_sdk), (Some(24), Some(0x7fff_ffff)));
        assert!(parse(&craft_anything_testkit::electron::zip_stored(&[("a", b"b")])).is_none());
    }

    #[test]
    fn hostile() {
        let apk = fx::notes_apk();
        for m in craft_anything_testkit::mutations(&apk) {
            let _ = parse(&m);
        }
        for len in 0..apk.len() {
            let _ = parse(&apk[..len]);
        }
        for seed in 0..32 {
            let mut n = craft_anything_testkit::noise(seed, 400);
            n.extend_from_slice(b"APK Sig Block 42PK\x05\x06");
            n.extend_from_slice(&[0; 18]);
            let _ = parse(&n);
        }
    }
}
