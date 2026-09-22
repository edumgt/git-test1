from __future__ import annotations

import base64
from datetime import datetime, timezone
import io
import json
import os
import re
import time
from threading import Lock
from time import monotonic
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from .openapi_docs import install_openapi
except ImportError:
    from openapi_docs import install_openapi

try:
    from .db import get_db
except ImportError:
    from db import get_db

try:
    import orjson
except ImportError:
    DEFAULT_RESPONSE_CLASS = JSONResponse
else:
    class FastORJSONResponse(Response):
        media_type = "application/json"

        def render(self, content: object) -> bytes:
            return orjson.dumps(content)

    DEFAULT_RESPONSE_CLASS = FastORJSONResponse

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT_DIR / "app" / "frontend"
GENERATED_DIR = ROOT_DIR / "app" / "generated"
QUIZ_SQL_PATH = ROOT_DIR / "app" / "backend" / "quiz_seed.sql"
DOCS_DIR = ROOT_DIR / "docs"
NOTEBOOK_IMAGE_DIR = ROOT_DIR / "image"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
_MATPLOTLIB_FONT_CONFIGURED = False
ACTIVE_VISITOR_TTL_SECONDS = 90
_active_visitors: dict[str, float] = {}
_active_visitors_lock = Lock()

def _learn_document_map() -> dict[str, Path]:
    """Expose exactly the Markdown files shipped in docs/, without traversal."""
    return {
        path.stem: path
        for path in DOCS_DIR.glob("*.md")
        if re.fullmatch(r"[A-Za-z0-9_-]+", path.stem)
    }


