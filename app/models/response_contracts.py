from __future__ import annotations

import re
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, model_validator

ACTION_CLASSIFICATION_TOKENS: tuple[str, ...] = (
    "조치",
    "요청",
    "확인",
    "검토",
    "회신",
    "적용",
    "등록",
    "생성",
    "제출",
    "공유",
    "전달",
    "승인",
    "반영",
    "필요",
    "대응",
    "해결",
    "수정",
    "보완",
    "재확인",
)
ACTION_CLASSIFICATION_PATTERNS: tuple[str, ...] = (
    r".*해야\s*함$",
    r".*해야\s*합니다$",
    r".*부탁드립니다$",
    r".*진행\s*필요$",
    r".*기한[:：]\s*.+$",
)
class SummaryResponseContract(BaseModel):
    """
    요약 응답의 최소 계약 모델.

    Attributes:
        requested_line_target: 사용자 요청 줄 수
        summary_lines: 최종 요약 라인 목록
    """

    requested_line_target: int = Field(default=5, ge=1, le=20)
    summary_lines: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_summary_lines(self) -> "SummaryResponseContract":
        """
        요약 라인 계약을 검증하고 정규화한다.

        Returns:
            검증/정규화가 적용된 계약 모델
        """
        normalized: list[str] = []
        for line in self.summary_lines:
            text = str(line or "").strip()
            if not text:
                continue
            if text not in normalized:
                normalized.append(text)

        if not normalized:
            normalized = ["요약할 수 있는 근거 문장을 찾지 못했습니다."]

        self.summary_lines = normalized[: self.requested_line_target]
        return self
class FinalAnswerContract(BaseModel):
    """
    최종 사용자 응답의 최소 계약 모델.

    Attributes:
        answer: 사용자에게 반환할 최종 텍스트
    """

    answer: str = Field(default="")

    @model_validator(mode="after")
    def validate_answer(self) -> "FinalAnswerContract":
        """
        최종 응답 문자열을 정규화한다.

        Returns:
            정규화된 계약 모델
        """
        self.answer = str(self.answer or "").strip()
        return self
class LLMResponseContract(BaseModel):
    """
    LLM 최종 출력(JSON) 계약 모델.

    Attributes:
        format_type: 응답 형식 타입
        title: 응답 제목
        answer: 자유 텍스트 응답
        summary_lines: 요약 라인 목록
        key_points: 핵심 포인트 목록
        action_items: 액션 아이템 목록
    """

    format_type: Literal["general", "summary", "standard_summary", "detailed_summary", "report"] = "general"
    title: str = Field(default="")
    answer: str = Field(default="")
    summary_lines: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    basic_info: dict[str, str] = Field(default_factory=dict)
    core_issue: str = Field(default="")
    major_points: list[str] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    one_line_summary: str = Field(default="")
    recipient_roles: list["RecipientRoleEntry"] = Field(default_factory=list)
    recipient_todos: list["RecipientTodoEntry"] = Field(default_factory=list)
    reply_draft: str = Field(
        default="",
        validation_alias=AliasChoices(
            "reply_draft",
            "draft_answer",
            "additional_body",
            "reply_body",
            "response_body",
        ),
    )
    suggested_action_ids: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "suggested_action_ids",
            "suggested_actions",
            "action_ids",
        ),
    )

    @model_validator(mode="after")
    def normalize_fields(self) -> "LLMResponseContract":
        """
        문자열/리스트 필드를 정규화한다.

        Returns:
            정규화된 계약 모델
        """
        self.title = str(self.title or "").strip()
        self.answer = str(self.answer or "").strip()
        self.summary_lines = _normalize_string_list(values=self.summary_lines)
        self.key_points = _normalize_string_list(values=self.key_points)
        self.action_items = _normalize_string_list(values=self.action_items)
        self.basic_info = _normalize_string_map(values=self.basic_info)
        self.core_issue = _strip_markdown_inline(text=str(self.core_issue or "").strip())
        normalized_major_points = _normalize_string_list(values=self.major_points)
        normalized_required_actions = _normalize_string_list(values=self.required_actions)
        normalized_required_actions = _normalize_required_actions(
            required_actions=normalized_required_actions,
            action_items=self.action_items,
        )
        self.major_points = _normalize_major_points(
            major_points=normalized_major_points,
            required_actions=normalized_required_actions,
        )
        self.required_actions = normalized_required_actions
        self.one_line_summary = _strip_markdown_inline(text=str(self.one_line_summary or "").strip())
        self.recipient_roles = _normalize_recipient_roles(values=self.recipient_roles)
        self.recipient_todos = _normalize_recipient_todos(values=self.recipient_todos)
        self.reply_draft = str(self.reply_draft or "").strip()
        self.suggested_action_ids = _normalize_action_ids(values=self.suggested_action_ids)
        return self


