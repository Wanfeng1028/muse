//! CMS `SignedData` (PKCS#7) as used by Apple code signing: the certificate set, the signer's
//! digest and signature algorithms, the authenticated (signed) attributes, the `messageDigest`
//! attribute (the hash of the signed content — for code signing, the primary CodeDirectory), and
//! the signature. Parsing is bounded and never panics; verification is done in [`crate::verify`].

use crate::der::{self, Tlv};
use crate::verify::{Digest, SigScheme};

const SIGNED_DATA: &str = "1.2.840.113549.1.7.2";
const OID_MESSAGE_DIGEST: &str = "1.2.840.113549.1.9.4";
const OID_CONTENT_TYPE: &str = "1.2.840.113549.1.9.3";
const RSA_ENCRYPTION: &str = "1.2.840.113549.1.1.1";
const RSA_PSS: &str = "1.2.840.113549.1.1.10";
const EC_PUBLIC_KEY: &str = "1.2.840.10045.2.1";

/// What the verifier needs out of a CMS `SignedData` blob.
#[derive(Debug, Clone)]
pub struct SignedData {
    /// Certificates (DER), leaf first (as `der::pkcs7_certificates` returns them).
    pub certificates: Vec<Vec<u8>>,
    /// The signer's digest algorithm.
    pub digest: Option<Digest>,
    /// The signer's `signatureAlgorithm` OID (dotted).
    pub signature_algorithm: String,
    /// The signature bytes.
    pub signature: Vec<u8>,
    /// The signed (authenticated) attributes re-encoded with a SET tag (`0x31`) — the exact bytes
    /// the signature is computed over. `None` when the signer carries no signed attributes.
    pub signed_attrs_reencoded: Option<Vec<u8>>,
    /// The `messageDigest` signed attribute (the hash of the signed content), hex.
    pub message_digest: Option<String>,
    /// The `contentType` signed attribute OID (dotted).
    pub content_type: Option<String>,
    /// The signer's issuer `Name` (DER) and serial (bytes), to pick its certificate.
    pub signer_issuer: Vec<u8>,
    pub signer_serial: Vec<u8>,
    /// The encapsulated eContent, when present (detached signatures have none).
    pub econtent: Option<Vec<u8>>,
}

fn oid_of(data: &[u8], t: &Tlv) -> String {
    der::oid(t.bytes(data).unwrap_or(&[]))
}

pub(crate) fn digest_from_oid(oid: &str) -> Option<Digest> {
    Some(match oid {
        "1.3.14.3.2.26" => Digest::Sha1,
        "2.16.840.1.101.3.4.2.1" => Digest::Sha256,
        "2.16.840.1.101.3.4.2.2" => Digest::Sha384,
        "2.16.840.1.101.3.4.2.3" => Digest::Sha512,
        _ => return None,
    })
}

