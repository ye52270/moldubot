from __future__ import annotations

import unittest

from app.models.response_contracts import LLMResponseContract


class ResponseContractsTest(unittest.TestCase):
    """LLM 응답 계약 정규화 동작을 검증한다."""

    def test_normalize_string_list_deduplicates_near_duplicates(self) -> None:
        """공백/구두점 차이만 있는 유사 문장은 중복 제거되어야 한다."""
        contract = LLMResponseContract(
            format_type="standard_summary",
            major_points=[
                "서비스 CI 변경 요청 — 적용 필요",
                "서비스CI변경요청-적용필요",
                "서비스 CI 변경 요청: 적용 필요.",
            ],
        )
        self.assertEqual(1, len(contract.major_points))
        self.assertEqual("서비스 CI 변경 요청 — 적용 필요", contract.major_points[0])

    def test_normalize_string_list_preserves_distinct_lines(self) -> None:
        """의미가 다른 문장은 정규화 후에도 유지되어야 한다."""
        contract = LLMResponseContract(
            format_type="standard_summary",
            major_points=[
                "서비스 CI 변경 요청 — 적용 필요",
                "회신 일정은 금일 18시까지 요청됨",
            ],
        )
        self.assertEqual(2, len(contract.major_points))

    def test_recipient_roles_are_normalized_and_deduplicated(self) -> None:
        """recipient_roles는 공백 정리/중복 제거되어야 한다."""
        contract = LLMResponseContract(
            format_type="general",
            recipient_roles=[
                {"recipient": " 김태호 ", "role": "실행 담당", "evidence": "API 수정 진행"},
                {"recipient": "김태호", "role": "실행 담당", "evidence": "API 수정 진행"},
                {"recipient": "ssl@skcc.com", "role": "검토 담당", "evidence": "보안 검토 요청"},
            ],
        )
        self.assertEqual(2, len(contract.recipient_roles))
        self.assertEqual("김태호", contract.recipient_roles[0].recipient)
        self.assertEqual("실행 담당", contract.recipient_roles[0].role)

    def test_recipient_todos_are_normalized_and_due_date_is_sanitized(self) -> None:
        """recipient_todos는 중복 제거되고 due_date 형식이 보정되어야 한다."""
        contract = LLMResponseContract(
            format_type="general",
            recipient_todos=[
                {
                    "recipient": "김태호",
                    "todo": "Redirect 도메인 검토",
                    "due_date": "2026-03-07T09:00:00Z",
                    "due_date_basis": "본문에 금주 내 검토 요청",
                },
                {
                    "recipient": "김태호",
                    "todo": "Redirect 도메인 검토",
                    "due_date": "2026-03-07",
                    "due_date_basis": "본문에 금주 내 검토 요청",
                },
            ],
        )
        self.assertEqual(1, len(contract.recipient_todos))
        self.assertEqual("2026-03-07", contract.recipient_todos[0].due_date)

    def test_major_points_exclude_overlap_with_required_actions(self) -> None:
        """주요 내용과 조치 필요 사항의 동일 문장은 major_points에서 제거되어야 한다."""
        contract = LLMResponseContract(
            format_type="standard_summary",
            major_points=[
                "정책 중첩 이슈 확인 요청",
                "현재 정책은 감사 모드로 동작 중",
            ],
            required_actions=[
                "정책 중첩 이슈 확인 요청",
            ],
        )
        self.assertEqual(["현재 정책은 감사 모드로 동작 중"], contract.major_points)
        self.assertEqual(["정책 중첩 이슈 확인 요청"], contract.required_actions)

    def test_required_actions_merge_action_items_and_filter_execution_lines(self) -> None:
        """required_actions는 action_items를 병합하고 실행성 문장을 우선 유지해야 한다."""
        contract = LLMResponseContract(
            format_type="standard_summary",
            required_actions=["금일 정책 변경 검토 요청"],
            action_items=["담당자 회신 요청", "배경 설명"],
        )
        self.assertEqual(["금일 정책 변경 검토 요청", "담당자 회신 요청"], contract.required_actions)

    def test_required_actions_detect_imperative_patterns(self) -> None:
        """실행형 패턴(부탁드립니다/해야 함/기한)은 조치 항목으로 분류되어야 한다."""
        contract = LLMResponseContract(
            format_type="standard_summary",
            required_actions=[],
            action_items=[
                "도메인 추가 여부 검토 부탁드립니다",
                "예외 계정 등록해야 함",
                "담당 지정 / 기한: 2026-03-10",
                "현재 정책은 감사 모드로 동작 중",
            ],
        )
        self.assertEqual(
            ["도메인 추가 여부 검토 부탁드립니다", "예외 계정 등록해야 함", "담당 지정 / 기한: 2026-03-10"],
            contract.required_actions,
        )


if __name__ == "__main__":
    unittest.main()
