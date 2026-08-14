"""Validate that a 12.1 loadout is equippable before calculating it."""

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from backend.models import GameVersion, Item, ItemVariant, Spec


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "12.1-equipment-rules.json"
SINGLE_SLOTS = {"head", "neck", "shoulders", "back", "chest", "wrist", "gloves", "waist", "legs", "feet"}
DOUBLE_SLOTS = {"finger": 2, "trinket": 2}
SLOT_ALIASES = {"shoulder": "shoulders", "hands": "gloves", "ring": "finger"}


@lru_cache(maxsize=1)
def rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def canonical_slot(slot):
    return SLOT_ALIASES.get(slot, slot)


def weapon_kind(item):
    raw = item.raw_json or {}
    original_slot = (raw.get("slot") or "").lower()
    if raw.get("weapon_type") == "off_hand":
        return "shield" if original_slot == "shield" else "held_in_off_hand"
    return item.weapon_type or raw.get("weapon_type")


def valid_weapon_set(spec_key, weapons):
    return valid_weapon_kinds(spec_key, [weapon_kind(item) for item in weapons])


def valid_weapon_kinds(spec_key, kinds):
    for option in rules()["specs"][spec_key]["weapon_loadouts"]:
        if "two_hand" in option and len(kinds) == 1 and kinds[0] in option["two_hand"]:
            return True
        if "ranged" in option and len(kinds) == 1 and kinds[0] in option["ranged"]:
            return True
        if "dual_wield" in option and len(kinds) == 2:
            allowed = option["dual_wield"]
            if kinds[0] in allowed["main_hand"] and kinds[1] in allowed["off_hand"]:
                return True
        if "main_plus_off_hand" in option and len(kinds) == 2:
            allowed = option["main_plus_off_hand"]
            if kinds[0] in allowed["main_hand"] and kinds[1] in allowed["off_hand"]:
                return True
    return False


