"""Educational portfolio Monte Carlo simulation."""

from __future__ import annotations

import math
import random

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/simulations", tags=["simulations"])


class PortfolioSimulationRequest(BaseModel):
    profile: str = Field(default="balanced", pattern=r"^(stable|balanced|growth)$")
    initial_amount: int = Field(default=10_000_000, ge=0, le=1_000_000_000)
    monthly_amount: int = Field(default=500_000, ge=0, le=100_000_000)
    years: int = Field(default=10, ge=1, le=30)


_PROFILES = {
    "stable": {"label": "안정 중심", "return": 0.045, "volatility": 0.07},
    "balanced": {"label": "균형 중심", "return": 0.065, "volatility": 0.12},
    "growth": {"label": "성장 중심", "return": 0.085, "volatility": 0.18},
}


def _percentile(values: list[float], percentile: float) -> int:
    values.sort()
    index = round((len(values) - 1) * percentile)
    return int(round(values[index]))


@router.post("/portfolio")
def simulate_portfolio(payload: PortfolioSimulationRequest) -> dict[str, object]:
    """Project illustrative 10th/50th/90th percentile portfolio paths."""
    config = _PROFILES[payload.profile]
    paths = 5_000
    rng = random.Random(20260806)
    balances = [float(payload.initial_amount)] * paths
    monthly_return = (1 + config["return"]) ** (1 / 12) - 1
    monthly_volatility = config["volatility"] / math.sqrt(12)
    points = [{"year": 0, "cautious": payload.initial_amount, "middle": payload.initial_amount, "positive": payload.initial_amount}]

    for month in range(1, payload.years * 12 + 1):
        balances = [max(0, (balance + payload.monthly_amount) * (1 + rng.gauss(monthly_return, monthly_volatility))) for balance in balances]
        if month % 12 == 0:
            points.append({
                "year": month // 12,
                "cautious": _percentile(balances.copy(), 0.10),
                "middle": _percentile(balances.copy(), 0.50),
                "positive": _percentile(balances.copy(), 0.90),
            })

    return {
        "profile_label": config["label"],
        "years": payload.years,
        "total_paid": payload.initial_amount + payload.monthly_amount * payload.years * 12,
        "points": points,
        "summary": {key: points[-1][key] for key in ("cautious", "middle", "positive")},
        "explanation": "같은 구성이라도 시장 흐름에 따라 결과가 달라질 수 있음을 보여주는 학습용 가상 시나리오입니다.",
    }