class RecipientRoleEntry(BaseModel):
    """
    수신자 역할 분석 행 모델.

    Attributes:
        recipient: 수신자 표기값(이름 또는 이메일)
        role: 역할 추정 요약
        evidence: 근거 요약
    """

    recipient: str = Field(default="")
    role: str = Field(default="")
    evidence: str = Field(default="")

    @model_validator(mode="after")
    def normalize_fields(self) -> "RecipientRoleEntry":
        """
        수신자 역할 행 필드를 정규화한다.

        Returns:
            정규화된 행 모델
        """
        self.recipient = _strip_markdown_inline(text=str(self.recipient or "").strip())
        self.role = _strip_markdown_inline(text=str(self.role or "").strip())
        self.evidence = _strip_markdown_inline(text=str(self.evidence or "").strip())
        return self


class RecipientTodoEntry(BaseModel):
    """
    수신자별 ToDo 행 모델.

    Attributes:
        recipient: 수신자 식별자(이름 또는 이메일)
        todo: 수행해야 할 할 일
        due_date: 마감기한(`YYYY-MM-DD` 또는 `미정`)
        due_date_basis: 기한 산정 근거
    """

    recipient: str = Field(default="")
    todo: str = Field(default="")
    due_date: str = Field(default="미정")
    due_date_basis: str = Field(default="")

    @model_validator(mode="after")
    def normalize_fields(self) -> "RecipientTodoEntry":
        """
        수신자별 ToDo 행 필드를 정규화한다.

        Returns:
            정규화된 행 모델
        """
        self.recipient = _strip_markdown_inline(text=str(self.recipient or "").strip())
        self.todo = _strip_markdown_inline(text=str(self.todo or "").strip())
        self.due_date = _normalize_due_date(value=self.due_date)
        self.due_date_basis = _strip_markdown_inline(text=str(self.due_date_basis or "").strip())
        return self


def _normalize_string_list(values: list[str]) -> list[str]:
    """
    문자열 리스트를 공백 제거/중복 제거로 정규화한다.

    Args:
        values: 원본 문자열 목록

    Returns:
        정규화된 문자열 목록
    """
    normalized: list[str] = []
    normalized_compare: list[str] = []
    for value in values:
        text = _strip_markdown_inline(text=str(value or "").strip())
        if not text:
            continue
        compare_text = _normalize_compare_text(text=text)
        if not compare_text:
            continue
        if compare_text in normalized_compare:
            continue
        normalized_compare.append(compare_text)
        normalized.append(text)
    return normalized


def _normalize_compare_text(text: str) -> str:
    """
    중복 판정을 위한 비교 문자열을 정규화한다.

    Args:
        text: 원본 텍스트

    Returns:
        비교용 정규화 문자열
    """
    normalized = str(text or "").strip().lower()
    if not normalized:
        return ""
    return (
        normalized.replace(" ", "")
        .replace("—", "")
        .replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace(",", "")
        .replace(";", "")
        .replace("|", "")
        .replace("(", "")
        .replace(")", "")
        .replace("[", "")
        .replace("]", "")
    )


def _strip_markdown_inline(text: str) -> str:
    """
    인라인 마크다운 강조 문법을 제거한다.

    Args:
        text: 원본 텍스트

    Returns:
        마크다운 제거 텍스트
    """
    stripped = str(text or "").strip()
    stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
    stripped = re.sub(r"__(.*?)__", r"\1", stripped)
    return stripped.strip()


def _normalize_major_points(major_points: list[str], required_actions: list[str]) -> list[str]:
    """
    주요 내용을 정규화하고 조치 항목과의 중복을 제거한다.

    Args:
        major_points: 정규화 전 주요 내용 목록
        required_actions: 정규화된 조치 필요 사항 목록

    Returns:
        정규화된 주요 내용 목록
    """
    action_keys = {_normalize_compare_text(text=item) for item in required_actions}
    filtered: list[str] = []
    for point in major_points:
        compare_key = _normalize_compare_text(text=point)
        if not compare_key:
            continue
        if compare_key in action_keys:
            continue
        filtered.append(point)

    if filtered:
        return filtered

    fallback: list[str] = []
    for point in major_points:
        compare_key = _normalize_compare_text(text=point)
        if not compare_key or compare_key in action_keys:
            continue
        if compare_key in {_normalize_compare_text(text=item) for item in fallback}:
            continue
        fallback.append(point)
    return fallback


