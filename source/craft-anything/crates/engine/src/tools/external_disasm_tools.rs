//! Thin, read-only wrappers over optional external disassemblers and decompilers: `objdump` (GNU
//! binutils or LLVM) for one fixed operation at a time, `rizin` for one allow-listed read-only
//! command, and ILSpy's command line (`ilspycmd`) for .NET assemblies. All run through the
//! process runner (stdin closed, deadline, capped output); their raw text output is the
//! result, paged by lines. The built-in engine never needs any of them.

use super::native_common::{params_json, spec};
use super::static_input::{self, builder};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Subject, ToolError};
use craft_anything_platform::{Output, Process};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "native_objdump_run",
            "objdump output",
            "Run the installed objdump (GNU binutils or llvm-objdump) for one operation on a file (absolute path or the active target): file_headers, private_headers, section_headers, symbols, dynamic_symbols, relocations, dwarf (GNU only; debuginfod disabled), disassemble or disassemble_all (optionally between start_address and stop_address), or architectures (no file needed). Returns the raw text paged by lines, with the exit status and stderr. Optional engine: the built-in disassembler needs nothing installed.",
            "See what the objdump tool says about a program.",
            Toolset::Native,
            Effects::NATIVE_EVIDENCE,
            Requires::Engine("objdump"),
            schema_of::<ObjdumpParams>,
            native_objdump_run,
        ),
        spec(
            "native_rizin_command_run",
            "Rizin command",
            "Run one read-only Rizin command against a file (absolute path or the active target) with user settings and scripts disabled (`rizin -N -q -c <command> <file>`; the file is opened read-only). Commands are checked against an allow-list of read-only families: information (i…), printing and disassembly (p…, x…), analysis (a…), search (/…), seek (s…), flags (f…), comments (C…), types (t…) and help (?…). Shell escapes, writes, file opening, debugging, scripts, configuration changes, pipes, redirects and command chaining are refused. Returns the raw text paged by lines. Optional engine.",
            "Ask the Rizin reverse-engineering tool a read-only question about a program.",
            Toolset::Native,
            Effects::NATIVE_EVIDENCE,
            Requires::Engine("rizin"),
            schema_of::<RizinParams>,
            native_rizin_command_run,
        ),
        spec(
            "managed_ilspy_decompile",
            "ILSpy decompile",
            "Decompile a .NET assembly (absolute path or the active target) with the installed ILSpy command line (ilspycmd): operation decompile gives C# for the whole assembly, or for one type with type_name (`Namespace.Type`, nested types as `Outer+Inner`); il gives the whole assembly's IL; list_types lists its classes, interfaces, structs, delegates and enums. Its update check is turned off, so it never goes online. Returns the raw text paged by lines. Optional engine: the built-in .NET tools need nothing installed.",
            "Turn a .NET program back into readable C# with ILSpy.",
            Toolset::Managed,
            Effects::NATIVE_EVIDENCE,
            Requires::Engine("ilspy"),
            schema_of::<IlspyParams>,
            managed_ilspy_decompile,
        ),
    ]
}

