from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.services.mail_summary_llm_service import MailSummaryLLMService


class MailSummaryLLMServiceTest(unittest.TestCase):
    """
    LLM summary 서비스의 fallback 요약 품질을 검증한다.
    """

    @patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": ""}, clear=False)
    def test_fallback_summary_uses_subject_when_body_is_noisy(self) -> None:
        """
        본문이 HTML/코드 노이즈면 제목 기반 함축 요약으로 생성되어야 한다.
        """
        service = MailSummaryLLMService()
        result = service.summarize(
            subject="Grafana Daily Report 미수신 확인 요청",
            body_text="&nbsp; <div> RIGHTS RESERVED </div> outer = APIRouter() logger = get_logger(__name__)",
        )
        self.assertIn("Grafana Daily Report", result.summary)
        self.assertLessEqual(len(result.summary), 140)

    @patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "", "AZURE_OPENAI_ENDPOINT": ""}, clear=False)
    def test_fallback_summary_is_compact(self) -> None:
        """
        fallback 요약은 장문 본문이어도 140자 이내로 압축되어야 한다.
        """
        service = MailSummaryLLMService()
        body = " ".join(["회의 결과 공유드립니다."] * 60)
        result = service.summarize(subject="회의 결과", body_text=body)
        self.assertTrue(bool(result.summary.strip()))
        self.assertLessEqual(len(result.summary), 140)


if __name__ == "__main__":
    unittest.main()
