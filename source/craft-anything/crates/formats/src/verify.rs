//! Public-key signature verification for code signatures, with pure-Rust RustCrypto back-ends
//! (RSA PKCS#1 v1.5 and PSS via `rsa`, ECDSA P-256/P-384 via `p256`/`p384`). Everything here is
//! honest about what it proves: a result is reported `valid` only when a cryptographic verify
//! returned success, `invalid` when it failed, and `unsupported` when we cannot check the
//! algorithm at all — never `valid` by default. Authenticity (a chain to a trusted root) is
//! reported separately from integrity/validity of a single signature.
//!
//! Wired into the Mach-O code-signature CMS (`verify_macho_cms`), the APK v2/v3 signing block
//! (`verify_apk_signer`) and the APK v1 (JAR) scheme (`verify_pkcs7_detached` + the JAR helpers).

use crate::der;
use crate::pkcs7;
use rsa::signature::Verifier as _;
use serde::Serialize;
use sha2::Digest as _;

// X.509 / PKCS algorithm OIDs.
const RSA_ENCRYPTION: &str = "1.2.840.113549.1.1.1";
const RSA_PSS: &str = "1.2.840.113549.1.1.10";
const EC_PUBLIC_KEY: &str = "1.2.840.10045.2.1";

/// A message-digest algorithm.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Digest {
    Sha1,
    Sha256,
    Sha384,
    Sha512,
}

impl Digest {
    pub fn hash(self, data: &[u8]) -> Vec<u8> {
        match self {
            Digest::Sha1 => sha1::Sha1::digest(data).to_vec(),
            Digest::Sha256 => sha2::Sha256::digest(data).to_vec(),
            Digest::Sha384 => sha2::Sha384::digest(data).to_vec(),
            Digest::Sha512 => sha2::Sha512::digest(data).to_vec(),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Digest::Sha1 => "sha1",
            Digest::Sha256 => "sha256",
            Digest::Sha384 => "sha384",
            Digest::Sha512 => "sha512",
        }
    }
}

/// A public-key signature scheme.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum SigScheme {
    RsaPkcs1v15(Digest),
    RsaPss(Digest),
    Ecdsa(Digest),
}

/// Hash several byte ranges as one message, without copying them together.
pub fn hash_parts(digest: Digest, parts: &[&[u8]]) -> Vec<u8> {
    fn run<D: sha2::Digest>(parts: &[&[u8]]) -> Vec<u8> {
        let mut h = D::new();
        for p in parts {
            h.update(p);
        }
        h.finalize().to_vec()
    }
    match digest {
        Digest::Sha1 => run::<sha1::Sha1>(parts),
        Digest::Sha256 => run::<sha2::Sha256>(parts),
        Digest::Sha384 => run::<sha2::Sha384>(parts),
        Digest::Sha512 => run::<sha2::Sha512>(parts),
    }
}

/// The signature algorithm OID of an X.509 `signatureAlgorithm` or CMS `signatureAlgorithm`.
pub fn scheme_from_oid(oid: &str) -> Option<SigScheme> {
    Some(match oid {
        "1.2.840.113549.1.1.5" => SigScheme::RsaPkcs1v15(Digest::Sha1),
        "1.2.840.113549.1.1.11" => SigScheme::RsaPkcs1v15(Digest::Sha256),
        "1.2.840.113549.1.1.12" => SigScheme::RsaPkcs1v15(Digest::Sha384),
        "1.2.840.113549.1.1.13" => SigScheme::RsaPkcs1v15(Digest::Sha512),
        // RSASSA-PSS: the hash lives in the parameters; code-signing uses SHA-256 overwhelmingly.
        "1.2.840.113549.1.1.10" => SigScheme::RsaPss(Digest::Sha256),
        "1.2.840.10045.4.3.2" => SigScheme::Ecdsa(Digest::Sha256),
        "1.2.840.10045.4.3.3" => SigScheme::Ecdsa(Digest::Sha384),
        "1.2.840.10045.4.3.4" => SigScheme::Ecdsa(Digest::Sha512),
        _ => return None,
    })
}

/// The outcome of one verification. `valid` only ever means a cryptographic verify succeeded.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "status", rename_all = "lowercase")]
pub enum Verified {
    Valid,
    Invalid,
    Unsupported { reason: String },
}

impl Verified {
    pub fn is_valid(&self) -> bool {
        matches!(self, Verified::Valid)
    }
    fn unsupported(reason: impl Into<String>) -> Self {
        Verified::Unsupported { reason: reason.into() }
    }
}

