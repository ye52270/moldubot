from __future__ import annotations

import importlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_build_graph_passes_skills_when_env_configured(self) -> None:
        """skills 경로 환경변수가 있으면 create_deep_agent에 전달해야 한다."""
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

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "dummy-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
                "MOLDUBOT_AGENT_SKILLS_PATHS": "/skills/core,/skills/mail",
            },
            clear=False,
        ):
            with patch.object(module, "create_deep_agent", side_effect=_fake_create_deep_agent):
                module.build_graph()

        self.assertEqual(["/skills/core", "/skills/mail"], captured.get("skills"))

    def test_build_graph_uses_filesystem_backend_when_skills_configured(self) -> None:
        """skills 경로가 있으면 FilesystemBackend도 함께 주입해야 한다."""
        module = importlib.import_module("app.agents.langgraph_entry")
        captured: dict[str, object] = {}
        fake_backend = object()

        class _DummyGraph:
            def invoke(self, payload: object, config: object | None = None) -> dict[str, object]:
                del payload, config
                return {}

        def _fake_create_deep_agent(*args: object, **kwargs: object) -> object:
            del args
            captured.update(kwargs)
            return _DummyGraph()

        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "dummy-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-12-01-preview",
                "MOLDUBOT_AGENT_SKILLS_PATHS": "/skills/core",
            },
            clear=False,
        ):
            with patch.object(module, "create_deep_agent", side_effect=_fake_create_deep_agent):
                with patch.object(module, "build_agent_backend", return_value=fake_backend):
                    module.build_graph()

        self.assertIs(fake_backend, captured.get("backend"))

    def test_build_graph_can_use_persistent_checkpointer_when_configured(self) -> None:
        """환경변수로 persistent checkpointer가 설정되면 해당 객체를 주입해야 한다."""
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
        fake_checkpointer = MagicMock()

        class _DummyGraph:
            def invoke(self, payload: object, config: object | None = None) -> dict[str, object]:
                del payload, config
                return {}

        def _fake_create_deep_agent(*args: object, **kwargs: object) -> object:
            del args
            captured.update(kwargs)
            return _DummyGraph()

        with patch.object(module, "create_deep_agent", side_effect=_fake_create_deep_agent):
            with patch.object(module, "build_agent_checkpointer", return_value=fake_checkpointer):
                graph = module.build_graph()

        self.assertTrue(hasattr(graph, "invoke"))
        self.assertIs(fake_checkpointer, captured.get("checkpointer"))


if __name__ == "__main__":
    unittest.main()
