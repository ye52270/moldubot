from __future__ import annotations

import unittest

from app.api.followup_reference import (
    build_followup_reference_hint,
    build_recent_context_hint,
    remember_recent_turn_context,
    remember_followup_reference,
    reset_followup_reference_state_for_test,
)


class FollowupReferenceTest(unittest.TestCase):
    """
    후속 지시어 문맥 해석 상태 저장/주입 계약을 검증한다.
    """

    def tearDown(self) -> None:
        """
        테스트 간 상태 오염을 방지하기 위해 저장소를 초기화한다.
        """
        reset_followup_reference_state_for_test()

    def test_remember_and_build_hint_for_deictic_delivery_question(self) -> None:
        """
        문제 주소 식별 후 '거기서 어떤 주소로 보내' 질의가 오면 참조 힌트를 생성해야 한다.
        """
        remember_followup_reference(
            thread_id="thread-1",
            user_message="문제가 되는 메일 주소가 뭐야?",
            answer="문제가 되는 메일 주소는 relay.grafana-reporter@relay.skbroadband.com입니다.",
            resolved_scope="current_mail",
            is_current_mail_mode=True,
        )

        hint = build_followup_reference_hint(
            thread_id="thread-1",
            user_message="거기서 어떤 주소로 보내는거야?",
            resolved_scope="current_mail",
            is_current_mail_mode=True,
        )
        self.assertIn("직전 확정 문제 메일주소", hint)
        self.assertIn("relay.grafana-reporter@relay.skbroadband.com", hint)
        self.assertIn("지시어(거기/그 주소)", hint)

    def test_build_hint_returns_empty_without_deictic_question(self) -> None:
        """
        지시어 기반 후속 질문이 아니면 힌트를 주입하지 않아야 한다.
        """
        remember_followup_reference(
            thread_id="thread-2",
            user_message="문제가 되는 메일 주소가 뭐야?",
            answer="relay.grafana-reporter@relay.skbroadband.com",
            resolved_scope="current_mail",
            is_current_mail_mode=True,
        )

        hint = build_followup_reference_hint(
            thread_id="thread-2",
            user_message="해결 방법 알려줘",
            resolved_scope="current_mail",
            is_current_mail_mode=True,
        )
        self.assertEqual("", hint)

    def test_remember_is_skipped_for_non_current_mail_scope(self) -> None:
        """
        current_mail 범위가 아니면 참조 상태를 저장하지 않아야 한다.
        """
        remember_followup_reference(
            thread_id="thread-3",
            user_message="문제가 되는 메일 주소가 뭐야?",
            answer="relay.grafana-reporter@relay.skbroadband.com",
            resolved_scope="global_search",
            is_current_mail_mode=False,
        )

        hint = build_followup_reference_hint(
            thread_id="thread-3",
            user_message="거기서 어떤 주소로 보내는거야?",
            resolved_scope="current_mail",
            is_current_mail_mode=True,
        )
        self.assertEqual("", hint)

    def test_recent_context_hint_uses_last_scope_and_evidence_top3(self) -> None:
        """
        지시어 기반 후속 질문이면 최근 저장된 scope/evidence 힌트를 주입해야 한다.
        """
        remember_recent_turn_context(
            thread_id="thread-4",
            resolved_scope="previous_results",
            evidence_mails=[
                {"subject": "IM DB 연결 오류", "snippet": "조직도 DB 프로비전 관련 확인 필요"},
                {"subject": "NSM 보안진단", "snippet": "보안성 검토 요청 양식 공유"},
                {"subject": "Grafana 미수신", "snippet": "발신 도메인 차단 이슈"},
            ],
        )
        hint = build_recent_context_hint(
            thread_id="thread-4",
            user_message="그거 조금 더 자세히 설명해줘",
        )
        self.assertIn("직전 질의 범위: 직전 조회 결과", hint)
        self.assertIn("최근 근거 1: IM DB 연결 오류", hint)
        self.assertIn("최근 근거 2: NSM 보안진단", hint)


if __name__ == "__main__":
    unittest.main()