fn hexs(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn sha256_hex(b: &[u8]) -> String {
    hexs(&sha2::Sha256::digest(b))
}

// ---------------------------------------------------------------------------------------------
// Primitive: verify one signature against a SubjectPublicKeyInfo.

/// Verify `sig` over `msg` with `scheme`, using the public key in `spki` (a DER
/// `SubjectPublicKeyInfo`). Returns `Valid` only when the crate's verify succeeded.
pub fn verify_signature(spki: &[u8], scheme: SigScheme, msg: &[u8], sig: &[u8]) -> Verified {
    let Some((alg_oid, key)) = der::spki_parts(spki) else {
        return Verified::unsupported("public key could not be parsed");
    };
    match scheme {
        SigScheme::RsaPkcs1v15(d) => {
            if alg_oid != RSA_ENCRYPTION {
                return Verified::unsupported(format!("PKCS#1 v1.5 signature but key is {alg_oid}"));
            }
            rsa_pkcs1v15(key, d, msg, sig)
        }
        SigScheme::RsaPss(d) => {
            if alg_oid != RSA_ENCRYPTION && alg_oid != RSA_PSS {
                return Verified::unsupported(format!("RSASSA-PSS signature but key is {alg_oid}"));
            }
            rsa_pss(key, d, msg, sig)
        }
        SigScheme::Ecdsa(d) => {
            if alg_oid != EC_PUBLIC_KEY {
                return Verified::unsupported(format!("ECDSA signature but key is {alg_oid}"));
            }
            ecdsa(key, d, msg, sig)
        }
    }
}

fn rsa_key(pkcs1_der: &[u8]) -> Option<rsa::RsaPublicKey> {
    use rsa::pkcs1::DecodeRsaPublicKey;
    rsa::RsaPublicKey::from_pkcs1_der(pkcs1_der).ok()
}

fn rsa_pkcs1v15(pkcs1_der: &[u8], d: Digest, msg: &[u8], sig: &[u8]) -> Verified {
    let Some(key) = rsa_key(pkcs1_der) else { return Verified::Invalid };
    let Ok(signature) = rsa::pkcs1v15::Signature::try_from(sig) else { return Verified::Invalid };
    let ok = match d {
        Digest::Sha1 => rsa::pkcs1v15::VerifyingKey::<sha1::Sha1>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha256 => rsa::pkcs1v15::VerifyingKey::<sha2::Sha256>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha384 => rsa::pkcs1v15::VerifyingKey::<sha2::Sha384>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha512 => rsa::pkcs1v15::VerifyingKey::<sha2::Sha512>::new(key).verify(msg, &signature).is_ok(),
    };
    if ok { Verified::Valid } else { Verified::Invalid }
}

fn rsa_pss(pkcs1_der: &[u8], d: Digest, msg: &[u8], sig: &[u8]) -> Verified {
    let Some(key) = rsa_key(pkcs1_der) else { return Verified::Invalid };
    let Ok(signature) = rsa::pss::Signature::try_from(sig) else { return Verified::Invalid };
    let ok = match d {
        Digest::Sha256 => rsa::pss::VerifyingKey::<sha2::Sha256>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha384 => rsa::pss::VerifyingKey::<sha2::Sha384>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha512 => rsa::pss::VerifyingKey::<sha2::Sha512>::new(key).verify(msg, &signature).is_ok(),
        Digest::Sha1 => return Verified::unsupported("RSASSA-PSS with SHA-1 is not checked"),
    };
    if ok { Verified::Valid } else { Verified::Invalid }
}

/// ECDSA over a SEC1 public-key point. The curve is chosen by point length (P-256 vs P-384); the
/// digest used is the curve's standard one, so non-standard curve/hash pairings are reported
/// unsupported rather than guessed.
fn ecdsa(sec1: &[u8], d: Digest, msg: &[u8], der_sig: &[u8]) -> Verified {
    match sec1.len() {
        33 | 65 => {
            if d != Digest::Sha256 {
                return Verified::unsupported(format!("ECDSA P-256 with {} is not checked", d.name()));
            }
            use p256::ecdsa::{Signature, VerifyingKey, signature::Verifier};
            let Ok(vk) = VerifyingKey::from_sec1_bytes(sec1) else { return Verified::Invalid };
            let Ok(s) = Signature::from_der(der_sig) else { return Verified::Invalid };
            if vk.verify(msg, &s).is_ok() { Verified::Valid } else { Verified::Invalid }
        }
        49 | 97 => {
            if d != Digest::Sha384 {
                return Verified::unsupported(format!("ECDSA P-384 with {} is not checked", d.name()));
            }
            use p384::ecdsa::{Signature, VerifyingKey, signature::Verifier};
            let Ok(vk) = VerifyingKey::from_sec1_bytes(sec1) else { return Verified::Invalid };
            let Ok(s) = Signature::from_der(der_sig) else { return Verified::Invalid };
            if vk.verify(msg, &s).is_ok() { Verified::Valid } else { Verified::Invalid }
        }
        n => Verified::unsupported(format!("unsupported EC public-key point length {n} (only P-256/P-384)")),
    }
}

// ---------------------------------------------------------------------------------------------
// Certificate chain.

/// Known Apple root CA certificate fingerprints: SHA-256 of the whole DER certificate.
/// Published by Apple at <https://www.apple.com/certificateauthority/>. A missing or wrong value
/// here can only ever suppress a positive "trusted root" claim; it can never create a false one,
/// because trust is only asserted on an exact match.
const APPLE_ROOTS: &[(&str, &str)] = &[
    ("Apple Root CA", "b0b1730ecbc7ff4505142c49f1295e6eda6bcaed7e2c68c5be91b5a11001f024"),
    ("Apple Root CA - G2", "c2b9b042dd57830e7d117dac55ac8ae19407d38e41d88f3215bc3a890444a050"),
    ("Apple Root CA - G3", "63343abfb89a6a03ebb57e9b3f5fa7be7c4f5c756f3017b3a8c488c3653e9179"),
];

/// One link in a certificate chain.
#[derive(Debug, Clone, Serialize)]
pub struct ChainLink {
    pub subject: String,
    pub issuer: String,
    pub sha256: String,
    /// Whether this certificate's signature was verified against its issuer in the set.
    pub signature_verified: Verified,
    pub self_signed: bool,
}

/// The result of walking a certificate chain.
#[derive(Debug, Clone, Serialize)]
pub struct ChainResult {
    pub links: Vec<ChainLink>,
    /// Every non-root link verified against its issuer.
    pub fully_linked: bool,
    pub root_subject: Option<String>,
    pub root_sha256: Option<String>,
    /// `Some(name)` when the top certificate's SHA-256 matches a bundled trusted Apple root.
    pub trusted_root: Option<&'static str>,
    pub notes: Vec<String>,
}

/// Verify `child`'s signature against `issuer`'s public key.
fn verify_cert_by(child: &[u8], issuer: &[u8]) -> Verified {
    let (Some(c), Some(i)) = (der::certificate_parts(child), der::certificate_parts(issuer)) else {
        return Verified::unsupported("certificate could not be parsed");
    };
    match scheme_from_oid(&c.signature_algorithm) {
        Some(scheme) => verify_signature(i.spki, scheme, c.tbs, c.signature),
        None => Verified::unsupported(format!("signature algorithm {} is not checked", c.signature_algorithm)),
    }
}

/// Walk and verify a certificate chain, starting from `certs[0]` (the leaf/signer) and following
/// issuer→subject links through the provided set. Bounded; tolerant of missing issuers.
pub fn verify_chain(certs: &[&[u8]]) -> ChainResult {
    let mut links: Vec<ChainLink> = Vec::new();
    let mut notes = Vec::new();
    let mut fully_linked = true;
    let mut seen: Vec<String> = Vec::new();
    let Some(&first) = certs.first() else {
        return ChainResult { links, fully_linked: false, root_subject: None, root_sha256: None, trusted_root: None, notes: vec!["no certificates".into()] };
    };
    let mut current = first;
    for _ in 0..certs.len().min(16) {
        let Some(parts) = der::certificate_parts(current) else {
            notes.push("a certificate in the chain could not be parsed".into());
            fully_linked = false;
            break;
        };
        let sha = sha256_hex(current);
        if seen.contains(&sha) {
            notes.push("certificate chain loops; stopped".into());
            break;
        }
        seen.push(sha.clone());
        let self_signed = parts.subject == parts.issuer;
        let info = der::certificate(current);
        let subject = info.as_ref().map(|c| c.subject.clone()).unwrap_or_default();
        let issuer = info.as_ref().map(|c| c.issuer.clone()).unwrap_or_default();
        // Find the issuer certificate in the set (by matching DN), else self for a root.
        let issuer_cert =
            if self_signed { Some(current) } else { certs.iter().copied().find(|c| der::certificate_parts(c).is_some_and(|p| p.subject == parts.issuer)) };
        let signature_verified = match issuer_cert {
            Some(ic) => verify_cert_by(current, ic),
            None => {
                fully_linked = false;
                Verified::unsupported("issuer certificate not present in the signature")
            }
        };
        if !signature_verified.is_valid() && issuer_cert.is_some() {
            fully_linked = false;
        }
        links.push(ChainLink { subject, issuer, sha256: sha, signature_verified, self_signed });
        if self_signed {
            break;
        }
        match issuer_cert {
            Some(ic) if ic != current => current = ic,
            _ => break,
        }
    }
    let (root_subject, root_sha256, trusted_root) = match links.last() {
        Some(top) => {
            let trusted = top.self_signed.then(|| APPLE_ROOTS.iter().find(|(_, fp)| *fp == top.sha256).map(|(n, _)| *n)).flatten();
            if top.self_signed && trusted.is_none() {
                notes.push("chain not verified to a trusted root: the top certificate is self-signed but not a bundled Apple root".into());
            } else if !top.self_signed {
                notes.push("chain not verified to a trusted root: no self-signed root certificate was reached".into());
            }
            (Some(top.subject.clone()), Some(top.sha256.clone()), trusted)
        }
        None => (None, None, None),
    };
    ChainResult { links, fully_linked, root_subject, root_sha256, trusted_root, notes }
}

// ---------------------------------------------------------------------------------------------
// Mach-O CMS.

/// The result of verifying a Mach-O code-signature CMS blob against its CodeDirectory.
#[derive(Debug, Clone, Serialize)]
pub struct MachoCms {
    /// The signer's signature over the signed attributes verified cryptographically.
    pub signature_valid: Verified,
    /// The `messageDigest` signed attribute matched the hash of the CodeDirectory, so the
    /// signature covers this exact CodeDirectory.
    pub binds_code_directory: bool,
    /// Overall: `signature_valid` is Valid AND it binds the CodeDirectory.
    pub authenticated: bool,
    pub digest_algorithm: Option<&'static str>,
    pub signer_subject: Option<String>,
    pub signer_issuer: Option<String>,
    pub not_before: Option<String>,
    pub not_after: Option<String>,
    pub certificate_count: usize,
    pub chain: ChainResult,
    pub notes: Vec<String>,
}

/// Verify a detached CMS `SignedData` (the Mach-O CMS blob) against the primary CodeDirectory.
pub fn verify_macho_cms(cms_der: &[u8], code_directory: &[u8]) -> Option<MachoCms> {
    let sd = pkcs7::parse_signed_data(cms_der)?;
    let mut notes = Vec::new();
    let signer = sd.signer_cert().map(<[u8]>::to_vec);
    let info = signer.as_deref().and_then(der::certificate);
    // Does the signed messageDigest attribute cover this CodeDirectory?
    let binds_code_directory = match (&sd.message_digest, sd.digest) {
        (Some(md), Some(d)) => hexs(&d.hash(code_directory)).eq_ignore_ascii_case(md),
        _ => {
            notes.push("no messageDigest signed attribute; cannot tie the signature to this CodeDirectory".into());
            false
        }
    };
    // Verify the signer's signature over the (re-encoded) signed attributes.
    let signature_valid = match (sd.scheme(), sd.signed_attrs_reencoded.as_deref(), signer.as_deref()) {
        (Some(scheme), Some(attrs), Some(cert)) => match der::certificate_spki(cert) {
            Some(spki) => verify_signature(spki, scheme, attrs, &sd.signature),
            None => Verified::unsupported("signer public key could not be read"),
        },
        (None, _, _) => Verified::unsupported(format!("signature algorithm {} is not checked", sd.signature_algorithm)),
        (_, None, _) => Verified::unsupported("CMS carries no signed attributes; this detached form is not checked"),
        (_, _, None) => Verified::unsupported("no signer certificate"),
    };
    let certs: Vec<&[u8]> = ordered_certs(&sd);
    let chain = verify_chain(&certs);
    let authenticated = signature_valid.is_valid() && binds_code_directory;
    Some(MachoCms {
        signature_valid,
        binds_code_directory,
        authenticated,
        digest_algorithm: sd.digest.map(Digest::name),
        signer_subject: info.as_ref().map(|c| c.subject.clone()),
        signer_issuer: info.as_ref().map(|c| c.issuer.clone()),
        not_before: info.as_ref().map(|c| c.not_before.clone()),
        not_after: info.as_ref().map(|c| c.not_after.clone()),
        certificate_count: sd.certificates.len(),
        chain,
        notes,
    })
}

/// Order a CMS certificate set so the signer's certificate is first (chain verification starts
/// from the leaf).
fn ordered_certs(sd: &pkcs7::SignedData) -> Vec<&[u8]> {
    let signer = sd.signer_cert();
    let mut out: Vec<&[u8]> = Vec::new();
    if let Some(s) = signer {
        out.push(s);
    }
    for c in &sd.certificates {
        if Some(c.as_slice()) != signer {
            out.push(c);
        }
    }
    out
}

// ---------------------------------------------------------------------------------------------
// APK signature scheme v2 / v3.

/// The result of verifying one APK v2/v3 signer.
#[derive(Debug, Clone, Serialize)]
pub struct ApkSigner {
    pub scheme: &'static str,
    /// A signature over the signed-data block verified cryptographically.
    pub signature_valid: Verified,
    /// The recomputed APK content digest matched the digest inside the signed data.
    pub digest_matches: bool,
    /// The signer's first certificate's public key matched the signing public key.
    pub public_key_matches_certificate: bool,
    /// Overall: signature valid AND content digest matches AND key matches the certificate.
    pub verified: bool,
    pub algorithm: Option<String>,
    /// SHA-256 of the signer's first certificate: the fingerprint users compare.
    pub certificate_sha256: Option<String>,
    pub min_sdk: Option<u32>,
    pub max_sdk: Option<u32>,
    pub notes: Vec<String>,
}

/// Map an APK signature-algorithm id to `(scheme, content-digest, algorithm name)`.
fn apk_algorithm(id: u32) -> Option<(SigScheme, Digest, bool)> {
    // The bool is `true` for the "verity" (Merkle-tree) content digests we do not recompute.
    Some(match id {
        0x0101 => (SigScheme::RsaPss(Digest::Sha256), Digest::Sha256, false),
        0x0102 => (SigScheme::RsaPss(Digest::Sha512), Digest::Sha512, false),
        0x0103 => (SigScheme::RsaPkcs1v15(Digest::Sha256), Digest::Sha256, false),
        0x0104 => (SigScheme::RsaPkcs1v15(Digest::Sha512), Digest::Sha512, false),
        0x0201 => (SigScheme::Ecdsa(Digest::Sha256), Digest::Sha256, false),
        0x0202 => (SigScheme::Ecdsa(Digest::Sha512), Digest::Sha512, false),
        0x0421 => (SigScheme::RsaPkcs1v15(Digest::Sha256), Digest::Sha256, true),
        0x0423 => (SigScheme::Ecdsa(Digest::Sha256), Digest::Sha256, true),
        // 0x0301 (DSA) and 0x0425 (DSA verity) are not supported.
        _ => return None,
    })
}

/// Verify one APK v2/v3 signer against the full APK bytes.
pub fn verify_apk_signer(apk: &[u8], block_offset: u64, signer: &crate::apk_sign::Signer) -> ApkSigner {
    let mut notes = Vec::new();
    let certificate_sha256 = signer.certificates.first().map(|c| sha256_hex(c));
    let public_key_matches_certificate = match (signer.certificates.first(), der::spki_parts(&signer.public_key)) {
        (Some(c), Some((_, _))) => der::certificate_spki(c) == Some(signer.public_key.as_slice()),
        _ => false,
    };
    if !public_key_matches_certificate {
        notes.push("the signing public key does not match the first certificate".into());
    }
    // Pick the strongest supported signature algorithm present.
    let chosen = signer
        .signatures
        .iter()
        .filter_map(|(id, sig)| apk_algorithm(*id).map(|(scheme, digest, verity)| (*id, scheme, digest, verity, sig)))
        .max_by_key(|(_, _, digest, verity, _)| (!*verity, matches!(digest, Digest::Sha512)));
    let Some((id, scheme, digest, verity, sig)) = chosen else {
        notes.push("no supported signature algorithm present (DSA and unknown ids are not checked)".into());
        return ApkSigner {
            scheme: signer.scheme,
            signature_valid: Verified::unsupported("no supported signature algorithm"),
            digest_matches: false,
            public_key_matches_certificate,
            verified: false,
            algorithm: None,
            certificate_sha256,
            min_sdk: signer.min_sdk,
            max_sdk: signer.max_sdk,
            notes,
        };
    };
    let signature_valid = verify_signature(&signer.public_key, scheme, &signer.signed_data, sig);
    // Recompute the APK content digest for this algorithm and compare to the one in signed data.
    let digest_matches = if verity {
        notes.push("the verity (Merkle-tree) content digest is not recomputed; the signature over the signed data is still verified".into());
        false
    } else {
        match signer.signed_digests.iter().find(|(did, _)| *did == id) {
            Some((_, stored)) => match apk_content_digest(apk, block_offset, digest) {
                Some(computed) => computed == *stored,
                None => {
                    notes.push("the APK content digest could not be recomputed (unreadable ZIP layout)".into());
                    false
                }
            },
            None => {
                notes.push("the signed data carries no digest for the verified signature algorithm".into());
                false
            }
        }
    };
    let verified = signature_valid.is_valid() && digest_matches && public_key_matches_certificate;
    ApkSigner {
        scheme: signer.scheme,
        signature_valid,
        digest_matches,
        public_key_matches_certificate,
        verified,
        algorithm: Some(crate::apk_sign::algorithm_name(id).to_string()),
        certificate_sha256,
        min_sdk: signer.min_sdk,
        max_sdk: signer.max_sdk,
        notes,
    }
}

/// The APK v2/v3 content digest: 1 MiB chunks of (ZIP entries | central directory | end-of-central
/// -directory with its CD offset patched to the signing block), each hashed with a `0xa5` prefix,
/// then a top-level hash with a `0x5a` prefix. The signing block itself is excluded.
pub fn apk_content_digest(apk: &[u8], block_offset: u64, d: Digest) -> Option<Vec<u8>> {
    let r = crate::bytes::Reader::new(apk);
    // Locate the end-of-central-directory record and the central directory.
    let from = apk.len().saturating_sub(22 + 0xffff);
    let mut eocd = None;
    let mut i = apk.len().checked_sub(22)?;
    while i >= from {
        if apk.get(i..i + 4) == Some(b"PK\x05\x06") {
            eocd = Some(i);
            break;
        }
        i = i.checked_sub(1)?;
    }
    let eocd = eocd?;
    let cd_off = r.u32_le(eocd + 16)? as usize;
    let bo = usize::try_from(block_offset).ok()?;
    if bo > apk.len() || cd_off > apk.len() || eocd > apk.len() || cd_off > eocd || bo > cd_off {
        return None;
    }
    let section1 = apk.get(0..bo)?;
    let section3 = apk.get(cd_off..eocd)?;
    // Section 4: the EOCD with its central-directory offset (bytes 16..20) set to the signing block.
    let mut section4 = apk.get(eocd..)?.to_vec();
    if section4.len() >= 20 {
        section4.get_mut(16..20)?.copy_from_slice(&(bo as u32).to_le_bytes());
    }
    const CHUNK: usize = 1024 * 1024;
    let mut chunk_count = 0u32;
    let mut all_chunk_digests: Vec<u8> = Vec::new();
    for section in [section1, section3, &section4] {
        for chunk in section.chunks(CHUNK) {
            if chunk.is_empty() {
                continue;
            }
            chunk_count = chunk_count.checked_add(1)?;
            let mut buf = Vec::with_capacity(5 + chunk.len());
            buf.push(0xa5);
            buf.extend_from_slice(&(chunk.len() as u32).to_le_bytes());
            buf.extend_from_slice(chunk);
            all_chunk_digests.extend_from_slice(&d.hash(&buf));
        }
    }
    let mut top = Vec::with_capacity(5 + all_chunk_digests.len());
    top.push(0x5a);
    top.extend_from_slice(&chunk_count.to_le_bytes());
    top.extend_from_slice(&all_chunk_digests);
    Some(d.hash(&top))
}

// ---------------------------------------------------------------------------------------------
// APK v1 (JAR) signatures.

/// The result of verifying one JAR (v1) signer's PKCS#7 over its signature file.
#[derive(Debug, Clone, Serialize)]
pub struct Pkcs7Signature {
    pub signature_valid: Verified,
    pub signer_subject: Option<String>,
    pub certificate_sha256: Option<String>,
    pub chain: ChainResult,
    pub notes: Vec<String>,
}

/// Verify a detached PKCS#7/CMS signature over `content` (for JAR signing, the `.SF` file bytes).
pub fn verify_pkcs7_detached(content: &[u8], pkcs7_der: &[u8]) -> Option<Pkcs7Signature> {
    let sd = pkcs7::parse_signed_data(pkcs7_der)?;
    let mut notes = Vec::new();
    let signer = sd.signer_cert().map(<[u8]>::to_vec);
    let cert_sha = signer.as_deref().map(sha256_hex);
    let subject = signer.as_deref().and_then(der::certificate).map(|c| c.subject);
    let signature_valid = match (sd.scheme(), signer.as_deref()) {
        (Some(scheme), Some(cert)) => {
            let Some(spki) = der::certificate_spki(cert) else {
                return Some(Pkcs7Signature {
                    signature_valid: Verified::unsupported("signer key unreadable"),
                    signer_subject: subject,
                    certificate_sha256: cert_sha,
                    chain: verify_chain(&ordered_certs(&sd)),
                    notes,
                });
            };
            match sd.signed_attrs_reencoded.as_deref() {
                // Signed attributes present: the signature covers them; messageDigest must equal H(content).
                Some(attrs) => {
                    let binds = match (&sd.message_digest, sd.digest) {
                        (Some(md), Some(dd)) => hexs(&dd.hash(content)).eq_ignore_ascii_case(md),
                        _ => false,
                    };
                    if !binds {
                        notes.push("the signed messageDigest does not match the signature file".into());
                    }
                    let v = verify_signature(spki, scheme, attrs, &sd.signature);
                    if v.is_valid() && binds {
                        Verified::Valid
                    } else if v.is_valid() {
                        Verified::Invalid
                    } else {
                        v
                    }
                }
                // Classic JAR signing: the signature is over the raw .SF content.
                None => verify_signature(spki, scheme, content, &sd.signature),
            }
        }
        (None, _) => Verified::unsupported(format!("signature algorithm {} is not checked", sd.signature_algorithm)),
        (_, None) => Verified::unsupported("no signer certificate"),
    };
    Some(Pkcs7Signature { signature_valid, signer_subject: subject, certificate_sha256: cert_sha, chain: verify_chain(&ordered_certs(&sd)), notes })
}

/// A parsed entry of a JAR manifest/signature file: its name and digest attributes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct JarSection {
    pub name: Option<String>,
    /// Attribute key → value, with any continuation lines joined.
    pub attrs: Vec<(String, String)>,
}

