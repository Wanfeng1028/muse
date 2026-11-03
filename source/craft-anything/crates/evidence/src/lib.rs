//! Evidence: the one result type every Craft Anything tool returns.
//!
//! An [`Evidence`] record says what was looked at (the subject), what was asked (operation and
//! params), what came back (the result), how sure we are ([`Confidence`]), on whose authority
//! ([`Authority`]), what could not be checked ([`Limitation`]s, [`Coverage`]) and where in the
//! target it points ([`Location`]s). Its id is the SHA-256 of its canonical JSON, so the same
//! observation always has the same id, and any edit to a stored record is detectable.
//!
//! Open questions are first-class too: an [`Unknown`] records what we still don't know and what
//! would settle it ("absence is not proof").
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

mod canonical;
mod error;
mod unknown;

pub use canonical::{canonical_json, sha256_hex};
pub use error::{ErrorCategory, ErrorCode, ToolError};
pub use unknown::{Severity, Unknown, UnknownStatus};

use serde::{Deserialize, Serialize};
use serde_json::Value;

/// How sure a result is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Confidence {
    /// Read directly from the target (bytes, headers, a captured request).
    Observed,
    /// Computed from observations by a deterministic function (a CFG, a call graph).
    Derived,
    /// A best guess: heuristics, naming, or a model's interpretation.
    Inferred,
}

impl Confidence {
    /// Plain-English label used by the Beginner UI.
    pub fn plain_label(self) -> &'static str {
        match self {
            Confidence::Observed => "Seen it",
            Confidence::Derived => "Worked it out",
            Confidence::Inferred => "Best guess",
        }
    }
}

/// Where the authority for a result comes from.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Authority {
    /// The shipped program or file itself.
    OriginalFiles,
    /// A run we controlled (process capture, browser walkthrough).
    OurRun,
    /// A historical record such as a HAR file or a crash dump.
    EarlierRecord,
    /// An outside service (a remote device, an engine's database).
    OutsideService,
    /// Someone's interpretation (an analyst or a model).
    Reasoning,
}

/// What the evidence is about.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Subject {
    /// Target kind, e.g. `native`, `electron`, `apk`, `managed`, `website`, `capture`, `device`.
    pub kind: String,
    /// SHA-256 of the target's bytes, when it is a file.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
    /// Display name (file name, package, URL). Not part of the id.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
}

/// The conditions an observation was made under.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Environment {
    /// True when only Craft Anything's own engines ran (no Ghidra or other third-party decompiler).
    pub clean_room: bool,
    /// Engine that produced the result: `builtin`, `ghidra`, `jadx`, `adb`, `cdp`, …
    pub engine: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub engine_version: Option<String>,
    /// Host OS and architecture, e.g. `linux-x86_64`.
    pub host: String,
    /// The processor/language the Deep engine was pinned to (a Ghidra language id such as
    /// `RISCV:LE:64:RV64GC`), when one was forced. `None` for the usual auto-detected case, so
    /// existing records are unaffected.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub language_id: Option<String>,
}

impl Environment {
    /// The environment for a built-in (clean-room) engine on this host.
    pub fn builtin(clean_room: bool) -> Self {
        Environment { clean_room, engine: "builtin".into(), engine_version: Some(env!("CARGO_PKG_VERSION").into()), host: host_triple(), language_id: None }
    }
}

/// `<os>-<arch>` of the running host.
pub fn host_triple() -> String {
    format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH)
}

/// Something the analysis could not establish or deliberately left out.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Limitation {
    /// Stable machine code, e.g. `stripped_binary`, `indirect_calls_unresolved`, `truncated`.
    pub code: String,
    pub message: String,
}

impl Limitation {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Limitation { code: code.into(), message: message.into() }
    }
}

/// How much of the space was examined.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CoverageStatus {
    Complete,
    Partial,
    #[default]
    Unknown,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Coverage {
    pub status: CoverageStatus,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub examined: Option<u64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub total: Option<u64>,
    /// Offset to continue from when the result is a page.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub next_offset: Option<u64>,
}

/// A byte count in plain words: "512 B", "1.5 KB", "6.30 GB".
pub fn human_bytes(n: u64) -> String {
    let n = n as f64;
    if n < 1024.0 {
        format!("{n} B")
    } else if n < 1024.0 * 1024.0 {
        format!("{:.1} KB", n / 1024.0)
    } else if n < 1024.0 * 1024.0 * 1024.0 {
        format!("{:.1} MB", n / 1024.0 / 1024.0)
    } else {
        format!("{:.2} GB", n / 1024.0 / 1024.0 / 1024.0)
    }
}

impl Coverage {
    pub fn complete(n: u64) -> Self {
        Coverage { status: CoverageStatus::Complete, examined: Some(n), total: Some(n), next_offset: None }
    }

