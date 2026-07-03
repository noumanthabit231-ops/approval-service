"""Auth stub and shared dependencies.

For local development, the client passes an X-User-Id header
and an X-User-Permissions header with a comma-separated list of permissions.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from .schemas import ACTIONS


class AuthContext:
    def __init__(self, user_id: str, workspace_id: str, permissions: set[str]):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.permissions = permissions

    def require(self, action: str) -> None:
        if action not in self.permissions:
            raise HTTPException(status_code=403, detail=f"Missing permission: {action}")


def get_auth_context(
    request: Request,
    x_user_id: Annotated[str, Header(alias="X-User-Id")] = "",
    x_user_permissions: Annotated[str, Header(alias="X-User-Permissions")] = "",
) -> AuthContext:
    """Extract auth context from headers. Workspace comes from path parameter."""
    workspace_id = request.path_params.get("workspace_id", "")
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Id header")

    permissions = set(
        p.strip() for p in x_user_permissions.split(",") if p.strip()
    ) if x_user_permissions else set(ACTIONS)  # allow all by default when header missing

    return AuthContext(user_id=x_user_id, workspace_id=workspace_id, permissions=permissions)
