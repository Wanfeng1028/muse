//! What an installed app of unknown make is built on, read from its folder: a bounded walk that
//! follows no links, runs nothing and writes nothing. It reads the ends of files a marker needs a
//! look at, and searches the start of a few main programs (Tauri leaves no file of its own). Each
//! runtime is one row of [`RUNTIMES`]; add one by adding a row.
//!
//! Games are recognised by the same code as `core_target_triage`
//! (`craft_anything_engines::game::detect_in`), over this tool's own no-links walk.

use super::native_common::{params_json, spec};
use super::static_input::{builder, partial};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::game;
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Location, Subject, ToolError};
use craft_anything_formats::{godot_pck, pe_is_managed, plist, unreal_iostore, unreal_pak};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, VecDeque};
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

const DEFAULT_ENTRIES: usize = 20_000;
const MAX_ENTRIES: usize = 200_000;
const DEFAULT_DEPTH: usize = 10;
const MAX_DEPTH: usize = 32;
/// Bytes read from each end of a file a marker asks to look inside.
const PROBE_READ: usize = 4096;
/// Files looked inside, at most, and bytes read in all (the text search reads more than a probe).
const MAX_PROBES: usize = 4000;
const MAX_PROBE_BYTES: u64 = 512 << 20;
/// How much of a program its text is searched in, and how many programs are searched.
const TEXT_WINDOW: u64 = 64 << 20;
const MAX_TEXT_SEARCHES: usize = 4;
/// A program this close to the top of the folder counts as a main program.
const MAIN_DEPTH: usize = 3;
/// A runtime whose nearest medium or strong evidence is deeper than this is carried along (a plug-in's
/// or a tool's own), not what the app itself is built on.
const LEAD_DEPTH: usize = 3;
/// Paths given for one marker, next steps in all, and how large a settings file may be to read for
/// an app's name.
const PATHS_SHOWN: usize = 5;
const MAX_NEXT_STEPS: usize = 12;
const MAX_PLIST: u64 = 1 << 20;
/// Folders of many small files whose insides say nothing more: they count as found, not walked.
const NOT_WALKED: [&str; 2] = ["node_modules", ".git"];

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "app_folder_explain",
        "Work out what an installed app is built on",
        "Survey an installed app's folder (absolute path; a macOS .app or its Contents, a Windows or Linux install folder) when you don't know what it is. Walks the folder within max_entries and max_depth, following no links, running nothing and writing nothing, and reads only the first and last 4 KiB of the files that need a look, plus a search of up to 64 MiB of up to 4 main programs for Tauri's own text, to name the runtimes it may be built on: Electron, Tauri, CEF, Qt, Flutter, .NET, Java, Python (with PyInstaller), Node, Unity, Unreal, Godot, other game engines, or plain native code. Each candidate has a strength and the files that support it, and next_steps says which tool to run on which file. These are inferences: a file being there doesn't prove the app runs it.",
        "Point at an installed app and find out what it was made with, and what to look at next.",
        Toolset::Formats,
        Effects::EVIDENCE | Effects::CARRIES_TARGET_CONTENT,
        Requires::Nothing,
        schema_of::<SurveyParams>,
        app_folder_explain,
    )]
}

fn default_entries() -> usize {
    DEFAULT_ENTRIES
}

