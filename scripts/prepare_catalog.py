#!/usr/bin/env python3
"""Normalize localization, slots, and broad class/spec eligibility."""

from __future__ import annotations

import json
import re
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-loot.json"

INSTANCES = {
    "Altar of Fangs": "毒牙祭坛",
    "Murder Row": "密谋小径",
    "Den of Nalorakk": "纳洛拉克的洞穴",
    "The Blinding Vale": "夺目谷",
    "Voidscar Arena": "虚空之痕竞技场",
    "King's Rest": "诸王之眠",
    "Ruby Life Pools": "红玉新生法池",
    "Temple of Sethraliss": "塞塔里斯神庙",
    "The Venomous Abyss": "烈毒之渊",
    "Tidebound Grotto": "潮缚石窟",
}

ENCOUNTERS = {
    "Atroxus": "阿特洛苏斯",
    "Avatar of Sethraliss": "塞塔里斯的化身",
    "Charonus": "煞戎努斯",
    "Dazar, The First King": "达萨大王",
    "Galvazzt": "加瓦兹特",
    "Ikuzz the Light Hunter": "圣光猎手伊库兹",
    "Kokia Blazehoof": "柯姬雅·焰蹄",
    "Kystia Manaheart": "凯斯媞亚·魔力之心",
    "The Council of Tribes": "部族议会",
    "Lightwarden Ruia": "护光者鲁伊亚",
    "Lithiel Cinderfury": "利希尔·烬怒",
    "Mchimba the Embalmer": "殓尸者姆沁巴",
    "Melidrussa Chillworn": "梅莉杜莎·寒妆",
    "Merektha": "米利克萨",
    "Nalorakk": "纳洛拉克",
    "Sentinel of Winter": "寒冬哨兵",
    "Taz'Rah": "塔兹拉尔",
    "The Golden Serpent": "黄金风蛇",
    "Xathuux the Annihilator": "歼灭者萨祖克斯",
    "Zaen Bladesorrow": "赞恩·刃悲",
    "Ziekket": "兹欧凯特",
    "Adderis and Aspix": "阿德里斯和阿斯匹克斯",
    "Kyrakka and Erkhart Stormvein": "基拉卡和厄克哈特·风脉",
    "Zul'jan": "祖尔加",
    "Nek'zali the Soulcoiler": "盘魂者内克扎莉",
    "Entombed Sentinels": "陵寝哨兵",
    "The Lost Explorers": "迷失的探险者",
    "Vashnik the Malignant": "万毒邪祟者瓦什尼克",
    "Sszorak": "斯索拉克",
    "The Twin Fangs": "双子毒牙",
    "The Coiled Altar": "盘卷祭坛",
    "Ula'tek": "乌拉特克",
    "Nymrissa Wavecaller": "尼姆瑞莎·唤波者",
}

CLASSES = {
    "death_knight": ("死亡骑士", "plate", [("blood", "鲜血", "tank", "strength"), ("frost", "冰霜", "dps", "strength"), ("unholy", "邪恶", "dps", "strength")]),
    "demon_hunter": ("恶魔猎手", "leather", [("devourer", "噬灭", "dps", "intellect"), ("havoc", "浩劫", "dps", "agility"), ("vengeance", "复仇", "tank", "agility")]),
    "druid": ("德鲁伊", "leather", [("balance", "平衡", "dps", "intellect"), ("feral", "野性", "dps", "agility"), ("guardian", "守护", "tank", "agility"), ("restoration", "恢复", "healer", "intellect")]),
    "evoker": ("唤魔师", "mail", [("augmentation", "增辉", "support", "intellect"), ("devastation", "湮灭", "dps", "intellect"), ("preservation", "恩护", "healer", "intellect")]),
    "hunter": ("猎人", "mail", [("beast_mastery", "野兽控制", "dps", "agility"), ("marksmanship", "射击", "dps", "agility"), ("survival", "生存", "dps", "agility")]),
    "mage": ("法师", "cloth", [("arcane", "奥术", "dps", "intellect"), ("fire", "火焰", "dps", "intellect"), ("frost", "冰霜", "dps", "intellect")]),
    "monk": ("武僧", "leather", [("brewmaster", "酒仙", "tank", "agility"), ("mistweaver", "织雾", "healer", "intellect"), ("windwalker", "踏风", "dps", "agility")]),
    "paladin": ("圣骑士", "plate", [("holy", "神圣", "healer", "intellect"), ("protection", "防护", "tank", "strength"), ("retribution", "惩戒", "dps", "strength")]),
    "priest": ("牧师", "cloth", [("discipline", "戒律", "healer", "intellect"), ("holy", "神圣", "healer", "intellect"), ("shadow", "暗影", "dps", "intellect")]),
    "rogue": ("潜行者", "leather", [("assassination", "奇袭", "dps", "agility"), ("outlaw", "狂徒", "dps", "agility"), ("subtlety", "敏锐", "dps", "agility")]),
    "shaman": ("萨满祭司", "mail", [("elemental", "元素", "dps", "intellect"), ("enhancement", "增强", "dps", "agility"), ("restoration", "恢复", "healer", "intellect")]),
    "warlock": ("术士", "cloth", [("affliction", "痛苦", "dps", "intellect"), ("demonology", "恶魔学识", "dps", "intellect"), ("destruction", "毁灭", "dps", "intellect")]),
    "warrior": ("战士", "plate", [("arms", "武器", "dps", "strength"), ("fury", "狂怒", "dps", "strength"), ("protection", "防护", "tank", "strength")]),
}

