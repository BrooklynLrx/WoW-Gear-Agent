#!/usr/bin/env python3
"""Build the 12.1 secondary-stat extras catalog."""

import json
from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-consumables.json"

FLASKS = [
    (241326, "Flask of the Shattered Sun", "critical_strike", 165),
    (241324, "Flask of the Blood Knights", "haste", 165),
    (241322, "Flask of the Magisters", "mastery", 165),
    (241320, "Flask of Thalassian Resistance", "versatility", 165),
]

# Each color supplies 16 of its base stat; hybrid cuts add 7 of the named stat.
GEMS = [
    (240904, "Flawless Deadly Garnet", {"critical_strike": 17}, "garnet"),
    (240906, "Flawless Quick Garnet", {"critical_strike": 16, "haste": 7}, "garnet"),
    (240908, "Flawless Masterful Garnet", {"critical_strike": 16, "mastery": 7}, "garnet"),
    (240910, "Flawless Versatile Garnet", {"critical_strike": 16, "versatility": 7}, "garnet"),
    (240888, "Flawless Quick Peridot", {"haste": 17}, "peridot"),
    (240890, "Flawless Deadly Peridot", {"haste": 16, "critical_strike": 7}, "peridot"),
    (240892, "Flawless Masterful Peridot", {"haste": 16, "mastery": 7}, "peridot"),
    (240894, "Flawless Versatile Peridot", {"haste": 16, "versatility": 7}, "peridot"),
    (240896, "Flawless Masterful Amethyst", {"mastery": 17}, "amethyst"),
    (240898, "Flawless Deadly Amethyst", {"mastery": 16, "critical_strike": 7}, "amethyst"),
    (240900, "Flawless Quick Amethyst", {"mastery": 16, "haste": 7}, "amethyst"),
    (240902, "Flawless Versatile Amethyst", {"mastery": 16, "versatility": 7}, "amethyst"),
    (240912, "Flawless Versatile Lapis", {"versatility": 17}, "lapis"),
    (240914, "Flawless Deadly Lapis", {"versatility": 16, "critical_strike": 7}, "lapis"),
    (240916, "Flawless Quick Lapis", {"versatility": 16, "haste": 7}, "lapis"),
    (240918, "Flawless Masterful Lapis", {"versatility": 16, "mastery": 7}, "lapis"),
]

DIAMONDS = [
    (240983, "Indecipherable Eversong Diamond", "+32 primary stat"),
    (240967, "Powerful Eversong Diamond", "+23 primary stat; critical-strike effectiveness per unique gem color"),
    (240971, "Stoic Eversong Diamond", "+23 primary stat and armor"),
    (240969, "Telluric Eversong Diamond", "+23 primary stat; maximum mana per unique gem color"),
]

RING_ENCHANTS = [
    (243987, "Enchant Ring - Nature's Fury", {"critical_strike": 29}),
    (244015, "Enchant Ring - Silvermoon's Alacrity", {"haste": 29}),
    (243959, "Enchant Ring - Zul'jin's Mastery", {"mastery": 29}),
    (244017, "Enchant Ring - Silvermoon's Tenacity", {"versatility": 29}),
]

WEAPON_ENCHANTS = [
    (243973, 1236067, "Enchant Weapon - Berserker's Rage", "proc_haste"),
    (243971, 1236066, "Enchant Weapon - Jan'alai's Precision", "proc_critical_strike"),
    (244031, 1236097, "Enchant Weapon - Arcane Mastery", "proc_mastery"),
    (244029, 1236095, "Enchant Weapon - Acuity of the Ren'dorei", "proc_primary_stat"),
    (243969, 1236065, "Enchant Weapon - Strength of Halazzi", "proc_bleed_damage"),
    (244027, 1236094, "Enchant Weapon - Flames of the Sin'dorei", "proc_fire_damage"),
    (243999, 1236080, "Enchant Weapon - Worldsoul Aegis", "proc_absorb_and_damage"),
    (244001, 1236081, "Enchant Weapon - Worldsoul Tenacity", "proc_versatility_and_absorb"),
    (243997, 1236079, "Enchant Weapon - Worldsoul Cradle", "proc_healing_absorb"),
]


def item(item_id, name, category, stats, included=True, **extra):
    return {
        "id": item_id,
        "name_en": name,
        "name_zh_cn": None,
        "category": category,
        "quality": "gold",
        "secondary_stats": stats,
        "stat_calculation_included": included,
        "wowhead_url": f"https://www.wowhead.com/item={item_id}",
        **extra,
    }


def build():
    old = {}
    if OUT.exists():
        old = {row["id"]: row for row in json.loads(OUT.read_text()).get("items", [])}
    rows = [item(i, n, "flask", {s: v}) for i, n, s, v in FLASKS]
    rows += [item(i, n, "gem", stats, color=color) for i, n, stats, color in GEMS]
    rows += [item(i, n, "unique_diamond", {}, False, unique_equipped_group="thalassian_diamond", effect=e) for i, n, e in DIAMONDS]
    rows += [item(i, n, "ring_enchant", stats, max_equipped=2) for i, n, stats in RING_ENCHANTS]
    rows += [item(i, n, "weapon_enchant", {}, False, spell_id=s, effect_type=e) for i, s, n, e in WEAPON_ENCHANTS]
    for row in rows:
        for key in ("name_zh_cn", "icon"):
            if old.get(row["id"], {}).get(key):
                row[key] = old[row["id"]][key]
    return {
        "patch": "12.1",
        "season": "Midnight Season 2",
        "quality_scope": "Highest quality only",
        "calculation_policy": {
            "include": ["flask secondary ratings", "socketed gem secondary ratings", "permanent ring-enchant secondary ratings"],
            "exclude": ["weapon-enchant effects", "temporary or proc secondary ratings", "non-rating diamond effects"],
        },
        "sources": [
            "https://www.wowhead.com/guide/midnight/professions/jewelcrafting-overview-trainer-locations-recipes-tools",
            "https://www.wow-professions.com/midnight/alchemy-guide",
            "https://www.wow-professions.com/midnight/enchanting-guide",
        ],
        "items": rows,
    }


def main():
    data = build()
    assert len(data["items"]) == 37
    assert sum(row["stat_calculation_included"] for row in data["items"]) == 24
    assert all(not row["stat_calculation_included"] for row in data["items"] if row["category"] == "weapon_enchant")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(data['items'])} records to {OUT}")


if __name__ == "__main__":
    main()
