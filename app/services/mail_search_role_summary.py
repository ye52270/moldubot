from __future__ import annotations

import re
from typing import Any

from app.services.person_identity_parser import normalize_person_identity
from app.services.role_taxonomy_config import get_role_taxonomy

MAX_RESULTS = 10
RECIPIENT_DELIMITERS_PATTERN = r"[,;\n]|\s+및\s+"


def is_mail_search_recipient_role_request(user_message: str) -> bool:
    """메일 검색 기반 수신자 역할 요약 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        메일 검색 + 수신자 역할 정리 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    has_mail_query = any(token in compact for token in ("메일", "m365", "관련"))
    has_recipient = any(token in compact for token in ("수신자", "받는사람", "recipient", "to"))
    has_role = any(token in compact for token in ("역할", "담당"))
    has_organize_intent = any(token in compact for token in ("요약", "정리", "표"))
    return has_mail_query and has_recipient and has_role and has_organize_intent


def render_mail_search_recipient_role_summary(user_message: str, tool_payload: dict[str, Any]) -> str:
    """메일 검색 결과에서 수신자별 역할 요약 결과를 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 도구 payload

    Returns:
        렌더링 문자열. 조건 불충족 시 빈 문자열
    """
    if not is_mail_search_recipient_role_request(user_message=user_message):
        return ""
    if str(tool_payload.get("action") or "").strip().lower() != "mail_search":
        return ""
    results = tool_payload.get("results")
    if not isinstance(results, list) or not results:
        return "## 수신자 역할 요약\n\n조건에 맞는 메일이 없어 수신자 역할을 정리하지 못했습니다."

    taxonomy = get_role_taxonomy()
    lines = [
        "## 수신자 역할 요약",
        "",
        "| 메일 제목 | 수신자 | 역할 추정 | 근거 |",
        "|---|---|---|---|",
    ]
    added_rows = 0
    for item in results[:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        subject = _sanitize_cell(str(item.get("subject") or "제목 없음"))
        recipients = _extract_recipients_from_result(item=item)
        if not recipients:
            lines.append(f"| {subject} | 미확인 | - | 검색 결과 payload에 수신자 필드 없음 |")
            added_rows += 1
            continue
        role = _sanitize_cell(str(taxonomy.default_roles.get("to") or "수신/실행 대상"))
        for recipient in recipients[:5]:
            lines.append(f"| {subject} | {_sanitize_cell(recipient)} | {role} | 메일 헤더 TO |")
            added_rows += 1

    if added_rows == 0:
        return "## 수신자 역할 요약\n\n수신자 정보를 추출하지 못했습니다."

    lines.extend(
        [
            "",
            "- 참고: 검색 결과에 수신자 정보가 없는 메일은 `미확인`으로 표시됩니다.",
            "- 정확한 수신자 역할이 필요하면 `현재메일 수신자 역할 표`로 확인해 주세요.",
        ]
    )
    return "\n".join(lines).strip()


def _extract_recipients_from_result(item: dict[str, Any]) -> list[str]:
    """검색 결과 레코드에서 수신자 문자열 후보를 추출한다.

    Args:
        item: 검색 결과 한 건

    Returns:
        정규화된 수신자 목록
    """
    candidates: list[str] = []
    for key in ("to_recipients", "recipients", "to", "receiver"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value)
        if isinstance(value, list):
            candidates.extend(str(entry).strip() for entry in value if str(entry).strip())

    snippet = str(item.get("snippet") or "")
    if snippet:
        header_match = re.search(r"To:\s*(.+?)(?:Cc:|Subject:|From:|$)", snippet, flags=re.IGNORECASE)
        if header_match:
            candidates.append(str(header_match.group(1) or "").strip())

    recipients: list[str] = []
    for candidate in candidates:
        for part in re.split(RECIPIENT_DELIMITERS_PATTERN, str(candidate or "")):
            normalized = normalize_person_identity(token=part)
            if not normalized:
                continue
            if normalized not in recipients:
                recipients.append(normalized)
    return recipients


def _sanitize_cell(value: str) -> str:
    """마크다운 표 셀 안전 문자열을 생성한다.

    Args:
        value: 원본 문자열

    Returns:
        셀 출력 문자열
    """
    return re.sub(r"\s+", " ", str(value or "-").replace("|", "\\|").strip()) or "-"
