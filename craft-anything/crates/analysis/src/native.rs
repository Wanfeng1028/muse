//! Native-code workflows over the built-in engine: triage, overview, function dossiers, call
//! graphs and paths, feature tracing, API boundaries, Objective-C/Swift metadata, UI action
//! traces and value flow. Each returns a [`Report`] the engine turns into evidence.

use craft_anything_disasm::dataflow::def_use;
use craft_anything_disasm::pseudo::lift;
use craft_anything_disasm::{Function, Image, Program, XrefKind};
use craft_anything_evidence::{Confidence, Limitation, Location};
use craft_anything_formats::hints::{Hint, detect};
use craft_anything_formats::{Binary, Format};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

/// What an analysis produced, before it becomes evidence.
#[derive(Debug, Clone)]
pub struct Report {
    pub result: Value,
    pub summary: String,
    pub confidence: Confidence,
    pub limitations: Vec<Limitation>,
    pub locations: Vec<Location>,
}

impl Report {
    fn new(result: Value, summary: impl Into<String>, confidence: Confidence) -> Self {
        Report { result, summary: summary.into(), confidence, limitations: Vec::new(), locations: Vec::new() }
    }

    fn limit(mut self, code: &str, msg: impl Into<String>) -> Self {
        self.limitations.push(Limitation::new(code, msg));
        self
    }
}

/// Resolves user-given names (annotations) before the engine's own.
pub type Names<'a> = &'a dyn Fn(u64) -> Option<String>;

fn hex(a: u64) -> String {
    format!("{a:#x}")
}

fn fname(prog: &Program, names: Names<'_>, a: u64) -> String {
    names(a).or_else(|| prog.name_at(a)).unwrap_or_else(|| format!("sub_{a:x}"))
}

fn program_limitations(prog: &Program) -> Vec<Limitation> {
    prog.limitations.iter().map(|(c, m)| Limitation::new(c.clone(), m.clone())).collect()
}

// ---------------------------------------------------------------------------------------------
// Triage

/// A plain-English description of what a native binary is, plus where to go next.
pub fn triage(bin: &Binary, data: &[u8], file_name: &str) -> Report {
    let hints = detect(bin, data);
    let os = match bin.format {
        Format::Elf => {
            if bin.libraries.iter().any(|l| l.contains("liblog.so") || l.contains("libandroid")) {
                "Android"
            } else {
                "Linux"
            }
        }
        Format::Pe => "Windows",
        Format::MachO => match bin.info.get("platform").map(String::as_str) {
            Some("ios") | Some("ios-simulator") => "iPhone/iPad",
            Some("macos") | None => "Mac",
            Some(_) => "Apple",
        },
        Format::DosMz | Format::DosCom => "DOS",
        Format::Coff => "Windows (object file)",
        Format::Raw => "no operating system (raw code)",
    };
    let what = match bin.kind {
        "shared-library" => "a library (code other programs load)",
        "relocatable" => "an object file (not linked into a program yet)",
        "core" => "a crash dump (memory of a program that crashed)",
        _ => "a program",
    };
    let lang: Vec<&Hint> = hints.iter().filter(|h| matches!(h.category, "language" | "runtime" | "framework")).collect();
    let packers: Vec<&Hint> = hints.iter().filter(|h| matches!(h.category, "packer" | "protector" | "installer")).collect();
    let has = |id: &str| hints.iter().any(|h| h.id == id);
    // An AnyCPU .NET assembly has a 32-bit PE header but runs at the machine's own size.
    let managed = if has("dotnet") { craft_anything_formats::dotnet::pe::parse_pe(data).ok().map(|p| p.dotnet_arch()) } else { None };
    let built_for = match managed.as_deref() {
        Some("anycpu") => "any CPU (64-bit on a 64-bit system)".to_string(),
        Some("anycpu-prefer-32") => "any CPU, preferring 32-bit".to_string(),
        _ => format!("{} ({}-bit)", bin.arch.name(), bin.bits),
    };
    let mut plain = format!("{file_name} is {what} for {os}, built for {built_for}.");
    if let Some(l) = lang.first() {
        plain.push_str(&format!(" It looks like it was made with {}.", l.label));
    }
    if !packers.is_empty() {
        plain.push_str(&format!(
            " It appears to be packed or protected ({}), so most of its real code is hidden until it runs.",
            packers.iter().map(|p| p.label.as_str()).collect::<Vec<_>>().join(", ")
        ));
    }
    // .NET metadata and Go's pclntab keep function names even without a native symbol table.
    let names_kept_in = if has("dotnet") {
        Some(".NET metadata")
    } else if has("go") {
        Some("Go's function table (pclntab)")
    } else {
        None
    };
    let stripped = bin.mitigations.stripped && bin.format != Format::Raw && names_kept_in.is_none();
    if stripped {
        plain.push_str(" Its internal names were removed (stripped), so most functions will have generated names.");
    } else if let (true, Some(source)) = (bin.mitigations.stripped, names_kept_in) {
        plain.push_str(&format!(" It has no native symbol table, but its function names are kept in {source}."));
    }
    // Recommendations.
    let mut toolsets: Vec<&str> = vec!["core", "native"];
    let mut tools: Vec<(&str, &str)> = vec![
        ("core_overview_show", "a one-page summary: sections, imports, counts"),
        ("native_functions_list", "every function we found"),
        ("native_strings_find", "find text the program shows or uses"),
        ("native_function_study", "a full dossier on one function (start with main or the entry point)"),
        ("core_feature_find", "follow a word you see in the app to the code behind it"),
    ];
    if has("dotnet") {
        toolsets.push("managed");
        tools.insert(0, ("managed_assembly_show", ".NET code decompiles far better as .NET than as machine code"));
    }
    if has("go") {
        toolsets.push("formats");
        tools.insert(0, ("native_go_binary_show", "Go keeps function names and package paths even when stripped"));
    }
    if has("electron") {
        toolsets.push("javascript");
        tools.insert(0, ("js_app_map", "the app's logic is JavaScript inside resources/app.asar, not in this file"));
    }
    if has("flutter") {
        toolsets.push("android");
        tools.insert(0, ("android_flutter_identify", "Flutter apps keep their Dart code in a snapshot (libapp.so)"));
    }
    if bin.format == Format::MachO || has("objc") || has("swift") {
        toolsets.push("apple");
        tools.push(("apple_objc_classes_list", "Objective-C classes and their methods"));
        tools.push(("apple_macho_show", "load commands, linked libraries, code signature"));
    }
    if bin.format == Format::Pe {
        toolsets.push("formats");
        tools.push(("native_pe_resources_list", "icons, version information and the manifest"));
    }
    if bin.format == Format::Elf {
        toolsets.push("formats");
        tools.push(("native_layout_show", "segments, symbols, relocations and hardening"));
    }
    if bin.kind == "core" {
        tools.insert(0, ("native_crash_show", "which signal killed it, registers, and where it was"));
    }
    if matches!(bin.format, Format::DosMz | Format::DosCom) {
        tools.insert(0, ("native_dos_image_show", "check the DOS load image: header, relocations, entry"));
    }
    if !packers.is_empty() {
        tools.insert(0, ("core_overview_show", "check section entropy; packed code must be unpacked (run in a sandbox) before static analysis helps"));
    }
    toolsets.dedup();
    let mut seen = BTreeSet::new();
    let next: Vec<Value> = tools.into_iter().filter(|(t, _)| seen.insert(*t)).map(|(t, why)| json!({"tool": t, "why": why})).collect();
    let result = json!({
        "plain_english": plain,
        "format": bin.format,
        "format_name": bin.format.plain(),
        "operating_system": os,
        "kind": bin.kind,
        "architecture": bin.arch.name(),
        "bits": bin.bits,
        "dotnet_arch": managed,
        "entry_point": bin.entry.map(hex),
        "stripped": stripped,
        "symbol_table_stripped": bin.mitigations.stripped,
        "libraries": bin.libraries.iter().take(32).collect::<Vec<_>>(),
        "toolchain_hints": hints,
        "recommended_toolsets": toolsets,
        "next_steps": next,
    });
    let mut r = Report::new(result, plain, if hints.iter().any(|h| h.strength == "weak") { Confidence::Inferred } else { Confidence::Observed });
    r.limitations.push(Limitation::new("heuristic_hints", "toolchain and packer hints come from markers that can be faked or borrowed"));
    if let Some(e) = bin.entry {
        r.locations.push(Location::address(e).with_label("entry point"));
    }
    r
}

