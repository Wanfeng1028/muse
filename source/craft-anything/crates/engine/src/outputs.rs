//! Finding what a project's build produced: the built site, the program, and what "Play" starts.

use std::path::{Path, PathBuf};

/// Where a built site lives in `app`: a build folder with index.html, else a plain static site.
/// An Electron app's bundled page is its window, not a site.
pub fn site_dir(app: &Path) -> Option<PathBuf> {
    if uses_electron(app) {
        return None;
    }
    for d in ["dist", "build", "out"] {
        let p = app.join(d);
        if p.join("index.html").is_file() {
            return Some(p);
        }
    }
    (app.join("index.html").is_file() && !app.join("package.json").exists()).then(|| app.to_path_buf())
}

/// The program a Rust build in `app` made, so a finished game or app can be started. A workspace
/// often builds several (the app, its CLI, tools), so the project's own Cargo.toml files decide:
/// its `default-run`, then a program whose package uses a window or game library, then the root
/// package's; the newest build of that program wins (release or debug). Only when the manifests
/// name no programs is it the newest executable. Build scripts and dependencies live in
/// subfolders and are skipped, and so are stray copies (`app.running-123.exe`) of a declared one.
/// shortcut: assumes the default target dir; read `cargo metadata` if a project ever moves it.
pub fn built_program(app: &Path) -> Option<PathBuf> {
    if !app.join("Cargo.toml").is_file() {
        return None;
    }
    let built: Vec<PathBuf> = ["release", "debug"]
        .iter()
        .filter_map(|d| std::fs::read_dir(app.join("target").join(d)).ok())
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter(|p| p.is_file() && is_program(p))
        .collect();
    let newest = |ps: &mut dyn Iterator<Item = &PathBuf>| ps.max_by_key(|p| p.metadata().and_then(|m| m.modified()).ok()).cloned();
    let stem = |p: &Path| p.file_stem().and_then(|s| s.to_str()).map(str::to_string).unwrap_or_default();
    let wanted = cargo_programs(app);
    if wanted.is_empty() {
        return newest(&mut built.iter());
    }
    wanted.iter().find_map(|name| newest(&mut built.iter().filter(|p| stem(p) == *name)))
}

/// Libraries that put a window on screen: a package using one makes the program to start.
const WINDOW_CRATES: &[&str] = &[
    "eframe",
    "egui",
    "winit",
    "macroquad",
    "bevy",
    "iced",
    "slint",
    "ggez",
    "fltk",
    "gtk",
    "gtk4",
    "tauri",
    "sdl2",
    "minifb",
    "pixels",
    "glium",
    "raylib",
    "notan",
    "fyrox",
    "nannou",
    "druid",
    "xilem",
    "dioxus",
    "floem",
    "piston_window",
    "tetra",
    "comfy",
    "miniquad",
    "softbuffer",
];

/// The programs `app`'s Cargo manifests declare, best first (see [`built_program`]).
fn cargo_programs(app: &Path) -> Vec<String> {
    let read = |dir: &Path| -> Option<toml::Table> { std::fs::read_to_string(dir.join("Cargo.toml")).ok()?.parse().ok() };
    let Some(root) = read(app) else { return Vec::new() };
    // The packages: the root's (if it has one) first, then the workspace members.
    let mut dirs = vec![app.to_path_buf()];
    let members = root.get("workspace").and_then(|w| w.get("members")).and_then(|m| m.as_array()).cloned().unwrap_or_default();
    for m in members.iter().filter_map(|m| m.as_str()) {
        match m.strip_suffix("/*") {
            Some(parent) => {
                let mut found: Vec<PathBuf> =
                    std::fs::read_dir(app.join(parent)).into_iter().flatten().flatten().map(|e| e.path()).filter(|p| p.join("Cargo.toml").is_file()).collect();
                found.sort();
                dirs.extend(found);
            }
            None if m != "." => dirs.push(app.join(m)),
            None => {}
        }
    }
    let mut default_run = Vec::new();
    let mut windowed = Vec::new();
    let mut root_bins = Vec::new();
    let mut other = Vec::new();
    for (i, dir) in dirs.iter().enumerate() {
        let Some(t) = read(dir) else { continue };
        let Some(pkg) = t.get("package").and_then(|p| p.as_table()) else { continue };
        let mut bins: Vec<String> = t
            .get("bin")
            .and_then(|b| b.as_array())
            .map(|bs| bs.iter().filter_map(|b| b.get("name")?.as_str().map(str::to_string)).collect())
            .unwrap_or_default();
        if bins.is_empty()
            && dir.join("src").join("main.rs").is_file()
            && let Some(name) = pkg.get("name").and_then(|n| n.as_str())
        {
            bins.push(name.to_string());
        }
        if let Some(d) = pkg.get("default-run").and_then(|d| d.as_str()) {
            default_run.push(d.to_string());
        }
        // [dependencies] and per-platform [target.'cfg(..)'.dependencies].
        let per_target = t.get("target").and_then(|x| x.as_table()).into_iter().flat_map(|ts| ts.values().filter_map(|v| v.get("dependencies")));
        let uses_window =
            t.get("dependencies").into_iter().chain(per_target).filter_map(|d| d.as_table()).any(|d| d.keys().any(|k| WINDOW_CRATES.contains(&k.as_str())));
        if uses_window {
            windowed.extend(bins.iter().cloned());
        }
        if i == 0 { root_bins.extend(bins) } else { other.extend(bins) }
    }
    let mut out: Vec<String> = Vec::new();
    for name in default_run.into_iter().chain(windowed).chain(root_bins).chain(other) {
        if !out.contains(&name) {
            out.push(name);
        }
    }
    out
}

