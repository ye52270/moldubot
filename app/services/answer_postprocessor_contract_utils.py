from __future__ import annotations

import ast
import json
import re
import unicodedata
from typing import Any

from app.core.logging_config import get_logger
from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_summary import (
    extract_summary_lines,
    is_explicit_line_summary_request,
    resolve_summary_line_target,
    sanitize_summary_lines,
    split_headline_and_detail,
)
from app.services.mail_text_utils import select_salient_summary_sentences

logger = get_logger("app.services.answer_postprocessor")
LOG_EVIDENCE_MAX_CHARS = 56
LOG_EVIDENCE_POINT_MAX_CHARS = 128


def parse_llm_response_contract(raw_answer: Any, log_failures: bool = True) -> LLMResponseContract | None:
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
    direct_payload = _try_load_direct_payload(text=sanitized)
    if isinstance(direct_payload, dict):
        try:
            return LLMResponseContract.model_validate(direct_payload)
        except Exception:
            pass
    json_candidates = _extract_json_object_candidates(text=sanitized)
    if not json_candidates:
        if log_failures:
            logger.warning(
                "answer_postprocess.json_parse_failed: reason=json_object_not_found answer_length=%s",
                len(stripped),
            )
        return None
    contract = _parse_contract_from_candidates(
        json_candidates=json_candidates,
        answer_length=len(stripped),
        log_failures=log_failures,
    )
    if contract is not None:
        return contract
    if log_failures:
        logger.warning(
            "answer_postprocess.json_parse_failed: reason=schema_validation_error answer_length=%s",
            len(stripped),
        )
    return None


def _try_load_direct_payload(text: str) -> dict[str, Any] | None:
    """
    후보 추출 전에 본문 전체를 JSON 객체로 직접 파싱한다.

    Args:
        text: 코드펜스 제거 후 텍스트

    Returns:
        파싱된 dict 또는 None
    """
    normalized = str(text or "").strip()
    if not normalized.startswith("{"):
        return None
    try:
        loaded = _load_json_candidate(candidate=normalized)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _extract_text_for_contract_parse(raw_answer: Any) -> str:
    """
    모델 원문 입력에서 JSON 파싱 대상 텍스트를 추출한다.

    Args:
        raw_answer: 모델 원문(str/list/dict)

    Returns:
        JSON 파싱 대상 텍스트
    """
    if isinstance(raw_answer, str):
        text = str(raw_answer)
        recovered = _recover_text_from_python_literal_string(raw_text=text)
        return recovered if recovered else text
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


def _recover_text_from_python_literal_string(raw_text: str) -> str:
    """
    파이썬 literal 문자열(`{'type': 'text', 'text': '...'}`)에서 text 블록을 복원한다.

    Args:
        raw_text: 문자열화된 원본 content

    Returns:
        복원된 text 블록. 복원 실패 시 빈 문자열
    """
    normalized = str(raw_text or "").strip()
    if not normalized:
        return ""
    has_content_shape = ("'type':" in normalized or '"type":' in normalized) and (
        "'text':" in normalized or '"text":' in normalized
    )
    if not has_content_shape:
        return ""
    try:
        parsed = ast.literal_eval(normalized)
    except (SyntaxError, ValueError):
        return ""
    extracted = _extract_text_for_contract_parse(raw_answer=parsed)
    if not extracted or extracted.strip() == normalized:
        return ""
    return extracted


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
    source = str(text or "")
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


def _parse_contract_from_candidates(
    json_candidates: list[str],
    answer_length: int,
    log_failures: bool = True,
) -> LLMResponseContract | None:
    """
    JSON 후보 목록에서 응답 계약(`format_type`)을 우선으로 파싱한다.

    Args:
        json_candidates: JSON 객체 후보 목록
        answer_length: 원본 응답 길이(로그용)

    Returns:
        파싱 성공 시 계약 객체, 실패 시 None
    """
    parsed_payloads: list[dict[str, Any]] = []
    decode_error_count = 0
    for candidate in json_candidates:
        try:
            loaded = _load_json_candidate(candidate=candidate)
        except json.JSONDecodeError as exc:
            decode_error_count += 1
            logger.info(
                "answer_postprocess.json_decode_detail: pos=%s msg=%s candidate_len=%s preview=%s",
                getattr(exc, "pos", -1),
                str(exc),
                len(candidate),
                _build_candidate_preview(candidate=candidate),
            )
            continue
        if isinstance(loaded, dict):
            parsed_payloads.append(loaded)
    if not parsed_payloads:
        if log_failures:
            logger.warning(
                "answer_postprocess.json_parse_failed: reason=json_decode_error answer_length=%s",
                answer_length,
            )
        return None
    preferred_payloads = [payload for payload in parsed_payloads if "format_type" in payload]
    ordered_payloads = preferred_payloads + [payload for payload in parsed_payloads if payload not in preferred_payloads]
    for payload in ordered_payloads:
        try:
            return LLMResponseContract.model_validate(payload)
        except Exception:
            continue
    if decode_error_count > 0 and log_failures:
        logger.warning(
            "answer_postprocess.json_parse_partial_failure: decode_errors=%s answer_length=%s",
            decode_error_count,
            answer_length,
        )
    return None


