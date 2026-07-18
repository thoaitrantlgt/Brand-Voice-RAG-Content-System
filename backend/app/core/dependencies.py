from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.auth import AuthError, Principal, parse_token_registry, require_project, require_role
from app.core.config import Settings, get_settings


bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not settings.AUTH_ENABLED:
        if not settings.ALLOW_INSECURE_AUTH:
            raise HTTPException(status_code=503, detail="Authentication is not configured")
        return Principal(username="development", role="admin")
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        registry = parse_token_registry(settings.INTERNAL_ACCESS_TOKENS)
    except AuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    principal = registry.get(credentials.credentials)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
    return principal


def authorize(principal: Principal, minimum_role: str) -> Principal:
    try:
        return require_role(principal, minimum_role)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def authorize_project(principal: Principal, project_id: str) -> Principal:
    try:
        return require_project(principal, project_id)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