/// Parse a JAR `MANIFEST.MF` or `.SF` file into its main section and per-entry sections.
/// Handles the 72-byte line-folding (continuation lines begin with a single space).
pub fn parse_jar_sections(data: &[u8]) -> Vec<JarSection> {
    let text = String::from_utf8_lossy(data);
    let mut logical: Vec<String> = Vec::new();
    for raw in text.split('\n') {
        let line = raw.strip_suffix('\r').unwrap_or(raw);
        if let Some(rest) = line.strip_prefix(' ')
            && let Some(last) = logical.last_mut()
        {
            last.push_str(rest);
            continue;
        }
        logical.push(line.to_string());
    }
    let mut sections = Vec::new();
    let mut attrs: Vec<(String, String)> = Vec::new();
    let mut name = None;
    let flush = |attrs: &mut Vec<(String, String)>, name: &mut Option<String>, sections: &mut Vec<JarSection>| {
        if !attrs.is_empty() || name.is_some() {
            sections.push(JarSection { name: name.take(), attrs: std::mem::take(attrs) });
        }
    };
    for line in logical {
        if line.is_empty() {
            flush(&mut attrs, &mut name, &mut sections);
            continue;
        }
        if let Some((k, v)) = line.split_once(':') {
            let k = k.trim().to_string();
            let v = v.trim().to_string();
            if k.eq_ignore_ascii_case("Name") {
                name = Some(v);
            } else {
                attrs.push((k, v));
            }
        }
    }
    flush(&mut attrs, &mut name, &mut sections);
    sections
}

