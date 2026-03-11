from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.services.intent_taxonomy_config import get_intent_taxonomy, reset_intent_taxonomy_cache


class IntentTaxonomyConfigTest(unittest.TestCase):
    """intent taxonomy 설정 로드/리로드 동작을 검증한다."""

    def tearDown(self) -> None:
        os.environ.pop("INTENT_TAXONOMY_CONFIG_PATH", None)
        reset_intent_taxonomy_cache()

    def test_uses_default_when_config_file_missing(self) -> None:
        """설정 파일이 없으면 기본 정책을 반환해야 한다."""
        os.environ["INTENT_TAXONOMY_CONFIG_PATH"] = "/tmp/not-exists-intent-taxonomy.json"
        config = get_intent_taxonomy()
        self.assertFalse(config.enable_token_fallback)
        self.assertEqual((), config.recipient_todo_policy.recipient_tokens)
        self.assertEqual((), config.recipient_todo_policy.todo_tokens)
        self.assertEqual((), config.recipient_todo_policy.due_tokens)

    def test_reload_when_config_file_changes(self) -> None:
        """설정 파일 변경 시 mtime 기반으로 자동 리로드되어야 한다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "intent_taxonomy.json"
            config_path.write_text(
                json.dumps(
                    {
                        "enable_token_fallback": True,
                        "recipient_todo_policy": {
                            "recipient_tokens": ["수신자"],
                            "todo_tokens": ["todo"],
                            "due_tokens": ["기한"],
                            "registration_tokens": ["등록"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.environ["INTENT_TAXONOMY_CONFIG_PATH"] = str(config_path)
            first = get_intent_taxonomy()
            self.assertTrue(first.enable_token_fallback)
            self.assertEqual(("수신자",), first.recipient_todo_policy.recipient_tokens)

            config_path.write_text(
                json.dumps(
                    {
                        "enable_token_fallback": True,
                        "recipient_todo_policy": {
                            "recipient_tokens": ["assignee"],
                            "todo_tokens": ["action"],
                            "due_tokens": ["due"],
                            "registration_tokens": ["create"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            time.sleep(0.01)

            second = get_intent_taxonomy()
            self.assertTrue(second.enable_token_fallback)
            self.assertEqual(("assignee",), second.recipient_todo_policy.recipient_tokens)
            self.assertEqual(("action",), second.recipient_todo_policy.todo_tokens)
            self.assertEqual(("due",), second.recipient_todo_policy.due_tokens)
            self.assertEqual(("create",), second.recipient_todo_policy.registration_tokens)

    def test_tokens_are_ignored_when_fallback_disabled(self) -> None:
        """fallback 비활성 시 설정 파일 토큰이 있어도 런타임 토큰은 비워야 한다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "intent_taxonomy.json"
            config_path.write_text(
                json.dumps(
                    {
                        "enable_token_fallback": False,
                        "recipient_todo_policy": {
                            "recipient_tokens": ["수신자"],
                            "todo_tokens": ["todo"],
                            "due_tokens": ["기한"],
                            "registration_tokens": ["등록"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            os.environ["INTENT_TAXONOMY_CONFIG_PATH"] = str(config_path)
            loaded = get_intent_taxonomy()

        self.assertFalse(loaded.enable_token_fallback)
        self.assertEqual((), loaded.recipient_todo_policy.recipient_tokens)
        self.assertEqual((), loaded.recipient_todo_policy.todo_tokens)
        self.assertEqual((), loaded.recipient_todo_policy.due_tokens)
        self.assertEqual((), loaded.recipient_todo_policy.registration_tokens)


if __name__ == "__main__":
    unittest.main()
