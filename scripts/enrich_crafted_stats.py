#!/usr/bin/env python3
"""Add exact Hero/Myth crafting-quality stats to crafted gear."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from enrich_items import fetch, save


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-crafted-gear.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.data.read_text())
    levels = sorted({
        *data["crafting_item_levels"]["hero_mistcrest"].values(),
        *data["crafting_item_levels"]["myth_mistcrest"].values(),
    })
    by_id = {item["id"]: item for item in data["items"]}
    jobs = []
    for item in data["items"]:
        done = set() if args.refresh else {v["item_level"] for v in item.get("variants", []) if "error" not in v}
        jobs.extend((item["id"], level) for level in levels if level not in done)

    failures = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch, item_id, level): (item_id, level) for item_id, level in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            item_id, level = futures[future]
            item = by_id[item_id]
            variants = [v for v in item.get("variants", []) if v["item_level"] != level]
            try:
                variant, name, icon = future.result()
                random_stats = [variant["stats"].pop(key) for key in ("random_stat_1", "random_stat_2") if key in variant["stats"]]
                if random_stats:
                    variant["customizable_secondary_amounts"] = random_stats
                item["name_zh_cn"], item["icon"] = name, icon
                variants.append(variant)
            except Exception as exc:
                failures += 1
                variants.append({"item_level": level, "error": str(exc)})
            item["variants"] = sorted(variants, key=lambda v: v["item_level"])
            if index % 25 == 0:
                save(args.data, data)
                print(f"{index}/{len(jobs)}", flush=True)

    for item in data["items"]:
        successful = [v for v in item.get("variants", []) if "error" not in v]
        item["customizable_secondaries"] = any(v.get("customizable_secondary_amounts") for v in successful)
        item["secondary_stat_mode"] = "customizable" if item["customizable_secondaries"] else "fixed"
        item["secondary_stat_choices"] = ["critical_strike", "haste", "mastery", "versatility"] if item["customizable_secondaries"] else []
        item["secondary_stats_selected"] = 2 if item["customizable_secondaries"] else 0
    save(args.data, data)
    print(f"items {len(data['items'])}; levels {levels}; failures {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
