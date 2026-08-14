from types import SimpleNamespace

from backend.loadout_validator import valid_weapon_set


def item(weapon_type, slot=""):
    return SimpleNamespace(weapon_type=weapon_type, raw_json={"weapon_type": weapon_type, "slot": slot})


def test_arcane_weapon_sets():
    assert valid_weapon_set("mage.arcane", [item("2h_staff")])
    assert valid_weapon_set("mage.arcane", [item("1h_dagger"), item("off_hand", "Off-Hand Weapon")])
    assert not valid_weapon_set("mage.arcane", [item("1h_dagger")])
    assert not valid_weapon_set("mage.arcane", [item("2h_sword")])


def test_hunter_ranged_weapon_set():
    assert valid_weapon_set("hunter.beast_mastery", [item("ranged_bow")])
