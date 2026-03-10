from __future__ import annotations

import importlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver


class LangGraphConfigTest(unittest.TestCase):
    """LangGraph Studio 로컬 실행 구성을 검증한다."""

    def test_langgraph_json_declares_graph_entry(self) -> None:
        """`langgraph.json`이 MolduBot 그래프 엔트리를 선언해야 한다."""
        root_dir = Path(__file__).resolve().parents[1]
        config_path = root_dir / "langgraph.json"
        payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(".env", payload.get("env"))
        graphs = payload.get("graphs", {})
        self.assertEqual("./app/agents/langgraph_entry.py:graph", graphs.get("moldubot_chat"))

    def test_langgraph_entry_exposes_graph_object(self) -> None:
        """LangGraph 진입 모듈이 `graph` 객체를 노출해야 한다."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "dummy-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
            },
        ):
            module = importlib.import_module("app.agents.langgraph_entry")

        self.assertTrue(hasattr(module, "graph"))
        self.assertTrue(hasattr(module.graph, "invoke"))

    def test_build_graph_passes_checkpointer_to_deep_agent(self) -> None:
        """LangGraph 진입 그래프는 HITL 재개를 위해 checkpointer를 전달해야 한다."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "dummy-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
            },
            clear=False,
        ):
            module = importlib.import_module("app.agents.langgraph_entry")

        captured: dict[str, object] = {}

        class _DummyGraph:
            def invoke(self, payload: object, config: object | None = None) -> dict[str, object]:
                del payload, config
                return {}

        def _fake_create_deep_agent(*args: object, **kwargs: object) -> object:
            del args
            captured.update(kwargs)
            return _DummyGraph()

        with patch.object(module, "create_deep_agent", side_effect=_fake_create_deep_agent):
            graph = module.build_graph()

        self.assertTrue(hasattr(graph, "invoke"))
        self.assertIn("checkpointer", captured)
        self.assertIsInstance(captured.get("checkpointer"), InMemorySaver)


if __name__ == "__main__":
    unittest.main()
