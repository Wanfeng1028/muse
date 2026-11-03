//! Annotations (names, comments, bookmarks) and navigation (cursor, next/previous address).
//! Annotations live on the open target and are saved to the project when one is open; every
//! write is read back and returned.

use super::native_common::{address_or_cursor, hex, image, name_of, native, resolve_function, select_document, spec, user_names};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::native as an;
use craft_anything_evidence::ToolError;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Longest name we keep (in UTF-16 units, like common disassembler limits).
pub const MAX_NAME_UNITS: usize = 1024;
pub const MAX_COMMENT_CHARS: usize = 16_384;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Native;
    let t = Requires::Target;
    let edit = Effects::MUTATES_TARGET.union(Effects::MUTATES_SESSION).union(Effects::MAY_DISCARD_DATA);
    let nav = Effects::MUTATES_SESSION.union(Effects::CHANGES_UI_STATE);
    vec![
        spec(
            "native_name_set",
            "Name an address",
            "Give an address a name (an empty name clears yours). Names show everywhere: listings, assembly, pseudo-C, call graphs. Saved with the project.",
            "Give a place in the program a meaningful name.",
            Native,
            edit,
            t,
            schema_of::<SetNameParams>,
            native_name_set,
        ),
        spec(
            "native_names_set",
            "Name many addresses",
            "Name several addresses at once; reports success per address.",
            "Rename several things at once.",
            Native,
            edit,
            t,
            schema_of::<SetNamesParams>,
            native_names_set,
        ),
        spec(
            "native_comment_write",
            "Write comment",
            "Set the comment at an address (empty clears it) and read it back.",
            "Leave a note at an address.",
            Native,
            edit,
            t,
            schema_of::<SetCommentParams>,
            native_comment_write,
        ),
        spec(
            "native_inline_comment_write",
            "Write inline comment",
            "Set the inline (end-of-line) comment at an address (empty clears it) and read it back.",
            "Leave a short note on a line.",
            Native,
            edit,
            t,
            schema_of::<SetCommentParams>,
            native_inline_comment_write,
        ),
        spec(
            "native_bookmark_add",
            "Bookmark",
            "Bookmark an address with an optional name.",
            "Bookmark a place to come back to.",
            Native,
            edit,
            t,
            schema_of::<BookmarkParams>,
            native_bookmark_add,
        ),
        spec(
            "native_bookmark_remove",
            "Remove bookmark",
            "Remove the bookmark at an address.",
            "Remove a bookmark.",
            Native,
            edit,
            t,
            schema_of::<AddrParams>,
            native_bookmark_remove,
        ),
        spec(
            "native_function_label",
            "Annotate function",
            "Rename a function and/or set its entry comment and inline comment in one step (empty strings clear), read them back, and return the refreshed function facts.",
            "Rename a function and note what it does.",
            Native,
            edit,
            t,
            schema_of::<AnnotateParams>,
            native_function_label,
        ),
        spec(
            "native_cursor_address_show",
            "Cursor address",
            "The cursor address in the active document (set with native_cursor_goto or in the app).",
            "Where am I looking?",
            Native,
            Effects::READ_ONLY,
            t,
            schema_of::<DocParams>,
            native_cursor_address_show,
        ),
        spec(
            "native_cursor_function_show",
            "Cursor function",
            "The function containing the cursor.",
            "Which function am I looking at?",
            Native,
            Effects::EVIDENCE,
            t,
            schema_of::<DocParams>,
            native_cursor_function_show,
        ),
        spec(
            "native_document_show",
            "Current document",
            "The active document (open target).",
            "Which file am I looking at?",
            Native,
            Effects::READ_ONLY,
            t,
            schema_of::<NoParams>,
            native_document_show,
        ),
        spec(
            "native_cursor_goto",
            "Go to address",
            "Move the cursor to an address (must be mapped in the program).",
            "Jump to a place in the program.",
            Native,
            nav,
            t,
            schema_of::<AddrParams>,
            native_cursor_goto,
        ),
        spec(
            "native_cursor_forward",
            "Next address",
            "The address of the next instruction (in code) or next byte (in data) after an address (the cursor by default). Doesn't move the cursor.",
            "Step forward one instruction.",
            Native,
            Effects::READ_ONLY,
            t,
            schema_of::<OptAddrParams>,
            native_cursor_forward,
        ),
        spec(
            "native_cursor_back",
            "Previous address",
            "The address of the previous instruction (in code) or previous byte (in data) before an address (the cursor by default). Doesn't move the cursor.",
            "Step back one instruction.",
            Native,
            Effects::READ_ONLY,
            t,
            schema_of::<OptAddrParams>,
            native_cursor_back,
        ),
    ]
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NoParams {}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DocParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AddrParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Virtual address (0x-hex).
    pub address: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OptAddrParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Virtual address (0x-hex); the cursor when omitted.
    #[serde(default)]
    pub address: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetNameParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Virtual address (0x-hex).
    pub address: String,
    /// New name; empty clears your name.
    pub name: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetNamesParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Map of address (0x-hex) → name; empty names clear.
    pub names: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetCommentParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Virtual address (0x-hex).
    pub address: String,
    /// Comment text; empty clears it.
    pub comment: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BookmarkParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Virtual address (0x-hex).
    pub address: String,
    /// Bookmark label.
    #[serde(default)]
    pub name: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AnnotateParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Function name or address.
    pub function: String,
    /// New name (empty clears your name).
    #[serde(default)]
    pub name: Option<String>,
    /// Comment at the entry (empty clears).
    #[serde(default)]
    pub comment: Option<String>,
    /// Inline comment at the entry (empty clears).
    #[serde(default)]
    pub inline_comment: Option<String>,
}

