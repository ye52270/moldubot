from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.core.azure_openai_client import has_azure_openai_config, normalize_azure_deployment_name


class AzureOpenAIClientTest(unittest.TestCase):
    """Azure OpenAI 공통 헬퍼 동작을 검증한다."""

    @patch.dict(
        os.environ,
        {"AZURE_OPENAI_API_KEY": "test-key", "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/"},
        clear=True,
    )
    def test_has_azure_openai_config_true_when_required_envs_exist(self) -> None:
        """필수 환경변수가 모두 있으면 True를 반환해야 한다."""
        self.assertTrue(has_azure_openai_config())

    @patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}, clear=True)
    def test_has_azure_openai_config_false_when_endpoint_missing(self) -> None:
        """endpoint 누락 시 False를 반환해야 한다."""
        self.assertFalse(has_azure_openai_config())

    def test_normalize_azure_deployment_name_strips_provider_prefix(self) -> None:
        """provider 접두어가 포함된 모델 문자열에서 배포명만 추출해야 한다."""
        deployment = normalize_azure_deployment_name("azure_openai:gpt-4o-mini")
        self.assertEqual("gpt-4o-mini", deployment)


if __name__ == "__main__":
    unittest.main()
