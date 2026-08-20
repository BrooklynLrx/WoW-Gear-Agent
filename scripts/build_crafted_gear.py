#!/usr/bin/env python3
"""Build the 12.1 Season 2 custom-stat crafted gear catalog."""

import json
from pathlib import Path


OUT = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-crafted-gear.json"
SOURCE = "https://www.wowhead.com/guide/professions/overview"

# ponytail: crafted secondaries are dynamic, so store one recipe template instead of six stat-pair copies.
SETS = {
    "tailoring": [
        (239656, "Adherent's Silken Shroud", "back", None),
        (239648, "Martyr's Bindings", "wrist", "cloth"),
        (239652, "Martyr's Crown", "head", "cloth"),
        (239653, "Martyr's Gloves", "hands", "cloth"),
        (239651, "Martyr's Leggings", "legs", "cloth"),
        (239650, "Martyr's Mantle", "shoulder", "cloth"),
        (239654, "Martyr's Slippers", "feet", "cloth"),
        (239655, "Martyr's Vestments", "chest", "cloth"),
        (239649, "Martyr's Waistwrap", "waist", "cloth"),
    ],
    "leatherworking": [
        (244570, "Silvermoon Agent's Coat", "chest", "leather"),
        (244571, "Silvermoon Agent's Cover", "head", "leather"),
        (244576, "Silvermoon Agent's Deflectors", "wrist", "leather"),
        (244575, "Silvermoon Agent's Handwraps", "hands", "leather"),
        (244574, "Silvermoon Agent's Leggings", "legs", "leather"),
        (244572, "Silvermoon Agent's Mantle", "shoulder", "leather"),
        (244569, "Silvermoon Agent's Sneakers", "feet", "leather"),
        (244573, "Silvermoon Agent's Utility Belt", "waist", "leather"),
        (244580, "Farstrider's Brilliant Plumes", "shoulder", "mail"),
        (244584, "Farstrider's Plated Bracers", "wrist", "mail"),
        (244577, "Farstrider's Razor Talons", "feet", "mail"),
        (244582, "Farstrider's Reinforced Faulds", "legs", "mail"),
        (244578, "Farstrider's Scouting Vest", "chest", "mail"),
        (244583, "Farstrider's Sharpened Claws", "hands", "mail"),
        (244581, "Farstrider's Trophy Belt", "waist", "mail"),
        (244579, "Farstrider's Unwavering Visage", "head", "mail"),
    ],
    "blacksmithing": [
        (237834, "Spellbreaker's Bracers", "wrist", "plate"),
        (237832, "Spellbreaker's Cover", "head", "plate"),
        (237830, "Spellbreaker's Girdle", "waist", "plate"),
        (237833, "Spellbreaker's Legguards", "legs", "plate"),
        (237835, "Spellbreaker's Mantle", "shoulder", "plate"),
        (237828, "Spellbreaker's March", "feet", "plate"),
        (237831, "Spellbreaker's Rebuke", "weapon", "shield"),
        (237836, "Spellbreaker's Resolve", "hands", "plate"),
        (237829, "Spellbreaker's Shelter", "chest", "plate"),
        (237850, "Farstrider's Chopper", "weapon", "1h_axe"),
        (237837, "Farstrider's Mercy", "weapon", "1h_dagger"),
        (237839, "Spellbreaker's Blade", "weapon", "1h_sword"),
        (237841, "Spellbreaker's Ultimatum", "weapon", "1h_mace"),
        (237840, "Spellbreaker's Warglaive", "weapon", "1h_warglaive"),
    ],
    "inscription": [
        (245770, "Aln'hara Cane", "weapon", "2h_staff"),
        (245769, "Aln'hara Lantern", "weapon", "off_hand"),
        (245771, "Aln'hara Pikestaff", "weapon", "2h_staff"),
        (265337, "Aln'hara Sprigshot", "weapon", "ranged_bow"),
    ],
    "jewelcrafting": [
        (240949, "Masterwork Sin'dorei Band", "ring", None),
        (240950, "Masterwork Sin'dorei Amulet", "neck", None),
    ],
}

