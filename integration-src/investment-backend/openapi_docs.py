"""OpenAPI metadata used by the interactive Swagger UI.

Keeping this separately from the route handlers makes the API guide readable
without changing the response payloads consumed by the frontend.
"""

from __future__ import annotations

from fastapi.openapi.utils import get_openapi


TAG_DESCRIPTIONS = [
    {"name": "시스템", "description": "서비스 상태, 접속 현황 및 학습 문서 조회 API입니다."},
    {"name": "DART·기업", "description": "OpenDART 공시와 시장 데이터로 기업을 찾고 재무를 분석합니다. DART 키가 필요한 API는 키가 없으면 503을 반환합니다."},
    {"name": "산업·시장", "description": "산업 경쟁 구조와 실시간 시장·거시 지표를 분석하거나 시뮬레이션합니다."},
    {"name": "퀀트", "description": "교육 목적의 백테스트, 포트폴리오, 리스크 및 분석 파이프라인 API입니다. 투자 권유나 실제 주문 기능은 제공하지 않습니다."},
    {"name": "머신러닝", "description": "합성 데이터 기반의 ML/DL·NLP 실습 결과와 시각화 데이터를 반환합니다."},
    {"name": "퀴즈", "description": "MongoDB에 저장된 학습 퀴즈를 조회·수정·초기화합니다."},
    {"name": "세무", "description": "거래내역 파일을 읽고 교육용 세금·회계 시뮬레이션을 수행합니다. 실제 신고 금액으로 사용하면 안 됩니다."},
    {"name": "RAG", "description": "Qdrant에 색인된 학습 문서의 유사도 검색 API입니다. 기본 답변은 검색 문서만 정리하며, 선택적으로 외부 AI가 같은 검색 원문만 문장 다듬기에 사용합니다."},
    {"name": "Amazon Lex", "description": "우측 AI 투자 도우미가 Amazon Lex V2 봇과 대화하는 API입니다. AWS 자격 증명은 서버에만 둡니다."},
    {"name": "파일", "description": "서버가 생성한 실습 산출물을 내려받습니다."},
]

# Swagger UI는 외부 개발자용 전체 서버 기능 목록이 아니라, 이 웹앱 화면이
# 실제 호출하는 API만 안내합니다. 운영·관리 스크립트용 또는 아직 화면에 연결되지
# 않은 엔드포인트는 서버에 유지하되 OpenAPI 문서에서는 노출하지 않습니다.
FRONTEND_API_PATHS = frozenset({
    "/api/health",
    "/api/system/resources",
    "/api/visitors/heartbeat",
    "/api/learn/doc/{doc_id}",
    "/api/lex/status",
    "/api/lex/chat",
    "/api/dart/company-search",
    "/api/dart/group-network",
    "/api/dart/company-list",
    "/api/dart/financial-analysis",
    "/api/finance/company-financials",
    "/api/industry/porter",
    "/api/industry/sector",
    "/api/industry/peer",
    "/api/industry/lifecycle",
    "/api/market/snapshot",
    "/api/market/volume-cloud",
    "/api/market/sector-cloud",
    "/api/market/top-gainers",
    "/api/market/top-sobujang",
    "/api/macro/realtime",
    "/api/macro/kospi-ex",
    "/api/macro/kospi-ex/meta",
    "/api/macro/simulation",
    "/api/home/market-candle",
    "/api/quant/backtest",
    "/api/quant/portfolio",
    "/api/quant/risk",
    "/api/quant/pipeline",
    "/api/ml/cross-validation",
    "/api/ml/decision-boundary",
    "/api/ml/random-forest",
    "/api/cv/circle-animation",
    "/api/ml/kmeans",
    "/api/ml/svm",
    "/api/ml/mlp",
    "/api/ml/linear-regression",
    "/api/nlp/text-classify",
    "/api/genai/text-to-image",
    "/api/dl/cnn-timeseries",
    "/api/dl/lstm-predictor",
    "/api/dl/transformer-timeseries",
    "/files/{file_name}",
    "/api/quiz/day/{day}",
    "/api/quiz/questions/{question_id}",
    "/api/tax/upload",
    "/api/tax/sample",
    "/api/tax/simulate",
})