// ---------------------------------------------------------------------------------------------
// Overview

pub fn overview(img: &Image, prog: &Program, file_name: &str) -> Report {
    let bin = &img.bin;
    let hints = detect(bin, &img.data);
    let segments: Vec<Value> = if bin.segments.is_empty() {
        bin.sections.iter().take(256).map(|s| json!({"name": s.name, "start": hex(s.addr), "end": hex(s.addr.saturating_add(s.size)), "size": s.size, "perms": perms(s.read, s.write, s.exec), "kind": s.kind, "entropy": s.entropy})).collect()
    } else {
        bin.segments.iter().take(256).map(|s| json!({"name": s.name, "start": hex(s.addr), "end": hex(s.addr.saturating_add(s.size)), "size": s.size, "perms": perms(s.read, s.write, s.exec)})).collect()
    };
    let generated = prog.functions.values().filter(|f| f.name_source == "generated").count();
    let result = json!({
        "file": file_name,
        "format": bin.format,
        "kind": bin.kind,
        "architecture": bin.arch.name(),
        "bits": bin.bits,
        "endianness": if bin.little_endian { "little" } else { "big" },
        "entry_point": bin.entry.map(hex),
        "image_base": hex(bin.image_base),
        "segments": segments,
        "section_count": bin.sections.len(),
        "counts": {
            "functions": prog.functions.len(),
            "functions_with_generated_names": generated,
            "basic_blocks": prog.stats.blocks,
            "instructions": prog.stats.instructions,
            "strings": prog.strings.len(),
            "imports": bin.imports.len(),
            "exports": bin.exports.len(),
            "symbols": bin.symbols.len(),
            "cross_references": prog.stats.xrefs,
            "jump_tables": prog.stats.jump_tables,
        },
        "libraries": bin.libraries,
        "mitigations": bin.mitigations,
        "info": bin.info,
        "toolchain_hints": hints,
        "discovered_by": prog.stats.discovered_by,
        "warnings": bin.warnings,
    });
    let summary = format!(
        "{} {} for {} with {} functions, {} strings, {} imports from {} libraries.",
        bin.format.plain(),
        bin.kind,
        bin.arch.name(),
        prog.functions.len(),
        prog.strings.len(),
        bin.imports.len(),
        bin.libraries.len()
    );
    let summary = if prog.discovery_capped() {
        format!("{summary} Function discovery stopped at an analysis limit, so the function list is incomplete.")
    } else {
        summary
    };
    let mut r = Report::new(result, summary, Confidence::Derived);
    r.limitations = program_limitations(prog);
    if let Some(e) = bin.entry {
        r.locations.push(Location::address(e).with_label("entry point"));
    }
    r
}

fn perms(r: bool, w: bool, x: bool) -> String {
    format!("{}{}{}", if r { 'r' } else { '-' }, if w { 'w' } else { '-' }, if x { 'x' } else { '-' })
}

// ---------------------------------------------------------------------------------------------
// Function dossier

/// Facts about one function: entry, size, blocks, calls, references.
pub fn function_info(prog: &Program, f: &Function, names: Names<'_>) -> Value {
    let callers = prog.callers(f.entry);
    json!({
        "name": fname(prog, names, f.entry),
        "default_name": f.name,
        "name_source": f.name_source,
        "entry": hex(f.entry),
        "end": hex(f.end),
        "size": f.size(),
        "instructions": f.insn_count,
        "basic_blocks": f.blocks.len(),
        "body_ranges": f.blocks.iter().map(|b| json!([hex(b.start), hex(b.end)])).collect::<Vec<_>>(),
        // A tail call (a jump into another function) is a call too.
        "calls_out": f.calls.len() + f.tail_calls.len(),
        "tail_calls": f.tail_calls.len(),
        "callers": callers.len(),
        "returns": f.returns,
        "thunk_of": f.thunk_of,
        "discovered_by": f.discovered_by,
        "jump_tables": f.jump_tables,
        "unresolved_indirect_jumps": f.unresolved_indirect_jumps,
        "truncated": f.truncated,
    })
}

fn strings_used(prog: &Program, f: &Function) -> Vec<Value> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for (from, xs) in prog.xrefs_from.range(f.entry..f.end.max(f.entry + 1)) {
        if !f.contains(*from) {
            continue;
        }
        for x in xs.iter().filter(|x| x.kind == XrefKind::String) {
            if let Some(s) = prog.string_at(x.to)
                && seen.insert(s.addr)
            {
                out.push(json!({"address": hex(s.addr), "from": hex(*from), "text": s.text}));
            }
        }
    }
    out
}

fn refs(prog: &Program, f: &Function, names: Names<'_>, outgoing: bool) -> Vec<Value> {
    let mut out = Vec::new();
    if outgoing {
        for (from, xs) in prog.xrefs_from.range(f.entry..f.end.max(f.entry + 1)) {
            if !f.contains(*from) {
                continue;
            }
            for x in xs {
                if x.kind == XrefKind::Jump && f.contains(x.to) {
                    continue;
                }
                out.push(json!({"from": hex(x.from), "to": hex(x.to), "kind": x.kind, "name": names(x.to).or_else(|| prog.name_at(x.to))}));
            }
        }
    } else if let Some(xs) = prog.xrefs_to.get(&f.entry) {
        for x in xs {
            let caller = prog.function_containing(x.from);
            if caller.is_some_and(|c| c.entry == f.entry) && x.kind == XrefKind::Jump {
                continue;
            }
            out.push(json!({"from": hex(x.from), "to": hex(x.to), "kind": x.kind, "function": caller.map(|c| fname(prog, names, c.entry))}));
        }
    }
    out
}

