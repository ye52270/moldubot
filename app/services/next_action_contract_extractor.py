from __future__ import annotations

import json
import re
from typing import Any

from app.services.answer_postprocessor_contract_utils import parse_llm_response_contract
from app.services.next_action_recommender import resolve_next_actions_from_action_ids

_ACTION_TAG_PATTERN = re.compile(
    r"\[\[\s*suggested_action_ids\s*:\s*(?P<body>.*?)\s*\]\]",
    flags=re.IGNORECASE | re.DOTALL,
)


def resolve_next_actions_from_model_content(
    raw_model_content: Any,
    tool_payload: dict[str, Any],
) -> list[dict[str, str]]:
    """
    모델 원문에서 suggested action 식별자를 복원해 UI 액션 카드로 변환한다.

    우선순위:
    1) JSON 계약(`suggested_action_ids`)
    2) freeform 메타 태그(`[[suggested_action_ids:...]]`)

    Args:
        raw_model_content: 모델 원문 content(str/list/dict)
        tool_payload: 최신 tool payload

    Returns:
        UI 표시용 next action 목록
    """
    contract = parse_llm_response_contract(raw_answer=raw_model_content, log_failures=False)
    if contract is not None:
        actions = resolve_next_actions_from_action_ids(
            action_ids=list(contract.suggested_action_ids),
            tool_payload=tool_payload,
        )
        if actions:
            return actions

    text = _extract_text(raw_model_content=raw_model_content)
    tag_action_ids = _extract_action_ids_from_tag(text=text)
    if not tag_action_ids:
        return []
    return resolve_next_actions_from_action_ids(
        action_ids=tag_action_ids,
        tool_payload=tool_payload,
    )


def _extract_text(raw_model_content: Any) -> str:
    """
    모델 content 객체를 태그 탐지용 문자열로 평탄화한다.

    Args:
        raw_model_content: 모델 원문 content(str/list/dict)

    Returns:
        평탄화된 문자열
    """
    if isinstance(raw_model_content, str):
        return str(raw_model_content)
    if isinstance(raw_model_content, dict):
        text = raw_model_content.get("text")
        if isinstance(text, str):
            return text
        content = raw_model_content.get("content")
        if isinstance(content, str):
            return content
        return json.dumps(raw_model_content, ensure_ascii=False)
    if isinstance(raw_model_content, list):
        lines: list[str] = []
        for item in raw_model_content:
            chunk = _extract_text(raw_model_content=item)
            if chunk:
                lines.append(chunk)
        return "\n".join(lines)
    return str(raw_model_content or "")


def _extract_action_ids_from_tag(text: str) -> list[str]:
    """
    freeform 메타 태그에서 action_id 목록을 추출한다.

    Args:
        text: 모델 원문 문자열

    Returns:
        정규화된 action_id 목록
    """
    source = str(text or "")
    if not source:
        return []
    matched = _ACTION_TAG_PATTERN.search(source)
    if matched is None:
        return []
    body = str(matched.group("body") or "").strip()
    if not body:
        return []
    if body.startswith("[") and body.endswith("]"):
        parsed = _parse_json_array(text=body)
        if parsed:
            return parsed
    return _parse_csv_action_ids(text=body)


def _parse_json_array(text: str) -> list[str]:
    """
    JSON 배열 형식 action_id 목록을 파싱한다.

    Args:
        text: JSON 배열 문자열

    Returns:
        정규화된 action_id 목록
    """
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return _normalize_action_ids(raw_items=loaded)


def _parse_csv_action_ids(text: str) -> list[str]:
    """
    콤마 구분 action_id 목록을 파싱한다.

    Args:
        text: 콤마 구분 문자열

    Returns:
        정규화된 action_id 목록
    """
    parts = [segment.strip() for segment in str(text or "").split(",")]
    return _normalize_action_ids(raw_items=parts)


def _normalize_action_ids(raw_items: list[Any]) -> list[str]:
    """
    action_id 문자열 목록을 정규화하고 중복 제거한다.

    Args:
        raw_items: 원본 action_id 목록

    Returns:
        정규화된 action_id 목록
    """
    normalized: list[str] = []
    for item in raw_items:
        action_id = str(item or "").strip().lower()
        if not action_id:
            continue
        if not re.fullmatch(r"[a-z0-9_]{2,64}", action_id):
            continue
        if action_id in normalized:
            continue
        normalized.append(action_id)
        if len(normalized) >= 3:
            break
    return normalized
