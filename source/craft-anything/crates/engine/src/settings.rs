//! User settings (`config.toml`). No environment variables are required for anything.

use crate::versioned::{Step, upgrade};
use craft_anything_evidence::{ErrorCode, ToolError};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    #[default]
    Beginner,
    Experienced,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct GhidraSettings {
    /// A Ghidra install to use instead of the managed one.
    pub install_dir: Option<PathBuf>,
    /// A Java runtime to use instead of the managed one.
    pub java_home: Option<PathBuf>,
    /// Seconds to wait for Ghidra to import and analyse a target.
    pub startup_timeout_secs: Option<u64>,
    /// A Ghidra language id to force, e.g. `RISCV:LE:64:RV64GC`, `PowerPC:BE:32:default`,
    /// `6502:LE:16:default`, `MIPS:BE:32:default`, `ARM:LE:32:v7`. Lets Deep mode target
    /// processors our own engine doesn't cover, with no per-architecture code. Only used in Deep
    /// mode with Ghidra installed.
    pub language_id: Option<String>,
    /// A Ghidra compiler-spec id to pair with `language_id` (e.g. `gcc`, `default`, `windows`).
    pub compiler_spec: Option<String>,
    /// Memory for Ghidra in GB (4 to 31). More makes its first look at a big program faster.
    /// `None`: half this computer's memory.
    pub memory_gb: Option<u64>,
}

/// One list for the per-engine path overrides: it declares the `ToolPaths` fields, `override_for`,
/// and the list the Engines settings page shows. The ids and their order are exactly the engines in
/// `craft_anything_engines::ENGINES` that have a path setting (a test checks it).
macro_rules! tool_paths {
    ($($id:ident),* $(,)?) => {
        /// Paths to external tools when the user prefers their own install over the managed one.
        #[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
        #[serde(default)]
        pub struct ToolPaths {
            $(pub $id: Option<PathBuf>,)*
        }

        impl ToolPaths {
            /// Every override as `(engine id, path)`, in settings-page order.
            pub fn entries_mut(&mut self) -> Vec<(&'static str, &mut Option<PathBuf>)> {
                vec![$((stringify!($id), &mut self.$id)),*]
            }
        }

        impl craft_anything_engines::ToolPathLookup for ToolPaths {
            fn override_for(&self, id: &str) -> Option<PathBuf> {
                match id {
                    $(stringify!($id) => self.$id.clone(),)*
                    _ => None,
                }
            }
        }
    };
}