pub fn callees(prog: &Program, f: &Function, names: Names<'_>) -> Vec<Value> {
    prog.callees(f)
        .into_iter()
        .map(|c| {
            let name = c.target.and_then(names).or(c.name);
            json!({"site": hex(c.site), "target": c.target.map(hex), "name": name, "import": c.import, "indirect": c.indirect})
        })
        .collect()
}

pub fn callers(prog: &Program, f: &Function, names: Names<'_>) -> Vec<Value> {
    prog.callers(f.entry)
        .into_iter()
        .map(|(site, caller)| json!({"site": hex(site), "caller": caller.map(hex), "name": caller.map(|c| fname(prog, names, c))}))
        .collect()
}

/// Category of an imported API, for the API-boundary view.
pub fn api_category(name: &str) -> &'static str {
    let n = name.trim_start_matches('_').to_ascii_lowercase();
    let has = |xs: &[&str]| xs.iter().any(|x| n.contains(x));
    if has(&["socket", "connect", "send", "recv", "http", "internet", "winhttp", "getaddrinfo", "curl", "ssl_", "nsurl", "wsa"]) {
        "network"
    } else if has(&[
        "fopen",
        "open",
        "read",
        "write",
        "createfile",
        "readfile",
        "writefile",
        "unlink",
        "deletefile",
        "stat",
        "mkdir",
        "fclose",
        "fread",
        "fwrite",
        "nsfilemanager",
    ]) {
        "files"
    } else if has(&["exec", "fork", "spawn", "createprocess", "shellexecute", "system", "popen", "kill", "terminateprocess", "ptrace"]) {
        "processes"
    } else if has(&["reg", "nsuserdefaults", "cfpreferences", "getenv", "setenv"]) {
        "settings"
    } else if has(&["crypt", "aes", "sha", "md5", "rand", "bcrypt", "evp_", "cc_sha", "seckey"]) {
        "crypto"
    } else if has(&["malloc", "free", "calloc", "realloc", "virtualalloc", "mmap", "munmap", "heap", "new", "delete", "memcpy", "memset", "memmove"]) {
        "memory"
    } else if has(&["window", "dialog", "messagebox", "button", "nsapp", "uiapp", "gtk_", "qwidget", "msgsend", "sendmessage", "postmessage"]) {
        "user_interface"
    } else if has(&["thread", "mutex", "lock", "semaphore", "dispatch_", "criticalsection", "wait"]) {
        "threads"
    } else if has(&["printf", "puts", "str", "fmt", "scanf", "strlen", "strcmp", "strcpy", "wcs"]) {
        "text"
    } else if has(&["dlopen", "dlsym", "loadlibrary", "getprocaddress"]) {
        "dynamic_loading"
    } else if has(&["exit", "abort", "atexit", "terminate"]) {
        "lifecycle"
    } else {
        "other"
    }
}

/// API boundary of one function: what it imports, grouped, plus indirect dispatch.
pub fn native_api(prog: &Program, f: &Function, names: Names<'_>) -> Report {
    let mut by_cat: BTreeMap<&str, Vec<Value>> = BTreeMap::new();
    let mut internal = Vec::new();
    let mut indirect = Vec::new();
    for c in prog.callees(f) {
        match (&c.name, c.import || prog.functions.get(&c.target.unwrap_or(0)).is_some_and(|x| x.thunk_of.is_some())) {
            (Some(n), true) => {
                let lib = prog.import_slots.values().find(|s| s.name == *n).and_then(|s| s.library.clone());
                by_cat.entry(api_category(n)).or_default().push(json!({"site": hex(c.site), "name": n, "library": lib}));
            }
            (_, _) if c.indirect => indirect.push(json!({"site": hex(c.site)})),
            _ => internal.push(json!({"site": hex(c.site), "target": c.target.map(hex), "name": c.target.map(|t| fname(prog, names, t))})),
        }
    }
    let n_api: usize = by_cat.values().map(Vec::len).sum();
    let result = json!({
        "function": fname(prog, names, f.entry),
        "entry": hex(f.entry),
        "api_calls_by_category": by_cat,
        "internal_calls": internal,
        "unresolved_indirect_calls": indirect,
        "jump_tables": f.jump_tables,
        "unresolved_indirect_jumps": f.unresolved_indirect_jumps,
    });
    let summary = format!(
        "{} makes {n_api} calls into system or library APIs, {} internal calls and {} unresolved indirect calls.",
        fname(prog, names, f.entry),
        internal.len(),
        indirect.len()
    );
    let mut r = Report::new(result, summary, Confidence::Derived);
    if !indirect.is_empty() {
        r = r.limit("indirect_calls_unresolved", "calls through registers or tables were not resolved statically");
    }
    r.locations.push(Location::address(f.entry));
    r
}

/// Everything about one function.
pub fn dossier(img: &Image, prog: &Program, f: &Function, names: Names<'_>) -> Report {
    let pseudo = lift(img, prog, f, names);
    let asm: Vec<Value> = prog.instructions(img, f, true).iter().map(|i| json!({"address": hex(i.addr), "text": i.text()})).collect();
    let du = def_use(img, prog, f, 5000, 12000);
    let api = native_api(prog, f, names);
    let unresolved: Vec<Value> = f.calls.iter().filter(|c| c.target.is_none() && c.import.is_none()).map(|c| json!({"site": hex(c.site)})).collect();
    let referenced_names: Vec<Value> = refs(prog, f, names, true).into_iter().filter(|r| !r["name"].is_null()).collect();
    let result = json!({
        "function": function_info(prog, f, names),
        "pseudocode": pseudo.text,
        "signature": pseudo.signature,
        "assembly": asm,
        "basic_blocks": f.blocks,
        "callers": callers(prog, f, names),
        "callees": callees(prog, f, names),
        "incoming_references": refs(prog, f, names, false),
        "outgoing_references": refs(prog, f, names, true),
        "unresolved_calls": unresolved,
        "referenced_strings": strings_used(prog, f),
        "referenced_names": referenced_names,
        "native_api": api.result,
        "flow_summary": {"parameters": du.parameters, "nodes": du.nodes.len(), "edges": du.edges.len(), "effects": du.effects.len(), "truncated": du.truncated},
        "flow_nodes": du.nodes,
        "flow_edges": du.edges,
        "flow_effects": du.effects,
        "flow_parameters": du.parameters,
        "flow_parameter_uses": du.parameter_uses,
        "comments": [],
    });
    let summary = format!(
        "{} at {:#x}: {} blocks, {} instructions, calls {} functions, called from {} places, uses {} strings.",
        fname(prog, names, f.entry),
        f.entry,
        f.blocks.len(),
        f.insn_count,
        f.calls.len(),
        prog.callers(f.entry).len(),
        result["referenced_strings"].as_array().map(Vec::len).unwrap_or(0)
    );
    let mut r = Report::new(result, summary, Confidence::Inferred);
    r.limitations = pseudo.limitations.iter().map(|(c, m)| Limitation::new(c.clone(), m.clone())).collect();
    r.limitations.push(Limitation::new("pseudo_code_inferred", "the pseudo-C is a reading aid built by the clean-room lifter, not compiler output"));
    r.locations.push(Location::address(f.entry).with_label(fname(prog, names, f.entry)));
    r
}

