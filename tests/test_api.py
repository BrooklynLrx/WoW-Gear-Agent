from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

import backend.main as api
from backend.builder_agent import BuildSessionState
from backend.models import ChatSession


class FakeBuilder:
    def __init__(self, spec):
        class_key, spec_key = spec.split(".", 1)
        self.build_state = BuildSessionState(class_key=class_key, spec_key=spec_key)

    def update_build_state(self, **patch):
        current = self.build_state.model_dump()
        current.update({key: value for key, value in patch.items() if key != "constraints"})
        if patch.get("constraints"):
            current["constraints"].update(patch["constraints"])
        self.build_state = BuildSessionState.model_validate(current)
        return {"success": True, "state": self.build_state.model_dump()}

    async def reply_payload(self, message):
        return {
            "message": message,
            "proposal": {"success": True, "solutions": []},
            "state": self.build_state.model_dump(),
            "tool_trace": [{"tool": "optimize_current_loadout", "success": True}],
        }

    async def stream_reply_payload(self, message):
        yield {"event": "text_delta", "data": {"text": message}}
        yield {"event": "proposal", "data": {"success": True, "solutions": []}}
        yield {"event": "state", "data": self.build_state.model_dump()}
        yield {"event": "done", "data": {"message": message, "tool_trace": []}}


def test_chat_sessions_index_matches_recent_conversation_order():
    index = next(value for value in ChatSession.__table__.indexes if value.name == "ix_chat_sessions_updated_at_id")
    assert [column.name for column in index.columns] == ["updated_at", "id"]


def test_builder_http_flow(monkeypatch):
    api.sessions.clear()
    monkeypatch.setattr(api, "create_builder_session", FakeBuilder)
    client = TestClient(api.app)

    created = client.post("/api/v1/builder/sessions", json={"spec": "paladin.holy"})
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    patched = client.patch(
        f"/api/v1/builder/sessions/{session_id}",
        json={"constraints": {"minimum_tier_pieces": 4}},
    )
    assert patched.json()["state"]["constraints"]["minimum_tier_pieces"] == 4

    reply = client.post(
        f"/api/v1/builder/sessions/{session_id}/messages",
        json={"message": "生成一套配装"},
    )
    assert reply.status_code == 200
    assert reply.json()["proposal"]["success"] is True

    stream = client.post(
        f"/api/v1/builder/sessions/{session_id}/messages/stream",
        json={"message": "生成一套配装"},
    )
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: text_delta" in stream.text
    assert "event: proposal" in stream.text
    assert "event: done" in stream.text


def test_invalid_state_patch_returns_422(monkeypatch):
    api.sessions.clear()
    builder = FakeBuilder("mage.arcane")
    builder.update_build_state = lambda **_: {"success": False, "error": "invalid_build_state", "validation": {"errors": ["bad weapon"]}}
    api.sessions["invalid"] = api.SessionEntry(builder)
    response = TestClient(api.app).patch("/api/v1/builder/sessions/invalid", json={"equipment": [{"item_id": 1, "item_level": 334}]})
    assert response.status_code == 422


def test_gem_catalog_exposes_icons():
    gems = TestClient(api.app).get("/api/v1/catalog/gems").json()
    assert gems and all(gem["icon"] for gem in gems)


def test_loadout_snapshot_round_trip():
    builder = FakeBuilder("paladin.holy")
    builder.update_build_state(
        objectives=[{"rule": "minimize", "stat": "mastery"}],
        constraints={"minimum_tier_pieces": 4},
    )
    now = datetime.now()
    loadout = SimpleNamespace(
        id=7,
        name="奶骑四件套",
        creator_name="Lrx",
        class_key=None,
        spec_key=None,
        target_stats_json={},
        constraints_json={},
        state_json=None,
        is_favorite=False,
        created_at=now,
        updated_at=now,
    )

    api.snapshot_loadout(loadout, builder.build_state)
    detail = api.loadout_detail(loadout)

    assert detail.creator_name == "Lrx"
    assert detail.state.spec_key == "holy"
    assert detail.state.constraints.minimum_tier_pieces == 4
    assert detail.state.objectives[0].stat == "mastery"
