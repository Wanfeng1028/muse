//! Find programs on `PATH` (with `PATHEXT` on Windows). No subprocess is run.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

/// The first match for `name` on `PATH`, or `name` itself when it is already a path to a file.
pub fn which(name: &str) -> Option<PathBuf> {
    which_all(name).into_iter().next()
}

/// Every match for `name` on [`search_path`], in order (useful to spot duplicate installs).
pub fn which_all(name: &str) -> Vec<PathBuf> {
    which_in(name, search_path())
}

/// Folders, under the home folder and then system-wide, where coding agents, npm, Homebrew and
/// other installers put command-line programs. OpenCode's installer uses `~/.opencode/bin`, or
/// `~/bin` when there is one (#112).
#[cfg(unix)]
const USUAL_HOME_DIRS: &[&str] = &[".local/bin", ".claude/local", ".npm-global/bin", ".bun/bin", ".volta/bin", ".cargo/bin", ".opencode/bin", "bin"];
#[cfg(unix)]
const USUAL_DIRS: &[&str] = &["/opt/homebrew/bin", "/usr/local/bin"];
// Claude Code's installer, npm (without a custom prefix), WinGet's portable packages (Claude
// Code's WinGet install), bun and cargo; PATH may not have them yet in an app started before
// the install.
#[cfg(windows)]
const USUAL_HOME_DIRS: &[&str] = &[r".local\bin", r"AppData\Roaming\npm", r"AppData\Local\Microsoft\WinGet\Links", r".bun\bin", r".cargo\bin"];
#[cfg(not(any(unix, windows)))]
const USUAL_HOME_DIRS: &[&str] = &[];
// WinGet's portable packages installed for every user (`--scope machine`).
#[cfg(windows)]
const USUAL_DIRS: &[&str] = &[r"C:\Program Files\WinGet\Links"];
#[cfg(not(any(unix, windows)))]
const USUAL_DIRS: &[&str] = &[];
const HOME_VAR: &str = if cfg!(windows) { "USERPROFILE" } else { "HOME" };

/// `PATH` plus the usual folders for command-line programs, after it so the person's own order
/// wins. An app opened from the Dock or a desktop launcher gets the system's short `PATH`, not the
/// shell's, and would miss a coding agent installed in `~/.local/bin`; on Windows an installer
/// may not have added its folder to `PATH` at all.
pub fn search_path() -> Option<OsString> {
    with_usual_dirs(std::env::var_os("PATH"), std::env::var_os(HOME_VAR).map(PathBuf::from))
}

/// How to start `program`, and the arguments that go before the caller's. On Windows only `.exe`
/// files start by bare name, and npm installs Gemini CLI, Codex and often Claude Code as `.cmd`
/// shims: an npm shim's script is run by its interpreter directly (through `cmd.exe` a prompt with
/// line breaks, or longer than 8191 characters, wouldn't arrive whole), and any other batch file
/// by its full path.
#[cfg(windows)]
pub(crate) fn launch_target(program: &std::ffi::OsStr) -> (OsString, Vec<OsString>) {
    let Some(found) = which_in(&program.to_string_lossy(), search_path()).into_iter().next() else { return (program.to_owned(), Vec::new()) };
    if !found.extension().is_some_and(|e| e.eq_ignore_ascii_case("cmd") || e.eq_ignore_ascii_case("bat")) {
        return (program.to_owned(), Vec::new());
    }
    let dir = found.parent().map(Path::to_path_buf).unwrap_or_default();
    let shim = std::fs::metadata(&found)
        .ok()
        .filter(|m| m.len() <= 64 * 1024)
        .and_then(|_| std::fs::read_to_string(&found).ok())
        .and_then(|text| parse_npm_shim(&text));
    match shim {
        Some((None, target)) if is_executable(&dir.join(&target)) => (dir.join(target).into_os_string(), Vec::new()),
        Some((Some(interpreter), target)) if dir.join(&target).is_file() => {
            let local = dir.join(format!("{interpreter}.exe"));
            match if local.is_file() { Some(local) } else { which_in(&interpreter, search_path()).into_iter().next() } {
                Some(i) => (i.into_os_string(), vec![dir.join(target).into_os_string()]),
                None => (found.into_os_string(), Vec::new()),
            }
        }
        _ => (found.into_os_string(), Vec::new()),
    }
}

#[cfg(not(windows))]
pub(crate) fn launch_target(program: &std::ffi::OsStr) -> (OsString, Vec<OsString>) {
    (program.to_owned(), Vec::new())
}

