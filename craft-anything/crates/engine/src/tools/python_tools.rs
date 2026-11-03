//! Compiled Python files: which Python made them, how they tie to their source, and the functions,
//! names and text inside. Nothing is executed and no bytecode is decoded.

use super::native_common::{DEFAULT_LIMIT, page, params_json, spec};
use super::static_input::{self, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Location, ToolError};
use craft_anything_formats::pyc::{self, CodeRead, PycFile};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "formats_bytecode_show",
        "Compiled Python file",
        "Read a CPython compiled file (.pyc): the Python version from its magic number, how it ties to its source (modification time and size, or a source hash), and, for Python 3.8 to 3.14, its compiled code: each module, class and function with its name, dotted name, source file, first line, argument counts, the names it uses and the text among its constants, paged with offset/limit, parents before children. Other versions report the header and say why. python_version reads a file of bare marshalled code, such as a script taken out of a PyInstaller program. Built-in; nothing is executed and bytecode isn't decoded.",
        "See what a compiled Python file holds: which Python made it, and its functions and text.",
        Toolset::Formats,
        Effects::EVIDENCE | Effects::CARRIES_TARGET_CONTENT,
        Requires::Nothing,
        schema_of::<PycParams>,
        formats_bytecode_show,
    )]
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PycParams {
    /// Absolute path of the file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Treat the file as bare marshalled code with no header, compiled by this Python ("3.12").
    #[serde(default)]
    pub python_version: Option<String>,
    #[serde(default)]
    pub offset: usize,
    #[serde(default = "default_limit")]
    pub limit: usize,
}

fn default_limit() -> usize {
    DEFAULT_LIMIT
}

/// Read bare marshalled code as the named Python would have written it.
fn read_bare(bytes: &[u8], version: &str) -> Result<PycFile, ToolError> {
    let known = || pyc::RELEASES.iter().filter(|r| r.layout.is_some()).map(|r| r.version).collect::<Vec<_>>().join(", ");
    let release = pyc::release_named(version)
        .filter(|r| r.layout.is_some())
        .ok_or_else(|| ToolError::invalid(format!("We can't read code from Python {version:?}")).with_remediation(format!("Use one of: {}.", known())))?;
    pyc::read_pyc(&pyc::wrap_marshal(release.last, bytes)).map_err(|e| format_err(e, "compiled Python"))
}

