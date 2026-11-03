//! Content-addressed inventories of archives and app bundles (ZIP/APK/IPA/JAR, ASAR, folders),
//! with nested archives expanded to a bounded depth. Pure: callers feed bytes.

use crate::js_app::Cancelled;
use craft_anything_evidence::sha256_hex;
use craft_anything_formats::{asar, java_class, zip};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy)]
pub struct InvLimits {
    pub max_entries: usize,
    /// How deep nested archives are opened (0 = only the outer container).
    pub max_depth: u32,
    /// Largest nested archive opened in memory.
    pub max_nested_bytes: u64,
    /// Largest single entry read (and hashed) from an archive.
    pub max_entry_bytes: u64,
    /// Total bytes decompressed and hashed across the inventory.
    pub max_total_bytes: u64,
}

impl Default for InvLimits {
    fn default() -> Self {
        InvLimits {
            max_entries: 200_000,
            max_depth: 3,
            max_nested_bytes: 512 * 1024 * 1024,
            max_entry_bytes: 1024 * 1024 * 1024,
            max_total_bytes: 8 * 1024 * 1024 * 1024,
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct InvEntry {
    /// Path; members of nested archives use `outer!/inner`.
    pub path: String,
    pub size: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
    /// What the bytes are (`elf`, `zip`, `asar`, `javascript`, `json`, …), or `directory`/`link`.
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    pub depth: u32,
    /// `verified`, `mismatch` or absent, for archives that carry per-file hashes.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub integrity: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Inventory {
    pub root: String,
    pub root_kind: String,
    pub entries: Vec<InvEntry>,
    pub containers: Vec<Value>,
    pub contradictions: Vec<Value>,
    pub truncated: bool,
    pub hashed_bytes: u64,
}

impl Inventory {
    pub fn by_kind(&self) -> BTreeMap<String, usize> {
        let mut m = BTreeMap::new();
        for e in &self.entries {
            *m.entry(e.kind.clone()).or_default() += 1;
        }
        m
    }

    /// `inv_` + sha256 over (path, sha256) pairs, sorted: equal content trees share an id whatever
    /// order their archive lists them in (#281).
    pub fn content_id(&self) -> String {
        let mut pairs: Vec<(&str, Option<&str>)> = self.entries.iter().map(|e| (e.path.as_str(), e.sha256.as_deref())).collect();
        pairs.sort_unstable();
        format!("inv_{}", sha256_hex(craft_anything_evidence::canonical_json(&json!(pairs)).as_bytes()))
    }
}

/// What a blob is, from magic bytes (and the name for text formats).
pub fn sniff_kind(bytes: &[u8], name: &str) -> &'static str {
    let lower = name.to_ascii_lowercase();
    let starts = |m: &[u8]| bytes.starts_with(m);
    if starts(b"\x7fELF") {
        return if lower.ends_with(".node") { "native-addon" } else { "elf" };
    }
    if starts(b"MZ") {
        return if lower.ends_with(".node") { "native-addon" } else { "pe" };
    }
    if starts(&[0xcf, 0xfa, 0xed, 0xfe]) || starts(&[0xce, 0xfa, 0xed, 0xfe]) || starts(&[0xfe, 0xed, 0xfa, 0xcf]) || starts(&[0xfe, 0xed, 0xfa, 0xce]) {
        return if lower.ends_with(".node") { "native-addon" } else { "macho" };
    }
    if starts(&[0xca, 0xfe, 0xba, 0xbe]) {
        // Both start 0xCAFEBABE; the class's version sits where a universal binary counts its slices.
        return if java_class::is_class(bytes) { "java-class" } else { "macho-fat" };
    }
    if starts(b"\0asm") {
        return "wasm";
    }
    if starts(b"dex\n") {
        return "dex";
    }
    if zip::looks_like_zip(bytes) {
        return match lower.rsplit('.').next().unwrap_or("") {
            "apk" | "aab" | "xapk" => "apk",
            "ipa" => "ipa",
            "jar" | "war" | "aar" => "jar",
            "hap" | "hsp" => "hap",
            "appx" | "msix" | "appxbundle" | "msixbundle" => "msix",
            _ => "zip",
        };
    }
    if asar::looks_like_asar(bytes) {
        return "asar";
    }
    if starts(b"bplist00") {
        return "binary-plist";
    }
    if starts(&[0x1f, 0x8b]) {
        return "gzip";
    }
    if starts(b"\x89PNG") {
        return "png";
    }
    if starts(&[0xff, 0xd8, 0xff]) {
        return "jpeg";
    }
    if starts(b"GIF8") {
        return "gif";
    }
    if starts(b"%PDF") {
        return "pdf";
    }
    if starts(b"SQLite format 3\0") {
        return "sqlite";
    }
    if starts(b"xar!") {
        return "xar";
    }
    if starts(b"BOMStore") {
        return "bom";
    }
    if starts(&[0x03, 0x00, 0x08, 0x00]) && lower.ends_with(".xml") {
        return "android-binary-xml";
    }
    let ext = lower.rsplit('.').next().unwrap_or("");
    match ext {
        "js" | "mjs" | "cjs" | "jsx" => "javascript",
        "ts" | "tsx" | "mts" | "cts" => "typescript",
        "map" => "source-map",
        "json" | "json5" => "json",
        "html" | "htm" => "html",
        "css" => "css",
        "plist" if bytes.windows(6).take(1024).any(|w| w == b"<plist") => "xml-plist",
        "xml" => "xml",
        "svg" => "svg",
        "txt" | "md" => "text",
        "abc" => "ark-bytecode",
        "car" => "asset-catalog",
        "nib" => "nib",
        _ if !bytes.is_empty() && std::str::from_utf8(bytes.get(..bytes.len().min(4096)).unwrap_or(&[])).is_ok() => "text",
        _ => "binary",
    }
}

/// What a path is for, by convention.
pub fn path_role(path: &str) -> Option<&'static str> {
    let l = path.to_ascii_lowercase();
    let name = l.rsplit('/').next().unwrap_or(&l);
    Some(if name == "androidmanifest.xml" {
        "android-manifest"
    } else if name.starts_with("classes") && name.ends_with(".dex") {
        "android-code"
    } else if name == "resources.arsc" {
        "android-resources"
    } else if l.starts_with("meta-inf/") && (name.ends_with(".rsa") || name.ends_with(".sf") || name.ends_with(".ec") || name == "manifest.mf") {
        "signature"
    } else if name == "info.plist" {
        "bundle-info"
    } else if l.contains("_codesignature/") || name == "embedded.mobileprovision" || name == "embedded.provisionprofile" {
        "code-signature"
    } else if name.ends_with(".entitlements") {
        "entitlements"
    } else if name == "assets.car" {
        "asset-catalog"
    } else if name.ends_with(".nib") || l.contains(".storyboardc/") {
        "interface"
    } else if name == "module.json" || name == "module.json5" || name == "pack.info" || name == "app.json5" {
        "harmony-manifest"
    } else if name.ends_with(".abc") {
        "harmony-code"
    } else if name == "package.json" {
        "package-manifest"
    } else if name.ends_with(".asar") {
        "electron-archive"
    } else if name.ends_with(".map") {
        "source-map"
    } else if name.ends_with(".js")
        || name.ends_with(".mjs")
        || name.ends_with(".cjs")
        || name.ends_with(".jsbundle")
        || name.ends_with(".bundle") && l.contains("assets/")
    {
        "script"
    } else if name.ends_with(".node") || name.ends_with(".dylib") || name.ends_with(".so") || name.ends_with(".dll") || l.contains(".so.") {
        "native-library"
    } else if l.contains(".framework/") {
        "framework"
    } else if name.ends_with(".plist") {
        "property-list"
    } else {
        return None;
    })
}

/// Builds an inventory; feed it files and archives.
pub struct Inventorier<'c> {
    pub limits: InvLimits,
    pub inv: Inventory,
    cancelled: &'c dyn Fn() -> bool,
    counter: usize,
}

