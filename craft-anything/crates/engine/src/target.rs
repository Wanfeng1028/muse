//! Targets: what we're looking at, loaded once, identified by content hash.

use craft_anything_evidence::{ErrorCode, Subject, ToolError, sha256_hex};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Arc;

/// Biggest file we load into memory. Bigger inputs get a clear error rather than an OOM.
pub const MAX_TARGET_BYTES: u64 = 2 * 1024 * 1024 * 1024;

pub type TargetId = String;

/// What kind of thing a target is. Detected from content, never from the extension alone.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum TargetKind {
    Elf,
    Pe,
    MachO,
    /// A fat/universal Mach-O.
    MachOFat,
    /// A .NET assembly (PE with a CLI header).
    Managed,
    Wasm,
    Apk,
    Dex,
    Jar,
    /// A single Java `.class` file.
    JavaClass,
    Zip,
    Asar,
    /// A folder: an app bundle, an unpacked Electron app, a project.
    Directory,
    /// A JavaScript or HTML file.
    Script,
    /// A HAR or other network capture.
    NetworkCapture,
    Plist,
    /// EVM bytecode.
    Evm,
    /// A SQLite 3 database file.
    Sqlite,
    /// A DOS .COM program.
    DosCom,
    /// Raw bytes with a user-declared architecture (firmware, shellcode).
    RawBinary,
    Unknown,
}

impl TargetKind {
    /// Plain-English description for Beginner mode.
    pub fn plain(self) -> &'static str {
        match self {
            TargetKind::Elf => "A Linux (or Unix) program",
            TargetKind::Pe => "A Windows program",
            TargetKind::MachO | TargetKind::MachOFat => "A Mac or iPhone program",
            TargetKind::Managed => "A .NET program (C#, F# or VB)",
            TargetKind::Wasm => "A WebAssembly module (code that runs in a browser)",
            TargetKind::Apk => "An Android app",
            TargetKind::Dex => "Android app code (DEX)",
            TargetKind::Jar => "A Java program",
            TargetKind::JavaClass => "Java program code (one class)",
            TargetKind::Zip => "A ZIP archive",
            TargetKind::Asar => "The packed contents of an Electron app (a website inside a desktop app)",
            TargetKind::Directory => "A folder",
            TargetKind::Script => "A script or web page",
            TargetKind::NetworkCapture => "A recording of network traffic",
            TargetKind::Plist => "An Apple settings file (plist)",
            TargetKind::Evm => "A smart contract (EVM bytecode)",
            TargetKind::Sqlite => "A SQLite database (how an app stores its data)",
            TargetKind::DosCom => "A DOS program",
            TargetKind::RawBinary => "Raw machine code",
            TargetKind::Unknown => "A file we don't recognise yet",
        }
    }

    pub fn id(self) -> String {
        serde_json::to_value(self).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_else(|| "unknown".into())
    }
}

/// Sniff the kind from the first bytes (and the name, only to break ties).
pub fn sniff(bytes: &[u8], name: &str) -> TargetKind {
    let lower = name.to_ascii_lowercase();
    let starts = |m: &[u8]| bytes.starts_with(m);
    if starts(b"SQLite format 3\0") {
        TargetKind::Sqlite
    } else if starts(b"\x7fELF") {
        TargetKind::Elf
    } else if starts(b"MZ") {
        if craft_anything_formats::pe_is_managed(bytes) { TargetKind::Managed } else { TargetKind::Pe }
    } else if starts(&[0xfe, 0xed, 0xfa, 0xce]) || starts(&[0xfe, 0xed, 0xfa, 0xcf]) || starts(&[0xce, 0xfa, 0xed, 0xfe]) || starts(&[0xcf, 0xfa, 0xed, 0xfe]) {
        TargetKind::MachO
    } else if starts(&[0xca, 0xfe, 0xba, 0xbe]) {
        // Both a Java class and a big-endian fat Mach-O start 0xCAFEBABE. A class has a plausible
        // major version where a fat binary has a small big-endian architecture count, so prefer
        // the .class extension, then the version check.
        if lower.ends_with(".class") || craft_anything_formats::java_class::is_class(bytes) { TargetKind::JavaClass } else { TargetKind::MachOFat }
    } else if starts(b"\0asm") {
        TargetKind::Wasm
    } else if starts(b"dex\n") {
        TargetKind::Dex
    } else if starts(b"PK\x03\x04") || starts(b"PK\x05\x06") {
        if lower.ends_with(".apk") || lower.ends_with(".aab") || lower.ends_with(".xapk") {
            TargetKind::Apk
        } else if lower.ends_with(".jar") || lower.ends_with(".war") {
            TargetKind::Jar
        } else if craft_anything_formats::zip_has_entry(bytes, "AndroidManifest.xml") {
            TargetKind::Apk
        } else {
            TargetKind::Zip
        }
    } else if lower.ends_with(".asar") || craft_anything_formats::looks_like_asar(bytes) {
        TargetKind::Asar
    } else if starts(b"bplist00") || (lower.ends_with(".plist") && bytes.windows(6).take(512).any(|w| w == b"<plist")) {
        TargetKind::Plist
    } else if lower.ends_with(".har") {
        TargetKind::NetworkCapture
    } else if lower.ends_with(".com") && bytes.len() <= 0xff00 {
        TargetKind::DosCom
    } else if [".js", ".mjs", ".cjs", ".html", ".htm", ".ts"].iter().any(|e| lower.ends_with(e)) {
        TargetKind::Script
    } else {
        TargetKind::Unknown
    }
}

