"""A5-01/A5-03: process ownership, and the three grants kept apart."""

from __future__ import annotations

import pytest

from one_memory.memory_server.daemon_contract import (
    AlreadyOwned,
    Grant,
    Owner,
    OwnershipLedger,
    Process,
    Switch,
    new_state,
    reconcile,
    with_desired,
)


def test_a_process_can_be_claimed() -> None:
    ledger = OwnershipLedger()
    claim = ledger.claim(Owner.DAEMON, Process.MYSQL)
    assert claim.owner is Owner.DAEMON
    assert ledger.owner_of(Process.MYSQL) is Owner.DAEMON


def test_a_second_claimant_is_refused() -> None:
    """A silent takeover would leave two components both believing they may
    stop the same process."""
    ledger = OwnershipLedger()
    ledger.claim(Owner.DAEMON, Process.SERVER)
    with pytest.raises(AlreadyOwned):
        ledger.claim(Owner.DESKTOP, Process.SERVER)


def test_the_same_owner_may_reclaim() -> None:
    ledger = OwnershipLedger()
    ledger.claim(Owner.DAEMON, Process.SERVER)
    ledger.claim(Owner.DAEMON, Process.SERVER)
    assert ledger.owner_of(Process.SERVER) is Owner.DAEMON


def test_only_the_owner_may_control() -> None:
    ledger = OwnershipLedger()
    ledger.claim(Owner.DAEMON, Process.BROKER)
    assert ledger.may_control(Owner.DAEMON, Process.BROKER) is True
    assert ledger.may_control(Owner.CLI, Process.BROKER) is False


def test_releasing_is_idempotent() -> None:
    ledger = OwnershipLedger()
    ledger.release(Owner.CLI, Process.MYSQL)
    assert ledger.owner_of(Process.MYSQL) is None


def test_you_cannot_release_another_owners_claim() -> None:
    """Otherwise a client could stop a process it does not own."""
    ledger = OwnershipLedger()
    ledger.claim(Owner.DAEMON, Process.MYSQL)
    ledger.release(Owner.CLI, Process.MYSQL)
    assert ledger.owner_of(Process.MYSQL) is Owner.DAEMON


def test_a_released_process_can_be_claimed_again() -> None:
    ledger = OwnershipLedger()
    ledger.claim(Owner.DAEMON, Process.MYSQL)
    ledger.release(Owner.DAEMON, Process.MYSQL)
    assert ledger.owner_of(Process.MYSQL) is None
    ledger.claim(Owner.CLI, Process.MYSQL)
    assert ledger.owner_of(Process.MYSQL) is Owner.CLI


def test_grants_start_off_and_consistent() -> None:
    state = new_state()
    for grant in Grant:
        assert state.is_actually_on(grant) is False
        assert state.is_desired_on(grant) is False


def test_setting_intent_does_not_change_what_is_in_force() -> None:
    """A switch the user just turned on is not yet in force."""
    state = with_desired(new_state(), Grant.SOURCE_READ, Switch.ON)
    assert state.is_desired_on(Grant.SOURCE_READ) is True
    assert state.is_actually_on(Grant.SOURCE_READ) is False


def test_reconcile_makes_actual_match_desired() -> None:
    state = with_desired(new_state(), Grant.SOURCE_READ, Switch.ON)
    assert reconcile(state).is_actually_on(Grant.SOURCE_READ) is True


def test_revoking_is_applied_too() -> None:
    state = with_desired(new_state(), Grant.MODEL_EGRESS, Switch.ON)
    applied = reconcile(state)
    assert applied.is_actually_on(Grant.MODEL_EGRESS) is True
    revoked = reconcile(with_desired(applied, Grant.MODEL_EGRESS, Switch.OFF))
    assert revoked.is_actually_on(Grant.MODEL_EGRESS) is False


def test_the_three_grants_are_independent() -> None:
    """Turning one on must not imply the others."""
    state = reconcile(with_desired(new_state(), Grant.HOST_READ, Switch.ON))
    assert state.is_actually_on(Grant.HOST_READ) is True
    assert state.is_actually_on(Grant.SOURCE_READ) is False
    assert state.is_actually_on(Grant.MODEL_EGRESS) is False


def test_reconcile_applies_all_at_once() -> None:
    """A partial application would leave a revoked grant still in force."""
    state = new_state()
    for grant in Grant:
        state = with_desired(state, grant, Switch.ON)
    applied = reconcile(state)
    assert all(applied.is_actually_on(grant) for grant in Grant)


def test_state_is_not_mutated_in_place() -> None:
    original = new_state()
    with_desired(original, Grant.SOURCE_READ, Switch.ON)
    assert original.is_desired_on(Grant.SOURCE_READ) is False
