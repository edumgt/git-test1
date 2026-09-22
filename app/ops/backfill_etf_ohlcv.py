"""Backfill roughly one year of daily OHLCV history for every ETF in the catalog into PostgreSQL.

The ETF explorer's period-return lookup (``/market/period-return``) only reads
PostgreSQL — it never calls Yahoo Finance live — so this script needs to run at
least once (and can be re-run any time to refresh the cache). Requests for a
period reaching further back than what this script stored are handled on
demand by ``POST /market/period-return/extend`` when a learner clicks
"1년 전 가져오기" in the UI, not by this script.

Run inside the api container, which has network egress to Yahoo Finance and a
mounted copy of the ETF catalog:

    docker compose exec api python -m app.ops.backfill_etf_ohlcv
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.models.stock_price_history import StockPriceHistory

CATALOG_PATH = Path("/app/frontend/days/assets/etf-catalog.json")
YF_RANGE = "1y"
CONCURRENCY = 6
TIMEOUT = 10.0


def parse_codes() -> list[str]:
    """Return the deduplicated list of ETF codes from the catalog the frontend already ships."""
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    codes = {item["code"] for item in data["items"] if item.get("code")}
    return sorted(codes)


async def fetch_daily_bars(client: httpx.AsyncClient, ticker: str, suffix: str) -> list[dict]:
    symbol = f"{ticker}{suffix}"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={YF_RANGE}&interval=1d"
    try:
        response = await client.get(url, headers={"User-Agent": "FinanceRagLab/1.0 (educational use)"})
        response.raise_for_status()
        result = response.json()["chart"]["result"][0]
    except Exception:  # noqa: BLE001 — best-effort backfill, caller tries the other market suffix
        return []

    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    opens, highs = quote.get("open") or [], quote.get("high") or []
    lows, closes = quote.get("low") or [], quote.get("close") or []
    volumes = quote.get("volume") or []

    bars = []
    for i, ts in enumerate(timestamps):
        o = opens[i] if i < len(opens) else None
        h = highs[i] if i < len(highs) else None
        l = lows[i] if i < len(lows) else None
        c = closes[i] if i < len(closes) else None
        if o is None or h is None or l is None or c is None:
            continue
        v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0
        bars.append({
            "date": datetime.fromtimestamp(ts, tz=timezone.utc).date(),
            "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2),
            "volume": int(v),
        })
    return bars


async def fetch_with_fallback(client: httpx.AsyncClient, ticker: str) -> tuple[str, list[dict]]:
    """KRX ETFs are almost always listed on the KOSPI segment; fall back to KOSDAQ for the rare exception."""
    for market, suffix in (("KOSPI", ".KS"), ("KOSDAQ", ".KQ")):
        bars = await fetch_daily_bars(client, ticker, suffix)
        if bars:
            return market, bars
    return "KOSPI", []


def upsert_bars(ticker: str, market: str, bars: list[dict]) -> None:
    if not bars:
        return
    session = SessionLocal()
    try:
        for bar in bars:
            stmt = pg_insert(StockPriceHistory).values(ticker=ticker, market=market, **bar)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "market", "date"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            session.execute(stmt)
        session.commit()
    finally:
        session.close()


async def main() -> None:
    codes = parse_codes()
    print(f"Found {len(codes)} unique ETF codes to backfill (range={YF_RANGE}).")
    semaphore = asyncio.Semaphore(CONCURRENCY)
    done = 0
    failed: list[str] = []

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        async def worker(ticker: str) -> None:
            nonlocal done
            async with semaphore:
                market, bars = await fetch_with_fallback(client, ticker)
            upsert_bars(ticker, market, bars)
            done += 1
            if not bars:
                failed.append(ticker)
            print(f"[{done}/{len(codes)}] {ticker} ({market}): {len(bars)} bars", flush=True)

        await asyncio.gather(*(worker(code) for code in codes))

    print("Backfill complete.")
    if failed:
        print(f"{len(failed)} tickers had no data: {', '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
