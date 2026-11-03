import asyncio

import pytest

from one_memory.matters.models import Citation, Claim, MatterDraft, MemoryRef, SampleRecord
from one_memory.matters.timeline import reconcile_governed_timeline


def fixture():
    records = [
        SampleRecord(
            evidence_id=f"e{i}",
            source_id="fixture",
            conversation_id="thread",
            role="user",
            written_by="person",
            created_at=f"2026-09-1{i}T08:00:00Z",
            observed_at="2026-09-12T00:00:00Z",
            revision=1,
            content_hash="hash",
            project="Atlas",
            workspace=None,
            text=text,
        )
        for i, text in enumerate(
            (
                "Start with design only; there are two developers.",
                "Now implement the agreed design.",
            )
        )
    ]
    refs = [
        MemoryRef(
            memory_id=f"m{i}",
            revision=1,
            status="confirmed",
            content_hash="hash",
            task_id=f"t{i}",
            hy_memory_id=f"h{i}",
            engine_version="fixture",
            profile_id="model",
            profile_revision=1,
            model="fixture",
        )
        for i in range(2)
    ]
    claims = [
        Claim(
            statement=r.text,
            kind="constraint" if i == 0 else "decision",
            state="current",
            basis="human_statement",
            memory_refs=[refs[i]],
            citations=[
                Citation(
                    evidence_id=r.evidence_id,
                    quote=r.text,
                    written_by="person",
                    created_at=r.created_at,
                )
            ],
        )
        for i, r in enumerate(records)
    ]
    return MatterDraft(
        title="Atlas",
        purpose="Ship Atlas",
        boundary="Product work",
        anchors=["e0", "e1"],
        claims=claims,
    ), records


class Model:
    def __init__(self, *, accept=True, unsupported_id=False):
        self.accept = accept
        self.unsupported_id = unsupported_id
        self.checks = 0
        self.preservation_checks = 0

    async def complete(self, system, data, **kwargs):
        if "preservation_groups" in data and "claims" not in data:
            self.preservation_checks += 1
            groups = data["preservation_groups"]
            assert len(groups) == 1
            assert groups[0]["before"]["statement"].endswith("two developers.")
            assert len(groups[0]["after"]) == 2
            assert all(
                item["statement"] != "Now implement the agreed design."
                for item in groups[0]["after"]
            ), "A change-reason reference is not a rewrite of that source statement"
            return {
                "preservation_reviews": [
                    {"id": group["id"], "verdict": "preserved", "reason": ""} for group in groups
                ]
            }
        if "timeline_claims" in data:
            assert len(data["catalog"]) == 2
            assert data["as_of"] == "2026-09-11T08:00:00Z"
            assert data["catalog"][1]["citations"][0]["quote"] == "Now implement the agreed design."
            return {
                "updates": [
                    {
                        "index": 0,
                        "entries": [
                            {
                                "text": "The design-only phase ended after approval.",
                                "kind": "constraint",
                                "state": "superseded",
                                "scope": "Earlier phase",
                                "supports": ["K0", "K404" if self.unsupported_id else "K1"],
                                "change": "Implementation authorized.",
                            },
                            {
                                "text": "There are two developers.",
                                "kind": "constraint",
                                "state": "current",
                                "scope": "Resources",
                                "supports": ["K0"],
                                "change": "",
                            },
                        ],
                    }
                ]
            }
        self.checks += 1
        assert len(data["governed_memories"]) == 2
        return {
            "reviews": [
                {"id": item["id"], "verdict": "supported" if self.accept else "uncertain"}
                for item in data["claims"]
            ]
        }


def test_timeline_splits_changed_phase_from_unchanged_resources_with_lineage():
    draft, records = fixture()
    model = Model()
    result = asyncio.run(reconcile_governed_timeline(model, draft, draft, records, profile_id=None))
    assert result.claims[0].state == "superseded"
    assert {c.evidence_id for c in result.claims[0].citations} == {"e0", "e1"}
    assert result.claims[1].state == "current" and "two developers" in result.claims[1].statement
    assert {ref.memory_id for claim in result.claims for ref in claim.memory_refs} == {"m0", "m1"}
    assert draft.claims[0].state == "current"
    assert model.checks == 1
    assert model.preservation_checks == 1


