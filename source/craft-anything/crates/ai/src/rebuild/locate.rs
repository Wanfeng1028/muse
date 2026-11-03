//! Finding what to study in a local target: the program behind a launcher, a game's own folder,
//! and a plain-words inventory of its files.

use super::*;

/// The folder whose files show how a picked game was made (beside a launcher, above bin/).
pub fn game_folder(path: &Path) -> Option<PathBuf> {
    locate(path, true).1
}

/// The game's own folder when the person picked one of its inner folders (Unreal's Engine/, a
/// Binaries/Win64, Content/Paks…): up to two levels, never further, so a pick can't widen to a
/// whole game library.
pub(super) fn game_root(picked: &Path) -> PathBuf {
    const INNER: [&str; 8] = ["engine", "binaries", "win64", "win32", "content", "paks", "bin", "bin_win32"];
    let mut dir = picked.to_path_buf();
    for _ in 0..2 {
        let name = dir.file_name().and_then(|n| n.to_str()).unwrap_or_default().to_ascii_lowercase();
        match dir.parent() {
            Some(up) if INNER.contains(&name.as_str()) => dir = up.to_path_buf(),
            _ => break,
        }
    }
    dir
}

/// What to study for a local target: the program itself (a launcher script points at it), and
/// the folder whose maps, pictures and sounds show how it looks (for launchers, and for games
/// when `game`).
pub(super) fn locate(path: &Path, game: bool) -> (PathBuf, Option<PathBuf>) {
    if path.is_dir() {
        if game {
            let root = game_root(path);
            return (main_program(&root).unwrap_or_else(|| path.to_path_buf()), Some(root));
        }
        return (path.to_path_buf(), None);
    }
    let dir = path.parent().unwrap_or(Path::new(".")).to_path_buf();
    let ext = path.extension().and_then(|e| e.to_str()).unwrap_or_default().to_ascii_lowercase();
    if ["bat", "cmd", "sh", "command", "ps1"].contains(&ext.as_str()) {
        let program = script_program(path).or_else(|| main_program(&dir)).unwrap_or_else(|| path.to_path_buf());
        return (program, Some(dir));
    }
    // A game's program often sits in bin/, bin_win32/ or Binaries/Win64; its content is above.
    let mut root = dir;
    for _ in 0..3 {
        let name = root.file_name().and_then(|n| n.to_str()).unwrap_or_default().to_ascii_lowercase();
        match root.parent() {
            Some(up) if name.starts_with("bin") || ["win64", "win32", "x64", "x86"].contains(&name.as_str()) => root = up.to_path_buf(),
            _ => break,
        }
    }
    (path.to_path_buf(), game.then_some(root))
}

/// The program a launcher script starts: the first word in it that names an existing file.
pub(super) fn script_program(script: &Path) -> Option<PathBuf> {
    let dir = script.parent()?;
    let text = std::fs::read(script).ok()?;
    let text = String::from_utf8_lossy(&text[..text.len().min(64 * 1024)]);
    text.split(|c: char| c.is_whitespace() || c == '"' || c == '\'')
        .map(|w| w.trim_start_matches("%~dp0").trim_start_matches("$(dirname \"$0\")/").trim_start_matches("./"))
        .filter(|w| !w.is_empty() && !w.starts_with('-'))
        .map(|w| dir.join(w.replace('\\', std::path::MAIN_SEPARATOR_STR)))
        .find(|p| p.is_file() && p.as_path() != script && is_program(p))
}

