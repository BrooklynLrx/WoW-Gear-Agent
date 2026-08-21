import json
from pathlib import Path

from scripts.build_delve_hero_gear import hero_bonus_ids, parse_chest_items, parse_hero_items


def test_parse_hero_items_keeps_only_epic_gear_bought_with_hero_currency():
    page = """id: 'sells', data:[
      {"id":1,"quality":4,"cost":[[0,[[3356,200]],[]]]},
      {"id":1,"quality":4,"cost":[[0,[[2803,3000]],[]]]},
      {"id":2,"quality":2,"cost":[[0,[[3356,200]],[]]]},
      {"id":3,"quality":4,"cost":[[0,[[2803,3000]],[]]]}
    ]});"""

    assert [item["id"] for item in parse_hero_items(page)] == [1]


def test_hero_bonus_ids_replace_vendor_track_but_keep_item_bonuses():
    row = {"bonuses": ["12786", "6652", "13668"]}

    assert hero_bonus_ids(row, 1) == ("12793", "6652", "13668")
    assert hero_bonus_ids(row, 6) == ("12798", "6652", "13668")
    assert hero_bonus_ids({"bonuses": [12786, 6652]}, 6) == ("12798", "6652")


def test_parse_chest_items_keeps_equippable_epics_and_drops_cosmetics():
    page = """id: 'contains', data:[
      {"id":1,"quality":4,"slot":16,"level":90},
      {"id":2,"quality":4,"slot":16,"level":1},
      {"id":3,"quality":3,"slot":16,"level":90},
      {"id":4,"quality":4,"slot":0,"level":90}
    ]});"""

    assert [item["id"] for item in parse_chest_items(page)] == [1]


def test_catalog_contains_only_complete_delve_hero_variants():
    data = json.loads((Path(__file__).parents[1] / "data" / "12.1-season2-loot.json").read_text())
    items = [item for item in data["items"] if item.get("instance_type") == "delve"]

    assert len(items) == 131
    assert any(item["id"] == 272226 for item in items)
    assert all({variant["item_level"] for variant in item["variants"]} == {321} for item in items)
    assert all(item["slot_key"] != "unknown" and item["candidate_specs"] for item in items)
    assert all("升级：英雄\n6/6" in item["variants"][0]["tooltip_zh_cn"] for item in items)
