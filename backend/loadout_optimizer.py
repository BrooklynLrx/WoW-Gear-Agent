"""Deterministic secondary-stat loadout search."""

import json
from collections import Counter
from functools import lru_cache
from itertools import combinations, permutations
from pathlib import Path

from sqlalchemy import select

from backend.builder_tools import calculate_stats, search_items_for_spec
from backend.db import SessionLocal
from backend.loadout_validator import SINGLE_SLOTS, canonical_slot, valid_weapon_kinds
from backend.models import BisItem, BisProfile, GameVersion, Item, Spec
from backend.stat_calculator import STATS, calculate_percentages


DATA = Path(__file__).resolve().parents[1] / "data" / "12.1-season2-consumables.json"
BEAM_WIDTH = 1200
MAX_GROUP_OPTIONS = 300
MAX_CRAFTED_ITEMS = 2
AUTO_FLASK_IDS = (241326, 241324, 241322, 241320)
CRAFTED_PRIMARY_STAT_PENALTY = 6.0


def preference_key(tier, minimum_tier, late_raid_special, crafted, stat_score, embellished=0, boe=0, crafted_large=0):
    """Apply the acquisition policy before comparing secondary-stat fit."""
    crafted_loss = CRAFTED_PRIMARY_STAT_PENALTY * crafted * crafted
    return (
        max(minimum_tier - tier, 0),
        -late_raid_special,
        abs(2 - embellished),
        boe,
        crafted_large,
        stat_score + crafted_loss,
    )


@lru_cache(maxsize=1)
def supplement_catalog():
    return {item["id"]: item for item in json.loads(DATA.read_text(encoding="utf-8"))["items"]}


def add_stats(left, right):
    return {stat: int(left.get(stat, 0)) + int(right.get(stat, 0)) for stat in STATS}


def crafted_budget_allows(state, option):
    return state["crafted"] + option["crafted"] <= MAX_CRAFTED_ITEMS


def supplement_stats(item_ids):
    total = {stat: 0 for stat in STATS}
    for item_id in item_ids:
        item = supplement_catalog().get(int(item_id), {})
        if item.get("stat_calculation_included"):
            total = add_stats(total, item.get("secondary_stats") or {})
    return total


def score_stats(ratings, mastery_coefficient, objectives, current_ratings=None):
    percentages = calculate_percentages(ratings, mastery_coefficient)["percentages"]
    score = 0.0
    for objective in objectives:
        rule = objective["rule"]
        stat = objective.get("stat")
        if rule == "rating_ratio":
            weights = objective["weights"]
            rating_total = sum(ratings[key] for key in weights) or 1
            weight_total = sum(weights.values())
            score += 10000 * sum(
                (ratings[key] / rating_total - weights[key] / weight_total) ** 2
                for key in weights
            )
        elif rule == "sheet_percent":
            score += 10 * (percentages[stat] - objective["target"]) ** 2
        elif rule == "sheet_percent_range":
            value = percentages[stat]
            distance = max(objective["minimum"] - value, 0, value - objective["maximum"])
            score += 10 * distance ** 2
        elif rule == "at_least":
            score += 10 * max((objective.get("target") or 0) - percentages[stat], 0) ** 2
        elif rule == "at_most":
            score += 10 * max(percentages[stat] - (objective.get("target") or 0), 0) ** 2
        elif rule == "minimize":
            score += 100 * ratings[stat] / (sum(ratings.values()) or 1)
        elif rule == "maximize":
            score -= 100 * ratings[stat] / (sum(ratings.values()) or 1)
        elif rule == "increase" and current_ratings:
            score += max(current_ratings[stat] - ratings[stat], 0) ** 2
        elif rule == "decrease" and current_ratings:
            score += max(ratings[stat] - current_ratings[stat], 0) ** 2
    return score


def choose_auto_flask(ratings, mastery_coefficient, objectives):
    """Choose the flask that best fills the finished gear set's objective gap."""
    return min(AUTO_FLASK_IDS, key=lambda item_id: score_stats(
        add_stats(ratings, supplement_stats([item_id])), mastery_coefficient, objectives,
    ))


