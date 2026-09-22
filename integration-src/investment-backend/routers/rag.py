from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
_QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "investment_docs")
_RAG_EMBEDDING_PROVIDER = os.getenv("RAG_EMBEDDING_PROVIDER", "ollama").lower()
_RAG_EMBEDDING_URL = os.getenv("RAG_EMBEDDING_URL", "").rstrip("/")
_RAG_EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "")
# CPU 환경에서는 임베딩 모델의 첫 로딩이 30초를 넘을 수 있다.
_RAG_EMBEDDING_TIMEOUT_SECONDS = max(30, int(os.getenv("RAG_EMBEDDING_TIMEOUT_SECONDS", "180")))
_RAG_LLM_TIMEOUT_SECONDS = max(30, int(os.getenv("RAG_LLM_TIMEOUT_SECONDS", "180")))
# The Domain RAG API is the single retrieval and answer service for both sites.
# It is resolved by Docker Compose service name on the shared application network.
_SHARED_RAG_URL = os.getenv("SHARED_RAG_URL", "http://domain-rag-api:8000").rstrip("/")


def _shared_rag_chat(query: str, top_k: int) -> tuple[str, list[dict[str, object]]]:
    """Ask the central Domain RAG and adapt its sources to this UI's contract."""
    payload = {"question": query, "domain": "finance", "top_k": top_k}
    request = urllib.request.Request(
        f"{_SHARED_RAG_URL}/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(502, f"중앙 RAG 응답 오류({exc.code}): {detail[:200]}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(503, f"중앙 RAG 연결 실패 ({_SHARED_RAG_URL}): {exc}") from exc

    sources = [
        {"score": reference.get("score", 0), "source_doc": reference.get("title", ""), "section": reference.get("document_id", ""), "chunk_index": reference.get("chunk_id", ""), "text": reference.get("content", "")}
        for reference in result.get("references", [])
    ]
    return str(result.get("answer", "관련 문서를 찾지 못했습니다.")), sources


def _qdrant_request(method: str, path: str, payload: dict | None = None) -> dict:
    url = _QDRANT_URL.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=10) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(502, f"Qdrant 오류({exc.code}): {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(503, f"Qdrant 연결 실패 ({_QDRANT_URL}): {exc.reason}") from exc


def _qdrant_available() -> bool:
    try:
        with urllib.request.urlopen(_QDRANT_URL.rstrip("/") + "/collections", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _qdrant_collection_available() -> bool:
    """Qdrant 연결과 컬렉션 생성 여부를 분리해 확인한다."""
    try:
        with urllib.request.urlopen(f"{_QDRANT_URL.rstrip('/')}/collections/{_QDRANT_COLLECTION}", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _hash_embed(text: str, dim: int = 384) -> list[float]:
    """Ollama를 쓰지 않는 서버용, 의존성 없는 해시 임베딩."""
    vector = [0.0] * dim
    for token in re.findall(r"[0-9A-Za-z가-힣_]+", text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[int.from_bytes(digest[:4], "big") % dim] += 1.0 if digest[4] & 1 == 0 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _embedding_method() -> str:
    return f"ollama/{_RAG_EMBEDDING_MODEL}" if _RAG_EMBEDDING_PROVIDER == "ollama" else "hash/384"


def _embed_query(text: str) -> list[float]:
    """Ollama 임베딩 API로 질의를 벡터화한다.

    문서 색인에도 동일한 RAG_EMBEDDING_URL·RAG_EMBEDDING_MODEL을 사용해야 한다.
    """
    if _RAG_EMBEDDING_PROVIDER == "hash":
        try:
            info = _qdrant_request("GET", f"/collections/{_QDRANT_COLLECTION}")
            dim = int(info.get("result", {}).get("config", {}).get("params", {}).get("vectors", {}).get("size", 384))
        except Exception:
            dim = 384
        return _hash_embed(text, dim)
    if _RAG_EMBEDDING_PROVIDER != "ollama":
        raise HTTPException(503, "RAG_EMBEDDING_PROVIDER는 ollama 또는 hash여야 합니다.")
    if not _RAG_EMBEDDING_URL or not _RAG_EMBEDDING_MODEL:
        raise HTTPException(503, "Ollama 임베딩을 사용하려면 RAG_EMBEDDING_URL과 RAG_EMBEDDING_MODEL을 설정하세요.")
    payload = {"model": _RAG_EMBEDDING_MODEL, "input": text, "truncate": True}
    try:
        request = urllib.request.Request(
            _RAG_EMBEDDING_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=_RAG_EMBEDDING_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
        embeddings = result.get("embeddings", [])
        vector = embeddings[0] if embeddings else []
        if not isinstance(vector, list) or not vector:
            raise ValueError("빈 임베딩 응답")
        return [float(value) for value in vector]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(502, f"Ollama 임베딩 응답 오류({exc.code}): {detail[:200]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError, IndexError) as exc:
        raise HTTPException(502, f"Ollama 임베딩 응답을 받지 못했습니다: {exc}") from exc


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="검색 질문")
    top_k: int = Field(default=5, ge=1, le=20, description="반환할 최대 청크 수")
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="최소 유사도 점수")


class RagAskRequest(RagSearchRequest):
    provider: str = Field(default="rag", pattern="^(rag|openai_compatible)$", description="답변 다듬기에 사용할 외부 AI 모듈")


def _search(query: str, top_k: int, score_threshold: float) -> list[dict[str, object]]:
    payload: dict[str, object] = {"vector": _embed_query(query), "limit": top_k, "with_payload": True, "with_vector": False}
    if score_threshold > 0:
        payload["score_threshold"] = score_threshold
    result = _qdrant_request("POST", f"/collections/{_QDRANT_COLLECTION}/points/search", payload)
    return [{
        "score": round(hit.get("score", 0), 4),
        "source_doc": hit.get("payload", {}).get("source_doc", ""),
        "section": hit.get("payload", {}).get("section", ""),
        "chunk_index": hit.get("payload", {}).get("chunk_index", 0),
        "text": hit.get("payload", {}).get("text", ""),
    } for hit in result.get("result", [])]


def _require_qdrant() -> None:
    if not _qdrant_available():
        raise HTTPException(503, f"Qdrant 서버에 연결할 수 없습니다 ({_QDRANT_URL}). 서버를 실행한 뒤 문서를 색인하세요.")
    if not _qdrant_collection_available():
        raise HTTPException(
            503,
            "문서 검색용 컬렉션이 아직 없습니다. Docker Compose 환경에서는 "
            "`docker compose --profile tools run --rm docs-index`로 학습 문서를 먼저 색인하세요.",
        )


def _cite(chunk: dict[str, object]) -> str:
    doc = str(chunk.get("source_doc", ""))
    section = str(chunk.get("section", "") or "").strip()
    return f"{doc} § {section}" if section else doc


def _rag_only_answer(chunks: list[dict[str, object]]) -> str:
    """검색된 원문만 잘라 정리한다. 생성 모델이나 외부 지식은 사용하지 않는다."""
    if not chunks:
        return "관련 문서를 찾지 못했습니다. 다른 표현으로 질문해 보세요."
    excerpts = []
    for chunk in chunks[:3]:
        text = " ".join(str(chunk.get("text", "")).split())
        if text:
            excerpts.append(f"• [{_cite(chunk)}] {text[:500]}{'…' if len(text) > 500 else ''}")
    return "문서에서 찾은 관련 내용입니다. 오른쪽 원문과 함께 확인하세요.\n\n" + "\n\n".join(excerpts)


def _openai_compatible_answer(query: str, chunks: list[dict[str, object]]) -> str:
    """RAG 원문만 근거로 Ollama의 OpenAI 호환 모델이 답변을 생성하도록 한다."""
    api_key = os.getenv("RAG_LLM_API_KEY")
    model = os.getenv("RAG_LLM_MODEL")
    base_url = os.getenv("RAG_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key or not model:
        raise HTTPException(503, "Ollama 답변 생성을 사용하려면 RAG_LLM_API_KEY와 RAG_LLM_MODEL을 설정하세요.")

    context = "\n\n".join(
        f"[출처 {index + 1}: {_cite(chunk)}]\n{chunk.get('text', '')}"
        for index, chunk in enumerate(chunks)
    )[:14000]
    prompt = (
        "아래 '검색 원문'만 근거로 사용자의 질문에 한국어로 간결하게 답하세요. "
        "원문에 없는 사실·숫자·투자 조언을 추가하지 말고, 정보가 부족하면 부족하다고 밝히세요. "
        "출처 번호를 [출처 1]처럼 표시하고 3개 이내의 짧은 문단 또는 목록으로 정리하세요. "
        "원문이 '예시', '추정', '~일 수 있습니다'처럼 단정하지 않는 표현을 쓴 부분은 답변에서도 같은 정도의 "
        "조심스러운 표현을 유지하고, 확정된 사실처럼 바꿔 말하지 마세요. 매수·매도를 권유하는 표현은 쓰지 마세요.\n\n"
        f"사용자 질문: {query}\n\n검색 원문:\n{context}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "당신은 제공된 RAG 문서만 다듬어 설명하는 도우미입니다."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 300,
        "reasoning_effort": "none",
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_RAG_LLM_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = str(result.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        if not answer:
            raise ValueError("빈 응답")
        return answer
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(502, f"Ollama 답변 응답 오류({exc.code}): {detail[:200]}") from exc
    except (urllib.error.URLError, ValueError, KeyError, IndexError) as exc:
        raise HTTPException(502, f"Ollama 답변 응답을 받지 못했습니다: {exc}") from exc


@router.post("/api/rag/search")
def rag_search(req: RagSearchRequest) -> dict[str, object]:
    """Search the shared Domain RAG instead of this app's legacy collection."""
    _, chunks = _shared_rag_chat(req.query, req.top_k)
    if req.score_threshold > 0:
        chunks = [chunk for chunk in chunks if float(chunk["score"]) >= req.score_threshold]
    return {"query": req.query, "embed_method": "domain-rag/hashing-384", "count": len(chunks), "results": chunks}


@router.post("/api/rag/ask")
def rag_ask(req: RagAskRequest) -> dict[str, object]:
    """Use the shared Domain RAG for retrieval, answer generation, and citations."""
    answer, chunks = _shared_rag_chat(req.query, req.top_k)
    if req.score_threshold > 0:
        chunks = [chunk for chunk in chunks if float(chunk["score"]) >= req.score_threshold]
    return {
        "query": req.query,
        "answer": answer,
        "provider": "domain-rag",
        "embed_method": "domain-rag/hashing-384",
        "sources": chunks,
        "source_count": len(chunks),
    }


@router.get("/api/rag/status")
def rag_status() -> dict[str, object]:
    """Report the central Domain RAG status; the legacy collection is unused."""
    available = False
    try:
        with urllib.request.urlopen(f"{_SHARED_RAG_URL}/health", timeout=5) as response:
            available = response.status == 200
    except (urllib.error.URLError, TimeoutError):
        pass
    return {
        "qdrant": {"available": available, "collection_available": available, "url": _SHARED_RAG_URL, "collection": "domain_docs"},
        "external_ai": {"openai_compatible_available": False},
        "embedding": {"provider": "domain-rag", "ollama_available": False, "model": "hashing-384"},
        "embed_method": "domain-rag/hashing-384",
    }