def configure_matplotlib_korean_font(plt) -> None:
    """Use an installed Korean font when Matplotlib renders Korean labels."""
    global _MATPLOTLIB_FONT_CONFIGURED
    if _MATPLOTLIB_FONT_CONFIGURED:
        return

    import matplotlib.font_manager as fm

    candidates = [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for font_path in candidates:
        if font_path.exists():
            fm.fontManager.addfont(str(font_path))
            font_name = fm.FontProperties(fname=str(font_path)).get_name()
            plt.rcParams["font.family"] = font_name
            break
    plt.rcParams["axes.unicode_minus"] = False
    _MATPLOTLIB_FONT_CONFIGURED = True


app = FastAPI(
    title="Python Education Cloud API",
    version="2.0.0",
    description=(
        "주식 투자 입문 가이드"
    ),
    default_response_class=DEFAULT_RESPONSE_CLASS,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


try:
    from .routers.ml import router as ml_router
    from .routers.quant import router as quant_router
    from .routers.lean import router as lean_router
    from .routers.quiz import router as quiz_router
    from .routers.vocabulary_exam import EXAM_OPEN_AT, router as vocabulary_exam_router
    from .routers.tax import router as tax_router
    from .routers.rag import router as rag_router
    from .routers.lex import router as lex_router
    from .routers.auth import router as auth_router
    from .routers.llm_bench import router as llm_bench_router
    from . import pattern_detection
except ImportError:  # Allows `uvicorn main:app` from app/backend.
    from routers.ml import router as ml_router  # type: ignore
    from routers.quant import router as quant_router  # type: ignore
    from routers.lean import router as lean_router  # type: ignore
    from routers.quiz import router as quiz_router  # type: ignore
    from routers.vocabulary_exam import EXAM_OPEN_AT, router as vocabulary_exam_router  # type: ignore
    from routers.tax import router as tax_router  # type: ignore
    from routers.rag import router as rag_router  # type: ignore
    from routers.lex import router as lex_router  # type: ignore
    from routers.auth import router as auth_router  # type: ignore
    from routers.llm_bench import router as llm_bench_router  # type: ignore
    import pattern_detection  # type: ignore
app.include_router(ml_router)
app.include_router(quant_router)
app.include_router(lean_router)
app.include_router(vocabulary_exam_router)
app.include_router(lex_router)
app.include_router(auth_router)
# Routers registered below are also included before the schema is first requested;
# the OpenAPI factory is installed at the bottom of this module.

@app.middleware("http")
async def no_cache_static_assets(request, call_next):
    """Always fetch the latest local HTML, JavaScript, and CSS on page load.

    StaticFiles normally uses ETag/Last-Modified revalidation. The learning
    app is deployed as a single image, so an old shell or module can otherwise
    survive a deployment in a browser cache. ``no-store`` plus legacy
    revalidation headers makes local frontend assets non-cacheable for both
    browsers and intermediary proxies.
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class DartCompanySearchRequest(BaseModel):
    company_name: str = Field(default="삼성전자", min_length=1, max_length=80)
    limit: int = Field(default=10, ge=1, le=30)


class GroupNetworkRequest(BaseModel):
    group_name: str = Field(default="삼성", min_length=1, max_length=50)
    limit: int = Field(default=80, ge=1, le=100)


class DartCompanyListRequest(BaseModel):
    region: str = Field(default="서울특별시", max_length=30)
    emp_min: int | None = Field(default=None, ge=0, le=1_000_000)
    emp_max: int | None = Field(default=None, ge=0, le=1_000_000)
    bsns_year: str = Field(default="2024", pattern=r"^\d{4}$")
    limit: int = Field(default=50, ge=1, le=200)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _read_cpu_times() -> tuple[int, int]:
    """Return total and idle CPU ticks from Linux procfs."""
    with open("/proc/stat", encoding="utf-8") as proc_stat:
        first_line = proc_stat.readline().split()
    values = [int(value) for value in first_line[1:]]
    total = sum(values)
    # Linux reports idle and iowait separately; both mean the CPU was not
    # executing application work for this interval.
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


def _memory_usage() -> tuple[int, int]:
    """Return total and used memory bytes, preferring MemAvailable on Linux."""
    meminfo: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as proc_meminfo:
            for line in proc_meminfo:
                key, raw_value, *_ = line.split()
                meminfo[key.rstrip(":")] = int(raw_value) * 1024
        total = meminfo["MemTotal"]
        available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        return total, max(total - available, 0)
    except (FileNotFoundError, KeyError, ValueError):
        page_size = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page_size
        available = os.sysconf("SC_AVPHYS_PAGES") * page_size
        return total, max(total - available, 0)


@app.get("/api/system/resources")
def system_resources() -> dict[str, object]:
    """Return host CPU, memory and root-disk utilization for the admin view."""
    try:
        total_before, idle_before = _read_cpu_times()
        time.sleep(0.1)
        total_after, idle_after = _read_cpu_times()
        total_delta = total_after - total_before
        idle_delta = idle_after - idle_before
        cpu_used = 0.0 if total_delta <= 0 else (1 - idle_delta / total_delta) * 100

        memory_total, memory_used = _memory_usage()
        disk = os.statvfs("/")
        disk_total = disk.f_frsize * disk.f_blocks
        disk_free = disk.f_frsize * disk.f_bavail
        disk_used = max(disk_total - disk_free, 0)

        def usage(total: int, used: int) -> dict[str, int | float]:
            percent = (used / total * 100) if total else 0.0
            return {"total_bytes": total, "used_bytes": used,
                    "free_bytes": max(total - used, 0), "used_percent": round(percent, 1)}

        return {
            "cpu": {"used_percent": round(max(0.0, min(cpu_used, 100.0)), 1),
                    "logical_cores": os.cpu_count() or 1},
            "memory": usage(memory_total, memory_used),
            "disk": usage(disk_total, disk_used),
            "disk_mount": "/",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"서버 리소스 정보를 읽을 수 없습니다: {exc}") from exc


class VisitorHeartbeatRequest(BaseModel):
    visitor_id: str = Field(min_length=16, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


@app.post("/api/visitors/heartbeat")
def visitor_heartbeat(payload: VisitorHeartbeatRequest) -> dict[str, int]:
    """Register one browser briefly and return the current active-browser count.

    This is an in-memory presence indicator, not an analytics counter. A browser
    remains active for 90 seconds after its latest heartbeat, so closed tabs
    disappear without retaining personally identifiable visit history.
    """
    now = monotonic()
    with _active_visitors_lock:
        expired = [
            visitor_id
            for visitor_id, last_seen in _active_visitors.items()
            if now - last_seen > ACTIVE_VISITOR_TTL_SECONDS
        ]
        for visitor_id in expired:
            _active_visitors.pop(visitor_id, None)
        _active_visitors[payload.visitor_id] = now
        count = len(_active_visitors)
    return {"active_visitors": count}


@app.get("/api/learn/doc/{doc_id}")
def get_learn_doc(doc_id: str) -> dict[str, str]:
    # 시험지는 /api/vocabulary-exam에서 개시 시각을 통과한 뒤에만 제공한다.
    # 문서 API로 직접 접근해도 문제를 미리 볼 수 없게 한다.
    if doc_id == "voca-exam" and datetime.now(EXAM_OPEN_AT.tzinfo) < EXAM_OPEN_AT:
        raise HTTPException(status_code=403, detail="단어장 시험은 2026년 8월 10일 14:00(한국시간)에 공개됩니다.")
    target = _learn_document_map().get(doc_id)
    if not target:
        raise HTTPException(status_code=404, detail="지원하지 않는 학습 문서입니다.")
    return {"doc_id": doc_id, "file": target.name, "content": target.read_text(encoding="utf-8")}


@app.get("/api/search")
def search_learning_documents(q: str = "", limit: int = 8) -> dict[str, object]:
    """Meilisearch를 통해 학습 문서의 제목과 본문을 전체 검색한다."""
    query = q.strip()
    if len(query) < 2:
        return {"query": query, "hits": []}
    base_url = os.getenv("MEILI_URL", "http://meilisearch:7700").rstrip("/")
    master_key = os.getenv("MEILI_MASTER_KEY", "")
    payload = json.dumps({
        "q": query,
        "limit": max(1, min(limit, 20)),
        "attributesToRetrieve": ["doc_id", "title"],
        "attributesToHighlight": ["content"],
        "attributesToCrop": ["content:35"],
        "cropMarker": "…",
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if master_key:
        headers["Authorization"] = f"Bearer {master_key}"
    request = urllib.request.Request(f"{base_url}/indexes/learning_documents/search", data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="문서 검색 색인을 준비하고 있습니다. 잠시 후 다시 시도해 주세요.") from exc
    hits = [{
        "doc_id": item.get("doc_id", ""),
        "title": item.get("title", ""),
        "snippet": re.sub(r"<[^>]+>", "", item.get("_formatted", {}).get("content", "")),
    } for item in result.get("hits", [])]
    return {"query": query, "hits": hits, "estimated_total_hits": result.get("estimatedTotalHits", len(hits))}


def _dart_api_key() -> str:
    key = os.getenv("DART_API_KEY") or os.getenv("OPENDART_API_KEY")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="DART_API_KEY 또는 OPENDART_API_KEY 환경변수를 설정하세요.",
        )
    return key


@lru_cache(maxsize=1)
def _load_dart_corp_codes() -> list[dict[str, str]]:
    key = _dart_api_key()
    url = "https://opendart.fss.or.kr/api/corpCode.xml?" + urllib.parse.urlencode({"crtfc_key": key})
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = response.read()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DART 회사코드 목록 수신 실패: {exc}") from exc

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            xml_name = zf.namelist()[0]
            xml_bytes = zf.read(xml_name)
    except zipfile.BadZipFile as exc:
        message = payload[:200].decode("utf-8", errors="ignore")
        raise HTTPException(status_code=502, detail=f"DART 응답을 해석할 수 없습니다: {message}") from exc

    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, str]] = []
    for item in root.findall("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        corp_name = (item.findtext("corp_name") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        modify_date = (item.findtext("modify_date") or "").strip()
        if corp_code and corp_name:
            rows.append({
                "corp_code": corp_code,
                "corp_name": corp_name,
                "stock_code": stock_code,
                "modify_date": modify_date,
            })
    return rows


@lru_cache(maxsize=4096)
def _resolve_krx_yahoo_ticker(stock_code: str) -> dict[str, object]:
    if not stock_code:
        return {"ticker": None, "candidates": []}

    candidates = [f"{stock_code}.KS", f"{stock_code}.KQ"]
    found: list[str] = []
    for ticker in candidates:
        chart_url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + urllib.parse.quote(ticker)
            + "?range=5d&interval=1d"
        )
        try:
            with urllib.request.urlopen(chart_url, timeout=4) as response:
                text = response.read(5000).decode("utf-8", errors="ignore")
            if '"regularMarketPrice"' in text or '"timestamp"' in text:
                found.append(ticker)
        except Exception:
            continue

    return {"ticker": found[0] if found else f"{stock_code}.KS", "candidates": found or candidates}


@app.post("/api/dart/company-search")
def dart_company_search(req: DartCompanySearchRequest) -> dict[str, object]:
    query = req.company_name.strip()
    normalized = query.replace(" ", "").lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="회사명을 입력하세요.")

    rows = _load_dart_corp_codes()
    listed = [row for row in rows if row["stock_code"]]
    exact = [row for row in listed if row["corp_name"].replace(" ", "").lower() == normalized]
    partial = [row for row in listed if normalized in row["corp_name"].replace(" ", "").lower()]
    matches = (exact + [row for row in partial if row not in exact])[: req.limit]

    results = []
    for row in matches:
        ticker_info = _resolve_krx_yahoo_ticker(row["stock_code"])
        results.append({
            **row,
            "ticker": ticker_info["ticker"],
            "ticker_candidates": ticker_info["candidates"],
            "display": f'{ticker_info["ticker"] or row["stock_code"]}, {row["corp_name"]}',
        })

    return {
        "query": query,
        "count": len(results),
        "results": results,
        "source": "OpenDART corpCode.xml",
        "notes": [
            "DART 회사코드 목록에서 상장기업(stock_code 보유 기업)만 검색합니다.",
            "DART는 .KS/.KQ suffix를 제공하지 않아 조회 가능한 Yahoo ticker 후보로 보완 표시합니다.",
        ],
    }


@lru_cache(maxsize=6)
def _pykrx_market_data(ref_date: str) -> dict[str, dict]:
    """Return {stock_code: {market, market_cap, close}} using pykrx.

    ref_date is "YYYYMMDD" and acts as the LRU cache key so that data is
    refreshed automatically each new trading day.  Failures are silently
    swallowed so that group-network still returns results even when pykrx
    cannot reach KRX servers.
    """
    try:
        from pykrx import stock as krx

        result: dict[str, dict] = {}

        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                cap_df = krx.get_market_cap_by_ticker(ref_date, market=mkt)
                for ticker, row in cap_df.iterrows():
                    result[ticker] = {
                        "market":     mkt,
                        "market_cap": int(row.get("시가총액", 0)),
                        "close":      int(row.get("종가", 0)),
                    }
            except Exception:
                pass

        return result
    except Exception:
        return {}


@app.post("/api/dart/group-network")
def dart_group_network(req: GroupNetworkRequest) -> dict[str, object]:
    """Search DART listed companies by group/conglomerate keyword and enrich
    each match with live market-cap data from pykrx."""
    import datetime

    query = req.group_name.strip()
    normalized = query.replace(" ", "").lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="그룹명을 입력하세요.")

    rows = _load_dart_corp_codes()
    listed = [row for row in rows if row["stock_code"]]

    # Exact name prefix matches first, then partial matches
    exact_codes = {r["corp_code"] for r in listed if r["corp_name"].replace(" ", "").lower().startswith(normalized)}
    exact = [r for r in listed if r["corp_code"] in exact_codes]
    partial = [r for r in listed if normalized in r["corp_name"].replace(" ", "").lower()
               and r["corp_code"] not in exact_codes]
    matches = (exact + partial)[: req.limit]

    # Try today first; fall back to yesterday for weekends / holidays
    today = datetime.date.today()
    ref_date = today.strftime("%Y%m%d")
    market_data = _pykrx_market_data(ref_date)
    if not market_data:
        yesterday = (today - datetime.timedelta(days=1)).strftime("%Y%m%d")
        market_data = _pykrx_market_data(yesterday)

    results = []
    for row in matches:
        sc = row["stock_code"]
        mkt_info = market_data.get(sc, {})
        market_label = mkt_info.get("market", "기타")
        results.append({
            "corp_code":   row["corp_code"],
            "corp_name":   row["corp_name"],
            "stock_code":  sc,
            "modify_date": row["modify_date"],
            "market":      market_label,
            "market_cap":  mkt_info.get("market_cap", 0),
            "close":       mkt_info.get("close", 0),
            "dart_url":    f"https://dart.fss.or.kr/corp/main.do?corp_code={row['corp_code']}",
        })

    # Sort by market cap descending so flagship companies appear first
    results.sort(key=lambda x: x["market_cap"], reverse=True)

    total_market_cap = sum(r["market_cap"] for r in results)
    kospi_count  = sum(1 for r in results if r["market"] == "KOSPI")
    kosdaq_count = sum(1 for r in results if r["market"] == "KOSDAQ")

    return {
        "query":            query,
        "count":            len(results),
        "total_market_cap": total_market_cap,
        "kospi_count":      kospi_count,
        "kosdaq_count":     kosdaq_count,
        "results":          results,
        "source":           "OpenDART corpCode.xml + pykrx KRX 시장데이터",
    }


@lru_cache(maxsize=10000)
def _fetch_company_detail(corp_code: str) -> dict:
    """Fetch company overview (address, bizr_no) from DART company.json."""
    key = _dart_api_key()
    url = ("https://opendart.fss.or.kr/api/company.json?"
           + urllib.parse.urlencode({"crtfc_key": key, "corp_code": corp_code}))
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read())
        return data if data.get("status") == "000" else {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_all_listed_details() -> list[dict]:
    """Batch-fetch company detail for all listed companies. Cached in-process.

    First call may take ~30 s; subsequent calls are instant.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    rows = _load_dart_corp_codes()
    listed = [r for r in rows if r["stock_code"]]

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_to_row = {
            executor.submit(_fetch_company_detail, r["corp_code"]): r
            for r in listed
        }
        for future in as_completed(future_to_row):
            row = future_to_row[future]
            detail = future.result()
            if detail:
                results.append({
                    "corp_code":   row["corp_code"],
                    "corp_name":   detail.get("corp_name") or row["corp_name"],
                    "stock_code":  row["stock_code"],
                    "modify_date": row["modify_date"],
                    "bizr_no":     detail.get("bizr_no", ""),
                    "jurir_no":    detail.get("jurir_no", ""),
                    "adres":       detail.get("adres", ""),
                    "ceo_nm":      detail.get("ceo_nm", ""),
                    "corp_cls":    detail.get("corp_cls", ""),
                    "est_dt":      detail.get("est_dt", ""),
                })
    return results


@lru_cache(maxsize=20000)
def _fetch_emp_count(corp_code: str, bsns_year: str) -> int:
    """Return total employee count from DART empSttus.json. Returns -1 on failure."""
    key = _dart_api_key()
    url = ("https://opendart.fss.or.kr/api/empSttus.json?"
           + urllib.parse.urlencode({
               "crtfc_key":  key,
               "corp_code":  corp_code,
               "bsns_year":  bsns_year,
               "reprt_code": "11011",  # 사업보고서
           }))
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.loads(response.read())
        if data.get("status") != "000":
            return -1

        def to_int(v: object) -> int:
            try:
                return int(str(v).replace(",", "").strip() or "0")
            except (ValueError, TypeError):
                return 0

        items = data.get("list", [])
        if not items:
            return -1

        total_rows = [x for x in items if "합계" in str(x.get("nm", ""))]
        target = total_rows or items[:1]
        total = sum(to_int(x.get("rgllbr_co", 0)) + to_int(x.get("cnttk_co", 0)) for x in target)
        if total > 0:
            return total
        return to_int(items[0].get("jan_blyy_empcnt", -1)) or -1
    except Exception:
        return -1


@app.post("/api/dart/company-list")
def dart_company_list(req: DartCompanyListRequest) -> dict[str, object]:
    """Search listed companies by region (address substring) and/or employee count."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    region = req.region.strip()
    use_emp = req.emp_min is not None or req.emp_max is not None

    all_companies = _load_all_listed_details()

    candidates = (
        [c for c in all_companies if region in c.get("adres", "")]
        if region else list(all_companies)
    )

    if use_emp:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_fetch_emp_count, c["corp_code"], req.bsns_year): c
                for c in candidates
            }
            filtered: list[dict] = []
            for future in as_completed(futures):
                company = futures[future]
                emp = future.result()
                if emp < 0:
                    continue
                if req.emp_min is not None and emp < req.emp_min:
                    continue
                if req.emp_max is not None and emp > req.emp_max:
                    continue
                filtered.append({**company, "emp_count": emp})
    else:
        filtered = [{**c, "emp_count": None} for c in candidates]

    results = sorted(filtered, key=lambda x: x["corp_name"])[: req.limit]

    return {
        "region":        region or None,
        "emp_min":       req.emp_min,
        "emp_max":       req.emp_max,
        "bsns_year":     req.bsns_year,
        "total_matched": len(filtered),
        "count":         len(results),
        "results":       results,
        "source":        "OpenDART company.json" + (" + empSttus.json" if use_emp else ""),
    }


def _calc_rsi(series: "pd.Series", period: int = 14) -> "pd.Series":
    import pandas as pd
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


# ── 산업 경쟁력 분석 ─────────────────────────────────────────────────────────

class PorterRequest(BaseModel):
    industry: str = "반도체"
    scores: dict[str, float] = {
        "경쟁강도":       8.0,
        "신규진입 위협":  6.0,
        "대체재 위협":    4.0,
        "구매자 교섭력":  5.0,
        "공급자 교섭력":  7.0,
    }

class SectorRequest(BaseModel):
    tickers: list[str] = ["SOXX", "XLE", "XLF", "XLV", "XLK", "XLI"]
    period:  str       = "1y"

class PeerRequest(BaseModel):
    tickers: dict[str, str] = {
        "삼성전자": "005930.KS",
        "SK하이닉스": "000660.KS",
        "엔비디아": "NVDA",
        "인텔": "INTC",
    }

class LifecycleRequest(BaseModel):
    stage:    str = "성장기"   # 도입기 성장기 성숙기 쇠퇴기
    industry: str = "전기차"


@app.post("/api/industry/porter")
def industry_porter(req: PorterRequest) -> dict[str, object]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import io, base64
    configure_matplotlib_korean_font(plt)

    DARK, SURF, BORDER, TEXT, MUTED = "#0f172a","#1e293b","#334155","#e2e8f0","#64748b"
    ACCENT = "#3b82f6"
    C_HIGH  = "#ef4444"   # 위협 강함
    C_MED   = "#f59e0b"
    C_LOW   = "#22c55e"   # 위협 약함

    forces = list(req.scores.keys())
    values = [max(0.0, min(10.0, float(v))) for v in req.scores.values()]
    N = len(forces)

    def force_color(v):
        if v >= 7: return C_HIGH
        if v >= 4: return C_MED
        return C_LOW

    fig = plt.figure(figsize=(14, 8), facecolor=DARK)
    gs  = gridspec.GridSpec(1, 2, figure=fig, wspace=0.35,
                            left=0.05, right=0.97, top=0.88, bottom=0.1)

    # ── Panel 1: Radar (polar) ──────────────────────────────────────────────
    ax_r = fig.add_subplot(gs[0, 0], polar=True, facecolor=SURF)
    angles = [n / N * 2 * np.pi for n in range(N)]
    angles += angles[:1]
    vals_plot = values + values[:1]

    ax_r.set_theta_offset(np.pi / 2)
    ax_r.set_theta_direction(-1)
    ax_r.set_ylim(0, 10)
    ax_r.set_yticks([2, 4, 6, 8, 10])
    ax_r.set_yticklabels(["2","4","6","8","10"], color=MUTED, fontsize=7)
    ax_r.set_xticks(angles[:-1])
    ax_r.set_xticklabels(forces, color=TEXT, fontsize=9)
    ax_r.spines["polar"].set_color(BORDER)
    ax_r.tick_params(colors=MUTED)
    ax_r.grid(color=BORDER, linewidth=0.8)

    # 배경 zone 색칠 (위험 등급)
    for thresh, col in [(10, "#ef444411"), (7, "#f59e0b11"), (4, "#22c55e11")]:
        zone = [thresh] * N + [thresh]
        ax_r.fill(angles, zone, color=col)

    ax_r.plot(angles, vals_plot, color=ACCENT, lw=2.2, zorder=3)
    ax_r.fill(angles, vals_plot, color=ACCENT, alpha=0.25, zorder=2)
    for a, v in zip(angles[:-1], values):
        ax_r.plot(a, v, "o", color=force_color(v), ms=8, zorder=4)
        ax_r.text(a, v + 0.8, f"{v:.1f}", ha="center", va="center",
                  fontsize=8, color=TEXT, fontweight="bold")

    ax_r.set_title(f"Porter 5 Forces\n{req.industry} 산업",
                   color=TEXT, fontsize=11, fontweight="bold", pad=18)

    # ── Panel 2: 수평 바 + 해석 ─────────────────────────────────────────────
    ax_b = fig.add_subplot(gs[0, 1], facecolor=SURF)
    bars = ax_b.barh(forces, values, color=[force_color(v) for v in values],
                     height=0.5, zorder=2)
    ax_b.set_xlim(0, 10)
    ax_b.axvline(4, color=MUTED, lw=0.8, ls="--", alpha=0.5)
    ax_b.axvline(7, color=MUTED, lw=0.8, ls="--", alpha=0.5)
    ax_b.text(2, -0.8, "약함", ha="center", color=C_LOW, fontsize=8)
    ax_b.text(5.5, -0.8, "보통", ha="center", color=C_MED, fontsize=8)
    ax_b.text(8.5, -0.8, "강함", ha="center", color=C_HIGH, fontsize=8)

    INTERP = {
        "경쟁강도":      {(7,10):"경쟁사 많음 → 가격경쟁↑·수익성↓", (4,7):"과점 구조 → 안정적", (0,4):"독점적 지위"},
        "신규진입 위협": {(7,10):"진입장벽 낮음 → 점유율 위협", (4,7):"중간 진입장벽", (0,4):"특허·규제·규모 장벽↑"},
        "대체재 위협":   {(7,10):"대체재 다수 → 가격결정력↓", (4,7):"부분 대체 가능", (0,4):"대체재 없음"},
        "구매자 교섭력": {(7,10):"구매자 협상력↑ → 마진압박", (4,7):"균형 협상", (0,4):"공급자 우위"},
        "공급자 교섭력": {(7,10):"원재료 공급 불안정·비용↑", (4,7):"복수 공급선 확보", (0,4):"공급 안정"},
    }

    for i, (bar, force, val) in enumerate(zip(bars, forces, values)):
        ax_b.text(val + 0.15, bar.get_y() + bar.get_height()/2,
                  f"{val:.1f}", va="center", fontsize=9,
                  color=TEXT, fontweight="bold")
        for (lo, hi), msg in INTERP.get(force, {}).items():
            if lo <= val <= hi:
                ax_b.text(10.2, bar.get_y() + bar.get_height()/2,
                          msg, va="center", fontsize=7, color=MUTED)
                break

    ax_b.set_xlabel("위협 강도 (0 = 낮음, 10 = 높음)", color=MUTED, fontsize=8)
    ax_b.tick_params(colors=TEXT, labelsize=9)
    ax_b.spines[:].set_color(BORDER)
    ax_b.set_title("5 Forces 위협 강도 분석", color=TEXT, fontsize=11,
                   fontweight="bold", pad=10)
    ax_b.set_xlim(0, 16)   # 오른쪽 텍스트 공간

    # 종합 점수
    avg = sum(values) / N
    grade = "고위험" if avg >= 7 else "중위험" if avg >= 4 else "저위험"
    grade_col = C_HIGH if avg >= 7 else C_MED if avg >= 4 else C_LOW
    fig.suptitle(
        f"산업 경쟁력 분석  |  {req.industry}  |  종합 위협 지수: {avg:.1f}/10  [{grade}]",
        color=TEXT, fontsize=12, fontweight="bold", y=0.97)
    fig.text(0.5, 0.01,
             "■ 녹색: 약함(0-4)  ■ 주황: 보통(4-7)  ■ 빨강: 강함(7-10)",
             ha="center", fontsize=8, color=MUTED)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=DARK, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    result = {f: {"score": v, "level": "강함" if v>=7 else "보통" if v>=4 else "약함"}
              for f, v in zip(forces, values)}
    return {"image": img, "industry": req.industry,
            "avg_score": round(avg, 2), "grade": grade, "forces": result}


SECTOR_LABELS = {
    "SOXX": "반도체 (SOXX)", "XLE": "에너지 (XLE)", "XLF": "금융 (XLF)",
    "XLV":  "헬스케어 (XLV)", "XLK": "기술 (XLK)",  "XLI": "산업재 (XLI)",
    "XLY":  "소비재경기 (XLY)","XLP": "소비재필수 (XLP)","XLB": "소재 (XLB)",
    "XLRE": "부동산 (XLRE)",  "XLU": "유틸리티 (XLU)","IBB": "바이오 (IBB)",
}

@app.post("/api/industry/sector")
def industry_sector(req: SectorRequest) -> dict[str, object]:
    import yfinance as yf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import pandas as pd
    import io, base64
    configure_matplotlib_korean_font(plt)

    DARK, SURF, BORDER, TEXT, MUTED = "#0f172a","#1e293b","#334155","#e2e8f0","#64748b"
    COLORS = ["#3b82f6","#22c55e","#f59e0b","#ef4444","#a855f7",
              "#06b6d4","#f97316","#84cc16","#ec4899","#14b8a6","#8b5cf6","#fb923c"]

    raw: dict[str, pd.Series] = {}
    for t in req.tickers:
        try:
            df = yf.download(t, period=req.period, progress=False, auto_adjust=True)
            if df.empty: continue
            s = df["Close"]
            if isinstance(s, pd.DataFrame): s = s.iloc[:, 0]
            s = s.dropna()
            if len(s) > 5: raw[t] = s
        except Exception:
            pass

    if not raw:
        raise HTTPException(status_code=503, detail="데이터를 가져올 수 없습니다.")

    fig = plt.figure(figsize=(14, 10), facecolor=DARK)
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.32,
                            left=0.07, right=0.97, top=0.92, bottom=0.07)

    # Panel 1: 정규화 수익률
    ax1 = fig.add_subplot(gs[0, :], facecolor=SURF)
    for i, (t, s) in enumerate(raw.items()):
        norm = (s / s.iloc[0] - 1) * 100
        ax1.plot(norm.index, norm.values, color=COLORS[i % len(COLORS)],
                 lw=1.8, label=SECTOR_LABELS.get(t, t))
    ax1.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax1.set_title("섹터 ETF 정규화 누적 수익률 (%)", color=TEXT, fontsize=10, pad=6)
    ax1.tick_params(colors=TEXT, labelsize=7)
    ax1.spines[:].set_color(BORDER)
    ax1.legend(fontsize=7, facecolor=SURF, labelcolor=TEXT,
               ncol=4, loc="upper left", framealpha=0.7)
    ax1.tick_params(axis="x", rotation=30)
    for lbl in ax1.get_xticklabels(): lbl.set_fontsize(6)

    # Panel 2: 기간 수익률 바
    ax2 = fig.add_subplot(gs[1, 0], facecolor=SURF)
    names, returns, cols = [], [], []
    for i, (t, s) in enumerate(raw.items()):
        r = (s.iloc[-1] / s.iloc[0] - 1) * 100
        names.append(SECTOR_LABELS.get(t, t))
        returns.append(r)
        cols.append(COLORS[i % len(COLORS)])
    order = sorted(range(len(returns)), key=lambda x: returns[x], reverse=True)
    names_s  = [names[i] for i in order]
    returns_s = [returns[i] for i in order]
    cols_s   = [cols[i] for i in order]
    bars = ax2.barh(names_s, returns_s, color=cols_s, height=0.6)
    ax2.axvline(0, color=MUTED, lw=0.8)
    for bar, v in zip(bars, returns_s):
        ax2.text(v + (0.3 if v >= 0 else -0.3), bar.get_y() + bar.get_height()/2,
                 f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right",
                 fontsize=7, color=TEXT)
    ax2.set_title(f"기간 수익률 순위 ({req.period})", color=TEXT, fontsize=10, pad=6)
    ax2.tick_params(colors=TEXT, labelsize=7)
    ax2.spines[:].set_color(BORDER)

    # Panel 3: 변동성 vs 수익률 (리스크-리턴 산점도)
    ax3 = fig.add_subplot(gs[1, 1], facecolor=SURF)
    for i, (t, s) in enumerate(raw.items()):
        ret  = (s.iloc[-1] / s.iloc[0] - 1) * 100
        vol  = s.pct_change().std() * (252**0.5) * 100
        ax3.scatter(vol, ret, color=COLORS[i % len(COLORS)], s=100, zorder=3)
        ax3.text(vol + 0.3, ret, SECTOR_LABELS.get(t, t).split("(")[0].strip(),
                 fontsize=6.5, color=TEXT)
    ax3.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax3.set_xlabel("연환산 변동성 (%)", color=MUTED, fontsize=8)
    ax3.set_ylabel(f"수익률 ({req.period}) %", color=MUTED, fontsize=8)
    ax3.set_title("리스크-리턴 산점도", color=TEXT, fontsize=10, pad=6)
    ax3.tick_params(colors=TEXT, labelsize=7)
    ax3.spines[:].set_color(BORDER)
    ax3.grid(color=BORDER, lw=0.5, alpha=0.5)

    fig.suptitle(f"섹터 주가 비교 분석  |  {req.period}",
                 color=TEXT, fontsize=12, fontweight="bold", y=0.97)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=DARK, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    summary = {}
    for t, s in raw.items():
        summary[SECTOR_LABELS.get(t, t)] = {
            "return_pct": round((s.iloc[-1]/s.iloc[0]-1)*100, 2),
            "annual_vol":  round(s.pct_change().std()*(252**0.5)*100, 2),
        }
    return {"image": img, "summary": summary}


@app.post("/api/industry/peer")
def industry_peer(req: PeerRequest) -> dict[str, object]:
    import math

    import yfinance as yf

    if not req.tickers:
        raise HTTPException(status_code=400, detail="비교할 종목을 1개 이상 입력하세요.")
    if len(req.tickers) > 12:
        raise HTTPException(status_code=400, detail="Peer Comparison은 최대 12개 종목까지 지원합니다.")

    def as_float(value):
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    rows: list[dict[str, object]] = []
    for name, ticker in req.tickers.items():
        label = (name or ticker).strip()[:40]
        symbol = (ticker or "").strip().upper()
        if not symbol:
            continue
        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            rows.append({
                "company": label,
                "ticker": symbol,
                "error": f"데이터 수신 실패: {exc}",
            })
            continue

        market_cap = as_float(info.get("marketCap"))
        revenue_growth = as_float(info.get("revenueGrowth"))
        operating_margin = as_float(info.get("operatingMargins"))
        debt_to_equity = as_float(info.get("debtToEquity"))
        roe = as_float(info.get("returnOnEquity"))
        per = as_float(info.get("trailingPE"))
        pbr = as_float(info.get("priceToBook"))

        rows.append({
            "company": label,
            "ticker": symbol,
            "market_cap_krw_100m": round(market_cap / 1e8, 0) if market_cap is not None else None,
            "revenue_growth_pct": round(revenue_growth * 100, 1) if revenue_growth is not None else None,
            "operating_margin_pct": round(operating_margin * 100, 1) if operating_margin is not None else None,
            "per": round(per, 1) if per is not None else None,
            "pbr": round(pbr, 2) if pbr is not None else None,
            "debt_to_equity_pct": round(debt_to_equity, 1) if debt_to_equity is not None else None,
            "roe_pct": round(roe * 100, 1) if roe is not None else None,
            "currency": info.get("currency"),
            "sector": info.get("sector"),
        })

    if not rows:
        raise HTTPException(status_code=400, detail="유효한 종목 코드가 없습니다.")

    valid_rows = [r for r in rows if not r.get("error")]
    leader = None
    if valid_rows:
        leader = max(
            valid_rows,
            key=lambda r: (
                r.get("operating_margin_pct") if r.get("operating_margin_pct") is not None else -999,
                r.get("roe_pct") if r.get("roe_pct") is not None else -999,
            ),
        ).get("company")

    return {
        "rows": rows,
        "leader": leader,
        "notes": [
            "동종 기업 여부를 먼저 확인한 뒤 멀티플 차이를 해석하세요.",
            "PER/PBR은 성장률, 수익성, 재무건전성과 함께 봐야 합니다.",
            "Yahoo Finance 항목 누락 시 일부 값은 빈칸으로 표시됩니다.",
        ],
    }


LIFECYCLE_DATA = {
    "도입기": {
        "idx": 0, "color": "#3b82f6",
        "chars": ["매출 낮음·손실 가능", "높은 R&D 비용", "선도자 이점 확보 기회"],
        "strategy": ["성장주 투자", "VC/초기 투자", "기술 모멘텀 추종"],
        "examples": ["양자컴퓨터", "뇌-컴퓨터 인터페이스", "핵융합"],
    },
    "성장기": {
        "idx": 1, "color": "#22c55e",
        "chars": ["매출 급증", "경쟁자 진입 시작", "규모의 경제 달성"],
        "strategy": ["성장주 비중 확대", "시장점유율 1위 기업 주목", "PEG 지표 활용"],
        "examples": ["AI 반도체", "전기차", "클라우드"],
    },
    "성숙기": {
        "idx": 2, "color": "#f59e0b",
        "chars": ["성장 둔화", "가격경쟁 심화", "배당·자사주 매입 증가"],
        "strategy": ["가치주·배당주 투자", "PER·PBR 저평가 선별", "FCF 중심 분석"],
        "examples": ["스마트폰", "자동차", "은행"],
    },
    "쇠퇴기": {
        "idx": 3, "color": "#ef4444",
        "chars": ["매출 감소", "구조조정·M&A", "대체재에 시장 잠식"],
        "strategy": ["Short 전략 고려", "방어주 비중 축소", "Exit 타이밍 관리"],
        "examples": ["인쇄매체", "유선전화", "DVD 렌탈"],
    },
}

@app.post("/api/industry/lifecycle")
def industry_lifecycle(req: LifecycleRequest) -> dict[str, object]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np
    import io, base64
    configure_matplotlib_korean_font(plt)

    DARK, SURF, BORDER, TEXT, MUTED = "#0f172a","#1e293b","#334155","#e2e8f0","#64748b"

    stage_info = LIFECYCLE_DATA.get(req.stage, LIFECYCLE_DATA["성장기"])
    cur_idx    = stage_info["idx"]

    # S-curve (logistic)
    x = np.linspace(-6, 10, 400)
    y = 100 / (1 + np.exp(-x * 0.9))          # 도입~성숙
    decline = np.linspace(0, 1, 100)
    x_full  = np.concatenate([x, x[-1] + decline * 4])
    y_full  = np.concatenate([y, y[-1] - decline * 35])  # 쇠퇴

    # 각 단계 x 범위
    stage_x = [(-6, -1.5), (-1.5, 3), (3, 7), (7, x_full[-1])]
    stage_colors = [d["color"] for d in LIFECYCLE_DATA.values()]
    stage_names  = list(LIFECYCLE_DATA.keys())

    fig, (ax_main, ax_info) = plt.subplots(1, 2, figsize=(14, 7),
                                           gridspec_kw={"width_ratios": [3, 2]},
                                           facecolor=DARK)

    # ── 메인: S-curve ────────────────────────────────────────────────────────
    ax_main.set_facecolor(SURF)
    for i, ((x0, x1), col, name) in enumerate(zip(stage_x, stage_colors, stage_names)):
        mask = (x_full >= x0) & (x_full <= x1)
        alpha = 0.9 if i == cur_idx else 0.35
        lw    = 3.5 if i == cur_idx else 1.5
        ax_main.plot(x_full[mask], y_full[mask], color=col, lw=lw, alpha=alpha, zorder=3)
        mid_x = (x0 + x1) / 2
        mid_y = np.interp(mid_x, x_full, y_full)
        ax_main.text(mid_x, mid_y + (8 if i != 3 else -8), name,
                     ha="center", fontsize=10, color=col,
                     fontweight="bold" if i == cur_idx else "normal",
                     bbox=dict(boxstyle="round,pad=0.3",
                               facecolor=SURF if i != cur_idx else col + "33",
                               edgecolor=col, linewidth=1.5 if i == cur_idx else 0.8))
        # 단계 구분선
        if i < 3:
            ax_main.axvline(x1, color=BORDER, lw=1, ls=":", alpha=0.7)

    # 현재 위치 표시
    cur_x0, cur_x1 = stage_x[cur_idx]
    cur_mid = (cur_x0 + cur_x1) / 2
    cur_y   = np.interp(cur_mid, x_full, y_full)
    ax_main.scatter([cur_mid], [cur_y], color=stage_info["color"],
                    s=200, zorder=5, edgecolors=TEXT, linewidths=1.5)
    ax_main.annotate(f"▶ {req.industry}\n({req.stage})",
                     xy=(cur_mid, cur_y), xytext=(cur_mid + 0.5, cur_y - 18),
                     fontsize=9, color=stage_info["color"], fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=stage_info["color"], lw=1.5))

    ax_main.set_xlabel("시간 →", color=MUTED, fontsize=10)
    ax_main.set_ylabel("시장 규모 / 매출", color=MUTED, fontsize=10)
    ax_main.set_title("산업 생애주기 (Industry Life Cycle)", color=TEXT,
                      fontsize=11, fontweight="bold", pad=10)
    ax_main.tick_params(colors=MUTED, labelsize=7)
    ax_main.set_xticklabels([])
    ax_main.spines[:].set_color(BORDER)
    ax_main.set_ylim(-5, 115)

    # ── 사이드: 단계별 특성표 ────────────────────────────────────────────────
    ax_info.set_facecolor(DARK)
    ax_info.axis("off")

    y_pos = 0.97
    ax_info.text(0.5, y_pos, f"{req.industry}  |  {req.stage}", ha="center",
                 fontsize=12, fontweight="bold", color=stage_info["color"],
                 transform=ax_info.transAxes)
    y_pos -= 0.08

    sections = [
        ("특징", stage_info["chars"], "#e2e8f0"),
        ("투자 전략", stage_info["strategy"], "#3b82f6"),
        ("예시 산업", stage_info["examples"], "#a855f7"),
    ]
    for title, items, col in sections:
        ax_info.text(0.05, y_pos, title, fontsize=9, fontweight="bold",
                     color=col, transform=ax_info.transAxes)
        y_pos -= 0.06
        for item in items:
            ax_info.text(0.08, y_pos, f"• {item}", fontsize=8.5, color=TEXT,
                         transform=ax_info.transAxes)
            y_pos -= 0.065
        y_pos -= 0.02

    # 4단계 요약 타임라인
    y_pos -= 0.02
    ax_info.text(0.5, y_pos, "── 4단계 흐름 ──", ha="center",
                 fontsize=8, color=MUTED, transform=ax_info.transAxes)
    y_pos -= 0.065
    for i, (name, data) in enumerate(LIFECYCLE_DATA.items()):
        marker = "●" if i == cur_idx else "○"
        weight = "bold" if i == cur_idx else "normal"
        ax_info.text(0.1 + i * 0.22, y_pos, f"{marker}\n{name}", ha="center",
                     fontsize=8, color=data["color"], fontweight=weight,
                     transform=ax_info.transAxes)

    fig.suptitle("산업 생애주기 분석  |  단계별 투자 전략",
                 color=TEXT, fontsize=12, fontweight="bold", y=0.99)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=DARK, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    return {"image": img, "stage": req.stage, "industry": req.industry,
            "characteristics": stage_info["chars"],
            "strategies": stage_info["strategy"]}


# ── 거시경제현황 1: yfinance 실시간 ──────────────────────────────────────────

class MacroRealtimeRequest(BaseModel):
    tickers: list[str] = ["^TNX", "CL=F", "^GSPC", "^KS11", "GC=F", "EURUSD=X"]
    period:  str       = "1y"   # 1mo 3mo 6mo 1y 2y 5y


class MarketSnapshotRequest(BaseModel):
    tickers: list[str] = ["^KS11", "^IXIC", "KRW=X"]


class PortfolioCombinationRequest(BaseModel):
    ticker_a: str = Field(default="AAPL", min_length=1, max_length=20)
    ticker_b: str = Field(default="JNJ", min_length=1, max_length=20)
    period: str = Field(default="1y", pattern=r"^(3mo|6mo|1y|2y)$")


MARKET_SNAPSHOT_LABELS = {
    "^KS11": "KOSPI",
    "^IXIC": "NASDAQ",
    "KRW=X": "USD/KRW",
}

TICKER_LABELS = {
    "^TNX":     "미국 10년물 금리",
    "CL=F":     "WTI 유가",
    "^GSPC":    "S&P 500",
    "^KS11":    "KOSPI",
    "GC=F":     "금 (Gold)",
    "EURUSD=X": "EUR/USD",
    "BTC-USD":  "Bitcoin",
    "^IRX":     "미국 단기금리(3M)",
    "^VIX":     "VIX 공포지수",
    "DX-Y.NYB": "달러 인덱스",
}

VOLUME_CLOUD_MARKETS = {
    "us": [
        {"ticker": "AAPL", "name": "Apple"}, {"ticker": "MSFT", "name": "Microsoft"},
        {"ticker": "GOOGL", "name": "Alphabet"}, {"ticker": "AMZN", "name": "Amazon"},
        {"ticker": "NVDA", "name": "NVIDIA"}, {"ticker": "META", "name": "Meta"},
        {"ticker": "TSLA", "name": "Tesla"},
    ],
    "kr": [
        {"ticker": "005930.KS", "name": "삼성전자"},
        {"ticker": "000660.KS", "name": "SK하이닉스"},
        {"ticker": "373220.KS", "name": "LG에너지솔루션"},
        {"ticker": "207940.KS", "name": "삼성바이오로직스"},
        {"ticker": "005380.KS", "name": "현대차"},
        {"ticker": "000270.KS", "name": "기아"},
        {"ticker": "068270.KS", "name": "셀트리온"},
        {"ticker": "105560.KS", "name": "KB금융"},
        {"ticker": "055550.KS", "name": "신한지주"},
        {"ticker": "012330.KS", "name": "현대모비스"},
        {"ticker": "035420.KS", "name": "NAVER"},
        {"ticker": "028260.KS", "name": "삼성물산"},
        {"ticker": "006400.KS", "name": "삼성SDI"},
        {"ticker": "051910.KS", "name": "LG화학"},
        {"ticker": "003670.KS", "name": "포스코홀딩스"},
        {"ticker": "035720.KS", "name": "카카오"},
        {"ticker": "096770.KS", "name": "SK이노베이션"},
        {"ticker": "034730.KS", "name": "SK"},
        {"ticker": "086790.KS", "name": "하나금융지주"},
        {"ticker": "032830.KS", "name": "삼성생명"},
    ],
}


def _extract_close_series(frame):
    close = frame["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return close.dropna()


@app.post("/api/market/portfolio-combination")
def portfolio_combination(req: PortfolioCombinationRequest) -> dict[str, object]:
    """Compare two real tickers and return a plain-language diversification signal."""
    import pandas as pd
    import yfinance as yf

    def clean_ticker(raw: str) -> str:
        ticker = raw.strip().upper()
        if not re.fullmatch(r"[A-Z0-9.^=\-]{1,20}", ticker):
            raise HTTPException(status_code=422, detail="올바른 종목 코드를 입력해 주세요.")
        return ticker

    ticker_a = clean_ticker(req.ticker_a)
    ticker_b = clean_ticker(req.ticker_b)
    if ticker_a == ticker_b:
        raise HTTPException(status_code=422, detail="서로 다른 두 종목을 선택해 주세요.")

    prices: dict[str, pd.Series] = {}
    unavailable: list[str] = []
    for ticker in (ticker_a, ticker_b):
        try:
            frame = yf.download(ticker, period=req.period, interval="1d", progress=False,
                                auto_adjust=True, threads=False)
            close = _extract_close_series(frame)
            if len(close) < 21:
                unavailable.append(ticker)
            else:
                prices[ticker] = close
        except Exception:
            unavailable.append(ticker)

    if unavailable:
        names = ", ".join(unavailable)
        raise HTTPException(status_code=422, detail=f"{names}의 충분한 가격 데이터를 찾지 못했습니다.")

    # 거래일이 겹치는 구간의 일간 변화만 이용한다. 화면에는 수식 대신 신호와 문장만 노출한다.
    aligned_prices = pd.concat(prices, axis=1, join="inner").dropna()
    daily_moves = aligned_prices.pct_change(fill_method=None).dropna()
    if len(daily_moves) < 20:
        raise HTTPException(status_code=422, detail="두 종목의 함께 비교할 수 있는 거래일이 부족합니다.")
    relationship = float(daily_moves.corr().iloc[0, 1])

    if relationship < 0.30:
        signal = "green"
        summary = "최근 흐름이 비교적 다르게 나타났습니다. 함께 담을 때 한 종목에만 의존하는 정도를 낮추는 데 도움이 될 수 있습니다."
        hint = "두 종목의 움직임이 겹치는 정도가 낮은 편입니다. 업종과 보유 비중도 함께 확인해 보세요."
    elif relationship < 0.70:
        signal = "yellow"
        summary = "최근에는 일부 구간에서 함께 움직였습니다. 분산 효과는 기대할 수 있지만 크기는 제한적일 수 있습니다."
        hint = "조합의 균형은 보통 수준입니다. 다른 업종이나 자산을 더하면 포트폴리오 폭을 넓힐 수 있습니다."
    else:
        signal = "red"
        summary = "최근 가격 흐름이 자주 같은 방향으로 움직였습니다. 두 종목을 함께 담아도 분산 효과가 작을 수 있습니다."
        hint = "한 종목의 영향이 다른 종목에도 이어질 수 있습니다. 업종이 다른 종목이나 다른 자산을 함께 검토해 보세요."

    period_labels = {"3mo": "최근 3개월", "6mo": "최근 6개월", "1y": "최근 1년", "2y": "최근 2년"}
    latest_data_at = pd.Timestamp(daily_moves.index[-1]).isoformat()
    # 두 종목의 가격 단위가 달라도 흐름을 한 차트에서 비교할 수 있도록 출발선을 맞춘다.
    chart_base = aligned_prices / aligned_prices.iloc[0] * 100
    chart_points = [
        {
            "date": pd.Timestamp(index).date().isoformat(),
            "a": round(float(row[ticker_a]), 4),
            "b": round(float(row[ticker_b]), 4),
        }
        for index, row in chart_base.iterrows()
    ]
    return {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "period_label": period_labels[req.period],
        "signal": signal,
        "summary": summary,
        "portfolio_hint": hint,
        "latest_data_at": latest_data_at,
        "chart_points": chart_points,
    }


@app.post("/api/market/snapshot")
def market_snapshot(req: MarketSnapshotRequest) -> dict[str, object]:
    import pandas as pd
    import yfinance as yf

    if not req.tickers:
        raise HTTPException(status_code=400, detail="최소 1개 종목을 선택하세요.")

    fetched_at = pd.Timestamp.utcnow()
    items: list[dict[str, object]] = []

    for ticker in req.tickers:
        label = MARKET_SNAPSHOT_LABELS.get(ticker, ticker)
        try:
            tk = yf.Ticker(ticker)
            fi = tk.fast_info

            # fast_info provides near-realtime last_price (15-min delayed for most exchanges)
            current  = float(fi.last_price)
            previous = float(fi.previous_close) if fi.previous_close else current
            change_pct = ((current / previous) - 1) * 100 if previous else 0.0

            items.append({
                "ticker": ticker,
                "label": label,
                "value": round(current, 4),
                "change_pct": round(change_pct, 2),
                "latest_data_at": fetched_at.isoformat(),
                "status": "ok",
            })
        except Exception as exc:
            # fallback: last daily close
            try:
                df = yf.download(ticker, period="5d", interval="1d",
                                 progress=False, auto_adjust=False, threads=False)
                close = _extract_close_series(df)
                current  = float(close.iloc[-1])
                previous = float(close.iloc[-2]) if len(close) > 1 else current
                change_pct = ((current / previous) - 1) * 100 if previous else 0.0
                items.append({
                    "ticker": ticker, "label": label,
                    "value": round(current, 4),
                    "change_pct": round(change_pct, 2),
                    "latest_data_at": pd.Timestamp(close.index[-1]).isoformat(),
                    "status": "ok",
                })
            except Exception as exc2:
                items.append({"ticker": ticker, "label": label,
                              "status": "error", "error": str(exc2)})

    return {
        "items": items,
        "fetched_at": fetched_at.isoformat(),
    }


@app.get("/api/market/volume-cloud")
def market_volume_cloud(market: str = "us") -> dict[str, object]:
    """Return recent volume and price changes for a compact market bubble cloud."""
    import pandas as pd
    import yfinance as yf

    market_key = market.lower()
    companies = VOLUME_CLOUD_MARKETS.get(market_key)
    if not companies:
        raise HTTPException(status_code=400, detail="market은 us 또는 kr만 선택할 수 있습니다.")

    tickers = [company["ticker"] for company in companies]
    try:
        data = yf.download(tickers, period="2mo", interval="1d", group_by="ticker",
                           progress=False, auto_adjust=False, threads=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"거래량 데이터를 가져오지 못했습니다: {exc}") from exc

    items: list[dict[str, object]] = []
    latest_dates: list[pd.Timestamp] = []
    for company in companies:
        ticker = company["ticker"]
        try:
            frame = data[ticker] if len(tickers) > 1 else data
            close = _extract_close_series(frame)
            volume = frame["Volume"]
            if hasattr(volume, "columns"):
                volume = volume.iloc[:, 0]
            volume = volume.dropna()
            if len(close) < 2 or volume.empty:
                raise ValueError("가격 또는 거래량 이력이 부족합니다.")

            last_close = float(close.iloc[-1])
            previous_close = float(close.iloc[-2])
            last_volume = float(volume.iloc[-1])
            prior_volume = volume.iloc[-21:-1] if len(volume) > 1 else volume
            average_volume = float(prior_volume.mean()) if not prior_volume.empty else last_volume
            items.append({
                "ticker": ticker,
                "name": company["name"],
                "price": round(last_close, 4),
                "change_pct": round((last_close / previous_close - 1) * 100, 2),
                "volume": int(last_volume),
                "average_volume_20d": int(average_volume),
                "volume_ratio": round(last_volume / average_volume, 2) if average_volume else 0.0,
                "latest_data_at": pd.Timestamp(close.index[-1]).isoformat(),
                "status": "ok",
            })
            latest_dates.append(pd.Timestamp(close.index[-1]))
        except Exception as exc:
            items.append({"ticker": ticker, "name": company["name"], "status": "error", "error": str(exc)})

    return {
        "market": market_key,
        "items": items,
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "latest_data_at": max(latest_dates).isoformat() if latest_dates else None,
        "source": "Yahoo Finance",
    }

@app.post("/api/macro/realtime")
def macro_realtime(req: MacroRealtimeRequest) -> dict[str, object]:
    import yfinance as yf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import pandas as pd
    import io, base64
    configure_matplotlib_korean_font(plt)

    DARK   = "#0f172a"
    SURF   = "#1e293b"
    BORDER = "#334155"
    TEXT   = "#e2e8f0"
    MUTED  = "#64748b"
    COLORS = ["#3b82f6","#22c55e","#f59e0b","#ef4444","#a855f7","#06b6d4","#f97316","#84cc16"]

    if not req.tickers:
        raise HTTPException(status_code=400, detail="최소 1개 종목을 선택하세요.")

    # ── 데이터 fetch ──────────────────────────────────────────────────────────
    raw: dict[str, pd.Series] = {}
    fetch_error: str | None = None
    fetched_at = pd.Timestamp.utcnow()

    for t in req.tickers:
        try:
            df = yf.download(t, period=req.period, progress=False, auto_adjust=True)
            if df.empty:
                continue
            close = _extract_close_series(df)
            if len(close) > 0:
                raw[t] = close
        except Exception as e:
            fetch_error = str(e)

    # ── 실시간 데이터 없을 때 GBM 시뮬레이션으로 폴백 ──────────────────────────
    is_simulated = False
    if not raw:
        is_simulated = True
        rng_fb = np.random.default_rng(42)
        n_days = {"1mo": 22, "3mo": 66, "6mo": 132, "1y": 252,
                  "2y": 504, "5y": 1260}.get(req.period, 252)
        BASE = {
            "^TNX": (4.20, 0.0, 0.40), "CL=F": (78.0, 0.03, 0.35),
            "^GSPC": (4800, 0.08, 0.17), "^KS11": (2650, 0.06, 0.18),
            "GC=F": (2000, 0.05, 0.14), "EURUSD=X": (1.08, -0.01, 0.07),
            "BTC-USD": (45000, 0.20, 0.70), "^IRX": (5.25, 0.0, 0.15),
            "^VIX": (18.0, 0.0, 0.80), "DX-Y.NYB": (104.0, 0.01, 0.06),
        }
        dt = 1 / 252
        for t in req.tickers:
            s0, mu, sigma = BASE.get(t, (100, 0.05, 0.20))
            shocks = rng_fb.standard_normal(n_days)
            log_r  = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
            vals   = s0 * np.exp(np.cumsum(log_r))
            idx    = pd.date_range(end=pd.Timestamp.today(), periods=n_days, freq="B")
            raw[t] = pd.Series(vals, index=idx)

    labels_used = [TICKER_LABELS.get(t, t) for t in raw]

    # ── 정규화 수익률 ─────────────────────────────────────────────────────────
    norm: dict[str, pd.Series] = {}
    for t, s in raw.items():
        norm[t] = (s / s.iloc[0] - 1) * 100

    # ── 공통 날짜로 상관관계 DataFrame ────────────────────────────────────────
    combined = pd.DataFrame({TICKER_LABELS.get(t, t): s for t, s in raw.items()})
    combined = combined.dropna()
    corr = combined.pct_change().dropna().corr()

    # ── Figure ────────────────────────────────────────────────────────────────
    n = len(raw)
    fig = plt.figure(figsize=(14, 11), facecolor=DARK)
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.4, wspace=0.35,
                            left=0.07, right=0.97, top=0.93, bottom=0.07)

    # Panel 1: 원시 가격 추세
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.set_facecolor(SURF)
    for i, (t, s) in enumerate(raw.items()):
        ax2_ = ax1.twinx() if i > 0 else ax1
        col  = COLORS[i % len(COLORS)]
        lbl  = TICKER_LABELS.get(t, t)
        if i == 0:
            ax1.plot(s.index, s.values, color=col, lw=1.5, label=lbl)
        # 정규화 차트가 더 유용하므로 여기선 첫 종목만 왼쪽 축에 표시
    ax1.tick_params(colors=TEXT, labelsize=7)
    ax1.set_title("가격 추이 (첫 번째 종목 기준)", color=TEXT, fontsize=9, pad=6)
    ax1.spines[:].set_color(BORDER)
    ax1.set_xlabel("")
    ax1.tick_params(axis='x', rotation=30)
    for label in ax1.get_xticklabels(): label.set_fontsize(6)

    # Panel 2: 정규화 수익률 (누적 %)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.set_facecolor(SURF)
    for i, (t, s) in enumerate(norm.items()):
        ax2.plot(s.index, s.values, color=COLORS[i % len(COLORS)],
                 lw=1.5, label=TICKER_LABELS.get(t, t))
    ax2.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax2.set_title("정규화 누적 수익률 (%)", color=TEXT, fontsize=9, pad=6)
    ax2.tick_params(colors=TEXT, labelsize=7)
    ax2.spines[:].set_color(BORDER)
    ax2.legend(fontsize=6, facecolor=SURF, labelcolor=TEXT,
               loc="upper left", framealpha=0.7)
    ax2.tick_params(axis='x', rotation=30)
    for label in ax2.get_xticklabels(): label.set_fontsize(6)

    # Panel 3: 상관관계 히트맵
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.set_facecolor(SURF)
    if len(corr) > 1:
        cmat = corr.values
        im = ax3.imshow(cmat, cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
        ax3.set_xticks(range(len(corr.columns)))
        ax3.set_yticks(range(len(corr.columns)))
        ax3.set_xticklabels(corr.columns, rotation=45, ha="right",
                            fontsize=7, color=TEXT)
        ax3.set_yticklabels(corr.columns, fontsize=7, color=TEXT)
        for ii in range(len(cmat)):
            for jj in range(len(cmat)):
                v = cmat[ii, jj]
                ax3.text(jj, ii, f"{v:.2f}", ha="center", va="center",
                         fontsize=7, color="white" if abs(v) > 0.5 else TEXT)
        plt.colorbar(im, ax=ax3, fraction=0.04, pad=0.02).ax.tick_params(
            labelcolor=TEXT, labelsize=7)
    else:
        ax3.text(0.5, 0.5, "2개 이상 선택 시\n상관관계 표시", ha="center",
                 va="center", color=MUTED, transform=ax3.transAxes, fontsize=9)
    ax3.set_title("수익률 상관관계 히트맵", color=TEXT, fontsize=9, pad=6)
    ax3.spines[:].set_color(BORDER)

    # Panel 4: 최근 수익률 바 차트 (1M / 3M / 기간 전체)
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.set_facecolor(SURF)
    period_returns = {}
    for t, s in raw.items():
        lbl = TICKER_LABELS.get(t, t)
        period_returns[lbl] = (s.iloc[-1] / s.iloc[0] - 1) * 100
    names  = list(period_returns.keys())
    values = list(period_returns.values())
    bar_colors = [COLORS[i % len(COLORS)] for i in range(len(names))]
    bars = ax4.barh(names, values, color=bar_colors, height=0.55)
    ax4.axvline(0, color=MUTED, lw=0.8)
    for bar, v in zip(bars, values):
        ax4.text(v + (0.5 if v >= 0 else -0.5), bar.get_y() + bar.get_height()/2,
                 f"{v:+.1f}%", va="center", ha="left" if v >= 0 else "right",
                 fontsize=7, color=TEXT)
    ax4.set_title(f"기간 전체 수익률 ({req.period})", color=TEXT, fontsize=9, pad=6)
    ax4.tick_params(colors=TEXT, labelsize=7)
    ax4.spines[:].set_color(BORDER)

    title_suffix = "  [시뮬레이션 — 실시간 연결 불가]" if is_simulated else "  (Yahoo Finance)"
    fig.suptitle(f"거시경제현황 — 실시간 데이터{title_suffix}", color=TEXT,
                 fontsize=12, fontweight="bold", y=0.97)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=DARK)
    plt.close(fig)
    buf.seek(0)
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    # ── 요약 통계 ─────────────────────────────────────────────────────────────
    summary = {}
    for t, s in raw.items():
        lbl = TICKER_LABELS.get(t, t)
        ret  = (s.iloc[-1] / s.iloc[0] - 1) * 100
        vol  = s.pct_change().std() * (252 ** 0.5) * 100
        summary[lbl] = {
            "current": round(float(s.iloc[-1]), 4),
            "return_pct": round(ret, 2),
            "annual_vol_pct": round(vol, 2),
            "latest_data_at": pd.Timestamp(s.index[-1]).isoformat(),
        }

    return {"image": img_b64, "summary": summary, "period": req.period,
            "n_tickers": len(raw),
            "is_simulated": is_simulated,
            "fetched_at": fetched_at.isoformat(),
            "warning": "Yahoo Finance 요청 한도 초과로 시뮬레이션 데이터를 표시합니다. 잠시 후 다시 시도하세요." if is_simulated else None}


# ── KOSPI 섹터/종목 제외 지수 ──────────────────────────────────────────────────

KOSPI_COMPONENTS = [
    {"ticker": "005930.KS", "name": "삼성전자",        "sector": "반도체",    "weight": 0.210},
    {"ticker": "000660.KS", "name": "SK하이닉스",      "sector": "반도체",    "weight": 0.075},
    {"ticker": "373220.KS", "name": "LG에너지솔루션",  "sector": "배터리",    "weight": 0.035},
    {"ticker": "207940.KS", "name": "삼성바이오로직스", "sector": "바이오",    "weight": 0.028},
    {"ticker": "005380.KS", "name": "현대차",          "sector": "자동차",    "weight": 0.025},
    {"ticker": "000270.KS", "name": "기아",            "sector": "자동차",    "weight": 0.022},
    {"ticker": "105560.KS", "name": "KB금융",          "sector": "금융",      "weight": 0.018},
    {"ticker": "035420.KS", "name": "NAVER",           "sector": "IT/플랫폼", "weight": 0.013},
    {"ticker": "055550.KS", "name": "신한지주",        "sector": "금융",      "weight": 0.015},
    {"ticker": "006400.KS", "name": "삼성SDI",         "sector": "배터리",    "weight": 0.012},
    {"ticker": "086790.KS", "name": "하나금융지주",    "sector": "금융",      "weight": 0.012},
    {"ticker": "012330.KS", "name": "현대모비스",      "sector": "자동차",    "weight": 0.009},
    {"ticker": "051910.KS", "name": "LG화학",          "sector": "화학",      "weight": 0.010},
    {"ticker": "032830.KS", "name": "삼성생명",        "sector": "금융",      "weight": 0.008},
    {"ticker": "035720.KS", "name": "카카오",          "sector": "IT/플랫폼", "weight": 0.008},
    {"ticker": "316140.KS", "name": "우리금융지주",    "sector": "금융",      "weight": 0.007},
    {"ticker": "068270.KS", "name": "셀트리온",        "sector": "바이오",    "weight": 0.010},
    {"ticker": "005490.KS", "name": "POSCO홀딩스",     "sector": "철강",      "weight": 0.015},
    {"ticker": "017670.KS", "name": "SK텔레콤",        "sector": "통신",      "weight": 0.010},
    {"ticker": "030200.KS", "name": "KT",              "sector": "통신",      "weight": 0.008},
    {"ticker": "018260.KS", "name": "삼성SDS",         "sector": "IT/플랫폼", "weight": 0.005},
    {"ticker": "096770.KS", "name": "SK이노베이션",    "sector": "에너지",    "weight": 0.006},
    {"ticker": "034730.KS", "name": "SK",              "sector": "에너지",    "weight": 0.006},
    {"ticker": "003550.KS", "name": "LG",              "sector": "지주회사",  "weight": 0.005},
    {"ticker": "090430.KS", "name": "아모레퍼시픽",    "sector": "소비재",    "weight": 0.004},
    {"ticker": "034220.KS", "name": "LG디스플레이",    "sector": "디스플레이","weight": 0.004},
    {"ticker": "011170.KS", "name": "롯데케미칼",      "sector": "화학",      "weight": 0.003},
    {"ticker": "000120.KS", "name": "CJ대한통운",      "sector": "물류",      "weight": 0.003},
]

# 반도체 가치사슬의 소재·부품·장비를 대표하는 국내 상장 종목이다. 전체 소부장
# 시장을 포괄하는 스크리너가 아니라, 같은 기준으로 매일 비교하는 학습용 표본이다.
SOBUJANG_COMPONENTS = [
    {"ticker": "042700.KS", "name": "한미반도체", "sector": "반도체 장비"},
    {"ticker": "240810.KQ", "name": "원익IPS", "sector": "반도체 장비"},
    {"ticker": "036930.KQ", "name": "주성엔지니어링", "sector": "반도체 장비"},
    {"ticker": "084370.KQ", "name": "유진테크", "sector": "반도체 장비"},
    {"ticker": "095610.KQ", "name": "테스", "sector": "반도체 장비"},
    {"ticker": "403870.KQ", "name": "HPSP", "sector": "반도체 장비"},
    {"ticker": "319660.KQ", "name": "피에스케이", "sector": "반도체 장비"},
    {"ticker": "281820.KS", "name": "케이씨텍", "sector": "반도체 장비"},
    {"ticker": "005290.KQ", "name": "동진쎄미켐", "sector": "반도체 소재"},
    {"ticker": "357780.KQ", "name": "솔브레인", "sector": "반도체 소재"},
    {"ticker": "074600.KQ", "name": "원익QnC", "sector": "반도체 소재"},
    {"ticker": "102710.KQ", "name": "이엔에프테크놀로지", "sector": "반도체 소재"},
    {"ticker": "093370.KS", "name": "후성", "sector": "반도체 소재"},
    {"ticker": "011790.KS", "name": "SKC", "sector": "반도체 소재"},
    {"ticker": "095340.KQ", "name": "ISC", "sector": "반도체 부품"},
    {"ticker": "067310.KQ", "name": "하나마이크론", "sector": "반도체 부품"},
    {"ticker": "222800.KQ", "name": "심텍", "sector": "반도체 부품"},
    {"ticker": "353200.KS", "name": "대덕전자", "sector": "반도체 부품"},
    {"ticker": "195870.KS", "name": "해성디에스", "sector": "반도체 부품"},
    {"ticker": "058470.KQ", "name": "리노공업", "sector": "반도체 부품"},
]

# 거래소 전체 업종지수 대신, 매일 같은 기준으로 조회할 수 있는 대표 종목 표본을
# 섹터별로 묶는다. 타일의 면적은 해당 표본의 당일 거래대금 합계다.
KOSDAQ_SECTOR_CLOUD_COMPONENTS = [
    {"ticker": "240810.KQ", "name": "원익IPS", "sector": "반도체 장비"},
    {"ticker": "036930.KQ", "name": "주성엔지니어링", "sector": "반도체 장비"},
    {"ticker": "084370.KQ", "name": "유진테크", "sector": "반도체 장비"},
    {"ticker": "403870.KQ", "name": "HPSP", "sector": "반도체 장비"},
    {"ticker": "039030.KQ", "name": "이오테크닉스", "sector": "반도체 장비"},
    {"ticker": "058470.KQ", "name": "리노공업", "sector": "반도체 부품"},
    {"ticker": "095340.KQ", "name": "ISC", "sector": "반도체 부품"},
    {"ticker": "357780.KQ", "name": "솔브레인", "sector": "반도체 소재"},
    {"ticker": "005290.KQ", "name": "동진쎄미켐", "sector": "반도체 소재"},
    {"ticker": "247540.KQ", "name": "에코프로비엠", "sector": "2차전지"},
    {"ticker": "086520.KQ", "name": "에코프로", "sector": "2차전지"},
    # 엘앤에프는 2024년 유가증권시장으로 이전상장했다. 이전 KOSDAQ 접미사는
    # Yahoo Finance에서 상장폐지 종목으로 취급돼 전체 섹터 조회 경고를 만들었다.
    {"ticker": "066970.KS", "name": "엘앤에프", "sector": "2차전지"},
    {"ticker": "196170.KQ", "name": "알테오젠", "sector": "바이오"},
    {"ticker": "145020.KQ", "name": "휴젤", "sector": "바이오"},
    # 091990은 2023년 합병으로 상장폐지된 셀트리온헬스케어 코드다. 셀트리온제약의
    # 현재 KOSDAQ 코드는 068760이므로 유효한 종목 코드로 교체한다.
    {"ticker": "068760.KQ", "name": "셀트리온제약", "sector": "바이오"},
    {"ticker": "214450.KQ", "name": "파마리서치", "sector": "바이오"},
    {"ticker": "293490.KQ", "name": "카카오게임즈", "sector": "게임·콘텐츠"},
    {"ticker": "112040.KQ", "name": "위메이드", "sector": "게임·콘텐츠"},
    {"ticker": "041510.KQ", "name": "에스엠", "sector": "엔터테인먼트"},
    {"ticker": "035900.KQ", "name": "JYP Ent.", "sector": "엔터테인먼트"},
    {"ticker": "122870.KQ", "name": "와이지엔터테인먼트", "sector": "엔터테인먼트"},
]

SECTOR_CLOUD_MARKETS = {
    "kospi": {"label": "KOSPI", "components": KOSPI_COMPONENTS},
    "kosdaq": {"label": "KOSDAQ", "components": KOSDAQ_SECTOR_CLOUD_COMPONENTS},
}


@app.get("/api/market/sector-cloud")
def market_sector_cloud(market: str = "kospi") -> dict[str, object]:
    """대표 종목 표본의 섹터별 거래대금·평균 등락률을 반환한다."""
    import pandas as pd
    import yfinance as yf

    market_key = market.lower()
    config = SECTOR_CLOUD_MARKETS.get(market_key)
    if not config:
        raise HTTPException(status_code=400, detail="market은 kospi 또는 kosdaq만 선택할 수 있습니다.")

    components = config["components"]
    tickers = [str(component["ticker"]) for component in components]
    try:
        data = yf.download(tickers, period="10d", interval="1d", group_by="ticker",
                           progress=False, auto_adjust=False, threads=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"섹터 시세를 가져오지 못했습니다: {exc}") from exc

    sector_rows: dict[str, list[dict[str, object]]] = {}
    latest_dates: list[pd.Timestamp] = []
    for component in components:
        ticker = str(component["ticker"])
        try:
            frame = data[ticker] if len(tickers) > 1 else data
            close = _extract_close_series(frame)
            volume = frame["Volume"]
            if hasattr(volume, "columns"):
                volume = volume.iloc[:, 0]
            volume = volume.dropna()
            if len(close) < 2 or volume.empty:
                raise ValueError("가격 또는 거래량 이력이 부족합니다.")
            price = float(close.iloc[-1])
            previous = float(close.iloc[-2])
            traded_value = price * float(volume.iloc[-1])
            change_pct = ((price / previous) - 1) * 100 if previous else 0.0
            sector_rows.setdefault(str(component["sector"]), []).append({
                "name": component["name"], "ticker": ticker, "trade_value": traded_value,
                "change_pct": change_pct,
            })
            latest_dates.append(pd.Timestamp(close.index[-1]))
        except Exception:
            continue

    sectors = []
    for sector, rows in sector_rows.items():
        trade_value = sum(float(row["trade_value"]) for row in rows)
        weighted_change = (
            sum(float(row["change_pct"]) * float(row["trade_value"]) for row in rows) / trade_value
            if trade_value else sum(float(row["change_pct"]) for row in rows) / len(rows)
        )
        leader = max(rows, key=lambda row: float(row["trade_value"]))
        sectors.append({
            "sector": sector,
            "stock_count": len(rows),
            "trade_value": round(trade_value),
            "change_pct": round(weighted_change, 2),
            "leader_name": leader["name"],
            "leader_ticker": leader["ticker"],
            "leader_change_pct": round(float(leader["change_pct"]), 2),
        })

    sectors.sort(key=lambda row: row["trade_value"], reverse=True)
    return {
        "market": market_key,
        "market_label": config["label"],
        "sectors": sectors,
        "sample_size": len(components),
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "latest_data_at": max(latest_dates).isoformat() if latest_dates else None,
        "source": "Yahoo Finance",
    }


@app.get("/api/market/chart-patterns")
def market_chart_patterns() -> dict[str, object]:
    """최근 한 달 종가 흐름을 학습용 대표 국내 종목에서 반환한다."""
    import pandas as pd
    import yfinance as yf

    # KOSPI 대표 종목과 KOSDAQ의 주요 성장 섹터를 함께 포함한 학습용 표본이다.
    components = KOSPI_COMPONENTS + KOSDAQ_SECTOR_CLOUD_COMPONENTS
    unique_components = {str(item["ticker"]): item for item in components}
    tickers = list(unique_components)
    try:
        data = yf.download(tickers, period="2mo", interval="1d", group_by="ticker",
                           progress=False, auto_adjust=True, threads=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"최근 차트 데이터를 가져오지 못했습니다: {exc}") from exc

    items: list[dict[str, object]] = []
    latest_dates: list[pd.Timestamp] = []
    for ticker, component in unique_components.items():
        try:
            frame = data[ticker] if len(tickers) > 1 else data
            close = _extract_close_series(frame).dropna().iloc[-22:]
            if len(close) < 15:
                continue
            base = float(close.iloc[0])
            if base <= 0:
                continue
            returns = [round((float(value) / base - 1) * 100, 3) for value in close]
            items.append({
                "ticker": ticker,
                "name": component["name"],
                "sector": component["sector"],
                "returns": returns,
                "one_month_change_pct": round(returns[-1], 2),
                "latest_data_at": pd.Timestamp(close.index[-1]).isoformat(),
            })
            latest_dates.append(pd.Timestamp(close.index[-1]))
        except Exception:
            continue
    if not items:
        raise HTTPException(status_code=503, detail="비교할 최근 차트 데이터가 충분하지 않습니다.")
    return {
        "items": items,
        "latest_data_at": max(latest_dates).isoformat(),
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "source": "Yahoo Finance (일별 수정주가)",
        "note": "KOSPI·KOSDAQ 대표 종목 표본의 최근 약 1개월 종가 흐름입니다.",
    }


OPENING_SESSION_MARKETS = {
    "kospi200": {"ticker": "069500.KS", "label": "KODEX 200", "market": "KOSPI 200", "note": "지수 자체는 거래량이 없으므로 KOSPI 200 추종 ETF를 거래량 참고값으로 사용합니다."},
    "kosdaq150": {"ticker": "229200.KS", "label": "KODEX 코스닥150", "market": "KOSDAQ 150", "note": "지수 자체는 거래량이 없으므로 KOSDAQ 150 추종 ETF를 거래량 참고값으로 사용합니다."},
}


@lru_cache(maxsize=4)
def _load_nps_domestic_equity_holdings(year: int) -> list[dict[str, object]]:
    """국민연금 연말 국내주식 보유현황 엑셀을 화면 표시용으로 정리한다."""
    import pandas as pd

    path = DOCS_DIR / f"국내주식 종목별 투자 현황({year}년 말).xlsx"
    if not path.exists():
        return []
    frame = pd.read_excel(path, skiprows=6, usecols="A:E")
    frame = frame.rename(columns={"종목명": "name", "평가액(억원)": "value_eok", "자산군 내 비중": "weight", "지분율": "ownership"})
    rows: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        name = str(row.get("name", "")).strip()
        if not name or name == "nan":
            continue
        try:
            value = float(row.get("value_eok", 0))
            weight = float(row.get("weight", 0))
            ownership = float(row.get("ownership", 0))
        except (TypeError, ValueError):
            continue
        rows.append({"name": name, "value_eok": round(value, 2), "weight_pct": round(weight * 100, 3), "ownership_pct": round(ownership * 100, 3)})
    return rows


@app.get("/api/nps/domestic-equity-holdings")
def nps_domestic_equity_holdings(year: int = 2025, query: str = "", limit: int = 30) -> dict[str, object]:
    """국민연금이 공개한 연말 국내주식 종목별 보유현황을 반환한다."""
    available_years = [item for item in range(2023, datetime.now().year + 1) if (DOCS_DIR / f"국내주식 종목별 투자 현황({item}년 말).xlsx").exists()]
    if not available_years:
        raise HTTPException(status_code=503, detail="국민연금 국내주식 보유현황 파일을 찾을 수 없습니다.")
    if year not in available_years:
        raise HTTPException(status_code=404, detail=f"{year}년 말 자료는 아직 준비되지 않았습니다.")
    limit = max(1, min(limit, 100))
    items = _load_nps_domestic_equity_holdings(year)
    keyword = query.strip().lower()
    if keyword:
        items = [item for item in items if keyword in str(item["name"]).lower()]
    return {
        "year": year,
        "available_years": available_years,
        "items": items[:limit],
        "total": len(items),
        "source": "국민연금기금운용본부 연간공시 · 국내주식 종목별 투자 현황",
        "as_of": f"{year}년 12월 31일",
        "note": "평가액은 억원이며, 보유 비중·지분율은 연말 기준 공개 자료입니다. 보유 사실만으로 매수·매도 의견을 뜻하지 않습니다.",
    }


@app.get("/api/market/opening-session")
def market_opening_session(market: str = "kospi200") -> dict[str, object]:
    """최근 약 한 달간 한국 장 개장 후 첫 30분의 ETF 가격·거래량을 반환한다."""
    import pandas as pd
    import yfinance as yf

    config = OPENING_SESSION_MARKETS.get(market.lower())
    if not config:
        raise HTTPException(status_code=400, detail="market은 kospi200 또는 kosdaq150만 선택할 수 있습니다.")
    try:
        frame = yf.download(config["ticker"], period="1mo", interval="30m", progress=False,
                            auto_adjust=False, threads=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"개장 직후 데이터를 가져오지 못했습니다: {exc}") from exc
    if frame.empty:
        raise HTTPException(status_code=503, detail="개장 직후 데이터가 충분하지 않습니다.")
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    index = pd.DatetimeIndex(frame.index)
    local_index = index.tz_localize("Asia/Seoul") if index.tz is None else index.tz_convert("Asia/Seoul")
    rows: list[dict[str, object]] = []
    for position, timestamp in enumerate(local_index):
        if timestamp.hour != 9 or timestamp.minute != 0:
            continue
        row = frame.iloc[position]
        try:
            opening = float(row["Open"])
            close = float(row["Close"])
            volume = float(row["Volume"])
            if opening <= 0:
                continue
            rows.append({
                "date": timestamp.date().isoformat(),
                "open": round(opening, 2),
                "close": round(close, 2),
                "change_pct": round((close / opening - 1) * 100, 3),
                "volume": int(volume),
            })
        except (KeyError, TypeError, ValueError):
            continue
    rows = rows[-22:]
    if not rows:
        raise HTTPException(status_code=503, detail="09:00~09:30 구간의 데이터가 아직 제공되지 않았습니다.")

    try:
        daily = yf.download(config["ticker"], period="2mo", interval="1d", progress=False,
                            auto_adjust=False, threads=False)
        if isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.get_level_values(0)
        daily_volume_by_date = {
            ts.date().isoformat(): float(vol)
            for ts, vol in zip(daily.index, daily["Volume"])
            if vol and vol == vol  # NaN 제외
        }
    except Exception:
        daily_volume_by_date = {}

    for row in rows:
        day_volume = daily_volume_by_date.get(row["date"])
        row["day_volume"] = int(day_volume) if day_volume else None
        row["volume_share_pct"] = (
            round(row["volume"] / day_volume * 100, 2) if day_volume else None
        )

    return {
        "market": market.lower(), "label": config["label"], "market_label": config["market"],
        "items": rows, "latest_data_at": f'{rows[-1]["date"]} 09:30:00+09:00',
        "source": "Yahoo Finance 30분 봉", "note": config["note"],
    }


US_KOREA_SECTOR_PAIRS = {
    "semicon": {
        "label": "반도체", "us": {"ticker": "^SOX", "label": "필라델피아 반도체지수(SOX)"},
        "kr": {"ticker": "091160.KS", "label": "TIGER Fn반도체 ETF (KRX 반도체 섹터 참고용)"},
        "note": "TIGER Fn반도체 ETF는 KRX 반도체 관련 지수를 추종하는 국내 상장 ETF로, 한국 반도체 섹터 흐름의 참고값입니다. SOX 구성 종목이 아니며, 환율·개별 종목 비중 차이로 SOX와 반드시 같은 방향으로 움직이지는 않습니다.",
    },
    "battery": {
        "label": "2차전지", "us": {"ticker": "XLK", "label": "미국 기술 섹터 ETF(XLK, 느슨한 참고용)"},
        "kr": {"ticker": "305720.KS", "label": "KODEX 2차전지산업 ETF"},
        "note": "미국에는 2차전지만 담은 대표 섹터 ETF가 따로 없어 기술 섹터 ETF(XLK)를 느슨한 참고선으로 사용했습니다. 구성 종목이 겹치지 않으므로 방향이 다를 수 있습니다.",
    },
    "healthcare": {
        "label": "헬스케어·바이오", "us": {"ticker": "IBB", "label": "미국 바이오 섹터 ETF(IBB)"},
        "kr": {"ticker": "244580.KS", "label": "TIGER 헬스케어 ETF"},
        "note": "IBB는 미국 나스닥 바이오텍 지수를 추종하고, TIGER 헬스케어는 국내 제약·바이오·의료기기 기업을 담습니다. 구성 종목과 파이프라인 특성이 달라 같은 방향으로 움직이지 않을 수 있습니다.",
    },
    "auto": {
        "label": "자동차", "us": {"ticker": "XLY", "label": "미국 소비재경기 섹터 ETF(XLY, 느슨한 참고용)"},
        "kr": {"ticker": "091180.KS", "label": "KODEX 자동차 ETF"},
        "note": "XLY는 자동차 외에도 다양한 소비재경기 기업을 담은 섹터 ETF로, 국내 완성차·부품 중심의 KODEX 자동차와는 구성이 다릅니다. 느슨한 참고선으로만 활용하세요.",
    },
    "finance": {
        "label": "금융", "us": {"ticker": "XLF", "label": "미국 금융 섹터 ETF(XLF)"},
        "kr": {"ticker": "091170.KS", "label": "KODEX 은행 ETF"},
        "note": "XLF는 은행 외에 보험·카드·자산운용사도 포함하는 반면 KODEX 은행은 국내 은행지주 중심입니다. 금리·규제 환경 차이로 흐름이 다를 수 있습니다.",
    },
    "cosmetics": {
        "label": "화장품·소비재", "us": {"ticker": "XLP", "label": "미국 소비재필수 섹터 ETF(XLP, 느슨한 참고용)"},
        "kr": {"ticker": "228790.KS", "label": "TIGER 화장품 ETF"},
        "note": "XLP는 생활필수 소비재 중심이라 국내 화장품·뷰티 기업 위주의 TIGER 화장품과 업종 구성이 다릅니다. 환율·중국 수요 등 별도 요인도 함께 작용합니다.",
    },
}


@app.get("/api/market/sox-vs-korea-semicon")
def market_sox_vs_korea_semicon(sector: str = "semicon", period: str = "6mo") -> dict[str, object]:
    """미국 섹터 지수·ETF와 한국 섹터 ETF의 최근 흐름을 비교한다."""
    import pandas as pd
    import yfinance as yf

    if period not in {"3mo", "6mo", "1y"}:
        raise HTTPException(status_code=400, detail="period는 3mo, 6mo, 1y 중 하나만 선택할 수 있습니다.")
    pair = US_KOREA_SECTOR_PAIRS.get(sector)
    if not pair:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 섹터입니다. 사용 가능: {', '.join(US_KOREA_SECTOR_PAIRS)}")

    series_config = [
        {"key": "us", "ticker": pair["us"]["ticker"], "label": pair["us"]["label"]},
        {"key": "kr", "ticker": pair["kr"]["ticker"], "label": pair["kr"]["label"]},
    ]

    series: dict[str, dict[str, object]] = {}
    for item in series_config:
        try:
            frame = yf.download(item["ticker"], period=period, interval="1d", progress=False,
                                auto_adjust=False, threads=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"{item['label']} 데이터를 가져오지 못했습니다: {exc}") from exc
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            raise HTTPException(status_code=503, detail=f"{item['label']} 데이터가 충분하지 않습니다.")
        base = float(frame["Close"].iloc[0])
        points = [
            {"date": ts.date().isoformat(), "close": round(float(close), 2), "index": round(float(close) / base * 100, 2)}
            for ts, close in zip(frame.index, frame["Close"])
        ]
        period_return = round((points[-1]["close"] / points[0]["close"] - 1) * 100, 2)
        series[item["key"]] = {
            "label": item["label"], "ticker": item["ticker"], "points": points,
            "period_return_pct": period_return, "latest_close": points[-1]["close"],
        }

    return {
        "sector": sector, "sector_label": pair["label"], "period": period, "series": series,
        "sectors": [{"key": key, "label": value["label"]} for key, value in US_KOREA_SECTOR_PAIRS.items()],
        "source": "Yahoo Finance 일봉 종가, 기간 시작일=100 기준 지수화",
        "note": pair["note"],
    }


_VKOSPI_INDEX_NAME = "코스피 200 변동성지수"
_VKOSPI_CACHE: dict[str, float | None] = {}
_VKOSPI_CACHE_LOADED = False


def _krx_auth_key() -> str | None:
    """KRX Open API 인증키. 환경변수 → KRX_KEY_FILE → 저장소 루트 .key 순으로 찾는다."""
    import os
    import re
    from pathlib import Path

    direct = os.getenv("KRX_API_KEY", "").strip()
    if direct:
        return direct
    candidates = [os.getenv("KRX_KEY_FILE", "").strip(), str(Path(__file__).resolve().parents[2] / ".key")]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            text = Path(candidate).read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^\s*KRX_KEY\s*=\s*['\"]?([A-Za-z0-9]+)['\"]?\s*$", text, re.M)
        if match:
            return match.group(1)
    return None


def _vkospi_cache_file():
    import tempfile
    from pathlib import Path

    return Path(tempfile.gettempdir()) / "vkospi_cache.json"


def _fetch_vkospi_close(bas_dd: str, key: str) -> tuple[bool, float | None]:
    """(성공 여부, 종가). 휴장일 등 데이터가 없으면 (True, None), 통신 오류면 (False, None)."""
    import json
    import urllib.request

    url = f"https://data-dbg.krx.co.kr/svc/apis/idx/drvprod_dd_trd?basDd={bas_dd}"
    request = urllib.request.Request(url, headers={"AUTH_KEY": key, "User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rows = json.loads(response.read().decode("utf-8")).get("OutBlock_1", [])
    except Exception:
        return False, None
    for row in rows:
        if row.get("IDX_NM") == _VKOSPI_INDEX_NAME:
            try:
                return True, float(str(row.get("CLSPRC_IDX", "")).replace(",", ""))
            except ValueError:
                return True, None
    return True, None


def _vkospi_closes(dates: list[str], key: str) -> dict[str, float]:
    """KRX Open API는 날짜별 조회만 되므로 거래일마다 병렬 조회하고 결과를 캐시한다."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    global _VKOSPI_CACHE_LOADED
    cache_file = _vkospi_cache_file()
    if not _VKOSPI_CACHE_LOADED:
        try:
            _VKOSPI_CACHE.update(json.loads(cache_file.read_text(encoding="utf-8")))
        except Exception:
            pass
        _VKOSPI_CACHE_LOADED = True

    keys = {date: date.replace("-", "") for date in dates}
    missing = [bas for bas in keys.values() if bas not in _VKOSPI_CACHE]
    if missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for bas, (ok, close) in zip(missing, pool.map(lambda d: _fetch_vkospi_close(d, key), missing)):
                if ok:
                    _VKOSPI_CACHE[bas] = close
        try:
            cache_file.write_text(json.dumps(_VKOSPI_CACHE), encoding="utf-8")
        except OSError:
            pass
    return {date: _VKOSPI_CACHE[bas] for date, bas in keys.items() if _VKOSPI_CACHE.get(bas) is not None}


@app.get("/api/market/vix-vs-kospi")
def market_vix_vs_kospi(period: str = "3mo") -> dict[str, object]:
    """최근 VIX 시계열과 KOSPI 지수 변동을 함께 반환한다."""
    import pandas as pd
    import yfinance as yf

    if period not in {"1mo", "3mo", "6mo", "1y"}:
        raise HTTPException(status_code=400, detail="period는 1mo, 3mo, 6mo, 1y 중 하나만 선택할 수 있습니다.")

    series_config = [
        {"key": "vix", "ticker": "^VIX", "label": "VIX (S&P 500 옵션 내재변동성)"},
        {"key": "kospi", "ticker": "^KS11", "label": "KOSPI 지수"},
    ]

    series: dict[str, dict[str, object]] = {}
    for item in series_config:
        try:
            frame = yf.download(item["ticker"], period=period, interval="1d", progress=False,
                                auto_adjust=False, threads=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"{item['label']} 데이터를 가져오지 못했습니다: {exc}") from exc
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.dropna(subset=["Close"])
        if frame.empty:
            raise HTTPException(status_code=503, detail=f"{item['label']} 데이터가 충분하지 않습니다.")
        points = [
            {"date": ts.date().isoformat(), "close": round(float(close), 2)}
            for ts, close in zip(frame.index, frame["Close"])
        ]
        period_change = round(points[-1]["close"] - points[0]["close"], 2)
        series[item["key"]] = {
            "label": item["label"], "ticker": item["ticker"], "points": points,
            "period_change": period_change, "latest_close": points[-1]["close"],
        }

    vkospi_error: str | None = None
    krx_key = _krx_auth_key()
    if not krx_key:
        vkospi_error = "KRX Open API 키가 설정되지 않아 한국 VKOSPI는 표시하지 못했습니다."
    else:
        try:
            kospi_dates = [point["date"] for point in series["kospi"]["points"]]
            closes = _vkospi_closes(kospi_dates, krx_key)
            vkospi_points = [{"date": date, "close": round(closes[date], 2)} for date in kospi_dates if date in closes]
            if len(vkospi_points) >= 2:
                series["vkospi"] = {
                    "label": "VKOSPI 200 (코스피200 옵션 내재변동성)", "ticker": f"KRX {_VKOSPI_INDEX_NAME}",
                    "points": vkospi_points,
                    "period_change": round(vkospi_points[-1]["close"] - vkospi_points[0]["close"], 2),
                    "latest_close": vkospi_points[-1]["close"],
                }
            else:
                vkospi_error = "한국 VKOSPI 데이터를 충분히 받지 못했습니다."
        except Exception as exc:  # KRX 장애가 있어도 VIX·KOSPI는 계속 보여 준다.
            vkospi_error = f"한국 VKOSPI 데이터를 가져오지 못했습니다: {exc}"

    return {
        "period": period, "series": series, "vkospi_error": vkospi_error,
        "source": "VIX·KOSPI: Yahoo Finance 일봉 종가 · VKOSPI: 한국거래소 정보데이터시스템 Open API",
        "note": "VIX는 미국 S&P 500 옵션, VKOSPI는 한국 코스피200 옵션 시장에서 계산한 향후 30일 기대 변동성이고, KOSPI는 한국 대형주 중심 가격지수여서 기준 시장과 계산 방식이 서로 다릅니다. 변동성지수가 오른 날에 KOSPI가 반드시 내리는 것은 아니며, 세 지표를 같은 화면에서 함께 관찰하는 참고용 자료입니다.",
    }


@app.get("/api/market/circuit-breaker-history")
def market_circuit_breaker_history(period: str = "6mo") -> dict[str, object]:
    """최근 KOSPI·KOSDAQ 일봉에서 서킷브레이커 발동 요건(전일 대비 장중 8·15·20% 하락)과,
    KOSPI200·KOSDAQ150 프록시 종목의 일봉에서 사이드카 발동 요건(±5%·±6% 이상 등락)에
    해당하는 날짜를 근사 추정해 반환한다. 둘 다 거래소의 공식 발동 기록이 아니라 일봉
    시가·고가·저가·종가 기준의 근사치다. 실제 사이드카는 선물의 장중 실시간 가격과 1분
    지속 여부가 필요하므로, 여기서는 선물 대신 관련 현물/ETF 프록시로 추정한다."""
    import pandas as pd
    import yfinance as yf

    if period not in {"3mo", "6mo", "1y"}:
        raise HTTPException(status_code=400, detail="period는 3mo, 6mo, 1y 중 하나만 선택할 수 있습니다.")

    def _download(ticker: str, label: str):
        try:
            frame = yf.download(ticker, period=period, interval="1d", progress=False,
                                auto_adjust=False, threads=False)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"{label} 데이터를 가져오지 못했습니다: {exc}") from exc
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        frame = frame.dropna(subset=["Close", "Low", "High"])
        if frame.empty:
            raise HTTPException(status_code=503, detail=f"{label} 데이터가 충분하지 않습니다.")
        return frame

    def _news_search_url(label: str, date_str: str) -> str:
        query = urllib.parse.quote(f"{label} 급락 {date_str}")
        return f"https://news.google.com/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

    cb_config = [
        {"key": "kospi", "ticker": "^KS11", "label": "KOSPI"},
        {"key": "kosdaq", "ticker": "^KQ11", "label": "KOSDAQ"},
    ]
    series: dict[str, dict[str, object]] = {}
    for item in cb_config:
        frame = _download(item["ticker"], item["label"])
        points: list[dict[str, object]] = []
        prev_close: float | None = None
        for ts, row in frame.iterrows():
            close = float(row["Close"]); low = float(row["Low"])
            low_decline_pct = round((low / prev_close - 1) * 100, 2) if prev_close else None
            cb_level = None
            if low_decline_pct is not None:
                if low_decline_pct <= -20:
                    cb_level = 3
                elif low_decline_pct <= -15:
                    cb_level = 2
                elif low_decline_pct <= -8:
                    cb_level = 1
            date_str = ts.date().isoformat()
            points.append({
                "date": date_str, "close": round(close, 2),
                "low_decline_pct": low_decline_pct, "cb_level": cb_level,
                "news_search_url": _news_search_url(item["label"], date_str) if cb_level else None,
            })
            prev_close = close
        flagged = [p for p in points if p["cb_level"]]
        series[item["key"]] = {"label": item["label"], "ticker": item["ticker"], "points": points, "flagged": flagged}

    sidecar_config = [
        {"key": "kospi200", "ticker": "^KS200", "label": "KOSPI200(프록시: 현물지수)", "threshold": 5.0},
        {"key": "kosdaq150", "ticker": "229200.KS", "label": "KOSDAQ150(프록시: KODEX 코스닥150 ETF)", "threshold": 6.0},
    ]
    sidecar: dict[str, dict[str, object]] = {}
    for item in sidecar_config:
        frame = _download(item["ticker"], item["label"])
        points = []
        prev_close = None
        for ts, row in frame.iterrows():
            close = float(row["Close"]); high = float(row["High"]); low = float(row["Low"])
            up_pct = round((high / prev_close - 1) * 100, 2) if prev_close else None
            down_pct = round((low / prev_close - 1) * 100, 2) if prev_close else None
            triggered = None
            if up_pct is not None and up_pct >= item["threshold"]:
                triggered = "up"
            elif down_pct is not None and down_pct <= -item["threshold"]:
                triggered = "down"
            date_str = ts.date().isoformat()
            points.append({
                "date": date_str, "close": round(close, 2), "up_pct": up_pct, "down_pct": down_pct,
                "triggered": triggered,
                "news_search_url": _news_search_url(item["label"].split("(")[0], date_str) if triggered else None,
            })
            prev_close = close
        flagged = [p for p in points if p["triggered"]]
        sidecar[item["key"]] = {"label": item["label"], "ticker": item["ticker"], "threshold_pct": item["threshold"], "points": points, "flagged": flagged}

    return {
        "period": period, "series": series, "sidecar": sidecar,
        "source": "Yahoo Finance 일봉 시가·고가·저가·종가",
        "common_causes": [
            "국내외 중앙은행의 금리·통화정책 발표",
            "전쟁·분쟁 등 지정학적 긴장 고조",
            "미국 등 해외 증시의 동반 급락",
            "반도체·대형주 등 지수 비중이 큰 종목의 실적 쇼크",
            "급격한 환율 변동이나 외국인 대량 매도",
        ],
        "note": (
            "이 화면의 서킷브레이커 표시는 공식 발동 기록이 아니라, 일봉 저가가 전일 종가 대비 "
            "8%·15%·20% 이상 하락했는지로 계산한 근사 추정치입니다. 사이드카 표시도 KOSPI200·KOSDAQ150 "
            "선물이 아니라 관련 현물지수·ETF의 일중 고가·저가가 ±5%·±6% 이상 움직였는지로 계산한 "
            "근사 추정치이며, 실제 선물 가격·1분 지속 여부와 다를 수 있습니다. 위 '흔한 원인'은 이런 "
            "큰 변동일에 자주 함께 언급되는 요인을 일반적으로 정리한 것일 뿐, 특정 날짜의 확정된 원인을 "
            "자동으로 판별한 것이 아닙니다. 각 날짜의 실제 원인은 표의 뉴스 검색 링크나 한국거래소 공지, "
            "DART 공시로 직접 확인하세요."
        ),
    }


@app.get("/api/market/mdd-history")
def market_mdd_history(ticker: str = "^KS11", years: int = 10) -> dict[str, object]:
    """최근 N년간 지수(기본 KOSPI)의 일별 낙폭(드로다운)과 최대낙폭(MDD)을 계산한다."""
    import pandas as pd
    import yfinance as yf

    if ticker not in {"^KS11", "^KQ11"}:
        raise HTTPException(status_code=400, detail="ticker는 ^KS11(KOSPI) 또는 ^KQ11(KOSDAQ)만 선택할 수 있습니다.")
    years = max(1, min(years, 20))
    label = "KOSPI" if ticker == "^KS11" else "KOSDAQ"

    try:
        frame = yf.download(ticker, period=f"{years}y", interval="1d", progress=False,
                            auto_adjust=False, threads=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{label} 데이터를 가져오지 못했습니다: {exc}") from exc
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        raise HTTPException(status_code=503, detail=f"{label} 데이터가 충분하지 않습니다.")

    points: list[dict[str, object]] = []
    running_peak = float(frame["Close"].iloc[0])
    worst = {"date": None, "drawdown_pct": 0.0}
    for ts, close in zip(frame.index, frame["Close"]):
        close = float(close)
        running_peak = max(running_peak, close)
        drawdown_pct = round((close / running_peak - 1) * 100, 2)
        date_str = ts.date().isoformat()
        points.append({"date": date_str, "close": round(close, 2), "drawdown_pct": drawdown_pct})
        if drawdown_pct < worst["drawdown_pct"]:
            worst = {"date": date_str, "drawdown_pct": drawdown_pct}

    return {
        "ticker": ticker, "label": label, "years": years, "points": points,
        "mdd": worst,
        "source": "Yahoo Finance 일봉 종가",
        "note": (
            f"최대낙폭(MDD)은 관찰 기간(최근 {years}년) 안에서 이전 고점 대비 가장 크게 떨어졌던 지점을 계산한 값입니다. "
            "관찰 기간을 더 길거나 짧게 잡으면 MDD 값도 달라질 수 있으며, 과거 최대낙폭이 미래의 최대 손실을 보장하지 않습니다."
        ),
    }


PATTERN_LABELS = {
    "cup_with_handle": {"label": "컵 위드 핸들", "direction": "매수(상승 지속) 후보", "en": "Cup with Handle"},
    "head_shoulders": {"label": "헤드 앤 숄더", "direction": "매도(하락 전환) 후보", "en": "Head and Shoulders"},
    "inverse_head_shoulders": {"label": "역헤드 앤 숄더", "direction": "매수(상승 전환) 후보", "en": "Inverse Head and Shoulders"},
    "double_top": {"label": "더블 탑", "direction": "매도(하락 전환) 후보", "en": "Double Top"},
    "double_bottom": {"label": "더블 바텀", "direction": "매수(상승 전환) 후보", "en": "Double Bottom"},
    "triangle": {"label": "삼각수렴", "direction": "돌파 방향에 따른 매수·매도 후보", "en": "Triangle"},
}


@app.get("/api/market/pattern-scan")
def market_pattern_scan(pattern: str, years: int = 5) -> dict[str, object]:
    """국내 대표 종목 표본에서 요청한 차트 패턴과 기하학적으로 비슷한 구간을 찾아
    실제 가격 데이터와 함께 반환한다. 규칙 기반 근사 탐지이며, 확정된 매매 신호가
    아니다."""
    import pandas as pd
    import yfinance as yf

    if pattern not in pattern_detection.DETECTORS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 패턴입니다. 사용 가능: {', '.join(pattern_detection.DETECTORS)}")
    years = max(1, min(years, 5))
    detector = pattern_detection.DETECTORS[pattern]

    tickers = [str(item["ticker"]) for item in KOSPI_COMPONENTS]
    try:
        data = yf.download(tickers, period=f"{years}y", interval="1d", group_by="ticker",
                           progress=False, auto_adjust=True, threads=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"종목 데이터를 가져오지 못했습니다: {exc}") from exc

    name_by_ticker = {str(item["ticker"]): item["name"] for item in KOSPI_COMPONENTS}
    best = None
    best_frame = None
    for ticker in tickers:
        try:
            frame = data[ticker] if len(tickers) > 1 else data
            close = _extract_close_series(frame).dropna()
            if len(close) < 60:
                continue
            values = close.to_numpy(dtype=float)
            matches = detector(values)
            confirmed = [m for m in matches if m.breakout_index is not None]
            candidates = confirmed or matches
            if not candidates:
                continue
            top = max(candidates, key=lambda m: m.score)
            if best is None or top.score > best[0].score:
                best = (top, ticker)
                best_frame = close
        except Exception:
            continue

    label_info = PATTERN_LABELS[pattern]
    if best is None:
        return {
            "pattern": pattern, "label": label_info["label"], "found": False,
            "note": f"최근 {years}년, 표본 {len(tickers)}개 종목에서 '{label_info['label']}'과 기하학적으로 비슷한 구간을 찾지 못했습니다. 기간을 늘리거나 다시 시도해 보세요.",
        }

    match, ticker = best
    pad_before = 15
    pad_after = 10
    window_start = max(0, match.start_index - pad_before)
    window_end = min(len(best_frame), (match.breakout_index or match.end_index) + pad_after + 1)
    window = best_frame.iloc[window_start:window_end]
    dates = [ts.date().isoformat() for ts in window.index]
    closes = [round(float(v), 2) for v in window.to_numpy()]

    def _to_window(idx: int) -> int:
        return idx - window_start

    key_points = [{"index": _to_window(kp.index), "date": dates[_to_window(kp.index)] if 0 <= _to_window(kp.index) < len(dates) else None,
                   "price": closes[_to_window(kp.index)] if 0 <= _to_window(kp.index) < len(dates) else None, "label": kp.label}
                  for kp in match.key_points]
    breakout = None
    if match.breakout_index is not None:
        bi = _to_window(match.breakout_index)
        if 0 <= bi < len(dates):
            breakout = {"index": bi, "date": dates[bi], "price": closes[bi]}
    neckline = None
    if match.neckline and match.neckline_span:
        s, e = _to_window(match.neckline_span[0]), _to_window(match.neckline_span[1])
        if 0 <= s < len(dates) and 0 <= e < len(dates):
            neckline = {"start": {"index": s, "date": dates[s], "price": round(match.neckline[0], 2)},
                        "end": {"index": e, "date": dates[e], "price": round(match.neckline[1], 2)}}

    return {
        "pattern": pattern, "label": label_info["label"], "label_en": label_info["en"],
        "direction": label_info["direction"], "found": True,
        "ticker": ticker, "name": name_by_ticker.get(ticker, ticker),
        "dates": dates, "closes": closes,
        "key_points": key_points, "breakout": breakout, "neckline": neckline,
        "score": round(match.score, 3), "summary": match.summary,
        "source": "Yahoo Finance 일봉 수정종가",
        "note": (
            f"이 구간은 국내 대표 종목 {len(tickers)}개 가운데 '{label_info['label']}' 모양과 기하학적으로 가장 비슷한 실제 사례를 "
            "규칙 기반으로 찾은 것입니다. 사람이 눈으로 확인한 정답이 아니라 느슨한 허용오차로 근사 탐지한 결과이므로, "
            "실제 차트를 직접 다시 확인하고 참고용으로만 활용하세요. 과거에 이런 모양이 있었다는 사실이 미래의 방향이나 수익을 보장하지 않습니다."
        ),
    }


@app.get("/api/market/price-volume-example")
def market_price_volume_example(ticker: str = "005930.KS", months: int = 6) -> dict[str, object]:
    """가격과 거래량을 함께 읽는 예시로 쓸 실제 일봉·거래량 데이터를 반환한다."""
    import pandas as pd
    import yfinance as yf

    months = max(1, min(months, 24))
    name_by_ticker = {str(item["ticker"]): item["name"] for item in KOSPI_COMPONENTS}
    if ticker not in name_by_ticker:
        raise HTTPException(status_code=400, detail="지원하지 않는 종목 코드입니다.")

    try:
        frame = yf.download(ticker, period=f"{months}mo", interval="1d", progress=False,
                            auto_adjust=True, threads=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{ticker} 데이터를 가져오지 못했습니다: {exc}") from exc
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.dropna(subset=["Close", "Volume"])
    if frame.empty:
        raise HTTPException(status_code=503, detail=f"{ticker} 데이터가 충분하지 않습니다.")

    points: list[dict[str, object]] = []
    prev_close: float | None = None
    for ts, row in frame.iterrows():
        close = float(row["Close"]); volume = float(row["Volume"])
        change_pct = round((close / prev_close - 1) * 100, 2) if prev_close else 0.0
        points.append({
            "date": ts.date().isoformat(), "open": round(float(row["Open"]), 2), "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2), "close": round(close, 2), "volume": int(volume), "change_pct": change_pct,
        })
        prev_close = close

    volumes = [p["volume"] for p in points]
    avg_volume = sum(volumes) / len(volumes)
    spike_index = max(range(len(points)), key=lambda i: points[i]["volume"])
    spike = {**points[spike_index], "index": spike_index, "volume_vs_avg_pct": round((points[spike_index]["volume"] / avg_volume - 1) * 100, 1)}

    return {
        "ticker": ticker, "name": name_by_ticker[ticker], "months": months,
        "points": points, "average_volume": round(avg_volume), "spike": spike,
        "source": "Yahoo Finance 일봉 시가·고가·저가·종가·거래량",
        "note": "가격이 크게 움직인 날 거래량이 평소보다 늘었는지 함께 보는 예시입니다. 거래량이 많다는 사실만으로 다음 방향을 알 수는 없으며, 공시·실적·시장 전체 흐름을 함께 확인해야 합니다.",
    }


RECENT_IPO_STOCKS = {
    "064400.KS": {"name": "LG CNS", "market": "KOSPI", "country": "국내"},
    "VG": {"name": "Venture Global", "market": "NYSE", "country": "해외"},
    "CRWV": {"name": "CoreWeave", "market": "Nasdaq", "country": "해외"},
    "CRCL": {"name": "Circle Internet Group", "market": "NYSE", "country": "해외"},
    "CHYM": {"name": "Chime Financial", "market": "Nasdaq", "country": "해외"},
    "FIG": {"name": "Figma", "market": "NYSE", "country": "해외"},
}


@app.get("/api/market/recent-ipo-list")
def market_recent_ipo_list() -> dict[str, object]:
    return {
        "items": [{"ticker": ticker, **meta} for ticker, meta in RECENT_IPO_STOCKS.items()],
        "note": "정확히 최근 6개월 이내로 확인되지 않아, 실제 상장일이 데이터로 검증된 종목 위주로 구성했습니다. 상장일은 야후 파이낸스에 거래 데이터가 시작된 날짜를 기준으로 합니다.",
    }


@app.get("/api/market/ipo-since-listing")
def market_ipo_since_listing(ticker: str = "064400.KS") -> dict[str, object]:
    """상장 이후 오늘까지의 종가 흐름을 반환한다."""
    import pandas as pd
    import yfinance as yf

    meta = RECENT_IPO_STOCKS.get(ticker)
    if not meta:
        raise HTTPException(status_code=400, detail="지원하지 않는 종목입니다.")

    try:
        frame = yf.download(ticker, period="max", interval="1d", progress=False, auto_adjust=True, threads=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{meta['name']} 데이터를 가져오지 못했습니다: {exc}") from exc
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        raise HTTPException(status_code=503, detail=f"{meta['name']} 데이터가 충분하지 않습니다.")

    listing_date = frame.index[0].date().isoformat()
    points = [{"date": ts.date().isoformat(), "close": round(float(close), 2)} for ts, close in zip(frame.index, frame["Close"])]
    ipo_price = points[0]["close"]
    latest = points[-1]["close"]
    performance_pct = round((latest / ipo_price - 1) * 100, 2)
    high = max(points, key=lambda p: p["close"])
    low = min(points, key=lambda p: p["close"])

    return {
        "ticker": ticker, "name": meta["name"], "market": meta["market"], "country": meta["country"],
        "listing_date": listing_date, "points": points,
        "ipo_price": ipo_price, "latest_price": latest, "performance_pct": performance_pct,
        "high": high, "low": low,
        "source": "Yahoo Finance 일봉 종가 (상장 첫 거래일부터)",
        "note": f"{meta['name']}의 상장일은 야후 파이낸스에서 거래 데이터가 시작된 {listing_date}을 기준으로 확인한 값입니다. 상장 첫날 가격 대비 등락률이며, 공모가와 실제 상장 첫날 시초가는 다를 수 있습니다.",
    }


PENNY_STOCK_RALLY_EXAMPLES = {
    "005360.KS": {"name": "모나미", "note": "문구류 제조·판매 회사로, 시장에서 정치 테마·자사주 소각 기대 등 다양한 재료가 언급되며 주가가 크게 흔들린 사례로 자주 인용됩니다."},
    "014710.KS": {"name": "사조씨푸드", "note": "참치캔 등 수산가공식품을 만드는 회사로, 원어(원재료) 가격이나 그룹 계열사 이슈가 언급될 때 주가 변동성이 커지는 사례로 언급됩니다."},
    "008040.KS": {"name": "사조동아원", "note": "제분·사료 등을 다루는 회사로, 곡물 가격이나 그룹 관련 소식에 따라 저가주 특유의 큰 변동폭을 보인 사례로 언급됩니다."},
}


@app.get("/api/market/penny-stock-rally")
def market_penny_stock_rally(ticker: str = "005360.KS", months: int = 6) -> dict[str, object]:
    """동전주였다가 시장에서 크게 흔들린 사례 종목의 일봉 데이터를 반환한다."""
    import pandas as pd
    import yfinance as yf

    meta = PENNY_STOCK_RALLY_EXAMPLES.get(ticker)
    if not meta:
        raise HTTPException(status_code=400, detail="지원하지 않는 종목입니다.")
    months = max(1, min(months, 24))

    try:
        frame = yf.download(ticker, period=f"{months}mo", interval="1d", progress=False, auto_adjust=True, threads=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{meta['name']} 데이터를 가져오지 못했습니다: {exc}") from exc
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.dropna(subset=["Close", "Volume"])
    if frame.empty:
        raise HTTPException(status_code=503, detail=f"{meta['name']} 데이터가 충분하지 않습니다.")

    points = [
        {"date": ts.date().isoformat(), "close": round(float(row["Close"]), 2), "volume": int(row["Volume"])}
        for ts, row in frame.iterrows()
    ]
    closes = [p["close"] for p in points]
    low_point = min(points, key=lambda p: p["close"])
    high_point = max(points, key=lambda p: p["close"])
    rally_from_low_pct = round((high_point["close"] / low_point["close"] - 1) * 100, 1)
    period_change_pct = round((closes[-1] / closes[0] - 1) * 100, 1)

    return {
        "ticker": ticker, "name": meta["name"], "months": months, "points": points,
        "low": low_point, "high": high_point, "rally_from_low_pct": rally_from_low_pct,
        "period_change_pct": period_change_pct, "latest_price": closes[-1],
        "source": "Yahoo Finance 일봉 종가·거래량",
        "note": (
            f"{meta['note']} 저점 {low_point['close']}원에서 고점 {high_point['close']}원까지 "
            f"{rally_from_low_pct}% 올랐던 구간이 있었지만, 이후 다시 하락했을 수도 있습니다. "
            "이 화면은 낮은 가격의 종목이 실제로 크게 흔들렸던 사례를 확인하는 학습용 자료이며, "
            "동전주가 오른 이유를 시장에서 회자되는 재료로 설명한 것일 뿐 공식적으로 확인된 인과관계가 아닙니다. "
            "실제 급등락 이유는 공시·재무제표에서 직접 확인하세요."
        ),
    }


DIVIDEND_HISTORY_STOCKS = {
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "005380.KS": "현대차",
    "105560.KS": "KB금융", "005490.KS": "POSCO홀딩스",
}


@app.get("/api/market/dividend-history")
def market_dividend_history(ticker: str = "005930.KS") -> dict[str, object]:
    """실제 배당락일·배당금 이력과, 최근 패턴을 바탕으로 한 다음 배당(추정)을 반환한다."""
    import datetime as dt

    import pandas as pd
    import yfinance as yf

    name = DIVIDEND_HISTORY_STOCKS.get(ticker)
    if not name:
        raise HTTPException(status_code=400, detail="지원하지 않는 종목입니다.")

    try:
        dividends = yf.Ticker(ticker).dividends
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{name} 배당 데이터를 가져오지 못했습니다: {exc}") from exc
    if dividends.empty:
        raise HTTPException(status_code=503, detail=f"{name} 배당 데이터가 충분하지 않습니다.")

    today = pd.Timestamp.now(tz=dividends.index.tz).normalize()
    past = dividends[dividends.index <= today].tail(8)
    if past.empty:
        raise HTTPException(status_code=503, detail=f"{name}의 과거 배당 이력을 찾을 수 없습니다.")

    def _next_business_day(d: dt.date) -> dt.date:
        nxt = d + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        return nxt

    history = [
        {
            "ex_date": ts.date().isoformat(),
            "estimated_record_date": _next_business_day(ts.date()).isoformat(),
            "amount": round(float(amount), 1),
        }
        for ts, amount in past.items()
    ]

    last_ts = past.index[-1]
    last_amount = float(past.iloc[-1])
    recent_amounts = [float(v) for v in past.tail(4)]
    projected_amount = round(sum(recent_amounts) / len(recent_amounts), 1)
    # 최근 배당 간격(분기·반기 등 실제 지급 주기)의 평균으로 다음 배당일을 추정한다.
    recent_dates = list(past.tail(5).index)
    gaps_days = [(recent_dates[i] - recent_dates[i - 1]).days for i in range(1, len(recent_dates))]
    avg_gap_days = round(sum(gaps_days) / len(gaps_days)) if gaps_days else 365
    projected_ts = last_ts
    while projected_ts.date() <= today.date():
        projected_ts = projected_ts + pd.Timedelta(days=avg_gap_days)
    projected_ex_date = projected_ts.date()

    next_dividend = {
        "ex_date": projected_ex_date.isoformat(),
        "estimated_record_date": _next_business_day(projected_ex_date).isoformat(),
        "amount": projected_amount,
        "is_estimate": True,
    }

    return {
        "ticker": ticker, "name": name,
        "as_of": today.date().isoformat(),
        "history": history,
        "latest": {"ex_date": last_ts.date().isoformat(), "amount": round(last_amount, 1)},
        "next_dividend": next_dividend,
        "source": "Yahoo Finance 배당(ex-dividend) 이력",
        "note": (
            "배당락일은 야후 파이낸스에 기록된 실제 이력이며, 배당기준일은 배당락일 다음 거래일로 근사 계산한 값입니다. "
            "'다음 배당(추정)'은 최근 배당 간격과 최근 4회 평균 금액을 바탕으로 추정한 값일 뿐, 회사의 공식 발표가 아닙니다. "
            "실제 배당 여부·금액·일정은 이사회 결의와 주주총회 결과에 따라 달라지므로 DART·KIND 공시로 반드시 확인하세요."
        ),
    }


def _market_top_ranked_components(
    components: list[dict[str, object]], limit: int, universe: str, simulation_seed: int,
) -> dict[str, object]:
    """대표 종목 표본의 당일 등락률 순위를 반환한다."""
    import pandas as pd
    import yfinance as yf

    limit = max(1, min(limit, len(components)))
    fetched_at = pd.Timestamp.utcnow()
    valid: list[dict[str, object]] = []

    for stock in components:
        ticker = str(stock["ticker"])
        try:
            fi = yf.Ticker(ticker).fast_info
            current = float(fi.last_price)
            previous = float(fi.previous_close) if fi.previous_close else current
            change_pct = ((current / previous) - 1) * 100 if previous else 0.0
            valid.append({
                "ticker": ticker, "name": stock["name"], "sector": stock["sector"],
                "price": round(current, 2), "change_pct": round(change_pct, 2),
            })
        except Exception:
            continue

    is_simulated = False
    if len(valid) < 5:
        is_simulated = True
        rng_state = simulation_seed

        def _rand():
            nonlocal rng_state
            rng_state = (rng_state * 1664525 + 1013904223) % 2**32
            return rng_state / 2**32

        valid = [{
            "ticker": stock["ticker"], "name": stock["name"], "sector": stock["sector"],
            "price": round(20000 + _rand() * 480000, 0),
            "change_pct": round((_rand() - 0.35) * 12, 2),
        } for stock in components]

    ranked = sorted(valid, key=lambda item: item["change_pct"], reverse=True)[:limit]
    for i, item in enumerate(ranked, start=1):
        item["rank"] = i

    return {
        "items": ranked,
        "universe": universe,
        "universe_size": len(components),
        "fetched_at": fetched_at.isoformat(),
        "is_simulated": is_simulated,
    }


@app.get("/api/market/top-gainers")
def market_top_gainers(limit: int = 20) -> dict[str, object]:
    """KOSPI 대표 종목 중 금일 등락률 상위 종목을 반환한다."""
    return _market_top_ranked_components(KOSPI_COMPONENTS, limit, "KOSPI 대표 종목", 777)


@app.get("/api/market/top-sobujang")
def market_top_sobujang(limit: int = 20) -> dict[str, object]:
    """반도체 소부장 대표 종목 중 금일 등락률 상위 종목을 반환한다."""
    return _market_top_ranked_components(SOBUJANG_COMPONENTS, limit, "국내 반도체 소부장 대표 종목", 1777)

KOSPI_SECTORS = sorted({c["sector"] for c in KOSPI_COMPONENTS})


class MacroKospiExRequest(BaseModel):
    exclude_tickers: list[str] = []
    exclude_sectors: list[str] = []
    period: str = "1y"


@app.post("/api/macro/kospi-ex")
def macro_kospi_ex(req: MacroKospiExRequest) -> dict[str, object]:
    import yfinance as yf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import pandas as pd
    import io, base64
    from datetime import datetime, timezone
    configure_matplotlib_korean_font(plt)

    # 제외 대상 결정
    excl_ticker_codes = {t.replace(".KS", "").replace(".KQ", "") for t in req.exclude_tickers}
    excl_sectors      = set(req.exclude_sectors)

    excluded: list[dict] = []
    included: list[dict] = []
    for comp in KOSPI_COMPONENTS:
        code = comp["ticker"].replace(".KS", "").replace(".KQ", "")
        if code in excl_ticker_codes or comp["sector"] in excl_sectors:
            excluded.append(comp)
        else:
            included.append(comp)

    total_excl_weight = sum(c["weight"] for c in excluded)
    if total_excl_weight >= 0.95:
        raise HTTPException(status_code=400, detail="제외 비중이 너무 커서 지수를 계산할 수 없습니다.")

    # 다운로드
    tickers_needed = ["^KS11"] + [c["ticker"] for c in excluded]
    raw: dict[str, pd.Series] = {}
    is_simulated = False
    fetched_at = datetime.now(timezone.utc)

    for t in tickers_needed:
        try:
            df = yf.download(t, period=req.period, progress=False, auto_adjust=True)
            if df.empty:
                raise ValueError("empty")
            s = df["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna()
            if len(s) > 5:
                raw[t] = s
        except Exception:
            is_simulated = True

    if "^KS11" not in raw or is_simulated:
        # 시뮬레이션 대체 데이터
        import math
        rng = 12345
        def _rnd():
            nonlocal rng
            rng = (rng * 1664525 + 1013904223) % 2**32
            return rng / 2**32
        def _randn():
            u, v = max(_rnd(), 1e-10), _rnd()
            return math.sqrt(-2*math.log(u)) * math.cos(2*math.pi*v)
        period_days = {"1mo":30,"3mo":90,"6mo":180,"1y":365,"2y":730,"3y":1095}
        days = period_days.get(req.period, 365)
        n_bars = int(days * 0.72)
        base_date = pd.Timestamp("today") - pd.Timedelta(days=days)
        dates = [base_date + pd.Timedelta(days=i+1) for i in range(n_bars)]
        price = 2650.0
        prices = []
        for _ in range(n_bars):
            price = max(price * (1 + _randn() * 0.012), 100)
            prices.append(price)
        raw["^KS11"] = pd.Series(prices, index=dates)
        # 시뮬레이션된 종목 데이터
        for comp in excluded:
            price2 = 50000.0
            p2 = []
            for _ in range(n_bars):
                price2 = max(price2 * (1 + _randn() * 0.015), 100)
                p2.append(price2)
            raw[comp["ticker"]] = pd.Series(p2, index=dates)
        is_simulated = True

    kospi_s = raw["^KS11"]
    # 공통 날짜 인덱스 정렬
    common_idx = kospi_s.index
    for comp in excluded:
        if comp["ticker"] in raw:
            common_idx = common_idx.intersection(raw[comp["ticker"]].index)
    kospi_s = kospi_s.loc[common_idx]

    # 일별 수익률
    kospi_ret = kospi_s.pct_change().fillna(0)

    # 제외 종목 기여도 계산
    contrib = pd.Series(0.0, index=common_idx)
    for comp in excluded:
        if comp["ticker"] in raw:
            s = raw[comp["ticker"]].reindex(common_idx).ffill()
            ret = s.pct_change().fillna(0)
            contrib += comp["weight"] * ret

    # 조정 수익률: r_adj = (r_KOSPI - contrib_excl) / (1 - total_excl_weight)
    adj_ret = (kospi_ret - contrib) / (1 - total_excl_weight)

    # 누적 가격 지수 (100 기준)
    kospi_norm  = (1 + kospi_ret).cumprod() * 100
    adj_norm    = (1 + adj_ret).cumprod() * 100
    kospi_norm.iloc[0] = 100.0
    adj_norm.iloc[0]   = 100.0

    # 통계
    def _stats(s: pd.Series) -> dict:
        ret_pct = float((s.iloc[-1] / s.iloc[0] - 1) * 100)
        vol_pct = float(s.pct_change().std() * (252**0.5) * 100)
        return {"return_pct": round(ret_pct, 2), "annual_vol_pct": round(vol_pct, 2)}

    stats = {
        "kospi":    _stats(kospi_s),
        "adjusted": _stats(adj_norm),
        "total_excl_weight": round(total_excl_weight * 100, 1),
    }

    # 차트 그리기 (화이트 테마)
    BG    = "#ffffff"
    SURF  = "#f8f9fa"
    GRID  = "#e8e8e8"
    TEXT  = "#1a1a1a"
    MUTED = "#666666"
    C1    = "#0078d4"   # KOSPI
    C2    = "#e63946"   # 제외 후

    fig = plt.figure(figsize=(13, 8), facecolor=BG)
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.44, wspace=0.30,
                            left=0.07, right=0.97, top=0.90, bottom=0.08)

    # Panel 1: 누적 수익률 비교 (상단 전체)
    ax1 = fig.add_subplot(gs[0, :], facecolor=SURF)
    excl_label = _build_excl_label(excluded, excl_sectors, total_excl_weight)
    ax1.plot(kospi_norm.index, kospi_norm.values, color=C1, lw=2.0,
             label="KOSPI (실제)", zorder=3)
    ax1.plot(adj_norm.index, adj_norm.values, color=C2, lw=2.0, ls="--",
             label=f"KOSPI 제외 후 ({excl_label})", zorder=3)
    ax1.axhline(100, color=MUTED, lw=0.8, ls=":")
    ax1.fill_between(adj_norm.index, kospi_norm.values, adj_norm.values,
                     where=(adj_norm.values > kospi_norm.values),
                     alpha=0.12, color=C2, label="제외 후 > KOSPI")
    ax1.fill_between(adj_norm.index, kospi_norm.values, adj_norm.values,
                     where=(adj_norm.values <= kospi_norm.values),
                     alpha=0.12, color=C1, label="KOSPI > 제외 후")
    ax1.set_title(f"KOSPI vs KOSPI 제외 후 비교  |  {req.period}", color=TEXT, fontsize=11, pad=8, fontweight="bold")
    ax1.tick_params(colors=MUTED, labelsize=7)
    for sp in ax1.spines.values(): sp.set_color(GRID)
    ax1.grid(color=GRID, lw=0.6, alpha=0.8)
    ax1.tick_params(axis="x", rotation=20)
    ax1.legend(fontsize=8, facecolor=BG, labelcolor=TEXT, framealpha=0.9, loc="upper left")
    ax1.set_facecolor(BG)

    # Panel 2: 수익률 차이 (하단 좌)
    ax2 = fig.add_subplot(gs[1, 0], facecolor=BG)
    diff = adj_norm.values - kospi_norm.values
    colors_diff = [C2 if d > 0 else C1 for d in diff]
    ax2.bar(range(len(diff)), diff, color=colors_diff, alpha=0.7, width=1.0)
    ax2.axhline(0, color=MUTED, lw=0.8)
    ax2.set_title("KOSPI 대비 초과 성과 (제외 후 - 실제)", color=TEXT, fontsize=9, pad=6)
    ax2.tick_params(colors=MUTED, labelsize=7)
    for sp in ax2.spines.values(): sp.set_color(GRID)
    ax2.grid(color=GRID, lw=0.6, axis="y", alpha=0.8)
    ax2.set_xticks([])
    ax2.set_facecolor(BG)

    # Panel 3: 제외 종목 기여 비중 파이 (하단 우)
    ax3 = fig.add_subplot(gs[1, 1], facecolor=BG)
    if excluded:
        pie_labels = [c["name"] for c in excluded]
        pie_sizes  = [c["weight"] for c in excluded]
        SECTOR_COLORS = ["#0078d4","#e63946","#2dc653","#f59e0b","#a855f7",
                         "#06b6d4","#f97316","#ec4899","#14b8a6","#8b5cf6"]
        wedge_colors = [SECTOR_COLORS[i % len(SECTOR_COLORS)] for i in range(len(pie_sizes))]
        wedges, texts, autotexts = ax3.pie(
            pie_sizes, labels=pie_labels, colors=wedge_colors,
            autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
            pctdistance=0.78, startangle=90,
            wedgeprops={"edgecolor": BG, "linewidth": 1.5},
            textprops={"fontsize": 7, "color": TEXT},
        )
        for at in autotexts: at.set_fontsize(6.5)
        ax3.set_title(f"제외 종목 구성  (총 비중 {total_excl_weight*100:.1f}%)", color=TEXT, fontsize=9, pad=6)
    else:
        ax3.text(0.5, 0.5, "제외 종목 없음", ha="center", va="center", color=MUTED, fontsize=10)
        ax3.set_title("제외 종목 구성", color=TEXT, fontsize=9, pad=6)
    ax3.set_facecolor(BG)

    title_excl = excl_label if excl_label else "없음"
    fig.suptitle(f"KOSPI 제외 지수 분석  |  제외: {title_excl}",
                 color=TEXT, fontsize=12, fontweight="bold", y=0.96)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    return {
        "image": img_b64,
        "stats": stats,
        "excluded": [{"name": c["name"], "ticker": c["ticker"].replace(".KS","").replace(".KQ",""),
                      "sector": c["sector"], "weight_pct": round(c["weight"]*100,1)} for c in excluded],
        "period": req.period,
        "is_simulated": is_simulated,
        "fetched_at": fetched_at.isoformat(),
        "warning": "Yahoo Finance 데이터 수신 실패로 시뮬레이션 데이터를 표시합니다." if is_simulated else None,
    }


def _build_excl_label(excluded: list, excl_sectors: set, total_weight: float) -> str:
    if not excluded:
        return "없음"
    sector_names = sorted(excl_sectors) if excl_sectors else []
    stock_names  = [c["name"] for c in excluded if c["sector"] not in excl_sectors]
    parts = sector_names + stock_names
    label = ", ".join(parts[:3])
    if len(parts) > 3:
        label += f" 외 {len(parts)-3}개"
    return label


@app.get("/api/macro/kospi-ex/meta")
def macro_kospi_ex_meta() -> dict[str, object]:
    sectors = sorted({c["sector"] for c in KOSPI_COMPONENTS})
    components = [
        {"ticker": c["ticker"].replace(".KS","").replace(".KQ",""),
         "name": c["name"], "sector": c["sector"],
         "weight_pct": round(c["weight"]*100, 1)}
        for c in KOSPI_COMPONENTS
    ]
    return {"sectors": sectors, "components": components}


# ── 거시경제현황 2: GBM 시뮬레이션 대시보드 ──────────────────────────────────

class MacroSimRequest(BaseModel):
    n_days:    int   = 252
    seed:      int   = 42

@app.post("/api/macro/simulation")
def macro_simulation(req: MacroSimRequest) -> dict[str, object]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    import io, base64
    configure_matplotlib_korean_font(plt)

    DARK   = "#0f172a"
    SURF   = "#1e293b"
    BORDER = "#334155"
    TEXT   = "#e2e8f0"
    MUTED  = "#64748b"
    COLORS = ["#3b82f6","#f59e0b","#ef4444","#22c55e","#a855f7","#06b6d4"]

    rng = np.random.default_rng(req.seed)
    T   = max(60, min(req.n_days, 1260))
    dt  = 1 / 252

    def gbm(s0, mu, sigma, n, rng):
        shocks = rng.standard_normal(n)
        log_r  = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
        return s0 * np.exp(np.cumsum(log_r))

    indicators = {
        "기준금리 (%)" :   {"s0": 3.50,  "mu":  0.05, "sigma": 0.08,  "fmt": ".2f"},
        "CPI (전년비 %)":  {"s0": 3.20,  "mu":  0.02, "sigma": 0.12,  "fmt": ".2f"},
        "WTI 유가 ($)":    {"s0": 78.0,  "mu":  0.03, "sigma": 0.30,  "fmt": ".1f"},
        "USD/KRW":         {"s0": 1320,  "mu": -0.01, "sigma": 0.07,  "fmt": ".0f"},
        "KOSPI":           {"s0": 2650,  "mu":  0.06, "sigma": 0.18,  "fmt": ".0f"},
        "S&P 500":         {"s0": 5200,  "mu":  0.08, "sigma": 0.16,  "fmt": ".0f"},
    }

    # macro regime: 경기 사이클 phase 추가 (상승/둔화/침체/회복)
    phase_len  = T // 4
    phases     = ["상승기", "과열기", "침체기", "회복기"]
    phase_muls = [1.0, 0.5, -0.5, 1.2]

    series_dict = {}
    for name, cfg in indicators.items():
        mu_adj = cfg["mu"]
        vals = []
        for ph_i, mul in enumerate(phase_muls):
            seg = gbm(cfg["s0"] if not vals else vals[-1],
                      mu_adj * mul, cfg["sigma"],
                      min(phase_len, T - len(vals)), rng)
            vals.extend(seg.tolist())
            if len(vals) >= T:
                break
        series_dict[name] = np.array(vals[:T])

    days = np.arange(T)

    # ── Figure ────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(14, 12), facecolor=DARK)
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35,
                            left=0.08, right=0.97, top=0.93, bottom=0.05)

    names_list = list(series_dict.keys())
    for idx, (name, vals) in enumerate(series_dict.items()):
        row, col = divmod(idx, 2)
        ax = fig.add_subplot(gs[row, col])
        ax.set_facecolor(SURF)
        color = COLORS[idx]
        cfg   = indicators[name]

        ax.plot(days, vals, color=color, lw=1.5)
        ax.fill_between(days, vals, vals[0], alpha=0.12, color=color)

        # 경기국면 배경
        for ph_i, (ph_name, mul) in enumerate(zip(phases, phase_muls)):
            x0 = ph_i * phase_len
            x1 = min((ph_i + 1) * phase_len, T)
            bg = "#22c55e22" if mul > 0.8 else "#f59e0b22" if mul > 0 else "#ef444422"
            ax.axvspan(x0, x1, color=bg, alpha=0.4)
            ax.text((x0 + x1) / 2, ax.get_ylim()[0], ph_name,
                    ha="center", va="bottom", fontsize=6, color=MUTED)

        cur  = vals[-1]
        chg  = (cur / vals[0] - 1) * 100
        sign = "+" if chg >= 0 else ""
        ax.set_title(f"{name}  현재: {cur:{cfg['fmt']}}  ({sign}{chg:.1f}%)",
                     color=TEXT, fontsize=8.5, pad=5)
        ax.tick_params(colors=TEXT, labelsize=7)
        ax.spines[:].set_color(BORDER)
        ax.set_xlim(0, T)

        # 최고/최저 표시
        hi, lo = np.argmax(vals), np.argmin(vals)
        ax.annotate(f"고: {vals[hi]:{cfg['fmt']}}",
                    xy=(hi, vals[hi]), xytext=(5, 5), textcoords="offset points",
                    fontsize=6, color="#22c55e", arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.5))
        ax.annotate(f"저: {vals[lo]:{cfg['fmt']}}",
                    xy=(lo, vals[lo]), xytext=(5, -12), textcoords="offset points",
                    fontsize=6, color="#ef4444", arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.5))

    # 경기국면 범례 (우측 상단)
    from matplotlib.patches import Patch
    legend_els = [
        Patch(facecolor="#22c55e44", label="상승기"),
        Patch(facecolor="#f59e0b44", label="과열기"),
        Patch(facecolor="#ef444444", label="침체기"),
        Patch(facecolor="#22c55e44", label="회복기"),
    ]
    fig.legend(handles=legend_els, loc="upper right", fontsize=7,
               facecolor=SURF, labelcolor=TEXT, framealpha=0.8, ncol=4,
               bbox_to_anchor=(0.97, 0.995))

    fig.suptitle(f"거시경제 시뮬레이션 대시보드 — {T}거래일 GBM 시뮬레이션",
                 color=TEXT, fontsize=12, fontweight="bold", y=0.975)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=DARK)
    plt.close(fig)
    buf.seek(0)
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    summary = {name: {"start": round(float(v[0]), 2),
                      "end":   round(float(v[-1]), 2),
                      "chg_pct": round((v[-1]/v[0]-1)*100, 2)}
               for name, v in series_dict.items()}

    return {"image": img_b64, "summary": summary, "n_days": T}


app.include_router(quiz_router)

class CompanyFinancialsRequest(BaseModel):
    ticker: str = Field(default="AAPL", min_length=1, max_length=30)
    period: str = Field(default="annual", pattern="^(annual|quarterly)$")


@app.post("/api/finance/company-financials")
def company_financials(req: CompanyFinancialsRequest) -> dict[str, object]:
    """Return structured financial data for a ticker using yfinance."""
    import math
    import yfinance as yf
    import pandas as pd

    def safe_float(v) -> float | None:
        if v is None:
            return None
        try:
            f = float(v)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return None

    def row(df: "pd.DataFrame", *keys: str) -> "pd.Series":
        for key in keys:
            if key in df.index:
                return df.loc[key]
        return pd.Series(dtype=float)

    def series_to_list(series: "pd.Series") -> list[dict]:
        result = []
        for idx, val in series.items():
            label = str(idx)[:7] if hasattr(idx, "strftime") else str(idx)[:10]
            result.append({"period": label, "value": safe_float(val)})
        return list(reversed(result))

    ticker_sym = req.ticker.strip().upper()
    try:
        tk = yf.Ticker(ticker_sym)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"티커 오류: {exc}") from exc

    # Select annual vs quarterly statements
    if req.period == "annual":
        income  = tk.income_stmt
        balance = tk.balance_sheet
        cashflow = tk.cashflow
    else:
        income  = tk.quarterly_income_stmt
        balance = tk.quarterly_balance_sheet
        cashflow = tk.quarterly_cashflow

    if income is None or income.empty:
        raise HTTPException(status_code=404, detail=f"'{ticker_sym}' 재무데이터를 찾을 수 없습니다.")

    # ── Income statement rows ──────────────────────────────────────────────────
    revenue       = row(income, "Total Revenue")
    cogs          = row(income, "Cost Of Revenue")
    gross_profit  = row(income, "Gross Profit")
    op_expense    = row(income, "Operating Expense")
    op_income     = row(income, "Operating Income", "EBIT")
    other_income  = row(income, "Other Income Expense",
                        "Other Non Operating Income Expense",
                        "Non Operating Income")
    pretax        = row(income, "Pretax Income")
    tax           = row(income, "Tax Provision")
    net_income    = row(income, "Net Income")

    # ── Balance sheet rows ────────────────────────────────────────────────────
    total_debt = row(balance, "Total Debt", "Long Term Debt")
    cash       = row(balance,
                     "Cash And Cash Equivalents",
                     "Cash Cash Equivalents And Short Term Investments")

    # ── Cash flow rows ─────────────────────────────────────────────────────────
    op_cf  = row(cashflow, "Operating Cash Flow",
                 "Cash Flow From Continuing Operating Activities")
    capex  = row(cashflow, "Capital Expenditure")

    # Free Cash Flow = Operating CF + Capex (capex stored as negative)
    if not op_cf.empty and not capex.empty:
        shared_idx = op_cf.index.intersection(capex.index)
        fcf = op_cf.loc[shared_idx] + capex.loc[shared_idx]
    elif not op_cf.empty:
        fcf = op_cf
    else:
        fcf = pd.Series(dtype=float)

    # Net margin %
    margin_data: list[dict] = []
    for idx in revenue.index:
        r = safe_float(revenue.get(idx))
        n = safe_float(net_income.get(idx))
        label = str(idx)[:7]
        if r and n and r != 0:
            margin_data.append({"period": label, "value": round(n / r * 100, 2)})
    margin_data = list(reversed(margin_data))

    # ── Waterfall (most recent period) ────────────────────────────────────────
    def wf(series: "pd.Series") -> float | None:
        return safe_float(series.iloc[0]) if not series.empty else None

    waterfall = {
        "revenue":          wf(revenue),
        "cogs":             wf(cogs),
        "gross_profit":     wf(gross_profit),
        "operating_expense": wf(op_expense),
        "operating_income": wf(op_income),
        "other_income":     wf(other_income),
        "tax":              wf(tax),
        "net_income":       wf(net_income),
    }

    # ── Earnings history ──────────────────────────────────────────────────────
    earnings_data: list[dict] = []
    try:
        ed = tk.earnings_dates
        if ed is not None and not ed.empty:
            for idx, erow in list(ed.iterrows())[:20]:
                earnings_data.append({
                    "date":         str(idx)[:10],
                    "eps_estimate": safe_float(erow.get("EPS Estimate")),
                    "eps_actual":   safe_float(erow.get("Reported EPS")),
                    "surprise_pct": safe_float(erow.get("Surprise(%)")),
                })
            earnings_data.sort(key=lambda x: x["date"])
    except Exception:
        pass

    # ── Company info ─────────────────────────────────────────────────────────
    company_name = ticker_sym
    currency = "USD"
    try:
        info = tk.info or {}
        company_name = info.get("longName") or info.get("shortName") or ticker_sym
        currency = info.get("currency", "USD")
    except Exception:
        pass

    return {
        "ticker":   ticker_sym,
        "name":     company_name,
        "currency": currency,
        "period":   req.period,
        "performance": {
            "revenue":        series_to_list(revenue),
            "net_income":     series_to_list(net_income),
            "net_margin_pct": margin_data,
        },
        "waterfall": waterfall,
        "debt": {
            "total_debt": series_to_list(total_debt),
            "fcf":        series_to_list(fcf),
            "cash":       series_to_list(cash),
        },
        "earnings": earnings_data,
    }