EMBELLISHED = {
    "alchemy": [(241340, "Magister's Alchemist Stone", "trinket", None)],
    "blacksmithing": [
        (244472, "Knight-Commander's Palisade", "weapon", "shield"),
        (244463, "Murder Row Fleet Feet", "feet", "plate"),
        (244679, "Murder Row Fishhook", "weapon", "1h_dagger"),
    ],
    "inscription": [
        (246305, "Darkmoon Dominion: Blood", "trinket", None),
        (246304, "Darkmoon Dominion: Hunt", "trinket", None),
        (246306, "Darkmoon Dominion: Rot", "trinket", None),
        (246307, "Darkmoon Dominion: Void", "trinket", None),
    ],
    "jewelcrafting": [
        (251513, "Loa Worshiper's Band", "ring", None),
        (241140, "Signet of Azerothian Blessings", "ring", None),
        (241139, "Thalassian Phoenix Torque", "neck", None),
        (251073, "Voidstone Shielding Array", "neck", None),
    ],
    "leatherworking": [
        (244606, "Hexwoven Strand", "waist", "leather"),
        (244612, "Row Walker's Deflectors", "wrist", "leather"),
        (244613, "Row Walker's Insurance", "chest", "leather"),
        (244614, "Row Walker's Swiftgrips", "hands", "leather"),
        (244601, "World Tree Rootwraps", "feet", "leather"),
        (244605, "Axe-Flingin' Bands", "wrist", "mail"),
        (244602, "Ranger-General's Grips", "hands", "mail"),
        (244611, "World Tender's Barkclasp", "waist", "mail"),
        (244610, "World Tender's Rootslippers", "feet", "mail"),
        (244609, "World Tender's Trunkplate", "chest", "mail"),
    ],
    "tailoring": [
        (239660, "Arcanoweave Bracers", "wrist", "cloth"),
        (239661, "Arcanoweave Cloak", "back", None),
        (239664, "Arcanoweave Cord", "waist", "cloth"),
        (239662, "Arcanoweave Treads", "feet", "cloth"),
        (239657, "Sunfire Bracers", "wrist", "cloth"),
        (239658, "Sunfire Cloak", "back", None),
        (239663, "Sunfire Sash", "waist", "cloth"),
        (239659, "Sunfire Treads", "feet", "cloth"),
    ],
}


