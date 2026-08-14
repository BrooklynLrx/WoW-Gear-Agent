"""FastAPI entry point for the WoW Builder Agent."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.builder_agent import (
    BuildConstraintsPatch,
    BuildObjective,
    BuildSessionState,
    BuilderAgentSession,
    EquippedItem,
)


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


class BuilderReply(BaseModel):
    message: str
    proposal: dict[str, Any] | None
    state: BuildSessionState
    tool_trace: list[dict[str, Any]]


@dataclass
class SessionEntry:
    builder: BuilderAgentSession
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ponytail: in-memory sessions are enough for local frontend development; move to MySQL when login ships.
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
    return SessionResponse(session_id=session_id, state=entry.builder.build_state)


@app.patch("/api/v1/builder/sessions/{session_id}", response_model=SessionResponse)
async def update_session(session_id: str, body: StatePatch) -> SessionResponse:
    entry = get_session(session_id)
    async with entry.lock:
        result = entry.builder.update_build_state(**body.model_dump(exclude_none=True))
    return SessionResponse(session_id=session_id, state=result["state"])


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
