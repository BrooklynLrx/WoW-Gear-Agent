#!/usr/bin/env python3
"""Merge the current Midnight Season 2 Delve Hero gear pool into the loot file."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.enrich_items import fetch as fetch_tooltip, save  # noqa: E402


DATA = ROOT / "data" / "12.1-season2-loot.json"
VENDOR_URL = "https://www.wowhead.com/npc=256670/zahran"
HERO_CURRENCY_ID = 3356
HERO_BONUS_START = 12793
UPGRADE_BONUS_IDS = {str(value) for value in range(12785, 12799)}


def fetch_vendor_page() -> str:
    request = urllib.request.Request(VENDOR_URL, headers={"User-Agent": "Mozilla/5.0 wow-gear-data/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def parse_hero_items(page: str) -> list[dict]:
    sells = page.index("id: 'sells'")
    data = page.index("data:", sells) + len("data:")
    rows, _ = json.JSONDecoder().raw_decode(page[data:])

    def costs_hero_currency(row: dict) -> bool:
        return any(currency[0] == HERO_CURRENCY_ID for cost in row.get("cost", []) for currency in cost[1])

    # ponytail: epic gear paid with Untainted Mana-Crystals is the vendor's Hero pool.
    return sorted(
        {row["id"]: row for row in rows if row.get("quality") == 4 and costs_hero_currency(row)}.values(),
        key=lambda row: row["id"],
    )


def hero_bonus_ids(row: dict, rank: int) -> tuple[str, ...]:
    return (str(HERO_BONUS_START + rank - 1), *(bonus for bonus in row.get("bonuses", ()) if bonus not in UPGRADE_BONUS_IDS))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--page", type=Path, help="use a saved Zah'ran page instead of downloading it")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    loot = json.loads(args.data.read_text())
    rows = parse_hero_items(args.page.read_text() if args.page else fetch_vendor_page())
    levels = sorted(loot["upgrade_tracks"]["hero"].values())
    existing_ids = {item["id"] for item in loot["items"] if item.get("instance_type") != "delve"}
    overlap = existing_ids.intersection(row["id"] for row in rows)
    if overlap:
        raise RuntimeError(f"Delve item IDs already exist in another pool: {sorted(overlap)}")

    items = [{
        "id": row["id"],
        "name_en": row.get("displayName") or row["name"],
        "slot": "Unknown",
        "encounter": None,
        "instance": "Midnight Delves",
        "instance_type": "delve",
        "wowhead_url": f"https://www.wowhead.com/item={row['id']}",
        "wowhead_url_zh_cn": f"https://www.wowhead.com/cn/item={row['id']}",
        "source_url": VENDOR_URL,
        "variants": [],
    } for row in rows]

    failures = 0
    by_id = {item["id"]: item for item in items}
    bonuses = {row["id"]: row for row in rows}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {
            pool.submit(fetch_tooltip, item["id"], level, hero_bonus_ids(bonuses[item["id"]], rank)): (item["id"], level)
            for item in items for rank, level in enumerate(levels, 1)
        }
        for index, future in enumerate(as_completed(futures), 1):
            item_id, level = futures[future]
            try:
                variant, name, icon = future.result()
                by_id[item_id]["name_zh_cn"] = name
                by_id[item_id]["icon"] = icon
                by_id[item_id]["variants"].append(variant)
            except Exception as exc:
                failures += 1
                by_id[item_id]["variants"].append({"item_level": level, "error": str(exc)})
            if index % 50 == 0:
                print(f"{index}/{len(futures)}", flush=True)

    for item in items:
        item["variants"].sort(key=lambda row: row["item_level"])
    loot["items"] = sorted(
        [item for item in loot["items"] if item.get("instance_type") != "delve"] + items,
        key=lambda row: (row["instance_type"], row["instance"], row.get("encounter") or "", row["slot"], row["name_en"]),
    )
    loot["scope"] = "Hero 1/6-6/6 and Myth 1/6-6/6; Delves Hero only; optimizer default Myth 6/6"
    loot["sources"] = [source for source in loot["sources"] if source.get("type") != "delve"] + [{
        "name": "Midnight Delves Hero gear",
        "type": "delve",
        "url": VENDOR_URL,
    }]
    save(args.data, loot)
    print(f"merged {len(items)} Delve Hero items; request failures {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