fn attr<'a>(section: &'a JarSection, key: &str) -> Option<&'a str> {
    section.attrs.iter().find(|(k, _)| k.eq_ignore_ascii_case(key)).map(|(_, v)| v.as_str())
}

/// Standard base64 (RFC 4648, padded), the encoding JAR digests use.
pub fn base64(data: &[u8]) -> String {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [chunk.first().copied().unwrap_or(0), chunk.get(1).copied().unwrap_or(0), chunk.get(2).copied().unwrap_or(0)];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        out.push(T[(n >> 18 & 63) as usize] as char);
        out.push(T[(n >> 12 & 63) as usize] as char);
        out.push(if chunk.len() > 1 { T[(n >> 6 & 63) as usize] as char } else { '=' });
        out.push(if chunk.len() > 2 { T[(n & 63) as usize] as char } else { '=' });
    }
    out
}

/// The digest (and its algorithm) a JAR section records, trying SHA-256 then SHA-1.
fn section_digest(section: &JarSection, suffix: &str) -> Option<(Digest, String)> {
    for (d, prefix) in [(Digest::Sha256, "SHA-256"), (Digest::Sha512, "SHA-512"), (Digest::Sha1, "SHA1")] {
        if let Some(v) = attr(section, &format!("{prefix}-Digest{suffix}")) {
            return Some((d, v.to_string()));
        }
    }
    None
}

