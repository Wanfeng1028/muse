//! Interface diff between two WebAssembly modules: imports and exports by name, kind and exact
//! signature, reported as added, removed or changed. Built on the built-in WASM reader; nothing is
//! instantiated or run.

use super::native_common::{page, params_json, spec};
use super::static_input::{self, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Limitation, Location, ToolError};
use craft_anything_formats::wasm::{self, WasmReport};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub fn specs() -> Vec<ToolSpec> {
    vec![spec(
        "formats_wasm_compare",
        "Compare WebAssembly interfaces",
        "Compare the imports and exports of two WebAssembly modules (absolute paths): each import by module and name, each export by name, with its kind (func, table, memory, global, tag) and exact signature (function parameter/result types, memory and table limits, global type). Lists what was added, removed or changed, paged, with counts including unchanged entries; scope picks imports, exports or both. Static comparison only: matching signatures do not prove the modules behave the same.",
        "See how two versions of a WebAssembly module differ in what they import and export.",
        Toolset::Formats,
        Effects::EVIDENCE,
        Requires::Nothing,
        schema_of::<CompareWasmParams>,
        formats_wasm_compare,
    )]
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Scope {
    Imports,
    Exports,
    #[default]
    Both,
}

fn d_limit() -> usize {
    200
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CompareWasmParams {
    /// Absolute path of the older (left) .wasm module.
    pub left_path: String,
    /// Absolute path of the newer (right) .wasm module.
    pub right_path: String,
    /// imports, exports or both (default).
    #[serde(default)]
    pub scope: Scope,
    /// First change of the page.
    #[serde(default)]
    pub offset: usize,
    /// Changes per page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

/// (direction, module, name) → every (kind, signature) occurrence, sorted.
type Interface = BTreeMap<(&'static str, Option<String>, String), Vec<(String, String)>>;

/// What an exported item looks like, resolved through the module's index spaces.
fn export_signature(r: &WasmReport, kind: &str, index: u32) -> String {
    let found = match kind {
        "func" => r
            .functions
            .iter()
            .find(|f| f.index == index)
            .map(|f| f.signature.clone())
            .or_else(|| r.imports.iter().filter(|i| i.kind == "func").nth(index as usize).map(|i| i.signature.clone())),
        "memory" => r
            .memories
            .iter()
            .find(|m| m.index == index)
            .map(|m| format!("{}..{}{}", m.initial, m.maximum.map(|x| x.to_string()).unwrap_or_default(), if m.shared { " shared" } else { "" })),
        "table" => r
            .tables
            .iter()
            .find(|t| t.index == index)
            .map(|t| format!("{} {}..{}", t.element_type, t.initial, t.maximum.map(|x| x.to_string()).unwrap_or_default())),
        "global" => r.globals.iter().find(|g| g.index == index).map(|g| format!("{}{}", if g.mutable { "mut " } else { "" }, g.value_type)),
        "tag" => r.tags.iter().find(|t| t.index == index).map(|t| t.signature.clone()),
        _ => None,
    };
    found.unwrap_or_else(|| format!("unresolved {kind} #{index}"))
}

fn interface(r: &WasmReport, scope: Scope) -> Interface {
    let mut m: Interface = BTreeMap::new();
    if scope != Scope::Exports {
        for i in &r.imports {
            m.entry(("import", Some(i.module.clone()), i.name.clone())).or_default().push((i.kind.to_string(), i.signature.clone()));
        }
    }
    if scope != Scope::Imports {
        for e in &r.exports {
            m.entry(("export", None, e.name.clone())).or_default().push((e.kind.to_string(), export_signature(r, e.kind, e.index)));
        }
    }
    for v in m.values_mut() {
        v.sort();
    }
    m
}

#[derive(Debug, Serialize)]
struct Change {
    direction: &'static str,
    module: Option<String>,
    name: String,
    /// added, removed or changed
    state: &'static str,
    left: Vec<Value>,
    right: Vec<Value>,
}

fn entries(v: Option<&Vec<(String, String)>>) -> Vec<Value> {
    v.map(|v| v.iter().map(|(k, s)| json!({"kind": k, "signature": s})).collect()).unwrap_or_default()
}

fn formats_wasm_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CompareWasmParams = parse_params(params)?;
    let left = static_input::load_path(&p.left_path, wasm::MAX_INPUT as u64)?;
    let right = static_input::load_path(&p.right_path, wasm::MAX_INPUT as u64)?;
    ctx.report(None, format!("Comparing {} with {}", left.name, right.name));
    let lr = wasm::inspect(&left.bytes).map_err(|e| format_err(e, "a WebAssembly module").with_details(json!({"side": "left"})))?;
    let rr = wasm::inspect(&right.bytes).map_err(|e| format_err(e, "a WebAssembly module").with_details(json!({"side": "right"})))?;
    ctx.cancel.check()?;
    let (li, ri) = (interface(&lr, p.scope), interface(&rr, p.scope));

    let mut changes = Vec::new();
    let mut unchanged = 0usize;
    let keys: std::collections::BTreeSet<_> = li.keys().chain(ri.keys()).collect();
    for key in keys {
        let (l, r) = (li.get(key), ri.get(key));
        let state = match (l, r) {
            (Some(a), Some(b)) if a == b => {
                unchanged += 1;
                continue;
            }
            (Some(_), Some(_)) => "changed",
            (Some(_), None) => "removed",
            _ => "added",
        };
        changes.push(Change { direction: key.0, module: key.1.clone(), name: key.2.clone(), state, left: entries(l), right: entries(r) });
    }
    let count = |s: &str| changes.iter().filter(|c| c.state == s).count();
    let (added, removed, changed) = (count("added"), count("removed"), count("changed"));
    let (rows, cov) = page(&changes, p.offset, p.limit);

    let mut lims = vec![Limitation::new(
        "static_interface_only",
        "Only declared names, kinds and types are compared; equal signatures do not prove the same behaviour, and host-side glue code is not examined.",
    )];
    for (side, r) in [("left", &lr), ("right", &rr)] {
        if !r.validation.valid {
            lims.push(Limitation::new(format!("{side}_invalid"), format!("The {side} module does not validate; its interface may be incomplete.")));
        }
        if r.truncated || r.parse_error.is_some() {
            lims.push(Limitation::new(format!("{side}_partial"), format!("The {side} module was not read completely; some entries may be missing.")));
        }
    }
    let summary = format!(
        "{} vs {}: {added} added, {removed} removed, {changed} changed, {unchanged} unchanged ({}).",
        left.name,
        right.name,
        match p.scope {
            Scope::Imports => "imports",
            Scope::Exports => "exports",
            Scope::Both => "imports and exports",
        }
    );
    let side = |i: &static_input::Input, r: &WasmReport| json!({"path": i.path, "sha256": i.subject.sha256, "bytes": i.bytes.len(), "imports": r.imports.len(), "exports": r.exports.len(), "valid": r.validation.valid});
    let b = builder(ctx, "formats_wasm_compare", right.subject.clone(), params_json(&p))
        .result(json!({
            "left": side(&left, &lr),
            "right": side(&right, &rr),
            "scope": p.scope,
            "counts": {"added": added, "removed": removed, "changed": changed, "unchanged": unchanged},
            "changes": rows,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(cov)
        .location(Location::new("path", left.path.display().to_string()).with_label("left"))
        .location(Location::new("path", right.path.display().to_string()).with_label("right"));
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err};
    use crate::Engine;
    use craft_anything_formats::wasm;
    use craft_anything_testkit::{formats as fx, temp_file};
    use serde_json::json;

    /// A module importing env.log (i64)->() and exporting add and sub as (i32, i32)->(i64).
    fn right_module() -> Vec<u8> {
        let mut m = b"\0asm\x01\0\0\0".to_vec();
        let sec = |id: u8, body: &[u8], m: &mut Vec<u8>| {
            m.push(id);
            m.push(body.len() as u8);
            m.extend_from_slice(body);
        };
        sec(1, &[2, 0x60, 1, 0x7e, 0, 0x60, 2, 0x7f, 0x7f, 1, 0x7e], &mut m);
        sec(2, &[1, 3, b'e', b'n', b'v', 3, b'l', b'o', b'g', 0, 0], &mut m);
        sec(3, &[1, 1], &mut m);
        sec(7, &[2, 3, b'a', b'd', b'd', 0, 1, 3, b's', b'u', b'b', 0, 1], &mut m);
        sec(10, &[1, 4, 0, 0x42, 0, 0x0b], &mut m);
        m
    }

    fn tag_module(imported_parameter: Option<u8>, defined_parameter: Option<u8>) -> Vec<u8> {
        let mut module = b"\0asm\x01\0\0\0".to_vec();
        let section = |id: u8, body: &[u8], bytes: &mut Vec<u8>| {
            assert!(body.len() < 128);
            bytes.extend_from_slice(&[id, body.len() as u8]);
            bytes.extend_from_slice(body);
        };
        let parameters: Vec<u8> = imported_parameter.into_iter().chain(defined_parameter).collect();
        let mut types = vec![parameters.len() as u8];
        for parameter in parameters {
            types.extend_from_slice(&[0x60, 1, parameter, 0]);
        }
        section(1, &types, &mut module);
        let imported = u8::from(imported_parameter.is_some());
        if imported_parameter.is_some() {
            // env.incoming is a tag with function type 0.
            section(2, &[1, 3, b'e', b'n', b'v', 8, b'i', b'n', b'c', b'o', b'm', b'i', b'n', b'g', 4, 0, 0], &mut module);
        }
        if defined_parameter.is_some() {
            section(13, &[1, 0, imported], &mut module);
        }
        let mut exports = vec![imported + u8::from(defined_parameter.is_some())];
        if imported_parameter.is_some() {
            exports.extend_from_slice(&[8, b'i', b'n', b'c', b'o', b'm', b'i', b'n', b'g', 4, 0]);
        }
        if defined_parameter.is_some() {
            exports.extend_from_slice(&[5, b'l', b'o', b'c', b'a', b'l', 4, imported]);
        }
        section(7, &exports, &mut module);
        assert!(wasm::inspect(&module).unwrap().validation.valid);
        module
    }

    fn tag_index_module(function_imports: usize, tag_imports: usize, export_indices: &[u32]) -> Vec<u8> {
        fn leb(mut n: u32, bytes: &mut Vec<u8>) {
            loop {
                let byte = (n & 0x7f) as u8;
                n >>= 7;
                bytes.push(byte | if n == 0 { 0 } else { 0x80 });
                if n == 0 {
                    break;
                }
            }
        }
        fn section(id: u8, body: &[u8], bytes: &mut Vec<u8>) {
            bytes.push(id);
            leb(body.len().try_into().unwrap(), bytes);
            bytes.extend_from_slice(body);
        }
        let mut module = b"\0asm\x01\0\0\0".to_vec();
        section(1, &[2, 0x60, 1, 0x7f, 0, 0x60, 1, 0x7e, 0], &mut module);
        let mut imports = Vec::new();
        leb((function_imports + tag_imports).try_into().unwrap(), &mut imports);
        for _ in 0..function_imports {
            imports.extend_from_slice(&[0, 0, 0, 0]); // Empty module/name, function type 0.
        }
        for _ in 0..tag_imports {
            imports.extend_from_slice(&[0, 0, 4, 0, 0]); // Empty module/name, tag type 0.
        }
        section(2, &imports, &mut module);
        section(13, &[1, 0, 1], &mut module); // Defined tag has the distinct i64 parameter.
        let mut exports = Vec::new();
        leb(export_indices.len().try_into().unwrap(), &mut exports);
        for index in export_indices {
            let name = format!("tag{index}");
            leb(name.len().try_into().unwrap(), &mut exports);
            exports.extend_from_slice(name.as_bytes());
            exports.push(4);
            leb(*index, &mut exports);
        }
        section(7, &exports, &mut module);
        module
    }

    #[test]
    fn tag_indices_survive_the_import_list_cap() {
        let report = wasm::inspect(&tag_index_module(wasm::MAX_ITEMS, 1, &[0, 1])).unwrap();
        assert!(report.validation.valid && report.parse_error.is_none(), "{report:?}");
        assert!(report.truncated);
        assert_eq!(report.imports.len(), wasm::MAX_ITEMS);
        assert_eq!(super::export_signature(&report, "tag", 0), "(i32) -> ()");
        assert_eq!(super::export_signature(&report, "tag", 1), "(i64) -> ()");
    }

    #[test]
    fn capped_tag_indices_are_never_filled_by_defined_tags() {
        let cap = u32::try_from(wasm::MAX_ITEMS).unwrap();
        let module = tag_index_module(0, wasm::MAX_ITEMS + 1, &[cap - 1, cap, cap + 1]);
        let report = wasm::inspect(&module).unwrap();
        assert!(report.validation.valid && report.parse_error.is_none(), "{report:?}");
        assert!(report.truncated);
        assert_eq!(super::export_signature(&report, "tag", cap - 1), "(i32) -> ()");
        assert_eq!(super::export_signature(&report, "tag", cap), format!("unresolved tag #{cap}"));
        assert_eq!(super::export_signature(&report, "tag", cap + 1), format!("unresolved tag #{}", cap + 1));
        let path = temp_file("capped-tags.wasm", &module);
        let e = Engine::new(crate::testing::session());
        let result = call(&e, "formats_wasm_compare", json!({"left_path": path, "right_path": path, "scope": "exports"}));
        for code in ["left_partial", "right_partial"] {
            assert!(result["limitations"].as_array().unwrap().iter().any(|l| l["code"] == code));
        }
    }

    #[test]
    fn invalid_tag_references_stay_diagnostic() {
        for (types, type_index, expected) in [(vec![1, 0x60, 0, 0], 1, "type 1 (missing)"), (vec![1, 0x5f, 0], 0, "type 0 (not a function type)")] {
            let mut module = b"\0asm\x01\0\0\0".to_vec();
            module.extend_from_slice(&[1, types.len() as u8]);
            module.extend_from_slice(&types);
            module.extend_from_slice(&[13, 3, 1, 0, type_index, 7, 5, 1, 1, b'e', 4, 0]);
            let report = wasm::inspect(&module).unwrap();
            assert!(!report.validation.valid);
            assert_eq!(super::export_signature(&report, "tag", 0), expected);
            assert_eq!(super::export_signature(&report, "tag", 99), "unresolved tag #99");
            let path = temp_file("invalid-tag.wasm", &module);
            let e = Engine::new(crate::testing::session());
            let result = call(&e, "formats_wasm_compare", json!({"left_path": path, "right_path": path}));
            for code in ["left_invalid", "right_invalid"] {
                assert!(result["limitations"].as_array().unwrap().iter().any(|l| l["code"] == code));
            }
        }
    }

    #[test]
    fn defined_tag_parameter_changes_are_reported() {
        let e = Engine::new(crate::testing::session());
        let left = temp_file("left-tag.wasm", &tag_module(None, Some(0x7f)));
        let right = temp_file("right-tag.wasm", &tag_module(None, Some(0x7e)));
        let v = call(&e, "formats_wasm_compare", json!({"left_path": left, "right_path": right}));
        assert_eq!(v["result"]["counts"], json!({"added": 0, "removed": 0, "changed": 1, "unchanged": 0}));
        let row = &v["result"]["changes"][0];
        assert_eq!(row["name"], "local");
        assert_eq!(row["left"][0]["signature"], "(i32) -> ()");
        assert_eq!(row["right"][0]["signature"], "(i64) -> ()");
        let same = call(&e, "formats_wasm_compare", json!({"left_path": left, "right_path": left}));
        assert_eq!(same["result"]["counts"], json!({"added": 0, "removed": 0, "changed": 0, "unchanged": 1}));
    }

    #[test]
    fn reexported_imported_tags_are_resolved() {
        let e = Engine::new(crate::testing::session());
        let left = temp_file("left-import-tag.wasm", &tag_module(Some(0x7f), None));
        let right = temp_file("right-import-tag.wasm", &tag_module(Some(0x7e), None));
        for scope in ["exports", "imports"] {
            let v = call(&e, "formats_wasm_compare", json!({"left_path": left, "right_path": right, "scope": scope}));
            assert_eq!(v["result"]["counts"], json!({"added": 0, "removed": 0, "changed": 1, "unchanged": 0}), "{scope}: {v}");
            assert_eq!(v["result"]["changes"][0]["left"][0]["signature"], "(i32) -> ()");
        }
    }

    #[test]
    fn defined_tags_follow_imported_tags_in_the_index_space() {
        let e = Engine::new(crate::testing::session());
        let left = temp_file("left-mixed-tags.wasm", &tag_module(Some(0x7f), Some(0x7f)));
        let right = temp_file("right-mixed-tags.wasm", &tag_module(Some(0x7f), Some(0x7e)));
        let v = call(&e, "formats_wasm_compare", json!({"left_path": left, "right_path": right, "scope": "exports"}));
        assert_eq!(v["result"]["counts"], json!({"added": 0, "removed": 0, "changed": 1, "unchanged": 1}));
        assert_eq!(v["result"]["changes"][0]["name"], "local");
    }

    #[test]
    fn reports_added_removed_changed() {
        let e = Engine::new(crate::testing::session());
        let l = temp_file("old.wasm", &fx::wasm_module());
        let r = temp_file("new.wasm", &right_module());
        let v = call(&e, "formats_wasm_compare", json!({"left_path": l, "right_path": r}));
        let res = &v["result"];
        assert_eq!(res["right"]["valid"], true, "{res}");
        assert_eq!(res["counts"], json!({"added": 1, "removed": 2, "changed": 2, "unchanged": 0}));
        let ch = res["changes"].as_array().unwrap();
        let find = |dir: &str, name: &str| ch.iter().find(|c| c["direction"] == dir && c["name"] == name).unwrap().clone();
        assert_eq!(find("export", "sub")["state"], "added");
        assert_eq!(find("export", "memory")["state"], "removed");
        let add = find("export", "add");
        assert_eq!(add["state"], "changed");
        assert_ne!(add["left"][0]["signature"], add["right"][0]["signature"]);
        assert_eq!(find("import", "log")["module"], "env");

        let v = call(&e, "formats_wasm_compare", json!({"left_path": l, "right_path": l, "scope": "exports"}));
        assert_eq!(v["result"]["counts"], json!({"added": 0, "removed": 0, "changed": 0, "unchanged": 3}));

        let bad = temp_file("bad.wasm", b"not wasm");
        call_err(&e, "formats_wasm_compare", json!({"left_path": l, "right_path": bad}));
    }
}