fn default_depth() -> usize {
    DEFAULT_DEPTH
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SurveyParams {
    /// Absolute path of the installed app's folder.
    pub path: String,
    /// Most files and folders to look at (up to 200000).
    #[serde(default = "default_entries")]
    pub max_entries: usize,
    /// How many folders deep to look (up to 32).
    #[serde(default = "default_depth")]
    pub max_depth: usize,
}

// ---- the table ---------------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize)]
#[serde(rename_all = "snake_case")]
enum Weight {
    /// Could be many things; supporting evidence only.
    Weak,
    /// Usual for this runtime, but others have it too.
    Medium,
    /// Hard to explain any other way.
    Strong,
}

/// A test on a file or folder's place. Text is lower case; the entry's path is lowered to match.
#[derive(Debug, Clone, Copy)]
enum At {
    Name(&'static str),
    NameStarts(&'static str),
    NameEnds(&'static str),
    /// Anywhere in the relative path, which starts with `/` here so a whole first part can match.
    PathHas(&'static str),
    PathEnds(&'static str),
    /// A file a system would start: it's executable, in a macOS `MacOS` folder, or a `.exe`.
    Program,
    /// A [`Self::Program`] within [`MAIN_DEPTH`] of the top.
    MainProgram,
}

/// A look inside a file, for a marker whose place alone isn't enough.
type Look = fn(&mut Probe) -> bool;

/// One thing that gives a runtime away. An entry must pass every `at`, and `look` when there is one.
#[derive(Debug, Clone, Copy)]
struct Marker {
    id: &'static str,
    at: &'static [At],
    look: Option<Look>,
    weight: Weight,
    /// What finding it means, in plain words.
    means: &'static str,
}

/// A tool to run next. `on` is the id of a marker in the same row, whose first file it runs on, or
/// `None` for the whole folder; `param` is the name the tool gives the path.
#[derive(Debug, Clone, Copy)]
struct Next {
    tool: &'static str,
    param: &'static str,
    on: Option<&'static str>,
    why: &'static str,
}

/// One runtime an app may be built on.
#[derive(Debug)]
struct Runtime {
    id: &'static str,
    title: &'static str,
    /// The game engine `game::detect_in` must report for this runtime to gain a marker from it.
    engine: Option<game::Made>,
    /// Runtimes this one is normally part of (their ids, or [`ANY_OTHER`]). When one of them is
    /// also found, this one is expected, so it doesn't lead the answer.
    beneath: &'static [&'static str],
    markers: &'static [Marker],
    next: &'static [Next],
}

/// The row for plain native code, which the answer falls back on.
const NATIVE: &str = "native";
/// In [`Runtime::beneath`]: any other runtime found at all.
const ANY_OTHER: &str = "*";

const fn mark(id: &'static str, at: &'static [At], weight: Weight, means: &'static str) -> Marker {
    Marker { id, at, look: None, weight, means }
}

const fn look(id: &'static str, at: &'static [At], look: Look, weight: Weight, means: &'static str) -> Marker {
    Marker { id, at, look: Some(look), weight, means }
}

const fn next(tool: &'static str, on: &'static str, why: &'static str) -> Next {
    Next { tool, param: "path", on: Some(on), why }
}

const fn folder(tool: &'static str, why: &'static str) -> Next {
    Next { tool, param: "path", on: None, why }
}

use At::{MainProgram, Name, NameEnds, NameStarts, PathEnds, PathHas, Program};
use Weight::{Medium, Strong, Weak};

/// Every runtime looked for. Add one with a row here; no other code changes.
static RUNTIMES: &[Runtime] = &[
    Runtime {
        id: "electron",
        title: "Electron (a web app in a desktop shell)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("app_asar", &[PathEnds("/resources/app.asar")], Strong, "the packed web app Electron loads"),
            mark("default_app", &[PathEnds("/resources/default_app.asar")], Strong, "Electron's built-in starter app"),
            mark("framework_binary", &[PathEnds("electron framework.framework/versions/a/electron framework")], Strong, "Electron's own engine on macOS"),
            mark("framework", &[PathEnds("electron framework.framework")], Strong, "Electron's own engine on macOS"),
            mark("unpacked_app", &[PathEnds("/resources/app")], Medium, "where an Electron app sits when left unpacked"),
            mark("asar", &[NameEnds(".asar")], Medium, "a packed web app in Electron's archive format"),
            mark("electron_program", &[Name("electron.exe")], Strong, "the stock Electron program"),
        ],
        next: &[
            Next { tool: "js_app_map", param: "input_path", on: Some("app_asar"), why: "map the app's JavaScript, IPC and routes" },
            Next { tool: "js_app_map", param: "input_path", on: Some("unpacked_app"), why: "map the app's JavaScript, IPC and routes" },
            next("core_archive_show", "app_asar", "list what's in the packed app"),
            next("js_electron_fuses_show", "framework_binary", "see which of Electron's safety switches are set"),
            next("js_electron_fuses_show", "electron_program", "see which of Electron's safety switches are set"),
        ],
    },
    Runtime {
        id: "tauri",
        title: "Tauri (a web app in a small Rust program)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("config", &[Name("tauri.conf.json")], Strong, "Tauri's settings file"),
            look("program_text", &[MainProgram], has_tauri_text, Strong, "the main program carries Tauri's own text"),
        ],
        next: &[
            next("native_rust_binary_show", "program_text", "which Rust toolchain and crates built it"),
            next("core_target_triage", "program_text", "what the main program is"),
        ],
    },
    Runtime {
        id: "cef",
        title: "CEF (Chromium embedded in a native app)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("framework", &[PathEnds("chromium embedded framework.framework")], Strong, "Chromium Embedded on macOS"),
            mark(
                "framework_binary",
                &[PathEnds("chromium embedded framework.framework/versions/a/chromium embedded framework")],
                Strong,
                "Chromium Embedded on macOS",
            ),
            mark("library", &[NameStarts("libcef.")], Strong, "Chromium Embedded on Windows or Linux"),
        ],
        next: &[
            next("core_target_triage", "library", "what its library exports and imports"),
            next("core_target_triage", "framework_binary", "what its library exports and imports"),
        ],
    },
    Runtime {
        id: "qt",
        title: "Qt (a native C++ interface toolkit)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("framework", &[PathEnds("qtcore.framework")], Strong, "Qt's core library on macOS"),
            mark("framework_binary", &[PathEnds("qtcore.framework/versions/a/qtcore")], Strong, "Qt's core library on macOS"),
            mark("library_5", &[NameStarts("qt5core")], Strong, "Qt 5's core library"),
            mark("library_6", &[NameStarts("qt6core")], Strong, "Qt 6's core library"),
            mark("library_so_5", &[NameStarts("libqt5core")], Strong, "Qt 5's core library"),
            mark("library_so_6", &[NameStarts("libqt6core")], Strong, "Qt 6's core library"),
            mark("platform_plugin", &[PathHas("/platforms/"), NameStarts("q")], Weak, "a file where Qt keeps its platform plugins"),
            mark("platform_plugin_lib", &[PathHas("/platforms/"), NameStarts("libq")], Medium, "a file where Qt keeps its platform plugins"),
            mark("conf", &[Name("qt.conf")], Medium, "Qt's settings file"),
        ],
        next: &[
            next("core_target_triage", "library_6", "what its Qt library is"),
            next("core_target_triage", "library_5", "what its Qt library is"),
            next("core_target_triage", "framework_binary", "what its Qt library is"),
        ],
    },
    Runtime {
        id: "flutter",
        title: "Flutter (a Dart app with its own renderer)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("macos", &[PathEnds("fluttermacos.framework")], Strong, "Flutter's engine on macOS"),
            mark("windows", &[Name("flutter_windows.dll")], Strong, "Flutter's engine on Windows"),
            mark("linux", &[Name("libflutter_linux_gtk.so")], Strong, "Flutter's engine on Linux"),
            mark("android", &[Name("libflutter.so")], Strong, "Flutter's engine"),
            mark("assets", &[PathEnds("/flutter_assets")], Strong, "the assets folder of a Flutter app"),
            mark("app_library", &[Name("libapp.so")], Medium, "where Flutter keeps compiled Dart code"),
        ],
        next: &[
            next("core_target_triage", "app_library", "what its compiled Dart library is"),
            next("core_archive_show", "assets", "list what's in its assets folder"),
        ],
    },
    Runtime {
        id: "dotnet",
        title: ".NET (C# and similar languages)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("runtime_config", &[NameEnds(".runtimeconfig.json")], Strong, "settings for starting a .NET program"),
            mark("dependencies", &[NameEnds(".deps.json")], Medium, "a .NET program's list of dependencies"),
            mark("host", &[NameStarts("hostfxr")], Strong, ".NET's starting library"),
            mark("host_so", &[NameStarts("libhostfxr")], Strong, ".NET's starting library"),
            mark("core_clr", &[Name("coreclr.dll")], Strong, ".NET's runtime"),
            mark("core_clr_so", &[NameStarts("libcoreclr")], Strong, ".NET's runtime"),
            look("assembly_dll", &[NameEnds(".dll")], is_managed_pe, Strong, "a file whose PE header declares .NET code"),
            look("assembly_exe", &[NameEnds(".exe")], is_managed_pe, Strong, "a file whose PE header declares .NET code"),
        ],
        next: &[
            next("managed_assembly_show", "assembly_exe", "what .NET it targets and what it depends on"),
            next("managed_assembly_show", "assembly_dll", "what .NET it targets and what it depends on"),
        ],
    },
    Runtime {
        id: "java",
        title: "Java (or another language on the JVM)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("jar", &[NameEnds(".jar")], Medium, "a Java archive"),
            mark("jvm", &[Name("jvm.dll")], Strong, "the Java virtual machine"),
            mark("jvm_so", &[NameStarts("libjvm.")], Strong, "the Java virtual machine"),
            mark("launcher", &[NameStarts("libjli.")], Strong, "Java's launcher library"),
            look("jre_modules", &[PathEnds("/lib/modules")], is_java_image, Strong, "a bundled Java's module image, checked by its start"),
            mark("java_program", &[Name("java.exe")], Strong, "the Java program"),
            mark("java_binary", &[PathEnds("/bin/java")], Strong, "the Java program"),
        ],
        next: &[next("java_archive_show", "jar", "its main class, packages and what it bundles")],
    },
    Runtime {
        id: "python",
        title: "Python (bundled with its interpreter)",
        engine: None,
        beneath: &[],
        markers: &[
            mark("base_library", &[Name("base_library.zip")], Strong, "the standard library PyInstaller packs"),
            look("pyinstaller_program", &[Program], has_pyinstaller_cookie, Strong, "a program ending in PyInstaller's mark"),
            mark("archive", &[NameEnds(".pyz")], Strong, "a packed Python app"),
            mark("framework", &[PathEnds("python.framework")], Strong, "Python on macOS"),
            mark("library", &[NameStarts("libpython")], Strong, "Python's interpreter library"),
            mark("library_dll", &[NameStarts("python3"), NameEnds(".dll")], Strong, "Python's interpreter library"),
            mark("standard_library", &[PathHas("/lib/python3")], Medium, "Python's standard library"),
            mark("compiled", &[NameEnds(".pyc")], Medium, "compiled Python code"),
        ],
        next: &[
            next("core_packed_files_list", "pyinstaller_program", "list the files packed inside the program"),
            next("core_archive_show", "base_library", "list what's in its standard library"),
        ],
    },
    Runtime {
        id: "node",
        title: "Node.js (JavaScript run outside a browser)",
        engine: None,
        beneath: &["electron", "tauri"],
        markers: &[
            mark("modules", &[Name("node_modules")], Medium, "JavaScript packages"),
            mark("node_program", &[Name("node.exe")], Strong, "the Node.js program"),
            mark("node_binary", &[PathEnds("/bin/node")], Strong, "the Node.js program"),
            mark("addon", &[NameEnds(".node")], Medium, "a native add-on for Node.js"),
            mark("package", &[Name("package.json")], Weak, "a JavaScript package's description"),
        ],
        next: &[
            Next { tool: "js_app_map", param: "input_path", on: None, why: "map the app's JavaScript, IPC and routes" },
            next("core_target_triage", "addon", "what a native add-on is"),
        ],
    },
    Runtime {
        id: "unity",
        title: "Unity (a game engine)",
        engine: Some(game::Made::Unity),
        beneath: &[],
        markers: &[
            mark("player", &[NameStarts("unityplayer.")], Strong, "Unity's player"),
            mark("framework", &[PathEnds("unityframework.framework")], Strong, "Unity's player on Apple systems"),
            mark("managers", &[Name("globalgamemanagers")], Strong, "Unity's settings for a game"),
            mark("il2cpp_metadata", &[Name("global-metadata.dat")], Strong, "IL2CPP's table of the game's C# names"),
            mark("il2cpp_code", &[NameStarts("gameassembly.")], Strong, "a game's C# compiled to native code by IL2CPP"),
            mark("mono_code", &[Name("assembly-csharp.dll")], Strong, "a game's C# code, kept as .NET"),
            mark("default_resources", &[Name("unity default resources")], Strong, "Unity's built-in assets"),
        ],
        next: &[
            folder("game_archives_list", "find the files it packs its assets in"),
            next("game_unity_code_names_show", "il2cpp_metadata", "the names of its code"),
            next("managed_assembly_show", "mono_code", "what its code depends on"),
            next("game_unity_list", "managers", "the objects it holds"),
        ],
    },
    Runtime {
        id: "unreal",
        title: "Unreal Engine (a game engine)",
        engine: Some(game::Made::Unreal),
        beneath: &[],
        markers: &[
            look("pak", &[PathHas("/content/paks/"), NameEnds(".pak")], is_unreal_pak, Strong, "an Unreal archive, checked by its footer"),
            look("iostore", &[NameEnds(".utoc")], is_unreal_toc, Strong, "an Unreal IoStore table of contents, checked by its start"),
            mark("shipping_program", &[NameEnds("-shipping.exe")], Strong, "Unreal's usual name for a released program"),
            mark("engine_binaries", &[PathHas("/engine/binaries/")], Medium, "where Unreal keeps its programs"),
        ],
        next: &[
            folder("game_archives_list", "find the files it packs its assets in"),
            next("game_pak_list", "pak", "what's packed in its archive"),
            next("game_iostore_list", "iostore", "what's packed in its IoStore container"),
        ],
    },
    Runtime {
        id: "godot",
        title: "Godot (a game engine)",
        engine: Some(game::Made::Godot),
        beneath: &[],
        markers: &[
            look("pack", &[NameEnds(".pck")], is_godot_pack, Strong, "a Godot pack, checked by its start"),
            look("embedded_pack", &[Program], has_godot_trailer, Strong, "a program with a Godot pack at its end"),
        ],
        next: &[
            next("core_packed_files_list", "pack", "list what's packed inside"),
            next("core_packed_files_list", "embedded_pack", "list what's packed inside the program"),
            folder("game_archives_list", "find its packs"),
        ],
    },
    Runtime {
        id: NATIVE,
        title: "Native code (no bigger runtime recognised for this)",
        engine: None,
        beneath: &[ANY_OTHER],
        markers: &[look("program", &[Program], is_native_program, Weak, "a program in a machine's own code")],
        next: &[
            next("core_target_triage", "program", "what the program is and what it does"),
            next("native_rust_binary_show", "program", "whether it was written in Rust"),
        ],
    },
];

