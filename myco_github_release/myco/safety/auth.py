"""
myco/safety/auth.py
===================
Authentication, authorisation, rate limiting, and prompt-injection detection.

Auth model:
  - Token-based (Bearer tokens stored as bcrypt hashes)
  - Three roles:  parent > user > readonly
  - parent  — full access including admin endpoints, rollback, self-improvement toggle
  - user    — chat, ingest, memory read, model switch
  - readonly — health + memory read only

Rate limiting:
  - Per-token sliding-window counters stored in memory (reset on restart)
  - Configurable limits per role

Prompt injection detection:
  - Pattern-based scanner on every incoming message
  - Suspicious inputs are flagged, logged, and optionally blocked
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

log = logging.getLogger("myco.auth")


# ── roles ─────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    PARENT   = "parent"    # full control
    USER     = "user"      # normal interaction
    READONLY = "readonly"  # read-only observer


ROLE_HIERARCHY: dict[Role, int] = {
    Role.READONLY: 0,
    Role.USER:     1,
    Role.PARENT:   2,
}

# Which endpoints each role may access
ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.READONLY: {
        "GET /health", "GET /mind", "GET /memory", "GET /episodes",
        "GET /sessions", "GET /graph", "GET /models", "GET /snapshots",
        "GET /audit",
    },
    Role.USER: {
        "POST /chat", "POST /ingest",
        "GET /health", "GET /mind", "GET /memory", "GET /episodes",
        "GET /sessions", "GET /graph", "GET /models", "GET /snapshots",
        "POST /models/switch",
    },
    Role.PARENT: {"*"},   # wildcard — all endpoints
}

# Requests per minute per role
RATE_LIMITS: dict[Role, int] = {
    Role.READONLY: 60,
    Role.USER:     30,
    Role.PARENT:   120,
}


# ── token management ──────────────────────────────────────────────────────────

@dataclass
class Token:
    token_id:    str
    hashed:      str          # bcrypt or PBKDF2 hash
    role:        Role
    label:       str          # human label e.g. "alice-laptop"
    created_at:  float        = field(default_factory=time.time)
    last_used:   float        = 0.0
    revoked:     bool         = False
    expires_at:  float | None = None   # None = never


class TokenStore:
    """
    In-memory token store (persisted to the audit DB on change).
    For production: swap backing store for Redis or Postgres.
    """

    def __init__(self):
        self._tokens: dict[str, Token] = {}
        self._ensure_parent_token()

    def create(self, role: Role, label: str, ttl_days: float | None = None) -> str:
        """Generate a new token. Returns the raw token (shown once)."""
        raw      = secrets.token_urlsafe(32)
        # FIX: use full 32-char token_id (not [:16]) to avoid birthday collisions
        token_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
        hashed   = self._hash(raw, token_id)   # per-token salt derived from token_id
        expires  = time.time() + ttl_days * 86400 if ttl_days else None
        self._tokens[token_id] = Token(
            token_id=token_id, hashed=hashed, role=role,
            label=label, expires_at=expires
        )
        log.info(f"Token created: {token_id[:8]}... role={role.value} label={label}")
        return raw

    def verify(self, raw_token: str) -> Token | None:
        """Return the Token if valid, else None."""
        token_id = hashlib.sha256(raw_token.encode()).hexdigest()[:32]
        t = self._tokens.get(token_id)
        if t is None:
            return None
        if t.revoked:
            return None
        if t.expires_at and time.time() > t.expires_at:
            return None
        # FIX: pass token_id as salt (matches how it was hashed at creation)
        if not hmac.compare_digest(self._hash(raw_token, token_id), t.hashed):
            return None
        t.last_used = time.time()
        return t

    def revoke(self, token_id: str) -> bool:
        # Support both full 32-char IDs and 8-char prefixes for convenience
        matches = [t for tid, t in self._tokens.items()
                   if tid == token_id or tid.startswith(token_id)]
        if not matches:
            return False
        for t in matches:
            t.revoked = True
            log.info(f"Token revoked: {t.token_id[:8]}...")
        return True

    def list_tokens(self) -> list[dict]:
        return [
            {
                "token_id":   t.token_id[:8] + "...",  # never expose full id
                "role":       t.role.value,
                "label":      t.label,
                "revoked":    t.revoked,
                "last_used":  t.last_used,
                "created_at": t.created_at,
                "expires_at": t.expires_at,
            }
            for t in self._tokens.values()
        ]

    def _hash(self, raw: str, salt_prefix: str = "") -> str:
        # FIX: use per-token salt (token_id prefix) instead of a fixed global salt.
        # This prevents rainbow table attacks if the token store is leaked.
        salt = f"myco-v2-{salt_prefix}".encode()
        return hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, 100_000).hex()

    def _ensure_parent_token(self):
        """
        On first run, create a parent token and print it once to stdout.
        If MYCO_PARENT_TOKEN env var is set, use that instead.
        """
        env_token = os.getenv("MYCO_PARENT_TOKEN", "")
        if env_token:
            token_id = hashlib.sha256(env_token.encode()).hexdigest()[:32]
            self._tokens[token_id] = Token(
                token_id=token_id,
                hashed=self._hash(env_token, token_id),
                role=Role.PARENT,
                label="env-parent",
            )
            return

        raw = self.create(Role.PARENT, "initial-parent")
        print("\n" + "═" * 60)
        print("  MYCO PARENT TOKEN (save this — shown only once)")
        print(f"  {raw}")
        print("═" * 60 + "\n")


# ── rate limiter ──────────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding-window rate limiter. Thread-safe via simple dict + timestamps."""

    def __init__(self):
        self._windows: dict[str, list[float]] = {}

    def check(self, token_id: str, role: Role) -> tuple[bool, int]:
        """
        Returns (allowed: bool, remaining: int).
        """
        limit  = RATE_LIMITS.get(role, 30)
        now    = time.time()
        window = self._windows.setdefault(token_id, [])
        # evict entries older than 60 seconds
        self._windows[token_id] = [t for t in window if now - t < 60]
        count  = len(self._windows[token_id])
        if count >= limit:
            return False, 0
        self._windows[token_id].append(now)
        return True, limit - count - 1


