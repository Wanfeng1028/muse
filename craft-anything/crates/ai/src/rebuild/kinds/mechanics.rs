//! Games (and apps decompiled in Deep mode) keep their numbers in `app/MECHANICS.md` for people and in `app/mechanics.json` for
//! checks ([`craft_anything_engine::mechanics`]). [`MechanicsCheck`] holds the build to the
//! sheet: it must exist and be readable, and every number in it must appear in the code as
//! written unless it's marked estimated (a value the code computes, or keeps in other units, is
//! written there as the sheet has it). The note also says which values have no source.

use super::*;
use craft_anything_engine::mechanics::{self, MechanicValue, SheetProblem};
use std::collections::HashSet;

/// What every game brief asks for, so the check can read the numbers.
pub const MECHANICS_CONTRACT: &str = "Keep the same values in app/mechanics.json, which Craft Anything reads after each build: {\"version\": 1, \"values\": [{\"name\": \"walk speed\", \"group\": \"movement\", \"value\": 4.5, \"unit\": \"m/s\", \"source\": \"function 0x140012a0\"}, {\"name\": \"crouch\", \"group\": \"controls\", \"value\": \"hold\", \"estimated\": true}]}. A value is a number, text or true/false; give each one its source or \"estimated\": true, and use the sheet's numbers in the code as they're written there.";

/// At most this many names are listed in a note.
const LISTED: usize = 8;
/// Code files bigger than this aren't read for numbers.
const MAX_FILE: u64 = 2 * 1024 * 1024;
/// Stop reading code after this much.
const MAX_CODE: u64 = 32 * 1024 * 1024;
const MAX_DEPTH: usize = 16;
/// Folders inside `app/` that hold builds, dependencies or tools' caches (Unreal's too), not the
/// builder's code; compared without case.
const SKIP_DIRS: [&str; 14] =
    ["target", "node_modules", "build", "dist", "bin", "obj", "library", "temp", "shots", "addons", "binaries", "intermediate", "saved", "deriveddatacache"];
/// Code and data files a number may be written in.
const CODE: [&str; 26] = [
    "rs", "gd", "cs", "c", "cc", "cpp", "h", "hpp", "js", "mjs", "ts", "py", "lua", "go", "java", "kt", "swift", "tres", "tscn", "cfg", "ini", "toml", "yaml",
    "yml", "json", "glsl",
];

pub struct MechanicsCheck;

impl MechanicsCheck {
    pub const ID: &'static str = "mechanics";
}

impl Check for MechanicsCheck {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        let round = cx.round;
        let sheet = match mechanics::read(&cx.ws.mechanics_path()) {
            Ok(s) => s,
            Err(p) => return Ok(CheckResult::new(self.id(), round, false, format!("{} {MECHANICS_CONTRACT}", problem_note(&p)))),
        };
        let found = numbers_in(&cx.ws.app_dir());
        let estimated = sheet.values.iter().filter(|v| v.estimated).count();
        let sourced = sheet.values.iter().filter(|v| !v.source.trim().is_empty()).count();
        let mut note = format!("app/mechanics.json has {} values ({sourced} with a source, {estimated} estimated).", sheet.values.len());
        let unsourced: Vec<&str> = sheet.values.iter().filter(|v| v.unsourced()).map(|v| v.name.as_str()).collect();
        if !unsourced.is_empty() {
            note.push_str(&format!(" {} have neither a source nor \"estimated\": {}.", unsourced.len(), listed(&unsourced)));
        }
        // An estimate may stay out of the code; a number found in the original must be used.
        let missing: Vec<String> = sheet
            .values
            .iter()
            .filter_map(|v| match v.value {
                MechanicValue::Number(n) if !v.estimated && !found.contains(&key(n)) => Some(format!("{} ({n})", v.name)),
                _ => None,
            })
            .collect();
        if !missing.is_empty() {
            let names: Vec<&str> = missing.iter().map(String::as_str).collect();
            note.push_str(&format!(
                " {} numbers from the original aren't in the code as written: {}. Use each in the code as the sheet writes it (build what uses it if it's missing), correct the sheet, or mark it \"estimated\" if it wasn't found in the original.",
                missing.len(),
                listed(&names)
            ));
        }
        // Each number found in the original is a claim of its own: it must be in the code.
        let claims = sheet
            .values
            .iter()
            .filter_map(|v| match v.value {
                MechanicValue::Number(n) if !v.estimated => Some(craft_anything_engine::workspace::Claim::new(
                    format!("{} ({n}) is used in the code", v.name),
                    found.contains(&key(n)),
                    "not in the code as written",
                )),
                _ => None,
            })
            .take(60)
            .collect();
        Ok(CheckResult { claims, ..CheckResult::new(self.id(), round, missing.is_empty(), note) })
    }
}

fn problem_note(p: &SheetProblem) -> String {
    match p {
        SheetProblem::Missing => "There's no app/mechanics.json yet.".into(),
        SheetProblem::TooLarge => format!("app/mechanics.json is over {} KB: keep it to the values that shape play.", mechanics::MAX_BYTES / 1024),
        SheetProblem::Unreadable(why) => format!("app/mechanics.json can't be read: {why}."),
        SheetProblem::Newer(v) => format!("app/mechanics.json says version {v}; this Craft Anything reads version {}.", mechanics::MECHANICS_VERSION),
        SheetProblem::Empty => "app/mechanics.json has no values.".into(),
    }
}

/// "a, b, c and 4 more".
fn listed(names: &[&str]) -> String {
    let shown = names.iter().take(LISTED).copied().collect::<Vec<_>>().join(", ");
    match names.len().saturating_sub(LISTED) {
        0 => shown,
        more => format!("{shown} and {more} more"),
    }
}

