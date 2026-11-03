//! A minimal DER (ASN.1) reader: enough to walk PKCS#7 SignedData and pull X.509 certificate
//! facts (subject, issuer, serial, validity, algorithms). No signature checking. Bounded depth,
//! checked lengths, never panics.

use serde::Serialize;

/// Deepest nesting walked.
const MAX_DEPTH: usize = 32;
/// Most certificates taken from one PKCS#7 blob.
const MAX_CERTS: usize = 64;

/// One TLV: tag byte, and the content range within the input.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Tlv {
    pub tag: u8,
    /// Offset of the first byte of the TLV (the tag).
    pub start: usize,
    /// Offset of the content.
    pub content: usize,
    /// Content length.
    pub len: usize,
}

impl Tlv {
    /// Offset just past this TLV.
    pub fn end(&self) -> usize {
        self.content.saturating_add(self.len)
    }

    pub fn bytes<'a>(&self, data: &'a [u8]) -> Option<&'a [u8]> {
        data.get(self.content..self.end())
    }

    /// The whole TLV, header included.
    pub fn whole<'a>(&self, data: &'a [u8]) -> Option<&'a [u8]> {
        data.get(self.start..self.end())
    }

    pub fn constructed(&self) -> bool {
        self.tag & 0x20 != 0
    }
}

/// Read one TLV at `off`. Only single-byte tags and definite lengths of up to 4 bytes.
pub fn read(data: &[u8], off: usize) -> Option<Tlv> {
    let tag = *data.get(off)?;
    if tag & 0x1f == 0x1f {
        return None;
    }
    let l0 = *data.get(off.checked_add(1)?)?;
    let (len, hdr) = if l0 & 0x80 == 0 {
        (usize::from(l0), 2usize)
    } else {
        let n = usize::from(l0 & 0x7f);
        if n == 0 || n > 4 {
            return None;
        }
        let mut v = 0usize;
        for i in 0..n {
            v = v.checked_mul(256)?.checked_add(usize::from(*data.get(off.checked_add(2 + i)?)?))?;
        }
        (v, 2 + n)
    };
    let content = off.checked_add(hdr)?;
    let end = content.checked_add(len)?;
    if end > data.len() {
        return None;
    }
    Some(Tlv { tag, start: off, content, len })
}

/// The children of a constructed TLV (stops at the first malformed child).
pub fn children(data: &[u8], parent: &Tlv) -> Vec<Tlv> {
    let mut out = Vec::new();
    let mut pos = parent.content;
    let end = parent.end();
    while pos < end && out.len() < 4096 {
        match read(data, pos) {
            Some(t) if t.end() <= end => {
                pos = t.end();
                out.push(t);
            }
            _ => break,
        }
    }
    out
}

/// Dotted form of an OBJECT IDENTIFIER's content.
pub fn oid(content: &[u8]) -> String {
    let mut parts: Vec<String> = Vec::new();
    let mut v: u64 = 0;
    let mut first = true;
    for &b in content.iter().take(64) {
        v = match v.checked_mul(128) {
            Some(x) => x | u64::from(b & 0x7f),
            None => return "invalid".into(),
        };
        if b & 0x80 == 0 {
            if first {
                let (a, b2) = if v < 40 {
                    (0, v)
                } else if v < 80 {
                    (1, v - 40)
                } else {
                    (2, v - 80)
                };
                parts.push(a.to_string());
                parts.push(b2.to_string());
                first = false;
            } else {
                parts.push(v.to_string());
            }
            v = 0;
        }
    }
    parts.join(".")
}

