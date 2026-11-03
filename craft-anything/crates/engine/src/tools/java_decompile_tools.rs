//! Java decompiled to source by Vineflower (Apache-2.0), run as an external program: its JAR with
//! the configured Java, or a `vineflower` wrapper script. It writes sources into a private temp
//! folder (plain `.java` files, or a sources archive for a JAR input), which is read back and
//! removed.

use super::artifact_tools::fresh_temp_dir;
use super::external_disasm_tools::{input_file, locate, run};
use super::native_common::{params_json, spec};
use super::static_input::builder;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, ToolError};
use craft_anything_formats::zip;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "java_vineflower_decompile",
        "Decompile Java with Vineflower",
        "Decompile a Java .class file or JAR (absolute path or the active target) to Java source with Vineflower, run as a program (its .jar with the configured Java, or a vineflower script; set its path in Settings → Engines). Without class: the decompiled source files with their line counts, paged with offset/limit (and the source itself when there is one file). With class (com.example.Foo or com/example/Foo): that class's source, paged by lines; inner classes are inside their outer class's file. Optional engine.",
        "Turn compiled Java back into readable source code.",
        Toolset::Java,
        Effects::LAUNCHES_PROCESS | Effects::WRITES_FILESYSTEM,
        Requires::Engine("vineflower"),
        schema_of::<Params>,
        java_vineflower_decompile,
    )]
}