def build():
    spec_catalog = json.loads((OUT.parent / "12.1-season2-loot.json").read_text())["spec_catalog"]
    equipment_specs = json.loads((OUT.parent / "12.1-equipment-rules.json").read_text())["specs"]
    tracks = {
        "spark_of_tides": {"quality_1": 292, "quality_2": 296, "quality_3": 299, "quality_4": 302, "quality_5": 305},
        "hero_mistcrest": {"quality_1": 305, "quality_2": 309, "quality_3": 312, "quality_4": 315, "quality_5": 318},
        "myth_mistcrest": {"quality_1": 318, "quality_2": 322, "quality_3": 325, "quality_4": 328, "quality_5": 331},
    }
    old = {}
    if OUT.exists():
        old = {item["id"]: item for item in json.loads(OUT.read_text()).get("items", [])}
    items = []
    for profession, rows in SETS.items():
        for item_id, name, slot, armor_or_weapon in rows:
            item = {
                "id": item_id,
                "name_en": name,
                "name_zh_cn": None,
                "profession": profession,
                "slot_key": slot,
                "armor_type": armor_or_weapon if armor_or_weapon in {"cloth", "leather", "mail", "plate"} else None,
                "weapon_type": armor_or_weapon if slot == "weapon" else None,
                "customizable_secondaries": True,
                "secondary_stat_choices": ["critical_strike", "haste", "mastery", "versatility"],
                "secondary_stats_selected": 2,
                "embellished": False,
                "catalyst_eligible": False,
                "item_levels": tracks,
                "default_optimizer_item_level": 331,
                "spark_of_tides_cost": 4 if armor_or_weapon in {"2h_staff", "ranged_bow"} else 2,
                "wowhead_url": f"https://www.wowhead.com/item={item_id}",
            }
            for key in ("name_zh_cn", "icon", "variants", "secondary_stat_mode", "customizable_secondaries", "secondary_stat_choices", "secondary_stats_selected"):
                if old.get(item_id, {}).get(key) is not None:
                    item[key] = old[item_id][key]
            item["sockets"] = 1 if slot in {"ring", "neck"} else 0
            item["unique_equipped"] = item_id == 240949
            item["effect_stat_policy"] = "count_static_item_stats_only"
            item["static_secondary_stats_included"] = True
            item["triggered_secondary_stats_included"] = False
            items.append(item)
    for profession, rows in EMBELLISHED.items():
        for item_id, name, slot, armor_or_weapon in rows:
            item = {
                "id": item_id,
                "name_en": name,
                "name_zh_cn": old.get(item_id, {}).get("name_zh_cn"),
                "profession": profession,
                "slot_key": slot,
                "armor_type": armor_or_weapon if armor_or_weapon in {"cloth", "leather", "mail", "plate"} else None,
                "weapon_type": armor_or_weapon if slot == "weapon" else None,
                "customizable_secondaries": slot not in {"trinket", "ring", "neck"},
                "secondary_stat_choices": ["critical_strike", "haste", "mastery", "versatility"] if slot not in {"trinket", "ring", "neck"} else [],
                "secondary_stats_selected": 2 if slot not in {"trinket", "ring", "neck"} else 0,
                "embellished": True,
                "embellishment_limit": 2,
                "effect_stat_policy": "count_static_item_stats_only",
                "static_secondary_stats_included": True,
                "triggered_secondary_stats_included": False,
                "catalyst_eligible": False,
                "item_levels": tracks,
                "default_optimizer_item_level": 331,
                "spark_of_tides_cost": 4 if armor_or_weapon in {"2h_staff", "ranged_bow"} else 2,
                "sockets": 1 if slot in {"ring", "neck"} else 0,
                "unique_equipped": slot in {"ring", "neck"},
                "wowhead_url": f"https://www.wowhead.com/item={item_id}",
            }
            for key in ("icon", "variants", "secondary_stat_mode", "customizable_secondaries", "secondary_stat_choices", "secondary_stats_selected"):
                if old.get(item_id, {}).get(key) is not None:
                    item[key] = old[item_id][key]
            items.append(item)
    for item in items:
        if not item["weapon_type"]:
            continue
        stats = item["variants"][-1]["stats"]
        primaries = {
            value
            for key in stats
            for value in key.split("_or_")
            if value in {"strength", "agility", "intellect"}
        }
        weapon_kind = "held_in_off_hand" if item["weapon_type"] == "off_hand" else item["weapon_type"]
        item["candidate_specs"] = [
            spec_key
            for spec_key, spec in spec_catalog.items()
            if spec["primary_stat"] in primaries and any(
                weapon_kind in kinds
                for option in equipment_specs[spec_key]["weapon_loadouts"]
                for rule in option.values()
                for kinds in (rule.values() if isinstance(rule, dict) else [rule])
            )
        ]
        item["candidate_classes"] = sorted({spec_catalog[key]["class"] for key in item["candidate_specs"]})
    return {
        "patch": "12.1",
        "season": "Midnight Season 2",
        "scope": "Endgame crafted combat gear; inherent effects recorded but not valued",
        "rules": {
            "crafting_quality_ranks": 5,
            "crafted_items_use_standard_upgrade_tracks": False,
            "optimizer_default": "myth_mistcrest quality_5 (331)",
            "crafted_max_is_below_myth_6_6_by_item_levels": 3,
            "secondary_stats": "Choose one of six two-stat pairs with a Thalassian combat missive.",
            "custom_secondary_distribution": "The two selected ratings receive the two values in variants[].customizable_secondary_amounts; current recipes split them equally.",
            "recrafting": "Can change quality/item level, chosen secondary pair, and optional reagents.",
            "catalyst": "Crafted gear is not eligible for tier conversion.",
            "effect_items": "Always include item level, primary stats, secondary stats and sockets; effect value is currently zero/unknown.",
        },
        "catalyst_rules_for_convertible_dropped_gear": {
            "preserves_item_level_and_upgrade_track": True,
            "inherits_secondary_stats": True,
            "inherits_tertiary_stats": True,
            "inherits_certain_cantrip_effects": True,
            "tier_stats_need_separate_variants": False,
        },
        "item_icon_assets": {
            "stored_field": "icon",
            "development_url_template": "https://wow.zamimg.com/images/wow/icons/large/{icon}.jpg",
            "production_policy": "Cache these icons under the site's own static assets during deployment.",
        },
        "crafting_item_levels": tracks,
        "sources": [
            SOURCE,
            "https://www.wowhead.com/ptr/currency=3445/hero-mistcrest",
            "https://www.wowhead.com/ptr/currency=3446/myth-mistcrest",
            "https://www.wowhead.com/news/full-patch-12-1-curse-of-ulatek-ptr-development-notes-381914",
        ],
        "items": sorted(items, key=lambda x: (x["profession"], x["slot_key"], x["name_en"])),
    }


def main():
    data = build()
    assert len(data["items"]) == 75
    assert data["crafting_item_levels"]["spark_of_tides"] == {
        "quality_1": 292, "quality_2": 296, "quality_3": 299, "quality_4": 302, "quality_5": 305
    }
    assert data["crafting_item_levels"]["hero_mistcrest"]["quality_5"] == 318
    assert data["crafting_item_levels"]["myth_mistcrest"]["quality_5"] == 331
    assert all(not item["catalyst_eligible"] for item in data["items"])
    assert sum(item["embellished"] for item in data["items"]) == 30
    custom_variants = [
        variant
        for item in data["items"] if item["customizable_secondaries"]
        for variant in item.get("variants", [])
    ]
    assert len(custom_variants) == 432
    assert all(len(v["customizable_secondary_amounts"]) == 2 for v in custom_variants)
    assert all(v["customizable_secondary_amounts"][0] == v["customizable_secondary_amounts"][1] for v in custom_variants)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(data['items'])} crafted templates to {OUT}")


if __name__ == "__main__":
    main()
