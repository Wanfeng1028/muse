//! Residual unknowns: open questions, recorded with what would settle them.

use crate::{ErrorCode, ToolError, canonical_json, sha256_hex};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum UnknownStatus {
    #[default]
    Open,
    Investigating,
    Blocked,
    Contradicted,
    Resolved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Low,
    #[default]
    Medium,
    High,
    Critical,
}

/// One open question. Revisions use optimistic concurrency: an update must name the revision it
/// was based on.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Unknown {
    /// `unk_` + 16 hex digits, derived from the first revision's question and domain.
    pub id: String,
    pub revision: u64,
    pub question: String,
    pub severity: Severity,
    /// Area: `native`, `network`, `ui`, `storage`, …
    pub domain: String,
    pub status: UnknownStatus,
    /// What would settle it: probes, tools to run, facts to check.
    #[serde(default)]
    pub probes: Vec<String>,
    #[serde(default)]
    pub evidence_for: Vec<String>,
    #[serde(default)]
    pub evidence_against: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolution: Option<String>,
}

impl Unknown {
    pub fn new(question: impl Into<String>, domain: impl Into<String>, severity: Severity) -> Self {
        let question = question.into();
        let domain = domain.into();
        let seed = serde_json::json!({"question": question, "domain": domain});
        let digest = sha256_hex(canonical_json(&seed).as_bytes());
        let short = digest.get(..16).unwrap_or(&digest).to_string();
        Unknown {
            id: format!("unk_{short}"),
            revision: 1,
            question,
            severity,
            domain,
            status: UnknownStatus::Open,
            probes: Vec::new(),
            evidence_for: Vec::new(),
            evidence_against: Vec::new(),
            resolution: None,
        }
    }

    /// Replace this record with `next` if `based_on_revision` matches; bumps the revision.
    pub fn apply_update(&mut self, based_on_revision: u64, mut next: Unknown) -> Result<(), ToolError> {
        if based_on_revision != self.revision {
            return Err(ToolError::new(ErrorCode::StaleRevision, format!("{} is at revision {}, not {}", self.id, self.revision, based_on_revision))
                .with_remediation("Read the unknown again and retry with its current revision."));
        }
        if self.status == UnknownStatus::Resolved && next.status == UnknownStatus::Resolved && next.resolution.is_none() {
            return Err(ToolError::invalid("A resolved unknown needs a resolution."));
        }
        next.id = self.id.clone();
        next.revision = self.revision.saturating_add(1);
        *self = next;
        Ok(())
    }

    /// A resolved unknown must say how, and cite at least one piece of evidence.
    pub fn resolution_is_valid(&self) -> bool {
        self.status == UnknownStatus::Resolved && self.resolution.as_deref().is_some_and(|r| !r.trim().is_empty()) && !self.evidence_for.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn optimistic_concurrency() {
        let mut u = Unknown::new("Where is the % rule implemented?", "native", Severity::High);
        assert!(u.id.starts_with("unk_"));
        let mut next = u.clone();
        next.status = UnknownStatus::Investigating;
        u.apply_update(1, next.clone()).unwrap();
        assert_eq!(u.revision, 2);
        let err = u.apply_update(1, next).unwrap_err();
        assert_eq!(err.code, ErrorCode::StaleRevision);
    }
}
