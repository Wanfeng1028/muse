//! Game engines: which one a game was made with (from its files, nothing is run), which ones this
//! computer can build with, and how to get one.
//!
//! Getting an engine never bypasses the vendor: Godot is a portable download checked against the
//! official checksums; Unity Hub and the Epic Games Launcher are the vendors' own installers,
//! opened only after Windows confirms the vendor signed them. Accounts, licences and terms stay in
//! the vendor's own windows, with the person.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::{Cancel, Launch, Process};
use serde::{Deserialize, Serialize};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

/// The engine a game was made with.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Made {
    Unity,
    Unreal,
    Godot,
    Source,
    Cube,
    GameMaker,
    RpgMaker,
    RenPy,
    MonoGame,
    Love,
    CryEngine,
    Cocos,
}

impl Made {
    pub fn name(self) -> &'static str {
        match self {
            Made::Unity => "Unity",
            Made::Unreal => "Unreal Engine",
            Made::Godot => "Godot",
            Made::Source => "Source (Valve)",
            Made::Cube => "the Cube engine",
            Made::GameMaker => "GameMaker",
            Made::RpgMaker => "RPG Maker",
            Made::RenPy => "Ren'Py",
            Made::MonoGame => "MonoGame / XNA",
            Made::Love => "LÖVE",
            Made::CryEngine => "CryEngine",
            Made::Cocos => "Cocos",
        }
    }
}

/// What [`detect`] found.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Found {
    pub engine: Made,
    pub version: Option<String>,
    /// The file that gave it away, relative to the game's folder.
    pub clue: String,
    /// Something worth knowing for the rebuild (e.g. how a Unity game's code is shipped).
    pub note: Option<String>,
}

impl Found {
    /// "Unity 2021.3.16f1".
    pub fn label(&self) -> String {
        match &self.version {
            Some(v) => format!("{} {v}", self.engine.name()),
            None => self.engine.name().to_string(),
        }
    }
}

/// An engine Craft Anything can build a game with.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Builder {
    Unity,
    Unreal,
    Godot,
    Rust,
}

impl Builder {
    /// In the order they're offered: the default first, Rust (no editor needed) last.
    pub const ALL: [Builder; 4] = [Builder::Unity, Builder::Unreal, Builder::Godot, Builder::Rust];

    pub fn name(self) -> &'static str {
        match self {
            Builder::Unity => "Unity",
            Builder::Unreal => "Unreal Engine",
            Builder::Godot => "Godot",
            Builder::Rust => "Rust",
        }
    }

    /// The stack text kept in a project's manifest.
    pub fn stack(self) -> &'static str {
        match self {
            Builder::Unity => "Unity",
            Builder::Unreal => "Unreal Engine",
            Builder::Godot => "Godot",
            Builder::Rust => "Rust + macroquad",
        }
    }

    pub fn from_stack(stack: &str) -> Option<Builder> {
        Builder::ALL.into_iter().find(|b| b.stack() == stack)
    }

    /// Build with the game's own engine when we can, else Unity.
    pub fn for_game(made: Option<Made>) -> Builder {
        match made {
            Some(Made::Unreal) => Builder::Unreal,
            Some(Made::Godot) => Builder::Godot,
            _ => Builder::Unity,
        }
    }

    /// Roughly what getting it involves, in plain words.
    pub fn needs(self) -> &'static str {
        match self {
            Builder::Unity => "About 10 GB. Free for personal use with a Unity account.",
            Builder::Unreal if cfg!(target_os = "linux") => "An Unreal Engine Linux installation with its bundled Clang C++ toolchain.",
            Builder::Unreal => "About 60 GB, an Epic Games account, and Visual Studio's C++ tools.",
            Builder::Godot => "A small download (under 200 MB). Free, no account needed.",
            Builder::Rust => "The Rust toolchain (rustup.rs).",
        }
    }
}

// ---- which engine made this game --------------------------------------------------------------

/// Which engine made the game in `folder` (its files only; nothing is run). `None` when nothing
/// recognisable was found.
pub fn detect(folder: &Path) -> Option<Found> {
    detect_in(&list(folder, 4, 30_000))
}

/// [`detect`] over a listing someone already made: (lowercase relative path with `/`, real path)
/// of regular files, nearest first.
pub fn detect_in(files: &[(String, PathBuf)]) -> Option<Found> {
    let find = |pred: &dyn Fn(&str) -> bool| files.iter().find(|(l, _)| pred(l));
    let found = |engine, version, clue: &str, note: Option<&str>| Found { engine, version, clue: clue.to_string(), note: note.map(str::to_string) };

    if let Some((l, _)) = find(&|l| l.ends_with(".pak") && l.contains("content/paks/")).or_else(|| find(&|l| l.ends_with("-shipping.exe"))) {
        let exe = find(&|l| l.ends_with("-shipping.exe") || (l.ends_with(".exe") && l.contains("binaries/win64/")));
        let version = exe.and_then(|(_, p)| unreal_version(p));
        return Some(found(Made::Unreal, version, l, Some("Its content is packed in .pak files under Content/Paks.")));
    }
    let unity = ["unityplayer.dll", "gameassembly.dll", "unityplayer.dylib", "unityplayer.so"];
    let unity_data = ["globalgamemanagers", "data.unity3d", "maindata"];
    if let Some((l, _)) = find(&|l| unity.contains(&file_name(l)) || (l.contains("_data/") && unity_data.contains(&file_name(l)))) {
        let version = files
            .iter()
            .filter(|(l, _)| l.contains("_data/") && (unity_data.contains(&file_name(l)) || file_name(l) == "level0"))
            .find_map(|(_, p)| head(p, 1024).and_then(|b| unity_version(&b)));
        let note = if find(&|l| file_name(l) == "gameassembly.dll").is_some() {
            "Its C# code was compiled to native code (IL2CPP), so it reads like any native program."
        } else if find(&|l| l.ends_with("managed/assembly-csharp.dll")).is_some() {
            "Its gameplay code is in Managed/Assembly-CSharp.dll (.NET), which reads back almost like the original C#."
        } else {
            "A Unity game."
        };
        return Some(found(Made::Unity, version, l, Some(note)));
    }
    if let Some((l, p)) = find(&|l| l.ends_with(".pck"))
        && let Some(v) = std::fs::File::open(p).ok().and_then(|mut f| godot_header(&mut f, 0))
    {
        return Some(found(Made::Godot, Some(v), l, None));
    }
    if let Some((l, v)) = files.iter().filter(|(l, _)| l.ends_with(".exe") || l.ends_with(".x86_64")).find_map(|(l, p)| godot_embedded(p).map(|v| (l, v))) {
        return Some(found(Made::Godot, Some(v), l, Some("Its game data is packed inside the program.")));
    }
    type Rule<'a> = (Made, &'a dyn Fn(&str) -> bool);
    let rules: [Rule; 9] = [
        (Made::Source, &|l| file_name(l) == "gameinfo.txt" || l.ends_with("_dir.vpk")),
        (Made::Cube, &|l| l.starts_with("packages/") && (l.ends_with(".cgz") || l.ends_with(".ogz"))),
        (Made::GameMaker, &|l| ["data.win", "game.unx", "game.ios"].contains(&file_name(l))),
        (Made::RpgMaker, &|l| ["rpg_core.js", "rmmz_core.js", "game.rgss3a", "game.rgss2a", "game.rgssad"].contains(&file_name(l))),
        (Made::RenPy, &|l| l.starts_with("renpy/") || l.ends_with(".rpa")),
        (Made::MonoGame, &|l| ["monogame.framework.dll", "microsoft.xna.framework.dll", "fna.dll"].contains(&file_name(l))),
        (Made::Love, &|l| file_name(l) == "love.dll" || l.ends_with(".love")),
        (Made::CryEngine, &|l| file_name(l) == "crysystem.dll"),
        (Made::Cocos, &|l| file_name(l).starts_with("libcocos2d")),
    ];
    rules.iter().find_map(|(engine, pred)| find(*pred).map(|(l, _)| found(*engine, None, l, None)))
}

