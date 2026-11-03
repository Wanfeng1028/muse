//! TOTP（RFC 6238 / RFC 4226）核心 + TOTP 密钥落库加密（AES-256-GCM）。
//! v1.11.0 新增。

pub fn base32_encode(data: &[u8]) -> String {
    const ALPHABET: &[u8; 32] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    let mut result = String::new();
    let mut buffer: u64 = 0;
    let mut bits = 0u32;

    for &byte in data {
        buffer = (buffer << 8) | byte as u64;
        bits += 8;
        while bits >= 5 {
            bits -= 5;
            let index = ((buffer >> bits) & 0x1F) as usize;
            result.push(ALPHABET[index] as char);
        }
    }

    if bits > 0 {
        let index = ((buffer << (5 - bits)) & 0x1F) as usize;
        result.push(ALPHABET[index] as char);
    }

    // Pad to multiple of 8
    let pad_needed = (8 - result.len() % 8) % 8;
    for _ in 0..pad_needed {
        result.push('=');
    }

    result
}

pub fn base32_decode(s: &str) -> Result<Vec<u8>, String> {
    const ALPHABET: &str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

    // Filter whitespace and convert to uppercase
    let filtered: Vec<char> = s
        .chars()
        .filter(|c| !c.is_whitespace())
        .map(|c| c.to_ascii_uppercase())
        .collect();

    // Check for invalid characters and separate padding
    let mut chars_no_pad = Vec::new();
    let mut seen_pad = false;
    for &c in &filtered {
        if c == '=' {
            seen_pad = true;
        } else if ALPHABET.contains(c) {
            if seen_pad {
                // Non-padding character after padding - could be an error
                // But spec says just check for illegal chars
                // Actually, this might be fine to just accept
            }
            chars_no_pad.push(c);
        } else {
            return Err("base32 非法字符".to_string());
        }
    }

    let len = chars_no_pad.len();
    if len % 8 == 1 {
        return Err("base32 长度非法".to_string());
    }

    // Decode
    let mut result = Vec::new();
    let mut buffer: u64 = 0;
    let mut bits = 0u32;

    for &c in &chars_no_pad {
        let val = ALPHABET.find(c).unwrap() as u64;
        buffer = (buffer << 5) | val;
        bits += 5;
        while bits >= 8 {
            bits -= 8;
            result.push((buffer >> bits) as u8);
            buffer &= (1 << bits) - 1;
        }
    }

    Ok(result)
}

fn hmac_sha1(key: &[u8], msg: &[u8]) -> [u8; 20] {
    use sha1::{Digest, Sha1};

    const BLOCK_SIZE: usize = 64;

    // If key is longer than block size, hash it
    let key = if key.len() > BLOCK_SIZE {
        let hash = Sha1::digest(key);
        hash.to_vec()
    } else {
        key.to_vec()
    };

    // Pad key to block size
    let mut padded_key = [0u8; BLOCK_SIZE];
    padded_key[..key.len()].copy_from_slice(&key);

    // ipad and opad
    let mut ipad = vec![0u8; BLOCK_SIZE];
    let mut opad = vec![0u8; BLOCK_SIZE];
    for i in 0..BLOCK_SIZE {
        ipad[i] = padded_key[i] ^ 0x36;
        opad[i] = padded_key[i] ^ 0x5c;
    }

    // Inner hash
    let mut inner_hasher = Sha1::new();
    inner_hasher.update(&ipad);
    inner_hasher.update(msg);
    let inner_result = inner_hasher.finalize();

    // Outer hash
    let mut outer_hasher = Sha1::new();
    outer_hasher.update(&opad);
    outer_hasher.update(inner_result);
    let outer_result = outer_hasher.finalize();

    let mut result = [0u8; 20];
    result.copy_from_slice(&outer_result);
    result
}

pub fn totp_code(secret: &[u8], unix_secs: i64) -> String {
    let counter = unix_secs.div_euclid(30);
    let mut counter_bytes = [0u8; 8];
    counter_bytes.copy_from_slice(&counter.to_be_bytes());

    let hmac_result = hmac_sha1(secret, &counter_bytes);

    // Dynamic truncation
    let offset = (hmac_result[19] & 0x0f) as usize;
    let binary = ((hmac_result[offset] as u32 & 0x7f) << 24)
        | ((hmac_result[offset + 1] as u32) << 16)
        | ((hmac_result[offset + 2] as u32) << 8)
        | (hmac_result[offset + 3] as u32);

    let otp = binary % 1_000_000;
    format!("{:06}", otp)
}