fn d_limit() -> usize {
    2000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Params {
    /// Absolute path of a .class or .jar; omit to use the active target.
    #[serde(default)]
    pub path: Option<String>,
    /// One class to show (com.example.Foo or com/example/Foo).
    #[serde(default)]
    pub class: Option<String>,
    /// First file (or, with class, first line) of the page.
    #[serde(default)]
    pub offset: usize,
    /// Files or lines per page (1–20000, default 2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

/// Sources read back per run.
const MAX_FILES: usize = 50_000;
const MAX_TOTAL: u64 = 256 << 20;

/// Removes the output folder however the tool ends.
struct TempDir(PathBuf);

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

/// The decompiled sources Vineflower left in `dir`: `.java` files, and `.java` entries of any
/// sources archive, as (path with `/`, text). True when a cap stopped the reading.
fn read_sources(dir: &Path) -> (Vec<(String, String)>, bool) {
    let mut out = Vec::new();
    let mut total = 0u64;
    let mut capped = false;
    let mut stack = vec![(dir.to_path_buf(), 0usize)];
    while let Some((d, depth)) = stack.pop() {
        let Ok(rd) = std::fs::read_dir(&d) else { continue };
        for entry in rd.flatten() {
            let p = entry.path();
            if p.is_dir() {
                if depth < 64 {
                    stack.push((p, depth + 1));
                }
                continue;
            }
            if out.len() >= MAX_FILES || total >= MAX_TOTAL {
                capped = true;
                continue;
            }
            let ext = p.extension().and_then(|e| e.to_str()).map(str::to_ascii_lowercase);
            match ext.as_deref() {
                Some("java") => {
                    let Ok(text) = std::fs::read_to_string(&p) else { continue };
                    total += text.len() as u64;
                    let rel = p.strip_prefix(dir).unwrap_or(&p).to_string_lossy().replace('\\', "/");
                    out.push((rel, text));
                }
                Some("jar" | "zip") => {
                    let Ok(bytes) = std::fs::read(&p) else { continue };
                    let Ok(archive) = zip::parse(&bytes, MAX_FILES) else { continue };
                    for e in archive.entries.iter().filter(|e| !e.is_dir && e.name.ends_with(".java")) {
                        if out.len() >= MAX_FILES || total >= MAX_TOTAL {
                            capped = true;
                            break;
                        }
                        let Ok(data) = zip::read_entry(&bytes, e, MAX_TOTAL - total) else { continue };
                        total += data.len() as u64;
                        out.push((e.name.clone(), String::from_utf8_lossy(&data).into_owned()));
                    }
                }
                _ => {}
            }
        }
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    (out, capped)
}

/// The file holding `class` (`com.example.Foo` or `com/example/Foo`, optionally with `.java`).
fn find_class<'a>(sources: &'a [(String, String)], class: &str) -> Option<&'a (String, String)> {
    let want = class.trim().trim_end_matches(".java").trim_end_matches(".class").replace('.', "/");
    let want = format!("{}.java", want.trim_start_matches('/'));
    sources.iter().find(|(name, _)| name == &want || name.ends_with(&format!("/{want}")))
}

fn java_vineflower_decompile(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: Params = parse_params(params)?;
    let (file, subject) = input_file(ctx, p.path.as_deref())?;
    let vineflower = locate(ctx, "vineflower")?;
    let out_dir = TempDir(fresh_temp_dir("craft-anything-vineflower")?);
    let (exe, mut args) = super::external_disasm_tools::program_for(ctx, &vineflower)?;
    args.extend([file.display().to_string(), out_dir.0.display().to_string()]);
    ctx.report(None, "Decompiling with Vineflower");
    let out = run(ctx, &exe, &args, "vineflower")?;
    let (sources, capped) = read_sources(&out_dir.0);
    if sources.is_empty() {
        let mut err = craft_anything_platform::process::nonzero_error("vineflower", &out);
        if out.success {
            err = ToolError::invalid("Vineflower produced no Java source").with_remediation("Pass a .class file or a JAR with classes in it.");
        }
        return Err(err);
    }
    let limit = p.limit.clamp(1, 20_000);
    let mut lims = vec![Limitation::new(
        "decompiled",
        "Decompiled source is a reconstruction: names of local variables, comments and some constructs (lambdas, switch on strings, synthetic code) may differ from the original.",
    )];
    if capped {
        lims.push(Limitation::new("output_capped", "More than 50,000 files or 256 MiB of source came back; the rest were left out."));
    }
    if !out.success {
        lims.push(Limitation::new("nonzero_exit", format!("Vineflower exited with {:?}; some classes may be missing.", out.code)));
    }
    let base = json!({"tool": exe, "arguments": args, "exit_code": out.code, "files": sources.len()});
    let (result, summary, coverage) = match p.class.as_deref() {
        Some(class) => {
            let (name, text) = find_class(&sources, class).ok_or_else(|| {
                ToolError::invalid(format!("no decompiled source for class {class}")).with_remediation("Call without class to list the decompiled files.")
            })?;
            let total = text.lines().count();
            let page: Vec<&str> = text.lines().skip(p.offset).take(limit).collect();
            let mut r = base;
            r["file"] = json!(name);
            r["total_lines"] = json!(total);
            r["source"] = json!(page.join("\n"));
            (r, format!("Vineflower: {name}, {total} lines."), Coverage::page(page.len() as u64, total as u64, p.offset as u64))
        }
        None => {
            let page: Vec<Value> = sources.iter().skip(p.offset).take(limit).map(|(n, t)| json!({"file": n, "lines": t.lines().count()})).collect();
            let mut r = base;
            r["sources"] = json!(page);
            if let [(name, text)] = sources.as_slice() {
                r["file"] = json!(name);
                r["source"] = json!(text);
            }
            (r, format!("Vineflower decompiled {} source file(s).", sources.len()), Coverage::page(page.len() as u64, sources.len() as u64, p.offset as u64))
        }
    };
    let e = builder(ctx, "java_vineflower_decompile", subject, params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Inferred)
        .authority(Authority::OutsideService)
        .limitations(lims)
        .coverage(coverage)
        .build()?;
    Ok(ToolOutput::evidence(e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};

    #[test]
    fn reads_plain_files_and_source_archives() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("com/example")).unwrap();
        std::fs::write(dir.path().join("com/example/Foo.java"), "class Foo {\n}\n").unwrap();
        std::fs::write(dir.path().join("notes.txt"), "not source").unwrap();
        let zip_bytes =
            craft_anything_testkit::electron::zip_stored(&[("org/demo/Bar.java", b"class Bar {}\n".as_slice()), ("META-INF/MANIFEST.MF", b"x".as_slice())]);
        std::fs::write(dir.path().join("app.jar"), zip_bytes).unwrap();
        let (s, capped) = read_sources(dir.path());
        assert!(!capped);
        let names: Vec<&str> = s.iter().map(|(n, _)| n.as_str()).collect();
        assert_eq!(names, ["com/example/Foo.java", "org/demo/Bar.java"]);
        assert_eq!(find_class(&s, "com.example.Foo").map(|f| f.0.as_str()), Some("com/example/Foo.java"));
        assert_eq!(find_class(&s, "org/demo/Bar").map(|f| f.1.as_str()), Some("class Bar {}\n"));
        assert!(find_class(&s, "Foo2").is_none());
    }

    #[test]
    fn needs_vineflower_and_an_input() {
        let e = Engine::new(crate::testing::session());
        assert!(e.call("java_vineflower_decompile", json!({"path": "relative.jar"}), CallOptions::new(Caller::Mcp)).is_err());
        assert!(e.call("java_vineflower_decompile", json!({}), CallOptions::new(Caller::Mcp)).is_err());
    }
}
