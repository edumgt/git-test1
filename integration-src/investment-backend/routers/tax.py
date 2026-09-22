from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

router = APIRouter()

# ─── Tax / Accounting Simulation ─────────────────────────────────────────────

class TaxSimulationRequest(BaseModel):
    transactions: list[dict]
    entity_type: str = Field(default="individual", pattern="^(individual|corporate)$")
    tax_year: int = Field(default=2024, ge=2020, le=2030)
    business_name: str = Field(default="")
    taxpayer_id: str = Field(default="")
    vat_registered: bool = Field(default=True)
    standard_deduction: float = Field(default=0.0, ge=0.0)


_INCOME_KEYWORDS: dict[str, list[str]] = {
    "상품매출":   ["매출", "판매대금", "카드매출", "판매입금", "상품판매"],
    "서비스매출": ["서비스", "용역", "컨설팅", "자문료", "강의료"],
    "임대수입":   ["임대", "월세", "부동산"],
    "이자수입":   ["이자수입", "예금이자", "이자"],
    "기타수입":   ["환급", "지원금", "보조금", "보상금", "배당"],
}

_EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "급여":       ["급여", "월급", "임금", "상여", "인건비", "퇴직금"],
    "임차료":     ["임대료", "임차료", "월세", "관리비"],
    "접대비":     ["접대", "회식", "식대", "거래처식사"],
    "광고선전비": ["광고", "마케팅", "홍보"],
    "복리후생비": ["복리", "후생", "식권", "직원식대"],
    "통신비":     ["통신", "인터넷", "전화요금", "KT", "SKT", "LGU"],
    "수도광열비": ["전기요금", "가스요금", "수도요금", "한전", "한국전력", "가스공사"],
    "교통비":     ["교통비", "주유", "택시", "버스", "주차비", "고속도로"],
    "사무용품비": ["사무용품", "문구", "비품", "소모품", "사무기기"],
    "보험료":     ["보험료", "화재보험", "자동차보험", "단체보험"],
    "수수료비용": ["수수료", "카드수수료", "결제수수료", "플랫폼수수료"],
}


def _categorize_tx(desc: str, deposit: float, withdrawal: float) -> tuple[str, str]:
    if deposit > 0:
        for cat, kws in _INCOME_KEYWORDS.items():
            if any(k in desc for k in kws):
                return "income", cat
        return "income", "기타수입"
    for cat, kws in _EXPENSE_KEYWORDS.items():
        if any(k in desc for k in kws):
            return "expense", cat
    return "expense", "기타비용"


def _calc_income_tax(income: float) -> float:
    """Korean individual income tax brackets (2024)."""
    if income <= 0:
        return 0.0
    brackets = [
        (14_000_000,         0.06, 0),
        (50_000_000,         0.15, 1_260_000),
        (88_000_000,         0.24, 5_220_000),
        (150_000_000,        0.35, 14_900_000),
        (300_000_000,        0.38, 19_400_000),
        (500_000_000,        0.40, 25_400_000),
        (1_000_000_000,      0.42, 35_400_000),
        (float("inf"),       0.45, 65_400_000),
    ]
    for limit, rate, deduction in brackets:
        if income <= limit:
            return max(0.0, income * rate - deduction)
    return max(0.0, income * 0.45 - 65_400_000)


def _calc_corporate_tax(income: float) -> float:
    """Korean corporate tax brackets (2024)."""
    if income <= 0:
        return 0.0
    brackets = [
        (200_000_000,         0.09, 0),
        (20_000_000_000,      0.19, 20_000_000),
        (300_000_000_000,     0.21, 420_000_000),
        (float("inf"),        0.24, 9_420_000_000),
    ]
    for limit, rate, deduction in brackets:
        if income <= limit:
            return max(0.0, income * rate - deduction)
    return max(0.0, income * 0.24 - 9_420_000_000)


