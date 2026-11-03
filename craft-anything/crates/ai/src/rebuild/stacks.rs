//! The stacks a build can use, from the `stacks.toml` table: what the builder is told for each,
//! and the phrases that ask for one by name. Kinds name their default stack; the table says how
//! to build with it. The table also lists libraries asked for on top of a stack (shadcn/ui,
//! Tailwind CSS), whose steps are added to the stack's.

use std::sync::OnceLock;

/// One stack ("React + TypeScript (Vite)", "Unity"…).
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct Stack {
    /// Shown to the person and stored in the project.
    pub name: String,
    /// The game engine it builds with (`unity`, `unreal`, `godot`, `rust`), if any.
    #[serde(default)]
    pub engine: Option<String>,
    /// Phrases in a request that ask for this stack (`" in python"`), matched on the lower-case
    /// request padded with spaces.
    #[serde(default)]
    pub asked_by: Vec<String>,
    /// What the builder is told; `{editor}`, `{player}` and `{ext}` are filled in. `None` gets
    /// the generic instruction.
    #[serde(default)]
    pub steps: Option<String>,
    /// package.json dependencies that show a build uses this stack (`next`, `vite`).
    #[serde(default)]
    pub uses: Vec<String>,
}

/// The stack that leaves the choice to the builder (a website's default); [`used_in`] then
/// records the one it used.
pub const BUILDERS_CHOICE: &str = "Builder's choice";

/// A component or styling library asked for on top of a stack ("shadcn/ui", "Tailwind CSS").
#[derive(Debug, Clone, PartialEq, Eq, serde::Deserialize)]
pub struct Library {
    pub name: String,
    /// Phrases in a request that ask for it, matched like [`Stack::asked_by`].
    #[serde(default)]
    pub asked_by: Vec<String>,
    /// The stacks it works with, by name; empty = any.
    #[serde(default)]
    pub stacks: Vec<String>,
    /// What the builder is told, after the stack's steps.
    pub steps: String,
}

#[derive(Debug, Default, serde::Deserialize)]
struct Table {
    #[serde(default)]
    stack: Vec<Stack>,
    #[serde(default)]
    library: Vec<Library>,
}

/// The built-in table. A table that doesn't parse (a broken edit) leaves it empty, so every
/// stack gets the generic instruction instead of the app failing; a test keeps it parsing.
fn table() -> &'static Table {
    static TABLE: OnceLock<Table> = OnceLock::new();
    TABLE.get_or_init(|| parse(include_str!("stacks.toml")).unwrap_or_default())
}

pub fn catalogue() -> &'static [Stack] {
    &table().stack
}

fn parse(text: &str) -> Result<Table, toml::de::Error> {
    toml::from_str::<Table>(text)
}

/// A request as `asked_by` phrases are matched: lower-case words, punctuation turned into
/// spaces, padded with spaces (`"Use Next.js, shadcn/ui"` → `" use next js shadcn ui "`).
pub fn words(request: &str) -> String {
    let lower = request.to_lowercase();
    format!(" {} ", lower.split(|c: char| !c.is_alphanumeric()).filter(|w| !w.is_empty()).collect::<Vec<_>>().join(" "))
}

pub fn get(name: &str) -> Option<&'static Stack> {
    catalogue().iter().find(|s| s.name == name)
}

/// A stack picked by name: its full name or its engine id, ignoring case (`unity`, `Godot`,
/// `React + TypeScript (Vite)`).
pub fn resolve(name: &str) -> Option<&'static Stack> {
    let n = name.trim();
    catalogue().iter().find(|s| s.name.eq_ignore_ascii_case(n) || s.engine.as_deref().is_some_and(|e| e.eq_ignore_ascii_case(n)))
}

/// The first stack whose phrases appear in `words` (a request through [`words`]).
pub fn asked_for(words: &str) -> Option<&'static Stack> {
    catalogue().iter().find(|s| s.asked_by.iter().any(|p| words.contains(p.as_str())))
}

/// The stack a build in `app` uses, from its package.json dependencies (the first stack in table
/// order whose `uses` it lists); None when it has none or names no stack in the table.
pub fn used_in(app: &std::path::Path) -> Option<&'static Stack> {
    let deps = craft_anything_engine::outputs::npm_dependencies(app);
    catalogue().iter().find(|s| s.uses.iter().any(|d| deps.contains(d)))
}

/// The libraries `request` asks for that work with `stack`, in table order.
pub fn libraries_for(request: &str, stack: &str) -> Vec<&'static Library> {
    let w = words(request);
    table()
        .library
        .iter()
        .filter(|l| l.asked_by.iter().any(|p| w.contains(p.as_str())) && (l.stacks.is_empty() || l.stacks.iter().any(|s| s == stack)))
        .collect()
}

