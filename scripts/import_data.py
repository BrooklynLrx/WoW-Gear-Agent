#!/usr/bin/env python3
"""Import the curated 12.1 JSON catalogs into MySQL."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.db import SessionLocal
from backend.models import (
    BisItem,
    BisProfile,
    GameVersion,
    Item,
    ItemSource,
    ItemVariant,
    Spec,
    StatRecommendation,
)


DATA = ROOT / "data"
FILES = {
    "loot": DATA / "12.1-season2-loot.json",
    "crafted": DATA / "12.1-season2-crafted-gear.json",
    "tier": DATA / "12.1-season2-tier-sets.json",
    "consumables": DATA / "12.1-season2-consumables.json",
    "conversions": DATA / "12.1-secondary-stat-conversions.json",
    "recommendations": DATA / "12.1-stat-recommendations.json",
    "bis": DATA / "12.1-wowhead-bis.json",
}

STAT_COLUMNS = (
    "strength", "agility", "intellect", "stamina",
    "critical_strike", "haste", "mastery", "versatility",
)


def read_json(name):
    return json.loads(FILES[name].read_text(encoding="utf-8"))


def normalize_key(value):
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_slot(value):
    value = normalize_key(value).replace("main_hand", "weapon").replace("mainhand", "weapon")
    value = value.replace("off_hand", "off_hand").replace("offhand", "off_hand")
    aliases = {
        "helm": "head", "shoulder": "shoulders", "cape": "back", "cloak": "back",
        "bracers": "wrist", "hands": "gloves", "belt": "waist", "boots": "feet",
        "ring": "finger", "ring_1": "finger", "ring_2": "finger",
        "1h_weapon": "weapon", "2h_weapon": "weapon", "weapon_(2h)": "weapon",
        "weapons_(1h)": "weapon", "trinkets": "trinket",
    }
    value = value.split("_(", 1)[0]
    return aliases.get(value, value or "unknown")


def stat_values(stats):
    stats = stats or {}
    return {name: int(stats.get(name, 0) or 0) for name in STAT_COLUMNS}


def upsert_item(session, version_id, data, *, kind, is_crafted=False, is_tier=False):
    game_item_id = int(data["id"])
    item = session.scalar(select(Item).where(
        Item.version_id == version_id,
        Item.game_item_id == game_item_id,
    ))
    if item is None:
        item = Item(version_id=version_id, game_item_id=game_item_id, slot_key="unknown")
        session.add(item)

    variants = data.get("variants") or []
    item.name_en = data.get("name_en") or item.name_en
    item.name_zh_cn = data.get("name_zh_cn") or item.name_zh_cn
    item.slot_key = normalize_slot(data.get("slot_key") or data.get("slot"))
    item.armor_type = data.get("armor_type")
    item.weapon_type = data.get("weapon_type")
    item.icon = data.get("icon") or item.icon
    item.max_sockets = max([int(data.get("sockets", 0) or 0)] + [int(v.get("sockets", 0) or 0) for v in variants])
    item.is_crafted = is_crafted
    item.is_tier = is_tier
    item.has_special_effect = bool(data.get("effect_stat_policy"))
    item.raw_json = {"catalog_kind": kind, **data}
    session.flush()

    for variant_data in variants:
        level = int(variant_data["item_level"])
        variant = session.scalar(select(ItemVariant).where(
            ItemVariant.item_id == item.id,
            ItemVariant.item_level == level,
        ))
        if variant is None:
            variant = ItemVariant(item_id=item.id, item_level=level)
            session.add(variant)
        for name, value in stat_values(variant_data.get("stats")).items():
            setattr(variant, name, value)
        variant.sockets = int(variant_data.get("sockets", 0) or 0)
        variant.raw_json = variant_data
    return item


def ensure_bis_item(session, version_id, data):
    game_item_id = int(data["item_id"])
    item = session.scalar(select(Item).where(
        Item.version_id == version_id,
        Item.game_item_id == game_item_id,
    ))
    if item is not None:
        return item
    item = Item(
        version_id=version_id,
        game_item_id=game_item_id,
        name_en=data.get("item_en"),
        name_zh_cn=data.get("item_zh_cn"),
        slot_key=normalize_slot(data.get("slot_en")),
        icon=data.get("icon"),
        raw_json={"catalog_kind": "bis_placeholder", **data},
    )
    session.add(item)
    session.flush()
    return item


def import_all(session):
    loot = read_json("loot")
    crafted = read_json("crafted")
    tier = read_json("tier")
    consumables = read_json("consumables")
    conversions = read_json("conversions")
    recommendations = read_json("recommendations")
    bis = read_json("bis")

    version = session.scalar(select(GameVersion).where(GameVersion.patch == "12.1"))
    if version is None:
        version = GameVersion(patch="12.1", season="Midnight Season 2")
        session.add(version)
    version.season = loot.get("season") or "Midnight Season 2"
    version.is_active = True
    version.imported_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.flush()

    conversions_by_name = {
        (row["class_zh_cn"], row["spec_zh_cn"]): row for row in conversions["specs"]
    }
    spec_by_key = {}
    for full_key, data in loot["spec_catalog"].items():
        class_key, spec_key = full_key.split(".", 1)
        spec = session.scalar(select(Spec).where(
            Spec.version_id == version.id,
            Spec.class_key == class_key,
            Spec.spec_key == spec_key,
        ))
        if spec is None:
            spec = Spec(version_id=version.id, class_key=class_key, spec_key=spec_key)
            session.add(spec)
        class_zh = loot["class_catalog"][class_key]["name_zh_cn"]
        conversion = conversions_by_name.get((class_zh, data["name_zh_cn"]), {})
        spec.class_name_zh_cn = class_zh
        spec.spec_name_zh_cn = data["name_zh_cn"]
        spec.role = data.get("role")
        spec.mastery_coefficient = conversion.get("primary_effect_percent_per_mastery_point")
        spec.rules_json = {
            "primary_stat": data.get("primary_stat"),
            "base_critical_strike_percent": 5,
            "base_mastery_points": 8,
            "mastery": conversion,
        }
        session.flush()
        spec_by_key[full_key] = spec

    item_ids = []
    for data in loot["items"]:
        item = upsert_item(session, version.id, data, kind="drop")
        item_ids.append(item.id)
    for data in crafted["items"]:
        item = upsert_item(session, version.id, data, kind="crafted", is_crafted=True)
        item_ids.append(item.id)
    for class_set in tier["class_sets"]:
        for data in class_set["items"]:
            enriched = {
                "class_key": class_set.get("class_key"),
                "armor_type": class_set.get("armor_type"),
                **data,
            }
            item = upsert_item(session, version.id, enriched, kind="tier", is_tier=True)
            item_ids.append(item.id)
    for data in consumables["items"]:
        enriched = {**data, "slot_key": f"consumable_{data.get('category', 'other')}"}
        item = upsert_item(session, version.id, enriched, kind="consumable")
        item_ids.append(item.id)

    session.execute(delete(ItemSource).where(ItemSource.item_id.in_(item_ids)))
    for data in loot["items"]:
        item = session.scalar(select(Item).where(
            Item.version_id == version.id, Item.game_item_id == int(data["id"])
        ))
        sources = data.get("drop_sources") or [{
            "instance": data.get("instance"), "instance_zh_cn": data.get("instance_zh_cn"),
            "encounter": data.get("encounter"), "encounter_zh_cn": data.get("encounter_zh_cn"),
            "source_url": data.get("source_url"),
        }]
        for source in sources:
            session.add(ItemSource(
                item_id=item.id,
                source_type=data.get("instance_type") or "drop",
                instance_name_en=source.get("instance"),
                instance_name_zh_cn=source.get("instance_zh_cn"),
                encounter_name_en=source.get("encounter"),
                encounter_name_zh_cn=source.get("encounter_zh_cn"),
                source_url=source.get("source_url"),
            ))

    session.execute(delete(StatRecommendation).where(
        StatRecommendation.spec_id.in_([spec.id for spec in spec_by_key.values()])
    ))
    for data in recommendations["profiles"]:
        spec = spec_by_key.get(data["spec"])
        if spec is None:
            continue
        target_type = data.get("hero_talent") or "default"
        for content_type, value_key, flag_key in (
            ("raid", "raid_single_target", "is_top_recommended_raid"),
            ("mythic_plus", "mythic_plus", "is_top_recommended_mythic_plus"),
        ):
            if value_key not in data and f"{content_type}_percent_targets" not in data:
                continue
            session.add(StatRecommendation(
                spec_id=spec.id,
                content_type=content_type,
                target_type=target_type,
                values_json={"ratio": data.get(value_key), "profile": data},
                is_recommended_spec=bool(data.get(flag_key)),
                source_url=(data.get("source") or {}).get("url"),
                source_note=data.get("notes_zh_cn") or data.get("rating_threshold_notes_zh_cn"),
            ))

    session.execute(delete(BisProfile).where(
        BisProfile.spec_id.in_([spec.id for spec in spec_by_key.values()])
    ))
    for profile_data in bis["profiles"]:
        full_key = f"{normalize_key(profile_data['class'])}.{normalize_key(profile_data['spec'])}"
        spec = spec_by_key.get(full_key)
        if spec is None:
            continue
        for variant_data in profile_data["variants"]:
            profile = BisProfile(
                spec_id=spec.id,
                content_type="overall",
                source_url=profile_data["source_url"],
                source_updated=profile_data.get("source_updated"),
                variant_index=int(variant_data.get("variant_index", 1)),
            )
            session.add(profile)
            session.flush()
            positions = {}
            for data in variant_data["items"]:
                item = ensure_bis_item(session, version.id, data)
                slot = normalize_slot(data.get("slot_en"))
                positions[slot] = positions.get(slot, 0) + 1
                session.add(BisItem(
                    profile_id=profile.id,
                    item_id=item.id,
                    slot_key=slot,
                    position=positions[slot],
                    source_text=data.get("source_zh_cn") or data.get("source_en"),
                ))

    session.flush()
    return {
        "versions": session.scalar(select(func.count()).select_from(GameVersion)),
        "specs": session.scalar(select(func.count()).select_from(Spec).where(Spec.version_id == version.id)),
        "items": session.scalar(select(func.count()).select_from(Item).where(Item.version_id == version.id)),
        "variants": session.scalar(select(func.count()).select_from(ItemVariant).join(Item).where(Item.version_id == version.id)),
        "sources": session.scalar(select(func.count()).select_from(ItemSource).join(Item).where(Item.version_id == version.id)),
        "recommendations": session.scalar(select(func.count()).select_from(StatRecommendation).join(Spec).where(Spec.version_id == version.id)),
        "bis_profiles": session.scalar(select(func.count()).select_from(BisProfile).join(Spec).where(Spec.version_id == version.id)),
        "bis_items": session.scalar(select(func.count()).select_from(BisItem).join(BisProfile).join(Spec).where(Spec.version_id == version.id)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Roll back after validating the import")
    args = parser.parse_args()
    with SessionLocal() as session:
        counts = import_all(session)
        assert counts["specs"] == 40
        assert counts["bis_profiles"] == 42
        assert counts["bis_items"] == 666
        session.rollback() if args.check else session.commit()
    print(json.dumps({"mode": "check" if args.check else "import", **counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
