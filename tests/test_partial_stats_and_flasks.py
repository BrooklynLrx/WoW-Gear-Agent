from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

import backend.builder_tools as tools
import backend.main as api
import backend.loadout_optimizer as optimizer
from backend.builder_agent import BuildSessionState, BuilderAgentSession
from backend.db import Base
from scripts.import_data import import_all


def test_partial_totals_and_flask_changes_are_counted_once(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, BigInteger):
                monkeypatch.setattr(column, "type", Integer())
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        import_all(db)
    monkeypatch.setattr(tools, "SessionLocal", sessions)
    monkeypatch.setattr(optimizer, "SessionLocal", sessions)
    builder = object.__new__(BuilderAgentSession)
    builder.build_state = BuildSessionState(class_key="mage", spec_key="arcane")
    monkeypatch.setattr(api, "sessions", {"partial": api.SessionEntry(builder)})
    client = TestClient(api.app)
    url = "/api/v1/builder/sessions/partial"

    def patch(**state):
        response = client.patch(url, json=state)
        assert response.status_code == 200, response.text
        result = client.get(url + "/stats").json()
        assert result["success"], result
        return result["calculation"]

    assert client.get(url + "/stats").json()["calculation"]["ratings"] == dict.fromkeys(("critical_strike", "haste", "mastery", "versatility"), 0)
    assert len(client.get("/api/v1/catalog/flasks").json()) == 4
    first = {"item_id": 239047, "item_level": 334}
    second = {"item_id": 251173, "item_level": 340}
    head = patch(equipment=[first])["ratings"]
    neck = tools.calculate_stats("mage", "arcane", [second], require_complete=False)["calculation"]["ratings"]
    two = patch(equipment=[first, second])["ratings"]
    assert two == {key: head[key] + neck[key] for key in head}
    crit = patch(consumable_ids=[241326], constraints={"auto_select_flask": False})["ratings"]
    assert crit == {key: value + (165 if key == "critical_strike" else 0) for key, value in two.items()}
    haste = patch(consumable_ids=[241324])["ratings"]
    assert haste == {key: value + (165 if key == "haste" else 0) for key, value in two.items()}
    assert patch(consumable_ids=[])["ratings"] == two
    assert patch(equipment=[first])["ratings"] == head
    only_flask = patch(equipment=[], consumable_ids=[241326])
    assert only_flask["ratings"]["critical_strike"] == 165
    assert only_flask["percentages"]["critical_strike"] > 5
    assert client.patch(url, json={"consumable_ids": [241326, 241324]}).status_code == 422
    patch(consumable_ids=[])

    monkeypatch.setattr(optimizer, "BEAM_WIDTH", 20)
    monkeypatch.setattr(optimizer, "MAX_GROUP_OPTIONS", 20)
    objective = [{"rule": "rating_ratio", "weights": {"critical_strike": 1, "haste": 1, "mastery": 1, "versatility": 1}}]
    constraints = {"auto_select_flask": False, "allow_crafted": False, "maximum_crafted_items": 0, "use_bis_trinkets": False}
    for consumables in ([], [241326]):
        result = optimizer.optimize_loadout("mage", "arcane", objective, constraints, consumable_ids=consumables, solution_count=1)
        assert result["success"], result
        assert result["solutions"][0]["consumable_ids"] == consumables
