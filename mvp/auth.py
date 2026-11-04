"""Server-side login and session handling for the OneShot MVP API.

The MVP has no external identity provider. When credentials are configured
via environment variables, this module provides a secure cookie-backed
session layer with server-side session storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

from fastapi import HTTPException, Request, Response


@dataclass(frozen=True, slots=True)
class AuthSettings:
    """Runtime configuration for the local MVP auth layer."""

    enabled: bool
    username: str
    password: str
    cookie_name: str = "oneshot_session"
    session_ttl_seconds: int = 24 * 60 * 60

    @classmethod
    def from_env(cls) -> "AuthSettings":
        username = os.environ.get("ONESHOT_AUTH_USERNAME", "").strip()
        password = os.environ.get("ONESHOT_AUTH_PASSWORD", "")
        ttl_raw = os.environ.get("ONESHOT_AUTH_SESSION_TTL_SECONDS", "86400").strip()
        try:
            ttl = max(60, int(ttl_raw))
        except ValueError:
            ttl = 24 * 60 * 60
        enabled = bool(username and password)
        return cls(enabled=enabled, username=username, password=password, session_ttl_seconds=ttl)


class AuthError(ValueError):
    """Raised when login or session validation fails."""


class AuthManager:
    """Persist and validate auth sessions in SQLite."""

    def __init__(self, state_root: str | Path, settings: AuthSettings | None = None) -> None:
        self.state_root = Path(state_root)
        self.settings = settings or AuthSettings.from_env()
        self.db_path = self.state_root / "auth_sessions.sqlite3"
        self._ensure_store()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def _ensure_store(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)"
            )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _expiry(self) -> datetime:
        return self._now() + timedelta(seconds=self.settings.session_ttl_seconds)

    def _purge_expired(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (self._now().isoformat(),))

    def _cookie_secure(self, request: Request) -> bool:
        forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        return request.url.scheme == "https" or forwarded == "https"

    def _cookie_samesite(self, request: Request) -> str:
        return "none" if self._cookie_secure(request) else "lax"

    def authenticate(self, username: str, password: str) -> None:
        if not self.enabled:
            raise AuthError("authentication is not configured")
        if not hmac.compare_digest(username, self.settings.username):
            raise AuthError("invalid username or password")
        if not hmac.compare_digest(password, self.settings.password):
            raise AuthError("invalid username or password")

    def _issue_session(self, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = self._now().isoformat()
        expires = self._expiry().isoformat()
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._purge_expired(conn)
            conn.execute(
                "INSERT INTO auth_sessions (session_id, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (session_id, username, now, expires),
            )
        return session_id

    def login(self, username: str, password: str) -> str:
        self.authenticate(username, password)
        return self._issue_session(username)

    def clear_session(self, session_id: str) -> None:
        if not session_id:
            return
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))

    def revoke_request_session(self, request: Request) -> None:
        session_id = request.cookies.get(self.settings.cookie_name, "")
        self.clear_session(session_id)

    def session_user(self, request: Request) -> str | None:
        if not self.enabled:
            return None
        session_id = request.cookies.get(self.settings.cookie_name, "")
        if not session_id:
            return None
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            self._purge_expired(conn)
            row = conn.execute(
                "SELECT username, expires_at FROM auth_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            expires_at = datetime.fromisoformat(str(row["expires_at"]))
            if expires_at <= self._now():
                conn.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session_id,))
                return None
            return str(row["username"])

    def status(self, request: Request) -> dict[str, object]:
        user = self.session_user(request)
        return {
            "auth_required": self.enabled,
            "authenticated": (not self.enabled) or user is not None,
            "user": user,
        }

    def require_request(self, request: Request) -> str | None:
        if not self.enabled:
            return None
        user = self.session_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return user

    def set_cookie(self, response: Response, request: Request, session_id: str) -> None:
        response.set_cookie(
            key=self.settings.cookie_name,
            value=session_id,
            max_age=self.settings.session_ttl_seconds,
            expires=self.settings.session_ttl_seconds,
            httponly=True,
            secure=self._cookie_secure(request),
            samesite=self._cookie_samesite(request),
            path="/",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(key=self.settings.cookie_name, path="/")
