from fastapi.testclient import TestClient

import backend.main as api
from backend.builder_agent import BuildSessionState


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
