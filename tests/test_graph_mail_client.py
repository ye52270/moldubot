from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from app.integrations.microsoft_graph.mail_client import (
    GraphMailClient,
    _extract_aadsts_metadata,
    _parse_graph_mail_payload,
)


class _FakeResponse:
    """
    Graph HTTP 실패 응답 더블.
    """

    def __init__(self) -> None:
        """
        테스트용 실패 응답을 초기화한다.
        """
        self.status_code = 403
        self.text = "forbidden"
        self.headers = {
            "request-id": "request-header-id",
            "client-request-id": "client-header-id",
        }

    def json(self) -> dict[str, object]:
        """
        Graph 에러 본문을 반환한다.

        Returns:
            Graph 표준 error payload
        """
        return {
            "error": {
                "code": "ErrorAccessDenied",
                "message": "Access is denied due to policy.",
                "innerError": {
                    "request-id": "inner-request-id",
                    "client-request-id": "inner-client-request-id",
                },
            }
        }


class _FakeUnauthorizedResponse:
    """
    Graph HTTP 401 응답 더블.
    """

    def __init__(self) -> None:
        """
        테스트용 401 응답을 초기화한다.
        """
        self.status_code = 401
        self.text = "unauthorized"
        self.headers = {
            "request-id": "request-401-id",
            "client-request-id": "client-401-id",
        }

    def json(self) -> dict[str, object]:
        """
        Graph 401 에러 본문을 반환한다.

        Returns:
            Graph 표준 error payload
        """
        return {
            "error": {
                "code": "InvalidAuthenticationToken",
                "message": "Access token has expired or is invalid.",
                "innerError": {
                    "request-id": "inner-401-request-id",
                    "client-request-id": "inner-401-client-request-id",
                },
            }
        }


class _FakeOkResponse:
    """
    Graph HTTP 200 응답 더블.
    """

    def __init__(self) -> None:
        """
        테스트용 성공 응답을 초기화한다.
        """
        self.status_code = 200
        self.text = "ok"
        self.headers = {}

    def json(self) -> dict[str, object]:
        """
        Graph 성공 본문을 반환한다.

        Returns:
            Graph 메시지 payload
        """
        return {
            "id": "m-200",
            "subject": "테스트 메일",
            "receivedDateTime": "2026-03-01T00:00:00Z",
            "from": {"emailAddress": {"address": "sender@example.com"}},
            "bodyPreview": "본문 미리보기",
            "body": {"contentType": "html", "content": "<p>본문</p>"},
            "toRecipients": [],
            "internetMessageId": "<m-200@example.com>",
            "webLink": "https://outlook.office.com/mail/read/id/m-200",
        }