def expand_candidate(item, selected=None):
    """Expand one crafted item into its six possible two-stat choices."""
    selected = selected or {}
    base = {stat: int(item["stats"].get(stat, 0)) for stat in STATS}
    gems = selected.get("gems") or []
    base = add_stats(base, supplement_stats(gems))
    overrides = selected.get("crafted_secondary_stats") or {}
    if overrides:
        variants = [overrides]
    elif item["customizable_secondaries"]:
        amounts = item.get("customizable_secondary_amounts") or []
        choices = item.get("secondary_stat_choices") or []
        variants = [dict(zip(pair, amounts)) for pair in combinations(choices, 2)]
    else:
        variants = [{}]

    expanded = []
    for override in variants:
        equipment = {
            "item_id": item["item_id"],
            "item_level": item["item_level"],
            "gems": list(gems),
            "crafted_secondary_stats": override,
        }
        detail = {**item, "selected_crafted_secondary_stats": override}
        if item["is_tier"]:
            detail["tier_acquisition_method"] = "curio_exchange"
        expanded.append({
            "equipment": equipment,
            "stats": add_stats(base, override),
            "item_id": item["item_id"],
            "slot_key": item["slot_key"],
            "tier": int(item["is_tier"]),
            "tier_capable": int(item["is_tier"] or item.get("catalyst_eligible", False)),
            "embellished": int(item["is_embellished"]),
            "crafted": int(item["is_crafted"]),
            "late_raid_special": int(item.get("is_late_raid_special_effect", False)),
            "boe": int(item.get("is_raid_boe", False)),
            "crafted_large": int(item["is_crafted"] and item["slot_key"] not in {"back", "wrist", "waist"}),
            "unique": bool(item["is_unique_equipped"]),
            "weapon_kind": item.get("weapon_kind"),
            "detail": detail,
        })
    return expanded


def package(candidates):
    stats = {stat: 0 for stat in STATS}
    for candidate in candidates:
        stats = add_stats(stats, candidate["stats"])
    return {
        "candidates": list(candidates),
        "stats": stats,
        "tier": sum(value["tier"] for value in candidates),
        "tier_capable": sum(value["tier_capable"] for value in candidates),
        "embellished": sum(value["embellished"] for value in candidates),
        "crafted": sum(value["crafted"] for value in candidates),
        "late_raid_special": sum(value["late_raid_special"] for value in candidates),
        "boe": sum(value["boe"] for value in candidates),
        "crafted_large": sum(value["crafted_large"] for value in candidates),
        "item_ids": [value["item_id"] for value in candidates],
        "unique_ids": {value["item_id"] for value in candidates if value["unique"]},
    }


def pair_packages(candidates):
    return [package(pair) for pair in combinations(candidates, 2) if pair[0]["item_id"] != pair[1]["item_id"]]


def weapon_packages(full_spec_key, candidates):
    options = [package([item]) for item in candidates if valid_weapon_kinds(full_spec_key, [item["weapon_kind"]])]
    seen = set()
    for pair in permutations(candidates, 2):
        if pair[0]["item_id"] == pair[1]["item_id"]:
            continue
        kinds = [pair[0]["weapon_kind"], pair[1]["weapon_kind"]]
        key = (
            pair[0]["item_id"], json.dumps(pair[0]["equipment"].get("crafted_secondary_stats"), sort_keys=True),
            pair[1]["item_id"], json.dumps(pair[1]["equipment"].get("crafted_secondary_stats"), sort_keys=True),
        )
        if key not in seen and valid_weapon_kinds(full_spec_key, kinds):
            seen.add(key)
            options.append(package(pair))
    return options


