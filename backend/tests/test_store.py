"""Tests for trusted session and deferred-call persistence."""

from pathlib import Path

import pytest

from mia_dpp.agent.models import HumanRequest, HumanRequestKind, MiaState
from mia_dpp.store import SessionSnapshot, Store


def _request() -> HumanRequest:
    return HumanRequest(
        kind=HumanRequestKind.MAPPING_REVIEW,
        product_id="product-one",
        summary="Review this mapping.",
    )


def test_store_survives_restart_and_consumes_a_call_once(tmp_path: Path) -> None:
    path = tmp_path / "mia.sqlite3"
    session_id = "thread-store-one"
    Store(path).save(
        SessionSnapshot(state=MiaState(thread_id=session_id), history=[]),
        deferred_calls=[("call-one", _request())],
    )

    restarted = Store(path)
    snapshot = restarted.load(session_id)
    assert snapshot is not None
    assert snapshot.state.thread_id == session_id
    assert restarted.pending(session_id)[0].call_id == "call-one"
    snapshot.state.user_goal = "Human input already applied"

    resolved = restarted.resolve(
        snapshot,
        "call-one",
        expected_kind=HumanRequestKind.MAPPING_REVIEW,
        result={"decision": "reject"},
    )
    assert restarted.pending(session_id) == ()
    assert restarted.resolved(session_id) == (resolved,)
    recovered = Store(path).load(session_id)
    assert recovered is not None
    assert recovered.state.user_goal == "Human input already applied"
    assert Store(path).resolved(session_id)[0].result == {"decision": "reject"}
    restarted.save(snapshot, completed_call_ids=("call-one",))
    assert restarted.resolved(session_id) == ()
    with pytest.raises(ValueError, match="already been consumed"):
        restarted.resolve(
            snapshot,
            "call-one",
            expected_kind=HumanRequestKind.MAPPING_REVIEW,
            result={"decision": "approve"},
        )


def test_store_rejects_wrong_session_call_and_action_type(tmp_path: Path) -> None:
    store = Store(tmp_path / "mia.sqlite3")
    snapshot = SessionSnapshot(state=MiaState(thread_id="thread-store-two"), history=[])
    store.save(snapshot, deferred_calls=[("call-two", _request())])

    with pytest.raises(ValueError, match="unknown deferred call"):
        store.resolve(
            SessionSnapshot(state=MiaState(thread_id="thread-other"), history=[]),
            "call-two",
            expected_kind=HumanRequestKind.MAPPING_REVIEW,
            result={},
        )
    with pytest.raises(ValueError, match="does not accept"):
        store.resolve(
            snapshot,
            "call-two",
            expected_kind=HumanRequestKind.REQUIREMENT_VALUE,
            result={},
        )


def test_store_preserves_multiple_pending_calls(tmp_path: Path) -> None:
    store = Store(tmp_path / "mia.sqlite3")
    session_id = "thread-store-many"
    store.save(
        SessionSnapshot(state=MiaState(thread_id=session_id), history=[]),
        deferred_calls=[("call-first", _request()), ("call-second", _request())],
    )

    assert [call.call_id for call in store.pending(session_id)] == [
        "call-first",
        "call-second",
    ]
