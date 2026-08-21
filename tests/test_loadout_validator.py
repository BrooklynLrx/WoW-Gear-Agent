from types import SimpleNamespace

from backend.loadout_validator import item_is_available_for_spec, valid_weapon_set, weapon_kind_available_in_position
from scripts.build_crafted_gear import build


def item(weapon_type, slot=""):
    return SimpleNamespace(weapon_type=weapon_type, raw_json={"weapon_type": weapon_type, "slot": slot})


def test_arcane_weapon_sets():
    assert valid_weapon_set("mage.arcane", [item("2h_staff")])
    assert valid_weapon_set("mage.arcane", [item("1h_dagger"), item("off_hand", "Off-Hand Weapon")])
    assert not valid_weapon_set("mage.arcane", [item("1h_dagger")])
    assert not valid_weapon_set("mage.arcane", [item("2h_sword")])
    assert valid_weapon_set("mage.arcane", [item("off_hand", "Off-Hand Weapon"), item("1h_dagger")])


def test_hunter_ranged_weapon_set():
    assert valid_weapon_set("hunter.beast_mastery", [item("ranged_bow")])


def test_dual_wield_position_rules():
    assert weapon_kind_available_in_position("death_knight.frost", item("1h_sword"), "main_hand")
    assert weapon_kind_available_in_position("death_knight.frost", item("1h_sword"), "off_hand")
    assert not weapon_kind_available_in_position("mage.arcane", item("1h_sword"), "off_hand")


def gear(slot, *, armor=None, weapon=None, specs=None):
    return SimpleNamespace(
        slot_key=slot,
        armor_type=armor,
        weapon_type=weapon,
        is_tier=False,
        raw_json={"slot": "Shield" if weapon == "shield" else slot, "weapon_type": weapon, "candidate_specs": specs},
    )


def test_single_item_eligibility_is_strict_for_armor_weapons_and_trinkets():
    assert item_is_available_for_spec("mage", "arcane", gear("head", armor="cloth"))
    assert not item_is_available_for_spec("mage", "arcane", gear("head", armor="leather"))
    assert item_is_available_for_spec("paladin", "holy", gear("weapon", weapon="shield"))
    assert not item_is_available_for_spec("mage", "arcane", gear("weapon", weapon="shield"))
    assert item_is_available_for_spec("mage", "arcane", gear("trinket", specs=["mage.arcane"]))
    assert not item_is_available_for_spec("mage", "arcane", gear("trinket", specs=["paladin.holy"]))
    assert not item_is_available_for_spec("mage", "arcane", gear("trinket"))
    assert not item_is_available_for_spec("mage", "arcane", gear("weapon", weapon="2h_staff", specs=[]))


def test_crafted_weapons_match_spec_primary_stat():
    items = {item["id"]: item for item in build()["items"]}
    intellect_staff = items[245770]
    agility_staff = items[245771]

    assert "mage.arcane" in intellect_staff["candidate_specs"]
    assert "mage.arcane" not in agility_staff["candidate_specs"]
    assert "druid.feral" in agility_staff["candidate_specs"]
    assert "druid.feral" not in intellect_staff["candidate_specs"]
    assert all(item["candidate_specs"] for item in items.values() if item["weapon_type"])


def test_holy_paladin_has_intellect_crafted_one_handers():
    items = {item["id"]: item for item in build()["items"]}

    assert "paladin.holy" in items[237843]["candidate_specs"]
    assert "paladin.holy" in items[237844]["candidate_specs"]
    assert "paladin.holy" not in items[237839]["candidate_specs"]
    assert valid_weapon_set("paladin.holy", [item("2h_mace")])
