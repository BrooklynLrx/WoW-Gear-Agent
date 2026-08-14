import asyncio

import pytest
from agentscope.message import Msg, TextBlock
from pydantic import ValidationError

from backend.builder_agent import BuildObjective, BuilderAgentSession


def test_objectives_support_mixed_constraints():
    ratio = BuildObjective(rule="rating_ratio", weights={"critical_strike": 3, "mastery": 1})
    haste = BuildObjective(rule="sheet_percent_range", stat="haste", minimum=19, maximum=21)
    assert ratio.weights["critical_strike"] == 3
    assert haste.maximum == 21


def test_ambiguous_ratio_is_rejected():
    with pytest.raises(ValidationError):
        BuildObjective(rule="rating_ratio")


def test_state_update_merges_constraints_without_model(monkeypatch):
    session = object.__new__(BuilderAgentSession)
    from backend.builder_agent import BuildSessionState
    session.build_state = BuildSessionState(class_key="mage", spec_key="arcane")
    result = session.update_build_state(
        objectives=[{"rule": "minimize", "stat": "versatility"}],
        constraints={"minimum_tier_pieces": 4},
    )
    assert result["state"]["class_key"] == "mage"
    assert result["state"]["constraints"]["minimum_tier_pieces"] == 4


def test_session_is_created_from_one_spec_key():
    session = BuilderAgentSession("mage.arcane")
    assert session.build_state.class_key == "mage"
    assert session.build_state.spec_key == "arcane"
    assert session.last_optimization_result is None


def test_frontend_payload_uses_canonical_optimizer_result():
    session = object.__new__(BuilderAgentSession)
    session.last_optimization_result = {"success": True, "solutions": [{"equipment": []}]}
    assert session.last_optimization_result["solutions"][0]["equipment"] == []


def test_reply_payload_only_returns_current_turn_trace(monkeypatch):
    session = object.__new__(BuilderAgentSession)
    from backend.builder_agent import BuildSessionState
    session.build_state = BuildSessionState(class_key="mage", spec_key="arcane")
    session.last_optimization_result = None
    session.tool_trace = [{"tool": "old_turn", "success": True}]

    async def fake_reply(_text):
        session.tool_trace.append({"tool": "get_build_state", "success": True})
        return Msg(name="wow_builder", role="assistant", content=[TextBlock(text="ok")])

    monkeypatch.setattr(session, "reply", fake_reply)
    payload = asyncio.run(session.reply_payload("test"))
    assert payload["tool_trace"] == [{"tool": "get_build_state", "success": True}]
