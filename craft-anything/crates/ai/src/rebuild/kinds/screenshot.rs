//! Apps and games can't be photographed from outside the way a website can, so the brief asks the
//! builder for a `--screenshot <file.png>` option (draw about 120 frames, save the screen, exit).
//! [`ScreenshotCheck`] holds the build to it: it starts the finished program with that option,
//! and the build passes only with a picture that isn't blank. When the person added pictures of
//! the original, the note says how alike the result looks to the closest one (advisory for now:
//! it doesn't decide when to stop refining). When Study pictured the original running (runtime
//! study), the build is also started normally and pictured the same way: the note adds how alike
//! the two windows look and which of the original's labelled controls the build lacks.

use super::*;
use craft_anything_engine::tools::web_common::{Image, decode_picture, decode_png, perceptual_similarity, resize};
use craft_anything_engine::workspace::Claim;
use craft_anything_platform::process::Process;

/// What every app and game brief asks for, so the check can see the result.
pub const SCREENSHOT_CONTRACT: &str = "Give the program a `--screenshot <file.png>` option: start normally, draw about 120 frames, save the window's picture as a PNG to that file and exit. Craft Anything runs it that way after each build to check the result, and a build without the option, or with a blank picture, doesn't pass. Try it yourself: run it with a file inside app/ (for example app/shots/now.png) and look at the picture.";

/// How long the program may take to start, draw and save its picture (or play its self-test).
const RUN_LIMIT: Duration = Duration::from_secs(90);
/// The size both pictures are brought to before comparing.
const COMPARE: (u32, u32) = (640, 360);

pub struct ScreenshotCheck;

impl Check for ScreenshotCheck {
    fn id(&self) -> &'static str {
        "app-screenshot"
    }

    /// A console program draws no window: its runs are compared instead ([`super::runs`]).
    fn applies(&self, cx: &CheckCx) -> bool {
        super::runs::captured(cx.ws).is_empty()
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        let (ws, round) = (cx.ws, cx.round);
        let dir = ws.checks_dir().join(format!("round-{round}"));
        let shot = dir.join("screenshot.png");
        let (bytes, program, base_args) = match run_with(cx, "--screenshot", &shot)? {
            OwnRun::NoProgram => return Ok(CheckResult::new(self.id(), round, false, NO_PROGRAM)),
            OwnRun::NoFile(why) => {
                return Ok(CheckResult::new(
                    self.id(),
                    round,
                    false,
                    format!("The program didn't save a picture with --screenshot.{why} {SCREENSHOT_CONTRACT}"),
                ));
            }
            OwnRun::Saved { bytes, program, args } => (bytes, program, args),
        };
        let mut artifacts: Vec<PathBuf> = shot.strip_prefix(&ws.root).ok().map(Path::to_path_buf).into_iter().collect();
        let img = match decode_png(&bytes) {
            Ok(i) => i,
            Err(e) => {
                return Ok(CheckResult {
                    artifacts,
                    ..CheckResult::new(self.id(), round, false, format!("The --screenshot file isn't a readable PNG: {}", e.message))
                });
            }
        };
        if is_blank(&img) {
            return Ok(CheckResult {
                artifacts,
                ..CheckResult::new(
                    self.id(),
                    round,
                    false,
                    "The program's screenshot is blank (one colour): nothing was drawn. Make sure it draws its first frames before saving.",
                )
            });
        }
        // The person's pictures, and the picture of the original running (runtime study).
        let mut pictures = ws.references();
        pictures.extend(Some(ws.capture_dir().join("window.png")).filter(|p| p.is_file()));
        let bar = cx.build_settings().picture_good_enough;
        let mut similarity = None;
        let note = match picture_likeness(&img, &pictures) {
            Likeness::Best { score, name } => {
                // With a bar set (`build.picture_good_enough`), the likeness decides when to stop.
                if bar.is_some() {
                    similarity = Some(score);
                }
                format!("The program starts and draws ({}×{}). It looks about {score:.0}% like {name}.", img.width, img.height)
            }
            Likeness::Unreadable => format!(
                "The program starts and draws ({}×{}). The person's pictures couldn't be read (PNG, JPEG, WebP or GIF), so they weren't compared.",
                img.width, img.height
            ),
            Likeness::NoPictures => format!("The program starts and draws ({}×{}).", img.width, img.height),
        };
        let (running, claims) = running_note(cx, &program, &base_args, &dir);
        let note = note + &running;
        artifacts.extend(dir.join("window.png").strip_prefix(&ws.root).ok().map(Path::to_path_buf).filter(|p| ws.root.join(p).is_file()));
        Ok(CheckResult { artifacts, similarity, good_enough: bar, claims, ..CheckResult::new(self.id(), round, true, note) })
    }
}

