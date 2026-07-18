import json
from dataclasses import dataclass


ROLES = {"writer": 1, "reviewer": 2, "admin": 3}


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    projects: frozenset[str] = frozenset({"*"})


def parse_token_registry(raw: str) -> dict[str, Principal]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AuthError("INTERNAL_ACCESS_TOKENS must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise AuthError("INTERNAL_ACCESS_TOKENS must be a JSON object")

    registry: dict[str, Principal] = {}
    for token, entry in payload.items():
        if not isinstance(token, str) or not token or not isinstance(entry, dict):
            raise AuthError("Each token must map to a user object")
        username = str(entry.get("username", "")).strip()
        role = str(entry.get("role", "")).strip().lower()
        projects = entry.get("projects")
        if (
            not username
            or role not in ROLES
            or not isinstance(projects, list)
            or not projects
            or any(not isinstance(item, str) or not item.strip() for item in projects)
        ):
            raise AuthError("Each user requires username, role, and a non-empty projects list")
        registry[token] = Principal(
            username=username,
            role=role,
            projects=frozenset(item.strip() for item in projects),
        )
    return registry


def require_role(principal: Principal, minimum_role: str) -> Principal:
    if minimum_role not in ROLES:
        raise AuthError(f"Unknown role: {minimum_role}")
    if ROLES.get(principal.role, 0) < ROLES[minimum_role]:
        raise AuthError(f"{minimum_role} role required")
    return principal


def require_project(principal: Principal, project_id: str) -> Principal:
    if "*" not in principal.projects and project_id not in principal.projects:
        raise AuthError("Project access denied")
    return principal