impl<'c> Inventorier<'c> {
    pub fn new(root: &str, root_kind: &str, limits: InvLimits, cancelled: &'c dyn Fn() -> bool) -> Self {
        Inventorier { limits, inv: Inventory { root: root.into(), root_kind: root_kind.into(), ..Default::default() }, cancelled, counter: 0 }
    }

    fn room(&mut self) -> bool {
        if self.inv.entries.len() >= self.limits.max_entries {
            self.inv.truncated = true;
            return false;
        }
        true
    }

    fn tick(&mut self) -> Result<(), Cancelled> {
        self.counter += 1;
        if self.counter.is_multiple_of(64) && (self.cancelled)() { Err(Cancelled) } else { Ok(()) }
    }

    /// Record a directory or link without content.
    pub fn add_marker(&mut self, path: &str, kind: &str, depth: u32, note: Option<String>) {
        if self.room() {
            self.inv.entries.push(InvEntry {
                path: path.into(),
                kind: kind.into(),
                depth,
                note,
                role: path_role(path).map(String::from),
                ..Default::default()
            });
        }
    }

    /// Record a file seen with its bytes; archives inside are expanded.
    pub fn add_file(&mut self, path: &str, bytes: &[u8], depth: u32) -> Result<(), Cancelled> {
        self.tick()?;
        if !self.room() {
            return Ok(());
        }
        self.inv.hashed_bytes = self.inv.hashed_bytes.saturating_add(bytes.len() as u64);
        let kind = sniff_kind(bytes, path);
        self.inv.entries.push(InvEntry {
            path: path.into(),
            size: bytes.len() as u64,
            sha256: Some(sha256_hex(bytes)),
            kind: kind.into(),
            role: path_role(path).map(String::from),
            depth,
            ..Default::default()
        });
        let archive = matches!(kind, "zip" | "apk" | "ipa" | "jar" | "hap" | "msix" | "asar");
        if archive {
            if depth >= self.limits.max_depth {
                self.note_last("nested archive not opened: depth limit");
            } else if bytes.len() as u64 > self.limits.max_nested_bytes {
                self.note_last("nested archive not opened: too large");
            } else {
                self.add_archive(&format!("{path}!/"), bytes, kind, depth + 1)?;
            }
        }
        Ok(())
    }

