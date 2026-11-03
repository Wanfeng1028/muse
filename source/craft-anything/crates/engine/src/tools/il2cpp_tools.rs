//! A Unity IL2CPP game's `global-metadata.dat`: the assembly, type and method names and string
//! literals its C# had before it was compiled to native code. Only this file is read; nothing runs.

use super::native_common::{DEFAULT_LIMIT, MAX_LIMIT, params_json, spec};
use super::static_input::{builder, load_path};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, ErrorCode, Limitation, Location, ToolError};
use craft_anything_formats::entropy;
use craft_anything_formats::il2cpp::{self, Metadata, Reading};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::VecDeque;
use std::path::{Path, PathBuf};

const FILE_NAME: &str = "global-metadata.dat";
/// Largest metadata file read (the largest games' are a few hundred MiB at most).
const MAX_FILE: u64 = 2 << 30;
/// How deep and how many entries are looked at when finding the file in a game's folder.
const MAX_DEPTH: usize = 8;
const MAX_ENTRIES: usize = 50_000;
/// How much of one string literal a row shows.
const MAX_LITERAL: usize = 4096;
/// How many rows are checked between looks at the cancel button.
const CANCEL_EVERY: usize = 4096;

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "game_unity_code_names_show",
        "Read a Unity game's IL2CPP metadata",
        "Read a Unity IL2CPP global-metadata.dat (path: the file, or a game's folder, where it's found under *_Data/il2cpp_data/Metadata or Data/il2cpp_data/Metadata): the metadata version, its assemblies (images) and how many types, methods, fields and string literals it names. view picks a list to page: images, types (namespace, name, assembly, method and field counts), methods (name, declaring type, parameter count) or strings (the string literals, each shown up to 4096 bytes); contains keeps rows holding that text (any case). Versions 24 (its later 264-byte-header form), 27, 29 and 31 are read, each only after the file proves it fits; other versions give their header and say so. Many games change or encrypt this file: that's stated plainly and nothing is decrypted or guessed. Only names are here, with no code or addresses.",
        "See the names of the code inside a Unity game built with IL2CPP, even though the code itself is compiled.",
        Toolset::Formats,
        Effects::EVIDENCE | Effects::CARRIES_TARGET_CONTENT,
        Requires::Nothing,
        schema_of::<MetadataParams>,
        game_unity_code_names_show,
    )]
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum View {
    /// Counts and the first page of images.
    #[default]
    Summary,
    Images,
    Types,
    Methods,
    Strings,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MetadataParams {
    /// Absolute path of global-metadata.dat, or of a game's folder to find it in.
    pub path: String,
    /// What to list: summary (the default), images, types, methods or strings.
    #[serde(default)]
    pub view: View,
    /// Keep only rows holding this text (any case).
    #[serde(default)]
    pub contains: Option<String>,
    /// First matching row of the page.
    #[serde(default)]
    pub offset: usize,
    /// Rows per page.
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    DEFAULT_LIMIT
}

/// The metadata file for `raw`: itself, or the nearest one under a folder, with any others found.
fn locate(raw: &str) -> Result<(PathBuf, Vec<String>), ToolError> {
    let path = PathBuf::from(raw);
    if !path.is_absolute() {
        return Err(
            ToolError::invalid(format!("{raw:?} is not an absolute path")).with_remediation("Pass the full path of global-metadata.dat or the game's folder.")
        );
    }
    if !path.is_dir() {
        return Ok((path, Vec::new()));
    }
    let found = find_in(&path);
    let mut found = found.into_iter();
    let first = found.next().ok_or_else(|| {
        ToolError::new(ErrorCode::NotFound, format!("There's no {FILE_NAME} under {raw}."))
            .with_remediation("A Unity game built with IL2CPP keeps it in <Game>_Data/il2cpp_data/Metadata. A game built with Mono has its code in Managed/ instead: try managed_assembly_show on Assembly-CSharp.dll.")
    })?;
    Ok((first, found.map(|p| p.display().to_string()).collect()))
}

/// Every metadata file under `root`, nearest first. Bounded, and symbolic links aren't followed.
fn find_in(root: &Path) -> Vec<PathBuf> {
    let mut found = Vec::new();
    let (mut seen, mut queue) = (0usize, VecDeque::from([(root.to_path_buf(), 0usize)]));
    while let Some((dir, depth)) = queue.pop_front() {
        for entry in std::fs::read_dir(&dir).into_iter().flatten().flatten() {
            seen += 1;
            if seen > MAX_ENTRIES {
                return found;
            }
            let Ok(kind) = entry.file_type() else { continue };
            if kind.is_dir() && depth < MAX_DEPTH {
                queue.push_back((entry.path(), depth + 1));
            } else if kind.is_file() && entry.file_name().to_string_lossy().eq_ignore_ascii_case(FILE_NAME) {
                found.push(entry.path());
            }
        }
    }
    found
}

/// The rows of one view that hold the filter, as a page, and how many matched.
fn rows<T: Serialize>(
    ctx: &Ctx<'_>,
    total: usize,
    row: impl Fn(usize) -> Option<T>,
    text: impl Fn(&T) -> String,
    p: &MetadataParams,
) -> Result<(Vec<Value>, usize), ToolError> {
    let needle = p.contains.as_deref().map(str::to_lowercase).filter(|c| !c.is_empty());
    let limit = p.limit.clamp(1, MAX_LIMIT);
    let as_json = |item: &T| serde_json::to_value(item).unwrap_or(Value::Null);
    // Without a filter every row matches, so only the page's rows are read.
    let Some(needle) = needle else {
        let page = (p.offset..total).take(limit).filter_map(&row).map(|item| as_json(&item)).collect();
        return Ok((page, total));
    };
    let (mut page, mut matching) = (Vec::new(), 0usize);
    for i in 0..total {
        if i.is_multiple_of(CANCEL_EVERY) {
            ctx.cancel.check()?;
        }
        let Some(item) = row(i) else { continue };
        if !text(&item).to_lowercase().contains(&needle) {
            continue;
        }
        if matching >= p.offset && page.len() < limit {
            page.push(as_json(&item));
        }
        matching += 1;
    }
    Ok((page, matching))
}

/// One view's page of rows and how many matched.
fn view_rows(ctx: &Ctx<'_>, m: &Metadata<'_>, p: &MetadataParams) -> Result<(Vec<Value>, usize), ToolError> {
    match p.view {
        View::Summary | View::Images => rows(ctx, m.image_count(), |i| m.image(i), |im| im.name.clone(), p),
        View::Types => rows(
            ctx,
            m.type_count(),
            |i| {
                m.type_def(i).map(|t| {
                    json!({
                        "index": t.index,
                        "full_name": t.full_name(),
                        "namespace": t.namespace,
                        "name": t.name,
                        "image": m.image_of(i).map(|im| im.name),
                        "method_count": t.method_count,
                        "first_method": (t.method_count > 0).then_some(t.method_start),
                        "field_count": t.field_count,
                        "flags": t.flags,
                        "token": t.token,
                    })
                })
            },
            |v| v["full_name"].as_str().unwrap_or_default().to_string(),
            p,
        ),
        View::Methods => rows(
            ctx,
            m.method_count(),
            |i| {
                m.method(i).map(|method| {
                    let owner = usize::try_from(method.type_index).ok().and_then(|t| m.type_def(t)).map(|t| t.full_name());
                    json!({
                        "index": method.index,
                        "name": method.name,
                        "type": owner,
                        "type_index": method.type_index,
                        "parameter_count": method.parameter_count,
                        "flags": method.flags,
                        "token": method.token,
                    })
                })
            },
            |v| format!("{} {}", v["type"].as_str().unwrap_or_default(), v["name"].as_str().unwrap_or_default()),
            p,
        ),
        View::Strings => rows(ctx, m.literal_count(), |i| m.literal(i, MAX_LITERAL), |l| l.text.clone(), p),
    }
}

fn game_unity_code_names_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MetadataParams = parse_params(params)?;
    let (path, others) = locate(&p.path)?;
    let input = load_path(&path.display().to_string(), MAX_FILE)?;
    ctx.report(None, format!("Reading {}", input.name));
    let mut lims = Vec::new();
    if !others.is_empty() {
        lims.push(Limitation::new(
            "several_found",
            format!("This folder holds {} more of these files; this result is about the nearest one. Pass the file to read another.", others.len()),
        ));
    }
    let size = input.bytes.len();
    let known = il2cpp::known_versions();
    let (result, summary, confidence, coverage) = match il2cpp::read(&input.bytes) {
        Reading::Altered { first_bytes, why } => {
            lims.push(Limitation::new(
                "altered_or_encrypted",
                format!("{} doesn't start like Unity's IL2CPP metadata ({why}). The game changed or encrypted it, or it's another kind of file, so none of its contents were read. Nothing is decrypted or guessed.", input.name),
            ));
            let sample = input.bytes.get(..size.min(1 << 16)).unwrap_or_default();
            let result = json!({
                "path": input.path,
                "reading": "altered",
                "size": size,
                "first_bytes": first_bytes.iter().map(|b| format!("{b:02x}")).collect::<String>(),
                "entropy": entropy(sample),
            });
            let summary = format!(
                "{}: this isn't readable IL2CPP metadata as it stands: {why}. It has been changed or encrypted, or it's another kind of file.",
                input.name
            );
            (result, summary, Confidence::Inferred, Coverage::complete(0))
        }
        Reading::HeaderOnly { version, sections, why } => {
            lims.push(Limitation::new(
                "header_only",
                format!("Only the header was read: {why}. The versions read here are {known:?}. Reading further would mean guessing where things are, so it isn't done."),
            ));
            let result = json!({"path": input.path, "reading": "header_only", "size": size, "metadata_version": version, "versions_read": known, "why": why, "sections": sections});
            let shown = version.map_or("an unreadable version".to_string(), |v| format!("metadata version {v}"));
            let summary = format!("{}: IL2CPP metadata, {shown}. Its contents weren't read: {why}.", input.name);
            (result, summary, Confidence::Inferred, Coverage::complete(0))
        }
        Reading::Readable(m) => {
            lims.push(Limitation::new(
                "names_only",
                "This file holds names, not code: which native address each method has is in the game's GameAssembly or libil2cpp program.",
            ));
            let (page, matching) = view_rows(ctx, &m, &p)?;
            let counts = json!({
                "images": m.image_count(),
                "types": m.type_count(),
                "methods": m.method_count(),
                "fields": m.field_count(),
                "string_literals": m.literal_count(),
            });
            let list = match p.view {
                View::Summary | View::Images => "images",
                View::Types => "types",
                View::Methods => "methods",
                View::Strings => "strings",
            };
            let mut result = json!({
                "path": input.path,
                "reading": "complete",
                "size": size,
                "metadata_version": m.version(),
                "counts": counts,
                "view": p.view,
                "matching": matching,
                "offset": p.offset,
            });
            result[list] = Value::Array(page.clone());
            let coverage = Coverage::page(page.len() as u64, matching as u64, p.offset as u64);
            let summary = format!(
                "{}: IL2CPP metadata version {}: {} assemblies, {} types, {} methods, {} string literals.",
                input.name,
                m.version(),
                m.image_count(),
                m.type_count(),
                m.method_count(),
                m.literal_count()
            );
            (result, summary, Confidence::Observed, coverage)
        }
    };
    let ev = builder(ctx, "game_unity_code_names_show", input.subject.clone(), params_json(&p))
        .result(result)
        .summary(summary)
        .confidence(confidence)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(coverage)
        .location(Location::new("path", input.path.display().to_string()))
        .build()?;
    Ok(ToolOutput::Evidence(Box::new(ev)))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_testkit::games::{Il2cppSample, il2cpp_metadata};
    use serde_json::{Value, json};
    use std::path::Path;

    fn engine() -> Engine {
        Engine::new(crate::testing::session())
    }

    fn sample() -> Vec<u8> {
        il2cpp_metadata(&Il2cppSample { version: 31, header_size: 256, type_size: 88, method_size: 36 })
    }

    fn write(dir: &Path, rel: &str, bytes: &[u8]) -> String {
        let p = dir.join(rel);
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, bytes).unwrap();
        p.display().to_string()
    }

    #[test]
    fn the_summary_gives_counts_and_images() {
        let dir = tempfile::tempdir().unwrap();
        let path = write(dir.path(), "global-metadata.dat", &sample());
        let v = call(&engine(), "game_unity_code_names_show", json!({"path": path}));
        let r = &v["result"];
        assert_eq!(r["metadata_version"], 31);
        assert_eq!(r["counts"], json!({"images": 2, "types": 3, "methods": 4, "fields": 7, "string_literals": 3}));
        assert_eq!(r["images"][1]["name"], "Assembly-CSharp.dll");
        assert_eq!(r["images"][1]["type_count"], 2);
        assert!(v["summary"].as_str().unwrap().contains("2 assemblies, 3 types, 4 methods"));
        assert_eq!(v["confidence"], "observed");
    }

    #[test]
    fn views_filter_and_page() {
        let dir = tempfile::tempdir().unwrap();
        let path = write(dir.path(), "global-metadata.dat", &sample());
        let e = engine();
        let types = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "types", "contains": "GAME."}));
        let names: Vec<&str> = types["result"]["types"].as_array().unwrap().iter().map(|t| t["full_name"].as_str().unwrap()).collect();
        assert_eq!(names, ["Game.Enemy", "Game.Player"]);
        assert_eq!(types["result"]["types"][1]["image"], "Assembly-CSharp.dll");
        assert_eq!(types["result"]["types"][1]["first_method"], 1);
        assert_eq!(types["result"]["matching"], 2);

        let methods = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "methods", "contains": "player update"}));
        assert_eq!(methods["result"]["methods"][0]["type"], "Game.Player");
        assert_eq!(methods["result"]["matching"], 1);
        let by_type = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "methods", "contains": "enemy"}));
        assert_eq!(by_type["result"]["methods"][0]["name"], "Update");

        let strings = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "strings", "contains": "over"}));
        assert_eq!(strings["result"]["strings"][0]["text"], "Game over");

        // Pages without a filter.
        let first = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "methods", "limit": 3}));
        assert_eq!(first["result"]["methods"].as_array().unwrap().len(), 3);
        assert_eq!(first["result"]["matching"], 4);
        assert_eq!(first["coverage"]["next_offset"], 3);
        let rest = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "methods", "offset": 3, "limit": 3}));
        assert_eq!(rest["result"]["methods"][0]["name"], "TakeDamage");
        assert_eq!(rest["result"]["methods"].as_array().unwrap().len(), 1);
        assert!(rest["coverage"]["next_offset"].is_null());
        let past = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "methods", "offset": 99}));
        assert_eq!(past["result"]["methods"], json!([]));
        assert_eq!(past["result"]["matching"], 4);
        // Pages with a filter.
        let second = call(&e, "game_unity_code_names_show", json!({"path": path, "view": "types", "contains": "game", "offset": 1, "limit": 1}));
        assert_eq!(second["result"]["types"][0]["name"], "Player");
    }

    #[test]
    fn a_folder_is_searched() {
        let dir = tempfile::tempdir().unwrap();
        write(dir.path(), "My Game_Data/il2cpp_data/Metadata/global-metadata.dat", &sample());
        write(dir.path(), "My Game_Data/unrelated.txt", b"x");
        let v = call(&engine(), "game_unity_code_names_show", json!({"path": dir.path()}));
        assert_eq!(v["result"]["reading"], "complete");
        assert!(v["result"]["path"].as_str().unwrap().contains("il2cpp_data"));
    }

    #[test]
    fn a_folder_with_none_says_where_it_looks() {
        let dir = tempfile::tempdir().unwrap();
        write(dir.path(), "readme.txt", b"x");
        let err = call_err(&engine(), "game_unity_code_names_show", json!({"path": dir.path()}));
        assert!(err.message.contains("global-metadata.dat"));
        assert!(err.remediation.unwrap().contains("il2cpp_data"));
    }

    #[test]
    fn altered_magic_is_a_plain_statement_not_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let mut bytes = sample();
        bytes[0] = 0x00;
        let path = write(dir.path(), "global-metadata.dat", &bytes);
        let v = call(&engine(), "game_unity_code_names_show", json!({"path": path}));
        assert_eq!(v["result"]["reading"], "altered");
        assert_eq!(v["confidence"], "inferred");
        assert!(v["summary"].as_str().unwrap().contains("changed or encrypted"));
        let limits: Vec<&str> = v["limitations"].as_array().unwrap().iter().map(|l| l["code"].as_str().unwrap()).collect();
        assert!(limits.contains(&"altered_or_encrypted"), "{limits:?}");
    }

    #[test]
    fn an_unknown_version_gives_its_header_and_a_limitation() {
        let dir = tempfile::tempdir().unwrap();
        let mut bytes = sample();
        bytes[4..8].copy_from_slice(&39i32.to_le_bytes());
        let path = write(dir.path(), "global-metadata.dat", &bytes);
        let v = call(&engine(), "game_unity_code_names_show", json!({"path": path, "view": "types"}));
        assert_eq!(v["result"]["reading"], "header_only");
        assert_eq!(v["result"]["metadata_version"], 39);
        assert!(v["result"].get("types").is_none());
        assert_eq!(v["confidence"], "inferred");
        assert!(v["summary"].as_str().unwrap().contains("39"));
    }

    #[test]
    fn a_file_cut_short_never_fails_at_any_length() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("global-metadata.dat");
        let bytes = sample();
        let e = engine();
        for n in [0, 3, 4, 7, 8, 100, 255, 256, 300, bytes.len() - 1] {
            std::fs::write(&path, &bytes[..n]).unwrap();
            let v: Value = call(&e, "game_unity_code_names_show", json!({"path": path}));
            assert_ne!(v["result"]["reading"], "complete", "{n} bytes");
        }
    }

    #[test]
    fn a_missing_file_or_relative_path_is_an_error() {
        let e = engine();
        assert!(call_err(&e, "game_unity_code_names_show", json!({"path": "relative/global-metadata.dat"})).message.contains("absolute"));
        let dir = tempfile::tempdir().unwrap();
        call_err(&e, "game_unity_code_names_show", json!({"path": dir.path().join("nope.dat")}));
    }

    #[test]
    #[cfg(unix)]
    fn symbolic_links_are_not_followed_when_searching() {
        let (dir, outside) = (tempfile::tempdir().unwrap(), tempfile::tempdir().unwrap());
        write(outside.path(), "global-metadata.dat", &sample());
        std::os::unix::fs::symlink(outside.path(), dir.path().join("link")).unwrap();
        let err = call_err(&engine(), "game_unity_code_names_show", json!({"path": dir.path()}));
        assert!(err.message.contains("no global-metadata.dat"));
    }

    #[test]
    fn clean_room_refuses_it() {
        let mut s = crate::testing::session();
        s.settings.deep_mode = false;
        let e = Engine::new(s);
        let dir = tempfile::tempdir().unwrap();
        let path = write(dir.path(), "global-metadata.dat", &sample());
        assert!(e.call("game_unity_code_names_show", json!({"path": path}), crate::CallOptions::new(crate::Caller::Mcp)).is_err());
    }
}
