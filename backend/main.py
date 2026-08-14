"""FastAPI entry point for the WoW Builder Agent."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from backend.builder_agent import (
    BuildConstraintsPatch,
    BuildObjective,
    BuildSessionState,
    BuilderAgentSession,
    EquippedItem,
)
from backend.db import SessionLocal
from backend.models import Loadout


logger = logging.getLogger(__name__)


class CreateSessionRequest(BaseModel):
    spec: str = Field(examples=["paladin.holy"])


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


def create_builder_session(spec: str) -> BuilderAgentSession:
    return BuilderAgentSession(spec)


def get_session(session_id: str) -> SessionEntry:
    entry = sessions.get(session_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="builder_session_not_found")
    return entry


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


@app.patch("/api/v1/builder/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: StatePatch) -> SessionResponse:
    entry = get_session(session_id)
    async with entry.lock:
        result = entry.builder.update_build_state(**body.model_dump(exclude_none=True))
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
        async with entry.lock:
            payload = await entry.builder.reply_payload(body.message)
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
        try:
            async with entry.lock:
                async for chunk in entry.builder.stream_reply_payload(body.message):
                    yield sse(chunk["event"], chunk["data"])
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