fn hexs(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

/// Parse a CMS `SignedData` blob. `None` when it is not well-formed SignedData.
pub fn parse_signed_data(cms: &[u8]) -> Option<SignedData> {
    let ci = der::read(cms, 0)?;
    let kids = der::children(cms, &ci);
    if !kids.first().is_some_and(|t| t.tag == 0x06 && oid_of(cms, t) == SIGNED_DATA) {
        return None;
    }
    let explicit = kids.get(1).filter(|t| t.tag == 0xa0)?;
    let sd = der::children(cms, explicit).into_iter().next()?;
    let fields = der::children(cms, &sd);
    let mut econtent = None;
    let mut signer_infos = None;
    for f in &fields {
        match f.tag {
            0x30 => {
                let ec = der::children(cms, f);
                if ec.first().is_some_and(|t| t.tag == 0x06)
                    && let Some(inner) = ec.get(1).filter(|t| t.tag == 0xa0)
                {
                    econtent = der::children(cms, inner).into_iter().next().and_then(|o| o.bytes(cms)).map(<[u8]>::to_vec);
                }
            }
            0x31 => signer_infos = Some(*f),
            _ => {}
        }
    }
    let certificates: Vec<Vec<u8>> = der::pkcs7_certificates(cms).into_iter().map(<[u8]>::to_vec).collect();
    let signer_infos = signer_infos?;
    let signer = der::children(cms, &signer_infos).into_iter().next()?;
    let si = der::children(cms, &signer);
    let mut idx = 0usize;
    idx += 1; // version INTEGER
    let sid = si.get(idx)?;
    let (signer_issuer, signer_serial) = {
        let sid_kids = der::children(cms, sid);
        let issuer = sid_kids.first().and_then(|t| t.whole(cms)).unwrap_or(&[]).to_vec();
        let serial = sid_kids.get(1).and_then(|t| t.bytes(cms)).unwrap_or(&[]).to_vec();
        (issuer, serial)
    };
    idx += 1;
    let digest_alg = si.get(idx).filter(|t| t.tag == 0x30)?;
    let digest = der::seq_alg_oid(cms, digest_alg).and_then(|o| digest_from_oid(&o));
    idx += 1;
    let (signed_attrs_reencoded, message_digest, content_type) = if si.get(idx).is_some_and(|t| t.tag == 0xa0) {
        let attrs = si.get(idx).copied()?;
        idx += 1;
        let reenc = attrs.whole(cms).map(|w| {
            let mut v = w.to_vec();
            if let Some(first) = v.first_mut() {
                *first = 0x31;
            }
            v
        });
        let mut md = None;
        let mut ct = None;
        for attr in der::children(cms, &attrs) {
            let akids = der::children(cms, &attr);
            let Some(aoid) = akids.first().filter(|t| t.tag == 0x06).map(|t| oid_of(cms, t)) else { continue };
            let val_set = akids.get(1).filter(|t| t.tag == 0x31);
            let first_val = val_set.and_then(|s| der::children(cms, s).into_iter().next());
            if aoid == OID_MESSAGE_DIGEST {
                md = first_val.and_then(|v| v.bytes(cms)).map(hexs);
            } else if aoid == OID_CONTENT_TYPE {
                ct = first_val.map(|v| oid_of(cms, &v));
            }
        }
        (reenc, md, ct)
    } else {
        (None, None, None)
    };
    let sig_alg = si.get(idx).filter(|t| t.tag == 0x30)?;
    let signature_algorithm = der::seq_alg_oid(cms, sig_alg).unwrap_or_default();
    idx += 1;
    let signature = si.get(idx).filter(|t| t.tag == 0x04).and_then(|t| t.bytes(cms)).unwrap_or(&[]).to_vec();
    Some(SignedData {
        certificates,
        digest,
        signature_algorithm,
        signature,
        signed_attrs_reencoded,
        message_digest,
        content_type,
        signer_issuer,
        signer_serial,
        econtent,
    })
}

impl SignedData {
    /// The signer's certificate: the one whose issuer+serial match the SignerIdentifier, else the
    /// first (leaf) certificate.
    pub fn signer_cert(&self) -> Option<&[u8]> {
        for c in &self.certificates {
            if let Some(p) = der::certificate_parts(c)
                && p.issuer == self.signer_issuer.as_slice()
                && p.serial == self.signer_serial.as_slice()
            {
                return Some(c);
            }
        }
        self.certificates.first().map(Vec::as_slice)
    }

    /// The signature scheme implied by the signer's signature and digest algorithms.
    pub fn scheme(&self) -> Option<SigScheme> {
        let digest = self.digest?;
        match self.signature_algorithm.as_str() {
            RSA_ENCRYPTION => Some(SigScheme::RsaPkcs1v15(digest)),
            RSA_PSS => Some(SigScheme::RsaPss(digest)),
            EC_PUBLIC_KEY => Some(SigScheme::Ecdsa(digest)),
            other => crate::verify::scheme_from_oid(other),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_and_garbage() {
        assert!(parse_signed_data(&[]).is_none());
        for seed in 0..64 {
            let n = craft_anything_testkit::noise(seed, 300);
            let _ = parse_signed_data(&n);
        }
        let p7 = craft_anything_testkit::android::pkcs7_der(&craft_anything_testkit::android::certificate_der("A", "B"));
        let _ = parse_signed_data(&p7);
    }
}