fn formats_bytecode_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PycParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), static_input::DEFAULT_MAX_BYTES)?;
    ctx.report(None, format!("Reading {} as compiled Python", input.name));
    let file = match p.python_version.as_deref() {
        Some(version) => read_bare(&input.bytes, version)?,
        None => pyc::read_pyc(&input.bytes).map_err(|e| format_err(e, "compiled Python"))?,
    };
    ctx.cancel.check()?;

    let mut lims =
        vec![Limitation::new("bytecode_not_decoded", "Bytecode isn't decoded: this shows what functions exist and what they name, not what they do.")];
    if let Some(why) = &file.code_missing {
        lims.push(Limitation::new("header_only", why.clone()));
    }
    if file.code.as_ref().is_some_and(|c| c.cut_short) {
        lims.push(Limitation::new("code_cut_short", "A limit stopped the walk through the code objects, so some names, text or functions are missing."));
    }
    if p.python_version.is_some() {
        lims.push(Limitation::new("version_given", "The file has no header, so the Python version is the one you gave, not one it states."));
    }
    let version = file.header.version.map_or_else(|| format!("an unknown Python (magic number {})", file.header.magic), |v| format!("Python {v}"));

    let flat = file.code.as_ref().map(|c: &CodeRead| pyc::flatten(&c.root)).unwrap_or_default();
    let (functions, coverage) = match &file.code {
        Some(_) => page(&flat, p.offset, p.limit),
        None => (Vec::new(), Coverage::complete(1)),
    };
    let summary = match &file.code {
        Some(c) => format!("Compiled by {version}: {} code object(s) from {:?}, {} shown.", flat.len(), c.root.filename, functions.len()),
        None => format!("Compiled by {version}; header only."),
    };
    let confidence = match (&file.code, file.header.version) {
        (Some(_), _) | (None, Some(_)) => Confidence::Observed,
        (None, None) => Confidence::Inferred,
    };
    let ev = builder(ctx, "formats_bytecode_show", input.subject.clone(), params_json(&p))
        .result(json!({
            "path": input.path,
            "file_size": input.bytes.len(),
            "header": file.header,
            "code_available": file.code.is_some(),
            "total_code_objects": flat.len(),
            "code_objects": functions,
        }))
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
    use craft_anything_formats::pyc;
    use craft_anything_testkit::packed::{self as kit, code_38, code_311};
    use craft_anything_testkit::temp_file;
    use serde_json::{Value, json};

    fn sample() -> Vec<u8> {
        let inner = code_311("helper", "Thing.helper", "app.py", 7, &["os"], &["inner text"], &[]);
        code_311("<module>", "<module>", "app.py", 1, &["Thing"], &["module doc"], &[inner])
    }

    #[test]
    fn a_pyc_shows_its_header_and_code_in_pages() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("app.pyc", &kit::pyc(3531, 0, [1, 0, 0, 0, 2, 0, 0, 0], &sample()));
        let v = call(&e, "formats_bytecode_show", json!({"path": p}));
        assert_eq!(v["result"]["header"]["version"], "3.12");
        assert_eq!(v["result"]["header"]["invalidation"], "timestamp");
        assert_eq!(v["result"]["header"]["source_mtime"], 1);
        assert_eq!(v["result"]["total_code_objects"], 2);
        assert_eq!(v["result"]["code_objects"][1]["qualname"], "Thing.helper");
        assert_eq!(v["result"]["code_objects"][1]["strings"][0], "inner text");
        assert_eq!(v["confidence"], "observed");
        assert_eq!(v["authority"], "original-files");

        let second = call(&e, "formats_bytecode_show", json!({"path": p, "offset": 1, "limit": 1}));
        assert_eq!(second["result"]["code_objects"].as_array().unwrap().len(), 1);
        assert_eq!(second["result"]["code_objects"][0]["name"], "helper");
    }

    #[test]
    fn the_older_layout_reads_too() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("old.pyc", &kit::pyc(3425, 0, [0; 8], &code_38("<module>", "old.py", 1, &["os"], &["doc"], &[])));
        let v = call(&e, "formats_bytecode_show", json!({"path": p}));
        assert_eq!(v["result"]["header"]["version"], "3.9");
        assert_eq!(v["result"]["code_objects"][0]["filename"], "old.py");
        assert_eq!(v["result"]["code_objects"][0]["qualname"], Value::Null);
    }

    #[test]
    fn other_versions_give_the_header_and_a_limitation() {
        let e = Engine::new(crate::testing::session());
        let codes = |v: &Value| v["limitations"].as_array().unwrap().iter().map(|l| l["code"].as_str().unwrap().to_string()).collect::<Vec<_>>();
        let p = temp_file("old.pyc", &kit::pyc(3394, 0, [0; 8], &sample()));
        let v = call(&e, "formats_bytecode_show", json!({"path": p}));
        assert_eq!(v["result"]["header"]["version"], "3.7");
        assert_eq!(v["result"]["code_available"], false);
        assert!(codes(&v).contains(&"header_only".to_string()));
        assert_eq!(v["confidence"], "observed");

        let p = temp_file("unknown.pyc", &kit::pyc(4000, 0, [0; 8], &sample()));
        let v = call(&e, "formats_bytecode_show", json!({"path": p}));
        assert_eq!(v["result"]["header"]["version"], Value::Null);
        assert_eq!(v["confidence"], "inferred");
    }

    #[test]
    fn damaged_code_is_a_limitation_and_a_non_pyc_is_an_error() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("cut.pyc", &kit::pyc(3531, 0, [0; 8], &sample()[..20]));
        let v = call(&e, "formats_bytecode_show", json!({"path": p}));
        assert_eq!(v["result"]["code_available"], false);
        assert!(v["limitations"].to_string().contains("couldn't be read"));
        let p = temp_file("plain.txt", b"not compiled python");
        call_err(&e, "formats_bytecode_show", json!({"path": p}));
    }

    #[test]
    fn bare_marshalled_code_reads_with_a_version() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("main", &sample());
        let v = call(&e, "formats_bytecode_show", json!({"path": p, "python_version": "3.12"}));
        assert_eq!(v["result"]["code_objects"][0]["name"], "<module>");
        assert!(v["limitations"].to_string().contains("version_given"));
        call_err(&e, "formats_bytecode_show", json!({"path": p, "python_version": "3.7"}));
        let newest = call(&e, "formats_bytecode_show", json!({"path": p, "python_version": "3.14"}));
        assert_eq!(newest["result"]["code_objects"][0]["name"], "<module>");
        call_err(&e, "formats_bytecode_show", json!({"path": p, "python_version": "nonsense"}));
    }

    #[test]
    fn a_module_taken_out_of_a_program_reads_here() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("onefile", &kit::pyinstaller_sample());
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("out");
        call(&e, "core_packed_files_unpack", json!({"path": p, "output_directory": out, "contains": "pkg/util"}));
        let v = call(&e, "formats_bytecode_show", json!({"path": out.join("PYZ-00.pyz.modules/pkg/util.pyc")}));
        assert_eq!(v["result"]["header"]["magic"], 3531);
        assert_eq!(v["result"]["code_objects"][0]["strings"][0], "util doc");
        assert_eq!(pyc::release_for_magic(3531).map(|r| r.version), Some("3.12"));
    }

    fn list(e: &Engine, p: &std::path::Path) -> Value {
        call(e, "core_packed_files_list", json!({"path": p, "limit": 100}))
    }

    /// Lists through the engine, takes everything out and checks one member's bytes.
    fn round_trip(name: &str, data: &[u8], format: &str, member: &str, body: &[u8], expected_files: usize) {
        let e = Engine::new(crate::testing::session());
        let p = temp_file(name, data);
        let v = list(&e, &p);
        assert_eq!(v["result"]["format"], format);
        assert_eq!(v["result"]["total"], expected_files, "{:?}", v["result"]["entries"]);
        assert_eq!(v["confidence"], "observed");
        let dir = tempfile::tempdir().unwrap();
        let out = dir.path().join("out");
        let x = call(&e, "core_packed_files_unpack", json!({"path": p, "output_directory": out}));
        assert_eq!(x["result"]["skipped"].as_array().unwrap().len(), 0, "{:?}", x["result"]["skipped"]);
        assert_eq!(x["result"]["written"], expected_files);
        assert_eq!(std::fs::read(out.join(member)).unwrap(), body);
        assert!(out.join("manifest.json").is_file());
    }

    #[test]
    fn bun_programs_work_through_the_engine() {
        let section = kit::macho_section("__BUN", "__bun", &kit::bun_section_payload(&kit::bun_sample()));
        round_trip("bunapp", &section, "bun_program", "root/app.js", b"console.log('app')", 2);
        round_trip("bunapp2", &kit::bun_appended(&kit::bun_sample()), "bun_program", "root/logo.png", b"\x89PNG", 2);
    }

    #[test]
    fn node_programs_work_through_the_engine() {
        let note = kit::elf_note("NODE_SEA_BLOB", &kit::sea_sample());
        round_trip("seaapp", &note, "node_sea", "assets/dir/b.bin", b"asset b", 4);
        round_trip("blob", &kit::sea_sample(), "node_sea", "main/hello.js", b"console.log('sea')", 4);
    }

    #[test]
    fn dotnet_programs_work_through_the_engine() {
        round_trip("netapp", &kit::dotnet_sample(), "dotnet_bundle", "App.dll", &[0x5a; 200], 3);
    }

    #[test]
    fn pyinstaller_programs_work_through_the_engine() {
        round_trip("pyapp", &kit::pyinstaller_sample(), "pyinstaller", "libz.so.1", b"native", 7);
    }

    #[test]
    fn listings_filter_and_page_and_clean_room_refuses_them() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("pyapp2", &kit::pyinstaller_sample());
        let v = call(&e, "core_packed_files_list", json!({"path": p, "contains": ".modules/", "limit": 1}));
        assert_eq!(v["result"]["matching"], 2);
        assert_eq!(v["result"]["entries"].as_array().unwrap().len(), 1);
        assert_eq!(v["result"]["facts"]["python"], "3.12");
        e.session().settings.deep_mode = false;
        call_err(&e, "core_packed_files_list", json!({"path": p}));
        call_err(&e, "formats_bytecode_show", json!({"path": p}));
    }

    #[test]
    fn a_reader_can_be_chosen_and_a_wrong_one_explains_itself() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("wrong", &kit::sea_sample());
        let err = call_err(&e, "core_packed_files_list", json!({"path": p, "format": "pyinstaller"}));
        assert!(err.to_string().contains("PyInstaller"), "{err}");
        let p = temp_file("cutbun", &kit::bun_appended(&kit::bun_sample())[40..]);
        call_err(&e, "core_packed_files_list", json!({"path": p}));
    }
}
