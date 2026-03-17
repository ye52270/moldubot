from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.chat_eval_cases import CHAT_EVAL_CASES, ChatEvalCase

_QUESTION_HEADER_PATTERN = re.compile(r"^##\s*Q(?P<index>\d+)\.\s*(?P<query>.+?)\s*$")
_EXPECTATION_HEADER_PATTERN = re.compile(r"^\*\*기대\s*결과:\*\*\s*$")
_CURRENT_MAIL_QUERY_TOKENS: tuple[str, ...] = (
    "현재메일",
    "현재 메일",
    "이 메일",
    "이메일",
    "해당 메일",
    "이 견적",
    "해당 견적",
    "이 프로젝트",
    "해당 프로젝트",
)
_GLOBAL_MAIL_QUERY_TOKENS: tuple[str, ...] = (
    "전체메일",
    "전체 메일",
    "메일함 전체",
    "전체 메일함",
    "전체에서",
    "전체 검색",
    "최근 메일",
    "모든 메일",
)


def load_chat_eval_cases(cases_file: str | None = None) -> list[ChatEvalCase]:
    """
    chat-eval 케이스셋을 로드한다.

    Args:
        cases_file: 외부 케이스 파일 경로(`.md` 또는 `.json`)

    Returns:
        케이스 목록
    """
    normalized_path = str(cases_file or "").strip()
    if not normalized_path:
        return [dict(case) for case in CHAT_EVAL_CASES]
    path = Path(normalized_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(f"chat_eval_cases_file_not_found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".md":
        return parse_markdown_chat_eval_cases(markdown_text=path.read_text(encoding="utf-8"), file_stem=path.stem)
    if suffix == ".json":
        return parse_json_chat_eval_cases(raw_json=path.read_text(encoding="utf-8"))
    raise ValueError(f"unsupported_cases_file_extension: {suffix}")


def parse_markdown_chat_eval_cases(markdown_text: str, file_stem: str = "md") -> list[ChatEvalCase]:
    """
    markdown 기반 judge 테스트셋을 chat-eval 케이스로 변환한다.

    Args:
        markdown_text: markdown 문자열
        file_stem: case_id 접두어로 사용할 파일 stem

    Returns:
        변환된 케이스 목록
    """
    lines = [str(line or "").rstrip() for line in str(markdown_text or "").splitlines()]
    cases: list[ChatEvalCase] = []
    index = 0
    while index < len(lines):
        header_match = _QUESTION_HEADER_PATTERN.match(lines[index].strip())
        if not header_match:
            index += 1
            continue
        question_index = header_match.group("index")
        query = str(header_match.group("query") or "").strip()
        index += 1
        expectation_lines: list[str] = []
        while index < len(lines):
            current = lines[index].strip()
            if _QUESTION_HEADER_PATTERN.match(current):
                break
            if _EXPECTATION_HEADER_PATTERN.match(current):
                index += 1
                while index < len(lines):
                    row = lines[index].strip()
                    if not row:
                        index += 1
                        if expectation_lines:
                            break
                        continue
                    if _QUESTION_HEADER_PATTERN.match(row):
                        break
                    if row.startswith("---"):
                        index += 1
                        continue
                    normalized = _normalize_expectation_line(raw_line=row)
                    if normalized:
                        expectation_lines.append(normalized)
                    index += 1
                continue
            index += 1
        expectation = "; ".join(expectation_lines).strip()
        requires_current_mail = _is_current_mail_case(query=query)
        cases.append(
            {
                "case_id": f"{file_stem}-q{question_index}",
                "query": query,
                "expectation": expectation or "질문 의도에 맞는 정확한 답변을 제공해야 한다.",
                "requires_current_mail": requires_current_mail,
            }
        )
    if not cases:
        raise ValueError("chat_eval_markdown_parse_failed: no_cases_detected")
    return cases


def parse_json_chat_eval_cases(raw_json: str) -> list[ChatEvalCase]:
    """
    JSON 문자열을 chat-eval 케이스 목록으로 변환한다.

    Args:
        raw_json: 케이스 JSON 문자열

    Returns:
        케이스 목록
    """
    decoded = json.loads(str(raw_json or "").strip() or "[]")
    if not isinstance(decoded, list):
        raise ValueError("chat_eval_json_cases_must_be_array")
    cases: list[ChatEvalCase] = []
    for row in decoded:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "").strip()
        query = str(row.get("query") or "").strip()
        expectation = str(row.get("expectation") or "").strip()
        requires_current_mail = bool(row.get("requires_current_mail"))
        if not case_id or not query:
            continue
        cases.append(
            {
                "case_id": case_id,
                "query": query,
                "expectation": expectation or "질문 의도에 맞는 정확한 답변을 제공해야 한다.",
                "requires_current_mail": requires_current_mail,
            }
        )
    if not cases:
        raise ValueError("chat_eval_json_parse_failed: no_valid_cases")
    return cases


def _normalize_expectation_line(raw_line: str) -> str:
    """
    기대 결과 라인을 정규화한다.

    Args:
        raw_line: 원본 라인

    Returns:
        정규화 문자열
    """
    text = str(raw_line or "").strip()
    if not text:
        return ""
    for prefix in ("- ", "* ", "• "):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _is_current_mail_case(query: str) -> bool:
    """
    질의가 현재메일 컨텍스트를 요구하는지 판별한다.

    Args:
        query: 사용자 질의

    Returns:
        현재메일 케이스면 True
    """
    normalized_query = _normalize_query_for_scope(query=query)
    if not normalized_query:
        return False
    if _contains_any_token(text=normalized_query, tokens=_GLOBAL_MAIL_QUERY_TOKENS):
        return False
    return _contains_any_token(text=normalized_query, tokens=_CURRENT_MAIL_QUERY_TOKENS)


def _normalize_query_for_scope(query: str) -> str:
    """
    스코프 판정을 위한 질의 텍스트를 정규화한다.

    Args:
        query: 사용자 질의

    Returns:
        소문자/공백 정규화된 질의
    """
    normalized = str(query or "").lower().strip()
    return re.sub(r"\s+", " ", normalized)


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    """
    텍스트에 토큰 집합 중 하나라도 포함되는지 확인한다.

    Args:
        text: 검색 대상 텍스트
        tokens: 포함 여부를 검사할 토큰 목록

    Returns:
        하나 이상 포함되면 True
    """
    return any(token in text for token in tokens)
