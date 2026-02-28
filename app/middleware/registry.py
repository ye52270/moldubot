from __future__ import annotations

from langchain.agents.middleware.types import AgentMiddleware

from app.middleware.agent_middlewares import (
    IntentDecompositionMiddleware,
    ModelOutputGuardMiddleware,
    RequestResponseLogMiddleware,
    ToolErrorGuardMiddleware,
)


def build_agent_middlewares() -> list[AgentMiddleware]:
    """
    몰두봇 deep agent에 적용할 공통 미들웨어 순서를 구성한다.

    Returns:
        순서가 고정된 미들웨어 목록
    """
    return [
        RequestResponseLogMiddleware(),
        IntentDecompositionMiddleware(),
        ModelOutputGuardMiddleware(),
        ToolErrorGuardMiddleware(),
    ]