// Ghidra is not here: its folder is `GhidraSettings::install_dir`.
tool_paths!(adb, jadx, apktool, chromium, frida, gdb, lldb, mitmdump, binwalk, unblob, ilspy, java, tshark, objdump, rizin, rtl433, vineflower);

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct EngineSettings {
    pub ghidra: GhidraSettings,
    pub tools: ToolPaths,
    /// Folder for managed engine installs; defaults to `<data dir>/engines`.
    pub store_dir: Option<PathBuf>,
    /// URL of a user-run JEB MCP server, e.g. `http://127.0.0.1:8425/mcp` (loopback, plain HTTP only).
    pub jeb_url: Option<String>,
    /// Find engines only where these settings and the managed store say, never on PATH or in the
    /// usual install folders. Never saved: test sessions set it so they don't find what this
    /// computer has installed ([`crate::testing::session`]).
    #[serde(skip)]
    pub only_configured: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Settings {
    /// The config.toml format version ([`SETTINGS_VERSION`]). Missing means 0: written before versions.
    pub version: u32,
    pub mode: Mode,
    /// Deep mode: tools may look inside the original (its code, files and page source), with our
    /// own engines and with Ghidra when it's installed. Off is Clean room: nothing inside the
    /// original is read, only what can be seen from outside ([`crate::clean_room`]).
    pub deep_mode: bool,
    /// `studio` (dark) or `studio-light`.
    pub theme: String,
    /// UI language (BCP 47), empty = system.
    pub language: String,
    pub first_run_done: bool,
    pub engines: EngineSettings,
    /// AI backends and roles. Owned and parsed by the `ai` crate; kept opaque here so the engine
    /// doesn't depend on it.
    pub ai: toml::Table,
    /// Ask before running tools that execute code or change devices (always true unless a project allows them).
    pub ask_before_running: bool,
    /// Auto mode: a build keeps going without stopping to ask the person. The builder's actions are
    /// allowed except a few that are never done unasked (deleting outside the project, system
    /// changes, publishing), and, unless `questions` says otherwise, its questions get "decide
    /// yourself". On by default.
    pub auto_mode: bool,
    /// What the builder's questions get in projects that don't choose (`Manifest::questions`):
    /// none follows Auto mode (decide when it's on, ask when it's off).
    pub questions: Option<crate::workspace::Questions>,
    /// Study an app or game target by running it once and picturing its window
    /// (`native_window_capture` into capture/window.png). Off by default: it runs the person's
    /// program.
    pub runtime_study: bool,
    /// Recently opened projects and targets.
    pub recent: Vec<PathBuf>,
    /// Where new projects are created; `None` = `Documents/Craft Anything`.
    pub projects_dir: Option<PathBuf>,
    /// More places projects are listed from: folders of projects, or projects started in a folder
    /// the person picked (added when they start one there).
    pub project_folders: Vec<PathBuf>,
    /// What the files already in a folder picked for a new project are: `None` asks each time;
    /// the person's "don't ask again" answer otherwise.
    pub existing_files: Option<crate::workspace::ExistingFiles>,
    /// Generated game assets: the budget a new project starts with and the picture model.
    pub assets: AssetSettings,
    /// External MCP servers whose tools are offered as Craft Anything tools (`[[plugins.mcp]]`).
    pub plugins: crate::plugins::PluginSettings,
    /// How builds are checked and when refining stops (`[build]`).
    pub build: BuildSettings,
}

/// How builds are checked and when refining stops.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BuildSettings {
    /// Likeness (percent) at which a compared build is good enough and refining stops.
    pub good_enough: f64,
    /// Refinement rounds after the first build in the app (the CLI's `--rounds` sets its own).
    pub max_rounds: u32,
    /// Widths (CSS px) a website and its rebuild are compared at.
    pub web_widths: Vec<u32>,
    /// Other pages of a website studied and checked besides the start page.
    pub max_pages: usize,
    /// When set, an app or game must look at least this alike (percent) to the person's pictures
    /// (or the original running) to be good enough; unset, that likeness is only reported.
    pub picture_good_enough: Option<f64>,
    /// Projects that may build at the same time; more wait their turn (at least 1).
    pub parallel: usize,
}

impl Default for BuildSettings {
    fn default() -> Self {
        BuildSettings { good_enough: 90.0, max_rounds: 6, web_widths: vec![1440, 768, 390], max_pages: 4, picture_good_enough: None, parallel: 2 }
    }
}

impl BuildSettings {
    /// The widths to compare at: the configured ones a capture can take (320-3840 px, at most 4),
    /// else the defaults (desktop, tablet and phone).
    pub fn widths(&self) -> Vec<u32> {
        let w: Vec<u32> = self.web_widths.iter().copied().filter(|w| (320..=3840).contains(w)).take(4).collect();
        if w.is_empty() { BuildSettings::default().web_widths } else { w }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AssetSettings {
    /// What a new project may spend on generated pictures and 3D models before the person is
    /// asked (US dollars). Each project keeps its own budget once created.
    pub budget_usd: f64,
    /// The picture model, by its id in the asset table (`nano-banana-pro`, `flux-dev`…); `None` = the
    /// table's default.
    pub image_model: Option<String>,
}

impl Default for AssetSettings {
    fn default() -> Self {
        AssetSettings { budget_usd: crate::workspace::ASSET_BUDGET_USD, image_model: None }
    }
}

impl AssetSettings {
    /// The budget for a new project; a negative or non-number value gives the built-in default.
    pub fn budget(&self) -> f64 {
        if self.budget_usd.is_finite() && self.budget_usd >= 0.0 { self.budget_usd } else { crate::workspace::ASSET_BUDGET_USD }
    }
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            version: SETTINGS_VERSION,
            mode: Mode::Beginner,
            deep_mode: false,
            theme: "studio".into(),
            language: String::new(),
            first_run_done: false,
            engines: EngineSettings::default(),
            ai: toml::Table::new(),
            ask_before_running: true,
            auto_mode: true,
            questions: None,
            runtime_study: false,
            recent: Vec::new(),
            projects_dir: None,
            project_folders: Vec::new(),
            existing_files: None,
            assets: AssetSettings::default(),
            plugins: crate::plugins::PluginSettings::default(),
            build: BuildSettings::default(),
        }
    }
}