def _parse_df_to_transactions(df: "import pandas; pandas.DataFrame") -> list[dict]:
    import pandas as pd

    raw_cols = list(df.columns)
    col_map: dict[str, str | None] = {
        "date": None, "description": None,
        "withdrawal": None, "deposit": None, "balance": None,
    }

    DATE_KW   = ["날짜", "일자", "거래일", "일시", "거래시간", "date"]
    DESC_KW   = ["내용", "적요", "거래내용", "거래명", "메모", "description"]
    OUT_KW    = ["출금", "출금액", "지출", "출금금액", "debit", "withdrawal"]
    IN_KW     = ["입금", "입금액", "수입", "입금금액", "credit", "deposit"]
    BAL_KW    = ["잔액", "잔금", "balance"]

    for c in raw_cols:
        cs = str(c).strip()
        if col_map["date"]        is None and any(k in cs for k in DATE_KW):   col_map["date"]        = c
        if col_map["description"] is None and any(k in cs for k in DESC_KW):   col_map["description"] = c
        if col_map["withdrawal"]  is None and any(k in cs for k in OUT_KW):    col_map["withdrawal"]  = c
        if col_map["deposit"]     is None and any(k in cs for k in IN_KW):     col_map["deposit"]     = c
        if col_map["balance"]     is None and any(k in cs for k in BAL_KW):    col_map["balance"]     = c

    def _num(val: object) -> float:
        try:
            s = str(val).replace(",", "").strip()
            return float(s) if s and s.lower() not in ("nan", "") else 0.0
        except (ValueError, TypeError):
            return 0.0

    txs: list[dict] = []
    for _, row in df.iterrows():
        date_val = str(row[col_map["date"]]).strip()   if col_map["date"]        else ""
        desc_val = str(row[col_map["description"]]).strip() if col_map["description"] else ""
        out_val  = _num(row[col_map["withdrawal"]])    if col_map["withdrawal"]   else 0.0
        in_val   = _num(row[col_map["deposit"]])       if col_map["deposit"]      else 0.0
        bal_val  = _num(row[col_map["balance"]])       if col_map["balance"]      else 0.0

        if not date_val or date_val.lower() == "nan":
            continue

        txs.append({
            "date":        date_val,
            "description": desc_val,
            "withdrawal":  out_val,
            "deposit":     in_val,
            "balance":     bal_val,
        })
    return txs