# (tag, Korean title, implementation/response contract).  Request models already
# expose type, defaults and validation limits; these notes explain why to call
# each endpoint and how to interpret its returned data.
OPERATION_DOCS: dict[str, tuple[str, str, str]] = {
    "/api/health": ("시스템", "서비스 상태 확인", "서버가 요청을 처리할 수 있는지 확인합니다. `status: ok`면 정상입니다."),
    "/api/system/resources": ("시스템", "서버 리소스 사용량", "서버의 CPU, 메모리, 루트 디스크 사용률과 바이트 단위 사용량을 반환합니다. 운영 상태를 살피는 용도이며 컨테이너·호스트 환경에 따라 관측 범위가 달라질 수 있습니다."),
    "/api/visitors/heartbeat": ("시스템", "활성 브라우저 하트비트", "익명 브라우저 식별자를 갱신하고 최근 90초 안에 신호를 보낸 활성 브라우저 수를 반환합니다. 분석용 방문 이력을 저장하지 않습니다."),
    "/api/learn/doc/{doc_id}": ("시스템", "학습 문서 본문 조회", "문서 ID(파일 확장자 제외)에 해당하는 Markdown 원문을 반환합니다. 지원하지 않는 ID는 404입니다."),
    "/api/lex/status": ("Amazon Lex", "Lex 연결 설정 상태", "민감한 AWS 자격 증명을 노출하지 않고, Amazon Lex 봇 연결에 필요한 공개 설정의 준비 여부만 반환합니다."),
    "/api/lex/chat": ("Amazon Lex", "AI 투자 도우미 대화", "브라우저 메시지를 서버 경유로 Amazon Lex V2에 전달합니다. 세션 ID를 유지하면 Lex의 대화 상태를 이어갈 수 있습니다."),
    "/api/dart/company-search": ("DART·기업", "DART 기업명 검색", "회사명 일부를 기준으로 DART 기업코드 목록을 검색합니다. 결과의 `corp_code`는 재무분석 요청에 사용합니다."),
    "/api/dart/group-network": ("DART·기업", "그룹사 관계망 조회", "그룹명으로 DART 기업을 찾아 관계망 표현에 사용할 기업 목록과 연결 정보를 반환합니다."),
    "/api/dart/company-list": ("DART·기업", "지역·고용조건 기업 검색", "본사 지역, 임직원 수 범위, 사업연도 조건으로 DART 기업을 조회합니다. 외부 공시 데이터 상태에 따라 일부 정보가 비어 있을 수 있습니다."),
    "/api/dart/financial-analysis": ("DART·기업", "DART 재무제표 분석", "DART 고유번호와 보고서 코드를 사용해 핵심 재무 항목, 비율 및 차트를 계산합니다. `corp_code`는 8자리여야 합니다."),
    "/api/finance/company-financials": ("DART·기업", "상장사 재무정보 조회", "Yahoo Finance 기준 종목의 손익·재무상태·현금흐름 데이터를 연간 또는 분기별로 정리합니다. 지원되지 않는 티커 또는 공급자 오류는 502/404가 될 수 있습니다."),
    "/api/industry/porter": ("산업·시장", "포터의 5가지 경쟁요인 분석", "산업명과 5개 경쟁요인 점수(0~10)를 받아 레이더 차트와 해석에 사용할 데이터를 반환합니다. 점수는 서버에서 0~10 범위로 보정됩니다."),
    "/api/industry/sector": ("산업·시장", "섹터 수익률 비교", "ETF/지수 티커와 기간을 기준으로 수익률 비교 데이터를 조회하고 시각화 이미지를 반환합니다."),
    "/api/industry/peer": ("산업·시장", "동종기업 비교", "표시명과 티커의 매핑을 받아 경쟁사 가격·수익률 비교 결과를 반환합니다."),
    "/api/industry/lifecycle": ("산업·시장", "산업 수명주기 분석", "산업명과 도입기·성장기·성숙기·쇠퇴기 중 하나를 입력하면 특성, 전략과 차트를 반환합니다."),
    "/api/market/snapshot": ("산업·시장", "시장 스냅샷", "지정한 지수·환율 티커의 최신 가격, 변동률과 조회 시각을 반환합니다. 시장이 닫혀 있으면 마지막 거래 기준일 수 있습니다."),
    "/api/market/volume-cloud": ("산업·시장", "거래량 클라우드", "미국 또는 한국 대표 종목의 최근 거래량, 20거래일 평균 대비 거래량, 가격과 전일 대비를 반환합니다. 시장마다 거래량 단위가 달라 국가별로 분리해 해석해야 합니다."),
    "/api/market/sector-cloud": ("산업·시장", "섹터별 클라우드", "KOSPI 또는 KOSDAQ 대표 종목 표본을 섹터별로 묶어 거래대금 합계와 거래대금 가중 평균 등락률을 반환합니다. 거래소 전체 업종지수 집계가 아닙니다."),
    "/api/market/top-gainers": ("산업·시장", "금일 상승종목", "KOSPI 대표 종목 표본을 전일 종가 대비 등락률 순으로 반환합니다. 전체 시장 스크리너가 아닙니다."),
    "/api/market/top-sobujang": ("산업·시장", "금일 소부장 종목", "국내 반도체 소재·부품·장비 대표 종목 표본을 전일 종가 대비 등락률 순으로 반환합니다. 전체 소부장 시장을 포괄하지 않습니다."),
    "/api/macro/realtime": ("산업·시장", "거시지표 시계열 조회", "금리·원유·주가지수 등 티커의 지정 기간 시계열과 비교 차트를 반환합니다. 외부 시세 공급자 지연이 반영될 수 있습니다."),
    "/api/macro/kospi-ex": ("산업·시장", "제외 종목 KOSPI 분석", "제외할 종목·섹터와 기간을 입력하면 남은 구성종목 기반 KOSPI 비교 분석 결과를 반환합니다."),
    "/api/macro/kospi-ex/meta": ("산업·시장", "KOSPI 제외 분석 메타데이터", "제외 분석 UI에 필요한 사용 가능 섹터와 구성종목·가중치를 반환합니다."),
    "/api/macro/simulation": ("산업·시장", "거시경제 GBM 시뮬레이션", "난수 시드와 거래일 수를 바탕으로 교육용 거시 시계열을 생성합니다. 같은 시드를 사용하면 같은 결과를 재현할 수 있습니다."),
    "/api/home/market-candle": ("산업·시장", "홈 화면 시장 캔들", "홈 대시보드에 표시할 대표 시장의 OHLCV 캔들 데이터를 반환합니다."),
    "/api/home/kospi-candle": ("산업·시장", "KOSPI 캔들", "KOSPI 지수의 홈 화면용 OHLCV 캔들 데이터를 반환합니다."),
    "/api/home/box-range": ("산업·시장", "가격 박스권 데이터", "홈 화면 기술적 분석 예시에 사용할 가격 범위·OHLCV·현재 위치 데이터를 반환합니다. 실제 매매 신호가 아닙니다."),
    "/api/quant/backtest": ("퀀트", "이동평균 전략 백테스트", "합성 가격 시계열에서 단기·장기 이동평균 교차 전략을 실행합니다. 수익률, Sharpe, MDD, 거래 수와 base64 차트를 반환하며 실투자 성과를 보장하지 않습니다."),
    "/api/quant/portfolio": ("퀀트", "몬테카를로 포트폴리오", "무작위 비중 포트폴리오를 생성해 수익률·변동성·Sharpe 기준의 효율적 조합과 차트를 반환합니다."),
    "/api/quant/financial-knowledge": ("퀀트", "금융지식 포트폴리오 실습", "학습 초점에 맞춘 자산배분·상품 설명과 몬테카를로 결과를 반환합니다."),
    "/api/quant/risk": ("퀀트", "포트폴리오 리스크 시뮬레이션", "신뢰수준과 시나리오 수를 사용해 VaR·CVaR 등 손실 위험을 교육용 난수 시뮬레이션으로 계산합니다."),
    "/api/quant/pipeline": ("퀀트", "퀀트 분석 파이프라인", "티커와 이동평균 기간을 받아 가격 조회부터 신호·성과 계산까지의 간단한 분석 흐름을 실행합니다."),
    "/api/ml/cross-validation": ("머신러닝", "교차검증 실습", "합성 분류 데이터를 만들고 로지스틱 회귀의 폴드별 정확도, 평균과 표준편차를 반환합니다."),
    "/api/ml/decision-boundary": ("머신러닝", "결정경계 시각화", "고정 합성 데이터로 학습한 분류기의 결정경계를 PNG base64 문자열로 반환합니다."),
    "/api/ml/random-forest": ("머신러닝", "랜덤포레스트 분류 실습", "예제 이탈 데이터로 랜덤포레스트를 학습하고 정확도와 클래스별 정밀도·재현율 보고서를 반환합니다."),
    "/api/cv/circle-animation": ("머신러닝", "OpenCV 원 애니메이션 생성", "해상도와 FPS로 원 애니메이션 MP4를 생성합니다. 응답의 `video_url`을 `GET /files/{file_name}`으로 요청해 내려받을 수 있습니다."),
    "/api/ml/kmeans": ("머신러닝", "K-Means 군집화 실습", "합성 군집 데이터의 레이블, 중심점, 실루엣 점수와 엘보 데이터를 반환하고 시각화 이미지를 포함합니다."),
    "/api/ml/svm": ("머신러닝", "SVM 분류 실습", "커널과 규제계수 C로 SVM을 학습해 정확도·예측 결과·결정경계 이미지를 반환합니다."),
    "/api/ml/mlp": ("머신러닝", "다층퍼셉트론 실습", "은닉층 구성과 반복 횟수로 MLP 분류기를 학습해 손실 곡선 및 평가 지표를 반환합니다."),
    "/api/ml/linear-regression": ("머신러닝", "다항 선형회귀 실습", "다항 차수, 표본 수와 노이즈로 합성 데이터를 만들고 회귀 계수·오차·시각화 결과를 반환합니다."),
    "/api/nlp/text-classify": ("머신러닝", "텍스트 분류 실습", "입력 문장에 TF-IDF 기반 예제 분류기를 적용하여 예측 레이블과 확률을 반환합니다."),
    "/api/genai/text-to-image": ("머신러닝", "텍스트-이미지 생성", "프롬프트와 이미지 크기를 받아 Diffusers 모델로 이미지를 생성합니다. 모델 다운로드·GPU 상태에 따라 오래 걸리거나 503/500이 발생할 수 있습니다."),
    "/api/dl/cnn-timeseries": ("머신러닝", "CNN 시계열 예측 실습", "입력 창, 표본 수와 에폭으로 합성 시계열 CNN을 학습하고 평가 지표·예측 차트를 반환합니다."),
    "/api/dl/lstm-predictor": ("머신러닝", "LSTM 시계열 예측 실습", "LSTM 은닉 유닛과 시퀀스 길이로 합성 시계열 예측기를 학습해 예측 결과를 반환합니다."),
    "/api/dl/transformer-timeseries": ("머신러닝", "Transformer 시계열 예측 실습", "인코더 길이·예측 구간·d_model·에폭을 사용해 Transformer 시계열 실습 결과를 반환합니다."),
    "/files/{file_name}": ("파일", "생성 파일 다운로드", "서버가 `app/generated`에 생성한 파일을 제공합니다. 허용되지 않거나 존재하지 않는 파일명은 404입니다."),
    "/api/quiz/day/{day}": ("퀴즈", "일차별 퀴즈 조회", "학습 일차의 문항을 문항 번호 순으로 반환합니다. 데이터가 없으면 빈 배열을 반환합니다."),
    "/api/quiz/questions/{question_id}": ("퀴즈", "퀴즈 문항 수정", "MongoDB ObjectId 형식의 문항을 수정합니다. 빈 보기는 허용하지 않으며 잘못된 ID는 400, 없는 문항은 404입니다."),
    "/api/quiz/days": ("퀴즈", "퀴즈 일차 목록", "문항이 존재하는 일차와 각 일차의 문항 수를 반환합니다."),
    "/api/quiz/seed": ("퀴즈", "퀴즈 시드 재적용", "기본 퀴즈 데이터를 강제로 최신 시드 내용으로 동기화하고 변경·삭제·총 문항 수를 반환합니다."),
    "/api/quiz/seed-script": ("퀴즈", "MongoDB 퀴즈 시드 스크립트", "현재 기본 퀴즈 데이터를 MongoDB 셸에서 실행 가능한 `insertMany` 스크립트 문자열로 반환합니다."),
    "/api/tax/upload": ("세무", "거래내역 파일 업로드", "CSV 또는 Excel 은행거래 파일을 multipart/form-data `file`로 업로드하면 컬럼을 추정해 표준 거래내역으로 변환합니다. 최대 500건을 반환합니다."),
    "/api/tax/sample": ("세무", "세무 시뮬레이션 예제 거래", "세무 시뮬레이션을 시험할 수 있도록 재현 가능한 가상 거래내역을 반환합니다."),
    "/api/tax/simulate": ("세무", "세금·회계 시뮬레이션", "거래내역을 수입·비용으로 분류하고 소득세/법인세, 부가세 및 월별 집계를 계산합니다. 교육용 단순화 계산이므로 실제 세무 신고에 사용하면 안 됩니다."),
    "/api/rag/search": ("RAG", "학습 문서 유사도 검색", "질문을 의존성 없는 해시 임베딩으로 변환해 Qdrant에서 관련 청크를 찾습니다. `score_threshold`를 높이면 낮은 유사도 결과를 제외합니다."),
    "/api/rag/ask": ("RAG", "관련 학습 문서 찾기", "기본적으로 검색 문서 청크만 정리해 답변합니다. `provider=openai_compatible`을 선택하면 설정된 외부 AI가 같은 원문만 문장 다듬기에 사용합니다. Qdrant가 준비되지 않으면 503입니다."),
    "/api/rag/status": ("RAG", "RAG 저장소 상태", "Qdrant 연결 가능 여부, URL, 컬렉션, 포인트 수와 벡터 차원을 반환합니다."),
}