// ---------------------------------------------------------------------------------------------
// Call graph and paths

fn neighbours(prog: &Program, entry: u64, forward: bool) -> Vec<(u64, Option<u64>, String)> {
    // (site, function entry or None for imports, label)
    if forward {
        let Some(f) = prog.functions.get(&entry) else { return Vec::new() };
        prog.callees(f)
            .into_iter()
            .filter_map(|c| match (c.target, c.import, &c.name) {
                (Some(t), _, _) if prog.functions.contains_key(&t) => Some((c.site, Some(t), c.name.clone().unwrap_or_default())),
                (_, true, Some(n)) => Some((c.site, None, n.clone())),
                _ => None,
            })
            .collect()
    } else {
        prog.callers(entry).into_iter().filter_map(|(site, f)| f.map(|f| (site, Some(f), String::new()))).collect()
    }
}

/// Callers or callees by depth, bounded.
pub fn call_graph(prog: &Program, start: u64, forward: bool, max_depth: usize, max_nodes: usize, names: Names<'_>) -> Report {
    let mut levels: BTreeMap<usize, Vec<Value>> = BTreeMap::new();
    let mut edges = Vec::new();
    let mut seen: BTreeSet<u64> = BTreeSet::from([start]);
    let mut seen_imports: BTreeSet<String> = BTreeSet::new();
    let mut q = VecDeque::from([(start, 0usize)]);
    let mut truncated = false;
    let mut limitations = Vec::new();
    while let Some((cur, d)) = q.pop_front() {
        if d >= max_depth {
            if !neighbours(prog, cur, forward).is_empty() {
                truncated = true;
            }
            continue;
        }
        for (site, n, label) in neighbours(prog, cur, forward) {
            let (from, to) = if forward { (cur, n) } else { (n.unwrap_or(0), Some(cur)) };
            edges.push(json!({"site": hex(site), "from": hex(from), "to": to.map(hex), "to_import": if n.is_none() { Some(label.clone()) } else { None }}));
            match n {
                Some(n) => {
                    if seen.len() >= max_nodes {
                        truncated = true;
                        continue;
                    }
                    if seen.insert(n) {
                        levels.entry(d + 1).or_default().push(json!({"address": hex(n), "name": fname(prog, names, n)}));
                        q.push_back((n, d + 1));
                    }
                }
                None => {
                    if seen_imports.insert(label.clone()) {
                        levels.entry(d + 1).or_default().push(json!({"import": label}));
                    }
                }
            }
        }
    }
    if truncated {
        limitations.push(Limitation::new("truncated", format!("stopped at depth {max_depth} or {max_nodes} functions")));
    }
    limitations.push(Limitation::new("direct_calls_only", "only statically resolved calls are followed; calls through pointers are not"));
    let total: usize = levels.values().map(Vec::len).sum();
    let result = json!({
        "root": {"address": hex(start), "name": fname(prog, names, start)},
        "direction": if forward { "forward" } else { "backward" },
        "levels": levels.iter().map(|(d, v)| (d.to_string(), json!(v))).collect::<serde_json::Map<String, Value>>(),
        "edges": edges,
        "truncated": truncated,
        "limitations": limitations.iter().map(|l| l.message.clone()).collect::<Vec<_>>(),
    });
    let summary = format!(
        "{} {} {total} functions and imports (within {} levels).",
        fname(prog, names, start),
        if forward { "reaches" } else { "is reached from" },
        levels.len()
    );
    let mut r = Report::new(result, summary, Confidence::Derived);
    r.limitations = limitations;
    r.locations.push(Location::address(start));
    r
}

/// Where a call path should end: a function, or (forward only) a call to an import.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Goal<'a> {
    Function(u64),
    Import(&'a str),
}

/// Shortest direct-call path from `start` to `goal`.
pub fn call_path(prog: &Program, start: u64, goal: Option<Goal<'_>>, forward: bool, names: Names<'_>) -> Report {
    const MAX_VISIT: usize = 100_000;
    let is_goal_fn = |a: u64| goal == Some(Goal::Function(a));
    let mut prev: BTreeMap<u64, (u64, u64)> = BTreeMap::new();
    let mut seen = BTreeSet::from([start]);
    let mut q = VecDeque::from([start]);
    let mut found = is_goal_fn(start);
    // (caller, call site) of the import call that ends the path.
    let mut import_hit = None;
    let mut truncated = false;
    while let Some(cur) = q.pop_front() {
        if found {
            break;
        }
        for (site, n, label) in neighbours(prog, cur, forward) {
            let Some(n) = n else {
                if let Some(Goal::Import(g)) = goal
                    && label.eq_ignore_ascii_case(g)
                {
                    import_hit = Some((cur, site));
                    found = true;
                    break;
                }
                continue;
            };
            if seen.len() >= MAX_VISIT {
                truncated = true;
                break;
            }
            if seen.insert(n) {
                prev.insert(n, (cur, site));
                if is_goal_fn(n) {
                    found = true;
                    break;
                }
                q.push_back(n);
            }
        }
    }
    let goal_name = |g: Goal<'_>| match g {
        Goal::Function(a) => fname(prog, names, a),
        Goal::Import(n) => n.to_string(),
    };
    let mut residual = Vec::new();
    let (status, path) = match goal {
        Some(g) if found => {
            let mut path = Vec::new();
            let mut cur = start;
            if let (Goal::Import(n), Some((caller, site))) = (g, import_hit) {
                path.push(json!({"name": n, "import": true}));
                path.push(json!({"address": hex(caller), "name": fname(prog, names, caller), "call_site": hex(site)}));
                cur = caller;
            } else if let Goal::Function(a) = g {
                path.push(json!({"address": hex(a), "name": fname(prog, names, a)}));
                cur = a;
            }
            while let Some(&(p, site)) = prev.get(&cur) {
                path.push(json!({"address": hex(p), "name": fname(prog, names, p), "call_site": hex(site)}));
                cur = p;
                if path.len() > 10_000 {
                    break;
                }
            }
            path.reverse();
            ("reached", path)
        }
        Some(_) => {
            residual.push("no direct-call path found; the link may go through function pointers, callbacks, virtual calls or another thread".to_string());
            ("not_reached", Vec::new())
        }
        None => ("no_goal", seen.iter().take(500).map(|a| json!({"address": hex(*a), "name": fname(prog, names, *a)})).collect()),
    };
    let unresolved: usize =
        seen.iter().filter_map(|a| prog.functions.get(a)).map(|f| f.calls.iter().filter(|c| c.target.is_none() && c.import.is_none()).count()).sum();
    if unresolved > 0 {
        residual.push(format!("{unresolved} indirect calls on the way were not followed"));
    }
    let result = json!({
        "start": {"address": hex(start), "name": fname(prog, names, start)},
        "goal": goal.map(|g| match g {
            Goal::Function(a) => json!({"address": hex(a), "name": fname(prog, names, a)}),
            Goal::Import(n) => json!({"name": n, "import": true}),
        }),
        "direction": if forward { "forward" } else { "backward" },
        "goal_result": status,
        "path": path,
        "visited": seen.len(),
        "still_unknown": residual,
        "truncated": truncated,
    });
    let summary = match status {
        "reached" => format!("{} reaches {} in {} calls.", fname(prog, names, start), goal.map(goal_name).unwrap_or_default(), path.len().saturating_sub(1)),
        "not_reached" => {
            format!("No direct-call path from {} to {} (absence is not proof).", fname(prog, names, start), goal.map(goal_name).unwrap_or_default())
        }
        _ => format!("{} reaches {} functions.", fname(prog, names, start), seen.len().saturating_sub(1)),
    };
    let mut r = Report::new(result, summary, Confidence::Derived).limit("direct_calls_only", "only statically resolved calls are followed");
    r.locations.push(Location::address(start));
    if let Some(Goal::Function(a)) = goal {
        r.locations.push(Location::address(a));
    }
    r
}

