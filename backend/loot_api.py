"""Read-only catalog queries used by the first web UI."""

from sqlalchemy import select

from backend.builder_tools import M7_M8_SPECIAL_EFFECT_ITEM_IDS, display_slot_key
from backend.db import SessionLocal
from backend.loadout_validator import canonical_slot, item_is_available_for_spec, rules, weapon_kind_available_in_position
from backend.models import GameVersion, Item, ItemSource, ItemVariant, Spec


SECONDARIES = ("critical_strike", "haste", "mastery", "versatility")


def list_specs():
    with SessionLocal() as db:
        rows = db.scalars(
            select(Spec).join(GameVersion).where(GameVersion.is_active.is_(True))
            .order_by(Spec.class_name_zh_cn, Spec.spec_name_zh_cn)
        ).all()
        return [{
            "key": f"{row.class_key}.{row.spec_key}",
            "class_key": row.class_key,
            "spec_key": row.spec_key,
            "class_name_zh_cn": row.class_name_zh_cn,
            "spec_name_zh_cn": row.spec_name_zh_cn,
            "role": row.role,
        } for row in rows]


def list_instances():
    with SessionLocal() as db:
        rows = db.execute(
            select(ItemSource.source_type, ItemSource.instance_name_zh_cn)
            .where(ItemSource.instance_name_zh_cn.is_not(None)).distinct()
            .order_by(ItemSource.source_type, ItemSource.instance_name_zh_cn)
        ).all()
        return [{"source_type": kind, "name_zh_cn": name} for kind, name in rows]


def search_loot(
    *, item_level=334, class_key=None, spec_key=None, slot_key=None,
    source_type=None, instance_name=None, secondary_stats=(), secondary_match="all",
    has_special_effect=None, q=None, item_ids=(), limit=100, offset=0,
):
    with SessionLocal() as db:
        version = db.scalar(select(GameVersion).where(GameVersion.is_active.is_(True)))
        if version is None:
            return {"items": [], "count": 0, "limit": limit, "offset": offset}
        rows = db.execute(
            select(Item, ItemVariant).join(ItemVariant).where(
                Item.version_id == version.id,
                ItemVariant.item_level == item_level,
            ).order_by(Item.name_zh_cn, Item.game_item_id)
        ).all()
        sources = db.scalars(select(ItemSource).join(Item).where(Item.version_id == version.id)).all()
        source_map = {}
        for value in sources:
            source_map.setdefault(value.item_id, []).append({
                "source_type": value.source_type,
                "instance_name_zh_cn": value.instance_name_zh_cn,
                "encounter_name_zh_cn": value.encounter_name_zh_cn,
            })

        wanted_slot = canonical_slot(slot_key) if slot_key else None
        wanted_stats = {value for value in secondary_stats if value in SECONDARIES}
        wanted_ids = {int(value) for value in item_ids}
        results = []
        for item, variant in rows:
            raw = item.raw_json or {}
            slot = canonical_slot(item.slot_key)
            item_sources = source_map.get(item.id, [])
            if raw.get("catalog_kind") in {"consumable", "bis_placeholder"} or slot in {"unknown", "tier_token"}:
                continue
            if wanted_ids and item.game_item_id not in wanted_ids:
                continue
            display_slot = display_slot_key(slot, item)
            if wanted_slot and (display_slot if wanted_slot == "off_hand" else slot) != wanted_slot:
                continue
            if source_type and not any(value["source_type"] == source_type for value in item_sources):
                continue
            if instance_name and not any(value["instance_name_zh_cn"] == instance_name for value in item_sources):
                continue
            if q and q.lower() not in (item.name_en or "").lower() and q not in (item.name_zh_cn or ""):
                continue
            if class_key and spec_key and not item_is_available_for_spec(class_key, spec_key, item):
                continue
            stats = {name: int(getattr(variant, name) or 0) for name in SECONDARIES}
            present = {name for name, value in stats.items() if value > 0}
            if wanted_stats and (not wanted_stats.issubset(present) if secondary_match == "all" else not wanted_stats.intersection(present)):
                continue
            special = bool(slot == "trinket" or item.has_special_effect or item.game_item_id in M7_M8_SPECIAL_EFFECT_ITEM_IDS)
            if has_special_effect is not None and special != has_special_effect:
                continue
            results.append({
                "item_id": item.game_item_id,
                "name_zh_cn": item.name_zh_cn,
                "name_en": item.name_en,
                "icon": item.icon,
                "icon_url": f"https://wow.zamimg.com/images/wow/icons/large/{item.icon}.jpg" if item.icon else None,
                "slot_key": slot,
                "display_slot_key": display_slot,
                "weapon_type": item.weapon_type or raw.get("weapon_type"),
                "can_equip_off_hand": bool(
                    class_key and spec_key and slot == "weapon" and
                    weapon_kind_available_in_position(f"{class_key}.{spec_key}", item, "off_hand")
                ),
                "item_level": variant.item_level,
                "stats": stats,
                "current_sockets": int(variant.sockets or 0),
                "maximum_user_selected_sockets": max(
                    int(item.max_sockets or 0),
                    int(variant.sockets or 0),
                    int(rules()["socket_rules"]["eligible_slots"].get("ring" if slot == "finger" else slot, 0)),
                ),
                "has_special_effect": special,
                "is_crafted": item.is_crafted,
                "catalyst_eligible": bool(raw.get("catalyst_eligible")),
                "sources": item_sources,
                "wowhead_url": f"https://www.wowhead.com/cn/item={item.game_item_id}&ilvl={variant.item_level}",
                "wowhead_data": f"item={item.game_item_id}&domain=cn&ilvl={variant.item_level}",
            })
        page = results[offset:offset + limit]
        return {"items": page, "count": len(results), "limit": limit, "offset": offset}