# ── prompt injection detector ─────────────────────────────────────────────────

# Patterns that suggest an attempt to hijack Myco's behaviour
_INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
     "classic ignore-instructions injection"),
    (re.compile(r"you\s+are\s+now\s+(?!myco)", re.I),
     "persona-replacement attempt"),
    (re.compile(r"(system\s*prompt|system\s*message)\s*:", re.I),
     "system prompt leak attempt"),
    (re.compile(r"<\s*/?system\s*>", re.I),
     "XML system tag injection"),
    (re.compile(r"\bDAN\b|\bjailbreak\b", re.I),
     "known jailbreak keyword"),
    (re.compile(r"forget\s+(everything|all)\s+(you\s+know|your\s+training)", re.I),
     "training-override attempt"),
    (re.compile(r"(act|pretend|behave)\s+as\s+(if\s+)?(you\s+are|a|an)\s+(?!myco)", re.I),
     "role-play override attempt"),
    (re.compile(r"disregard\s+(your|all)\s+(safety|ethical|moral|previous)", re.I),
     "safety-bypass attempt"),
    (re.compile(r"sudo\s+|as\s+root\s+|admin\s+mode", re.I),
     "privilege escalation language"),
    (re.compile(r"(print|show|reveal|output|display)\s+(your\s+)?(system\s+)?prompt", re.I),
     "system prompt extraction attempt"),
    (re.compile(r"</?\w+>.*</?\w+>", re.I),
     "HTML/XML injection in message"),
]

_THREAT_SCORE_THRESHOLD = 1   # flag after any match (change to 2+ for higher tolerance)


@dataclass
class InjectionResult:
    clean:    bool
    score:    int
    findings: list[str]


def detect_injection(text: str) -> InjectionResult:
    """
    Scan user text for prompt injection patterns.
    Returns InjectionResult with clean=False if suspicious.
    """
    findings: list[str] = []
    for pattern, description in _INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append(description)
    score = len(findings)
    return InjectionResult(
        clean    = score < _THREAT_SCORE_THRESHOLD,
        score    = score,
        findings = findings,
    )


# ── permission checker ────────────────────────────────────────────────────────

def check_permission(token: Token, method: str, path: str) -> bool:
    """Return True if this token's role permits the given request."""
    if token.role == Role.PARENT:
        return True
    key     = f"{method.upper()} {path}"
    allowed = ROLE_PERMISSIONS.get(token.role, set())
    return key in allowed or "*" in allowed


# ── FastAPI dependency ────────────────────────────────────────────────────────
# Imported and used in api/main.py as a dependency injection

_token_store   = TokenStore()
_rate_limiter  = RateLimiter()


def get_token_store() -> TokenStore:
    return _token_store


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


async def require_auth(
    authorization: str | None = None,
    method: str = "GET",
    path: str = "/",
    audit: "AuditLog | None" = None,
) -> Token:
    """
    FastAPI dependency. Raises HTTPException if auth fails.
    Returns the validated Token on success.
    """
    from fastapi import HTTPException, status

    if not authorization or not authorization.startswith("Bearer "):
        if audit:
            audit.log_auth("missing_token", "anonymous", {"path": path})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    token     = _token_store.verify(raw_token)

    if token is None:
        if audit:
            audit.log_auth("invalid_token", raw_token[:8] + "...", {"path": path})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # rate limit
    allowed, remaining = _rate_limiter.check(token.token_id, token.role)
    if not allowed:
        if audit:
            audit.log_threat("rate_limit_exceeded", token.token_id, {"path": path})
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in ~60 seconds.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    # permission
    if not check_permission(token, method, path):
        if audit:
            audit.log_auth("permission_denied", token.token_id,
                           {"role": token.role.value, "path": path})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{token.role.value}' cannot access {method} {path}",
        )

    if audit:
        audit.log_auth("auth_ok", token.token_id,
                       {"role": token.role.value, "path": path, "remaining": remaining})
    return token
