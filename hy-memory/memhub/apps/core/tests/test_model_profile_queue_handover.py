"""Queued work when the model changes or its configuration is deleted (D75).

Switching to a new model continues the queue with it; deleting the
configuration holds the queue instead of failing it, and a later model
resumes the same work. Nothing is deleted in either direction.
"""

import pytest

from one_memory.imports.models import (
    EvidenceContentKind,
    EvidenceInput,
    EvidenceOrigin,
    OriginMetadata,
    WrittenBy,
)
from one_memory.imports.storage import EvidenceStore
from one_memory.memory_tasks import MemoryTaskKind, MemoryTaskStatus, MemoryTaskStore
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileInput,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore


@pytest.fixture
def library(tmp_path):
    class Fixture:
        def __init__(self):
            self.database = tmp_path / "one-memory.sqlite3"
            self.evidence = EvidenceStore(self.database)
            self.profiles = ModelProfileStore(self.database)
            self.secrets = InMemorySecretStore()
            self.tasks = MemoryTaskStore(self.database)
            self.record = self.evidence.put(
                EvidenceInput(
                    source_id="cursor",
                    conversation_id="conversation",
                    message_id="turn",
                    role="user",
                    written_by=WrittenBy.PERSON,
                    verbatim="Synthetic original turn",
                    content_kind=EvidenceContentKind.RAW_CONVERSATION,
                    origin_meta={EvidenceOrigin.FILE: OriginMetadata()},
                )
            ).record

        def profile(self, name, model):
            created = self.profiles.create(
                ModelProfileInput(
                    name=name,
                    provider_kind=ProviderKind.OLLAMA,
                    model=model,
                    embedding_provider_kind=ProviderKind.LOCAL_ONNX,
                    embedding_model="test-local-embedding",
                ),
                self.secrets,
            )
            self.profiles.record_capabilities(
                created.profile_id,
                expected_revision=created.revision,
                capabilities=ModelCapabilities(
                    endpoint_reachable=True,
                    model_available=True,
                    embedding_available=True,
                ),
                secrets=self.secrets,
            )
            return self.profiles.require(created.profile_id, self.secrets)

        def active(self, profile):
            """Activate, then read the profile back so `is_active` is current."""
            self.profiles.activate(profile.profile_id, self.secrets)
            return self.profiles.require(profile.profile_id, self.secrets)

        def task(self, profile):
            return self.tasks.create(
                request_id=f"handover:{profile.profile_id}:{profile.revision}",
                user_id="local",
                kind=MemoryTaskKind.EXTRACT,
                input_ref=self.record.evidence_id,
                profile=profile,
                input_records=(self.record,),
            )

    return Fixture()


def test_activating_a_new_model_continues_the_queue_with_it(library):
    old = library.profile("Old", "old-model")
    new = library.profile("New", "new-model")
    task = library.task(library.active(old))

    moved = library.tasks.rebind_unstarted_profile(new)

    assert moved == 1
    rebound = library.tasks.require(task.task_id)
    assert rebound.profile_id == new.profile_id
    assert rebound.profile_revision == new.revision
    assert rebound.status is MemoryTaskStatus.PENDING
    assert rebound.last_error_code is None


def test_a_deleted_configuration_holds_the_queue_without_failing_it(library):
    profile = library.profile("Doomed", "doomed-model")
    task = library.task(library.active(profile))

    held = library.tasks.pause_profile_for_model(profile.profile_id)

    assert held == 1
    waiting = library.tasks.require(task.task_id)
    assert waiting.status is MemoryTaskStatus.WAITING_FOR_MODEL
    assert waiting.last_error_code == "model_profile_unavailable"
    # Waiting is not failure, and the work is still there to resume.
    assert not library.tasks.list(statuses=(MemoryTaskStatus.FAILED,))

    replacement = library.profile("Replacement", "replacement-model")
    library.tasks.rebind_unstarted_profile(replacement)

    resumed = library.tasks.require(task.task_id)
    assert resumed.profile_id == replacement.profile_id
    assert resumed.status is MemoryTaskStatus.PENDING
