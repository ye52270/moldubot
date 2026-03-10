from __future__ import annotations

import unittest
from unittest.mock import patch

from app.middleware.registry import _build_summarization_middleware, build_agent_middlewares


class MiddlewareRegistryTest(unittest.TestCase):
    """미들웨어 레지스트리 조립 규칙을 검증한다."""

    def test_build_without_azure_key_skips_summarization(self) -> None:
        """Azure OpenAI 필수 키가 없으면 요약 미들웨어를 제외해야 한다."""
        with patch.dict("os.environ", {"AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": ""}, clear=False):
            middlewares = build_agent_middlewares()

        middleware_names = [type(item).__name__ for item in middlewares]
        self.assertNotIn("SummarizationMiddleware", middleware_names)
        self.assertIn("HumanInTheLoopMiddleware", middleware_names)

    def test_build_with_azure_key_enables_summarization(self) -> None:
        """Azure OpenAI 키/엔드포인트가 있으면 요약 미들웨어가 포함되어야 한다."""
        with patch.dict(
            "os.environ",
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
            },
            clear=False,
        ):
            middlewares = build_agent_middlewares()

        middleware_names = [type(item).__name__ for item in middlewares]
        self.assertIn("SummarizationMiddleware", middleware_names)
        self.assertIn("HumanInTheLoopMiddleware", middleware_names)

    def test_build_summarization_middleware_without_key_returns_none(self) -> None:
        """요약 미들웨어 빌더는 키가 없을 때 None을 반환해야 한다."""
        with patch.dict("os.environ", {"AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": ""}, clear=False):
            middleware = _build_summarization_middleware()

        self.assertIsNone(middleware)


if __name__ == "__main__":
    unittest.main()
