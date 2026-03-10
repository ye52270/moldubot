from __future__ import annotations

import re

from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_summary import extract_summary_lines, normalize_multiline_text, sanitize_summary_lines


def resolve_subject_text(contract: LLMResponseContract) -> str:
    """
    제목(메일 subject) 텍스트를 우선순위 기반으로 반환한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        제목 텍스트
    """
    subject = resolve_basic_info_value(contract=contract, keys=("제목", "subject"), default="")
    if subject and subject not in ("제목 정보 없음", "-"):
        return subject
    from_answer = _extract_subject_from_answer(answer=contract.answer)
    if from_answer:
        return from_answer
    title = str(contract.title or "").strip()
    if title and title not in ("제목 정보 없음", "-"):
        return title
    return "제목 정보 없음"


def resolve_basic_info_value(contract: LLMResponseContract, keys: tuple[str, ...], default: str = "-") -> str:
    """
    basic_info에서 키 우선순위로 값을 조회한다.

    Args:
        contract: JSON 계약 객체
        keys: 우선순위 키 목록
        default: 미존재 시 기본값

    Returns:
        조회된 값 또는 기본 문자열
    """
    lowered = {str(key).strip().lower(): str(value).strip() for key, value in contract.basic_info.items()}
    for key in keys:
        value = lowered.get(str(key).strip().lower(), "")
        if value:
            return value
    return default


def resolve_core_issue_text(contract: LLMResponseContract) -> str:
    """
    핵심 이슈 문장을 우선순위 기반으로 결정한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        핵심 이슈 텍스트
    """
    if contract.core_issue:
        return contract.core_issue
    major_points = resolve_major_points(contract=contract)
    if major_points:
        return major_points[0]
    summary_lines = sanitize_summary_lines(lines=list(contract.summary_lines))
    if summary_lines:
        return summary_lines[0]
    extracted = extract_summary_lines(answer=contract.answer)
    if extracted:
        return extracted[0]
    return ""


def resolve_major_points(contract: LLMResponseContract) -> list[str]:
    """
    주요 내용 bullet 목록을 정규화해 반환한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        주요 내용 목록
    """
    major_points = _filter_major_points_quality(lines=sanitize_summary_lines(lines=list(contract.major_points)))
    if major_points:
        return major_points[:6]
    from_summary = _filter_major_points_quality(lines=sanitize_summary_lines(lines=list(contract.summary_lines)))
    if from_summary:
        return from_summary[:6]
    return _filter_major_points_quality(lines=extract_summary_lines(answer=contract.answer))[:6]


def resolve_required_actions(contract: LLMResponseContract) -> list[str]:
    """
    조치 필요 사항 목록을 정규화해 반환한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        조치 필요 사항 목록
    """
    required_actions = _sanitize_action_lines(lines=list(contract.required_actions))
    if required_actions:
        return required_actions[:5]
    from_actions = _sanitize_action_lines(lines=list(contract.action_items))
    if from_actions:
        return from_actions[:5]
    return []


def _sanitize_action_lines(lines: list[str]) -> list[str]:
    """
    조치 필요 사항 라인을 실행 항목 중심으로 정규화한다.

    Args:
        lines: 정규화 전 액션 라인 목록

    Returns:
        정규화된 액션 라인 목록
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for line in lines:
        item = str(line or "").strip()
        item = re.sub(r"^[-*]\s*", "", item)
        item = re.sub(r"^\d+[.)]\s*", "", item).strip()
        if not item:
            continue
        compare_key = _normalize_compare_key(text=item)
        if not compare_key or compare_key in seen:
            continue
        seen.add(compare_key)
        normalized.append(item)
    return normalized


def resolve_one_line_summary(contract: LLMResponseContract, major_points: list[str]) -> str:
    """
    1줄 요약 문장을 정규화해 반환한다.

    Args:
        contract: JSON 계약 객체
        major_points: 주요 내용 목록

    Returns:
        1줄 요약 텍스트
    """
    if contract.one_line_summary:
        candidate = str(contract.one_line_summary or "").strip()
        if not _is_near_duplicate_text(candidate=candidate, existing=major_points):
            return candidate
        return ""
    if major_points:
        return major_points[0]
    return normalize_multiline_text(text=contract.answer).split("\n")[0] if contract.answer else ""


def _extract_subject_from_answer(answer: str) -> str:
    """
    자유 텍스트 answer에서 제목 후보를 추출한다.

    Args:
        answer: 모델 자유 텍스트

    Returns:
        제목 후보 텍스트
    """
    text = str(answer or "")
    if not text:
        return ""
    patterns = (
        r"(?:subject|제목)\s*[:：]\s*([^\n]+)",
        r"(?:subject|제목)\s+([^\n]+)",
        r"(?:메일\s*보고서)\s*[:：]\s*([^\n]+)",
    )
    for pattern in patterns:
        matched = re.search(pattern, text, flags=re.IGNORECASE)
        if matched:
            return matched.group(1).strip()
    return ""


def _filter_major_points_quality(lines: list[str]) -> list[str]:
    """
    주요 내용 후보에서 질문형/저품질 라인을 제거한다.

    Args:
        lines: 원본 후보 라인 목록

    Returns:
        필터링된 라인 목록
    """
    filtered: list[str] = []
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        if _looks_like_raw_mail_dump_line(text=text):
            continue
        condensed = text.replace(" ", "")
        if condensed.endswith("?") or condensed.endswith("？"):
            continue
        if condensed.endswith("라고하는데요") or condensed.endswith("어떻게할까요"):
            continue
        if _is_near_duplicate_text(candidate=text, existing=filtered):
            continue
        filtered.append(text)
    return filtered


def _looks_like_raw_mail_dump_line(text: str) -> bool:
    """
    메일 원문/표 조각이 그대로 섞인 저품질 라인인지 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        원문 덩어리/헤더 조각/표 조각으로 판단되면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return True
    lowered = normalized.lower()
    if any(token in lowered for token in ("from:", "sent:", "to:", "cc:", "subject:")):
        return True
    if any(token in lowered for token in ("http://", "https://", "license", "ad/mail+ad", "시스템항목", "비고금액")):
        return True
    if lowered.count("@") >= 2:
        return True
    if "..." in normalized and len(normalized) > 90:
        return True
    if len(normalized) >= 180:
        return True
    if len(normalized) >= 130 and (" - " in normalized or " — " in normalized):
        return True
    if len(normalized) >= 90 and ". - " in normalized:
        return True
    if len(normalized) >= 90 and normalized.count(". ") >= 2 and "—" not in normalized:
        return True
    if normalized.count("  ") >= 2:
        return True
    return False


def _is_near_duplicate_text(candidate: str, existing: list[str]) -> bool:
    """
    후보 문장이 기존 목록과 의미상 거의 동일한지 비교한다.

    Args:
        candidate: 후보 문장
        existing: 기존 문장 목록

    Returns:
        유사 중복이면 True
    """
    candidate_key = _normalize_compare_key(text=candidate)
    if not candidate_key:
        return True
    for line in existing:
        if _normalize_compare_key(text=line) == candidate_key:
            return True
    return False


def _normalize_compare_key(text: str) -> str:
    """
    중복 판정용 비교 키를 만든다.

    Args:
        text: 원문 문장

    Returns:
        비교 키
    """
    value = str(text or "").strip().lower()
    if not value:
        return ""
    return (
        value.replace(" ", "")
        .replace("—", "")
        .replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace(",", "")
        .replace(";", "")
        .replace("|", "")
        .replace("(", "")
        .replace(")", "")
    )
