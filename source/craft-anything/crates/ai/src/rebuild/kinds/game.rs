//! Games: built with a game engine (or Rust), studied with the game's own folder, and told how
//! to play like the original (mechanics sheet, decompiling in Deep mode, generated assets).

use super::*;
use craft_anything_engines::game;

/// Told to a resumed builder when the person turned generated assets off after some were made.
const ASSETS_NOW_OFF: &str =
    "Generated assets are now off for this project: don't make more with assets_image_generate or assets_model_generate. Keep the ones already in app/.";

pub struct GameKind;

impl GameKind {
    pub const ID: &'static str = "game";
}

impl TargetKind for GameKind {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn words(&self) -> KindWords {
        KindWords {
            button: "Play the game",
            icon: "play",
            ready: "Your game is ready",
            change_hint: "Ask for a change, e.g. \"make it faster\" or \"add a high-score table\"",
        }
    }

    fn detect(&self, cx: &DetectCx) -> Option<u32> {
        // Built with a game engine (the person picked a game on Make): a game whatever its words
        // say ("Clone <its title> 1:1" never says "game").
        if game::Builder::from_stack(cx.stack).is_some() {
            Some(200)
        } else if cx.says(&["game", "gameplay", "steam", "level", "player", "游戏", "遊戲", "玩法"]) {
            Some(60)
        } else {
            None
        }
    }

    /// The original's own engine when the target is a game made with one we can build with
    /// (Unreal, Godot), else Unity. Finding it reads the game's files, so only in Deep mode. The
    /// person can still pick another before starting.
    fn default_stack(&self, cx: &DetectCx) -> &'static str {
        let made = match cx.target {
            TargetRef::Local { path } if cx.deep => game_folder(path).and_then(|f| game::detect(&f)).map(|f| f.engine),
            _ => None,
        };
        game::Builder::for_game(made).stack()
    }

    /// An engine named in the request ("…in Rust", "with Godot"), as whole words.
    fn named_stack(&self, cx: &DetectCx) -> Option<&'static str> {
        game::Builder::ALL
            .into_iter()
            .find(|b| {
                let n = b.name().to_lowercase();
                let short = n.split(' ').next().unwrap_or(&n).to_string();
                [&n, &short].iter().any(|w| ["in", "with", "using"].iter().any(|p| cx.words.contains(&format!(" {p} {w} "))))
            })
            .map(game::Builder::stack)
    }

    fn studies_folder(&self) -> bool {
        true
    }

    fn goal(&self) -> &'static str {
        "a playable game that plays like the original: the same rules, controls, numbers and feel"
    }

    fn brief_sections(&self, cx: &BriefCx) -> Vec<String> {
        let target = &cx.ws.manifest.target;
        if matches!(target, TargetRef::Website { .. }) {
            return vec![screenshot::SCREENSHOT_CONTRACT.to_string(), self_test::SELF_TEST_CONTRACT.to_string()];
        }
        // Paid, so only when the person turned it on for this project and a key is set up.
        let generated = cx.assets && cx.ws.manifest.generate_assets;
        let mut s = vec![game_steps(cx.deep, cx.ghidra, matches!(target, TargetRef::Local { .. }), generated)];
        if generated {
            s.push(assets_note(cx.ws, cx.image_model));
        }
        s.push(screenshot::SCREENSHOT_CONTRACT.to_string());
        s.push(self_test::SELF_TEST_CONTRACT.to_string());
        s
    }

    /// The person may have turned generated assets on (or added a key) or off since the brief.
    fn follow_up_sections(&self, cx: &BriefCx) -> Vec<String> {
        if cx.assets && cx.ws.manifest.generate_assets {
            vec![assets_note(cx.ws, cx.image_model)]
        } else if !cx.ws.assets().is_empty() {
            vec![ASSETS_NOW_OFF.to_string()]
        } else {
            Vec::new()
        }
    }

    /// Every game must play its core loop; a game of a website has no mechanics sheet (its brief
    /// doesn't ask for one), and only Deep mode on a program brings in the original's files.
    fn checks(&self, ws: &Workspace) -> Vec<Box<dyn Check>> {
        let mut v: Vec<Box<dyn Check>> = vec![Box::new(BuildCheck), Box::new(ScreenshotCheck), Box::new(SelfTestCheck)];
        if !matches!(ws.manifest.target, TargetRef::Website { .. }) {
            v.push(Box::new(MechanicsCheck));
            v.push(Box::new(DeepOnly(CreditsCheck)));
        }
        v
    }
}

/// Deep mode with the original's files: the build says which it used (`app/CREDITS.md`) and that
/// it is for private use (`app/README.md` with `PRIVATE_USE_NOTE`), as the brief asks.
pub struct CreditsCheck;

impl CreditsCheck {
    pub const ID: &'static str = "credits";
}

impl Check for CreditsCheck {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        let (passed, note) = credits(&cx.ws.app_dir());
        Ok(CheckResult::new(self.id(), cx.round, passed, note))
    }
}

/// Whether `app/` credits the original's files and says they're private, with the note.
fn credits(app: &Path) -> (bool, String) {
    // Whitespace collapsed, so a wrapped line still counts.
    let read = |name: &str| std::fs::read_to_string(app.join(name)).unwrap_or_default().split_whitespace().collect::<Vec<_>>().join(" ");
    let mut add = Vec::new();
    if !read("README.md").contains(PRIVATE_USE_NOTE) {
        add.push(format!("start app/README.md with this line, as written: \"{PRIVATE_USE_NOTE}\""));
    }
    if read("CREDITS.md").is_empty() {
        add.push("list every original file you used in app/CREDITS.md, with its path in the game's folder".to_string());
    }
    if add.is_empty() {
        (true, "app/README.md says the build is for private use and app/CREDITS.md lists the original's files.".into())
    } else {
        (false, format!("This build uses the original game's own files, so {}.", add.join(", and ")))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_originals_files_need_credits_and_the_private_use_note() {
        let d = tempfile::tempdir().unwrap();
        let (ok, note) = credits(d.path());
        assert!(!ok && note.contains("app/README.md with this line") && note.contains(PRIVATE_USE_NOTE) && note.contains("app/CREDITS.md"), "{note}");
        // The note wrapped over lines under a heading counts; a README without it doesn't.
        std::fs::write(
            d.path().join("README.md"),
            format!(
                "# Game

{}

How to play…",
                PRIVATE_USE_NOTE.replacen(
                    ", for", ",
for", 1
                )
            ),
        )
        .unwrap();
        std::fs::write(
            d.path().join("CREDITS.md"),
            " 
",
        )
        .unwrap();
        let (ok, note) = credits(d.path());
        assert!(!ok && !note.contains("README") && note.contains("CREDITS.md"), "an empty CREDITS.md fails: {note}");
        std::fs::write(d.path().join("CREDITS.md"), "- Content/Rock.uasset from Game/Content/Paks").unwrap();
        assert!(credits(d.path()).0);
        std::fs::write(
            d.path().join("README.md"),
            "# Game
A private copy.",
        )
        .unwrap();
        assert!(!credits(d.path()).0, "the note must be there as written");
    }
}
