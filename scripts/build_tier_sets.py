#!/usr/bin/env python3
"""Build Midnight Season 2 tier targets and mark Catalyst source gear."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOOT = ROOT / "data" / "12.1-season2-loot.json"
OUT = ROOT / "data" / "12.1-season2-tier-sets.json"
SLOTS = ("chest", "hands", "head", "legs", "shoulder")
SETS = {
    "warrior": ("plate", "Jade Warlord's Dominion", (271459, 271457, 271456, 271455, 271454)),
    "paladin": ("plate", "Radiance of the Consecrated Flame", (271468, 271466, 271465, 271464, 271463)),
    "hunter": ("mail", "Skulking Viper's Ambush", (271495, 271493, 271492, 271491, 271490)),
    "rogue": ("leather", "Chosen Bloodslayer's Hexweave", (271513, 271511, 271510, 271509, 271508)),
    "priest": ("cloth", "Cosmic Penitent's Raiment", (271558, 271556, 271555, 271554, 271553)),
    "death_knight": ("plate", "Baleful Grave-Knight's Crucible", (271477, 271475, 271474, 271473, 271472)),
    "shaman": ("mail", "Ophidian Oracle's Prophecy", (271486, 271484, 271483, 271482, 271481)),
    "mage": ("cloth", "Primal Leywarden's Attire", (271567, 271565, 271564, 271563, 271562)),
    "warlock": ("cloth", "Damned Necrolyte's Shattered Restraints", (271547, 271546, 271545, 271549, 271544)),
    "monk": ("leather", "Guile of the Monkey King", (271522, 271520, 271519, 271518, 271517)),
    "druid": ("leather", "Bark of the Enigmatic Dreamwatcher", (271531, 271529, 271528, 271527, 271526)),
    "demon_hunter": ("leather", "Abyssal Doomhound's Pursuit", (271540, 271538, 271537, 271536, 271535)),
    "evoker": ("mail", "Echo of Calamity", (271504, 271502, 271501, 271500, 271499)),
}


def main():
    loot = json.loads(LOOT.read_text())
    for item in loot["items"]:
        eligible = item.get("slot_key") in SLOTS
        item["catalyst_eligible"] = eligible
        item["catalyst_tier_bonus_slot"] = eligible
    LOOT.write_text(json.dumps(loot, ensure_ascii=False, indent=2) + "\n")

    old = {}
    if OUT.exists():
        old = {item["id"]: item for row in json.loads(OUT.read_text())["class_sets"] for item in row["items"]}
    class_sets = []
    for class_key, (armor, set_name, ids) in SETS.items():
        items = []
        for slot, item_id in zip(SLOTS, ids):
            previous = old.get(item_id, {})
            items.append({
                **previous,
                "id": item_id,
                "slot_key": slot,
                "name_en": previous.get("name_en"),
                "name_zh_cn": previous.get("name_zh_cn"),
                "icon": previous.get("icon"),
                "wowhead_url": f"https://www.wowhead.com/item={item_id}",
            })
        class_sets.append({"class_key": class_key, "armor_type": armor, "set_name_en": set_name, "items": items})

    data = {
        "patch": "12.1",
        "season": "Midnight Season 2",
        "rules": {
            "eligible_sources": "Season 2 PvE gear of Veteran rank or higher and seasonal PvP gear.",
            "tier_bonus_slots": list(SLOTS),
            "preserves_item_level": True,
            "preserves_upgrade_path": True,
            "preserves_secondary_stats": True,
            "preserves_random_tertiary_stats": True,
            "preserves_supported_cantrip_effects": True,
            "crafted_gear_eligible": False,
            "source_relation": "Match source and target by armor_type and slot_key; the selected source_item_id remains the displayed origin.",
        },
        "sources": [
            "https://www.wowhead.com/news/massive-changes-to-end-game-gearing-in-patch-12-1-raid-item-levels-buffed-and-381915",
            "https://www.icy-veins.com/wow/catalyst-guide",
            "https://github.com/simulationcraft/simc/blob/midnight/engine/dbc/generated/item_set_bonus.inc",
        ],
        "class_sets": class_sets,
    }
    assert len(class_sets) == 13
    assert sum(len(row["items"]) for row in class_sets) == 65
    assert sum(item["catalyst_eligible"] for item in loot["items"]) == 94
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("wrote 13 class sets / 65 targets; marked 94 Catalyst source items")


if __name__ == "__main__":
    main()
