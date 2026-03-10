from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.agents.agent_runtime_config import resolve_agent_skills_paths


class AgentRuntimeConfigTest(unittest.TestCase):
    """에이전트 런타임 설정 파서를 검증한다."""

    def test_returns_empty_when_env_missing(self) -> None:
        """환경변수가 없으면 빈 목록을 반환해야 한다."""
        with patch.dict(os.environ, {"MOLDUBOT_AGENT_SKILLS_PATHS": ""}, clear=False):
            paths = resolve_agent_skills_paths()
        self.assertEqual([], paths)

    def test_parses_comma_separated_paths(self) -> None:
        """콤마 구분 skills 경로를 정규화해야 한다."""
        with patch.dict(
            os.environ,
            {"MOLDUBOT_AGENT_SKILLS_PATHS": "/skills/core, /skills/mail ,/skills/core"},
            clear=False,
        ):
            paths = resolve_agent_skills_paths()
        self.assertEqual(["/skills/core", "/skills/mail"], paths)

    def test_parses_semicolon_and_newline(self) -> None:
        """세미콜론/줄바꿈 구분도 허용해야 한다."""
        with patch.dict(
            os.environ,
            {"MOLDUBOT_AGENT_SKILLS_PATHS": "/skills/a;/skills/b\n/skills/c"},
            clear=False,
        ):
            paths = resolve_agent_skills_paths()
        self.assertEqual(["/skills/a", "/skills/b", "/skills/c"], paths)


if __name__ == "__main__":
    unittest.main()
