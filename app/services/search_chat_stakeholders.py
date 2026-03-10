from __future__ import annotations

import re
from typing import Any

from app.services.text_overlap_utils import normalize_compare_text

EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PERSON_EMAIL_PAIR_PATTERN = re.compile(
    r"([^<;\n]{1,120}?)\s*<([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})>"
)
DOMAIN_ONLY_TOKENS = {"sk", "skcc", "cnthoth", "com", "co", "kr", "net", "org"}


def build_stakeholders(
    answer_format: dict[str, Any],
    source_text: str,
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
    llm_recipient_roles: list[dict[str, str]] | None,
    llm_recipient_todos: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """
    컨텍스트 탭의 관계자 정보를 구성한다.

    Args:
        answer_format: answer_format metadata
        source_text: 메일 원문 기반 정리 텍스트
        tool_payload: 마지막 tool payload
        evidence_mails: 근거메일 목록
        llm_recipient_roles: LLM recipient_roles 목록
        llm_recipient_todos: LLM recipient_todos 목록

    Returns:
        관계자 목록(이름/역할/근거)
    """
    llm_first = _build_stakeholders_from_llm(
        llm_recipient_roles=llm_recipient_roles,
        llm_recipient_todos=llm_recipient_todos,
        source_text=source_text,
    )
    if llm_first:
        return llm_first

    names = _collect_person_names(source_text=source_text, tool_payload=tool_payload, evidence_mails=evidence_mails)
    if not names:
        return []

    role_hints = _extract_role_hints(answer_format=answer_format)
    stakeholders: list[dict[str, str]] = []
    for index, name in enumerate(names[:5], start=1):
        role = role_hints.get(name) or ("요청자" if index == 1 else "담당자")
        evidence = _find_person_evidence(source_text=source_text, person=name)
        stakeholders.append({"name": name, "role": role, "evidence": evidence})
    return stakeholders


def _build_stakeholders_from_llm(
    llm_recipient_roles: list[dict[str, str]] | None,
    llm_recipient_todos: list[dict[str, str]] | None,
    source_text: str,
) -> list[dict[str, str]]:
    """
    LLM recipient_roles/recipient_todos를 관계자 카드 스키마로 변환한다.

    Args:
        llm_recipient_roles: LLM recipient_roles 목록
        llm_recipient_todos: LLM recipient_todos 목록
        source_text: 메일 원문 정리 텍스트

    Returns:
        관계자 목록
    """
    rows = llm_recipient_roles if isinstance(llm_recipient_roles, list) else []
    todos = llm_recipient_todos if isinstance(llm_recipient_todos, list) else []
    if not rows and not todos:
        return []

    llm_source = _collect_llm_source_text(rows=rows, todos=todos)
    recipient_candidates = _extract_recipient_candidates(text=" ".join([source_text, llm_source]))
    stakeholders: list[dict[str, str]] = []
    seen: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("recipient") or "").strip()
        role = str(row.get("role") or "").strip() or "담당자"
        evidence = str(row.get("evidence") or "").strip()
        name = _resolve_stakeholder_name(raw_name=raw_name, evidence=evidence, candidates=recipient_candidates)
        normalized = normalize_compare_text(text=name)
        if not name or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        stakeholders.append({"name": name, "role": role, "evidence": evidence})

    for row in todos:
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("recipient") or "").strip()
        todo = str(row.get("todo") or "").strip()
        due = str(row.get("due_date") or "").strip()
        basis = str(row.get("due_date_basis") or "").strip()
        evidence_parts = [part for part in (todo, due, basis) if part]
        name = _resolve_stakeholder_name(
            raw_name=raw_name,
            evidence=" / ".join(evidence_parts),
            candidates=recipient_candidates,
        )
        if not name:
            continue
        normalized = normalize_compare_text(text=name)
        if not normalized or normalized in seen:
            continue
        stakeholders.append({"name": name, "role": "실행 담당", "evidence": " / ".join(evidence_parts)})
        seen.add(normalized)
    return stakeholders[:6]


