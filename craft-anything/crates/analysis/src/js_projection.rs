//! Platform application graphs projected from an artifact inventory (Android, Apple, HarmonyOS).
//!
//! These read only the inventory's paths, kinds and sizes: package layout, code containers,
//! native libraries by ABI, embedded runtimes (React Native, Flutter, Electron, Cordova/Capacitor,
//! Xamarin/.NET, Unity, Hermes) and signing material. Runtime and framework hints are guesses
//! from file names and are labelled as such; binary manifests are not decoded here.

use crate::js_inventory::{InvEntry, Inventory};
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn name_of(p: &str) -> &str {
    p.rsplit('/').next().unwrap_or(p)
}

struct Hints<'i> {
    entries: &'i [InvEntry],
}

impl Hints<'_> {
    fn any(&self, f: impl Fn(&str) -> bool) -> Vec<String> {
        self.entries.iter().filter(|e| f(&e.path.to_ascii_lowercase())).map(|e| e.path.clone()).take(8).collect()
    }
}

/// (runtime, evidence-path predicate) pairs shared by the platforms.
fn runtimes(h: &Hints<'_>) -> Vec<Value> {
    let checks: Vec<(&str, Vec<String>)> = vec![
        (
            "react-native",
            h.any(|p| {
                p.ends_with("index.android.bundle")
                    || p.ends_with("main.jsbundle")
                    || p.contains("libreactnativejni")
                    || p.contains("react.framework/")
                    || p.contains("libreact_render")
            }),
        ),
        ("hermes", h.any(|p| p.contains("libhermes") || p.contains("hermes.framework/"))),
        ("flutter", h.any(|p| p.contains("libflutter.so") || p.contains("flutter.framework/") || p.contains("flutter_assets/"))),
        (
            "electron",
            h.any(|p| {
                p.ends_with("app.asar") || p.contains("electron framework.framework/") || p.ends_with("/electron") || p.ends_with("resources/app/package.json")
            }),
        ),
        (
            "cordova-or-capacitor",
            h.any(|p| {
                p.contains("assets/www/index.html")
                    || p.contains("assets/public/index.html")
                    || p.ends_with("capacitor.config.json")
                    || p.ends_with("cordova.js")
                    || p.contains("/www/index.html")
            }),
        ),
        (
            "dotnet-xamarin-maui",
            h.any(|p| {
                p.contains("libmonodroid") || p.contains("libmonosgen") || p.contains("/assemblies/") || p.contains("xamarin") || p.contains("libxamarin")
            }),
        ),
        ("unity", h.any(|p| p.contains("libunity.so") || p.contains("unityframework.framework/") || p.contains("assets/bin/data/"))),
        ("godot", h.any(|p| p.contains("libgodot"))),
        ("kotlin", h.any(|p| p.ends_with(".kotlin_module") || p.starts_with("kotlin/"))),
        ("swift-runtime", h.any(|p| name_of(p).starts_with("libswift") && p.ends_with(".dylib"))),
        ("arkts", h.any(|p| p.ends_with("modules.abc"))),
        ("webview-content", h.any(|p| p.ends_with(".html") && !p.contains("license"))),
    ];
    checks.into_iter().filter(|(_, ev)| !ev.is_empty()).map(|(n, ev)| json!({"runtime": n, "evidence": ev, "confidence": "inferred"})).collect()
}

fn native_by_abi(entries: &[InvEntry], marker: &str) -> BTreeMap<String, Vec<String>> {
    let mut m: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for e in entries {
        let p = e.path.as_str();
        if let Some(i) = p.find(marker) {
            let rest = p.get(i + marker.len()..).unwrap_or("");
            if let Some((abi, file)) = rest.split_once('/')
                && (file.ends_with(".so") || file.contains(".so."))
            {
                let v = m.entry(abi.to_string()).or_default();
                if v.len() < 500 {
                    v.push(file.to_string());
                }
            }
        }
    }
    m
}

fn graph(nodes: &[(String, &str, String)], root: &str) -> Value {
    json!({
        "nodes": std::iter::once(json!({"id": format!("app:{root}"), "kind": "application", "label": root}))
            .chain(nodes.iter().map(|(id, kind, label)| json!({"id": id, "kind": kind, "label": label})))
            .collect::<Vec<_>>(),
        "edges": nodes.iter().map(|(id, _, _)| json!({"from": format!("app:{root}"), "to": id, "kind": "contains"})).collect::<Vec<_>>(),
    })
}

