#!/usr/bin/env python3
"""Join parsed BIS rows to the existing zh-CN item catalogs."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_catalog():
    items = []
    for name in ("12.1-season2-loot.json", "12.1-season2-crafted-gear.json"):
        items += json.loads((ROOT / "data" / name).read_text())["items"]
    tiers = json.loads((ROOT / "data/12.1-season2-tier-sets.json").read_text())
    for class_set in tiers["class_sets"]:
        items += class_set["items"]
    return {item["id"]: item for item in items}


def main():
    source, target = map(Path, sys.argv[1:3])
    data = json.loads(source.read_text())
    catalog = load_catalog()
    for row in data["items"]:
        item = catalog.get(row.get("item_id"))
        row["name_zh_cn"] = item.get("name_zh_cn") if item else None
        row["icon"] = item.get("icon") if item else None
        row["localization_status"] = "matched_by_item_id" if item else "unmatched"
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
