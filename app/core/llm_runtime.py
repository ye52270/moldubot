from __future__ import annotations

import json
import os
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_CHAT_MODEL_FALLBACK = "gpt-4o-mini"
PROVIDER_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "azure_openai": ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
}
AZURE_API_VERSION_ENV = "AZURE_OPENAI_API_VERSION"
OPENAI_API_VERSION_ENV = "OPENAI_API_VERSION"


def normalize_model_name(model_name: str, default_model: str = DEFAULT_CHAT_MODEL_FALLBACK) -> str:
    """
    모델명을 provider 접두어 포함 형식으로 정규화한다.

    Args:
        model_name: 원본 모델명
        default_model: 비어 있을 때 사용할 기본 모델명

    Returns:
        정규화된 모델명
    """
    raw = str(model_name or "").strip()
    if not raw:
        raw = str(default_model or "").strip() or DEFAULT_CHAT_MODEL_FALLBACK
    lowered = raw.lower()
    if ":" in raw:
        if lowered.startswith("azure_openai:"):
            ensure_azure_openai_env_compat()
        return raw
    if lowered.startswith("claude"):
        return f"anthropic:{raw}"
    if lowered.startswith(("gpt", "o1", "o3", "o4", "text-embedding")):
        if _are_all_envs_set(PROVIDER_ENV_KEYS["azure_openai"]):
            ensure_azure_openai_env_compat()
            return f"azure_openai:{raw}"
        return f"openai:{raw}"
    return raw


def detect_provider(model_name: str) -> str:
    """
    모델명에서 provider를 추론한다.

    Args:
        model_name: 모델명

    Returns:
        provider 문자열
    """
    normalized = normalize_model_name(model_name=model_name)
    if ":" not in normalized:
        return ""
    return normalized.split(":", 1)[0].strip().lower()


def is_model_provider_configured(model_name: str) -> bool:
    """
    모델 provider에 필요한 API 키가 설정되어 있는지 확인한다.

    Args:
        model_name: 모델명

    Returns:
        키가 설정되어 있으면 True
    """
    provider = detect_provider(model_name=model_name)
    required_envs = PROVIDER_ENV_KEYS.get(provider)
    if not required_envs:
        return True
    if provider == "openai":
        return _are_all_envs_set(PROVIDER_ENV_KEYS["openai"]) or _are_all_envs_set(PROVIDER_ENV_KEYS["azure_openai"])
    if provider == "azure_openai":
        return _are_all_envs_set(required_envs) and _is_azure_api_version_set()
    return _are_all_envs_set(required_envs)


def resolve_env_model(primary_env: str, fallback_envs: tuple[str, ...], default_model: str) -> str:
    """
    환경변수 우선순위에 따라 모델명을 조회하고 정규화한다.

    Args:
        primary_env: 최우선 환경변수 이름
        fallback_envs: 차선 환경변수 이름 목록
        default_model: 기본 모델명

    Returns:
        정규화된 모델명
    """
    raw = str(os.getenv(primary_env, "")).strip()
    if not raw:
        for env_name in fallback_envs:
            raw = str(os.getenv(env_name, "")).strip()
            if raw:
                break
    return normalize_model_name(model_name=raw, default_model=default_model)


def _are_all_envs_set(env_names: tuple[str, ...]) -> bool:
    """
    지정된 환경변수들이 모두 설정되어 있는지 확인한다.

    Args:
        env_names: 확인할 환경변수 이름 목록

    Returns:
        모두 비어있지 않으면 True
    """
    return all(bool(str(os.getenv(name, "")).strip()) for name in env_names)


def _is_azure_api_version_set() -> bool:
    """
    Azure OpenAI API 버전 환경변수가 존재하는지 확인한다.

    Returns:
        OPENAI_API_VERSION 또는 AZURE_OPENAI_API_VERSION 중 하나가 있으면 True
    """
    return bool(str(os.getenv(OPENAI_API_VERSION_ENV, "")).strip()) or bool(str(os.getenv(AZURE_API_VERSION_ENV, "")).strip())


def ensure_azure_openai_env_compat() -> None:
    """
    Azure OpenAI API 버전 환경변수를 LangChain 호환 이름으로 동기화한다.
    """
    current = str(os.getenv(OPENAI_API_VERSION_ENV, "")).strip()
    if current:
        return
    azure_version = str(os.getenv(AZURE_API_VERSION_ENV, "")).strip()
    if not azure_version:
        return
    os.environ[OPENAI_API_VERSION_ENV] = azure_version


def invoke_json_object(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    timeout_sec: int = 60,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    LLM 호출 결과를 JSON 객체로 파싱해 반환한다.

    Args:
        model_name: 모델명
        system_prompt: 시스템 프롬프트
        user_prompt: 사용자 프롬프트
        timeout_sec: 타임아웃(초)
        temperature: 샘플링 온도

    Returns:
        파싱된 JSON 사전

    Raises:
        ValueError: 응답이 JSON 객체가 아닐 때
    """
    content = invoke_text_messages(
        model_name=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        timeout_sec=timeout_sec,
        temperature=temperature,
    )
    loaded = json.loads(content)
    if not isinstance(loaded, dict):
        raise ValueError("llm_response_not_json_object")
    return loaded


def invoke_text_messages(
    model_name: str,
    messages: list[dict[str, str]],
    timeout_sec: int = 60,
    temperature: float | None = None,
) -> str:
    """
    LLM을 호출해 텍스트 응답을 반환한다.

    Args:
        model_name: 모델명
        messages: role/content 배열
        timeout_sec: 타임아웃(초)
        temperature: 샘플링 온도

    Returns:
        응답 텍스트
    """
    normalized_model = normalize_model_name(model_name=model_name)
    model_kwargs: dict[str, Any] = {"model": normalized_model, "timeout": timeout_sec}
    if temperature is not None:
        model_kwargs["temperature"] = temperature
    llm = init_chat_model(**model_kwargs)
    lc_messages = _to_langchain_messages(messages=messages)
    response = llm.invoke(lc_messages)
    return _coerce_message_content(content=getattr(response, "content", ""))


def _to_langchain_messages(messages: list[dict[str, str]]) -> list[SystemMessage | HumanMessage]:
    """
    role/content 사전을 LangChain 메시지 객체로 변환한다.

    Args:
        messages: role/content 배열

    Returns:
        LangChain 메시지 배열
    """
    converted: list[SystemMessage | HumanMessage] = []
    for item in messages:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "")
        if role == "system":
            converted.append(SystemMessage(content=content))
            continue
        converted.append(HumanMessage(content=content))
    return converted


def _coerce_message_content(content: Any) -> str:
    """
    모델 응답 content를 문자열로 정규화한다.

    Args:
        content: 응답 content 원본

    Returns:
        문자열 content
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    chunks.append(text)
            else:
                text = str(item or "").strip()
                if text:
                    chunks.append(text)
        return "\n".join(chunks).strip()
    return str(content or "").strip()