/// What "Play" starts for a finished game or app: (program, arguments), run from app/. A Godot
/// project opens in the Godot it was built with, an Electron app in the Electron it installed.
pub fn launch(app: &Path, godot: Option<&Path>) -> Option<(PathBuf, Vec<String>)> {
    if app.join("project.godot").is_file() {
        return godot.map(|g| (g.to_path_buf(), vec!["--path".to_string(), app.display().to_string()]));
    }
    if uses_electron(app) {
        return electron_program(app).map(|e| (e, vec![app.display().to_string()]));
    }
    built_program(app).or_else(|| packaged_program(&app.join("Build"))).map(|p| (p, Vec::new()))
}

/// The packages `app`'s package.json depends on (dev dependencies too); none without a readable one.
pub fn npm_dependencies(app: &Path) -> Vec<String> {
    let pkg: Option<serde_json::Value> = std::fs::read(app.join("package.json")).ok().and_then(|b| serde_json::from_slice(&b).ok());
    ["dependencies", "devDependencies"].iter().filter_map(|k| pkg.as_ref()?.get(k)?.as_object()).flat_map(|d| d.keys().cloned()).collect()
}

fn uses_electron(app: &Path) -> bool {
    npm_dependencies(app).iter().any(|d| d == "electron")
}

/// The Electron that `npm install` put in `app`'s node_modules.
fn electron_program(app: &Path) -> Option<PathBuf> {
    let dist = app.join("node_modules").join("electron").join("dist");
    let program = if cfg!(windows) {
        dist.join("electron.exe")
    } else if cfg!(target_os = "macos") {
        dist.join("Electron.app").join("Contents").join("MacOS").join("Electron")
    } else {
        dist.join("electron")
    };
    program.is_file().then_some(program)
}

/// The game a Unity or Unreal build packaged into `dir` (newest; crash reporters skipped).
pub fn packaged_program(dir: &Path) -> Option<PathBuf> {
    let mut best: Option<(std::time::SystemTime, PathBuf)> = None;
    let mut stack = vec![(dir.to_path_buf(), 0)];
    while let Some((d, depth)) = stack.pop() {
        for e in std::fs::read_dir(&d).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() {
                if depth < 4 {
                    stack.push((p, depth + 1));
                }
                continue;
            }
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or_default().to_ascii_lowercase();
            let helper = ["crashreport", "crashhandler", "crashpad", "-cmd", "unrealpak", "shadercompile"].iter().any(|s| name.contains(s));
            let at = e.metadata().and_then(|m| m.modified()).unwrap_or(std::time::UNIX_EPOCH);
            if is_program(&p) && !helper && best.as_ref().is_none_or(|(b, _)| at > *b) {
                best = Some((at, p));
            }
        }
    }
    best.map(|(_, p)| p)
}

#[cfg(all(test, unix))]
mod tests {
    use super::packaged_program;
    use std::os::unix::fs::PermissionsExt;
    use std::time::{Duration, UNIX_EPOCH};

    #[test]
    fn packaged_program_finds_executable_with_crash_in_name() {
        let build = tempfile::tempdir().unwrap();
        let reporter = build.path().join("CrashReportClient");
        let game = build.path().join("CrashSample");
        std::fs::write(&reporter, b"reporter").unwrap();
        std::fs::write(&game, b"game").unwrap();
        for path in [&reporter, &game] {
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
        }
        std::fs::File::open(&reporter).unwrap().set_times(std::fs::FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(1))).unwrap();
        std::fs::File::open(&game).unwrap().set_times(std::fs::FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(2))).unwrap();

        assert_eq!(packaged_program(build.path()), Some(game));
    }
}

/// Whether `p` is a program this computer can start.
#[cfg(windows)]
pub fn is_program(p: &Path) -> bool {
    p.extension().is_some_and(|e| e.eq_ignore_ascii_case("exe"))
}

#[cfg(unix)]
pub fn is_program(p: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    p.extension().is_none() && p.metadata().is_ok_and(|m| m.permissions().mode() & 0o111 != 0)
}
