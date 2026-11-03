//! Solana sBPF (and classic eBPF) static analysis: parse the ELF (machine type `EM_BPF`),
//! report sections, syscalls and relocations, discover functions, and disassemble the code into
//! a paged listing with a simple control-flow view and a small pseudo form. Built-in, clean-room,
//! pure Rust — nothing is executed.

use super::native_common::{page, spec};
use super::static_input::{self, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_disasm::sbpf;
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, Limitation, Location, ToolError};
use craft_anything_formats::solana;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    let e = Effects::EVIDENCE;
    vec![
        spec(
            "formats_sbpf_show",
            "Solana program (sBPF)",
            "Inspect a Solana on-chain program or classic eBPF object (an ELF whose machine type is EM_BPF=247): the sBPF version (guessed from e_flags), sections (.text, .rodata, relocation tables), the dynamic symbol table, relocations with their R_BPF_* types, the syscalls it calls (resolved by the murmur3 hash of the helper name — sol_log_, sol_invoke_signed_*, …), the entrypoint, discovered functions with basic blocks, and a paged disassembly listing with jump/call targets and a small pseudo form. Built-in decoder; nothing is executed. Honest limits: no account-model semantics and no Anchor IDL unless supplied separately.",
            "Read a Solana program: what it imports (syscalls), its functions, and its instructions.",
            Toolset::Formats,
            e | Effects::CARRIES_TARGET_CONTENT,
            Requires::Nothing,
            schema_of::<InspectParams>,
            formats_sbpf_show,
        ),
        spec(
            "formats_sbpf_disassemble",
            "Disassemble sBPF code",
            "Disassemble a range of eBPF / Solana sBPF bytecode into an instruction listing (address, mnemonic, operands, and resolved jump/call targets). Give a file (ELF with EM_BPF, or raw bytecode with encoding=raw) and an optional byte offset and length into the code. Built-in decoder; nothing is executed.",
            "Turn a span of Solana/eBPF bytecode into readable instructions.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<DisasmParams>,
            formats_sbpf_disassemble,
        ),
    ]
}

