from __future__ import annotations

import unittest

from app.middleware.agent_middlewares import (
    TRACE_MAX_CONTENT_CHARS,
    TRACE_TRUNCATION_SUFFIX,
    _normalize_trace_content,
)


class AgentMiddlewaresTraceTest(unittest.TestCase):
    """프롬프트 트레이스 직렬화의 content 길이 제한 동작을 검증한다."""

    def test_normalize_trace_content_truncates_long_string(self) -> None:
        """긴 문자열 content는 trace 최대 길이를 초과하지 않게 잘라야 한다."""
        raw = "A" * (TRACE_MAX_CONTENT_CHARS + 50)
        normalized = _normalize_trace_content(raw)
        self.assertIsInstance(normalized, str)
        self.assertTrue(str(normalized).endswith(TRACE_TRUNCATION_SUFFIX))
        self.assertLessEqual(len(str(normalized)), TRACE_MAX_CONTENT_CHARS + len(TRACE_TRUNCATION_SUFFIX))


if __name__ == "__main__":
    unittest.main()
