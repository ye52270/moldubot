from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx

from app.core.logging_config import get_logger
from app.core.intent_rules import is_code_review_query
from app.services.verification_policy_service import decide_web_verification

logger = get_logger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_TIMEOUT_SECONDS = 4.0
MAX_WEB_SOURCES = 4
CODE_QUERY_MAX_TOKENS = 8
CODE_IDENTIFIER_MIN_LENGTH = 4
CODE_REVIEW_INCLUDE_DOMAINS = [
    "owasp.org",
    "developer.mozilla.org",
    "docs.oracle.com",
    "learn.microsoft.com",
]


def should_search_web_sources(
    user_message: str,
    intent_task_type: str = "",
    resolved_scope: str = "",
    tool_payload: dict[str, object] | None = None,
    intent_confidence: float | None = None,
    model_answer: str = "",
) -> bool:
    """
    사용자 질의가 웹 검색 보강이 필요한지 판별한다.

    Args:
        user_message: 사용자 입력
        intent_task_type: 의도 task type

    Returns:
        웹 검색 수행 여부
    """
    decision = decide_web_verification(
        user_message=user_message,
        intent_task_type=intent_task_type,
        resolved_scope=resolved_scope,
        tool_payload=tool_payload,
        intent_confidence=intent_confidence,
        model_answer=model_answer,
    )
    return bool(decision.enabled)


def get_web_verification_reasons(
    user_message: str,
    intent_task_type: str = "",
    resolved_scope: str = "",
    tool_payload: dict[str, object] | None = None,
    intent_confidence: float | None = None,
    model_answer: str = "",
) -> list[str]:
    """
    웹 검증 정책 판단 근거를 반환한다.

    Args:
        user_message: 사용자 입력
        intent_task_type: 의도 task type
        resolved_scope: 최종 scope
        tool_payload: 최근 도구 payload
        intent_confidence: 의도 confidence
        model_answer: 모델 응답

    Returns:
        정책 근거 문자열 목록
    """
    decision = decide_web_verification(
        user_message=user_message,
        intent_task_type=intent_task_type,
        resolved_scope=resolved_scope,
        tool_payload=tool_payload,
        intent_confidence=intent_confidence,
        model_answer=model_answer,
    )
    return list(decision.reasons)