/// What the builder is told for `stack`. `editor`: the game engine's editor for engine stacks.
pub fn steps(stack: &str, editor: Option<&std::path::Path>) -> String {
    let Some(text) = get(stack).and_then(|s| s.steps.as_deref()) else {
        return format!("Use {stack}. Create the project in app/ and make sure it builds or runs without errors.");
    };
    let (player, ext) = if cfg!(windows) {
        ("StandaloneWindows64", "exe")
    } else if cfg!(target_os = "macos") {
        ("StandaloneOSX", "app")
    } else {
        ("StandaloneLinux64", "x86_64")
    };
    let editor = editor.map(|e| e.display().to_string()).unwrap_or_default();
    text.replace("{editor}", &editor).replace("{player}", player).replace("{ext}", ext)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_table_parses_and_covers_every_engine() {
        let names: Vec<&str> = catalogue().iter().map(|s| s.name.as_str()).collect();
        assert!(names.len() >= 7, "{names:?}");
        for b in craft_anything_engines::game::Builder::ALL {
            assert!(get(b.stack()).is_some(), "no stack in stacks.toml for {}", b.stack());
        }
        assert_eq!(get("Unity").and_then(|s| s.engine.as_deref()), Some("unity"));
        assert!(parse("[[stack]]\nname = 3").is_err(), "a broken table is an error, not a panic");
        for l in &table().library {
            assert!(!l.steps.is_empty() && !l.asked_by.is_empty(), "{l:?}");
            assert!(l.stacks.iter().all(|s| get(s).is_some()), "{} names a stack that isn't in the table", l.name);
        }
    }

    #[test]
    fn a_build_left_to_the_builder_is_recorded_under_the_stack_it_used() {
        let d = tempfile::tempdir().unwrap();
        assert!(
            get(BUILDERS_CHOICE)
                .is_some_and(|s| s.steps.as_deref().is_some_and(|t| t.starts_with("Use what their request names; otherwise choose the stack yourself")))
        );
        assert!(used_in(d.path()).is_none(), "no package.json");
        std::fs::write(d.path().join("package.json"), "not json").unwrap();
        assert!(used_in(d.path()).is_none(), "a broken package.json is no stack, not a crash");
        std::fs::write(d.path().join("package.json"), r#"{"dependencies": {"next": "16", "react": "19"}, "devDependencies": {"vite": "7"}}"#).unwrap();
        assert_eq!(used_in(d.path()).map(|s| s.name.as_str()), Some("Next.js + TypeScript"), "table order decides");
        std::fs::write(d.path().join("package.json"), r#"{"devDependencies": {"vite": "7"}}"#).unwrap();
        assert_eq!(used_in(d.path()).map(|s| s.name.as_str()), Some("React + TypeScript (Vite)"));
        std::fs::write(d.path().join("package.json"), r#"{"dependencies": {"astro": "5"}}"#).unwrap();
        assert!(used_in(d.path()).is_none(), "a stack the table doesn't know stays the builder's choice");
        assert_eq!(libraries_for("use shadcn", BUILDERS_CHOICE).len(), 1, "a library works with the builder's choice too");
    }

    #[test]
    fn spelled_variants_of_a_stack_and_its_libraries() {
        let next = Some("Next.js + TypeScript");
        for r in ["use nextjs", "Use Next.js", "built with next js", "in Next.JS please", "(Next.js) with React", "use next and shadcn", "a site in next"] {
            assert_eq!(asked_for(&words(r)).map(|s| s.name.as_str()), next, "{r}");
        }
        assert_eq!(asked_for(&words("what to do next")), None, "\"next\" alone isn't a stack");
        assert_eq!(asked_for(&words("build it with Vite")).map(|s| s.name.as_str()), Some("React + TypeScript (Vite)"));
        let names = |r: &str, stack: &str| libraries_for(r, stack).iter().map(|l| l.name.as_str()).collect::<Vec<_>>();
        for r in ["use shadcn", "with shadcn/ui", "shadcn-ui components", "ShadCN"] {
            assert_eq!(names(r, "Next.js + TypeScript"), ["shadcn/ui"], "{r}");
        }
        assert_eq!(names("shadcn and tailwind", "React + TypeScript (Vite)"), ["shadcn/ui", "Tailwind CSS"]);
        assert_eq!(names("TailwindCSS", "Next.js + TypeScript"), ["Tailwind CSS"]);
        assert!(names("shadcn", "Python").is_empty(), "a library only joins the stacks it works with");
        assert!(names("a plain page", "Next.js + TypeScript").is_empty());
    }

    #[test]
    fn named_stacks_and_placeholders() {
        assert_eq!(asked_for(&words("A tool in Python.")).map(|s| s.name.as_str()), Some("Python"));
        assert_eq!(asked_for(&words("a page with react")).map(|s| s.name.as_str()), Some("React + TypeScript (Vite)"));
        assert_eq!(asked_for(&words("a notes app")), None);
        assert_eq!(resolve("godot").map(|s| s.name.as_str()), Some("Godot"));
        assert_eq!(resolve(" unreal ").map(|s| s.name.as_str()), Some("Unreal Engine"));
        assert_eq!(resolve("rust + EGUI (eframe)").map(|s| s.name.as_str()), Some("Rust + egui (eframe)"));
        assert!(resolve("cobol").is_none());
        let unity = steps("Unity", Some(std::path::Path::new("/ed/Unity")));
        assert!(unity.contains("the editor is /ed/Unity") && !unity.contains('{'), "{unity}");
        assert_eq!(steps("Elm", None), "Use Elm. Create the project in app/ and make sure it builds or runs without errors.");
    }
}
