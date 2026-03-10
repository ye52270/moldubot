from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router


@dataclass(frozen=True)
class E2ESampleCase:
    """`/search/chat` 샘플 E2E 입력 계약을 표현한다."""

    thread_id: str
    message: str


SAMPLE_CASES: list[E2ESampleCase] = [
    E2ESampleCase(thread_id="e2e-1", message="나는 이번주에 M365 전환 관련 메일만 집중해서 볼 거야. 기억해줘."),
    E2ESampleCase(thread_id="e2e-1", message="방금 내가 집중해서 본다고 한 주제가 뭐였지?"),
    E2ESampleCase(thread_id="e2e-2", message="지난 주 조영득 관련 메일 3개만 찾아서 핵심만 요약해줘."),
    E2ESampleCase(thread_id="e2e-3", message="1월달 M365 관련 메일 조회해줘."),
    E2ESampleCase(thread_id="e2e-4", message="최근 4주 보안 점검 관련 메일 찾아줘."),
    E2ESampleCase(thread_id="e2e-5", message="현재메일 요약해줘."),
    E2ESampleCase(thread_id="e2e-5", message="현재메일 3줄 요약해줘."),
    E2ESampleCase(thread_id="e2e-5", message="현재메일에서 내가 해야 할 액션 아이템만 정리해줘."),
    E2ESampleCase(thread_id="e2e-6", message="최근 2주 회의실 예약 관련 메일 조회하고 팀 공유용으로 정리해줘."),
    E2ESampleCase(thread_id="e2e-7", message="내가 방금 집중한다고 했던 주제가 뭐야?"),
]


class FakeDeepAgent:
    """thread_id 기반 메모리 동작을 모사하는 테스트용 deep-agent."""

    def __init__(self) -> None:
        """테스트용 상태 저장소를 초기화한다."""
        self._memory_by_thread: dict[str, str] = {}
        self._last_tool_payload: dict[str, Any] = {}

    def respond(self, user_message: str, thread_id: str | None = None) -> str:
        """
        입력 문장을 기준으로 테스트용 응답을 생성한다.

        Args:
            user_message: 사용자 입력
            thread_id: 요청 스레드 식별자

        Returns:
            테스트 검증용 응답 문자열
        """
        normalized_thread = str(thread_id or "").strip() or "thread-default"
        text = str(user_message or "")
        normalized = text.replace(" ", "")

        if "집중해서볼거야" in normalized:
            self._memory_by_thread[normalized_thread] = "M365 전환 관련 메일"
            self._last_tool_payload = {}
            return "알겠습니다. 이번 주에는 M365 전환 관련 메일에 집중하겠습니다."

        if "주제가뭐" in normalized:
            topic = self._memory_by_thread.get(normalized_thread, "기억된 주제가 없습니다.")
            self._last_tool_payload = {}
            return f"현재 스레드 기준 기억된 주제: {topic}"

        if "조회" in normalized and "현재메일" not in normalized:
            self._last_tool_payload = {
                "action": "mail_search",
                "results": [
                    {
                        "message_id": "m-e2e-1",
                        "subject": "E2E 샘플 메일",
                        "received_date": "2026-03-01",
                        "sender_names": "테스터",
                        "web_link": "https://outlook.office.com/mail/m-e2e-1",
                    }
                ],
                "aggregated_summary": ["조회 결과 1건"],
            }
            return "조회 결과를 정리했습니다."

        self._last_tool_payload = {"action": "current_mail"} if "현재메일" in normalized else {}
        return f"테스트 응답: {text[:40]}"

    def get_last_tool_payload(self) -> dict[str, Any]:
        """
        마지막 tool payload를 반환한다.

        Returns:
            마지막 payload 사전
        """
        return dict(self._last_tool_payload)


class SearchChatE2ESamplesTest(unittest.TestCase):
    """샘플 시나리오 기반 `/search/chat` E2E 계약을 검증한다."""

    def setUp(self) -> None:
        """테스트용 FastAPI 앱과 Fake agent를 초기화한다."""
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.fake_agent = FakeDeepAgent()

    def test_sample_cases_return_completed_response(self) -> None:
        """샘플 10개 요청이 모두 completed 응답을 반환해야 한다."""
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=self.fake_agent):
                for case in SAMPLE_CASES:
                    response = self.client.post(
                        "/search/chat",
                        json={"thread_id": case.thread_id, "message": case.message},
                    )
                    payload = response.json()

                    self.assertEqual(200, response.status_code)
                    self.assertEqual("completed", payload.get("status"))
                    self.assertEqual(case.thread_id, payload.get("thread_id"))
                    self.assertIn("answer", payload)
                    self.assertEqual("deep-agent", payload.get("metadata", {}).get("source"))

    def test_memory_is_thread_scoped(self) -> None:
        """같은 thread_id에서는 기억을 재사용하고, 다른 thread_id에서는 격리해야 한다."""
        with patch("app.api.routes.is_openai_key_configured", return_value=True):
            with patch("app.api.routes.get_deep_chat_agent", return_value=self.fake_agent):
                self.client.post(
                    "/search/chat",
                    json={
                        "thread_id": "memory-thread-a",
                        "message": "나는 이번주에 M365 전환 관련 메일만 집중해서 볼 거야. 기억해줘.",
                    },
                )
                remembered = self.client.post(
                    "/search/chat",
                    json={"thread_id": "memory-thread-a", "message": "방금 내가 집중해서 본다고 한 주제가 뭐였지?"},
                )
                isolated = self.client.post(
                    "/search/chat",
                    json={"thread_id": "memory-thread-b", "message": "방금 내가 집중해서 본다고 한 주제가 뭐였지?"},
                )

        self.assertIn("M365 전환 관련 메일", remembered.json().get("answer", ""))
        self.assertIn("기억된 주제가 없습니다", isolated.json().get("answer", ""))


if __name__ == "__main__":
    unittest.main()