fn d_limit() -> usize {
    200
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Encoding {
    /// ELF when the file starts with the ELF magic, raw bytecode otherwise.
    #[default]
    Auto,
    /// Force ELF parsing (machine type EM_BPF).
    Elf,
    /// Treat the whole file as raw sBPF bytecode (no ELF, no sections or syscalls).
    Raw,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Detail {
    /// Format, version, section/syscall/function counts and the entrypoint.
    Summary,
    /// Everything, with the disassembly listing paged.
    #[default]
    Complete,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum AssumeVersion {
    #[default]
    Auto,
    V1,
    V2,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InspectParams {
    /// Absolute path of the program file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// auto (default), elf or raw.
    #[serde(default)]
    pub encoding: Encoding,
    /// summary or complete (default).
    #[serde(default)]
    pub detail: Detail,
    /// Override the sBPF version instead of the e_flags guess (and the version for raw bytecode).
    #[serde(default)]
    pub assume_version: AssumeVersion,
    /// First instruction of the disassembly page.
    #[serde(default)]
    pub offset: usize,
    /// Instructions per disassembly page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DisasmParams {
    /// Absolute path of the program file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// auto (default), elf or raw.
    #[serde(default)]
    pub encoding: Encoding,
    /// Override the sBPF version (and the version for raw bytecode).
    #[serde(default)]
    pub assume_version: AssumeVersion,
    /// Byte offset into the code (the .text section for ELF, the file for raw). Default 0.
    #[serde(default)]
    pub offset: usize,
    /// Bytes to disassemble from `offset` (default: to the end, capped).
    #[serde(default)]
    pub length: Option<usize>,
}

/// Decide the encoding and the sBPF version, parse the ELF (when applicable), and return the
/// code bytes, their base address, the parsed program (ELF only) and the version in force.
struct Prepared {
    encoding: &'static str,
    code: Vec<u8>,
    truncated_text: Option<String>,
    base: u64,
    version: sbpf::SbpfVersion,
    version_source: String,
    program: Option<solana::SolanaProgram>,
}

fn version_for(assume: AssumeVersion, elf_flags: Option<u32>) -> (sbpf::SbpfVersion, String) {
    match assume {
        AssumeVersion::V1 => (sbpf::SbpfVersion::V1, "forced to sbpf_v1 by assume_version".to_string()),
        AssumeVersion::V2 => (sbpf::SbpfVersion::V2, "forced to sbpf_v2 by assume_version".to_string()),
        AssumeVersion::Auto => match elf_flags {
            Some(f) => sbpf::SbpfVersion::from_e_flags(f),
            None => (sbpf::SbpfVersion::V1, "raw bytecode: assuming sbpf_v1 (no ELF e_flags to read)".to_string()),
        },
    }
}

fn prepare(bytes: &[u8], encoding: Encoding, assume: AssumeVersion) -> Result<Prepared, ToolError> {
    let is_elf = bytes.starts_with(b"\x7fELF");
    let use_raw = matches!(encoding, Encoding::Raw) || (matches!(encoding, Encoding::Auto) && !is_elf);
    if use_raw {
        let (version, version_source) = version_for(assume, None);
        return Ok(Prepared { encoding: "raw", code: bytes.to_vec(), truncated_text: None, base: 0, version, version_source, program: None });
    }
    // ELF path.
    let prog = solana::inspect(bytes).map_err(|e| format_err(e, "an ELF (Solana sBPF / eBPF) program"))?;
    if !prog.is_sbpf {
        return Err(ToolError::unsupported(format!(
            "this ELF's machine type is {} ({}), not EM_BPF (247); it is not a Solana sBPF / eBPF program",
            prog.e_machine, prog.machine_name
        ))
        .with_remediation("Use the native-code tools for a normal ELF, or pass encoding=raw to decode the bytes as raw sBPF."));
    }
    let (version, version_source) = version_for(assume, Some(prog.e_flags));
    let (code, truncated_text, base) = match prog.text {
        Some(t) => {
            let start = usize::try_from(t.file_offset).unwrap_or(usize::MAX);
            let len = usize::try_from(t.size).unwrap_or(usize::MAX);
            match start.checked_add(len).and_then(|end| bytes.get(start..end)) {
                Some(slice) => (slice.to_vec(), None, t.addr),
                None => {
                    let prefix = bytes.get(start..).unwrap_or(&[]).to_vec();
                    let read = prefix.len();
                    let note = format!(".text declares {} bytes at {:#x}, but the {}-byte file has {read}", t.size, t.file_offset, bytes.len());
                    (prefix, Some(note), t.addr)
                }
            }
        }
        None => (Vec::new(), None, prog.entry),
    };
    Ok(Prepared { encoding: "elf", code, truncated_text, base, version, version_source, program: Some(prog) })
}

/// Resolve a `call imm` hash to a syscall name: first the program's own relocations/dynsym, then
/// the built-in known-syscall table.
fn resolve_hash(prog: Option<&solana::SolanaProgram>, imm: u32) -> Option<String> {
    if let Some(p) = prog
        && let Some(s) = p.syscalls.iter().find(|s| s.hash == imm)
    {
        return Some(s.name.clone());
    }
    solana::syscall_by_hash(imm).map(str::to_string)
}

/// Build one disassembly line as JSON, resolving call hashes and naming targets.
fn insn_json(n: &sbpf::Insn, prog: Option<&solana::SolanaProgram>) -> Value {
    let mut o = json!({
        "address": format!("{:#x}", n.addr),
        "slot": n.slot,
        "size": n.size,
        "opcode": format!("{:#04x}", n.opcode),
        "mnemonic": n.mnemonic,
        "operands": n.operands,
    });
    if let Value::Object(m) = &mut o {
        match &n.flow {
            sbpf::Flow::Jump { target } | sbpf::Flow::Branch { target } | sbpf::Flow::Call { target } => {
                m.insert("target".into(), json!(format!("{target:#x}")));
            }
            sbpf::Flow::CallHash { imm } => {
                if let Some(name) = resolve_hash(prog, *imm) {
                    m.insert("syscall".into(), json!(name));
                }
                m.insert("call_hash".into(), json!(format!("{imm:#010x}")));
            }
            _ => {}
        }
    }
    o
}

/// Function entry points: the entrypoint and every defined function symbol inside the code.
fn entries_from(prog: Option<&solana::SolanaProgram>, base: u64, code_len: usize) -> Vec<(u64, Option<String>)> {
    let mut out: Vec<(u64, Option<String>)> = Vec::new();
    match prog {
        Some(p) => {
            let end = base.saturating_add(code_len as u64);
            out.push((p.entry, p.entry_symbol.clone().or_else(|| Some("entrypoint".to_string()))));
            for s in &p.symbols {
                if s.defined && s.kind == "function" && s.value >= base && s.value < end {
                    out.push((s.value, Some(s.name.clone())));
                }
            }
        }
        None => out.push((base, Some("entry".to_string()))),
    }
    out
}

fn formats_sbpf_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InspectParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), solana::MAX_INPUT as u64)?;
    ctx.report(None, format!("Reading sBPF program {}", input.name));
    let prep = prepare(&input.bytes, p.encoding, p.assume_version)?;
    ctx.cancel.check()?;

    let insns = sbpf::decode(&prep.code, prep.base, prep.version);
    ctx.cancel.check()?;
    let entries = entries_from(prep.program.as_ref(), prep.base, prep.code.len());
    let analysis = sbpf::analyze(&insns, &entries);

    let prog = prep.program.as_ref();
    let limit = p.limit.clamp(1, 5000);
    // Page the disassembly listing.
    let lines: Vec<Value> = insns.iter().map(|n| insn_json(n, prog)).collect();
    let (listing, cov) = if p.detail == Detail::Complete { page(&lines, p.offset, limit) } else { (Vec::new(), Coverage::complete(1)) };

    // A small pseudo form of the first (entry) function.
    let resolver = |imm: u32| resolve_hash(prog, imm);
    let pseudo = analysis
        .functions
        .iter()
        .find(|f| Some(f.entry) == prog.map(|p| p.entry).or(Some(prep.base)))
        .or_else(|| analysis.functions.first())
        .map(|f| sbpf::pseudo(f, &insns, &resolver));

    // Syscalls actually reached (resolved from the decoded call hashes), merged with the ELF list.
    let mut syscall_names: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    for imm in &analysis.call_hashes {
        if let Some(name) = resolve_hash(prog, *imm) {
            syscall_names.insert(name);
        }
    }
    if let Some(p) = prog {
        for s in &p.syscalls {
            syscall_names.insert(s.name.clone());
        }
    }

    let fn_summaries: Vec<Value> = analysis
        .functions
        .iter()
        .map(|f| json!({"entry": format!("{:#x}", f.entry), "name": f.name, "blocks": f.block_count, "instructions": f.instruction_count}))
        .collect();

    let version_name = prep.version.name();
    let summary = match prog {
        Some(p) => format!(
            "{} sBPF program ({version_name}): entry {:#x}{}, {} sections, {} functions, {} syscalls{}; {} instructions.",
            match p.e_type {
                2 => "executable",
                3 => "shared-object",
                _ => "relocatable",
            },
            p.entry,
            p.entry_symbol.as_deref().map(|s| format!(" ({s})")).unwrap_or_default(),
            p.sections.len(),
            analysis.functions.len(),
            syscall_names.len(),
            if analysis.has_indirect_calls { ", has indirect calls (callx)" } else { "" },
            insns.len()
        ),
        None => format!(
            "Raw sBPF bytecode ({version_name}): {} functions, {} instructions{}.",
            analysis.functions.len(),
            insns.len(),
            if analysis.has_indirect_calls { ", has indirect calls (callx)" } else { "" }
        ),
    };

    let mut lims = vec![
        Limitation::new("static_only", "Nothing was executed; syscall and account behaviour comes from the Solana runtime, which is not part of the file."),
        Limitation::new(
            "sbpf_version",
            format!(
                "{} The call/callx encoding and some arithmetic opcodes differ between sBPF versions; opcodes whose meaning is version-dependent are decoded literally and flagged.",
                prep.version_source
            ),
        ),
        Limitation::new(
            "no_anchor_idl",
            "Instruction/account layouts and human names come from an Anchor IDL, which is a separate sidecar file not embedded here; none was read.",
        ),
    ];
    if analysis.has_indirect_calls {
        lims.push(Limitation::new("indirect_calls", "Some calls go through a register (callx); their targets are not statically known."));
    }
    if prog.is_none() {
        lims.push(Limitation::new(
            "raw_no_sections",
            "Raw mode: no ELF, so no sections, symbols, relocations or entrypoint — the whole input was decoded from offset 0.",
        ));
    }
    for w in prog.map(|p| p.warnings.clone()).unwrap_or_default() {
        lims.push(Limitation::new("parse_warning", w));
    }
    if let Some(note) = &prep.truncated_text {
        lims.push(Limitation::new("text_truncated", note.clone()));
    }

    let result = match p.detail {
        Detail::Summary => json!({
            "encoding": prep.encoding,
            "sbpf_version": version_name,
            "version_note": prep.version_source,
            "format": prog.map(format_block),
            "counts": {
                "sections": prog.map(|p| p.sections.len()).unwrap_or(0),
                "symbols": prog.map(|p| p.symbols.len()).unwrap_or(0),
                "relocations": prog.map(|p| p.relocations.len()).unwrap_or(0),
                "syscalls": syscall_names.len(),
                "functions": analysis.functions.len(),
                "instructions": insns.len(),
            },
            "syscalls": syscall_names.iter().collect::<Vec<_>>(),
            "functions": fn_summaries,
            "has_indirect_calls": analysis.has_indirect_calls,
        }),
        Detail::Complete => json!({
            "encoding": prep.encoding,
            "sbpf_version": version_name,
            "version_note": prep.version_source,
            "format": prog.map(format_block),
            "sections": prog.map(|p| p.sections.clone()),
            "symbols": prog.map(|p| p.symbols.clone()),
            "relocations": prog.map(|p| p.relocations.clone()),
            "syscalls": prog.map(|p| p.syscalls.clone()),
            "syscalls_reached": syscall_names.iter().collect::<Vec<_>>(),
            "functions": analysis.functions,
            "call_targets": analysis.call_targets.iter().map(|a| format!("{a:#x}")).collect::<Vec<_>>(),
            "has_indirect_calls": analysis.has_indirect_calls,
            "pseudo": pseudo,
            "disassembly": {
                "base": format!("{:#x}", prep.base),
                "total": insns.len(),
                "offset": p.offset,
                "count": listing.len(),
                "next_offset": cov.next_offset,
                "instructions": listing,
            },
        }),
    };

    let mut coverage = if p.detail == Detail::Complete { cov } else { Coverage::complete(1) };
    if prep.truncated_text.is_some() {
        coverage.status = CoverageStatus::Partial;
    }
    let mut ev = builder(
        ctx,
        "formats_sbpf_show",
        input.subject.clone(),
        json!({"path": input.path, "encoding": p.encoding, "detail": p.detail, "assume_version": p.assume_version, "offset": p.offset, "limit": limit}),
    )
    .result(result)
    .summary(summary)
    .confidence(if prog.is_some() { Confidence::Observed } else { Confidence::Derived })
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(coverage)
    .location(Location::new("path", input.path.display().to_string()));
    if let Some(prog) = prog {
        ev = ev.location(Location::new("virtual_address", format!("{:#x}", prog.entry)).with_label("entrypoint"));
    }
    Ok(ToolOutput::evidence(ev.build()?))
}

fn format_block(p: &solana::SolanaProgram) -> Value {
    json!({
        "e_machine": p.e_machine,
        "machine": p.machine_name,
        "is_sbpf": p.is_sbpf,
        "e_type": p.e_type,
        "e_flags": format!("{:#x}", p.e_flags),
        "entry": format!("{:#x}", p.entry),
        "entry_symbol": p.entry_symbol,
    })
}

fn formats_sbpf_disassemble(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DisasmParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), solana::MAX_INPUT as u64)?;
    let prep = prepare(&input.bytes, p.encoding, p.assume_version)?;
    ctx.cancel.check()?;

    // The byte window within the code to decode.
    let total = prep.code.len();
    let start = p.offset.min(total);
    let end = match p.length {
        Some(l) => start.saturating_add(l).min(total),
        None => total,
    };
    let window = prep.code.get(start..end).unwrap_or(&[]);
    let base = prep.base.wrapping_add(start as u64);
    let insns = sbpf::decode(window, base, prep.version);
    ctx.cancel.check()?;

    let prog = prep.program.as_ref();
    let lines: Vec<Value> = insns.iter().map(|n| insn_json(n, prog)).collect();
    let text_dump: Vec<String> = insns.iter().map(|n| n.text()).collect();

    let mut lims = vec![Limitation::new(
        "static_only",
        "Decoding only; nothing was executed. Decoding starts exactly at the given offset, which must land on an instruction boundary.",
    )];
    for w in prog.map(|p| p.warnings.clone()).unwrap_or_default() {
        lims.push(Limitation::new("parse_warning", w));
    }
    if let Some(note) = &prep.truncated_text {
        lims.push(Limitation::new("text_truncated", note.clone()));
    }
    let coverage = if prep.truncated_text.is_some() { static_input::partial(insns.len() as u64) } else { Coverage::complete(insns.len() as u64) };
    let summary = format!("Disassembled {} instruction(s) of {} sBPF code from byte {:#x} (base {:#x}).", insns.len(), prep.version.name(), start, prep.base);
    let ev = builder(
        ctx,
        "formats_sbpf_disassemble",
        input.subject.clone(),
        json!({"path": input.path, "encoding": p.encoding, "assume_version": p.assume_version, "offset": p.offset, "length": p.length}),
    )
    .result(json!({
        "encoding": prep.encoding,
        "sbpf_version": prep.version.name(),
        "base": format!("{:#x}", prep.base),
        "window": {"offset": start, "end": end, "code_size": total},
        "count": insns.len(),
        "instructions": lines,
        "listing": text_dump,
    }))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(coverage)
    .location(Location::new("path", input.path.display().to_string()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err, engine_with};
    use crate::Engine;
    use craft_anything_testkit::sbpf as fx;
    use craft_anything_testkit::temp_file;
    use serde_json::json;

    #[test]
    fn inspects_the_fixture() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("prog.so", &fx::program());
        let v = call(&e, "formats_sbpf_show", json!({"path": p.to_string_lossy()}));
        let r = &v["result"];
        assert_eq!(r["encoding"], "elf");
        assert_eq!(r["sbpf_version"], "sbpf_v1");
        assert_eq!(r["format"]["is_sbpf"], true);
        assert_eq!(r["format"]["entry_symbol"], "entrypoint");
        // One function (the entrypoint), ending in exit.
        let funcs = r["functions"].as_array().unwrap();
        assert!(!funcs.is_empty());
        // The sol_log_ syscall is reached and named.
        let reached: Vec<&str> = r["syscalls_reached"].as_array().unwrap().iter().map(|s| s.as_str().unwrap()).collect();
        assert!(reached.contains(&"sol_log_"), "reached: {reached:?}");
        // The call instruction carries the resolved syscall name.
        let dis = r["disassembly"]["instructions"].as_array().unwrap();
        let callline = dis.iter().find(|i| i["mnemonic"] == "call").unwrap();
        assert_eq!(callline["syscall"], "sol_log_");
        assert_eq!(dis.last().unwrap()["mnemonic"], "exit");
        assert!(r["pseudo"].as_str().unwrap().contains("sol_log_"));
        assert!(v["summary"].as_str().unwrap().contains("sBPF program"));
    }

    #[test]
    fn summary_detail_and_paging() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("prog.so", &fx::program());
        let s = call(&e, "formats_sbpf_show", json!({"path": p.to_string_lossy(), "detail": "summary"}));
        assert_eq!(s["result"]["counts"]["instructions"], 3);
        assert!(s["result"]["sections"].is_null());
        let pg = call(&e, "formats_sbpf_show", json!({"path": p.to_string_lossy(), "offset": 1, "limit": 1}));
        let dis = &pg["result"]["disassembly"];
        assert_eq!(dis["count"], 1);
        assert_eq!(dis["offset"], 1);
    }

    #[test]
    fn raw_bytecode_decodes() {
        let e = Engine::new(crate::testing::session());
        let code = fx::text_bytes();
        let p = temp_file("code.bin", &code);
        let v = call(&e, "formats_sbpf_show", json!({"path": p.to_string_lossy(), "encoding": "raw"}));
        let r = &v["result"];
        assert_eq!(r["encoding"], "raw");
        assert!(r["format"].is_null());
        assert_eq!(r["disassembly"]["total"], 3);
        // Even without an ELF, the known-syscall table resolves the hash.
        let reached: Vec<&str> = r["syscalls_reached"].as_array().unwrap().iter().map(|s| s.as_str().unwrap()).collect();
        assert!(reached.contains(&"sol_log_"));
    }

    #[test]
    fn disassemble_tool_window() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("prog.so", &fx::program());
        let v = call(&e, "formats_sbpf_disassemble", json!({"path": p.to_string_lossy(), "offset": 16, "length": 8}));
        let r = &v["result"];
        assert_eq!(r["count"], 1);
        assert_eq!(r["instructions"][0]["mnemonic"], "exit");
    }

    #[test]
    fn non_bpf_elf_is_a_clean_error() {
        let e = engine_with("plain", &craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true).0);
        let err = call_err(&e, "formats_sbpf_show", json!({}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::NotSupported);
        assert!(err.message.contains("not") && err.message.contains("EM_BPF"));
        // But raw mode will still decode the bytes without complaint.
        let _ = call(&e, "formats_sbpf_show", json!({"encoding": "raw"}));
    }

    #[test]
    fn truncated_text_section_reports_partial_coverage_and_limitation() {
        fn build_elf(declared_size: u64, insns: usize) -> Vec<u8> {
            let mut b = vec![0u8; 280 + insns * 8];
            b[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
            for (o, v) in [(16, 3u16), (18, 247), (52, 64), (58, 64), (60, 3), (62, 2)] {
                b[o..o + 2].copy_from_slice(&v.to_le_bytes());
            }
            for (o, v) in [(20, 1u32), (128, 1), (132, 1), (192, 7), (196, 3)] {
                b[o..o + 4].copy_from_slice(&v.to_le_bytes());
            }
            for (o, v) in [(24, 0x1000u64), (40, 64), (136, 6), (144, 0x1000), (152, 280), (160, declared_size), (176, 8)] {
                b[o..o + 8].copy_from_slice(&v.to_le_bytes());
            }
            for (o, v) in [(216, 256u64), (224, 17), (240, 1)] {
                b[o..o + 8].copy_from_slice(&v.to_le_bytes());
            }
            b[256..273].copy_from_slice(b"\0.text\0.shstrtab\0");
            for i in 0..insns {
                b[280 + i * 8] = 0x95;
            }
            b
        }

        let e = Engine::new(crate::testing::session());
        let readable = temp_file("readable.so", &build_elf(8, 1));
        let truncated = temp_file("truncated.so", &build_elf(24, 2));
        let empty = temp_file("empty.so", &build_elf(0, 0));

        let show_ok = call(&e, "formats_sbpf_show", json!({"path": readable.to_string_lossy()}));
        assert_eq!(show_ok["result"]["disassembly"]["total"], 1);
        assert_eq!(show_ok["coverage"]["status"], "complete");

        let show_empty = call(&e, "formats_sbpf_show", json!({"path": empty.to_string_lossy()}));
        assert_eq!(show_empty["result"]["disassembly"]["total"], 0);
        assert_eq!(show_empty["coverage"]["status"], "complete");
        assert_eq!(show_empty["limitations"].as_array().unwrap().len(), 3);

        let show_trunc = call(&e, "formats_sbpf_show", json!({"path": truncated.to_string_lossy(), "limit": 1}));
        assert_eq!(show_trunc["result"]["disassembly"]["total"], 2);
        assert_eq!(show_trunc["coverage"]["status"], "partial");
        assert_eq!(show_trunc["coverage"]["next_offset"], 1);
        assert!(show_trunc["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "text_truncated"));

        let dis_trunc = call(&e, "formats_sbpf_disassemble", json!({"path": truncated.to_string_lossy()}));
        assert_eq!(dis_trunc["result"]["count"], 2);
        assert_eq!(dis_trunc["coverage"]["status"], "partial");
        assert!(dis_trunc["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "text_truncated"));
    }
}
