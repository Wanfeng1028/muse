//! `cargo xtask <layers | locks | i18n-coverage | tools [--check] | wasm | licenses | schemas [--check] | pending [--count] | secrets [--history] | ci | version [set X.Y.Z] | ico <out.ico> <png>...>`

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

mod i18n_coverage;
mod ico;
mod locks;
mod secrets;

/// Workspace crates and their layer. A crate may depend only on strictly lower layers
/// (L0 format crates depend on nothing in the workspace).
const LAYERS: &[(&str, u8)] = &[
    ("craft-anything-evidence", 0),
    ("craft-anything-formats", 0),
    ("craft-anything-disasm", 1),
    ("craft-anything-js", 1),
    ("craft-anything-analysis", 2),
    ("craft-anything-platform", 2),
    ("craft-anything-engines", 3),
    ("craft-anything-engine", 4),
    ("craft-anything-ai", 5),
    ("craft-anything-mcp", 5),
    ("craft-anything-setup", 5),
    ("craft-anything-ui-egui", 6),
];

/// Crates that must build for wasm32-unknown-unknown (static analysis in the browser).
const WASM_CRATES: &[&str] = &["craft-anything-evidence", "craft-anything-formats", "craft-anything-disasm", "craft-anything-js", "craft-anything-analysis"];

/// UI toolkits only the UI layer may use.
const UI_ONLY: &[&str] = &["egui", "eframe", "winit", "rfd", "egui_extras", "egui_kittest"];

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let root = workspace_root();
    let ok = match args.first().map(String::as_str) {
        Some("layers") => layers(&root),
        Some("locks") => locks::check(&root),
        Some("i18n-coverage") => i18n_coverage::check(&root),
        Some("tools") => tools(&root, args.iter().any(|a| a == "--check")),
        Some("schemas") => schemas(&root, args.iter().any(|a| a == "--check")),
        Some("wasm") => wasm(),
        Some("licenses") => licenses(),
        Some("version") => version(&root, args.get(1).map(String::as_str), args.get(2).map(String::as_str)),
        Some("pending") => pending(&root, args.iter().any(|a| a == "--count")),
        Some("secrets") => secrets::secrets(&root, args.iter().any(|a| a == "--history")),
        Some("ico") => {
            let rest: Vec<&str> = args.iter().skip(1).map(String::as_str).collect();
            ico::run(&rest).map_err(|e| eprintln!("ico: {e}")).is_ok()
        }
        Some("ci") => {
            layers(&root)
                && locks::check(&root)
                && i18n_coverage::check(&root)
                && secrets::secrets(&root, false)
                && run("cargo", &["fmt", "--all", "--check"])
                && run("cargo", &["clippy", "--workspace", "--all-targets", "--", "-D", "warnings"])
                && run("cargo", &["test", "--workspace"])
                // The off-by-default WASM plugin host, built and tested on its own.
                && run("cargo", &["clippy", "-p", "craft-anything-engine", "--features", "wasm-plugins", "--all-targets", "--", "-D", "warnings"])
                && run("cargo", &["test", "-p", "craft-anything-engine", "--features", "wasm-plugins"])
                && tools(&root, true)
                && schemas(&root, true)
                && wasm()
        }
        _ => {
            eprintln!(
                "usage: cargo xtask <layers | locks | i18n-coverage | tools [--check] | wasm | licenses | schemas [--check] | pending [--count] | secrets [--history] | ci | version [set X.Y.Z] | ico <out.ico> <png>...>"
            );
            false
        }
    };
    if ok { ExitCode::SUCCESS } else { ExitCode::FAILURE }
}

