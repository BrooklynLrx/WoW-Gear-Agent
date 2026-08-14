#!/usr/bin/env python3
"""Send one real natural-language build request to every specialization agent."""

import asyncio
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from sqlalchemy import select

from backend.builder_agent import BuilderAgentSession
from backend.db import SessionLocal
from backend.models import GameVersion, Spec


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "12.1-all-spec-agent-audit.json"
PROMPT = "按暴击:急速:精通:全能=1:1:1:1，至少四件套，生成一套完整毕业配装。"


def message_text(message):
    return "".join(block.text for block in message.content if hasattr(block, "text"))


def run_agent(spec):
    full_key, name = spec
    started = time.monotonic()
    session = BuilderAgentSession(full_key)
    try:
        async def request():
            payload = await session.reply_payload(PROMPT)
            await asyncio.sleep(0.2)
            return payload

        payload = asyncio.run(request())
        state = payload["state"]
        tools = [entry["tool"] for entry in session.tool_trace]
        proposal = payload["proposal"] or {}
        solutions = proposal.get("solutions", [])
        proposal_equipment_count = len(solutions[0]["equipment"]) if solutions else 0
        passed = (
            "update_build_state" in tools
            and "optimize_current_loadout" in tools
            and bool(state["objectives"])
            and state["constraints"]["minimum_tier_pieces"] >= 4
            and proposal.get("success") is True
            and proposal_equipment_count in {15, 16}
        )
        return {
            "spec": full_key,
            "name_zh_cn": name,
            "success": True,
            "passed": passed,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "prompt": PROMPT,
            "tool_trace": session.tool_trace,
            "proposal_equipment_count": proposal_equipment_count,
            "objectives_after_reply": state["objectives"],
            "constraints_after_reply": state["constraints"],
            "model_response": payload["message"],
        }
    except Exception as exc:
        return {
            "spec": full_key,
            "name_zh_cn": name,
            "success": False,
            "passed": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "prompt": PROMPT,
            "tool_trace": session.tool_trace,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main():
    with SessionLocal() as session:
        specs = [
            (f"{row.class_key}.{row.spec_key}", f"{row.class_name_zh_cn}·{row.spec_name_zh_cn}")
            for row in session.scalars(
                select(Spec).join(GameVersion).where(GameVersion.is_active.is_(True)).order_by(Spec.class_key, Spec.spec_key)
            )
        ]
    assert len(specs) == 40

    rows = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_agent, spec) for spec in specs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in ("spec", "success", "passed", "proposal_equipment_count", "elapsed_seconds", "error")}, ensure_ascii=False), flush=True)

    rows.sort(key=lambda row: row["spec"])
    report = {
        "summary": {
            "total": len(rows),
            "successful_replies": sum(row["success"] for row in rows),
            "passed": sum(row["passed"] for row in rows),
            "failed": [row["spec"] for row in rows if not row["passed"]],
        },
        "results": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
