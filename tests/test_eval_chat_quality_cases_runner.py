from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tests import eval_chat_quality_cases


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self._status_code = status_code

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _ = (exc_type, exc, tb)
        return False

    def getcode(self) -> int:
        return self._status_code

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")


class EvalChatQualityCasesRunnerTest(unittest.TestCase):
    """
    run_chat_quality_cases 실행 파라미터 동작을 검증한다.
    """

    def test_run_chat_quality_cases_respects_max_cases(self) -> None:
        """
        max_cases 지정 시 앞에서부터 지정 개수만 실행해야 한다.
        """
        called = {"count": 0}

        def fake_urlopen(req, timeout):
            _ = (req, timeout)
            called["count"] += 1
            return _FakeResponse({"answer": "ok", "metadata": {"source": "deep-agent"}})

        original_cases = list(eval_chat_quality_cases.CHAT_QUALITY_CASES)
        eval_chat_quality_cases.CHAT_QUALITY_CASES = [
            {"case_id": 1, "utterance": "a", "pattern": "x"},
            {"case_id": 2, "utterance": "b", "pattern": "y"},
            {"case_id": 3, "utterance": "c", "pattern": "z"},
        ]
        try:
            with patch("tests.eval_chat_quality_cases.request.urlopen", side_effect=fake_urlopen):
                result = eval_chat_quality_cases.run_chat_quality_cases(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    request_timeout_sec=5,
                    max_cases=2,
                )
        finally:
            eval_chat_quality_cases.CHAT_QUALITY_CASES = original_cases

        self.assertEqual(2, called["count"])
        self.assertEqual(2, result["summary"]["total"])


if __name__ == "__main__":
    unittest.main()
