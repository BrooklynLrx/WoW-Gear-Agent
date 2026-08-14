#!/usr/bin/env python3
"""Merge the 40 Wowhead BiS pages into one frontend-ready JSON file."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/bis-wowhead-raw"
OUT = ROOT / "data/12.1-wowhead-bis.json"

CLASSES = {
    "death-knight": "死亡骑士", "demon-hunter": "恶魔猎手", "druid": "德鲁伊",
    "evoker": "唤魔师", "hunter": "猎人", "mage": "法师", "monk": "武僧",
    "paladin": "圣骑士", "priest": "牧师", "rogue": "潜行者", "shaman": "萨满祭司",
    "warlock": "术士", "warrior": "战士",
}
SPECS = {
    "blood": "鲜血", "frost": "冰霜", "unholy": "邪恶", "havoc": "浩劫",
    "vengeance": "复仇", "devourer": "吞噬", "balance": "平衡", "feral": "野性",
    "guardian": "守护", "restoration": "恢复", "augmentation": "增辉",
    "devastation": "湮灭", "preservation": "恩护", "beast-mastery": "野兽控制",
    "marksmanship": "射击", "survival": "生存", "arcane": "奥术", "fire": "火焰",
    "brewmaster": "酒仙", "mistweaver": "织雾", "windwalker": "踏风", "holy": "神圣",
    "protection": "防护", "retribution": "惩戒", "discipline": "戒律", "shadow": "暗影",
    "assassination": "奇袭", "outlaw": "狂徒", "subtlety": "敏锐", "elemental": "元素",
    "enhancement": "增强", "affliction": "痛苦", "demonology": "恶魔学识",
    "destruction": "毁灭", "arms": "武器", "fury": "狂怒",
}
SLOTS = {
    "Weapon": "武器", "Mainhand": "主手", "Offhand": "副手", "Head": "头部",
    "Neck": "颈部", "Shoulders": "肩部", "Cloak": "披风", "Chest": "胸部",
    "Bracers": "护腕", "Gloves": "手套", "Belt": "腰带", "Legs": "腿部",
    "Boots": "脚部", "Ring": "戒指", "Trinket": "饰品", "Main Hand": "主手",
    "Off Hand": "副手", "Wrist": "护腕", "Ring 1": "戒指1", "Ring 2": "戒指2",
    "Trinket 1": "饰品1", "Trinket 2": "饰品2", "Helm": "头部",
}
SUPPLEMENTAL = {
    270167: ("唤波者的海石", "inv_tradeskillitem_sorcererswater"),
    268217: ("怒潮护腕", "inv_bracer_mail_raidhunterulatek_d_01"),
    268247: ("破浪皮靴", "inv_boot_leather_raiddemonhunterulatek_d_01"),
    271506: ("天选屠血者护腕", "inv_bracer_leather_raidrogueulatek_d_01"),
    271512: ("天选屠血者皮靴", "inv_boot_leather_raidrogueulatek_d_01"),
    159369: ("圣金古墓腰带", "inv_belt_mail_zandalardungeon_c_01"),
    240166: ("奥纹内衬", "inv_12_tailoring_rare_cloth_violet_rare-cloth"),
}


def load(path):
    return json.loads(path.read_text())


def build_catalog():
    catalog = {}
    for item in load(ROOT / "data/12.1-season2-loot.json")["items"]:
        catalog[item["id"]] = ("drop", item)
    for item in load(ROOT / "data/12.1-season2-crafted-gear.json")["items"]:
        catalog[item["id"]] = ("crafted", item)
    for class_set in load(ROOT / "data/12.1-season2-tier-sets.json")["class_sets"]:
        for item in class_set["items"]:
            catalog[item["id"]] = ("tier", item)
    return catalog


def localize_link(link, catalog):
    item_id = link["id"] or int(re.search(r"item=(\d+)", link["url"]).group(1))
    kind, item = catalog.get(item_id, (None, {}))
    fallback_name, fallback_icon = SUPPLEMENTAL.get(item_id, (None, None))
    return {
        "id": item_id,
        "name_en": link["name"],
        "name_zh_cn": item.get("name_zh_cn") or fallback_name,
        "icon": item.get("icon") or fallback_icon,
        "catalog_kind": kind,
        "url": link["url"],
        "original_item_id": int(m.group(1)) if (m := re.search(r"original-item=(\d+)", link["url"])) else None,
    }


def main():
    catalog = build_catalog()
    pages = []
    unresolved = []
    for path in sorted(RAW.glob("*.json")):
        raw = load(path)
        variants = []
        for index, table in enumerate(raw["tables"], 1):
            rows = []
            for raw_row in table["rows"][1:]:
                # ponytail: Wowhead sometimes inserts one empty icon column.
                cells = [cell for cell in raw_row["cells"] if cell]
                if len(cells) < 3:
                    continue
                links = []
                seen = set()
                for link in raw_row["items"]:
                    localized = localize_link(link, catalog)
                    if localized["id"] not in seen:
                        seen.add(localized["id"])
                        links.append(localized)
                primary = next((x for x in links if x["name_en"] == cells[1]), links[-1] if links else None)
                if primary and not primary["name_zh_cn"]:
                    unresolved.append({"class": raw["class"], "spec": raw["spec"], "id": primary["id"], "name_en": primary["name_en"]})
                source_item = catalog.get(primary["id"], (None, {}))[1] if primary else {}
                rows.append({
                    "slot_en": cells[0], "slot_zh_cn": SLOTS.get(cells[0]),
                    "item_en": cells[1], "item_id": primary["id"] if primary else None,
                    "item_zh_cn": primary["name_zh_cn"] if primary else None,
                    "icon": primary["icon"] if primary else None,
                    "source_en": cells[2],
                    "source_zh_cn": source_item.get("encounter_zh_cn") or source_item.get("instance_zh_cn"),
                    "linked_items": links,
                })
            variants.append({"variant_index": index, "items": rows})
        pages.append({
            "class": raw["class"], "class_zh_cn": CLASSES[raw["class"]],
            "spec": raw["spec"], "spec_zh_cn": SPECS[raw["spec"]],
            "source_url": raw["source_url"], "source_updated": raw.get("updated"),
            "variants": variants,
        })

    assert len(pages) == 40, f"expected 40 specs, got {len(pages)}"
    assert all(page["variants"] for page in pages), "a spec has no BiS table"
    total_variants = sum(len(page["variants"]) for page in pages)
    total_rows = sum(len(v["items"]) for page in pages for v in page["variants"])
    output = {
        "patch": "12.1.0", "season": "Midnight Season 2", "generated_at": "2026-08-13",
        "scope": "Wowhead overall BiS display data; not a DPS simulation",
        "defaults": {"item_level_policy": "myth_6_of_6_when_available"},
        "profiles": pages,
        "validation": {
            "spec_count": len(pages), "variant_count": total_variants, "row_count": total_rows,
            "unresolved_primary_item_count": len(unresolved), "unresolved_primary_items": unresolved,
        },
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(output["validation"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