/// Start the build normally and picture it the way Study pictured the original, when it did
/// (`capture/window.png`, and `capture/ui-tree.json` when its controls were read): how alike the
/// windows look and the controls are, and a claim for each of the original's interactive
/// controls ([`control_claims`]). Empty when there's nothing to compare with.
fn running_note(cx: &CheckCx, program: &Path, args: &[String], dir: &Path) -> (String, Vec<Claim>) {
    let capture = cx.ws.capture_dir();
    let (original, original_tree) = (capture.join("window.png"), capture.join("ui-tree.json"));
    if !original.is_file() {
        return (String::new(), Vec::new());
    }
    let (shot, tree) = (dir.join("window.png"), dir.join("ui-tree.json"));
    let mut params = json!({"program": program, "args": args, "wait_secs": 15, "output": &shot});
    if original_tree.is_file() {
        params["ui_tree"] = json!(&tree);
    }
    if let Err(e) = cx.call("native_window_capture", params) {
        return (format!(" Started normally, its window couldn't be pictured: {}", e.message), Vec::new());
    }
    let mut out = String::new();
    if let Some(img) = std::fs::read(&shot).ok().and_then(|b| decode_png(&b).ok())
        && let Likeness::Best { score, .. } = picture_likeness(&img, &[original])
    {
        out.push_str(&format!(" Started normally, its window looks about {score:.0}% like the original's (capture/window.png)."));
    }
    let read = |p: &Path| std::fs::read(p).ok().and_then(|b| serde_json::from_slice::<Value>(&b).ok());
    let mut claims = Vec::new();
    if let (Some(o), Some(b)) = (read(&original_tree), read(&tree)) {
        if let Some(c) = controls_likeness(&o, &b) {
            out.push_str(&format!(" {}", c.note()));
        }
        claims = control_claims(&o, &b);
    }
    (out, claims)
}

/// The roles of controls a person uses (lower case, macOS's `AX` prefix removed): each of the
/// original's must be in the build. Text and other labels may hold content the builder replaces
/// with placeholders, so they stay advisory.
const INTERACTIVE: &[&str] = &[
    "button",
    "splitbutton",
    "togglebutton",
    "menu",
    "menubaritem",
    "menuitem",
    "menubutton",
    "tab",
    "tabitem",
    "checkbox",
    "radiobutton",
    "combobox",
    "popupbutton",
    "edit",
    "textfield",
    "hyperlink",
    "link",
    "slider",
];

/// A claim for each of the original's labelled interactive controls (each label once, at most
/// 20): the build has a control with the same label, whatever its role.
pub fn control_claims(original: &Value, built: &Value) -> Vec<Claim> {
    let ours: std::collections::BTreeSet<String> = labelled(built).into_iter().map(|(key, ..)| key).collect();
    let mut seen = std::collections::BTreeSet::new();
    labelled(original)
        .into_iter()
        .filter(|(key, _, role)| INTERACTIVE.contains(&role.as_str()) && seen.insert(key.clone()))
        .take(20)
        .map(|(key, shown, role)| Claim::new(format!("It has the original's \"{shown}\" {role}"), ours.contains(&key), "no control with that label"))
        .collect()
}

/// How alike two UI trees' labelled controls are (`ui-tree.json`: `nodes` with `role` and `title`).
#[derive(Debug, Clone, PartialEq)]
pub struct ControlsLikeness {
    /// 0..=100: the labels both have, over all labels of both (Dice over label counts).
    pub similarity: f64,
    /// The original's controls the build has no label for, as `"Copy" (button)`, in tree order
    /// (at most 8).
    pub missing: Vec<String>,
}

/// A UI tree's labelled controls as (label to compare, label to show, role). Labels are compared
/// without case, spacing, `&` mnemonics or a trailing colon; roles lose macOS's `AX` prefix.
fn labelled(tree: &Value) -> Vec<(String, String, String)> {
    let nodes = tree.get("nodes").and_then(Value::as_array).into_iter().flatten();
    nodes
        .filter_map(|n| {
            let shown = n.get("title").and_then(Value::as_str)?.replace('&', "").split_whitespace().collect::<Vec<_>>().join(" ");
            let key = shown.trim_end_matches(':').trim().to_lowercase();
            let role = n.get("role").and_then(Value::as_str).unwrap_or_default();
            (!key.is_empty()).then(|| (key, shown, role.strip_prefix("AX").unwrap_or(role).to_lowercase()))
        })
        .collect()
}