// ---------------------------------------------------------------------------------------------
// Feature tracing and name lookups

fn matches(hay: &str, needle: &str, case_sensitive: bool) -> bool {
    if case_sensitive { hay.contains(needle) } else { hay.to_lowercase().contains(&needle.to_lowercase()) }
}

/// Literal query → strings, functions and imports that match, and the code using them.
pub fn feature_paths(prog: &Program, query: &str, case_sensitive: bool, names: Names<'_>) -> Report {
    const CAP: usize = 200;
    let mut strings = Vec::new();
    let mut containing: BTreeMap<u64, Vec<String>> = BTreeMap::new();
    let mut matching_strings = 0;
    for s in prog.strings.iter().filter(|s| matches(&s.text, query, case_sensitive)) {
        matching_strings += 1;
        if strings.len() < CAP {
            let users: Vec<Value> = prog
                .xrefs_to
                .get(&s.addr)
                .map(|xs| {
                    xs.iter()
                        .take(64)
                        .map(|x| {
                            let f = prog.function_containing(x.from);
                            if let Some(f) = f {
                                containing.entry(f.entry).or_default().push(format!("uses string \"{}\"", s.text.chars().take(60).collect::<String>()));
                            }
                            json!({"from": hex(x.from), "kind": x.kind, "function": f.map(|f| fname(prog, names, f.entry))})
                        })
                        .collect()
                })
                .unwrap_or_default();
            strings.push(json!({"address": hex(s.addr), "text": s.text, "references": users}));
        }
    }
    let mut procs = Vec::new();
    let mut matching_functions = 0;
    for f in prog.functions.values() {
        let n = fname(prog, names, f.entry);
        if matches(&n, query, case_sensitive) {
            matching_functions += 1;
            containing.entry(f.entry).or_default().push("name matches".into());
            if procs.len() < CAP {
                procs.push(json!({"address": hex(f.entry), "name": n}));
            }
        }
    }
    let mut imports = Vec::new();
    let mut matching_imports = 0;
    for (slot, s) in prog.import_slots.iter().filter(|(_, s)| matches(&s.name, query, case_sensitive)) {
        matching_imports += 1;
        if imports.len() < CAP {
            let users: Vec<Value> = prog
                .xrefs_to
                .get(slot)
                .map(|xs| {
                    xs.iter()
                        .take(64)
                        .filter_map(|x| prog.function_containing(x.from))
                        .map(|f| json!({"function": fname(prog, names, f.entry), "address": hex(f.entry)}))
                        .collect()
                })
                .unwrap_or_default();
            for u in &users {
                if let Some(a) = u["address"].as_str().and_then(|a| u64::from_str_radix(a.trim_start_matches("0x"), 16).ok()) {
                    containing.entry(a).or_default().push(format!("calls {}", s.name));
                }
            }
            imports.push(json!({"slot": hex(*slot), "name": s.name, "library": s.library, "used_by": users}));
        }
    }
    let funcs: Vec<Value> = containing.iter().take(CAP).map(|(a, why)| json!({"address": hex(*a), "name": fname(prog, names, *a), "why": why})).collect();
    let summary = format!(
        "\"{query}\": {} matching strings, {} matching function names, {} matching imports; {} functions involved.",
        matching_strings,
        matching_functions,
        matching_imports,
        containing.len()
    );
    let locations: Vec<Location> = containing.keys().take(50).map(|a| Location::address(*a)).collect();
    let truncated = matching_strings > CAP || matching_functions > CAP || matching_imports > CAP || containing.len() > CAP;
    let result = json!({"query": query, "case_sensitive": case_sensitive, "strings": strings, "function_names": procs, "imports": imports, "functions": funcs, "truncated": truncated});
    let mut r = Report::new(result, summary, Confidence::Derived);
    r.locations = locations;
    if truncated {
        r = r.limit("truncated", format!("results capped at {CAP} entries per category"));
    }
    if containing.is_empty() {
        r = r.limit("no_match", "nothing matched; the text may be built at run time, encrypted, or come from a resource file (absence is not proof)");
    }
    r
}

/// Resolve a name (function, data symbol, import) to its address.
pub fn resolve_name(prog: &Program, user: &BTreeMap<u64, String>, name: &str) -> Option<u64> {
    if let Some((a, _)) = user.iter().find(|(_, n)| n.as_str() == name) {
        return Some(*a);
    }
    if let Some(f) = prog.function_by_name(name) {
        return Some(f.entry);
    }
    if let Some((a, _)) = prog.data_names.iter().find(|(_, n)| n.as_str() == name) {
        return Some(*a);
    }
    prog.import_slots
        .iter()
        .find(|(_, s)| s.name == name || craft_anything_disasm::slot_label(s) == name || s.name.trim_start_matches('_') == name)
        .map(|(a, _)| *a)
}

pub fn xrefs_to_name(prog: &Program, user: &BTreeMap<u64, String>, name: &str, names: Names<'_>) -> Report {
    let Some(addr) = resolve_name(prog, user, name) else {
        let r = Report::new(
            json!({"name": name, "found": false, "reason": "name_not_found", "references": []}),
            format!("No function, symbol or import is named {name}."),
            Confidence::Derived,
        );
        return r.limit("name_not_found", "check the spelling with native_named_addresses_list or native_functions_search");
    };
    let mut targets = vec![addr];
    // Calls to an import also go through its stub.
    if let Some(s) = prog.import_slots.get(&addr) {
        targets.extend(prog.functions.values().filter(|f| f.thunk_of.as_deref() == Some(s.name.as_str())).map(|f| f.entry));
        targets.extend(prog.import_slots.iter().filter(|(_, x)| x.name == s.name).map(|(a, _)| *a));
    }
    targets.sort_unstable();
    targets.dedup();
    let mut refs = Vec::new();
    for t in &targets {
        for x in prog.xrefs_to.get(t).map(Vec::as_slice).unwrap_or(&[]) {
            refs.push(json!({"from": hex(x.from), "to": hex(x.to), "kind": x.kind, "function": prog.function_containing(x.from).map(|f| fname(prog, names, f.entry))}));
        }
    }
    let summary = format!("{name} ({addr:#x}) is referenced from {} places.", refs.len());
    let mut r = Report::new(
        json!({"name": name, "found": true, "address": hex(addr), "also_via": targets.iter().filter(|t| **t != addr).map(|t| hex(*t)).collect::<Vec<_>>(), "references": refs}),
        summary,
        Confidence::Derived,
    );
    r.locations.push(Location::address(addr).with_label(name));
    r
}

