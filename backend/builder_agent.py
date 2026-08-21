"""One stateful AgentScope agent for the equipment Builder."""

import asyncio
import os
from typing import Literal

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import OpenAICredential
from agentscope.event import (
    TextBlockDeltaEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
)
from agentscope.message import Msg, TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, Toolkit
from agentscope.types import ReplyFinishedReason
from pydantic import BaseModel, Field, model_validator

from backend.builder_tools import calculate_stats, search_items_for_spec
from backend.db import load_local_env
from backend.loadout_optimizer import optimize_loadout


StatKey = Literal["critical_strike", "haste", "mastery", "versatility"]
Rule = Literal[
    "rating_ratio",
    "sheet_percent",
    "sheet_percent_range",
    "at_least",
    "at_most",
    "minimize",
    "maximize",
    "increase",
    "decrease",
    "remainder",
]


class EquippedItem(BaseModel):
    item_id: int
    item_level: int = 334
    gems: list[int] = Field(default_factory=list)
    crafted_secondary_stats: dict[StatKey, int] = Field(default_factory=dict)
    catalyst_tier_item_id: int | None = None
    equipped_slot: Literal["weapon", "off_hand"] | None = None


class BuildObjective(BaseModel):
    rule: Rule
    stat: StatKey | None = None
    weights: dict[StatKey, float] | None = None
    target: float | None = None
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def check_shape(self):
        if self.rule == "rating_ratio":
            if not self.weights or any(value <= 0 for value in self.weights.values()):
                raise ValueError("rating_ratio requires positive named weights")
        elif not self.stat:
            raise ValueError(f"{self.rule} requires stat")
        if self.rule == "sheet_percent" and self.target is None:
            raise ValueError("sheet_percent requires target")
        if self.rule == "sheet_percent_range":
            if self.minimum is None or self.maximum is None or self.minimum > self.maximum:
                raise ValueError("sheet_percent_range requires minimum <= maximum")
        return self


class BuildConstraints(BaseModel):
    minimum_tier_pieces: int = Field(default=0, ge=0, le=5)
    locked_slots: list[str] = Field(default_factory=list)
    locked_item_ids: list[int] = Field(default_factory=list)
    allow_crafted: bool = True
    excluded_instances: list[str] = Field(default_factory=list)
    require_complete: bool = True
    use_bis_trinkets: bool = True


class BuildConstraintsPatch(BaseModel):
    minimum_tier_pieces: int | None = Field(default=None, ge=0, le=5)
    locked_slots: list[str] | None = None
    locked_item_ids: list[int] | None = None
    allow_crafted: bool | None = None
    excluded_instances: list[str] | None = None
    require_complete: bool | None = None
    use_bis_trinkets: bool | None = None


class BuildSessionState(BaseModel):
    class_key: str | None = None
    spec_key: str | None = None
    equipment: list[EquippedItem] = Field(default_factory=list)
    consumable_ids: list[int] = Field(default_factory=list)
    objectives: list[BuildObjective] = Field(default_factory=list)
    constraints: BuildConstraints = Field(default_factory=BuildConstraints)


class AllowedFunctionTool(FunctionTool):
    """Local Builder tools are explicitly safe for automatic execution."""

    async def check_permissions(self, *_args, **_kwargs):
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="Local Builder state and read-only calculation are allowed.",
        )


def safe_reply_text(message: Msg | None, proposal: dict | None) -> str:
    if message is None:
        return ""
    if message.finished_reason == ReplyFinishedReason.EXCEED_MAX_ITERS:
        return "配装方案已生成，请在下方选择。" if proposal else "这次请求包含的步骤过多，请拆成两条消息重试。"
    return "".join(block.text for block in message.content if hasattr(block, "text"))


def requests_optimization(text: str) -> bool:
    return any(marker in text for marker in ("配一套", "帮我配", "配装方案", "生成方案", "自动配装"))


