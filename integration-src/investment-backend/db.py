"""애플리케이션 전역에서 공유하는 비동기 MongoDB 연결 관리 모듈.

Motor의 ``AsyncIOMotorClient``는 연결 풀을 내부적으로 관리한다. 따라서 요청마다
새 클라이언트를 만들기보다, 이 모듈에서 한 번 만든 클라이언트와 데이터베이스 핸들을
재사용한다. 실제 네트워크 연결은 클라이언트 생성 시점이 아니라 첫 DB 작업 시점에
필요에 따라 이루어진다.
"""
from __future__ import annotations

import os

# Motor는 asyncio 기반 MongoDB 드라이버다. FastAPI 등 비동기 웹 서버에서 DB I/O가
# 완료될 때까지 이벤트 루프를 불필요하게 막지 않도록 해 준다.
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# 모듈 수준 캐시(간단한 singleton)다. 처음 접근할 때만 생성하고, 애플리케이션이
# 종료될 때 ``close_client``에서 정리한다.
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

# 환경변수로 배포 환경별 MongoDB 주소와 DB 이름을 바꿀 수 있다. 환경변수가 없으면
# 로컬 개발을 위한 기본값을 사용한다.
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "investment_db")


def get_client() -> AsyncIOMotorClient:
    """공유 MongoDB 클라이언트를 반환하고, 없으면 최초 한 번 생성한다.

    ``serverSelectionTimeoutMS``는 MongoDB 서버를 선택하지 못했을 때 최대 5초만
    기다리게 한다. 서버가 꺼져 있거나 URL이 잘못된 경우 요청이 장시간 멈추는 것을
    줄여 준다. 실제 연결 실패는 보통 이후 DB 연산을 ``await``할 때 발생한다.
    """
    global _client

    # 지연 초기화: DB 기능을 전혀 쓰지 않는 실행 경로에서는 클라이언트를 만들지 않는다.
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """설정된 이름의 데이터베이스 핸들을 반환하고, 없으면 캐시한다.

    Motor에서 ``client[database_name]``은 특정 데이터베이스를 가리키는 핸들을
    얻는 작업이다. 이 단계만으로 데이터베이스가 생성되거나 서버에 연결되지는 않으며,
    컬렉션에 첫 데이터를 기록할 때 MongoDB가 실제 DB를 만든다.
    """
    global _db

    # 클라이언트 생성 책임은 get_client에 모아 두어 설정과 연결 수명주기를 일관되게 관리한다.
    if _db is None:
        _db = get_client()[MONGODB_DB]
    return _db


async def close_client() -> None:
    """애플리케이션 종료 시 공유 클라이언트와 캐시된 DB 핸들을 해제한다.

    Motor의 ``close``는 동기 메서드지만, 이 함수는 FastAPI의 lifespan/종료 훅에서
    자연스럽게 호출할 수 있도록 비동기 함수 형태를 유지한다. 클라이언트를 닫은 뒤
    캐시를 ``None``으로 되돌려, 같은 프로세스에서 재초기화가 필요한 경우에도
    get_client/get_db가 새 핸들을 만들 수 있게 한다.
    """
    global _client, _db

    # 아직 DB를 사용하지 않아 클라이언트가 생성되지 않은 경우에는 아무 작업도 하지 않는다.
    if _client:
        _client.close()
        _client = None
        _db = None
