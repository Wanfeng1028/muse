//! Rust programs: which toolchain and crates built them, read from the file's bytes, symbols and
//! the optional cargo-auditable dependency list. Nothing is executed.

use super::native_common::{params_json, spec};
use super::static_input::{self, builder};
use super::{Detail, detailed};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Location, ToolError};
use craft_anything_formats::{Format, rust_bin};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "native_rust_binary_show",
        "Rust program details",
        "Identify a Rust program (ELF, PE or Mach-O, or any file) from its bytes: rustc version strings and the toolchain commit from /rustc/<commit>/ paths, the standard-library path layout, crates with versions from embedded Cargo paths (registry/src/<index>/<crate>-<version>/ and git checkouts), the program's own source paths left by panic locations, well-known panic messages, Rust symbol names (legacy and v0 mangling) with demangled samples and whether they are stripped, and the cargo-auditable dependency list (.dep-v0) when present. Confidence is honest: strong signals (symbols, toolchain paths, dependency data) versus weak ones (panic text alone). Built-in; never runs the program.",
        "Find out whether a program was written in Rust, with which compiler and which libraries.",
        Toolset::Formats,
        Effects::EVIDENCE,
        Requires::Nothing,
        schema_of::<RustParams>,
        native_rust_binary_show,
    )]
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RustParams {
    /// Absolute path of the program; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// summary or complete (default).
    #[serde(default)]
    pub detail: Detail,
}

fn native_rust_binary_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RustParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), static_input::DEFAULT_MAX_BYTES)?;
    ctx.report(None, format!("Looking for Rust fingerprints in {}", input.name));
    let bin = craft_anything_formats::parse_binary(&input.bytes).ok();
    ctx.cancel.check()?;
    let r = rust_bin::inspect(&input.bytes, bin.as_ref());

    let version = r.rustc_versions.first().map(|v| format!(" rustc {}", v.value)).unwrap_or_default();
    let summary = if r.is_rust {
        format!(
            "{} Rust evidence{version}: {} crate(s) from Cargo paths{}, {} local source path(s), symbols {}.",
            if r.strength == "strong" { "Strong" } else { "Weak" },
            r.crates.len(),
            r.auditable.as_ref().map(|a| format!(", {} package(s) in the cargo-auditable list", a.packages.len())).unwrap_or_default(),
            r.source_paths.local.len(),
            if r.symbols.stripped { "stripped or absent".to_string() } else { format!("present ({} Rust names)", r.symbols.rust_legacy + r.symbols.rust_v0) },
        )
    } else {
        "No Rust fingerprints found in this file.".to_string()
    };

    let mut lims = vec![Limitation::new(
        "string_heuristics",
        "Crates, versions and source paths come from text left in the file; a path next to other text can pick up a few stray characters, and crates without panics or debug paths leave no trace.",
    )];
    if r.auditable.is_none() {
        lims.push(Limitation::new(
            "no_auditable_data",
            r.auditable_error
                .clone()
                .unwrap_or_else(|| "No cargo-auditable (.dep-v0) section: the crate list is partial and versions come only from paths.".into()),
        ));
    }
    if bin.is_none() {
        lims.push(Limitation::new("not_a_program", "This file is not a readable ELF, PE or Mach-O program, so symbols and sections were not read."));
    } else if bin.as_ref().is_some_and(|b| b.format == Format::Pe) && r.symbols.stripped {
        lims.push(Limitation::new(
            "pdb_symbols",
            "Windows programs usually keep their symbol names in a separate .pdb file, so missing symbols here are normal.",
        ));
    }
    if !r.is_rust {
        lims.push(Limitation::new(
            "absence_not_proof",
            "Not finding Rust fingerprints does not prove the program isn't Rust: it can be stripped, packed or built with path remapping.",
        ));
    }
    if r.rustc_commits.is_empty() && r.rustc_versions.is_empty() && r.is_rust {
        lims.push(Limitation::new("no_toolchain_version", "No rustc version or commit was found; the compiler version is unknown."));
    }

    let confidence = match r.strength {
        "strong" => Confidence::Observed,
        _ => Confidence::Inferred,
    };
    let result = serde_json::to_value(&r).unwrap_or(Value::Null);
    let extras = json!({"is_rust": r.is_rust, "strength": r.strength, "counts": {
        "crates": r.crates.len(),
        "local_source_paths": r.source_paths.local.len(),
        "rust_symbols": r.symbols.rust_legacy + r.symbols.rust_v0,
        "auditable_packages": r.auditable.as_ref().map(|a| a.packages.len()),
    }});
    let mut b = builder(ctx, "native_rust_binary_show", input.subject.clone(), params_json(&p))
        .result(json!({"path": input.path, "file_size": input.bytes.len(), "container": bin.as_ref().map(|b| b.format), "report": result}))
        .summary(summary)
        .confidence(confidence)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", input.path.display().to_string()));
    if let Some(a) = &r.auditable {
        b = b.location(Location::new("file_offset", format!("{:#x}", a.file_offset)).with_label(a.section.clone()));
    }
    detailed(ctx, b.build()?, p.detail, extras)
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::call;
    use crate::Engine;
    use craft_anything_testkit::temp_file;
    use serde_json::json;

    #[test]
    fn reports_rust_and_not_rust() {
        let e = Engine::new(crate::testing::session());
        let mut d = b"MZ junk ".to_vec();
        d.extend(b"/rustc/82e1608dfa6e0b5569232559e3d385fea5a93112/library/std/src/rt.rs\x00");
        d.extend(b"/c/.cargo/registry/src/index.crates.io-6f17d22bba15001f/anyhow-1.0.79/src/error.rs\x00src/main.rs\x00");
        let p = temp_file("tool.bin", &d);
        let v = call(&e, "native_rust_binary_show", json!({"path": p}));
        let r = &v["result"]["report"];
        assert_eq!(r["strength"], "strong");
        assert_eq!(r["crates"][0]["name"], "anyhow");
        assert_eq!(r["crates"][0]["version"], "1.0.79");
        assert_eq!(v["confidence"], "observed");
        assert!(v["summary"].as_str().unwrap().starts_with("Strong Rust evidence"));

        let s = call(&e, "native_rust_binary_show", json!({"path": p, "detail": "summary"}));
        assert_eq!(s["result"]["counts"]["crates"], 1);
        assert!(s["result"]["saved_evidence"]["evidence_id"].is_string());

        let p = temp_file("plain.bin", b"nothing to see here");
        let v = call(&e, "native_rust_binary_show", json!({"path": p}));
        assert_eq!(v["result"]["report"]["is_rust"], false);
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "absence_not_proof"));
    }
}