fn file_name(l: &str) -> &str {
    l.rsplit('/').next().unwrap_or(l)
}

// ---- what a game is made of ---------------------------------------------------------------------

/// A library or tool a game was built with.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StackItem {
    pub name: String,
    /// What it's for, in plain words.
    pub what: String,
}

/// What a game is made of, read from its files (nothing is run).
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Profile {
    pub found: Option<Found>,
    /// The engine and its version, e.g. "Unity 2022.3.62f2".
    pub engine: Option<String>,
    /// Libraries recognised by its code's assembly names (Unity games), in the order listed.
    pub stack: Vec<StackItem>,
    /// Its other assemblies: the game's own code, or libraries we don't recognise.
    pub other_code: Vec<String>,
    /// The same, grouped by their first name ("Combat (4)" for Combat, Combat.Systems…).
    pub other_groups: Vec<String>,
    /// Where the assembly names were read, relative to the game's folder.
    pub code_list: Option<String>,
    /// Scene files (Unity's level0, level1…).
    pub scenes: usize,
    pub bytes: u64,
    pub files: usize,
    /// The folder holds more than was counted, so `bytes` and `files` are a floor.
    pub capped: bool,
}

/// Groups of other code named in a profile's summary (all are in `other_groups`).
const SUMMARY_GROUPS: usize = 12;

/// Files counted for a profile's size.
const MAX_COUNTED: usize = 200_000;

/// Libraries recognised by an assembly name: (name it starts with, what it is, what it's for).
const KNOWN: &[(&str, &str, &str)] = &[
    ("Unity.RenderPipelines.Universal", "URP", "rendering"),
    ("Unity.RenderPipelines.HighDefinition", "HDRP", "rendering"),
    ("Unity.Postprocessing", "Post Processing", "screen effects"),
    ("Unity.InputSystem", "Input System", "controls"),
    ("Unity.TextMeshPro", "TextMeshPro", "text"),
    ("Unity.Timeline", "Timeline", "cutscenes and sequences"),
    ("Cinemachine", "Cinemachine", "cameras"),
    ("Unity.Cinemachine", "Cinemachine", "cameras"),
    ("Unity.Netcode", "Netcode for GameObjects", "multiplayer"),
    ("Unity.Entities", "Entities (DOTS)", "many objects at once"),
    ("Unity.Addressables", "Addressables", "loading content"),
    ("Unity.Localization", "Localization", "languages"),
    ("Unity.AI.Navigation", "AI Navigation", "characters finding their way"),
    ("Unity.VisualScripting", "Visual Scripting", "logic built without code"),
    ("Unity.Burst", "Burst", "fast code"),
    ("FishNet", "FishNet", "multiplayer"),
    ("Mirror", "Mirror", "multiplayer"),
    ("PhotonUnityNetworking", "Photon PUN", "multiplayer"),
    ("PhotonRealtime", "Photon Realtime", "multiplayer"),
    ("Fusion.Runtime", "Photon Fusion", "multiplayer"),
    ("Edgegap", "Edgegap", "game servers"),
    ("com.rlabrecque.steamworks.net", "Steamworks.NET", "Steam features"),
    ("Steamworks.NET", "Steamworks.NET", "Steam features"),
    ("Facepunch.Steamworks", "Facepunch.Steamworks", "Steam features"),
    ("EOSSDK", "Epic Online Services", "online features"),
    ("AstarPathfindingProject", "A* Pathfinding Project", "characters finding their way"),
    ("Pathfinding", "A* Pathfinding Project", "characters finding their way"),
    ("RootMotion", "Final IK", "character poses"),
    ("Newtonsoft.Json", "Newtonsoft.Json", "reading and writing data, often saves"),
    ("DOTween", "DOTween", "animation"),
    ("DG.Tweening", "DOTween", "animation"),
    ("Rewired", "Rewired", "controls"),
    ("FMODUnity", "FMOD", "sound"),
    ("AK.Wwise.Unity.API", "Wwise", "sound"),
    ("Sirenix.Serialization", "Odin", "data and editor tools"),
    ("UniTask", "UniTask", "background work"),
    ("Zenject", "Zenject", "how the code is wired together"),
    ("I2Localization", "I2 Localization", "languages"),
    ("AmplifyImpostors", "Amplify Impostors", "far-away objects"),
    ("AmplifyShaderEditor", "Amplify Shader Editor", "materials"),
    ("StylizedWater2", "Stylized Water 2", "water"),
    ("sc.stylizedwater2", "Stylized Water 2", "water"),
    ("CorgiGodRays", "Corgi God Rays", "light shafts"),
    ("AmazingAssets.TerrainToMesh", "Terrain To Mesh", "terrain"),
    ("com.olegknyazev.softmask", "SoftMask", "interface masks"),
    ("HSVPicker", "HSV Picker", "colour picker"),
    ("Ookii.Dialogs", "Ookii Dialogs", "file dialogs"),
    ("Autodesk.Fbx", "FBX SDK", "3D model files"),
    ("Sentry", "Sentry", "crash reports"),
    ("io.sentry", "Sentry", "crash reports"),
    ("PlayFab", "PlayFab", "online services"),
    ("PlayFabMultiplayerSDK", "PlayFab", "online services"),
    ("PlayFabParty", "PlayFab Party", "voice and text chat"),
    ("Discord.SDK", "Discord SDK", "Discord features"),
    ("modio", "mod.io", "mods"),
    ("MessagePack", "MessagePack", "saving and sending data"),
    ("QFSW.QC", "Quantum Console", "a developer console"),
    ("DissonanceVoip", "Dissonance", "voice chat"),
    ("DunGen", "DunGen", "dungeon generation"),
    ("Facepunch Transport for Netcode for GameObjects", "Facepunch Transport", "multiplayer over Steam"),
    ("NaughtyAttributes", "NaughtyAttributes", "editor tools"),
    ("RoslynCSharp", "Roslyn C#", "compiling C# while it runs, often for mods"),
    ("0Harmony", "Harmony", "changing code while it runs, often for mods"),
    ("MonoMod", "MonoMod", "changing code while it runs, often for mods"),
    ("I2", "I2 Localization", "languages"),
    ("VisualDesignCafe", "Nature Renderer", "grass and trees"),
    ("BepInEx", "BepInEx", "mods"),
    ("MelonLoader", "MelonLoader", "mods"),
];

/// The engine's and .NET's own assemblies, left out of a game's stack.
const PLATFORM: &[&str] = &["UnityEngine", "UnityEditor", "Unity", "System", "Mono", "mscorlib", "netstandard", "Microsoft", "__Generated", "Bee"];

/// `name` is `prefix`, or `prefix` followed by `.`, `-` or `_`.
fn named(name: &str, prefix: &str) -> bool {
    name.strip_prefix(prefix).is_some_and(|rest| rest.is_empty() || rest.starts_with(['.', '-', '_']))
}