@router.post("/api/tax/upload")
async def tax_upload(file: UploadFile = File(...)) -> dict:
    """Parse a bank-statement CSV or Excel file and return structured transactions."""
    import pandas as pd

    filename = (file.filename or "").lower()
    content  = await file.read()

    try:
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            df = None
            for enc in ("utf-8-sig", "utf-8", "euc-kr", "cp949"):
                try:
                    text = content.decode(enc)
                    df   = pd.read_csv(io.StringIO(text), dtype=str)
                    break
                except (UnicodeDecodeError, Exception):
                    continue
            if df is None:
                raise HTTPException(status_code=400, detail="파일 인코딩을 감지할 수 없습니다.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"파일 파싱 오류: {exc}") from exc

    df.dropna(how="all", inplace=True)
    txs = _parse_df_to_transactions(df)

    if not txs:
        raise HTTPException(status_code=400, detail="유효한 거래 데이터를 찾을 수 없습니다. 컬럼명을 확인하세요.")

    return {
        "status":   "ok",
        "rows":     len(txs),
        "columns":  list(df.columns),
        "transactions": txs[:500],  # max 500 rows for safety
    }


@router.get("/api/tax/sample")
def tax_sample() -> dict:
    """Return synthetic sample transaction data for demo purposes."""
    import datetime, math, random

    rng = random.Random(42)
    base_date = datetime.date(2024, 1, 2)
    balance   = 50_000_000.0
    txs: list[dict] = []

    INCOME_TEMPLATES = [
        ("상품 판매 대금 입금 (거래처A)",   3_000_000, 8_000_000, "상품매출"),
        ("컨설팅 용역료 입금",               2_000_000, 5_000_000, "서비스매출"),
        ("카드매출 정산",                    1_000_000, 4_000_000, "상품매출"),
        ("임대료 수입",                      1_500_000, 1_500_000, "임대수입"),
        ("이자수입",                          50_000,   200_000, "이자수입"),
    ]
    EXPENSE_TEMPLATES = [
        ("급여 지급",                        3_500_000, 6_000_000, "급여"),
        ("사무실 임대료 납부",               1_200_000, 1_200_000, "임차료"),
        ("광고비 지출",                       300_000,  800_000, "광고선전비"),
        ("사무용품 구매",                      50_000,  200_000, "사무용품비"),
        ("KT 통신비",                          80_000,  150_000, "통신비"),
        ("전기요금 납부 (한전)",              120_000,  300_000, "수도광열비"),
        ("교통비 (주유·택시)",               100_000,  400_000, "교통비"),
        ("거래처 회식 (접대비)",             300_000,  500_000, "접대비"),
        ("카드수수료",                         30_000,  100_000, "수수료비용"),
        ("복리후생비",                        200_000,  500_000, "복리후생비"),
        ("단체보험료",                        150_000,  250_000, "보험료"),
    ]

    for day_offset in range(0, 365, rng.randint(1, 4)):
        date = base_date + datetime.timedelta(days=day_offset)
        if date >= datetime.date(2025, 1, 1):
            break

        # 50% income, 50% expense
        if rng.random() < 0.45:
            tmpl = rng.choice(INCOME_TEMPLATES)
            amt  = rng.randint(int(tmpl[1] / 1000), int(tmpl[2] / 1000)) * 1000
            balance += amt
            txs.append({
                "date":        date.strftime("%Y-%m-%d"),
                "description": tmpl[0],
                "deposit":     float(amt),
                "withdrawal":  0.0,
                "balance":     balance,
            })
        else:
            tmpl = rng.choice(EXPENSE_TEMPLATES)
            amt  = rng.randint(int(tmpl[1] / 1000), int(tmpl[2] / 1000)) * 1000
            balance -= amt
            txs.append({
                "date":        date.strftime("%Y-%m-%d"),
                "description": tmpl[0],
                "deposit":     0.0,
                "withdrawal":  float(amt),
                "balance":     balance,
            })

    return {"status": "ok", "rows": len(txs), "transactions": txs}


@router.post("/api/tax/simulate")
def tax_simulate(req: TaxSimulationRequest) -> dict:
    """Run full Korean tax simulation on the provided transaction list."""
    import datetime

    categorized: list[dict] = []
    income_by_cat: dict[str, float] = {}
    expense_by_cat: dict[str, float] = {}
    monthly: dict[str, dict[str, float]] = {}

    for tx in req.transactions:
        deposit    = float(tx.get("deposit", 0) or 0)
        withdrawal = float(tx.get("withdrawal", 0) or 0)
        desc       = str(tx.get("description", ""))
        date_str   = str(tx.get("date", ""))
        balance    = float(tx.get("balance", 0) or 0)

        tx_type, category = _categorize_tx(desc, deposit, withdrawal)
        amount = deposit if tx_type == "income" else withdrawal

        categorized.append({
            "date":        date_str,
            "description": desc,
            "deposit":     deposit,
            "withdrawal":  withdrawal,
            "balance":     balance,
            "type":        tx_type,
            "category":    category,
            "amount":      amount,
        })

        month = date_str[:7]
        if month not in monthly:
            monthly[month] = {"income": 0.0, "expense": 0.0}
        monthly[month][tx_type] += amount

        if tx_type == "income":
            income_by_cat[category]  = income_by_cat.get(category, 0.0)  + amount
        else:
            expense_by_cat[category] = expense_by_cat.get(category, 0.0) + amount

    total_income  = sum(income_by_cat.values())
    total_expense = sum(expense_by_cat.values())
    net_income    = total_income - total_expense
    taxable_income = max(0.0, net_income - req.standard_deduction)

    # VAT (부가가치세) — 일반과세자 기준 10%
    vat_output  = total_income  * 0.10 if req.vat_registered else 0.0
    vat_input   = total_expense * 0.10 if req.vat_registered else 0.0
    vat_payable = max(0.0, vat_output - vat_input)

    # 소득세 또는 법인세
    if req.entity_type == "individual":
        base_tax = _calc_income_tax(taxable_income)
    else:
        base_tax = _calc_corporate_tax(taxable_income)

    local_tax  = base_tax * 0.10   # 지방소득세
    total_tax  = base_tax + local_tax
    effective_rate = (base_tax / taxable_income * 100) if taxable_income > 0 else 0.0

    # Income tax bracket breakdown (for audit report)
    bracket_info: list[dict] = []
    if req.entity_type == "individual":
        BRACKETS = [
            (14_000_000,   "6%",  14_000_000),
            (50_000_000,   "15%", 36_000_000),
            (88_000_000,   "24%", 38_000_000),
            (150_000_000,  "35%", 62_000_000),
            (300_000_000,  "38%", 150_000_000),
            (500_000_000,  "40%", 200_000_000),
            (1_000_000_000,"42%", 500_000_000),
            (float("inf"), "45%", 0),
        ]
        prev = 0.0
        for limit, rate_label, width in BRACKETS:
            if taxable_income > prev:
                in_bracket = min(taxable_income, limit if limit != float("inf") else taxable_income) - prev
                bracket_info.append({
                    "range": f"{int(prev):,}원 초과 ~ {int(limit):,}원 이하" if limit != float("inf") else f"{int(prev):,}원 초과",
                    "rate":  rate_label,
                    "amount": in_bracket,
                })
                prev = limit
            else:
                break

    monthly_sorted = dict(sorted(monthly.items()))

    return {
        "entity_type":    req.entity_type,
        "tax_year":       req.tax_year,
        "business_name":  req.business_name,
        "taxpayer_id":    req.taxpayer_id,
        "summary": {
            "total_income":    total_income,
            "total_expense":   total_expense,
            "net_income":      net_income,
            "taxable_income":  taxable_income,
            "standard_deduction": req.standard_deduction,
        },
        "income_by_category":  income_by_cat,
        "expense_by_category": expense_by_cat,
        "monthly":             monthly_sorted,
        "vat": {
            "output_tax":  vat_output,
            "input_tax":   vat_input,
            "payable":     vat_payable,
            "registered":  req.vat_registered,
        },
        "income_tax": {
            "amount":         base_tax,
            "local_tax":      local_tax,
            "total":          total_tax,
            "effective_rate": effective_rate,
            "brackets":       bracket_info,
        },
        "transactions": categorized,
    }