// ---------------------------------------------------------------------------------------------
// Objective-C and Swift

fn glob_like(name: &str, pattern: &str) -> bool {
    pattern.is_empty() || name.to_lowercase().contains(&pattern.to_lowercase())
}

pub fn objc_classes(img: &Image, pattern: &str) -> Report {
    let meta = craft_anything_formats::macho::objc_metadata(&img.data, &img.bin);
    let mut labels: Vec<String> = meta
        .classes
        .iter()
        .map(|c| match &c.category {
            Some(cat) => format!("{}({cat})", c.name),
            None => c.name.clone(),
        })
        .filter(|n| glob_like(n, pattern))
        .collect();
    labels.sort();
    labels.dedup();
    let classes: Vec<Value> = meta
        .classes
        .iter()
        .filter(|c| glob_like(&c.name, pattern))
        .map(|c| json!({"name": c.name, "category": c.category, "address": hex(c.addr), "superclass": c.superclass, "swift": c.swift, "methods": c.methods.len()}))
        .collect();
    let summary =
        format!("{} Objective-C classes and categories{}.", labels.len(), if pattern.is_empty() { String::new() } else { format!(" matching \"{pattern}\"") });
    let mut r = Report::new(json!({"classes": labels, "details": classes}), summary, Confidence::Observed);
    if img.bin.format != Format::MachO {
        r = r.limit("not_macho", "Objective-C metadata only exists in Mach-O images");
    }
    r.limitations.extend(meta.warnings.iter().take(20).map(|w| Limitation::new("objc_parse", w.clone())));
    r.limitations.push(Limitation::new("static_metadata_only", "classes registered at run time (objc_allocateClassPair) are not listed"));
    r
}

pub fn objc_protocols(img: &Image) -> Report {
    let meta = craft_anything_formats::macho::objc_metadata(&img.data, &img.bin);
    let mut protocols: Vec<Value> = meta.protocols.iter().map(|p| json!({"name": p.name, "address": hex(p.addr), "methods": p.methods})).collect();
    // Swift protocol descriptors from symbols.
    let swift: BTreeSet<String> =
        img.bin.symbols.iter().filter_map(|s| craft_anything_formats::swift::classify(&s.name)).filter(|c| c.category == "protocols").map(|c| c.path).collect();
    for s in &swift {
        protocols.push(json!({"name": s, "swift": true}));
    }
    let summary = format!("{} Objective-C protocols and {} Swift protocols.", meta.protocols.len(), swift.len());
    let mut r = Report::new(json!({"protocols": protocols}), summary, Confidence::Observed);
    if img.bin.format != Format::MachO {
        r = r.limit("not_macho", "Objective-C metadata only exists in Mach-O images");
    }
    r
}

pub fn swift_types(bin: &Binary, category: Option<&str>, pattern: Option<&str>) -> Report {
    let mut groups: BTreeMap<&str, BTreeMap<String, Vec<String>>> = BTreeMap::new();
    let mut total = 0usize;
    for s in &bin.symbols {
        let Some(c) = craft_anything_formats::swift::classify(&s.name) else { continue };
        if category.is_some_and(|cat| cat != c.category) || pattern.is_some_and(|p| !glob_like(&c.path, p)) {
            continue;
        }
        total += 1;
        let roles = groups.entry(c.category).or_default().entry(c.path.clone()).or_default();
        if roles.len() < 16 && !roles.contains(&c.role.to_string()) {
            roles.push(c.role.into());
        }
    }
    let counts: BTreeMap<&str, usize> = groups.iter().map(|(k, v)| (*k, v.len())).collect();
    let summary = format!("{total} Swift symbols describing {} types.", counts.values().sum::<usize>());
    let mut r = Report::new(json!({"counts": counts, "types": groups, "symbols_examined": bin.symbols.len()}), summary, Confidence::Inferred);
    r.limitations.push(Limitation::new(
        "mangling_heuristic",
        "types are classified from the mangled names without a full demangler; nested generic types may be misfiled",
    ));
    if bin.mitigations.stripped {
        r.limitations.push(Limitation::new("stripped_binary", "stripped images keep few Swift symbols"));
    }
    r
}

pub fn dispatch_metadata(img: &Image, prog: &Program, max_records: usize, names: Names<'_>) -> Report {
    let meta = craft_anything_formats::macho::objc_metadata(&img.data, &img.bin);
    let mut records = Vec::new();
    'outer: for c in &meta.classes {
        for m in &c.methods {
            if records.len() >= max_records {
                break 'outer;
            }
            records.push(json!({
                "kind": "objc_method",
                "class": c.name,
                "category": c.category,
                "selector": m.selector,
                "method_kind": m.kind,
                "types": m.types,
                "implementation": m.imp.map(hex),
                "implementation_name": m.imp.map(|a| fname(prog, names, a)),
            }));
        }
    }
    for s in &img.bin.symbols {
        if records.len() >= max_records {
            break;
        }
        if let Some(c) = craft_anything_formats::swift::classify(&s.name)
            && matches!(c.role, "Objective-C thunk" | "protocol witness table" | "metadata accessor")
        {
            records.push(json!({"kind": "swift_symbol", "symbol": s.name, "type": c.path, "role": c.role, "address": hex(s.addr)}));
        }
    }
    let truncated = records.len() >= max_records;
    let summary = format!("{} dispatch records ({} Objective-C classes, {} selectors referenced).", records.len(), meta.classes.len(), meta.selectors.len());
    let mut r = Report::new(json!({"records": records, "selectors_referenced": meta.selectors.len(), "truncated": truncated}), summary, Confidence::Observed);
    if truncated {
        r = r.limit("truncated", format!("stopped at max_records={max_records}"));
    }
    r.limitations.push(Limitation::new("symbol_level", "dispatch is read from static metadata and symbols; dynamic method resolution is not modelled"));
    r
}

