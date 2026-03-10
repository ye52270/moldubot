from __future__ import annotations

import unittest

from app.agents.prompts import (
    CODE_REVIEW_EXPERT_SYSTEM_PROMPT,
    DEFAULT_DEEP_AGENT_SYSTEM_PROMPT,
    FAST_COMPACT_SYSTEM_PROMPT,
    MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT,
    MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT,
    QUALITY_FREEFORM_GROUNDED_SYSTEM_PROMPT,
    QUALITY_STRUCTURED_SYSTEM_PROMPT,
    get_agent_system_prompt,
)


class AgentPromptsTest(unittest.TestCase):
    """에이전트 시스템 프롬프트 variant 조회를 검증한다."""

    def test_returns_default_for_empty_variant(self) -> None:
        """빈 variant 입력 시 기본 프롬프트를 반환해야 한다."""
        self.assertEqual(get_agent_system_prompt(""), DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_returns_default_for_unknown_variant(self) -> None:
        """미등록 variant 입력 시 기본 프롬프트를 반환해야 한다."""
        self.assertEqual(
            get_agent_system_prompt("unknown_variant"),
            DEFAULT_DEEP_AGENT_SYSTEM_PROMPT,
        )

    def test_returns_fast_compact_variant(self) -> None:
        """fast_compact variant 조회가 가능해야 한다."""
        self.assertEqual(get_agent_system_prompt("fast_compact"), FAST_COMPACT_SYSTEM_PROMPT)

    def test_returns_quality_structured_variant(self) -> None:
        """quality_structured variant 조회가 가능해야 한다."""
        self.assertEqual(
            get_agent_system_prompt("quality_structured"),
            QUALITY_STRUCTURED_SYSTEM_PROMPT,
        )

    def test_returns_code_review_expert_variant(self) -> None:
        """code_review_expert variant 조회가 가능해야 한다."""
        self.assertEqual(
            get_agent_system_prompt("code_review_expert"),
            CODE_REVIEW_EXPERT_SYSTEM_PROMPT,
        )

    def test_returns_quality_freeform_grounded_variant(self) -> None:
        """quality_freeform_grounded variant 조회가 가능해야 한다."""
        self.assertEqual(
            get_agent_system_prompt("quality_freeform_grounded"),
            QUALITY_FREEFORM_GROUNDED_SYSTEM_PROMPT,
        )

    def test_quality_freeform_prompt_does_not_force_json_contract(self) -> None:
        """freeform variant는 JSON 강제 계약 문구를 포함하지 않아야 한다."""
        self.assertNotIn("Return exactly one JSON object", QUALITY_FREEFORM_GROUNDED_SYSTEM_PROMPT)
        self.assertIn("prefer rich freeform prose", QUALITY_FREEFORM_GROUNDED_SYSTEM_PROMPT)

    def test_code_review_prompt_requires_concise_snippet_policy(self) -> None:
        """코드리뷰 프롬프트는 짧은 스니펫 중심의 간결 정책을 포함해야 한다."""
        self.assertIn("exactly once", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)
        self.assertIn("1~3개", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)
        self.assertIn("<= 6 lines", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)
        self.assertIn("Never dump full file", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)
        self.assertIn("## 코드 분석", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)
        self.assertIn("## 코드 리뷰", CODE_REVIEW_EXPERT_SYSTEM_PROMPT)

    def test_default_prompt_contains_action_items_field_rule(self) -> None:
        """액션아이템 추출 요청은 action_items 필드에 채우도록 기본 프롬프트에 명시되어야 한다."""
        self.assertIn("액션 아이템/할 일/조치사항", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("action_items", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("write_todos", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("`task`", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_default_prompt_contains_standard_summary_quality_constraints(self) -> None:
        """표준 요약 품질 제약(중복 금지/최소 포인트)이 기본 프롬프트에 포함되어야 한다."""
        self.assertIn("standard_summary", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("4~6 distinct lines", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("Do not repeat the same meaning", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("must contain only observed facts/causes/impacts", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("must not overlap in sentence/meaning", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_quality_structured_prompt_includes_orchestration_contract(self) -> None:
        """quality_structured 프롬프트는 todo 계획/서브에이전트 위임 규칙을 포함해야 한다."""
        self.assertIn("write_todos", QUALITY_STRUCTURED_SYSTEM_PROMPT)
        self.assertIn("`task`", QUALITY_STRUCTURED_SYSTEM_PROMPT)

    def test_default_prompt_contains_recipient_roles_structout_rules(self) -> None:
        """수신자 역할 분석 StructOut 필드와 규칙이 프롬프트에 포함되어야 한다."""
        self.assertIn('"recipient_roles"', DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("현재메일 수신자 역할 표/정리", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("role", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("evidence", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_default_prompt_contains_recipient_todos_structout_rules(self) -> None:
        """수신자별 ToDo StructOut 필드와 규칙이 프롬프트에 포함되어야 한다."""
        self.assertIn('"recipient_todos"', DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("수신자별 todo/할일 + 마감기한", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("due_date", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_default_prompt_blocks_todo_tool_for_summary_planning_queries(self) -> None:
        """요약/정리형 ToDo 질의는 create_outlook_todo 호출 금지 규칙이 포함되어야 한다."""
        self.assertIn("never call `create_outlook_todo`", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)
        self.assertIn("without explicit registration verbs", DEFAULT_DEEP_AGENT_SYSTEM_PROMPT)

    def test_mail_subagent_prompts_require_json_struct_output(self) -> None:
        """메일 조회/기술 이슈 subagent 프롬프트는 JSON StructOutput 계약을 강제해야 한다."""
        self.assertIn("Return exactly one JSON object", MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT)
        self.assertIn('"query_summaries"', MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT)
        self.assertIn('"action": "mail_search"', MAIL_RETRIEVAL_SUMMARY_SUBAGENT_SYSTEM_PROMPT)
        self.assertIn("Return exactly one JSON object", MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT)
        self.assertIn('"query_summaries"', MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT)
        self.assertIn('"query": "기술적 이슈"', MAIL_TECH_ISSUE_SUBAGENT_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
