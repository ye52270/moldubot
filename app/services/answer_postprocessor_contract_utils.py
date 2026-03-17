from __future__ import annotations

import json
import re
from typing import Any

from app.core.logging_config import get_logger
from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_summary import (
    extract_summary_lines,
    is_explicit_line_summary_request,
    resolve_summary_line_target,
    sanitize_summary_lines,
)
from app.services.mail_text_utils import select_salient_summary_sentences

logger = get_logger("app.services.answer_postprocessor")


def parse_llm_response_contract(
    raw_answer: Any,
    log_failures: bool = True,
    allow_json_repair: bool = True,
) -> LLMResponseContract | None:
    """
    모델 원문에서 JSON 객체를 추출해 계약 모델로 파싱한다.

    Args:
        raw_answer: 모델 원문 출력(str/list/dict)

    Returns:
        파싱 성공 시 LLMResponseContract, 실패 시 None
    """
    normalized_text = _extract_text_for_contract_parse(raw_answer=raw_answer)
    stripped = normalized_text.strip()
    if not stripped:
        if log_failures:
            logger.warning("answer_postprocess.json_parse_failed: reason=empty_answer answer_length=0")
        return None
    sanitized = _strip_json_code_fence(text=stripped)
    json_candidates = _extract_json_object_candidates(text=sanitized)
    if not json_candidates:
        if log_failures:
            logger.warning(
                "answer_postprocess.json_parse_failed: reason=json_object_not_found answer_length=%s",
                len(stripped),
            )
        return None
    decode_failed = False
    for candidate in json_candidates:
        loaded, had_decode_error = _load_json_candidate_simple(
            candidate=candidate,
            allow_json_repair=allow_json_repair,
        )
        decode_failed = decode_failed or had_decode_error
        if not isinstance(loaded, dict):
            continue
        if not any(key in loaded for key in ("format_type", "reply_draft", "answer", "summary_lines")):
            continue
        try:
            return LLMResponseContract.model_validate(loaded)
        except Exception:
            continue
    if log_failures:
        if decode_failed:
            logger.warning(
                "answer_postprocess.json_parse_failed: reason=json_decode_error answer_length=%s",
                len(stripped),
            )
            return None
        logger.warning(
            "answer_postprocess.json_parse_failed: reason=schema_validation_error answer_length=%s",
            len(stripped),
        )
    return None


def _extract_text_for_contract_parse(raw_answer: Any) -> str:
    """
    모델 원문 입력에서 JSON 파싱 대상 텍스트를 추출한다.

    Args:
        raw_answer: 모델 원문(str/list/dict)

    Returns:
        JSON 파싱 대상 텍스트
    """
    if isinstance(raw_answer, str):
        return str(raw_answer)
    if isinstance(raw_answer, dict):
        return _extract_text_from_content_block(block=raw_answer)
    if isinstance(raw_answer, list):
        texts = [
            text
            for item in raw_answer
            for text in [_extract_text_from_content_block(block=item)]
            if text
        ]
        return "\n".join(texts).strip()
    return str(raw_answer or "")


def _extract_text_from_content_block(block: Any) -> str:
    """
    단일 content block에서 텍스트를 추출한다.

    Args:
        block: 모델 content block(dict/str/기타)

    Returns:
        텍스트 블록 값
    """
    if isinstance(block, str):
        return block.strip()
    if not isinstance(block, dict):
        return ""
    if "text" in block and isinstance(block.get("text"), str):
        return str(block.get("text") or "").strip()
    content = block.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def augment_contract_with_tool_payload(
    user_message: str,
    contract: LLMResponseContract,
    tool_payload: dict[str, Any],
) -> LLMResponseContract:
    """
    도구 payload를 사용해 계약 필드를 보강한다.

    Args:
        user_message: 사용자 원문
        contract: 파싱된 계약 객체
        tool_payload: 직전 tool 결과 payload

    Returns:
        보강된 계약 객체
    """
    if not tool_payload:
        return contract
    mail_context = tool_payload.get("mail_context")
    if not isinstance(mail_context, dict):
        mail_context = {}
    _fill_basic_summary_fields(contract=contract, mail_context=mail_context)
    _fill_line_summary_fields(
        user_message=user_message,
        contract=contract,
        mail_context=mail_context,
    )
    _fill_standard_summary_major_points(
        contract=contract,
        mail_context=mail_context,
        min_points=3,
    )
    return contract