/// The outcome of checking a JAR (v1) MANIFEST.MF against the files it lists.
#[derive(Debug, Clone, Serialize)]
pub struct JarIntegrity {
    /// The `.SF` file's recorded digest of the whole manifest matched.
    pub manifest_digest_matches: Option<bool>,
    pub files_listed: usize,
    pub files_matched: usize,
    pub files_mismatched: usize,
    pub files_unchecked: usize,
    pub mismatched_names: Vec<String>,
    pub notes: Vec<String>,
}

/// Check a JAR signature file's manifest digest and every per-file digest in MANIFEST.MF.
/// `read_entry(name)` returns the uncompressed bytes of a named ZIP entry (or `None` if absent).
pub fn verify_jar_integrity(manifest_mf: &[u8], sf: &[u8], mut read_entry: impl FnMut(&str) -> Option<Vec<u8>>) -> JarIntegrity {
    let mut notes = Vec::new();
    let sf_sections = parse_jar_sections(sf);
    let manifest_digest_matches = sf_sections.first().and_then(|main| section_digest(main, "-Manifest").map(|(d, want)| base64(&d.hash(manifest_mf)) == want));
    if manifest_digest_matches.is_none() {
        notes.push("the signature file records no whole-manifest digest; per-file digests are still checked".into());
    }
    let sections = parse_jar_sections(manifest_mf);
    let mut files_listed = 0;
    let mut files_matched = 0;
    let mut files_mismatched = 0;
    let mut files_unchecked = 0;
    let mut mismatched_names = Vec::new();
    for s in sections.iter().filter(|s| s.name.is_some()) {
        let Some(name) = &s.name else { continue };
        files_listed += 1;
        let Some((d, want)) = section_digest(s, "") else {
            files_unchecked += 1;
            continue;
        };
        match read_entry(name) {
            Some(bytes) => {
                if base64(&d.hash(&bytes)) == want {
                    files_matched += 1;
                } else {
                    files_mismatched += 1;
                    if mismatched_names.len() < 32 {
                        mismatched_names.push(name.clone());
                    }
                }
            }
            None => files_unchecked += 1,
        }
    }
    JarIntegrity { manifest_digest_matches, files_listed, files_matched, files_mismatched, files_unchecked, mismatched_names, notes }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_vectors() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foo"), "Zm9v");
        assert_eq!(base64(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn scheme_oids() {
        assert_eq!(scheme_from_oid("1.2.840.113549.1.1.11"), Some(SigScheme::RsaPkcs1v15(Digest::Sha256)));
        assert_eq!(scheme_from_oid("1.2.840.10045.4.3.2"), Some(SigScheme::Ecdsa(Digest::Sha256)));
        assert_eq!(scheme_from_oid("1.2.840.113549.1.1.4"), None);
    }

    #[test]
    fn jar_section_folding() {
        let mf = b"Manifest-Version: 1.0\r\nCreated-By: test\r\n\r\nName: a/b/really-long-\r\n name.txt\r\nSHA-256-Digest: AAA=\r\n\r\n";
        let s = parse_jar_sections(mf);
        assert_eq!(s.len(), 2);
        assert_eq!(s[1].name.as_deref(), Some("a/b/really-long-name.txt"));
        assert_eq!(attr(&s[1], "SHA-256-Digest"), Some("AAA="));
    }

    #[test]
    fn unsupported_is_never_valid_on_garbage() {
        // Random bytes must never verify as Valid.
        for seed in 0..64 {
            let n = craft_anything_testkit::noise(seed, 200);
            let v = verify_signature(&n, SigScheme::RsaPkcs1v15(Digest::Sha256), &n, &n);
            assert!(!v.is_valid());
            let _ = verify_macho_cms(&n, &n);
            let _ = parse_jar_sections(&n);
        }
    }

    #[test]
    fn rsa_signature_round_trip_and_tamper() {
        use craft_anything_testkit::crypto;
        let (spki, sign) = crypto::rsa_signer();
        let msg = b"the exact bytes that were signed";
        let sig = sign(msg, 0);
        assert!(verify_signature(&spki, SigScheme::RsaPkcs1v15(Digest::Sha256), msg, &sig).is_valid());
        // A flipped message byte must not verify.
        let mut bad = msg.to_vec();
        bad[0] ^= 0xff;
        assert_eq!(verify_signature(&spki, SigScheme::RsaPkcs1v15(Digest::Sha256), &bad, &sig), Verified::Invalid);
        // A flipped signature byte must not verify.
        let mut bad_sig = sig.clone();
        bad_sig[0] ^= 0xff;
        assert_eq!(verify_signature(&spki, SigScheme::RsaPkcs1v15(Digest::Sha256), msg, &bad_sig), Verified::Invalid);
    }

    #[test]
    fn ecdsa_p256_round_trip() {
        use craft_anything_testkit::crypto;
        let (spki, sign) = crypto::p256_signer();
        let msg = b"ecdsa message";
        let sig = sign(msg);
        assert!(verify_signature(&spki, SigScheme::Ecdsa(Digest::Sha256), msg, &sig).is_valid());
        let mut bad = msg.to_vec();
        bad[0] ^= 1;
        assert_eq!(verify_signature(&spki, SigScheme::Ecdsa(Digest::Sha256), &bad, &sig), Verified::Invalid);
    }

    #[test]
    fn chain_links_and_self_signed() {
        use craft_anything_testkit::crypto;
        // Leaf signed by a self-signed CA: the leaf link verifies against the CA.
        let (leaf, ca) = crypto::cert_chain();
        let chain = verify_chain(&[&leaf, &ca]);
        assert!(chain.links[0].signature_verified.is_valid(), "{:?}", chain.links[0]);
        assert!(chain.links.last().unwrap().self_signed);
        // The top is self-signed but not a bundled Apple root, so it is not trusted.
        assert!(chain.trusted_root.is_none());
        assert!(chain.notes.iter().any(|n| n.contains("not verified to a trusted root")));
        // A single self-signed certificate verifies against itself.
        let ss = crypto::self_signed_rsa("Solo", "Org");
        assert!(verify_chain(&[&ss]).links[0].signature_verified.is_valid());
    }

    #[test]
    fn macho_cms_verifies_and_detects_tamper() {
        use craft_anything_testkit::{apple, crypto};
        let cd = apple::code_directory_blob();
        let cms = crypto::cms_detached_rsa(&cd, "Craft Signer", "Craft Org");
        let r = verify_macho_cms(&cms, &cd).expect("parse");
        assert!(r.signature_valid.is_valid(), "{:?}", r);
        assert!(r.binds_code_directory);
        assert!(r.authenticated);
        // A changed CodeDirectory no longer matches the signed messageDigest.
        let mut bad_cd = cd.clone();
        bad_cd[100] ^= 0xff;
        let r2 = verify_macho_cms(&cms, &bad_cd).expect("parse");
        assert!(!r2.binds_code_directory);
        assert!(!r2.authenticated);
    }

    #[test]
    fn apk_signer_verifies_and_detects_tamper() {
        use craft_anything_testkit::android;
        let apk = android::signed_apk(false);
        let block = crate::apk_sign::parse(&apk).expect("signing block");
        assert!(!block.signers.is_empty());
        for s in &block.signers {
            let r = verify_apk_signer(&apk, block.offset, s);
            assert!(r.signature_valid.is_valid(), "{}: {:?}", s.scheme, r);
            assert!(r.digest_matches, "{}: {:?}", s.scheme, r);
            assert!(r.public_key_matches_certificate);
            assert!(r.verified);
            assert_eq!(r.certificate_sha256.as_ref().unwrap().len(), 64);
        }
        // Tampering a content byte breaks the digest but not the (well-formed) signature.
        let bad = android::signed_apk(true);
        let bblock = crate::apk_sign::parse(&bad).expect("block");
        let r = verify_apk_signer(&bad, bblock.offset, &bblock.signers[0]);
        assert!(!r.digest_matches);
        assert!(!r.verified);
    }

    #[test]
    fn apk_content_digest_matches_reference() {
        use craft_anything_testkit::{android, crypto};
        let apk = android::signed_apk(false);
        let block = crate::apk_sign::parse(&apk).unwrap();
        let computed = apk_content_digest(&apk, block.offset, Digest::Sha256).unwrap();
        // The digest recorded in the signed data (algorithm 0x0103 = SHA-256) must match.
        let stored = &block.signers[0].signed_digests.iter().find(|(id, _)| *id == 0x0103).unwrap().1;
        assert_eq!(&computed, stored);
        // And it matches the independent testkit reference computation over the same APK.
        assert_eq!(computed, crypto::apk_content_digest_sha256(&apk, block.offset as usize).to_vec());
    }

    #[test]
    fn jar_v1_integrity_and_pkcs7() {
        use craft_anything_testkit::{android, crypto};
        // Build the same .SF/.RSA the signed APK carries and verify the PKCS#7 over the .SF.
        let sf = b"Signature-Version: 1.0\r\nSHA-256-Digest-Manifest: AAA=\r\n\r\n";
        let rsa = crypto::cms_detached_rsa(sf, "Craft Signer", "Craft Org");
        let v = verify_pkcs7_detached(sf, &rsa).expect("pkcs7");
        assert!(v.signature_valid.is_valid(), "{:?}", v);
        assert_eq!(v.certificate_sha256.as_ref().unwrap().len(), 64);
        // A changed signature file no longer matches the signed messageDigest.
        let v2 = verify_pkcs7_detached(b"tampered", &rsa).expect("pkcs7");
        assert!(!v2.signature_valid.is_valid());
        // Full JAR integrity against a built manifest.
        let apk = android::signed_apk(false);
        let z = crate::zip::parse(&apk, 10_000).unwrap();
        let read = |name: &str| -> Option<Vec<u8>> {
            let e = z.entries.iter().find(|e| e.name == name)?;
            crate::zip::read_entry(&apk, e, 4 << 20).ok()
        };
        let mf = read("META-INF/MANIFEST.MF").unwrap();
        let sf = read("META-INF/CERT.SF").unwrap();
        let integ = verify_jar_integrity(&mf, &sf, read);
        assert_eq!(integ.manifest_digest_matches, Some(true), "{integ:?}");
        assert!(integ.files_listed >= 3);
        assert_eq!(integ.files_mismatched, 0, "{integ:?}");
        assert!(integ.files_matched >= 3);
    }
}
