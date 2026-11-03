"""A7-01: the golden corpus, and the reconciliation that proves a migration.

A migration is only proven by comparing what came out against what went in.
This module defines that comparison so it is runnable rather than described.

Two properties matter more than the row counts:

- **Every domain in the objective is covered.** The corpus names the domains
  A7-01 requires (Evidence, cursor, tasks, Governance, grants). A migration that
  reconciles four of five would otherwise look finished.
- **A difference is reported per domain, not as one verdict.** "Counts differ"
  tells you nothing about where; `mismatches` names the domain.

The digest here is over identities rather than whole rows, because a row's
representation legitimately differs between engines (timestamps, numeric types)
while its identity must not. Comparing representations would report a false
mismatch on every row.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

#: Domains A7-01 requires. Migrating a subset must not read as complete.
REQUIRED_DOMAINS: tuple[str, ...] = (
    "evidence",
    "source_cursors",
    "memory_tasks",
    "governed_memories",
    "grants",
)


@dataclass(frozen=True)
class DomainSample:
    """One domain as observed on one side of the migration."""

    domain: str
    #: Ordered row identities. Order must be stable across runs.
    identities: tuple[str, ...]
    row_count: int


def digest(sample: DomainSample) -> str:
    """Digest ordered identities, not whole rows.

    Row representations differ between engines for legitimate reasons;
    identities do not. Digesting representations would flag every row.
    """
    joined = "\n".join(sample.identities)
    return hashlib.sha256(joined.encode()).hexdigest()


@dataclass(frozen=True)
class DomainVerdict:
    domain: str
    ok: bool
    reason: str = ""


@dataclass
class CorpusReport:
    """Result of comparing both sides."""

    verdicts: list[DomainVerdict] = field(default_factory=list)
    missing_domains: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        """True only when every required domain was actually compared and agreed.

        An empty report must not be `ok`. "Nothing disagreed" is not the same as
        "everything was checked", and an empty verdict list would otherwise let a
        comparison that never ran be reported as a successful migration.
        """
        if self.missing_domains:
            return False
        if len(self.verdicts) != len(REQUIRED_DOMAINS):
            return False
        return all(item.ok for item in self.verdicts)

    @property
    def mismatches(self) -> list[DomainVerdict]:
        return [item for item in self.verdicts if not item.ok]


def compare(
    source: dict[str, DomainSample],
    target: dict[str, DomainSample],
) -> CorpusReport:
    """Compare both sides, per domain.

    A domain present on one side only is a mismatch, not a pass: silently
    skipping it would let a partially-migrated database look complete.
    """
    report = CorpusReport()
    report.missing_domains = tuple(
        domain for domain in REQUIRED_DOMAINS if domain not in source or domain not in target
    )

    for domain in REQUIRED_DOMAINS:
        if domain in report.missing_domains:
            continue
        before, after = source[domain], target[domain]
        if before.row_count != after.row_count:
            report.verdicts.append(
                DomainVerdict(
                    domain,
                    False,
                    f"row count differs: {before.row_count} -> {after.row_count}",
                )
            )
            continue
        if digest(before) != digest(after):
            report.verdicts.append(
                DomainVerdict(domain, False, "identity digest differs at equal row count")
            )
            continue
        report.verdicts.append(DomainVerdict(domain, True))

    return report
