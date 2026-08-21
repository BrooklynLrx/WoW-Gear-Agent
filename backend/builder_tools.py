"""Functions registered as tools for the equipment Builder agent."""

from sqlalchemy import select

from backend.db import SessionLocal
from backend.loadout_validator import (
    canonical_slot, item_is_available_for_spec, rules, validate_loadout,
    weapon_kind, weapon_kind_available, weapon_kind_available_in_position,
)
from backend.models import GameVersion, Item, ItemSource, ItemVariant, Spec
from backend.stat_calculator import calculate_equipment


# 12.1 M7/M8的cantrip装备。特效不折算成绿字，但配装时保留其装备价值。
M7_M8_SPECIAL_EFFECT_ITEM_IDS = {
    268209, 268213,
    268202, 268207, 268215, 268265,
    271092, 271093, 271874, 271875, 271876, 271878,
}


def display_slot_key(slot, item):
    """Keep weapon legality grouped while exposing off-hands to the UI."""
    return "off_hand" if slot == "weapon" and weapon_kind(item) in {"held_in_off_hand", "shield"} else slot


def calculate_stats(
    class_key: str,
    spec_key: str,
    equipment: list[dict],
    consumable_ids: list[int] | None = None,
    require_complete: bool = True,
) -> dict:
    """Validate a WoW 12.1 loadout and return its static secondary ratings and sheet percentages.

    Args:
        class_key: English class key, for example ``mage``.
        spec_key: English specialization key, for example ``arcane``.
        equipment: Items shaped as ``{"item_id": 123, "item_level": 334, "gems": [240906]}``.
        consumable_ids: Selected flask, ring-enchant and weapon-enchant item IDs.
        require_complete: Require every armor, jewelry, trinket and weapon slot.
    """
    consumable_ids = consumable_ids or []
    with SessionLocal() as session:
        validation = validate_loadout(
            session, class_key, spec_key, equipment, consumable_ids, require_complete
        )
        if not validation["valid"]:
            return {
                "success": False,
                "error": "invalid_loadout",
                "validation": validation,
            }
        calculation = calculate_equipment(
            session, class_key, spec_key, equipment, consumable_ids
        )
    return {
        "success": True,
        "patch": "12.1",
        "validation": validation,
        "calculation": calculation,
        "policy": {
            "base_critical_strike_percent": 5,
            "base_mastery_percent": 8,
            "mastery_formula": "(8 + rating-derived mastery percent) * spec coefficient",
            "excluded": ["talent stats", "temporary item procs", "weapon enchant effects"],
        },
    }


def _weapon_is_available(full_spec_key, item):
    return weapon_kind_available(full_spec_key, item)