/// What the game in `folder` is made of (its files only; nothing is run).
pub fn profile(folder: &Path) -> Profile {
    let all = list(folder, 8, MAX_COUNTED);
    let bytes = all.iter().filter_map(|(_, p)| std::fs::metadata(p).ok()).fold(0u64, |n, m| n.saturating_add(m.len()));
    let scenes = all
        .iter()
        .filter(|(l, _)| l.contains("_data/") && file_name(l).strip_prefix("level").is_some_and(|n| !n.is_empty() && n.bytes().all(|b| b.is_ascii_digit())))
        .count();
    let (code_list, names) = assemblies(folder, &all);
    let found = detect(folder);
    let mut p = Profile {
        engine: found.as_ref().map(Found::label),
        found,
        code_list,
        scenes,
        bytes,
        files: all.len(),
        capped: all.len() >= MAX_COUNTED,
        ..Default::default()
    };
    for n in names {
        match KNOWN.iter().find(|(prefix, ..)| named(&n, prefix)) {
            Some((_, name, what)) => {
                if !p.stack.iter().any(|s| s.name == *name) {
                    p.stack.push(StackItem { name: name.to_string(), what: what.to_string() });
                }
            }
            None if !PLATFORM.iter().any(|prefix| named(&n, prefix)) && !p.other_code.contains(&n) => p.other_code.push(n),
            None => {}
        }
    }
    let mut groups: Vec<(&str, usize)> = Vec::new();
    for n in &p.other_code {
        let first = n.split('.').next().unwrap_or(n);
        match groups.iter_mut().find(|(g, _)| *g == first) {
            Some((_, count)) => *count += 1,
            None => groups.push((first, 1)),
        }
    }
    p.other_groups = groups.into_iter().map(|(g, n)| if n == 1 { g.to_string() } else { format!("{g} ({n})") }).collect();
    p
}

/// A Unity game's assembly names (without `.dll`): from its ScriptingAssemblies.json, else its
/// Managed folder; with where they were read.
fn assemblies(folder: &Path, all: &[(String, PathBuf)]) -> (Option<String>, Vec<String>) {
    let shown = |p: &Path| p.strip_prefix(folder).unwrap_or(p).display().to_string();
    let stem = |n: &str| n.strip_suffix(".dll").unwrap_or(n).to_string();
    if let Some((_, p)) = all.iter().find(|(l, _)| l.contains("_data/") && file_name(l) == "scriptingassemblies.json") {
        let json = head(p, 4 << 20).and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok()).unwrap_or_default();
        let names = json["names"].as_array().into_iter().flatten().filter_map(|n| n.as_str()).map(stem).collect();
        return (Some(shown(p)), names);
    }
    let managed: Vec<&PathBuf> = all.iter().filter(|(l, _)| l.contains("_data/managed/") && l.ends_with(".dll")).map(|(_, p)| p).collect();
    let names = managed.iter().filter_map(|p| p.file_name()).map(|n| stem(&n.to_string_lossy())).collect();
    (managed.first().and_then(|p| p.parent()).map(shown), names)
}

impl Profile {
    /// A few plain sentences about the game; `None` when no engine was recognised.
    pub fn summary(&self, name: &str) -> Option<String> {
        let found = self.found.as_ref()?;
        let mut s = format!("{name} is a game made with {}.", found.label());
        if let Some(note) = &found.note {
            s.push(' ');
            s.push_str(note);
        }
        if !self.stack.is_empty() {
            let list: Vec<String> = self.stack.iter().map(|i| format!("{} ({})", i.name, i.what)).collect();
            s.push_str(&format!(" Built with: {}.", list.join(", ")));
        }
        if !self.other_groups.is_empty() {
            let shown = self.other_groups.iter().take(SUMMARY_GROUPS).cloned().collect::<Vec<_>>().join(", ");
            let more = self.other_groups.len().saturating_sub(SUMMARY_GROUPS);
            let more = if more > 0 { format!(" and {more} more") } else { String::new() };
            s.push_str(&format!(" Its own code, or libraries we don't recognise: {shown}{more}."));
        }
        if self.scenes > 0 {
            s.push_str(&format!(" {} scene file{}.", self.scenes, if self.scenes == 1 { "" } else { "s" }));
        }
        let floor = if self.capped { "at least " } else { "" };
        s.push_str(&format!(" Size: {floor}{} in {} files.", craft_anything_evidence::human_bytes(self.bytes), self.files));
        Some(s)
    }
}

/// Files under `root` as (lowercase relative path with `/`, real path), breadth-first and bounded.
fn list(root: &Path, max_depth: usize, max_files: usize) -> Vec<(String, PathBuf)> {
    let mut out = Vec::new();
    let mut queue = std::collections::VecDeque::from([(root.to_path_buf(), 0)]);
    while let Some((dir, depth)) = queue.pop_front() {
        for e in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            if out.len() >= max_files {
                return out;
            }
            let p = e.path();
            if p.is_dir() {
                if depth < max_depth {
                    queue.push_back((p, depth + 1));
                }
            } else if let Ok(rel) = p.strip_prefix(root) {
                out.push((rel.to_string_lossy().replace('\\', "/").to_ascii_lowercase(), p));
            }
        }
    }
    out
}

fn head(p: &Path, n: usize) -> Option<Vec<u8>> {
    let mut buf = vec![0; n];
    let got = std::fs::File::open(p).ok()?.read(&mut buf).ok()?;
    buf.truncate(got);
    Some(buf)
}

/// A Unity version token ("2021.3.16f1", "5.6.7f1", "6000.0.23f1") in a data file's header.
pub fn unity_version(bytes: &[u8]) -> Option<String> {
    let text: String = bytes.iter().map(|&b| if b.is_ascii_graphic() { b as char } else { ' ' }).collect();
    text.split(|c: char| !(c.is_ascii_alphanumeric() || c == '.')).find(|w| is_unity_version(w)).map(str::to_string)
}

fn is_unity_version(w: &str) -> bool {
    let parts: Vec<&str> = w.split('.').collect();
    let [major, minor, last] = parts.as_slice() else { return false };
    let digits = |s: &str| !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit());
    let Some(i) = last.find(['a', 'b', 'f', 'p', 'x']) else { return false };
    digits(major) && major.len() <= 4 && digits(minor) && digits(&last[..i]) && digits(&last[i + 1..])
}

/// The Unreal version a shipped program was built with ("5.3"), from its "++UE5+Release-5.3"
/// build tag (ASCII or UTF-16). Reads at most 512 MB.
pub fn unreal_version(exe: &Path) -> Option<String> {
    let mut f = std::fs::File::open(exe).ok()?;
    let tags: [Vec<u8>; 4] = [b"++UE5+Release-".to_vec(), b"++UE4+Release-".to_vec(), utf16("++UE5+Release-"), utf16("++UE4+Release-")];
    let mut buf = vec![0u8; 8 << 20];
    let mut carry: Vec<u8> = Vec::new();
    let mut read_total = 0usize;
    while read_total < 512 << 20 {
        let n = f.read(&mut buf).ok()?;
        if n == 0 {
            return None;
        }
        read_total += n;
        let mut window = std::mem::take(&mut carry);
        window.extend_from_slice(&buf[..n]);
        for (i, tag) in tags.iter().enumerate() {
            if let Some(at) = window.windows(tag.len()).position(|w| w == tag.as_slice()) {
                let rest = &window[at + tag.len()..];
                let step = if i >= 2 { 2 } else { 1 };
                let v: String = rest.iter().step_by(step).take_while(|b| b.is_ascii_digit() || **b == b'.').map(|&b| b as char).collect();
                let v = v.trim_end_matches('.').to_string();
                if !v.is_empty() {
                    return Some(v);
                }
            }
        }
        carry = window[window.len().saturating_sub(64)..].to_vec();
    }
    None
}

fn utf16(s: &str) -> Vec<u8> {
    s.encode_utf16().flat_map(u16::to_le_bytes).collect()
}

