from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from scripts.export_agent_graph import PLACEHOLDER_OPENAI_KEY, generate_agent_graph_mermaid, resolve_output_path, temporary_openai_key


class ExportAgentGraphTest(unittest.TestCase):
    """`scripts/export_agent_graph.py`의 핵심 동작을 검증한다."""

    def test_resolve_output_path_with_relative_path(self) -> None:
        """상대 경로는 root_dir 기준 절대 경로로 정규화되어야 한다."""
        resolved = resolve_output_path(raw_output="docs/agent_graph.mmd", root_dir=Path("/tmp/moldubot"))
        self.assertEqual(Path("/tmp/moldubot/docs/agent_graph.mmd"), resolved)

    def test_resolve_output_path_with_absolute_path(self) -> None:
        """절대 경로는 원본을 유지해야 한다."""
        resolved = resolve_output_path(
            raw_output="/Users/jaeyoung/Desktop/moldubot/docs/agent_graph.mmd",
            root_dir=Path("/tmp/moldubot"),
        )
        self.assertEqual(Path("/Users/jaeyoung/Desktop/moldubot/docs/agent_graph.mmd"), resolved)

    def test_temporary_openai_key_injects_placeholder_when_missing(self) -> None:
        """OPENAI 키가 없으면 컨텍스트 내부에서 플레이스홀더 키를 주입해야 한다."""
        with patch.dict(os.environ, {}, clear=True):
            with temporary_openai_key():
                self.assertEqual(PLACEHOLDER_OPENAI_KEY, os.getenv("OPENAI_API_KEY"))
            self.assertIsNone(os.getenv("OPENAI_API_KEY"))

    def test_generate_agent_graph_mermaid_returns_mermaid_text(self) -> None:
        """그래프 생성 함수는 agent graph의 Mermaid 문자열을 반환해야 한다."""
        fake_graph_view = MagicMock()
        fake_graph_view.draw_mermaid.return_value = "graph TD; A-->B;"
        fake_graph = MagicMock()
        fake_graph.get_graph.return_value = fake_graph_view
        fake_agent = MagicMock()
        fake_agent._graph = fake_graph

        with patch("scripts.export_agent_graph.get_deep_chat_agent", return_value=fake_agent):
            mermaid = generate_agent_graph_mermaid()

        self.assertEqual("graph TD; A-->B;", mermaid)


if __name__ == "__main__":
    unittest.main()