def validate_loadout(session, class_key, spec_key, equipment, consumable_ids=(), require_complete=True):
    errors = []
    warnings = []
    full_spec_key = f"{class_key}.{spec_key}"
    spec = session.scalar(select(Spec).join(GameVersion).where(
        Spec.class_key == class_key,
        Spec.spec_key == spec_key,
        GameVersion.is_active.is_(True),
    ))
    if spec is None or full_spec_key not in rules()["specs"]:
        return {"valid": False, "errors": [f"未知职业专精：{full_spec_key}"], "warnings": []}

    class_armor = rules()["classes"][class_key]["armor_type"]
    slot_counts = Counter()
    item_counts = Counter()
    weapons = []
    tier_count = 0
    embellishment_count = 0
    unique_diamonds = 0
    resolved = []

    for index, selected in enumerate(equipment, 1):
        try:
            game_item_id = int(selected["item_id"])
            item_level = int(selected["item_level"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"第{index}件装备缺少有效的 item_id 或 item_level")
            continue
        row = session.execute(
            select(Item, ItemVariant)
            .join(ItemVariant, ItemVariant.item_id == Item.id)
            .where(
                Item.version_id == spec.version_id,
                Item.game_item_id == game_item_id,
                ItemVariant.item_level == item_level,
            )
        ).first()
        if row is None:
            errors.append(f"装备不存在或没有该装等：{game_item_id}@{item_level}")
            continue
        item, variant = row
        raw = item.raw_json or {}
        slot = canonical_slot(item.slot_key)
        slot_counts[slot] += 1
        item_counts[item.game_item_id] += 1
        catalyst_tier_item_id = selected.get("catalyst_tier_item_id")
        if catalyst_tier_item_id:
            tier_item = session.scalar(select(Item).where(
                Item.version_id == spec.version_id,
                Item.game_item_id == int(catalyst_tier_item_id),
            ))
            tier_raw = tier_item.raw_json if tier_item else {}
            if not tier_item or not tier_item.is_tier:
                errors.append(f"无效套装转化目标：{catalyst_tier_item_id}")
            elif tier_raw.get("class_key") != class_key or canonical_slot(tier_item.slot_key) != slot:
                errors.append(f"套装转化目标与职业或部位不匹配：{catalyst_tier_item_id}")
            elif item.is_crafted or not raw.get("catalyst_eligible"):
                errors.append(f"{item.name_zh_cn or item.name_en}不能进行套装转化")
        tier_count += int(item.is_tier or bool(catalyst_tier_item_id))
        embellishment_count += int(bool(raw.get("embellished")))
        if slot == "weapon":
            weapons.append(item)
        if item.armor_type and slot not in {"back"} and item.armor_type != class_armor:
            errors.append(f"{item.name_zh_cn or item.name_en}不是{class_armor}护甲")
        candidate_classes = raw.get("candidate_classes")
        candidate_specs = raw.get("candidate_specs")
        if candidate_classes and class_key not in candidate_classes:
            errors.append(f"{item.name_zh_cn or item.name_en}不适合法师职业" if class_key == "mage" else f"{item.name_zh_cn or item.name_en}不适合{class_key}")
        if candidate_specs and full_spec_key not in candidate_specs:
            errors.append(f"{item.name_zh_cn or item.name_en}不适合{full_spec_key}")
        if item.is_tier and raw.get("class_key") and raw["class_key"] != class_key:
            errors.append(f"{item.name_zh_cn or item.name_en}是其他职业套装")
        unique = bool(raw.get("unique_equipped")) or any(
            "装备唯一" in (v.get("tooltip_zh_cn") or "") for v in raw.get("variants", [])
        )
        if unique and item_counts[item.game_item_id] > 1:
            errors.append(f"唯一装备重复：{item.name_zh_cn or item.name_en}")

        default_sockets = rules()["socket_rules"]["eligible_slots"].get(
            {"finger": "ring"}.get(slot, slot), 0
        )
        max_sockets = max(int(item.max_sockets or 0), int(variant.sockets or 0), int(default_sockets))
        gems = selected.get("gems") or []
        if len(gems) > max_sockets:
            errors.append(f"{item.name_zh_cn or item.name_en}最多允许{max_sockets}个宝石，实际选择{len(gems)}个")
        for gem_id in gems:
            gem = session.scalar(select(Item).where(
                Item.version_id == spec.version_id,
                Item.game_item_id == int(gem_id),
            ))
            gem_raw = gem.raw_json if gem else {}
            if not gem or gem_raw.get("catalog_kind") != "consumable" or gem_raw.get("category") not in {"gem", "unique_diamond"}:
                errors.append(f"无效宝石：{gem_id}")
            elif gem_raw.get("category") == "unique_diamond":
                unique_diamonds += 1
        crafted_stats = selected.get("crafted_secondary_stats") or {}
        if crafted_stats:
            amounts = (variant.raw_json or {}).get("customizable_secondary_amounts") or []
            choices = set(raw.get("secondary_stat_choices") or [])
            if not item.is_crafted or not raw.get("customizable_secondaries"):
                errors.append(f"{item.name_zh_cn or item.name_en}不允许自定义绿字")
            elif set(crafted_stats) - choices or sorted(crafted_stats.values()) != sorted(amounts):
                errors.append(f"{item.name_zh_cn or item.name_en}的制造绿字选择无效")
        resolved.append({
            "item_id": game_item_id, "item_level": item_level, "slot_key": slot,
            "max_sockets": max_sockets, "catalyst_tier_item_id": catalyst_tier_item_id,
        })

    for slot in SINGLE_SLOTS:
        if slot_counts[slot] > 1:
            errors.append(f"{slot}部位超过1件")
    for slot, maximum in DOUBLE_SLOTS.items():
        if slot_counts[slot] > maximum:
            errors.append(f"{slot}部位超过{maximum}件")
    if weapons and not valid_weapon_set(full_spec_key, weapons):
        errors.append("武器组合不符合该专精规则")
    if embellishment_count > 2:
        errors.append(f"美化装备超过2件：当前{embellishment_count}件")
    if unique_diamonds > 1:
        errors.append(f"永歌钻石超过1颗：当前{unique_diamonds}颗")

    consumable_counts = Counter()
    for game_item_id in consumable_ids:
        item = session.scalar(select(Item).where(
            Item.version_id == spec.version_id,
            Item.game_item_id == int(game_item_id),
        ))
        raw = item.raw_json if item else {}
        category = raw.get("category")
        if not item or raw.get("catalog_kind") != "consumable" or category not in {"flask", "ring_enchant", "weapon_enchant"}:
            errors.append(f"无效附加物品：{game_item_id}")
            continue
        consumable_counts[category] += 1
    if consumable_counts["flask"] > 1:
        errors.append("合剂最多选择1个")
    if consumable_counts["ring_enchant"] > 2:
        errors.append("戒指附魔最多选择2个")
    if consumable_counts["weapon_enchant"] > 1:
        errors.append("武器附魔最多选择1个")

    if require_complete:
        for slot in sorted(SINGLE_SLOTS):
            if slot_counts[slot] != 1:
                errors.append(f"缺少{slot}部位")
        for slot, expected in DOUBLE_SLOTS.items():
            if slot_counts[slot] != expected:
                errors.append(f"{slot}部位需要{expected}件，当前{slot_counts[slot]}件")
        if not weapons:
            errors.append("缺少武器")
    elif not equipment:
        warnings.append("当前配装没有装备")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "equipment_count": len(resolved),
            "slot_counts": dict(slot_counts),
            "tier_count": tier_count,
            "embellishment_count": embellishment_count,
            "socketed_gem_count": sum(len(item.get("gems") or []) for item in equipment),
        },
        "equipment": resolved,
    }