@pytest.mark.parametrize("verdict", ["missing", "uncertain", "omitted"])
def test_supported_remaining_text_cannot_hide_lost_meaning(verdict):
    draft, records = fixture()

    class LossyModel(Model):
        async def complete(self, system, data, **kwargs):
            if "preservation_groups" in data and "claims" not in data:
                return {
                    "preservation_reviews": []
                    if verdict == "omitted"
                    else [
                        {
                            "id": group["id"],
                            "verdict": verdict,
                            "reason": "The separate two-developer resource constraint was lost.",
                        }
                        for group in data["preservation_groups"]
                    ]
                }
            if "timeline_claims" in data:
                return {
                    "updates": [
                        {
                            "index": 0,
                            "entries": [
                                {
                                    "text": "The design-only phase ended after approval.",
                                    "kind": "constraint",
                                    "state": "historical",
                                    "scope": "Earlier phase",
                                    "supports": ["K0", "K1"],
                                    "change": "Implementation authorized.",
                                }
                            ],
                        }
                    ]
                }
            return {
                "reviews": [{"id": item["id"], "verdict": "supported"} for item in data["claims"]]
            }

    with pytest.raises(ValueError, match="timeline_(review_failed|preservation_incomplete)"):
        asyncio.run(
            reconcile_governed_timeline(LossyModel(), draft, draft, records, profile_id=None)
        )


@pytest.mark.parametrize("returned_ids", [["p404"], ["p0", "p0"]])
def test_preservation_cannot_accept_duplicate_or_unrequested_group_ids(returned_ids):
    draft, records = fixture()

    class WrongIdentityModel(Model):
        async def complete(self, system, data, **kwargs):
            if "preservation_groups" in data and "claims" not in data:
                return {
                    "preservation_reviews": [
                        {"id": key, "verdict": "preserved"} for key in returned_ids
                    ]
                }
            return await super().complete(system, data, **kwargs)

    with pytest.raises(ValueError, match="timeline_preservation_incomplete"):
        asyncio.run(
            reconcile_governed_timeline(
                WrongIdentityModel(), draft, draft, records, profile_id=None
            )
        )


def test_timeline_cannot_introduce_unknown_support():
    draft, records = fixture()
    with pytest.raises(ValueError, match="unknown_support"):
        asyncio.run(
            reconcile_governed_timeline(
                Model(unsupported_id=True), draft, draft, records, profile_id=None
            )
        )


def test_uncertain_timeline_is_not_saved_as_current_fact():
    draft, records = fixture()
    with pytest.raises(ValueError, match="timeline_review_failed"):
        asyncio.run(
            reconcile_governed_timeline(Model(accept=False), draft, draft, records, profile_id=None)
        )


def test_repair_rechecks_every_projection_of_the_affected_memory():
    draft, records = fixture()
    repeated = draft.model_copy(
        update={"claims": [draft.claims[0], draft.claims[0].model_copy(deep=True), draft.claims[1]]}
    )

    class SharedMemoryModel:
        repaired = []
        checks = 0

        async def complete(self, system, data, **kwargs):
            if "preservation_groups" in data and "claims" not in data:
                return {
                    "preservation_reviews": [
                        {"id": group["id"], "verdict": "preserved"}
                        for group in data["preservation_groups"]
                    ]
                }
            if "timeline_claims" in data:
                if not data.get("review_notes"):
                    return {"updates": []}
                target = data["timeline_claims"][0]
                self.repaired.append(target["index"])
                return {
                    "updates": [
                        {
                            "index": target["index"],
                            "entries": [
                                {
                                    "text": target["statement"],
                                    "kind": "constraint",
                                    "state": "historical",
                                    "scope": "Earlier phase",
                                    "supports": ["K0", "K1"],
                                    "change": "Implementation approved.",
                                }
                            ],
                        }
                    ]
                }
            self.checks += 1
            return {
                "reviews": [
                    {
                        "id": item["id"],
                        "verdict": "unsupported"
                        if (
                            (self.checks == 1 and item["id"] == "r0")
                            or (
                                self.checks > 1
                                and item["kind"] == "constraint"
                                and item["state"] == "current"
                            )
                        )
                        else "supported",
                        "reason": "The phase restriction ended.",
                    }
                    for item in data["claims"]
                ]
            }

    model = SharedMemoryModel()
    result = asyncio.run(
        reconcile_governed_timeline(model, repeated, draft, records, profile_id=None)
    )
    assert model.repaired == [0, 1]
    assert [claim.state for claim in result.claims] == ["historical", "historical", "current"]


def test_historical_human_decisions_remain_required_after_state_resolution():
    from one_memory.matters.synthesis import required_memory_ids

    draft, _ = fixture()
    historical = draft.claims[0].model_copy(update={"state": "historical"})
    superseded = draft.claims[1].model_copy(update={"state": "superseded"})
    assert required_memory_ids([historical, superseded]) == {"m0", "m1"}