pub fn verify_totp(secret: &[u8], code: &str, unix_secs: i64) -> bool {
    if code.len() != 6 || !code.as_bytes().iter().all(|&b| b.is_ascii_digit()) {
        return false;
    }

    let mut result = false;
    for delta in -1i64..=1 {
        let expected = totp_code(secret, unix_secs + delta * 30);

        // Constant-time comparison
        let mut diff: u8 = 0;
        for (a, b) in code.as_bytes().iter().zip(expected.as_bytes().iter()) {
            diff |= a ^ b;
        }
        if diff == 0 {
            result = true;
        }
    }

    result
}

pub fn generate_secret() -> Result<String, String> {
    use rand::TryRngCore;
    let mut buf = [0u8; 20];
    let mut rng = rand::rngs::OsRng;
    rng.try_fill_bytes(&mut buf)
        .map_err(|e| format!("os rng failed: {e}"))?;
    let encoded = base32_encode(&buf);
    // Remove trailing '='
    Ok(encoded.trim_end_matches('=').to_string())
}

pub fn otpauth_url(username: &str, secret_b32: &str) -> String {
    let encoded_user: String = username
        .bytes()
        .flat_map(|b| {
            if (b as char).is_ascii_alphanumeric() || b == b'_' || b == b'.' || b == b'-' {
                vec![b as char]
            } else {
                format!("%{:02X}", b).chars().collect()
            }
        })
        .collect();

    format!(
        "otpauth://totp/mini-os:{}?secret={}&issuer=mini-os&algorithm=SHA1&digits=6&period=30",
        encoded_user, secret_b32
    )
}

pub fn qr_svg(text: &str) -> Result<String, String> {
    let code = qrcode::QrCode::new(text).map_err(|_| "二维码生成失败".to_string())?;
    Ok(code
        .render::<qrcode::render::svg::Color>()
        .min_dimensions(240, 240)
        .quiet_zone(true)
        .build())
}

pub fn master_key() -> Result<[u8; 32], String> {
    match std::env::var("MINIOS_TOTP_MASTER_KEY") {
        Ok(val) => {
            if val.len() != 64 {
                return Err("MINIOS_TOTP_MASTER_KEY 非法：必须是 64 个十六进制字符".to_string());
            }
            let decoded = hex::decode(&val)
                .map_err(|_| "MINIOS_TOTP_MASTER_KEY 非法：必须是 64 个十六进制字符".to_string())?;
            if decoded.len() != 32 {
                return Err("MINIOS_TOTP_MASTER_KEY 非法：必须是 64 个十六进制字符".to_string());
            }
            let mut key = [0u8; 32];
            key.copy_from_slice(&decoded);
            Ok(key)
        }
        Err(_) => Err(
            "未配置 MINIOS_TOTP_MASTER_KEY：需要 64 位十六进制（32 字节），启用两步验证前请先配置"
                .to_string(),
        ),
    }
}

pub fn encrypt_secret(plain_b32: &str) -> Result<String, String> {
    use aes_gcm::aead::Aead;
    use aes_gcm::{Aes256Gcm, KeyInit, Nonce};

    let key = master_key()?;
    let cipher = Aes256Gcm::new(aes_gcm::Key::<Aes256Gcm>::from_slice(&key));

    use rand::TryRngCore;
    let mut nonce_bytes = [0u8; 12];
    let mut rng = rand::rngs::OsRng;
    rng.try_fill_bytes(&mut nonce_bytes)
        .map_err(|_| "TOTP 密钥加密失败".to_string())?;

    let nonce = Nonce::from_slice(&nonce_bytes);
    let ciphertext = cipher
        .encrypt(nonce, plain_b32.as_bytes())
        .map_err(|_| "TOTP 密钥加密失败".to_string())?;

    let mut combined = Vec::with_capacity(12 + ciphertext.len());
    combined.extend_from_slice(&nonce_bytes);
    combined.extend_from_slice(&ciphertext);

    Ok(hex::encode(&combined))
}

