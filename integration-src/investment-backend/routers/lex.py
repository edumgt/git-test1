"""Amazon Lex V2 runtime integration for the floating investment assistant."""

from __future__ import annotations

import os
import re
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_SESSION_ID_PATTERN = r"^[A-Za-z0-9._:-]{2,100}$"


class LexChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1024, description="Lex 봇에 전달할 사용자 메시지")
    session_id: str = Field(min_length=2, max_length=100, pattern=_SESSION_ID_PATTERN, description="브라우저 대화 세션 ID")


def _settings() -> tuple[str, str, str, str]:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    bot_id = os.getenv("LEX_BOT_ID")
    alias_id = os.getenv("LEX_BOT_ALIAS_ID")
    locale_id = os.getenv("LEX_LOCALE_ID", "ko_KR")
    missing = [name for name, value in {
        "AWS_REGION": region,
        "LEX_BOT_ID": bot_id,
        "LEX_BOT_ALIAS_ID": alias_id,
    }.items() if not value]
    if missing:
        raise HTTPException(503, f"Amazon Lex 설정이 필요합니다: {', '.join(missing)}")
    return region, bot_id, alias_id, locale_id


@lru_cache(maxsize=4)
def _client(region: str):
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(503, "Amazon Lex 연동 모듈(boto3)이 설치되지 않았습니다.") from exc
    return boto3.client("lexv2-runtime", region_name=region)


def _messages(response: dict) -> list[str]:
    return [
        str(item.get("content", "")).strip()
        for item in response.get("messages", [])
        if item.get("contentType") in {None, "PlainText", "CustomPayload", "SSML"}
        and str(item.get("content", "")).strip()
    ]


@router.get("/api/lex/status")
def lex_status() -> dict[str, object]:
    """Return safe Lex configuration state without exposing AWS credentials."""
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    return {
        "configured": bool(region and os.getenv("LEX_BOT_ID") and os.getenv("LEX_BOT_ALIAS_ID")),
        "region": region,
        "locale_id": os.getenv("LEX_LOCALE_ID", "ko_KR"),
    }


@router.post("/api/lex/chat")
def lex_chat(request: LexChatRequest) -> dict[str, object]:
    """Send text to Amazon Lex V2 while keeping AWS credentials on the server."""
    if not re.fullmatch(_SESSION_ID_PATTERN, request.session_id):
        raise HTTPException(422, "세션 ID 형식이 올바르지 않습니다.")

    region, bot_id, alias_id, locale_id = _settings()
    try:
        response = _client(region).recognize_text(
            botId=bot_id,
            botAliasId=alias_id,
            localeId=locale_id,
            sessionId=request.session_id,
            text=request.message.strip(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        error_name = exc.__class__.__name__
        if error_name in {"NoCredentialsError", "PartialCredentialsError"}:
            raise HTTPException(503, "AWS 자격 증명을 찾지 못했습니다. IAM 역할 또는 표준 AWS 자격 증명을 설정하세요.") from exc
        if error_name == "ClientError":
            detail = getattr(exc, "response", {}).get("Error", {})
            code = detail.get("Code", "AWS 오류")
            message = detail.get("Message", "Amazon Lex 요청에 실패했습니다.")
            status = 403 if code == "AccessDeniedException" else 502
            raise HTTPException(status, f"Amazon Lex {code}: {message}") from exc
        raise HTTPException(502, f"Amazon Lex 응답을 받지 못했습니다: {error_name}") from exc

    state = response.get("sessionState", {})
    intent = state.get("intent", {})
    return {
        "session_id": response.get("sessionId", request.session_id),
        "messages": _messages(response) or ["응답 메시지가 없습니다."],
        "intent": intent.get("name"),
        "dialog_action": state.get("dialogAction", {}).get("type"),
    }
