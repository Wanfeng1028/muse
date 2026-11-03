//! Real key generation and signing for signature-verification fixtures.
//!
//! One 2048-bit RSA key and one NIST P-256 key are generated lazily and reused, so the signing
//! fixtures (X.509 certs, APK v2/v3 signers, Mach-O CMS) carry genuine signatures that the
//! verifier in `craft-anything-formats` can check round-trip. Test-time only.

use crate::android::{der, der_oid};
use p256::ecdsa::{Signature as P256Sig, SigningKey as P256Sk, VerifyingKey as P256Vk};
use rsa::pkcs1::EncodeRsaPublicKey;
use rsa::signature::{SignatureEncoding, Signer};
use rsa::{RsaPrivateKey, RsaPublicKey};
use sha2::{Digest, Sha256};
use std::sync::OnceLock;

fn seq(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x30, &parts.concat())
}
fn set(parts: &[Vec<u8>]) -> Vec<u8> {
    der(0x31, &parts.concat())
}
fn bit_string(contents: &[u8]) -> Vec<u8> {
    let mut v = vec![0u8];
    v.extend_from_slice(contents);
    der(0x03, &v)
}
fn dn(cn: &str, o: &str) -> Vec<u8> {
    seq(&[set(&[seq(&[der_oid("2.5.4.3"), der(0x0c, cn.as_bytes())])]), set(&[seq(&[der_oid("2.5.4.10"), der(0x0c, o.as_bytes())])])])
}

// ---------------------------------------------------------------------------------------------
// Keys (generated once, reused)

fn rsa_key() -> &'static RsaPrivateKey {
    static KEY: OnceLock<RsaPrivateKey> = OnceLock::new();
    KEY.get_or_init(|| {
        let mut rng = rand::thread_rng();
        RsaPrivateKey::new(&mut rng, 2048).expect("rsa keygen")
    })
}

fn p256_key() -> &'static P256Sk {
    static KEY: OnceLock<P256Sk> = OnceLock::new();
    KEY.get_or_init(|| {
        let mut rng = rand::thread_rng();
        P256Sk::random(&mut rng)
    })
}

/// The RSA key's `subjectPublicKeyInfo` (DER).
pub fn rsa_spki() -> Vec<u8> {
    let pkcs1 = RsaPublicKey::from(rsa_key()).to_pkcs1_der().expect("pkcs1").as_bytes().to_vec();
    seq(&[seq(&[der_oid("1.2.840.113549.1.1.1"), der(0x05, &[])]), bit_string(&pkcs1)])
}

/// The P-256 key's `subjectPublicKeyInfo` (DER).
pub fn p256_spki() -> Vec<u8> {
    let vk = P256Vk::from(p256_key());
    let point = vk.to_encoded_point(false);
    seq(&[seq(&[der_oid("1.2.840.10045.2.1"), der_oid("1.2.840.10045.3.1.7")]), bit_string(point.as_bytes())])
}

/// Sign `msg` with the RSA key (PKCS#1 v1.5, SHA-256).
pub fn rsa_sign_sha256(msg: &[u8]) -> Vec<u8> {
    let sk = rsa::pkcs1v15::SigningKey::<Sha256>::new(rsa_key().clone());
    sk.sign(msg).to_vec()
}

/// Sign `msg` with the P-256 key (ECDSA, SHA-256); returns an ASN.1 DER signature.
pub fn p256_sign_sha256(msg: &[u8]) -> Vec<u8> {
    let sig: P256Sig = p256_key().sign(msg);
    sig.to_der().as_bytes().to_vec()
}

/// SHA-256 of a byte slice (e.g. a DER certificate fingerprint).
pub fn sha256(data: &[u8]) -> [u8; 32] {
    Sha256::digest(data).into()
}

// ---------------------------------------------------------------------------------------------
// Certificates (genuinely signed)