/// `version`: print `[workspace.package] version` (the single source of the app version).
/// `version set X.Y.Z[-pre]`: rewrite it and refresh the workspace entries in Cargo.lock.
fn version(root: &Path, sub: Option<&str>, value: Option<&str>) -> bool {
    let path = root.join("Cargo.toml");
    let Ok(text) = std::fs::read_to_string(&path) else {
        eprintln!("can't read {}", path.display());
        return false;
    };
    // The line index of `version = "..."` inside [workspace.package], and its value.
    let mut in_pkg = false;
    let mut found: Option<(usize, String)> = None;
    for (i, line) in text.lines().enumerate() {
        let t = line.trim();
        if t.starts_with('[') {
            in_pkg = t == "[workspace.package]";
            continue;
        }
        if in_pkg && let Some(v) = t.strip_prefix("version = \"").and_then(|r| r.strip_suffix('"')) {
            found = Some((i, v.to_string()));
            break;
        }
    }
    let Some((line_no, cur)) = found else {
        eprintln!("no version in [workspace.package] of {}", path.display());
        return false;
    };
    match (sub, value) {
        (None, _) => {
            println!("{cur}");
            true
        }
        (Some("set"), Some(v)) => {
            let core = v.split(['-', '+']).next().unwrap_or_default();
            let parts: Vec<&str> = core.split('.').collect();
            let valid = parts.len() == 3 && parts.iter().all(|p| !p.is_empty() && p.parse::<u64>().is_ok()) && !v.chars().any(char::is_whitespace);
            if !valid {
                eprintln!("version must look like 1.2.3 or 1.2.3-rc.1, not {v:?}");
                return false;
            }
            let mut out: Vec<String> = text.lines().map(str::to_string).collect();
            if let Some(line) = out.get_mut(line_no) {
                *line = format!("version = \"{v}\"");
            }
            let mut new = out.join("\n");
            if text.ends_with('\n') {
                new.push('\n');
            }
            if let Err(e) = std::fs::write(&path, new) {
                eprintln!("can't write {}: {e}", path.display());
                return false;
            }
            eprintln!("version {cur} -> {v}");
            run("cargo", &["update", "--workspace", "--offline"]) || run("cargo", &["update", "--workspace"])
        }
        _ => {
            eprintln!("usage: cargo xtask version [set X.Y.Z]");
            false
        }
    }
}

fn workspace_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().map(Path::to_path_buf).unwrap_or(here)
}

fn run(cmd: &str, args: &[&str]) -> bool {
    eprintln!("$ {cmd} {}", args.join(" "));
    Command::new(cmd).args(args).status().map(|s| s.success()).unwrap_or(false)
}

fn manifest_deps(path: &Path) -> (String, Vec<String>) {
    let text = std::fs::read_to_string(path).unwrap_or_default();
    let v: toml::Table = toml::from_str(&text).unwrap_or_default();
    let name = v.get("package").and_then(|p| p.get("name")).and_then(|n| n.as_str()).unwrap_or_default().to_string();
    let mut deps = Vec::new();
    let mut collect = |t: Option<&toml::Value>| {
        if let Some(t) = t.and_then(|t| t.as_table()) {
            deps.extend(t.keys().cloned());
        }
    };
    collect(v.get("dependencies"));
    if let Some(targets) = v.get("target").and_then(|t| t.as_table()) {
        for t in targets.values() {
            collect(t.get("dependencies"));
        }
    }
    (name, deps)
}

/// Apps (`apps/*`) sit above every crate: they may depend on any crate, but only an app built on
/// the UI crate may use a UI toolkit, and test helpers stay out of shipped binaries.
const APP_LAYER: u8 = 7;

/// Apps that are user interfaces of their own. The browser viewer can't build on the UI crate
/// (it pulls in native-only crates), so it draws with egui directly and may use only the
/// wasm-safe crates.
const UI_APPS: &[&str] = &["craft-anything", "craft-anything-web"];
const WASM_APPS: &[&str] = &["craft-anything-web"];

