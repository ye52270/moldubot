from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.person_identity_parser import normalize_person_identity


@dataclass(frozen=True)
class PersonRoleRow:
    """인물별 역할 추정 행 데이터.

    Attributes:
        person: 사람 이름/주소
        audience: 구분(To/CC/본문)
        role: 추정 역할
        evidence: 근거 텍스트
    """

    person: str
    audience: str
    role: str
    evidence: str


def normalize_person_token(token: str) -> str:
    """
    이름/주소 토큰을 표시용 문자열로 정규화한다.

    Args:
        token: 원본 토큰

    Returns:
        정규화 문자열
    """
    normalized = normalize_person_identity(token=token)
    if len(normalized) > 60:
        return normalized[:60].strip()
    return normalized


def dedupe_person_rows(rows: list[PersonRoleRow]) -> list[PersonRoleRow]:
    """
    인물/구분 단위로 중복 행을 제거한다.

    Args:
        rows: 원본 역할 행 목록

    Returns:
        중복 제거된 역할 행 목록
    """
    deduped: list[PersonRoleRow] = []
    seen: set[str] = set()
    for row in rows:
        key = f"{row.person.lower()}::{row.audience}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def render_markdown_table(title: str, headers: list[str], rows: list[list[str]], empty_message: str) -> str:
    """
    테이블 스펙을 Markdown 표 문자열로 렌더링한다.

    Args:
        title: 테이블 제목
        headers: 컬럼 헤더
        rows: 행 데이터
        empty_message: 빈 데이터 안내 문구

    Returns:
        Markdown 표 문자열
    """
    lines = [title, ""]
    if not rows:
        lines.append(empty_message)
        return "\n".join(lines).strip()

    header_line = "| " + " | ".join(sanitize_table_cell(value=header) for header in headers) + " |"
    divider_line = "|" + "|".join("---" for _ in headers) + "|"
    lines.extend([header_line, divider_line])

    for row in rows:
        padded = list(row)[: len(headers)]
        while len(padded) < len(headers):
            padded.append("-")
        row_line = "| " + " | ".join(sanitize_table_cell(value=value) for value in padded) + " |"
        lines.append(row_line)
    return "\n".join(lines).strip()


def sanitize_table_cell(value: object) -> str:
    """
    Markdown 표 셀 문자를 이스케이프한다.

    Args:
        value: 셀 값

    Returns:
        안전한 셀 문자열
    """
    text = str(value or "-").replace("\n", " ").strip()
    if not text:
        return "-"
    escaped = text.replace("|", "\\|")
    return re.sub(r"\s+", " ", escaped)