def search_items_for_spec(
    class_key: str,
    spec_key: str,
    slot_key: str | None = None,
    item_level: int = 334,
    name: str | None = None,
    game_item_id: int | None = None,
    limit: int = 20,
    crafted_only: bool = False,
    weapon_kind_key: str | None = None,
) -> dict:
    """Search only items equippable by one fixed specialization."""
    full_spec_key = f"{class_key}.{spec_key}"
    wanted_slot = canonical_slot(slot_key) if slot_key else None
    limit = max(1, min(int(limit), 500))
    with SessionLocal() as session:
        spec = session.scalar(select(Spec).join(GameVersion).where(
            Spec.class_key == class_key,
            Spec.spec_key == spec_key,
            GameVersion.is_active.is_(True),
        ))
        if spec is None:
            return {"success": False, "error": "unknown_spec"}
        rows = session.execute(
            select(Item, ItemVariant)
            .join(ItemVariant, ItemVariant.item_id == Item.id)
            .where(Item.version_id == spec.version_id)
            .order_by(Item.name_zh_cn, Item.game_item_id, ItemVariant.item_level.desc())
        ).all()
        source_rows = session.execute(
            select(ItemSource).join(Item).where(Item.version_id == spec.version_id)
        ).scalars().all()
        source_map = {}
        for source in source_rows:
            source_map.setdefault(source.item_id, []).append({
                "source_type": source.source_type,
                "instance_name_zh_cn": source.instance_name_zh_cn,
                "encounter_name_zh_cn": source.encounter_name_zh_cn,
            })

        results = []
        seen = set()
        for item, variant in rows:
            raw = item.raw_json or {}
            catalog_kind = raw.get("catalog_kind")
            slot = canonical_slot(item.slot_key)
            if item.id in seen or catalog_kind in {"consumable", "bis_placeholder"}:
                continue
            if crafted_only and not item.is_crafted:
                continue
            if game_item_id is not None and item.game_item_id != int(game_item_id):
                continue
            if slot in {"unknown", "tier_token"}:
                continue
            if name and name.lower() not in (item.name_en or "").lower() and name not in (item.name_zh_cn or ""):
                continue
            display_slot = display_slot_key(slot, item)
            if wanted_slot == "off_hand" and not weapon_kind_available_in_position(full_spec_key, item, "off_hand"):
                continue
            if wanted_slot and wanted_slot != "off_hand" and slot != wanted_slot:
                continue
            if not item_is_available_for_spec(class_key, spec_key, item):
                continue
            if weapon_kind_key and weapon_kind(item) != weapon_kind_key:
                continue

            requested_level = item_level
            if item.is_crafted and item_level == 334:
                requested_level = int(raw.get("default_optimizer_item_level", 331))
            if variant.item_level != requested_level:
                continue
            seen.add(item.id)
            stats = {
                key: int(getattr(variant, key))
                for key in ("critical_strike", "haste", "mastery", "versatility")
            }
            socket_slot = "ring" if slot == "finger" else slot
            default_sockets = rules()["socket_rules"]["eligible_slots"].get(socket_slot, 0)
            sources = source_map.get(item.id, [])
            encounters = {source.get("encounter_name_zh_cn") for source in sources}
            is_final_boss_drop = "乌拉特克" in encounters
            is_penultimate_boss_drop = "盘卷祭坛" in encounters
            is_late_raid_special_effect = slot != "trinket" and item.game_item_id in M7_M8_SPECIAL_EFFECT_ITEM_IDS
            is_raid_boe = bool(raw.get("bind_on_equip") and any(source.get("source_type") == "raid" for source in sources))
            results.append({
                "item_id": item.game_item_id,
                "name_zh_cn": item.name_zh_cn,
                "name_en": item.name_en,
                "icon": item.icon,
                "icon_url": f"https://wow.zamimg.com/images/wow/icons/large/{item.icon}.jpg" if item.icon else None,
                "wowhead_url": f"https://www.wowhead.com/cn/item={item.game_item_id}&ilvl={variant.item_level}",
                "wowhead_data": f"item={item.game_item_id}&domain=cn&ilvl={variant.item_level}",
                "slot_key": slot,
                "display_slot_key": display_slot,
                "item_level": variant.item_level,
                "stats": stats,
                "current_sockets": variant.sockets,
                "maximum_user_selected_sockets": max(item.max_sockets, variant.sockets, default_sockets),
                "socket_policy_zh_cn": "仅用户实际选择的宝石计入绿字；最大值不代表装备自带孔。",
                "is_crafted": item.is_crafted,
                "is_tier": item.is_tier,
                "catalyst_eligible": bool(raw.get("catalyst_eligible")),
                "tier_acquisition_note_zh_cn": "套装由符合条件的胚子转化，实际来源取决于胚子。" if item.is_tier else None,
                "is_embellished": bool(raw.get("embellished")),
                "has_special_effect": item.has_special_effect or is_late_raid_special_effect,
                "is_late_raid_special_effect": is_late_raid_special_effect,
                "is_raid_boe": is_raid_boe,
                "is_penultimate_boss_drop": is_penultimate_boss_drop,
                "is_final_boss_drop": is_final_boss_drop,
                "acquisition_difficulty_zh_cn": (
                    "M8乌拉特克尾王掉落，获取难度高" if is_final_boss_drop else
                    "M7盘卷祭坛掉落，获取难度较高" if is_penultimate_boss_drop else None
                ),
                "is_unique_equipped": bool(raw.get("unique_equipped")) or any(
                    "装备唯一" in (value.get("tooltip_zh_cn") or "")
                    for value in raw.get("variants", [])
                ),
                "weapon_kind": weapon_kind(item) if slot == "weapon" else None,
                "customizable_secondaries": bool(raw.get("customizable_secondaries")),
                "secondary_stat_choices": raw.get("secondary_stat_choices") or [],
                "customizable_secondary_amounts": (variant.raw_json or {}).get("customizable_secondary_amounts"),
                "sources": sources,
            })
            if len(results) >= limit:
                break
    return {
        "success": True,
        "spec": full_spec_key,
        "requested_item_level": item_level,
        "count": len(results),
        "items": results,
    }
