//! `secrets [--history]`: refuse API keys, private keys, secret-looking environment values and
//! the local home folder in the files git would commit (tracked plus untracked, not ignored), or,
//! with `--history`, in every commit. A line holding `secret-scan: allow` is skipped (for
//! deliberate fixtures that can't be split up).

use std::path::Path;
use std::process::Command;

/// Token prefixes and the shortest run of key characters that follows a real one.
const PREFIXES: &[(&str, usize)] = &[
    ("sk-ant-", 20),
    ("sk-proj-", 20),
    ("sk-or-v1-", 20),
    ("AKIA", 16),
    ("ASIA", 16),
    ("AIza", 30),
    ("ghp_", 30),
    ("gho_", 30),
    ("ghs_", 30),
    ("github_pat_", 30),
    ("glpat-", 20),
    ("xoxb-", 10),
    ("xoxp-", 10),
    ("hf_", 30),
    ("r8_", 30),
    ("sk_live_", 20),
];

/// Files that hold secrets or local state, never committed.
const FORBIDDEN_NAMES: &[&str] = &[".env", ".netrc", ".npmrc", "id_rsa", "id_ed25519", "settings.local.json", "credentials.json"];
const FORBIDDEN_EXT: &[&str] = &["pem", "p12", "pfx", "key", "keystore", "jks"];
const FORBIDDEN_DIRS: &[&str] = &["log/", "plan/", "plans/"];

/// Larger files aren't read (lockfiles and fixtures stay well under it).
const MAX_FILE: u64 = 4 * 1024 * 1024;
const ALLOW: &str = "secret-scan: allow";
/// Made-up fixtures already in history (a truncated key in the firmware scanner's test).
const KNOWN_FAKES: &[&str] = &["MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu"];

pub fn secrets(root: &Path, history: bool) -> bool {
    let env = env_values();
    let mut found = Vec::new();
    if history {
        let Some(log) = git(root, &["log", "--all", "-p", "--no-color", "--format=commit %H"]) else { return false };
        let mut commit = String::new();
        for line in log.lines() {
            if let Some(c) = line.strip_prefix("commit ") {
                commit = c.chars().take(10).collect();
            } else if line.starts_with('+') && !line.starts_with("+++") {
                for why in line_problems(line, &env) {
                    found.push(format!("commit {commit}: {why}"));
                }
            } else if let Some(p) = line.strip_prefix("+++ b/")
                && let Some(why) = path_problem(p)
            {
                found.push(format!("commit {commit}: {why}"));
            }
        }
    } else {
        let Some(list) = git(root, &["ls-files", "-z", "--cached", "--others", "--exclude-standard"]) else { return false };
        for rel in list.split('\0').filter(|p| !p.is_empty()) {
            if let Some(why) = path_problem(rel) {
                found.push(why);
            }
            let path = root.join(rel);
            if std::fs::metadata(&path).map_or(true, |m| m.len() > MAX_FILE) {
                continue;
            }
            let Ok(bytes) = std::fs::read(&path) else { continue };
            let text = String::from_utf8_lossy(&bytes);
            for (n, line) in text.lines().enumerate() {
                for why in line_problems(line, &env) {
                    found.push(format!("{rel}:{}: {why}", n + 1));
                }
            }
        }
    }
    if found.is_empty() {
        println!("secrets: ok{}", if history { " (all history)" } else { "" });
        return true;
    }
    for f in &found {
        eprintln!("secrets: {f}");
    }
    eprintln!("secrets: {} problem(s). Remove them (and rotate any real key); fixtures use obvious fakes like \"sk-test\".", found.len());
    false
}

fn git(root: &Path, args: &[&str]) -> Option<String> {
    match Command::new("git").args(args).current_dir(root).output() {
        Ok(o) if o.status.success() => Some(String::from_utf8_lossy(&o.stdout).into_owned()),
        Ok(o) => {
            eprintln!("git {} failed: {}", args.join(" "), String::from_utf8_lossy(&o.stderr).trim());
            None
        }
        Err(e) => {
            eprintln!("can't run git: {e}");
            None
        }
    }
}

