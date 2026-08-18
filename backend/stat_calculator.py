"""Deterministic level-90 secondary-stat calculator for WoW 12.1."""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from backend.models import GameVersion, Item, ItemVariant, Spec


RATING_PER_PERCENT = {
    "critical_strike": Decimal("46"),
    "haste": Decimal("44"),
    "mastery": Decimal("46"),
    "versatility": Decimal("54"),
}
BASE_PERCENT = {
    "critical_strike": Decimal("5"),
    "haste": Decimal("0"),
    "mastery": Decimal("8"),
    "versatility": Decimal("0"),
}
DR_BANDS = (
    (Decimal("30"), Decimal("1.0")),
    (Decimal("39"), Decimal("0.9")),
    (Decimal("47"), Decimal("0.8")),
    (Decimal("54"), Decimal("0.7")),
    (Decimal("66"), Decimal("0.6")),
    (Decimal("126"), Decimal("0.5")),
)
STATS = tuple(RATING_PER_PERCENT)
def item_static_stats(variant, primary_stat):
    """Return the stats shown on the item for this spec, including hybrid primaries."""
    raw = (variant.raw_json or {}).get("stats") or {}
    primary = int(raw.get(primary_stat, getattr(variant, primary_stat, 0)) or 0)
    primary += sum(
        int(value or 0)
        for key, value in raw.items()
        if "_or_" in key and primary_stat in key.split("_or_")
    )
    return {
        "primary_stat": primary_stat,
        "primary_stat_value": primary,
        "stamina": int(raw.get("stamina", variant.stamina) or 0),
        # ponytail: armor is null until the source catalog contains an exact value.
        "armor": int(raw["armor"]) if raw.get("armor") is not None else None,
    }


def _round(value):
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apply_diminishing_returns(raw_percent):
    """Convert rating-derived raw percent to effective percent."""
    remaining = max(Decimal(str(raw_percent)), Decimal("0"))
    effective = Decimal("0")
    lower = Decimal("0")
    for upper, multiplier in DR_BANDS:
        width = upper - lower
        used = min(remaining, width)
        effective += used * multiplier
        remaining -= used
        if remaining <= 0:
            return effective
        lower = upper
    return effective + remaining * DR_BANDS[-1][1]


def reverse_diminishing_returns(effective_percent):
    """Convert an effective rating-derived percent target back to raw percent."""
    remaining = max(Decimal(str(effective_percent)), Decimal("0"))
    raw = Decimal("0")
    lower = Decimal("0")
    for upper, multiplier in DR_BANDS:
        raw_width = upper - lower
        effective_width = raw_width * multiplier
        used = min(remaining, effective_width)
        raw += used / multiplier
        remaining -= used
        if remaining <= 0:
            return raw
        lower = upper
    return raw + remaining / DR_BANDS[-1][1]


def calculate_percentages(ratings, mastery_coefficient):
    """Return character-sheet percentages from static secondary ratings."""
    coefficient = Decimal(str(mastery_coefficient))
    normalized = {stat: int(ratings.get(stat, 0) or 0) for stat in STATS}
    derived = {
        stat: apply_diminishing_returns(Decimal(value) / RATING_PER_PERCENT[stat])
        for stat, value in normalized.items()
    }
    return {
        "ratings": normalized,
        "percentages": {
            "critical_strike": _round(BASE_PERCENT["critical_strike"] + derived["critical_strike"]),
            "haste": _round(derived["haste"]),
            # 基础8%先与绿字精通相加，再乘专精系数。
            "mastery": _round((BASE_PERCENT["mastery"] + derived["mastery"]) * coefficient),
            "versatility": _round(derived["versatility"]),
        },
        "mastery_coefficient": float(coefficient),
        "base_percentages": {key: float(value) for key, value in BASE_PERCENT.items()},
    }


