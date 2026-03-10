from __future__ import annotations

import re

from app.core.intent_rules import extract_summary_line_target, is_mail_summary_skill_query
from app.services.answer_postprocessor_line_filters import (
    is_header_like_line,
    is_low_value_summary_line,
    is_meta_summary_line,
    is_section_header_line,
    is_signature_noise_line,
)
from app.services.answer_postprocessor_summary_utils import is_near_duplicate

ORIGINAL_USER_INPUT_MARKER = "원본 사용자 입력:"


def extract_original_user_message(user_message: str) -> str:
    """
    의도 컨텍스트 주입 문자열에서 실제 사용자 원문을 복원한다.

    Args:
        user_message: 원본 또는 주입된 사용자 입력 문자열

    Returns:
        사용자 원문 문자열
    """
    text = str(user_message or "").strip()
    marker_index = text.rfind(ORIGINAL_USER_INPUT_MARKER)
    if marker_index < 0:
        return text
    return text[marker_index + len(ORIGINAL_USER_INPUT_MARKER) :].strip()


def is_summary_request(user_message: str) -> bool:
    """
    사용자 요청이 요약 작업인지 판별한다.

    Args:
        user_message: 사용자 입력 문자열

    Returns:
        요약 요청이면 True
    """
    return "요약" in str(user_message or "")


def is_current_mail_summary_request(user_message: str) -> bool:
    """
    현재메일 대상 요약 질의인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        현재메일 요약 질의면 True
    """
    text = str(user_message or "")
    compact = re.sub(r"\s+", "", text)
    return ("현재메일" in compact and "요약" in compact) or is_mail_summary_skill_query(user_message=text)


def is_explicit_line_summary_request(user_message: str) -> bool:
    """
    N줄 요약처럼 줄 수가 명시된 요청인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        줄 수 명시 요약 요청이면 True
    """
    return bool(re.search(r"\d+\s*줄", str(user_message or "")))


def resolve_summary_line_target(user_message: str) -> int:
    """
    요약 라인 타깃을 계산하고 상세 요약 요청에 최소값을 적용한다.

    Args:
        user_message: 사용자 입력

    Returns:
        라인 타깃 수
    """
    target = extract_summary_line_target(user_message=user_message)
    if re.search(r"(자세히|상세)", str(user_message or "")):
        return max(target, 8)
    return target


def is_report_request(user_message: str) -> bool:
    """
    사용자 요청이 보고서 작업인지 판별한다.

    Args:
        user_message: 사용자 입력 문자열

    Returns:
        보고서 요청이면 True
    """
    return "보고서" in str(user_message or "")


def normalize_multiline_text(text: str) -> str:
    """
    다중 줄 텍스트의 공백과 빈 줄을 정규화한다.

    Args:
        text: 원본 텍스트

    Returns:
        정규화된 텍스트
    """
    lines = [line.strip() for line in str(text or "").replace("\r", "\n").split("\n")]
    non_empty = [line for line in lines if line]
    return "\n".join(non_empty).strip()


def extract_summary_lines(answer: str) -> list[str]:
    """
    모델 응답에서 요약 라인 후보를 추출한다.

    Args:
        answer: 모델 응답 텍스트

    Returns:
        요약 라인 후보 목록
    """
    text = str(answer or "").strip()
    if not text:
        return []

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    extracted: list[str] = []
    for line in lines:
        normalized = re.sub(r"^[-*]\s*", "", line)
        normalized = re.sub(r"^\d+[.)]\s*", "", normalized)
        normalized = normalized.strip()
        if is_section_header_line(line=normalized):
            continue
        if is_meta_summary_line(line=normalized):
            continue
        if is_header_like_line(line=normalized):
            continue
        if is_signature_noise_line(line=normalized):
            continue
        if is_low_value_summary_line(line=normalized):
            continue
        if normalized:
            extracted.append(normalized)

    if extracted:
        return extracted

    sentence_candidates = re.split(r"(?<=[.!?])\s+", text)
    return [
        item.strip()
        for item in sentence_candidates
        if item
        and item.strip()
        and not is_section_header_line(line=item.strip())
        and not is_meta_summary_line(line=item.strip())
        and not is_header_like_line(line=item.strip())
        and not is_signature_noise_line(line=item.strip())
        and not is_low_value_summary_line(line=item.strip())
    ]


def render_summary_lines_for_request(user_message: str, lines: list[str]) -> str:
    """
    사용자 질의 유형에 맞춰 요약 라인 렌더 포맷을 선택한다.

    Args:
        user_message: 사용자 입력
        lines: 요약 라인 목록

    Returns:
        렌더링된 요약 문자열
    """
    if is_mail_search_summary_request(user_message=user_message):
        return render_mail_search_summary_lines(lines=lines)
    if is_current_mail_summary_request(user_message=user_message) and is_explicit_line_summary_request(
        user_message=user_message
    ):
        return render_emphasis_numbered_lines(lines=lines)
    return render_summary_lines(lines=lines)


def is_mail_search_summary_request(user_message: str) -> bool:
    """
    메일 조회/검색 기반 요약 요청인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        조회/검색 요약 요청이면 True
    """
    text = str(user_message or "").strip()
    if not text:
        return False
    has_mail_context = "메일" in text
    has_search_intent = ("조회" in text) or ("검색" in text)
    return has_mail_context and has_search_intent