/// Friendly names for the OIDs certificates usually carry.
pub fn oid_name(o: &str) -> Option<&'static str> {
    Some(match o {
        "2.5.4.3" => "CN",
        "2.5.4.6" => "C",
        "2.5.4.7" => "L",
        "2.5.4.8" => "ST",
        "2.5.4.10" => "O",
        "2.5.4.11" => "OU",
        "2.5.4.5" => "serialNumber",
        "1.2.840.113549.1.9.1" => "emailAddress",
        "1.2.840.113549.1.1.1" => "rsaEncryption",
        "1.2.840.113549.1.1.5" => "sha1WithRSAEncryption",
        "1.2.840.113549.1.1.11" => "sha256WithRSAEncryption",
        "1.2.840.113549.1.1.12" => "sha384WithRSAEncryption",
        "1.2.840.113549.1.1.13" => "sha512WithRSAEncryption",
        "1.2.840.10045.2.1" => "ecPublicKey",
        "1.2.840.10045.4.3.2" => "ecdsa-with-SHA256",
        "1.2.840.10045.4.3.3" => "ecdsa-with-SHA384",
        "1.2.840.10040.4.1" => "dsa",
        "1.2.840.10040.4.3" => "dsa-with-sha1",
        "2.16.840.1.101.3.4.3.2" => "dsa-with-sha256",
        "1.2.840.113549.1.7.2" => "signedData",
        "1.2.840.113549.1.7.1" => "data",
        _ => return None,
    })
}

fn text(data: &[u8], t: &Tlv) -> String {
    let b = t.bytes(data).unwrap_or(&[]);
    match t.tag {
        // BMPString: UTF-16BE.
        0x1e => {
            let units: Vec<u16> = b.as_chunks::<2>().0.iter().map(|c| u16::from_be_bytes(*c)).collect();
            String::from_utf16_lossy(&units)
        }
        _ => String::from_utf8_lossy(b).into_owned(),
    }
}

/// A distinguished name as `CN=…, O=…`.
pub fn name(data: &[u8], seq: &Tlv) -> String {
    let mut parts = Vec::new();
    for set in children(data, seq) {
        for atv in children(data, &set) {
            let kids = children(data, &atv);
            if let (Some(o), Some(v)) = (kids.first(), kids.get(1)) {
                let id = oid(o.bytes(data).unwrap_or(&[]));
                let key = oid_name(&id).map(str::to_string).unwrap_or(id);
                parts.push(format!("{key}={}", text(data, v)));
            }
        }
    }
    parts.join(", ")
}

/// Facts read from one X.509 certificate.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct CertInfo {
    pub subject: String,
    pub issuer: String,
    /// Serial number, hex.
    pub serial: String,
    pub not_before: String,
    pub not_after: String,
    pub signature_algorithm: String,
    pub public_key_algorithm: String,
    pub version: u8,
}

fn alg(data: &[u8], seq: &Tlv) -> String {
    children(data, seq)
        .first()
        .filter(|t| t.tag == 0x06)
        .map(|t| {
            let o = oid(t.bytes(data).unwrap_or(&[]));
            oid_name(&o).map(str::to_string).unwrap_or(o)
        })
        .unwrap_or_default()
}

/// Read a DER certificate.
pub fn certificate(data: &[u8]) -> Option<CertInfo> {
    let cert = read(data, 0)?;
    if cert.tag != 0x30 {
        return None;
    }
    let parts = children(data, &cert);
    let tbs = parts.first().filter(|t| t.tag == 0x30)?;
    let mut info = CertInfo { version: 1, ..CertInfo::default() };
    if let Some(sa) = parts.get(1) {
        info.signature_algorithm = alg(data, sa);
    }
    let f = children(data, tbs);
    let mut i = 0usize;
    if let Some(v) = f.first().filter(|t| t.tag == 0xa0) {
        i = 1;
        if let Some(int) = children(data, v).first() {
            info.version = int.bytes(data).and_then(|b| b.last()).copied().unwrap_or(0).saturating_add(1);
        }
    }
    let serial = f.get(i).filter(|t| t.tag == 0x02)?;
    info.serial = serial.bytes(data).unwrap_or(&[]).iter().take(64).map(|b| format!("{b:02x}")).collect();
    if let Some(issuer) = f.get(i + 2) {
        info.issuer = name(data, issuer);
    }
    if let Some(validity) = f.get(i + 3) {
        let v = children(data, validity);
        info.not_before = v.first().map(|t| text(data, t)).unwrap_or_default();
        info.not_after = v.get(1).map(|t| text(data, t)).unwrap_or_default();
    }
    if let Some(subject) = f.get(i + 4) {
        info.subject = name(data, subject);
    }
    if let Some(spki) = f.get(i + 5)
        && let Some(a) = children(data, spki).first()
    {
        info.public_key_algorithm = alg(data, a);
    }
    Some(info)
}

