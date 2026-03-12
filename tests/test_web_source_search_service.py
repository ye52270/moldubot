from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.web_source_search_service import (
    build_web_search_query,
    search_web_sources,
    should_search_web_sources,
)


class WebSourceSearchServiceTest(unittest.TestCase):
    """
    Tavily 웹 출처 검색 서비스 테스트.
    """

    def test_should_search_web_sources_by_keyword(self) -> None:
        """
        명시 외부근거 요청 토큰이 있을 때만 웹 검색이 트리거되어야 한다.
        """
        self.assertTrue(should_search_web_sources("인터넷으로 검색해서 출처 포함해줘"))
        self.assertFalse(should_search_web_sources("SSL 오류 원인 알려줘"))
        self.assertFalse(should_search_web_sources("현재메일 요약해줘", intent_task_type="summary"))
        self.assertTrue(
            should_search_web_sources(
                "이 답변이 정말 맞는지 근거와 출처를 검증해줘",
                intent_task_type="analysis",
                resolved_scope="global_search",
                tool_payload={},
            )
        )
        self.assertFalse(
            should_search_web_sources(
                "SSL 오류 원인 알려줘",
                intent_task_type="analysis",
                resolved_scope="current_mail",
                tool_payload={"action": "current_mail"},
            )
        )
        self.assertTrue(
            should_search_web_sources(
                "현재메일 기준으로 이 내용이 맞는지 검증해줘",
                intent_task_type="analysis",
                resolved_scope="current_mail",
                tool_payload={"action": "current_mail"},
            )
        )
        self.assertTrue(
            should_search_web_sources(
                "현재메일 기준으로 외부 최신 공식문서 찾아줘",
                intent_task_type="analysis",
                resolved_scope="current_mail",
                tool_payload={"action": "current_mail"},
            )
        )
        self.assertFalse(
            should_search_web_sources(
                "원인과 대응 정리해줘",
                intent_task_type="analysis",
                intent_confidence=0.51,
            )
        )

    @patch("app.services.web_source_search_service.os.getenv", return_value="test-key")
    @patch("app.services.web_source_search_service.httpx.post")
    def test_search_web_sources_normalizes_results(
        self,
        mocked_post: Mock,
        _mocked_getenv: Mock,
    ) -> None:
        """
        Tavily 응답을 UI용 출처 목록으로 정규화해야 한다.
        """
        fake_response = Mock()
        fake_response.content = b"ok"
        fake_response.json.return_value = {
            "results": [
                {
                    "title": "OpenAI latency optimization",
                    "url": "https://platform.openai.com/docs/guides/latency-optimization",
                    "content": "Streaming and prompt caching reduce latency.",
                    "favicon": "https://platform.openai.com/favicon.ico",
                },
                {
                    "title": "OpenAI latency optimization duplicate",
                    "url": "https://platform.openai.com/docs/guides/latency-optimization",
                    "content": "duplicate row should be removed",
                },
            ]
        }
        fake_response.raise_for_status.return_value = None
        mocked_post.return_value = fake_response

        result = search_web_sources("latency optimization", max_results=4)
        self.assertEqual(1, len(result))
        self.assertEqual("platform.openai.com", result[0]["site_name"])
        self.assertEqual("P", result[0]["icon_text"])
        self.assertEqual("https://platform.openai.com/favicon.ico", result[0]["favicon_url"])

    def test_build_web_search_query_uses_code_context(self) -> None:
        """
        코드리뷰 질의는 코드 문맥 기반 Tavily 질의를 생성해야 한다.
        """
        tool_payload = {
            "mail_context": {
                "body_code_excerpt": (
                    '<%@include file="../../taglibs.jsp" %>\n'
                    '<input type="password" name="PWDNAME" />\n'
                    '<logic:equal value="true" name="ISAUTHN">'
                )
            }
        }
        query = build_web_search_query(
            user_message="현재메일 코드 리뷰해줘",
            intent_task_type="analysis",
            tool_payload=tool_payload,
        )
        self.assertIn("JSP", query)
        self.assertIn("CSRF", query)
        self.assertIn("XSS", query)
        self.assertIn("PWDNAME", query)


if __name__ == "__main__":
    unittest.main()