/// The current `config.toml` format version. Bumping it means appending a step to [`SETTINGS_STEPS`].
pub const SETTINGS_VERSION: u32 = 3;

/// The steps that bring an older `config.toml` forward; step `i` goes from version `i` to `i + 1`.
const SETTINGS_STEPS: &[Step<toml::Table>] = &[settings_v0_to_v1, settings_v1_to_v2, settings_v2_to_v3];
const _: () = assert!(SETTINGS_STEPS.len() == SETTINGS_VERSION as usize, "one step per config.toml version");

/// Version 0 (no `version` key) has the same shape as version 1; only the number is new.
fn settings_v0_to_v1(_: &mut toml::Table) -> Result<(), String> {
    Ok(())
}

/// Version 2: Deep mode is its own switch. `[engines.ghidra] enabled` (the old switch, which
/// already meant Deep mode with or without Ghidra installed) becomes the top-level `deep_mode`.
fn settings_v1_to_v2(table: &mut toml::Table) -> Result<(), String> {
    let old = table
        .get_mut("engines")
        .and_then(toml::Value::as_table_mut)
        .and_then(|e| e.get_mut("ghidra"))
        .and_then(toml::Value::as_table_mut)
        .and_then(|g| g.remove("enabled"));
    if let Some(v) = old {
        let on = v.as_bool().ok_or_else(|| format!("engines.ghidra.enabled ({v}) isn't true or false"))?;
        table.entry("deep_mode").or_insert(toml::Value::Boolean(on));
    }
    Ok(())
}

/// Version 3 adds more project folders and the answer about a picked folder's files; both start
/// empty. The number is new so an older build doesn't save over the list (and lose it).
fn settings_v2_to_v3(_: &mut toml::Table) -> Result<(), String> {
    Ok(())
}

/// Read a `config.toml` of any version: older ones are brought forward step by step; a newer one is
/// read as far as its keys are known and keeps its version, so [`Settings::save_to`] won't write it.
pub fn read_settings(text: &str) -> Result<Settings, String> {
    let mut table: toml::Table = toml::from_str(text).map_err(|e| e.to_string())?;
    let found = match table.get("version") {
        None => 0,
        Some(v) => v.as_integer().and_then(|n| u32::try_from(n).ok()).ok_or_else(|| format!("its version ({v}) isn't a whole number"))?,
    };
    if found <= SETTINGS_VERSION {
        let reached = upgrade(&mut table, found, 0, SETTINGS_STEPS)?;
        table.insert("version".into(), toml::Value::Integer(reached.into()));
    }
    table.try_into::<Settings>().map_err(|e| e.to_string())
}

/// Where settings, logs and the engine store live: `CRAFT_ANYTHING_CONFIG_DIR`, then a portable
/// `portable.txt` marker next to the executable, then the platform config dir.
pub fn config_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("CRAFT_ANYTHING_CONFIG_DIR") {
        return PathBuf::from(dir);
    }
    if let Some(exe_dir) = std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf))
        && exe_dir.join("portable.txt").exists()
    {
        return exe_dir.join("CraftAnythingData");
    }
    dirs::config_dir().map(|d| d.join("craft-anything")).unwrap_or_else(|| PathBuf::from(".craft-anything"))
}

impl Settings {
    /// The folder new projects go in.
    pub fn projects_dir(&self) -> PathBuf {
        self.projects_dir.clone().unwrap_or_else(crate::workspace::default_projects_dir)
    }

    /// What the builder's questions get in a project that doesn't choose.
    pub fn questions(&self) -> crate::workspace::Questions {
        use crate::workspace::Questions;
        self.questions.unwrap_or(if self.auto_mode { Questions::Decide } else { Questions::Ask })
    }

    /// What the builder's questions get in `project` (its own choice, else the app's default).
    pub fn questions_in(&self, project: Option<&crate::workspace::Manifest>) -> crate::workspace::Questions {
        project.and_then(|m| m.questions).unwrap_or_else(|| self.questions())
    }

    /// Everywhere projects are listed from: the folder new projects go in, then the others, each once.
    pub fn project_locations(&self) -> Vec<PathBuf> {
        let mut v = vec![self.projects_dir()];
        for f in &self.project_folders {
            if !v.contains(f) {
                v.push(f.clone());
            }
        }
        v
    }

