#!/usr/bin/env python3
"""Fetch exact 12.1.5 variants, retaining historical gear and item levels."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.enrich_items import fetch, save

RAID_URL = "https://www.wowhead.com/guide/midnight/raids/the-unbinding-of-kithix-boss-strategy-abilities-rewards"
UPGRADE_URL = "https://www.wowhead.com/ptr/guide/midnight/bonus-rolls-item-upgrades"
ARMOR_SLOTS = {"head", "shoulder", "chest", "wrist", "hands", "waist", "legs", "feet"}
MYTH_REWARD_SLOTS = ARMOR_SLOTS | {"back", "ring", "neck"}
DELVE_OFFHAND_IDS = {249672, 249676, 272275, 272276}
RAID = {
    280799: ("Lu'selama, Light's Justice", "2H Sword"),
    281056: ("Sanctified Knight's Phoenixblade", "1H Sword"),
    281239: ("Corroded Hulk's Skullcap", "Plate Helm"),
    281238: ("Aberrant Commander's Gauntlets", "Mail Hands"),
    281236: ("Chestwrap of Palpable Terror", "Leather Chest"),
    281235: ("Voidweaver's Leggings", "Cloth Legs"),
    281029: ("Band of the Swarmcaller", "Ring"),
    280617: ("Lightbearer's Shield Fragment", "Trinket"),
    280835: ("Sigil of the Impending Eclipse", "Trinket"),
    281215: ("Twisted Horror's Tendril", "Trinket"),
}


def main():
    paths = [ROOT / "data" / name for name in ("12.1-season2-loot.json", "12.1-season2-crafted-gear.json")]
    loot, crafted = [json.loads(path.read_text()) for path in paths]
    ids = {item["id"] for item in loot["items"]}
    for item_id, (name, slot) in RAID.items():
        if item_id not in ids:
            loot["items"].append({
                "id": item_id, "name_en": name, "slot": slot,
                "instance": "The Unbinding of Kith'ix", "instance_type": "raid",
                "encounter": "Kith'ix", "source_url": RAID_URL,
                "wowhead_url": f"https://www.wowhead.com/item={item_id}",
                "variants": [], "effect_stat_policy": "count_static_item_stats_only",
            })
    jobs = []
    for catalog, is_crafted in ((loot, False), (crafted, True)):
        for item in catalog["items"]:
            levels = {v["item_level"] for v in item.get("variants", []) if "error" not in v}
            slot = item.get("slot_key")
            if item.get("instance_type") == "delve":
                item["default_optimizer_item_level"] = 321
            if item["id"] in RAID:
                item["catalyst_eligible"] = item["slot"] in {"Plate Helm", "Mail Hands", "Leather Chest", "Cloth Legs"}
                levels.update({305, 308, 311, 315, 318, 321, 324, 328, 331, 334})
                slot = "weapon" if "Sword" in item["slot"] else "trinket" if item["slot"] == "Trinket" else slot
            delve_offhand = item.get("instance_type") == "delve" and item["id"] in DELVE_OFFHAND_IDS
            if item.get("instance_type") == "delve" and (slot in MYTH_REWARD_SLOTS or delve_offhand):
                levels.add(334)
                item["default_optimizer_item_level"] = 334
                item["myth_reward_source"] = "https://www.wowhead.com/npc=256670/zahran" if delve_offhand else "https://www.wowhead.com/item=285044/venerated-loa-armament"
            if slot in {"weapon", "neck", "trinket"} and (331 if is_crafted else 334) in levels:
                target = 338 if is_crafted else 340
                item["default_optimizer_item_level"] = target
                item["ascendant_upgrade_source"] = UPGRADE_URL
                levels.add(target)
            done = {v["item_level"] for v in item.get("variants", []) if "error" not in v}
            for level in levels - done:
                bonuses = ("12806",) if level == 334 else ()
                jobs.append((item, level, bonuses))
    # ponytail: keep the existing bounded tooltip fetcher; save only after every request succeeds.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, item["id"], level, bonuses): (item, level) for item, level, bonuses in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            item, level = futures[future]
            variant, name, icon = future.result()
            text = variant["tooltip_zh_cn"]
            if f"物品等级：\n{level}\n" not in text:
                raise ValueError(f"wrong tooltip level: {item['id']} / {level}")
            random = [variant["stats"].pop(key) for key in ("random_stat_1", "random_stat_2") if key in variant["stats"]]
            if random:
                variant["customizable_secondary_amounts"] = random
            item["name_zh_cn"], item["icon"] = name, icon
            item["variants"] = [v for v in item.get("variants", []) if v["item_level"] != level] + [variant]
            if index % 25 == 0:
                print(f"{index}/{len(jobs)}", flush=True)
    for path, catalog in zip(paths, (loot, crafted)):
        for item in catalog["items"]:
            item["variants"].sort(key=lambda v: v["item_level"])
        catalog["content_patch"] = "12.1.5"
        if catalog is loot:
            catalog["scope"] = "Hero/Myth tracks; Delve armor, cloak and ring default Myth 6/6 334; Delve neck and off-hand default Ascendant Myth 340; other Delve weapons/trinkets remain Hero 6/6 321"
        save(path, catalog)
    print(f"fetched {len(jobs)} variants; run scripts/prepare_catalog.py and scripts/import_data.py next")


if __name__ == "__main__":
    main()