/// Android (APK/AAB/XAPK or an extracted folder).
pub fn project_android(inv: &Inventory) -> Value {
    let e = &inv.entries;
    let h = Hints { entries: e };
    let find = |f: &dyn Fn(&str) -> bool| e.iter().filter(|x| f(&x.path)).map(|x| x.path.clone()).collect::<Vec<_>>();
    let manifests = find(&|p| name_of(p) == "AndroidManifest.xml");
    let dex = find(&|p| name_of(p).starts_with("classes") && p.ends_with(".dex"));
    let natives = native_by_abi(e, "lib/");
    let signing = find(&|p| p.contains("META-INF/") && (p.ends_with(".RSA") || p.ends_with(".SF") || p.ends_with(".EC") || p.ends_with("MANIFEST.MF")));
    let splits = find(&|p| p.ends_with(".apk") && p != inv.root);
    let assets = e.iter().filter(|x| x.path.contains("assets/")).count();
    let mut nodes: Vec<(String, &str, String)> = Vec::new();
    for m in &manifests {
        nodes.push((format!("manifest:{m}"), "manifest", m.clone()));
    }
    for d in &dex {
        nodes.push((format!("dex:{d}"), "code", d.clone()));
    }
    for (abi, libs) in &natives {
        nodes.push((format!("abi:{abi}"), "native-abi", format!("{abi} ({} libraries)", libs.len())));
    }
    for s in &splits {
        nodes.push((format!("split:{s}"), "split-apk", s.clone()));
    }
    let rts = runtimes(&h);
    let mut limitations = vec!["AndroidManifest.xml is binary XML; components, permissions and the package name are not decoded by this projection."];
    if manifests.is_empty() {
        limitations.push("No AndroidManifest.xml in the inventory: this may not be an Android package.");
    }
    json!({
        "platform": "android",
        "recognised": !manifests.is_empty() || !dex.is_empty(),
        "manifests": manifests, "code": dex, "native_libraries": natives, "signing": signing, "split_apks": splits,
        "resources": {"arsc": e.iter().any(|x| name_of(&x.path) == "resources.arsc"), "res_files": e.iter().filter(|x| x.path.contains("res/")).count(), "asset_files": assets},
        "runtimes": rts,
        "graph": graph(&nodes, &inv.root),
        "next_steps": next_steps(&h),
        "limitations": limitations,
    })
}

fn apple_bundle_kind(root: &str, inv: &Inventory) -> &'static str {
    let name = if root.is_empty() && inv.root_kind == "directory" { inv.root.as_str() } else { root };
    if name.ends_with(".appex") {
        "extension"
    } else if name.ends_with(".xpc") {
        "xpc-service"
    } else {
        "bundle"
    }
}

