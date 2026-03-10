from __future__ import annotations

import os
from typing import Any

from deepagents.middleware.subagents import SubAgent

from app.agents.prompts import (
    CODE_REVIEW_EXPERT_SYSTEM_PROMPT,
    MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT,
    MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT,
)
from app.agents.tools import current_date, run_mail_post_action, search_mails, search_meeting_schedule


def get_agent_subagents() -> list[SubAgent]:
    """
    메인 deep agent에 주입할 서브에이전트 목록을 반환한다.

    Returns:
        서브에이전트 사양 목록
    """
    subagents: list[SubAgent] = []
    code_review_subagent: SubAgent = {
        "name": "code-review-agent",
        "description": "현재메일 코드 스니펫의 보안/품질/유지보수 리스크를 전문가 수준으로 리뷰한다.",
        "system_prompt": CODE_REVIEW_EXPERT_SYSTEM_PROMPT,
        "tools": [_ensure_tool_callable(run_mail_post_action)],
    }
    subagents.append(code_review_subagent)
    if not _is_mail_subagents_enabled():
        return subagents
    mail_retrieval_summary_subagent: SubAgent = {
        "name": "mail-retrieval-summary-agent",
        "description": "복합 메일 조회 질의에서 일정/프로젝트 관련 메일을 검색하고 핵심 요약 라인을 정리한다.",
        "system_prompt": MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT,
        "tools": [
            _ensure_tool_callable(search_mails),
            _ensure_tool_callable(search_meeting_schedule),
            _ensure_tool_callable(current_date),
        ],
    }
    mail_tech_issue_subagent: SubAgent = {
        "name": "mail-tech-issue-agent",
        "description": "메일 조회 결과에서 기술 이슈(장애/오류/보안/API) 관련 근거를 추려 기술 이슈 섹션 후보를 만든다.",
        "system_prompt": MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT,
        "tools": [
            _ensure_tool_callable(search_mails),
            _ensure_tool_callable(search_meeting_schedule),
            _ensure_tool_callable(current_date),
        ],
    }
    subagents.extend([mail_retrieval_summary_subagent, mail_tech_issue_subagent])
    return subagents


def _is_mail_subagents_enabled() -> bool:
    """
    메일 조회 전용 서브에이전트 활성화 여부를 반환한다.

    Returns:
        환경변수(`MOLDUBOT_ENABLE_MAIL_SUBAGENTS`)가 truthy면 True
    """
    raw_value = str(os.getenv("MOLDUBOT_ENABLE_MAIL_SUBAGENTS", "")).strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _ensure_tool_callable(tool_obj: Any) -> Any:
    """
    TypedDict 직렬화 호환을 위해 도구 객체를 그대로 반환한다.

    Args:
        tool_obj: LangChain tool callable

    Returns:
        입력 도구 객체
    """
    return tool_obj
