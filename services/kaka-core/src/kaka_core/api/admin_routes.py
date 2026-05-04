from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from kaka_core.admin import service
from kaka_core.config.settings import get_settings
from kaka_core.storage.database import create_session_factory, init_database

LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def verify_admin_access(
    request: Request,
    x_kaka_admin_token: str | None = Header(default=None),
) -> None:
    settings = get_settings().admin
    client_host = request.client.host if request.client else ""

    if settings.local_only and client_host not in LOCAL_CLIENT_HOSTS:
        raise HTTPException(status_code=403, detail="admin api is local-only")

    if not settings.local_only and not settings.api_token:
        raise HTTPException(status_code=403, detail="admin api token is required when local-only is disabled")

    if settings.api_token and not secrets.compare_digest(x_kaka_admin_token or "", settings.api_token):
        raise HTTPException(status_code=401, detail="invalid admin api token")


admin_api_router = APIRouter(
    prefix="/admin/api",
    tags=["admin"],
    dependencies=[Depends(verify_admin_access)],
)


class IdListRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class SetInputStatusRequest(IdListRequest):
    status: str


class MergeCandidatesRequest(IdListRequest):
    apply: bool = False
    limit: int = 50


class SetCandidateStatusRequest(IdListRequest):
    status: str


class SetMemoryStatusRequest(IdListRequest):
    status: str


class CreateMemoryRequest(BaseModel):
    user_id: str
    display_name: str | None = None
    group_id: str | None = None
    private: bool = False
    memory_text: str
    memory_type: str
    confidence: float = 0.8
    source_text: str | None = None
    status: str = "active"
    merge_reason: str | None = None


class UpdateMemoryRequest(BaseModel):
    user_id: str | None = None
    display_name: str | None = None
    group_id: str | None = None
    private: bool = False
    scene_update: bool = False
    memory_text: str | None = None
    memory_type: str | None = None
    confidence: float | None = None
    source_text: str | None = None
    status: str | None = None
    merge_reason: str | None = None


class DeleteMemoriesRequest(IdListRequest):
    confirm: bool = False


class SearchMemoriesRequest(BaseModel):
    user_id: str
    text: str
    group_id: str | None = None
    private: bool = False
    limit: int = 5
    pool_size: int = 300
    min_score: float = 1.0
    memory_type: str | None = None


class ReplyContextPreviewRequest(BaseModel):
    user_id: str
    text: str
    group_id: str | None = None
    private: bool = False
    display_name: str | None = None


def get_admin_session() -> Iterator[Session]:
    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        yield session