class GraphMailClientTest(unittest.TestCase):
    """
    GraphMailClient 동작을 검증한다.
    """

    def test_extract_aadsts_metadata_parses_trace_values(self) -> None:
        """
        AADSTS 오류 설명에서 Trace/Correlation/Timestamp를 파싱해야 한다.
        """
        description = (
            "AADSTS53003: Access blocked. Trace ID: 11111111-2222-3333-4444-555555555555 "
            "Correlation ID: aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee Timestamp: 2026-02-28 11:20:25Z"
        )
        metadata = _extract_aadsts_metadata(error_description=description)
        self.assertEqual("11111111-2222-3333-4444-555555555555", metadata["trace_id"])
        self.assertEqual("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", metadata["correlation_id"])
        self.assertEqual("2026-02-28", metadata["timestamp"][:10])

    def test_acquire_access_token_prefers_silent_when_account_exists(self) -> None:
        """
        계정과 silent 토큰이 있으면 interactive 로그인을 건너뛰어야 한다.
        """
        with patch.dict(os.environ, {"MICROSOFT_APP_ID": "client-id"}, clear=False):
            client = GraphMailClient()
        app_mock = Mock()
        app_mock.get_accounts.return_value = [{"home_account_id": "1"}]
        app_mock.acquire_token_silent.return_value = {"access_token": "silent-token"}
        client._msal_app = app_mock
        token = client._acquire_access_token()
        self.assertEqual("silent-token", token)
        app_mock.acquire_token_interactive.assert_not_called()

    def test_acquire_access_token_logs_failure_when_interactive_fails(self) -> None:
        """
        silent/interactive 모두 실패하면 경고 로그를 남기고 빈 문자열을 반환해야 한다.
        """
        with patch.dict(os.environ, {"MICROSOFT_APP_ID": "client-id"}, clear=False):
            client = GraphMailClient()
        app_mock = Mock()
        app_mock.get_accounts.return_value = []
        app_mock.acquire_token_interactive.return_value = {
            "error": "access_denied",
            "error_description": "user cancelled",
        }
        client._msal_app = app_mock
        with self.assertLogs("app.integrations.microsoft_graph.mail_client", level="WARNING") as captured:
            token = client._acquire_access_token()
        self.assertEqual("", token)
        log_text = "\n".join(captured.output)
        self.assertIn("Graph Delegated 토큰 발급 실패", log_text)
        self.assertIn("access_denied", log_text)

    def test_get_message_logs_graph_error_metadata_on_non_200(self) -> None:
        """
        Graph 메시지 조회 실패 시 Graph 에러 코드와 request ID가 로그에 포함되어야 한다.
        """
        with patch.dict(os.environ, {"MICROSOFT_APP_ID": "client-id"}, clear=False):
            client = GraphMailClient()
        with patch.object(client, "_acquire_access_token", return_value="token"):
            with patch(
                "app.integrations.microsoft_graph.mail_client.requests.get",
                return_value=_FakeResponse(),
            ):
                with self.assertLogs(
                    "app.integrations.microsoft_graph.mail_client",
                    level="WARNING",
                ) as captured:
                    result = client.get_message(
                        mailbox_user="jaeyoung_dev@outlook.com",
                        message_id="AQMkADAwATMwMAExLWE2",
                    )
        self.assertIsNone(result)
        log_text = "\n".join(captured.output)
        self.assertIn("status=403", log_text)
        self.assertIn("graph_error_code=ErrorAccessDenied", log_text)
        self.assertIn("request_id=inner-request-id", log_text)

    def test_get_message_retries_once_on_401_and_returns_message(self) -> None:
        """
        401 발생 시 토큰을 재획득한 뒤 1회 재시도하여 성공 응답을 반환해야 한다.
        """
        with patch.dict(os.environ, {"MICROSOFT_APP_ID": "client-id"}, clear=False):
            client = GraphMailClient()
        with patch.object(
            client,
            "_acquire_access_token",
            side_effect=["token-first", "token-refreshed"],
        ) as acquire_mock:
            with patch(
                "app.integrations.microsoft_graph.mail_client.requests.get",
                side_effect=[_FakeUnauthorizedResponse(), _FakeOkResponse()],
            ) as request_mock:
                result = client.get_message(
                    mailbox_user="jaeyoung_dev@outlook.com",
                    message_id="AQMkADAwATMwMAExLWE2",
                )
        self.assertIsNotNone(result)
        self.assertEqual("m-200", result.message_id if result else "")
        self.assertEqual(2, request_mock.call_count)
        self.assertEqual(2, acquire_mock.call_count)

    def test_get_message_returns_none_when_retry_after_401_still_fails(self) -> None:
        """
        401 이후 재시도도 실패하면 None을 반환해야 한다.
        """
        with patch.dict(os.environ, {"MICROSOFT_APP_ID": "client-id"}, clear=False):
            client = GraphMailClient()
        with patch.object(
            client,
            "_acquire_access_token",
            side_effect=["token-first", "token-refreshed"],
        ) as acquire_mock:
            with patch(
                "app.integrations.microsoft_graph.mail_client.requests.get",
                side_effect=[_FakeUnauthorizedResponse(), _FakeUnauthorizedResponse()],
            ) as request_mock:
                result = client.get_message(
                    mailbox_user="jaeyoung_dev@outlook.com",
                    message_id="AQMkADAwATMwMAExLWE2",
                )
        self.assertIsNone(result)
        self.assertEqual(2, request_mock.call_count)
        self.assertEqual(2, acquire_mock.call_count)

    def test_parse_graph_mail_payload_strips_html_style_noise(self) -> None:
        """
        HTML 본문은 style/script를 제거한 텍스트로 정규화해야 한다.
        """
        payload = {
            "id": "msg-1",
            "subject": "회의 일정",
            "receivedDateTime": "2026-03-10T00:00:00Z",
            "from": {"emailAddress": {"address": "sender@example.com"}},
            "bodyPreview": "미리보기",
            "body": {
                "contentType": "html",
                "content": (
                    "<style>table{width:640px}@media only screen and (max-width:640px){}</style>"
                    "<div>안녕하세요, 회의 일정 공유드립니다.</div>"
                    "<script>console.log('x')</script>"
                ),
            },
            "internetMessageId": "<msg-1@example.com>",
            "webLink": "https://outlook.office.com",
        }
        message = _parse_graph_mail_payload(payload=payload)
        self.assertIn("안녕하세요, 회의 일정 공유드립니다.", message.body_text)
        self.assertNotIn("table{width:640px}", message.body_text)
        self.assertNotIn("@media only screen", message.body_text)
        self.assertNotIn("console.log", message.body_text)


if __name__ == "__main__":
    unittest.main()
