from __future__ import annotations

import unittest

from app.api.contracts import ChatRequest
from app.api.search_chat_stream_utils import (
    CODE_REVIEW_STREAM_PHASE_STEPS,
    GENERAL_STREAM_PHASE_STEPS,
    _resolve_phase_steps,
    _resolve_progress_state,
)


class SearchChatStreamUtilsTest(unittest.TestCase):
    """스트리밍 진행 단계 문구 선택 로직을 검증한다."""

    def test_resolve_phase_steps_uses_generic_messages_for_non_code_review(self) -> None:
        """일반 요약 질의는 코드분석 문구를 사용하면 안 된다."""
        payload = ChatRequest(message="현재메일 요약해줘")
        steps = _resolve_phase_steps(payload=payload)

        self.assertGreater(len(steps), 0)
        messages = [message for _, message in steps]
        self.assertFalse(any("코드/문맥" in message for message in messages))
        self.assertIn("요청을 처리하고 있어요.", messages)

    def test_resolve_phase_steps_uses_code_review_messages_for_code_query(self) -> None:
        """코드리뷰 질의는 코드분석 문구를 유지해야 한다."""
        payload = ChatRequest(message="현재메일 코드 분석해줘")
        steps = _resolve_phase_steps(payload=payload)

        self.assertGreater(len(steps), 0)
        messages = [message for _, message in steps]
        self.assertIn("코드/문맥을 분석하고 있어요.", messages)

    def test_progress_phase_caps_before_finalizing_until_completion(self) -> None:
        """heartbeat 진행 중에는 finalizing 단계로 조기 진입하면 안 된다."""
        phase, _, step = _resolve_progress_state(
            heartbeat_count=999,
            phase_steps=GENERAL_STREAM_PHASE_STEPS,
        )
        self.assertNotEqual(phase, "finalizing")
        self.assertLess(step, len(GENERAL_STREAM_PHASE_STEPS))

    def test_progress_phase_caps_before_finalizing_for_code_review(self) -> None:
        """코드리뷰 진행 중에도 finalizing은 완료 직전 이벤트로만 노출되어야 한다."""
        phase, _, step = _resolve_progress_state(
            heartbeat_count=999,
            phase_steps=CODE_REVIEW_STREAM_PHASE_STEPS,
        )
        self.assertNotEqual(phase, "finalizing")
        self.assertLess(step, len(CODE_REVIEW_STREAM_PHASE_STEPS))


if __name__ == "__main__":
    unittest.main()