def _load_json_candidate(candidate: str) -> dict[str, Any] | list[Any] | Any:
    """
    JSON 후보 문자열을 관용적으로 파싱한다.

    Args:
        candidate: JSON 문자열 후보

    Returns:
        파싱된 JSON 객체

    Raises:
        json.JSONDecodeError: 파싱 실패 시
    """
    cleaned = _sanitize_json_candidate(candidate=candidate)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = _repair_common_json_issues(text=cleaned)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            unwrapped = _unwrap_double_braces(text=repaired)
            try:
                return json.loads(unwrapped)
            except json.JSONDecodeError:
                retried = _decode_escaped_json_candidate(text=unwrapped)
                return json.loads(retried)


def _sanitize_json_candidate(candidate: str) -> str:
    """
    JSON 파싱 전 제어문자/BOM을 정리한다.

    Args:
        candidate: 원본 후보 문자열

    Returns:
        정리된 문자열
    """
    text = str(candidate or "").replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
    return _remove_invisible_unicode_controls(text=text)


def _remove_invisible_unicode_controls(text: str) -> str:
    """
    JSON 파싱을 깨뜨릴 수 있는 보이지 않는 유니코드 제어문자를 제거한다.

    Args:
        text: 입력 문자열

    Returns:
        제어문자가 제거된 문자열
    """
    kept_chars: list[str] = []
    for char in str(text or ""):
        category = unicodedata.category(char)
        if category in ("Cf", "Cs", "Co", "Cn"):
            continue
        kept_chars.append(char)
    return "".join(kept_chars)


def _repair_common_json_issues(text: str) -> str:
    """
    흔한 JSON 오류(후행 콤마)를 보정한다.

    Args:
        text: 정리된 JSON 후보 문자열

    Returns:
        보정된 문자열
    """
    repaired = re.sub(r",(\s*[}\]])", r"\1", str(text or ""))
    return _escape_invalid_backslashes(text=repaired)


def _escape_invalid_backslashes(text: str) -> str:
    """
    JSON 문자열 내 유효하지 않은 백슬래시 이스케이프를 보정한다.

    Args:
        text: JSON 후보 문자열

    Returns:
        보정된 문자열
    """
    source = str(text or "")
    if "\\" not in source:
        return source
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", source)


def _decode_escaped_json_candidate(text: str) -> str:
    """
    이스케이프된 JSON 텍스트(`{\\n \"k\":...}` 등)를 1회 복원한다.

    Args:
        text: JSON 후보 문자열

    Returns:
        복원된 JSON 후보 문자열
    """
    candidate = str(text or "").strip()
    if not candidate:
        return candidate
    if candidate.startswith('"') and candidate.endswith('"'):
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            decoded = ""
        if isinstance(decoded, str):
            candidate = decoded.strip()
    if "\\n" not in candidate and '\\"' not in candidate and "\\t" not in candidate:
        return candidate
    return (
        candidate.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
    )


def _unwrap_double_braces(text: str) -> str:
    """
    응답이 `{{...}}` 형태로 감싸진 경우 외곽 중괄호 1쌍을 제거한다.

    Args:
        text: JSON 후보 문자열

    Returns:
        언랩된 문자열(조건 미충족 시 원본)
    """
    candidate = str(text or "").strip()
    if not (candidate.startswith("{{") and candidate.endswith("}}")):
        return candidate
    inner = candidate[1:-1].strip()
    if inner.startswith("{") and inner.endswith("}"):
        return inner
    return candidate


def _build_candidate_preview(candidate: str, limit: int = 120) -> str:
    """
    JSON decode 실패 로그용 후보 문자열 프리뷰를 생성한다.

    Args:
        candidate: JSON 후보 문자열
        limit: 미리보기 최대 길이

    Returns:
        이스케이프 포함 축약 문자열
    """
    text = repr(str(candidate or ""))
    if len(text) <= limit:
        return text
    return text[:limit] + "...(truncated)"


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
        contract.major_points = _enrich_major_points_with_log_evidence(
            major_points=existing,
            mail_context=mail_context,
        )
        return
    supplements = _build_standard_summary_supplements(
        mail_context=mail_context,
        line_target=max(3, min_points),
    )
    merged = _merge_unique_lines(primary=existing, supplements=supplements, limit=6)
    if merged:
        contract.major_points = _enrich_major_points_with_log_evidence(
            major_points=merged,
            mail_context=mail_context,
        )


