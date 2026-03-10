from __future__ import annotations

import json
import re
from typing import Any

from app.core.intent_rules import is_code_review_query
from app.services.answer_postprocessor_guards import looks_like_json_contract_text


def render_auto_code_snippet_text(user_message: str, answer: str) -> str:
    """
    코드성 텍스트(JSON/HTML/JS/LDAP)를 fenced code block으로 정규화한다.

    Args:
        user_message: 사용자 입력
        answer: 모델 응답 텍스트

    Returns:
        코드스니펫 마크다운 문자열. 비대상이면 빈 문자열
    """
    if is_code_review_query(user_message=user_message):
        return ""
    text = str(answer or "").strip()
    if not text or "```" in text:
        return ""
    if looks_like_json_contract_text(text=text):
        return ""
    ldap_rendered = _render_ldap_filter_blocks(text=text)
    if ldap_rendered:
        return ldap_rendered
    language = _infer_code_language(text=text)
    if not language:
        return ""
    code_text = text
    if language == "json":
        parsed = _try_parse_plain_json(text=text)
        if parsed is not None:
            code_text = json.dumps(parsed, ensure_ascii=False, indent=2)
    return f"```{language}\n{code_text}\n```"


def _render_ldap_filter_blocks(text: str) -> str:
    """
    LDAP 필터 문자열을 추출해 코드블록으로 렌더링한다.

    Args:
        text: 모델 응답 텍스트

    Returns:
        LDAP 코드블록 문자열. 감지 실패 시 빈 문자열
    """
    compact = str(text or "").lower()
    ldap_tokens = ("objectclass=", "objectcategory=", "samaccountname=", "mailnickname=", "memberof=")
    if not any(token in compact for token in ldap_tokens):
        return ""
    filters = _extract_parenthesized_filters(text=text)
    if not filters:
        return ""
    blocks = [f"```text\n{item}\n```" for item in filters[:3]]
    return "\n\n".join(blocks).strip()


def _extract_parenthesized_filters(text: str) -> list[str]:
    """
    중첩 괄호 기반으로 LDAP 필터 후보를 추출한다.

    Args:
        text: 입력 문자열

    Returns:
        LDAP 필터 후보 목록(중복 제거)
    """
    source = str(text or "")
    candidates: list[str] = []
    start = -1
    depth = 0
    for index, char in enumerate(source):
        if char == "(":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = source[start : index + 1].strip()
                if len(chunk) >= 24 and "=" in chunk:
                    candidates.append(chunk)
                start = -1
    deduped: list[str] = []
    for chunk in candidates:
        if chunk not in deduped:
            deduped.append(chunk)
    return deduped


def _infer_code_language(text: str) -> str:
    """
    텍스트 패턴으로 코드 언어를 추론한다.

    Args:
        text: 입력 문자열

    Returns:
        markdown code fence 언어 문자열. 비코드면 빈 문자열
    """
    source = str(text or "").strip()
    if not source:
        return ""
    if _try_parse_plain_json(text=source) is not None:
        return "json"
    if re.search(r"<[a-zA-Z][^>]*>", source) and (("</" in source) or source.count("<") >= 2):
        return "html"
    js_tokens = ("const ", "let ", "function ", "=>", "return ", "console.", "import ", "export ")
    if any(token in source for token in js_tokens):
        return "javascript"
    return ""


def _try_parse_plain_json(text: str) -> Any | None:
    """
    일반 JSON 본문 파싱을 시도한다.

    Args:
        text: 입력 문자열

    Returns:
        파싱된 JSON 값. 실패 시 None
    """
    candidate = str(text or "").strip()
    if not candidate or candidate[0] not in ("{", "["):
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