/// A loaded target.
#[derive(Debug, Clone)]
pub struct Target {
    /// `t_` + first 12 hex of the sha256 (+ a suffix if the same file is opened twice).
    pub id: TargetId,
    pub path: PathBuf,
    pub name: String,
    pub sha256: String,
    pub kind: TargetKind,
    /// File contents (empty for directories).
    pub bytes: Arc<[u8]>,
    /// For raw binaries: declared architecture and entry point.
    pub raw: Option<RawSpec>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
pub struct RawSpec {
    /// `x86`, `x86_64`, `arm`, `arm64`.
    pub architecture: String,
    /// Load and entry address.
    pub entry_point: u64,
}

impl Target {
    /// Load a file or directory.
    pub fn load(path: &Path) -> Result<Target, ToolError> {
        let meta = std::fs::metadata(path).map_err(|e| ToolError::io(path.display(), e))?;
        let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
        if meta.is_dir() {
            let digest = sha256_hex(path.to_string_lossy().as_bytes());
            return Ok(Target {
                id: format!("t_{}", digest.get(..12).unwrap_or(&digest)),
                path: path.to_path_buf(),
                name,
                sha256: digest,
                kind: TargetKind::Directory,
                bytes: Arc::from(Vec::new()),
                raw: None,
            });
        }
        if meta.len() > MAX_TARGET_BYTES {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is {} bytes; the limit is {MAX_TARGET_BYTES}", path.display(), meta.len())));
        }
        let bytes = std::fs::read(path).map_err(|e| ToolError::io(path.display(), e))?;
        Ok(Target::from_bytes(path.to_path_buf(), name, bytes))
    }

    pub fn from_bytes(path: PathBuf, name: String, bytes: Vec<u8>) -> Target {
        let sha256 = sha256_hex(&bytes);
        let kind = sniff(&bytes, &name);
        Target { id: format!("t_{}", sha256.get(..12).unwrap_or(&sha256)), path, name, sha256, kind, bytes: Arc::from(bytes), raw: None }
    }

    pub fn subject(&self) -> Subject {
        Subject { kind: self.kind.id(), sha256: Some(self.sha256.clone()), name: Some(self.name.clone()) }
    }

    /// Fail if the file on disk no longer matches what we loaded.
    pub fn check_unchanged(&self) -> Result<(), ToolError> {
        if self.kind == TargetKind::Directory {
            return Ok(());
        }
        match std::fs::read(&self.path) {
            Ok(b) if sha256_hex(&b) == self.sha256 => Ok(()),
            Ok(_) => Err(ToolError::new(ErrorCode::FileChanged, format!("{} changed on disk since it was opened", self.path.display()))
                .with_remediation("Open it again to analyse the new version.")),
            Err(e) => Err(ToolError::io(self.path.display(), e)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sniffs_common_magics() {
        assert_eq!(sniff(b"\x7fELF\x02\x01", "a"), TargetKind::Elf);
        assert_eq!(sniff(b"\0asm\x01\0\0\0", "m"), TargetKind::Wasm);
        assert_eq!(sniff(b"dex\n035\0", "classes.dex"), TargetKind::Dex);
        assert_eq!(sniff(b"PK\x03\x04", "app.apk"), TargetKind::Apk);
        assert_eq!(sniff(b"bplist00", "Info.plist"), TargetKind::Plist);
        assert_eq!(sniff(b"SQLite format 3\0\x10\x00", "app.db"), TargetKind::Sqlite);
        assert_eq!(sniff(b"", "x"), TargetKind::Unknown);
        assert_eq!(sniff(b"console.log(1)", "main.js"), TargetKind::Script);
    }
}