/// Asks of a file, kept to small reads, counted against the survey's budget.
struct Probe {
    file: File,
    len: u64,
    bytes_read: u64,
    text_budget: bool,
    head: Option<Vec<u8>>,
    tail: Option<Vec<u8>>,
    /// Text search results, so markers wanting the same search read once.
    searched: Option<bool>,
}

impl Probe {
    fn open(path: &Path, text_budget: bool) -> Option<Probe> {
        let file = File::open(path).ok()?;
        let len = file.metadata().ok()?.len();
        Some(Probe { file, len, bytes_read: 0, text_budget, head: None, tail: None, searched: None })
    }

    fn read_at(&mut self, at: u64, len: usize) -> Option<Vec<u8>> {
        self.file.seek(SeekFrom::Start(at)).ok()?;
        let mut buf = vec![0; len];
        let mut got = 0;
        while got < len {
            match self.file.read(buf.get_mut(got..)?) {
                Ok(0) => break,
                Ok(n) => got += n,
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {}
                Err(_) => return None,
            }
        }
        buf.truncate(got);
        self.bytes_read = self.bytes_read.saturating_add(got as u64);
        Some(buf)
    }

    /// The file's first bytes.
    fn head(&mut self) -> &[u8] {
        if self.head.is_none() {
            self.head = Some(self.read_at(0, PROBE_READ).unwrap_or_default());
        }
        self.head.as_deref().unwrap_or_default()
    }

    /// The file's last bytes.
    fn tail(&mut self) -> &[u8] {
        if self.tail.is_none() {
            let start = self.len.saturating_sub(PROBE_READ as u64);
            self.tail = Some(self.read_at(start, PROBE_READ).unwrap_or_default());
        }
        self.tail.as_deref().unwrap_or_default()
    }

    /// Whether the file's start holds any of `needles`, reading at most [`TEXT_WINDOW`] bytes and
    /// only when the survey has budget for it.
    fn start_holds(&mut self, needles: &[&[u8]]) -> bool {
        if let Some(found) = self.searched {
            return found;
        }
        let longest = needles.iter().map(|n| n.len()).max().unwrap_or(0);
        if !self.text_budget || longest == 0 {
            return false;
        }
        let mut found = false;
        let (mut at, mut carry) = (0u64, Vec::new());
        while at < self.len.min(TEXT_WINDOW) && !found {
            let Some(chunk) = self.read_at(at, 1 << 20) else { break };
            if chunk.is_empty() {
                break;
            }
            at = at.saturating_add(chunk.len() as u64);
            carry.extend_from_slice(&chunk);
            found = needles.iter().any(|n| !n.is_empty() && carry.windows(n.len()).any(|w| w == *n));
            let keep = carry.len().saturating_sub(longest);
            carry.drain(..keep);
        }
        self.searched = Some(found);
        found
    }
}

fn is_native_program(p: &mut Probe) -> bool {
    const MARKS: [&[u8]; 8] = [
        b"\x7fELF",
        b"MZ",
        &[0xfe, 0xed, 0xfa, 0xce],
        &[0xfe, 0xed, 0xfa, 0xcf],
        &[0xce, 0xfa, 0xed, 0xfe],
        &[0xcf, 0xfa, 0xed, 0xfe],
        &[0xca, 0xfe, 0xba, 0xbe],
        &[0xca, 0xfe, 0xba, 0xbf],
    ];
    let head = p.head();
    MARKS.iter().any(|m| head.starts_with(m))
}

/// Java's module image starts with 0xCAFEDADA, in the byte order of the machine it's for.
fn is_java_image(p: &mut Probe) -> bool {
    let head = p.head();
    head.starts_with(&[0xda, 0xda, 0xfe, 0xca]) || head.starts_with(&[0xca, 0xfe, 0xda, 0xda])
}

fn is_managed_pe(p: &mut Probe) -> bool {
    pe_is_managed(p.head())
}

fn is_godot_pack(p: &mut Probe) -> bool {
    p.head().starts_with(godot_pck::MAGIC)
}

/// A program with a Godot pack at its end: the trailer's pointer must land on a pack's mark.
fn has_godot_trailer(p: &mut Probe) -> bool {
    let len = p.len;
    let Some(start) = godot_pck::trailer_start(p.tail(), len) else { return false };
    p.read_at(start, godot_pck::MAGIC.len()).is_some_and(|m| m == godot_pck::MAGIC)
}

