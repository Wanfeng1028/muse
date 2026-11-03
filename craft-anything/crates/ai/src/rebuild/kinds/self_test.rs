//! A game that draws isn't yet a game that plays: a first slice can draw a level with no player
//! in it. The brief asks every game for a `--self-test <file.json>` option (play the core loop
//! with scripted input, measure it from the game's own state, save the results, exit), and
//! [`SelfTestCheck`] holds the build to it: it starts the finished game that way after the
//! screenshot check, and the game isn't ready until every step of the core loop passes.

use super::screenshot::{NO_PROGRAM, OwnRun, run_with};
use super::*;
use craft_anything_engine::self_test::{SELF_TEST_VERSION as VERSION, SelfTestReport as Report};
use craft_anything_engine::workspace::Claim;

/// What every game brief asks for, so the check can see the core loop played.
pub const SELF_TEST_CONTRACT: &str = "Give the game a `--self-test <file.json>` option too: start a game the way a player would, drive the player with scripted input for a few seconds, measure from the game's own state whether each step of the core loop works, save the results to that file and exit: {\"version\": 1, \"steps\": [{\"step\": \"move\", \"passed\": true, \"detail\": \"walked 3.1 m forward\"}, {\"step\": \"act\", \"passed\": true, \"detail\": \"fired 5 shots, 2 hit\"}, {\"step\": \"hud\", \"passed\": true, \"detail\": \"health, ammo and the objective are drawn\"}]}. \"move\": the player (or what they steer) moves; \"act\": their main action works (firing, mining, jumping, eating…); \"hud\": the on-screen information the original shows (score, health, ammo…) is drawn. Craft Anything runs it after each build, and the game isn't ready until every step passes.";

/// The core loop, as the steps a self-test must pass: (step, what it shows).
const CORE_LOOP: [(&str, &str); 3] = [("move", "the player moves"), ("act", "the player's main action works"), ("hud", "the on-screen information is drawn")];

pub struct SelfTestCheck;

impl SelfTestCheck {
    pub const ID: &'static str = "game-self-test";
}

impl Check for SelfTestCheck {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        let round = cx.round;
        let file = cx.ws.checks_dir().join(format!("round-{round}")).join("self-test.json");
        let (passed, note, claims) = match run_with(cx, "--self-test", &file)? {
            OwnRun::NoProgram => (false, NO_PROGRAM.to_string(), Vec::new()),
            OwnRun::NoFile(why) => (false, format!("The game didn't save a report with --self-test.{why} {SELF_TEST_CONTRACT}"), Vec::new()),
            OwnRun::Saved { bytes, .. } => {
                let (passed, note) = verdict(&bytes);
                (passed, note, claims(&bytes))
            }
        };
        let artifacts = file.strip_prefix(&cx.ws.root).ok().map(Path::to_path_buf).filter(|_| file.is_file()).into_iter().collect();
        Ok(CheckResult { artifacts, claims, ..CheckResult::new(self.id(), round, passed, note) })
    }
}

/// Whether a self-test report shows every step of the core loop passing, with the note.
/// Each step of a saved self-test as a claim of its own: the core loop's steps (one the game
/// didn't test fails as "not tested"), then any steps the game added. An unreadable report makes
/// none ([`verdict`] says why).
pub fn claims(bytes: &[u8]) -> Vec<Claim> {
    let Ok(report) = serde_json::from_slice::<Report>(bytes) else { return Vec::new() };
    let core = |s: &str| CORE_LOOP.iter().any(|(step, _)| s.trim().eq_ignore_ascii_case(step));
    let mut out: Vec<Claim> = CORE_LOOP
        .iter()
        .map(|(step, shows)| {
            let title = format!("In play, {shows}");
            match report.steps.iter().find(|s| s.step.trim().eq_ignore_ascii_case(step)) {
                Some(s) => {
                    Claim::new(title, s.passed, if s.detail.trim().is_empty() { "the self-test says it failed".into() } else { s.detail.trim().to_string() })
                }
                None => Claim::new(title, false, "not tested"),
            }
        })
        .collect();
    out.extend(
        report.steps.iter().filter(|s| !core(&s.step)).take(20).map(|s| Claim::new(format!("Self-test step \"{}\"", s.step.trim()), s.passed, s.detail.trim())),
    );
    out
}