/// The biggest program in a folder (3 levels deep), skipping installers, servers and helpers.
pub(super) fn main_program(dir: &Path) -> Option<PathBuf> {
    const SKIP: [&str; 8] = ["unins", "setup", "install", "crash", "redist", "server", "update", "helper"];
    let mut best: Option<(u64, PathBuf)> = None;
    let mut stack = vec![(dir.to_path_buf(), 0)];
    while let Some((d, depth)) = stack.pop() {
        for e in std::fs::read_dir(&d).into_iter().flatten().flatten() {
            let p = e.path();
            if p.is_dir() {
                if depth < 3 {
                    stack.push((p, depth + 1));
                }
                continue;
            }
            let name = p.file_name().and_then(|n| n.to_str()).unwrap_or_default().to_ascii_lowercase();
            let size = e.metadata().map(|m| m.len()).unwrap_or(0);
            if is_program(&p) && !SKIP.iter().any(|s| name.contains(s)) && best.as_ref().is_none_or(|(b, _)| size > *b) {
                best = Some((size, p));
            }
        }
    }
    best.map(|(_, p)| p)
}

/// A plain-words list of a game folder's content (maps, pictures, models, sounds, settings),
/// with a few example paths each, so the builder knows what shapes the look and where to look.
pub(super) fn inventory(folder: &Path) -> String {
    const KINDS: [(&str, &[&str]); 6] = [
        ("Maps and levels", &["cgz", "ogz", "bsp", "map", "tmx", "ldtk", "lvl", "wad", "umap", "level"]),
        ("Textures and pictures", &["png", "jpg", "jpeg", "tga", "dds", "bmp", "ktx", "webp", "gif"]),
        ("3D models", &["md2", "md3", "md5mesh", "iqm", "obj", "fbx", "gltf", "glb", "mdl", "dae", "3ds", "ply"]),
        ("Sounds and music", &["ogg", "wav", "mp3", "flac", "opus"]),
        ("Settings and scripts", &["cfg", "ini", "json", "lua", "xml", "yaml", "yml", "toml", "txt"]),
        ("Read-me and licence files", &["md", "html", "htm", "rtf"]),
    ];
    let mut found: Vec<(usize, u64, Vec<PathBuf>)> = vec![(0, 0, Vec::new()); KINDS.len()];
    let mut stack = vec![(folder.to_path_buf(), 0)];
    let mut seen = 0usize;
    // Bounded, so picking a huge folder can't stall the study.
    while seen < 50_000
        && let Some((d, depth)) = stack.pop()
    {
        for e in std::fs::read_dir(&d).into_iter().flatten().flatten() {
            seen += 1;
            let p = e.path();
            if p.is_dir() {
                if depth < 6 {
                    stack.push((p, depth + 1));
                }
                continue;
            }
            let ext = p.extension().and_then(|x| x.to_str()).unwrap_or_default().to_ascii_lowercase();
            let stem = p.file_stem().and_then(|x| x.to_str()).unwrap_or_default().to_ascii_lowercase();
            // A licence.txt says what may be reused, so it goes with the licences, not settings.
            let licence = ["licen", "copying", "readme"].iter().any(|w| stem.starts_with(w));
            let kind = if licence { Some(KINDS.len() - 1) } else { KINDS.iter().position(|(_, exts)| exts.contains(&ext.as_str())) };
            if let Some(i) = kind {
                let f = &mut found[i];
                f.0 += 1;
                f.1 += e.metadata().map(|m| m.len()).unwrap_or(0);
                // Examples from different folders say more than ten files side by side.
                if f.2.len() < 8 && !f.2.iter().any(|q| q.parent() == p.parent()) {
                    f.2.push(p);
                }
            }
        }
    }
    let mut s = format!("\n## The game's own files\n\nFolder: {}\n\n", folder.display());
    for ((title, _), (count, bytes, examples)) in KINDS.iter().zip(&found) {
        if *count == 0 {
            continue;
        }
        s.push_str(&format!("- {title}: {count} files, {:.1} MB. For example:\n", *bytes as f64 / 1_048_576.0));
        for p in examples {
            s.push_str(&format!("  - {}\n", p.strip_prefix(folder).unwrap_or(p).display()));
        }
    }
    if found.iter().all(|f| f.0 == 0) {
        s.push_str("No maps, pictures, models or sounds were found here.\n");
    }
    s
}