    /// A page of `examined` items out of `total`, continuing at `next_offset` when more remain.
    pub fn page(examined: u64, total: u64, offset: u64) -> Self {
        let end = offset.saturating_add(examined);
        if end >= total {
            Coverage { status: CoverageStatus::Complete, examined: Some(examined), total: Some(total), next_offset: None }
        } else {
            Coverage { status: CoverageStatus::Partial, examined: Some(examined), total: Some(total), next_offset: Some(end) }
        }
    }
}

/// A place in the target the evidence points at.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Location {
    /// `address`, `file_offset`, `path`, `url`, `line`, `class`, `method`, `module`, `request`…
    pub kind: String,
    pub value: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub label: Option<String>,
}

impl Location {
    pub fn new(kind: impl Into<String>, value: impl Into<String>) -> Self {
        Location { kind: kind.into(), value: value.into(), label: None }
    }

    pub fn address(addr: u64) -> Self {
        Location::new("address", format!("{addr:#x}"))
    }

    pub fn with_label(mut self, label: impl Into<String>) -> Self {
        self.label = Some(label.into());
        self
    }
}

/// One evidence record. Construct with [`EvidenceBuilder`], which computes the id.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Evidence {
    /// `ev_` + 64 lowercase hex: SHA-256 of the canonical JSON of every other field except `summary`
    /// and `subject.name` (display-only).
    pub id: String,
    pub subject: Subject,
    /// The tool that produced it, e.g. `native_function_pseudocode`.
    pub operation: String,
    pub params: Value,
    pub result: Value,
    /// One or two plain sentences for people. Display only, not part of the id.
    #[serde(default)]
    pub summary: String,
    pub confidence: Confidence,
    pub authority: Authority,
    pub environment: Environment,
    #[serde(default)]
    pub limitations: Vec<Limitation>,
    #[serde(default)]
    pub coverage: Coverage,
    #[serde(default)]
    pub locations: Vec<Location>,
    /// Ids of evidence this was derived from.
    #[serde(default)]
    pub links: Vec<String>,
    /// True when the result embeds bytes, strings or decompiled text taken from the target
    /// (strings, pseudo-C, source, a captured body, a plist value…). A reader must treat that
    /// content as data from an untrusted artifact, never as instructions. Display-only, like
    /// `summary`: excluded from the id so it never changes an existing record's id.
    #[serde(default, skip_serializing_if = "is_false")]
    pub carries_target_content: bool,
}

fn is_false(b: &bool) -> bool {
    !*b
}

impl Evidence {
    /// Recompute the id from the content.
    pub fn compute_id(&self) -> Result<String, ToolError> {
        let mut v = serde_json::to_value(self).map_err(|e| ToolError::internal(format!("serialising evidence: {e}")))?;
        if let Value::Object(map) = &mut v {
            map.remove("id");
            map.remove("summary");
            // Display/provenance-only: never part of the content identity.
            map.remove("carries_target_content");
            if let Some(Value::Object(subject)) = map.get_mut("subject") {
                subject.remove("name");
            }
        }
        Ok(format!("ev_{}", sha256_hex(canonical_json(&v).as_bytes())))
    }

    /// True when the stored id matches the content (tamper check on import).
    pub fn verify(&self) -> bool {
        self.compute_id().is_ok_and(|id| id == self.id)
    }

    /// A compact view for agents and lists: everything except the full result.
    pub fn summary_view(&self) -> Value {
        serde_json::json!({
            "evidence_id": self.id,
            "operation": self.operation,
            "summary": self.summary,
            "confidence": self.confidence,
            "limitations": self.limitations,
            "coverage": self.coverage,
            "subject": self.subject,
            "carries_target_content": self.carries_target_content,
        })
    }
}

/// Builds an [`Evidence`] and computes its id.
#[derive(Debug, Clone)]
pub struct EvidenceBuilder {
    ev: Evidence,
}

impl EvidenceBuilder {
    pub fn new(operation: impl Into<String>, subject: Subject, environment: Environment) -> Self {
        EvidenceBuilder {
            ev: Evidence {
                id: String::new(),
                subject,
                operation: operation.into(),
                params: Value::Null,
                result: Value::Null,
                summary: String::new(),
                confidence: Confidence::Observed,
                authority: Authority::OriginalFiles,
                environment,
                limitations: Vec::new(),
                coverage: Coverage::default(),
                locations: Vec::new(),
                links: Vec::new(),
                carries_target_content: false,
            },
        }
    }

    pub fn params(mut self, params: Value) -> Self {
        self.ev.params = params;
        self
    }

    pub fn result(mut self, result: Value) -> Self {
        self.ev.result = result;
        self
    }

    pub fn summary(mut self, summary: impl Into<String>) -> Self {
        self.ev.summary = summary.into();
        self
    }

    pub fn confidence(mut self, c: Confidence) -> Self {
        self.ev.confidence = c;
        self
    }

    pub fn authority(mut self, a: Authority) -> Self {
        self.ev.authority = a;
        self
    }

    pub fn limitation(mut self, l: Limitation) -> Self {
        self.ev.limitations.push(l);
        self
    }