fn is_unreal_pak(p: &mut Probe) -> bool {
    let len = p.len;
    let tail = p.tail();
    let cut = tail.len().saturating_sub(unreal_pak::FOOTER_READ);
    unreal_pak::footer(tail.get(cut..).unwrap_or_default(), len).is_ok()
}

fn is_unreal_toc(p: &mut Probe) -> bool {
    p.head().starts_with(unreal_iostore::MAGIC)
}

/// PyInstaller's cookie sits near the end of the program it packs into.
fn has_pyinstaller_cookie(p: &mut Probe) -> bool {
    const COOKIE: &[u8; 8] = b"MEI\x0c\x0b\x0a\x0b\x0e";
    p.tail().windows(COOKIE.len()).any(|w| w == COOKIE)
}

/// Tauri programs carry the script names their web view is given; a plain mention of the word could
/// be anything, so these are its own distinctive spellings.
fn has_tauri_text(p: &mut Probe) -> bool {
    p.start_holds(&[b"__TAURI_INTERNALS__", b"__TAURI_INVOKE_KEY__", b"tauri://localhost"])
}

// ---- the walk -----------------------------------------------------------------------------------

/// One entry seen: its path relative to the top, lower case with `/`, starting with `/`.
struct Seen {
    rel: String,
    name: String,
    path: PathBuf,
    depth: usize,
    regular: bool,
    program: bool,
}

#[derive(Default)]
struct Walk {
    seen: Vec<Seen>,
    folders: u64,
    links: u64,
    not_walked: Vec<String>,
    capped: bool,
    unreadable: u64,
}

fn walk(root: &Path, max_entries: usize, max_depth: usize, ctx: &Ctx<'_>) -> Result<Walk, ToolError> {
    let mut w = Walk::default();
    let mut queue = VecDeque::from([(root.to_path_buf(), String::new(), 0usize)]);
    'all: while let Some((dir, rel, depth)) = queue.pop_front() {
        ctx.cancel.check()?;
        let Ok(entries) = std::fs::read_dir(&dir) else {
            w.unreadable += 1;
            continue;
        };
        for entry in entries.flatten() {
            if w.seen.len() >= max_entries {
                w.capped = true;
                break 'all;
            }
            // `file_type` doesn't follow links, so a link is only ever its own name.
            let Ok(kind) = entry.file_type() else {
                w.unreadable += 1;
                continue;
            };
            let name = entry.file_name().to_string_lossy().to_lowercase();
            let this = format!("{rel}/{name}");
            let path = entry.path();
            if kind.is_symlink() {
                w.links += 1;
            } else if kind.is_dir() {
                w.folders += 1;
                if NOT_WALKED.contains(&name.as_str()) {
                    w.not_walked.push(this.trim_start_matches('/').to_string());
                } else if depth < max_depth {
                    queue.push_back((path.clone(), this.clone(), depth + 1));
                } else {
                    w.capped = true;
                }
            }
            let regular = kind.is_file();
            let program = regular && looks_like_program(&entry, &rel, &name);
            w.seen.push(Seen { rel: this, name, path, depth, regular, program });
        }
    }
    Ok(w)
}

/// Whether a file sits or is marked as something a system would start.
fn looks_like_program(entry: &std::fs::DirEntry, parent: &str, name: &str) -> bool {
    if name.ends_with(".exe") || parent.ends_with("/macos") {
        return true;
    }
    executable(entry) && !name.contains('.')
}

#[cfg(unix)]
fn executable(entry: &std::fs::DirEntry) -> bool {
    use std::os::unix::fs::PermissionsExt;
    entry.metadata().is_ok_and(|m| m.permissions().mode() & 0o111 != 0)
}

#[cfg(not(unix))]
fn executable(_: &std::fs::DirEntry) -> bool {
    false
}

fn place_matches(at: &At, e: &Seen) -> bool {
    match at {
        Name(n) => e.name == *n,
        NameStarts(s) => e.name.starts_with(s),
        NameEnds(s) => e.name.ends_with(s),
        PathHas(s) => e.rel.contains(s),
        PathEnds(s) => e.rel.ends_with(s),
        Program => e.program,
        MainProgram => e.program && e.depth < MAIN_DEPTH,
    }
}

/// How the looks inside files have gone so far.
#[derive(Default)]
struct Budget {
    probes: usize,
    bytes: u64,
    text_searches: usize,
    ran_out: bool,
    /// Files that couldn't be opened to look inside (#292).
    unopened: u64,
}

/// The markers of every runtime that an entry passes, as (row, marker) → paths seen.
type Hits = BTreeMap<(usize, usize), Vec<usize>>;

fn scan(w: &Walk, ctx: &Ctx<'_>) -> Result<(Hits, Budget), ToolError> {
    let mut hits = Hits::new();
    let mut budget = Budget::default();
    for (i, e) in w.seen.iter().enumerate() {
        if i.is_multiple_of(1024) {
            ctx.cancel.check()?;
        }
        let mut probe = None;
        for (r, runtime) in RUNTIMES.iter().enumerate() {
            for (m, marker) in runtime.markers.iter().enumerate() {
                if !marker.at.iter().all(|at| place_matches(at, e)) {
                    continue;
                }
                let passed = match marker.look {
                    None => true,
                    Some(_) if !e.regular => false,
                    Some(look) => run_look(look, e, &mut probe, &mut budget),
                };
                if passed {
                    hits.entry((r, m)).or_default().push(i);
                }
            }
        }
        if let Some(Some(p)) = probe.take() {
            budget.bytes = budget.bytes.saturating_add(p.bytes_read);
        }
    }
    Ok((hits, budget))
}

/// `probe` is `None` until the file is opened, then `Some(None)` when that failed, so it's tried once.
fn run_look(look: Look, e: &Seen, probe: &mut Option<Option<Probe>>, budget: &mut Budget) -> bool {
    if probe.is_none() {
        if budget.probes >= MAX_PROBES || budget.bytes >= MAX_PROBE_BYTES {
            budget.ran_out = true;
            return false;
        }
        budget.probes += 1;
        let may_search = e.depth < MAIN_DEPTH && budget.text_searches < MAX_TEXT_SEARCHES;
        budget.text_searches += usize::from(may_search && e.program);
        let opened = Probe::open(&e.path, may_search && e.program);
        budget.unopened += u64::from(opened.is_none());
        *probe = Some(opened);
    }
    probe.as_mut().and_then(Option::as_mut).is_some_and(look)
}

// ---- the result ---------------------------------------------------------------------------------

/// What a macOS app's settings file says it is.
fn bundle_facts(root: &Path) -> Option<Value> {
    let regular = |p: &PathBuf| std::fs::symlink_metadata(p).is_ok_and(|m| m.is_file() && m.len() <= MAX_PLIST);
    let path = [root.join("Contents/Info.plist"), root.join("Info.plist")].into_iter().find(|p| regular(p))?;
    let v = plist::parse(&std::fs::read(&path).ok()?).ok()?;
    let text = |k: &str| v.get(k).and_then(plist::Value::as_str).map(str::to_string);
    Some(json!({
        "name": text("CFBundleDisplayName").or_else(|| text("CFBundleName")),
        "identifier": text("CFBundleIdentifier"),
        "version": text("CFBundleShortVersionString"),
        "executable": text("CFBundleExecutable"),
    }))
}

/// A candidate's rows, in the order they're shown.
#[derive(Debug, Serialize)]
struct Candidate {
    runtime: String,
    title: String,
    strength: Weight,
    score: u32,
    /// Expected under another candidate found here, or only found deep inside the folder: the app
    /// carries it, but it doesn't look like what the app itself is built on.
    secondary: bool,
    /// Normally part of another candidate found here, so not worth a mention of its own.
    #[serde(skip)]
    expected: bool,
    markers: Vec<Value>,
    next: Vec<Value>,
}

