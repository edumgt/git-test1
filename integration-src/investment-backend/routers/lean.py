from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[3]

LEAN_RUNS: dict[str, dict[str, Any]] = {
    "samsung": {
        "label": "삼성전자",
        "code": "005930",
        "summary_path": ROOT_DIR / "lean-results" / "SamsungBuyAndHold-summary.json",
        "strategy_name": "매수 후 보유(Buy & Hold)",
        "strategy_note": "동작 확인용 스모크 테스트입니다. 첫 거래일에 1주를 매수한 뒤 추가 매매 없이 그대로 보유합니다.",
    },
    "hyundai": {
        "label": "현대자동차",
        "code": "005380",
        "summary_path": ROOT_DIR / "hyundai-results" / "HyundaiTrendBacktest-summary.json",
        "strategy_name": "이동평균 추세추종 (20일선 vs 60일선)",
        "strategy_note": "20일 이동평균이 60일 이동평균 위에 있으면 매수, 아래로 내려오면 전량 매도하는 추세추종 전략입니다.",
    },
    "samsung-em": {
        "label": "삼성전기",
        "code": "009150",
        "summary_path": ROOT_DIR / "samsung-em-results" / "SamsungEMBuyAndHold-summary.json",
        "strategy_name": "매수 후 보유(Buy & Hold)",
        "strategy_note": "동작 확인용 스모크 테스트입니다. 첫 거래일에 1주를 매수한 뒤 추가 매매 없이 그대로 보유합니다.",
    },
}


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"LEAN 결과 파일을 찾을 수 없습니다: {path.name}")
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


@router.get("/api/quant/lean")
def list_lean_backtests() -> dict[str, Any]:
    return {
        "items": [
            {"symbol": symbol, "label": meta["label"], "code": meta["code"]}
            for symbol, meta in LEAN_RUNS.items()
        ]
    }


@router.get("/api/quant/lean/{symbol}")
def get_lean_backtest(symbol: str) -> dict[str, Any]:
    meta = LEAN_RUNS.get(symbol)
    if not meta:
        raise HTTPException(status_code=404, detail="지원하지 않는 종목입니다. hyundai, samsung, samsung-em 중 하나를 사용하세요.")

    data = _load_summary(meta["summary_path"])
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
