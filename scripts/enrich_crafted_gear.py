#!/usr/bin/env python3
"""Add official zh-CN names and icon keys to crafted gear."""

import html
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-crafted-gear.json"
PAGE = "https://db.damijing.com/item/{}"


def fetch(item_id):
    request = urllib.request.Request(PAGE.format(item_id), headers={"User-Agent": "wow-gear-data/0.1"})
    # ponytail: bypass the optional local proxy; this public source works directly.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
        page = response.read().decode("utf-8")
    title = re.search(r"<title>([^<]+?)-魔兽世界", page)
    image = re.search(r'<div class="item-detail-des[^>]*><img src="https?://static\.damijing\.com/wow/item/([^".]+)(?:\.jpg)?"', page)
    if not title or not image:
        raise ValueError(f"missing localized data for item {item_id}")
    icon = image.group(1)
    return html.unescape(title.group(1)), icon


def main():
    data = json.loads(DATA.read_text())
    by_id = {item["id"]: item for item in data["items"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch, item_id): item_id for item_id in by_id}
        for index, future in enumerate(as_completed(jobs), 1):
            item = by_id[jobs[future]]
            item["name_zh_cn"], item["icon"] = future.result()
            print(f"{index}/{len(data['items'])} {item['name_zh_cn']}", flush=True)
    assert all(item.get("name_zh_cn") and item.get("icon") for item in data["items"])
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