fn layers(root: &Path) -> bool {
    let layer: BTreeMap<&str, u8> = LAYERS.iter().copied().collect();
    let mut ok = true;
    let mut manifests = Vec::new();
    for dir in ["crates", "apps"] {
        let Ok(entries) = std::fs::read_dir(root.join(dir)) else {
            eprintln!("layers: cannot read {dir}/");
            return false;
        };
        manifests.extend(entries.flatten().map(|e| (dir == "apps", e.path().join("Cargo.toml"))));
    }
    for (is_app, manifest) in manifests {
        let (name, deps) = manifest_deps(&manifest);
        if name == "craft-anything-testkit" {
            continue;
        }
        let mine = if is_app {
            APP_LAYER
        } else if let Some(&l) = layer.get(name.as_str()) {
            l
        } else {
            eprintln!("layers: {name} is not registered in xtask/src/main.rs LAYERS");
            ok = false;
            continue;
        };
        let ui_allowed = mine == 6 || (is_app && (UI_APPS.contains(&name.as_str()) || deps.iter().any(|d| d == "craft-anything-ui-egui")));
        for d in &deps {
            if let Some(&theirs) = layer.get(d.as_str())
                && theirs >= mine
            {
                eprintln!("layers: {name} (L{mine}) depends on {d} (L{theirs})");
                ok = false;
            }
            if !ui_allowed && UI_ONLY.contains(&d.as_str()) {
                eprintln!("layers: {name} (L{mine}) uses UI toolkit {d}; only ui crates (and apps built on them) may");
                ok = false;
            }
            if WASM_APPS.contains(&name.as_str()) && layer.contains_key(d.as_str()) && !WASM_CRATES.contains(&d.as_str()) {
                eprintln!("layers: browser app {name} depends on {d}, which doesn't build for wasm");
                ok = false;
            }
            if is_app && d == "craft-anything-testkit" {
                eprintln!("layers: app {name} depends on craft-anything-testkit; use it as a dev-dependency only");
                ok = false;
            }
        }
    }
    ok &= process_calls_only_in_platform(root);
    ok &= ui_has_no_side_effects(root);
    ok &= no_real_machine_sessions(root);
    if ok {
        eprintln!("layers: ok");
    }
    ok
}

/// Golden rule 10: every external program goes through `craft_anything_platform::process`, so
/// `std::process::Command` may appear only in crates/platform, xtask and test code (`tests/`
/// folders, and everything after a file's first `#[cfg(test)]` / `#[cfg(all(test, …))]`).
fn process_calls_only_in_platform(root: &Path) -> bool {
    fn walk(dir: &Path, files: &mut Vec<PathBuf>) {
        let Ok(entries) = std::fs::read_dir(dir) else { return };
        for e in entries.flatten() {
            let p = e.path();
            let name = e.file_name().to_string_lossy().into_owned();
            if p.is_dir() {
                if !matches!(name.as_str(), "target" | "tests" | "platform" | "xtask") && !name.starts_with('.') {
                    walk(&p, files);
                }
            } else if name.ends_with(".rs") {
                files.push(p);
            }
        }
    }
    let mut files = Vec::new();
    walk(&root.join("crates"), &mut files);
    walk(&root.join("apps"), &mut files);
    let mut ok = true;
    for f in files {
        let text = std::fs::read_to_string(&f).unwrap_or_default();
        for (i, line) in text.lines().enumerate() {
            let code = line.trim_start();
            if code.starts_with("#[cfg(test)]") || code.starts_with("#[cfg(all(test") {
                break;
            }
            // `std::process::Command` and `use std::process::{Command, …}`, not `Stdio` or `ExitCode`.
            let direct = code.split("std::process::").skip(1).any(|rest| rest.split(|c: char| !c.is_alphanumeric() && c != '_').any(|w| w == "Command"));
            if !code.starts_with("//") && (direct || code.contains("process::Command::new")) {
                let rel = f.strip_prefix(root).unwrap_or(&f).display().to_string();
                eprintln!("layers: {rel}:{}: runs a program with std::process::Command; use craft_anything_platform::process (golden rule 10)", i + 1);
                ok = false;
            }
        }
    }
    ok
}