PERIOD_DAYS = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
INTRADAY_PERIODS = {"1d"}
# 이동평균(MA20) 등 보조지표가 표시 구간 맨 앞부터 끊김 없이 나오도록, 실제 요청 기간보다
# 이만큼 앞선 과거 데이터까지 함께 가져와 지표를 계산한 뒤 표시 구간만 잘라서 내려준다.
MA_LOOKBACK_BUFFER_DAYS = 40
HOME_MARKETS = {
    "kospi":  {"ticker": "^KS11", "name": "KOSPI", "base_price": 2650.0, "seed": 42},
    "kosdaq": {"ticker": "^KQ11", "name": "KOSDAQ", "base_price": 850.0, "seed": 73},
    "nasdaq": {"ticker": "^IXIC", "name": "NASDAQ", "base_price": 18000.0, "seed": 109},
    "sp500":  {"ticker": "^GSPC", "name": "S&P 500", "base_price": 5200.0, "seed": 151},
    "dow":    {"ticker": "^DJI", "name": "다우존스", "base_price": 39000.0, "seed": 187},
    "gold":    {"ticker": "GC=F", "name": "국제 금 선물", "base_price": 2600.0, "seed": 211},
    "oil":     {"ticker": "CL=F", "name": "WTI 원유 선물", "base_price": 75.0, "seed": 233},
    "dxy":     {"ticker": "DX-Y.NYB", "name": "달러인덱스(DXY)", "base_price": 103.0, "seed": 255},
    "usdkrw":  {"ticker": "KRW=X", "name": "원/달러 환율", "base_price": 1380.0, "seed": 277},
    "ust10y":  {"ticker": "^TNX", "name": "미국 10년물 국채금리", "base_price": 42.0, "seed": 299},
    "bitcoin": {"ticker": "BTC-USD", "name": "비트코인(BTC/USD)", "base_price": 65000.0, "seed": 321},
}

