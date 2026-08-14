#!/usr/bin/env python3
"""Minimal terminal smoke test for the Builder agent."""

import asyncio
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.builder_agent import BuilderAgentSession


def message_text(message):
    return "".join(block.text for block in message.content if hasattr(block, "text"))


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default="mage.arcane")
    args = parser.parse_args()
    session = BuilderAgentSession(args.spec)
    print("Builder Agent 已启动，输入 exit 退出。")
    while text := input("你：").strip():
        if text.lower() in {"exit", "quit"}:
            break
        answer = await session.reply(text)
        print("Agent：", message_text(answer))


if __name__ == "__main__":
    asyncio.run(main())
