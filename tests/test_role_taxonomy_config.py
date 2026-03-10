from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from app.services.answer_table_spec import render_current_mail_people_roles_table
from app.services.role_taxonomy_config import get_role_taxonomy, reset_role_taxonomy_cache


class RoleTaxonomyConfigTest(unittest.TestCase):
    """역할 taxonomy 설정 로드/리로드 동작을 검증한다."""

    def setUp(self) -> None:
        """테스트 시작 전 캐시와 환경변수를 정리한다."""
        reset_role_taxonomy_cache()
        self._original_path = os.environ.get("ROLE_TAXONOMY_CONFIG_PATH")

    def tearDown(self) -> None:
        """테스트 종료 후 캐시와 환경변수를 복원한다."""
        if self._original_path is None:
            os.environ.pop("ROLE_TAXONOMY_CONFIG_PATH", None)
        else:
            os.environ["ROLE_TAXONOMY_CONFIG_PATH"] = self._original_path
        reset_role_taxonomy_cache()

    def test_loads_default_when_config_file_missing(self) -> None:
        """설정 파일이 없으면 기본 taxonomy를 사용해야 한다."""
        os.environ["ROLE_TAXONOMY_CONFIG_PATH"] = "/tmp/not-exists-role-taxonomy.json"
        config = get_role_taxonomy()
        self.assertEqual("수신/실행 대상", config.default_roles["to"])
        self.assertGreaterEqual(len(config.role_hints), 1)

    def test_reload_reflects_updated_file_without_restart(self) -> None:
        """설정 파일 변경 시 재시작 없이 역할 규칙이 반영되어야 한다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "role_taxonomy.json"
            os.environ["ROLE_TAXONOMY_CONFIG_PATH"] = str(config_path)

            payload_a = {
                "default_roles": {"unknown": "역할 미상"},
                "role_hints": [{"keyword": "협의", "role": "검토자"}],
            }
            config_path.write_text(json.dumps(payload_a, ensure_ascii=False), encoding="utf-8")
            first_rendered = render_current_mail_people_roles_table(
                user_message="현재메일 본문에 명시된 사람들의 역할을 표 형태로 정리해줘",
                mail_context={"body_excerpt": "김민수님이 협의 요청했습니다."},
            )
            self.assertIn("| 김민수 | 검토자 |", first_rendered)

            payload_b = {
                "default_roles": {"unknown": "미분류"},
                "role_hints": [{"keyword": "협의", "role": "승인자"}],
            }
            config_path.write_text(json.dumps(payload_b, ensure_ascii=False), encoding="utf-8")
            os.utime(config_path, None)

            second_rendered = render_current_mail_people_roles_table(
                user_message="현재메일 본문에 명시된 사람들의 역할을 표 형태로 정리해줘",
                mail_context={"body_excerpt": "김민수님이 협의 요청했습니다."},
            )
            self.assertIn("| 김민수 | 승인자 |", second_rendered)


if __name__ == "__main__":
    unittest.main()