pub fn decrypt_secret(blob_hex: &str) -> Result<String, String> {
    use aes_gcm::aead::Aead;
    use aes_gcm::{Aes256Gcm, KeyInit, Nonce};

    let key = master_key().map_err(|_| "TOTP 密钥解密失败".to_string())?;
    let blob = hex::decode(blob_hex).map_err(|_| "TOTP 密钥解密失败".to_string())?;

    if blob.len() < 12 + 16 {
        return Err("TOTP 密钥解密失败".to_string());
    }

    let nonce = Nonce::from_slice(&blob[..12]);
    let ciphertext = &blob[12..];

    let cipher = Aes256Gcm::new(aes_gcm::Key::<Aes256Gcm>::from_slice(&key));
    let plaintext = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|_| "TOTP 密钥解密失败".to_string())?;

    String::from_utf8(plaintext).map_err(|_| "TOTP 密钥解密失败".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    static ENV_LOCK: Mutex<()> = Mutex::new(());

    #[test]
    fn rfc6238_sha1_vectors() {
        let secret = b"12345678901234567890";
        assert_eq!(totp_code(secret, 59), "287082");
        assert_eq!(totp_code(secret, 1111111109), "081804");
        assert_eq!(totp_code(secret, 1111111111), "050471");
        assert_eq!(totp_code(secret, 1234567890), "005924");
        assert_eq!(totp_code(secret, 2000000000), "279037");
        assert_eq!(totp_code(secret, 20000000000), "353130");
    }

    #[test]
    fn base32_specific() {
        assert_eq!(base32_encode(b"f"), "MY======");
        assert_eq!(base32_decode("MY======").unwrap(), b"f");
        assert_eq!(base32_decode("MY").unwrap(), b"f");
        assert_eq!(base32_decode("my").unwrap(), b"f");
        assert_eq!(base32_decode("MY*=====").unwrap_err(), "base32 非法字符");
        assert_eq!(base32_decode("A").unwrap_err(), "base32 长度非法");
    }

    #[test]
    fn base32_roundtrip() {
        let empty: Vec<u8> = Vec::new();
        assert_eq!(base32_decode(&base32_encode(&empty)).unwrap(), empty);
        let bytes_20 = b"12345678901234567890";
        assert_eq!(
            base32_decode(&base32_encode(bytes_20)).unwrap(),
            bytes_20.to_vec()
        );
    }

    #[test]
    fn verify_window() {
        let secret = b"12345678901234567890";
        let t = 1111111109;
        let code = totp_code(secret, t);

        assert!(verify_totp(secret, &code, t));
        assert!(verify_totp(secret, &code, t - 30));
        assert!(verify_totp(secret, &code, t + 30));

        assert!(!verify_totp(secret, &code, t - 60));
        assert!(!verify_totp(secret, &code, t + 60));

        assert!(!verify_totp(secret, "12345", t));
        assert!(!verify_totp(secret, "1234567", t));
        assert!(!verify_totp(secret, "abcdef", t));
        assert!(!verify_totp(secret, "", t));
    }

    #[test]
    fn generate_secret_test() {
        let s1 = generate_secret().unwrap();
        let s2 = generate_secret().unwrap();
        assert_ne!(s1, s2);
        assert_eq!(base32_decode(&s1).unwrap().len(), 20);
    }

    #[test]
    fn otpauth_url_test() {
        assert_eq!(
            otpauth_url("alice", "JBSWY3DPEHPK3PXP"),
            "otpauth://totp/mini-os:alice?secret=JBSWY3DPEHPK3PXP&issuer=mini-os&algorithm=SHA1&digits=6&period=30"
        );
        assert!(otpauth_url("a b", "JBSWY3DPEHPK3PXP").contains("a%20b"));
    }

    #[test]
    fn qr_svg_test() {
        let svg = qr_svg("hello").unwrap();
        assert!(svg.contains("<svg"));
    }

    #[test]
    fn encrypt_decrypt_roundtrip() {
        let _lock = ENV_LOCK.lock().unwrap();

        std::env::remove_var("MINIOS_TOTP_MASTER_KEY");
        std::env::set_var("MINIOS_TOTP_MASTER_KEY", "aa".repeat(32));

        let encrypted = encrypt_secret("JBSWY3DPEHPK3PXP").unwrap();
        let decrypted = decrypt_secret(&encrypted).unwrap();
        assert_eq!(decrypted, "JBSWY3DPEHPK3PXP");

        let mut tampered = encrypted.clone();
        let last_char = tampered.chars().last().unwrap();
        let tampered_last = if last_char == '0' { '1' } else { '0' };
        tampered.pop();
        tampered.push(tampered_last);
        assert!(decrypt_secret(&tampered).is_err());

        std::env::remove_var("MINIOS_TOTP_MASTER_KEY");
        let err = master_key().unwrap_err();
        assert!(err.contains("MINIOS_TOTP_MASTER_KEY"));

        std::env::set_var("MINIOS_TOTP_MASTER_KEY", "abc");
        let err = master_key().unwrap_err();
        assert!(err.contains("MINIOS_TOTP_MASTER_KEY"));

        std::env::remove_var("MINIOS_TOTP_MASTER_KEY");
    }

    #[test]
    fn decrypt_secret_invalid() {
        let _lock = ENV_LOCK.lock().unwrap();
        std::env::remove_var("MINIOS_TOTP_MASTER_KEY");
        std::env::set_var("MINIOS_TOTP_MASTER_KEY", "aa".repeat(32));

        assert_eq!(decrypt_secret("zzzz").unwrap_err(), "TOTP 密钥解密失败");
        assert_eq!(decrypt_secret("00").unwrap_err(), "TOTP 密钥解密失败");

        std::env::remove_var("MINIOS_TOTP_MASTER_KEY");
    }
}
