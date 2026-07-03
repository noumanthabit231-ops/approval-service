"""Integration tests for the approval-service API."""

import pytest

from .conftest import AUTH_HEADERS, READ_ONLY_HEADERS, auth_headers

WORKSPACE = "ws_1"
OTHER_WS = "ws_2"
BASE = f"/api/v1/workspaces/{WORKSPACE}/approval-requests"


def _create_body(**overrides):
    return {
        "sourceType": "publication",
        "sourceId": "pub_123",
        "title": "Instagram reel draft",
        "description": "Needs final approval",
        "reviewerUserIds": ["usr_1", "usr_2"],
        **overrides,
    }


# ── Health ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


# ── Create ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_request(client):
    resp = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["sourceType"] == "publication"
    assert data["sourceId"] == "pub_123"
    assert data["workspaceId"] == WORKSPACE
    assert len(data["auditEntries"]) == 1
    assert data["auditEntries"][0]["action"] == "created"


@pytest.mark.asyncio
async def test_create_request_invalid_source_type(client):
    resp = await client.post(
        BASE, json=_create_body(sourceType="invalid"), headers=AUTH_HEADERS
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_idempotency(client):
    body = _create_body(idempotencyKey="key_001")
    r1 = await client.post(BASE, json=body, headers=AUTH_HEADERS)
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    # Same key → same resource
    r2 = await client.post(BASE, json=body, headers=AUTH_HEADERS)
    assert r2.status_code == 201
    assert r2.json()["id"] == id1


# ── Workspace isolation ─────────────────────────────────

@pytest.mark.asyncio
async def test_workspace_isolation(client):
    await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)

    # Other workspace should not see it
    other_url = f"/api/v1/workspaces/{OTHER_WS}/approval-requests"
    resp = await client.get(other_url, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── Get / List ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_request(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    resp = await client.get(f"{BASE}/{req_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == req_id


@pytest.mark.asyncio
async def test_get_request_not_found(client):
    resp = await client.get(f"{BASE}/nonexistent", headers=AUTH_HEADERS)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_requests(client):
    await client.post(BASE, json=_create_body(title="A"), headers=AUTH_HEADERS)
    await client.post(BASE, json=_create_body(title="B"), headers=AUTH_HEADERS)

    resp = await client.get(BASE, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_requests_filter_by_status(client):
    await client.post(BASE, json=_create_body(title="A"), headers=AUTH_HEADERS)
    resp = await client.get(BASE, headers=AUTH_HEADERS, params={"status": "approved"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = await client.get(BASE, headers=AUTH_HEADERS, params={"status": "pending"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# ── Decisions ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_request(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    resp = await client.post(
        f"{BASE}/{req_id}/approve",
        json={"comment": "Looks good"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert len(data["auditEntries"]) == 2  # created + approved


@pytest.mark.asyncio
async def test_reject_request(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    resp = await client.post(
        f"{BASE}/{req_id}/reject",
        json={"reason": "Brand tone is wrong"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_cancel_request(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    resp = await client.post(
        f"{BASE}/{req_id}/cancel",
        json={"reason": "Draft was removed"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cannot_double_decide(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    await client.post(
        f"{BASE}/{req_id}/approve", json={"comment": "ok"}, headers=AUTH_HEADERS
    )
    # Second decision must fail
    resp = await client.post(
        f"{BASE}/{req_id}/reject",
        json={"reason": "too late"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 409


# ── Auth / Permissions ──────────────────────────────────

@pytest.mark.asyncio
async def test_missing_auth(client):
    resp = await client.get(BASE)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_insufficient_permissions_create(client):
    resp = await client.post(BASE, json=_create_body(), headers=READ_ONLY_HEADERS)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_insufficient_permissions_decide(client):
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    resp = await client.post(
        f"{BASE}/{req_id}/approve",
        json={"comment": "ok"},
        headers=READ_ONLY_HEADERS,
    )
    assert resp.status_code == 403


# ── Pagination ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_pagination(client):
    for i in range(5):
        await client.post(
            BASE, json=_create_body(title=f"Item {i}"), headers=AUTH_HEADERS
        )

    resp = await client.get(BASE, headers=AUTH_HEADERS, params={"offset": 0, "limit": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


# ── Audit trail ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_trail_records_all_actions(client):
    # Create
    r = await client.post(BASE, json=_create_body(), headers=AUTH_HEADERS)
    req_id = r.json()["id"]

    # Approve
    await client.post(
        f"{BASE}/{req_id}/approve",
        json={"comment": "ok"},
        headers=auth_headers(**{"X-User-Id": "usr_reviewer"}),
    )

    # Read back — 2 audit entries
    resp = await client.get(f"{BASE}/{req_id}", headers=AUTH_HEADERS)
    entries = resp.json()["auditEntries"]
    assert len(entries) == 2
    assert entries[0]["action"] == "created"
    assert entries[0]["actor"] == "usr_1"
    assert entries[1]["action"] == "approved"
    assert entries[1]["actor"] == "usr_reviewer"
