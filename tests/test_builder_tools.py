import backend.builder_tools as tools
from types import SimpleNamespace


class Session:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def test_off_hand_weapon_has_separate_display_slot():
    item = SimpleNamespace(raw_json={"slot": "Off-Hand Weapon", "weapon_type": "off_hand"}, weapon_type="off_hand")
    assert tools.display_slot_key("weapon", item) == "off_hand"


def test_invalid_loadout_stops_before_calculation(monkeypatch):
    monkeypatch.setattr(tools, "SessionLocal", Session)
    monkeypatch.setattr(tools, "validate_loadout", lambda *args: {"valid": False, "errors": ["bad"]})
    monkeypatch.setattr(tools, "calculate_equipment", lambda *args: (_ for _ in ()).throw(AssertionError()))
    result = tools.calculate_stats("mage", "arcane", [])
    assert result["success"] is False
    assert result["error"] == "invalid_loadout"
