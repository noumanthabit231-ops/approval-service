"""Business logic for approval requests — pure functions operating on DB session."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import events
from .models import ApprovalRequest, AuditEntry
from .schemas import (
    FINAL_STATUSES,
    SOURCE_TYPES,
    CancelRequest,
    CreateRequest,
    DecideRequest,
    RejectRequest,
)


def _make_id() -> str:
    return uuid.uuid4().hex[:12]


async def create_request(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    body: CreateRequest,
) -> ApprovalRequest:
    """Create a new approval request. Idempotent by idempotency_key within a workspace."""

    if body.source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid sourceType: {body.source_type}")

    # Idempotency: if key provided and request exists, return existing
    if body.idempotency_key:
        existing = await _find_by_idempotency(db, workspace_id, body.idempotency_key)
        if existing:
            return existing

    req = ApprovalRequest(
        id=_make_id(),
        workspace_id=workspace_id,
        source_type=body.source_type,
        source_id=body.source_id,
        title=body.title,
        description=body.description,
        reviewer_user_ids=body.reviewer_user_ids,
        status="pending",
        idempotency_key=body.idempotency_key,
        created_by=user_id,
    )
    db.add(req)
    await db.flush()

    await _record_audit(db, req, "created", user_id, {"title": body.title})

    # Eager-load audit entries so caller can safely read them
    await db.refresh(req, ["audit_entries"])

    await events.publish(
        "approval_request.created",
        {
            "request_id": req.id,
            "workspace_id": workspace_id,
            "source_type": body.source_type,
            "source_id": body.source_id,
            "created_by": user_id,
        },
    )

    return req


async def get_requests(
    db: AsyncSession,
    workspace_id: str,
    status: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ApprovalRequest], int]:
    """List requests in a workspace, optionally filtered by status."""
    base = select(ApprovalRequest).where(ApprovalRequest.workspace_id == workspace_id)

    if status:
        base = base.where(ApprovalRequest.status == status)

    # Count
    count_result = await db.execute(base)
    total_count = len(count_result.scalars().all())

    # Fetch page
    stmt = base.order_by(ApprovalRequest.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return list(items), total_count


async def get_request(
    db: AsyncSession,
    request_id: str,
    workspace_id: str,
) -> ApprovalRequest | None:
    """Get a single request, scoped to workspace. Eager-loads audit trail."""
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.workspace_id == workspace_id,
        )
        .options(selectinload(ApprovalRequest.audit_entries))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def approve_request(
    db: AsyncSession,
    req: ApprovalRequest,
    user_id: str,
    body: DecideRequest,
) -> ApprovalRequest:
    """Approve a pending request."""
    _ensure_pending(req, "approve")
    return await _finalize(db, req, "approved", user_id, {"comment": body.comment})


async def reject_request(
    db: AsyncSession,
    req: ApprovalRequest,
    user_id: str,
    body: RejectRequest,
) -> ApprovalRequest:
    """Reject a pending request."""
    _ensure_pending(req, "reject")
    return await _finalize(db, req, "rejected", user_id, {"reason": body.reason})


async def cancel_request(
    db: AsyncSession,
    req: ApprovalRequest,
    user_id: str,
    body: CancelRequest,
) -> ApprovalRequest:
    """Cancel a pending request."""
    _ensure_pending(req, "cancel")
    return await _finalize(db, req, "cancelled", user_id, {"reason": body.reason})


# ── helpers ────────────────────────────────────────────

def _ensure_pending(req: ApprovalRequest, action: str) -> None:
    if req.status in FINAL_STATUSES:
        raise ValueError(
            f"Cannot {action}: request {req.id} is already in final state '{req.status}'"
        )


async def _finalize(
    db: AsyncSession,
    req: ApprovalRequest,
    new_status: str,
    user_id: str,
    details: dict,
) -> ApprovalRequest:
    req.status = new_status
    req.updated_at = datetime.now(UTC)
    await db.flush()

    await _record_audit(db, req, new_status, user_id, details)

    # Eager-load audit entries so caller can safely read them
    await db.refresh(req, ["audit_entries"])

    await events.publish(
        "approval_request.status_changed",
        {
            "request_id": req.id,
            "workspace_id": req.workspace_id,
            "new_status": new_status,
            "changed_by": user_id,
        },
    )

    return req


async def _record_audit(
    db: AsyncSession,
    req: ApprovalRequest,
    action: str,
    actor: str,
    details: dict | None,
) -> None:
    entry = AuditEntry(
        request_id=req.id,
        workspace_id=req.workspace_id,
        action=action,
        actor=actor,
        details=details,
    )
    db.add(entry)
    await db.flush()


async def _find_by_idempotency(
    db: AsyncSession,
    workspace_id: str,
    key: str,
) -> ApprovalRequest | None:
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.workspace_id == workspace_id,
            ApprovalRequest.idempotency_key == key,
        )
        .options(selectinload(ApprovalRequest.audit_entries))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