/// UI action / selector → handlers → static calls.
pub fn ui_action(img: &Image, prog: &Program, action: &str, max_depth: usize, max_nodes: usize, max_edges: usize, names: Names<'_>) -> Report {
    let meta = craft_anything_formats::macho::objc_metadata(&img.data, &img.bin);
    let mut handlers: Vec<(u64, String)> = Vec::new();
    for c in &meta.classes {
        for m in &c.methods {
            if (m.selector == action || m.selector.trim_end_matches(':') == action.trim_end_matches(':') || glob_like(&m.selector, action))
                && let Some(imp) = m.imp
            {
                handlers.push((imp, format!("{}[{} {}] (Objective-C method)", m.kind, c.name, m.selector)));
            }
        }
    }
    for f in prog.functions.values() {
        let n = fname(prog, names, f.entry);
        if glob_like(&n, action) && !handlers.iter().any(|(a, _)| *a == f.entry) {
            handlers.push((f.entry, format!("{n} (name matches)")));
        }
    }
    // Code that references the action as a string (selector registration, command tables).
    for s in prog.strings.iter().filter(|s| s.text == action || s.text.trim_end_matches(':') == action.trim_end_matches(':')) {
        for x in prog.xrefs_to.get(&s.addr).map(Vec::as_slice).unwrap_or(&[]) {
            if let Some(f) = prog.function_containing(x.from)
                && !handlers.iter().any(|(a, _)| *a == f.entry)
            {
                handlers.push((f.entry, format!("{} (uses the string \"{}\")", fname(prog, names, f.entry), s.text)));
            }
        }
    }
    handlers.truncate(max_nodes);
    let mut nodes: BTreeMap<u64, Value> = BTreeMap::new();
    let mut edges: Vec<Value> = Vec::new();
    let mut truncated = false;
    let mut q: VecDeque<(u64, usize)> = VecDeque::new();
    for (a, why) in &handlers {
        nodes.insert(*a, json!({"address": hex(*a), "name": fname(prog, names, *a), "depth": 0, "role": "handler", "why": why}));
        q.push_back((*a, 0));
    }
    while let Some((cur, d)) = q.pop_front() {
        if d >= max_depth {
            continue;
        }
        let Some(f) = prog.functions.get(&cur) else { continue };
        for c in prog.callees(f) {
            if edges.len() >= max_edges {
                truncated = true;
                break;
            }
            edges.push(json!({"from": hex(cur), "site": hex(c.site), "to": c.target.map(hex), "name": c.target.and_then(names).or(c.name.clone()), "import": c.import}));
            if let Some(t) = c.target.filter(|t| prog.functions.contains_key(t)) {
                if nodes.len() >= max_nodes {
                    truncated = true;
                    continue;
                }
                if let std::collections::btree_map::Entry::Vacant(e) = nodes.entry(t) {
                    e.insert(json!({"address": hex(t), "name": fname(prog, names, t), "depth": d + 1, "role": "callee"}));
                    q.push_back((t, d + 1));
                }
            }
        }
    }
    let summary = if handlers.is_empty() {
        format!("No handler found for \"{action}\" (absence is not proof).")
    } else {
        format!("\"{action}\": {} handlers reaching {} functions through {} static calls.", handlers.len(), nodes.len(), edges.len())
    };
    let mut r = Report::new(
        json!({"action": action, "handlers": handlers.iter().map(|(a, w)| json!({"address": hex(*a), "why": w})).collect::<Vec<_>>(), "nodes": nodes.into_values().collect::<Vec<_>>(), "edges": edges, "truncated": truncated}),
        summary,
        Confidence::Inferred,
    );
    r.limitations.push(Limitation::new(
        "best_effort",
        "handlers are matched by selector, name or string; target-action wiring in nib/storyboard files and run-time registration are not followed",
    ));
    r.limitations.push(Limitation::new("direct_calls_only", "objc_msgSend and other dynamic dispatch is not resolved to its receiver"));
    if truncated {
        r.limitations.push(Limitation::new("truncated", "hit max_nodes or max_edges"));
    }
    r.locations = handlers.iter().take(50).map(|(a, _)| Location::address(*a)).collect();
    r
}

// ---------------------------------------------------------------------------------------------
// Value flow

pub struct ValueTraceOpts {
    pub max_depth: usize,
    pub max_functions: usize,
    pub max_call_sites: usize,
    pub max_nodes: usize,
    pub max_edges: usize,
    pub offset: usize,
    pub limit: usize,
}

