from __future__ import annotations

import types
import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.runtime_components import _build_sqlite_checkpointer, build_agent_checkpointer


class AgentRuntimeComponentsTest(unittest.TestCase):
    """Deep Agents runtime component 조립을 검증한다."""

    def test_build_agent_checkpointer_falls_back_to_memory_when_sqlite_module_missing(self) -> None:
        """sqlite backend가 설정돼도 모듈이 없으면 InMemorySaver로 폴백해야 한다."""
        with patch("app.agents.runtime_components.importlib.import_module", side_effect=ModuleNotFoundError()):
            checkpointer = build_agent_checkpointer(cache_namespace="sqlite-fallback")

        self.assertIsInstance(checkpointer, InMemorySaver)

    def test_build_sqlite_checkpointer_enters_context_manager_resource(self) -> None:
        """sqlite saver factory가 context manager를 반환하면 enter 결과를 사용해야 한다."""

        class _FakeContextManager:
            def __init__(self) -> None:
                self.entered = False

            def __enter__(self) -> str:
                self.entered = True
                return "sqlite-saver"

            def __exit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb
                return None

        class _FakeSqliteSaver:
            @staticmethod
            def from_conn_string(conn: str) -> _FakeContextManager:
                self.assertTrue(conn.endswith(".db"))
                return _FakeContextManager()

        fake_module = types.SimpleNamespace(SqliteSaver=_FakeSqliteSaver)

        with patch("app.agents.runtime_components.importlib.import_module", return_value=fake_module):
            saver = _build_sqlite_checkpointer(sqlite_path="/tmp/moldubot-test.db")

        self.assertEqual("sqlite-saver", saver)


if __name__ == "__main__":
    unittest.main()
