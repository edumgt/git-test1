"""회원 인증과 개인별 사용 이력 API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

try:
    from ..db import get_db
except ImportError:
    from db import get_db

router = APIRouter(prefix="/api/auth", tags=["인증"])
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9가-힣_-]{2,30}$")
PASSWORD_ITERATIONS = 310_000


class SignupRequest(BaseModel):
    email: str = Field(max_length=120)
    username: str = Field(max_length=30)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=128)


class ActivityRequest(BaseModel):
    action: str = Field(default="view", pattern=r"^[a-z0-9_-]{1,40}$")
    view: str = Field(default="", max_length=80)
    detail: str = Field(default="", max_length=160)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, encoded_salt, encoded_digest = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(encoded_salt)
        expected = base64.b64decode(encoded_digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _public_user(user: dict) -> dict[str, str]:
    return {"id": str(user["_id"]), "email": user["email"], "username": user["username"]}


async def _ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.auth_sessions.create_index("token_hash", unique=True)
    await db.auth_sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.user_activity.create_index([("user_id", 1), ("created_at", -1)])


async def _issue_session(user_id) -> str:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    await get_db().auth_sessions.insert_one({"user_id": user_id, "token_hash": token_hash, "created_at": _now(), "expires_at": datetime.fromtimestamp(_now().timestamp() + 60 * 60 * 24 * 14, timezone.utc)})
    return raw_token


async def current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    token_hash = hashlib.sha256(authorization.removeprefix("Bearer ").strip().encode()).hexdigest()
    session = await get_db().auth_sessions.find_one({"token_hash": token_hash, "expires_at": {"$gt": _now()}})
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인 세션이 만료되었습니다.")
    user = await get_db().users.find_one({"_id": session["user_id"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다.")
    return user


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest) -> dict:
    email = request.email.strip().lower()
    username = request.username.strip()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="올바른 이메일 주소를 입력하세요.")
    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(status_code=422, detail="이름은 2~30자의 한글·영문·숫자·_-만 사용할 수 있습니다.")
    await _ensure_indexes()
    try:
        result = await get_db().users.insert_one({"email": email, "username": username, "password_hash": _password_hash(request.password), "created_at": _now()})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="이미 사용 중인 이메일 또는 이름입니다.")
    user = {"_id": result.inserted_id, "email": email, "username": username}
    token = await _issue_session(user["_id"])
    return {"token": token, "user": _public_user(user)}


@router.post("/login")
async def login(request: LoginRequest) -> dict:
    email = request.email.strip().lower()
    user = await get_db().users.find_one({"email": email})
    if not user or not _password_matches(request.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    token = await _issue_session(user["_id"])
    return {"token": token, "user": _public_user(user)}


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return {"user": _public_user(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(authorization: str | None = Header(default=None)) -> None:
    if authorization and authorization.startswith("Bearer "):
        token_hash = hashlib.sha256(authorization.removeprefix("Bearer ").strip().encode()).hexdigest()
        await get_db().auth_sessions.delete_one({"token_hash": token_hash})


@router.post("/activity", status_code=status.HTTP_201_CREATED)
async def record_activity(request: ActivityRequest, user: dict = Depends(current_user)) -> dict:
    await get_db().user_activity.insert_one({"user_id": user["_id"], "action": request.action, "view": request.view, "detail": request.detail, "created_at": _now()})
    return {"ok": True}


@router.get("/activity")
async def activity(limit: int = 30, user: dict = Depends(current_user)) -> dict:
    limit = max(1, min(limit, 100))
    rows = await get_db().user_activity.find({"user_id": user["_id"]}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"items": [{**row, "created_at": row["created_at"].isoformat()} for row in rows]}
