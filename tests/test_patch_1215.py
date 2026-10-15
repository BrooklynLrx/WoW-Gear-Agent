from sqlalchemy import BigInteger, Integer, create_engine
from sqlalchemy.orm import sessionmaker

import backend.builder_tools as tools
import backend.loot_api as loot_api
import backend.loadout_optimizer as optimizer
from backend.db import Base
from backend.loadout_validator import rules
from scripts.import_data import import_all


def test_1215_default_levels_search_and_optimizer_preserve_history(monkeypatch):
    engine = create_engine("sqlite://")
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, BigInteger):
                monkeypatch.setattr(column, "type", Integer())
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        import_all(db)
    for module in (tools, loot_api, optimizer):
        monkeypatch.setattr(module, "SessionLocal", sessions)

    for spec in rules()["specs"]:
        class_key, spec_key = spec.split(".")
        items = tools.search_items_for_spec(class_key, spec_key, item_level=0, limit=500)["items"]
        assert items, spec
        for item in items:
            assert item["item_level"] == item["graduation_item_level"]
            if item["slot_key"] in {"weapon", "neck", "trinket"} and item["item_level"] != 321:
                assert item["item_level"] == (338 if item["is_crafted"] else 340), (spec, item)

    defaults = loot_api.search_loot(item_level=0, class_key="mage", spec_key="arcane", limit=500)["items"]
    staff = next(item for item in defaults if item["item_id"] == 245770)
    assert staff["item_level"] == 338 and staff["customizable_secondary_amounts"]
    assert any(item["item_id"] == 281235 and item["item_level"] == 334 for item in defaults)
    assert next(item for item in defaults if item["item_id"] == 281235)["catalyst_eligible"]
    assert any(item["item_id"] == 281056 and item["item_level"] == 340 for item in defaults)
    assert not any(item["item_id"] == 280835 for item in defaults)  # healer-only trinket
    assert loot_api.search_loot(item_level=334, item_ids=[251173])["items"][0]["item_level"] == 334
    delve_hero = loot_api.search_loot(item_level=321, source_type="delve", class_key="mage", spec_key="arcane", limit=500)["items"]
    assert delve_hero
    delve_default = loot_api.search_loot(item_level=0, source_type="delve", class_key="mage", spec_key="arcane", limit=500)["items"]
    assert any(item["slot_key"] == "head" and item["item_level"] == 334 for item in delve_default)
    rings = {item["item_id"]: item for item in delve_default if item["slot_key"] == "finger"}
    assert rings[272149]["item_level"] == 334  # screenshot: 妖术指环
    assert rings[249621]["item_level"] == 334  # screenshot: 巫毒指环
    assert all(item["item_level"] == 334 for item in rings.values())
    assert all(item["item_level"] == 334 for item in delve_default if item["slot_key"] == "back")
    assert all(item["item_level"] == 340 for item in delve_default if item["slot_key"] == "neck")
    assert all(item["item_level"] == 321 for item in delve_default if item["slot_key"] in {"weapon", "trinket"})

    result = optimizer.optimize_loadout(
        "mage", "arcane", [{"rule": "rating_ratio", "weights": {"critical_strike": 3, "haste": 3, "versatility": 3, "mastery": 1}}],
        {"locked_item_ids": [245770], "excluded_source_types": ["raid", "world_boss"], "use_bis_trinkets": False},
        solution_count=1,
    )
    assert result["success"], result
    equipment = result["solutions"][0]["equipment"]
    assert sum(item["is_crafted"] for item in equipment) == 2
    assert any(item["item_id"] == 245770 and item["item_level"] == 338 for item in equipment)
    assert all(item["item_level"] == 340 for item in equipment if item["slot_key"] in {"neck", "trinket"} and not item["is_crafted"])