/// The certificates (whole DER TLVs) inside a PKCS#7 SignedData blob, as in `META-INF/*.RSA`.
pub fn pkcs7_certificates(data: &[u8]) -> Vec<&[u8]> {
    let mut out = Vec::new();
    let Some(ci) = read(data, 0) else { return out };
    let kids = children(data, &ci);
    let is_signed = kids.first().is_some_and(|t| t.tag == 0x06 && oid(t.bytes(data).unwrap_or(&[])) == "1.2.840.113549.1.7.2");
    if !is_signed {
        return out;
    }
    let Some(explicit) = kids.get(1).filter(|t| t.tag == 0xa0) else { return out };
    let Some(sd) = children(data, explicit).into_iter().next() else { return out };
    for field in children(data, &sd) {
        // certificates [0] IMPLICIT SET OF Certificate
        if field.tag == 0xa0 {
            for c in children(data, &field).into_iter().take(MAX_CERTS) {
                if let Some(w) = c.whole(data) {
                    out.push(w);
                }
            }
        }
    }
    out
}

/// The dotted OID of an AlgorithmIdentifier SEQUENCE's first child (the algorithm OID).
pub fn seq_alg_oid(data: &[u8], seq: &Tlv) -> Option<String> {
    children(data, seq).into_iter().find(|t| t.tag == 0x06).map(|t| oid(t.bytes(data).unwrap_or(&[])))
}

/// The byte ranges a verifier needs from one DER X.509 certificate.
#[derive(Debug, Clone)]
pub struct CertParts<'a> {
    /// The raw DER of the `tbsCertificate` SEQUENCE (header included): this is the signed message.
    pub tbs: &'a [u8],
    /// The `signatureAlgorithm` OID (dotted).
    pub signature_algorithm: String,
    /// The `signatureValue` BIT STRING contents (leading unused-bits byte stripped).
    pub signature: &'a [u8],
    /// The `subjectPublicKeyInfo` SEQUENCE (header included).
    pub spki: &'a [u8],
    /// The `issuer` Name SEQUENCE (header included).
    pub issuer: &'a [u8],
    /// The `subject` Name SEQUENCE (header included).
    pub subject: &'a [u8],
    /// The `serialNumber` INTEGER contents.
    pub serial: &'a [u8],
}

/// Split a certificate into the ranges a verifier needs. `None` on any structural problem.
pub fn certificate_parts(data: &[u8]) -> Option<CertParts<'_>> {
    let cert = read(data, 0)?;
    if cert.tag != 0x30 {
        return None;
    }
    let parts = children(data, &cert);
    let tbs_tlv = parts.first().filter(|t| t.tag == 0x30)?;
    let tbs = tbs_tlv.whole(data)?;
    let sig_alg_seq = parts.get(1)?;
    let signature_algorithm = seq_alg_oid(data, sig_alg_seq).unwrap_or_default();
    let sig_bits = parts.get(2).filter(|t| t.tag == 0x03)?;
    // A BIT STRING's first content byte is the count of unused bits; skip it.
    let signature = sig_bits.bytes(data).and_then(|b| b.get(1..))?;
    let f = children(data, tbs_tlv);
    let mut i = 0usize;
    if f.first().is_some_and(|t| t.tag == 0xa0) {
        i = 1;
    }
    let serial_tlv = f.get(i).filter(|t| t.tag == 0x02)?;
    let serial = serial_tlv.bytes(data)?;
    let issuer = f.get(i + 2).and_then(|t| t.whole(data))?;
    let subject = f.get(i + 4).and_then(|t| t.whole(data))?;
    let spki = f.get(i + 5).filter(|t| t.tag == 0x30).and_then(|t| t.whole(data))?;
    Some(CertParts { tbs, signature_algorithm, signature, spki, issuer, subject, serial })
}

