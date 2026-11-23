"""서버 실행 경로.

CLI와 같은 그래프를 쓰고 엔드포인트로만 감싼다. FastAPI는 선택 의존성이므로
(`pip install -e ".[server]"`) 여기서 `app` 을 미리 불러오지 않는다 — CLI만
설치한 환경에서 `commit_agent.server` 를 import 하는 경로가 생기면 터진다.
"""

from __future__ import annotations

from commit_agent.server.schemas import GenerateRequest, GenerateResponse

__all__ = ["GenerateRequest", "GenerateResponse"]
