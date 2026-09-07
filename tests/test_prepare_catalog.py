from scripts.prepare_catalog import TIDEBOUND_GROTTO_ITEM_IDS, apply_known_item_corrections, normalize_slot


def test_shield_is_not_classified_as_a_caster_off_hand():
    item = {"slot": "Shield", "variants": [{"tooltip_zh_cn": "\n副手\n盾\n"}]}
    assert normalize_slot(item) == ("weapon", None, "shield")


def test_delve_chinese_slot_names_are_normalized():
    assert normalize_slot({"slot": "Unknown", "variants": [{"tooltip_zh_cn": "\n腕部\n锁甲\n"}]}) == ("wrist", "mail", None)
    assert normalize_slot({"slot": "Unknown", "variants": [{"tooltip_zh_cn": "\n手指\n"}]}) == ("ring", None, None)
    assert normalize_slot({"slot": "Unknown", "variants": [{"tooltip_zh_cn": "\n副手物品\n"}]}) == ("weapon", None, "off_hand")
    assert normalize_slot({"slot": "Unknown", "variants": [{"tooltip_zh_cn": "\n单手\n权杖\n"}]}) == ("weapon", None, "1h_mace")


def test_known_tidebound_grotto_items_match_blizzards_complete_loot_table():
    assert TIDEBOUND_GROTTO_ITEM_IDS == {
        268199, 268217, 268221, 268225, 268226, 268232, 268238,
        268244, 268247, 268262, 268263, 268266, 270167,
    }


def test_current_ulatek_item_corrections():
    neck = {"id": 268265, "variants": [{"stats": {"critical_strike": 405}, "sockets": 1, "tooltip_zh_cn": "+\n405暴击\n棱彩插槽\n你的法术和技能有几率使你的爆击提高"}]}
    chest = {"id": 271876, "variants": [{"stats": {"critical_strike": 201}, "tooltip_zh_cn": "+\n201暴击\n使你的爆击提高"}]}
    legs = {"id": 271878, "variants": [{"stats": {"mastery": 201}, "tooltip_zh_cn": "+\n201精通\n使你的精通提高"}]}
    dagger = {"id": 271092, "variants": []}

    for item in (neck, chest, legs, dagger):
        apply_known_item_corrections(item)
        apply_known_item_corrections(item)

    assert neck["variants"][0]["stats"] == {"critical_strike": 101, "haste": 101, "mastery": 101, "versatility": 101}
    assert neck["variants"][0]["sockets"] == 2
    assert chest["variants"][0]["stats"] == {"mastery": 201}
    assert legs["variants"][0]["stats"] == {"critical_strike": 201}
    assert dagger["unique_equipped"] is True