def build_filters(
    *,
    ids: str | None = None,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    memory_type: str | None = None,
    group_id: str | None = None,
    user_id: str | None = None,
    target_date: str | None = None,
    scene_type: str | None = None,
    reply_state: str | None = None,
    output_origin: str | None = None,
    output_reason: str | None = None,
) -> service.ListFilters:
    try:
        parsed_ids = service.parse_ids(ids)
        parsed_date = service.parse_date(target_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.ListFilters(
        limit=service.clamp_limit(limit),
        offset=service.clamp_offset(offset),
        ids=parsed_ids,
        status=service.normalize_text(status),
        memory_type=service.normalize_text(memory_type),
        group_id=service.normalize_text(group_id),
        user_id=service.normalize_text(user_id),
        target_date=parsed_date,
        scene_type=service.normalize_text(scene_type),
        reply_state=service.normalize_text(reply_state),
        output_origin=service.normalize_text(output_origin),
        output_reason=service.normalize_text(output_reason),
    )


SessionDep = Annotated[Session, Depends(get_admin_session)]
IdsQuery = Annotated[str | None, Query(description="Comma separated numeric IDs")]


@admin_api_router.get("/summary")
def summary(session: SessionDep) -> dict:
    return service.get_admin_summary(session)


@admin_api_router.get("/conversations")
def conversations(
    session: SessionDep,
    ids: IdsQuery = None,
    limit: int = 50,
    group_id: str | None = None,
    user_id: str | None = None,
    date: str | None = None,
    scene_type: str | None = None,
    reply_state: str | None = None,
    output_origin: str | None = None,
    output_reason: str | None = None,
) -> dict:
    filters = build_filters(
        ids=ids,
        limit=limit,
        group_id=group_id,
        user_id=user_id,
        target_date=date,
        scene_type=scene_type,
        reply_state=reply_state,
        output_origin=output_origin,
        output_reason=output_reason,
    )
    return service.list_conversations(session, filters)


@admin_api_router.get("/inputs")
def inputs(
    session: SessionDep,
    ids: IdsQuery = None,
    limit: int = 50,
    status: str | None = "not_analyzed",
    group_id: str | None = None,
    user_id: str | None = None,
    date: str | None = None,
    scene_type: str | None = None,
) -> dict:
    filters = build_filters(
        ids=ids,
        limit=limit,
        status=status,
        group_id=group_id,
        user_id=user_id,
        target_date=date,
        scene_type=scene_type,
    )
    return service.list_inputs(session, filters)


@admin_api_router.get("/inputs/analysis-preview")
def input_analysis_preview(
    session: SessionDep,
    ids: IdsQuery = None,
    limit: int = 50,
    status: str | None = "not_analyzed",
    group_id: str | None = None,
    user_id: str | None = None,
    date: str | None = None,
    scene_type: str | None = None,
) -> dict:
    filters = build_filters(
        ids=ids,
        limit=limit,
        status=status,
        group_id=group_id,
        user_id=user_id,
        target_date=date,
        scene_type=scene_type,
    )
    return service.preview_input_analysis(session, filters)


@admin_api_router.post("/inputs/mark-skipped")
def mark_inputs_skipped(request: IdListRequest, session: SessionDep) -> dict:
    result = service.mark_inputs_skipped(session, tuple(request.ids))
    session.commit()
    return result


@admin_api_router.post("/inputs/status")
def update_input_status(request: SetInputStatusRequest, session: SessionDep) -> dict:
    try:
        result = service.set_input_status(session, tuple(request.ids), request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return result


@admin_api_router.get("/candidates")
def candidates(
    session: SessionDep,
    ids: IdsQuery = None,
    limit: int = 50,
    status: str | None = "pending",
    memory_type: str | None = None,
    group_id: str | None = None,
    user_id: str | None = None,
    date: str | None = None,
    scene_type: str | None = None,
) -> dict:
    filters = build_filters(
        ids=ids,
        limit=limit,
        status=status,
        memory_type=memory_type,
        group_id=group_id,
        user_id=user_id,
        target_date=date,
        scene_type=scene_type,
    )
    return service.list_candidates(session, filters)


@admin_api_router.post("/candidates/merge")
def merge_candidates(request: MergeCandidatesRequest, session: SessionDep) -> dict:
    result = service.merge_candidates(
        session,
        tuple(request.ids),
        apply=request.apply,
        limit=service.clamp_limit(request.limit),
    )
    if request.apply:
        session.commit()
    return result


@admin_api_router.post("/candidates/status")
def update_candidate_status(request: SetCandidateStatusRequest, session: SessionDep) -> dict:
    try:
        result = service.set_candidate_status(session, tuple(request.ids), request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return result


@admin_api_router.get("/memories")
def memories(
    session: SessionDep,
    ids: IdsQuery = None,
    limit: int = 50,
    offset: int = 0,
    status: str | None = "active",
    memory_type: str | None = None,
    group_id: str | None = None,
    user_id: str | None = None,
    date: str | None = None,
    scene_type: str | None = None,
) -> dict:
    filters = build_filters(
        ids=ids,
        limit=limit,
        offset=offset,
        status=status,
        memory_type=memory_type,
        group_id=group_id,
        user_id=user_id,
        target_date=date,
        scene_type=scene_type,
    )
    return service.list_memories(session, filters)


@admin_api_router.post("/memories/status")
def update_memory_status(request: SetMemoryStatusRequest, session: SessionDep) -> dict:
    try:
        result = service.set_memory_status(session, tuple(request.ids), request.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return result


@admin_api_router.post("/memories")
def create_memory(request: CreateMemoryRequest, session: SessionDep) -> dict:
    try:
        item = service.create_manual_memory(
            session,
            user_id=request.user_id,
            display_name=request.display_name,
            group_id=request.group_id,
            private=request.private,
            memory_text=request.memory_text,
            memory_type=request.memory_type,
            confidence=request.confidence,
            source_text=request.source_text,
            status=request.status,
            merge_reason=request.merge_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return {"item": item}


@admin_api_router.patch("/memories/{memory_id}")
def update_memory(memory_id: int, request: UpdateMemoryRequest, session: SessionDep) -> dict:
    try:
        item = service.update_memory(
            session,
            memory_id,
            user_id=request.user_id,
            display_name=request.display_name,
            group_id=request.group_id,
            private=request.private,
            scene_update=request.scene_update,
            memory_text=request.memory_text,
            memory_type=request.memory_type,
            confidence=request.confidence,
            source_text=request.source_text,
            status=request.status,
            merge_reason=request.merge_reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return {"item": item}


@admin_api_router.post("/memories/delete")
def delete_memories(request: DeleteMemoriesRequest, session: SessionDep) -> dict:
    if not request.confirm:
        raise HTTPException(status_code=400, detail="delete requires confirm=true")
    result = service.delete_memories(session, tuple(request.ids))
    session.commit()
    return result


@admin_api_router.post("/memories/search")
def memory_search(request: SearchMemoriesRequest, session: SessionDep) -> dict:
    return service.search_memories(
        session,
        user_id=request.user_id,
        text=request.text,
        group_id=request.group_id,
        private=request.private,
        limit=service.clamp_limit(request.limit, default=5, maximum=20),
        pool_size=service.clamp_limit(request.pool_size, default=300, maximum=1000),
        min_score=request.min_score,
        memory_type=service.normalize_text(request.memory_type),
    )


@admin_api_router.post("/reply-context/preview")
def reply_context_preview(request: ReplyContextPreviewRequest) -> dict:
    return service.preview_reply_context(
        user_id=request.user_id,
        text=request.text,
        group_id=request.group_id,
        private=request.private,
        display_name=service.normalize_text(request.display_name),
    )


def mount_web_console(app) -> None:
    repo_root = Path(__file__).resolve().parents[5]
    dist_dir = repo_root / "apps" / "web-console" / "dist"
    assets_dir = dist_dir / "assets"

    if assets_dir.exists():
        app.mount(
            "/admin/assets",
            StaticFiles(directory=assets_dir),
            name="admin-assets",
        )

    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    def admin_index(path: str = ""):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="admin api route not found")

        index_file = dist_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse(
            """
            <html>
              <head><title>卡咔管理</title></head>
              <body style="font-family: sans-serif; padding: 32px">
                <h1>卡咔管理平台</h1>
                <p>Web console has not been built yet.</p>
                <p>Run <code>npm install</code> and <code>npm run build</code> in
                <code>apps/web-console</code>, then restart kaka-core.</p>
              </body>
            </html>
            """,
            status_code=200,
        )
