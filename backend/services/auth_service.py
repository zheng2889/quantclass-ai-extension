"""Authentication service — password hashing, JWT tokens, user management."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import bcrypt
import jwt

from config import get_settings
from database.connection import db


class AuthService:
    """Handles authentication logic."""

    # JWT config
    ALGORITHM = "HS256"
    TOKEN_EXPIRE_HOURS = 24

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password with bcrypt."""
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )

    @staticmethod
    def create_access_token(
        user_id: int,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT access token."""
        settings = get_settings()
        expire = datetime.now(timezone.utc) + (
            expires_delta or timedelta(hours=AuthService.TOKEN_EXPIRE_HOURS)
        )
        payload = {
            "sub": str(user_id),
            "role": role,
            "exp": expire,
        }
        return jwt.encode(payload, settings.secret_key, algorithm=AuthService.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Decode and validate a JWT token. Raises jwt.PyJWTError on failure."""
        settings = get_settings()
        return jwt.decode(
            token, settings.secret_key, algorithms=[AuthService.ALGORITHM]
        )

    @staticmethod
    async def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user by username/password. Returns user dict or None."""
        row = await db.fetchone(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        )
        if not row:
            return None

        user = dict(row)
        if not AuthService.verify_password(password, user["password_hash"]):
            return None

        # Update last_login
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        await db.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (now, user["id"]),
        )
        user["last_login"] = now
        return user

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        row = await db.fetchone(
            "SELECT * FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        )
        return dict(row) if row else None

    @staticmethod
    async def change_password(user_id: int, old_password: str, new_password: str) -> bool:
        """Change a user's password. Returns True on success."""
        user = await AuthService.get_user_by_id(user_id)
        if not user:
            return False

        if not AuthService.verify_password(old_password, user["password_hash"]):
            return False

        new_hash = AuthService.hash_password(new_password)
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id),
        )
        return True
