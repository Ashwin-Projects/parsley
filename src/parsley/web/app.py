"""FastAPI backend for the frontend (``web/API_CONTRACT.md`` on branch ``web-frontend``).

A thin adapter: every sentence goes through ``pipeline.run`` and every answer through
``pipeline.answer``, so a web request gets the same checks as the CLI. Only the semantic
analyzer changes a session (undo replays through it). ``run`` uses the V3 interpreter with its
step budget. A provider is loaded the first time a session asks for ``llm`` or ``hybrid``, so a
rules-only server never reads ``.env``. Errors never carry a stack trace, a request body or a
key: ``_CatchAll`` logs an unexpected failure by type and answers ``internal error``. It is
middleware and not an exception handler because Starlette re-raises after such a handler, and
uvicorn would then log the message, which can hold a sentence.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Callable
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from parsley import pipeline
from parsley.compiler import codegen
from parsley.compiler.ast_nodes import Program
from parsley.compiler.semantic import analyze
from parsley.nlp.candidates import LLM_RULE_ID, MAX_INPUT_CHARS
from parsley.session import Session
from parsley.verify import STEP_LIMIT, Verification, interpreter
from parsley.web.sessions import DEFAULT_CAPACITY, DEFAULT_TTL, SessionStore, WebSession

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
MAX_BODY_BYTES = 8 * 1024
MAX_STATEMENTS = 500  # V3 re-runs the whole session on each sentence, so its cost grows with this
MAX_ID_CHARS = 128

_STATUS = {"ok": "accepted", "needs_clarification": "clarify", "unsupported": "rejected", "error": "error"}
_NO_QUESTION = {"code": "E102", "stage": "ambiguity", "message": "There is no pending question."}

Mode = Literal["rules", "llm", "hybrid"]
Check = Literal["ok", "fail", "skipped"]


class SessionRequest(BaseModel):
    session_id: str = Field(max_length=MAX_ID_CHARS)


class CompileRequest(SessionRequest):
    sentence: str = Field(max_length=MAX_INPUT_CHARS)
    mode: Mode | None = None  # None: the session's mode


class AnswerRequest(SessionRequest):
    answer: str = Field(max_length=MAX_INPUT_CHARS)


class SessionResponse(BaseModel):
    session_id: str


class Checks(BaseModel):
    v1: Check
    v2: Check
    v3: Check


class Question(BaseModel):
    text: str
    options: list[str]
    kind: str


class DiagnosticBody(BaseModel):
    code: str
    stage: str
    message: str


class CompileResponse(BaseModel):
    status: Literal["accepted", "clarify", "rejected", "error"]
    minilang: str | None = None
    understood: str | None = None
    checks: Checks | None = None
    question: Question | None = None
    diagnostics: list[DiagnosticBody]
    suggestion: str | None = None
    source: Literal["rules", "llm"] | None = None
    trace: dict[str, Any] | None = None


class Statement(BaseModel):
    english: str
    minilang: str


class ProgramResponse(BaseModel):
    minilang: str
    statements: list[Statement]


class RunResponse(BaseModel):
    output: list[str]
    variables: dict[str, Any]
    error: str | None = None


class OkResponse(BaseModel):
    ok: bool


class _BodyLimit:
    """Refuse a body over ``limit`` bytes, whether or not it declares its length."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self._app = app
        self._limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self._limit:
            await JSONResponse({"detail": "the request is too large"}, status_code=413)(scope, receive, send)
            return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self._limit:
                raise ValueError("the request is too large")
            return message

        await self._app(scope, limited, send)


