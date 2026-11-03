//! The builder tests its own work while it builds: `rebuild_check` (in [`super::tools`]) asks the
//! run through `checks/asks/` (the inbox's folder protocol, in a folder only the run reads), and
//! the run answers during the builder's turn with the same checks it runs after the turn, as
//! round 0 (`checks/round-0/`), not counted as a round.

use super::*;

/// The round a builder's own check is run as; real rounds start at 1.
pub const SELF_CHECK_ROUND: u32 = 0;

/// Where `rebuild_check` asks a project's run for a check.
pub fn asks_dir(project: &Path) -> PathBuf {
    project.join("checks").join("asks")
}

/// Projects whose build runs in this process. A builder in this process (an API backend) calls
/// tools with the engine locked, so its `rebuild_check` could never be answered by this run.
static BUILDING_HERE: Mutex<Vec<PathBuf>> = Mutex::new(Vec::new());

/// Marks a project as building in this process until dropped.
pub(super) struct BuildingHere(PathBuf);

impl BuildingHere {
    pub(super) fn new(root: &Path) -> BuildingHere {
        BUILDING_HERE.lock().unwrap_or_else(PoisonError::into_inner).push(root.to_path_buf());
        BuildingHere(root.to_path_buf())
    }
}

impl Drop for BuildingHere {
    fn drop(&mut self) {
        let mut v = BUILDING_HERE.lock().unwrap_or_else(PoisonError::into_inner);
        if let Some(i) = v.iter().position(|p| *p == self.0) {
            v.remove(i);
        }
    }
}

/// The project builds in this process.
pub fn building_here(root: &Path) -> bool {
    BUILDING_HERE.lock().unwrap_or_else(PoisonError::into_inner).iter().any(|p| p == root)
}

/// The questions the builder recorded (`core_unknown_add`, kept in the project's investigation
/// folder) that aren't resolved yet, most severe first. Read from disk: the builder's tool server
/// writes them while this run works.
pub fn open_questions(ws: &Workspace) -> Vec<craft_anything_evidence::Unknown> {
    let mut open: Vec<_> = Project::open(&ws.investigation_dir())
        .and_then(|p| p.load_unknowns())
        .unwrap_or_default()
        .into_iter()
        .filter(|u| u.status != craft_anything_evidence::UnknownStatus::Resolved)
        .collect();
    open.sort_by(|a, b| b.severity.cmp(&a.severity).then_with(|| a.question.cmp(&b.question)));
    open
}

/// One plain line on how a round of checks went: how alike when compared, else how many checks
/// pass, and how many of their claims hold ("about 93% like the original, 5 of 5 claims hold";
/// "all 4 checks pass, 5 of 5 claims hold").
pub fn summary(checks: &[CheckResult], good_enough: f64) -> String {
    let claims: Vec<_> = checks.iter().flat_map(|c| &c.claims).collect();
    let held = claims.iter().filter(|c| c.passed).count();
    let claims_part = if claims.is_empty() { String::new() } else { format!(", {held} of {} claims hold", claims.len()) };
    let good = checks.iter().filter(|c| c.good(good_enough)).count();
    match checks.iter().find_map(|c| c.similarity) {
        Some(s) => format!("about {s:.0}% like the original{claims_part}"),
        None if good == checks.len() => format!("all {} checks pass{claims_part}", checks.len()),
        None => format!("{good} of {} checks pass{claims_part}", checks.len()),
    }
}

