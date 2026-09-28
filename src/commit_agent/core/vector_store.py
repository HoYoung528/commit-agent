"""벡터 스토어 클라이언트 생성.

설정에 `vector_store_url` 이 있으면 공유 서버에, 없으면 로컬 파일에 붙는다.
두 모드는 호출 방식이 같아서 이후 코드는 어느 쪽인지 몰라도 된다.

로컬 모드는 서버를 띄우지 않고 파이썬 프로세스 안에서 동작하며,
한 번에 한 프로세스만 열 수 있다.
"""

from __future__ import annotations

from pathlib import Path

from qdrant_client import QdrantClient

from commit_agent.core.config import Settings, get_settings


def get_store(settings: Settings | None = None) -> QdrantClient:
    """설정에 맞는 벡터 스토어 클라이언트를 만든다."""
    settings = settings or get_settings()

    if settings.vector_store_url:
        return QdrantClient(url=settings.vector_store_url)

    path = Path(settings.vector_store_path)
    path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))