    fn note_last(&mut self, note: &str) {
        if let Some(e) = self.inv.entries.last_mut() {
            e.note = Some(note.into());
        }
    }

    /// Expand an archive's members under `prefix` (use "" for the root archive).
    pub fn add_archive(&mut self, prefix: &str, bytes: &[u8], kind: &str, depth: u32) -> Result<(), Cancelled> {
        if kind == "asar" {
            return self.add_asar(prefix, bytes, depth);
        }
        let z = match zip::parse(bytes, self.limits.max_entries) {
            Ok(z) => z,
            Err(e) => {
                self.inv.containers.push(json!({"path": prefix, "kind": kind, "error": e.to_string()}));
                return Ok(());
            }
        };
        self.inv.containers.push(
            json!({"path": prefix, "kind": kind, "entries": z.entries.len(), "declared": z.declared_entries, "truncated": z.truncated, "zip64": z.zip64}),
        );
        if z.truncated {
            self.inv.truncated = true;
        }
        for e in &z.entries {
            let path = format!("{prefix}{}", e.name);
            if e.is_dir {
                self.add_marker(path.trim_end_matches('/'), "directory", depth, None);
                continue;
            }
            if self.inv.hashed_bytes.saturating_add(e.uncompressed_size) > self.limits.max_total_bytes {
                self.inv.truncated = true;
                self.add_marker(&path, "unread", depth, Some("total size budget reached".into()));
                continue;
            }
            match zip::read_entry(bytes, e, self.limits.max_entry_bytes) {
                Ok(data) => self.add_file(&path, &data, depth)?,
                Err(err) => {
                    if matches!(err, zip::ZipError::CrcMismatch { .. }) {
                        self.inv.contradictions.push(json!({"path": path, "reason": err.to_string()}));
                    }
                    let note = Some(err.to_string());
                    if self.room() {
                        self.inv.entries.push(InvEntry {
                            path: path.clone(),
                            size: e.uncompressed_size,
                            kind: "unread".into(),
                            role: path_role(&path).map(String::from),
                            depth,
                            note,
                            ..Default::default()
                        });
                    }
                }
            }
        }
        Ok(())
    }

    fn add_asar(&mut self, prefix: &str, bytes: &[u8], depth: u32) -> Result<(), Cancelled> {
        let a = match asar::parse(bytes, self.limits.max_entries) {
            Ok(a) => a,
            Err(e) => {
                self.inv.containers.push(json!({"path": prefix, "kind": "asar", "error": e.to_string()}));
                return Ok(());
            }
        };
        self.inv.containers.push(json!({"path": prefix, "kind": "asar", "entries": a.entries.len(), "truncated": a.truncated, "rejected_names": a.rejected_names, "header_bytes": a.json_bytes}));
        if a.truncated {
            self.inv.truncated = true;
        }
        for name in &a.rejected_names {
            self.inv.contradictions.push(json!({"path": format!("{prefix}{name}"), "reason": "entry name could escape the archive; skipped"}));
        }
        for e in &a.entries {
            let path = format!("{prefix}{}", e.path);
            match e.kind {
                asar::AsarKind::Directory => self.add_marker(&path, "directory", depth, None),
                asar::AsarKind::Link => self.add_marker(&path, "link", depth, e.link.clone().map(|l| format!("link to {l}"))),
                asar::AsarKind::File if e.unpacked => self.add_marker(&path, "unpacked", depth, Some("stored beside the archive in .asar.unpacked".into())),
                asar::AsarKind::File => match asar::file_bytes(bytes, &a, e) {
                    Some(data) => {
                        self.add_file(&path, data, depth)?;
                        if let Some(int) = &e.integrity
                            && int.algorithm.eq_ignore_ascii_case("sha256")
                        {
                            let ok = self.inv.entries.iter().rev().find(|x| x.path == path).and_then(|x| x.sha256.as_deref()) == Some(int.hash.as_str());
                            if let Some(x) = self.inv.entries.iter_mut().rev().find(|x| x.path == path) {
                                x.integrity = Some(if ok { "verified" } else { "mismatch" }.into());
                            }
                            if !ok {
                                self.inv.contradictions.push(json!({"path": path, "reason": "ASAR integrity hash does not match the file content"}));
                            }
                        }
                    }
                    None => {
                        self.inv.contradictions.push(json!({"path": path, "reason": "file data lies outside the archive"}));
                        self.add_marker(&path, "unread", depth, Some("offset/size outside the archive".into()));
                    }
                },
            }
        }
        Ok(())
    }

