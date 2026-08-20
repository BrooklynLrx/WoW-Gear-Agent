from scripts.prepare_catalog import TIDEBOUND_GROTTO_ITEM_IDS, apply_known_item_corrections, normalize_slot


def test_shield_is_not_classified_as_a_caster_off_hand():
    item = {"slot": "Shield", "variants": [{"tooltip_zh_cn": "\n副手\n盾\n"}]}
    assert normalize_slot(item) == ("weapon", None, "shield")


def test_known_tidebound_grotto_items_include_alluring_bubbleband():
    assert 268266 in TIDEBOUND_GROTTO_ITEM_IDS


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
