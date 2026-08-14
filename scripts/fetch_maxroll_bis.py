#!/usr/bin/env python3
"""Fetch factual Maxroll BIS tables without copying guide prose."""

import argparse
import html
import json
import re
import subprocess
import os
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

SPECS = [
    "blood-death-knight", "frost-death-knight", "unholy-death-knight",
    "devourer-demon-hunter", "havoc-demon-hunter", "vengeance-demon-hunter",
    "balance-druid", "feral-druid", "guardian-druid", "restoration-druid",
    "augmentation-evoker", "devastation-evoker", "preservation-evoker",
    "beast-mastery-hunter", "marksmanship-hunter", "survival-hunter",
    "arcane-mage", "fire-mage", "frost-mage",
    "brewmaster-monk", "mistweaver-monk", "windwalker-monk",
    "holy-paladin", "protection-paladin", "retribution-paladin",
    "discipline-priest", "holy-priest", "shadow-priest",
    "assassination-rogue", "outlaw-rogue", "subtlety-rogue",
    "elemental-shaman", "enhancement-shaman", "restoration-shaman",
    "affliction-warlock", "demonology-warlock", "destruction-warlock",
    "arms-warrior", "fury-warrior", "protection-warrior",
]


def fetch(url):
    env = os.environ.copy()
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    result = subprocess.run(
        ["curl", "-sS", "-L", "--retry", "3", "--retry-delay", "2", url],
        check=True, capture_output=True, text=True, env=env,
    )
    return result.stdout


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def parse(text, url, spec, recommendation_context):
    item_ids = {}
    for item_id, item_name in re.findall(r'data-wow-item="(\d+):[^"]*"[^>]*>(.*?)</span>', text, re.S):
        clean_name = html.unescape(re.sub(r"<[^>]+>", "", item_name)).strip()
        item_ids.setdefault(clean_name, int(item_id))
    if "<html" in text[:1000].lower():
        extractor = TextExtractor()
        extractor.feed(text)
        text = "\n".join(extractor.parts)
    updated = re.search(r"Last Updated:\s*\n([^\n]+)", text)
    match = re.search(
        r"Gear\s*\nPatch 12\.1 - Midnight\s*\n.*?\nBest in Slot\s*\nFarmable Alternatives\s*\n"
        r"Slot\s*\nItem\s*\nLocation\s*\n(.*?)\nBelow you are presented with",
        text, re.S | re.I,
    )
    if not match:
        raise ValueError(f"BIS table not found: {url}")

    lines = [line.strip().replace("‍", "") for line in match.group(1).splitlines() if line.strip()]
    slots = {"Head", "Neck", "Shoulder", "Cloak", "Chest", "Wrist", "Gloves", "Belt",
             "Legs", "Boots", "Ring 1", "Ring 2", "Trinket 1", "Trinket 2",
             "Main-hand", "Off-hand", "Two-hand"}
    slot_pattern = re.compile(r"^(" + "|".join(map(re.escape, sorted(slots, key=len, reverse=True))) + r")(?:\t|$)")
    raw_rows = []
    current = None
    for line in lines:
        found = slot_pattern.match(line)
        if found:
            if current:
                raw_rows.append(current)
            current = [found.group(1), line[found.end():].strip()]
        elif current:
            current.append(line)
    if current:
        raw_rows.append(current)

    rows = []
    for slot, *parts in raw_rows:
        columns = [value.strip() for value in " ".join(parts).split("\t") if value.strip()]
        if len(columns) == 1:
            tokens = [p for p in parts if p]
            if len(tokens) >= 2:
                columns = [" ".join(tokens[:-1]), tokens[-1]]
        if len(columns) >= 2:
            item = " ".join(columns[:-1]).replace("Convert ", "").replace(" into ", " → ")
            final_item = item.split(" → ")[-1]
            rows.append({"slot": slot, "item_id": item_ids.get(final_item),
                         "item_en": item, "location_en": columns[-1]})

    return {
        "spec": spec,
        "recommendation_context": recommendation_context,
        "set_kind": "final_bis",
        "one_set_per_context": True,
        "gear_source_policy": "unrestricted_final_bis",
        "gear_source_policy_zh_cn": "最终毕业配装可混用团本、大秘境、制造、套装及转化装备，不按掉落来源拆分。",
        "patch": "12.1",
        "last_updated": updated.group(1) if updated else None,
        "source_url": url,
        "items": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", nargs="?", help="Maxroll slug prefix, e.g. arcane-mage")
    parser.add_argument("--type", choices=("mythic-plus", "raid"), default="mythic-plus")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("data/bis/raw"))
    args = parser.parse_args()
    if args.all:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        failures = []
        for spec in SPECS:
            for content_type in ("raid", "mythic-plus"):
                url = f"https://maxroll.gg/wow/class-guides/{spec}-{content_type}-guide"
                try:
                    data = parse(fetch(url), url + "#gear-header", spec, content_type)
                    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    path = args.output_dir / f"{spec}-{content_type}.json"
                    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                    print(f"OK {spec} {content_type} {len(data['items'])}", flush=True)
                except Exception as error:
                    failures.append({"spec": spec, "context": content_type, "error": str(error)})
                    print(f"FAIL {spec} {content_type}: {error}", flush=True)
        (args.output_dir / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n")
        return
    if not args.spec:
        parser.error("spec is required unless --all is used")
    url = f"https://maxroll.gg/wow/class-guides/{args.spec}-{args.type}-guide"
    data = parse(fetch(url), url, args.spec, args.type)
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