fn shown(root: &Path, e: &Seen) -> String {
    e.path.strip_prefix(root).unwrap_or(&e.path).to_string_lossy().replace('\\', "/")
}

/// A hit's paths, with the app's declared program first when it's among them.
fn ordered<'a>(w: &'a Walk, hit: &[usize], main_program: Option<&str>) -> Vec<&'a Seen> {
    let mut seen: Vec<&Seen> = hit.iter().filter_map(|i| w.seen.get(*i)).collect();
    if let Some(main) = main_program.map(str::to_lowercase) {
        seen.sort_by_key(|e| !(e.program && e.name == main));
    }
    seen
}

fn candidates(root: &Path, w: &Walk, hits: &Hits, found: Option<&game::Found>, main_program: Option<&str>) -> Vec<Candidate> {
    let mut out = Vec::new();
    for (r, runtime) in RUNTIMES.iter().enumerate() {
        let mut markers = Vec::new();
        let (mut strength, mut score, mut nearest) = (None, 0u32, usize::MAX);
        let mut first_of: BTreeMap<&str, String> = BTreeMap::new();
        for (m, marker) in runtime.markers.iter().enumerate() {
            let Some(hit) = hits.get(&(r, m)) else { continue };
            let seen = ordered(w, hit, main_program);
            let Some(first) = seen.first() else { continue };
            first_of.insert(marker.id, first.path.display().to_string());
            strength = strength.max(Some(marker.weight));
            if marker.weight >= Medium {
                nearest = nearest.min(seen.iter().map(|e| e.depth).min().unwrap_or(usize::MAX));
            }
            score += match marker.weight {
                Weak => 1,
                Medium => 3,
                Strong => 5,
            };
            markers.push(json!({
                "marker": marker.id,
                "means": marker.means,
                "weight": marker.weight,
                "count": seen.len(),
                "paths": seen.iter().take(PATHS_SHOWN).map(|e| shown(root, e)).collect::<Vec<_>>(),
            }));
        }
        if let Some(f) = found.filter(|f| runtime.engine == Some(f.engine)) {
            strength = Some(Strong);
            score += 5;
            nearest = 0;
            markers.push(json!({"marker": "game_detection", "means": format!("recognised as made with {}", f.label()), "weight": Strong, "count": 1, "paths": [f.clue], "version": f.version, "note": f.note}));
        }
        let Some(strength) = strength else { continue };
        let next: Vec<Value> = runtime
            .next
            .iter()
            .filter_map(|n| {
                let path = match n.on {
                    Some(on) => first_of.get(on)?.clone(),
                    None => root.display().to_string(),
                };
                Some(json!({"tool": n.tool, "args": {n.param: path}, "why": n.why}))
            })
            .collect();
        // Weak evidence is only ever supporting, wherever it is, so it doesn't count as carried.
        let deep = strength >= Medium && nearest > LEAD_DEPTH;
        out.push(Candidate { runtime: runtime.id.into(), title: runtime.title.into(), strength, score, secondary: deep, expected: false, markers, next });
    }
    // A game engine with no row of its own still counts.
    if let Some(f) = found.filter(|f| !RUNTIMES.iter().any(|r| r.engine == Some(f.engine))) {
        out.push(Candidate {
            runtime: format!("{:?}", f.engine).to_lowercase(),
            title: format!("{} (a game engine)", f.engine.name()),
            strength: Strong,
            score: 5,
            secondary: false,
            expected: false,
            markers: vec![json!({"marker": "game_detection", "means": format!("recognised as made with {}", f.label()), "weight": Strong, "count": 1, "paths": [f.clue], "version": f.version, "note": f.note})],
            next: vec![json!({"tool": "core_target_triage", "args": {"path": root.display().to_string()}, "why": "what it's made of and how big it is"})],
        });
    }
    let found_ids: Vec<String> = out.iter().map(|c| c.runtime.clone()).collect();
    for c in &mut out {
        let beneath = RUNTIMES.iter().find(|r| r.id == c.runtime).map_or(&[][..], |r| r.beneath);
        c.expected = beneath.iter().any(|b| if *b == ANY_OTHER { found_ids.len() > 1 } else { found_ids.iter().any(|f| f == b) });
        c.secondary |= c.expected;
    }
    out.sort_by(|a, b| a.secondary.cmp(&b.secondary).then(b.strength.cmp(&a.strength)).then(b.score.cmp(&a.score)));
    out
}

