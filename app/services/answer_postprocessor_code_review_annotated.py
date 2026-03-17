from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.answer_postprocessor_code_review import (
    _build_analysis_lines,
    _detect_language,
    _extract_code_snippet,
    _is_code_review_request,
)

SEGMENT_MAX_COUNT = 4
SEGMENT_LINE_COUNT = 6


@dataclass(frozen=True)
class SegmentReview:
    """
    코드 구간 주석 리뷰 결과를 담는 데이터 구조.
    """

    comment: str
    improvement: str


def render_current_mail_code_review_annotated_response(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    코드 리뷰 요청을 핵심 코드 구간 + 주석 포맷으로 렌더링한다.

    Args:
        user_message: 사용자 입력
        answer: 모델 원문 응답
        tool_payload: 마지막 도구 payload

    Returns:
        렌더링된 문자열. 대상 질의가 아니면 빈 문자열
    """
    if not _is_code_review_request(user_message=user_message):
        return ""
    context = tool_payload.get("mail_context") if isinstance(tool_payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    body_code_excerpt = str(context.get("body_code_excerpt") or "").strip()
    body_excerpt = str(context.get("body_excerpt") or "").strip()
    code = _extract_code_snippet(text=body_code_excerpt or body_excerpt)
    if not code:
        return "코드 스니펫이 없습니다."
    language = _detect_language(code=code)
    analysis_lines = _normalize_analysis_lines(
        lines=_build_analysis_lines(answer=answer, language=language)
    )
    segments = _build_code_segments(code=code)
    blocks = ["## 코드 분석", "", *[f"- {line}" for line in analysis_lines], "", "## 주석 리뷰 (핵심 구간)", ""]
    for index, segment in enumerate(segments, start=1):
        segment_review = _build_segment_review(segment=segment, language=language)
        blocks.extend(
            [
                f"### 구간 {index}",
                "",
                f"```{language}",
                segment,
                "```",
                f"- 주석: {segment_review.comment}",
                f"- 개선: {segment_review.improvement}",
                "",
            ]
        )
    return "\n".join(blocks).strip()


def _build_code_segments(code: str) -> list[str]:
    """
    코드 본문을 고정 길이 핵심 구간 목록으로 분할한다.

    Args:
        code: 코드 문자열

    Returns:
        코드 구간 목록
    """
    lines = [line for line in str(code or "").split("\n") if line.strip()]
    segments: list[str] = []
    for start in range(0, len(lines), SEGMENT_LINE_COUNT):
        if len(segments) >= SEGMENT_MAX_COUNT:
            break
        chunk = lines[start : start + SEGMENT_LINE_COUNT]
        if chunk:
            segments.append("\n".join(chunk).strip())
    return segments


def _build_segment_review(segment: str, language: str) -> SegmentReview:
    """
    코드 구간의 위험 신호를 기준으로 주석/개선 문구를 생성한다.

    Args:
        segment: 코드 구간
        language: 코드 언어

    Returns:
        구간 리뷰 결과
    """
    text = str(segment or "").lower()
    if "password" in text or "passwd" in text:
        return SegmentReview(
            comment="비밀번호 처리 구간입니다. 로그/브라우저 저장/평문 전송 노출 여부를 점검해야 합니다.",
            improvement="비밀번호 필드에 autocomplete 정책을 지정하고 서버 로그 마스킹을 적용하세요.",
        )
    if "onclick" in text or "script" in text:
        return SegmentReview(
            comment="클라이언트 이벤트 처리 구간입니다. 스크립트 인젝션 및 권한 검증 누락 여부를 점검해야 합니다.",
            improvement="이벤트 핸들러에서 직접 문자열 조합을 피하고 서버측 권한 검증을 강제하세요.",
        )
    if "<input" in text and language in {"jsp", "html"}:
        return SegmentReview(
            comment="사용자 입력 구간입니다. 서버측 유효성 검증 및 XSS 방어 적용 여부를 확인해야 합니다.",
            improvement="입력값 길이/포맷 화이트리스트 검증과 출력 이스케이프를 기본 정책으로 적용하세요.",
        )
    if "isauthn" in text or "session" in text:
        return SegmentReview(
            comment="인증/세션 분기 구간입니다. 세션 고정 방지와 권한 경계 검증이 필요합니다.",
            improvement="로그인 성공 시 세션 재발급을 적용하고 권한 체크를 서버 단에서 재확인하세요.",
        )
    if "<ac:warning" in text or "msghtml" in text:
        return SegmentReview(
            comment="메시지 출력 구간입니다. 사용자 제어 문자열이 포함될 경우 XSS 전파 가능성이 있습니다.",
            improvement="경고/오류 메시지 렌더링 시 HTML sanitize 및 escape 정책을 명시적으로 적용하세요.",
        )
    return SegmentReview(
        comment="핵심 로직 구간입니다. 입력-처리-출력 흐름의 예외 처리와 보안 검증을 확인해야 합니다.",
        improvement="예외 처리 분기에서 사용자 메시지와 운영 로그를 분리하고 민감 정보 노출을 차단하세요.",
    )


def _normalize_analysis_lines(lines: list[str]) -> list[str]:
    """
    코드 분석 라인에서 헤딩/중복 노이즈를 제거한다.

    Args:
        lines: 원본 분석 라인

    Returns:
        정제된 분석 라인
    """
    normalized: list[str] = []
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        lowered = line.lower()
        if lowered in {"코드 분석", "코드 리뷰"}:
            continue
        if line in normalized:
            continue
        normalized.append(line)
    if normalized:
        return normalized[:3]
    return [
        "로그인/인증 관련 UI 및 입력 처리 흐름을 담당하는 코드입니다.",
        "입력값 검증, 세션 처리, CSRF/XSS 방어 적용 여부를 우선 점검해야 합니다.",
    ]
