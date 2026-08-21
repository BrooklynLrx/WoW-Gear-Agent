import backend.builder_tools as tools
from backend.loot_api import search_loot


def test_weapon_availability_uses_fixed_spec_rules():
    class Item:
        weapon_type = "2h_staff"
        raw_json = {"weapon_type": "2h_staff"}

    assert tools._weapon_is_available("mage.arcane", Item())
    assert not tools._weapon_is_available("rogue.assassination", Item())


def test_picker_weapon_results_match_requested_position():
    main_hands = search_loot(item_level=334, class_key="paladin", spec_key="holy", slot_key="weapon", limit=500)["items"]
    off_hands = search_loot(item_level=334, class_key="paladin", spec_key="holy", slot_key="off_hand", limit=500)["items"]
    assert main_hands and all(item["display_slot_key"] == "weapon" for item in main_hands)
    assert off_hands and all(item["can_equip_off_hand"] for item in off_hands)


def test_picker_exposes_mage_crafted_offhand_stats():
    items = search_loot(
        item_level=331, class_key="mage", spec_key="arcane", slot_key="off_hand", limit=500,
    )["items"]
    lantern = next(item for item in items if item["item_id"] == 245769)
    assert lantern["is_crafted"]
    assert lantern["customizable_secondaries"]
    assert set(lantern["secondary_stat_choices"]) == {
        "critical_strike", "haste", "mastery", "versatility",
    }
    assert lantern["customizable_secondary_amounts"] == [50, 50]
