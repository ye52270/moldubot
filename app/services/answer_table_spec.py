from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from app.models.response_contracts import LLMResponseContract
from app.services.person_identity_parser import normalize_person_identity
from app.services.answer_table_spec_utils import (
    PersonRoleRow,
    dedupe_person_rows,
    normalize_person_token,
    render_markdown_table,
)
from app.services.recipient_roles_guard import sanitize_contract_recipient_roles
from app.services.recipient_todos_guard import sanitize_contract_recipient_todos
from app.services.role_evidence_inference import (
    infer_role_evidence_for_person,
    infer_role_from_line,
    normalize_evidence_line,
)
from app.services.role_taxonomy_config import RoleTaxonomyConfig, get_role_taxonomy

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KOREAN_NAME_PATTERN = re.compile(r"(?<![가-힣A-Za-z0-9])([가-힣]{2,4})\s*(?:님|책임|매니저|팀장|실장|PM|pm)")
ROLE_SCOPE_TO = "to"
ROLE_SCOPE_CC = "cc"
ROLE_SCOPE_BODY = "body"
ROLE_SCOPE_ALL = "all"
MAX_ROLE_ROWS = 12


@dataclass(frozen=True)
class TableSpec:
    """Markdown 테이블 렌더링 스펙.

    Attributes:
        title: 섹션 제목
        headers: 컬럼 헤더 목록
        rows: 행 목록
        empty_message: 데이터가 없을 때 대체 문구
    """

    title: str
    headers: list[str]
    rows: list[list[str]]
    empty_message: str


def is_current_mail_people_roles_table_request(user_message: str) -> bool:
    """현재메일 인물 역할 표 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        인물 역할 표 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    has_current_mail = "현재메일" in compact
    has_table = "표" in compact
    has_people = any(token in compact for token in ("수신자", "받는사람", "참조", "cc", "사람", "인물"))
    has_role = any(token in compact for token in ("역할", "담당"))
    return has_current_mail and has_table and has_people and has_role


def is_current_mail_recipient_todos_request(user_message: str) -> bool:
    """현재메일 수신자별 ToDo/마감기한 정리 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        수신자별 ToDo 정리 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    has_current_mail = "현재메일" in compact
    has_recipient = any(token in compact for token in ("수신자", "받는사람", "recipient"))
    has_todo = any(token in compact for token in ("todo", "할일", "액션", "조치"))
    has_due = any(token in compact for token in ("마감", "기한", "due"))
    return has_current_mail and has_recipient and has_todo and has_due


def render_current_mail_people_roles_table(user_message: str, mail_context: dict[str, object] | None) -> str:
    """현재메일 인물 역할 요청을 동적 테이블로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        mail_context: 현재메일 컨텍스트

    Returns:
        렌더링된 Markdown. 대상이 아니거나 데이터가 없으면 빈 문자열
    """
    if not is_current_mail_people_roles_table_request(user_message=user_message):
        return ""
    if not isinstance(mail_context, dict):
        return ""
    spec = _build_people_roles_table_spec(user_message=user_message, mail_context=mail_context)
    if spec is None:
        return ""
    return render_markdown_table(
        title=spec.title,
        headers=spec.headers,
        rows=spec.rows,
        empty_message=spec.empty_message,
    )


def render_current_mail_people_roles_from_contract(
    user_message: str,
    contract: LLMResponseContract,
    mail_context: dict[str, object] | None = None,
) -> str:
    """현재메일 인물 역할 요청을 모델 JSON(`recipient_roles`) 기반으로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 모델 JSON 계약

    Returns:
        렌더링된 Markdown. 적용 대상이 아니거나 recipient_roles가 비면 빈 문자열
    """
    if not is_current_mail_people_roles_table_request(user_message=user_message):
        return ""
    filtered_rows = sanitize_contract_recipient_roles(rows=list(contract.recipient_roles), mail_context=mail_context)
    rows = []
    for row in filtered_rows:
        recipient = normalize_person_identity(token=str(row.recipient or ""))
        role = str(row.role or "").strip()
        evidence = str(row.evidence or "").strip()
        if not recipient or not role:
            continue
        rows.append([recipient, role, evidence or "-"])
    if not rows:
        return ""
    spec = TableSpec(
        title="## 수신자 역할 정리",
        headers=["수신자", "역할 추정", "근거"],
        rows=rows[:MAX_ROLE_ROWS],
        empty_message="수신자 역할 정보를 찾지 못했습니다.",
    )
    return render_markdown_table(
        title=spec.title,
        headers=spec.headers,
        rows=spec.rows,
        empty_message=spec.empty_message,
    )


