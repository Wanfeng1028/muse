//! Canonical JSON (RFC 8785 style) and SHA-256 helpers.
//!
//! Object keys are sorted by UTF-16 code units, there is no insignificant whitespace, and strings
//! use the minimal JSON escapes. Integers print as integers. Finite floats print through
//! `serde_json`'s shortest round-trip form, which matches ECMAScript for the values evidence
//! records hold (counts, offsets, ratios); non-finite floats cannot occur in `serde_json::Value`.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fmt::Write as _;

/// The canonical JSON text of `v`.
pub fn canonical_json(v: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, v, 0);
    out
}

/// Lowercase hex SHA-256 of `bytes`.
pub fn sha256_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

// Values nested deeper than this are written as `null`: evidence never nests this deep, and the
// bound keeps a hostile document from exhausting the stack.
const MAX_DEPTH: usize = 512;

fn write_value(out: &mut String, v: &Value, depth: usize) {
    if depth > MAX_DEPTH {
        out.push_str("null");
        return;
    }
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&n.to_string()),
        Value::String(s) => write_string(out, s),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_value(out, item, depth + 1);
            }
            out.push(']');
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort_by(|a, b| a.encode_utf16().cmp(b.encode_utf16()));
            out.push('{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                write_string(out, k);
                out.push(':');
                if let Some(child) = map.get(*k) {
                    write_value(out, child, depth + 1);
                }
            }
            out.push('}');
        }
    }
}

fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn sorts_keys_and_strips_whitespace() {
        let v = json!({"b": [1, {"z": null, "a": true}], "a": "x\ny"});
        assert_eq!(canonical_json(&v), r#"{"a":"x\ny","b":[1,{"a":true,"z":null}]}"#);
    }

    #[test]
    fn sorts_by_utf16_not_utf8() {
        // U+FB01 (one UTF-16 unit, 0xFB01) sorts after U+1F600 (surrogates 0xD83D…) in UTF-16,
        // but before it in UTF-8 byte order.
        let v = json!({"\u{1F600}": 1, "\u{FB01}": 2});
        assert_eq!(canonical_json(&v), "{\"\u{1F600}\":1,\"\u{FB01}\":2}");
    }

    #[test]
    fn deep_nesting_is_bounded() {
        let mut v = json!(0);
        for _ in 0..2000 {
            v = json!([v]);
        }
        let s = canonical_json(&v);
        assert!(s.contains("null"));
    }

    #[test]
    fn sha256_known_vector() {
        assert_eq!(sha256_hex(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }
}