fn app_folder_explain(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SurveyParams = parse_params(params)?;
    let root = PathBuf::from(&p.path);
    if !root.is_absolute() {
        return Err(ToolError::invalid(format!("{:?} is not an absolute path", p.path)).with_remediation("Pass the full path of the app's folder."));
    }
    let meta = std::fs::metadata(&root).map_err(|e| ToolError::io(root.display(), e))?;
    if !meta.is_dir() {
        return Err(ToolError::invalid(format!("{} isn't a folder", root.display()))
            .with_remediation("Pass the app's install folder; for one file use core_target_triage."));
    }
    let name = root.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| p.path.clone());
    ctx.report(None, format!("Looking through {name}"));
    let (max_entries, max_depth) = (p.max_entries.clamp(1, MAX_ENTRIES), p.max_depth.min(MAX_DEPTH));
    let w = walk(&root, max_entries, max_depth, ctx)?;
    let (hits, budget) = scan(&w, ctx)?;
    let bundle = bundle_facts(&root);
    let main_program = bundle.as_ref().and_then(|b| b["executable"].as_str());
    // Games are recognised by the same code as triage, given this walk's regular files.
    let files: Vec<(String, PathBuf)> = w.seen.iter().filter(|e| e.regular).map(|e| (e.rel.trim_start_matches('/').to_string(), e.path.clone())).collect();
    let found = game::detect_in(&files);
    let list = candidates(&root, &w, &hits, found.as_ref(), main_program);

    let mut lims = vec![
        Limitation::new(
            "presence_not_proof",
            "A file being in the folder doesn't prove the app runs it: it may be unused, left over from an update, or there for another reason. Nothing was started, so these are inferences.",
        ),
        Limitation::new(
            "small_reads_only",
            "Only names, the ends of some files and the start of the main programs were read. The app's contents weren't unpacked or analysed; next_steps says what to run for that.",
        ),
    ];
    if w.capped {
        lims.push(Limitation::new(
            "walk_capped",
            format!("max_entries ({max_entries}) or max_depth ({max_depth}) stopped the walk, so what's further in wasn't seen. Raise them to see more."),
        ));
    }
    if budget.ran_out {
        lims.push(Limitation::new(
            "look_budget",
            format!("After {MAX_PROBES} files or {MAX_PROBE_BYTES} bytes, no more files were looked inside, so markers that need a look may be missing."),
        ));
    }
    if w.links > 0 {
        lims.push(Limitation::new("links_not_followed", format!("{} symbolic link(s) were noted by name only; what they point at wasn't read.", w.links)));
    }
    if w.unreadable > 0 {
        lims.push(Limitation::new("unreadable_entries", format!("{} file(s) or folder(s) couldn't be read.", w.unreadable)));
    }
    if budget.unopened > 0 {
        lims.push(Limitation::new(
            "unopened_files",
            format!("{} file(s) couldn't be opened to look inside, so what they would show is missing.", budget.unopened),
        ));
    }
    if !w.not_walked.is_empty() {
        lims.push(Limitation::new(
            "folders_counted_not_walked",
            format!(
                "{} folder(s) of packages were noted but not walked: {}.",
                w.not_walked.len(),
                w.not_walked.iter().take(3).cloned().collect::<Vec<_>>().join(", ")
            ),
        ));
    }
    let leading: Vec<&Candidate> = list.iter().filter(|c| !c.secondary && c.strength == Strong).collect();
    let titles = |cs: &[&Candidate]| cs.iter().map(|c| c.title.as_str()).collect::<Vec<_>>().join("; ");
    let carried: Vec<&Candidate> =
        list.iter().filter(|c| !leading.iter().any(|l| l.runtime == c.runtime) && c.runtime != NATIVE && !c.expected && c.strength >= Medium).collect();
    let is_native = list.iter().any(|c| c.runtime == NATIVE);
    let summary = match (leading.is_empty(), carried.is_empty(), is_native) {
        (false, true, _) => format!("{name}: looks built on {}.", titles(&leading)),
        (false, false, _) => format!("{name}: looks built on {}. It also carries {}.", titles(&leading), titles(&carried)),
        (true, false, true) => format!("{name}: its programs are native code, and it also carries {}.", titles(&carried)),
        (true, false, false) => format!("{name}: possibly {}, on some evidence.", titles(&carried)),
        (true, true, true) => format!("{name}: its programs are native code; no bigger runtime was recognised."),
        (true, true, false) => match list.first() {
            Some(c) => format!("{name}: possibly {}, on weak evidence.", c.title),
            None => format!("{name}: nothing in it points to a runtime, not even a native program."),
        },
    };
    // What leads the answer first, then the plain look at the program; the same step once.
    let mut next_steps: Vec<&Value> = Vec::new();
    let others = list.iter().filter(|c| leading.is_empty() || c.runtime == NATIVE);
    for step in leading.iter().copied().chain(others).flat_map(|c| &c.next) {
        let same = |s: &&Value| s["tool"] == step["tool"] && s["args"] == step["args"];
        if next_steps.len() < MAX_NEXT_STEPS && !next_steps.iter().any(same) {
            next_steps.push(step);
        }
    }
    let examined = w.seen.len() as u64;
    let result = json!({
        "folder": root.display().to_string(),
        "bundle": bundle,
        "candidates": list,
        "next_steps": next_steps,
        "game": found,
        "walk": {
            "entries": examined,
            "folders": w.folders,
            "links_not_followed": w.links,
            "folders_not_walked": w.not_walked,
            "files_looked_inside": budget.probes,
            "bytes_read": budget.bytes,
            "capped": w.capped,
            "max_entries": max_entries,
            "max_depth": max_depth,
        },
    });
    let unread = w.unreadable > 0 || budget.unopened > 0;
    let coverage = if w.capped || budget.ran_out || unread { partial(examined) } else { Coverage::complete(examined) };
    let ev = builder(ctx, "app_folder_explain", Subject { kind: "folder".into(), sha256: None, name: Some(name) }, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Inferred)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(coverage)
        .location(Location::new("path", p.path.clone()))
        .build()?;
    Ok(ToolOutput::Evidence(Box::new(ev)))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use super::*;
    use crate::Engine;
    use craft_anything_testkit::games::{GodotFile, Il2cppSample, godot_embedded, godot_pck, il2cpp_metadata};
    use std::collections::HashSet;

    fn engine() -> Engine {
        Engine::new(crate::testing::session())
    }

    fn write(root: &Path, rel: &str, bytes: &[u8]) {
        let p = root.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, bytes).unwrap();
    }

    fn survey(root: &Path) -> Value {
        call(&engine(), "app_folder_explain", json!({"path": root}))
    }

    fn ids(v: &Value) -> Vec<String> {
        v["result"]["candidates"].as_array().unwrap().iter().map(|c| c["runtime"].as_str().unwrap().to_string()).collect()
    }

    fn candidate<'a>(v: &'a Value, id: &str) -> &'a Value {
        v["result"]["candidates"].as_array().unwrap().iter().find(|c| c["runtime"] == id).unwrap_or_else(|| panic!("no {id} in {:?}", ids(v)))
    }

    fn step<'a>(v: &'a Value, tool: &str) -> &'a Value {
        v["result"]["next_steps"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["tool"] == tool)
            .unwrap_or_else(|| panic!("no {tool} in {:?}", v["result"]["next_steps"]))
    }

    /// A tiny PE with a CLI header, which is all `pe_is_managed` asks.
    fn managed_pe() -> Vec<u8> {
        craft_anything_testkit::managed::managed_assembly(4)
    }

    #[test]
    fn the_table_is_well_formed() {
        let specs = crate::tools::all();
        let mut runtimes = HashSet::new();
        for r in RUNTIMES {
            assert!(runtimes.insert(r.id), "two rows named {}", r.id);
            assert!(!r.markers.is_empty() && !r.next.is_empty(), "{}", r.id);
            let mut markers = HashSet::new();
            for m in r.markers {
                assert!(markers.insert(m.id), "{}: two markers named {}", r.id, m.id);
                assert!(!m.at.is_empty(), "{}.{}", r.id, m.id);
                for at in m.at {
                    if let Name(s) | NameStarts(s) | NameEnds(s) | PathHas(s) | PathEnds(s) = at {
                        assert_eq!(*s, s.to_lowercase(), "{}.{}: paths are compared in lower case", r.id, m.id);
                    }
                }
            }
            for n in r.next {
                let spec = specs.iter().find(|s| s.id == n.tool).unwrap_or_else(|| panic!("{}: no tool called {}", r.id, n.tool));
                let schema = (spec.input_schema)();
                assert!(schema["properties"].get(n.param).is_some(), "{} doesn't take {}", n.tool, n.param);
                if let Some(on) = n.on {
                    assert!(r.markers.iter().any(|m| m.id == on), "{}: next step points at no marker {on}", r.id);
                }
            }
        }
    }

    #[test]
    fn electron_on_windows_and_macos() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "resources/app.asar", b"not read");
        write(d.path(), "resources/elevate.exe", b"MZ");
        write(d.path(), "MyApp.exe", b"MZ");
        write(d.path(), "chrome_100_percent.pak", b"x");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "electron");
        assert_eq!(candidate(&v, "electron")["strength"], "strong");
        assert!(step(&v, "js_app_map")["args"]["input_path"].as_str().unwrap().ends_with("app.asar"));
        assert_eq!(v["confidence"], "inferred");
        assert!(v["summary"].as_str().unwrap().contains("Electron"));

        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/Resources/app.asar", b"x");
        write(d.path(), "Contents/MacOS/Slack", b"\xcf\xfa\xed\xfe");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "electron");
        assert!(step(&v, "js_electron_fuses_show")["args"]["path"].as_str().unwrap().ends_with("Electron Framework"));
        assert_eq!(candidate(&v, "native")["strength"], "weak");
        assert_eq!(*ids(&v).last().unwrap(), "native", "native comes last");
    }

    #[test]
    fn node_inside_electron_does_not_lead_however_many_markers_it_has() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/Resources/app.asar", b"x");
        write(d.path(), "Contents/Resources/bin/node", b"x");
        write(d.path(), "Contents/Resources/a.node", b"x");
        write(d.path(), "Contents/Resources/node_modules/x.js", b"x");
        write(d.path(), "Contents/Resources/package.json", b"{}");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "electron");
        assert_eq!(candidate(&v, "node")["secondary"], true);
        assert_eq!(candidate(&v, "electron")["secondary"], false);
        assert!(!v["summary"].as_str().unwrap().contains("Node"), "{}", v["summary"]);
        assert!(step(&v, "js_app_map")["args"]["input_path"].as_str().unwrap().ends_with("app.asar"));
        // Alone, it leads.
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "bin/node", b"x");
        let v = survey(d.path());
        assert_eq!(candidate(&v, "node")["secondary"], false);
        assert!(v["summary"].as_str().unwrap().contains("Node"));
    }

    #[test]
    fn a_runtime_only_found_deep_inside_is_carried_not_what_it_is_built_on() {
        // A native app keeping a Python for its scripts, and a Java app whose debugger brings one.
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/MacOS/App", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/Resources/FL/Shared/Python/Python.framework/x", b"x");
        let v = survey(d.path());
        assert_eq!(candidate(&v, "python")["secondary"], true);
        let summary = v["summary"].as_str().unwrap();
        assert!(summary.contains("native code") && summary.contains("carries Python"), "{summary}");

        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/lib/app.jar", b"PK");
        write(d.path(), "Contents/jbr/Contents/Home/lib/server/libjvm.dylib", b"x");
        write(d.path(), "Contents/bin/gdb/mac/arm/Python.framework/x", b"x");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "java");
        let summary = v["summary"].as_str().unwrap();
        assert!(summary.contains("built on Java") && summary.contains("also carries Python"), "{summary}");

        // A lone jar beside a native program is no more than that, too.
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/MacOS/App", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/MacOS/plugins/a.jar", b"PK");
        assert!(survey(d.path())["summary"].as_str().unwrap().contains("native code, and it also carries Java"));
    }

    #[test]
    fn a_java_image_is_checked_by_its_start() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "plugins/qml/lib/modules", b"a folder's name elsewhere, or any other file");
        assert!(survey(d.path())["result"]["candidates"].as_array().unwrap().is_empty());
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "runtime/lib/modules", &[0xda, 0xda, 0xfe, 0xca, 1, 0]);
        assert_eq!(ids(&survey(d.path()))[0], "java");
    }

    #[test]
    fn a_stray_weak_marker_doesnt_steer_the_next_steps_and_a_step_comes_once() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/Frameworks/QtCore.framework/Versions/A/QtCore", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/MacOS/App", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/PlugIns/x/package.json", b"{}");
        let v = survey(d.path());
        let steps = v["result"]["next_steps"].as_array().unwrap();
        assert!(steps.iter().all(|s| s["tool"] != "js_app_map"), "{steps:?}");
        assert!(steps[0]["args"]["path"].as_str().unwrap().ends_with("QtCore"), "{steps:?}");
        for (i, a) in steps.iter().enumerate() {
            assert!(steps.iter().skip(i + 1).all(|b| b["tool"] != a["tool"] || b["args"] != a["args"]), "{a} twice");
        }
    }

    #[test]
    fn tauri_is_found_in_the_main_program_alone() {
        let d = tempfile::tempdir().unwrap();
        let mut program = vec![0xcf, 0xfa, 0xed, 0xfe];
        program.resize(5 << 20, 0);
        program.extend_from_slice(b"window.__TAURI_INTERNALS__");
        write(d.path(), "Contents/MacOS/app", &program);
        write(d.path(), "Contents/Frameworks/x/y/z/deep", b"__TAURI_INTERNALS__");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "tauri");
        // Far down, or just saying the word, isn't enough.
        assert_eq!(candidate(&v, "tauri")["markers"][0]["paths"], json!(["Contents/MacOS/app"]));
        // The same look at the same program, wanted by two rows, is one step.
        let steps = v["result"]["next_steps"].as_array().unwrap();
        assert_eq!(steps.iter().filter(|s| s["tool"] == "core_target_triage").count(), 1, "{steps:?}");

        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/MacOS/app", b"\xcf\xfa\xed\xfe talks about tauri a lot");
        assert_eq!(ids(&survey(d.path())), ["native"]);
    }

    #[test]
    fn each_runtime_is_named_from_its_files() {
        let pyi = {
            let mut b = vec![0x7f, b'E', b'L', b'F'];
            b.extend_from_slice(&[0; 100]);
            b.extend_from_slice(b"MEI\x0c\x0b\x0a\x0b\x0e");
            b.extend_from_slice(&[0; 80]);
            b
        };
        type Files = Vec<(&'static str, Vec<u8>)>;
        let cases: Vec<(&str, Files)> = vec![
            ("tauri", vec![("tauri.conf.json", b"{}".to_vec())]),
            ("cef", vec![("libcef.dll", b"MZ".to_vec())]),
            ("qt", vec![("Qt6Core.dll", b"MZ".to_vec()), ("plugins/platforms/libqcocoa.dylib", b"x".to_vec())]),
            ("flutter", vec![("flutter_windows.dll", b"MZ".to_vec()), ("data/flutter_assets/AssetManifest.json", b"{}".to_vec())]),
            ("dotnet", vec![("App.runtimeconfig.json", b"{}".to_vec()), ("App.dll", managed_pe())]),
            ("java", vec![("lib/app.jar", b"PK".to_vec()), ("runtime/lib/server/libjvm.dylib", b"x".to_vec())]),
            ("python", vec![("_internal/base_library.zip", b"PK".to_vec()), ("python312.dll", b"MZ".to_vec())]),
            ("python", vec![("app.exe", pyi.clone())]),
            ("node", vec![("bin/node", b"x".to_vec()), ("lib/thing.node", b"x".to_vec())]),
            ("unity", vec![("UnityPlayer.dll", b"MZ".to_vec()), ("Game_Data/globalgamemanagers", b"x".to_vec())]),
            ("unity", vec![("Contents/Frameworks/UnityPlayer.dylib", b"x".to_vec()), ("Contents/Resources/Data/globalgamemanagers", b"x".to_vec())]),
            ("unreal", vec![("Game/Binaries/Win64/Game-Win64-Shipping.exe", b"MZ".to_vec())]),
            ("godot", vec![("game.pck", godot_pck(2, 2, &[]))]),
            ("native", vec![("bin/tool.exe", b"MZ".to_vec())]),
        ];
        for (want, files) in cases {
            let d = tempfile::tempdir().unwrap();
            for (rel, bytes) in &files {
                write(d.path(), rel, bytes);
            }
            let v = survey(d.path());
            assert_eq!(ids(&v).first().map(String::as_str), Some(want), "{files:?} gave {:?}", ids(&v));
            assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "presence_not_proof"));
        }
    }

    #[test]
    fn looks_inside_files_are_really_looked_at() {
        // A .pck that isn't a pack, a Chromium .pak, a stray .utoc and a plain .dll aren't evidence.
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "other.pck", b"not a godot pack");
        write(d.path(), "resources/cef.pak", b"a Chromium resource pack, not an Unreal one");
        write(d.path(), "assets.utoc", b"not a table of contents");
        write(d.path(), "plain.dll", b"MZ not managed");
        let v = survey(d.path());
        assert!(ids(&v).is_empty(), "{:?}", ids(&v));
        assert!(v["summary"].as_str().unwrap().contains("nothing"));
        assert_eq!(v["result"]["next_steps"], json!([]));
    }

    #[test]
    fn a_real_unreal_pak_and_a_program_with_a_pack_pass_their_looks() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Game/Content/Paks/Game.pak", &craft_anything_testkit::games::unreal_pak(&[("Game/", "a.txt", b"hi", false)]));
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "unreal");
        assert!(step(&v, "game_pak_list")["args"]["path"].as_str().unwrap().ends_with("Game.pak"));

        let d = tempfile::tempdir().unwrap();
        let files = [GodotFile { path: "res://a", data: b"x", flags: 0, md5: [1; 16] }];
        write(d.path(), "game.exe", &godot_embedded(b"MZ program", &godot_pck(2, 2, &files)));
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "godot");
        assert_eq!(candidate(&v, "godot")["markers"][0]["marker"], "embedded_pack");
        assert!(step(&v, "core_packed_files_list")["args"]["path"].as_str().unwrap().ends_with("game.exe"));

        // Its trailer's pointer must land on a pack.
        let d = tempfile::tempdir().unwrap();
        let mut liar = b"MZ program".to_vec();
        liar.extend_from_slice(&3u64.to_le_bytes());
        liar.extend_from_slice(b"GDPC");
        write(d.path(), "game.exe", &liar);
        assert_eq!(ids(&survey(d.path())), ["native"]);
    }

    #[test]
    fn unity_points_at_its_metadata_and_shares_the_game_detection() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "GameAssembly.dll", b"MZ");
        write(d.path(), "UnityPlayer.dll", b"MZ");
        let metadata = il2cpp_metadata(&Il2cppSample { version: 31, header_size: 256, type_size: 88, method_size: 36 });
        write(d.path(), "Game_Data/il2cpp_data/Metadata/global-metadata.dat", &metadata);
        write(d.path(), "Game_Data/globalgamemanagers", b"2022.3.62f1 and more");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "unity");
        assert_eq!(v["result"]["game"]["engine"], "unity", "the same detection triage uses");
        assert!(candidate(&v, "unity")["markers"].as_array().unwrap().iter().any(|m| m["marker"] == "game_detection"));
        let path = step(&v, "game_unity_code_names_show")["args"]["path"].as_str().unwrap().to_string();
        assert!(path.ends_with("global-metadata.dat"));
        // The step it names works.
        let shown = call(&engine(), "game_unity_code_names_show", json!({"path": path}));
        assert_eq!(shown["result"]["counts"]["types"], 3);
    }

    #[test]
    fn a_game_engine_without_a_row_still_counts() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "data.win", b"FORM");
        let v = survey(d.path());
        assert_eq!(ids(&v)[0], "gamemaker");
        assert_eq!(candidate(&v, "gamemaker")["strength"], "strong");
    }

    #[test]
    fn the_bundle_names_the_main_program_and_it_comes_first() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/Info.plist", br#"<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleExecutable</key><string>Zebra</string><key>CFBundleIdentifier</key><string>com.example.zebra</string></dict></plist>"#);
        write(d.path(), "Contents/MacOS/Aardvark", b"\xcf\xfa\xed\xfe");
        write(d.path(), "Contents/MacOS/Zebra", b"\xcf\xfa\xed\xfe");
        let v = survey(d.path());
        assert_eq!(v["result"]["bundle"]["identifier"], "com.example.zebra");
        assert!(step(&v, "core_target_triage")["args"]["path"].as_str().unwrap().ends_with("Zebra"));
    }

    #[test]
    fn walks_are_bounded_and_say_so() {
        let d = tempfile::tempdir().unwrap();
        for i in 0..30 {
            write(d.path(), &format!("f{i}.txt"), b"x");
        }
        write(d.path(), "a/b/c/d/e/deep.jar", b"PK");
        let e = engine();
        let v = call(&e, "app_folder_explain", json!({"path": d.path(), "max_entries": 5}));
        assert_eq!(v["result"]["walk"]["entries"], 5);
        assert_eq!(v["result"]["walk"]["capped"], true);
        assert_eq!(v["coverage"]["status"], "partial");
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "walk_capped"));

        let v = call(&e, "app_folder_explain", json!({"path": d.path(), "max_depth": 2}));
        assert!(!ids(&v).contains(&"java".to_string()), "too deep to reach");
        assert_eq!(v["result"]["walk"]["capped"], true);
        let v = call(&e, "app_folder_explain", json!({"path": d.path(), "max_depth": 9, "max_entries": 999_999_999}));
        assert_eq!(ids(&v)[0], "java");
        assert_eq!(v["result"]["walk"]["max_entries"], MAX_ENTRIES);
    }

    #[test]
    fn package_folders_are_noted_and_not_walked() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "node_modules/deep/libcef.dll", b"MZ");
        let v = survey(d.path());
        assert_eq!(ids(&v), ["node"]);
        assert_eq!(v["result"]["walk"]["folders_not_walked"], json!(["node_modules"]));
    }

    #[test]
    #[cfg(unix)]
    fn links_are_not_followed_even_in_a_loop() {
        let (d, outside) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
        write(outside.path(), "libcef.dll", b"MZ");
        std::os::unix::fs::symlink(outside.path(), d.path().join("away")).unwrap();
        std::os::unix::fs::symlink(d.path(), d.path().join("round")).unwrap();
        std::os::unix::fs::symlink(outside.path().join("libcef.dll"), d.path().join("link.jar")).unwrap();
        let v = survey(d.path());
        assert!(!ids(&v).contains(&"cef".to_string()), "{:?}", ids(&v));
        assert_eq!(v["result"]["walk"]["links_not_followed"], 3);
        assert_eq!(v["result"]["walk"]["entries"], 3);
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "links_not_followed"));
    }

    #[test]
    #[cfg(unix)]
    fn a_look_at_a_link_reads_nothing() {
        let (d, outside) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
        write(outside.path(), "real.pck", &godot_pck(2, 2, &[]));
        std::os::unix::fs::symlink(outside.path().join("real.pck"), d.path().join("game.pck")).unwrap();
        assert!(!ids(&survey(d.path())).contains(&"godot".to_string()));
    }

    #[test]
    fn an_empty_folder_says_so_and_a_file_or_relative_path_is_refused() {
        let d = tempfile::tempdir().unwrap();
        let v = survey(d.path());
        assert!(ids(&v).is_empty());
        assert_eq!(v["coverage"]["status"], "complete");
        let e = engine();
        write(d.path(), "file.exe", b"MZ");
        assert!(call_err(&e, "app_folder_explain", json!({"path": d.path().join("file.exe")})).message.contains("isn't a folder"));
        assert!(call_err(&e, "app_folder_explain", json!({"path": "relative/app"})).message.contains("absolute"));
        call_err(&e, "app_folder_explain", json!({"path": d.path().join("missing")}));
    }

    #[test]
    fn it_writes_nothing() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "resources/app.asar", b"x");
        let before: Vec<_> = std::fs::read_dir(d.path()).unwrap().flatten().map(|e| e.path()).collect();
        survey(d.path());
        assert_eq!(before, std::fs::read_dir(d.path()).unwrap().flatten().map(|e| e.path()).collect::<Vec<_>>());
    }

    #[test]
    fn clean_room_refuses_it() {
        let mut s = crate::testing::session();
        s.settings.deep_mode = false;
        let e = Engine::new(s);
        let d = tempfile::tempdir().unwrap();
        assert!(e.call("app_folder_explain", json!({"path": d.path()}), crate::CallOptions::new(crate::Caller::Mcp)).is_err());
    }

    #[test]
    fn a_program_is_recognised_where_a_system_would_start_one() {
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/MacOS/Thing", b"\xca\xfe\xba\xbe");
        write(d.path(), "script.exe", b"#!/bin/sh");
        let v = survey(d.path());
        assert_eq!(ids(&v), ["native"], "only the real Mach-O: a .exe that holds a script isn't native code");
    }

    /// #292: a program that couldn't be read made "nothing points to a runtime" with complete coverage.
    #[cfg(unix)]
    #[test]
    fn a_program_that_cant_be_opened_is_said_and_leaves_coverage_partial() {
        use std::os::unix::fs::PermissionsExt;
        let d = tempfile::tempdir().unwrap();
        write(d.path(), "Contents/MacOS/Thing", b"\xcf\xfa\xed\xfe");
        let program = d.path().join("Contents/MacOS/Thing");
        std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o111)).unwrap();
        if std::fs::read(&program).is_ok() {
            return; // Run as root: nothing is unreadable.
        }
        let v = survey(d.path());
        std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(v["coverage"]["status"], "partial", "{v}");
        let lim = v["limitations"].as_array().unwrap().iter().find(|l| l["code"] == "unopened_files").cloned();
        assert!(lim.is_some_and(|l| l["message"].as_str().unwrap().starts_with("1 file")), "{v}");
        assert_eq!(ids(&survey(d.path())), ["native"], "readable again, it's found");
    }
}