class _CatchAll:
    """Stop any unexpected exception here: log its type, answer 500, re-raise nothing."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def tracking(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self._app(scope, receive, tracking)
        except Exception as error:
            logger.error("request failed: %s", type(error).__name__)
            if not started and scope["type"] == "http":
                await JSONResponse({"detail": "internal error"}, status_code=500)(scope, receive, send)


def _load_provider() -> object:
    from parsley.llm.config import load_provider

    return load_provider()


def create_app(
    *, provider: object = None, provider_factory: Callable[[], object] = _load_provider,
    ttl: float = DEFAULT_TTL, capacity: int = DEFAULT_CAPACITY,
) -> FastAPI:
    """The API; ``provider`` overrides the configured one (tests pass a ``FakeProvider``)."""
    app = FastAPI(title="Parsley", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(_CatchAll)  # innermost, so a 500 still gets its CORS headers
    app.add_middleware(_BodyLimit, limit=MAX_BODY_BYTES)
    app.add_middleware(
        CORSMiddleware, allow_origins=list(ALLOWED_ORIGINS), allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.store = SessionStore(ttl, capacity)
    app.state.provider = provider
    app.state.step_limit = STEP_LIMIT
    provider_lock = threading.Lock()

    def get_provider() -> object:
        with provider_lock:
            if app.state.provider is not None:
                return app.state.provider
            built = provider_factory()
            if getattr(built, "error", None) is None:  # a bad configuration is read again next time
                app.state.provider = built
            return built

    def session_for(session_id: str) -> WebSession:
        web = app.state.store.get(session_id)
        if web is None:
            raise HTTPException(404, "unknown or expired session")
        return web

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        too_long = any(e["type"] == "string_too_long" and e["loc"][-1] == "sentence" for e in error.errors())
        detail = f"the sentence is longer than {MAX_INPUT_CHARS} characters" if too_long else "invalid request"
        return JSONResponse({"detail": detail}, status_code=422)

    @app.post("/api/session", response_model=SessionResponse)
    def create_session() -> dict[str, str]:
        return {"session_id": app.state.store.create().id}

    @app.post("/api/compile", response_model=CompileResponse, response_model_exclude_none=True)
    def compile_sentence(body: CompileRequest) -> dict[str, Any]:
        web = session_for(body.session_id)
        with web.lock:
            if len(web.statements) >= MAX_STATEMENTS:
                raise HTTPException(409, f"a session holds at most {MAX_STATEMENTS} statements")
            web.mode = body.mode or web.mode
            source = None if web.mode == "rules" else get_provider()
            result = pipeline.run(body.sentence, web.session, mode=web.mode, provider=source)
            app.state.store.touch(web)
            return _respond(web, result, body.sentence)

    @app.post("/api/answer", response_model=CompileResponse, response_model_exclude_none=True)
    def answer_question(body: AnswerRequest) -> dict[str, Any]:
        web = session_for(body.session_id)
        with web.lock:
            if web.pending is None:
                return {"status": "error", "diagnostics": [_NO_QUESTION]}
            result = pipeline.answer(web.pending, body.answer, web.session)
            return _respond(web, result, web.pending_sentence)

    @app.get("/api/program", response_model=ProgramResponse)
    def show_program(session_id: str) -> dict[str, Any]:
        web = session_for(session_id)
        with web.lock:
            return {
                "minilang": _source(web),
                "statements": [
                    {"english": english, "minilang": codegen.generate(statement)}
                    for english, statement in zip(web.statements, web.session.history, strict=True)
                ],
            }

    @app.post("/api/run", response_model=RunResponse, response_model_exclude_none=True)
    def run_program(body: SessionRequest) -> dict[str, Any]:
        web = session_for(body.session_id)
        with web.lock:
            source = _source(web)
        if not source:
            return {"output": [], "variables": {}}
        variables, output, errors = interpreter.run(source, max_steps=app.state.step_limit)
        return {
            "output": output, "variables": {name: _plain(value) for name, value in variables.items()},
            "error": "; ".join(errors) or None,
        }

    @app.post("/api/undo", response_model=OkResponse)
    def undo(body: SessionRequest) -> dict[str, bool]:
        web = session_for(body.session_id)
        with web.lock:
            web.pending = None
            if web.statements:
                restored = Session()
                for statement in web.session.history[:-1]:
                    analyze(statement, restored)  # only the semantic analyzer writes a session
                web.session = restored
                web.statements.pop()
        return {"ok": True}

    @app.post("/api/reset", response_model=OkResponse)
    def reset(body: SessionRequest) -> dict[str, bool]:
        web = session_for(body.session_id)
        with web.lock:
            web.session, web.statements, web.pending = Session(), [], None
        return {"ok": True}

    return app


def _source(web: WebSession) -> str:
    accepted = tuple(web.session.history)
    return codegen.generate(Program(accepted)) if accepted else ""


def _plain(value: object) -> object:
    """A value JSON can carry: an infinite number travels as text."""
    return str(value) if isinstance(value, float) and not math.isfinite(value) else value


def _respond(web: WebSession, result: pipeline.PipelineResult, sentence: str) -> dict[str, Any]:
    """Remember what the result changes for the session, and shape it for the contract."""
    if result.status == "ok":
        web.statements.append(sentence)
    asking = result.status == "needs_clarification"
    web.pending, web.pending_sentence = (result, sentence) if asking else (None, "")
    chosen = result.trace.chosen
    return {
        "status": _STATUS[result.status],
        "minilang": result.minilang,
        "understood": result.back_translation,
        "checks": None if result.verification is None else _checks(result.verification),
        "question": {"text": result.question, "options": list(result.options),
                     "kind": result.clarification.kind} if asking and result.clarification else None,
        "diagnostics": [{"code": d.code, "stage": d.stage, "message": d.message} for d in result.diagnostics],
        "suggestion": result.suggestion,
        "source": None if chosen is None else "llm" if chosen.rule_id == LLM_RULE_ID else "rules",
        "trace": _trace(result.trace),
    }


def _checks(verification: Verification) -> dict[str, str]:
    def word(match: bool | None) -> str:
        return "skipped" if match is None else "ok" if match else "fail"

    return {
        "v1": "ok" if verification.back_translation else "fail",
        "v2": word(verification.v2_match), "v3": word(verification.v3_match),
    }


def _trace(trace: pipeline.Trace) -> dict[str, Any]:
    """The trace as plain JSON; keys with nothing to say are left out."""
    def candidate(c: Any) -> dict[str, Any]:
        return {"rule_id": c.rule_id, "intent": c.intent, "score": c.score, "notes": list(c.notes)}

    body: dict[str, Any] = {
        "input": trace.input, "normalized": trace.normalized, "decision": trace.decision,
        "candidates": [candidate(c) for c in trace.candidates], "ranked": [candidate(c) for c in trace.ranked],
    }
    if trace.chosen is not None:
        body["chosen"] = candidate(trace.chosen)
    if trace.ast is not None:
        body["ast"] = repr(trace.ast)
    if trace.verification is not None:
        body["verification"] = list(trace.verification.details)
    if trace.llm is not None:
        body["llm"] = {
            "provider": trace.llm.provider, "trigger": trace.llm.trigger,
            "discarded": [{"reason": str(d.reason), "detail": d.detail} for d in trace.llm.discarded],
        }
    return body
