from __future__ import annotations

import json
import re


def is_reply_draft_request(user_message: str) -> bool:
    """
    사용자 질의가 회신/답장 본문 초안 생성 요청인지 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        회신 초안 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if "답변하기" in compact:
        return True
    has_reply = any(token in compact for token in ("회신", "답장", "reply", "답변"))
    has_draft = any(token in compact for token in ("초안", "본문", "작성", "생성"))
    return has_reply and has_draft


def normalize_reply_draft_text(text: str) -> str:
    """
    회신 본문 텍스트를 빈 줄 단락을 유지한 채 정규화한다.

    Args:
        text: 회신 초안 텍스트

    Returns:
        단락 구분이 보존된 정규화 텍스트
    """
    normalized = str(text or "")
    normalized = (
        normalized.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )
    lines = [line.strip() for line in normalized.split("\n")]
    joined = "\n".join(lines)
    return joined.replace("\n\n\n", "\n\n").strip()


def select_reply_body_from_contract(reply_draft: str, answer: str) -> str:
    """
    계약 파싱 성공 시 회신 본문 필드를 우선순위로 선택한다.

    Args:
        reply_draft: 계약의 `reply_draft`(alias 포함) 필드
        answer: 계약의 일반 `answer` 필드

    Returns:
        선택된 회신 본문 문자열. 없으면 빈 문자열
    """
    primary = normalize_reply_draft_text(text=reply_draft)
    if primary:
        return primary
    fallback = normalize_reply_draft_text(text=answer)
    return fallback


def recover_reply_draft_from_json_text(user_message: str, answer: str) -> str:
    """
    회신 초안 질의에서 JSON 파싱 실패 시 draft 필드를 텍스트로 복구한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 응답 원문

    Returns:
        복구된 회신 본문. 대상이 아니거나 복구 실패 시 빈 문자열
    """
    source = str(answer or "").strip()
    if not source:
        return ""
    if not _should_attempt_reply_body_recovery(user_message=user_message, source=source):
        return ""
    encoded = _extract_encoded_json_string(source=source, key="reply_draft")
    if not encoded:
        encoded = _extract_encoded_json_string(source=source, key="draft_answer")
    if not encoded:
        encoded = _extract_encoded_json_string(source=source, key="additional_body")
    if not encoded:
        encoded = _extract_encoded_json_string(source=source, key="reply_body")
    if not encoded:
        encoded = _extract_encoded_json_string(source=source, key="response_body")
    if not encoded:
        encoded = _extract_encoded_json_string(source=source, key="answer")
    if not encoded:
        return ""
    try:
        decoded = json.loads(f'"{encoded}"')
    except Exception:
        decoded = encoded.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    return normalize_reply_draft_text(text=str(decoded or ""))


def _extract_encoded_json_string(source: str, key: str) -> str:
    """
    문자열 JSON 텍스트에서 특정 key의 encoded 문자열 값을 추출한다.

    Args:
        source: JSON 원문 문자열
        key: 추출할 키 이름

    Returns:
        encoded 문자열. 없으면 빈 문자열
    """
    matched = re.search(
        rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"',
        source,
        flags=re.IGNORECASE,
    )
    if not matched:
        return ""
    return str(matched.group(1) or "").strip()


def _should_attempt_reply_body_recovery(user_message: str, source: str) -> bool:
    """
    회신 본문 복구 시도를 수행할지 결정한다.

    Args:
        user_message: 사용자 입력 원문
        source: 모델 응답 원문

    Returns:
        회신 요청이거나 회신 본문 키가 존재하면 True
    """
    if is_reply_draft_request(user_message=user_message):
        return True
    lowered = str(source or "").lower()
    return any(
        key in lowered
        for key in (
            '"reply_draft"',
            '"draft_answer"',
            '"additional_body"',
            '"reply_body"',
            '"response_body"',
        )
    )


def recover_reply_draft_from_plain_text(user_message: str, answer: str) -> str:
    """
    회신 초안 질의에서 plain text(설명 + 코드펜스) 응답을 본문만으로 복구한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 응답 원문

    Returns:
        복구된 회신 본문. 대상이 아니거나 복구 실패 시 빈 문자열
    """
    if not is_reply_draft_request(user_message=user_message):
        return ""
    source = str(answer or "").strip()
    if not source:
        return ""
    fenced_blocks = list(re.finditer(r"```(?!json)([^\n]*)\n([\s\S]*?)```", source, flags=re.IGNORECASE))
    for block in fenced_blocks:
        body = normalize_reply_draft_text(text=str(block.group(2) or ""))
        if body:
            return body
    json_fence = re.search(r"```json[\s\S]*?```", source, flags=re.IGNORECASE)
    if not json_fence:
        return ""
    prefix = source[: json_fence.start()].strip()
    if not prefix:
        return ""
    cleaned = _strip_reply_preamble_lines(text=prefix)
    return normalize_reply_draft_text(text=cleaned)


def _strip_reply_preamble_lines(text: str) -> str:
    """
    회신 초안 안내 문구/구분선을 제거하고 본문 라인만 남긴다.

    Args:
        text: 원문 텍스트

    Returns:
        회신 본문 후보 텍스트
    """
    source = str(text or "").strip()
    if not source:
        return ""
    lines = [line.strip() for line in source.splitlines()]
    kept: list[str] = []
    for line in lines:
        lowered = line.lower()
        if not line or line in {"---", "—", "–"}:
            continue
        if "회신 메일 본문 초안" in line:
            continue
        if lowered.startswith("다음은 바로 보낼 수 있는 회신 본문"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()