def rating_for_percentage(stat, target_percent, mastery_coefficient=1):
    """Return the approximate rating required for a character-sheet target."""
    target = Decimal(str(target_percent))
    if stat == "mastery":
        effective = target / Decimal(str(mastery_coefficient)) - BASE_PERCENT["mastery"]
    else:
        effective = target - BASE_PERCENT[stat]
    raw = reverse_diminishing_returns(max(effective, Decimal("0")))
    return int((raw * RATING_PER_PERCENT[stat]).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_equipment(session, class_key, spec_key, equipment, consumable_ids=()):
    """Calculate equipment plus selected static-rating supplements."""
    spec = session.scalar(select(Spec).join(GameVersion).where(
        Spec.class_key == class_key,
        Spec.spec_key == spec_key,
        GameVersion.is_active.is_(True),
    ))
    if spec is None:
        raise ValueError(f"unknown spec: {class_key}.{spec_key}")
    if spec.mastery_coefficient is None:
        raise ValueError(f"missing mastery coefficient: {class_key}.{spec_key}")

    primary_stat = (spec.rules_json or {}).get("primary_stat") or "intellect"
    totals = {stat: 0 for stat in STATS}
    primary_totals = {
        "primary_stat": primary_stat,
        "primary_stat_value": 0,
        "stamina": 0,
        "armor": 0,
        "armor_complete": True,
    }
    resolved = []
    for selected in equipment:
        row = session.execute(
            select(Item, ItemVariant)
            .join(ItemVariant, ItemVariant.item_id == Item.id)
            .where(
                Item.game_item_id == int(selected["item_id"]),
                ItemVariant.item_level == int(selected["item_level"]),
                Item.version_id == spec.version_id,
            )
        ).first()
        if row is None:
            raise ValueError(f"item variant not found: {selected['item_id']}@{selected['item_level']}")
        item, variant = row
        static_stats = item_static_stats(variant, primary_stat)
        primary_totals["primary_stat_value"] += static_stats["primary_stat_value"]
        primary_totals["stamina"] += static_stats["stamina"]
        if static_stats["armor"] is None:
            if item.armor_type:
                primary_totals["armor_complete"] = False
        else:
            primary_totals["armor"] += static_stats["armor"]
        crafted_stats = selected.get("crafted_secondary_stats") or {}
        stats = {stat: int(getattr(variant, stat)) + int(crafted_stats.get(stat, 0)) for stat in STATS}
        for stat, value in stats.items():
            totals[stat] += value
        resolved.append({
            "item_id": item.game_item_id,
            "item_level": variant.item_level,
            "name_zh_cn": item.name_zh_cn,
            "slot_key": item.slot_key,
            "stats": stats,
            "static_stats": static_stats,
            "crafted_secondary_stats": crafted_stats,
            "catalyst_tier_item_id": selected.get("catalyst_tier_item_id"),
        })

    supplements = []
    counts = {}
    allowed_categories = {"gem", "unique_diamond", "flask", "ring_enchant", "weapon_enchant"}
    supplement_ids = [gem_id for selected in equipment for gem_id in (selected.get("gems") or [])]
    supplement_ids.extend(consumable_ids)
    for game_item_id in supplement_ids:
        item = session.scalar(select(Item).where(
            Item.version_id == spec.version_id,
            Item.game_item_id == int(game_item_id),
        ))
        raw = item.raw_json if item else None
        if not raw or raw.get("catalog_kind") != "consumable":
            raise ValueError(f"consumable not found: {game_item_id}")
        category = raw.get("category")
        if category not in allowed_categories:
            raise ValueError(f"invalid supplement category: {game_item_id}")
        counts[game_item_id] = counts.get(game_item_id, 0) + 1
        max_equipped = int(raw.get("max_equipped", 1 if category == "flask" else 99))
        if counts[game_item_id] > max_equipped:
            raise ValueError(f"too many copies of consumable: {game_item_id}")
        stats = {stat: int((raw.get("secondary_stats") or {}).get(stat, 0) or 0) for stat in STATS}
        included = bool(raw.get("stat_calculation_included"))
        if included:
            for stat, value in stats.items():
                totals[stat] += value
        supplements.append({
            "item_id": item.game_item_id,
            "name_zh_cn": item.name_zh_cn,
            "category": category,
            "stats": stats,
            "included_in_secondary_stats": included,
        })

    result = calculate_percentages(totals, spec.mastery_coefficient)
    result.update({
        "spec": f"{class_key}.{spec_key}",
        "spec_name_zh_cn": f"{spec.class_name_zh_cn}·{spec.spec_name_zh_cn}",
        "equipment": resolved,
        "supplements": supplements,
        "equipment_totals": primary_totals,
    })
    return result
