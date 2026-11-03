"""A7-01: the golden corpus comparison."""

from __future__ import annotations

from one_memory.memory_server.golden_corpus import (
    REQUIRED_DOMAINS,
    CorpusReport,
    DomainSample,
    compare,
    digest,
)


def _sample(domain: str, identities: tuple[str, ...]) -> DomainSample:
    return DomainSample(domain=domain, identities=identities, row_count=len(identities))


def _both_sides() -> tuple[dict[str, DomainSample], dict[str, DomainSample]]:
    def side() -> dict[str, DomainSample]:
        return {domain: _sample(domain, ("a", "b")) for domain in REQUIRED_DOMAINS}

    return side(), side()


def test_identical_sides_reconcile() -> None:
    source, target = _both_sides()
    report = compare(source, target)
    assert report.ok is True
    assert report.mismatches == []


def test_a_row_count_difference_is_reported_per_domain() -> None:
    source, target = _both_sides()
    target["evidence"] = _sample("evidence", ("a",))
    report = compare(source, target)
    assert report.ok is False
    assert [item.domain for item in report.mismatches] == ["evidence"]
    assert "row count" in report.mismatches[0].reason


def test_a_content_difference_at_equal_count_is_caught() -> None:
    """Comparing representations would flag every row; identities must match."""
    source, target = _both_sides()
    target["source_cursors"] = _sample("source_cursors", ("a", "different"))
    report = compare(source, target)
    assert report.ok is False
    assert report.mismatches[0].domain == "source_cursors"
    assert "digest" in report.mismatches[0].reason


def test_a_domain_present_on_one_side_only_is_not_a_pass() -> None:
    """Silently skipping it would let a partial migration look complete."""
    source, target = _both_sides()
    del target["grants"]
    report = compare(source, target)
    assert report.ok is False
    assert report.missing_domains == ("grants",)


def test_digest_is_stable_and_order_sensitive() -> None:
    first = digest(_sample("evidence", ("a", "b")))
    assert first == digest(_sample("evidence", ("a", "b")))
    assert first != digest(_sample("evidence", ("b", "a")))


def test_all_required_domains_are_covered() -> None:
    assert set(REQUIRED_DOMAINS) == {
        "evidence",
        "source_cursors",
        "memory_tasks",
        "governed_memories",
        "grants",
    }


def test_an_empty_report_is_not_ok() -> None:
    """No verdicts at all means nothing was compared, which is not success."""
    assert CorpusReport().ok is False
