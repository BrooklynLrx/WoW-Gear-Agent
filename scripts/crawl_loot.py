#!/usr/bin/env python3
"""Collect Midnight Season 2 dungeon/raid loot from Wowhead guide pages."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "12.1-season2-loot.json"
JINA = "https://r.jina.ai/https://www.wowhead.com/"
RANKS = {
    "hero": {"1/6": 305, "2/6": 308, "3/6": 311, "4/6": 315, "5/6": 318, "6/6": 321},
    "myth": {"1/6": 318, "2/6": 321, "3/6": 324, "4/6": 328, "5/6": 331, "6/6": 334},
}

DUNGEONS = {
    "Altar of Fangs": "guide/midnight/altar-of-fangs-dungeon-overview-location-rewards",
    "Murder Row": "guide/midnight/murder-row-dungeon-overview-location-rewards",
    "Den of Nalorakk": "guide/midnight/den-of-nalorakk-dungeon-overview-location-rewards",
    "The Blinding Vale": "guide/midnight/the-blinding-vale-dungeon-overview-location-rewards",
    "Voidscar Arena": "guide/midnight/voidscar-arena-dungeon-overview-location-rewards",
    "Ruby Life Pools": "guide/midnight/ruby-life-pools-dungeon-overview-mythic-plus",
    "Temple of Sethraliss": "guide/midnight/temple-of-sethraliss-dungeon-overview-mythic-plus",
    "King's Rest": "guide/midnight/kings-rest-dungeon-overview-mythic-plus",
}

RAID_BOSSES = {
    "Nek'zali the Soulcoiler": "nekzali-the-soulcoiler",
    "Entombed Sentinels": "entombed-sentinels",
    "Vashnik the Malignant": "vashnik-the-malignant",
    "The Lost Explorers": "lost-explorers",
    "Sszorak": "sszorak",
    "The Twin Fangs": "twin-fangs",
    "The Coiled Altar": "coiled-altar",
    "Ula'tek": "ulatek",
}

ITEM_RE = re.compile(
    r"^\[!\[Image \d+: (?P<alt>[^\]]+)\]\([^)]+\)(?P<name>[^\]]+)\]"
    r"\(https://www\.wowhead\.com/(?:ptr/)?item=(?P<id>\d+)(?:/[^?)]*)?(?:\?[^)]*)?\)(?P<tail>.*)$"
)
STAT_RE = re.compile(r"\+([\d,]+) (Strength|Agility|Intellect|Stamina|Armor|Critical Strike|Haste|Mastery|Versatility)\b")
SLOTS = sorted(
    [
        "Cloth Shoulder", "Leather Shoulder", "Mail Shoulder", "Plate Shoulder",
        "Cloth Shoulders", "Leather Shoulders", "Mail Shoulders", "Plate Shoulders",
        "Cloth Wrist", "Leather Wrist", "Mail Wrist", "Plate Wrist",
        "Cloth Hands", "Leather Hands", "Mail Hands", "Plate Hands",
        "Cloth Chest", "Leather Chest", "Mail Chest", "Plate Chest",
        "Cloth Waist", "Leather Waist", "Mail Waist", "Plate Waist",
        "Cloth Legs", "Leather Legs", "Mail Legs", "Plate Legs",
        "Cloth Feet", "Leather Feet", "Mail Feet", "Plate Feet",
        "Cloth Helm", "Leather Helm", "Mail Helm", "Plate Helm",
        "Cloth Tier Set Token - Shoulders", "Leather Tier Set Token - Shoulders",
        "Mail Tier Set Token - Shoulders", "Plate Tier Set Token - Shoulders",
        "Cloth Tier Set Token - Chest", "Leather Tier Set Token - Chest",
        "Mail Tier Set Token - Chest", "Plate Tier Set Token - Chest",
        "Cloth Tier Set Token - Hands", "Leather Tier Set Token - Hands",
        "Mail Tier Set Token - Hands", "Plate Tier Set Token - Hands",
        "Cloth Tier Set Token - Legs", "Leather Tier Set Token - Legs",
        "Mail Tier Set Token - Legs", "Plate Tier Set Token - Legs",
        "Cloth Tier Set Token - Helm", "Leather Tier Set Token - Helm",
        "Mail Tier Set Token - Helm", "Plate Tier Set Token - Helm",
        "Curio Tier Set Token", "1H Warglaive", "1H Fist Weapon", "1H Dagger",
        "1H Mace", "1H Sword", "1H Axe", "2H Polearm", "2H Staff", "2H Sword",
        "2H Axe", "Ranged Crossbow", "Ranged Gun", "Ranged Bow", "Shield",
        "Off-Hand Weapon", "Trinket", "Neck", "Ring", "Back",
    ],
    key=len,
    reverse=True,
)


def fetch(path: str) -> str:
    req = urllib.request.Request(JINA + path, headers={"User-Agent": "wow-gear-data/0.1"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
    raise last_error or RuntimeError("fetch failed")


def split_tail(tail: str, raid_boss: str | None) -> tuple[str, str | None]:
    for slot in SLOTS:
        if tail.startswith(slot):
            encounter = raid_boss or tail[len(slot):].strip() or None
            return slot, encounter
    return tail.strip() or "Unknown", raid_boss


def parse_items(page: str, instance: str, kind: str, source_path: str, boss: str | None = None) -> list[dict]:
    if kind == "dungeon":
        start = page.find("## All Gear Drops")
        end_markers = ("At the end of a Mythic+ dungeon", "## All Rewards")
    else:
        start = page.find("### Gear")
        end_markers = ("### More Rewards",)
    if start < 0:
        raise ValueError(f"loot heading not found: {instance} {boss or ''}")
    end = min((page.find(marker, start) for marker in end_markers if page.find(marker, start) >= 0), default=len(page))

    found: list[dict] = []
    for line in page[start:end].splitlines():
        match = ITEM_RE.match(line)
        if not match:
            continue
        slot, encounter = split_tail(match.group("tail"), boss)
        found.append({
            "id": int(match.group("id")),
            "name_en": match.group("name"),
            "slot": slot,
            "encounter": encounter,
            "instance": instance,
            "instance_type": kind,
            "wowhead_url": f"https://www.wowhead.com/ptr/item={match.group('id')}",
            "source_url": "https://www.wowhead.com/" + source_path,
        })
    if not found:
        raise ValueError(f"no items parsed: {instance} {boss or ''}")
    return found


def tooltip_variant(item_id: int, ilvl: int) -> dict:
    page = ""
    for attempt in range(4):
        try:
            page = fetch(f"ptr/item={item_id}?ilvl={ilvl}")
            break
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    tooltip = next((line for line in page.splitlines() if f"Item Level {ilvl}" in line and line.startswith("| **")), "")
    if not tooltip:
        return {"item_level": ilvl, "error": "tooltip not found"}
    stats = {name.lower().replace(" ", "_"): int(value.replace(",", "")) for value, name in STAT_RE.findall(tooltip)}
    return {
        "item_level": ilvl,
        "stats": stats,
        "sockets": tooltip.count("Prismatic Socket"),
        "tooltip": tooltip.removeprefix("| ").removesuffix(" |"),
    }


def collect(stats_mode: str) -> dict:
    items: list[dict] = []
    errors: list[str] = []
    sources: list[dict] = []

    source_jobs = [
        (instance, "dungeon", path, None) for instance, path in DUNGEONS.items()
    ] + [
        ("The Venomous Abyss", "raid", f"ptr/guide/midnight/raids/venomous-abyss-{slug}-boss-strategy-abilities", boss)
        for boss, slug in RAID_BOSSES.items()
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch, path): (instance, kind, path, boss) for instance, kind, path, boss in source_jobs}
        for future in as_completed(futures):
            instance, kind, path, boss = futures[future]
            label = boss or instance
            try:
                items.extend(parse_items(future.result(), instance, kind, path, boss))
                sources.append({"name": label, "type": "raid_boss" if boss else "dungeon", "url": "https://www.wowhead.com/" + path})
            except Exception as exc:
                errors.append(f"{label}: {exc}")

    # ponytail: one flat list is enough until the UI proves it needs a database.
    unique: dict[int, dict] = {}
    conflicts: list[dict] = []
    for item in items:
        old = unique.get(item["id"])
        if old and any(old[key] != item[key] for key in ("name_en", "slot", "encounter", "instance")):
            conflicts.append({"id": item["id"], "first": old, "duplicate": item})
        else:
            unique[item["id"]] = item

    levels = [] if stats_mode == "none" else ([334] if stats_mode == "max" else sorted({v for track in RANKS.values() for v in track.values()}))
    jobs = [(item_id, ilvl) for item_id in unique for ilvl in levels]
    if jobs:
        variants: dict[int, list[dict]] = {item_id: [] for item_id in unique}
        # ponytail: two workers respect the public reader; use Blizzard API if nightly speed matters.
        with ThreadPoolExecutor(max_workers=2) as pool:
            future_jobs = {pool.submit(tooltip_variant, item_id, ilvl): (item_id, ilvl) for item_id, ilvl in jobs}
            for future in as_completed(future_jobs):
                item_id, ilvl = future_jobs[future]
                try:
                    variants[item_id].append(future.result())
                except Exception as exc:
                    variants[item_id].append({"item_level": ilvl, "error": str(exc)})
        for item_id, item in unique.items():
            item["variants"] = sorted(variants[item_id], key=lambda row: row["item_level"])

    return {
        "patch": "12.1",
        "season": "Midnight Season 2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Hero 1/6-6/6 and Myth 1/6-6/6; optimizer default Myth 6/6",
        "upgrade_tracks": RANKS,
        "official_pool_source": "https://worldofwarcraft.blizzard.com/en-us/news/24280285",
        "sources": sources,
        "items": sorted(unique.values(), key=lambda row: (row["instance_type"], row["instance"], row["encounter"] or "", row["slot"], row["name_en"])),
        "validation": {"errors": errors, "conflicts": conflicts},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", choices=("none", "max", "all"), default="max")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    data = collect(args.stats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(data['items'])} items to {args.output}")
    print(f"source errors: {len(data['validation']['errors'])}; conflicts: {len(data['validation']['conflicts'])}")
    return 1 if data["validation"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
