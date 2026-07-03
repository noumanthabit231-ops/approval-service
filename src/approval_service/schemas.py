"""Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────

SOURCE_TYPES = {"publication", "scenario", "edit", "external"}
STATUSES = {"pending", "approved", "rejected", "cancelled"}
FINAL_STATUSES = {"approved", "rejected", "cancelled"}
ACTIONS = {"approval:read", "approval:create", "approval:decide", "approval:cancel"}


# ── Request schemas ────────────────────────────────────

class CreateRequest(BaseModel):
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    reviewer_user_ids: list[str] = Field(default_factory=list, alias="reviewerUserIds")
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey", max_length=128)


class DecideRequest(BaseModel):
    comment: str = ""


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


# ── Response schemas ───────────────────────────────────

class AuditEntryOut(BaseModel):
    action: str
    actor: str
    details: dict | None = None
    created_at: datetime = Field(alias="createdAt")


class ApprovalRequestOut(BaseModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    title: str
    description: str
    reviewer_user_ids: list[str] = Field(alias="reviewerUserIds")
    status: str
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    audit_entries: list[AuditEntryOut] = Field(default_factory=list, alias="auditEntries")


class ApprovalRequestListItem(BaseModel):
    id: str
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    title: str
    status: str
    reviewer_user_ids: list[str] = Field(alias="reviewerUserIds")
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


class PaginatedResponse(BaseModel):
    items: list[ApprovalRequestListItem]
    total: int


class ErrorResponse(BaseModel):
    detail: str