/// R1.6 headless first: `crates/ui-egui` shows things and calls tools; it doesn't write files or
/// start programs itself, so the CLI and MCP can do everything the app does. Its non-test code
/// (`src/`, up to a file's first `#[cfg(test)]`) may not name these. Reading files and eframe's
/// own storage are fine; writes made inside other crates (`Workspace::save`…) aren't seen here.
fn ui_has_no_side_effects(root: &Path) -> bool {
    const FORBIDDEN: &[&str] =
        &["fs::write", "File::create", "OpenOptions", "fs::create_dir", "fs::remove_", "fs::rename", "write_atomic", "std::process", "Launch::", "Process::"];
    /// Today's offenders: `(file in crates/ui-egui/src, pattern, why it's still there)`. The list
    /// only shrinks: move the work behind a tool, then delete the entry (a stale entry fails).
    const BASELINE: &[(&str, &str, &str)] = &[];
    let Ok(entries) = std::fs::read_dir(root.join("crates/ui-egui/src")) else {
        eprintln!("layers: cannot read crates/ui-egui/src");
        return false;
    };
    let mut ok = true;
    let mut seen: Vec<(String, &str)> = Vec::new();
    for e in entries.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        if !name.ends_with(".rs") {
            continue;
        }
        let text = std::fs::read_to_string(e.path()).unwrap_or_default();
        for (i, line) in text.lines().enumerate() {
            let code = line.trim_start();
            if code.starts_with("#[cfg(test)]") || code.starts_with("#[cfg(all(test") {
                break;
            }
            if code.starts_with("//") {
                continue;
            }
            for &pat in FORBIDDEN.iter().filter(|p| code.contains(**p)) {
                if BASELINE.iter().any(|(f, p, _)| *f == name && *p == pat) {
                    seen.push((name.clone(), pat));
                } else {
                    eprintln!("layers: crates/ui-egui/src/{name}:{}: `{pat}` in the UI; do it through a tool so the CLI and MCP get it too (R1.6)", i + 1);
                    ok = false;
                }
            }
        }
    }
    for (f, p, _) in BASELINE {
        if !seen.iter().any(|(sf, sp)| sf == f && sp == p) {
            eprintln!("layers: crates/ui-egui/src/{f} no longer uses `{p}`; remove its entry from BASELINE in ui_has_no_side_effects");
            ok = false;
        }
    }
    ok
}

fn tools(root: &Path, check: bool) -> bool {
    let registry = craft_anything_engine::Registry::with_all_tools();
    let report = craft_anything_engine::tool_list::report(&registry);
    let n = registry.all().len();
    let path = root.join("docs").join("tools.md");
    if check {
        let current = std::fs::read_to_string(&path).unwrap_or_default();
        if current != report {
            eprintln!("tools: docs/tools.md is stale; run `cargo xtask tools`");
            return false;
        }
        eprintln!("tools: {n} (up to date)");
        return true;
    }
    let _ = std::fs::create_dir_all(root.join("docs"));
    match std::fs::write(&path, report) {
        Ok(()) => {
            eprintln!("tools: {n} → docs/tools.md");
            true
        }
        Err(e) => {
            eprintln!("tools: {e}");
            false
        }
    }
}

/// `cargo xtask schemas [--check]`: regenerates the JSON Schemas of the files we persist into
/// `docs/schemas/`, or with `--check` fails when they're stale (see docs/file-formats.md).
fn schemas(root: &Path, check: bool) -> bool {
    let dir = root.join("docs").join("schemas");
    let files = [
        ("craft.schema.json", craft_anything_engine::workspace::manifest_schema()),
        ("mechanics.schema.json", craft_anything_engine::mechanics::mechanics_schema()),
        ("self-test.schema.json", craft_anything_engine::self_test::self_test_schema()),
    ];
    let mut ok = true;
    for (name, schema) in files {
        let path = dir.join(name);
        let current = std::fs::read_to_string(&path).unwrap_or_default().replace("\r\n", "\n");
        if current == schema {
            eprintln!("schemas: docs/schemas/{name} (up to date)");
            continue;
        }
        if check {
            eprintln!("schemas: docs/schemas/{name} is stale; run `cargo xtask schemas`");
            ok = false;
            continue;
        }
        match std::fs::create_dir_all(&dir).and_then(|()| std::fs::write(&path, &schema)) {
            Ok(()) => eprintln!("schemas: wrote docs/schemas/{name}"),
            Err(e) => {
                eprintln!("schemas: {name}: {e}");
                ok = false;
            }
        }
    }
    ok
}