def render_current_mail_recipient_todos_from_contract(
    user_message: str,
    contract: LLMResponseContract,
    mail_context: dict[str, object] | None = None,
) -> str:
    """현재메일 수신자별 ToDo 요청을 모델 JSON(`recipient_todos`) 기반으로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 모델 JSON 계약
        mail_context: 현재메일 컨텍스트

    Returns:
        렌더링된 Markdown. 적용 대상이 아니거나 recipient_todos가 비면 빈 문자열
    """
    if not is_current_mail_recipient_todos_request(user_message=user_message):
        return ""
    filtered_rows = sanitize_contract_recipient_todos(rows=list(contract.recipient_todos), mail_context=mail_context)
    rows: list[list[str]] = []
    for row in filtered_rows:
        recipient = normalize_person_identity(token=str(row.recipient or ""))
        todo = str(row.todo or "").strip()
        due_date = str(row.due_date or "미정").strip() or "미정"
        basis = str(row.due_date_basis or "근거 부족").strip() or "근거 부족"
        if not recipient or not todo:
            continue
        rows.append([recipient, todo, due_date, basis])
    if not rows:
        return ""
    spec = TableSpec(
        title="## 수신자별 ToDo",
        headers=["수신자", "할 일", "마감기한", "기한 근거"],
        rows=rows[:MAX_ROLE_ROWS],
        empty_message="수신자별 ToDo 정보를 찾지 못했습니다.",
    )
    return render_markdown_table(
        title=spec.title,
        headers=spec.headers,
        rows=spec.rows,
        empty_message=spec.empty_message,
    )


def _build_people_roles_table_spec(user_message: str, mail_context: dict[str, object]) -> TableSpec | None:
    """질문 의도와 메일 컨텍스트로 인물 역할 테이블 스펙을 생성한다.

    Args:
        user_message: 사용자 입력 원문
        mail_context: 현재메일 컨텍스트

    Returns:
        생성된 TableSpec. 구성 실패 시 None
    """
    scope = _detect_people_scope(user_message=user_message)
    taxonomy = get_role_taxonomy()
    people_rows = _extract_people_rows(mail_context=mail_context, scope=scope, taxonomy=taxonomy)
    if not people_rows:
        return TableSpec(
            title="## 인물 역할 정리",
            headers=_build_headers(scope=scope),
            rows=[],
            empty_message="메일에서 역할을 추정할 수 있는 인물 정보를 찾지 못했습니다.",
        )

    target_rows = people_rows[:MAX_ROLE_ROWS]
    if scope == ROLE_SCOPE_TO:
        rows = [[row.person, row.role, row.evidence] for row in target_rows]
        return TableSpec(
            title="## 수신자 역할 정리",
            headers=["수신자", "역할 추정", "근거"],
            rows=rows,
            empty_message="수신자 정보를 찾지 못했습니다.",
        )
    if scope == ROLE_SCOPE_CC:
        rows = [[row.person, row.role, row.evidence] for row in target_rows]
        return TableSpec(
            title="## 참조자 역할 정리",
            headers=["참조자(CC)", "역할 추정", "근거"],
            rows=rows,
            empty_message="참조자 정보를 찾지 못했습니다.",
        )
    if scope == ROLE_SCOPE_BODY:
        rows = [[row.person, row.role, row.evidence] for row in target_rows]
        return TableSpec(
            title="## 인물 역할 정리",
            headers=["이름/주소", "역할 추정", "근거"],
            rows=rows,
            empty_message="메일에서 역할을 추정할 수 있는 인물 정보를 찾지 못했습니다.",
        )

    rows = [[row.person, row.audience, row.role, row.evidence] for row in target_rows]
    return TableSpec(
        title="## 인물 역할 정리",
        headers=_build_headers(scope=scope),
        rows=rows,
        empty_message="메일에서 역할을 추정할 수 있는 인물 정보를 찾지 못했습니다.",
    )


