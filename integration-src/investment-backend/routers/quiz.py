from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from ..db import get_db
except ImportError:  # Supports importing through `uvicorn main:app`.
    from db import get_db  # type: ignore

ROOT_DIR = Path(__file__).resolve().parents[3]
QUIZ_SQL_PATH = ROOT_DIR / 'app' / 'backend' / 'quiz_seed.sql'
QUIZ_SEED_VERSION = 'stock-learning-2026-08-29-v2'
QUIZ_SEED_META_ID = 'quiz_seed_version'
router = APIRouter()

class QuizQuestionUpdate(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    choices: list[str] = Field(min_length=4, max_length=4)
    answer: int = Field(ge=0, le=3)
    explanation: str = Field(default="", max_length=2000)


def _quiz_collection():
    return get_db()["quiz_questions"]


def _serialize_quiz_question(doc: dict) -> dict:
    data = dict(doc)
    data["_id"] = str(data["_id"])
    return data


@lru_cache(maxsize=1)
def _quiz_seed_from_sql() -> list[dict[str, object]]:
    if not QUIZ_SQL_PATH.exists():
        return []

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(QUIZ_SQL_PATH.read_text(encoding="utf-8"))
        rows = conn.execute(
            """
            SELECT day, question_no, source_doc, topic, question,
                   choice_1, choice_2, choice_3, choice_4,
                   answer, explanation
              FROM quiz_questions
             ORDER BY day, question_no
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()

    seeds: list[dict[str, object]] = []
    for (
        day,
        question_no,
        source_doc,
        topic,
        question,
        choice_1,
        choice_2,
        choice_3,
        choice_4,
        answer,
        explanation,
    ) in rows:
        seeds.append(
            {
                "day": int(day),
                "question_no": int(question_no),
                "source_doc": source_doc,
                "topic": topic,
                "question": question,
                "choices": [choice_1, choice_2, choice_3, choice_4],
                "answer": int(answer),
                "explanation": explanation,
            }
        )

    return seeds


async def _seed_quiz_questions(*, force: bool = False) -> dict[str, int]:
    coll = _quiz_collection()
    await coll.create_index([("day", 1), ("question_no", 1)], unique=True)
    meta = get_db()["app_metadata"]
    current = await meta.find_one({"_id": QUIZ_SEED_META_ID})
    if not force and current and current.get("version") == QUIZ_SEED_VERSION:
        return {"updated": 0, "removed": 0}

    quiz_seed = _quiz_seed_from_sql()
    if not quiz_seed:
        raise RuntimeError(f"퀴즈 SQL 시드를 읽을 수 없습니다: {QUIZ_SQL_PATH}")

    updated = 0
    for q in quiz_seed:
        payload = dict(q)
        payload["seed_version"] = QUIZ_SEED_VERSION
        result = await coll.update_one(
            {"day": payload["day"], "question_no": payload["question_no"]},
            {"$set": payload},
            upsert=True,
        )
        updated += int(result.modified_count + (1 if result.upserted_id else 0))

    removed = (await coll.delete_many({"seed_version": {"$ne": QUIZ_SEED_VERSION}})).deleted_count
    await meta.update_one(
        {"_id": QUIZ_SEED_META_ID},
        {"$set": {"version": QUIZ_SEED_VERSION}},
        upsert=True,
    )
    return {"updated": updated, "removed": removed}


@router.on_event("startup")
async def seed_current_quiz_questions() -> None:
    """Apply a changed quiz revision once when the backend starts."""
    await _seed_quiz_questions()


@router.get("/api/quiz/day/{day}")
async def get_quiz_by_day(day: int) -> list[dict]:
    coll = _quiz_collection()
    rows = await coll.find({"day": day}).sort("question_no", 1).to_list(length=100)
    return [_serialize_quiz_question(r) for r in rows]


@router.patch("/api/quiz/questions/{question_id}")
async def update_quiz_question(question_id: str, payload: QuizQuestionUpdate) -> dict:
    try:
        oid = ObjectId(question_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="유효하지 않은 문항 ID입니다.") from exc

    choices = [c.strip() for c in payload.choices]
    if any(not c for c in choices):
        raise HTTPException(status_code=400, detail="보기는 빈 문자열일 수 없습니다.")

    coll = _quiz_collection()
    result = await coll.update_one(
        {"_id": oid},
        {
            "$set": {
                "question": payload.question.strip(),
                "choices": choices,
                "answer": payload.answer,
                "explanation": payload.explanation.strip(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다.")

    updated = await coll.find_one({"_id": oid})
    return _serialize_quiz_question(updated) if updated else {}


@router.get("/api/quiz/days")
async def get_quiz_days() -> list[dict]:
    coll = _quiz_collection()
    pipeline = [
        {"$group": {"_id": "$day", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"day": "$_id", "count": 1, "_id": 0}},
    ]
    result = await coll.aggregate(pipeline).to_list(length=100)
    return result


@router.post("/api/quiz/seed")
async def seed_quiz_questions() -> dict[str, int]:
    result = await _seed_quiz_questions(force=True)
    coll = _quiz_collection()
    total = await coll.count_documents({})
    return {**result, "total_questions": total}


@router.get("/api/quiz/seed-script")
def get_quiz_seed_script() -> dict[str, str]:
    quiz_seed = _quiz_seed_from_sql()
    script = "db.quiz_questions.insertMany(" + json.dumps(quiz_seed, ensure_ascii=False, indent=2) + ");"
    return {"script": script}