def apply_tier_marks(candidates, minimum_tier, tier_targets):
    """Mark selected armor as tier after gear selection; stats and effects stay unchanged."""
    marked = []
    tier_count = sum(value["tier"] for value in candidates)
    needed = max(minimum_tier - tier_count, 0)
    for value in candidates:
        value = {**value, "equipment": dict(value["equipment"]), "detail": dict(value["detail"])}
        target = tier_targets.get(value["slot_key"])
        if needed and not value["tier"] and value["tier_capable"] and target:
            value["equipment"]["catalyst_tier_item_id"] = target["item_id"]
            value["detail"].update({
                "tier_set_item_name_zh_cn": target["name_zh_cn"],
                "tier_acquisition_method": "catalyst_conversion",
                "source_item_id": value["item_id"],
                "source_item_name_zh_cn": value["detail"]["name_zh_cn"],
                "source_item_sources": value["detail"]["sources"],
                "catalyst_tier_item_id": target["item_id"],
            })
            needed -= 1
            tier_count += 1
        marked.append(value)
    return marked, tier_count


def optimize_loadout(
    class_key,
    spec_key,
    objectives,
    constraints,
    current_equipment=(),
    consumable_ids=(),
    default_item_level=334,
    solution_count=3,
):
    if not objectives:
        return {"success": False, "error": "missing_objectives"}
    if int(default_item_level) != 334:
        return {"success": False, "error": "optimizer_only_supports_graduation_levels", "drop_item_level": 334, "crafted_item_level": 331}
    full_spec_key = f"{class_key}.{spec_key}"
    locked_slots = {canonical_slot(value.split("_", 1)[0]) for value in constraints.get("locked_slots", [])}
    locked_ids = set(constraints.get("locked_item_ids") or [])
    with SessionLocal() as session:
        spec = session.scalar(select(Spec).join(GameVersion).where(
            Spec.class_key == class_key,
            Spec.spec_key == spec_key,
            GameVersion.is_active.is_(True),
        ))
        if spec is None:
            return {"success": False, "error": "unknown_spec"}
        coefficient = float(spec.mastery_coefficient)
        bis_trinket_ids = list(session.scalars(
            select(Item.game_item_id)
            .join(BisItem, BisItem.item_id == Item.id)
            .join(BisProfile, BisProfile.id == BisItem.profile_id)
            .where(
                BisProfile.spec_id == spec.id,
                BisProfile.variant_index == 1,
                BisItem.slot_key == "trinket",
            )
            .order_by(BisItem.position)
        ))

    slots = ["head", "neck", "shoulders", "back", "chest", "wrist", "gloves", "waist", "legs", "feet", "finger", "trinket", "weapon"]
    candidates = {}
    tier_targets = {}
    bis_trinkets_applied = False
    for slot in slots:
        result = search_items_for_spec(
            class_key, spec_key, slot_key=slot, item_level=334, limit=500,
        )
        values = []
        items = result.get("items", [])
        tier_target = next((item for item in items if item["is_tier"]), None)
        if tier_target:
            tier_targets[slot] = tier_target
        for item in items:
            # Tier identity is applied after optimization; do not duplicate every item as a tier variant.
            if item["is_tier"]:
                continue
            if item["is_crafted"] and not constraints.get("allow_crafted", True):
                continue
            excluded = set(constraints.get("excluded_instances") or [])
            if excluded and any(source.get("instance_name_zh_cn") in excluded for source in item["sources"]):
                continue
            values.extend(expand_candidate(item))
        if slot == "trinket" and constraints.get("use_bis_trinkets", True) and slot not in locked_slots:
            bis_values = [value for value in values if value["item_id"] in bis_trinket_ids]
            if len({value["item_id"] for value in bis_values}) >= 2:
                values = bis_values
                bis_trinkets_applied = True
        candidates[slot] = values
    current_by_slot = {slot: [] for slot in slots}
    for selected in current_equipment:
        result = search_items_for_spec(
            class_key, spec_key,
            item_level=int(selected.get("item_level", default_item_level)),
            game_item_id=int(selected["item_id"]), limit=1,
        )
        if not result.get("items"):
            return {"success": False, "error": "current_item_not_found", "item_id": selected["item_id"]}
        item = result["items"][0]
        slot = item["slot_key"]
        values = expand_candidate(item, selected)
        current_by_slot[slot].extend(values)
        graduation_level = 331 if item["is_crafted"] else 334
        if item["item_level"] != graduation_level:
            if slot in locked_slots or item["item_id"] in locked_ids:
                return {
                    "success": False,
                    "error": "locked_item_below_graduation_level",
                    "item_id": item["item_id"],
                    "item_level": item["item_level"],
                    "required_item_level": graduation_level,
                }
            continue
        existing = {
            (
                value["item_id"],
                value["equipment"]["item_level"],
                json.dumps(value["equipment"].get("crafted_secondary_stats"), sort_keys=True),
            )
            for value in candidates[slot]
        }
        for value in values:
            key = (value["item_id"], value["equipment"]["item_level"], json.dumps(value["equipment"].get("crafted_secondary_stats"), sort_keys=True))
            if key not in existing:
                candidates[slot].insert(0, value)

    required_slots = locked_slots | {
        slot for slot, values in current_by_slot.items()
        if any(value["item_id"] in locked_ids for value in values)
    }
    groups = []
    for slot in sorted(slots, key=lambda value: value not in required_slots):
        values = candidates[slot]
        if slot in locked_slots:
            values = current_by_slot[slot]
        if slot in DOUBLE_SLOTS_LOCAL:
            options = pair_packages(values)
        elif slot == "weapon":
            options = weapon_packages(full_spec_key, values)
        else:
            options = [package([value]) for value in values]

        required = {value["item_id"] for value in current_by_slot[slot]} if slot in locked_slots else set()
        required |= {item_id for item_id in locked_ids if any(value["item_id"] == item_id for value in values)}
        if required:
            options = [option for option in options if required <= set(option["item_ids"])]
        if not options:
            return {"success": False, "error": "no_candidates", "slot_key": slot}
        groups.append((slot, options))

    selected_categories = {
        supplement_catalog().get(int(item_id), {}).get("category") for item_id in consumable_ids
    }
    auto_flask = "flask" not in selected_categories
    selected_consumables = list(consumable_ids)
    baseline = supplement_stats(selected_consumables)
    current_ratings = dict(baseline)
    for values in current_by_slot.values():
        for value in values:
            current_ratings = add_stats(current_ratings, value["stats"])
    minimum_tier = int(constraints.get("minimum_tier_pieces", 0) or 0)
    current_ids = Counter(int(item["item_id"]) for item in current_equipment)

    beam = [{
        "ratings": baseline, "tier": 0, "tier_capable": 0, "embellished": 0,
        "crafted": 0, "late_raid_special": 0, "boe": 0, "crafted_large": 0,
        "consumable_ids": selected_consumables,
        "item_ids": [], "unique_ids": set(), "candidates": [],
    }]
    for slot, options in groups:
        options.sort(key=lambda option: preference_key(
            option["tier_capable"], minimum_tier, option["late_raid_special"], option["crafted"],
            score_stats(add_stats(baseline, option["stats"]), coefficient, objectives, current_ratings),
            2, option["boe"], option["crafted_large"],
        ))
        options = options[:MAX_GROUP_OPTIONS]
        expanded = []
        for state in beam:
            for option in options:
                if state["embellished"] + option["embellished"] > 2:
                    continue
                if not crafted_budget_allows(state, option):
                    continue
                if option["unique_ids"] & set(state["item_ids"]):
                    continue
                if state["unique_ids"] & set(option["item_ids"]):
                    continue
                expanded.append({
                    "ratings": add_stats(state["ratings"], option["stats"]),
                    "tier": state["tier"] + option["tier"],
                    "tier_capable": state["tier_capable"] + option["tier_capable"],
                    "embellished": state["embellished"] + option["embellished"],
                    "crafted": state["crafted"] + option["crafted"],
                    "late_raid_special": state["late_raid_special"] + option["late_raid_special"],
                    "boe": state["boe"] + option["boe"],
                    "crafted_large": state["crafted_large"] + option["crafted_large"],
                    "consumable_ids": state["consumable_ids"],
                    "item_ids": state["item_ids"] + option["item_ids"],
                    "unique_ids": state["unique_ids"] | option["unique_ids"],
                    "candidates": state["candidates"] + option["candidates"],
                })
        if not expanded:
            return {"success": False, "error": "search_exhausted", "slot_key": slot}
        expanded.sort(key=lambda state: preference_key(
            state["tier_capable"], minimum_tier, state["late_raid_special"], state["crafted"],
            score_stats(state["ratings"], coefficient, objectives, current_ratings),
            state["embellished"], state["boe"], state["crafted_large"],
        ))
        beam = expanded[:BEAM_WIDTH]

    solutions = []
    for state in beam:
        if state["tier_capable"] < minimum_tier:
            continue
        marked_candidates, tier_count = apply_tier_marks(state["candidates"], minimum_tier, tier_targets)
        equipment = [value["equipment"] for value in marked_candidates]
        selected_consumables = list(state["consumable_ids"])
        if auto_flask:
            selected_consumables.append(choose_auto_flask(state["ratings"], coefficient, objectives))
        calculated = calculate_stats(
            class_key, spec_key, equipment, selected_consumables, require_complete=True
        )
        if not calculated["success"]:
            continue
        proposed_ids = Counter(state["item_ids"])
        changes = sum((current_ids - proposed_ids).values()) + sum((proposed_ids - current_ids).values())
        ratio_score = score_stats(
            calculated["calculation"]["ratings"], coefficient, objectives, current_ratings
        ) + changes * 0.001
        solutions.append({
            "score": round(ratio_score, 6),
            "equipment": [
                {
                    key: data
                    for key, data in value["detail"].items()
                    if key not in {"maximum_user_selected_sockets", "socket_policy_zh_cn"}
                }
                for value in marked_candidates
            ],
            "ratings": calculated["calculation"]["ratings"],
            "percentages": calculated["calculation"]["percentages"],
            "tier_count": tier_count,
            "embellishment_count": state["embellished"],
            "crafted_item_count": state["crafted"],
            "crafted_large_slot_count": state["crafted_large"],
            "late_raid_special_effect_count": state["late_raid_special"],
            "raid_boe_count": state["boe"],
            "changed_item_count": changes,
            "consumable_ids": selected_consumables,
            "selected_flask": next((supplement_catalog()[item_id] for item_id in selected_consumables if supplement_catalog().get(item_id, {}).get("category") == "flask"), None),
        })
        if len(solutions) >= max(solution_count * 5, 15):
            break
    solutions.sort(key=lambda value: preference_key(
        value["tier_count"], minimum_tier, value["late_raid_special_effect_count"],
        value["crafted_item_count"], value["score"], value["embellishment_count"],
        value["raid_boe_count"], value["crafted_large_slot_count"],
    ))
    return {
        "success": bool(solutions),
        "spec": full_spec_key,
        "objective_source": "user_only",
        "trinket_policy": {
            "mode": (
                "user_override" if "trinket" in locked_slots or not constraints.get("use_bis_trinkets", True)
                else "spec_bis" if bis_trinkets_applied
                else "stat_fallback"
            ),
            "bis_item_ids": bis_trinket_ids,
        },
        "solutions": solutions[:max(1, min(int(solution_count), 5))],
        "warnings": [
            "饰品默认固定为该专精Wowhead BIS；用户可锁定饰品栏或设置use_bis_trinkets=false后自行更换。饰品特效不折算绿字，静态绿字正常计入。",
            "新选择的装备不会自动添加宝石。",
            "用户未指定合剂时，自动从四种最高品质单绿字合剂中选择一瓶并计入165点绿字。",
            "套装不作为重复候选参与绿字搜索；选装后从已穿的可催化部位标记四件，属性和特效不变。",
            "毕业方案整套最多选择两件制造装备，制造武器也计入；其中美化装备同样不得超过两件。",
            "老七/老八的非饰品特效装备按最高优先级处理；饰品只按专精BIS选择。",
            "团本小怪装绑因价格高置于普通副本装和制造装之后；其随机双绿字仍可参与目标计算。",
            "毕业候选池固定为普通/套装334与制造331；更低装等只用于比较当前装备。",
        ],
    }


DOUBLE_SLOTS_LOCAL = {"finger", "trinket"}
