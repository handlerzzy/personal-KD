"""Authentication utilities: JWT tokens and password hashing."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.persistence.user_repo import TokenBlacklistRepository, UserRepository

logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# JWT settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # 2 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days

# Input validation patterns
USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d).{8,20}$")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def validate_username(username: str) -> bool:
    """Validate username format: 3-20 characters, alphanumeric + underscore."""
    return bool(USERNAME_PATTERN.match(username))


def validate_password(password: str) -> bool:
    """Validate password format: 8-20 characters, must contain letter and digit."""
    return bool(PASSWORD_PATTERN.match(password))


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token with jti for revocation support."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": uuid.uuid4().hex})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_token_pair(
    user_id: str,
    token_version: int = 0,
    refresh_expire_days: int = REFRESH_TOKEN_EXPIRE_DAYS,
) -> tuple[str, str]:
    """Create access + refresh token pair with token_version."""
    access = create_access_token({"sub": user_id, "token_version": token_version})
    refresh = create_refresh_token(
        {"sub": user_id, "token_version": token_version},
        expires_delta=timedelta(days=refresh_expire_days),
    )
    return access, refresh


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning("Token decode failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    """Get current user from access token."""
    # Decode and validate token first (cheaper than database query)
    payload = decode_token(token)

    # Verify token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if token is blacklisted (only after validating token format)
    if await TokenBlacklistRepository.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserRepository.get(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", 1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Check token_version — invalidates all tokens after password change
    token_version = payload.get("token_version", 0)
    user_version = user.get("token_version", 0)
    if token_version != user_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been invalidated by password change",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Remove sensitive field before passing to endpoint handlers
    user.pop("hashed_password", None)
    return user
