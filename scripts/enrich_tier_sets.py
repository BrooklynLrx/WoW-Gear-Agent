#!/usr/bin/env python3
"""Add localized names and icons to the Season 2 tier targets."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from enrich_items import fetch, save


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-tier-sets.json"


def main():
    data = json.loads(DATA.read_text())
    items = [item for row in data["class_sets"] for item in row["items"]]
    levels = (305, 308, 311, 315, 318, 321, 324, 328, 331, 334)
    jobs_to_run = []
    for item in items:
        done = {variant["item_level"] for variant in item.get("variants", []) if "error" not in variant}
        jobs_to_run.extend((item, level) for level in levels if level not in done)
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(fetch, item["id"], level): (item, level) for item, level in jobs_to_run}
        for index, future in enumerate(as_completed(jobs), 1):
            item, level = jobs[future]
            variant, name, icon = future.result()
            item["name_zh_cn"], item["icon"] = name, icon
            item["variants"] = sorted(
                [row for row in item.get("variants", []) if row["item_level"] != level] + [variant],
                key=lambda row: row["item_level"],
            )
            if index % 25 == 0:
                save(DATA, data)
                print(f"{index}/{len(jobs)}", flush=True)
    assert all(item["name_zh_cn"] and item["icon"] for item in items)
    assert all(len(item["variants"]) == len(levels) for item in items)
    save(DATA, data)
    print(f"enriched {len(items)} tier targets across {len(levels)} item levels")


if __name__ == "__main__":
    main()
