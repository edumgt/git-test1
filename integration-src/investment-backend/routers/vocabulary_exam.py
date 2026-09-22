from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from ..db import get_db
except ImportError:
    from db import get_db  # type: ignore

router = APIRouter()
KST = ZoneInfo("Asia/Seoul")
EXAM_OPEN_AT = datetime(2026, 8, 10, 14, 0, tzinfo=KST)
ANSWER_RELEASE_AT = datetime(2026, 8, 11, 0, 0, tzinfo=KST)
EXAM_PATH = Path(__file__).resolve().parents[3] / "docs" / "voca-exam.md"
# 보기 번호(1부터)가 아니라 0부터 시작하는 보기 인덱스입니다.
ANSWER_KEY = [1, 0, 0, 2, 1, 1, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 2]
REGIONS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
]


class VocabularyExamSubmission(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    region: str = Field(min_length=1, max_length=20)
    answers: list[int] = Field(min_length=30, max_length=30)


def _now() -> datetime:
    return datetime.now(KST)


def _require_open() -> None:
    if _now() < EXAM_OPEN_AT:
        raise HTTPException(
            status_code=403,
            detail={"code": "exam_not_open", "opens_at": EXAM_OPEN_AT.isoformat()},
        )


def _questions() -> list[dict[str, object]]:
    text = EXAM_PATH.read_text(encoding="utf-8")
    # Markdown은 두 자리 문제 번호부터 보기를 한 칸 더 들여쓴다.
    pattern = re.compile(r"^(\d+)\. (.+?)\n((?: {3,4}\d\. .+\n){4})", re.MULTILINE)
    questions: list[dict[str, object]] = []
    for number, question, choices_block in pattern.findall(text):
        choices = re.findall(r"^ {3,4}\d\. (.+)$", choices_block, re.MULTILINE)
        questions.append({"id": int(number), "question": question, "choices": choices})
    if len(questions) != len(ANSWER_KEY) or any(len(q["choices"]) != 4 for q in questions):
        raise RuntimeError("단어장 시험지의 30문항 형식이 올바르지 않습니다.")
    return questions


@router.get("/api/vocabulary-exam")
async def get_vocabulary_exam() -> dict[str, object]:
    _require_open()
    return {
        "opens_at": EXAM_OPEN_AT.isoformat(),
        "answer_release_at": ANSWER_RELEASE_AT.isoformat(),
        "regions": REGIONS,
        "questions": _questions(),
    }


@router.post("/api/vocabulary-exam/submissions")
async def submit_vocabulary_exam(payload: VocabularyExamSubmission) -> dict[str, object]:
    _require_open()
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="이름을 입력해 주세요.")
    if payload.region not in REGIONS:
        raise HTTPException(status_code=422, detail="거주 지역은 17개 시·도 중에서 선택해 주세요.")
    if any(answer not in (0, 1, 2, 3) for answer in payload.answers):
        raise HTTPException(status_code=422, detail="답안은 0부터 3 사이의 보기 번호여야 합니다.")
    submission_id = secrets.token_urlsafe(32)
    await get_db()["vocabulary_exam_submissions"].insert_one({
        "_id": submission_id,
        "name": name,
        "region": payload.region,
        "answers": payload.answers,
        "submitted_at": _now(),
    })
    return {"submission_id": submission_id, "answer_release_at": ANSWER_RELEASE_AT.isoformat()}


@router.get("/api/vocabulary-exam/submissions/{submission_id}")
async def get_vocabulary_exam_result(submission_id: str) -> dict[str, object]:
    if _now() < ANSWER_RELEASE_AT:
        raise HTTPException(
            status_code=403,
            detail={"code": "answers_not_released", "answer_release_at": ANSWER_RELEASE_AT.isoformat()},
        )
    submission = await get_db()["vocabulary_exam_submissions"].find_one({"_id": submission_id})
    if not submission:
        raise HTTPException(status_code=404, detail="제출 기록을 찾을 수 없습니다.")
    questions = _questions()
    reviewed = []
    for index, question in enumerate(questions):
        correct = ANSWER_KEY[index]
        reviewed.append({
            **question,
            "selected": submission["answers"][index],
            "answer": correct,
            "explanation": "단어장(voca.md)의 해당 용어 설명과 주의할 점을 다시 확인해 보세요.",
        })
    score = sum(answer == correct for answer, correct in zip(submission["answers"], ANSWER_KEY))
    return {"score": score, "total": len(ANSWER_KEY), "questions": reviewed}