# 검색 서버가 일시적으로 응답하지 않을 때도 찾을 수 있도록 제공하는 대표 종목이다.
MODAL_CHART_STOCKS = {
    "aapl": {"ticker": "AAPL", "name": "Apple", "base_price": 220.0, "seed": 401},
    "msft": {"ticker": "MSFT", "name": "Microsoft", "base_price": 450.0, "seed": 419},
    "googl": {"ticker": "GOOGL", "name": "Alphabet", "base_price": 180.0, "seed": 431},
    "amzn": {"ticker": "AMZN", "name": "Amazon", "base_price": 220.0, "seed": 443},
    "nvda": {"ticker": "NVDA", "name": "NVIDIA", "base_price": 180.0, "seed": 457},
    "meta": {"ticker": "META", "name": "Meta", "base_price": 750.0, "seed": 467},
    "tsla": {"ticker": "TSLA", "name": "Tesla", "base_price": 330.0, "seed": 479},
    "samsung": {"ticker": "005930.KS", "name": "삼성전자", "base_price": 75000.0, "seed": 491},
    "skhynix": {"ticker": "000660.KS", "name": "SK하이닉스", "base_price": 250000.0, "seed": 503},
    "lgenergy": {"ticker": "373220.KS", "name": "LG에너지솔루션", "base_price": 350000.0, "seed": 521},
    "samsungbio": {"ticker": "207940.KS", "name": "삼성바이오로직스", "base_price": 1000000.0, "seed": 541},
    "hyundai": {"ticker": "005380.KS", "name": "현대차", "base_price": 220000.0, "seed": 557},
    "kia": {"ticker": "000270.KS", "name": "기아", "base_price": 100000.0, "seed": 571},
    "naver": {"ticker": "035420.KS", "name": "NAVER", "base_price": 200000.0, "seed": 587},
}
MODAL_CHART_INSTRUMENTS = {**HOME_MARKETS, **MODAL_CHART_STOCKS}
INTRADAY_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h"}
CHART_TIMEFRAMES = {
    "1m": ("1m", 1), "3m": ("3m", 1), "5m": ("5m", 1), "15m": ("15m", 1),
    "30m": ("30m", 1), "1h": ("1h", 1), "1d": ("1d", 365), "2y": ("2y", 365 * 2), "5y": ("5y", 365 * 5), "1wk": ("1wk", 365 * 5),
    "1mo": ("1mo", 365 * 10), "1y": ("1y", 365 * 30),
}
# Yahoo 자동완성은 한글 회사명을 충분히 지원하지 않으므로, 국내에서 많이 조회하는
# 종목은 KRX 코드와 함께 보완한다. 이후 Yahoo 결과와 동일한 형식으로 반환된다.
KOREAN_SEARCH_ALIASES = {
    "삼성전자": ("005930.KS", "삼성전자"), "SK하이닉스": ("000660.KS", "SK하이닉스"),
    "LG에너지솔루션": ("373220.KS", "LG에너지솔루션"), "삼성바이오로직스": ("207940.KS", "삼성바이오로직스"),
    "현대차": ("005380.KS", "현대자동차"), "기아": ("000270.KS", "기아"), "NAVER": ("035420.KS", "NAVER"),
    "카카오": ("035720.KS", "카카오"), "셀트리온": ("068270.KS", "셀트리온"), "삼성물산": ("028260.KS", "삼성물산"),
    "삼성SDI": ("006400.KS", "삼성SDI"), "LG화학": ("051910.KS", "LG화학"), "KB금융": ("105560.KS", "KB금융"),
    "신한지주": ("055550.KS", "신한지주"), "POSCO홀딩스": ("005490.KS", "POSCO홀딩스"), "한화에어로스페이스": ("012450.KS", "한화에어로스페이스"),
    "두산에너빌리티": ("034020.KS", "두산에너빌리티"), "HD현대중공업": ("329180.KS", "HD현대중공업"),
    "알테오젠": ("196170.KQ", "알테오젠"), "에코프로비엠": ("247540.KQ", "에코프로비엠"), "에코프로": ("086520.KQ", "에코프로"),
    "HLB": ("028300.KQ", "HLB"), "펄어비스": ("263750.KQ", "펄어비스"), "JYP": ("035900.KQ", "JYP Ent."),
}


