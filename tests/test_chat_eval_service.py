from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.services import chat_eval_service


class ChatEvalServiceTest(unittest.TestCase):
    """chat_eval_service의 실행/저장 계약을 검증한다."""

    def test_run_chat_eval_session_builds_report_and_persists_latest(self) -> None:
        """주입된 chat/judge 호출기로 리포트를 생성하고 latest 파일을 저장해야 한다."""
        calls: list[dict[str, Any]] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            answer = f"응답:{payload.get('message')}"
            if "액션 아이템" in str(payload.get("message") or ""):
                answer = "1. 항목A\n2. 항목B"
            calls.append({"chat_url": chat_url, "payload": dict(payload), "timeout_sec": timeout_sec})
            return (
                200,
                {
                    "answer": answer,
                    "metadata": {"source": "deep-agent"},
                },
                123.4,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = judge_context
            return (
                {
                    "pass": "현재메일" not in query,
                    "score": 4,
                    "reason": "ok",
                    "checks": {
                        "intent_match": True,
                        "format_match": True,
                        "grounded": True,
                    },
                },
                88.1,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    judge_model="gpt-4o-mini",
                    selected_email_id="selected-id",
                    mailbox_user="user@example.com",
                    request_timeout_sec=30,
                    max_cases=3,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

            self.assertEqual(3, report["summary"]["total_cases"])
            self.assertEqual(123.4, report["summary"]["avg_chat_elapsed_ms"])
            self.assertEqual(88.1, report["summary"]["avg_judge_elapsed_ms"])
            self.assertIn("used_current_mail_context", report["cases"][0])
            self.assertIn("raw_answer", report["cases"][0])
            self.assertIn("answer_format", report["cases"][0])
            self.assertIn("guard_name", report["cases"][0])
            self.assertIn("tool_action", report["cases"][0])
            self.assertIn("server_elapsed_ms", report["cases"][0])
            self.assertIn("evidence_top_k", report["cases"][0])
            self.assertIn("metadata_snapshot", report["cases"][0])
            self.assertIn("search_result_count", report["cases"][0])
            self.assertIn("evidence_count", report["cases"][0])
            self.assertTrue(latest_path.exists())

            saved = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(3, saved["summary"]["total_cases"])
            self.assertEqual(3, len(calls))
            self.assertIn("thread_id", calls[0]["payload"])

    def test_load_latest_chat_eval_report_returns_none_when_file_missing(self) -> None:
        """latest 파일이 없으면 None을 반환해야 한다."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            latest_path = Path(tmp_dir) / "missing.json"
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                self.assertIsNone(chat_eval_service.load_latest_chat_eval_report())
            finally:
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

    def test_run_chat_eval_session_filters_cases_by_case_ids(self) -> None:
        """case_ids가 전달되면 해당 케이스들만 실행해야 한다."""
        captured_case_ids: list[str] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            captured_case_ids.append(str(payload.get("message") or ""))
            return (
                200,
                {"answer": "ok", "metadata": {"source": "deep-agent"}},
                50.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                5.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    case_ids=["mail-02", "mail-04"],
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

        self.assertEqual(2, report["summary"]["total_cases"])
        report_case_ids = [item["case_id"] for item in report["cases"]]
        self.assertEqual(["mail-02", "mail-04"], report_case_ids)

    def test_run_chat_eval_session_uses_cases_file_markdown(self) -> None:
        """cases_file 지정 시 외부 markdown 케이스셋으로 실행해야 한다."""
        markdown = """
## Q1. 현재메일 요약
**기대 결과:**
- 현재메일 기준 요약

## Q2. 전체 메일 조회
**기대 결과:**
- 조회 결과 제시
""".strip()

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            return (
                200,
                {"answer": str(payload.get("message") or ""), "metadata": {"source": "deep-agent"}},
                30.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                1.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "cases.md"
            path.write_text(markdown, encoding="utf-8")
            reports_dir = Path(tmp_dir) / "reports"
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    cases_file=str(path),
                    max_cases=2,
                    selected_email_id="selected-id",
                    mailbox_user="user@example.com",
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

        self.assertEqual(2, report["summary"]["total_cases"])
        self.assertEqual("cases-q1", report["cases"][0]["case_id"])

    def test_run_chat_eval_session_uses_rule_override_for_mail_search_no_result(self) -> None:
        """검색 결과 0건 + 부재 안내 응답이면 Judge 호출 없이 규칙 기반 PASS를 반환해야 한다."""

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = chat_url
            _ = timeout_sec
            return (
                200,
                {
                    "answer": "조회 결과: 조건에 맞는 메일이 없습니다.",
                    "metadata": {
                        "source": "deep-agent",
                        "search_result_count": 0,
                        "evidence_mails": [],
                    },
                },
                80.0,
                None,
            )

        def should_not_be_called(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            raise AssertionError("judge_caller should not be called for no-result override")

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=should_not_be_called,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

        self.assertEqual(1, report["summary"]["total_cases"])
        case = report["cases"][0]
        self.assertEqual(True, case["judge"]["pass"])
        self.assertEqual(0.0, case["judge_elapsed_ms"])

    def test_run_chat_eval_session_aligns_evidence_count_with_search_result_count(self) -> None:
        """metadata.search_result_count가 evidence 개수보다 크면 judge_context.evidence_count를 search_result_count에 맞춰야 한다."""
        captured_contexts: list[dict[str, Any]] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, payload, timeout_sec)
            return (
                200,
                {
                    "answer": "m1-subject 정리 결과입니다.",
                    "metadata": {
                        "source": "deep-agent",
                        "search_result_count": 5,
                        "evidence_mails": [
                            {"message_id": "m1", "subject": "m1-subject", "snippet": "m1-snippet", "received_date": "2026-02-01"},
                            {"message_id": "m2", "subject": "m2-subject", "snippet": "m2-snippet", "received_date": "2026-02-02"},
                            {"message_id": "m3", "subject": "m3-subject", "snippet": "m3-snippet", "received_date": "2026-02-03"},
                        ],
                    },
                },
                100.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source)
            captured_contexts.append(dict(judge_context))
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {
                        "intent_match": True,
                        "format_match": True,
                        "grounded": True,
                    },
                },
                10.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            try:
                _ = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path

        self.assertEqual(1, len(captured_contexts))
        self.assertEqual(5, captured_contexts[0]["search_result_count"])
        self.assertEqual(5, captured_contexts[0]["evidence_count"])
        self.assertEqual(3, len(captured_contexts[0]["evidence_top_k"]))
        self.assertEqual("m1-subject", captured_contexts[0]["evidence_top_k"][0]["subject"])

    def test_run_chat_eval_session_fails_when_action_items_list_is_missing(self) -> None:
        """액션 아이템 요청에서 구조화된 항목이 없으면 규칙 기반 FAIL이어야 한다."""

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, payload, timeout_sec)
            return (
                200,
                {
                    "answer": "메일 내용에서 확인된 액션 아이템은 다음과 같습니다.",
                    "metadata": {"source": "deep-agent", "search_result_count": 1, "evidence_mails": [{"id": "x"}]},
                },
                70.0,
                None,
            )

        def should_not_be_called(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            raise AssertionError("judge_caller should not be called when format guard fails")

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "guard-action-items",
                    "query": "메일 조회 후 액션 아이템만 정리해줘",
                    "expectation": "액션 아이템 목록을 제공해야 한다.",
                    "requires_current_mail": False,
                }
            ]
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=should_not_be_called,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertEqual(1, report["summary"]["total_cases"])
        self.assertEqual(0, report["summary"]["passed_cases"])
        case = report["cases"][0]
        self.assertFalse(case["judge"]["pass"])
        self.assertIn("액션 아이템 요청", str(case["judge"]["reason"]))

    def test_run_chat_eval_session_allows_action_items_list_when_present(self) -> None:
        """액션 아이템 요청에서 구조화된 항목이 있으면 Judge 경로로 진행해야 한다."""
        judge_called = {"value": False}

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, payload, timeout_sec)
            return (
                200,
                {
                    "answer": "1. 보안정책 적용 대상 확인\n2. 예외 사용자 목록 업데이트",
                    "metadata": {
                        "source": "deep-agent",
                        "search_result_count": 1,
                        "evidence_mails": [
                            {
                                "subject": "보안정책 적용 대상 확인",
                                "snippet": "예외 사용자 목록 업데이트 필요",
                                "received_date": "2026-02-25",
                            }
                        ],
                    },
                },
                65.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            judge_called["value"] = True
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                10.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "guard-action-items-ok",
                    "query": "메일 조회 후 액션 아이템만 정리해줘",
                    "expectation": "액션 아이템 목록을 제공해야 한다.",
                    "requires_current_mail": False,
                }
            ]
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertTrue(judge_called["value"])
        self.assertEqual(1, report["summary"]["passed_cases"])

    def test_run_chat_eval_session_hard_fails_retrieval_when_answer_mismatches_evidence(self) -> None:
        """retrieval 질의에서 답변이 근거와 불일치하면 judge 호출 없이 hard-fail이어야 한다."""

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, payload, timeout_sec)
            return (
                200,
                {
                    "answer": "회의실 예약 승인 프로세스만 안내드립니다.",
                    "metadata": {
                        "source": "deep-agent",
                        "search_result_count": 2,
                        "evidence_mails": [
                            {
                                "subject": "IT Application 위탁운영 1월분 계산서 발행 요청",
                                "snippet": "1월분 계산서 발행을 위해 담당자 확인이 필요합니다.",
                                "received_date": "2026-02-25T00:45:06Z",
                            },
                            {
                                "subject": "계산서 발행 요청 추가 확인",
                                "snippet": "도메인별 사용자 수 확인 요청",
                                "received_date": "2026-02-26T03:00:00Z",
                            },
                        ],
                    },
                },
                55.0,
                None,
            )

        def should_not_be_called(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            raise AssertionError("judge_caller should not be called when retrieval hard-fail triggers")

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "guard-retrieval",
                    "query": "M365 프로젝트 일정관련 최근 2주 메일 찾아줘",
                    "expectation": "관련 메일을 조회해 요약해야 한다.",
                    "requires_current_mail": False,
                }
            ]
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=should_not_be_called,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        case = report["cases"][0]
        self.assertFalse(case["judge"]["pass"])
        self.assertEqual(1, int(case["judge"]["score"]))
        self.assertIn("hard-fail", str(case["judge"]["reason"]))
        self.assertEqual(0.0, float(case["judge_elapsed_ms"]))

    def test_run_chat_eval_session_passes_visible_answer_to_judge(self) -> None:
        """Judge 입력 answer는 answer_format.blocks 기준 화면 표시 텍스트를 사용해야 한다."""
        captured_answers: list[str] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, payload, timeout_sec)
            return (
                200,
                {
                    "answer": "## 제목\n- 원본 **강조** 문장",
                    "metadata": {
                        "source": "deep-agent",
                        "answer_format": {
                            "version": "v1",
                            "format_type": "summary",
                            "blocks": [
                                {"type": "heading", "level": 2, "text": "제목"},
                                {"type": "paragraph", "text": "원본 **강조** 문장"},
                            ],
                        },
                    },
                },
                40.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, expectation, source, judge_context)
            captured_answers.append(answer)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                10.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "visible-answer",
                    "query": "테스트 조회",
                    "expectation": "표시 기준 텍스트 사용",
                    "requires_current_mail": False,
                }
            ]
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertEqual(1, len(captured_answers))
        self.assertEqual("제목\n원본 강조 문장", captured_answers[0])
        self.assertEqual("제목\n원본 강조 문장", report["cases"][0]["answer"])

    def test_run_chat_eval_session_summary_includes_quality_metrics(self) -> None:
        """리포트 summary는 자동 품질 지표 3종을 포함해야 한다."""

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            query = str(payload.get("message") or "")
            if "3줄 요약" in query:
                answer = "요약 결과:\n1. A\n2. B\n3. C"
            elif "보고서" in query:
                answer = "# 보고서\n- 항목"
            else:
                answer = "예약 실패: 과거 날짜는 예약할 수 없습니다."
            return (
                200,
                {"answer": answer, "metadata": {"source": "deep-agent"}},
                44.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                11.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "quality-summary",
                    "query": "현재 메일 3줄 요약해줘",
                    "expectation": "3줄 요약",
                    "requires_current_mail": False,
                },
                {
                    "case_id": "quality-report",
                    "query": "현재 메일 보고서 작성해줘",
                    "expectation": "보고서 형식",
                    "requires_current_mail": False,
                },
                {
                    "case_id": "quality-booking",
                    "query": "회의실 예약해줘",
                    "expectation": "예약 결과",
                    "requires_current_mail": False,
                },
            ]
            try:
                report = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        summary = report["summary"]
        self.assertEqual(100.0, summary["summary_line_compliance_rate"])
        self.assertEqual(1, summary["summary_line_checked_cases"])
        self.assertEqual(100.0, summary["report_format_compliance_rate"])
        self.assertEqual(1, summary["report_format_checked_cases"])
        self.assertEqual(100.0, summary["booking_failure_reason_compliance_rate"])
        self.assertEqual(1, summary["booking_failure_reason_checked_cases"])

    def test_run_chat_eval_session_attaches_current_mail_context_for_deictic_query(self) -> None:
        """requires_current_mail=False여도 지시대명사 질의면 현재메일 컨텍스트를 주입해야 한다."""
        captured_payloads: list[dict[str, Any]] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            captured_payloads.append(dict(payload))
            return (
                200,
                {"answer": "ok", "metadata": {"source": "deep-agent"}},
                22.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                3.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "deictic-current",
                    "query": "이 메일에서 누락 항목 정리해줘",
                    "expectation": "누락 항목 정리",
                    "requires_current_mail": False,
                }
            ]
            try:
                _ = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    selected_email_id="selected-id",
                    mailbox_user="user@example.com",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertEqual(1, len(captured_payloads))
        payload = captured_payloads[0]
        self.assertEqual("selected-id", payload.get("email_id"))
        self.assertEqual("user@example.com", payload.get("mailbox_user"))
        self.assertEqual({"scope": "current_mail"}, payload.get("runtime_options"))

    def test_run_chat_eval_session_does_not_attach_current_mail_for_global_query(self) -> None:
        """전체 메일 지시 질의는 선택 메일이 있어도 current_mail 컨텍스트를 강제 주입하지 않아야 한다."""
        captured_payloads: list[dict[str, Any]] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            captured_payloads.append(dict(payload))
            return (
                200,
                {"answer": "ok", "metadata": {"source": "deep-agent"}},
                21.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                3.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "global-query",
                    "query": "전체 메일함에서 관련 메일 찾아줘",
                    "expectation": "검색 결과",
                    "requires_current_mail": False,
                }
            ]
            try:
                _ = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    selected_email_id="selected-id",
                    mailbox_user="user@example.com",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertEqual(1, len(captured_payloads))
        payload = captured_payloads[0]
        self.assertNotIn("email_id", payload)
        self.assertNotIn("mailbox_user", payload)
        self.assertNotIn("runtime_options", payload)

    def test_run_chat_eval_session_attaches_current_mail_for_non_search_query_when_selected_mail_exists(self) -> None:
        """명시적 전체검색이 아닌 비검색 질의는 선택 메일이 있으면 current_mail 컨텍스트를 붙여야 한다."""
        captured_payloads: list[dict[str, Any]] = []

        def fake_chat_caller(
            chat_url: str,
            payload: dict[str, Any],
            timeout_sec: int,
        ) -> tuple[int, dict[str, Any], float, str | None]:
            _ = (chat_url, timeout_sec)
            captured_payloads.append(dict(payload))
            return (
                200,
                {"answer": "ok", "metadata": {"source": "deep-agent"}},
                12.0,
                None,
            )

        def fake_judge(
            query: str,
            answer: str,
            expectation: str,
            source: str,
            judge_context: dict[str, Any],
        ) -> tuple[dict[str, Any], float]:
            _ = (query, answer, expectation, source, judge_context)
            return (
                {
                    "pass": True,
                    "score": 5,
                    "reason": "ok",
                    "checks": {"intent_match": True, "format_match": True, "grounded": True},
                },
                2.0,
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            reports_dir = Path(tmp_dir)
            latest_path = reports_dir / "chat_eval_latest.json"
            original_reports_dir = chat_eval_service.REPORTS_DIR
            original_latest_path = chat_eval_service.LATEST_REPORT_PATH
            original_cases = list(chat_eval_service.CHAT_EVAL_CASES)
            chat_eval_service.REPORTS_DIR = reports_dir
            chat_eval_service.LATEST_REPORT_PATH = latest_path
            chat_eval_service.CHAT_EVAL_CASES = [
                {
                    "case_id": "non-search",
                    "query": "AD join tool이란 무엇이며 왜 라이선스가 필요한가요?",
                    "expectation": "현재 메일 기준 설명",
                    "requires_current_mail": False,
                }
            ]
            try:
                _ = chat_eval_service.run_chat_eval_session(
                    chat_url="http://127.0.0.1:8000/search/chat",
                    selected_email_id="selected-id",
                    mailbox_user="user@example.com",
                    max_cases=1,
                    chat_caller=fake_chat_caller,
                    judge_caller=fake_judge,
                )
            finally:
                chat_eval_service.REPORTS_DIR = original_reports_dir
                chat_eval_service.LATEST_REPORT_PATH = original_latest_path
                chat_eval_service.CHAT_EVAL_CASES = original_cases

        self.assertEqual(1, len(captured_payloads))
        payload = captured_payloads[0]
        self.assertEqual("selected-id", payload.get("email_id"))
        self.assertEqual({"scope": "current_mail"}, payload.get("runtime_options"))


if __name__ == "__main__":
    unittest.main()
