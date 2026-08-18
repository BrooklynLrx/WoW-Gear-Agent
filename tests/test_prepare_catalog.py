from scripts.prepare_catalog import TIDEBOUND_GROTTO_ITEM_IDS, normalize_slot


def test_shield_is_not_classified_as_a_caster_off_hand():
    item = {"slot": "Shield", "variants": [{"tooltip_zh_cn": "\n副手\n盾\n"}]}
    assert normalize_slot(item) == ("weapon", None, "shield")


def test_known_tidebound_grotto_items_include_alluring_bubbleband():
    assert 268266 in TIDEBOUND_GROTTO_ITEM_IDS