/// Apple (.ipa, .app bundle, macOS .app folder).
pub fn project_apple(inv: &Inventory) -> Value {
    let e = &inv.entries;
    let h = Hints { entries: e };
    // Bundle roots have an Info.plist directly inside (iOS) or in Contents/ (macOS).
    let mut apps: Vec<String> = Vec::new();
    for x in e {
        let p = x.path.as_str();
        if name_of(p) == "Info.plist" {
            let dir = p.rsplit_once('/').map_or("", |(d, _)| d);
            // A directory's name identifies its bundle; an archive's name identifies the container.
            if dir == "Contents" && inv.root_kind == "directory" && ![".app", ".appex", ".xpc"].iter().any(|suffix| inv.root.ends_with(*suffix)) {
                continue;
            }
            // A selected macOS bundle has no directory prefix before Contents.
            let root = if dir == "Contents" { "" } else { dir.strip_suffix("/Contents").unwrap_or(dir) };
            if (root.ends_with(".app") || root.ends_with(".appex") || root.ends_with(".xpc") || root.is_empty())
                && !apps.contains(&root.to_string())
                && apps.len() < 64
            {
                apps.push(root.to_string());
            }
        }
    }
    let frameworks: Vec<String> = {
        let mut v: Vec<String> = e
            .iter()
            .filter_map(|x| {
                let i = x.path.find(".framework/")?;
                Some(x.path.get(..i + ".framework".len())?.to_string())
            })
            .collect();
        v.sort();
        v.dedup();
        v.truncate(500);
        v
    };
    let extensions: Vec<String> = apps.iter().filter(|a| apple_bundle_kind(a, inv) == "extension").cloned().collect();
    let services: Vec<String> = apps.iter().filter(|a| apple_bundle_kind(a, inv) == "xpc-service").cloned().collect();
    let executables: Vec<Value> = e
        .iter()
        .filter(|x| {
            matches!(x.kind.as_str(), "macho" | "macho-fat")
                && !x.path.ends_with(".dylib")
                && (!x.path.contains(".framework/")
                    || services.iter().any(|s| x.path.strip_prefix(s).is_some_and(|rest| rest.starts_with('/') && !rest.contains(".framework/"))))
        })
        .map(|x| json!({"path": x.path, "kind": x.kind, "size": x.size}))
        .take(64)
        .collect();
    let dylibs: Vec<String> = e.iter().filter(|x| x.path.ends_with(".dylib")).map(|x| x.path.clone()).take(500).collect();
    let signing: Vec<String> = e
        .iter()
        .filter(|x| x.role.as_deref() == Some("code-signature") || x.role.as_deref() == Some("entitlements"))
        .map(|x| x.path.clone())
        .take(64)
        .collect();
    let interfaces = e.iter().filter(|x| x.role.as_deref() == Some("interface")).count();
    let catalogs: Vec<String> = e.iter().filter(|x| x.role.as_deref() == Some("asset-catalog")).map(|x| x.path.clone()).collect();
    let mut nodes: Vec<(String, &str, String)> = Vec::new();
    for a in &apps {
        let kind = apple_bundle_kind(a, inv);
        nodes.push((format!("bundle:{a}"), kind, a.clone()));
    }
    for f in &frameworks {
        nodes.push((format!("framework:{f}"), "framework", name_of(f).to_string()));
    }
    for x in &executables {
        if let Some(p) = x.get("path").and_then(Value::as_str) {
            nodes.push((format!("exe:{p}"), "executable", p.to_string()));
        }
    }
    // Only a bundle (an Info.plist root) is an app; a lone Mach-O is a program, not an app.
    let shape = match (apps.is_empty(), executables.is_empty()) {
        (false, _) => "app-bundle",
        (true, false) => "bare-executable",
        (true, true) => "none",
    };
    json!({
        "platform": "apple",
        "recognised": !apps.is_empty(),
        "shape": shape,
        "bundles": apps, "extensions": extensions, "services": services, "executables": executables, "frameworks": frameworks, "dylibs": dylibs,
        "signing": signing, "interface_files": interfaces, "asset_catalogs": catalogs,
        "runtimes": runtimes(&h),
        "graph": graph(&nodes, &inv.root),
        "next_steps": next_steps(&h),
        "limitations": ["Info.plist values, entitlements and code signatures are listed, not decoded, by this projection; use apple_plist_show and apple_signature_show for those."],
    })
}

/// HarmonyOS (.hap/.hsp modules or an .app pack).
pub fn project_harmony(inv: &Inventory) -> Value {
    let e = &inv.entries;
    let h = Hints { entries: e };
    let modules: Vec<String> = e.iter().filter(|x| matches!(name_of(&x.path), "module.json" | "module.json5")).map(|x| x.path.clone()).collect();
    let haps: Vec<String> = e.iter().filter(|x| x.kind == "hap" || x.path.ends_with(".hap") || x.path.ends_with(".hsp")).map(|x| x.path.clone()).collect();
    let abc: Vec<String> = e.iter().filter(|x| x.path.ends_with(".abc")).map(|x| x.path.clone()).take(200).collect();
    let natives = native_by_abi(e, "libs/");
    let pack_info: Vec<String> = e.iter().filter(|x| name_of(&x.path) == "pack.info").map(|x| x.path.clone()).collect();
    let mut nodes: Vec<(String, &str, String)> = Vec::new();
    for m in &modules {
        nodes.push((format!("module:{m}"), "module-manifest", m.clone()));
    }
    for hp in &haps {
        nodes.push((format!("hap:{hp}"), "hap", hp.clone()));
    }
    for a in &abc {
        nodes.push((format!("abc:{a}"), "code", a.clone()));
    }
    for (abi, libs) in &natives {
        nodes.push((format!("abi:{abi}"), "native-abi", format!("{abi} ({} libraries)", libs.len())));
    }
    // module.json is JSON text: report what we can read from the inventory without its bytes.
    json!({
        "platform": "harmony",
        "recognised": !modules.is_empty() || !abc.is_empty() || !haps.is_empty(),
        "module_manifests": modules, "packages": haps, "pack_info": pack_info, "ark_bytecode": abc, "native_libraries": natives,
        "resources": e.iter().filter(|x| x.path.contains("resources/")).count(),
        "runtimes": runtimes(&h),
        "graph": graph(&nodes, &inv.root),
        "next_steps": next_steps(&h),
        "limitations": ["Ark bytecode (.abc) is listed, not disassembled.", "module.json contents (abilities, permissions) are not read by this projection; open the file to see them."],
    })
}

