//! Shared plumbing for the built-in format tools (Apple, managed, Android, formats, firmware):
//! reading an input file (an explicit absolute path or the active target) with a size cap, starting
//! an evidence record about it, and turning parser errors into plain-English tool errors.

use crate::target::{Target, TargetKind};
use crate::tool::Ctx;
use craft_anything_evidence::{Coverage, CoverageStatus, Environment, ErrorCode, EvidenceBuilder, Subject, ToolError};
use craft_anything_formats::FormatError;
use serde_json::Value;
use std::path::PathBuf;
use std::sync::Arc;

/// Default cap for inputs read into memory (256 MiB).
pub const DEFAULT_MAX_BYTES: u64 = 256 << 20;

/// A file read for a format tool.
#[derive(Debug, Clone)]
pub struct Input {
    pub bytes: Arc<[u8]>,
    pub subject: Subject,
    pub path: PathBuf,
    pub name: String,
    pub kind: TargetKind,
}

/// Read `path` (absolute, a regular file, at most `max` bytes) or, when omitted, the active target.
pub fn load(ctx: &Ctx<'_>, path: Option<&str>, max: u64) -> Result<Input, ToolError> {
    match path {
        Some(p) => load_path(p, max),
        None => {
            let t = &ctx.session.active().map_err(|e| e.with_remediation("Open a target first, or pass path (an absolute file path)."))?.target;
            if t.kind == TargetKind::Directory {
                return Err(ToolError::invalid(format!("{} is a folder; pass path to a file inside it", t.path.display())));
            }
            if t.bytes.len() as u64 > max {
                return Err(ToolError::new(ErrorCode::OverLimit, format!("the target is {} bytes; the limit is {max}", t.bytes.len())));
            }
            Ok(Input { bytes: t.bytes.clone(), subject: t.subject(), path: t.path.clone(), name: t.name.clone(), kind: t.kind })
        }
    }
}

/// Read one absolute file path with a size cap.
pub fn load_path(p: &str, max: u64) -> Result<Input, ToolError> {
    let pb = PathBuf::from(p);
    if !pb.is_absolute() {
        return Err(ToolError::invalid(format!("{p:?} is not an absolute path")).with_remediation("Pass the full path, for example /home/me/app.apk."));
    }
    let meta = std::fs::metadata(&pb).map_err(|e| ToolError::io(p, e))?;
    if meta.is_dir() {
        return Err(ToolError::invalid(format!("{p} is a folder; pass a file")));
    }
    if meta.len() > max {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{p} is {} bytes; the limit is {max}", meta.len()))
            .with_remediation("Raise the size limit parameter if the tool has one, or pass a smaller file."));
    }
    let bytes = std::fs::read(&pb).map_err(|e| ToolError::io(p, e))?;
    let name = pb.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| p.to_string());
    let t = Target::from_bytes(pb.clone(), name.clone(), bytes);
    Ok(Input { subject: t.subject(), bytes: t.bytes.clone(), path: pb, name, kind: t.kind })
}

/// The start of a file, for formats whose header says all a tool needs. Big files are never read
/// whole.
#[derive(Debug, Clone)]
pub struct PrefixInput {
    pub bytes: Vec<u8>,
    /// The file's real size.
    pub file_size: u64,
    /// `bytes` is the whole file.
    pub whole: bool,
    /// Carries the file's SHA-256 only when `whole`: a hash of a part would pass for the file's.
    pub subject: Subject,
    pub path: PathBuf,
    pub name: String,
}

/// Read at most `max` bytes from the start of `path` (absolute, a regular file) or, when omitted,
/// of the active target.
pub fn load_prefix(ctx: &Ctx<'_>, path: Option<&str>, max: u64) -> Result<PrefixInput, ToolError> {
    use std::io::Read;
    let Some(p) = path else {
        let t = &ctx.session.active().map_err(|e| e.with_remediation("Open a target first, or pass path (an absolute file path)."))?.target;
        if t.kind == TargetKind::Directory {
            return Err(ToolError::invalid(format!("{} is a folder; pass path to a file inside it", t.path.display())));
        }
        let keep = usize::try_from(max).unwrap_or(usize::MAX).min(t.bytes.len());
        let bytes = t.bytes.get(..keep).unwrap_or(&[]).to_vec();
        let whole = keep == t.bytes.len();
        let mut subject = t.subject();
        if !whole {
            subject.sha256 = None;
        }
        return Ok(PrefixInput { bytes, file_size: t.bytes.len() as u64, whole, subject, path: t.path.clone(), name: t.name.clone() });
    };
    let pb = PathBuf::from(p);
    if !pb.is_absolute() {
        return Err(ToolError::invalid(format!("{p:?} is not an absolute path")).with_remediation("Pass the full path, for example /home/me/model.gguf."));
    }
    let meta = std::fs::metadata(&pb).map_err(|e| ToolError::io(p, e))?;
    if meta.is_dir() {
        return Err(ToolError::invalid(format!("{p} is a folder; pass a file")));
    }
    let file = std::fs::File::open(&pb).map_err(|e| ToolError::io(p, e))?;
    let mut bytes = Vec::with_capacity(usize::try_from(meta.len().min(max)).unwrap_or(0));
    file.take(max).read_to_end(&mut bytes).map_err(|e| ToolError::io(p, e))?;
    let whole = bytes.len() as u64 >= meta.len();
    let name = pb.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| p.to_string());
    let sha256 = whole.then(|| craft_anything_evidence::sha256_hex(&bytes));
    let subject = Subject { kind: "file".into(), sha256, name: Some(name.clone()) };
    Ok(PrefixInput { bytes, file_size: meta.len(), whole, subject, path: pb, name })
}

/// Start an evidence record about `subject` from a built-in engine.
pub fn builder(ctx: &Ctx<'_>, op: &str, subject: Subject, params: Value) -> EvidenceBuilder {
    EvidenceBuilder::new(op, subject, Environment::builtin(ctx.session.clean_room())).params(params)
}

/// A parser error as a tool error, naming what we expected the file to be.
pub fn format_err(e: FormatError, expected: &str) -> ToolError {
    let msg = format!("Couldn't read this as {expected}: {e}");
    match e {
        FormatError::TooLarge(_) => ToolError::new(ErrorCode::OverLimit, msg),
        FormatError::Unsupported(_) => ToolError::unsupported(msg).with_remediation("Run triage to see which tools fit this file."),
        _ => ToolError::new(ErrorCode::NotSupported, msg).with_remediation("Check the file is complete; run triage to see what it is."),
    }
}

/// Partial coverage with an unknown total (a limit stopped the work).
pub fn partial(examined: u64) -> Coverage {
    Coverage { status: CoverageStatus::Partial, examined: Some(examined), total: None, next_offset: None }
}
