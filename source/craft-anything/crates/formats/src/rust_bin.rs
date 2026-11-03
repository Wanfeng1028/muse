//! Rust program fingerprints: rustc version and commit, crates and versions from embedded Cargo
//! paths, standard-library path layout, source paths left by panic locations, well-known panic
//! messages, Rust symbol names (legacy and v0 mangling) and the cargo-auditable dependency list
//! (`.dep-v0`, zlib-compressed JSON). Pure byte scans; never executes anything.

use crate::binary::Binary;
use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeMap;

/// Most entries kept per list.
pub const MAX_ITEMS: usize = 500;
/// Most occurrences of one needle examined.
const MAX_HITS: usize = 200_000;
/// Largest cargo-auditable section read (1 MiB) and largest inflated JSON (8 MiB).
const MAX_DEP_SECTION: u64 = 1 << 20;
const MAX_DEP_JSON: usize = 8 << 20;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Counted {
    pub value: String,
    pub count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CrateRef {
    pub name: String,
    pub version: Option<String>,
    /// registry, toolchain-vendored, vendored or git
    pub source: &'static str,
    /// The registry index folder or git checkout it was built from.
    pub origin: String,
    pub occurrences: usize,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct SourcePaths {
    /// Paths under the Rust toolchain (`/rustc/<commit>/…`).
    pub toolchain: usize,
    /// Paths inside crates downloaded by Cargo.
    pub dependencies: usize,
    /// Everything else: usually the program's own source files.
    pub local: Vec<Counted>,
    pub local_truncated: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct SymbolSample {
    pub mangled: String,
    pub demangled: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct RustSymbols {
    /// Symbols in the container's symbol tables (exports and imports included).
    pub total: usize,
    pub rust_legacy: usize,
    pub rust_v0: usize,
    /// No Rust-mangled names at all (stripped, or names kept in a separate debug file).
    pub stripped: bool,
    /// Leading path component of demangled names, by frequency.
    pub crates: Vec<Counted>,
    pub samples: Vec<SymbolSample>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AuditablePackage {
    pub name: String,
    pub version: String,
    pub source: Option<String>,
    pub kind: Option<String>,
    pub dependencies: Vec<u64>,
    pub root: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Auditable {
    pub section: String,
    pub file_offset: u64,
    pub section_bytes: u64,
    pub uncompressed_bytes: usize,
    pub format_version: Option<i64>,
    pub packages: Vec<AuditablePackage>,
    pub root_package_index: Option<usize>,
    pub dependency_edges: usize,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct RustReport {
    pub is_rust: bool,
    /// strong (symbols, toolchain paths or dependency data), weak (only panic text or crate paths) or none
    pub strength: &'static str,
    pub signals: Vec<String>,
    pub rustc_versions: Vec<Counted>,
    pub rustc_commits: Vec<Counted>,
    /// `library/` (rustc 1.47 or later) or `src/lib*` (older); from toolchain paths.
    pub std_layout: Option<&'static str>,
    pub crates: Vec<CrateRef>,
    pub source_paths: SourcePaths,
    pub panic_messages: Vec<Counted>,
    pub symbols: RustSymbols,
    pub auditable: Option<Auditable>,
    /// Why a present `.dep-v0` section could not be read.
    pub auditable_error: Option<String>,
}

/// Offsets of `needle` in `data`, at most `MAX_HITS`.
fn occurrences<'a>(data: &'a [u8], needle: &'a [u8]) -> impl Iterator<Item = usize> + 'a {
    let mut i = 0usize;
    std::iter::from_fn(move || {
        let (&first, rest) = needle.split_first()?;
        while let Some(p) = data.get(i..).and_then(|h| h.iter().position(|&b| b == first)) {
            let at = i + p;
            i = at + 1;
            if data.get(at + 1..at + 1 + rest.len()) == Some(rest) {
                return Some(at);
            }
        }
        None
    })
    .take(MAX_HITS)
}

fn is_sep(b: u8) -> bool {
    b == b'/' || b == b'\\'
}

/// The path component starting at `at` (up to a separator), when it is plain name characters.
fn component(data: &[u8], at: usize) -> Option<(&str, usize)> {
    let rest = data.get(at..)?;
    let len = rest.iter().take(129).position(|&b| is_sep(b))?;
    let s = std::str::from_utf8(rest.get(..len)?).ok()?;
    let ok = !s.is_empty() && s.bytes().all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b'+'));
    ok.then_some((s, at + len + 1))
}

/// Split `serde_json-1.0.108` into name and version at the first `-<digit>` followed by a dotted version.
fn split_crate_dir(dir: &str) -> Option<(&str, &str)> {
    let b = dir.as_bytes();
    (1..b.len()).find_map(|i| {
        let (name, ver) = (dir.get(..i)?, dir.get(i + 1..)?);
        let looks_versioned = b.get(i) == Some(&b'-') && ver.split('.').take(2).all(|p| !p.is_empty() && p.bytes().all(|c| c.is_ascii_digit()));
        (looks_versioned && ver.contains('.')).then_some((name, ver))
    })
}

fn bump(map: &mut BTreeMap<String, usize>, key: String) {
    if map.len() < MAX_ITEMS * 4 || map.contains_key(&key) {
        *map.entry(key).or_insert(0) += 1;
    }
}

/// Most frequent first, then by value; at most `MAX_ITEMS`.
fn ranked(map: BTreeMap<String, usize>) -> Vec<Counted> {
    let mut v: Vec<Counted> = map.into_iter().map(|(value, count)| Counted { value, count }).collect();
    v.sort_by(|a, b| b.count.cmp(&a.count).then_with(|| a.value.cmp(&b.value)));
    v.truncate(MAX_ITEMS);
    v
}

/// Printable text from `at`, at most `max` bytes, ending at a control byte or just after `stop`.
fn text_at(data: &[u8], at: usize, max: usize, stop: Option<u8>) -> String {
    let rest = data.get(at..).unwrap_or(&[]);
    let mut end = 0usize;
    for &b in rest.iter().take(max) {
        if !(0x20..0x7f).contains(&b) {
            break;
        }
        end += 1;
        if Some(b) == stop {
            break;
        }
    }
    String::from_utf8_lossy(rest.get(..end).unwrap_or(&[])).into_owned()
}

fn path_char(b: u8) -> bool {
    b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b'/' | b'\\' | b':' | b'+' | b'@' | b'~')
}

/// Well-known messages and markers from the Rust standard library's panic machinery.
const PANIC_TEXTS: &[&str] = &[
    "called `Option::unwrap()` on a `None` value",
    "called `Result::unwrap()` on an `Err` value",
    "index out of bounds: the len is ",
    "attempt to add with overflow",
    "attempt to subtract with overflow",
    "attempt to multiply with overflow",
    "RUST_BACKTRACE",
    "rust_begin_unwind",
    "rust_panic",
];

/// Crates that ship inside the standard library; their symbols say little about the program.
const STD_CRATES: &[&str] = &[
    "core",
    "alloc",
    "std",
    "compiler_builtins",
    "hashbrown",
    "panic_unwind",
    "panic_abort",
    "gimli",
    "addr2line",
    "miniz_oxide",
    "rustc_demangle",
    "object",
    "memchr",
    "adler",
    "adler2",
    "std_detect",
];

/// Path markers that precede a dependency's folder, with the source they indicate.
const DEP_NEEDLES: &[(&[u8], &str)] = &[
    (b"registry/src/", "registry"),
    (b"registry\\src\\", "registry"),
    (b"/rust/deps/", "toolchain-vendored"),
    (b"/rust/deps\\", "toolchain-vendored"),
    (b"vendor/", "vendored"),
    (b"vendor\\", "vendored"),
    (b"git/checkouts/", "git"),
    (b"git\\checkouts\\", "git"),
];

type CrateKey = (String, Option<String>, &'static str, String);

/// Look for Rust fingerprints in `data`; `bin` adds symbols and the cargo-auditable section.
pub fn inspect(data: &[u8], bin: Option<&Binary>) -> RustReport {
    // Toolchain: `/rustc/<40-hex commit>/library/...` and `rustc version 1.x.y (...)`.
    let mut commits = BTreeMap::new();
    let (mut layout_new, mut layout_old) = (0usize, 0usize);
    for at in occurrences(data, b"/rustc/") {
        let Some(h) = data.get(at + 7..at + 47) else { continue };
        if h.iter().all(u8::is_ascii_hexdigit) && data.get(at + 47).copied().is_some_and(is_sep) {
            bump(&mut commits, String::from_utf8_lossy(h).into_owned());
            let tail = data.get(at + 48..).unwrap_or(&[]);
            if tail.starts_with(b"library") {
                layout_new += 1;
            } else if tail.starts_with(b"src") {
                layout_old += 1;
            }
        }
    }
    let mut versions = BTreeMap::new();
    for at in occurrences(data, b"rustc version 1.") {
        bump(&mut versions, text_at(data, at + 14, 80, Some(b')')));
    }

    // Dependencies from Cargo's folders: registry/src/<index>/<crate>-<ver>/, the toolchain's
    // remapped /rust/deps/<crate>-<ver>/, vendor/<crate>-<ver>/ and git/checkouts/<repo>-<hash>/<rev>/.
    let mut crates: BTreeMap<CrateKey, usize> = BTreeMap::new();
    for &(needle, source) in DEP_NEEDLES {
        for at in occurrences(data, needle) {
            let Some((first, next)) = component(data, at + needle.len()) else { continue };
            let key: CrateKey = if source != "git" {
                // Only registry paths have an index folder before the crate folder.
                let (dir, origin) = if source == "registry" {
                    let Some((dir, _)) = component(data, next) else { continue };
                    (dir, first)
                } else {
                    (first, source)
                };
                let Some((name, ver)) = split_crate_dir(dir) else { continue };
                (name.to_string(), Some(ver.to_string()), source, origin.to_string())
            } else {
                let name = first.rsplit_once('-').map(|(n, _)| n).unwrap_or(first);
                (name.to_string(), component(data, next).map(|(r, _)| r.to_string()), source, first.to_string())
            };
            if crates.len() < MAX_ITEMS * 4 || crates.contains_key(&key) {
                *crates.entry(key).or_insert(0) += 1;
            }
        }
    }
    let mut crate_list: Vec<CrateRef> =
        crates.into_iter().map(|((name, version, source, origin), occurrences)| CrateRef { name, version, source, origin, occurrences }).collect();
    crate_list.truncate(MAX_ITEMS);

    // Source paths (panic locations, debug info): any path ending in `.rs`.
    let mut paths = SourcePaths::default();
    let mut local = BTreeMap::new();
    for at in occurrences(data, b".rs") {
        let mut start = at;
        while start > 0 && at - start < 300 && data.get(start - 1).copied().is_some_and(path_char) {
            start -= 1;
        }
        let Some(p) = data.get(start..at + 3).and_then(|b| std::str::from_utf8(b).ok()) else { continue };
        let stem = p.trim_end_matches(".rs").rsplit(['/', '\\']).next().unwrap_or("");
        if !p.contains(['/', '\\']) || stem.is_empty() || !stem.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-') {
            continue;
        }
        if p.contains("/rustc/") {
            paths.toolchain += 1;
        } else if DEP_NEEDLES.iter().any(|(n, _)| p.as_bytes().windows(n.len()).any(|w| w == *n)) {
            paths.dependencies += 1;
        } else {
            bump(&mut local, p.to_string());
        }
    }
    let local_kinds = local.len();
    paths.local = ranked(local);
    paths.local_truncated = local_kinds > paths.local.len();

    let panic_messages: Vec<Counted> =
        PANIC_TEXTS.iter().map(|t| Counted { value: (*t).to_string(), count: occurrences(data, t.as_bytes()).count() }).filter(|c| c.count > 0).collect();

    let symbols = bin.map(rust_symbols).unwrap_or(RustSymbols { stripped: true, ..RustSymbols::default() });
    let (auditable, auditable_error) = match bin.map(|b| auditable(b, data)) {
        Some(Ok(a)) => (a, None),
        Some(Err(e)) => (None, Some(e)),
        None => (None, None),
    };

    let mut signals = Vec::new();
    if let Some(a) = &auditable {
        signals.push(format!("cargo-auditable dependency list ({} packages)", a.packages.len()));
    }
    if symbols.rust_legacy + symbols.rust_v0 > 0 {
        signals.push(format!("{} Rust-mangled symbol names", symbols.rust_legacy + symbols.rust_v0));
    }
    if !commits.is_empty() {
        signals.push("Rust toolchain source paths (/rustc/<commit>/)".into());
    }
    if !versions.is_empty() {
        signals.push("rustc version string".into());
    }
    let strong = !signals.is_empty();
    if !crate_list.is_empty() {
        signals.push(format!("{} Cargo dependency paths", crate_list.len()));
    }
    if !panic_messages.is_empty() {
        signals.push("Rust standard-library panic text".into());
    }
    let strength = match (strong, signals.is_empty()) {
        (true, _) => "strong",
        (false, true) => "none",
        (false, false) => "weak",
    };
    RustReport {
        is_rust: strength != "none",
        strength,
        signals,
        rustc_versions: ranked(versions),
        rustc_commits: ranked(commits),
        std_layout: match (layout_new, layout_old) {
            (0, 0) => None,
            (n, o) if n >= o => Some("library/ (rustc 1.47 or later)"),
            _ => Some("src/lib* (before rustc 1.47)"),
        },
        crates: crate_list,
        source_paths: paths,
        panic_messages,
        symbols,
        auditable,
        auditable_error,
    }
}

fn rust_symbols(bin: &Binary) -> RustSymbols {
    let names =
        bin.symbols.iter().map(|s| s.name.as_str()).chain(bin.imports.iter().map(|i| i.name.as_str())).chain(bin.exports.iter().map(|e| e.name.as_str()));
    let mut out = RustSymbols::default();
    let mut crates = BTreeMap::new();
    let mut std_samples = Vec::new();
    for name in names {
        out.total += 1;
        let Ok(d) = rustc_demangle::try_demangle(name) else { continue };
        let full = format!("{d}");
        let v0 = name.trim_start_matches('_').starts_with('R');
        // Legacy names are Itanium-shaped; only the trailing `::h<16 hex>` hash marks them as Rust.
        let legacy = !v0 && full.rsplit_once("::h").is_some_and(|(_, h)| h.len() == 16 && h.bytes().all(|b| b.is_ascii_hexdigit()));
        if !(v0 || legacy) {
            continue;
        }
        if v0 {
            out.rust_v0 += 1;
        } else {
            out.rust_legacy += 1;
        }
        let short = format!("{d:#}");
        let krate = short.trim_start_matches('<').split("::").next().unwrap_or("").to_string();
        let is_std = STD_CRATES.contains(&krate.as_str());
        bump(&mut crates, krate);
        let sample = SymbolSample { mangled: name.to_string(), demangled: short };
        if !is_std && out.samples.len() < 40 {
            out.samples.push(sample);
        } else if is_std && std_samples.len() < 10 {
            std_samples.push(sample);
        }
    }
    out.samples.extend(std_samples);
    out.stripped = out.rust_legacy + out.rust_v0 == 0;
    out.crates = ranked(crates);
    out
}

/// The cargo-auditable `.dep-v0` section: `Ok(None)` when absent.
fn auditable(bin: &Binary, data: &[u8]) -> Result<Option<Auditable>, String> {
    let Some(sec) = bin.sections.iter().find(|s| s.name == ".dep-v0") else { return Ok(None) };
    let off = sec.file_offset.ok_or("the .dep-v0 section has no bytes in the file")?;
    if sec.file_size > MAX_DEP_SECTION {
        return Err(format!("the .dep-v0 section is {} bytes; the limit is {MAX_DEP_SECTION}", sec.file_size));
    }
    let raw = usize::try_from(off)
        .ok()
        .zip(usize::try_from(sec.file_size).ok())
        .and_then(|(o, n)| data.get(o..o.checked_add(n)?))
        .ok_or("the .dep-v0 section runs past the end of the file")?;
    let cap = MAX_DEP_JSON.min(raw.len().saturating_mul(64)).max(1024);
    let json = miniz_oxide::inflate::decompress_to_vec_zlib_with_limit(raw, cap).map_err(|e| format!("the .dep-v0 data did not inflate: {:?}", e.status))?;
    let v: Value = serde_json::from_slice(&json).map_err(|e| format!("the .dep-v0 data is not JSON: {e}"))?;
    let pkgs = v.get("packages").and_then(Value::as_array).ok_or("the .dep-v0 JSON has no packages list")?;
    let s = |p: &Value, k: &str| p.get(k).and_then(Value::as_str).map(str::to_string);
    let packages: Vec<AuditablePackage> = pkgs
        .iter()
        .take(100_000)
        .map(|p| AuditablePackage {
            name: s(p, "name").unwrap_or_default(),
            version: s(p, "version").unwrap_or_default(),
            source: s(p, "source"),
            kind: s(p, "kind"),
            dependencies: p.get("dependencies").and_then(Value::as_array).map(|d| d.iter().filter_map(Value::as_u64).collect()).unwrap_or_default(),
            root: p.get("root").and_then(Value::as_bool).unwrap_or(false),
        })
        .collect();
    Ok(Some(Auditable {
        section: match &sec.segment {
            Some(seg) => format!("{seg},{}", sec.name),
            None => sec.name.clone(),
        },
        file_offset: off,
        section_bytes: sec.file_size,
        uncompressed_bytes: json.len(),
        format_version: v.get("format").and_then(Value::as_i64),
        root_package_index: packages.iter().position(|p| p.root),
        dependency_edges: packages.iter().map(|p| p.dependencies.len()).sum(),
        packages,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn crate_dir_split() {
        assert_eq!(split_crate_dir("serde_json-1.0.108"), Some(("serde_json", "1.0.108")));
        assert_eq!(split_crate_dir("windows-sys-0.52.0"), Some(("windows-sys", "0.52.0")));
        assert_eq!(split_crate_dir("tokio-1.35.0-alpha.1"), Some(("tokio", "1.35.0-alpha.1")));
        assert_eq!(split_crate_dir("noversion"), None);
        assert_eq!(split_crate_dir("x-1"), None);
    }

    #[test]
    fn finds_toolchain_crates_paths_and_panics() {
        let commit = "82e1608dfa6e0b5569232559e3d385fea5a93112";
        let mut d = b"\x00junk".to_vec();
        d.extend(format!("/rustc/{commit}/library/core/src/str/mod.rs").as_bytes());
        d.extend(b"rustc version 1.75.0 (82e1608df 2023-12-21)\x00");
        d.extend(b"/home/u/.cargo/registry/src/index.crates.io-6f17d22bba15001f/serde_json-1.0.108/src/de.rs\x00");
        d.extend(b"C:\\Users\\u\\.cargo\\registry\\src\\index.crates.io-6f17d22bba15001f\\windows-sys-0.52.0\\src\\lib.rs\x00");
        d.extend(b"/home/u/.cargo/git/checkouts/egui-1a2b3c4d5e6f7a8b/abc1234/src/lib.rs\x00");
        d.extend(b"/rust/deps\\aho-corasick-1.1.4\\src\\dfa.rs\x00");
        d.extend(b"\x00src/main.rs\x00called `Option::unwrap()` on a `None` value\x00.rsrc\x00");
        let r = inspect(&d, None);
        assert!(r.is_rust);
        assert_eq!(r.strength, "strong");
        assert_eq!(r.rustc_commits[0].value, commit);
        assert_eq!(r.rustc_versions[0].value, "1.75.0 (82e1608df 2023-12-21)");
        assert_eq!(r.std_layout, Some("library/ (rustc 1.47 or later)"));
        let names: Vec<_> = r.crates.iter().map(|c| (c.name.as_str(), c.version.as_deref(), c.source)).collect();
        assert!(names.contains(&("serde_json", Some("1.0.108"), "registry")), "{names:?}");
        assert!(names.contains(&("windows-sys", Some("0.52.0"), "registry")), "{names:?}");
        assert!(names.contains(&("egui", Some("abc1234"), "git")), "{names:?}");
        assert!(names.contains(&("aho-corasick", Some("1.1.4"), "toolchain-vendored")), "{names:?}");
        assert_eq!(r.source_paths.toolchain, 1);
        assert_eq!(r.source_paths.dependencies, 4);
        assert_eq!(r.source_paths.local[0].value, "src/main.rs");
        assert_eq!(r.panic_messages.len(), 1);
        assert!(r.symbols.stripped);
    }

    #[test]
    fn symbols_and_auditable_section() {
        let json = br#"{"format":1,"packages":[{"name":"app","version":"0.1.0","source":"local","dependencies":[1],"root":true},{"name":"serde","version":"1.0.193","source":"crates.io"}]}"#;
        let packed = miniz_oxide::deflate::compress_to_vec_zlib(json, 6);
        let mut data = vec![0u8; 16];
        data.extend(&packed);
        let mut bin = Binary::raw(crate::Arch::X86_64, 0x1000, packed.len() as u64, 16);
        if let Some(s) = bin.sections.first_mut() {
            s.name = ".dep-v0".into();
        }
        let sym = |name: &str| crate::Symbol {
            name: name.into(),
            demangled: None,
            addr: 0,
            size: 0,
            kind: crate::SymbolKind::Function,
            global: true,
            weak: false,
            defined: true,
            dynamic: false,
        };
        bin.symbols = vec![
            sym("_ZN4core9panicking5panic17h0123456789abcdefE"),
            sym("_ZN5myapp6config4load17hfedcba9876543210E"),
            sym("_RNvCs1234_5myapp4main"),
            sym("_ZN3foo3barEv"),
            sym("printf"),
        ];
        let r = inspect(&data, Some(&bin));
        assert_eq!(r.strength, "strong");
        assert_eq!((r.symbols.rust_legacy, r.symbols.rust_v0, r.symbols.total), (2, 1, 5));
        assert!(!r.symbols.stripped);
        assert_eq!(r.symbols.crates[0].value, "myapp");
        assert_eq!(r.symbols.samples[0].demangled, "myapp::config::load");
        let a = r.auditable.expect("auditable data");
        assert_eq!(a.packages.len(), 2);
        assert_eq!(a.root_package_index, Some(0));
        assert_eq!(a.dependency_edges, 1);
        assert_eq!(a.format_version, Some(1));
        assert_eq!(a.packages[1].name, "serde");

        // Corrupt compressed data is reported, not fatal.
        let r = inspect(&vec![0u8; 16 + packed.len()], Some(&bin));
        assert!(r.auditable.is_none());
        assert!(r.auditable_error.is_some());
    }

    #[test]
    fn plain_bytes_are_not_rust() {
        let r = inspect(b"hello world .rsrc /usr/lib/x.rs.bak \xff", None);
        assert_eq!(r.strength, "none");
        assert!(!r.is_rust);
        assert_eq!(inspect(b"RUST_BACKTRACE", None).strength, "weak");
        assert_eq!(inspect(b"", None).strength, "none");
    }
}
