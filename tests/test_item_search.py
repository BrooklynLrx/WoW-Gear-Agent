import backend.builder_tools as tools


def test_weapon_availability_uses_fixed_spec_rules():
    class Item:
        weapon_type = "2h_staff"
        raw_json = {"weapon_type": "2h_staff"}

    assert tools._weapon_is_available("mage.arcane", Item())
    assert not tools._weapon_is_available("rogue.assassination", Item())