pub fn verdict(bytes: &[u8]) -> (bool, String) {
    let report: Report = match serde_json::from_slice(bytes) {
        Ok(r) => r,
        Err(e) => return (false, format!("The --self-test file can't be read: {e}. {SELF_TEST_CONTRACT}")),
    };
    if report.version > VERSION {
        return (false, format!("The --self-test file says version {}; this Craft Anything reads version {VERSION}.", report.version));
    }
    let (mut played, mut not) = (Vec::new(), Vec::new());
    for (step, shows) in CORE_LOOP {
        match report.steps.iter().find(|s| s.step.trim().eq_ignore_ascii_case(step)) {
            Some(s) if s.passed => played.push(if s.detail.trim().is_empty() { step.to_string() } else { format!("{step} ({})", s.detail.trim()) }),
            Some(s) => {
                not.push(format!("{step}: {shows}, failed{}", if s.detail.trim().is_empty() { String::new() } else { format!(" ({})", s.detail.trim()) }))
            }
            None => not.push(format!("{step}: {shows}, not tested")),
        }
    }
    if not.is_empty() {
        return (true, format!("The self-test plays the core loop: {}.", played.join(", ")));
    }
    (
        false,
        format!(
            "The self-test doesn't show the core loop working yet: {} of {} steps don't pass ({}). Build what's missing so a player can move, act and see the on-screen information, then measure each step from the game's own state in --self-test.",
            not.len(),
            CORE_LOOP.len(),
            not.join("; ")
        ),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_core_loop_passes_only_when_every_step_does() {
        let all = br#"{"version": 1, "steps": [{"step": "move", "passed": true, "detail": "moved 4 cells"}, {"step": "Act", "passed": true}, {"step": "hud", "passed": true, "detail": "score 1"}]}"#;
        let (ok, note) = verdict(all);
        assert!(ok, "{note}");
        assert_eq!(note, "The self-test plays the core loop: move (moved 4 cells), act, hud (score 1).");

        // A first slice: the level draws, but nobody plays in it.
        let slice = br#"{"steps": [{"step": "move", "passed": false, "detail": "no player in the level"}, {"step": "hud", "passed": true}]}"#;
        let (ok, note) = verdict(slice);
        assert!(!ok);
        assert!(note.contains("2 of 3 steps don't pass (move") && note.contains("move: the player moves, failed (no player in the level)"), "{note}");
        assert!(note.contains("act: the player's main action works, not tested") && !note.contains("hud:"), "{note}");

        for bad in [&b"not json"[..], br#"{"version": 1}"#, br#"{"steps": [{"step": "move"}]}"#] {
            let (ok, note) = verdict(bad);
            assert!(!ok && note.contains("can't be read") && note.contains("--self-test <file.json>"), "{note}");
        }
        let (ok, note) = verdict(br#"{"version": 2, "steps": []}"#);
        assert!(!ok && note.contains("version 2"), "{note}");
    }

    #[test]
    fn each_step_of_the_self_test_is_a_claim() {
        assert!(claims(all_steps()).iter().all(|c| c.passed) && claims(all_steps()).len() == 3);
        let slice = br#"{"steps": [{"step": "move", "passed": false, "detail": "no player in the level"}, {"step": "hud", "passed": true}, {"step": "reload", "passed": false, "detail": "ammo stays at 0"}]}"#;
        let got: Vec<(String, bool, String)> = claims(slice).into_iter().map(|c| (c.title, c.passed, c.detail)).collect();
        assert_eq!(
            got,
            [
                ("In play, the player moves".to_string(), false, "no player in the level".to_string()),
                ("In play, the player's main action works".to_string(), false, "not tested".to_string()),
                ("In play, the on-screen information is drawn".to_string(), true, String::new()),
                ("Self-test step \"reload\"".to_string(), false, "ammo stays at 0".to_string()),
            ],
            "the core loop first (untested steps fail), then the game's own steps"
        );
        assert!(claims(b"not json").is_empty());
    }

    fn all_steps() -> &'static [u8] {
        br#"{"version": 1, "steps": [{"step": "move", "passed": true, "detail": "moved 4 cells"}, {"step": "Act", "passed": true}, {"step": "hud", "passed": true, "detail": "score 1"}]}"#
    }
}
