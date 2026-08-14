#!/usr/bin/env python3
"""Add official zh-CN names and icons to the 12.1 extras catalog."""

import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-consumables.json"


def fetch(item_id):
    request = urllib.request.Request(f"https://db.damijing.com/item/{item_id}", headers={"User-Agent": "wow-gear-data/0.1"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        page = response.read().decode("utf-8")
    title = re.search(r"<title>([^<]+?)-魔兽世界", page)
    image = re.search(r'<div class="item-detail-des[^>]*><img src="https?://static\.damijing\.com/wow/item/([^".]+)(?:\.jpg)?"', page)
    if not title or not image:
        raise ValueError(f"missing localized data for item {item_id}")
    return html.unescape(title.group(1)), image.group(1)


def main():
    data = json.loads(DATA.read_text())
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch, row["id"]): row for row in data["items"]}
        for index, future in enumerate(as_completed(jobs), 1):
            row = jobs[future]
            row["name_zh_cn"], row["icon"] = future.result()
            print(f"{index}/{len(jobs)} {row['name_zh_cn']}", flush=True)
    assert all(row.get("name_zh_cn") and row.get("icon") for row in data["items"])
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
