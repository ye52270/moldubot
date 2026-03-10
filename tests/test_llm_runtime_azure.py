from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.core.llm_runtime import detect_provider, is_model_provider_configured, normalize_model_name


class LLMRuntimeAzureTest(unittest.TestCase):
    """Azure/OpenAI provider 정규화 및 키 감지 규칙을 검증한다."""

    @patch.dict(
        os.environ,
        {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
        },
        clear=True,
    )
    def test_normalize_model_name_prefers_azure_openai_when_azure_env_exists(self) -> None:
        """Azure 환경이 설정되면 gpt 계열 모델은 azure_openai provider로 정규화되어야 한다."""
        normalized = normalize_model_name("gpt-4o-mini")
        self.assertEqual("azure_openai:gpt-4o-mini", normalized)
        self.assertEqual("azure_openai", detect_provider("gpt-4o-mini"))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_normalize_model_name_keeps_openai_without_azure_env(self) -> None:
        """Azure 환경이 없고 OpenAI 키만 있으면 openai provider로 정규화되어야 한다."""
        normalized = normalize_model_name("gpt-4o-mini")
        self.assertEqual("openai:gpt-4o-mini", normalized)
        self.assertEqual("openai", detect_provider("gpt-4o-mini"))

    @patch.dict(
        os.environ,
        {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
        },
        clear=True,
    )
    def test_is_model_provider_configured_accepts_azure_openai(self) -> None:
        """azure_openai provider는 endpoint/api_key가 모두 있을 때만 사용 가능해야 한다."""
        self.assertTrue(is_model_provider_configured("azure_openai:gpt-4o-mini"))
        self.assertTrue(is_model_provider_configured("gpt-4o-mini"))

    @patch.dict(
        os.environ,
        {"AZURE_OPENAI_API_KEY": "test-key", "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/"},
        clear=True,
    )
    def test_is_model_provider_configured_rejects_missing_api_version(self) -> None:
        """Azure API 버전 누락 시 provider 준비 상태를 false로 반환해야 한다."""
        self.assertFalse(is_model_provider_configured("azure_openai:gpt-4o-mini"))


if __name__ == "__main__":
    unittest.main()