fn check_name(name: &str) -> Result<(), ToolError> {
    if name.encode_utf16().count() > MAX_NAME_UNITS {
        return Err(ToolError::invalid(format!("names are limited to {MAX_NAME_UNITS} characters")));
    }
    if name.chars().any(|c| c.is_control()) {
        return Err(ToolError::invalid("names can't contain control characters or newlines"));
    }
    Ok(())
}

fn check_comment(c: &str) -> Result<(), ToolError> {
    if c.chars().count() > MAX_COMMENT_CHARS {
        return Err(ToolError::invalid(format!("comments are limited to {MAX_COMMENT_CHARS} characters")));
    }
    if c.contains('\0') {
        return Err(ToolError::invalid("comments can't contain NUL"));
    }
    Ok(())
}

/// Addresses must lie in the program (or be a known name target).
fn check_mapped(ctx: &mut Ctx<'_>, a: u64) -> Result<(), ToolError> {
    let img = image(ctx)?;
    if img.0.is_mapped(a) {
        Ok(())
    } else {
        Err(ToolError::invalid(format!("{a:#x} isn't inside the program")).with_remediation("Pick an address inside a segment (native_sections_list)."))
    }
}

fn put(map: &mut BTreeMap<u64, String>, a: u64, v: &str) -> Option<String> {
    if v.is_empty() {
        map.remove(&a);
        None
    } else {
        map.insert(a, v.to_string());
        Some(v.to_string())
    }
}

fn native_name_set(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetNameParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = super::parse_address(&p.address)?;
    check_name(&p.name)?;
    check_mapped(ctx, a)?;
    let t = ctx.session.active_mut()?;
    let previous = t.annotations.names.get(&a).cloned();
    let now = put(&mut t.annotations.names, a, p.name.trim());
    ctx.session.save_annotations()?;
    Ok(ToolOutput::Value(json!({"address": hex(a), "name": now, "previous": previous, "persisted": ctx.session.project.is_some()})))
}

fn native_names_set(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetNamesParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if p.names.len() > 10_000 {
        return Err(ToolError::invalid("at most 10000 names per call"));
    }
    let img = image(ctx)?;
    let mut results = Vec::new();
    let mut ok = 0usize;
    for (addr, name) in &p.names {
        let r = super::parse_address(addr).and_then(|a| {
            check_name(name)?;
            if !img.0.is_mapped(a) {
                return Err(ToolError::invalid(format!("{a:#x} isn't inside the program")));
            }
            Ok(a)
        });
        match r {
            Ok(a) => {
                let t = ctx.session.active_mut()?;
                let now = put(&mut t.annotations.names, a, name.trim());
                ok += 1;
                results.push(json!({"address": hex(a), "ok": true, "name": now}));
            }
            Err(e) => results.push(json!({"address": addr, "ok": false, "error": e.message})),
        }
    }
    ctx.session.save_annotations()?;
    Ok(ToolOutput::Value(json!({"results": results, "succeeded": ok, "failed": p.names.len() - ok})))
}