/// Build a DER X.509 v3 certificate carrying `subject_spki`, signed over the tbsCertificate by
/// `sign` with the given signature-algorithm OID.
pub fn make_cert(subject_cn: &str, subject_o: &str, issuer_cn: &str, subject_spki: &[u8], sig_alg_oid: &str, sign: &dyn Fn(&[u8]) -> Vec<u8>) -> Vec<u8> {
    let alg = if sig_alg_oid.starts_with("1.2.840.10045") {
        seq(&[der_oid(sig_alg_oid)]) // ECDSA: no NULL parameters
    } else {
        seq(&[der_oid(sig_alg_oid), der(0x05, &[])])
    };
    let tbs = seq(&[
        der(0xa0, &der(0x02, &[2])), // version v3
        der(0x02, &[1, 2, 3, 4, 5]), // serial
        alg.clone(),
        dn(issuer_cn, subject_o),
        seq(&[der(0x17, b"250101000000Z"), der(0x17, b"350101000000Z")]),
        dn(subject_cn, subject_o),
        subject_spki.to_vec(),
    ]);
    let sig = sign(&tbs);
    seq(&[tbs, alg, bit_string(&sig)])
}

/// A self-signed RSA certificate (sha256WithRSAEncryption) over the shared RSA key.
pub fn self_signed_rsa(cn: &str, o: &str) -> Vec<u8> {
    make_cert(cn, o, cn, &rsa_spki(), "1.2.840.113549.1.1.11", &rsa_sign_sha256)
}

/// A leaf certificate signed by a self-signed CA, returned `(leaf, ca)`.
pub fn cert_chain() -> (Vec<u8>, Vec<u8>) {
    let ca = self_signed_rsa("Craft Test CA", "Craft Org");
    // Leaf's own key is the P-256 key; it is signed by the RSA CA (sha256WithRSA).
    let leaf = make_cert("Craft Leaf", "Craft Org", "Craft Test CA", &p256_spki(), "1.2.840.113549.1.1.11", &rsa_sign_sha256);
    (leaf, ca)
}

// ---------------------------------------------------------------------------------------------
// Signer closures used by the formats verify.rs unit tests

/// An RSA public key (SPKI) and a SHA-256 PKCS#1 v1.5 signing closure over the matching key.
#[allow(clippy::type_complexity)]
pub fn rsa_signer() -> (Vec<u8>, Box<dyn Fn(&[u8], u8) -> Vec<u8> + Send + Sync>) {
    (rsa_spki(), Box::new(|msg: &[u8], _digest: u8| rsa_sign_sha256(msg)))
}

/// A P-256 public key (SPKI) and a SHA-256 ECDSA (DER) signing closure.
#[allow(clippy::type_complexity)]
pub fn p256_signer() -> (Vec<u8>, Box<dyn Fn(&[u8]) -> Vec<u8> + Send + Sync>) {
    (p256_spki(), Box::new(|msg: &[u8]| p256_sign_sha256(msg)))
}

// ---------------------------------------------------------------------------------------------
// CMS SignedData (detached), as Apple code signing and JAR (v1) signatures use.

/// Standard base64 (padded) — the encoding JAR manifests use for digests.
pub fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for chunk in data.chunks(3) {
        let b = [chunk[0], chunk.get(1).copied().unwrap_or(0), chunk.get(2).copied().unwrap_or(0)];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        out.push(T[(n >> 18 & 63) as usize] as char);
        out.push(T[(n >> 12 & 63) as usize] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6 & 63) as usize] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[(n & 63) as usize] as char } else { '=' });
    }
    out
}

/// A detached CMS `SignedData` over `content`, signed RSA PKCS#1 v1.5 SHA-256 by the shared RSA
/// key, with signed attributes (contentType = data, messageDigest = SHA-256 of `content`) and the
/// self-signed RSA certificate for `(cn, o)` embedded. This is the structure the Mach-O code
/// signature and JAR `.RSA` files carry.
pub fn cms_detached_rsa(content: &[u8], cn: &str, o: &str) -> Vec<u8> {
    let cert = self_signed_rsa(cn, o);
    let sha256_oid = seq(&[der_oid("2.16.840.1.101.3.4.2.1"), der(0x05, &[])]);
    // Signed attributes.
    let content_type = seq(&[der_oid("1.2.840.113549.1.9.3"), set(&[der_oid("1.2.840.113549.1.7.1")])]);
    let message_digest = seq(&[der_oid("1.2.840.113549.1.9.4"), set(&[der(0x04, &sha256(content))])]);
    let attrs_content = [content_type, message_digest].concat();
    let signed_attrs_set = der(0x31, &attrs_content); // the exact bytes signed
    let signature = rsa_sign_sha256(&signed_attrs_set);
    let signed_attrs_implicit = der(0xa0, &attrs_content); // [0] IMPLICIT in the SignerInfo
    let issuer_and_serial = seq(&[dn(cn, o), der(0x02, &[1, 2, 3, 4, 5])]);
    let signer_info = seq(&[
        der(0x02, &[1]),
        issuer_and_serial,
        sha256_oid.clone(),
        signed_attrs_implicit,
        seq(&[der_oid("1.2.840.113549.1.1.1"), der(0x05, &[])]),
        der(0x04, &signature),
    ]);
    let signed_data = seq(&[der(0x02, &[1]), set(&[sha256_oid]), seq(&[der_oid("1.2.840.113549.1.7.1")]), der(0xa0, &cert), set(&[signer_info])]);
    seq(&[der_oid("1.2.840.113549.1.7.2"), der(0xa0, &signed_data)])
}