SYSTEM_PROMPT = """你是魔兽世界12.1装备 Builder Agent。你的职责是维护用户给出的配装状态，调用工具计算，并用中文解释结果。

严格规则：
1. 不读取、套用或暗示任何职业预设绿字推荐。目标完全来自用户。
2. 职业专精只用于装备合法性和精通系数。
3. 必须区分绿字比例（rating_ratio）与角色面板百分比（sheet_percent/range）；二者可以同时存在。
4. 职业和专精由前端创建会话时预先固定。不要询问、推断或修改它们；用户提供装备、消耗品、目标或限制后，先调用 update_build_state 保存。
5. 所有属性数值必须来自 calculate_current_stats；禁止心算、估算或编造物品、装等、掉落。
6. 只有无歧义时才解析。例如用户只说“3:3:1:3”却未说明属性顺序，必须询问。
7. 自动换装由确定性工具完成；模型只负责理解用户目标、调用工具和解释工具返回，不得自行计算或编造配装。
8. 缺少计算所需的职业、专精或装备时，只询问缺少的信息。当前装备必须来自 SimC 解析结果，或 item_id + item_level；不要要求用户手填装备绿字。
9. 武器附魔和触发型属性不计入静态绿字；基础只考虑5%暴击、8%精通及专精精通系数。
10. 装备展示必须调用 search_items。该工具已绑定当前专精，不得声称其他职业装备可用。
11. current_sockets 才是当前孔数；maximum_user_selected_sockets 只是用户可手动选择的上限，绝不能说成装备自带孔。
12. 用户要求自动配装时必须调用 optimize_current_loadout。它返回前不得自行挑选、替换或排序装备。
13. 自动配装候选固定为普通/M7/M8装备334和制造331，不使用9/6装等。套装不是另一件候选装备，而是选装完成后给四件可催化装备添加的身份；转化不改变属性、装等或特效。
14. 老七/老八的非饰品特效装备是最高优先级；饰品只走专精BIS。其后依次为普通团本/大秘境装备、最多两件带美化的制造装备、昂贵的团本小怪装绑。制造装备优先披风、护腕、腰带等小部位；解释方案时说明331装等代价。展示 is_final_boss_drop 时必须注明“尾王掉落，获取难度高”。
15. 用户未指定合剂时，优化器应自动选择一瓶最高品质单绿字合剂并计入属性；宝石不自动选择。
16. 套装必须说明 tier_acquisition_method；转化套装仍展示原装备名称和来源，并注明催化后的套装名称，不能把它说成属性不同的新装备。
17. optimize_current_loadout 返回的是前端配装提案。不得把提案再次调用 update_build_state 写入当前装备；前端负责应用用户选择的方案。
18. 用户询问当前装备是否完整、是否合法或当前面板属性时，必须调用 calculate_current_stats；仅调用 get_build_state 不足以声称校验通过，也不得沿用上一份提案的数值。
19. solutions 数组顺序就是最终推荐顺序。不得自行计算、改名或展示综合评分；score 只供程序内部比较属性偏差。
20. optimize_current_loadout 返回后直接解释并结束回复；不要重复调用任何工具，也不要重新验证同一份方案。
"""