fn set_comment_kind(ctx: &mut Ctx<'_>, params: Value, inline: bool) -> Result<ToolOutput, ToolError> {
    let p: SetCommentParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = super::parse_address(&p.address)?;
    check_comment(&p.comment)?;
    check_mapped(ctx, a)?;
    let t = ctx.session.active_mut()?;
    let map = if inline { &mut t.annotations.inline_comments } else { &mut t.annotations.comments };
    put(map, a, &p.comment);
    let readback = map.get(&a).cloned();
    ctx.session.save_annotations()?;
    Ok(ToolOutput::Value(json!({"address": hex(a), "comment": readback, "inline": inline})))
}

fn native_comment_write(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    set_comment_kind(ctx, params, false)
}

fn native_inline_comment_write(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    set_comment_kind(ctx, params, true)
}

fn native_bookmark_add(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: BookmarkParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = super::parse_address(&p.address)?;
    let name = p.name.unwrap_or_default();
    check_name(&name)?;
    check_mapped(ctx, a)?;
    let t = ctx.session.active_mut()?;
    t.annotations.bookmarks.insert(a, name.clone());
    ctx.session.save_annotations()?;
    Ok(ToolOutput::Value(json!({"address": hex(a), "bookmark": name})))
}

fn native_bookmark_remove(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AddrParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = super::parse_address(&p.address)?;
    let t = ctx.session.active_mut()?;
    let removed = t.annotations.bookmarks.remove(&a);
    ctx.session.save_annotations()?;
    Ok(ToolOutput::Value(json!({"address": hex(a), "removed": removed.is_some()})))
}

fn native_function_label(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AnnotateParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if p.name.is_none() && p.comment.is_none() && p.inline_comment.is_none() {
        return Err(ToolError::invalid("give at least one of name, comment, native_inline_comment_read"));
    }
    if let Some(n) = &p.name {
        check_name(n)?;
    }
    for c in [&p.comment, &p.inline_comment].into_iter().flatten() {
        check_comment(c)?;
    }
    let st = native(ctx)?;
    let entry = resolve_function(ctx.session.active()?, &st.prog, &p.function)?.entry;
    let t = ctx.session.active_mut()?;
    if let Some(n) = &p.name {
        put(&mut t.annotations.names, entry, n.trim());
    }
    if let Some(c) = &p.comment {
        put(&mut t.annotations.comments, entry, c);
    }
    if let Some(c) = &p.inline_comment {
        put(&mut t.annotations.inline_comments, entry, c);
    }
    ctx.session.save_annotations()?;
    let t = ctx.session.active()?;
    let f = st.prog.functions.get(&entry).ok_or_else(|| ToolError::internal("function vanished"))?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let info = an::function_info(&st.prog, f, &names);
    Ok(ToolOutput::Value(json!({
        "entry": hex(entry),
        "name": name_of(t, &st.prog, entry),
        "comment": t.annotations.comments.get(&entry),
        "inline_comment": t.annotations.inline_comments.get(&entry),
        "function": info,
        "persisted": ctx.session.project.is_some(),
    })))
}

fn native_cursor_address_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DocParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let t = ctx.session.active()?;
    Ok(ToolOutput::Value(json!({"document": t.target.id, "address": t.cursor.address.map(hex)})))
}

fn native_cursor_function_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DocParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let Some(a) = ctx.session.active()?.cursor.address else {
        return Ok(ToolOutput::Value(json!({"address": null, "function": null, "reason": "the cursor isn't set; use native_cursor_goto"})));
    };
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let f = st.prog.function_containing(a);
    Ok(ToolOutput::Value(json!({"address": hex(a), "function": f.map(|f| name_of(t, &st.prog, f.entry)), "entry": f.map(|f| hex(f.entry))})))
}

fn native_document_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let _: NoParams = parse_params(params)?;
    let t = ctx.session.active()?;
    Ok(ToolOutput::Value(json!({"document": t.target.id, "name": t.target.name, "path": t.target.path, "kind": t.target.kind, "sha256": t.target.sha256})))
}

fn native_cursor_goto(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AddrParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = super::parse_address(&p.address)?;
    check_mapped(ctx, a)?;
    let t = ctx.session.active_mut()?;
    let previous = t.cursor.address;
    t.cursor.address = Some(a);
    Ok(ToolOutput::Value(json!({"address": hex(a), "previous": previous.map(hex)})))
}

