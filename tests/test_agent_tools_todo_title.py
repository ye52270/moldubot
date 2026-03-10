from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.tools import create_outlook_todo
from app.integrations.microsoft_graph.todo_client import GraphTodoTask


class AgentToolsTodoTitleTest(unittest.TestCase):
    """
    Outlook ToDo 제목 정규화 동작을 검증한다.
    """

    def test_create_outlook_todo_normalizes_markdown_action_item_title(self) -> None:
        """
        마크다운/액션아이템 노이즈 제목은 메일 제목 요약 기반 형식으로 정규화해야 한다.
        """
        fake_mail = type("FakeMail", (), {"subject": "FW: [외부] ESG Data Hub- 전자결재(품의서) 연동 관련"})()
        with patch("app.agents.tools._TODO_CLIENT") as todo_client, patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            mail_service.get_current_mail.return_value = fake_mail
            todo_client.create_task.return_value = GraphTodoTask(
                task_id="todo-1",
                web_link="https://outlook.live.com/tasks/1",
            )

            payload = create_outlook_todo.func(
                title="## 액션 아이템 1. 액션 아이템을 확인하지 못했습니다.",
                due_date="2026-03-03",
                detail="구체적 책임자 배정 및 일정 확정",
            )

        self.assertEqual("completed", payload["status"])
        task_title = str(payload["task"]["title"])
        self.assertTrue(task_title.startswith("[전자결재품]"))
        self.assertIn("]", task_title)
        self.assertNotIn("[메일요약]", task_title)
        self.assertNotIn("##", task_title)
        self.assertNotIn("액션 아이템을 확인하지 못했습니다", task_title)

    def test_create_outlook_todo_adds_mail_summary_prefix_to_clean_title(self) -> None:
        """
        현재 메일 컨텍스트가 없으면 read_current_mail fallback으로 제목 접두어를 구성해야 한다.
        """
        with patch("app.agents.tools._TODO_CLIENT") as todo_client, patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            fake_mail = type("FakeMail", (), {"subject": "RE: 브로드넷 왼쪽 상단 서비스에이스 CI 변경"})()
            mail_service.get_current_mail.return_value = None
            mail_service.read_current_mail.return_value = fake_mail
            todo_client.create_task.return_value = GraphTodoTask(
                task_id="todo-2",
                web_link="https://outlook.live.com/tasks/2",
            )

            payload = create_outlook_todo.func(
                title="센스메일 작업 일정 확정",
                due_date="2026-03-03",
                detail="",
            )

        self.assertEqual("completed", payload["status"])
        task_title = str(payload["task"]["title"])
        self.assertTrue(task_title.startswith("[브로드넷왼]"))
        self.assertNotIn("[메일요약]", task_title)
        self.assertTrue(task_title.endswith("]센스메일 작업 일정 확정"))

    def test_create_outlook_todo_strips_model_inserted_mail_bracket_from_title(self) -> None:
        """
        모델이 제목에 메일 요약 대괄호를 포함해도 접두부에서 제거해야 한다.
        """
        fake_mail = type("FakeMail", (), {"subject": "FW: [새 앱] Microsoft 계정 연기 관련"})()
        with patch("app.agents.tools._TODO_CLIENT") as todo_client, patch("app.agents.tools._MAIL_SERVICE") as mail_service:
            mail_service.get_current_mail.return_value = fake_mail
            todo_client.create_task.return_value = GraphTodoTask(
                task_id="todo-3",
                web_link="https://outlook.live.com/tasks/3",
            )

            payload = create_outlook_todo.func(
                title="[새 앱이 Microsoft 계정에 연기한 내 센스메일] 구체적 책임자 배정 확인",
                due_date="2026-03-03",
                detail="",
            )

        self.assertEqual("completed", payload["status"])
        task_title = str(payload["task"]["title"])
        self.assertTrue(task_title.startswith("[계정연기관]"))
        self.assertNotIn("Microsoft 계정에 연기한", task_title)
        self.assertIn("구체적 책임자 배정 확인", task_title)

    def test_create_outlook_todo_normalizes_iso_due_date(self) -> None:
        """
        ISO datetime 형식의 due_date는 YYYY-MM-DD로 정규화해 등록해야 한다.
        """
        with patch("app.agents.tools._TODO_CLIENT") as todo_client:
            todo_client.create_task.return_value = GraphTodoTask(
                task_id="todo-4",
                web_link="https://outlook.live.com/tasks/4",
            )

            payload = create_outlook_todo.func(
                title="시스템 점검 일정 확인",
                due_date="2026-03-03T09:30:00Z",
                detail="",
            )

        self.assertEqual("completed", payload["status"])
        self.assertEqual("2026-03-03", payload["task"]["due_date"])

    def test_create_outlook_todo_uses_default_due_date_when_unparseable(self) -> None:
        """
        파싱 불가능한 due_date는 기본 마감일로 보정해 실패 없이 등록해야 한다.
        """
        with (
            patch("app.agents.tools._TODO_CLIENT") as todo_client,
            patch("app.agents.tools._resolve_default_outlook_todo_due_date", return_value="2026-03-07"),
        ):
            todo_client.create_task.return_value = GraphTodoTask(
                task_id="todo-5",
                web_link="https://outlook.live.com/tasks/5",
            )

            payload = create_outlook_todo.func(
                title="운영 정책 검토",
                due_date="미정",
                detail="",
            )

        self.assertEqual("completed", payload["status"])
        self.assertEqual("2026-03-07", payload["task"]["due_date"])

    def test_create_outlook_todo_returns_config_reason_when_graph_not_configured(self) -> None:
        """
        Graph ToDo 설정이 없으면 명시적인 설정 오류 사유를 반환해야 한다.
        """
        with patch("app.agents.tools._resolve_todo_client") as resolve_client:
            resolve_client.return_value.is_configured.return_value = False
            payload = create_outlook_todo.func(
                title="운영 점검",
                due_date="2026-03-07",
                detail="",
            )

        self.assertEqual("failed", payload["status"])
        self.assertIn("MICROSOFT_APP_ID", payload["reason"])


if __name__ == "__main__":
    unittest.main()