/// A number compared by its first seven significant digits, sign ignored (code often writes the
/// minus apart: `y -= 9.8`).
fn key(n: f64) -> String {
    format!("{:.6e}", n.abs())
}

/// Every number literal in the code and data files under `dir`.
fn numbers_in(dir: &Path) -> HashSet<String> {
    let mut found = HashSet::new();
    let mut budget = MAX_CODE;
    walk(dir, 0, &mut budget, &mut found);
    found
}

fn walk(dir: &Path, depth: usize, budget: &mut u64, found: &mut HashSet<String>) {
    if depth > MAX_DEPTH {
        return;
    }
    let Ok(rd) = std::fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let path = e.path();
        let name = e.file_name().to_string_lossy().into_owned();
        let Ok(ft) = e.file_type() else { continue };
        if ft.is_dir() {
            if !name.starts_with('.') && !SKIP_DIRS.contains(&name.to_ascii_lowercase().as_str()) {
                walk(&path, depth + 1, budget, found);
            }
            continue;
        }
        let code = path.extension().and_then(|x| x.to_str()).is_some_and(|x| CODE.contains(&x.to_ascii_lowercase().as_str()));
        if !ft.is_file() || !code || name == mechanics::MECHANICS {
            continue;
        }
        let Ok(len) = e.metadata().map(|m| m.len()) else { continue };
        if len > MAX_FILE || len > *budget {
            continue;
        }
        *budget -= len;
        if let Ok(bytes) = std::fs::read(&path) {
            literals(&bytes, found);
        }
    }
}

/// The number literals in some text: `4.5`, `.5`, `4.5f`, `1_000`, `1e-3`. Digits inside a word
/// (`vec3`, `x2`) aren't numbers.
fn literals(text: &[u8], found: &mut HashSet<String>) {
    let mut i = 0;
    while i < text.len() {
        let b = text.get(i).copied().unwrap_or(0);
        let starts = b.is_ascii_digit() || (b == b'.' && text.get(i + 1).is_some_and(u8::is_ascii_digit));
        let after_word = i > 0 && text.get(i - 1).is_some_and(|p| p.is_ascii_alphanumeric() || *p == b'_' || *p == b'.');
        if !starts || after_word {
            i += 1;
            continue;
        }
        let mut s = String::new();
        let mut j = i;
        while let Some(&c) = text.get(j) {
            if c.is_ascii_digit() || c == b'.' {
                s.push(char::from(c));
            } else if c != b'_' {
                break;
            }
            j += 1;
        }
        // An exponent: e5, e-3, E+2.
        if text.get(j).is_some_and(|c| *c == b'e' || *c == b'E') {
            let sign = usize::from(text.get(j + 1).is_some_and(|c| *c == b'+' || *c == b'-'));
            if text.get(j + 1 + sign).is_some_and(u8::is_ascii_digit) {
                s.push('e');
                if sign == 1 {
                    s.push(char::from(text.get(j + 1).copied().unwrap_or(b'+')));
                }
                j += 1 + sign;
                while let Some(&c) = text.get(j).filter(|c| c.is_ascii_digit()) {
                    s.push(char::from(c));
                    j += 1;
                }
            }
        }
        if let Ok(n) = s.trim_end_matches('.').parse::<f64>() {
            found.insert(key(n));
        }
        i = j.max(i + 1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn nums(text: &str) -> HashSet<String> {
        let mut found = HashSet::new();
        literals(text.as_bytes(), &mut found);
        found
    }

    #[test]
    fn number_literals_are_read_as_code_writes_them() {
        let f = nums("const WALK: f32 = 4.5; let g = -9.80; x = .25f; big = 1_000; tiny = 1e-3; v = vec3(0.0); p2 = 7.");
        for n in [4.5, 9.8, 0.25, 1000.0, 0.001, 0.0, 7.0] {
            assert!(f.contains(&key(n)), "{n} in {f:?}");
        }
        assert!(!f.contains(&key(3.0)) && !f.contains(&key(2.0)), "digits inside words aren't numbers: {f:?}");
        assert!(nums("1.2.3").contains(&key(1.2)) || nums("1.2.3").is_empty(), "a version string never panics");
    }

    #[test]
    fn notes_list_a_few_names() {
        let names: Vec<String> = (1..=10).map(|i| format!("v{i}")).collect();
        let refs: Vec<&str> = names.iter().map(String::as_str).collect();
        assert_eq!(listed(&refs), "v1, v2, v3, v4, v5, v6, v7, v8 and 2 more");
        assert_eq!(listed(&refs[..2]), "v1, v2");
    }

    #[test]
    fn code_is_read_apart_from_builds_and_the_sheet() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("main.rs"), "const JUMP: f32 = 1.25;").unwrap();
        std::fs::write(dir.path().join(mechanics::MECHANICS), r#"{"values": [{"name": "x", "value": 77.5}]}"#).unwrap();
        std::fs::create_dir_all(dir.path().join("target")).unwrap();
        std::fs::write(dir.path().join("target/gen.rs"), "33.5").unwrap();
        std::fs::create_dir_all(dir.path().join("Intermediate")).unwrap();
        std::fs::write(dir.path().join("Intermediate/Game.gen.cpp"), "55.5").unwrap();
        std::fs::write(dir.path().join("notes.txt"), "44.5").unwrap();
        let f = numbers_in(dir.path());
        assert!(f.contains(&key(1.25)));
        for n in [77.5, 33.5, 44.5, 55.5] {
            assert!(!f.contains(&key(n)), "{n}: the sheet, builds and other files aren't code");
        }
    }
}
