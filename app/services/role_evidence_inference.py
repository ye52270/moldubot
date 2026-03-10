from __future__ import annotations

import re

from app.services.role_taxonomy_config import RoleTaxonomyConfig


def infer_role_from_line(line: str, taxonomy: RoleTaxonomyConfig) -> str:
    """본문 문장에서 역할을 추정한다.

    Args:
        line: 본문 한 줄
        taxonomy: 역할 taxonomy 설정

    Returns:
        역할 추정 문자열
    """
    lowered = str(line or "").lower()
    best_position: int | None = None
    best_role = ""
    for hint in taxonomy.role_hints:
        keyword = hint.keyword.lower()
        position = lowered.find(keyword)
        if position < 0:
            continue
        if best_position is None or position < best_position:
            best_position = position
            best_role = hint.role
    if best_role:
        return best_role
    return str(taxonomy.default_roles.get("unknown") or "역할 미상")


def normalize_evidence_line(line: str) -> str:
    """근거 문장을 테이블 셀 길이에 맞게 정규화한다.

    Args:
        line: 원본 근거 라인

    Returns:
        정규화된 근거 문자열
    """
    compact = re.sub(r"\s+", " ", str(line or "").strip())
    if len(compact) <= 90:
        return compact
    return compact[:89].rstrip() + "…"


def infer_role_evidence_for_person(
    person: str,
    body_text: str,
    taxonomy: RoleTaxonomyConfig,
    fallback_role: str,
    header_type: str,
) -> tuple[str, str]:
    """수신자/참조자 한 명에 대해 본문 기반 역할/근거를 추론한다.

    Args:
        person: 표시용 인물 식별자
        body_text: 본문 발췌 텍스트
        taxonomy: 역할 taxonomy 설정
        fallback_role: 단서 없음 fallback 역할
        header_type: to 또는 cc

    Returns:
        (역할, 근거) 튜플
    """
    lines = _find_person_lines(person=person, body_text=body_text)
    if not lines:
        return fallback_role, f"메일 헤더 {header_type.upper()}"
    best_line = _select_best_role_line(lines=lines, taxonomy=taxonomy)
    inferred_role = infer_role_from_line(line=best_line, taxonomy=taxonomy)
    unknown_role = str(taxonomy.default_roles.get("unknown") or "역할 미상")
    role = fallback_role if inferred_role == unknown_role else inferred_role
    return role, normalize_evidence_line(line=best_line)


def _find_person_lines(person: str, body_text: str) -> list[str]:
    """사람 식별자가 포함된 본문 라인을 찾는다.

    Args:
        person: 인물 식별자
        body_text: 본문 텍스트

    Returns:
        매칭된 본문 라인 목록
    """
    terms = _build_person_match_terms(person=person)
    if not terms:
        return []
    lines = [str(line).strip() for line in str(body_text or "").replace("\r", "\n").split("\n") if str(line).strip()]
    matched: list[str] = []
    for line in lines:
        if _is_header_line(line=line):
            continue
        lowered = line.lower()
        if any(term in lowered for term in terms):
            matched.append(line)
    return matched


def _is_header_line(line: str) -> bool:
    """헤더 블록 라인(To/Cc/From/Subject) 여부를 판별한다.

    Args:
        line: 본문 한 줄

    Returns:
        헤더 라인이면 True
    """
    lowered = str(line or "").strip().lower()
    return lowered.startswith(("to:", "cc:", "from:", "subject:", "sent:", "date:"))


def _build_person_match_terms(person: str) -> list[str]:
    """인물 매칭용 키워드 목록을 생성한다.

    Args:
        person: 인물 식별자

    Returns:
        소문자 키워드 목록
    """
    normalized = str(person or "").strip().lower()
    if not normalized:
        return []
    terms = [normalized]
    if "@" in normalized:
        local_part = normalized.split("@", maxsplit=1)[0].strip()
        if local_part and local_part not in terms:
            terms.append(local_part)
    compact = normalized.replace(" ", "")
    if compact and compact not in terms:
        terms.append(compact)
    return terms


def _select_best_role_line(lines: list[str], taxonomy: RoleTaxonomyConfig) -> str:
    """역할 단서가 가장 많은 라인을 선택한다.

    Args:
        lines: 후보 라인 목록
        taxonomy: 역할 taxonomy 설정

    Returns:
        대표 근거 라인
    """
    best_line = lines[0]
    best_score = -1
    for line in lines:
        lowered = str(line or "").lower()
        score = sum(1 for hint in taxonomy.role_hints if hint.keyword.lower() in lowered)
        if score > best_score:
            best_score = score
            best_line = line
    return best_line
