#!/usr/bin/env python3
"""Run the production loadout optimizer once for every active specialization."""

import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import select

from backend.db import SessionLocal
from backend.loadout_optimizer import optimize_loadout
from backend.models import GameVersion, Spec


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "12.1-all-spec-builder-audit.json"
OBJECTIVES = [{
    "rule": "rating_ratio",
    "weights": {"critical_strike": 1, "haste": 1, "mastery": 1, "versatility": 1},
}]


def audit_spec(spec):
    started = time.monotonic()
    class_key, spec_key, class_name, spec_name = spec
    result = optimize_loadout(
        class_key,
        spec_key,
        OBJECTIVES,
        {"minimum_tier_pieces": 4, "use_bis_trinkets": True},
        solution_count=1,
    )
    row = {
        "spec": f"{class_key}.{spec_key}",
        "name_zh_cn": f"{class_name}·{spec_name}",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "success": bool(result.get("success")),
    }
    if not row["success"]:
        row["error"] = result.get("error")
        row["detail"] = result
        return row

    solution = result["solutions"][0]
    equipment = solution["equipment"]
    trinkets = [item for item in equipment if item["slot_key"] == "trinket"]
    wrong_levels = [
        item["item_id"] for item in equipment
        if item["item_level"] != (331 if item["is_crafted"] else 334)
    ]
    selected_trinkets = [item["item_id"] for item in trinkets]
    policy = result["trinket_policy"]
    checks = {
        "complete_loadout": len(equipment) in {15, 16},
        "valid_graduation_levels": not wrong_levels,
        "minimum_four_tier": solution["tier_count"] >= 4,
        "two_trinkets": len(trinkets) == 2,
        "bis_trinkets_match": policy["mode"] != "spec_bis" or set(selected_trinkets) <= set(policy["bis_item_ids"]),
        "auto_flask_selected": bool(solution.get("selected_flask")),
    }
    row.update({
        "passed": all(checks.values()),
        "checks": checks,
        "score": solution["score"],
        "ratings": solution["ratings"],
        "percentages": solution["percentages"],
        "tier_count": solution["tier_count"],
        "crafted_item_count": solution["crafted_item_count"],
        "special_effect_item_count": solution["late_raid_special_effect_count"],
        "trinket_policy": policy,
        "trinkets": [{"item_id": item["item_id"], "name_zh_cn": item["name_zh_cn"]} for item in trinkets],
        "wrong_level_item_ids": wrong_levels,
        "equipment": [{
            "slot_key": item["slot_key"],
            "item_id": item["item_id"],
            "name_zh_cn": item.get("display_name_zh_cn", item["name_zh_cn"]),
            "item_level": item["item_level"],
            "is_crafted": item["is_crafted"],
            "tier_acquisition_method": item.get("tier_acquisition_method"),
            "source_item_id": item.get("source_item_id"),
        } for item in equipment],
    })
    return row


def main():
    with SessionLocal() as session:
        specs = session.execute(
            select(Spec.class_key, Spec.spec_key, Spec.class_name_zh_cn, Spec.spec_name_zh_cn)
            .join(GameVersion)
            .where(GameVersion.is_active.is_(True))
            .order_by(Spec.class_key, Spec.spec_key)
        ).all()
    assert len(specs) == 40, f"expected 40 specs, got {len(specs)}"

    rows = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(audit_spec, tuple(spec)): spec for spec in specs}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in ("spec", "success", "passed", "elapsed_seconds", "error")}, ensure_ascii=False), flush=True)

    rows.sort(key=lambda row: row["spec"])
    report = {
        "patch": "12.1",
        "test_target": "Myth 6/6 drop/tier 334; crafted 331; equal 1:1:1:1 rating target; minimum four tier",
        "summary": {
            "total": len(rows),
            "successful": sum(row["success"] for row in rows),
            "passed": sum(bool(row.get("passed")) for row in rows),
            "failed": [row["spec"] for row in rows if not row.get("passed")],
            "total_elapsed_seconds": round(sum(row["elapsed_seconds"] for row in rows), 2),
        },
        "results": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