/// The `subjectPublicKeyInfo` SEQUENCE of a certificate (header included).
pub fn certificate_spki(data: &[u8]) -> Option<&[u8]> {
    certificate_parts(data).map(|p| p.spki)
}

/// Split a `subjectPublicKeyInfo` into `(algorithm OID, public-key BIT STRING contents)`.
/// The BIT STRING's leading unused-bits byte is stripped.
pub fn spki_parts(data: &[u8]) -> Option<(String, &[u8])> {
    let seq = read(data, 0)?;
    if seq.tag != 0x30 {
        return None;
    }
    let kids = children(data, &seq);
    let alg = kids.first().filter(|t| t.tag == 0x30)?;
    let algorithm = seq_alg_oid(data, alg).unwrap_or_default();
    let bits = kids.get(1).filter(|t| t.tag == 0x03)?;
    let key = bits.bytes(data).and_then(|b| b.get(1..))?;
    Some((algorithm, key))
}

/// Walk every TLV to `MAX_DEPTH`, counting them (a structural sanity check).
pub fn count_nodes(data: &[u8]) -> usize {
    fn walk(data: &[u8], t: &Tlv, depth: usize, n: &mut usize) {
        *n += 1;
        if depth >= MAX_DEPTH || *n > 100_000 || !t.constructed() {
            return;
        }
        for c in children(data, t) {
            walk(data, &c, depth + 1, n);
        }
    }
    let mut n = 0;
    if let Some(t) = read(data, 0) {
        walk(data, &t, 0, &mut n);
    }
    n
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_synthetic_certificate() {
        let cert = craft_anything_testkit::android::certificate_der("Craft Test", "Craft Org");
        let info = certificate(&cert).unwrap();
        assert_eq!(info.subject, "CN=Craft Test, O=Craft Org");
        assert_eq!(info.issuer, "CN=Craft Test, O=Craft Org");
        assert_eq!(info.serial, "0102030405");
        assert_eq!(info.signature_algorithm, "sha256WithRSAEncryption");
        assert_eq!(info.public_key_algorithm, "rsaEncryption");
        assert_eq!(info.version, 3);
        assert_eq!(info.not_before, "250101000000Z");
        let p7 = craft_anything_testkit::android::pkcs7_der(&cert);
        let certs = pkcs7_certificates(&p7);
        assert_eq!(certs, vec![cert.as_slice()]);
        assert!(count_nodes(&p7) > 10);
    }

    #[test]
    fn oids_and_garbage() {
        assert_eq!(oid(&[0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x0b]), "1.2.840.113549.1.1.11");
        let cert = craft_anything_testkit::android::pkcs7_der(&craft_anything_testkit::android::certificate_der("A", "B"));
        for m in craft_anything_testkit::mutations(&cert) {
            let _ = pkcs7_certificates(&m);
            let _ = certificate(&m);
            let _ = count_nodes(&m);
        }
        for len in 0..cert.len() {
            let _ = pkcs7_certificates(&cert[..len]);
            let _ = certificate(&cert[..len]);
        }
        for seed in 0..64 {
            let n = craft_anything_testkit::noise(seed, 300);
            let _ = certificate(&n);
            let _ = pkcs7_certificates(&n);
        }
        assert!(read(&[0x30, 0x85, 1, 1, 1, 1, 1], 0).is_none());
        assert!(read(&[0x30, 0x84, 0xff, 0xff, 0xff, 0xff], 0).is_none());
    }
}