ARMOR_CLASSES = {armor: [key for key, (_, class_armor, _) in CLASSES.items() if class_armor == armor] for armor in ("cloth", "leather", "mail", "plate")}
WEAPON_CLASSES = {
    "1h_axe": ["death_knight", "demon_hunter", "hunter", "monk", "paladin", "rogue", "shaman", "warrior", "evoker"],
    "2h_axe": ["death_knight", "hunter", "paladin", "shaman", "warrior"],
    "1h_mace": ["death_knight", "druid", "monk", "paladin", "priest", "rogue", "shaman", "warrior", "evoker"],
    "2h_mace": ["death_knight", "druid", "paladin", "shaman", "warrior"],
    "1h_sword": ["death_knight", "demon_hunter", "hunter", "mage", "monk", "paladin", "rogue", "warlock", "warrior", "evoker"],
    "2h_sword": ["death_knight", "hunter", "paladin", "warrior", "evoker"],
    "1h_dagger": ["druid", "mage", "priest", "rogue", "shaman", "warlock", "evoker"],
    "1h_fist": ["demon_hunter", "druid", "hunter", "monk", "rogue", "shaman", "warrior", "evoker"],
    "2h_polearm": ["death_knight", "druid", "hunter", "monk", "paladin", "warrior"],
    "2h_staff": ["druid", "hunter", "mage", "monk", "priest", "shaman", "warlock", "evoker"],
    "1h_warglaive": ["demon_hunter"],
    "ranged_wand": ["mage", "priest", "warlock"],
    "ranged_bow": ["hunter"], "ranged_crossbow": ["hunter"], "ranged_gun": ["hunter"],
    "shield": ["paladin", "shaman", "warrior"],
    "off_hand": ["druid", "evoker", "mage", "priest", "shaman", "warlock"],
}

SLOT_WORDS = {"Helm": "head", "Shoulder": "shoulder", "Shoulders": "shoulder", "Chest": "chest", "Wrist": "wrist", "Hands": "hands", "Waist": "waist", "Legs": "legs", "Feet": "feet"}
WEAPON_WORDS = {"1H Axe": "1h_axe", "2H Axe": "2h_axe", "1H Mace": "1h_mace", "2H Mace": "2h_mace", "1H Sword": "1h_sword", "2H Sword": "2h_sword", "1H Dagger": "1h_dagger", "1H Fist Weapon": "1h_fist", "2H Polearm": "2h_polearm", "2H Staff": "2h_staff", "1H Warglaive": "1h_warglaive", "Ranged Wand": "ranged_wand", "Ranged Bow": "ranged_bow", "Ranged Crossbow": "ranged_crossbow", "Ranged Gun": "ranged_gun", "Shield": "shield", "Off-Hand Weapon": "off_hand"}
ROLE_HINTS = {"Soulcoiler Ritual Vessel": "healer", "Mycolic Medicine": "healer", "Seed of Radiant Hope": "healer", "Preternatural Antivenom": "healer", "First Mate's Shellward": "tank", "Manaheart's Binding Flame": "tank", "Permafrost Essence": "tank"}
TIDEBOUND_GROTTO_ITEM_IDS = {268262, 268263, 268266, 270167}


