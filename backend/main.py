"""FastAPI entry point for the WoW Builder Agent."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select

from backend.builder_agent import (
    BuildConstraintsPatch,
    BuildObjective,
    BuildSessionState,
    BuilderAgentSession,
    EquippedItem,
)
from backend.db import SessionLocal
from backend.models import ChatMessage, ChatSession, Loadout
from backend.loot_api import list_instances, list_specs, search_loot
from backend.loadout_optimizer import supplement_catalog


logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    spec: str = Field(examples=["paladin.holy"])


class CreateConversationRequest(BaseModel):
    spec: str | None = Field(default=None, examples=["paladin.holy"])
    title: str | None = Field(default=None, max_length=160)
    loadout_id: int | None = None


class UpdateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class StatePatch(BaseModel):
    equipment: list[EquippedItem] | None = None
    consumable_ids: list[int] | None = None
    objectives: list[BuildObjective] | None = None
    constraints: BuildConstraintsPatch | None = None


class SessionResponse(BaseModel):
    session_id: str
    state: BuildSessionState
    source_loadout_id: int | None = None


class ConversationMessage(BaseModel):
    id: int
    role: str
    content: str
    proposal: dict[str, Any] | None = None
    created_at: datetime


class ConversationSummary(BaseModel):
    id: int
    title: str
    class_key: str
    spec_key: str
    message_count: int
    has_compressed_context: bool
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationSummary):
    session_id: str
    state: BuildSessionState
    source_loadout_id: int | None = None
    messages: list[ConversationMessage]


class BuilderReply(BaseModel):
    message: str
    proposal: dict[str, Any] | None
    state: BuildSessionState
    tool_trace: list[dict[str, Any]]


class SaveLoadoutRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    creator_name: str = Field(min_length=1, max_length=64)
    builder_session_id: str = Field(min_length=1)

    @field_validator("name", "creator_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class UpdateLoadoutRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    creator_name: str | None = Field(default=None, min_length=1, max_length=64)
    builder_session_id: str | None = None
    is_favorite: bool | None = None

    @field_validator("name", "creator_name")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class LoadoutSummary(BaseModel):
    id: int
    name: str
    creator_name: str
    class_key: str
    spec_key: str
    is_favorite: bool
    created_at: datetime
    updated_at: datetime


class LoadoutDetail(LoadoutSummary):
    state: BuildSessionState


@dataclass
class SessionEntry:
    builder: BuilderAgentSession
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    source_loadout_id: int | None = None
    conversation_id: int | None = None


# ponytail: active chats stay in memory; saved loadout snapshots survive in MySQL.
sessions: dict[str, SessionEntry] = {}


app = FastAPI(title="WoW 12.1 Builder API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_builder_session(spec: str, agent_state: dict | None = None) -> BuilderAgentSession:
    return BuilderAgentSession(spec, agent_state) if agent_state else BuilderAgentSession(spec)


def get_session(session_id: str) -> SessionEntry:
    entry = sessions.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="builder_session_not_found")
    return entry


def conversation_session_id(conversation_id: int) -> str:
    return f"chat-{conversation_id}"


def persist_conversation(entry: SessionEntry) -> None:
    if entry.conversation_id is None:
        return
    with SessionLocal.begin() as db:
        conversation = db.get(ChatSession, entry.conversation_id)
        if conversation is None:
            return
        conversation.state_json = entry.builder.build_state.model_dump(mode="json")
        conversation.agent_state_json = entry.builder.export_agent_state()


def ensure_conversation_entry(conversation: ChatSession) -> tuple[str, SessionEntry]:
    if not conversation.class_key or not conversation.spec_key or not conversation.state_json:
        raise HTTPException(status_code=409, detail="conversation_missing_state")
    session_id = conversation_session_id(conversation.id)
    entry = sessions.get(session_id)
    if entry is None:
        builder = create_builder_session(
            f"{conversation.class_key}.{conversation.spec_key}",
            conversation.agent_state_json,
        )
        builder.build_state = BuildSessionState.model_validate(conversation.state_json)
        entry = SessionEntry(
            builder,
            source_loadout_id=conversation.loadout_id,
            conversation_id=conversation.id,
        )
        sessions[session_id] = entry
    return session_id, entry


def conversation_payload(db, conversation: ChatSession) -> ConversationDetail:
    session_id, entry = ensure_conversation_entry(conversation)
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.session_id == conversation.id)
        .order_by(ChatMessage.id)
    ).all()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        class_key=conversation.class_key,
        spec_key=conversation.spec_key,
        message_count=len(rows),
        has_compressed_context=bool(entry.builder.agent.state.summary),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        session_id=session_id,
        state=entry.builder.build_state,
        source_loadout_id=conversation.loadout_id,
        messages=[ConversationMessage(
            id=value.id,
            role=value.role,
            content=value.content,
            proposal=(value.tool_result_json or {}).get("proposal"),
            created_at=value.created_at,
        ) for value in rows],
    )


def loadout_summary(loadout: Loadout) -> LoadoutSummary:
    if not loadout.class_key or not loadout.spec_key:
        raise HTTPException(status_code=409, detail="loadout_missing_spec")
    return LoadoutSummary(
        id=loadout.id,
        name=loadout.name,
        creator_name=loadout.creator_name,
        class_key=loadout.class_key,
        spec_key=loadout.spec_key,
        is_favorite=loadout.is_favorite,
        created_at=loadout.created_at,
        updated_at=loadout.updated_at,
    )


def loadout_detail(loadout: Loadout) -> LoadoutDetail:
    if not loadout.state_json:
        raise HTTPException(status_code=409, detail="loadout_missing_state")
    return LoadoutDetail(
        **loadout_summary(loadout).model_dump(),
        state=BuildSessionState.model_validate(loadout.state_json),
    )


def snapshot_loadout(loadout: Loadout, state: BuildSessionState) -> None:
    loadout.class_key = state.class_key
    loadout.spec_key = state.spec_key
    loadout.target_stats_json = {"objectives": [value.model_dump() for value in state.objectives]}
    loadout.constraints_json = state.constraints.model_dump()
    loadout.state_json = state.model_dump()


def get_loadout(db, loadout_id: int) -> Loadout:
    loadout = db.get(Loadout, loadout_id)
    if loadout is None:
        raise HTTPException(status_code=404, detail="loadout_not_found")
    return loadout


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/catalog/specs")
def catalog_specs() -> list[dict]:
    return list_specs()


@app.get("/api/v1/catalog/gems")
def catalog_gems() -> list[dict]:
    return [value for value in supplement_catalog().values() if value.get("category") in {"gem", "unique_diamond"}]


@app.get("/api/v1/loot/instances")
def loot_instances() -> list[dict]:
    return list_instances()


@app.get("/api/v1/loot/items")
def loot_items(
    item_level: int = 334,
    class_key: str | None = None,
    spec_key: str | None = None,
    slot_key: str | None = None,
    source_type: str | None = None,
    instance_name: str | None = None,
    secondary_stats: list[str] = Query(default=[]),
    secondary_match: str = "all",
    has_special_effect: bool | None = None,
    item_ids: list[int] = Query(default=[]),
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    if secondary_match not in {"all", "any"}:
        raise HTTPException(status_code=422, detail="secondary_match_must_be_all_or_any")
    return search_loot(
        item_level=item_level, class_key=class_key, spec_key=spec_key,
        slot_key=slot_key, source_type=source_type, instance_name=instance_name,
        secondary_stats=secondary_stats, secondary_match=secondary_match,
        has_special_effect=has_special_effect, q=q, item_ids=item_ids, limit=limit, offset=offset,
    )


@app.post("/api/v1/conversations", response_model=ConversationDetail, status_code=201)
def create_conversation(body: CreateConversationRequest) -> ConversationDetail:
    if body.loadout_id is not None:
        with SessionLocal() as db:
            loadout = loadout_detail(get_loadout(db, body.loadout_id))
        spec = f"{loadout.class_key}.{loadout.spec_key}"
        title = body.title or loadout.name
        state = loadout.state
    else:
        if not body.spec:
            raise HTTPException(status_code=422, detail="spec_required")
        spec = body.spec
        title = body.title or "新对话"
        state = None
    try:
        builder = create_builder_session(spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if state is not None:
        builder.build_state = state.model_copy(deep=True)
    with SessionLocal.begin() as db:
        conversation = ChatSession(
            user_id=None,
            loadout_id=body.loadout_id,
            title=title.strip() or "新对话",
            class_key=builder.build_state.class_key,
            spec_key=builder.build_state.spec_key,
            state_json=builder.build_state.model_dump(mode="json"),
            agent_state_json=builder.export_agent_state(),
        )
        db.add(conversation)
        db.flush()
        session_id = conversation_session_id(conversation.id)
        sessions[session_id] = SessionEntry(
            builder,
            source_loadout_id=body.loadout_id,
            conversation_id=conversation.id,
        )
        db.refresh(conversation)
        return conversation_payload(db, conversation)


@app.get("/api/v1/conversations", response_model=list[ConversationSummary])
def list_conversations() -> list[ConversationSummary]:
    with SessionLocal() as db:
        message_count = select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == ChatSession.id
        ).correlate(ChatSession).scalar_subquery()
        statement = select(
            ChatSession.id,
            ChatSession.title,
            ChatSession.class_key,
            ChatSession.spec_key,
            ChatSession.created_at,
            ChatSession.updated_at,
            message_count.label("message_count"),
            func.json_extract(ChatSession.agent_state_json, "$.summary").is_not(None).label("has_compressed_context"),
        ).where(
            ChatSession.class_key.is_not(None),
            ChatSession.spec_key.is_not(None),
            ChatSession.state_json.is_not(None),
        ).order_by(
            ChatSession.updated_at.desc(), ChatSession.id.desc()
        ).with_hint(
            ChatSession, "FORCE INDEX (ix_chat_sessions_updated_at_id)", dialect_name="mysql"
        )
        rows = db.execute(statement).all()
        return [ConversationSummary(**row._mapping) for row in rows]


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationDetail)
def read_conversation(conversation_id: int) -> ConversationDetail:
    with SessionLocal() as db:
        conversation = db.get(ChatSession, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        return conversation_payload(db, conversation)


@app.patch("/api/v1/conversations/{conversation_id}", response_model=ConversationSummary)
def update_conversation(conversation_id: int, body: UpdateConversationRequest) -> ConversationSummary:
    with SessionLocal.begin() as db:
        conversation = db.get(ChatSession, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        conversation.title = body.title
        db.flush()
        db.refresh(conversation)
        detail = conversation_payload(db, conversation)
        return ConversationSummary(**detail.model_dump(exclude={"session_id", "state", "messages"}))


@app.post("/api/v1/conversations/{conversation_id}/clear", response_model=ConversationDetail)
def clear_conversation(conversation_id: int) -> ConversationDetail:
    with SessionLocal.begin() as db:
        conversation = db.get(ChatSession, conversation_id)
        if conversation is None or not conversation.class_key or not conversation.spec_key or not conversation.state_json:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        builder = create_builder_session(f"{conversation.class_key}.{conversation.spec_key}")
        builder.build_state = BuildSessionState.model_validate(conversation.state_json)
        session_id = conversation_session_id(conversation.id)
        sessions[session_id] = SessionEntry(
            builder,
            source_loadout_id=conversation.loadout_id,
            conversation_id=conversation.id,
        )
        db.execute(delete(ChatMessage).where(ChatMessage.session_id == conversation.id))
        conversation.agent_state_json = builder.export_agent_state()
        db.flush()
        db.refresh(conversation)
        return conversation_payload(db, conversation)


@app.delete("/api/v1/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int) -> None:
    with SessionLocal.begin() as db:
        conversation = db.get(ChatSession, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        db.delete(conversation)
    sessions.pop(conversation_session_id(conversation_id), None)


@app.post("/api/v1/builder/sessions", response_model=SessionResponse, status_code=201)
def create_session(body: CreateSessionRequest) -> SessionResponse:
    try:
        builder = create_builder_session(body.spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    session_id = uuid4().hex
    sessions[session_id] = SessionEntry(builder)
    return SessionResponse(session_id=session_id, state=builder.build_state)


@app.get("/api/v1/builder/sessions/{session_id}", response_model=SessionResponse)
def read_session(session_id: str) -> SessionResponse:
    entry = get_session(session_id)
    return SessionResponse(
        session_id=session_id,
        state=entry.builder.build_state,
        source_loadout_id=entry.source_loadout_id,
    )


@app.get("/api/v1/builder/sessions/{session_id}/stats")
async def session_stats(session_id: str) -> dict:
    entry = get_session(session_id)
    async with entry.lock:
        return entry.builder.calculate_current_stats()


@app.patch("/api/v1/builder/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: StatePatch) -> SessionResponse:
    entry = get_session(session_id)
    async with entry.lock:
        result = entry.builder.update_build_state(**body.model_dump(exclude_none=True))
        if not result["success"]:
            raise HTTPException(status_code=422, detail=result.get("validation") or result.get("error"))
        persist_conversation(entry)
    return SessionResponse(
        session_id=session_id,
        state=result["state"],
        source_loadout_id=entry.source_loadout_id,
    )


@app.post("/api/v1/loadouts", response_model=LoadoutDetail, status_code=201)
async def save_loadout(body: SaveLoadoutRequest) -> LoadoutDetail:
    entry = get_session(body.builder_session_id)
    async with entry.lock:
        state = entry.builder.build_state.model_copy(deep=True)
    with SessionLocal.begin() as db:
        loadout = Loadout(
            user_id=None,
            character_id=None,
            name=body.name,
            creator_name=body.creator_name,
            patch="12.1",
            content_type="custom",
            target_type="user",
            target_stats_json={},
            constraints_json={},
            calculated_stats_json=None,
            state_json=None,
            is_favorite=False,
        )
        snapshot_loadout(loadout, state)
        db.add(loadout)
        db.flush()
        db.refresh(loadout)
        result = loadout_detail(loadout)
    entry.source_loadout_id = result.id
    if entry.conversation_id is not None:
        with SessionLocal.begin() as db:
            conversation = db.get(ChatSession, entry.conversation_id)
            if conversation:
                conversation.loadout_id = result.id
    return result


@app.get("/api/v1/loadouts", response_model=list[LoadoutSummary])
def list_loadouts(creator_name: str | None = None) -> list[LoadoutSummary]:
    with SessionLocal() as db:
        query = select(Loadout).where(Loadout.state_json.is_not(None))
        if creator_name:
            query = query.where(Loadout.creator_name == creator_name.strip())
        loadouts = db.scalars(query.order_by(Loadout.updated_at.desc(), Loadout.id.desc())).all()
        return [loadout_summary(value) for value in loadouts]


@app.get("/api/v1/loadouts/{loadout_id}", response_model=LoadoutDetail)
def read_loadout(loadout_id: int) -> LoadoutDetail:
    with SessionLocal() as db:
        return loadout_detail(get_loadout(db, loadout_id))


@app.patch("/api/v1/loadouts/{loadout_id}", response_model=LoadoutDetail)
async def update_loadout(loadout_id: int, body: UpdateLoadoutRequest) -> LoadoutDetail:
    if not body.model_dump(exclude_none=True):
        raise HTTPException(status_code=422, detail="empty_loadout_update")
    entry = get_session(body.builder_session_id) if body.builder_session_id else None
    state = None
    if entry is not None:
        async with entry.lock:
            state = entry.builder.build_state.model_copy(deep=True)
    with SessionLocal.begin() as db:
        loadout = get_loadout(db, loadout_id)
        if body.name is not None:
            loadout.name = body.name
        if body.creator_name is not None:
            loadout.creator_name = body.creator_name
        if body.is_favorite is not None:
            loadout.is_favorite = body.is_favorite
        if state is not None:
            snapshot_loadout(loadout, state)
        db.flush()
        db.refresh(loadout)
        result = loadout_detail(loadout)
    if entry is not None:
        entry.source_loadout_id = loadout_id
        if entry.conversation_id is not None:
            with SessionLocal.begin() as db:
                conversation = db.get(ChatSession, entry.conversation_id)
                if conversation:
                    conversation.loadout_id = loadout_id
    return result


@app.delete("/api/v1/loadouts/{loadout_id}", status_code=204)
def delete_loadout(loadout_id: int) -> None:
    with SessionLocal.begin() as db:
        db.delete(get_loadout(db, loadout_id))


@app.post("/api/v1/loadouts/{loadout_id}/open", response_model=SessionResponse, status_code=201)
def open_loadout(loadout_id: int) -> SessionResponse:
    with SessionLocal() as db:
        detail = loadout_detail(get_loadout(db, loadout_id))
    builder = create_builder_session(f"{detail.class_key}.{detail.spec_key}")
    builder.build_state = detail.state.model_copy(deep=True)
    session_id = uuid4().hex
    sessions[session_id] = SessionEntry(builder, source_loadout_id=loadout_id)
    return SessionResponse(
        session_id=session_id,
        state=builder.build_state,
        source_loadout_id=loadout_id,
    )


@app.post("/api/v1/builder/sessions/{session_id}/messages", response_model=BuilderReply)
async def chat(session_id: str, body: ChatRequest) -> BuilderReply:
    entry = get_session(session_id)
    try:
        if entry.conversation_id is not None:
            with SessionLocal.begin() as db:
                conversation = db.get(ChatSession, entry.conversation_id)
                if conversation and conversation.title == "新对话":
                    conversation.title = body.message.strip()[:36]
                db.add(ChatMessage(session_id=entry.conversation_id, role="user", content=body.message))
        async with entry.lock:
            payload = await entry.builder.reply_payload(body.message)
            persist_conversation(entry)
        if entry.conversation_id is not None:
            with SessionLocal.begin() as db:
                db.add(ChatMessage(
                    session_id=entry.conversation_id,
                    role="assistant",
                    content=payload["message"],
                    tool_result_json={"proposal": payload.get("proposal"), "tool_trace": payload.get("tool_trace", [])},
                ))
        return BuilderReply.model_validate(payload)
    except Exception as exc:
        logger.exception("builder agent failed")
        raise HTTPException(status_code=502, detail="builder_agent_failed") from exc


def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


@app.post("/api/v1/builder/sessions/{session_id}/messages/stream")
async def chat_stream(session_id: str, body: ChatRequest) -> StreamingResponse:
    entry = get_session(session_id)

    async def events():
        assistant_message = ""
        proposal = None
        tool_trace = []
        try:
            if entry.conversation_id is not None:
                with SessionLocal.begin() as db:
                    conversation = db.get(ChatSession, entry.conversation_id)
                    if conversation and conversation.title == "新对话":
                        conversation.title = body.message.strip()[:36]
                    db.add(ChatMessage(session_id=entry.conversation_id, role="user", content=body.message))
            async with entry.lock:
                async for chunk in entry.builder.stream_reply_payload(body.message):
                    if chunk["event"] == "proposal":
                        proposal = chunk["data"]
                    elif chunk["event"] == "done":
                        assistant_message = chunk["data"].get("message", "")
                        tool_trace = chunk["data"].get("tool_trace", [])
                    yield sse(chunk["event"], chunk["data"])
                persist_conversation(entry)
            if entry.conversation_id is not None:
                with SessionLocal.begin() as db:
                    db.add(ChatMessage(
                        session_id=entry.conversation_id,
                        role="assistant",
                        content=assistant_message,
                        tool_result_json={"proposal": proposal, "tool_trace": tool_trace},
                    ))
        except Exception:
            logger.exception("streaming builder agent failed")
            yield sse("error", {"code": "builder_agent_failed"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/v1/builder/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    get_session(session_id)
    del sessions[session_id]