/// A Godot pack header at `offset`: "GDPC", format, then major.minor.patch.
fn godot_header(f: &mut std::fs::File, offset: u64) -> Option<String> {
    let mut h = [0u8; 20];
    f.seek(SeekFrom::Start(offset)).ok()?;
    f.read_exact(&mut h).ok()?;
    if &h[..4] != b"GDPC" {
        return None;
    }
    let n = |i: usize| u32::from_le_bytes([h[i], h[i + 1], h[i + 2], h[i + 3]]);
    Some(format!("{}.{}.{}", n(8), n(12), n(16)))
}

/// A Godot pack embedded at the end of a program: `… pack, u64 pack size, "GDPC"`.
fn godot_embedded(p: &Path) -> Option<String> {
    let mut f = std::fs::File::open(p).ok()?;
    let len = f.metadata().ok()?.len();
    if len < 32 {
        return None;
    }
    let mut tail = [0u8; 12];
    f.seek(SeekFrom::Start(len - 12)).ok()?;
    f.read_exact(&mut tail).ok()?;
    if &tail[8..] != b"GDPC" {
        return None;
    }
    let size = u64::from_le_bytes(tail[..8].try_into().ok()?);
    godot_header(&mut f, len.checked_sub(12 + size)?)
}

// ---- which engines this computer has ------------------------------------------------------------

/// An engine on this computer that can build.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Installed {
    pub builder: Builder,
    pub version: String,
    /// The editor (or toolchain) program.
    pub program: PathBuf,
}

/// What's on this computer: engines that can build, and the vendor apps that get them.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Inventory {
    pub engines: Vec<Installed>,
    pub unity_hub: Option<PathBuf>,
    pub epic_launcher: Option<PathBuf>,
    /// A C++ compiler Unreal can use (Visual Studio, Xcode, or the selected Linux engine's bundled Clang).
    pub cpp_tools: bool,
}

impl Inventory {
    /// The newest install of `b`.
    pub fn best(&self, b: Builder) -> Option<&Installed> {
        self.engines.iter().find(|i| i.builder == b)
    }

    /// Ready to build: Unreal also needs C++ tools.
    pub fn ready(&self, b: Builder) -> bool {
        self.best(b).is_some() && (b != Builder::Unreal || self.cpp_tools)
    }
}

/// Where to look. [`Places::here`] for this computer; tests point it at temporary folders.
#[derive(Debug, Clone, Default)]
pub struct Places {
    pub program_files: Vec<PathBuf>,
    pub program_data: Option<PathBuf>,
    pub app_data: Option<PathBuf>,
    pub home: Option<PathBuf>,
    /// An explicit Unreal installation root, preferred over registered installations when valid.
    pub unreal_root: Option<PathBuf>,
    pub applications: Option<PathBuf>,
    /// Craft Anything's own engine store (where it puts Godot).
    pub store: PathBuf,
    /// Look on PATH too (off in tests).
    pub use_path: bool,
}

impl Places {
    /// Capture environment-based search locations and the supplied engine store, with PATH lookup enabled.
    pub fn here(store: PathBuf) -> Places {
        let env = |k: &str| std::env::var_os(k).map(PathBuf::from);
        Places {
            program_files: [env("ProgramFiles"), env("ProgramFiles(x86)"), env("ProgramW6432")].into_iter().flatten().collect(),
            program_data: env("ProgramData"),
            app_data: env("APPDATA"),
            home: env("HOME").or_else(|| env("USERPROFILE")),
            unreal_root: env("UE_ROOT"),
            applications: cfg!(target_os = "macos").then(|| PathBuf::from("/Applications")),
            store,
            use_path: true,
        }
    }
}

/// Every engine install found, newest first within each engine.
pub fn inventory(p: &Places) -> Inventory {
    let mut engines = Vec::new();
    engines.extend(unity_editors(p));
    engines.extend(unreal_installs(p));
    engines.extend(godot_installs(p));
    if let Some(cargo) = p.use_path.then(|| craft_anything_platform::which("cargo")).flatten() {
        engines.push(Installed { builder: Builder::Rust, version: String::new(), program: cargo });
    }
    engines.sort_by(|a, b| (a.builder as u8).cmp(&(b.builder as u8)).then_with(|| version_key(&b.version).cmp(&version_key(&a.version))));
    engines.dedup_by(|a, b| a.program == b.program);
    let cpp_tools = cpp_tools(p, engines.iter().find(|i| i.builder == Builder::Unreal));
    let first = |paths: Vec<PathBuf>| paths.into_iter().find(|x| x.exists());
    Inventory {
        engines,
        unity_hub: first(
            p.program_files.iter().map(|pf| pf.join("Unity Hub").join("Unity Hub.exe")).chain(p.applications.iter().map(|a| a.join("Unity Hub.app"))).collect(),
        ),
        epic_launcher: first(
            p.program_files
                .iter()
                .flat_map(|pf| ["Win64", "Win32"].map(|w| pf.join("Epic Games/Launcher/Portal/Binaries").join(w).join("EpicGamesLauncher.exe")))
                .chain(p.applications.iter().map(|a| a.join("Epic Games Launcher.app")))
                .collect(),
        ),
        cpp_tools,
    }
}

/// "2022.3.10f1" / "5.4" / "4.4.1" as comparable numbers.
fn version_key(v: &str) -> Vec<u64> {
    v.split(|c: char| !c.is_ascii_digit()).filter(|s| !s.is_empty()).filter_map(|s| s.parse().ok()).collect()
}

fn subdirs(dir: &Path) -> Vec<PathBuf> {
    std::fs::read_dir(dir).into_iter().flatten().flatten().map(|e| e.path()).filter(|p| p.is_dir()).collect()
}

fn unity_editors(p: &Places) -> Vec<Installed> {
    let mut roots: Vec<PathBuf> = p.program_files.iter().map(|pf| pf.join("Unity/Hub/Editor")).collect();
    roots.extend(p.applications.iter().map(|a| a.join("Unity/Hub/Editor")));
    roots.extend(p.home.iter().map(|h| h.join("Unity/Hub/Editor")));
    // Unity Hub's "install location" setting: a JSON string with the folder.
    if let Some(s) = p.app_data.as_ref().and_then(|a| std::fs::read_to_string(a.join("UnityHub/secondaryInstallPath.json")).ok())
        && let Ok(path) = serde_json::from_str::<String>(&s).map(PathBuf::from)
        && !path.as_os_str().is_empty()
    {
        roots.push(path);
    }
    let exes = ["Editor/Unity.exe", "Unity.app/Contents/MacOS/Unity", "Editor/Unity"];
    roots
        .iter()
        .flat_map(|r| subdirs(r))
        .filter_map(|dir| {
            let program = exes.iter().map(|e| dir.join(e)).find(|e| e.is_file())?;
            let version = dir.file_name()?.to_string_lossy().into_owned();
            Some(Installed { builder: Builder::Unity, version, program })
        })
        .collect()
}

/// Prefer a valid absolute `UE_ROOT`; otherwise discover installs in registries and standard folders.
fn unreal_installs(p: &Places) -> Vec<Installed> {
    if let Some(install) = p.unreal_root.as_deref().filter(|root| root.is_absolute()).and_then(unreal_install) {
        return vec![install];
    }
    let mut roots: Vec<PathBuf> = Vec::new();
    // Match UnrealVersionSelector's fixed per-user registry location.
    if let Some(home) = &p.home {
        roots.extend(unreal_registry_roots(&home.join(".config")));
    }
    // The Epic Games Launcher lists its engine installs here.
    if let Some(dat) = p.program_data.as_ref().and_then(|d| std::fs::read_to_string(d.join("Epic/UnrealEngineLauncher/LauncherInstalled.dat")).ok())
        && let Ok(v) = serde_json::from_str::<serde_json::Value>(&dat)
    {
        for i in v["InstallationList"].as_array().into_iter().flatten() {
            if i["AppName"].as_str().is_some_and(|n| n.starts_with("UE_")) {
                roots.extend(i["InstallLocation"].as_str().map(PathBuf::from));
            }
        }
    }
    let shared = [p.program_files.iter().map(|pf| pf.join("Epic Games")).collect::<Vec<_>>(), vec![PathBuf::from("/Users/Shared/Epic Games")]].concat();
    roots.extend(shared.iter().flat_map(|d| subdirs(d)).filter(|d| d.file_name().is_some_and(|n| n.to_string_lossy().starts_with("UE_"))));
    roots.sort();
    roots.dedup();
    roots.iter().filter_map(|dir| unreal_install(dir)).collect()
}