/// Compare the labelled controls of the original's UI tree with the build's. None when the
/// original has fewer than 3 (a game or a window that draws its own controls says little here).
pub fn controls_likeness(original: &Value, built: &Value) -> Option<ControlsLikeness> {
    let (a, b) = (labelled(original), labelled(built));
    if a.len() < 3 {
        return None;
    }
    let mut left = std::collections::BTreeMap::<&str, usize>::new();
    for (key, ..) in &b {
        *left.entry(key).or_default() += 1;
    }
    let (mut shared, mut missing) = (0, Vec::new());
    for (key, shown, role) in &a {
        match left.get_mut(key.as_str()) {
            Some(n) if *n > 0 => {
                *n -= 1;
                shared += 1;
            }
            _ if missing.len() < 8 => missing.push(format!("\"{shown}\" ({role})")),
            _ => {}
        }
    }
    Some(ControlsLikeness { similarity: 200.0 * shared as f64 / (a.len() + b.len()) as f64, missing })
}

impl ControlsLikeness {
    /// One sentence for the check's note.
    pub fn note(&self) -> String {
        let mut s = format!("Its controls are {:.0}% alike by their labels", self.similarity);
        if !self.missing.is_empty() {
            s.push_str(&format!("; the original also has {}", self.missing.join(", ")));
        }
        s.push('.');
        s
    }
}

/// The arguments that ask the program for one of its own options (`--screenshot <file>`); a
/// Godot project passes its own after `--`.
pub fn option_args(godot_project: bool, option: &str, file: &Path) -> Vec<String> {
    let mut v = Vec::new();
    if godot_project {
        v.push("--".to_string());
    }
    v.push(option.to_string());
    v.push(file.display().to_string());
    v
}

/// What a run of the built program with one of its own options left behind.
pub(super) enum OwnRun {
    /// Nothing is built to start yet.
    NoProgram,
    /// It ran but saved no file: why, as a sentence starting with a space (or empty).
    NoFile(String),
    /// The file it saved, and how the program is started without the option.
    Saved { bytes: Vec<u8>, program: PathBuf, args: Vec<String> },
}

pub(super) const NO_PROGRAM: &str = "There's no built program to start yet.";

/// Start the built program with `option <file>` and read back the file it saved (an old one is
/// removed first, so only this run's counts).
pub(super) fn run_with(cx: &CheckCx, option: &str, file: &Path) -> Result<OwnRun, ToolError> {
    let app = cx.ws.app_dir();
    let godot = cx.godot();
    let Some((program, args)) = launch(&app, godot.as_deref()) else { return Ok(OwnRun::NoProgram) };
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    }
    let _ = std::fs::remove_file(file);
    let mut with = args.clone();
    with.extend(option_args(godot.is_some() && app.join("project.godot").is_file(), option, file));
    let stop = cx.stop().clone();
    let out = Process::new(&program).args(&with).cwd(&app).timeout(RUN_LIMIT).stdout_cap(256 * 1024).cancel_when(move || stop.is_cancelled()).run();
    let Ok(bytes) = std::fs::read(file) else {
        let why = match &out {
            Ok(o) if !o.success => {
                format!(" It exited with {}: {}", o.code.map_or("an error".into(), |c| format!("code {c}")), last_lines(&o.stderr_text(), &o.stdout_text()))
            }
            Err(e) => format!(" {}", e.message),
            Ok(_) => String::new(),
        };
        return Ok(OwnRun::NoFile(why));
    };
    Ok(OwnRun::Saved { bytes, program, args })
}

/// Nothing drawn: almost every pixel the same brightness.
pub fn is_blank(img: &Image) -> bool {
    let small = resize(img, 64, 36);
    let lumas: Vec<f64> =
        small.rgba.as_chunks::<4>().0.iter().map(|[r, g, b, _]| 0.299 * f64::from(*r) + 0.587 * f64::from(*g) + 0.114 * f64::from(*b)).collect();
    let n = lumas.len().max(1) as f64;
    let mean = lumas.iter().sum::<f64>() / n;
    let var = lumas.iter().map(|l| (l - mean).powi(2)).sum::<f64>() / n;
    var.sqrt() < 2.0
}

/// How the result compares with the person's pictures.
#[derive(Debug, PartialEq)]
pub enum Likeness {
    Best {
        score: f64,
        name: String,
    },
    /// None of the pictures could be decoded.
    Unreadable,
    NoPictures,
}