def _strip_json_code_fence(text: str) -> str:
    """
    JSON 코드펜스 래핑을 제거한다.

    Args:
        text: 원본 텍스트

    Returns:
        코드펜스 제거 텍스트
    """
    stripped = str(text or "").strip()
    if not stripped:
        return stripped
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", flags=re.IGNORECASE)
    match = fence_pattern.search(stripped)
    if not match:
        return stripped
    inner = str(match.group(1) or "").strip()
    return inner or stripped


def _extract_json_object_candidates(text: str) -> list[str]:
    """
    텍스트에서 JSON 객체 후보 문자열 목록을 추출한다.

    Args:
        text: 원본 텍스트

    Returns:
        JSON 객체 문자열 목록. 찾지 못하면 빈 목록
    """
    source = str(text or "").strip()
    if not source:
        return []
    candidates: list[str] = []
    start_index = -1
    depth = 0
    in_string = False
    escape_next = False
    for index, char in enumerate(source):
        if escape_next:
            escape_next = False
            continue
        if char == "\\" and in_string:
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if char == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start_index >= 0:
                candidates.append(source[start_index : index + 1].strip())
                start_index = -1
    return [candidate for candidate in candidates if candidate]

def _load_json_candidate_simple(
    candidate: str,
    allow_json_repair: bool,
) -> tuple[dict[str, Any] | list[Any] | Any, bool]:
    """
    JSON 후보 문자열을 단순 규칙으로 파싱한다.

    Args:
        candidate: JSON 문자열 후보

    Returns:
        파싱된 JSON 객체 또는 None
    """
    cleaned = str(candidate or "").replace("\ufeff", "").strip()
    if not cleaned:
        return (None, False)
    try:
        return (json.loads(cleaned), False)
    except json.JSONDecodeError:
        if allow_json_repair:
            repaired = re.sub(r",(\s*[}\]])", r"\1", cleaned)
            try:
                return (json.loads(repaired), False)
            except json.JSONDecodeError:
                pass
        return (None, True)


def _fill_basic_summary_fields(contract: LLMResponseContract, mail_context: dict[str, Any]) -> None:
    """
    표준 요약 필드(제목/basic_info)를 mail_context로 보강한다.

    Args:
        contract: 계약 객체
        mail_context: 도구 메일 컨텍스트
    """
    subject = str(mail_context.get("subject") or "").strip()
    sender = str(mail_context.get("from_address") or "").strip()
    date_text = str(mail_context.get("received_date") or "").strip()
    route_flow = str(mail_context.get("route_flow") or "").strip()
    if not contract.title and subject:
        contract.title = subject
    if subject and not contract.basic_info.get("제목"):
        contract.basic_info["제목"] = subject
    if sender and not contract.basic_info.get("최종 발신자"):
        contract.basic_info["최종 발신자"] = sender
    if date_text and not contract.basic_info.get("날짜"):
        contract.basic_info["날짜"] = date_text
    if route_flow:
        # route_flow는 메일 본문 헤더 기반으로 생성한 서버값을 우선 신뢰한다.
        contract.basic_info["커뮤니케이션 흐름"] = route_flow


def _fill_line_summary_fields(
    user_message: str,
    contract: LLMResponseContract,
    mail_context: dict[str, Any],
) -> None:
    """
    명시 줄수 요약 요청에서 라인 후보를 tool payload 기반으로 보강한다.

    Args:
        user_message: 사용자 입력
        contract: 계약 객체
        mail_context: 메일 컨텍스트
    """
    if not is_explicit_line_summary_request(user_message=user_message):
        return
    model_lines = sanitize_summary_lines(lines=list(contract.summary_lines))
    if model_lines:
        contract.summary_lines = model_lines
        logger.info(
            "answer_postprocess.explicit_line_source: source=model model_lines=%s grounded_lines=%s target=%s",
            len(model_lines),
            0,
            resolve_summary_line_target(user_message=user_message),
        )
        return

    target = resolve_summary_line_target(user_message=user_message)
    grounded_lines = _build_tool_grounded_summary_lines(
        mail_context=mail_context,
        line_target=target,
    )
    if grounded_lines:
        contract.summary_lines = grounded_lines
        logger.info(
            "answer_postprocess.explicit_line_source: source=grounded model_lines=%s grounded_lines=%s target=%s",
            len(model_lines),
            len(grounded_lines),
            target,
        )