fn d_limit() -> usize {
    2000
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObjdumpOperation {
    FileHeaders,
    PrivateHeaders,
    SectionHeaders,
    Symbols,
    DynamicSymbols,
    Relocations,
    Dwarf,
    Disassemble,
    DisassembleAll,
    /// The targets and architectures this objdump supports; no file needed.
    Architectures,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObjdumpParams {
    /// What to print.
    pub operation: ObjdumpOperation,
    /// Absolute path of the file; the active target when omitted (not used for architectures).
    #[serde(default)]
    pub path: Option<String>,
    /// For disassembly: first address (0x-hex).
    #[serde(default)]
    pub start_address: Option<String>,
    /// For disassembly: address to stop before (0x-hex).
    #[serde(default)]
    pub stop_address: Option<String>,
    /// First output line of the page.
    #[serde(default)]
    pub offset: usize,
    /// Lines per page (1–20000, default 2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RizinParams {
    /// One read-only Rizin command, e.g. "iI", "iS", "afl", "pdf @ main", "izz~http".
    pub command: String,
    /// Run `aa` (basic analysis) first, for commands that need functions.
    #[serde(default)]
    pub analyze: bool,
    /// Absolute path of the file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// First output line of the page.
    #[serde(default)]
    pub offset: usize,
    /// Lines per page (1–20000, default 2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum IlspyOperation {
    /// C# source.
    #[default]
    Decompile,
    /// The IL, for the whole assembly.
    Il,
    /// Every class, interface, struct, delegate and enum, one per line.
    ListTypes,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct IlspyParams {
    /// What to print (default decompile).
    #[serde(default)]
    pub operation: IlspyOperation,
    /// For decompile: one fully qualified type (`Namespace.Type`, nested as `Outer+Inner`).
    #[serde(default)]
    pub type_name: Option<String>,
    /// Absolute path of the assembly; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// First output line of the page.
    #[serde(default)]
    pub offset: usize,
    /// Lines per page (1–20000, default 2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

/// The file to hand to the external tool, with its evidence subject.
pub(super) fn input_file(ctx: &Ctx<'_>, path: Option<&str>) -> Result<(PathBuf, Subject), ToolError> {
    let i = static_input::load(ctx, path, static_input::DEFAULT_MAX_BYTES)?;
    Ok((i.path, i.subject))
}

pub(super) fn locate(ctx: &Ctx<'_>, id: &str) -> Result<PathBuf, ToolError> {
    let s = &ctx.session.settings;
    craft_anything_engines::locate(id, &s.engines.tools, &s.engine_store_dir()).ok_or_else(|| {
        ToolError::unavailable(format!("{} is not installed.", craft_anything_engines::display_name(id)))
            .with_remediation(format!("Install {} and set its path in Settings → Engines.", craft_anything_engines::display_name(id)))
    })
}

/// How to run a located engine: a `.jar` (a single-file install) with the configured Java
/// (`java -jar <jar>`), anything else as itself. Returns the program and the arguments before
/// the engine's own.
pub(crate) fn program_for(ctx: &Ctx<'_>, located: &Path) -> Result<(PathBuf, Vec<String>), ToolError> {
    if located.extension().is_some_and(|e| e.eq_ignore_ascii_case("jar")) {
        Ok((locate(ctx, "java")?, vec!["-jar".to_string(), located.display().to_string()]))
    } else {
        Ok((located.to_path_buf(), Vec::new()))
    }
}

pub(super) fn run(ctx: &Ctx<'_>, exe: &Path, args: &[String], label: &str) -> Result<Output, ToolError> {
    let cancel = ctx.cancel.clone();
    Process::new(exe)
        .args(args)
        .env("DEBUGINFOD_URLS", "")
        .timeout(Duration::from_secs(300))
        .idle_timeout(Duration::from_secs(120))
        .stdout_cap(16 << 20)
        .stderr_cap(1 << 20)
        .cancel_when(move || cancel.is_cancelled())
        .label(label)
        .run()
}

/// Evidence for raw tool output, paged by lines.
#[allow(clippy::too_many_arguments)]
fn text_evidence(
    ctx: &Ctx<'_>,
    op: &str,
    subject: Subject,
    params: Value,
    exe: &Path,
    args: &[String],
    out: &Output,
    offset: usize,
    limit: usize,
    headline: String,
) -> Result<ToolOutput, ToolError> {
    let text = out.stdout_text();
    let limit = limit.clamp(1, 20_000);
    let total = text.lines().count();
    let page: Vec<&str> = text.lines().skip(offset).take(limit).collect();
    let stderr = out.stderr_text();
    let mut lims = vec![Limitation::new(
        "raw_tool_output",
        "This is the external tool's own text; its format can change between versions and is not checked by Craft Anything.",
    )];
    if out.stdout_truncated {
        lims.push(Limitation::new(
            "output_capped",
            "The tool printed more than 16 MiB; the rest was cut off. Narrow the request (for example an address range).",
        ));
    }
    if String::from_utf8(out.stdout.clone()).is_err() {
        lims.push(Limitation::new("invalid_utf8", "Some output bytes were not valid UTF-8 and are shown as replacement characters."));
    }
    if !out.success {
        lims.push(Limitation::new("nonzero_exit", format!("The tool exited with {:?}; see stderr.", out.code)));
    }
    let b = builder(ctx, op, subject, params)
        .result(json!({
            "tool": exe,
            "arguments": args,
            "exit_code": out.code,
            "success": out.success,
            "duration_ms": out.duration.as_millis() as u64,
            "total_lines": total,
            "offset": offset,
            "limit": limit,
            "output": page.join("\n"),
            "stderr": stderr.get(..stderr.floor_char_boundary(64 << 10)).unwrap_or(""),
        }))
        .summary(format!("{headline}: {total} lines of output{}.", if out.success { String::new() } else { format!(", exit code {:?}", out.code) }))
        .confidence(Confidence::Observed)
        .authority(Authority::OutsideService)
        .limitations(lims)
        .coverage(Coverage::page(page.len() as u64, total as u64, offset as u64));
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// objdump

fn objdump_args(op: ObjdumpOperation, llvm: bool, start: Option<u64>, stop: Option<u64>) -> Result<Vec<String>, ToolError> {
    let flag = match op {
        ObjdumpOperation::FileHeaders => "-f",
        ObjdumpOperation::PrivateHeaders => "-p",
        ObjdumpOperation::SectionHeaders => "-h",
        ObjdumpOperation::Symbols => "-t",
        ObjdumpOperation::DynamicSymbols => "-T",
        ObjdumpOperation::Relocations => "-r",
        ObjdumpOperation::Disassemble => "-d",
        ObjdumpOperation::DisassembleAll => "-D",
        ObjdumpOperation::Dwarf if llvm => {
            return Err(ToolError::unsupported("llvm-objdump does not print DWARF debug information")
                .with_remediation("Use llvm-dwarfdump, or install GNU binutils objdump."));
        }
        ObjdumpOperation::Dwarf => "--dwarf=info",
        ObjdumpOperation::Architectures => return Ok(vec![if llvm { "--version" } else { "-i" }.to_string()]),
    };
    let mut args = vec![flag.to_string()];
    if matches!(op, ObjdumpOperation::Disassemble | ObjdumpOperation::DisassembleAll) {
        args.extend(start.map(|a| format!("--start-address={a:#x}")));
        args.extend(stop.map(|a| format!("--stop-address={a:#x}")));
    } else if start.is_some() || stop.is_some() {
        return Err(ToolError::invalid("start_address and stop_address only apply to disassembly"));
    }
    Ok(args)
}

fn native_objdump_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ObjdumpParams = parse_params(params)?;
    let exe = locate(ctx, "objdump")?;
    let llvm = exe.file_name().is_some_and(|n| n.to_string_lossy().to_ascii_lowercase().contains("llvm"));
    let start = p.start_address.as_deref().map(super::parse_address).transpose()?;
    let stop = p.stop_address.as_deref().map(super::parse_address).transpose()?;
    let mut args = objdump_args(p.operation, llvm, start, stop)?;
    let subject = if p.operation == ObjdumpOperation::Architectures {
        Subject { kind: "engine".into(), sha256: None, name: Some("objdump".into()) }
    } else {
        let (file, subject) = input_file(ctx, p.path.as_deref())?;
        args.push(file.display().to_string());
        subject
    };
    ctx.report(None, format!("Running objdump {}", args.first().map(String::as_str).unwrap_or("")));
    let out = run(ctx, &exe, &args, "objdump")?;
    ctx.cancel.check()?;
    if !out.success && out.stdout.is_empty() {
        return Err(craft_anything_platform::process::nonzero_error("objdump", &out));
    }
    let headline = format!("objdump {}", serde_json::to_value(p.operation).ok().and_then(|v| v.as_str().map(str::to_string)).unwrap_or_default());
    text_evidence(ctx, "native_objdump_run", subject, params_json(&p), &exe, &args, &out, p.offset, p.limit, headline)
}

// ---------------------------------------------------------------------------------------------
// rizin

/// Command families that only read (first letter of the command).
const RIZIN_ALLOWED: &[char] = &['i', 'p', 'x', 'a', '/', 's', 'f', 'C', 't', '?'];
/// Read-only families' members that write files, read other files or wait for input.
const RIZIN_DENIED_PREFIXES: &[&str] = &["iO", "agw", "to", "?i", "aec", "aes", "aei", "aef"];
/// Characters that chain, pipe, redirect, escape to a shell or run scripts.
const RIZIN_DENIED_CHARS: &[char] = &[';', '|', '>', '<', '!', '`', '#', '\n', '\r', '\0', '(', ')', '$', '"', '\''];

/// Accept one read-only command, or say why not.
pub(super) fn check_rizin_command(cmd: &str) -> Result<&str, ToolError> {
    let c = cmd.trim();
    let refuse = |why: &str| {
        ToolError::invalid(format!("Rizin command {c:?} was refused: {why}"))
            .with_remediation("Use one read-only command such as iI, iS, ii, iz, afl, pdf @ main, px 64 @ 0x1000 or /x 9090.")
    };
    if c.is_empty() || c.len() > 512 {
        return Err(refuse("it must be 1–512 characters"));
    }
    if let Some(bad) = c.chars().find(|ch| RIZIN_DENIED_CHARS.contains(ch)) {
        return Err(refuse(&format!("the character {bad:?} could chain, redirect or run something else")));
    }
    let first = c.chars().next().unwrap_or(' ');
    if !RIZIN_ALLOWED.contains(&first) {
        return Err(refuse("only information, printing, analysis, search, seek, flag, comment, type and help commands are allowed"));
    }
    let head = c.split_whitespace().next().unwrap_or("");
    if let Some(d) = RIZIN_DENIED_PREFIXES.iter().find(|d| head.starts_with(**d)) {
        return Err(refuse(&format!("{d}… can write files, read other files, emulate code or wait for input")));
    }
    Ok(c)
}

fn rizin_args(cmd: &str, analyze: bool, file: &Path) -> Vec<String> {
    let mut args: Vec<String> = ["-N", "-q", "-e", "scr.color=0", "-e", "scr.interactive=false", "-e", "scr.prompt=false"].map(String::from).to_vec();
    if analyze {
        args.extend(["-c".to_string(), "aa".to_string()]);
    }
    args.extend(["-c".to_string(), cmd.to_string(), file.display().to_string()]);
    args
}

fn native_rizin_command_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RizinParams = parse_params(params)?;
    let cmd = check_rizin_command(&p.command)?.to_string();
    let exe = locate(ctx, "rizin")?;
    let (file, subject) = input_file(ctx, p.path.as_deref())?;
    let args = rizin_args(&cmd, p.analyze, &file);
    ctx.report(None, format!("Running rizin {cmd}"));
    let out = run(ctx, &exe, &args, "rizin")?;
    ctx.cancel.check()?;
    if !out.success && out.stdout.is_empty() {
        return Err(craft_anything_platform::process::nonzero_error("rizin", &out));
    }
    text_evidence(ctx, "native_rizin_command_run", subject, params_json(&p), &exe, &args, &out, p.offset, p.limit, format!("rizin `{cmd}`"))
}

// ---------------------------------------------------------------------------------------------
// ILSpy

fn ilspy_args(op: IlspyOperation, type_name: Option<&str>, file: &Path) -> Result<Vec<String>, ToolError> {
    // Never let it go online to look for updates.
    let mut args = vec!["--disable-updatecheck".to_string()];
    match (op, type_name.map(str::trim)) {
        (IlspyOperation::Decompile, None) => {}
        (IlspyOperation::Decompile, Some(t)) => {
            if t.is_empty() || t.starts_with('-') || t.chars().any(char::is_control) {
                return Err(
                    ToolError::invalid(format!("{t:?} is not a type name")).with_remediation("Pass a full name such as MyApp.Program; list_types shows them.")
                );
            }
            args.extend(["-t".to_string(), t.to_string()]);
        }
        (IlspyOperation::Il, None) => args.push("-il".to_string()),
        (IlspyOperation::ListTypes, None) => args.extend(["-l".to_string(), "cisde".to_string()]),
        // ilspycmd prints the whole assembly's IL even when given a type.
        (_, Some(_)) => return Err(ToolError::invalid("type_name only applies to decompile")),
    }
    args.push(file.display().to_string());
    Ok(args)
}

fn managed_ilspy_decompile(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: IlspyParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), static_input::DEFAULT_MAX_BYTES)?;
    if !craft_anything_formats::pe_is_managed(&input.bytes) {
        return Err(ToolError::unsupported(format!("{} is not a .NET assembly", input.name))
            .with_remediation("ILSpy reads .NET programs and libraries (.exe or .dll with .NET metadata)."));
    }
    let args = ilspy_args(p.operation, p.type_name.as_deref(), &input.path)?;
    let exe = locate(ctx, "ilspy")?;
    ctx.report(None, format!("Decompiling {} with ILSpy", input.name));
    let out = run(ctx, &exe, &args, "ilspycmd")?;
    ctx.cancel.check()?;
    if !out.success && out.stdout.is_empty() {
        let err = craft_anything_platform::process::nonzero_error("ilspycmd", &out);
        // ilspycmd prints `Exception: message` first, then the stack trace.
        return Err(match out.stderr_text().lines().next().and_then(|l| l.split_once(": ")) {
            Some((_, why)) => ToolError { message: format!("ILSpy couldn't do it: {}", why.trim()), ..err },
            None => err,
        });
    }
    let what = match (p.operation, p.type_name.as_deref()) {
        (IlspyOperation::Decompile, Some(t)) => format!("ILSpy C# of {t}"),
        (IlspyOperation::Decompile, None) => format!("ILSpy C# of {}", input.name),
        (IlspyOperation::Il, _) => format!("ILSpy IL of {}", input.name),
        (IlspyOperation::ListTypes, _) => format!("ILSpy types of {}", input.name),
    };
    text_evidence(ctx, "managed_ilspy_decompile", input.subject, params_json(&p), &exe, &args, &out, p.offset, p.limit, what)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ilspy_flags() {
        let f = Path::new("/x/App.dll");
        assert_eq!(ilspy_args(IlspyOperation::Decompile, None, f).unwrap(), vec!["--disable-updatecheck", "/x/App.dll"]);
        assert_eq!(ilspy_args(IlspyOperation::Decompile, Some(" App.Program "), f).unwrap(), vec!["--disable-updatecheck", "-t", "App.Program", "/x/App.dll"]);
        assert_eq!(ilspy_args(IlspyOperation::Il, None, f).unwrap(), vec!["--disable-updatecheck", "-il", "/x/App.dll"]);
        assert_eq!(ilspy_args(IlspyOperation::ListTypes, None, f).unwrap(), vec!["--disable-updatecheck", "-l", "cisde", "/x/App.dll"]);
        for bad in ["", "-o", "--project", "A\nB"] {
            assert!(ilspy_args(IlspyOperation::Decompile, Some(bad), f).is_err(), "{bad:?}");
        }
        assert!(ilspy_args(IlspyOperation::Il, Some("App.Program"), f).is_err(), "IL is whole-assembly only");
    }

    #[test]
    fn ilspy_refuses_native_files_before_running() {
        let p = craft_anything_testkit::temp_file("prog.bin", &craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true).0);
        // A stand-in for ilspycmd, so the test doesn't depend on what this machine has installed;
        // the file is refused before any program would run.
        let mut s = crate::testing::session();
        s.settings.engines.tools.ilspy = Some(p.clone());
        let e = crate::Engine::new(s);
        let err = e.call("managed_ilspy_decompile", serde_json::json!({"path": p}), crate::CallOptions::new(crate::Caller::Mcp)).unwrap_err();
        assert!(err.message.contains("not a .NET assembly"), "{err:?}");
    }

    #[test]
    fn rizin_allow_list() {
        for ok in ["iI", "iS", "afl", "pdf @ main", "px 64 @ 0x1000", "/x 9090", "izz~http", "?v 1+2", "s main", "axt @ sym.imp.puts", "aaa"] {
            assert!(check_rizin_command(ok).is_ok(), "{ok}");
        }
        for bad in [
            "w hello",
            "wx 90",
            "!ls",
            "o /etc/passwd",
            "iI; w x",
            "pd 1 | sh",
            "px > out.txt",
            "#!pipe",
            ". script.rz",
            "e cmd.load=!x",
            "iO r 0",
            "agw out.png",
            "to /tmp/h.h",
            "db main",
            "",
            "?i name",
            "pd `ls`",
            "(m; w x)",
            "$alias",
            "iI\nw x",
        ] {
            assert!(check_rizin_command(bad).is_err(), "{bad:?}");
        }
        let a = rizin_args("iI", true, Path::new("/x/prog"));
        assert_eq!(a.first().map(String::as_str), Some("-N"));
        assert_eq!(a.iter().filter(|x| *x == "-c").count(), 2);
        assert_eq!(a.last().map(String::as_str), Some("/x/prog"));
    }

    #[test]
    fn objdump_flags() {
        assert_eq!(
            objdump_args(ObjdumpOperation::Disassemble, false, Some(0x10), Some(0x20)).unwrap(),
            vec!["-d", "--start-address=0x10", "--stop-address=0x20"]
        );
        assert_eq!(objdump_args(ObjdumpOperation::Architectures, false, None, None).unwrap(), vec!["-i"]);
        assert_eq!(objdump_args(ObjdumpOperation::Architectures, true, None, None).unwrap(), vec!["--version"]);
        assert!(objdump_args(ObjdumpOperation::Dwarf, true, None, None).is_err());
        assert!(objdump_args(ObjdumpOperation::Symbols, false, Some(1), None).is_err());
    }

    #[test]
    fn missing_engine_is_a_clear_error_or_a_run() {
        // Whether rizin is installed varies by machine; either way the call must not panic.
        let e = crate::Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file("prog.bin", &craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true).0);
        match e.call("native_rizin_command_run", serde_json::json!({"path": p, "command": "iI"}), crate::CallOptions::new(crate::Caller::Mcp)) {
            Ok(_) => {}
            Err(err) => assert!(err.remediation.is_some(), "{err:?}"),
        }
        let err = e.call("native_rizin_command_run", serde_json::json!({"path": p, "command": "w x"}), crate::CallOptions::new(crate::Caller::Mcp));
        assert!(err.is_err());
    }

    #[test]
    fn stderr_cut_inside_a_multibyte_character_keeps_the_text_before_it() {
        let mut session = crate::testing::session();
        let ctx =
            Ctx { tool: "native_objdump_run", session: &mut session, cancel: crate::CancelToken::default(), progress: &|_| {}, caller: crate::Caller::Cli };
        // 64 KiB falls inside the arrow in the first case and right after it in the second.
        for (ascii, kept) in [(65535, 65535), (65533, 65536)] {
            let mut stderr = vec![b'a'; ascii];
            stderr.extend_from_slice("\u{2192}tail".as_bytes());
            let out = Output { code: Some(1), success: false, stderr, ..Default::default() };
            let subject = Subject { kind: "engine".into(), sha256: None, name: Some("objdump".into()) };
            let ToolOutput::Evidence(ev) =
                text_evidence(&ctx, "native_objdump_run", subject, json!({}), Path::new("objdump"), &[], &out, 0, 10, "objdump".into()).unwrap()
            else {
                panic!("expected evidence");
            };
            let s = ev.result["stderr"].as_str().unwrap();
            assert_eq!(s.len(), kept);
            assert!(s.starts_with("aaa"));
        }
    }
}