/// UnrealVersionSelector's per-user Linux registry. Only the Installations section contains roots.
fn unreal_registry_roots(config: &Path) -> Vec<PathBuf> {
    let Some(bytes) = head(&config.join("Epic/UnrealEngine/Install.ini"), 1 << 20) else { return Vec::new() };
    let Ok(text) = std::str::from_utf8(&bytes) else { return Vec::new() };
    let mut installations = false;
    let mut roots = Vec::new();
    for line in text.trim_start_matches('\u{feff}').lines().map(str::trim) {
        if line.starts_with('[') {
            installations = line == "[Installations]";
        } else if installations
            && !line.starts_with([';', '#'])
            && let Some((_, root)) = line.split_once('=')
        {
            let root = PathBuf::from(root.trim().trim_matches('"'));
            if root.is_absolute() {
                roots.push(root);
            }
        }
    }
    roots
}

/// Find an editor in an install root, using Linux's `Build.version` when valid or the directory name otherwise.
fn unreal_install(dir: &Path) -> Option<Installed> {
    let exes = [
        "Engine/Binaries/Win64/UnrealEditor.exe",
        "Engine/Binaries/Win64/UE4Editor.exe",
        "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor",
        "Engine/Binaries/Linux/UnrealEditor",
    ];
    let program = exes.iter().map(|e| dir.join(e)).find(|e| e.is_file())?;
    let version = program
        .ends_with("Engine/Binaries/Linux/UnrealEditor")
        .then(|| head(&dir.join("Engine/Build/Build.version"), 64 << 10))
        .flatten()
        .and_then(|bytes| serde_json::from_slice::<serde_json::Value>(&bytes).ok())
        .and_then(|v| Some(format!("{}.{}.{}", v.get("MajorVersion")?.as_u64()?, v.get("MinorVersion")?.as_u64()?, v.get("PatchVersion")?.as_u64()?)))
        .or_else(|| dir.file_name().map(|n| n.to_string_lossy().trim_start_matches("UE_").to_string()))?;
    Some(Installed { builder: Builder::Unreal, version, program })
}

fn godot_installs(p: &Places) -> Vec<Installed> {
    let dir = p.store.join("godot");
    let mut v: Vec<Installed> = std::fs::read_dir(&dir)
        .into_iter()
        .flatten()
        .flatten()
        .map(|e| e.path())
        .filter_map(|path| {
            let name = path.file_name()?.to_string_lossy().into_owned();
            // The console build is a helper; the app build is the editor.
            let editor =
                name.starts_with("Godot_v") && !name.contains("console") && (name.ends_with(".exe") || name.ends_with(".x86_64") || name.ends_with(".app"));
            if !editor {
                return None;
            }
            let program = if name.ends_with(".app") { path.join("Contents/MacOS/Godot") } else { path };
            let version = name.trim_start_matches("Godot_v").split('-').next()?.to_string();
            Some(Installed { builder: Builder::Godot, version, program })
        })
        .collect();
    if p.use_path {
        for n in ["godot4", "godot"] {
            if let Some(program) = craft_anything_platform::which(n) {
                v.push(Installed { builder: Builder::Godot, version: String::new(), program });
            }
        }
    }
    v
}

/// Check filesystem presence of MSVC, Xcode, or the selected Linux engine's bundled Clang.
/// This readiness heuristic does not execute or validate a compiler.
fn cpp_tools(p: &Places, unreal: Option<&Installed>) -> bool {
    if p.applications.as_ref().is_some_and(|a| a.join("Xcode.app").exists()) {
        return true;
    }
    // Visual Studio <year>/<edition>/VC/Tools/MSVC, in either Program Files.
    if p.program_files.iter().flat_map(|pf| subdirs(&pf.join("Microsoft Visual Studio"))).flat_map(|y| subdirs(&y)).any(|e| e.join("VC/Tools/MSVC").is_dir()) {
        return true;
    }
    // A system clang can have the wrong version or sysroot. Look inside the selected Linux engine.
    let Some(unreal) = unreal.filter(|i| i.program.ends_with("Engine/Binaries/Linux/UnrealEditor")) else { return false };
    let Some(root) = unreal.program.ancestors().nth(4) else { return false };
    subdirs(&root.join("Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64")).iter().any(|sdk| sdk.join("x86_64-unknown-linux-gnu/bin/clang++").is_file())
}

// ---- getting one ---------------------------------------------------------------------------------

/// The Godot release Craft Anything downloads.
pub const GODOT_VERSION: &str = "4.4.1-stable";
/// Largest file unpacked from Godot's download: the macOS app's universal program is over the
/// 256 MB other engines' files are held to (#100). The download is checked against Godot's own
/// SHA-512 list first.
const GODOT_MAX_FILE: u64 = 1 << 30;

/// The official page to get `b` by hand (used where we can't download it for the person).
pub fn download_page(b: Builder) -> &'static str {
    match b {
        Builder::Unity => "https://unity.com/download",
        Builder::Unreal => "https://www.unrealengine.com/download",
        Builder::Godot => "https://godotengine.org/download",
        Builder::Rust => "https://rustup.rs",
    }
}

/// Visual Studio (Community is free); Unreal needs its "Game development with C++" workload.
pub const VISUAL_STUDIO_PAGE: &str = "https://visualstudio.microsoft.com/downloads/";

/// A vendor installer we can download for the person on this OS: (url, file name, the
/// organisation that must have signed it).
pub fn installer(b: Builder) -> Option<(&'static str, &'static str, &'static str)> {
    if !cfg!(windows) {
        return None;
    }
    match b {
        Builder::Unity => Some(("https://public-cdn.cloud.unity3d.com/hub/prod/UnityHubSetup.exe", "UnityHubSetup.exe", "Unity Technologies")),
        Builder::Unreal => Some((
            "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi",
            "EpicGamesLauncherInstaller.msi",
            "Epic Games",
        )),
        _ => None,
    }
}

/// Download the vendor's installer into `dir` and check who signed it. Returns the file.
pub fn download_installer(b: Builder, dir: &Path, cancel: Option<Cancel>, progress: &dyn Fn(u64, Option<u64>)) -> Result<PathBuf, ToolError> {
    let (url, name, org) = installer(b).ok_or_else(|| ToolError::new(ErrorCode::NotSupported, format!("{} can't be downloaded for you here.", b.name())))?;
    std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    let dest = dir.join(name);
    crate::install::download_file(url, &dest, 2 << 30, cancel.as_ref(), progress)?;
    if let Err(e) = verify_publisher(&dest, org) {
        let _ = std::fs::remove_file(&dest);
        return Err(e);
    }
    Ok(dest)
}

/// Open a downloaded installer (its own window takes over: licence, location, sign-in).
pub fn run_installer(path: &Path) -> Result<(), ToolError> {
    let is_msi = path.extension().is_some_and(|e| e.eq_ignore_ascii_case("msi"));
    // It runs as long as the person needs (licence, location, sign-in), so no deadline: launched,
    // not supervised.
    let launch = if is_msi { Launch::new("msiexec").arg("/i").arg(path) } else { Launch::new(path) };
    launch.label("the installer").remediation("Open the downloaded installer by hand, or get it from the official website.").start().map(|_| ())
}