def normalize_slot(item: dict) -> tuple[str, str | None, str | None]:
    slot = item["slot"]
    if slot == "Shield": return "weapon", None, "shield"
    text = item["variants"][-1]["tooltip_zh_cn"]
    if "\n饰品\n" in text: return "trinket", None, None
    armor = next((value for label, value in (("布甲", "cloth"), ("皮甲", "leather"), ("锁甲", "mail"), ("板甲", "plate")) if f"\n{label}\n" in text), None)
    zh_slot = next((value for label, value in (("头部", "head"), ("肩部", "shoulder"), ("胸部", "chest"), ("手腕", "wrist"), ("手", "hands"), ("腰部", "waist"), ("腿部", "legs"), ("脚", "feet")) if f"\n{label}\n" in text), None)
    if armor and zh_slot: return zh_slot, armor, None
    hand_match = re.search(r"\n(单手|主手|双手|远程)\n(战刃|匕首|拳套|长柄武器|法杖|魔杖|弓|弩|枪|斧|锤|剑)\n", text)
    if hand_match:
        hand_zh, weapon_zh = hand_match.groups()
        weapon_name = {"战刃": "warglaive", "匕首": "dagger", "拳套": "fist", "长柄武器": "polearm", "法杖": "staff", "魔杖": "wand", "弓": "bow", "弩": "crossbow", "枪": "gun", "斧": "axe", "锤": "mace", "剑": "sword"}[weapon_zh]
        prefix = "ranged_" if hand_zh == "远程" else ("2h_" if hand_zh == "双手" else "1h_")
        return "weapon", None, prefix + weapon_name
    if "\n副手\n" in text: return "weapon", None, "off_hand"
    if "\n盾牌\n" in text: return "weapon", None, "shield"
    for armor in ("Cloth", "Leather", "Mail", "Plate"):
        if slot.startswith(armor + " "):
            rest = slot[len(armor) + 1:].split(" Tier Set Token")[0]
            return ("tier_token" if "Tier Set Token" in slot else SLOT_WORDS.get(rest, rest.lower()), armor.lower(), None)
    if slot == "Curio Tier Set Token": return "tier_token", None, None
    if slot in {"Neck", "Ring", "Back", "Trinket"}: return slot.lower(), None, None
    for label, weapon in WEAPON_WORDS.items():
        if slot.startswith(label): return "weapon", None, weapon

    return "unknown", None, None


def primary_stats(item: dict) -> set[str]:
    keys = item["variants"][-1]["stats"]
    result = {stat for stat in ("strength", "agility", "intellect") if stat in keys}
    for key in keys:
        if "_or_" in key:
            result.update(part for part in key.split("_or_") if part in {"strength", "agility", "intellect"})
    return result


