from __future__ import annotations

import json
import unittest

from app.services.answer_postprocessor import postprocess_final_answer


class AnswerPostprocessorDynamicTableTest(unittest.TestCase):
    """후처리에서 동적 인물 역할 표 라우팅을 검증한다."""

    def test_people_roles_table_is_rendered_before_json_fallback(self) -> None:
        """모델 응답이 malformed여도 mail_context 기반 역할표를 우선 렌더링해야 한다."""
        result = postprocess_final_answer(
            user_message="현재메일에서 수신자별 역할을 표 형식으로 정리해줘",
            answer='{"format_type":',
            tool_payload={
                "mail_context": {
                    "to_recipients": "김태호 <kimth@cnthoth.com>",
                    "body_excerpt": "To: 김태호 <kimth@cnthoth.com>",
                }
            },
        )
        self.assertIn("## 수신자 역할 정리", result)
        self.assertIn("| 수신자 | 역할 추정 | 근거 |", result)
        self.assertIn("| 김태호 | 수신/실행 대상 | 메일 헤더 TO |", result)

    def test_current_mail_people_roles_uses_llm_contract_when_available(self) -> None:
        """현재메일 역할표 요청은 contract.recipient_roles를 우선 렌더링해야 한다."""
        answer_payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
            "recipient_roles": [
                {
                    "recipient": "김태호 <kimth@cnthoth.com>",
                    "role": "API 장애 수정 책임자로 배포 조치 실행",
                    "evidence": "본문에서 김태호님이 오늘 수정 조치를 진행한다고 명시됨",
                }
            ],
        }
        result = postprocess_final_answer(
            user_message="현재메일 수신자를 분석해서 각각 역할을 표로 정리해줘",
            answer=json.dumps(answer_payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "to_recipients": "김태호 <kimth@cnthoth.com>",
                    "body_excerpt": "To: 김태호 <kimth@cnthoth.com>",
                }
            },
        )
        self.assertIn("## 수신자 역할 정리", result)
        self.assertIn("| 김태호 | API 장애 수정 책임자로 배포 조치 실행 |", result)
        self.assertNotIn("| alpha@example.com | 수신/실행 대상 |", result)

    def test_current_mail_people_roles_contract_applies_strict_quality_guard(self) -> None:
        """contract.recipient_roles는 To 수신자/근거 품질 가드로 정제되어야 한다."""
        answer_payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
            "recipient_roles": [
                {
                    "recipient": "박정호/AT Infra팀/SKB",
                    "role": "메시지 발신 및 질문 제기",
                    "evidence": "안녕하세요, Mydesk Cloud CP내 Edge 브라우저에 MSN NEWS가 업데이트 되고 있는데요.",
                },
                {
                    "recipient": "이상수/AX Solution서비스4팀/SK",
                    "role": "Redirect 대상 도메인 후보 검토 담당",
                    "evidence": "@박정호 회의 중 언급된 redirect 후보 도메인 목록 확인 요청",
                },
                {
                    "recipient": "김태호",
                    "role": "Redirect 예시 기준 추가 도메인 검토 담당",
                    "evidence": "@김태호 아래 Redirect 예시에서 추가 되어야 할 도메인 검토 부탁드립니다.",
                },
                {
                    "recipient": "박제영/AX Solution서비스5팀/SK",
                    "role": "정보 공유 대상",
                    "evidence": "참조: 박제영",
                },
            ],
        }
        result = postprocess_final_answer(
            user_message="현재메일 수신자를 분석해서 각자 역할을 표로 정리해줘",
            answer=json.dumps(answer_payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "from_address": "eva1397@sk.com",
                    "to_recipients": "이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>; 김태호 <kimth@cnthoth.com>",
                    "cc_recipients": "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@SKCC.COM>",
                    "body_excerpt": (
                        "To: 이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>; 김태호 <kimth@cnthoth.com>\n"
                        "Cc: 박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@SKCC.COM>\n"
                        "@김태호 아래 Redirect 예시에서 추가 되어야 할 도메인 검토 부탁드립니다."
                    ),
                }
            },
        )
        self.assertIn("| 이상수 | Redirect 대상 도메인 후보 검토 담당 |", result)
        self.assertIn("| 김태호 | Redirect 예시 기준 추가 도메인 검토 담당 |", result)
        self.assertNotIn("| 박정호 |", result)
        self.assertNotIn("| 박제영 |", result)
        self.assertNotIn("안녕하세요", result)
        self.assertNotIn("참조:", result)

    def test_mail_search_recipient_role_request_renders_role_summary_table(self) -> None:
        """메일검색 기반 수신자 역할 요청은 주요내용 요약이 아닌 역할 요약 표를 렌더링해야 한다."""
        result = postprocess_final_answer(
            user_message="M365 구축과 관련된 메일을 정리해서 메일의 수신자별 역할을 요약해줘",
            answer="임시 응답",
            tool_payload={
                "action": "mail_search",
                "results": [
                    {
                        "subject": "FW: M365 + AD 환경 구축 문의",
                        "to_recipients": "김태호 <kimth@cnthoth.com>; ssl@skcc.com",
                    }
                ],
            },
        )
        self.assertIn("## 수신자 역할 요약", result)
        self.assertIn("| 메일 제목 | 수신자 | 역할 추정 | 근거 |", result)
        self.assertIn("| FW: M365 + AD 환경 구축 문의 | 김태호 | 수신/실행 대상 | 메일 헤더 TO |", result)
        self.assertIn("| FW: M365 + AD 환경 구축 문의 | ssl@skcc.com | 수신/실행 대상 | 메일 헤더 TO |", result)
        self.assertNotIn("## 📌 주요 내용", result)

    def test_mail_search_recipient_role_request_marks_missing_recipient_field(self) -> None:
        """검색 결과에 수신자 필드가 없으면 미확인으로 표시해야 한다."""
        result = postprocess_final_answer(
            user_message="M365 관련 메일에서 수신자 역할 정리해줘",
            answer="임시 응답",
            tool_payload={
                "action": "mail_search",
                "results": [
                    {
                        "subject": "FW: M365 + AD 환경 구축 문의",
                        "summary_text": "수신자 필드가 없는 케이스",
                    }
                ],
            },
        )
        self.assertIn("| FW: M365 + AD 환경 구축 문의 | 미확인 | - | 검색 결과 payload에 수신자 필드 없음 |", result)

    def test_current_mail_recipient_todos_renders_contract_table(self) -> None:
        """현재메일 수신자 ToDo+마감기한 요청은 contract.recipient_todos 표를 렌더링해야 한다."""
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
            "recipient_roles": [],
            "recipient_todos": [
                {
                    "recipient": "김태호",
                    "todo": "Redirect 예시 기준 추가 도메인 검토",
                    "due_date": "2026-03-07",
                    "due_date_basis": "본문에서 금주 내 검토 요청",
                }
            ],
        }
        result = postprocess_final_answer(
            user_message="현재 메일에서 수신자를 요약해서 그들이 해야할 todo 와 마감기한을 정해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "to_recipients": "김태호 <kimth@cnthoth.com>",
                    "body_excerpt": "@김태호 아래 Redirect 예시 도메인 검토 부탁드립니다.",
                }
            },
        )
        self.assertIn("## 수신자별 ToDo", result)
        self.assertIn("| 수신자 | 할 일 | 마감기한 | 기한 근거 |", result)
        self.assertIn("| 김태호 | Redirect 예시 기준 추가 도메인 검토 | 2026-03-07 |", result)

    def test_current_mail_recipient_todos_guard_filters_out_non_to_recipients(self) -> None:
        """recipient_todos는 To 수신자 범위만 남기고 발신자/참조자를 제거해야 한다."""
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
            "recipient_roles": [],
            "recipient_todos": [
                {
                    "recipient": "박정호",
                    "todo": "질문 전달",
                    "due_date": "2026-03-07",
                    "due_date_basis": "안녕하세요",
                },
                {
                    "recipient": "김태호",
                    "todo": "Redirect 도메인 검토",
                    "due_date": "2026-03-07",
                    "due_date_basis": "@김태호 검토 부탁드립니다.",
                },
            ],
        }
        result = postprocess_final_answer(
            user_message="현재메일 수신자들의 todo와 마감기한 표로 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "from_address": "eva1397@sk.com",
                    "to_recipients": "김태호 <kimth@cnthoth.com>",
                    "cc_recipients": "박제영 <izocuna@skcc.com>",
                }
            },
        )
        self.assertIn("| 김태호 | Redirect 도메인 검토 | 미정 |", result)
        self.assertNotIn("| 박정호 |", result)

    def test_current_mail_recipient_todos_guard_due_date_unknown_when_basis_weak(self) -> None:
        """근거가 약한 due_date는 미정으로 강제되어야 한다."""
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
            "recipient_roles": [],
            "recipient_todos": [
                {
                    "recipient": "김태호",
                    "todo": "Redirect 도메인 검토 및 회신",
                    "due_date": "2026-03-27",
                    "due_date_basis": "검토 부탁드립니다.",
                },
            ],
        }
        result = postprocess_final_answer(
            user_message="현재메일 수신자들의 todo와 마감기한 표로 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={"mail_context": {"to_recipients": "김태호 <kimth@cnthoth.com>"}},
        )
        self.assertIn("| 김태호 | Redirect 도메인 검토 및 회신 | 미정 | 검토 부탁드립니다. |", result)


if __name__ == "__main__":
    unittest.main()