/// The closest of the person's pictures (PNG, JPEG, WebP or GIF): the mean of perceptual detail and coarse layout,
/// both pictures brought to the same size first.
pub fn picture_likeness(shot: &Image, pictures: &[PathBuf]) -> Likeness {
    if pictures.is_empty() {
        return Likeness::NoPictures;
    }
    let a = resize(shot, COMPARE.0, COMPARE.1);
    let mut best: Option<(f64, String)> = None;
    for p in pictures {
        let Some(b) = std::fs::read(p).ok().and_then(|bytes| decode_picture(&bytes).ok()) else { continue };
        let b = resize(&b, COMPARE.0, COMPARE.1);
        let detail = perceptual_similarity(&a, &b);
        let layout = craft_anything_engine::tools::web_common::block_similarity(&a, &b, 16, 24);
        let score = (detail + layout) * 50.0;
        // "reference/picture-1.png", or "capture/window.png" for the original running.
        let folder = p.parent().and_then(|d| d.file_name()).map(|d| d.to_string_lossy().into_owned()).unwrap_or_default();
        let name = p.file_name().map(|n| format!("{folder}/{}", n.to_string_lossy())).unwrap_or_default();
        if best.as_ref().is_none_or(|(s, _)| score > *s) {
            best = Some((score, name));
        }
    }
    match best {
        Some((score, name)) => Likeness::Best { score, name },
        None => Likeness::Unreadable,
    }
}

fn last_lines(stderr: &str, stdout: &str) -> String {
    let text = if stderr.trim().is_empty() { stdout } else { stderr };
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    lines.get(lines.len().saturating_sub(6)..).unwrap_or_default().join(" / ")
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_engine::tools::web_common::encode_png;

    fn img(w: u32, h: u32, f: &dyn Fn(u32, u32) -> [u8; 3]) -> Image {
        let mut rgba = Vec::new();
        for y in 0..h {
            for x in 0..w {
                let [r, g, b] = f(x, y);
                rgba.extend_from_slice(&[r, g, b, 255]);
            }
        }
        Image { width: w, height: h, rgba }
    }

    #[test]
    fn a_godot_project_gets_its_screenshot_flag_after_a_double_dash() {
        let p = Path::new("/p/checks/round-1/screenshot.png");
        assert_eq!(option_args(false, "--screenshot", p), ["--screenshot", "/p/checks/round-1/screenshot.png"]);
        assert_eq!(option_args(true, "--screenshot", p).first().map(String::as_str), Some("--"));
    }

    #[test]
    fn blank_pictures_fail_and_the_closest_reference_is_named() {
        assert!(is_blank(&img(320, 180, &|_, _| [10, 10, 10])));
        let scene = img(320, 180, &|x, y| if (x / 20 + y / 20) % 2 == 0 { [200, 40, 40] } else { [20, 20, 120] });
        assert!(!is_blank(&scene));
        assert_eq!(picture_likeness(&scene, &[]), Likeness::NoPictures);
        let d = tempfile::tempdir().unwrap();
        let refs = d.path().join("reference");
        std::fs::create_dir_all(&refs).unwrap();
        let same = refs.join("picture-1.png");
        let other = refs.join("picture-2.png");
        let broken = refs.join("picture-3.jpg");
        std::fs::write(&same, encode_png(&resize(&scene, 640, 360)).unwrap()).unwrap();
        std::fs::write(&other, encode_png(&img(640, 360, &|x, _| [(x % 256) as u8, 0, 0])).unwrap()).unwrap();
        std::fs::write(&broken, b"not a picture").unwrap();
        match picture_likeness(&scene, &[other.clone(), same, broken.clone()]) {
            Likeness::Best { score, name } => {
                assert_eq!(name, "reference/picture-1.png");
                assert!(score > 90.0, "{score}");
            }
            l => panic!("{l:?}"),
        }
        assert_eq!(picture_likeness(&scene, &[broken]), Likeness::Unreadable);
    }

    #[test]
    fn resize_keeps_the_picture() {
        let half = img(4, 2, &|x, _| if x < 2 { [0, 0, 0] } else { [255, 255, 255] });
        let small = resize(&half, 2, 1);
        assert_eq!(small.rgba, [0, 0, 0, 255, 255, 255, 255, 255]);
        let back = decode_png(&encode_png(&half).unwrap()).unwrap();
        assert_eq!(back.rgba, half.rgba, "encode and decode round-trip");
    }
}