// ---------------------------------------------------------------------------------------------
// APK v2/v3 content digest and signers (genuinely signed).

/// The APK v2/v3 SHA-256 content digest over an unsigned ZIP, with `block_offset` the position the
/// signing block will occupy (the ZIP's original central-directory offset). Mirrors the scheme in
/// `craft-anything-formats::verify`, reimplemented here so the fixtures do not depend on it.
pub fn apk_content_digest_sha256(zip: &[u8], block_offset: usize) -> [u8; 32] {
    let eocd = zip.len() - 22;
    let cd_off = u32::from_le_bytes(zip[eocd + 16..eocd + 20].try_into().unwrap()) as usize;
    let section1 = &zip[0..block_offset];
    let section3 = &zip[cd_off..eocd];
    let mut section4 = zip[eocd..].to_vec();
    section4[16..20].copy_from_slice(&(block_offset as u32).to_le_bytes());
    let mut chunk_digests = Vec::new();
    let mut count = 0u32;
    for section in [section1, section3, &section4] {
        for chunk in section.chunks(1024 * 1024) {
            if chunk.is_empty() {
                continue;
            }
            count += 1;
            let mut buf = vec![0xa5u8];
            buf.extend_from_slice(&(chunk.len() as u32).to_le_bytes());
            buf.extend_from_slice(chunk);
            chunk_digests.extend_from_slice(&sha256(&buf));
        }
    }
    let mut top = vec![0x5au8];
    top.extend_from_slice(&count.to_le_bytes());
    top.extend_from_slice(&chunk_digests);
    sha256(&top)
}

fn lp(b: &[u8]) -> Vec<u8> {
    let mut v = (b.len() as u32).to_le_bytes().to_vec();
    v.extend_from_slice(b);
    v
}

/// A genuinely-signed APK v2 (or v3) signer: the content digest (algorithm 0x0103, RSA PKCS#1 v1.5
/// SHA-256) carried in the signed data, an RSA signature over that signed data, the RSA SPKI, and
/// the self-signed RSA certificate. `tamper_sig` flips a byte of the signature.
pub fn apk_rsa_signer(v3: bool, cn: &str, o: &str, content_digest: &[u8; 32], tamper_sig: bool) -> Vec<u8> {
    let cert = self_signed_rsa(cn, o);
    let pubkey = rsa_spki();
    let mut digest_item = 0x0103u32.to_le_bytes().to_vec();
    digest_item.extend(lp(content_digest));
    let mut signed = lp(&lp(&digest_item)); // digests
    signed.extend(lp(&lp(&cert))); // certificates
    if v3 {
        signed.extend(24u32.to_le_bytes());
        signed.extend(0x7fff_ffffu32.to_le_bytes());
    }
    signed.extend(lp(&[])); // additional attributes
    let mut signature = rsa_sign_sha256(&signed);
    if tamper_sig && !signature.is_empty() {
        signature[0] ^= 0xff;
    }
    let mut sig_item = 0x0103u32.to_le_bytes().to_vec();
    sig_item.extend(lp(&signature));
    let mut s = lp(&signed);
    if v3 {
        s.extend(24u32.to_le_bytes());
        s.extend(0x7fff_ffffu32.to_le_bytes());
    }
    s.extend(lp(&lp(&sig_item))); // signatures
    s.extend(lp(&pubkey)); // public key
    lp(&lp(&s))
}