def _collect_person_names(
    source_text: str,
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[str]:
    """
    메일텍스트/근거메일에서 인명 후보를 추출한다.

    Args:
        source_text: 메일 정리 텍스트
        tool_payload: 마지막 tool payload
        evidence_mails: 근거메일 목록

    Returns:
        중복 제거된 인명 목록
    """
    candidates: list[str] = []
    if isinstance(tool_payload, dict):
        context = tool_payload.get("mail_context")
        if isinstance(context, dict):
            sender = str(context.get("from_display_name") or "").strip()
            if sender:
                candidates.append(sender)

    for item in evidence_mails[:3]:
        if not isinstance(item, dict):
            continue
        sender_name = str(item.get("sender_names") or "").strip()
        if sender_name:
            candidates.append(sender_name)

    text = str(source_text or "")
    candidates.extend(re.findall(r"@([가-힣A-Za-z]{2,20})", text))
    candidates.extend(re.findall(r"([가-힣]{2,4})\s*(?:님|매니저)", text))

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_name in candidates:
        name = str(raw_name or "").strip()
        if not name:
            continue
        normalized = normalize_compare_text(text=name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(name)
    return deduped


def _extract_role_hints(answer_format: dict[str, Any]) -> dict[str, str]:
    """
    answer_format 주요 내용 문장에서 관계자 역할 힌트를 추출한다.

    Args:
        answer_format: answer_format metadata

    Returns:
        이름별 역할 힌트
    """
    hints: dict[str, str] = {}
    points = _extract_major_points_from_answer_format(answer_format=answer_format)
    for line in points:
        text = str(line or "").strip()
        if not text:
            continue
        names = re.findall(r"([가-힣]{2,4})", text)
        role = "담당자"
        normalized = text.lower()
        if "요청" in normalized or "문의" in normalized:
            role = "요청자"
        elif "기술" in normalized or "가이드" in normalized or "검토" in normalized:
            role = "기술담당"
        for name in names:
            if name and name not in hints:
                hints[name] = role
    return hints


def _extract_major_points_from_answer_format(answer_format: dict[str, Any]) -> list[str]:
    """
    answer_format에서 주요 내용 포인트를 추출한다.

    Args:
        answer_format: answer_format metadata

    Returns:
        주요 포인트 목록
    """
    points = answer_format.get("major_points")
    if isinstance(points, list):
        return [str(item).strip() for item in points if str(item or "").strip()]
    summary_lines = answer_format.get("summary_lines")
    if isinstance(summary_lines, list):
        return [str(item).strip() for item in summary_lines if str(item or "").strip()]
    return []


def _find_person_evidence(source_text: str, person: str) -> str:
    """
    본문에서 인물명을 포함하는 근거 문장을 찾아 반환한다.

    Args:
        source_text: 메일 텍스트
        person: 인물명

    Returns:
        매칭된 근거 문장(없으면 빈 문자열)
    """
    target = normalize_compare_text(text=person)
    if not target:
        return ""
    for sentence in _split_sentences(text=source_text):
        normalized_sentence = normalize_compare_text(text=sentence)
        if target and target in normalized_sentence:
            return sentence[:160]
    return ""


def _split_sentences(text: str) -> list[str]:
    """
    텍스트를 문장 단위로 분리한다.

    Args:
        text: 원문 텍스트

    Returns:
        문장 목록
    """
    normalized = str(text or "").replace("\r", " ").replace("\n", " ")
    candidates = re.split(r"(?<=[\.\?!])\s+", normalized)
    return [item.strip() for item in candidates if item and item.strip()]


def _collect_llm_source_text(rows: list[dict[str, str]], todos: list[dict[str, str]]) -> str:
    """
    LLM recipient_roles/todos에서 식별 가능한 원문 단서를 결합한다.

    Args:
        rows: recipient_roles 목록
        todos: recipient_todos 목록

    Returns:
        결합된 단서 텍스트
    """
    parts: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        parts.append(str(row.get("recipient") or "").strip())
        parts.append(str(row.get("evidence") or "").strip())
    for row in todos:
        if not isinstance(row, dict):
            continue
        parts.append(str(row.get("recipient") or "").strip())
        parts.append(str(row.get("todo") or "").strip())
        parts.append(str(row.get("due_date_basis") or "").strip())
    return " ".join([item for item in parts if item])


def _extract_recipient_candidates(text: str) -> list[dict[str, str]]:
    """
    텍스트에서 수신자 후보(이름/이메일) 목록을 추출한다.

    Args:
        text: 원문 텍스트

    Returns:
        후보 목록
    """
    normalized_text = str(text or "").replace("&lt;", "<").replace("&gt;", ">")
    candidates: list[dict[str, str]] = []
    seen_emails: set[str] = set()
    for matched in PERSON_EMAIL_PAIR_PATTERN.finditer(normalized_text):
        raw_name = str(matched.group(1) or "").strip()
        email = str(matched.group(2) or "").strip().lower()
        if not email or email in seen_emails:
            continue
        seen_emails.add(email)
        candidates.append({"name": _normalize_person_label(raw_name), "email": email})
    for email in EMAIL_PATTERN.findall(normalized_text):
        lowered = str(email or "").strip().lower()
        if not lowered or lowered in seen_emails:
            continue
        seen_emails.add(lowered)
        candidates.append({"name": "", "email": lowered})
    return candidates


def _resolve_stakeholder_name(raw_name: str, evidence: str, candidates: list[dict[str, str]]) -> str:
    """
    LLM 원문 recipient 값을 표시용 관계자 이름으로 정규화한다.

    Args:
        raw_name: LLM recipient 원문
        evidence: LLM evidence 원문
        candidates: 텍스트에서 추출된 이름/이메일 후보

    Returns:
        정규화된 표시 문자열
    """
    normalized = _normalize_person_label(raw_name)
    direct_email = _first_email(text=" ".join([raw_name, evidence]))
    if direct_email:
        return _display_name_from_email(candidates=candidates, email=direct_email)
    if normalized and not _is_domain_only_token(normalized):
        return normalized
    email_from_evidence = _first_email(text=evidence)
    if email_from_evidence:
        return _display_name_from_email(candidates=candidates, email=email_from_evidence)
    return ""


def _normalize_person_label(raw_name: str) -> str:
    """
    사람 표시 문자열에서 조직/불필요 토큰을 제거한다.

    Args:
        raw_name: 원문 이름 문자열

    Returns:
        정리된 표시 이름(없으면 빈 문자열)
    """
    value = str(raw_name or "").replace("&lt;", "<").replace("&gt;", ">").strip()
    if not value:
        return ""
    email = _first_email(text=value)
    if email:
        return email
    value = re.sub(r"^\s*[@\-\*]+", "", value).strip()
    value = re.sub(r"^(?:to|cc|from|참조)\s*[:：]\s*", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\([^)]*\)", "", value).strip()
    value = value.split("/", 1)[0].strip()
    value = re.sub(r"\s+", " ", value).strip()
    if _is_domain_only_token(value):
        return ""
    return value


def _is_domain_only_token(token: str) -> bool:
    """
    토큰이 도메인 단편(예: sk, skcc)인지 판단한다.

    Args:
        token: 검사 대상 토큰

    Returns:
        도메인 단편이면 True
    """
    normalized = str(token or "").strip().lower()
    return bool(normalized) and normalized in DOMAIN_ONLY_TOKENS


def _first_email(text: str) -> str:
    """
    텍스트에서 첫 이메일을 추출한다.

    Args:
        text: 원문 텍스트

    Returns:
        첫 이메일(없으면 빈 문자열)
    """
    matched = EMAIL_PATTERN.search(str(text or ""))
    if not matched:
        return ""
    return str(matched.group(1) or "").strip().lower()


def _display_name_from_email(candidates: list[dict[str, str]], email: str) -> str:
    """
    후보 목록에서 이메일과 일치하는 사람 표시 이름을 반환한다.

    Args:
        candidates: 이름/이메일 후보
        email: 찾을 이메일

    Returns:
        이름 우선, 없으면 이메일
    """
    target = str(email or "").strip().lower()
    if not target:
        return ""
    for item in candidates:
        if not isinstance(item, dict):
            continue
        candidate_email = str(item.get("email") or "").strip().lower()
        if candidate_email != target:
            continue
        candidate_name = str(item.get("name") or "").strip()
        if candidate_name:
            return candidate_name
        return target
    return target