def main() -> None:
    data = json.loads(DATA.read_text())
    specs = {f"{class_key}.{key}": {"class": class_key, "name_en": key, "name_zh_cn": zh, "role": role, "primary_stat": primary} for class_key, (_, _, rows) in CLASSES.items() for key, zh, role, primary in rows}
    data["class_catalog"] = {key: {"name_zh_cn": zh, "armor_type": armor, "specs": [f"{key}.{spec[0]}" for spec in rows]} for key, (zh, armor, rows) in CLASSES.items()}
    data["spec_catalog"] = specs
    conflicts = []
    missing_localizations = set()
    reverse_encounters = {value: key for key, value in ENCOUNTERS.items()}
    duplicate_sources: dict[int, list[dict]] = {}
    for conflict in data["validation"].get("conflicts", []):
        duplicate_sources.setdefault(conflict["id"], []).extend((conflict["first"], conflict["duplicate"]))

    # ponytail: these two upstream guide tables are stale/misparsed; item tooltips and boss loot tables are authoritative here.
    source_overrides = {
        251123: ("Kystia Manaheart", "https://www.wowhead.com/guide/midnight/murder-row-dungeon-overview-location-rewards"),
        268231: ("Nek'zali the Soulcoiler", "https://www.wowhead.com/ptr/guide/midnight/raids/venomous-abyss-nekzali-the-soulcoiler-boss-strategy-abilities"),
        268262: ("Nymrissa Wavecaller", "https://worldofwarcraft.blizzard.com/en-us/news/24295085/step-into-lairs-and-face-the-foes-inside"),
        268263: ("Nymrissa Wavecaller", "https://worldofwarcraft.blizzard.com/en-us/news/24295085/step-into-lairs-and-face-the-foes-inside"),
        268266: ("Nymrissa Wavecaller", "https://worldofwarcraft.blizzard.com/en-us/news/24295085/step-into-lairs-and-face-the-foes-inside"),
    }

    for item in data["items"]:
        if item["id"] in TIDEBOUND_GROTTO_ITEM_IDS:
            item["instance"] = "Tidebound Grotto"
            item["instance_type"] = "world_boss"
        item["instance_zh_cn"] = INSTANCES[item["instance"]]
        text = item["variants"][-1]["tooltip_zh_cn"]
        dropped = re.search(r"掉落于:\s*([^\n]+)", text)
        tooltip_name = dropped.group(1).strip() if dropped else None
        source_encounter = item["encounter_source_en"] if "encounter_source_en" in item else item["encounter"]
        expected = ENCOUNTERS.get(source_encounter)
        canonical_encounter = reverse_encounters.get(tooltip_name, item["encounter"])
        item["encounter_source_en"] = source_encounter
        item["encounter"] = canonical_encounter
        expected = ENCOUNTERS.get(canonical_encounter)
        item["encounter_zh_cn"] = tooltip_name or expected
        item["encounter_localization_source"] = "item_tooltip" if tooltip_name else ("official_mapping" if expected else "missing")
        if item["id"] in source_overrides:
            canonical_encounter, source_url = source_overrides[item["id"]]
            item["encounter"] = canonical_encounter
            item["encounter_zh_cn"] = ENCOUNTERS[canonical_encounter]
            item["source_url"] = source_url
        if not item["encounter_zh_cn"] and item["encounter"]:
            missing_localizations.add(item["encounter"])
        if item["encounter_source_en"] != canonical_encounter:
            conflicts.append({"item_id": item["id"], "source_encounter_en": item["encounter_source_en"], "canonical_encounter_en": canonical_encounter, "tooltip_zh_cn": tooltip_name})

        raw_sources = duplicate_sources.get(item["id"], [item])
        if item["id"] in source_overrides:
            encounter, source_url = source_overrides[item["id"]]
            raw_sources = [{**item, "encounter": encounter, "source_url": source_url}]
        seen_sources = set()
        item["drop_sources"] = []
        for source in raw_sources:
            source_encounter = source.get("encounter")
            if tooltip_name and reverse_encounters.get(tooltip_name) and source_encounter != canonical_encounter:
                continue
            key = (source.get("instance"), source_encounter)
            if key in seen_sources: continue
            seen_sources.add(key)
            item["drop_sources"].append({"instance": source.get("instance"), "instance_zh_cn": INSTANCES.get(source.get("instance")), "encounter": source_encounter, "encounter_zh_cn": ENCOUNTERS.get(source_encounter), "source_url": source.get("source_url")})
        if not item["drop_sources"]:
            item["drop_sources"] = [{"instance": item["instance"], "instance_zh_cn": item["instance_zh_cn"], "encounter": canonical_encounter, "encounter_zh_cn": item["encounter_zh_cn"], "source_url": item["source_url"]}]
        item["multiple_drop_sources"] = len(item["drop_sources"]) > 1

        slot_key, armor, weapon = normalize_slot(item)
        item["slot_key"] = slot_key
        item["armor_type"] = armor
        item["weapon_type"] = weapon
        item["loot_role"] = ROLE_HINTS.get(item["name_en"], "all")
        primaries = primary_stats(item)
        if armor:
            candidate_classes = ARMOR_CLASSES[armor]
        elif weapon:
            candidate_classes = WEAPON_CLASSES.get(weapon, [])
        elif slot_key in {"neck", "ring", "back", "trinket", "tier_token"}:
            candidate_classes = list(CLASSES)
        else:
            candidate_classes = []
        item["candidate_classes"] = candidate_classes
        item["candidate_specs"] = [key for key, spec in specs.items() if spec["class"] in candidate_classes and (not primaries or spec["primary_stat"] in primaries) and (item["loot_role"] == "all" or spec["role"] == item["loot_role"])]
        item["eligibility_status"] = "broad_rule_v1" if candidate_classes else "needs_review"

    data["validation"]["catalog_conflicts"] = conflicts
    data["validation"]["missing_encounter_localizations"] = sorted(missing_localizations)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"prepared {len(data['items'])} items; conflicts {len(conflicts)}; missing encounter localizations {len(missing_localizations)}")


if __name__ == "__main__":
    main()
