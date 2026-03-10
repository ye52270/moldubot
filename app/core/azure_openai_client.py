from __future__ import annotations

import os
from functools import lru_cache

from openai import AzureOpenAI

DEFAULT_AZURE_OPENAI_API_VERSION = "2024-12-01-preview"


def has_azure_openai_config() -> bool:
    """
    Azure OpenAI 최소 필수 환경변수 설정 여부를 확인한다.

    Returns:
        endpoint/api_key가 모두 설정되어 있으면 True
    """
    return bool(_read_env("AZURE_OPENAI_ENDPOINT")) and bool(_read_env("AZURE_OPENAI_API_KEY"))


def normalize_azure_deployment_name(model_name: str, default_deployment: str = "gpt-4o-mini") -> str:
    """
    Azure OpenAI 배포명을 정규화한다.

    Args:
        model_name: 원본 모델/배포명
        default_deployment: 기본 배포명

    Returns:
        provider 접두어가 제거된 배포명
    """
    raw = str(model_name or "").strip() or str(default_deployment or "").strip() or "gpt-4o-mini"
    if ":" not in raw:
        return raw
    _, deployment = raw.split(":", 1)
    return deployment.strip() or str(default_deployment or "").strip() or "gpt-4o-mini"


@lru_cache(maxsize=8)
def get_azure_openai_client(timeout_sec: int = 60) -> AzureOpenAI:
    """
    Azure OpenAI SDK 클라이언트를 생성한다.

    Args:
        timeout_sec: 요청 타임아웃(초)

    Returns:
        AzureOpenAI 클라이언트 인스턴스

    Raises:
        ValueError: 필수 환경변수가 누락된 경우
    """
    endpoint = _read_env("AZURE_OPENAI_ENDPOINT")
    api_key = _read_env("AZURE_OPENAI_API_KEY")
    api_version = _read_env("AZURE_OPENAI_API_VERSION") or DEFAULT_AZURE_OPENAI_API_VERSION
    if not endpoint:
        raise ValueError("missing_azure_openai_endpoint")
    if not api_key:
        raise ValueError("missing_azure_openai_api_key")
    return AzureOpenAI(
        api_version=api_version,
        azure_endpoint=endpoint,
        api_key=api_key,
        timeout=timeout_sec,
    )


def _read_env(name: str) -> str:
    """
    환경변수 문자열 값을 정리해 반환한다.

    Args:
        name: 환경변수 이름

    Returns:
        trim된 값(미설정 시 빈 문자열)
    """
    return str(os.getenv(name, "")).strip()
