"""Auth router — login, user info, password management."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import jwt as pyjwt

from models import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    ChangePasswordRequest,
    success,
    error,
    ResponseCode,
)
from services.auth_service import AuthService

router = APIRouter(tags=["Auth"])
security = HTTPBearer()


def _user_response(user: dict) -> UserResponse:
    """Build a UserResponse from a user dict."""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        is_active=bool(user["is_active"]),
        created_at=user["created_at"],
        last_login=user.get("last_login"),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Extract and validate the current user from a Bearer token."""
    try:
        payload = AuthService.decode_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = await AuthService.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require that the current user has admin role."""
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return user


# ── Endpoints ──────────────────────────────────────────────


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate and return a JWT token."""
    user = await AuthService.authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = AuthService.create_access_token(user["id"], user["role"])
    return success(
        LoginResponse(token=token, user=_user_response(user)).model_dump()
    )


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return current user info."""
    return success(_user_response(user).model_dump())


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: dict = Depends(get_current_user),
):
    """Change the current user's password."""
    ok = await AuthService.change_password(user["id"], req.old_password, req.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Old password is incorrect",
        )
    return success({"message": "Password changed successfully"})
