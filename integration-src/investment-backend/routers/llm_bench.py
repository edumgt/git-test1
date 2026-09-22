"""로컬 Ollama를 대체할 AWS 상 LLM 서빙 방식 3종을 같은 화면에서 비교 테스트한다.

1) EC2/ECS + vLLM · Ollama — OpenAI 호환 /v1/chat/completions 엔드포인트
2) Amazon Bedrock — bedrock-runtime Converse API
3) Amazon SageMaker JumpStart — sagemaker-runtime invoke_endpoint
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_TIMEOUT_SECONDS = max(30, int(os.getenv("LLM_BENCH_TIMEOUT_SECONDS", "120")))


class LlmBenchChatRequest(BaseModel):
    provider: str = Field(pattern="^(ec2|bedrock|sagemaker)$", description="테스트할 LLM 서빙 방식")
    prompt: str = Field(min_length=1, max_length=4000, description="테스트 프롬프트")


def _region() -> str | None:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")


@lru_cache(maxsize=4)
def _boto_client(service: str, region: str):
    try:
        import boto3
    except ImportError as exc:
        raise HTTPException(503, f"{service} 연동 모듈(boto3)이 설치되지 않았습니다.") from exc
    return boto3.client(service, region_name=region)


def _translate_boto_error(exc: Exception, label: str) -> HTTPException:
    error_name = exc.__class__.__name__
    if error_name in {"NoCredentialsError", "PartialCredentialsError"}:
        return HTTPException(503, "AWS 자격 증명을 찾지 못했습니다. IAM 역할 또는 표준 AWS 자격 증명을 설정하세요.")
    if error_name == "ClientError":
        detail = getattr(exc, "response", {}).get("Error", {})
        code = detail.get("Code", "AWS 오류")
        message = detail.get("Message", f"{label} 요청에 실패했습니다.")
        status = 403 if code == "AccessDeniedException" else 502
        return HTTPException(status, f"{label} {code}: {message}")
    return HTTPException(502, f"{label} 응답을 받지 못했습니다: {error_name}")


# ── 1) EC2/ECS + vLLM · Ollama (OpenAI 호환 엔드포인트) ─────────────────────

def _ec2_configured() -> bool:
    return bool(os.getenv("LLM_EC2_BASE_URL") and os.getenv("LLM_EC2_MODEL"))


def _call_ec2(prompt: str) -> tuple[str, str]:
    base_url = os.getenv("LLM_EC2_BASE_URL", "").rstrip("/")
    model = os.getenv("LLM_EC2_MODEL", "")
    api_key = os.getenv("LLM_EC2_API_KEY", "ollama")
    if not base_url or not model:
        raise HTTPException(503, "EC2/ECS 서빙을 사용하려면 LLM_EC2_BASE_URL과 LLM_EC2_MODEL을 설정하세요.")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
        text = str(result.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        if not text:
            raise ValueError("빈 응답")
        return text, model
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(502, f"EC2/ECS 서빙 오류({exc.code}): {detail[:300]}") from exc
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TimeoutError, OSError) as exc:
        raise HTTPException(502, f"EC2/ECS 서빙 응답을 받지 못했습니다: {exc}") from exc


# ── 2) Amazon Bedrock (Converse API) ────────────────────────────────────────

def _bedrock_configured() -> bool:
    return bool(_region() and os.getenv("BEDROCK_MODEL_ID"))


def _call_bedrock(prompt: str) -> tuple[str, str]:
    region = _region()
    model_id = os.getenv("BEDROCK_MODEL_ID", "")
    if not region or not model_id:
        raise HTTPException(503, "Amazon Bedrock을 사용하려면 AWS_REGION과 BEDROCK_MODEL_ID를 설정하세요.")
    client = _boto_client("bedrock-runtime", region)
    try:
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0.2},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_boto_error(exc, "Amazon Bedrock")
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    text = "\n".join(block.get("text", "") for block in blocks if block.get("text")).strip()
    if not text:
        raise HTTPException(502, "Amazon Bedrock 응답에 텍스트가 없습니다.")
    return text, model_id


# ── 3) Amazon SageMaker JumpStart 엔드포인트 ─────────────────────────────────

def _sagemaker_configured() -> bool:
    return bool(_region() and os.getenv("SAGEMAKER_ENDPOINT_NAME"))


def _call_sagemaker(prompt: str) -> tuple[str, str]:
    region = _region()
    endpoint_name = os.getenv("SAGEMAKER_ENDPOINT_NAME", "")
    if not region or not endpoint_name:
        raise HTTPException(503, "SageMaker JumpStart를 사용하려면 AWS_REGION과 SAGEMAKER_ENDPOINT_NAME을 설정하세요.")
    client = _boto_client("sagemaker-runtime", region)
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 400, "temperature": 0.2, "return_full_text": False},
    }
    try:
        response = client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        body = json.loads(response["Body"].read().decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_boto_error(exc, "SageMaker")
    # JumpStart 컨테이너(TGI/DJL-LMI 등)는 배포 방식에 따라 응답 형태가 달라질 수 있다.
    if isinstance(body, list) and body:
        text = str(body[0].get("generated_text", body[0])).strip()
    elif isinstance(body, dict):
        choices = body.get("choices") or [{}]
        text = str(
            body.get("generated_text")
            or choices[0].get("message", {}).get("content", "")
            or body
        ).strip()
    else:
        text = str(body).strip()
    if not text:
        raise HTTPException(502, "SageMaker 엔드포인트 응답에 텍스트가 없습니다.")
    return text, endpoint_name


_HANDLERS = {"ec2": _call_ec2, "bedrock": _call_bedrock, "sagemaker": _call_sagemaker}


@router.get("/api/llm-bench/status")
def llm_bench_status() -> dict[str, object]:
    """3가지 서빙 방식의 설정 여부를 AWS 자격 증명 노출 없이 반환합니다."""
    region = _region()
    return {
        "ec2": {
            "label": "EC2/ECS + vLLM · Ollama",
            "configured": _ec2_configured(),
            "base_url": os.getenv("LLM_EC2_BASE_URL"),
            "model": os.getenv("LLM_EC2_MODEL"),
        },
        "bedrock": {
            "label": "Amazon Bedrock",
            "configured": _bedrock_configured(),
            "region": region,
            "model": os.getenv("BEDROCK_MODEL_ID"),
        },
        "sagemaker": {
            "label": "SageMaker JumpStart",
            "configured": _sagemaker_configured(),
            "region": region,
            "endpoint": os.getenv("SAGEMAKER_ENDPOINT_NAME"),
        },
    }


@router.post("/api/llm-bench/chat")
def llm_bench_chat(request: LlmBenchChatRequest) -> dict[str, object]:
    """선택한 서빙 방식으로 프롬프트를 보내고 응답과 지연 시간을 반환합니다."""
    handler = _HANDLERS.get(request.provider)
    if handler is None:
        raise HTTPException(422, "지원하지 않는 provider입니다.")
    started = time.monotonic()
    text, model = handler(request.prompt.strip())
    latency_ms = round((time.monotonic() - started) * 1000)
    return {"provider": request.provider, "model": model, "response": text, "latency_ms": latency_ms}