pub fn value_trace(img: &Image, prog: &Program, f: &Function, o: &ValueTraceOpts, names: Names<'_>) -> Report {
    let du = def_use(img, prog, f, o.max_nodes, o.max_edges);
    // Follow calls: which callees receive values (bounded).
    let mut functions = vec![json!({"address": hex(f.entry), "name": fname(prog, names, f.entry), "depth": 0, "parameters": du.parameters})];
    let mut seen = BTreeSet::from([f.entry]);
    let mut q = VecDeque::from([(f.entry, 0usize)]);
    let mut sites = 0usize;
    let mut call_args = Vec::new();
    while let Some((cur, d)) = q.pop_front() {
        if d >= o.max_depth || functions.len() >= o.max_functions {
            continue;
        }
        let Some(cf) = prog.functions.get(&cur) else { continue };
        for c in &cf.calls {
            if sites >= o.max_call_sites {
                break;
            }
            sites += 1;
            if let Some(t) = c.target.filter(|t| prog.functions.contains_key(t))
                && functions.len() < o.max_functions
                && seen.insert(t)
                && let Some(tf) = prog.functions.get(&t)
            {
                let tdu = def_use(img, prog, tf, o.max_nodes.min(2000), o.max_edges.min(4000));
                call_args.push(json!({"site": hex(c.site), "callee": fname(prog, names, t), "callee_parameters": tdu.parameters}));
                functions.push(json!({"address": hex(t), "name": fname(prog, names, t), "depth": d + 1, "parameters": tdu.parameters}));
                q.push_back((t, d + 1));
            }
        }
    }
    let total = du.nodes.len();
    let page: Vec<_> = du.nodes.iter().skip(o.offset).take(o.limit).collect();
    let ids: BTreeSet<usize> = page.iter().map(|n| n.id).collect();
    let page_edges: Vec<_> = du.edges.iter().filter(|e| ids.contains(&e.to) || ids.contains(&e.from)).collect();
    let next = (o.offset + page.len() < total).then_some(o.offset + page.len());
    let summary = format!(
        "{}: {} operations, {} def-use edges, parameters {:?}, {} side effects; followed {} callees.",
        fname(prog, names, f.entry),
        total,
        du.edges.len(),
        du.parameters,
        du.effects.len(),
        functions.len() - 1
    );
    let result = json!({
        "function": {"address": hex(f.entry), "name": fname(prog, names, f.entry)},
        "parameters": du.parameters,
        "parameter_uses": du.parameter_uses,
        "effects": du.effects,
        "nodes": page,
        "edges": page_edges,
        "functions": functions,
        "call_arguments": call_args,
        "page": {"offset": o.offset, "limit": o.limit, "total": total, "next_offset": next},
        "truncated": du.truncated,
    });
    let mut r = Report::new(result, summary, Confidence::Derived);
    r.limitations.push(Limitation::new("register_level", "values are tracked through registers only; memory and stack slots are not followed"));
    if du.truncated {
        r.limitations.push(Limitation::new("truncated", "hit max_nodes or max_edges"));
    }
    r.locations.push(Location::address(f.entry));
    r
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_disasm::{Limits, NoControl};
    use craft_anything_testkit as tk;
    use std::sync::Arc;

    fn setup(bytes: Vec<u8>) -> (Image, Program) {
        let img = Image::parse(Arc::from(bytes)).unwrap();
        let p = Program::analyze(&img, &Limits::default(), &NoControl).unwrap();
        (img, p)
    }

    #[test]
    fn triage_does_not_call_go_or_dotnet_stripped() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, false);
        let bin = craft_anything_formats::parse_binary(&elf).unwrap();
        assert!(bin.mitigations.stripped);
        let plain = triage(&bin, &elf, "s");
        assert!(plain.summary.contains("(stripped)"), "{}", plain.summary);
        assert_eq!(plain.result["stripped"], true);

        let mut go = elf.clone();
        go.extend_from_slice(b"\xff Go buildinf:\x08\x02go1.22.3\0");
        let t = triage(&bin, &go, "g");
        assert!(!t.summary.contains("(stripped)"), "{}", t.summary);
        assert!(t.summary.contains("pclntab"), "{}", t.summary);
        assert_eq!(t.result["stripped"], false);
        assert_eq!(t.result["symbol_table_stripped"], true);

        let mut net = bin.clone();
        net.info.insert("dotnet".into(), "v4.0.30319".into());
        let t = triage(&net, &elf, "n");
        assert!(!t.summary.contains("(stripped)"), "{}", t.summary);
        assert!(t.summary.contains(".NET metadata"), "{}", t.summary);
    }

    #[test]
    fn triage_calls_an_anycpu_assembly_any_cpu_not_32_bit() {
        let data = tk::managed::managed_assembly(1);
        let bin = craft_anything_formats::parse_binary(&data).unwrap();
        assert_eq!(bin.bits, 32, "the PE header itself is PE32");
        let t = triage(&bin, &data, "Sample.dll");
        assert_eq!(t.result["dotnet_arch"], "anycpu");
        assert!(t.summary.contains("any CPU") && !t.summary.contains("32-bit"), "{}", t.summary);
    }

    #[test]
    fn calls_out_counts_tail_calls() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let (_, p) = setup(elf);
        let none = |_: u64| None;
        let mut main = p.function_by_name("main").unwrap().clone();
        let before = function_info(&p, &main, &none)["calls_out"].as_u64().unwrap();
        main.tail_calls.push(p.function_by_name("helper").unwrap().entry);
        let info = function_info(&p, &main, &none);
        assert_eq!(info["calls_out"].as_u64().unwrap(), before + 1);
        assert_eq!(info["tail_calls"], 1);
    }

    #[test]
    fn workflows_on_elf() {
        let (elf, l) = tk::elf64(tk::ElfArch::X86_64, true);
        let (img, p) = setup(elf);
        let none = |_: u64| None;
        let t = triage(&img.bin, &img.data, "sample");
        assert!(t.summary.contains("Linux"), "{}", t.summary);
        let o = overview(&img, &p, "sample");
        assert_eq!(o.result["counts"]["functions"], 4);
        let main = p.function_by_name("main").unwrap();
        let d = dossier(&img, &p, main, &none);
        assert!(d.result["pseudocode"].as_str().unwrap().contains("puts"));
        assert_eq!(d.result["referenced_strings"][0]["text"], tk::HELLO);
        let g = call_graph(&p, main.entry, true, 3, 100, &none);
        assert!(g.result["levels"]["1"].as_array().unwrap().len() >= 3);
        let helper = p.function_by_name("helper").unwrap();
        let path = call_path(&p, main.entry, Some(Goal::Function(helper.entry)), true, &none);
        assert_eq!(path.result["goal_result"], "reached");
        let back = call_path(&p, helper.entry, Some(Goal::Function(main.entry)), true, &none);
        assert_eq!(back.result["goal_result"], "not_reached");
        // An import is a goal too: main calls puts.
        let imp = call_path(&p, main.entry, Some(Goal::Import("PUTS")), true, &none);
        assert_eq!(imp.result["goal_result"], "reached", "{}", imp.summary);
        let steps = imp.result["path"].as_array().unwrap();
        assert_eq!(steps.first().unwrap()["name"], "main");
        assert_eq!(steps.last().unwrap()["import"], true);
        assert_eq!(imp.result["goal"]["import"], true);
        let none_such = call_path(&p, main.entry, Some(Goal::Import("CreateWindowExW")), true, &none);
        assert_eq!(none_such.result["goal_result"], "not_reached");
        let tf = feature_paths(&p, "settings", false, &none);
        assert_eq!(tf.result["functions"][0]["address"], format!("{:#x}", l.code_va + tk::x64::HIDDEN));
        let x = xrefs_to_name(&p, &BTreeMap::new(), "puts", &none);
        assert_eq!(x.result["found"], true);
        assert!(!x.result["references"].as_array().unwrap().is_empty());
        let missing = xrefs_to_name(&p, &BTreeMap::new(), "nope", &none);
        assert_eq!(missing.result["reason"], "name_not_found");
        let api = native_api(&p, main, &none);
        assert_eq!(api.result["api_calls_by_category"]["text"][0]["name"], "puts");
        let v = value_trace(
            &img,
            &p,
            main,
            &ValueTraceOpts { max_depth: 2, max_functions: 8, max_call_sites: 64, max_nodes: 500, max_edges: 1000, offset: 0, limit: 5 },
            &none,
        );
        assert_eq!(v.result["nodes"].as_array().unwrap().len(), 5);
        assert!(v.result["page"]["next_offset"].is_number());
    }

    #[test]
    fn apple_workflows() {
        let (img, p) = setup(tk::macho64());
        let none = |_: u64| None;
        let c = objc_classes(&img, "");
        assert_eq!(c.result["classes"][0], tk::OBJC_CLASS);
        let pr = objc_protocols(&img);
        assert_eq!(pr.result["protocols"][0]["name"], tk::OBJC_PROTOCOL);
        let d = dispatch_metadata(&img, &p, 100, &none);
        assert_eq!(d.result["records"][0]["selector"], tk::OBJC_SELECTOR);
        let u = ui_action(&img, &p, "tapButton:", 4, 50, 100, &none);
        assert_eq!(u.result["handlers"].as_array().unwrap().len(), 1, "{}", u.result);
        assert!(u.summary.contains("1 handlers"));
        let s = swift_types(&img.bin, None, None);
        assert_eq!(s.result["symbols_examined"], 4);
        let t = triage(&img.bin, &img.data, "app");
        assert!(t.result["recommended_toolsets"].as_array().unwrap().iter().any(|x| x == "apple"));
    }

    /// #351: feature_paths reports actual matching function count beyond CAP and records truncated limitation.
    #[test]
    fn feature_paths_reports_accurate_matching_function_count_beyond_cap() {
        let names: Vec<String> = (0..205).map(|i| format!("beacon_{i:03}")).collect();
        let funcs: Vec<(&str, Vec<u8>)> = names.iter().map(|s| (s.as_str(), vec![0x55, 0x48, 0x89, 0xe5, 0x5d, 0xc3])).collect();
        let bytes = tk::program_facts::elf_with_functions(&funcs);
        let (_, p) = setup(bytes);
        let none = |_: u64| None;
        let r = feature_paths(&p, "beacon_", false, &none);
        assert_eq!(r.result["function_names"].as_array().unwrap().len(), 200, "capped at 200");
        assert_eq!(r.result["functions"].as_array().unwrap().len(), 200, "capped at 200");
        assert_eq!(r.result["truncated"], true);
        assert!(r.summary.contains("205 matching function names"), "summary must report actual count: {}", r.summary);
        assert!(r.summary.contains("205 functions involved"), "summary must report actual involved count: {}", r.summary);
        assert!(r.limitations.iter().any(|l| l.code == "truncated"), "must include truncated limitation");
    }
}