    /// Keep a project started in a picked folder in the list. Returns whether the list changed:
    /// false when one of the locations already shows it (it is one, or sits directly in one).
    pub fn remember_project(&mut self, root: &Path) -> bool {
        let shown = self.project_locations().iter().any(|l| l == root || root.parent() == Some(l.as_path()));
        if !shown {
            self.project_folders.push(root.to_path_buf());
        }
        !shown
    }

    pub fn path() -> PathBuf {
        config_dir().join("config.toml")
    }

    /// Load settings; a missing file gives defaults, an older one is brought up to date, a corrupt
    /// one is set aside and replaced with defaults (never a crash).
    pub fn load_from(path: &Path) -> Settings {
        match std::fs::read_to_string(path) {
            Ok(text) => match read_settings(&text) {
                Ok(s) => {
                    if s.version > SETTINGS_VERSION {
                        log::warn!("{} is from a newer Craft Anything (version {}); changes won't be saved over it", path.display(), s.version);
                    }
                    s
                }
                Err(e) => {
                    // A newer file this build can't read is left in place, and never saved over.
                    let newer = toml::from_str::<toml::Table>(&text)
                        .ok()
                        .and_then(|t| t.get("version").and_then(toml::Value::as_integer))
                        .and_then(|n| u32::try_from(n).ok());
                    if let Some(version) = newer.filter(|v| *v > SETTINGS_VERSION) {
                        log::warn!(
                            "{} is from a newer Craft Anything (version {version}) and unreadable here ({e}); using defaults without saving",
                            path.display()
                        );
                        return Settings { version, ..Settings::default() };
                    }
                    log::warn!("{} is unreadable ({e}); using defaults and keeping a copy", path.display());
                    let _ = std::fs::rename(path, path.with_extension("toml.broken"));
                    Settings::default()
                }
            },
            Err(_) => Settings::default(),
        }
    }

    pub fn load() -> Settings {
        Settings::load_from(&Settings::path())
    }

    pub fn save_to(&self, path: &Path) -> Result<(), ToolError> {
        if self.version > SETTINGS_VERSION {
            return Err(ToolError::new(
                ErrorCode::BadSettings,
                format!("{} was written by a newer Craft Anything (version {}), so this one doesn't change it.", path.display(), self.version),
            )
            .with_remediation("Update Craft Anything to change settings, or move config.toml aside to start fresh. Nothing was written."));
        }
        let text = toml::to_string_pretty(self).map_err(|e| ToolError::new(ErrorCode::BadSettings, e.to_string()))?;
        crate::project::write_atomic(path, text.as_bytes())
    }

    pub fn save(&self) -> Result<(), ToolError> {
        self.save_to(&Settings::path())
    }

    pub fn engine_store_dir(&self) -> PathBuf {
        self.engines.store_dir.clone().unwrap_or_else(|| config_dir().join("engines"))
    }

    /// Ghidra's headless launcher, when Deep mode can really use Ghidra (`None`: not installed).
    pub fn ghidra_launcher(&self) -> Option<PathBuf> {
        let (dir, store) = (self.engines.ghidra.install_dir.as_deref(), self.engine_store_dir());
        if self.engines.only_configured {
            craft_anything_engines::ghidra::get::headless_configured(dir, &store)
        } else {
            craft_anything_engines::ghidra::get::headless(dir, &store)
        }
    }

    /// The Java runtime Ghidra runs on (`None`: let Ghidra find its own).
    pub fn ghidra_java(&self) -> Option<PathBuf> {
        craft_anything_engines::ghidra::get::java_home(self.engines.ghidra.java_home.as_deref(), &self.engine_store_dir())
    }

