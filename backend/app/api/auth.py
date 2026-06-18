"""Authentication API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from sqlite3 import IntegrityError
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from app.auth import (
    create_token_pair,
    decode_token,
    get_current_user,
    get_password_hash,
    validate_password,
    validate_username,
    verify_password,
)
from app.persistence.user_repo import TokenBlacklistRepository, UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# Request/Response models
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: EmailStr | None = None


class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None
    is_active: int
    created_at: str
    updated_at: str


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(req: RegisterRequest):
    """Register a new user."""
    # Validate input
    if not validate_username(req.username):
        raise HTTPException(
            status_code=400,
            detail="用户名格式无效：需要3-20个字符，只能包含字母、数字和下划线",
        )
    if not validate_password(req.password):
        raise HTTPException(
            status_code=400,
            detail="密码格式无效：需要8-20个字符，必须包含字母和数字",
        )

    # Check if username exists
    existing_user = await UserRepository.get_by_username(req.username)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="用户名已存在",
        )

    # Create user (catch UNIQUE constraint race condition)
    hashed_password = get_password_hash(req.password)
    try:
        user = await UserRepository.create(
            username=req.username,
            hashed_password=hashed_password,
            email=req.email,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="用户名已存在",
        )

    logger.info("User registered: username=%s", req.username)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Login and get access + refresh tokens."""
    # Find user
    user = await UserRepository.get_by_username(req.username)

    # Always verify password to prevent timing attack
    # Use a valid bcrypt hash as dummy (must be exactly 60 chars)
    dummy_hash = "$2b$12$j3cTG6MC.B3lRYnfALCE.uMggKpMzCT8Z0GzMavfMbEnKExOiCOom"
    if user:
        password_valid = verify_password(req.password, user["hashed_password"])
    else:
        # Verify against dummy hash to maintain constant time
        verify_password(req.password, dummy_hash)
        password_valid = False

    if not user or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if user is active
    if not user.get("is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用",
        )

    # Create tokens with token_version for invalidation on password change
    token_version = user.get("token_version", 0)
    refresh_expire_days = 30 if req.remember_me else 7
    access_token, refresh_token = create_token_pair(user["id"], token_version, refresh_expire_days)

    logger.info("User logged in: username=%s", req.username)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """Refresh access token using refresh token."""
    # Decode refresh token
    payload = decode_token(req.refresh_token)

    # Verify token type
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is already blacklisted (prevent replay attack)
    if await TokenBlacklistRepository.is_blacklisted(req.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user exists
    user = await UserRepository.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用",
        )

    # Check token_version — invalidate if password was changed
    token_version = payload.get("token_version", 0)
    user_version = user.get("token_version", 0)
    if token_version != user_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated by password change",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create new tokens with current token_version
    new_access_token, new_refresh_token = create_token_pair(user_id, user_version)

    # Blacklist old refresh token
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC).isoformat()
    await TokenBlacklistRepository.add(req.refresh_token, user_id, expires_at)

    logger.info("Token refreshed for user: id=%s", user_id)
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    req: LogoutRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Logout and blacklist current access token + refresh token."""
    # Extract access token from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_token(token)
            expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC).isoformat()
            await TokenBlacklistRepository.add(token, current_user["id"], expires_at)
        except Exception:
            logger.warning(
                "Failed to decode access token during logout: user_id=%s",
                current_user["id"],
            )

    # Also blacklist the refresh token if provided
    if req.refresh_token:
        try:
            refresh_payload = decode_token(req.refresh_token)
            if refresh_payload.get("type") == "refresh":
                refresh_expires_at = datetime.fromtimestamp(
                    refresh_payload["exp"], tz=UTC
                ).isoformat()
                await TokenBlacklistRepository.add(
                    req.refresh_token, current_user["id"], refresh_expires_at
                )
        except Exception:
            logger.warning(
                "Failed to blacklist refresh token during logout: user_id=%s",
                current_user["id"],
            )

    logger.info("User logged out: id=%s", current_user["id"])
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get current user information."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    req: UpdateUserRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Update current user information."""
    updated_user = await UserRepository.update(current_user["id"], email=req.email)
    return updated_user


@router.put("/password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Change current user password."""
    # Fetch full user from DB (get_current_user strips hashed_password for safety)
    full_user = await UserRepository.get(current_user["id"])
    if not full_user:
        raise HTTPException(status_code=401, detail="User not found")

    # Verify old password
    if not verify_password(req.old_password, full_user["hashed_password"]):
        raise HTTPException(
            status_code=400,
            detail="旧密码错误",
        )

    # Validate new password
    if not validate_password(req.new_password):
        raise HTTPException(
            status_code=400,
            detail="新密码格式无效：需要8-20个字符，必须包含字母和数字",
        )

    # Update password
    hashed_password = get_password_hash(req.new_password)
    await UserRepository.update_password(current_user["id"], hashed_password)

    logger.info("Password changed for user: id=%s", current_user["id"])
    return {"message": "密码修改成功"}
