from __future__ import annotations

import re
from typing import Iterable

from app.models.response_contracts import RecipientTodoEntry
from app.services.person_identity_parser import normalize_person_identity
from app.services.recipient_roles_guard import _extract_aliases_from_text

DISALLOWED_TODO_PREFIXES = ("확인 필요", "추가 확인 필요", "미정")


def sanitize_contract_recipient_todos(
    rows: list[RecipientTodoEntry],
    mail_context: dict[str, object] | None,
) -> list[RecipientTodoEntry]:
    """LLM recipient_todos를 현재메일 맥락 기반으로 정제한다.

    Args:
        rows: 모델이 생성한 recipient_todos
        mail_context: 현재메일 컨텍스트

    Returns:
        정제된 recipient_todos 목록
    """
    if not rows:
        return []
    context = mail_context if isinstance(mail_context, dict) else {}
    allowed_to = _extract_recipient_aliases(context=context, keys=("to_recipients", "recipients", "to", "receiver"))
    blocked_sender = _extract_recipient_aliases(context=context, keys=("from_address", "from_display_name"))
    blocked_cc = _extract_recipient_aliases(context=context, keys=("cc_recipients", "cc", "reference", "참조"))

    sanitized: list[RecipientTodoEntry] = []
    seen: set[str] = set()
    for row in rows:
        recipient = normalize_person_identity(token=str(row.recipient or ""))
        if not recipient:
            continue
        aliases = _extract_aliases_from_text(text=recipient)
        if allowed_to and aliases.isdisjoint(allowed_to):
            continue
        if aliases & blocked_sender:
            continue
        if aliases & blocked_cc:
            continue

        todo = _sanitize_todo(text=str(row.todo or ""))
        if not todo:
            continue
        due_date = _normalize_due_date(str(row.due_date or ""))
        basis = _sanitize_basis(text=str(row.due_date_basis or ""))
        due_date = _enforce_due_date_with_basis(due_date=due_date, basis=basis)

        key = f"{recipient.lower()}::{todo.lower()}::{due_date}"
        if key in seen:
            continue
        seen.add(key)
        sanitized.append(
            RecipientTodoEntry(
                recipient=recipient,
                todo=todo,
                due_date=due_date,
                due_date_basis=basis,
            )
        )
    return sanitized


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


def _sanitize_todo(text: str) -> str:
    """todo 문장을 정규화한다."""
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) < 4:
        return ""
    lowered = compact.lower()
    if lowered.startswith(DISALLOWED_TODO_PREFIXES):
        return ""
    return compact


def _sanitize_basis(text: str) -> str:
    """기한 근거 문장을 정규화한다."""
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if not compact:
        return "근거 부족"
    lowered = compact.lower()
    if lowered.startswith(("안녕하세요", "from:", "to:", "cc:", "subject:", "참조:")):
        return "근거 부족"
    return compact


def _normalize_due_date(value: str) -> str:
    """마감일을 YYYY-MM-DD 또는 미정으로 정규화한다."""
    text = str(value or "").strip()
    if not text or text == "미정":
        return "미정"
    matched = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if not matched:
        return "미정"
    return matched.group(1)


def _enforce_due_date_with_basis(due_date: str, basis: str) -> str:
    """기한 근거가 약하면 due_date를 미정으로 강제한다."""
    if due_date == "미정":
        return due_date
    if basis == "근거 부족":
        return "미정"
    if _contains_due_signal(basis):
        return due_date
    return "미정"


def _contains_due_signal(text: str) -> bool:
    """기한 근거 문장에 일정 단서가 포함됐는지 확인한다."""
    normalized = str(text or "").strip()
    if not normalized:
        return False
    patterns = (
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}월\s*\d{1,2}일",
        r"\d{1,2}월\s*(말|초|중순|하순)",
        r"(오늘|내일|이번주|다음주|금주|차주)",
        r"(마감|기한|완료|까지|due)",
    )
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)