/// Values of this machine's environment that would be a leak in a file: secret-named variables
/// and the home folder.
fn env_values() -> Vec<(String, String)> {
    let mut v = Vec::new();
    for (k, val) in std::env::vars() {
        let up = k.to_ascii_uppercase();
        let secret = ["KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "AUTH"].iter().any(|w| up.contains(w));
        if secret && val.len() >= 12 && !val.contains(['/', '\\']) {
            v.push((k, val));
        }
    }
    for k in ["USERPROFILE", "HOME"] {
        if let Ok(home) = std::env::var(k) {
            // Only a real person's folder: "/root" or "C:\" aren't personal.
            if home.len() > 6 {
                v.push((k.to_string(), home.replace('\\', "/")));
                v.push((k.to_string(), home.clone()));
            }
        }
    }
    v
}

fn path_problem(rel: &str) -> Option<String> {
    let name = rel.rsplit('/').next().unwrap_or(rel);
    let ext = name.rsplit_once('.').map(|(_, e)| e.to_ascii_lowercase());
    let bad = FORBIDDEN_NAMES.iter().any(|f| name == *f || (name.starts_with(".env.") && *f == ".env"))
        || ext.as_deref().is_some_and(|e| FORBIDDEN_EXT.contains(&e))
        || FORBIDDEN_DIRS.iter().any(|d| rel.starts_with(d));
    bad.then(|| format!("{rel}: a file of secrets or local notes; it must not be committed"))
}

fn line_problems(line: &str, env: &[(String, String)]) -> Vec<String> {
    if line.contains(ALLOW) {
        return Vec::new();
    }
    let mut out = Vec::new();
    for (prefix, min) in PREFIXES {
        let mut rest = line;
        while let Some(i) = rest.find(prefix) {
            let before_ok = rest[..i].chars().next_back().is_none_or(|c| !c.is_ascii_alphanumeric());
            let tail = &rest[i + prefix.len()..];
            let run = tail.chars().take_while(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-').count();
            if before_ok && run >= *min {
                out.push(format!("looks like an API key ({prefix}…)"));
                break;
            }
            rest = tail;
        }
    }
    if private_key(line) && !KNOWN_FAKES.iter().any(|f| line.contains(f)) {
        out.push("a private key".into());
    }
    if fal_key(line) {
        out.push("looks like a fal.ai key (id:secret)".into());
    }
    for (k, val) in env {
        if line.contains(val.as_str()) {
            out.push(format!("holds this machine's ${k}"));
        }
    }
    out
}

/// The PEM header of a private key (`BEGIN`, capital words, `PRIVATE KEY`) written in one piece.
fn private_key(line: &str) -> bool {
    line.match_indices("-----BEGIN ").any(|(i, m)| {
        let rest = &line[i + m.len()..];
        rest.find("-----").is_some_and(|end| {
            let words = &rest[..end];
            words.ends_with("PRIVATE KEY") && words.chars().all(|c| c.is_ascii_uppercase() || c == ' ')
        })
    })
}

/// `uuid:32-hex`, the shape of a fal.ai key.
fn fal_key(line: &str) -> bool {
    let b = line.as_bytes();
    let hex = |s: &[u8]| s.iter().all(u8::is_ascii_hexdigit);
    b.windows(36 + 1 + 32).any(|w| {
        let (id, rest) = w.split_at(36);
        let dashes = [8, 13, 18, 23].iter().all(|&i| id.get(i) == Some(&b'-'));
        let parts = id.split(|c| *c == b'-').all(hex);
        dashes && parts && rest.first() == Some(&b':') && hex(&rest[1..])
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_keys_and_lets_fakes_through() {
        let env = vec![("MY_TOKEN".to_string(), "abcdefghijklmnop".to_string())];
        let key = format!("{}{}", "sk-ant-", "a".repeat(30));
        assert!(!line_problems(&format!("let k = \"{key}\";"), &[]).is_empty());
        assert!(line_problems("s.set(\"Claude\", \"sk-test-123\")", &[]).is_empty());
        assert!(line_problems("name = \"phf_shared\"", &[]).is_empty());
        assert!(!line_problems(&format!("{}{}", "-----BEGIN RSA ", "PRIVATE KEY-----"), &[]).is_empty());
        let fal = format!("{}:{}", "12345678-1234-1234-1234-123456789abc", "0".repeat(32));
        assert!(!line_problems(&fal, &[]).is_empty());
        assert!(!line_problems("x = abcdefghijklmnop", &env).is_empty(), "an env secret's value");
        assert!(line_problems(&format!("{key} // {ALLOW}"), &[]).is_empty());
        assert!(path_problem(".env").is_some() && path_problem("a/.env.local").is_some() && path_problem("log/devlog.md").is_some());
        assert!(path_problem("certs/server.pem").is_some() && path_problem(".claude/settings.local.json").is_some());
        assert!(path_problem("crates/ai/src/keys.rs").is_none() && path_problem("docs/environment.md").is_none());
    }
}