    /// Where an external engine is on this computer, honouring every setting that can name one:
    /// the path overrides (`engines.tools`) and, for Ghidra, its own folder setting
    /// (`engines.ghidra.install_dir`). The one lookup behind every listing (`engines_list`,
    /// `doctor`, `capabilities`) and behind `Requires::Engine`, so they all agree with what Deep
    /// mode actually runs.
    pub fn engine_path(&self, id: &str) -> Option<PathBuf> {
        if id == craft_anything_engines::ghidra::get::ID {
            return self.ghidra_launcher();
        }
        if self.engines.only_configured {
            craft_anything_engines::locate_configured(id, &self.engines.tools, &self.engine_store_dir())
        } else {
            craft_anything_engines::locate(id, &self.engines.tools, &self.engine_store_dir())
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn build_settings_have_safe_widths_and_old_configs_get_defaults() {
        let b = BuildSettings { web_widths: vec![10, 1280, 99_999, 375, 200], ..BuildSettings::default() };
        assert_eq!(b.widths(), [1280, 375], "widths a capture can't take are dropped");
        assert_eq!(BuildSettings { web_widths: vec![], ..BuildSettings::default() }.widths(), [1440, 768, 390]);
        let old: Settings = toml::from_str(
            "version = 1
auto_mode = true
",
        )
        .unwrap();
        assert_eq!(old.build, BuildSettings::default());
        assert_eq!(old.build.picture_good_enough, None, "picture likeness is only reported unless set");
    }

    use super::*;

    #[test]
    fn only_configured_finds_no_engine_from_this_computer_but_keeps_the_ones_set() {
        let dir = tempfile::tempdir().unwrap();
        let mut s = Settings::default();
        s.engines.store_dir = Some(dir.path().join("engines"));
        s.engines.only_configured = true;
        assert_eq!(s.ghidra_launcher(), None, "PATH and the usual install folders aren't searched");
        assert_eq!(s.engine_path("java"), None);
        // The folder the person picked still counts, and so does the managed store.
        let launcher_name = if cfg!(windows) { "analyzeHeadless.bat" } else { "analyzeHeadless" };
        let picked = dir.path().join("picked").join("ghidra_12_PUBLIC");
        std::fs::create_dir_all(picked.join("support")).unwrap();
        std::fs::write(picked.join("support").join(launcher_name), "").unwrap();
        s.engines.ghidra.install_dir = Some(dir.path().join("picked"));
        assert_eq!(s.ghidra_launcher(), Some(picked.join("support").join(launcher_name)));
        assert_eq!(s.engine_path("ghidra"), s.ghidra_launcher());
        s.engines.ghidra.install_dir = None;
        let managed = dir.path().join("engines").join("ghidra").join("ghidra_12_PUBLIC").join("support");
        std::fs::create_dir_all(&managed).unwrap();
        std::fs::write(managed.join(launcher_name), "").unwrap();
        assert_eq!(s.ghidra_launcher(), Some(managed.join(launcher_name)));
        // It is never written to config.toml, and a loaded config looks around the computer.
        let text = toml::to_string_pretty(&s).unwrap();
        assert!(!text.contains("only_configured"), "{text}");
        let loaded: Settings = toml::from_str(&text).unwrap();
        assert!(!loaded.engines.only_configured);
    }

    #[test]
    fn the_test_session_looks_only_where_its_settings_say() {
        assert!(crate::testing::session().settings.engines.only_configured);
    }

    #[test]
    fn path_overrides_match_the_engine_table_exactly() {
        use craft_anything_engines::ToolPathLookup;
        let mut paths = ToolPaths::default();
        let ids: Vec<&str> = paths.entries_mut().into_iter().map(|(id, _)| id).collect();
        let table: Vec<&str> = craft_anything_engines::path_setting_ids().collect();
        assert_eq!(ids, table, "tool_paths! must list the engine table's path-setting ids, in table order");
        for (id, v) in paths.entries_mut() {
            *v = Some(PathBuf::from(format!("/opt/{id}")));
        }
        for id in table {
            assert_eq!(paths.override_for(id), Some(PathBuf::from(format!("/opt/{id}"))), "no override for {id}");
        }
        // An older config.toml without the newer fields still loads.
        let old: ToolPaths = toml::from_str("adb = \"/x/adb\"\n").unwrap();
        assert_eq!(old.adb, Some(PathBuf::from("/x/adb")));
        assert_eq!(old.tshark, None);
    }

    /// A config.toml as written before versions existed.
    const CONFIG_V0: &str = r#"mode = "experienced"
theme = "studio-light"
language = ""
first_run_done = true
ask_before_running = true
auto_mode = false
recent = ["/home/me/app.exe"]

[engines]
store_dir = "/data/engines"

[engines.ghidra]
enabled = true

[engines.tools]
adb = "/x/adb"

[ai]
default = "Claude Code"
"#;

    #[test]
    fn configs_from_before_versions_load_unchanged() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        std::fs::write(&path, CONFIG_V0).unwrap();
        let s = Settings::load_from(&path);
        assert_eq!(s.version, SETTINGS_VERSION);
        assert_eq!((s.mode, s.theme.as_str(), s.first_run_done, s.auto_mode), (Mode::Experienced, "studio-light", true, false));
        assert!(s.deep_mode, "the old Ghidra switch becomes Deep mode");
        assert_eq!(s.engines.tools.adb, Some(PathBuf::from("/x/adb")));
        assert_eq!(s.ai.get("default").and_then(|v| v.as_str()), Some("Claude Code"));
        assert!(!path.with_extension("toml.broken").exists());
        s.save_to(&path).unwrap();
        let saved = std::fs::read_to_string(&path).unwrap();
        assert!(saved.starts_with(&format!("version = {SETTINGS_VERSION}\n")) && saved.contains("deep_mode = true") && !saved.contains("enabled"), "{saved}");
        assert_eq!(Settings::load_from(&path), s);
    }

    #[test]
    fn newer_configs_load_but_are_never_overwritten() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        let newer = format!("version = 9\nsomething_new = 3\n{CONFIG_V0}");
        std::fs::write(&path, &newer).unwrap();
        let s = Settings::load_from(&path);
        assert_eq!((s.version, s.mode), (9, Mode::Experienced));
        let err = s.save_to(&path).unwrap_err();
        assert!(err.message.contains("newer") && err.remediation.is_some());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), newer);
        // Newer and unreadable here: defaults, but the file stays where it is and isn't saved over.
        let unreadable = "version = 9\nmode = { kind = \"pro\" }\n";
        std::fs::write(&path, unreadable).unwrap();
        let s = Settings::load_from(&path);
        assert_eq!(s, Settings { version: 9, ..Settings::default() });
        assert!(s.save_to(&path).is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), unreadable);
        assert!(!path.with_extension("toml.broken").exists());
        // A version that isn't a number is a broken file: set aside, defaults used.
        std::fs::write(&path, "version = \"two\"\n").unwrap();
        assert_eq!(Settings::load_from(&path), Settings::default());
        assert!(path.with_extension("toml.broken").exists());
        assert!(read_settings("version = -1").is_err());
    }

    #[test]
    fn round_trip_and_corrupt_file_recovery() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        let mut s = Settings { mode: Mode::Experienced, ..Default::default() };
        s.deep_mode = true;
        s.save_to(&path).unwrap();
        assert_eq!(Settings::load_from(&path), s);
        std::fs::write(&path, "mode = [[[").unwrap();
        assert_eq!(Settings::load_from(&path), Settings::default());
        assert!(path.with_extension("toml.broken").exists());
    }

    #[test]
    fn the_asset_budget_is_a_setting_and_old_configs_load() {
        let old: Settings = toml::from_str("mode = \"experienced\"\nauto_mode = false\n").unwrap();
        assert_eq!(old.assets.budget(), 5.0, "a config without [assets] gets the built-in budget");
        assert_eq!(old.assets.image_model, None);
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        let mut s = Settings::default();
        s.assets.budget_usd = 12.5;
        s.assets.image_model = Some("flux-schnell".into());
        s.save_to(&path).unwrap();
        assert_eq!(Settings::load_from(&path), s);
        let odd: Settings = toml::from_str("[assets]\nbudget_usd = -3.0\n").unwrap();
        assert_eq!(odd.assets.budget(), 5.0, "a negative budget isn't used");
    }

    #[test]
    fn projects_are_listed_from_more_folders_and_a_picked_one_is_remembered() {
        let mut s = Settings { projects_dir: Some(PathBuf::from("/p")), ..Settings::default() };
        assert_eq!(s.project_locations(), [PathBuf::from("/p")]);
        assert!(!s.remember_project(Path::new("/p/notes")), "already listed: it's in the projects folder");
        assert!(s.remember_project(Path::new("/work/mine")));
        assert!(!s.remember_project(Path::new("/work/mine")), "once");
        s.project_folders.push(PathBuf::from("/p"));
        assert_eq!(s.project_locations(), [PathBuf::from("/p"), PathBuf::from("/work/mine")], "each place once");
        // Saved and read back, with the answer about a picked folder's files.
        s.existing_files = Some(crate::workspace::ExistingFiles::StartFrom);
        let back = read_settings(&toml::to_string(&s).unwrap()).unwrap();
        assert_eq!(back.project_folders, s.project_folders);
        assert_eq!(back.existing_files, s.existing_files);
        // A version 2 config has neither, and asks.
        let v2 = read_settings("version = 2\ndeep_mode = true\n").unwrap();
        assert_eq!(v2.version, SETTINGS_VERSION);
        assert!(v2.project_folders.is_empty() && v2.existing_files.is_none() && v2.deep_mode);
    }
}