@app.get("/api/home/chart-search")
def home_chart_search(q: str = "") -> dict[str, object]:
    """Yahoo Finance 자동완성과 기본 대표 종목으로 차트 검색 결과를 제공한다."""
    query = q.strip()
    if len(query) < 1:
        return {"items": []}
    items: list[dict[str, str]] = []
    lowered = query.lower()
    # 한글 검색은 먼저 KRX 별칭을 확인한다. 부분 검색도 지원한다.
    for alias, (ticker, name) in KOREAN_SEARCH_ALIASES.items():
        if lowered in alias.lower() or lowered in name.lower():
            items.append({"ticker": ticker, "name": name, "exchange": "Korea Exchange"})
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search?" + urllib.parse.urlencode({"q": query, "quotesCount": 12, "newsCount": 0})
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
        allowed_types = {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY", "FUTURE", "MUTUALFUND"}
        for quote in payload.get("quotes", []):
            ticker = str(quote.get("symbol", "")).upper()
            if quote.get("quoteType") not in allowed_types or not re.fullmatch(r"[A-Z0-9.^=\-]{1,24}", ticker):
                continue
            items.append({"ticker": ticker, "name": str(quote.get("shortname") or quote.get("longname") or ticker), "exchange": str(quote.get("exchange", ""))})
    except Exception:
        pass
    if not items:
        for config in MODAL_CHART_INSTRUMENTS.values():
            if lowered in config["ticker"].lower() or lowered in config["name"].lower():
                items.append({"ticker": config["ticker"], "name": config["name"], "exchange": ""})
    return {"items": items[:12]}


@app.get("/api/home/market-candle")
def home_market_candle(market: str = "kospi", period: str = "3mo", interval: str = "5m", ticker: str = "", timeframe: str = "") -> dict[str, object]:
    if period not in PERIOD_DAYS and period not in INTRADAY_PERIODS:
        period = "3mo"
    if interval not in INTRADAY_INTERVALS:
        interval = "5m"
    if ticker and re.fullmatch(r"[A-Za-z0-9.^=\-]{1,24}", ticker):
        config = {"ticker": ticker.upper(), "name": ticker.upper(), "base_price": 100.0, "seed": 911}
    else:
        config = MODAL_CHART_INSTRUMENTS.get(market, HOME_MARKETS["kospi"])
    if timeframe in CHART_TIMEFRAMES:
        interval, history_days = CHART_TIMEFRAMES[timeframe]
        intraday = interval in INTRADAY_INTERVALS
        display_days = history_days
    else:
        intraday = period in INTRADAY_PERIODS
        display_days = PERIOD_DAYS.get(period, 90)
    import pandas as pd
    import datetime as _dt
    display_from: str | None = None
    try:
        import yfinance as yf
        if intraday:
            # Yahoo Finance에는 3분 간격이 없으므로 1분 OHLCV를 3분봉으로 집계한다.
            fetch_interval = "1m" if interval in {"1m", "3m"} else interval
            df = yf.download(config["ticker"], period="1d", interval=fetch_interval,
                             progress=False, auto_adjust=True, threads=False)
            if interval == "3m" and not df.empty:
                # yfinance 버전에 따라 단일 티커도 MultiIndex 열을 반환한다.
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.resample("3min", label="left", closed="left").agg({
                    "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
                }).dropna(subset=["Open", "High", "Low", "Close"])
        else:
            days = display_days
            end_date = _dt.date.today() + _dt.timedelta(days=1)
            start_date = end_date - _dt.timedelta(days=days + MA_LOOKBACK_BUFFER_DAYS)
            display_from = (end_date - _dt.timedelta(days=days)).isoformat()
            df = yf.download(config["ticker"], start=start_date.isoformat(), end=end_date.isoformat(),
                             interval="1d", progress=False, auto_adjust=True, threads=False)
            if timeframe in {"1wk", "1mo", "1y"} and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                rule = {"1wk": "W-FRI", "1mo": "ME", "1y": "YE"}[timeframe]
                df = df.resample(rule).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Open", "High", "Low", "Close"])
        if df.empty:
            raise ValueError("empty")
        ohlcv = []
        for idx, row in df.iterrows():
            def _f(col):
                v = row.get(col)
                if v is None:
                    return None
                if hasattr(v, '__iter__') and not isinstance(v, (str, float, int)):
                    v = list(v)[0]
                return round(float(v), 2)
            ohlcv.append({
                "date": idx.isoformat() if intraday else str(idx)[:10],
                "o": _f("Open"), "h": _f("High"),
                "l": _f("Low"),  "c": _f("Close"),
                "v": int(_f("Volume") or 0),
            })
        return {"market": market, "name": config["name"], "ticker": config["ticker"], "ohlcv": ohlcv,
                "is_simulated": False, "display_from": display_from, "interval": interval}
    except Exception:
        import math
        rng_state = config["seed"]
        def _rand():
            nonlocal rng_state
            rng_state = (rng_state * 1664525 + 1013904223) % 2**32
            return rng_state / 2**32
        def _randn():
            u, v = max(_rand(), 1e-10), _rand()
            return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)
        price = config["base_price"]
        ohlcv = []
        if intraday:
            interval_minutes = int(interval[:-1])
            n_bars = 390 // interval_minutes  # 미국 정규장 6.5시간 분량
            base = pd.Timestamp("today").normalize() + pd.Timedelta(hours=9)
            for i in range(n_bars):
                ts = base + pd.Timedelta(minutes=interval_minutes * i)
                chg = _randn() * price * 0.003
                o = price
                c = max(o * 0.97, o + chg)
                h = max(o, c) * (1 + _rand() * 0.002)
                l = min(o, c) * (1 - _rand() * 0.002)
                ohlcv.append({"date": ts.isoformat(), "o": round(o, 2), "h": round(h, 2),
                              "l": round(l, 2), "c": round(c, 2), "v": int(_rand() * 1e6)})
                price = c
        else:
            days = display_days
            total_days = days + MA_LOOKBACK_BUFFER_DAYS
            n_bars = int(total_days * 0.72)
            base = pd.Timestamp("today") - pd.Timedelta(days=total_days)
            display_from = (pd.Timestamp("today") - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            for i in range(n_bars):
                date = (base + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d")
                chg = _randn() * price * 0.012
                o = price
                c = max(o * 0.9, o + chg)
                h = max(o, c) * (1 + _rand() * 0.008)
                l = min(o, c) * (1 - _rand() * 0.008)
                ohlcv.append({"date": date, "o": round(o, 2), "h": round(h, 2),
                              "l": round(l, 2), "c": round(c, 2), "v": int(_rand() * 1e8)})
                price = c
        return {"market": market, "name": config["name"], "ticker": config["ticker"], "ohlcv": ohlcv,
                "is_simulated": True, "display_from": display_from, "interval": interval}


@app.get("/api/home/kospi-candle")
def home_kospi_candle(period: str = "3mo") -> dict[str, object]:
    """Backward-compatible KOSPI endpoint for older clients."""
    return home_market_candle("kospi", period)


@app.get("/api/home/box-range")
def home_box_range(market: str = "kospi", start: str = "", end: str = "") -> dict[str, object]:
    """지정한 from~to 기간의 박스권(최고가·최저가) 상단/하단 퍼센티지를 계산한다."""
    import datetime as _dt
    config = HOME_MARKETS.get(market, HOME_MARKETS["kospi"])

    today = _dt.date.today()
    try:
        end_date = _dt.date.fromisoformat(end) if end else today
    except ValueError:
        end_date = today
    try:
        start_date = _dt.date.fromisoformat(start) if start else end_date - _dt.timedelta(days=90)
    except ValueError:
        start_date = end_date - _dt.timedelta(days=90)
    if start_date >= end_date:
        start_date = end_date - _dt.timedelta(days=1)

    import pandas as pd
    ohlcv: list[dict] = []
    is_simulated = True
    try:
        import yfinance as yf
        df = yf.download(config["ticker"], start=start_date.isoformat(),
                         end=(end_date + _dt.timedelta(days=1)).isoformat(),
                         interval="1d", progress=False, auto_adjust=True, threads=False)
        if df.empty:
            raise ValueError("empty")
        for idx, row in df.iterrows():
            def _f(col):
                v = row.get(col)
                if v is None:
                    return None
                if hasattr(v, '__iter__') and not isinstance(v, (str, float, int)):
                    v = list(v)[0]
                return round(float(v), 2)
            ohlcv.append({
                "date": str(idx)[:10],
                "o": _f("Open"), "h": _f("High"),
                "l": _f("Low"),  "c": _f("Close"),
            })
        is_simulated = False
    except Exception:
        import math
        rng_state = config["seed"]
        def _rand():
            nonlocal rng_state
            rng_state = (rng_state * 1664525 + 1013904223) % 2**32
            return rng_state / 2**32
        def _randn():
            u, v = max(_rand(), 1e-10), _rand()
            return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)
        price = config["base_price"]
        n_days = max(1, (end_date - start_date).days)
        n_bars = max(1, int(n_days * 0.72))
        for i in range(n_bars):
            date = (start_date + _dt.timedelta(days=int(i / 0.72) + 1)).isoformat()
            chg = _randn() * price * 0.012
            o = price
            c = max(o * 0.9, o + chg)
            h = max(o, c) * (1 + _rand() * 0.008)
            l = min(o, c) * (1 - _rand() * 0.008)
            ohlcv.append({"date": date, "o": round(o, 2), "h": round(h, 2),
                          "l": round(l, 2), "c": round(c, 2)})
            price = c

    if not ohlcv:
        raise HTTPException(status_code=404, detail="해당 기간의 시세 데이터를 찾을 수 없습니다.")

    box_high = max(bar["h"] for bar in ohlcv)
    box_low  = min(bar["l"] for bar in ohlcv)
    last_close = ohlcv[-1]["c"]
    box_range = box_high - box_low
    upper_pct    = round((box_high - last_close) / last_close * 100, 2) if last_close else None
    lower_pct    = round((last_close - box_low) / last_close * 100, 2) if last_close else None
    position_pct = round((last_close - box_low) / box_range * 100, 2) if box_range else None

    return {
        "market": market, "name": config["name"], "ticker": config["ticker"],
        "start": start_date.isoformat(), "end": end_date.isoformat(),
        "ohlcv": ohlcv, "is_simulated": is_simulated,
        "box_high": round(box_high, 2), "box_low": round(box_low, 2),
        "last_close": last_close,
        "upper_pct": upper_pct, "lower_pct": lower_pct, "position_pct": position_pct,
    }


# ─── DART Financial Analysis ─────────────────────────────────────────────────

class DartFinancialAnalysisRequest(BaseModel):
    corp_code:    str       = Field(min_length=8, max_length=8, description="DART 고유번호 (8자리)")
    bsns_year:    str       = Field(default="2023", pattern=r"^\d{4}$")
    reprt_code:   str       = Field(default="11011", pattern=r"^1101[1-4]$",
                                    description="11011=사업보고서 11012=반기 11013=1분기 11014=3분기")


def _parse_dart_amounts(items: list[dict]) -> dict[str, dict[str, float]]:
    """Extract key financial line items from DART fnlttSinglAcnt response.

    Returns a dict mapping account_nm → {current, prior}.
    """
    ACCT_MAP: dict[str, list[str]] = {
        "current_assets":       ["유동자산"],
        "noncurrent_assets":    ["비유동자산"],
        "total_assets":         ["자산총계"],
        "current_liabilities":  ["유동부채"],
        "noncurrent_liabilities": ["비유동부채"],
        "total_liabilities":    ["부채총계"],
        "paid_in_capital":      ["자본금"],
        "retained_earnings":    ["이익잉여금"],
        "total_equity":         ["자본총계"],
        "revenue":              ["매출액", "영업수익", "수익(매출액)"],
        "op_income":            ["영업이익", "영업손익"],
        "pretax_income":        ["법인세차감전", "법인세비용차감전"],
        "net_income":           ["당기순이익(손실)", "당기순이익"],
        "comprehensive_income": ["총포괄손익"],
    }

    def _num(val: object) -> float:
        try:
            s = str(val or "").replace(",", "").strip()
            return float(s) if s and s not in ("-", "") else 0.0
        except (ValueError, TypeError):
            return 0.0

    result: dict[str, dict[str, float]] = {}
    for key, kws in ACCT_MAP.items():
        for item in items:
            nm = (item.get("account_nm") or "").strip()
            if any(kw in nm for kw in kws):
                result[key] = {
                    "current": _num(item.get("thstrm_amount")),
                    "prior":   _num(item.get("frmtrm_amount")),
                }
                break
        if key not in result:
            result[key] = {"current": 0.0, "prior": 0.0}
    return result


def _calc_dart_ratios(fin: dict[str, dict[str, float]]) -> dict[str, float | None]:
    """Compute financial ratios from parsed DART data."""

    def g(k: str, period: str = "current") -> float:
        return fin.get(k, {}).get(period, 0.0)

    def safe_r(a: float, b: float, mult: float = 100.0) -> float | None:
        return (a / b * mult) if b != 0 else None

    rev     = g("revenue")
    prev_rev = g("revenue", "prior")
    op_inc  = g("op_income")
    net_inc = g("net_income")
    assets  = g("total_assets")
    liab    = g("total_liabilities")
    equity  = g("total_equity")
    cur_a   = g("current_assets")
    cur_l   = g("current_liabilities")
    ret_e   = g("retained_earnings")
    prev_eq = g("total_equity", "prior")
    avg_equity = (equity + prev_eq) / 2 if prev_eq else equity

    return {
        "debt_equity_ratio": safe_r(liab, equity),
        "op_margin":         safe_r(op_inc, rev),
        "net_margin":        safe_r(net_inc, rev),
        "roe":               safe_r(net_inc, avg_equity),
        "roa":               safe_r(net_inc, assets),
        "current_ratio":     safe_r(cur_a, cur_l),
        "revenue_growth":    safe_r(rev - prev_rev, prev_rev) if prev_rev else None,
        "equity_growth":     safe_r(equity - prev_eq, prev_eq) if prev_eq else None,
        "retained_ratio":    safe_r(ret_e, equity),
        "debt_ratio":        safe_r(liab, assets),
    }


def _score_financial_health(ratios: dict) -> tuple[float, dict]:
    """Score financial health on 0-100 scale with breakdown."""
    breakdown: dict[str, dict] = {}
    total = 0.0

    def score_item(key: str, label: str, max_score: float,
                   thresholds: list[tuple[float, float]], value: float | None) -> float:
        if value is None:
            s = max_score * 0.5
        else:
            s = 0.0
            for limit, pts in thresholds:
                if value >= limit:
                    s = pts
                    break
        breakdown[label] = {"score": round(s, 1), "max": max_score, "value": value}
        return s

    # 부채비율 (20점) — 낮을수록 좋음 (역방향)
    dr = ratios.get("debt_equity_ratio")
    dr_inv = -dr if dr is not None else None  # invert so higher=better
    total += score_item("debt_equity_ratio", "부채비율", 20,
                        [(-50, 20), (-100, 16), (-200, 10), (-300, 5), (-1e9, 0)], dr_inv)

    # 영업이익률 (20점)
    total += score_item("op_margin", "영업이익률", 20,
                        [(20, 20), (10, 16), (5, 10), (0, 5), (-1e9, 0)],
                        ratios.get("op_margin"))

    # ROE (15점)
    total += score_item("roe", "자기자본이익률(ROE)", 15,
                        [(20, 15), (10, 12), (5, 8), (0, 4), (-1e9, 0)],
                        ratios.get("roe"))

    # 유동비율 (15점)
    total += score_item("current_ratio", "유동비율", 15,
                        [(200, 15), (150, 12), (100, 8), (50, 4), (-1e9, 0)],
                        ratios.get("current_ratio"))

    # 매출 성장률 (15점)
    total += score_item("revenue_growth", "매출 성장률", 15,
                        [(15, 15), (5, 12), (0, 7), (-10, 3), (-1e9, 0)],
                        ratios.get("revenue_growth"))

    # 이익잉여금 비율 (15점)
    total += score_item("retained_ratio", "이익잉여금 비율", 15,
                        [(70, 15), (50, 12), (30, 8), (10, 4), (-1e9, 0)],
                        ratios.get("retained_ratio"))

    return round(total, 1), breakdown


def _generate_dart_analysis(
    company: dict, market: str, ratios: dict,
    score: float, grade: str, bsns_year: str,
) -> dict:
    """Generate rule-based AI financial analysis narrative."""
    corp_name = company.get("corp_name", "동 기업")

    market_ctx = {
        "KOSPI":  "유가증권시장(KOSPI)에 상장된",
        "KOSDAQ": "코스닥(KOSDAQ)에 상장된",
        "KONEX":  "코넥스(KONEX)에 상장된",
    }.get(market, "상장된")

    paragraphs: list[str] = []

    # Overall verdict
    if score >= 85:
        paragraphs.append(
            f"{corp_name}의 {bsns_year}년 재무제표는 전반적으로 매우 우수한 건전성을 보입니다. "
            f"{market_ctx} 기업으로, 재무 안정성과 수익성 모두 업계 상위 수준입니다."
        )
    elif score >= 70:
        paragraphs.append(
            f"{corp_name}의 {bsns_year}년 재무 상태는 양호한 수준입니다. "
            f"{market_ctx} 기업으로, 핵심 재무지표들이 안정적으로 관리되고 있습니다."
        )
    elif score >= 55:
        paragraphs.append(
            f"{corp_name}의 {bsns_year}년 재무 상태는 보통 수준이며, 일부 지표에서 개선이 필요합니다. "
            f"{market_ctx} 기업으로, 선별적 모니터링이 권고됩니다."
        )
    else:
        paragraphs.append(
            f"{corp_name}의 {bsns_year}년 재무 상태는 취약한 것으로 분석됩니다. "
            f"{market_ctx} 기업이나, 재무 리스크가 높아 투자에 각별한 주의가 필요합니다."
        )

    # Debt structure
    dr = ratios.get("debt_equity_ratio")
    if dr is not None:
        if dr < 50:
            paragraphs.append(
                f"부채비율 {dr:.1f}%는 매우 낮은 수준으로, 무차입 또는 보수적 재무 구조를 유지하고 있습니다. "
                "금리 상승기에도 재무적 부담이 경미합니다."
            )
        elif dr < 100:
            paragraphs.append(
                f"부채비율 {dr:.1f}%는 안정적 수준으로, 재무 레버리지가 건전하게 관리되고 있습니다."
            )
        elif dr < 200:
            paragraphs.append(
                f"부채비율 {dr:.1f}%는 업계 평균 수준(100~200%)에 해당하며, 레버리지 관리가 중요합니다."
            )
        else:
            paragraphs.append(
                f"부채비율 {dr:.1f}%는 높은 편입니다. 이자 부담 및 유동성 리스크를 면밀히 점검해야 합니다."
            )

    # Profitability
    om = ratios.get("op_margin")
    nm = ratios.get("net_margin")
    if om is not None:
        if om > 20:
            paragraphs.append(
                f"영업이익률 {om:.1f}%는 매우 높은 수익성을 입증합니다. "
                "강력한 가격 결정력 또는 원가 경쟁력을 보유한 것으로 판단됩니다."
            )
        elif om > 10:
            paragraphs.append(
                f"영업이익률 {om:.1f}%는 안정적 수익성을 나타냅니다."
                + (f" 순이익률 {nm:.1f}%까지 고려할 때 전반적 수익 구조가 건전합니다." if nm and nm > 5 else "")
            )
        elif om > 0:
            paragraphs.append(
                f"영업이익률 {om:.1f}%는 낮은 편으로, 수익성 개선이 향후 핵심 과제입니다."
            )
        else:
            paragraphs.append(
                f"영업이익 적자(영업이익률 {om:.1f}%)는 핵심 영업 활동에서의 손실을 의미합니다. "
                "사업 구조 재편 또는 비용 절감이 시급합니다."
            )

    # Capital efficiency
    roe = ratios.get("roe")
    roa = ratios.get("roa")
    if roe is not None:
        if roe > 15:
            paragraphs.append(
                f"ROE {roe:.1f}%는 자본 효율성이 탁월함을 보여줍니다."
                + (f" ROA {roa:.1f}%도 양호해 자산 운용 효율이 높습니다." if roa and roa > 5 else "")
            )
        elif roe > 5:
            paragraphs.append(f"ROE {roe:.1f}%는 적정 수준의 자본 수익성을 나타냅니다.")
        else:
            paragraphs.append(
                f"ROE {roe:.1f}%는 낮은 자본 효율성을 시사합니다. "
                "수익 모델 개선 또는 자본 재구조화 여지를 검토할 필요가 있습니다."
            )

    # Growth
    rg = ratios.get("revenue_growth")
    if rg is not None:
        if rg > 20:
            paragraphs.append(f"전년 대비 매출이 {rg:.1f}% 급성장하며 강한 성장 모멘텀을 보여줍니다.")
        elif rg > 5:
            paragraphs.append(f"매출 성장률 {rg:.1f}%는 안정적 성장세를 나타냅니다.")
        elif rg >= 0:
            paragraphs.append(f"매출 성장률 {rg:.1f}%로 소폭 성장에 그쳤습니다. 성장 동력 강화가 필요합니다.")
        else:
            paragraphs.append(
                f"매출이 전년 대비 {abs(rg):.1f}% 감소했습니다. "
                "수요 약화 또는 경쟁 심화 여부를 면밀히 파악해야 합니다."
            )

    # Liquidity
    cr = ratios.get("current_ratio")
    if cr is not None:
        if cr > 200:
            paragraphs.append(f"유동비율 {cr:.0f}%는 단기 채무 상환 능력이 매우 충분함을 나타냅니다.")
        elif cr > 100:
            paragraphs.append(f"유동비율 {cr:.0f}%는 단기 유동성이 적정 수준입니다.")
        else:
            paragraphs.append(
                f"유동비율 {cr:.0f}%는 단기 유동성이 다소 취약합니다. "
                "단기 차입 의존도를 낮추는 전략이 필요합니다."
            )

    # Outlook
    if score >= 75:
        outlook       = "매수(Buy)"
        outlook_eng   = "BUY"
        outlook_color = "green"
        outlook_reason = (
            f"재무 건전성 종합점수 {score:.0f}점(등급: {grade}) — "
            "견실한 재무구조·수익성을 바탕으로 중장기 투자 매력이 높습니다."
        )
    elif score >= 55:
        outlook       = "중립(Hold)"
        outlook_eng   = "HOLD"
        outlook_color = "yellow"
        outlook_reason = (
            f"재무 건전성 종합점수 {score:.0f}점(등급: {grade}) — "
            "일부 지표의 개선 여부를 모니터링하면서 보유 또는 소규모 분할 접근이 권고됩니다."
        )
    else:
        outlook       = "관망(Sell/Wait)"
        outlook_eng   = "SELL"
        outlook_color = "red"
        outlook_reason = (
            f"재무 건전성 종합점수 {score:.0f}점(등급: {grade}) — "
            "재무 리스크가 높아 투자에 신중을 기하고 실적 개선 확인 후 재검토를 권고합니다."
        )

    return {
        "paragraphs":     paragraphs,
        "outlook":        outlook,
        "outlook_eng":    outlook_eng,
        "outlook_color":  outlook_color,
        "outlook_reason": outlook_reason,
        "disclaimer":     (
            "본 분석은 DART 공시 재무제표를 기반으로 한 자동화 AI 분석이며, "
            "투자 권유가 아닙니다. 실제 투자 판단은 전문가와 상담하시기 바랍니다."
        ),
    }


@app.post("/api/dart/financial-analysis")
def dart_financial_analysis(req: DartFinancialAnalysisRequest) -> dict:
    """Fetch DART financial statements and run AI-powered financial health analysis."""
    key = _dart_api_key()

    # ── 1. Company meta-data ─────────────────────────────────────────────────
    company = _fetch_company_detail(req.corp_code)
    if not company:
        raise HTTPException(status_code=404, detail="DART 기업 정보를 조회할 수 없습니다.")

    corp_cls = company.get("corp_cls", "")
    market   = {"Y": "KOSPI", "K": "KOSDAQ", "N": "KONEX"}.get(corp_cls, "비상장/기타")

    # ── 2. Financial statements ──────────────────────────────────────────────
    def _fetch_fin(fs_div: str) -> dict:
        url = ("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json?"
               + urllib.parse.urlencode({
                   "crtfc_key":  key,
                   "corp_code":  req.corp_code,
                   "bsns_year":  req.bsns_year,
                   "reprt_code": req.reprt_code,
                   "fs_div":     fs_div,
               }))
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception:
            return {}

    fin_data = _fetch_fin("CFS")  # 연결재무제표 우선
    is_consolidated = True
    if fin_data.get("status") != "000" or not fin_data.get("list"):
        fin_data = _fetch_fin("OFS")  # 별도재무제표 fallback
        is_consolidated = False

    if fin_data.get("status") != "000" or not fin_data.get("list"):
        raise HTTPException(
            status_code=404,
            detail=f"{req.bsns_year}년 재무제표 데이터가 없습니다: {fin_data.get('message', '알 수 없음')}"
        )

    items = fin_data.get("list", [])
    fin   = _parse_dart_amounts(items)

    # ── 3. Ratios & scoring ──────────────────────────────────────────────────
    ratios       = _calc_dart_ratios(fin)
    score, breakdown = _score_financial_health(ratios)
    grade        = (
        "A+" if score >= 90 else "A" if score >= 80 else "B+" if score >= 75
        else "B" if score >= 70 else "C" if score >= 60 else "D" if score >= 50 else "F"
    )
    verdict      = "매우 견실" if score >= 85 else "견실" if score >= 70 else "보통" if score >= 55 else "취약"

    # ── 4. Friendly financial snapshot (unit: 억원) ──────────────────────────
    B = 100_000_000  # 1억

    def to_eok(v: float) -> float | None:
        return round(v / B, 1) if v else None

    snap = {
        "revenue":              to_eok(fin["revenue"]["current"]),
        "prev_revenue":         to_eok(fin["revenue"]["prior"]),
        "op_income":            to_eok(fin["op_income"]["current"]),
        "prev_op_income":       to_eok(fin["op_income"]["prior"]),
        "net_income":           to_eok(fin["net_income"]["current"]),
        "prev_net_income":      to_eok(fin["net_income"]["prior"]),
        "total_assets":         to_eok(fin["total_assets"]["current"]),
        "total_liabilities":    to_eok(fin["total_liabilities"]["current"]),
        "total_equity":         to_eok(fin["total_equity"]["current"]),
        "current_assets":       to_eok(fin["current_assets"]["current"]),
        "current_liabilities":  to_eok(fin["current_liabilities"]["current"]),
        "retained_earnings":    to_eok(fin["retained_earnings"]["current"]),
        "is_consolidated":      is_consolidated,
        "unit":                 "억원",
    }

    analysis = _generate_dart_analysis(company, market, ratios, score, grade, req.bsns_year)

    return {
        "company":  {
            "corp_code":  req.corp_code,
            "corp_name":  company.get("corp_name", ""),
            "ceo_nm":     company.get("ceo_nm", ""),
            "adres":      company.get("adres", ""),
            "est_dt":     company.get("est_dt", ""),
            "stock_code": company.get("stock_code", ""),
            "corp_cls":   corp_cls,
            "market":     market,
        },
        "financials": snap,
        "ratios":     ratios,
        "health":     {
            "score":     score,
            "grade":     grade,
            "verdict":   verdict,
            "breakdown": breakdown,
        },
        "analysis":       analysis,
        "bsns_year":  req.bsns_year,
    }


app.include_router(tax_router)
app.include_router(rag_router)
app.include_router(llm_bench_router)
install_openapi(app)

# ─────────────────────────────────────────────────────────────────────────────

# 학습 문서에서 사용하는 Notebook 내보내기 이미지는 프런트엔드 정적 폴더 밖에
# 보관되어 있으므로, 루트 정적 파일보다 먼저 별도 경로로 제공합니다.
app.mount("/image", StaticFiles(directory=NOTEBOOK_IMAGE_DIR), name="notebook-images")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