/// What an npm (or pnpm) `.cmd` shim runs: its interpreter (`node`; none when the target is an
/// `.exe`) and the target, relative to the shim's folder.
#[cfg(any(windows, test))]
fn parse_npm_shim(text: &str) -> Option<(Option<String>, String)> {
    let run = text.lines().find(|l| l.contains("%*"))?;
    let quoted: Vec<&str> = run.split('"').skip(1).step_by(2).collect();
    let target = quoted.iter().rev().find_map(|q| q.strip_prefix(r"%dp0%\").or_else(|| q.strip_prefix(r"%~dp0\")))?;
    if target.to_ascii_lowercase().ends_with(".exe") {
        return Some((None, target.to_string()));
    }
    let interpreter = if quoted.contains(&"%_prog%") {
        // npm: `SET "_prog=%dp0%\node.exe"` when Node sits beside the shim, else `SET "_prog=node"`.
        text.lines().filter_map(|l| l.trim().strip_prefix("SET \"_prog=")?.strip_suffix('"')).find(|p| !p.contains('%'))?
    } else {
        // pnpm: `"%~dp0\node.exe"  "%~dp0\..\pnpm\bin\pnpm.cjs" %*`.
        quoted.iter().any(|q| q.to_ascii_lowercase().ends_with(r"\node.exe")).then_some("node")?
    };
    Some((Some(interpreter.to_string()), target.to_string()))
}

/// The `bin` folders of the Node versions nvm installed, newest first: npm puts the agents it
/// installs there, and only a shell that loaded nvm has them on `PATH` (#112).
#[cfg(unix)]
fn nvm_bins(home: &Path) -> Vec<PathBuf> {
    let Ok(versions) = std::fs::read_dir(home.join(".nvm/versions/node")) else { return Vec::new() };
    let mut found: Vec<(Vec<u64>, PathBuf)> = versions
        .flatten()
        .filter_map(|e| {
            let name = e.file_name().into_string().ok()?;
            let version = name.trim_start_matches('v').split('.').map(|n| n.parse().unwrap_or(0)).collect();
            Some((version, e.path().join("bin")))
        })
        .collect();
    found.sort_by(|a, b| b.0.cmp(&a.0));
    found.into_iter().map(|(_, bin)| bin).take(8).collect()
}

#[cfg(not(unix))]
fn nvm_bins(_home: &Path) -> Vec<PathBuf> {
    Vec::new()
}

/// Where npm puts what it installs globally when the person moved its prefix
/// (`npm config set prefix …` writes `prefix=` to `~/.npmrc`, and `NPM_CONFIG_PREFIX` sets it
/// too): the prefix itself on Windows, its `bin` folder elsewhere (#132).
fn npm_global_bin(home: &Path) -> Option<PathBuf> {
    let set = ["NPM_CONFIG_PREFIX", "npm_config_prefix"].iter().find_map(std::env::var_os).filter(|v| !v.is_empty());
    let prefix = set.map(PathBuf::from).or_else(|| npmrc_prefix(home))?;
    Some(if cfg!(windows) { prefix } else { prefix.join("bin") })
}

/// The `prefix` set in `~/.npmrc`, if any (the last one wins, as in npm).
fn npmrc_prefix(home: &Path) -> Option<PathBuf> {
    let file = home.join(".npmrc");
    let text = std::fs::metadata(&file).ok().filter(|m| m.len() <= 64 * 1024).and_then(|_| std::fs::read_to_string(&file).ok())?;
    let value = text.lines().rev().filter_map(|l| l.split_once('=')).find(|(k, _)| k.trim() == "prefix")?.1.trim().trim_matches('"');
    if value.is_empty() {
        return None;
    }
    Some(match value.strip_prefix("~/").or_else(|| value.strip_prefix("~\\")) {
        Some(rest) => home.join(rest),
        None => PathBuf::from(value),
    })
}

fn with_usual_dirs(path: Option<OsString>, home: Option<PathBuf>) -> Option<OsString> {
    let mut dirs: Vec<PathBuf> = path.as_ref().map(|p| std::env::split_paths(p).collect()).unwrap_or_default();
    let before = dirs.len();
    let in_home = home.iter().flat_map(|h| USUAL_HOME_DIRS.iter().map(move |d| h.join(d)).chain(nvm_bins(h)).chain(npm_global_bin(h)));
    for d in in_home.chain(USUAL_DIRS.iter().map(PathBuf::from)) {
        if !dirs.contains(&d) {
            dirs.push(d);
        }
    }
    if dirs.len() == before {
        return path;
    }
    std::env::join_paths(&dirs).ok().or(path)
}

/// Like [`which_all`] with an explicit search path.
pub fn which_in(name: &str, path: Option<OsString>) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if name.is_empty() {
        return out;
    }
    let as_path = Path::new(name);
    if as_path.components().count() > 1 || as_path.is_absolute() {
        for c in candidates(as_path) {
            if is_executable(&c) {
                out.push(c);
                break;
            }
        }
        return out;
    }
    let Some(path) = path else { return out };
    for dir in std::env::split_paths(&path) {
        if dir.as_os_str().is_empty() {
            continue;
        }
        for c in candidates(&dir.join(name)) {
            if is_executable(&c) && !out.contains(&c) {
                out.push(c);
                break;
            }
        }
    }
    out
}

/// File name of the command-line binary (`craft-anything-cli`, plus `.exe` on Windows).
pub fn cli_file_name() -> String {
    format!("craft-anything-cli{}", std::env::consts::EXE_SUFFIX)
}

/// Absolute path of the installed `craft-anything-cli`: this executable when it is the CLI, else
/// a sibling of this executable (the desktop app ships next to it), else the first one on `PATH`.
pub fn self_cli_path() -> Option<PathBuf> {
    let name = cli_file_name();
    let exe = std::env::current_exe().ok().map(|p| std::fs::canonicalize(&p).unwrap_or(p));
    if let Some(exe) = &exe {
        if exe.file_name().is_some_and(|n| n == name.as_str()) {
            return Some(exe.clone());
        }
        if let Some(dir) = exe.parent() {
            let sib = dir.join(&name);
            if is_executable(&sib) {
                return Some(sib);
            }
            // test binaries live in target/<profile>/deps; the CLI is one level up
            if let Some(up) = dir.parent().map(|d| d.join(&name))
                && is_executable(&up)
            {
                return Some(up);
            }
        }
    }
    which("craft-anything-cli")
}

#[cfg(windows)]
fn candidates(base: &Path) -> Vec<PathBuf> {
    let mut v = Vec::new();
    // A file with no extension can't be started by name (CreateProcess only adds `.exe`), and npm
    // puts an extensionless POSIX shell script beside every `.cmd` shim it installs. Try the kinds
    // Windows runs first, then the bare name, so `which` returns what the system would start (#41).
    if base.extension().is_none() {
        let exts = std::env::var("PATHEXT").unwrap_or_else(|_| ".COM;.EXE;.BAT;.CMD".into());
        for e in exts.split(';').filter(|e| !e.is_empty()) {
            let mut s = base.as_os_str().to_os_string();
            s.push(e);
            v.push(PathBuf::from(s));
        }
    }
    v.push(base.to_path_buf());
    v
}

#[cfg(not(windows))]
fn candidates(base: &Path) -> Vec<PathBuf> {
    vec![base.to_path_buf()]
}

#[cfg(unix)]
fn is_executable(p: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt as _;
    std::fs::metadata(p).is_ok_and(|m| m.is_file() && m.permissions().mode() & 0o111 != 0)
}

#[cfg(not(unix))]
fn is_executable(p: &Path) -> bool {
    p.is_file()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_sh_and_misses_nonsense() {
        #[cfg(unix)]
        assert!(which("sh").is_some());
        assert!(which("definitely-not-a-program-xyz").is_none());
        assert!(which("").is_none());
    }

    #[cfg(unix)]
    #[test]
    fn usual_dirs_come_after_path() {
        let home = PathBuf::from("/home/u");
        let path = std::env::join_paths([PathBuf::from("/usr/bin"), home.join(".local/bin")]).unwrap();
        let dirs: Vec<PathBuf> = std::env::split_paths(&with_usual_dirs(Some(path), Some(home.clone())).unwrap()).collect();
        assert_eq!(dirs[..3], [PathBuf::from("/usr/bin"), home.join(".local/bin"), home.join(".claude/local")]);
        // (Plus npm's prefix where the environment sets one.)
        let npm = usize::from(npm_global_bin(&home).is_some());
        assert_eq!(dirs.len(), 1 + USUAL_HOME_DIRS.len() + USUAL_DIRS.len() + npm, "nothing twice");
        assert!(dirs.contains(&PathBuf::from("/opt/homebrew/bin")));
        // No PATH and no home folder: the system-wide folders still.
        assert_eq!(with_usual_dirs(None, None), std::env::join_paths(USUAL_DIRS).ok());
    }

    /// #112: agents npm installed under nvm, newest Node first, after the usual folders.
    #[cfg(unix)]
    #[test]
    fn nvm_node_versions_are_searched_newest_first() {
        let home = tempfile::tempdir().unwrap();
        for v in ["v9.11.2", "v20.10.0", "v18.19.1"] {
            std::fs::create_dir_all(home.path().join(".nvm/versions/node").join(v).join("bin")).unwrap();
        }
        let bins = nvm_bins(home.path());
        let node = home.path().join(".nvm/versions/node");
        assert_eq!(bins, [node.join("v20.10.0/bin"), node.join("v18.19.1/bin"), node.join("v9.11.2/bin")]);
        let dirs: Vec<PathBuf> = std::env::split_paths(&with_usual_dirs(None, Some(home.path().to_path_buf())).unwrap()).collect();
        assert!(dirs.contains(&home.path().join(".opencode/bin")));
        let at = |p: &Path| dirs.iter().position(|d| d == p).unwrap();
        assert!(at(&home.path().join(".cargo/bin")) < at(&bins[0]) && at(&bins[2]) < at(Path::new("/usr/local/bin")));
        assert!(nvm_bins(Path::new("/nowhere")).is_empty());
    }

    /// #132: npm's own prefix setting says where it put the agents it installed.
    #[test]
    fn npms_prefix_setting_is_searched() {
        let home = tempfile::tempdir().unwrap();
        assert_eq!(npmrc_prefix(home.path()), None, "no .npmrc");
        let rc = home.path().join(".npmrc");
        std::fs::write(&rc, "; a comment\nregistry=https://registry.npmjs.org/\nprefix=/old\nprefix = \"C:\\npm-global\"\n").unwrap();
        assert_eq!(npmrc_prefix(home.path()), Some(PathBuf::from("C:\\npm-global")), "the last one wins, quotes dropped");
        std::fs::write(&rc, "prefix=~/.npm-packages\n").unwrap();
        assert_eq!(npmrc_prefix(home.path()), Some(home.path().join(".npm-packages")));
        std::fs::write(&rc, "#prefix=/commented\nprefix=\n").unwrap();
        assert_eq!(npmrc_prefix(home.path()), None);
        // Unless npm's prefix is set in the environment, the folder it names is searched.
        if std::env::var_os("NPM_CONFIG_PREFIX").is_none() && std::env::var_os("npm_config_prefix").is_none() {
            std::fs::write(&rc, "prefix=~/.npm-packages\n").unwrap();
            let bin = if cfg!(windows) { home.path().join(".npm-packages") } else { home.path().join(".npm-packages").join("bin") };
            let dirs: Vec<PathBuf> = std::env::split_paths(&with_usual_dirs(None, Some(home.path().to_path_buf())).unwrap()).collect();
            assert!(dirs.contains(&bin), "{dirs:?}");
        }
    }

    #[cfg(windows)]
    #[test]
    fn usual_windows_dirs_come_after_path() {
        let home = PathBuf::from(r"C:\Users\u");
        let path = OsString::from(r"C:\Windows;C:\Users\u\.local\bin");
        let dirs: Vec<PathBuf> = std::env::split_paths(&with_usual_dirs(Some(path), Some(home.clone())).unwrap()).collect();
        assert_eq!(dirs[..3], [PathBuf::from(r"C:\Windows"), home.join(r".local\bin"), home.join(r"AppData\Roaming\npm")]);
        // (Plus npm's prefix where the environment sets one.)
        let npm = usize::from(npm_global_bin(&home).is_some());
        assert_eq!(dirs.len(), 1 + USUAL_HOME_DIRS.len() + USUAL_DIRS.len() + npm, "nothing twice");
        // Each way Claude Code installs on Windows: native, npm, WinGet (per user and machine-wide).
        assert!(dirs.contains(&home.join(r"AppData\Local\Microsoft\WinGet\Links")));
        assert!(dirs.contains(&PathBuf::from(r"C:\Program Files\WinGet\Links")));
    }

    const NPM_SHIM: &str = "@ECHO off\r\nGOTO start\r\n:find_dp0\r\nSET dp0=%~dp0\r\nEXIT /b\r\n:start\r\nSETLOCAL\r\nCALL :find_dp0\r\n\r\n\
        IF EXIST \"%dp0%\\node.exe\" (\r\n  SET \"_prog=%dp0%\\node.exe\"\r\n) ELSE (\r\n  SET \"_prog=node\"\r\n  SET PATHEXT=%PATHEXT:;.JS;=;%\r\n)\r\n\r\n\
        endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & \"%_prog%\"  \"%dp0%\\node_modules\\@google\\gemini-cli\\dist\\index.js\" %*\r\n";

    #[test]
    fn npm_shims_name_their_script() {
        assert_eq!(parse_npm_shim(NPM_SHIM), Some((Some("node".into()), r"node_modules\@google\gemini-cli\dist\index.js".into())));
        let pnpm = "@SETLOCAL\n@IF EXIST \"%~dp0\\node.exe\" (\n  \"%~dp0\\node.exe\"  \"%~dp0\\..\\pnpm\\bin\\pnpm.cjs\" %*\n) ELSE (\n  node  \"%~dp0\\..\\pnpm\\bin\\pnpm.cjs\" %*\n)\n";
        assert_eq!(parse_npm_shim(pnpm), Some((Some("node".into()), r"..\pnpm\bin\pnpm.cjs".into())));
        let exe = "@ECHO off\nendLocal & \"%dp0%\\node_modules\\tool\\bin\\tool.exe\"   %*\n";
        assert_eq!(parse_npm_shim(exe), Some((None, r"node_modules\tool\bin\tool.exe".into())));
        // Not a shim we know: the batch file is run as it is.
        assert_eq!(parse_npm_shim("@echo off\r\n\"%NODE_EXE%\" \"%NPM_CLI_JS%\" %*\r\n"), None);
        assert_eq!(parse_npm_shim("@echo off\r\necho hi\r\n"), None);
    }

    #[cfg(windows)]
    #[test]
    fn npm_shims_start_their_script_with_node() {
        let dir = tempfile::tempdir().unwrap();
        let shim = dir.path().join("gemini.cmd");
        std::fs::write(&shim, NPM_SHIM).unwrap();
        // The shim's script missing: the batch file itself.
        assert_eq!(launch_target(shim.as_os_str()), (shim.clone().into_os_string(), Vec::new()));
        let script = dir.path().join(r"node_modules\@google\gemini-cli\dist\index.js");
        std::fs::create_dir_all(script.parent().unwrap()).unwrap();
        std::fs::write(&script, "").unwrap();
        std::fs::write(dir.path().join("node.exe"), "").unwrap();
        // Found without its extension too, as a bare name is.
        assert_eq!(launch_target(dir.path().join("gemini").as_os_str()), (dir.path().join("node.exe").into_os_string(), vec![script.into_os_string()]));
        // An .exe is left to the system's own lookup.
        assert_eq!(launch_target(dir.path().join("node").as_os_str()), (dir.path().join("node").into_os_string(), Vec::new()));
    }

    /// A prompt with line breaks and quotes reaches the agent whole (needs Node; skipped without).
    #[cfg(windows)]
    #[test]
    fn a_shim_gets_a_multiline_prompt() {
        if which("node").is_none() {
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let script = dir.path().join(r"node_modules\@google\gemini-cli\dist\index.js");
        std::fs::create_dir_all(script.parent().unwrap()).unwrap();
        std::fs::write(&script, "process.stdout.write(JSON.stringify(process.argv.slice(2)))").unwrap();
        std::fs::write(dir.path().join("gemini.cmd"), NPM_SHIM).unwrap();
        let prompt = "Make a game.\nIt says \"hi\" & 100% works | <ok>";
        let out = crate::Process::new(dir.path().join("gemini")).args(["-p", prompt]).run_checked().unwrap();
        assert_eq!(serde_json::from_str::<Vec<String>>(&out.stdout_text()).unwrap(), ["-p", prompt]);
    }

    /// #41: npm writes an extensionless POSIX script beside its `.cmd` shim, and Windows can't start
    /// that script by name, so a bare name must find the shim first.
    #[cfg(windows)]
    #[test]
    fn a_bare_name_finds_what_windows_can_start() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("tool"), "#!/bin/sh\n").unwrap();
        std::fs::write(dir.path().join("tool.cmd"), "@echo off\n").unwrap();
        let path = || Some(dir.path().as_os_str().to_owned());
        // The extension comes from PATHEXT, so its case need not match the file's.
        let found = which_in("tool", path());
        assert_eq!(found.len(), 1);
        assert!(found[0].file_name().is_some_and(|n| n.to_string_lossy().eq_ignore_ascii_case("tool.cmd")), "the shim, not the POSIX script: {found:?}");
        // With only the script there, it's still reported (and starting it fails with the program's name).
        std::fs::remove_file(dir.path().join("tool.cmd")).unwrap();
        assert_eq!(which_in("tool", path()), vec![dir.path().join("tool")]);
    }

    #[cfg(unix)]
    #[test]
    fn explicit_search_path() {
        use std::os::unix::fs::PermissionsExt as _;
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("tool");
        std::fs::write(&p, "#!/bin/sh\n").unwrap();
        assert!(which_in("tool", Some(dir.path().as_os_str().to_owned())).is_empty());
        std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(which_in("tool", Some(dir.path().as_os_str().to_owned())), vec![p]);
    }
}
