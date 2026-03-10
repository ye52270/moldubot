from __future__ import annotations

import json
from typing import Any

from app.agents.deep_chat_agent import is_openai_key_configured
from app.core.llm_runtime import invoke_json_object, resolve_env_model
from app.core.intent_rules import is_code_review_query
from app.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_QUALITY_MODEL = "gpt-4o-mini"
QUALITY_TIMEOUT_SECONDS = 20.0
QUALITY_MAX_CODE_CHARS = 2600
QUALITY_MAX_ANSWER_CHARS = 2600


def refine_code_review_answer_with_metadata(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    코드리뷰 응답 품질 보정 결과와 메타데이터를 함께 반환한다.

    Args:
        user_message: 사용자 원문
        answer: 1차 모델 응답
        tool_payload: 최근 도구 payload

    Returns:
        (최종 응답, 품질 메타데이터) 튜플
    """
    original_answer = str(answer or "")
    metadata: dict[str, Any] = {
        "enabled": False,
        "critic_used": False,
        "revise_applied": False,
        "detected_language": "",
    }
    if not _is_target(user_message=user_message, answer=original_answer):
        return original_answer, metadata
    if not is_openai_key_configured():
        metadata["enabled"] = True
        return original_answer, metadata

    code_excerpt = _extract_code_excerpt(tool_payload=tool_payload)
    language = _detect_language(code_excerpt=code_excerpt)
    metadata["enabled"] = True
    metadata["detected_language"] = language
    model_name = resolve_env_model(
        primary_env="MOLDUBOT_REVIEW_QUALITY_MODEL",
        fallback_envs=("QUALITY_REVIEW_MODEL", "DEFAULT_CHAT_MODEL"),
        default_model=DEFAULT_QUALITY_MODEL,
    )
    try:
        critic = _run_critic(
            model_name=model_name,
            user_message=user_message,
            answer=original_answer,
            code_excerpt=code_excerpt,
            language=language,
        )
        metadata["critic_used"] = True
        revised_answer = _run_reviser(
            model_name=model_name,
            user_message=user_message,
            answer=original_answer,
            critic=critic,
            code_excerpt=code_excerpt,
            language=language,
        )
        if revised_answer:
            metadata["revise_applied"] = True
            logger.info("code_review_quality.revise_applied: language=%s", language)
            return revised_answer, metadata
    except Exception as exc:
        logger.warning("code_review_quality.failed: %s", exc)
    return original_answer, metadata


def refine_code_review_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
) -> str:
    """
    코드리뷰 응답 품질을 critic/revise 2단계로 보정한다.

    Args:
        user_message: 사용자 원문
        answer: 1차 모델 응답
        tool_payload: 최근 도구 payload

    Returns:
        보정된 코드리뷰 응답. 실패 시 원문 응답
    """
    refined, _metadata = refine_code_review_answer_with_metadata(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    return refined


def _is_target(user_message: str, answer: str) -> bool:
    """
    품질 보정 대상 코드리뷰 응답인지 판별한다.

    Args:
        user_message: 사용자 원문
        answer: 모델 응답

    Returns:
        보정 대상 여부
    """
    if not is_code_review_query(user_message=user_message):
        return False
    text = str(answer or "").strip()
    if not text:
        return False
    if "코드 스니펫이 없습니다." in text:
        return False
    return "## 코드 리뷰" in text or "```" in text


def _run_critic(
    model_name: str,
    user_message: str,
    answer: str,
    code_excerpt: str,
    language: str,
) -> dict[str, Any]:
    """
    코드리뷰 초안에 대한 critic JSON 결과를 생성한다.

    Args:
        model_name: 모델명
        user_message: 사용자 질의
        answer: 초안 응답
        code_excerpt: 코드 발췌
        language: 감지 언어

    Returns:
        critic JSON 사전
    """
    system_prompt = (
        "너는 코드리뷰 품질 검사기다. 반드시 JSON 객체만 출력한다.\n"
        "스키마: {\"verdict\":\"pass|needs_revision\",\"language\":\"string\","
        "\"issues\":[{\"id\":\"string\",\"severity\":\"high|medium|low\","
        "\"reason\":\"string\",\"suggested_fix\":\"string\"}],\"must_fix\":[\"string\"]}"
    )
    user_prompt = json.dumps(
        {
            "query": str(user_message or "")[:400],
            "detected_language": language,
            "draft_answer": str(answer or "")[:QUALITY_MAX_ANSWER_CHARS],
            "code_excerpt": str(code_excerpt or "")[:QUALITY_MAX_CODE_CHARS],
            "checks": [
                "코드와 주석의 정합성",
                "언어 표기 정확성(JSP/HTML/JS 등)",
                "과장/근거부족 주장 여부",
                "중복/일반론 남발 여부",
            ],
        },
        ensure_ascii=False,
    )
    loaded = invoke_json_object(
        model_name=model_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=int(QUALITY_TIMEOUT_SECONDS),
    )
    return loaded if isinstance(loaded, dict) else {}


def _run_reviser(
    model_name: str,
    user_message: str,
    answer: str,
    critic: dict[str, Any],
    code_excerpt: str,
    language: str,
) -> str:
    """
    critic 결과를 반영해 최종 코드리뷰 마크다운을 재작성한다.

    Args:
        model_name: 모델명
        user_message: 사용자 질의
        answer: 초안 응답
        critic: critic JSON
        code_excerpt: 코드 발췌
        language: 감지 언어

    Returns:
        보정된 마크다운 응답. 실패 시 빈 문자열
    """
    system_prompt = (
        "너는 코드리뷰 교정기다. 반드시 JSON 객체만 출력한다.\n"
        "스키마: {\"answer_markdown\":\"string\"}\n"
        "규칙:\n"
        "- `## 코드 분석`에는 기능 요약/보안 리스크 2개만 유지\n"
        "- `## 코드 리뷰`에는 `### 언어`를 포함하고 JSP면 반드시 JSP로 표기\n"
        "- 코드 블록은 1~3개, 각 6줄 이하\n"
        "- 각 스니펫마다 `주석/리스크/개선`을 구체적으로 작성\n"
        "- 코드 근거 없는 단정 금지, 불확실하면 `확인 필요` 명시"
    )
    user_prompt = json.dumps(
        {
            "query": str(user_message or "")[:400],
            "detected_language": language,
            "draft_answer": str(answer or "")[:QUALITY_MAX_ANSWER_CHARS],
            "critic": critic,
            "code_excerpt": str(code_excerpt or "")[:QUALITY_MAX_CODE_CHARS],
        },
        ensure_ascii=False,
    )
    loaded = invoke_json_object(
        model_name=model_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_sec=int(QUALITY_TIMEOUT_SECONDS),
    )
    if not isinstance(loaded, dict):
        return ""
    return str(loaded.get("answer_markdown") or "").strip()


def _extract_code_excerpt(tool_payload: dict[str, Any] | None) -> str:
    """
    tool payload에서 코드 발췌를 추출한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        코드 발췌 문자열
    """
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    context = payload.get("mail_context") if isinstance(payload.get("mail_context"), dict) else {}
    code = str(context.get("body_code_excerpt") or "").strip()
    if code:
        return code
    return str(context.get("body_excerpt") or "").strip()


def _detect_language(code_excerpt: str) -> str:
    """
    코드 발췌 언어를 추정한다.

    Args:
        code_excerpt: 코드 발췌

    Returns:
        언어명
    """
    text = str(code_excerpt or "").lower()
    if "<%" in text or "bean:write" in text or "logic:" in text:
        return "JSP"
    if "<input" in text or "<div" in text:
        return "HTML"
    if "function " in text or "const " in text:
        return "JavaScript"
    return "text"