/// Checks every dependency's licence against `deny.toml` (policy: docs/licences.md).
fn licenses() -> bool {
    let installed = Command::new("cargo").args(["deny", "--version"]).output().map(|o| o.status.success()).unwrap_or(false);
    if !installed {
        eprintln!("licenses: cargo-deny is not installed; install it with `cargo install cargo-deny --locked`");
        return false;
    }
    run("cargo", &["deny", "check", "licenses"])
}

fn wasm() -> bool {
    let mut args = vec!["check", "--target", "wasm32-unknown-unknown"];
    for c in WASM_CRATES {
        args.push("-p");
        args.push(c);
    }
    run("cargo", &args)
}

/// Tests never touch the real machine (docs/pitfalls.md): `Session::default()` points at this
/// computer's config folder and engine store, so code uses `testing::session()` (a temp folder)
/// or `Session::new(settings)` with settings it chose. Comments are fine.
fn no_real_machine_sessions(root: &Path) -> bool {
    let mut ok = true;
    let mut stack = vec![root.join("crates"), root.join("apps")];
    while let Some(dir) = stack.pop() {
        for e in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() {
                if p.file_name().is_some_and(|n| n != "target") {
                    stack.push(p);
                }
                continue;
            }
            if p.extension().is_none_or(|x| x != "rs") {
                continue;
            }
            let text = std::fs::read_to_string(&p).unwrap_or_default();
            for (i, line) in text.lines().enumerate() {
                let code = line.trim_start();
                if code.starts_with("//") {
                    continue;
                }
                if code.contains("Session::default()") {
                    eprintln!("layers: {}:{}: Session::default() uses this computer's folders; use testing::session() in tests", p.display(), i + 1);
                    ok = false;
                }
            }
        }
    }
    ok
}

/// `pending`: every unticked `- [ ]` line in docs/ROADMAP.md, under its `### R…` item (with any
/// indented continuation lines), and the totals. `--count` prints only the totals.
fn pending(root: &Path, count_only: bool) -> bool {
    let Ok(text) = std::fs::read_to_string(root.join("docs/ROADMAP.md")) else {
        eprintln!("pending: can't read docs/ROADMAP.md");
        return false;
    };
    let mut groups: Vec<(String, Vec<String>)> = Vec::new();
    let mut heading = String::from("(before any item)");
    let mut open: Option<String> = None;
    let flush = |open: &mut Option<String>, groups: &mut Vec<(String, Vec<String>)>, heading: &str| {
        if let Some(line) = open.take() {
            match groups.last_mut() {
                Some((h, items)) if h == heading => items.push(line),
                _ => groups.push((heading.to_string(), vec![line])),
            }
        }
    };
    for line in text.lines() {
        if let Some(h) = line.strip_prefix("### ").or_else(|| line.strip_prefix("## ")) {
            flush(&mut open, &mut groups, &heading);
            heading = h.trim().to_string();
        } else if let Some(item) = line.strip_prefix("- [ ] ") {
            flush(&mut open, &mut groups, &heading);
            open = Some(item.trim().to_string());
        } else if open.is_some() && line.starts_with("      ") {
            if let Some(o) = open.as_mut() {
                o.push(' ');
                o.push_str(line.trim());
            }
        } else {
            flush(&mut open, &mut groups, &heading);
        }
    }
    flush(&mut open, &mut groups, &heading);
    let total: usize = groups.iter().map(|(_, i)| i.len()).sum();
    if !count_only {
        for (h, items) in &groups {
            println!("{h}");
            for i in items {
                println!("  - {i}");
            }
        }
        println!();
    }
    println!("{total} open item(s) under {} roadmap entr{}", groups.len(), if groups.len() == 1 { "y" } else { "ies" });
    true
}