fn next_steps(h: &Hints<'_>) -> Vec<String> {
    let mut v = Vec::new();
    if !h.any(|p| p.ends_with("app.asar")).is_empty() {
        v.push("Run js_app_map on the app.asar (core_archive_extract first if it is nested).".to_string());
    }
    if !h.any(|p| p.ends_with("index.android.bundle") || p.ends_with("main.jsbundle")).is_empty() {
        v.push(
            "The JavaScript bundle can be analysed with js_app_map after core_archive_extract (Hermes bytecode bundles are not JavaScript text).".to_string(),
        );
    }
    if !h.any(|p| p.contains("/www/index.html") || p.contains("/public/index.html")).is_empty() {
        v.push("The embedded web app (www/ or public/) can be analysed as a web bundle folder after core_archive_extract.".to_string());
    }
    v
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::js_inventory::{InvLimits, Inventorier};

    fn inv(files: &[(&str, &[u8])]) -> Inventory {
        let mut i = Inventorier::new("x", "zip", InvLimits::default(), &|| false);
        for (p, b) in files {
            i.add_file(p, b, 0).unwrap();
        }
        i.finish()
    }

    #[test]
    fn android_projection() {
        let i = inv(&[
            ("AndroidManifest.xml", &[3, 0, 8, 0]),
            ("classes.dex", b"dex\n035\0"),
            ("classes2.dex", b"dex\n035\0"),
            ("lib/arm64-v8a/libflutter.so", b"\x7fELF"),
            ("lib/arm64-v8a/libapp.so", b"\x7fELF"),
            ("assets/flutter_assets/AssetManifest.json", b"{}"),
            ("META-INF/CERT.RSA", b"x"),
        ]);
        let p = project_android(&i);
        assert_eq!(p["recognised"], true);
        assert_eq!(p["code"].as_array().unwrap().len(), 2);
        assert_eq!(p["native_libraries"]["arm64-v8a"].as_array().unwrap().len(), 2);
        assert!(p["runtimes"].as_array().unwrap().iter().any(|r| r["runtime"] == "flutter"));
        assert_eq!(p["signing"], json!(["META-INF/CERT.RSA"]));
    }

    #[test]
    fn relative_macos_bundle_and_nested_xpc_are_recognised() {
        let p = project_apple(&inv(&[
            ("Contents/Info.plist", b"bplist00"),
            ("Contents/MacOS/Example", &[0xcf, 0xfa, 0xed, 0xfe]),
            ("Contents/XPCServices/Helper.xpc/Contents/Info.plist", b"bplist00"),
            ("Contents/XPCServices/Helper.xpc/Contents/MacOS/Helper", &[0xcf, 0xfa, 0xed, 0xfe]),
        ]));
        assert_eq!(p["recognised"], true);
        assert_eq!(p["shape"], "app-bundle");
        assert_eq!(p["bundles"], json!(["", "Contents/XPCServices/Helper.xpc"]));
        assert_eq!(p["services"], json!(["Contents/XPCServices/Helper.xpc"]));
        assert_eq!(p["executables"].as_array().unwrap().len(), 2);
        assert!(p["extensions"].as_array().unwrap().is_empty());
        let service = "Contents/XPCServices/Helper.xpc";
        assert!(p["graph"]["nodes"].as_array().unwrap().iter().any(|n| n["id"] == format!("bundle:{service}") && n["kind"] == "xpc-service"));
        assert!(p["graph"]["nodes"].as_array().unwrap().iter().any(|n| n["id"] == "bundle:" && n["kind"] == "bundle"));
        assert!(p["graph"]["edges"].as_array().unwrap().iter().any(|edge| edge["to"] == format!("bundle:{service}") && edge["kind"] == "contains"));
    }

    #[test]
    fn apple_bundle_layout_controls() {
        for (plist, root) in [
            ("Example.app/Contents/Info.plist", "Example.app"),
            ("Info.plist", ""),
            ("Contents/XPCServices/Helper.xpc/Info.plist", "Contents/XPCServices/Helper.xpc"),
        ] {
            let p = project_apple(&inv(&[(plist, b"bplist00")]));
            assert_eq!(p["recognised"], true, "{plist}");
            assert_eq!(p["bundles"], json!([root]));
        }
        let p = project_apple(&inv(&[("Resources/Info.plist", b"bplist00")]));
        assert_eq!(p["recognised"], false);
        assert_eq!(p["shape"], "none");
        let bare = project_apple(&inv(&[("Contents/MacOS/Example", &[0xcf, 0xfa, 0xed, 0xfe])]));
        assert_eq!(bare["recognised"], false);
        assert_eq!(bare["shape"], "bare-executable");
    }

    #[test]
    fn selected_apple_service_and_extension_keep_their_type() {
        for (name, field, kind) in [("Helper.xpc", "services", "xpc-service"), ("Share.appex", "extensions", "extension")] {
            let mut inventory = inv(&[("Contents/Info.plist", b"bplist00"), ("Contents/MacOS/Helper", &[0xcf, 0xfa, 0xed, 0xfe])]);
            inventory.root = name.into();
            inventory.root_kind = "directory".into();
            let p = project_apple(&inventory);
            assert_eq!(p[field], json!([""]), "{name}");
            assert_eq!(p["bundles"], json!([""]));
            assert!(p["graph"]["nodes"].as_array().unwrap().iter().any(|n| n["id"] == "bundle:" && n["kind"] == kind));
        }
    }

    #[test]
    fn framework_hosted_xpc_keeps_only_service_executables() {
        let service = "Contents/Frameworks/Example.framework/Versions/A/XPCServices/Helper.xpc";
        let executable = format!("{service}/Contents/MacOS/Helper");
        let p = project_apple(&inv(&[
            (&format!("{service}/Contents/Info.plist"), b"bplist00"),
            (&executable, &[0xcf, 0xfa, 0xed, 0xfe]),
            ("Contents/Frameworks/Example.framework/Versions/A/Example", &[0xcf, 0xfa, 0xed, 0xfe]),
            (&format!("{service}/Contents/Frameworks/Private.framework/Private"), &[0xcf, 0xfa, 0xed, 0xfe]),
            (&format!("{service}/Contents/MacOS/Private.dylib"), &[0xcf, 0xfa, 0xed, 0xfe]),
            (&format!("{service}-other/Contents/MacOS/Other"), &[0xcf, 0xfa, 0xed, 0xfe]),
        ]));
        assert_eq!(p["services"], json!([service]));
        let paths: Vec<_> = p["executables"].as_array().unwrap().iter().map(|v| v["path"].as_str().unwrap()).collect();
        assert_eq!(paths, vec![executable.as_str()]);
    }

    #[test]
    fn root_relative_apple_layout_distinguishes_directories_from_archives() {
        for (name, kind, recognised) in [("Data", "directory", false), ("Example.app", "directory", true), ("bundle.zip", "zip", true)] {
            let mut inventory = inv(&[("Contents/Info.plist", b"bplist00"), ("Contents/MacOS/Example", &[0xcf, 0xfa, 0xed, 0xfe])]);
            inventory.root = name.into();
            inventory.root_kind = kind.into();
            let p = project_apple(&inventory);
            assert_eq!(p["recognised"], recognised, "{name}");
            assert_eq!(p["shape"], if recognised { "app-bundle" } else { "bare-executable" });
        }
    }

    #[test]
    fn apple_and_harmony_projections() {
        let a = inv(&[
            ("Payload/Notes.app/Info.plist", b"bplist00"),
            ("Payload/Notes.app/Notes", &[0xcf, 0xfa, 0xed, 0xfe]),
            ("Payload/Notes.app/Frameworks/Flutter.framework/Flutter", &[0xcf, 0xfa, 0xed, 0xfe]),
            ("Payload/Notes.app/PlugIns/Share.appex/Info.plist", b"bplist00"),
            ("Payload/Notes.app/_CodeSignature/CodeResources", b"<plist>"),
        ]);
        let p = project_apple(&a);
        assert_eq!(p["bundles"], json!(["Payload/Notes.app", "Payload/Notes.app/PlugIns/Share.appex"]));
        assert_eq!(p["extensions"], json!(["Payload/Notes.app/PlugIns/Share.appex"]));
        assert_eq!(p["frameworks"], json!(["Payload/Notes.app/Frameworks/Flutter.framework"]));
        assert_eq!((p["recognised"].clone(), p["shape"].clone()), (json!(true), json!("app-bundle")));
        // A lone Mach-O is a program, not an app.
        let bare = project_apple(&inv(&[("Notes", &[0xcf, 0xfa, 0xed, 0xfe])]));
        assert_eq!((bare["recognised"].clone(), bare["shape"].clone()), (json!(false), json!("bare-executable")));
        assert_eq!(project_apple(&inv(&[("x.txt", b"x")]))["shape"], "none");
        let h = inv(&[("module.json", b"{}"), ("ets/modules.abc", b"PANDA"), ("libs/arm64-v8a/libentry.so", b"\x7fELF")]);
        let q = project_harmony(&h);
        assert_eq!(q["recognised"], true);
        assert!(q["runtimes"].as_array().unwrap().iter().any(|r| r["runtime"] == "arkts"));
        assert_eq!(project_harmony(&inv(&[("x.txt", b"x")]))["recognised"], false);
    }
}
