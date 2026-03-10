from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.next_action_recommender import recommend_next_actions
from app.services.next_action_recommender_engine import _get_domain_embeddings, _resolve_embedding_deployment


class NextActionRecommenderTest(unittest.TestCase):
    """
    도메인 기반 next_actions 추천기 단위 테스트.
    """

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_returns_top3_actionable_items_for_current_mail(self) -> None:
        """
        현재메일 컨텍스트에서는 실행 가능한 도메인 액션을 최대 3개 반환해야 한다.
        """
        result = recommend_next_actions(
            user_message="현재메일 요약해줘",
            answer="조치 필요 사항과 회신 필요 내용이 있습니다. 일정 협의가 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "message_id": "m-1",
                    "subject": "일정 협의 및 조치 요청",
                    "summary_text": "회신과 todo 정리가 필요합니다.",
                },
            },
            intent_task_type="summary",
            intent_output_format="structured_template",
        )

        self.assertLessEqual(len(result), 3)
        self.assertGreaterEqual(len(result), 1)
        for item in result:
            self.assertIn("title", item)
            self.assertIn("query", item)
            self.assertIn(item.get("priority"), {"high", "medium", "low"})

    @patch.dict(
        "os.environ",
        {
            "MOLDUBOT_ACTION_USE_EMBEDDING": "0",
            "MOLDUBOT_ACTION_ENABLE_MEETING_ROOM": "0",
        },
        clear=False,
    )
    def test_filters_disabled_capability_action(self) -> None:
        """
        기능 플래그가 꺼진 도메인은 추천 목록에서 제외되어야 한다.
        """
        result = recommend_next_actions(
            user_message="회의실 예약 필요",
            answer="참석자 8명 회의가 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {"message_id": "m-2", "subject": "회의실 예약 요청"},
            },
            intent_task_type="calendar",
            intent_output_format="action",
        )

        titles = [item.get("title", "") for item in result]
        self.assertNotIn("회의실 예약", titles)

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_excludes_current_mail_only_actions_without_mail_context(self) -> None:
        """
        현재메일 컨텍스트가 없으면 current_mail 전용 액션은 제외되어야 한다.
        """
        result = recommend_next_actions(
            user_message="이슈 관련해서 다음에 뭘 하면 좋을까",
            answer="원인 분석이 추가로 필요합니다.",
            tool_payload={"action": "mail_search", "count": 5},
            intent_task_type="analysis",
            intent_output_format="structured_template",
        )

        titles = [item.get("title", "") for item in result]
        self.assertNotIn("회신 초안 작성", titles)
        self.assertNotIn("할 일(ToDo) 등록", titles)

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_recommends_code_snippet_analysis_for_code_security_context(self) -> None:
        """
        코드/보안 조치 문맥에서는 코드 스니펫 분석 액션이 추천되어야 한다.
        """
        result = recommend_next_actions(
            user_message="현재메일 요약해줘",
            answer="조치 필요 사항: 코드 리뷰 및 보안 정책 확인이 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "message_id": "m-3",
                    "subject": "FW: login form",
                    "summary_text": "보안 관련 스크립트와 코드 검토가 필요합니다.",
                    "body_preview": "if (user.isAuthenticated) { showDashboard(); }",
                },
            },
            intent_task_type="summary",
            intent_output_format="structured_template",
        )
        titles = [item.get("title", "") for item in result]
        self.assertIn("코드 스니펫 분석", titles)
        code_action = next((item for item in result if item.get("title") == "코드 스니펫 분석"), {})
        self.assertIn("코드 리뷰", str(code_action.get("query", "")))

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_excludes_code_snippet_action_without_code_evidence(self) -> None:
        """
        코드 증거가 없으면 코드 스니펫 분석 액션은 추천되지 않아야 한다.
        """
        result = recommend_next_actions(
            user_message="현재메일 요약해줘",
            answer="조치 필요 사항: 보안 정책 확인과 담당자 공유가 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "message_id": "m-4",
                    "subject": "FW: 설날 연휴 안내",
                    "summary_text": "팀 인사와 연휴 안내 메일입니다.",
                    "body_preview": "새해 복 많이 받으시고 안전한 귀경길 되세요.",
                },
            },
            intent_task_type="summary",
            intent_output_format="structured_template",
        )
        titles = [item.get("title", "") for item in result]
        self.assertNotIn("코드 스니펫 분석", titles)

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_recommends_code_snippet_action_when_code_only_in_body_code_excerpt(self) -> None:
        """
        코드가 body_code_excerpt에만 있어도 코드 스니펫 분석 액션이 추천되어야 한다.
        """
        result = recommend_next_actions(
            user_message="현재메일 요약해줘",
            answer="조치 필요 사항: 보안 정책 확인과 코드 검토가 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "message_id": "m-5",
                    "subject": "FW: 인증 로직 점검",
                    "summary_text": "인증 관련 코드 검토 요청",
                    "body_excerpt": "요청 배경과 일정 안내입니다.",
                    "body_code_excerpt": "def verify_token(token: str) -> bool:\n    return token.startswith('sk-')",
                },
            },
            intent_task_type="summary",
            intent_output_format="structured_template",
        )
        titles = [item.get("title", "") for item in result]
        self.assertIn("코드 스니펫 분석", titles)

    @patch.dict("os.environ", {"MOLDUBOT_ACTION_USE_EMBEDDING": "0"}, clear=False)
    def test_recommends_code_snippet_action_for_jsp_markup_preview(self) -> None:
        """
        JSP/HTML 마크업 코드가 body_preview에 있으면 코드 스니펫 분석이 추천되어야 한다.
        """
        result = recommend_next_actions(
            user_message="현재메일 요약해줘",
            answer="로그인 페이지 코드의 보안 점검이 필요합니다.",
            tool_payload={
                "action": "current_mail",
                "body_preview": (
                    "[hintadmin@hintssodev template]$ cat login.default.jsp "
                    "<%--로그인 기본 페이지--%><%@include file=\"../../taglibs.jsp\" %>"
                    "<div class=\"login\">"
                ),
                "mail_context": {
                    "message_id": "m-6",
                    "subject": "FW: login form",
                },
            },
            intent_task_type="summary",
            intent_output_format="structured_template",
        )
        titles = [item.get("title", "") for item in result]
        self.assertIn("코드 스니펫 분석", titles)

    @patch.dict("os.environ", {"AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-large"}, clear=False)
    def test_resolve_embedding_deployment_prefers_azure_embedding_env(self) -> None:
        """
        임베딩 배포명은 AZURE_OPENAI_EMBEDDING_DEPLOYMENT 값을 우선 사용해야 한다.
        """
        deployment = _resolve_embedding_deployment()
        self.assertEqual("text-embedding-3-large", deployment)

    def test_domain_embedding_cache_is_separated_by_deployment(self) -> None:
        """
        임베딩 캐시는 deployment가 다르면 분리되어야 한다.
        """
        _get_domain_embeddings.cache_clear()

        class _FakeEmbeddings:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def create(self, model: str, input: list[str]):
                self.calls.append(model)
                class _Item:
                    embedding = [0.1, 0.2]
                class _Response:
                    data = [_Item()]
                return _Response()

        class _FakeClient:
            def __init__(self) -> None:
                self.embeddings = _FakeEmbeddings()

        fake_client = _FakeClient()
        with patch("app.services.next_action_recommender_engine._get_embedding_client", return_value=fake_client):
            _get_domain_embeddings(domain_texts=("domain-a",), deployment="text-embedding-3-small")
            _get_domain_embeddings(domain_texts=("domain-a",), deployment="text-embedding-3-large")

        self.assertEqual(["text-embedding-3-small", "text-embedding-3-large"], fake_client.embeddings.calls)


if __name__ == "__main__":
    unittest.main()