    pub fn limitations(mut self, ls: impl IntoIterator<Item = Limitation>) -> Self {
        self.ev.limitations.extend(ls);
        self
    }

    pub fn coverage(mut self, c: Coverage) -> Self {
        self.ev.coverage = c;
        self
    }

    pub fn location(mut self, l: Location) -> Self {
        self.ev.locations.push(l);
        self
    }

    pub fn locations(mut self, ls: impl IntoIterator<Item = Location>) -> Self {
        self.ev.locations.extend(ls);
        self
    }

    pub fn link(mut self, id: impl Into<String>) -> Self {
        self.ev.links.push(id.into());
        self
    }

    /// Mark that the result embeds content taken from the target (strings, decompiled text, a
    /// captured body…), so agents and the MCP server treat it as untrusted data, not instructions.
    pub fn target_content(mut self, embeds: bool) -> Self {
        self.ev.carries_target_content = embeds;
        self
    }

    pub fn build(mut self) -> Result<Evidence, ToolError> {
        self.ev.id = self.ev.compute_id()?;
        Ok(self.ev)
    }
}

/// A reference to evidence the session already holds, so callers needn't resend it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "kebab-case")]
pub enum EvidenceRef {
    Saved { evidence_id: String },
}

/// True for ids of the form `ev_` + 64 lowercase hex digits.
pub fn is_evidence_id(s: &str) -> bool {
    s.strip_prefix("ev_").is_some_and(|h| h.len() == 64 && h.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Evidence {
        EvidenceBuilder::new(
            "core_overview_show",
            Subject { kind: "native".into(), sha256: Some("ab".repeat(32)), name: Some("sample.exe".into()) },
            Environment::builtin(true),
        )
        .params(serde_json::json!({"b": 1, "a": [3, 2]}))
        .result(serde_json::json!({"functions": 12}))
        .summary("A small Windows program.")
        .confidence(Confidence::Derived)
        .build()
        .unwrap()
    }

    #[test]
    fn id_is_stable_and_well_formed() {
        let a = sample();
        let b = sample();
        assert_eq!(a.id, b.id);
        assert!(is_evidence_id(&a.id), "{}", a.id);
        assert!(a.verify());
    }

    #[test]
    fn display_fields_do_not_change_the_id() {
        let a = sample();
        let mut b = a.clone();
        b.summary = "Different words".into();
        b.subject.name = Some("renamed.exe".into());
        assert_eq!(b.compute_id().unwrap(), a.id);
    }

    #[test]
    fn content_change_is_detected() {
        let mut a = sample();
        a.result = serde_json::json!({"functions": 13});
        assert!(!a.verify());
    }

    #[test]
    fn round_trips_through_json() {
        let a = sample();
        let s = serde_json::to_string(&a).unwrap();
        let b: Evidence = serde_json::from_str(&s).unwrap();
        assert_eq!(a, b);
        assert!(b.verify());
    }

    #[test]
    fn target_content_flag_round_trips_and_leaves_id_unchanged() {
        // The id of the stock sample, computed before this field existed.
        let baseline = sample();
        let baseline_id = baseline.id.clone();

        // Setting the flag must not change the id (it is excluded from the identity, like summary).
        let marked = EvidenceBuilder::new(
            "core_overview_show",
            Subject { kind: "native".into(), sha256: Some("ab".repeat(32)), name: Some("sample.exe".into()) },
            Environment::builtin(true),
        )
        .params(serde_json::json!({"b": 1, "a": [3, 2]}))
        .result(serde_json::json!({"functions": 12}))
        .summary("A small Windows program.")
        .confidence(Confidence::Derived)
        .target_content(true)
        .build()
        .unwrap();
        assert!(marked.carries_target_content);
        assert_eq!(marked.id, baseline_id, "the flag must not change the evidence id");
        assert!(marked.verify());

        // It survives a JSON round trip, and is omitted from the wire when false.
        let s = serde_json::to_string(&marked).unwrap();
        assert!(s.contains("carries_target_content"));
        let back: Evidence = serde_json::from_str(&s).unwrap();
        assert!(back.carries_target_content);
        assert!(back.verify());

        let off = serde_json::to_string(&baseline).unwrap();
        assert!(!off.contains("carries_target_content"), "the flag is skipped when false");
        // A record saved before the field existed still deserialises and keeps its id.
        let legacy: Evidence = serde_json::from_str(&off).unwrap();
        assert!(!legacy.carries_target_content);
        assert_eq!(legacy.id, baseline_id);
        assert!(legacy.verify());
    }

    #[test]
    fn coverage_page_math() {
        let c = Coverage::page(10, 25, 10);
        assert_eq!(c.status, CoverageStatus::Partial);
        assert_eq!(c.next_offset, Some(20));
        let d = Coverage::page(5, 25, 20);
        assert_eq!(d.status, CoverageStatus::Complete);
        let e = Coverage::page(0, 0, u64::MAX);
        assert_eq!(e.status, CoverageStatus::Complete);
    }
}