def _detect_people_scope(user_message: str) -> str:
    """질문 텍스트에서 인물 추출 범위를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        to/cc/body/all 중 하나
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if "참조" in compact or "cc" in compact:
        return ROLE_SCOPE_CC
    if "수신자" in compact or "받는사람" in compact:
        return ROLE_SCOPE_TO
    if "본문" in compact or "명시" in compact or "인물" in compact:
        return ROLE_SCOPE_BODY
    return ROLE_SCOPE_ALL


def _build_headers(scope: str) -> list[str]:
    """범위별 테이블 헤더를 반환한다.

    Args:
        scope: 인물 추출 범위

    Returns:
        테이블 헤더 목록
    """
    if scope == ROLE_SCOPE_BODY:
        return ["이름/주소", "역할 추정", "근거"]
    return ["이름/주소", "구분", "역할 추정", "근거"]


def _extract_people_rows(
    mail_context: dict[str, object],
    scope: str,
    taxonomy: RoleTaxonomyConfig,
) -> list[PersonRoleRow]:
    """컨텍스트에서 범위별 인물 역할 행 목록을 추출한다.

    Args:
        mail_context: 현재메일 컨텍스트
        scope: 인물 추출 범위

    Returns:
        중복 제거된 인물 역할 행 목록
    """
    rows: list[PersonRoleRow] = []
    if scope in (ROLE_SCOPE_TO, ROLE_SCOPE_ALL):
        to_people = _extract_header_people(
            mail_context=mail_context,
            header_type=ROLE_SCOPE_TO,
            taxonomy=taxonomy,
        )
        rows.extend(to_people)
    if scope in (ROLE_SCOPE_CC, ROLE_SCOPE_ALL):
        cc_people = _extract_header_people(
            mail_context=mail_context,
            header_type=ROLE_SCOPE_CC,
            taxonomy=taxonomy,
        )
        rows.extend(cc_people)
    if scope in (ROLE_SCOPE_BODY, ROLE_SCOPE_ALL):
        rows.extend(_extract_body_people(mail_context=mail_context, taxonomy=taxonomy))
    return dedupe_person_rows(rows=rows)


def _extract_header_people(
    mail_context: dict[str, object],
    header_type: str,
    taxonomy: RoleTaxonomyConfig,
) -> list[PersonRoleRow]:
    """헤더(To/Cc) 기반 인물 목록을 역할 행으로 변환한다.

    Args:
        mail_context: 현재메일 컨텍스트
        header_type: to 또는 cc

    Returns:
        역할 행 목록
    """
    audience = "수신(To)" if header_type == ROLE_SCOPE_TO else "참조(CC)"
    if header_type == ROLE_SCOPE_TO:
        default_role = str(taxonomy.default_roles.get("to") or "수신/실행 대상")
    else:
        default_role = str(taxonomy.default_roles.get("cc") or "공유 대상")
    source_texts = _collect_header_candidates(mail_context=mail_context, header_type=header_type)
    people = _split_people_tokens(tokens=source_texts)
    body_text = str(mail_context.get("body_excerpt") or "")
    rows: list[PersonRoleRow] = []
    for person in people:
        role, evidence = infer_role_evidence_for_person(
            person=person,
            body_text=body_text,
            taxonomy=taxonomy,
            fallback_role=default_role,
            header_type=header_type,
        )
        rows.append(
            PersonRoleRow(
                person=person,
                audience=audience,
                role=role,
                evidence=evidence,
            )
        )
    return rows


def _collect_header_candidates(mail_context: dict[str, object], header_type: str) -> list[str]:
    """헤더 타입별 후보 문자열을 수집한다.

    Args:
        mail_context: 현재메일 컨텍스트
        header_type: to 또는 cc

    Returns:
        후보 문자열 목록
    """
    if header_type == ROLE_SCOPE_TO:
        keys = ("to_recipients", "recipients", "to", "receiver")
    else:
        keys = ("cc_recipients", "cc", "reference", "참조")
    collected: list[str] = []
    for key in keys:
        value = mail_context.get(key)
        if isinstance(value, str) and value.strip():
            collected.append(value)
        if isinstance(value, list):
            collected.extend(str(item).strip() for item in value if str(item).strip())

    body_excerpt = str(mail_context.get("body_excerpt") or "")
    if not collected:
        header_values = _extract_header_value_from_body(body_text=body_excerpt, header_type=header_type)
    else:
        header_values = ""
    if header_values:
        collected.append(header_values)
    return collected


def _extract_header_value_from_body(body_text: str, header_type: str) -> str:
    """본문 헤더 블록에서 To/Cc 값을 추출한다.

    Args:
        body_text: 본문 발췌 텍스트
        header_type: to 또는 cc

    Returns:
        추출 문자열
    """
    normalized = str(body_text or "").replace("\r", "\n")
    if not normalized:
        return ""
    if header_type == ROLE_SCOPE_TO:
        pattern = r"To:\s*(.+?)(?:Cc:|Subject:|From:|$)"
    else:
        pattern = r"Cc:\s*(.+?)(?:Subject:|From:|To:|$)"
    matched = re.search(pattern, normalized, flags=re.IGNORECASE | re.DOTALL)
    if not matched:
        return ""
    return str(matched.group(1) or "").replace("\n", " ").strip()


def _split_people_tokens(tokens: Iterable[str]) -> list[str]:
    """다양한 구분자로 섞인 주소/이름 토큰을 분할해 중복 제거한다.

    Args:
        tokens: 원본 후보 토큰 iterable

    Returns:
        정규화된 인물 문자열 목록
    """
    people: list[str] = []
    for token in tokens:
        normalized = str(token or "").strip()
        if not normalized:
            continue
        parts = re.split(r"[,;\n]|\s+및\s+", normalized)
        for part in parts:
            candidate = normalize_person_token(token=part)
            if not candidate:
                continue
            if candidate not in people:
                people.append(candidate)
    return people


def _extract_body_people(
    mail_context: dict[str, object],
    taxonomy: RoleTaxonomyConfig,
) -> list[PersonRoleRow]:
    """본문에서 인물/역할 힌트를 추출한다.

    Args:
        mail_context: 현재메일 컨텍스트

    Returns:
        역할 행 목록
    """
    body_text = str(mail_context.get("body_excerpt") or "")
    if not body_text:
        return []
    lines = [str(line).strip() for line in body_text.replace("\r", "\n").split("\n") if str(line).strip()]
    rows: list[PersonRoleRow] = []
    for line in lines:
        role = infer_role_from_line(line=line, taxonomy=taxonomy)
        line_people = _extract_people_from_line(line=line)
        for person in line_people:
            rows.append(
                PersonRoleRow(
                    person=person,
                    audience="본문",
                    role=role,
                    evidence=normalize_evidence_line(line=line),
                )
            )
    return rows


def _extract_people_from_line(line: str) -> list[str]:
    """본문 한 줄에서 인물 후보를 추출한다.

    Args:
        line: 본문 한 줄

    Returns:
        인물 문자열 목록
    """
    people: list[str] = []
    emails = EMAIL_PATTERN.findall(line)
    for email in emails:
        if email not in people:
            people.append(email)

    for matched in KOREAN_NAME_PATTERN.findall(line):
        name = str(matched or "").strip()
        if len(name) < 2:
            continue
        if name in ("현재메일", "요약", "수신자", "참조", "담당", "역할", "확인", "요청"):
            continue
        if name not in people:
            people.append(name)
    return people