class BuilderAgentSession:
    def __init__(self, full_spec_key: str, agent_state=None):
        from backend.loadout_validator import rules
        if full_spec_key not in rules()["specs"]:
            raise ValueError(f"unknown spec: {full_spec_key}")
        class_key, spec_key = full_spec_key.split(".", 1)
        if isinstance(agent_state, dict):
            agent_state = AgentState.model_validate(agent_state)
        self.build_state = BuildSessionState(class_key=class_key, spec_key=spec_key)
        self.tool_trace = []
        self.last_optimization_result = None
        toolkit = Toolkit(tools=[
            AllowedFunctionTool(self._update_build_state_tool, name="update_build_state", is_read_only=False),
            AllowedFunctionTool(self.get_build_state, is_read_only=True),
            AllowedFunctionTool(self._calculate_current_stats_tool, name="calculate_current_stats", is_read_only=True),
            AllowedFunctionTool(self._search_items_tool, name="search_items", is_read_only=True),
            AllowedFunctionTool(self._optimize_current_loadout_tool, name="optimize_current_loadout", is_read_only=True),
        ])

        load_local_env()
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        model = OpenAIChatModel(
            credential=OpenAICredential(
                api_key=api_key,
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            ),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            parameters=OpenAIChatModel.Parameters(
                temperature=0,
                parallel_tool_calls=False,
            ),
            extra_body={"thinking": {"type": "disabled"}},
            stream=True,
        )
        self.agent = Agent(
            name="wow_builder",
            system_prompt=SYSTEM_PROMPT,
            model=model,
            toolkit=toolkit,
            state=agent_state,
            react_config=ReActConfig(max_iters=12),
        )

    def export_agent_state(self) -> dict:
        """Serialize conversation context, including AgentScope summaries."""
        return self.agent.state.model_dump(mode="json")

    def update_build_state(
        self,
        equipment: list[EquippedItem] | None = None,
        consumable_ids: list[int] | None = None,
        objectives: list[BuildObjective] | None = None,
        constraints: BuildConstraintsPatch | None = None,
    ) -> dict:
        """Update only the provided fields in the current Builder session.

        Args:
            equipment: Full current equipment list; replaces the old list.
            consumable_ids: Full flask and enchant ID list; replaces the old list.
            objectives: Full list of user-defined stat objectives; replaces the old list.
            constraints: Constraint fields to merge with existing constraints.
        """
        current = self.build_state.model_dump()
        patch = {
            "equipment": [item.model_dump() if isinstance(item, BaseModel) else item for item in equipment] if equipment is not None else None,
            "consumable_ids": consumable_ids,
            "objectives": [item.model_dump() if isinstance(item, BaseModel) else item for item in objectives] if objectives is not None else None,
        }
        current.update({key: value for key, value in patch.items() if value is not None})
        if constraints is not None:
            constraint_patch = constraints.model_dump(exclude_none=True) if isinstance(constraints, BaseModel) else constraints
            current["constraints"] = {**current["constraints"], **constraint_patch}
        candidate = BuildSessionState.model_validate(current)
        if candidate.equipment:
            validation = calculate_stats(
                candidate.class_key,
                candidate.spec_key,
                [item.model_dump() for item in candidate.equipment],
                candidate.consumable_ids,
                require_complete=False,
            )
            if not validation["success"]:
                result = {
                    "success": False,
                    "error": "invalid_build_state",
                    "validation": validation.get("validation"),
                }
                if hasattr(self, "tool_trace"):
                    self.tool_trace.append({"tool": "update_build_state", "success": False})
                return result
        self.build_state = candidate
        result = {"success": True, "state": self.build_state.model_dump()}
        if hasattr(self, "tool_trace"):
            self.tool_trace.append({"tool": "update_build_state", "success": True})
        return result

    def get_build_state(self) -> dict:
        """Return the complete current Builder session state."""
        if hasattr(self, "tool_trace"):
            self.tool_trace.append({"tool": "get_build_state", "success": True})
        return self.build_state.model_dump()

    def calculate_current_stats(self) -> dict:
        """Validate and calculate the equipment stored in the current Builder session."""
        state = self.build_state
        missing = [name for name in ("class_key", "spec_key") if not getattr(state, name)]
        if not state.equipment:
            missing.append("equipment")
        if missing:
            result = {"success": False, "error": "missing_state", "missing": missing}
        else:
            result = calculate_stats(
                state.class_key,
                state.spec_key,
                [item.model_dump() for item in state.equipment],
                state.consumable_ids,
                state.constraints.require_complete,
            )
        if hasattr(self, "tool_trace"):
            self.tool_trace.append({"tool": "calculate_current_stats", "success": result.get("success", False)})
        return result

    def search_items(
        self,
        slot_key: str | None = None,
        name: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search equippable items for the specialization fixed by the frontend.

        Args:
            slot_key: Canonical slot such as head, chest, finger, trinket or weapon.
            name: Optional Chinese or English item-name substring.
            limit: Maximum number of results, from 1 to 50.
        """
        state = self.build_state
        return search_items_for_spec(
            state.class_key,
            state.spec_key,
            slot_key=slot_key,
            item_level=334,
            name=name,
            limit=limit,
        )

    def optimize_current_loadout(
        self,
        solution_count: int = 3,
    ) -> dict:
        """Generate complete legal loadouts for the user's stored objectives and constraints.

        Args:
            solution_count: Number of best solutions to return, from 1 to 5.
        """
        state = self.build_state
        result = optimize_loadout(
            state.class_key,
            state.spec_key,
            [value.model_dump() for value in state.objectives],
            state.constraints.model_dump(),
            [value.model_dump() for value in state.equipment],
            state.consumable_ids,
            334,
            solution_count,
        )
        self.last_optimization_result = result
        if hasattr(self, "tool_trace"):
            self.tool_trace.append({"tool": "optimize_current_loadout", "success": result.get("success", False), "solution_count": len(result.get("solutions", []))})
        return result

    async def _update_build_state_tool(
        self,
        equipment: list[EquippedItem] | None = None,
        consumable_ids: list[int] | None = None,
        objectives: list[BuildObjective] | None = None,
        constraints: BuildConstraintsPatch | None = None,
    ) -> dict:
        """Update the current Builder state without blocking other conversations."""
        return await asyncio.to_thread(
            self.update_build_state,
            equipment,
            consumable_ids,
            objectives,
            constraints,
        )

    async def _calculate_current_stats_tool(self) -> dict:
        """Calculate the current equipment without blocking other conversations."""
        return await asyncio.to_thread(self.calculate_current_stats)

    async def _search_items_tool(
        self,
        slot_key: str | None = None,
        name: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search usable items without blocking other conversations."""
        return await asyncio.to_thread(self.search_items, slot_key, name, limit)

    async def _optimize_current_loadout_tool(self, solution_count: int = 3) -> dict:
        """Optimize a loadout without blocking other conversations."""
        return await asyncio.to_thread(self.optimize_current_loadout, solution_count)

    async def reply(self, text: str) -> Msg:
        return await self.agent.reply(
            Msg(name="user", role="user", content=[TextBlock(text=text)]),
        )

    async def reply_payload(self, text: str) -> dict:
        """Return prose plus the optimizer's canonical JSON proposal for the frontend."""
        self.last_optimization_result = None
        trace_start = len(self.tool_trace)
        message = await self.reply(text)
        if self.last_optimization_result is None and self.build_state.objectives and requests_optimization(text):
            await self._optimize_current_loadout_tool()
        return {
            "message": safe_reply_text(message, self.last_optimization_result),
            "proposal": self.last_optimization_result,
            "state": self.build_state.model_dump(),
            "tool_trace": list(self.tool_trace[trace_start:]),
        }

    async def stream_reply_payload(self, text: str):
        """Yield safe UI events, followed by the canonical proposal and state."""
        self.last_optimization_result = None
        trace_start = len(self.tool_trace)
        tool_names = {}
        final_message = None
        yield {"event": "status", "data": {"message": "正在理解配装要求"}}
        async for chunk in self.agent.reply_stream(
            Msg(name="user", role="user", content=[TextBlock(text=text)]),
            yield_final_msg=True,
        ):
            if isinstance(chunk, TextBlockDeltaEvent):
                yield {"event": "text_delta", "data": {"text": chunk.delta}}
            elif isinstance(chunk, ToolCallStartEvent):
                tool_names[chunk.tool_call_id] = chunk.tool_call_name
                yield {
                    "event": "tool_start",
                    "data": {"tool": chunk.tool_call_name},
                }
            elif isinstance(chunk, ToolResultEndEvent):
                state = getattr(chunk.state, "value", chunk.state)
                yield {
                    "event": "tool_result",
                    "data": {
                        "tool": tool_names.get(chunk.tool_call_id, "unknown"),
                        "success": state == "success",
                    },
                }
            elif isinstance(chunk, Msg):
                final_message = chunk

        if self.last_optimization_result is None and self.build_state.objectives and requests_optimization(text):
            yield {"event": "status", "data": {"message": "正在运行确定性配装优化器"}}
            yield {"event": "tool_start", "data": {"tool": "optimize_current_loadout"}}
            result = await self._optimize_current_loadout_tool()
            yield {"event": "tool_result", "data": {"tool": "optimize_current_loadout", "success": result.get("success", False)}}

        message = safe_reply_text(final_message, self.last_optimization_result)
        yield {"event": "proposal", "data": self.last_optimization_result}
        yield {"event": "state", "data": self.build_state.model_dump()}
        yield {
            "event": "done",
            "data": {
                "message": message,
                "tool_trace": list(self.tool_trace[trace_start:]),
            },
        }