def render_mail_search_summary_lines(lines: list[str]) -> str:
    """
    조회/검색 요약 라인을 강조 헤더 + 불릿 목록 형식으로 렌더링한다.

    Args:
        lines: 요약 라인 목록

    Returns:
        강조 헤더 + 하위 불릿 형태의 요약 문자열
    """
    subpoints = _collect_mail_search_summary_items(lines=lines)
    if not subpoints:
        return "## 📌 주요 내용\n- 확인 가능한 요약이 없습니다."
    rendered = [_render_mail_search_bullet_with_subline(point=point) for point in subpoints]
    return "## 📌 주요 내용\n" + "\n".join(rendered)


def _collect_mail_search_summary_items(lines: list[str]) -> list[str]:
    """
    조회/검색 요약 라인에서 메일당 1줄 불릿 항목을 수집한다.

    Args:
        lines: 원본 요약 라인 목록

    Returns:
        중복 제거된 불릿 텍스트 목록
    """
    candidates = [str(line or "").strip() for line in lines if str(line or "").strip()]
    return _dedupe_preserving_order(lines=candidates)


def _render_mail_search_bullet_with_subline(point: str) -> str:
    """
    조회 요약 1개 항목을 메인 불릿 + 하이픈 서브라인 문자열로 렌더링한다.

    Args:
        point: 원본 요약 문장

    Returns:
        렌더링 문자열
    """
    text = str(point or "").strip()
    if not text:
        return "- 확인 가능한 요약이 없습니다."
    return f"- {text}"


def _dedupe_preserving_order(lines: list[str]) -> list[str]:
    """
    순서를 유지하며 중복 라인을 제거한다.

    Args:
        lines: 중복 가능 라인 목록

    Returns:
        중복 제거 라인 목록
    """
    unique: list[str] = []
    for line in lines:
        item = str(line or "").strip()
        if not item or item in unique:
            continue
        unique.append(item)
    return unique


def render_emphasis_numbered_lines(lines: list[str]) -> str:
    """
    번호 + 핵심 강조 + 설명 스타일로 요약 라인을 렌더링한다.

    Args:
        lines: 요약 라인 목록

    Returns:
        렌더링 문자열
    """
    rendered: list[str] = []
    for index, line in enumerate(lines, start=1):
        headline, detail = split_headline_and_detail(line=line)
        emphasized = ensure_bold_phrase(text=headline)
        if detail:
            rendered.append(f"{index}. {emphasized} — {detail}")
            continue
        rendered.append(f"{index}. {emphasized}")
    return "\n\n".join(rendered)


def split_headline_and_detail(line: str) -> tuple[str, str]:
    """
    문장을 핵심(headline)과 설명(detail)으로 분리한다.

    Args:
        line: 원본 문장

    Returns:
        (핵심, 설명) 튜플
    """
    text = str(line or "").strip()
    delimiters = (" — ", " - ", ": ")
    for delimiter in delimiters:
        if delimiter in text:
            left, right = text.split(delimiter, 1)
            return left.strip(), right.strip()
    connective_match = re.match(r"^(.*?(?:으나|그러나|하지만|때문에|하여))\s+(.*)$", text)
    if connective_match:
        return connective_match.group(1).strip(), connective_match.group(2).strip()
    if len(text) >= 28:
        split_index = find_balanced_space_index(text=text)
        if split_index > 0:
            return text[:split_index].strip(), text[split_index + 1 :].strip()
    return text, ""


def find_balanced_space_index(text: str) -> int:
    """
    긴 문장을 headline/detail로 나눌 적절한 공백 인덱스를 찾는다.

    Args:
        text: 원본 문장

    Returns:
        분리 공백 인덱스. 찾지 못하면 -1
    """
    midpoint = len(text) // 2
    left = text.rfind(" ", 12, midpoint + 1)
    right = text.find(" ", midpoint, len(text) - 6)
    if left < 0 and right < 0:
        return -1
    if left < 0:
        return right
    if right < 0:
        return left
    return left if (midpoint - left) <= (right - midpoint) else right


def ensure_bold_phrase(text: str) -> str:
    """
    핵심 구문에 마크다운 bold를 적용한다.

    Args:
        text: 원본 구문

    Returns:
        강조 적용 문자열
    """
    normalized = str(text or "").strip()
    if not normalized:
        return normalized
    if normalized.startswith("**") and normalized.endswith("**"):
        return normalized
    return f"**{normalized}**"


def sanitize_summary_lines(lines: list[str]) -> list[str]:
    """
    요약 라인 목록을 헤더/메타/중복 제거 규칙으로 정규화한다.

    Args:
        lines: 정규화 전 요약 라인 목록

    Returns:
        정규화된 요약 라인 목록
    """
    normalized: list[str] = []
    for line in lines:
        item = str(line or "").strip()
        item = re.sub(r"^[-*]\s*", "", item)
        item = re.sub(r"^\d+[.)]\s*", "", item).strip()
        if not item:
            continue
        if is_section_header_line(line=item):
            continue
        if is_meta_summary_line(line=item):
            continue
        if is_header_like_line(line=item):
            continue
        if is_signature_noise_line(line=item):
            continue
        if is_low_value_summary_line(line=item):
            continue
        if is_near_duplicate(existing=normalized, candidate=item):
            continue
        normalized.append(item)
    return normalized


def render_summary_lines(lines: list[str]) -> str:
    """
    요약 라인 목록을 사용자 응답 텍스트로 렌더링한다.

    Args:
        lines: 요약 라인 목록

    Returns:
        번호 목록 형식의 요약 문자열
    """
    rendered_lines = [f"{idx}. {line}" for idx, line in enumerate(lines, start=1)]
    return "요약 결과:\n" + "\n".join(rendered_lines)