def install_openapi(app) -> None:
    """Install a cached OpenAPI factory after all routers have been registered."""
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title="Investment Analysis Learning API",
            version="2.0.0",
            summary="투자·금융 학습용 API",
            description=(
                "## 사용 안내\n\n"
                "투자 분석과 AI/데이터 실습을 위한 교육용 API입니다. 모든 시간·시세 데이터는 외부 공급자 상태에 따라 지연되거나 달라질 수 있으며, "
                "분석 결과는 투자·세무 의사결정의 근거가 아닙니다.\n\n"
                "### 공통 규칙\n\n"
                "- 요청 본문의 필수 여부, 기본값, 범위와 정규식은 각 Schema에서 확인합니다.\n"
                "- 검증에 실패하면 `422`와 필드별 오류가 반환됩니다. 외부 데이터·저장소 의존 API는 연결 실패 시 주로 `502` 또는 `503`을 반환합니다.\n"
                "- 차트는 `data:image/png;base64,...` 또는 base64 문자열로 반환될 수 있습니다. 프런트엔드에서는 이미지 `src`에 그대로 넣어 표시합니다.\n"
                "- 별도 인증은 현재 요구되지 않습니다."
            ),
            routes=app.routes,
            tags=TAG_DESCRIPTIONS,
        )
        schema["paths"] = {
            path: operations
            for path, operations in schema.get("paths", {}).items()
            if path in FRONTEND_API_PATHS
        }
        for path, operations in schema.get("paths", {}).items():
            metadata = OPERATION_DOCS.get(path)
            if not metadata:
                continue
            tag, summary, description = metadata
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                operation["tags"] = [tag]
                operation["summary"] = summary
                operation["description"] = description + "\n\n**공통 오류:** 요청값 검증 실패 시 `422`입니다."
                operation.setdefault("responses", {}).setdefault(
                    "503", {"description": "필요한 외부 서비스 또는 서버 설정을 사용할 수 없습니다."}
                )
        used_tags = {
            tag
            for operations in schema["paths"].values()
            for operation in operations.values()
            for tag in operation.get("tags", [])
        }
        schema["tags"] = [tag for tag in TAG_DESCRIPTIONS if tag["name"] in used_tags]
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
