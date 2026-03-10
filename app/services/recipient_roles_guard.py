from __future__ import annotations

import html
import re
from typing import Iterable

from app.models.response_contracts import RecipientRoleEntry
from app.services.person_identity_parser import normalize_person_identity

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SPLIT_PATTERN = re.compile(r"[,;\n]|\s+및\s+")
ROLE_FALLBACK_BY_KEYWORD: tuple[tuple[str, str], ...] = (
    ("검토", "요청 사항 검토 담당"),
    ("확인", "현황 확인 담당"),
    ("조치", "조치 실행 담당"),
    ("수정", "수정 작업 담당"),
    ("승인", "승인 검토 담당"),
    ("요청", "요청 대응 담당"),
)
DISALLOWED_ROLE_PHRASES = (
    "처음 질문을 받는 사람",
    "메시지 발신 및 질문 제기",
    "정보 공유 대상",
    "추가 정보 확인 및 지원 필요",
)


def sanitize_contract_recipient_roles(
    rows: list[RecipientRoleEntry],
    mail_context: dict[str, object] | None,
) -> list[RecipientRoleEntry]:
    """LLM recipient_roles를 현재메일 맥락 기반으로 정제한다.

    Args:
        rows: 모델이 생성한 recipient_roles
        mail_context: 현재메일 컨텍스트

    Returns:
        정제된 recipient_roles 목록
    """
    if not rows:
        return []
    context = mail_context if isinstance(mail_context, dict) else {}
    allowed_to = _extract_recipient_aliases(context=context, keys=("to_recipients", "recipients", "to", "receiver"))
    blocked_sender = _extract_recipient_aliases(context=context, keys=("from_address", "from_display_name"))
    blocked_cc = _extract_recipient_aliases(context=context, keys=("cc_recipients", "cc", "reference", "참조"))

    normalized_rows: list[RecipientRoleEntry] = []
    seen: set[str] = set()
    for row in rows:
        recipient_aliases = _extract_aliases_from_text(text=row.recipient)
        canonical_recipient = normalize_person_identity(token=row.recipient)
        if not canonical_recipient:
            continue
        if allowed_to and recipient_aliases.isdisjoint(allowed_to):
            continue
        if recipient_aliases & blocked_sender:
            continue
        if recipient_aliases & blocked_cc:
            continue

        evidence = _sanitize_evidence(str(row.evidence or ""))
        if not evidence:
            continue
        role = _sanitize_role(str(row.role or ""), evidence=evidence)
        if not role:
            continue

        compare_key = canonical_recipient.lower()
        if compare_key in seen:
            continue
        seen.add(compare_key)
        normalized_rows.append(RecipientRoleEntry(recipient=canonical_recipient, role=role, evidence=evidence))
    return normalized_rows


def _extract_recipient_aliases(context: dict[str, object], keys: Iterable[str]) -> set[str]:
    """메일 컨텍스트 키 목록에서 인물 alias 집합을 추출한다."""
    aliases: set[str] = set()
    for key in keys:
        value = context.get(key)
        if isinstance(value, str):
            aliases.update(_extract_aliases_from_text(text=value))
        elif isinstance(value, list):
            for item in value:
                aliases.update(_extract_aliases_from_text(text=str(item)))
    return aliases


def _extract_aliases_from_text(text: str) -> set[str]:
    """인물 문자열에서 이름/이메일 alias 후보를 추출한다."""
    unescaped = html.unescape(str(text or ""))
    aliases: set[str] = set()
    canonical = normalize_person_identity(token=unescaped)
    if canonical:
        aliases.add(canonical.lower())
    for email in EMAIL_PATTERN.findall(unescaped):
        aliases.add(email.strip().lower())
    for part in SPLIT_PATTERN.split(unescaped):
        candidate = normalize_person_identity(token=part)
        if candidate:
            aliases.add(candidate.lower())
    return aliases


def _sanitize_evidence(text: str) -> str:
    """근거 문장을 품질 규칙으로 정제한다."""
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) < 12:
        return ""
    lowered = compact.lower()
    if lowered.startswith(("to:", "cc:", "from:", "subject:", "sent:", "date:")):
        return ""
    if compact.startswith(("참조:", "cc:", "수신:")):
        return ""
    if compact.startswith(("안녕하세요", "수고", "감사")):
        return ""
    return compact


def _sanitize_role(role: str, evidence: str) -> str:
    """역할 텍스트를 정제하고 필요 시 근거 기반 fallback 역할을 생성한다."""
    normalized = re.sub(r"\s+", " ", str(role or "").strip())
    for phrase in DISALLOWED_ROLE_PHRASES:
        if phrase in normalized:
            normalized = ""
            break
    if normalized:
        return normalized
    lowered = evidence.lower()
    for keyword, fallback in ROLE_FALLBACK_BY_KEYWORD:
        if keyword in lowered:
            return fallback
    return "근거 기반 역할 확인 필요"