/// Windows: the file carries a valid Authenticode signature from `org`. Elsewhere this can't be
/// checked, so it refuses (the person gets the vendor's page instead).
pub fn verify_publisher(path: &Path, org: &str) -> Result<(), ToolError> {
    if !cfg!(windows) {
        return Err(ToolError::new(ErrorCode::NotSupported, "Installer signatures can only be checked on Windows."));
    }
    // The path goes in through the environment, never into the script text.
    let script = "$s = Get-AuthenticodeSignature -LiteralPath $env:CA_FILE; \
                  [Console]::Out.Write(([string]$s.Status) + '|' + $s.SignerCertificate.Subject)";
    // Usually a second or two; checking the certificate's revocation online can take longer.
    let out = Process::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .env("CA_FILE", path)
        .timeout(std::time::Duration::from_secs(90))
        .stdout_cap(64 * 1024)
        .label("the installer signature check")
        .remediation("Windows PowerShell is needed to check the installer's signature; get the installer from the official website instead.")
        .run()?;
    let text = out.stdout_text();
    let (status, subject) = text.split_once('|').unwrap_or((text.as_ref(), ""));
    if status.trim() == "Valid" && subject.contains(org) {
        Ok(())
    } else {
        Err(ToolError::new(ErrorCode::FileHashMismatch, format!("The download isn't signed by {org}, so it wasn't opened."))
            .with_remediation("Get it from the official website instead.")
            .with_details(serde_json::json!({"status": status.trim(), "signer": subject.trim()})))
    }
}

/// Godot's release files for this OS: (zip name, the program inside it).
fn godot_asset() -> Option<(String, String)> {
    let v = GODOT_VERSION;
    match std::env::consts::OS {
        "windows" => Some((format!("Godot_v{v}_win64.exe.zip"), format!("Godot_v{v}_win64.exe"))),
        "macos" => Some((format!("Godot_v{v}_macos.universal.zip"), "Godot.app".into())),
        "linux" => Some((format!("Godot_v{v}_linux.x86_64.zip"), format!("Godot_v{v}_linux.x86_64"))),
        _ => None,
    }
}

/// Download Godot into the engine store, checked against the release's official SHA-512 list.
/// Returns the editor program.
pub fn install_godot(store: &Path, cancel: Option<Cancel>, progress: &dyn Fn(u64, Option<u64>)) -> Result<PathBuf, ToolError> {
    use sha2::{Digest, Sha512};
    let (zip, program) = godot_asset().ok_or_else(|| ToolError::new(ErrorCode::NotSupported, "Godot can't be downloaded for this computer."))?;
    let base = format!("https://github.com/godotengine/godot/releases/download/{GODOT_VERSION}");
    // shortcut: the checksum list comes from the same release over HTTPS, which catches broken or
    // swapped downloads but not a compromised release; pin the hash here to go further.
    let mut sums = Vec::new();
    crate::install::download_to(&format!("{base}/SHA512-SUMS.txt"), &mut sums, 1 << 20, cancel.as_ref(), &|_, _| {})?;
    let sums = String::from_utf8_lossy(&sums);
    let expected = sums
        .lines()
        .find_map(|l| l.split_once(char::is_whitespace).filter(|(_, f)| f.trim().trim_start_matches('*') == zip).map(|(h, _)| h.to_ascii_lowercase()))
        .ok_or_else(|| ToolError::new(ErrorCode::FileHashMismatch, "Godot's checksum list doesn't mention this download."))?;
    let dir = store.join("godot");
    std::fs::create_dir_all(&dir).map_err(|e| ToolError::io(dir.display(), e))?;
    let tmp = dir.join(format!(".{zip}.part"));
    crate::install::download_file(&format!("{base}/{zip}"), &tmp, 512 << 20, cancel.as_ref(), progress)?;
    let data = std::fs::read(&tmp).map_err(|e| ToolError::io(tmp.display(), e))?;
    let _ = std::fs::remove_file(&tmp);
    if hex::encode(Sha512::digest(&data)) != expected {
        return Err(ToolError::new(ErrorCode::FileHashMismatch, "The Godot download didn't match its official checksum, so it wasn't used.")
            .with_remediation("Try again, or get Godot from godotengine.org."));
    }
    crate::install::unpack_zip_into(&data, &dir, GODOT_MAX_FILE, cancel.as_ref())?;
    let mut path = dir.join(&program);
    if program == "Godot.app" && path.exists() {
        path = name_macos_godot(&dir)?;
    }
    if !path.exists() {
        return Err(ToolError::new(ErrorCode::GarbledOutput, "Godot was unpacked, but its program wasn't where we expected."));
    }
    Ok(if program.ends_with(".app") { path.join("Contents/MacOS/Godot") } else { path })
}