def _normalize_required_actions(required_actions: list[str], action_items: list[str]) -> list[str]:
    """
    조치 필요 사항을 실행 중심 항목으로 정규화하고 중복을 제거한다.

    Args:
        required_actions: 정규화 전 조치 필요 사항 목록
        action_items: action_items 필드 목록

    Returns:
        정규화된 조치 필요 사항 목록
    """
    merged = _normalize_string_list(values=[*required_actions, *action_items])
    execution_focused = [item for item in merged if _looks_like_action_line(text=item)]
    if execution_focused:
        return execution_focused[:5]
    return merged[:5]


def _looks_like_action_line(text: str) -> bool:
    """
    문장이 조치/실행 지시 성격인지 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        조치/실행 성격이면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if any(token in normalized for token in ACTION_CLASSIFICATION_TOKENS):
        return True
    return any(re.search(pattern, normalized) for pattern in ACTION_CLASSIFICATION_PATTERNS)


def _normalize_string_map(values: dict[str, str]) -> dict[str, str]:
    """
    문자열 맵(dict)을 공백/마크다운 제거 기준으로 정규화한다.

    Args:
        values: 원본 문자열 맵

    Returns:
        정규화된 문자열 맵
    """
    normalized: dict[str, str] = {}
    for key, value in values.items():
        normalized_key = str(key or "").strip()
        normalized_value = _strip_markdown_inline(text=str(value or "").strip())
        if not normalized_key or not normalized_value:
            continue
        normalized[normalized_key] = normalized_value
    return normalized


def _normalize_recipient_roles(values: list["RecipientRoleEntry"]) -> list["RecipientRoleEntry"]:
    """
    수신자 역할 행 목록을 공백 제거/중복 제거로 정규화한다.

    Args:
        values: 원본 수신자 역할 행 목록

    Returns:
        정규화된 행 목록
    """
    normalized: list[RecipientRoleEntry] = []
    compare_keys: set[str] = set()
    for row in values:
        if not isinstance(row, RecipientRoleEntry):
            continue
        recipient = str(row.recipient or "").strip()
        role = str(row.role or "").strip()
        evidence = str(row.evidence or "").strip()
        if not recipient or not role:
            continue
        compare_key = f"{_normalize_compare_text(recipient)}::{_normalize_compare_text(role)}::{_normalize_compare_text(evidence)}"
        if compare_key in compare_keys:
            continue
        compare_keys.add(compare_key)
        normalized.append(RecipientRoleEntry(recipient=recipient, role=role, evidence=evidence))
    return normalized


def _normalize_recipient_todos(values: list["RecipientTodoEntry"]) -> list["RecipientTodoEntry"]:
    """
    수신자별 ToDo 목록을 공백 제거/중복 제거로 정규화한다.

    Args:
        values: 원본 수신자별 ToDo 목록

    Returns:
        정규화된 ToDo 목록
    """
    normalized: list[RecipientTodoEntry] = []
    compare_keys: set[str] = set()
    for row in values:
        if not isinstance(row, RecipientTodoEntry):
            continue
        recipient = str(row.recipient or "").strip()
        todo = str(row.todo or "").strip()
        due_date = _normalize_due_date(value=row.due_date)
        basis = str(row.due_date_basis or "").strip()
        if not recipient or not todo:
            continue
        compare_key = (
            f"{_normalize_compare_text(recipient)}::"
            f"{_normalize_compare_text(todo)}::"
            f"{_normalize_compare_text(due_date)}"
        )
        if compare_key in compare_keys:
            continue
        compare_keys.add(compare_key)
        normalized.append(
            RecipientTodoEntry(
                recipient=recipient,
                todo=todo,
                due_date=due_date,
                due_date_basis=basis,
            )
        )
    return normalized


def _normalize_due_date(value: object) -> str:
    """
    마감일 문자열을 `YYYY-MM-DD` 또는 `미정`으로 정규화한다.

    Args:
        value: 원본 마감일 값

    Returns:
        정규화된 마감일 문자열
    """
    text = str(value or "").strip()
    if not text:
        return "미정"
    if text == "미정":
        return text
    matched = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if matched:
        return matched.group(1)
    return "미정"


def _normalize_action_ids(values: list[str]) -> list[str]:
    """
    액션 식별자 목록을 소문자/중복 제거 형태로 정규화한다.

    Args:
        values: 원본 액션 식별자 목록

    Returns:
        정규화된 액션 식별자 목록
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        action_id = str(value or "").strip().lower()
        if not action_id or action_id in seen:
            continue
        seen.add(action_id)
        normalized.append(action_id)
    return normalized
