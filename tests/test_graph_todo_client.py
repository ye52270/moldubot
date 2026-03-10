from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from app.integrations.microsoft_graph.todo_client import GraphTodoClient


class GraphTodoClientTest(unittest.TestCase):
    """GraphTodoClient 동작을 검증한다."""

    def test_create_task_success(self) -> None:
        auth_client = MagicMock()
        auth_client.is_configured.return_value = True
        auth_client.acquire_access_token.return_value = "token-1"
        list_response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {"value": [{"id": "list-1", "displayName": "Tasks"}]},
            headers={},
        )
        task_response = types.SimpleNamespace(
            status_code=201,
            json=lambda: {"id": "todo-1", "webLink": "https://outlook.live.com/tasks/1"},
            headers={},
        )
        with patch(
            "app.integrations.microsoft_graph.todo_client.requests.get",
            return_value=list_response,
        ):
            with patch(
                "app.integrations.microsoft_graph.todo_client.requests.post",
                return_value=task_response,
            ):
                client = GraphTodoClient(auth_client=auth_client)
                task = client.create_task(
                    title="기술 이슈 점검",
                    due_date="2026-03-05",
                    body_text="현재메일 요약 기반 생성",
                )

        self.assertIsNotNone(task)
        self.assertEqual("todo-1", task.task_id if task else "")
        self.assertEqual("https://outlook.live.com/tasks/1", task.web_link if task else "")

    def test_create_task_returns_none_when_not_configured(self) -> None:
        auth_client = MagicMock()
        auth_client.is_configured.return_value = False
        client = GraphTodoClient(auth_client=auth_client)
        task = client.create_task(
            title="기술 이슈 점검",
            due_date="2026-03-05",
            body_text="",
        )
        self.assertIsNone(task)


if __name__ == "__main__":
    unittest.main()
