"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from . import service
from .config import settings
from .database import async_session_factory, engine, get_db
from .dependencies import AuthContext, get_auth_context
from .models import Base
from .schemas import (
    ApprovalRequestListItem,
    ApprovalRequestOut,
    CancelRequest,
    CreateRequest,
    DecideRequest,
    ErrorResponse,
    PaginatedResponse,
    RejectRequest,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup, close connections on shutdown."""
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")
    yield
    await engine.dispose()


app = FastAPI(
    title="Approval Service",
    version="0.1.0",
    lifespan=lifespan,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


# ── Health / Readiness ──────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    try:
        from sqlalchemy import text
        async with async_session_factory() as s:
            await s.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database not reachable")


# ── Approval Requests ───────────────────────────────────

@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalRequestOut,
)
async def create_approval_request(
    workspace_id: str,
    body: CreateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth.require("approval:create")
    try:
        req = await service.create_request(db, workspace_id, auth.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_out(req)


@app.get(
    "/api/v1/workspaces/{workspace_id}/approval-requests",
    response_model=PaginatedResponse,
)
async def list_approval_requests(
    workspace_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    offset: int = 0,
    limit: int = 50,
):
    auth.require("approval:read")
    items, total = await service.get_requests(db, workspace_id, status_filter, offset, limit)
    return PaginatedResponse(
        items=[_to_list_item(r) for r in items],
        total=total,
    )


@app.get(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}",
    response_model=ApprovalRequestOut,
)
async def get_approval_request(
    workspace_id: str,
    request_id: str,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth.require("approval:read")
    req = await service.get_request(db, request_id, workspace_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    return _to_out(req)


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/approve",
    response_model=ApprovalRequestOut,
)
async def approve_request(
    workspace_id: str,
    request_id: str,
    body: DecideRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth.require("approval:decide")
    req = await service.get_request(db, request_id, workspace_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        req = await service.approve_request(db, req, auth.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _to_out(req)


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/reject",
    response_model=ApprovalRequestOut,
)
async def reject_request(
    workspace_id: str,
    request_id: str,
    body: RejectRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth.require("approval:decide")
    req = await service.get_request(db, request_id, workspace_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        req = await service.reject_request(db, req, auth.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _to_out(req)


@app.post(
    "/api/v1/workspaces/{workspace_id}/approval-requests/{request_id}/cancel",
    response_model=ApprovalRequestOut,
)
async def cancel_request(
    workspace_id: str,
    request_id: str,
    body: CancelRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    auth.require("approval:cancel")
    req = await service.get_request(db, request_id, workspace_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    try:
        req = await service.cancel_request(db, req, auth.user_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _to_out(req)


# ── Response builders ───────────────────────────────────

def _to_out(req) -> ApprovalRequestOut:
    # Safely read audit entries — they MUST be eager-loaded by the service layer.
    try:
        entries = list(req.audit_entries) if req.audit_entries else []
    except Exception:
        entries = []
    return ApprovalRequestOut(
        id=req.id,
        workspaceId=req.workspace_id,
        sourceType=req.source_type,
        sourceId=req.source_id,
        title=req.title,
        description=req.description,
        reviewerUserIds=req.reviewer_user_ids,
        status=req.status,
        createdBy=req.created_by,
        createdAt=req.created_at,
        updatedAt=req.updated_at,
        auditEntries=[
            {
                "action": e.action,
                "actor": e.actor,
                "details": e.details,
                "createdAt": e.created_at,
            }
            for e in entries
        ],
    )


def _to_list_item(req) -> ApprovalRequestListItem:
    return ApprovalRequestListItem(
        id=req.id,
        sourceType=req.source_type,
        sourceId=req.source_id,
        title=req.title,
        status=req.status,
        reviewerUserIds=req.reviewer_user_ids,
        createdBy=req.created_by,
        createdAt=req.created_at,
    )