def _build_tool_grounded_summary_lines(mail_context: dict[str, Any], line_target: int) -> list[str]:
    """
    mail_context 본문 발췌 기반으로 핵심 요약 라인을 생성한다.

    Args:
        mail_context: 도구 메일 컨텍스트
        line_target: 목표 줄 수

    Returns:
        선별된 요약 라인 목록
    """
    candidates: list[str] = []
    summary_text = str(mail_context.get("summary_text") or "").strip()
    if summary_text:
        candidates.extend(extract_summary_lines(answer=summary_text))
    body_excerpt = str(mail_context.get("body_excerpt") or "").strip()
    if body_excerpt:
        candidates.extend(
            select_salient_summary_sentences(
                text=body_excerpt,
                line_target=line_target * 2,
            )
        )
    return sanitize_summary_lines(lines=candidates)[: max(1, line_target)]


def _fill_standard_summary_major_points(
    contract: LLMResponseContract,
    mail_context: dict[str, Any],
    min_points: int,
) -> None:
    """
    표준 요약의 주요 내용을 tool 근거로 보강한다.

    Args:
        contract: 계약 객체
        mail_context: 도구 메일 컨텍스트
        min_points: 보강 목표 최소 개수
    """
    if contract.format_type not in ("standard_summary", "detailed_summary"):
        return
    existing = sanitize_summary_lines(lines=list(contract.major_points))
    if len(existing) >= max(1, min_points):
        evidence_line = _build_structured_log_evidence_line(mail_context=mail_context)
        if evidence_line and all("근거:" not in item for item in existing):
            existing = [*existing[:5], evidence_line]
        contract.major_points = existing
        return
    supplements = _build_standard_summary_supplements(
        mail_context=mail_context,
        line_target=max(3, min_points),
    )
    evidence_line = _build_structured_log_evidence_line(mail_context=mail_context)
    if evidence_line:
        supplements.append(evidence_line)
    merged = _merge_unique_lines(primary=existing, supplements=supplements, limit=6)
    if merged:
        contract.major_points = merged


def _build_standard_summary_supplements(mail_context: dict[str, Any], line_target: int) -> list[str]:
    """
    표준 요약 주요 내용 보강 라인을 생성한다.

    Args:
        mail_context: 도구 메일 컨텍스트
        line_target: 목표 라인 수

    Returns:
        보강용 요약 라인 목록
    """
    summary_text = str(mail_context.get("summary_text") or "").strip()
    if not summary_text:
        return []
    candidates = sanitize_summary_lines(lines=extract_summary_lines(answer=summary_text))
    return candidates[: max(1, line_target)]


def _build_structured_log_evidence_line(mail_context: dict[str, Any]) -> str:
    """
    본문 로그 발췌에서 구조화 근거 라인 1개를 추출한다.

    Args:
        mail_context: 메일 컨텍스트

    Returns:
        근거 라인 문자열. 추출 실패 시 빈 문자열
    """
    body_excerpt = str(mail_context.get("body_excerpt") or "").strip()
    if not body_excerpt:
        return ""
    for line in body_excerpt.splitlines():
        normalized = str(line or "").strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if "ldapgroupattributesmapper" in lowered and "groupname" in lowered:
            return "근거: LDAPGroupAttributesMapper 로그에서 groupname 누락 오류가 확인됨"
        if "ERROR" in normalized or "Exception" in normalized or "LDAPGroupAttributesMapper" in normalized:
            compact = " ".join(normalized.split())
            return f"근거: {compact[:100]}"
    return ""


def _merge_unique_lines(primary: list[str], supplements: list[str], limit: int) -> list[str]:
    """
    기존/보강 라인을 중복 없이 병합한다.

    Args:
        primary: 기존 라인 목록
        supplements: 보강 라인 목록
        limit: 최대 반환 개수

    Returns:
        중복 제거된 병합 라인 목록
    """
    merged: list[str] = []
    seen: set[str] = set()
    for line in list(primary) + list(supplements):
        normalized = _normalize_line_for_merge(line=line)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(str(line or "").strip())
        if len(merged) >= max(1, limit):
            break
    return merged


def _normalize_line_for_merge(line: str) -> str:
    """
    라인 병합 비교용 정규화 문자열을 생성한다.

    Args:
        line: 원본 라인

    Returns:
        비교용 문자열
    """
    text = str(line or "").strip().lower()
    if not text:
        return ""
    return (
        text.replace(" ", "")
        .replace("—", "")
        .replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace(",", "")
        .replace(";", "")
        .replace("|", "")
    )