def _enrich_major_points_with_log_evidence(
    major_points: list[str],
    mail_context: dict[str, Any],
) -> list[str]:
    """
    구조화된 에러 로그가 있을 때 주요 내용 세부에 근거 문구를 보강한다.

    Args:
        major_points: 현재 주요 내용 목록
        mail_context: 메일 컨텍스트

    Returns:
        로그 근거가 반영된 주요 내용 목록
    """
    evidence_lines = _extract_structured_log_evidence_lines(mail_context=mail_context)
    if not evidence_lines:
        return major_points
    enriched: list[str] = []
    evidence_index = 0
    for point in major_points:
        text = str(point or "").strip()
        if not text:
            continue
        if evidence_index >= len(evidence_lines):
            enriched.append(text)
            continue
        if not _should_attach_log_evidence(point=text):
            enriched.append(text)
            continue
        headline, detail = split_headline_and_detail(line=text)
        base_detail = detail or "추가 로그 확인 필요"
        evidence = evidence_lines[evidence_index]
        evidence_index += 1
        candidate = f"{headline} — {base_detail} (근거: {evidence})"
        if len(candidate) > LOG_EVIDENCE_POINT_MAX_CHARS:
            clipped = evidence[:30].rstrip()
            candidate = f"{headline} — {base_detail} (근거: {clipped})"
        enriched.append(candidate)
    return enriched


def _should_attach_log_evidence(point: str) -> bool:
    """
    주요 내용 문장에 로그 근거를 덧붙일지 판별한다.

    Args:
        point: 주요 내용 문장

    Returns:
        보강 대상이면 True
    """
    normalized = str(point or "").strip()
    if not normalized:
        return False
    if "근거:" in normalized:
        return False
    detail = split_headline_and_detail(line=normalized)[1]
    target_text = detail or normalized
    generic_tokens = ("확인 필요", "점검 필요", "요청 필요", "가능성", "미상", "추가 확인")
    return any(token in target_text for token in generic_tokens)


def _extract_structured_log_evidence_lines(mail_context: dict[str, Any]) -> list[str]:
    """
    본문 발췌에서 구조화된 에러 로그 문구를 추출한다.

    Args:
        mail_context: 메일 컨텍스트

    Returns:
        정규화된 로그 근거 문구 목록
    """
    body_excerpt = str(mail_context.get("body_excerpt") or "").strip()
    if not body_excerpt:
        return []
    candidates: list[str] = []
    for raw_line in body_excerpt.splitlines():
        line = str(raw_line or "").strip()
        if not line:
            continue
        if not _looks_like_structured_log_line(line=line):
            continue
        compact = _compact_log_evidence_line(line=line)
        if compact and compact not in candidates:
            candidates.append(compact)
        if len(candidates) >= 3:
            break
    return candidates


def _looks_like_structured_log_line(line: str) -> bool:
    """
    라인이 에러 로그 형태인지 판별한다.

    Args:
        line: 검사 대상 라인

    Returns:
        구조화된 로그 라인이면 True
    """
    lowered = str(line or "").strip().lower()
    if not lowered:
        return False
    has_error_token = any(token in lowered for token in ("error", "exception", "failed", "traceback", "ldap"))
    if not has_error_token:
        return False
    has_structure = bool(
        re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", lowered)
        or ("[" in lowered and "]" in lowered)
        or ("{" in lowered and "}" in lowered)
    )
    return has_structure


def _compact_log_evidence_line(line: str) -> str:
    """
    장문 로그 1줄을 카드용 짧은 근거 문구로 축약한다.

    Args:
        line: 원본 로그 라인

    Returns:
        축약된 근거 문구
    """
    normalized = re.sub(r"\s+", " ", str(line or "")).strip()
    normalized = re.sub(r"\[B@[0-9A-Za-z]+", "[id]", normalized)
    class_match = re.search(r"\[([A-Za-z0-9_.]+)\]\s*(.*)$", normalized)
    class_name = ""
    message = normalized
    if class_match:
        class_name = class_match.group(1).split(".")[-1].strip()
        message = class_match.group(2).strip()
    else:
        error_match = re.search(r"(ERROR|WARN|INFO)\s+(.*)$", normalized, flags=re.IGNORECASE)
        if error_match:
            message = str(error_match.group(2) or "").strip()
    message = message.replace("The following record does not have a groupname", "groupname 누락")
    cn_match = re.search(r"cn[:=]\s*([A-Za-z0-9._-]+)", normalized, flags=re.IGNORECASE)
    if cn_match:
        cn_value = cn_match.group(1)
        if cn_value not in message:
            message = f"{message} (cn={cn_value})"
    message = re.sub(r"\{[^}]+\}", "", message).strip()
    if class_name:
        message = f"{class_name} {message}".strip()
    return message[:LOG_EVIDENCE_MAX_CHARS].rstrip()


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
