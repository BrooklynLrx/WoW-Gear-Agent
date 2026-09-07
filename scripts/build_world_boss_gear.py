#!/usr/bin/env python3
"""Merge Blizzard's complete Midnight Season 2 world-boss loot table."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.enrich_items import fetch, save  # noqa: E402
from scripts.prepare_catalog import TIDEBOUND_GROTTO_ITEM_IDS  # noqa: E402


DATA = ROOT / "data" / "12.1-season2-loot.json"
SOURCE_URL = "https://worldofwarcraft.blizzard.com/en-us/news/24295085/step-into-lairs-and-face-the-foes-inside"
ITEMS = {
    268199: ("Tidepiercer's Bubble Popper", "2H Staff"),
    268217: ("Rising Tide Wristguards", "Mail Wrist"),
    268221: ("Tidebound Sorcereress's Robes", "Cloth Chest"),
    268225: ("Coiled Hex Legguards", "Leather Legs"),
    268226: ("Swelling Sea Spaulders", "Plate Shoulders"),
    268232: ("Cincture of the Abyssal Grotto", "Cloth Waist"),
    268238: ("Grips of Swirling Fury", "Mail Hands"),
    268244: ("Forgotten Grotto Girdle", "Plate Waist"),
    268247: ("Breakwater Boots", "Leather Feet"),
    268262: ("Bubblefin Splash Guard", "Shield"),
    268263: ("Frostscale's Mystic Frond", "Off-Hand Weapon"),
    268266: ("Alluring Bubbleband", "Ring"),
    270167: ("Wavecaller's Seastone", "Trinket"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    loot = json.loads(args.data.read_text())
    assert set(ITEMS) == TIDEBOUND_GROTTO_ITEM_IDS
    previous = {item["id"]: item for item in loot["items"]}
    levels = sorted({level for track in loot["upgrade_tracks"].values() for level in track.values()})
    items = []
    for item_id, (name, slot) in ITEMS.items():
        item = previous.get(item_id, {})
        item.update({
            "id": item_id,
            "name_en": name,
            "slot": slot,
            "encounter": "Nymrissa Wavecaller",
            "instance": "Tidebound Grotto",
            "instance_type": "world_boss",
            "wowhead_url": f"https://www.wowhead.com/item={item_id}",
            "source_url": SOURCE_URL,
        })
        item["variants"] = [variant for variant in item.get("variants", []) if "error" not in variant]
        items.append(item)

    by_id = {item["id"]: item for item in items}
    jobs = [
        (item["id"], level)
        for item in items
        for level in levels
        if level not in {variant["item_level"] for variant in item["variants"]}
    ]
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, item_id, level): (item_id, level) for item_id, level in jobs}
        for future in as_completed(futures):
            item_id, level = futures[future]
            try:
                variant, name, icon = future.result()
                by_id[item_id]["name_zh_cn"] = name
                by_id[item_id]["icon"] = icon
                by_id[item_id]["variants"].append(variant)
            except Exception as exc:
                failures += 1
                by_id[item_id]["variants"].append({"item_level": level, "error": str(exc)})

    for item in items:
        item["variants"].sort(key=lambda variant: variant["item_level"])
    loot["items"] = sorted(
        [item for item in loot["items"] if item["id"] not in ITEMS] + items,
        key=lambda item: (item["instance_type"], item["instance"], item.get("encounter") or "", item["slot"], item["name_en"]),
    )
    loot["sources"] = [source for source in loot["sources"] if source.get("type") != "world_boss"] + [{
        "name": "Nymrissa Wavecaller",
        "type": "world_boss",
        "url": SOURCE_URL,
    }]
    save(args.data, loot)
    print(f"merged {len(items)} world-boss items; request failures {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
