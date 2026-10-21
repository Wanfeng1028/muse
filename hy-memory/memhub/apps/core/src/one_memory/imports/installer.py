from __future__ import annotations

import hashlib
import os
import shutil
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class InstallAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    NOOP = "noop"
    CONFLICT = "conflict"


class InstallState(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    VERIFIED = "verified"
    ROLLED_BACK = "rolled_back"
    UNAVAILABLE = "unavailable"


class InstallPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    plan_id: str
    source_id: str
    action: InstallAction
    target_path: Path
    before_hash: str | None
    after_hash: str
    backup_path: Path | None
    state: InstallState = InstallState.PLANNED
    reason_code: str | None = None


class InstallReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    plan_id: str
    source_id: str
    action: InstallAction
    state: InstallState
    target_path: Path
    observed_hash: str | None
    changed_at: datetime
    reason_code: str | None = None


class Installer(Protocol):
    def plan(self) -> InstallPlan: ...

    def apply(self, plan: InstallPlan) -> InstallReceipt: ...

    def verify(self, plan: InstallPlan) -> InstallReceipt: ...

    def rollback(self, plan: InstallPlan) -> InstallReceipt: ...


class TransactionalOwnedFileInstaller:
    """Fail-closed installer for a single file wholly owned by One Memory."""

    def __init__(
        self,
        *,
        source_id: str,
        allowed_root: Path,
        relative_path: Path,
        content: bytes,
        backup_root: Path,
        owner_marker: bytes,
    ) -> None:
        root = allowed_root.resolve()
        target = self._validated_target(root, relative_path)
        if not owner_marker or not content.startswith(owner_marker):
            raise ValueError("installed content must start with the owner marker")
        self.allowed_root = root
        self.relative_path = relative_path
        self.source_id = source_id
        self.target = target
        self.content = content
        self.backup_root = backup_root
        self.owner_marker = owner_marker

    @staticmethod
    def _validated_target(root: Path, relative_path: Path) -> Path:
        target = (root / relative_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError("installer target escapes allowed root")
        return target

    def _target_is_contained(self) -> bool:
        try:
            return self._validated_target(self.allowed_root, self.relative_path) == self.target
        except ValueError:
            return False

    def plan(self) -> InstallPlan:
        if not self._target_is_contained():
            return InstallPlan(
                plan_id=uuid4().hex,
                source_id=self.source_id,
                action=InstallAction.CONFLICT,
                target_path=self.target,
                before_hash=None,
                after_hash=_hash(self.content),
                backup_path=None,
                reason_code="installer_target_escaped_allowed_root",
            )
        existing = self.target.read_bytes() if self.target.exists() else None
        before_hash = _hash(existing) if existing is not None else None
        after_hash = _hash(self.content)
        action = InstallAction.CREATE
        reason = None
        if existing is not None and existing == self.content:
            action = InstallAction.NOOP
        elif existing is not None and not existing.startswith(self.owner_marker):
            action = InstallAction.CONFLICT
            reason = "installer_target_not_owned"
        elif existing is not None:
            action = InstallAction.UPDATE
        plan_id = uuid4().hex
        backup = (
            self.backup_root / self.source_id / f"{plan_id}.bak"
            if action is InstallAction.UPDATE
            else None
        )
        return InstallPlan(
            plan_id=plan_id,
            source_id=self.source_id,
            action=action,
            target_path=self.target,
            before_hash=before_hash,
            after_hash=after_hash,
            backup_path=backup,
            reason_code=reason,
        )

    def apply(self, plan: InstallPlan) -> InstallReceipt:
        self._require_plan(plan)
        if not self._target_is_contained():
            return self._unavailable_receipt(
                plan, reason_code="installer_target_escaped_allowed_root"
            )
        if plan.action is InstallAction.CONFLICT:
            return self._receipt(
                plan,
                InstallState.UNAVAILABLE,
                reason_code=plan.reason_code,
            )
        if plan.action is InstallAction.NOOP:
            return self._receipt(plan, InstallState.VERIFIED)
        current = self.target.read_bytes() if self.target.exists() else None
        if (_hash(current) if current is not None else None) != plan.before_hash:
            return self._receipt(
                plan,
                InstallState.UNAVAILABLE,
                reason_code="installer_target_changed_after_plan",
            )
        if plan.backup_path is not None and current is not None:
            plan.backup_path.parent.mkdir(parents=True, exist_ok=True)
            plan.backup_path.write_bytes(current)
            plan.backup_path.chmod(0o600)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.target.with_name(f".{self.target.name}.{plan.plan_id}.tmp")
        temporary.write_bytes(self.content)
        temporary.chmod(0o600)
        os.replace(temporary, self.target)
        return self._receipt(plan, InstallState.APPLIED)

    def verify(self, plan: InstallPlan) -> InstallReceipt:
        self._require_plan(plan)
        if not self._target_is_contained():
            return self._unavailable_receipt(
                plan, reason_code="installer_target_escaped_allowed_root"
            )
        observed = _hash(self.target.read_bytes()) if self.target.exists() else None
        return self._receipt(
            plan,
            InstallState.VERIFIED if observed == plan.after_hash else InstallState.UNAVAILABLE,
            reason_code=None if observed == plan.after_hash else "installer_verify_failed",
        )

    def rollback(self, plan: InstallPlan) -> InstallReceipt:
        self._require_plan(plan)
        if not self._target_is_contained():
            return self._unavailable_receipt(
                plan, reason_code="installer_target_escaped_allowed_root"
            )
        current = self.target.read_bytes() if self.target.exists() else None
        if (_hash(current) if current is not None else None) != plan.after_hash:
            return self._receipt(
                plan,
                InstallState.UNAVAILABLE,
                reason_code="installer_target_changed_after_install",
            )
        if plan.action is InstallAction.CREATE:
            self.target.unlink(missing_ok=True)
        elif plan.action is InstallAction.UPDATE and plan.backup_path is not None:
            if not plan.backup_path.exists():
                return self._receipt(
                    plan,
                    InstallState.UNAVAILABLE,
                    reason_code="installer_backup_missing",
                )
            temporary = self.target.with_name(f".{self.target.name}.{plan.plan_id}.rollback")
            shutil.copyfile(plan.backup_path, temporary)
            temporary.chmod(0o600)
            os.replace(temporary, self.target)
        return self._receipt(plan, InstallState.ROLLED_BACK)

    def _require_plan(self, plan: InstallPlan) -> None:
        if (
            plan.source_id != self.source_id
            or plan.target_path != self.target
            or plan.after_hash != _hash(self.content)
        ):
            raise ValueError("install plan does not belong to this installer")

    def _receipt(
        self,
        plan: InstallPlan,
        state: InstallState,
        *,
        reason_code: str | None = None,
    ) -> InstallReceipt:
        observed = _hash(self.target.read_bytes()) if self.target.exists() else None
        return InstallReceipt(
            plan_id=plan.plan_id,
            source_id=plan.source_id,
            action=plan.action,
            state=state,
            target_path=plan.target_path,
            observed_hash=observed,
            changed_at=datetime.now(UTC),
            reason_code=reason_code,
        )

    def _unavailable_receipt(
        self,
        plan: InstallPlan,
        *,
        reason_code: str,
    ) -> InstallReceipt:
        """Report refusal without reading a target that has escaped its root."""
        return InstallReceipt(
            plan_id=plan.plan_id,
            source_id=plan.source_id,
            action=plan.action,
            state=InstallState.UNAVAILABLE,
            target_path=plan.target_path,
            observed_hash=None,
            changed_at=datetime.now(UTC),
            reason_code=reason_code,
        )


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
