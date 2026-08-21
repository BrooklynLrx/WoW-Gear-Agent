import json
from pathlib import Path

from scripts.build_delve_hero_gear import hero_bonus_ids, parse_hero_items


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


def test_catalog_contains_only_complete_delve_hero_variants():
    data = json.loads((Path(__file__).parents[1] / "data" / "12.1-season2-loot.json").read_text())
    items = [item for item in data["items"] if item.get("instance_type") == "delve"]

    assert len(items) == 74
    assert all({variant["item_level"] for variant in item["variants"]} == {305, 308, 311, 315, 318, 321} for item in items)
    assert all(item["slot_key"] != "unknown" and item["candidate_specs"] for item in items)
    assert all(f"升级：英雄\n{rank}/6" in variant["tooltip_zh_cn"] for item in items for rank, variant in enumerate(item["variants"], 1))
