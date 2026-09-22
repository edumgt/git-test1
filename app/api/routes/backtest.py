from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas.chat import BacktestRequest, BacktestResponse
from app.services.lean_backtest_service import LeanBacktestError, LeanBacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])
service = LeanBacktestService()

REPORTS_DIR = Path(__file__).resolve().parents[3] / "data" / "lean-reports"

LEAN_RUNS: dict[str, dict[str, Any]] = {
    "hyundai": {
        "label": "현대자동차",
        "code": "005380",
        "summary_file": "HyundaiTrendBacktest-summary.json",
        "strategy_name": "이동평균 추세추종 (20일선 vs 60일선)",
        "strategy_note": "20일 이동평균이 60일 이동평균 위에 있으면 매수, 아래로 내려오면 전량 매도하는 추세추종 전략입니다.",
    },
    "samsung": {
        "label": "삼성전자",
        "code": "005930",
        "summary_file": "SamsungBuyAndHold-summary.json",
        "strategy_name": "매수 후 보유 (Buy and Hold)",
        "strategy_note": "동작 확인용 스모크 테스트입니다. 첫 거래일에 1주를 매수한 뒤 추가 매매 없이 그대로 보유합니다.",
    },
    "samsung-em": {
        "label": "삼성전기",
        "code": "009150",
        "summary_file": "SamsungEMBuyAndHold-summary.json",
        "strategy_name": "매수 후 보유 (Buy and Hold)",
        "strategy_note": "동작 확인용 스모크 테스트입니다. 첫 거래일에 1주를 매수한 뒤 추가 매매 없이 그대로 보유합니다.",
    },
}


def _load_summary(filename: str) -> dict[str, Any]:
    path = REPORTS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"LEAN 결과 파일을 찾을 수 없습니다: {filename}")
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _equity_curve(data: dict[str, Any]) -> list[dict[str, float]]:
    try:
        values = data["charts"]["Strategy Equity"]["series"]["Equity"]["values"]
    except (KeyError, TypeError):
        return []
    return [
        {"time": point[0], "equity": point[4]}
        for point in values
        if isinstance(point, list) and len(point) >= 5
    ]


@router.get("/reports")
def list_lean_reports() -> dict[str, Any]:
    return {
        "items": [
            {"symbol": symbol, "label": meta["label"], "code": meta["code"]}
            for symbol, meta in LEAN_RUNS.items()
        ]
    }


@router.get("/reports/{symbol}")
def get_lean_report(symbol: str) -> dict[str, Any]:
    meta = LEAN_RUNS.get(symbol)
    if not meta:
        raise HTTPException(status_code=404, detail="지원하지 않는 종목입니다. hyundai, samsung, samsung-em 중 하나를 사용하세요.")

    data = _load_summary(meta["summary_file"])
    config = data.get("algorithmConfiguration", {})
    state = data.get("state", {})

    return {
        "symbol": symbol,
        "label": meta["label"],
        "code": meta["code"],
        "strategy_name": meta["strategy_name"],
        "strategy_note": meta["strategy_note"],
        "status": state.get("Status"),
        "order_count": state.get("OrderCount"),
        "start_date": config.get("startDate"),
        "end_date": config.get("endDate"),
        "statistics": data.get("statistics", {}),
        "runtime_statistics": data.get("runtimeStatistics", {}),
        "equity_curve": _equity_curve(data),
    }


@router.post("/run", response_model=BacktestResponse)
def run_backtest(payload: BacktestRequest):
    try:
        return service.run(**payload.model_dump())
    except LeanBacktestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="백테스트 실행 중 외부 데이터 또는 LEAN 실행 오류가 발생했습니다.") from exc
