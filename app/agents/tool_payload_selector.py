from __future__ import annotations

import json
from typing import Any, Mapping

from langchain_core.messages import ToolMessage


def extract_preferred_tool_payload_from_messages(
    messages: list[Any],
    preferred_action: str = "",
) -> dict[str, Any]:
    """
    메시지 목록에서 선호 action 우선 규칙으로 tool payload를 추출한다.

    Args:
        messages: 에이전트 메시지 목록
        preferred_action: 우선 선택할 action 이름(예: `mail_search`)

    Returns:
        추출된 tool payload. 선호 action이 없으면 최신 payload를 반환한다.
    """
    normalized_preferred = str(preferred_action or "").strip().lower()
    latest_payload: dict[str, Any] = {}
    matched_payloads: list[dict[str, Any]] = []
    for message in reversed(messages):
        payload = parse_tool_payload_from_message(message=message)
        if not payload:
            continue
        if not latest_payload:
            latest_payload = payload
        if normalized_preferred and _is_matching_action(payload=payload, expected_action=normalized_preferred):
            matched_payloads.append(payload)
    if normalized_preferred and matched_payloads:
        if normalized_preferred == "mail_search":
            return _merge_mail_search_payloads(payloads=list(reversed(matched_payloads)))
        return matched_payloads[0]
    return latest_payload


def _merge_mail_search_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """
    동일 턴의 다중 mail_search payload를 병합한다.

    Args:
        payloads: 시간순 mail_search payload 목록

    Returns:
        results/aggregated_summary/count를 합친 단일 payload
    """
    if not payloads:
        return {}
    merged = dict(payloads[0])
    merged_results: list[dict[str, Any]] = []
    merged_summary: list[str] = []
    query_summaries: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()
    for payload in payloads:
        query_text = str(payload.get("query") or "").strip()
        per_query_lines: list[str] = []
        raw_query_summaries = payload.get("query_summaries")
        if isinstance(raw_query_summaries, list):
            for row in raw_query_summaries:
                if not isinstance(row, dict):
                    continue
                row_query = str(row.get("query") or "").strip()
                row_lines = row.get("lines")
                if not isinstance(row_lines, list):
                    continue
                normalized_row_lines = [str(item or "").strip() for item in row_lines if str(item or "").strip()]
                if row_query and normalized_row_lines:
                    query_summaries.append({"query": row_query, "lines": normalized_row_lines})
        results = payload.get("results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                message_id = str(item.get("message_id") or "").strip()
                if message_id and message_id in seen_message_ids:
                    continue
                if message_id:
                    seen_message_ids.add(message_id)
                merged_results.append(item)
        aggregated_summary = payload.get("aggregated_summary")
        if isinstance(aggregated_summary, list):
            for line in aggregated_summary:
                text = str(line or "").strip()
                if text:
                    merged_summary.append(text)
                    per_query_lines.append(text)
        if not per_query_lines and isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                summary_text = str(item.get("summary_text") or "").strip()
                if summary_text:
                    per_query_lines.append(summary_text)
        if query_text and per_query_lines:
            query_summaries.append({"query": query_text, "lines": per_query_lines})
    merged["action"] = "mail_search"
    merged["results"] = merged_results
    if merged_results:
        merged["count"] = len(merged_results)
    else:
        merged["count"] = max(
            [int(payload.get("count") or 0) for payload in payloads if isinstance(payload.get("count"), int)] or [0]
        )
    merged["aggregated_summary"] = merged_summary
    merged["query_summaries"] = query_summaries
    merged_query = ", ".join([str(item.get("query") or "").strip() for item in query_summaries if item.get("query")])[:240]
    if not merged_query:
        merged_query = ", ".join([str(item.get("query") or "").strip() for item in payloads if str(item.get("query") or "").strip()])[
            :240
        ]
    merged["query"] = merged_query
    return merged


def parse_tool_payload_from_message(message: object) -> dict[str, Any]:
    """
    단일 메시지에서 tool payload를 파싱한다.

    Args:
        message: ToolMessage 또는 role=tool dict 메시지

    Returns:
        payload dict. 파싱 실패 시 빈 dict
    """
    if isinstance(message, ToolMessage):
        return parse_tool_payload_content(content=message.content)
    if isinstance(message, Mapping):
        role = str(message.get("role", "")).strip().lower()
        if role == "tool":
            return parse_tool_payload_content(content=message.get("content"))
    return {}


def parse_tool_payload_content(content: object) -> dict[str, Any]:
    """
    tool message content를 payload dict로 파싱한다.

    Args:
        content: tool content 객체

    Returns:
        payload dict. 파싱 실패 시 빈 dict
    """
    if isinstance(content, dict):
        return dict(content)
    if isinstance(content, list):
        for item in content:
            payload = parse_tool_payload_content(content=item)
            if payload:
                return payload
        return {}
    text = str(content or "").strip()
    if not text:
        return {}
    decoded = _try_decode_json_object(text=text)
    if decoded is None:
        candidate = _extract_first_json_object(text=text)
        if not candidate:
            return {}
        decoded = _try_decode_json_object(text=candidate)
        if decoded is None:
            return {}
    return decoded


def _try_decode_json_object(text: str) -> dict[str, Any] | None:
    """
    문자열을 JSON 객체로 파싱한다.

    Args:
        text: 파싱 대상 문자열

    Returns:
        JSON 객체면 dict, 아니면 None
    """
    try:
        decoded = json.loads(str(text or "").strip())
    except json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_first_json_object(text: str) -> str:
    """
    텍스트에서 첫 JSON 객체 문자열을 추출한다.

    Args:
        text: 원본 텍스트

    Returns:
        추출된 JSON 객체 문자열. 없으면 빈 문자열
    """
    source = str(text or "")
    start = source.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    return ""


def _is_matching_action(payload: Mapping[str, object], expected_action: str) -> bool:
    """
    payload action이 기대 action과 일치하는지 확인한다.

    Args:
        payload: tool payload dict
        expected_action: 기대 action 소문자 문자열

    Returns:
        action 일치 시 True
    """
    action = str(payload.get("action", "")).strip().lower()
    return action == expected_action