/// What the builder is told about its own check: each result with its likeness and the bar,
/// what's still unknown (the checks' and its own open questions), where its pictures are, and
/// whether it would pass.
pub fn report(checks: &[CheckResult], good_enough: f64, open: &[craft_anything_evidence::Unknown]) -> String {
    if checks.is_empty() {
        return "There was nothing to check yet.".into();
    }
    let mut lines = Vec::new();
    for c in checks {
        let mut line = format!("{}: {}", c.check, if c.passed { "passed" } else { "failed" });
        if let Some(s) = c.similarity {
            line.push_str(&format!(", {s:.0}% alike (needs {:.0}%)", c.good_enough.unwrap_or(good_enough)));
        }
        line.push_str(&format!(" — {}", c.note));
        lines.push(line);
    }
    let failed: Vec<String> = checks.iter().flat_map(|c| c.failed_claims()).map(|c| format!("{} ({})", c.title, c.detail)).collect();
    if !failed.is_empty() {
        lines.push(format!("These must hold before it can pass: {}.", failed.join("; ")));
    }
    let unknowns: Vec<&str> = checks.iter().flat_map(|c| &c.unknowns).map(String::as_str).collect();
    if !unknowns.is_empty() {
        lines.push(format!("Not compared, so it can't pass yet: {}. Make those parts exist and render, then check again.", unknowns.join(", ")));
    }
    if !open.is_empty() {
        let shown: Vec<String> = open.iter().take(8).map(|u| format!("{} ({})", u.question, u.id)).collect();
        lines.push(format!(
            "Your open questions: {}. Settle what one more look can and close it with core_unknown_edit (status resolved, the resolution and the evidence ids); say what's left in your summary.",
            shown.join("; ")
        ));
    }
    let pictures: Vec<String> = checks.iter().flat_map(|c| &c.artifacts).map(|p| p.display().to_string().replace('\\', "/")).collect();
    if !pictures.is_empty() {
        lines.push(format!("Pictures of your build (compare each with the original's in capture/ or reference/): {}", pictures.join(", ")));
    }
    lines.push(if checks.iter().all(|c| c.good(good_enough)) {
        "This would pass. Finish what you're doing, then reply.".to_string()
    } else {
        "Not good enough yet: fix what it lists, build again, and check again with rebuild_check.".to_string()
    });
    lines.join("\n")
}