fn step(ctx: &mut Ctx<'_>, params: Value, forward: bool) -> Result<ToolOutput, ToolError> {
    let p: OptAddrParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let a = address_or_cursor(ctx.session, &p.address)?;
    let st = native(ctx)?;
    let (next, unit) = if let Some(f) = st.prog.function_containing(a) {
        let insns = st.prog.instructions(&st.img, f, false);
        let addrs: Vec<u64> = insns.iter().map(|i| i.addr).collect();
        let n = if forward {
            addrs.iter().find(|x| **x > a).copied().or_else(|| insns.last().map(|i| i.end()))
        } else {
            addrs.iter().rev().find(|x| **x < a).copied()
        };
        (n, "instruction")
    } else if forward {
        (st.img.decode(a, false).filter(|_| st.img.is_exec(a)).map(|i| i.end()).or(a.checked_add(1)), "byte")
    } else {
        (a.checked_sub(1), "byte")
    };
    let next = next.filter(|n| st.img.is_mapped(*n) || st.prog.function_containing(a).is_some());
    Ok(ToolOutput::Value(json!({"from": hex(a), "address": next.map(hex), "unit": unit})))
}

fn native_cursor_forward(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    step(ctx, params, true)
}

fn native_cursor_back(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    step(ctx, params, false)
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::*;
    use craft_anything_testkit as tk;
    use serde_json::json;

    #[test]
    fn names_comments_bookmarks_and_navigation() {
        let (elf, l) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let helper = format!("{:#x}", l.code_va + tk::x64::HELPER);
        let r = call(&e, "native_name_set", json!({"address": helper, "name": "sum_to"}));
        assert_eq!(r["result"]["name"], "sum_to");
        let r = call(&e, "native_function_pseudocode", json!({"function": "main"}));
        assert!(r["result"]["pseudo_code"].as_str().unwrap().contains("sum_to(5)"));
        let r = call(&e, "native_function_show", json!({"function": "sum_to"}));
        assert_eq!(r["result"]["name"], "sum_to");
        let r = call(&e, "native_names_set", json!({"names": {format!("{:#x}", l.code_va): "start_here", "0x1": "bad", "zz": "worse"}}));
        assert_eq!(r["result"]["succeeded"], 1);
        assert_eq!(r["result"]["failed"], 2);
        assert!(call_err(&e, "native_name_set", json!({"address": helper, "name": "x".repeat(1025)})).message.contains("1024"));
        call(&e, "native_comment_write", json!({"address": helper, "comment": "adds 1..n"}));
        let r = call(&e, "native_comment_read", json!({"address": helper}));
        assert_eq!(r["result"]["comment"], "adds 1..n");
        call(&e, "native_comment_write", json!({"address": helper, "comment": ""}));
        assert!(call(&e, "native_comment_read", json!({"address": helper}))["result"]["comment"].is_null());
        call(&e, "native_inline_comment_write", json!({"address": helper, "comment": "loop"}));
        assert_eq!(call(&e, "native_inline_comment_read", json!({"address": helper}))["result"]["comment"], "loop");
        call(&e, "native_bookmark_add", json!({"address": helper, "name": "look here"}));
        assert_eq!(call(&e, "native_bookmarks_show", json!({}))["result"]["bookmarks"][0]["name"], "look here");
        assert_eq!(call(&e, "native_bookmark_remove", json!({"address": helper}))["result"]["removed"], true);
        let r = call(&e, "native_function_label", json!({"function": "dispatch", "name": "pick_value", "comment": "switch on 0..2"}));
        assert_eq!(r["result"]["name"], "pick_value");
        assert_eq!(r["result"]["function"]["name"], "pick_value");
        assert!(call_err(&e, "native_function_label", json!({"function": "main"})).message.contains("at least one"));
        // navigation
        assert!(call(&e, "native_cursor_address_show", json!({}))["result"]["address"].is_null());
        call(&e, "native_cursor_goto", json!({"address": helper}));
        assert_eq!(call(&e, "native_cursor_address_show", json!({}))["result"]["address"], helper);
        assert_eq!(call(&e, "native_cursor_function_show", json!({}))["result"]["function"], "sum_to");
        let n = call(&e, "native_cursor_forward", json!({}));
        assert_eq!(n["result"]["address"], format!("{:#x}", l.code_va + tk::x64::HELPER + 1));
        let p = call(&e, "native_cursor_back", json!({"address": format!("{:#x}", l.code_va + tk::x64::HELPER + 4)}));
        assert_eq!(p["result"]["address"], format!("{:#x}", l.code_va + tk::x64::HELPER + 1));
        assert_eq!(call(&e, "native_document_show", json!({}))["result"]["name"], "prog");
        assert!(call_err(&e, "native_cursor_goto", json!({"address": "0x5"})).remediation.is_some());
    }
}
