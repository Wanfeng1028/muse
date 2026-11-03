//! Building a project with its own tools (cargo, npm, or the game engine's), for [`BuildCheck`].
//! A plain static site has no build, and passes as it is.

use super::*;

/// For non-website builds: run the project's build (its engine's own, for Unity, Unreal and
/// Godot) and report whether it succeeded, with a note (the first error lines when it didn't).
/// `place` says where `app` is, for messages (`Workspace::app_place`).
pub(super) fn build_check(app: &Path, place: &str, stack: &str, editor: Option<&Path>, stop: &CancelToken) -> (bool, String) {
    let run = |prog: &Path, args: &[String], minutes: u64| {
        let s = stop.clone();
        craft_anything_platform::Process::new(prog)
            .args(args)
            .cwd(app)
            .timeout(Duration::from_secs(minutes * 60))
            // Engines go quiet for long stretches (shader compiles, cooking, a cold cargo build).
            .idle_timeout(Duration::from_secs(60 * 60))
            .stdout_cap(8 << 20)
            .cancel_when(move || s.is_cancelled())
            .run()
            .map(|o| (o.success, format!("{}{}", o.stdout_text(), o.stderr_text())))
            .map_err(|e| format!("Couldn't run the build: {}", e.message))
    };
    let app_s = app.display().to_string();
    let built = || packaged_program(&app.join("Build")).is_some();
    let result: Result<(bool, String), String> = match (engine_for(stack, app), editor) {
        (Some(game::Builder::Unity), Some(ed)) => {
            if !app.join("Assets").is_dir() {
                return (false, format!("No Unity project found in {place} yet."));
            }
            let args = ["-batchmode", "-quit", "-nographics", "-projectPath", &app_s, "-executeMethod", "CraftBuild.Build", "-logFile", "-"].map(String::from);
            run(ed, &args, 4 * 60).map(|(ok, out)| {
                if out.contains("No valid Unity Editor license") {
                    (false, "Unity needs its free licence first: open Unity Hub, sign in and accept the Personal licence, then try again.".into())
                } else {
                    (ok && built(), out)
                }
            })
        }
        (Some(game::Builder::Unreal), Some(ed)) => {
            let Some(uproject) = uproject(app) else {
                return (false, format!("No Unreal project (.uproject) found in {place} yet."));
            };
            // The editor is <engine>/Engine/Binaries/<platform>/UnrealEditor; its packager is beside it.
            let Some(root) = ed.ancestors().nth(4) else { return (false, "Couldn't find Unreal's build tools.".into()) };
            let uat = root.join("Engine/Build/BatchFiles").join(if cfg!(windows) { "RunUAT.bat" } else { "RunUAT.sh" });
            let platform = if cfg!(windows) {
                "Win64"
            } else if cfg!(target_os = "macos") {
                "Mac"
            } else {
                "Linux"
            };
            let args = vec![
                "BuildCookRun".to_string(),
                format!("-project={}", uproject.display()),
                format!("-platform={platform}"),
                "-clientconfig=Development".into(),
                "-build".into(),
                "-cook".into(),
                "-stage".into(),
                "-pak".into(),
                "-archive".into(),
                format!("-archivedirectory={}", app.join("Build").display()),
                "-unattended".into(),
                "-utf8output".into(),
                "-nop4".into(),
            ];
            // A first Unreal build compiles and cooks for a long while. Run RunUAT.bat directly:
            // std quotes .bat launches itself, whereas `cmd /C "<path with spaces>" "<arg>"` strips the quotes.
            run(&uat, &args, 8 * 60).map(|(ok, out)| (ok && built(), out))
        }
        (Some(game::Builder::Godot), Some(ed)) => {
            if !app.join("project.godot").is_file() {
                return (false, format!("No Godot project (project.godot) found in {place} yet."));
            }
            let import = ["--headless", "--path", &app_s, "--import"].map(String::from);
            let play = ["--headless", "--path", &app_s, "--quit-after", "120"].map(String::from);
            // Godot exits cleanly even when scripts fail, so its error lines decide.
            run(ed, &import, 60).and_then(|(_, a)| run(ed, &play, 10).map(|(ok, b)| (ok, a + &b))).map(|(ok, out)| {
                let bad = out.lines().any(|l| l.contains("SCRIPT ERROR") || l.contains("Parse Error") || l.trim_start().starts_with("ERROR:"));
                (ok && !bad, out)
            })
        }
        _ if app.join("Cargo.toml").is_file() => run(Path::new("cargo"), &["build".into(), "--quiet".into()], 2 * 60),
        _ if app.join("package.json").is_file() => run(Path::new(if cfg!(windows) { "npm.cmd" } else { "npm" }), &["run".into(), "build".into()], 2 * 60),
        (None, _) if static_site(app) => return (true, "Nothing to build: a static site.".into()),
        _ => return (false, format!("No project to build found in {place} yet.")),
    };
    match result {
        Ok((true, _)) => (true, "Build succeeded.".into()),
        Ok((false, out)) => (false, format!("Build failed: {}", error_lines(&out))),
        Err(e) => (false, e),
    }
}

/// The engine whose own build runs: the stack's, unless app/ holds another kind of project
/// rather than the engine's. What was built decides, since the person may have asked for
/// something other than the engine picked at the start.
fn engine_for(stack: &str, app: &Path) -> Option<game::Builder> {
    if static_site(app) {
        return None;
    }
    let own_project = app.join("Cargo.toml").is_file() || app.join("package.json").is_file();
    game::Builder::from_stack(stack).filter(|b| !own_project || engine_project(*b, app))
}