impl Worker {
    /// Answer the builder's own check requests during its turn (once the build loop has started).
    pub(super) fn answer_self_checks(&mut self, ws: &mut Workspace) -> Result<(), ToolError> {
        let Some((kind, good_enough)) = self.self_check.clone() else { return Ok(()) };
        let asks = Inbox::new(asks_dir(&ws.root));
        for r in asks.pending() {
            self.step(ws, Step::Build, Status::Building, "The builder is checking its work against the original…")?;
            let (text, line) = match self.run_checks(ws, kind.as_ref(), SELF_CHECK_ROUND) {
                Ok(checks) => {
                    let line = format!("The builder checked its work: {}.", summary(&checks, good_enough));
                    (report(&checks, good_enough, &open_questions(ws)), line)
                }
                Err(e) if e.code == ErrorCode::Cancelled => return Err(e),
                Err(e) => (format!("The check couldn't run: {}", e.message), "The builder's check couldn't run.".to_string()),
            };
            asks.answer(&r.id, &Answer { text: Some(text), ..Default::default() })?;
            self.step(ws, Step::Build, Status::Building, &line)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_report_says_what_differs_and_whether_it_would_pass() {
        let web = CheckResult {
            similarity: Some(82.4),
            artifacts: vec![PathBuf::from("checks/round-0/screenshot-390.png")],
            ..CheckResult::new(CheckResult::WEB_VISUAL, SELF_CHECK_ROUND, true, "at 390 px: the page scrolls sideways (512 px wide)")
        };
        let r = report(std::slice::from_ref(&web), 90.0, &[]);
        assert!(r.contains("82% alike (needs 90%) — at 390 px: the page scrolls sideways") && r.contains("checks/round-0/screenshot-390.png"), "{r}");
        assert!(r.ends_with("check again with rebuild_check."), "{r}");
        let good = CheckResult { similarity: Some(93.0), ..web };
        assert!(report(&[good], 90.0, &[]).ends_with("This would pass. Finish what you're doing, then reply."));
        let build = CheckResult::new(CheckResult::BUILD, SELF_CHECK_ROUND, false, "Build failed: error[E0425]");
        let r = report(&[build], 90.0, &[]);
        assert!(r.starts_with("build: failed — Build failed") && r.contains("Not good enough yet"), "{r}");
        assert_eq!(report(&[], 90.0, &[]), "There was nothing to check yet.");
        let claim = |passed| craft_anything_engine::workspace::Claim::new("In play, the player moves", passed, "it doesn't");
        let game = [
            CheckResult::new(CheckResult::BUILD, 1, true, "Build succeeded."),
            CheckResult { claims: vec![claim(true), claim(true)], ..CheckResult::new("game-self-test", 1, true, "") },
            CheckResult::new("mechanics", 1, true, "app/mechanics.json has 15 values"),
        ];
        assert_eq!(summary(&game, 90.0), "all 3 checks pass, 2 of 2 claims hold");
        let failing = [game[0].clone(), CheckResult { claims: vec![claim(true), claim(false)], ..CheckResult::new("game-self-test", 1, false, "") }];
        assert_eq!(summary(&failing, 90.0), "1 of 2 checks pass, 1 of 2 claims hold");
        let site = [CheckResult { similarity: Some(93.4), ..CheckResult::new(CheckResult::WEB_VISUAL, 1, true, "") }];
        assert_eq!(summary(&site, 90.0), "about 93% like the original");
        let alike_but_broken = CheckResult {
            similarity: Some(96.0),
            claims: vec![craft_anything_engine::workspace::Claim::new("The start page loads every file it asks for", false, "/logo.png (404)")],
            ..CheckResult::new(CheckResult::WEB_VISUAL, 0, true, "")
        };
        let r = report(&[alike_but_broken], 90.0, &[]);
        assert!(
            r.contains("These must hold before it can pass: The start page loads every file it asks for (/logo.png (404))")
                && r.contains("Not good enough yet"),
            "{r}"
        );
        let blind = CheckResult {
            similarity: Some(95.0),
            unknowns: vec!["/about at 768 px couldn't be compared".into()],
            ..CheckResult::new(CheckResult::WEB_VISUAL, 0, true, "")
        };
        let r = report(&[blind], 90.0, &[]);
        assert!(r.contains("Not compared, so it can't pass yet: /about at 768 px") && r.contains("Not good enough yet"), "an unknown never passes: {r}");
    }

    #[test]
    fn the_builders_open_questions_are_read_from_the_project_and_reported() {
        use craft_anything_evidence::{Severity, Unknown, UnknownStatus};
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Arena", "Recreate this game", TargetRef::None).unwrap();
        assert!(open_questions(&ws).is_empty(), "no investigation folder yet");
        let project = Project::create(&ws.investigation_dir(), "Arena", Purpose::default()).unwrap();
        project.store_unknown(&Unknown::new("Jump height?", "game", Severity::Low)).unwrap();
        project.store_unknown(&Unknown::new("Which font is the menu set in?", "ui", Severity::High)).unwrap();
        let mut done = Unknown::new("Map size?", "game", Severity::Critical);
        done.status = UnknownStatus::Resolved;
        project.store_unknown(&done).unwrap();
        let open = open_questions(&ws);
        let questions: Vec<&str> = open.iter().map(|u| u.question.as_str()).collect();
        assert_eq!(questions, ["Which font is the menu set in?", "Jump height?"], "unresolved only, most severe first");
        let r = report(&[CheckResult::new(CheckResult::BUILD, 0, true, "Build succeeded.")], 90.0, &open);
        assert!(r.contains("Your open questions: Which font is the menu set in? (unk_") && r.contains("close it with core_unknown_edit"), "{r}");
    }

    #[test]
    fn a_project_is_marked_as_building_here_only_while_its_run_lasts() {
        let root = PathBuf::from("/projects/marked-here");
        assert!(!building_here(&root));
        let mark = BuildingHere::new(&root);
        assert!(building_here(&root));
        drop(mark);
        assert!(!building_here(&root));
    }
}
