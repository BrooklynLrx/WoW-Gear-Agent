#!/usr/bin/env python3
"""Add zh-CN names and exact item-level tooltips to the collected loot file."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "12.1-season2-loot.json"
ENDPOINT = "https://nether.wowhead.com/tooltip/item/{item_id}?dataEnv=1&locale=4&ilvl={ilvl}"
STAT_IDS = {"3": "agility", "4": "strength", "5": "intellect", "7": "stamina"}
RATING_IDS = {
    "24": "random_stat_1", "25": "random_stat_2",
    "32": "critical_strike", "36": "haste", "40": "versatility", "49": "mastery",
}
HYBRID_STATS = {
    "敏捷 or 智力": "agility_or_intellect",
    "力量 or 智力": "strength_or_intellect",
    "敏捷 or 力量": "agility_or_strength",
    "敏捷 or 力量 or 智力": "agility_or_strength_or_intellect",
}


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def clean_tooltip(raw: str) -> str:
    parser = Text()
    parser.feed(raw)
    return "\n".join(parser.parts).replace("\x08", "")


def fetch(item_id: int, ilvl: int) -> dict:
    request = urllib.request.Request(ENDPOINT.format(item_id=item_id, ilvl=ilvl), headers={"User-Agent": "wow-gear-data/0.1"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            raw = payload["tooltip"]
            # ponytail: everything after the item-stat block is effect text; never count proc ratings.
            stat_raw = raw.split("<!--eistats-->", 1)[0]
            stats: dict[str, int] = {}
            for stat_id, value in re.findall(r"<!--stat(\d+)-->\+?([\d,]+)", stat_raw):
                if stat_id in STAT_IDS:
                    stats[STAT_IDS[stat_id]] = int(value.replace(",", ""))
            for value, label in re.findall(r"<!--stat\d+-->\+?([\d,]+) \[([^\]]+)]", stat_raw):
                if label in HYBRID_STATS:
                    stats[HYBRID_STATS[label]] = int(value.replace(",", ""))
            for rating_id, value in re.findall(r"<!--rtg(\d+)-->([\d,]+)", stat_raw):
                if rating_id in RATING_IDS:
                    stats[RATING_IDS[rating_id]] = int(value.replace(",", ""))
            return {
                "item_level": ilvl,
                "quality": payload.get("quality"),
                "stats": stats,
                "sockets": raw.count("棱彩插槽"),
                "tooltip_zh_cn": clean_tooltip(html.unescape(raw)),
            }, payload["name"], payload.get("icon")
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            if attempt == 4:
                raise RuntimeError(str(exc)) from exc
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--levels", choices=("max", "all"), default="max")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.data.read_text())
    levels = [334] if args.levels == "max" else sorted({value for track in data["upgrade_tracks"].values() for value in track.values()})
    jobs = []
    for item in data["items"]:
        item["wowhead_url_zh_cn"] = f"https://www.wowhead.com/cn/item={item['id']}"
        done = set() if args.refresh else {variant["item_level"] for variant in item.get("variants", []) if "error" not in variant}
        jobs.extend((item["id"], level) for level in levels if level not in done)

    by_id = {item["id"]: item for item in data["items"]}
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch, item_id, level): (item_id, level) for item_id, level in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            item_id, level = futures[future]
            item = by_id[item_id]
            variants = [variant for variant in item.get("variants", []) if variant["item_level"] != level]
            try:
                variant, name, icon = future.result()
                item["name_zh_cn"] = name
                item["icon"] = icon
                variants.append(variant)
            except Exception as exc:
                failures += 1
                variants.append({"item_level": level, "error": str(exc)})
            item["variants"] = sorted(variants, key=lambda variant: variant["item_level"])
            # ponytail: JSON checkpointing is enough for this small, occasional batch.
            if index % 20 == 0:
                save(args.data, data)
                print(f"{index}/{len(jobs)}", flush=True)
    save(args.data, data)
    localized = sum(bool(item.get("name_zh_cn")) for item in data["items"])
    print(f"localized {localized}/{len(data['items'])}; request failures {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
