//! The error contract shared by every tool, the CLI and the MCP server.

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// Stable error codes. Agents branch on these; never rename one.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
    /// The input is wrong: a missing or malformed field, or a value out of range.
    BadInput,
    /// The operating system refused (permissions).
    NoPermission,
    /// A file changed on disk since it was opened.
    FileChanged,
    /// An external program answered with something we couldn't read.
    GarbledOutput,
    /// This feature isn't available here (platform, mode or setting).
    FeatureMissing,
    /// This kind of target isn't supported by the tool.
    NotSupported,
    /// A needed external program or engine isn't installed or reachable.
    EngineMissing,
    TimedOut,
    /// A size, count or time limit was reached.
    OverLimit,
    Cancelled,
    /// A file's contents don't match the hash it should have.
    FileHashMismatch,
    /// Reading, writing or unpacking a file failed.
    FileError,
    /// A saved evidence record doesn't match its own id.
    EvidenceHashMismatch,
    Truncated,
    /// Running and recording a program failed.
    RecordingFailed,
    /// Something we started or made couldn't be cleaned up.
    CleanupFailed,
    /// The record changed since the caller read it; re-read and retry.
    StaleRevision,
    BadSettings,
    /// The target, file or item asked for doesn't exist (or none is open).
    NotFound,
    /// An external program ran and failed.
    ProgramFailed,
    /// The user (or project policy) declined consent for a tool that runs code or changes a device.
    ConsentRequired,
    /// A bug in Craft Anything itself. Reported, never panicked.
    Internal,
}

/// What the person or agent can do about an error, for UI treatment.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCategory {
    /// Fix the request.
    Input,
    /// Install or start an engine.
    Engine,
    /// Pick another target.
    Target,
    /// Something was changed or tampered with.
    Tampered,
    /// Part of the result is missing.
    Partial,
    Stopped,
    Slow,
    Limit,
    Missing,
    Failed,
}

impl ErrorCode {
    pub fn category(self) -> ErrorCategory {
        use ErrorCode::*;
        match self {
            BadInput | StaleRevision | BadSettings => ErrorCategory::Input,
            EngineMissing => ErrorCategory::Engine,
            NotSupported => ErrorCategory::Target,
            FileChanged | FileHashMismatch | EvidenceHashMismatch => ErrorCategory::Tampered,
            Truncated => ErrorCategory::Partial,
            Cancelled => ErrorCategory::Stopped,
            TimedOut => ErrorCategory::Slow,
            OverLimit => ErrorCategory::Limit,
            FeatureMissing | NotFound | NoPermission | ConsentRequired => ErrorCategory::Missing,
            GarbledOutput | FileError | RecordingFailed | CleanupFailed | ProgramFailed | Internal => ErrorCategory::Failed,
        }
    }

    pub fn retryable(self) -> bool {
        matches!(self, ErrorCode::TimedOut | ErrorCode::Cancelled | ErrorCode::OverLimit | ErrorCode::StaleRevision)
    }
}

/// A tool failure the user or agent can act on.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, thiserror::Error)]
#[error("{message}")]
pub struct ToolError {
    pub code: ErrorCode,
    pub category: ErrorCategory,
    pub message: String,
    pub retryable: bool,
    /// What to do about it, in plain words.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remediation: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub details: Option<Value>,
}

impl ToolError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        ToolError { code, category: code.category(), message: message.into(), retryable: code.retryable(), remediation: None, details: None }
    }

    pub fn invalid(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::BadInput, message)
    }

    pub fn unsupported(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::NotSupported, message)
    }

    pub fn unavailable(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::FeatureMissing, message)
    }

    pub fn target_required() -> Self {
        Self::new(ErrorCode::NotFound, "No target is open.").with_remediation("Open a file, app or folder first (core_target_open).")
    }

    pub fn internal(message: impl Into<String>) -> Self {
        Self::new(ErrorCode::Internal, message)
    }

    pub fn cancelled() -> Self {
        Self::new(ErrorCode::Cancelled, "The operation was cancelled.")
    }

    pub fn io(context: impl std::fmt::Display, e: std::io::Error) -> Self {
        let code = match e.kind() {
            std::io::ErrorKind::NotFound => ErrorCode::NotFound,
            std::io::ErrorKind::PermissionDenied => ErrorCode::NoPermission,
            _ => ErrorCode::FileError,
        };
        Self::new(code, format!("{context}: {e}"))
    }

    pub fn with_remediation(mut self, r: impl Into<String>) -> Self {
        self.remediation = Some(r.into());
        self
    }

    /// The message and what to do about it, as sentences for a person ("It failed. Try again.").
    pub fn for_people(&self) -> String {
        let message = self.message.trim();
        let Some(fix) = self.remediation.as_deref().map(str::trim).filter(|r| !r.is_empty()) else { return message.to_string() };
        let end = if message.ends_with(['.', '!', '?', ':']) { "" } else { "." };
        format!("{message}{end} {fix}")
    }

    pub fn with_details(mut self, d: Value) -> Self {
        self.details = Some(d);
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serialises_with_snake_case_code() {
        let e = ToolError::target_required();
        let v = serde_json::to_value(&e).unwrap();
        assert_eq!(v["code"], "not_found");
        assert_eq!(v["category"], "missing");
        assert!(v["remediation"].is_string());
    }

    #[test]
    fn a_message_and_its_fix_read_as_sentences() {
        let e = ToolError::new(ErrorCode::TimedOut, "the browser didn't get ready in time").with_remediation("Try again.");
        assert_eq!(e.for_people(), "the browser didn't get ready in time. Try again.");
        assert_eq!(ToolError::invalid("Already a sentence.").with_remediation("Fix it.").for_people(), "Already a sentence. Fix it.");
        assert_eq!(ToolError::invalid("No fix").for_people(), "No fix");
        assert_eq!(ToolError::invalid("Blank fix").with_remediation("  ").for_people(), "Blank fix");
    }
}