/// Whether `app` is a static site with nothing to build: a page with something in it, as the
/// preview finds it, and no game engine's project beside it. A site's `assets/` folder is no sign
/// of Unity (file names ignore case on Windows and macOS), so Unity needs its settings folder too.
fn static_site(app: &Path) -> bool {
    let engine = app.join("project.godot").is_file() || uproject(app).is_some() || (app.join("Assets").is_dir() && app.join("ProjectSettings").is_dir());
    let page = |site: PathBuf| std::fs::read(site.join("index.html")).is_ok_and(|html| html.iter().any(|b| !b.is_ascii_whitespace()));
    !engine && site_dir(app).is_some_and(page)
}

/// The Unreal project file in `app`, if there is one.
fn uproject(app: &Path) -> Option<PathBuf> {
    std::fs::read_dir(app).into_iter().flatten().flatten().map(|e| e.path()).find(|p| p.extension().is_some_and(|x| x == "uproject"))
}

/// Whether `app` holds a project of the engine `b` builds with (Rust's is an ordinary cargo one).
fn engine_project(b: game::Builder, app: &Path) -> bool {
    match b {
        game::Builder::Unity => app.join("Assets").is_dir(),
        game::Builder::Unreal => uproject(app).is_some(),
        game::Builder::Godot => app.join("project.godot").is_file(),
        game::Builder::Rust => false,
    }
}

/// The lines that explain a failed build: error lines first, else the last lines.
pub(super) fn error_lines(out: &str) -> String {
    let lines: Vec<&str> = out.lines().filter(|l| !l.trim().is_empty()).collect();
    let errors: Vec<&str> = lines.iter().copied().filter(|l| l.to_ascii_lowercase().contains("error") || l.contains("licen")).take(12).collect();
    if errors.is_empty() { lines[lines.len().saturating_sub(12)..].join("\n") } else { errors.join("\n") }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_build_follows_what_was_built_not_the_stack_picked_first() {
        let d = tempfile::tempdir().unwrap();
        let app = d.path();
        // nothing built yet: the engine's build says what's missing
        assert_eq!(engine_for("Unity", app), Some(game::Builder::Unity));
        // the person asked for something else and got it: npm or cargo builds it
        std::fs::write(app.join("package.json"), "{}").unwrap();
        assert_eq!(engine_for("Unity", app), None);
        assert_eq!(engine_for("Godot", app), None);
        assert_eq!(engine_for("Unreal Engine", app), None);
        // an engine's own project is built by the engine, whatever else is beside it
        std::fs::create_dir(app.join("Assets")).unwrap();
        assert_eq!(engine_for("Unity", app), Some(game::Builder::Unity));
        std::fs::write(app.join("project.godot"), "").unwrap();
        assert_eq!(engine_for("Godot", app), Some(game::Builder::Godot));
        std::fs::write(app.join("Game.uproject"), "{}").unwrap();
        assert_eq!(engine_for("Unreal Engine", app), Some(game::Builder::Unreal));
        // stacks without an engine of their own
        assert_eq!(engine_for("Electron", app), None);
        std::fs::write(app.join("Cargo.toml"), "").unwrap();
        assert_eq!(engine_for("Rust + macroquad", app), None);
    }

    #[test]
    fn a_static_site_has_nothing_to_build() {
        let d = tempfile::tempdir().unwrap();
        let app = d.path();
        let stop = CancelToken::default();
        let passed = (true, "Nothing to build: a static site.".to_string());
        let check = |stack, editor| build_check(app, "app/", stack, editor, &stop);
        assert!(!check("Plain HTML and CSS", None).0, "nothing there yet");

        // #496: the page itself, with no manifest.
        std::fs::write(app.join("index.html"), "<!doctype html><h1>Hello</h1>").unwrap();
        assert_eq!(check("Plain HTML and CSS", None), passed);
        // What was built decides: a page made under a game engine's stack isn't a missing project.
        let unity = Path::new("C:/Engines/Unity/Editor/Unity.exe");
        assert_eq!(check("Unity", Some(unity)), passed);

        // A site's own assets folder doesn't make it a Unity project.
        std::fs::create_dir(app.join("Assets")).unwrap();
        assert_eq!(check("Plain HTML and CSS", None), passed);
        assert_eq!(check("Unity", Some(unity)), passed);

        // A real engine project doesn't pass for the page beside it, with or without the editor,
        // and whichever engine the stack named.
        std::fs::create_dir(app.join("ProjectSettings")).unwrap();
        assert!(!check("Unity", None).0);
        assert!(!check("Plain HTML and CSS", None).0);
        std::fs::remove_dir(app.join("ProjectSettings")).unwrap();
        for project in ["project.godot", "Game.uproject"] {
            std::fs::write(app.join(project), "").unwrap();
            assert!(!check("Unity", None).0, "{project}");
            std::fs::remove_file(app.join(project)).unwrap();
        }

        // A blank page isn't a site, and doesn't pass for one under an engine's stack either.
        std::fs::write(app.join("index.html"), " \n").unwrap();
        assert!(!check("Plain HTML and CSS", None).0);
        std::fs::remove_dir(app.join("Assets")).unwrap();
        assert_eq!(check("Unity", Some(unity)), (false, "No Unity project found in app/ yet.".into()));

        // Already-built pages count too, as they do for the preview.
        let built = tempfile::tempdir().unwrap();
        std::fs::create_dir(built.path().join("dist")).unwrap();
        std::fs::write(built.path().join("dist").join("index.html"), "<h1>Hello</h1>").unwrap();
        assert_eq!(build_check(built.path(), "app/", "Builder's choice", None, &stop), passed);
    }
}
