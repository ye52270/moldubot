from __future__ import annotations

import os

from deepagents import create_deep_agent
from langgraph.graph.state import CompiledStateGraph

from app.agents.deep_chat_agent import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_PROMPT_VARIANT,
    DEFAULT_SYSTEM_PROMPT,
)
from app.agents.prompts import get_agent_system_prompt
from app.agents.tools import get_agent_tools
from app.core.logging_config import get_logger
from app.middleware.registry import build_agent_middlewares

PLACEHOLDER_OPENAI_KEY = "langgraph-studio-placeholder-key"
logger = get_logger(__name__)


def _ensure_openai_key() -> None:
    """
    LangGraph Studio 로컬 부팅 시 OPENAI_API_KEY 누락을 완화한다.
    """
    openai_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
    if openai_key:
        return
    os.environ["OPENAI_API_KEY"] = PLACEHOLDER_OPENAI_KEY
    logger.warning("OPENAI_API_KEY가 없어 placeholder 키를 임시 적용합니다.")


def build_graph() -> CompiledStateGraph:
    """
    LangGraph Studio가 사용할 MolduBot 그래프 객체를 생성한다.

    Returns:
        CompiledStateGraph 인스턴스
    """
    _ensure_openai_key()
    model_name = str(os.getenv("MOLDUBOT_AGENT_MODEL", DEFAULT_AGENT_MODEL)).strip() or DEFAULT_AGENT_MODEL
    prompt_override = str(os.getenv("MOLDUBOT_AGENT_SYSTEM_PROMPT", "")).strip()
    prompt_variant = str(os.getenv("MOLDUBOT_AGENT_PROMPT_VARIANT", DEFAULT_PROMPT_VARIANT)).strip()
    selected_variant_prompt = get_agent_system_prompt(prompt_variant)
    system_prompt = prompt_override or selected_variant_prompt or DEFAULT_SYSTEM_PROMPT
    logger.info(
        "LangGraph Studio 그래프 초기화: model=%s prompt_variant=%s override=%s",
        model_name,
        prompt_variant or DEFAULT_PROMPT_VARIANT,
        bool(prompt_override),
    )
    return create_deep_agent(
        model=model_name,
        tools=get_agent_tools(),
        system_prompt=system_prompt,
        middleware=build_agent_middlewares(),
        name="moldubot-chat-agent",
    )


graph = build_graph()