def search_web_sources(
    user_message: str,
    max_results: int = MAX_WEB_SOURCES,
    intent_task_type: str = "",
    tool_payload: dict[str, object] | None = None,
) -> list[dict[str, str]]:
    """
    Tavily 검색 결과를 UI 표출용 출처 목록으로 변환한다.

    Args:
        user_message: 사용자 질의
        max_results: 반환 최대 개수

    Returns:
        출처 목록
    """
    api_key = str(os.getenv("TAVILY_API_KEY", "")).strip()
    query = build_web_search_query(
        user_message=user_message,
        intent_task_type=intent_task_type,
        tool_payload=tool_payload,
    )
    if not api_key or not query:
        return []
    include_domains = resolve_include_domains(
        user_message=user_message,
        intent_task_type=intent_task_type,
        tool_payload=tool_payload,
    )
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(8, int(max_results))),
        "include_answer": False,
        "include_raw_content": False,
        "include_favicon": True,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    try:
        response = httpx.post(TAVILY_SEARCH_URL, json=payload, timeout=TAVILY_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("web_source_search.tavily_request_failed: %s", exc)
        return []
    data = response.json() if response.content else {}
    return _normalize_tavily_results(results=data.get("results"), max_results=max_results)


def build_web_search_query(
    user_message: str,
    intent_task_type: str = "",
    tool_payload: dict[str, object] | None = None,
) -> str:
    """
    사용자 질의와 코드 문맥을 결합한 Tavily 검색 질의를 생성한다.

    Args:
        user_message: 사용자 질의
        intent_task_type: 의도 task type
        tool_payload: 최근 도구 payload

    Returns:
        Tavily 검색 질의 문자열
    """
    query = str(user_message or "").strip()
    if not _should_apply_code_context_query(
        user_message=user_message,
        intent_task_type=intent_task_type,
        tool_payload=tool_payload,
    ):
        return query
    code = _extract_code_excerpt(tool_payload=tool_payload)
    if not code:
        return query
    language = _infer_code_language(code=code)
    identifiers = _extract_code_identifiers(code=code)
    token_text = " ".join(identifiers)
    return (
        f"{language} 보안 코드 리뷰 체크리스트 CSRF XSS 세션고정 입력검증 "
        f"{token_text}".strip()
    )


def resolve_include_domains(
    user_message: str,
    intent_task_type: str = "",
    tool_payload: dict[str, object] | None = None,
) -> list[str]:
    """
    코드리뷰 질의에 대해 신뢰도 높은 도메인 제한 목록을 반환한다.

    Args:
        user_message: 사용자 질의
        intent_task_type: 의도 task type
        tool_payload: 최근 도구 payload

    Returns:
        포함 도메인 목록
    """
    if _should_apply_code_context_query(
        user_message=user_message,
        intent_task_type=intent_task_type,
        tool_payload=tool_payload,
    ):
        return list(CODE_REVIEW_INCLUDE_DOMAINS)
    return []


def _should_apply_code_context_query(
    user_message: str,
    intent_task_type: str,
    tool_payload: dict[str, object] | None,
) -> bool:
    """
    코드 문맥 기반 Tavily 질의 적용 대상인지 판별한다.

    Args:
        user_message: 사용자 질의
        intent_task_type: 의도 task type
        tool_payload: 최근 도구 payload

    Returns:
        코드 문맥 질의 적용 여부
    """
    if is_code_review_query(user_message=user_message):
        return True
    normalized_task_type = str(intent_task_type or "").strip().lower()
    if normalized_task_type != "analysis":
        return False
    return bool(_extract_code_excerpt(tool_payload=tool_payload))


def _extract_code_excerpt(tool_payload: dict[str, object] | None) -> str:
    """
    도구 payload에서 코드 발췌를 추출한다.

    Args:
        tool_payload: 최근 도구 payload

    Returns:
        코드 발췌 문자열
    """
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    context = payload.get("mail_context") if isinstance(payload.get("mail_context"), dict) else {}
    code = str(context.get("body_code_excerpt") or "").strip()
    if code:
        return code
    return str(context.get("body_excerpt") or "").strip()


def _infer_code_language(code: str) -> str:
    """
    코드 스니펫의 언어명을 휴리스틱으로 추정한다.

    Args:
        code: 코드 문자열

    Returns:
        언어명
    """
    text = str(code or "").lower()
    if "<%" in text or "logic:" in text or "bean:write" in text:
        return "JSP"
    if "<div" in text or "<input" in text:
        return "HTML"
    if "function " in text or "const " in text:
        return "JavaScript"
    return "code"


def _extract_code_identifiers(code: str) -> list[str]:
    """
    코드에서 Tavily 질의용 식별자 토큰을 추출한다.

    Args:
        code: 코드 문자열

    Returns:
        상위 식별자 목록
    """
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_:-]{3,}", str(code or ""))
    filtered: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        lowered = token.lower()
        if lowered in seen:
            continue
        if len(token) < CODE_IDENTIFIER_MIN_LENGTH:
            continue
        if lowered in {"class", "style", "input", "button", "div", "name", "value"}:
            continue
        seen.add(lowered)
        filtered.append(token)
        if len(filtered) >= CODE_QUERY_MAX_TOKENS:
            break
    return filtered


def _normalize_tavily_results(results: object, max_results: int) -> list[dict[str, str]]:
    """
    Tavily 원본 결과를 정규화한다.

    Args:
        results: Tavily 결과 필드
        max_results: 최대 반환 개수

    Returns:
        정규화된 출처 목록
    """
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(item.get("title") or "").strip() or "제목 없음"
        snippet = str(item.get("content") or "").strip()
        site_name = _extract_site_name(url=url)
        icon_text = site_name[:1].upper() if site_name else "•"
        normalized.append(
            {
                "title": title,
                "url": url,
                "site_name": site_name,
                "snippet": snippet[:180],
                "icon_text": icon_text,
                "favicon_url": str(item.get("favicon") or "").strip(),
            }
        )
        if len(normalized) >= max(1, int(max_results)):
            break
    return normalized


def _extract_site_name(url: str) -> str:
    """
    URL에서 사이트명을 추출한다.

    Args:
        url: 출처 URL

    Returns:
        사이트명
    """
    parsed = urlparse(str(url or "").strip())
    host = str(parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host
