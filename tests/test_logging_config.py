from __future__ import annotations

import os
import unittest

from app.core.logging_config import is_prompt_trace_enabled


class LoggingConfigTest(unittest.TestCase):
    """
    로깅 설정 유틸리티를 검증한다.
    """

    def test_prompt_trace_enabled_for_truthy_values(self) -> None:
        """
        PROMPT_TRACE_ENABLED가 truthy 값이면 True를 반환해야 한다.
        """
        original = os.environ.get("PROMPT_TRACE_ENABLED")
        try:
            os.environ["PROMPT_TRACE_ENABLED"] = "1"
            self.assertTrue(is_prompt_trace_enabled())
            os.environ["PROMPT_TRACE_ENABLED"] = "true"
            self.assertTrue(is_prompt_trace_enabled())
        finally:
            _restore_env(original)

    def test_prompt_trace_disabled_for_falsey_values(self) -> None:
        """
        PROMPT_TRACE_ENABLED가 falsey 값이면 False를 반환해야 한다.
        """
        original = os.environ.get("PROMPT_TRACE_ENABLED")
        try:
            os.environ["PROMPT_TRACE_ENABLED"] = "0"
            self.assertFalse(is_prompt_trace_enabled())
            os.environ["PROMPT_TRACE_ENABLED"] = "off"
            self.assertFalse(is_prompt_trace_enabled())
        finally:
            _restore_env(original)


def _restore_env(original: str | None) -> None:
    """
    테스트 후 PROMPT_TRACE_ENABLED 환경변수를 복구한다.

    Args:
        original: 테스트 시작 전 환경변수 값
    """
    if original is None:
        os.environ.pop("PROMPT_TRACE_ENABLED", None)
        return
    os.environ["PROMPT_TRACE_ENABLED"] = original


if __name__ == "__main__":
    unittest.main()
