"""Authentication and Role-Based Access Control (RBAC) for SmartCanteen AI Pilot.

Implements cryptographically signed, zero-dependency HS256 tokens compliant with RFC 7519,
enforcing role-based authorization across operational pilot endpoints.

Roles:
- staff: Create meal services, record pre-service headcount observations, log production, service & waste.
- supervisor: Staff permissions + auditable record corrections + POS CSV register ingestion.
- auditor: Read-only visibility over services, quality metrics, audit trail, and pre-service features.
- admin: Master menu catalog items, holdout cohort reservation/sealing, raw data export, and database maintenance.
"""

import base64
from enum import Enum
import hashlib
import hmac
import json
import time
from typing import Any, Callable, Dict, List, Optional
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.pilot.config import (
    PILOT_ACCESS_TOKEN_EXPIRE_MINUTES,
    PILOT_JWT_SECRET,
    PILOT_REQUIRE_AUTH,
)


class Role(str, Enum):
    """Operational pilot staff roles."""
    STAFF = "staff"
    SUPERVISOR = "supervisor"
    AUDITOR = "auditor"
    ADMIN = "admin"


class AuthenticatedActor(BaseModel):
    """Model representing an authenticated caller with verified identity and role."""
    actor_id: str = Field(..., description="Unique staff identifier or badge number")
    role: Role = Field(..., description="Assigned operational role")
    auth_method: str = Field("bearer_jwt", description="Authentication mechanism")
    is_authenticated: bool = True
    issued_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 3600)


def _b64encode(data: bytes) -> str:
    """URL-safe base64 encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64decode(s: str) -> bytes:
    """URL-safe base64 decoding restoring required padding."""
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_access_token(
    actor_id: str,
    role: str,
    expires_in_seconds: Optional[int] = None,
    secret_key: Optional[str] = None,
) -> str:
    """Create a signed HS256 JWT access token.
    
    Args:
        actor_id: Identifier of the staff member or system agent.
        role: Assigned role (staff, supervisor, auditor, admin).
        expires_in_seconds: Optional token lifetime (defaults to PILOT_ACCESS_TOKEN_EXPIRE_MINUTES).
        secret_key: Optional HMAC secret override.
    """
    if expires_in_seconds is None:
        expires_in_seconds = PILOT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    secret = (secret_key or PILOT_JWT_SECRET).encode("utf-8")
    now = time.time()

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(actor_id),
        "role": str(role),
        "iat": int(now),
        "exp": int(now + expires_in_seconds),
        "iss": "smartcanteen-pilot",
    }

    header_b64 = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_access_token(token: str, secret_key: Optional[str] = None) -> AuthenticatedActor:
    """Verify and decode a signed HS256 JWT access token.
    
    Raises:
        HTTPException(401): If the token is missing, malformed, expired, or has an invalid signature.
    """
    token = token.strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication token: expected 3 dot-separated segments.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    header_b64, payload_b64, sig_b64 = parts
    secret = (secret_key or PILOT_JWT_SECRET).encode("utf-8")
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _b64decode(sig_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature encoding.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature: cryptographic verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload_data = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload content.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate expiration
    exp = payload_data.get("exp")
    if not exp or time.time() > float(exp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    actor_id = payload_data.get("sub")
    if not actor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identifier ('sub').",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_str = payload_data.get("role", "staff").lower()
    valid_roles = [r.value for r in Role]
    assigned_role = Role(role_str) if role_str in valid_roles else Role.STAFF

    return AuthenticatedActor(
        actor_id=actor_id,
        role=assigned_role,
        auth_method="bearer_jwt",
        is_authenticated=True,
        issued_at=float(payload_data.get("iat", time.time())),
        expires_at=float(exp),
    )


def get_current_actor(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_staff_auth_token: Optional[str] = Header(None, alias="X-Staff-Auth-Token"),
) -> AuthenticatedActor:
    """FastAPI dependency extracting and validating the authenticated staff caller.
    
    Inspects Authorization header (Bearer token) or X-Staff-Auth-Token header.
    Rejects unauthenticated or invalid tokens with HTTP 401 when PILOT_REQUIRE_AUTH is active.
    """
    token_str = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            token_str = authorization[7:].strip()
        else:
            token_str = authorization.strip()
    elif x_staff_auth_token:
        token_str = x_staff_auth_token.strip()

    if not token_str:
        if not PILOT_REQUIRE_AUTH:
            # Fallback for unauthenticated development sandbox
            return AuthenticatedActor(
                actor_id="dev_staff",
                role=Role.ADMIN,
                auth_method="unauthenticated_dev_fallback",
                is_authenticated=False,
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: No Bearer token provided in Authorization or X-Staff-Auth-Token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_access_token(token_str)


def require_role(allowed_roles: List[Role]) -> Callable:
    """Dependency factory enforcing that the authenticated caller has one of the allowed roles.
    
    Raises:
        HTTPException(403): If the authenticated user's role is not in allowed_roles.
    """
    def role_checker(actor: AuthenticatedActor = Depends(get_current_actor)) -> AuthenticatedActor:
        if actor.role not in allowed_roles:
            allowed_names = [r.value for r in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient operational privileges: Operation requires role in {allowed_names}, "
                    f"but actor '{actor.actor_id}' holds role '{actor.role.value}'."
                ),
            )
        return actor

    return role_checker


# Predefined role dependencies for clean route decoration
require_staff = require_role([Role.STAFF, Role.SUPERVISOR, Role.ADMIN])
require_supervisor = require_role([Role.SUPERVISOR, Role.ADMIN])
require_auditor = require_role([Role.AUDITOR, Role.ADMIN])
require_admin = require_role([Role.ADMIN])
require_any_authenticated = require_role([Role.STAFF, Role.SUPERVISOR, Role.AUDITOR, Role.ADMIN])