/// The macOS zip unpacks as `Godot.app`; the store finds editors by their `Godot_v<version>` name,
/// so rename it to that. Returns the new path.
fn name_macos_godot(dir: &Path) -> Result<PathBuf, ToolError> {
    let from = dir.join("Godot.app");
    let to = dir.join(format!("Godot_v{GODOT_VERSION}.app"));
    // A reinstall finds the copy from the last install here, and rename can't replace a folder
    // that isn't empty. Move the old copy aside (hidden, so the store ignores it) and put it back
    // if the new one can't be moved in, so a failed reinstall keeps the working editor.
    let backup = dir.join(format!(".Godot_v{GODOT_VERSION}.app.previous"));
    // An archive that unpacks a `Godot.app` without the editor inside must not displace a working
    // install, so check before anything is moved.
    let exe = from.join("Contents/MacOS/Godot");
    if !exe.is_file() {
        let missing = std::io::Error::new(std::io::ErrorKind::NotFound, "the unpacked Godot.app has no editor executable");
        return Err(ToolError::io(exe.display(), missing));
    }
    // An interrupted reinstall can leave only the hidden backup behind; bring it back first so it
    // is treated as the previous install instead of staying unavailable.
    let mut had_previous = to.exists();
    if !had_previous && backup.exists() {
        std::fs::rename(&backup, &to).map_err(|e| ToolError::io(backup.display(), e))?;
        had_previous = true;
    }
    if had_previous {
        match std::fs::remove_dir_all(&backup) {
            Ok(()) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(ToolError::io(backup.display(), e)),
        }
        std::fs::rename(&to, &backup).map_err(|e| ToolError::io(to.display(), e))?;
    }
    if let Err(e) = std::fs::rename(&from, &to) {
        if had_previous {
            let _ = std::fs::rename(&backup, &to);
        }
        return Err(ToolError::io(from.display(), e));
    }
    if had_previous {
        let _ = std::fs::remove_dir_all(&backup);
    }
    Ok(to)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn touch(root: &Path, rel: &str, bytes: &[u8]) {
        let p = root.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, bytes).unwrap();
    }

    #[test]
    fn a_unity_games_stack_comes_from_its_assembly_names() {
        let d = tempfile::tempdir().unwrap();
        let g = d.path();
        touch(g, "Game.exe", b"MZ");
        touch(g, "GameAssembly.dll", &[0; 100]);
        touch(g, "Game_Data/globalgamemanagers", b"\0\0\0\0\x16\0\x002022.3.62f2\0\0junk");
        touch(g, "Game_Data/level0", b"x");
        touch(g, "Game_Data/level1", b"x");
        touch(g, "Game_Data/level1.resS", b"x");
        let names = [
            "Assembly-CSharp.dll",
            "Game.Core.dll",
            "Game.Core.Systems.dll",
            "Unity.RenderPipelines.Universal.Runtime.dll",
            "Unity.RenderPipelines.Universal.Shaders.dll",
            "FishNet.Runtime.dll",
            "Unity.Mathematics.dll",
            "UnityEngine.CoreModule.dll",
            "System.Core.dll",
            "Mirrorball.dll",
        ];
        touch(g, "Game_Data/ScriptingAssemblies.json", serde_json::json!({"names": names, "types": [16]}).to_string().as_bytes());
        let p = profile(g);
        assert_eq!(p.found.as_ref().map(Found::label).as_deref(), Some("Unity 2022.3.62f2"));
        assert_eq!(p.stack.iter().map(|s| s.name.as_str()).collect::<Vec<_>>(), ["URP", "FishNet"], "one entry per library");
        assert_eq!(p.other_code, ["Assembly-CSharp", "Game.Core", "Game.Core.Systems", "Mirrorball"], "a name only starting like a library isn't it");
        assert_eq!(p.other_groups, ["Assembly-CSharp", "Game (2)", "Mirrorball"]);
        assert_eq!((p.scenes, p.files, p.capped), (2, 7, false));
        assert_eq!(p.code_list.as_deref().map(|c| c.replace('\\', "/")).as_deref(), Some("Game_Data/ScriptingAssemblies.json"));
        let s = p.summary("Game").unwrap();
        assert!(
            s.contains("Unity 2022.3.62f2") && s.contains("IL2CPP") && s.contains("URP (rendering), FishNet (multiplayer)") && s.contains("2 scene files"),
            "{s}"
        );
        // Without the list, the Managed folder's assemblies are read.
        std::fs::remove_file(g.join("Game_Data/ScriptingAssemblies.json")).unwrap();
        touch(g, "Game_Data/Managed/DOTween.dll", b"MZ");
        assert_eq!(profile(g).stack.iter().map(|s| s.name.as_str()).collect::<Vec<_>>(), ["DOTween"]);
        // A folder that isn't a game has no summary, and nothing breaks on an empty one.
        let empty = tempfile::tempdir().unwrap();
        assert_eq!(profile(empty.path()).summary("x"), None);
    }

    #[test]
    fn detects_engines_from_their_files() {
        let d = tempfile::tempdir().unwrap();
        let unity = d.path().join("unity");
        touch(&unity, "Game.exe", b"MZ");
        touch(&unity, "UnityPlayer.dll", b"MZ");
        touch(&unity, "Game_Data/globalgamemanagers", b"\0\0\0\0\x16\0\x002021.3.16f1\0\0junk");
        touch(&unity, "Game_Data/Managed/Assembly-CSharp.dll", b"MZ");
        let f = detect(&unity).unwrap();
        assert_eq!((f.engine, f.version.as_deref()), (Made::Unity, Some("2021.3.16f1")));
        assert!(f.note.unwrap().contains("Assembly-CSharp"));
        assert_eq!(Builder::for_game(Some(f.engine)), Builder::Unity);

        let ue = d.path().join("ue");
        touch(&ue, "Shooter/Content/Paks/Shooter-WindowsNoEditor.pak", b"x");
        let mut exe = b"MZ....".to_vec();
        exe.extend(utf16("++UE5+Release-5.3"));
        exe.extend([0, 0]);
        touch(&ue, "Shooter/Binaries/Win64/Shooter-Win64-Shipping.exe", &exe);
        let f = detect(&ue).unwrap();
        assert_eq!((f.engine, f.version.as_deref()), (Made::Unreal, Some("5.3")));
        assert_eq!(Builder::for_game(Some(f.engine)), Builder::Unreal);

        let gd = d.path().join("godot");
        let mut pck = b"GDPC".to_vec();
        for n in [2u32, 4, 2, 1] {
            pck.extend(n.to_le_bytes());
        }
        let mut exe = b"MZ program bytes".to_vec();
        let size = pck.len() as u64;
        exe.extend(&pck);
        exe.extend(size.to_le_bytes());
        exe.extend(b"GDPC");
        touch(&gd, "game.exe", &exe);
        let f = detect(&gd).unwrap();
        assert_eq!((f.engine, f.version.as_deref()), (Made::Godot, Some("4.2.1")));

        let cube = d.path().join("cube");
        touch(&cube, "packages/maps/official/dust.cgz", b"x");
        let f = detect(&cube).unwrap();
        assert_eq!(f.engine, Made::Cube);
        assert_eq!(Builder::for_game(Some(f.engine)), Builder::Unity, "engines we can't build with default to Unity");

        assert!(detect(&d.path().join("missing")).is_none());
    }

    #[test]
    fn unity_version_tokens() {
        assert_eq!(unity_version(b"xx 6000.0.23f1 yy").as_deref(), Some("6000.0.23f1"));
        assert_eq!(unity_version(b"5.6.7f1").as_deref(), Some("5.6.7f1"));
        assert!(unity_version(b"1.2.3 and 2021.3").is_none());
    }

    #[test]
    fn finds_installed_engines() {
        let d = tempfile::tempdir().unwrap();
        let pf = d.path().join("pf");
        touch(&pf, "Unity/Hub/Editor/2022.3.10f1/Editor/Unity.exe", b"");
        touch(&pf, "Unity/Hub/Editor/6000.0.23f1/Editor/Unity.exe", b"");
        touch(&pf, "Unity Hub/Unity Hub.exe", b"");
        touch(&pf, "Epic Games/UE_5.4/Engine/Binaries/Win64/UnrealEditor.exe", b"");
        let store = d.path().join("store");
        touch(&store, "godot/Godot_v4.4.1-stable_win64.exe", b"");
        touch(&store, "godot/Godot_v4.4.1-stable_win64_console.exe", b"");
        let p = Places { program_files: vec![pf.clone()], store, ..Default::default() };
        let inv = inventory(&p);
        assert_eq!(inv.best(Builder::Unity).unwrap().version, "6000.0.23f1", "newest first");
        assert_eq!(inv.engines.iter().filter(|i| i.builder == Builder::Unity).count(), 2);
        assert_eq!(inv.best(Builder::Godot).unwrap().version, "4.4.1");
        assert_eq!(inv.engines.iter().filter(|i| i.builder == Builder::Godot).count(), 1, "the console helper isn't the editor");
        assert_eq!(inv.best(Builder::Unreal).unwrap().version, "5.4");
        assert!(inv.unity_hub.is_some() && inv.epic_launcher.is_none());
        assert!(!inv.ready(Builder::Unreal), "Unreal also needs C++ tools");
        touch(&pf, "Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.40/x", b"");
        assert!(inventory(&p).ready(Builder::Unreal));
        assert!(!inv.ready(Builder::Rust), "PATH isn't searched here");
    }

    #[test]
    fn linux_unreal_registry_finds_an_install_outside_the_launcher_folders() {
        let d = tempfile::tempdir().unwrap();
        let home = d.path().join("home");
        let root = d.path().join("custom engine = 5");
        touch(&root, "Engine/Binaries/Linux/UnrealEditor", b"");
        touch(&root, "Engine/Build/Build.version", br#"{"MajorVersion":5,"MinorVersion":8,"PatchVersion":4}"#);
        let ignored = d.path().join("ignored-engine");
        touch(&ignored, "Engine/Binaries/Linux/UnrealEditor", b"");
        touch(
            &home,
            ".config/Epic/UnrealEngine/Install.ini",
            format!(
                "\u{feff}[Installations]\r\n; Registered by UnrealVersionSelector\r\nengine={}\r\nstale={}\r\nrelative=relative/engine\r\nempty=\r\n[Other]\r\nignored={}\r\n",
                root.display(), d.path().join("missing-engine").display(), ignored.display()
            )
            .as_bytes(),
        );

        let inv = inventory(&Places { home: Some(home), ..Default::default() });
        let installed = inv.best(Builder::Unreal).expect("the registered Linux editor must be found");
        assert_eq!(installed.program, root.join("Engine/Binaries/Linux/UnrealEditor"));
        assert_eq!(installed.version, "5.8.4", "the engine build file supplies the version, not its directory name");
        assert_eq!(inv.engines.iter().filter(|i| i.builder == Builder::Unreal).count(), 1);
        assert!(!inv.ready(Builder::Unreal), "an editor alone does not prove its C++ toolchain is installed");
    }

    #[test]
    fn linux_unreal_is_ready_with_its_bundled_clang() {
        let d = tempfile::tempdir().unwrap();
        let home = d.path().join("home");
        let root = d.path().join("UE_5.8");
        touch(&root, "Engine/Binaries/Linux/UnrealEditor", b"");
        touch(&home, ".config/Epic/UnrealEngine/Install.ini", format!("[Installations]\nengine={}\n", root.display()).as_bytes());
        // An unrelated compiler is not evidence that Unreal's own toolchain is present.
        touch(&home, "bin/clang++", b"");
        let places = Places { home: Some(home), ..Default::default() };
        assert!(!inventory(&places).ready(Builder::Unreal));

        touch(&root, "Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++", b"");
        let inv = inventory(&places);
        assert!(inv.cpp_tools, "the compiler shipped with this Unreal install must be recognized");
        assert!(inv.ready(Builder::Unreal));
    }

    #[test]
    fn linux_unreal_explicit_root_selects_that_install() {
        let d = tempfile::tempdir().unwrap();
        let home = d.path().join("home");
        let root = d.path().join("UE_5.8");
        let other = d.path().join("UE_6.0");
        touch(&root, "Engine/Binaries/Linux/UnrealEditor", b"");
        touch(&other, "Engine/Binaries/Linux/UnrealEditor", b"");
        touch(&home, ".config/Epic/UnrealEngine/Install.ini", format!("[Installations]\nengine={}\n", other.display()).as_bytes());
        let mut places = Places { home: Some(home), unreal_root: Some(root.clone()), ..Default::default() };

        let inv = inventory(&places);
        assert_eq!(inv.best(Builder::Unreal).unwrap().program, root.join("Engine/Binaries/Linux/UnrealEditor"));
        assert_eq!(inv.engines.iter().filter(|i| i.builder == Builder::Unreal).count(), 1);
        places.unreal_root = Some(d.path().join("missing"));
        assert_eq!(inventory(&places).best(Builder::Unreal).unwrap().program, other.join("Engine/Binaries/Linux/UnrealEditor"));
    }

    #[test]
    fn linux_unreal_does_not_borrow_another_installs_compiler() {
        let d = tempfile::tempdir().unwrap();
        let home = d.path().join("home");
        let older = d.path().join("UE_5.7");
        let newer = d.path().join("UE_5.8");
        for root in [&older, &newer] {
            touch(root, "Engine/Binaries/Linux/UnrealEditor", b"");
        }
        touch(
            &home,
            ".config/Epic/UnrealEngine/Install.ini",
            format!("[Installations]\nolder={}\nnewer={}\nduplicate={}\n", older.display(), newer.display(), older.display()).as_bytes(),
        );
        touch(&older, "Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v25_clang-18.1.0-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++", b"");

        let inv = inventory(&Places { home: Some(home), ..Default::default() });
        assert_eq!(inv.best(Builder::Unreal).unwrap().program, newer.join("Engine/Binaries/Linux/UnrealEditor"));
        assert_eq!(inv.engines.iter().filter(|i| i.builder == Builder::Unreal).count(), 2);
        assert!(!inv.cpp_tools, "an older engine's compiler cannot establish readiness for the selected engine");
        assert!(!inv.ready(Builder::Unreal));
    }

    #[test]
    fn unpacked_macos_godot_is_found_in_the_store() {
        let d = tempfile::tempdir().unwrap();
        let store = d.path().join("store");
        touch(&store.join("godot"), "Godot.app/Contents/MacOS/Godot", b"");
        let renamed = name_macos_godot(&store.join("godot")).unwrap();
        assert!(renamed.ends_with(format!("Godot_v{GODOT_VERSION}.app")));
        let inv = inventory(&Places { store: store.clone(), ..Default::default() });
        let godot = inv.best(Builder::Godot).expect("an unpacked Godot.app must be found");
        assert_eq!(godot.version, "4.4.1");
        assert!(godot.program.ends_with("Contents/MacOS/Godot"));

        // A reinstall unpacks a new Godot.app over the one from the first install.
        touch(&store.join("godot"), "Godot.app/Contents/MacOS/Godot", b"new");
        touch(&store.join("godot"), &format!("Godot_v{GODOT_VERSION}.app/stale.txt"), b"old");
        let again = name_macos_godot(&store.join("godot")).expect("a second install must not fail on the first copy");
        assert!(!again.join("stale.txt").exists(), "the old copy is replaced");
        assert_eq!(std::fs::read(again.join("Contents/MacOS/Godot")).unwrap(), b"new");
    }

    #[test]
    fn failed_macos_reinstall_keeps_the_working_editor() {
        let d = tempfile::tempdir().unwrap();
        let dir = d.path().join("godot");
        // The previous install is there, but the new download did not unpack a Godot.app.
        touch(&dir, &format!("Godot_v{GODOT_VERSION}.app/stale.txt"), b"old");
        assert!(name_macos_godot(&dir).is_err(), "no Godot.app to move in");
        assert_eq!(std::fs::read(dir.join(format!("Godot_v{GODOT_VERSION}.app/stale.txt"))).unwrap(), b"old", "the working install is put back");
        assert!(!dir.join(format!(".Godot_v{GODOT_VERSION}.app.previous")).exists());

        // A Godot.app without the editor inside is just as unusable and must not replace it either.
        touch(&dir, "Godot.app/Contents/Info.plist", b"");
        assert!(name_macos_godot(&dir).is_err(), "no editor executable in the new app");
        assert!(dir.join(format!("Godot_v{GODOT_VERSION}.app/stale.txt")).exists());
        assert!(dir.join("Godot.app").exists(), "the download is left as it was");
    }

    #[test]
    fn an_orphaned_macos_backup_is_recovered_before_a_failed_reinstall() {
        let d = tempfile::tempdir().unwrap();
        let dir = d.path().join("godot");
        // A past reinstall was interrupted after the old copy was moved aside.
        touch(&dir, &format!(".Godot_v{GODOT_VERSION}.app.previous/stale.txt"), b"old");
        touch(&dir, "Godot.app/Contents/MacOS/Godot", b"new");
        let installed = name_macos_godot(&dir).unwrap();
        assert_eq!(std::fs::read(installed.join("Contents/MacOS/Godot")).unwrap(), b"new");
        assert!(!dir.join(format!(".Godot_v{GODOT_VERSION}.app.previous")).exists());

        // An archive without the editor is refused before anything, the backup included, is moved.
        let d = tempfile::tempdir().unwrap();
        let dir = d.path().join("godot");
        touch(&dir, &format!(".Godot_v{GODOT_VERSION}.app.previous/stale.txt"), b"old");
        touch(&dir, "Godot.app/Contents/Info.plist", b"");
        assert!(name_macos_godot(&dir).is_err());
        assert!(dir.join(format!(".Godot_v{GODOT_VERSION}.app.previous/stale.txt")).exists(), "an invalid archive leaves the backup alone");
    }

    #[test]
    fn stacks_round_trip() {
        for b in Builder::ALL {
            assert_eq!(Builder::from_stack(b.stack()), Some(b));
        }
    }
}