    pub fn finish(self) -> Inventory {
        self.inv
    }
}

/// Compare two inventories by path and content.
pub fn compare_inventories(l: &Inventory, r: &Inventory, max_rows: usize) -> Value {
    let lm: BTreeMap<&str, &InvEntry> = l.entries.iter().filter(|e| e.sha256.is_some()).map(|e| (e.path.as_str(), e)).collect();
    let rm: BTreeMap<&str, &InvEntry> = r.entries.iter().filter(|e| e.sha256.is_some()).map(|e| (e.path.as_str(), e)).collect();
    let mut added = Vec::new();
    let mut removed = Vec::new();
    let mut changed = Vec::new();
    let mut moved = Vec::new();
    let mut unchanged = 0usize;
    // Where a file may have moved: the right's new paths by content, each taken once, so two
    // copies don't both move to one file (#283).
    let mut move_to: BTreeMap<&str, std::collections::VecDeque<&str>> = BTreeMap::new();
    for x in rm.values().filter(|x| !lm.contains_key(x.path.as_str())) {
        if let Some(h) = x.sha256.as_deref() {
            move_to.entry(h).or_default().push_back(x.path.as_str());
        }
    }
    for (p, e) in &lm {
        match rm.get(p) {
            Some(x) if x.sha256 == e.sha256 => unchanged += 1,
            Some(x) => changed.push(json!({"path": p, "kind": e.kind, "size": [e.size, x.size], "sha256": [e.sha256, x.sha256]})),
            None => match e.sha256.as_deref().and_then(|h| move_to.get_mut(h)).and_then(std::collections::VecDeque::pop_front) {
                Some(to) => moved.push(json!({"from": p, "to": to})),
                None => removed.push(json!({"path": p, "kind": e.kind, "size": e.size})),
            },
        }
    }
    let moved_to: std::collections::BTreeSet<String> = moved.iter().filter_map(|m| m["to"].as_str().map(String::from)).collect();
    for (p, e) in &rm {
        if !lm.contains_key(p) && !moved_to.contains(*p) {
            added.push(json!({"path": p, "kind": e.kind, "size": e.size}));
        }
    }
    let total = added.len() + removed.len() + changed.len() + moved.len();
    json!({
        "identical": total == 0 && l.content_id() == r.content_id(),
        "left": {"root": l.root, "content_id": l.content_id(), "files": lm.len()},
        "right": {"root": r.root, "content_id": r.content_id(), "files": rm.len()},
        "counts": {"added": added.len(), "removed": removed.len(), "changed": changed.len(), "moved": moved.len(), "unchanged": unchanged},
        "added": added.into_iter().take(max_rows).collect::<Vec<_>>(),
        "removed": removed.into_iter().take(max_rows).collect::<Vec<_>>(),
        "changed": changed.into_iter().take(max_rows).collect::<Vec<_>>(),
        "moved": moved.into_iter().take(max_rows).collect::<Vec<_>>(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::electron as fx;

    #[test]
    fn nested_zip_with_asar_inside() {
        let asar = fx::notes_app_asar();
        let z = fx::zip_stored(&[("resources/app.asar", &asar), ("README.txt", b"hi")]);
        let mut inv = Inventorier::new("bundle.zip", "zip", InvLimits::default(), &|| false);
        inv.add_archive("", &z, "zip", 0).unwrap();
        let inv = inv.finish();
        assert!(inv.entries.iter().any(|e| e.path == "resources/app.asar" && e.kind == "asar"));
        let main = inv.entries.iter().find(|e| e.path == "resources/app.asar!/main.js").unwrap();
        assert_eq!(main.kind, "javascript");
        assert_eq!(main.sha256.as_deref(), Some(sha256_hex(fx::MAIN_JS.as_bytes()).as_str()));
        assert!(inv.content_id().starts_with("inv_"));
        // Depth limit stops expansion.
        let mut shallow = Inventorier::new("b", "zip", InvLimits { max_depth: 0, ..Default::default() }, &|| false);
        shallow.add_file("outer.zip", &z, 0).unwrap();
        assert_eq!(shallow.finish().entries.len(), 1);
    }

    #[test]
    fn compare_detects_changes() {
        let mut a = Inventorier::new("a", "directory", InvLimits::default(), &|| false);
        a.add_file("x.js", b"1", 0).unwrap();
        a.add_file("y.js", b"2", 0).unwrap();
        a.add_file("z.js", b"3", 0).unwrap();
        let mut b = Inventorier::new("b", "directory", InvLimits::default(), &|| false);
        b.add_file("x.js", b"1", 0).unwrap();
        b.add_file("y.js", b"22", 0).unwrap();
        b.add_file("moved/z.js", b"3", 0).unwrap();
        b.add_file("new.js", b"4", 0).unwrap();
        let d = compare_inventories(&a.finish(), &b.finish(), 100);
        assert_eq!(d["counts"], json!({"added": 1, "removed": 0, "changed": 1, "moved": 1, "unchanged": 1}));
    }

    /// #281: the same files listed in another order are the same content tree.
    #[test]
    fn member_order_does_not_change_the_content_id() {
        let zip = |files: &[(&str, &[u8])]| {
            let mut i = Inventorier::new("a.zip", "zip", InvLimits::default(), &|| false);
            i.add_archive("", &fx::zip_stored(files), "zip", 0).unwrap();
            i.finish()
        };
        let (x, y): (&[u8], &[u8]) = (b"one", b"two");
        let (ab, ba) = (zip(&[("a.txt", x), ("b.txt", y)]), zip(&[("b.txt", y), ("a.txt", x)]));
        assert_eq!(ab.content_id(), ba.content_id());
        assert_eq!(compare_inventories(&ab, &ba, 100)["identical"], true);
        assert_ne!(ab.content_id(), zip(&[("a.txt", y), ("b.txt", x)]).content_id(), "swapped contents differ");
    }

    /// #283: two identical old files both "moved" to one new file, and nothing was removed.
    #[test]
    fn each_new_file_is_one_move() {
        let inv = |files: &[&str]| {
            let mut i = Inventorier::new("x", "directory", InvLimits::default(), &|| false);
            for f in files {
                i.add_file(f, b"SAME", 0).unwrap();
            }
            i.finish()
        };
        let d = compare_inventories(&inv(&["a/license.txt", "b/license.txt"]), &inv(&["c/license.txt"]), 100);
        assert_eq!(d["counts"], json!({"added": 0, "removed": 1, "changed": 0, "moved": 1, "unchanged": 0}), "{d}");
        let d = compare_inventories(&inv(&["a/license.txt", "b/license.txt"]), &inv(&["c/license.txt", "d/license.txt"]), 100);
        assert_eq!(d["counts"], json!({"added": 0, "removed": 0, "changed": 0, "moved": 2, "unchanged": 0}), "{d}");
        let to: std::collections::BTreeSet<&str> = d["moved"].as_array().unwrap().iter().filter_map(|m| m["to"].as_str()).collect();
        assert_eq!(to.len(), 2, "two different destinations: {d}");
    }

    #[test]
    fn java_classes_and_universal_binaries_by_contents() {
        let class = [0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 52];
        let fat = [0xca, 0xfe, 0xba, 0xbe, 0, 0, 0, 2];
        assert_eq!(sniff_kind(&class, "Main.class"), "java-class");
        assert_eq!(sniff_kind(&class, "lib/Main"), "java-class");
        assert_eq!(sniff_kind(&fat, "MyApp"), "macho-fat");
        assert_eq!(sniff_kind(&fat, "odd.class"), "macho-fat");
        assert_eq!(sniff_kind(&[0xca, 0xfe, 0xba, 0xbe], "short"), "macho-fat");
    }

    #[test]
    fn hostile_archives_do_not_panic() {
        let z = fx::zip_stored(&[("a/../../evil", b"x"), ("/abs", b"y")]);
        for cut in [0, 10, 30, z.len() / 2, z.len() - 1] {
            let mut inv = Inventorier::new("z", "zip", InvLimits::default(), &|| false);
            let _ = inv.add_archive("", &z[..cut], "zip", 0);
            let _ = inv.add_file("x.asar", &z[..cut], 0);
        }
    }
}
