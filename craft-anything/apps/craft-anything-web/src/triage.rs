//! What a dropped file is: native triage for programs, a signature check for everything else.
//!
//! Pure and synchronous (no clock, threads or file system), so it is safe in the browser.

use craft_anything_analysis::js_inventory::sniff_kind;
use craft_anything_analysis::native;
use craft_anything_evidence::{Confidence, sha256_hex};
use craft_anything_formats::{entropy, parse_binary};
use serde_json::Value;

/// Largest file the page reads (browser memory is the limit; the desktop app has none).
pub const MAX_BYTES: usize = 512 * 1024 * 1024;

/// The answer for one file.
pub struct Look {
    pub file_name: String,
    /// One or two plain sentences.
    pub summary: String,
    pub confidence: Confidence,
    /// Label/value pairs shown as a table.
    pub facts: Vec<(String, String)>,
    pub limitations: Vec<String>,
    /// The full result, pretty-printed (empty when there is none beyond the facts).
    pub details: String,
}

pub fn look(file_name: &str, bytes: &[u8]) -> Look {
    let mut facts = vec![("Size".to_string(), size_text(bytes.len())), ("SHA-256".to_string(), sha256_hex(bytes))];
    let sample = bytes.get(..bytes.len().min(4 * 1024 * 1024)).unwrap_or_default();
    facts.push(("Entropy (first 4 MB)".to_string(), format!("{:.2} bits per byte", entropy(sample))));
    let kind = sniff_kind(bytes, file_name);
    if let Ok(bin) = parse_binary(bytes) {
        let report = native::triage(&bin, bytes, file_name);
        let field = |k: &str| report.result.get(k).and_then(Value::as_str).map(str::to_string);
        let mut native_facts = Vec::new();
        for (label, key) in
            [("Format", "format_name"), ("Runs on", "operating_system"), ("Kind", "kind"), ("Architecture", "architecture"), ("Entry point", "entry_point")]
        {
            if let Some(v) = field(key) {
                native_facts.push((label.to_string(), v));
            }
        }
        if let Some(s) = report.result.get("stripped").and_then(Value::as_bool) {
            native_facts.push(("Names removed (stripped)".to_string(), if s { "yes" } else { "no" }.to_string()));
        }
        native_facts.append(&mut facts);
        return Look {
            file_name: file_name.to_string(),
            summary: report.summary,
            confidence: report.confidence,
            facts: native_facts,
            limitations: report.limitations.into_iter().map(|l| l.message).collect(),
            details: serde_json::to_string_pretty(&report.result).unwrap_or_default(),
        };
    }
    let (what, next) = describe(kind);
    facts.insert(0, ("Detected as".to_string(), kind.to_string()));
    Look {
        file_name: file_name.to_string(),
        summary: format!("{file_name} looks like {what}. {next}"),
        confidence: if matches!(kind, "text" | "binary") { Confidence::Inferred } else { Confidence::Observed },
        facts,
        limitations: vec!["identified from its first bytes and name only; the web viewer doesn't open containers or code".to_string()],
        details: String::new(),
    }
}

/// A plain description of a sniffed kind, and where to look next.
fn describe(kind: &str) -> (&'static str, &'static str) {
    const DESKTOP: &str = "Open it in the Craft Anything desktop app to look inside.";
    match kind {
        "wasm" => ("a WebAssembly module (code that runs in browsers and other hosts)", DESKTOP),
        "dex" => ("Android app code (a DEX file)", DESKTOP),
        "apk" => ("an Android app package", DESKTOP),
        "ipa" => ("an iPhone/iPad app package", DESKTOP),
        "jar" => ("a Java archive", DESKTOP),
        "java-class" => ("a compiled Java class", DESKTOP),
        "msix" => ("a Windows app package (MSIX/AppX)", DESKTOP),
        "hap" => ("a HarmonyOS app package", DESKTOP),
        "zip" => ("a ZIP archive", DESKTOP),
        "asar" => ("an Electron app archive (app.asar): the app's JavaScript lives here", DESKTOP),
        "native-addon" => ("a Node.js native add-on", DESKTOP),
        "javascript" | "typescript" => ("JavaScript or TypeScript source", DESKTOP),
        "source-map" => ("a source map (links bundled JavaScript back to its sources)", DESKTOP),
        "binary-plist" | "xml-plist" => ("an Apple property list (settings or app metadata)", DESKTOP),
        "gzip" => ("gzip-compressed data", DESKTOP),
        "xar" => ("a XAR archive (macOS installer packages use it)", DESKTOP),
        "sqlite" => ("an SQLite database", DESKTOP),
        "png" | "jpeg" | "gif" | "svg" => ("an image", "There's no code to look at in an image."),
        "pdf" => ("a PDF document", "There's no program to look at here."),
        "json" | "html" | "css" | "xml" | "text" => ("text", DESKTOP),
        _ => ("data we don't recognise", "The desktop app has many more ways to identify files."),
    }
}

fn size_text(n: usize) -> String {
    const UNITS: [&str; 4] = ["KB", "MB", "GB", "TB"];
    if n < 1024 {
        return format!("{n} bytes");
    }
    let mut v = n as f64 / 1024.0;
    let mut unit = UNITS[0];
    for u in UNITS.iter().skip(1) {
        if v < 1024.0 {
            break;
        }
        v /= 1024.0;
        unit = u;
    }
    format!("{v:.1} {unit} ({n} bytes)")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_and_garbage_never_crash() {
        for bytes in [&b""[..], b"\x7fELF", b"MZ\0\0\0\0", &[0xcf, 0xfa, 0xed, 0xfe, 1, 2], &[0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 9]] {
            let l = look("x", bytes);
            assert!(!l.summary.is_empty());
        }
    }

    #[test]
    fn signatures() {
        assert!(look("a.png", b"\x89PNG\r\n\x1a\n").summary.contains("image"));
        assert!(look("m.wasm", b"\0asm\x01\0\0\0").summary.contains("WebAssembly"));
    }

    #[test]
    fn host_program() {
        let Ok(bytes) = std::fs::read("/bin/ls") else { return };
        let l = look("ls", &bytes);
        assert!(l.summary.starts_with("ls is a program"), "{}", l.summary);
        assert!(l.facts.iter().any(|(k, _)| k == "Architecture"));
        assert!(!l.details.is_empty());
    }

    #[test]
    fn sizes() {
        assert_eq!(size_text(10), "10 bytes");
        assert_eq!(size_text(2048), "2.0 KB (2048 bytes)");
    }
}
