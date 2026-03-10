from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services.answer_postprocessor import postprocess_final_answer


class AnswerPostprocessorRoutingTest(unittest.TestCase):
    """
    최종 응답 후처리 라우팅(summary/report/복합)을 검증한다.
    """

    def test_summary_request_renders_numbered_lines(self) -> None:
        """
        요약 요청은 번호형 `요약 결과` 포맷으로 정규화되어야 한다.
        """
        result = postprocess_final_answer(
            user_message="메일 2줄 요약해줘",
            answer="요약했습니다.\n1. 첫 문장\n2. 둘째 문장\n3. 셋째 문장",
        )
        self.assertEqual("요약 결과:\n1. 첫 문장\n2. 둘째 문장", result)

    def test_current_mail_n_line_summary_renders_emphasis_style(self) -> None:
        """
        현재메일 N줄 요약은 번호+강조+설명 스타일로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "SK 메일 발송서버에서 KISTI 수신 실패 — 보안장비 로그 미수신",
                "이전 유사 사례 존재 — 조치 회신 미완료",
                "SKB 담당자 긴급 전달 — 빠른 확인 요청",
            ],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일 3줄로 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. **SK 메일 발송서버에서 KISTI 수신 실패** — 보안장비 로그 미수신", result)
        self.assertIn("2. **이전 유사 사례 존재** — 조치 회신 미완료", result)
        self.assertNotIn("요약 결과:", result)

    def test_report_request_skips_summary_format(self) -> None:
        """
        보고서 요청은 요약 번호 포맷을 강제하지 않아야 한다.
        """
        report_text = "보고서 제목\n- 항목 A\n- 항목 B"
        result = postprocess_final_answer(
            user_message="현재 메일 보고서 작성해줘",
            answer=report_text,
        )
        self.assertEqual(report_text, result)

    def test_mixed_request_prioritizes_report_route(self) -> None:
        """
        복합 요청(요약+보고서)은 report 우선 라우팅으로 요약 후처리를 건너뛰어야 한다.
        """
        result = postprocess_final_answer(
            user_message="메일 요약해서 보고서로 정리해줘",
            answer="보고서 본문\n1. 이 번호는 본문 항목이다",
        )
        self.assertEqual("보고서 본문\n1. 이 번호는 본문 항목이다", result)

    def test_injected_user_message_marker_is_resolved(self) -> None:
        """
        미들웨어 주입 문자열에서도 원본 사용자 요청 기준으로 라우팅되어야 한다.
        """
        injected = (
            "의도 구조분해 결과:\n{}\n\n"
            "원본 사용자 입력: 메일 1줄 요약해줘"
        )
        result = postprocess_final_answer(
            user_message=injected,
            answer="요약 결과:\n- 핵심 문장",
        )
        self.assertEqual("요약 결과:\n1. 핵심 문장", result)

    def test_json_detailed_summary_renders_standard_template(self) -> None:
        """
        JSON 계약의 detailed_summary는 표준 섹션 템플릿으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "detailed_summary",
            "title": "상세 요약",
            "answer": "",
            "summary_lines": [f"항목 {index}" for index in range(1, 10)],
            "key_points": ["핵심 A", "핵심 B"],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일 자세히 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 이메일 요약", result)
        self.assertIn("### 🔎 핵심 문제 요약", result)
        self.assertIn("### 📌 주요 내용", result)

    def test_json_summary_cleans_markdown_and_duplicates(self) -> None:
        """
        JSON 계약 summary는 중복/마크다운이 정리된 번호 요약으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "요약",
            "answer": "",
            "summary_lines": ["**첫 문장**", "**첫 문장**", "둘째 문장"],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="메일 2줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertEqual("요약 결과:\n1. 첫 문장\n2. 둘째 문장", result)

    def test_general_query_with_summary_format_renders_summary_lines_only(self) -> None:
        """
        일반 질의에서 format_type=summary 계약은 summary_lines 우선으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "RE: 협업툴 ldap 연동 실패 관련 문의",
            "answer": "",
            "summary_lines": [
                "LDAP 쿼리 정상 호출됨 — 사용자 확인.",
                "특정일 이후 쿼리 작동 중단 — 원인 확인 필요.",
            ],
            "major_points": [
                "LDAP 쿼리 정상 호출됨 — 사용자 확인.",
                "서영빈에게 화면 캡쳐 요청 — 정보 제공 필요.",
            ],
            "required_actions": [
                "LDAP 쿼리 작동 중단 원인 확인 / 담당: 박정호 / 기한: 미상",
            ],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재 메일의 주요 내용이 뭐야?",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("- LDAP 쿼리 정상 호출됨 — 사용자 확인.", result)
        self.assertIn("- 특정일 이후 쿼리 작동 중단 — 원인 확인 필요.", result)
        self.assertNotIn("LDAP 쿼리 작동 중단 원인 확인 / 담당: 박정호 / 기한: 미상", result)

    def test_mixed_json_objects_prefers_contract_payload(self) -> None:
        """
        의도 JSON + 응답 JSON이 연속된 경우에도 응답 계약 JSON을 우선 파싱해야 한다.
        """
        intent_json = {
            "original_query": "조건부 액세스 정책 안내 메일 찾아서 3줄 요약해줘",
            "steps": ["search_mails", "extract_key_facts"],
            "summary_line_target": 5,
            "date_filter": {"mode": "none"},
            "missing_slots": [],
        }
        response_json = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["첫 줄", "둘째 줄", "셋째 줄"],
            "key_points": [],
            "action_items": [],
        }
        mixed_answer = (
            json.dumps(intent_json, ensure_ascii=False)
            + "\n"
            + json.dumps(response_json, ensure_ascii=False)
        )
        result = postprocess_final_answer(
            user_message="조건부 액세스 정책 안내 메일 찾아서 3줄 요약해줘",
            answer=mixed_answer,
        )
        self.assertIn("요약 결과:", result)
        self.assertIn("첫 줄", result)
        self.assertNotIn("original_query", result)

    def test_standard_summary_renders_section_template(self) -> None:
        """
        표준 요약 포맷은 섹션형 템플릿으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "[FW] KISTI 보안장비 내 SK 메일 발송서버 차단 확인 요청",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "홍길동",
                "수신자": "jaeyoung_dev@outlook.com",
                "날짜": "2026-03-01",
                "원본 문의 발신": "문수연 → 임영석",
            },
            "core_issue": "메일 발송 차단 이슈 확인 필요",
            "major_points": ["수신 측 로그 미확인", "유사 사례 재발"],
            "required_actions": ["차단 여부 확인", "조치 결과 회신"],
            "one_line_summary": "차단 의심으로 즉시 확인이 필요합니다.",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 이메일 요약", result)
        self.assertIn("### 🧾 제목", result)
        self.assertIn("[FW] KISTI 보안장비 내 SK 메일 발송서버 차단 확인 요청", result)
        self.assertIn("### 📋 기본 정보", result)
        self.assertIn("| **최종 발신자** | 홍길동 |", result)
        self.assertIn("### 🔎 핵심 문제 요약", result)
        self.assertIn("### 📌 주요 내용", result)
        self.assertIn("### ✅ 조치 필요 사항", result)
        self.assertIn("1. 차단 여부 확인", result)
        self.assertIn("2. 조치 결과 회신", result)
        self.assertNotIn("> **요약:**", result)

    def test_current_mail_json_contract_is_preferred_over_grounded_safe(self) -> None:
        """
        현재메일 위험 질의라도 JSON 계약 파싱에 성공하면 grounded-safe 축약보다 계약 렌더를 우선해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "Grafana Daily Report 미수신 확인 요청",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "izocuna@sk.com",
                "수신자": "박제영",
                "날짜": "2026-03-05",
                "원본 문의 발신": "공재환",
            },
            "core_issue": "Gmail 도메인 정책으로 보고 메일이 차단됨",
            "major_points": [
                "Gmail 정책에서 발신 도메인 정합성 검증 실패가 확인됨",
                "dsptek.co.kr 수신은 정상으로 도메인별 차이가 존재함",
                "헤더 분석 결과를 기반으로 후속 조치가 필요함",
            ],
            "required_actions": ["도메인 정합성 재점검 / 담당: 메일운영 / 기한: 미정"],
            "one_line_summary": "메일 차단 원인 파악 및 조치 계획 수립 필요",
        }
        tool_payload = {
            "action": "current_mail",
            "mail_context": {
                "summary_text": "Grafana Daily Report 미수신 확인 요청",
                "body_excerpt": "메일 차단 원인 확인 요청",
            },
        }
        result = postprocess_final_answer(
            user_message="현재메일 문제점 알려줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload=tool_payload,
        )
        self.assertIn("### 📌 주요 내용", result)
        self.assertIn("1. Gmail 정책에서 발신 도메인 정합성 검증 실패가 확인됨", result)
        self.assertIn("2. dsptek.co.kr 수신은 정상으로 도메인별 차이가 존재함", result)
        self.assertNotIn("현재 메일 근거에서 확인되는 내용:", result)

    def test_current_mail_grounded_safe_still_applies_when_contract_parse_fails(self) -> None:
        """
        JSON 계약 파싱이 실패한 현재메일 위험 질의에서는 grounded-safe 안전응답이 유지되어야 한다.
        """
        tool_payload = {
            "action": "current_mail",
            "mail_context": {
                "summary_text": "Grafana Daily Report 미수신 확인 요청",
                "body_excerpt": "메일 차단 원인 확인 요청",
            },
        }
        result = postprocess_final_answer(
            user_message="현재메일 문제점 알려줘",
            answer="문제 원인은 관리자 권한 충돌로 보입니다. 2026-03-05 18:00에 수정되었습니다.",
            tool_payload=tool_payload,
        )
        self.assertIn("현재 메일 근거에서 확인되는 내용:", result)
        self.assertIn("질문과 직접 관련된 세부 항목은 현재 근거만으로 확인할 수 없습니다.", result)

    def test_current_mail_direct_value_overrides_summary_contract_render(self) -> None:
        """
        현재메일 direct-value 질의는 모델의 summary JSON보다 값 추출 렌더를 우선해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "협업툴 ldap 연동 실패 관련 문의",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {"최종 발신자": "izocuna@sk.com"},
            "core_issue": "ldap 연동 실패",
            "major_points": ["이슈 요약 1", "이슈 요약 2"],
            "required_actions": ["쿼리 가이드 요청 / 담당:정진식 / 기한:미상"],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 사용한 OU 쿼리를 알려줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "action": "current_mail",
                "mail_context": {
                    "body_code_excerpt": (
                        "ldapsearch -x -b \"OU=SKB,DC=example,DC=com\" \"(cn=SKB.ZN997)\""
                    ),
                    "body_excerpt": "관련 쿼리 가이드 요청",
                },
            },
        )
        self.assertIn("현재메일 본문에서 확인된 값:", result)
        self.assertIn("OU=SKB,DC=example,DC=com", result)
        self.assertNotIn("### 📌 주요 내용", result)

    def test_standard_summary_renders_recipient_roles_section(self) -> None:
        """
        표준 요약 포맷에서 recipient_roles가 있으면 수신자 역할 섹션을 렌더링해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "박정호",
                "수신자": "박제영",
                "날짜": "2026-03-05",
            },
            "core_issue": "핵심 이슈",
            "major_points": ["포인트 1"],
            "required_actions": [],
            "one_line_summary": "요약",
            "recipient_roles": [
                {
                    "recipient": "박제영",
                    "role": "양식 작성 및 신청 담당",
                    "evidence": "보안진단 신청 양식 작성 주체로 언급됨",
                }
            ],
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### 👥 수신자 역할", result)
        self.assertIn("1. 박제영 — 양식 작성 및 신청 담당", result)
        self.assertIn("- 근거: 보안진단 신청 양식 작성 주체로 언급됨", result)
        self.assertLess(result.find("### 👥 수신자 역할"), result.find("### 🔎 핵심 문제 요약"))

    def test_standard_summary_renders_path_as_code_block(self) -> None:
        """
        전달 경로 항목은 코드블록으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심 이슈",
            "major_points": ["전달 경로 — A → B → C"],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. 전달 경로", result)
        self.assertIn("```", result)
        self.assertIn("A → B → C", result)

    def test_standard_summary_does_not_copy_major_points_into_required_actions(self) -> None:
        """
        조치 필요 사항이 비어 있으면 major_points를 그대로 조치로 재사용하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심 이슈",
            "major_points": ["현재 정책은 감사 모드로 설정됨", "중첩 정책 2건이 동시에 적용됨"],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### 📌 주요 내용", result)
        self.assertNotIn("### ✅ 조치 필요 사항", result)

    def test_standard_summary_keeps_required_actions_with_owner_due_tokens(self) -> None:
        """
        `담당:/기한:` 토큰이 포함된 조치 문장도 조치 필요 사항에서 제거되지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "정유정",
                "수신자": "강민창",
                "날짜": "2026-02-26",
            },
            "core_issue": "디자인 검토 필요",
            "major_points": ["포인트 1"],
            "required_actions": [
                "글자 테두리 흰색 처리 방안 검토 및 회신 / 담당: 강민창 / 기한: 미정",
                "최종 승인 후 운영시스템 적용 / 담당: AX Solution서비스5팀 / 기한: 미정",
            ],
            "one_line_summary": "요약",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### ✅ 조치 필요 사항", result)
        self.assertIn("1. 글자 테두리 흰색 처리 방안 검토 및 회신 / 담당: 강민창 / 기한: 미정", result)
        self.assertIn("2. 최종 승인 후 운영시스템 적용 / 담당: AX Solution서비스5팀 / 기한: 미정", result)

    def test_standard_summary_omits_empty_basic_info_rows(self) -> None:
        """
        기본 정보에서 값이 없는 항목(`-`)은 표 행으로 출력하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "-",
                "수신자": "jaeyoung_dev@outlook.com",
                "날짜": "-",
                "원본 문의 발신": "",
            },
            "core_issue": "핵심",
            "major_points": ["포인트 1", "포인트 2"],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("| **수신자** | jaeyoung_dev |", result)
        self.assertNotIn("| **최종 발신자** | - |", result)
        self.assertNotIn("| **날짜** | - |", result)

    def test_standard_summary_basic_info_orders_date_first_and_normalizes_person_names(self) -> None:
        """
        기본 정보 표는 날짜를 최상단에 배치하고 사람 정보는 이름만 표시해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {
                "최종 발신자": "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@sk.com>",
                "수신자": "윤경훈/Cloud PC개발팀/SKB <kh_yoon@sk.com>; 김태호 <kimth@cnthoth.com>",
                "날짜": "2026-02-14",
                "원본 문의 발신": "박정호/AT Infra팀/SKB <eva1397@sk.com>",
            },
            "core_issue": "핵심",
            "major_points": ["포인트 1", "포인트 2"],
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        date_row = "| **날짜** | 2026-02-14 |"
        sender_row = "| **최종 발신자** | 박제영 |"
        recipient_row = "| **수신자** | 윤경훈, 김태호 |"
        original_row = "| **원본 문의 발신** | 박정호 |"
        self.assertIn(date_row, result)
        self.assertIn(sender_row, result)
        self.assertIn(recipient_row, result)
        self.assertIn(original_row, result)
        self.assertTrue(result.index(date_row) < result.index(sender_row))

    def test_standard_summary_shows_basic_info_fallback_when_all_missing(self) -> None:
        """
        기본 정보 전체가 비어 있으면 빈 표 대신 안내 문장을 출력해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["포인트 1", "포인트 2"],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### 📋 기본 정보", result)
        self.assertIn("- 확인 가능한 기본 정보가 없습니다.", result)
        self.assertNotIn("| 항목 | 내용 |", result)

    def test_standard_summary_avoids_duplicate_detail_when_headline_equals_detail(self) -> None:
        """
        주요 내용 headline/detail이 동일하면 detail 불릿 중복을 출력하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["서비스 CI 변경 요청 — 서비스 CI 변경 요청"],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. 서비스 CI 변경 요청", result)
        self.assertNotIn("- 서비스 CI 변경 요청", result)

    def test_standard_summary_avoids_duplicate_detail_when_split_has_no_detail(self) -> None:
        """
        주요 내용이 분리되지 않아 detail이 비면 동일 문장 불릿을 중복 출력하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["서비스에이스CI변경사항적용이필요함."],
            "required_actions": [],
            "one_line_summary": "요약 문장",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. 서비스에이스CI변경사항적용이필요함.", result)
        self.assertNotIn("- 서비스에이스CI변경사항적용이필요함.", result)

    def test_standard_summary_filters_question_style_major_points(self) -> None:
        """
        주요 내용에서 질문형/잡음 문장은 제외되어야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": [
                "정책 적용이 필요함 — 즉시 반영 필요",
                "해당 뉴스를 조직관리자가 차단할 수 있다고 하는데요?",
            ],
            "required_actions": ["조치 요청"],
            "one_line_summary": "정책 적용이 필요함",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. 정책 적용이 필요함", result)
        self.assertNotIn("조직관리자가 차단할 수 있다고 하는데요", result)

    def test_standard_summary_filters_raw_mail_dump_major_points(self) -> None:
        """
        주요 내용에 원문 메일 덤프/표 조각이 섞이면 렌더에서 제외되어야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "FW: [규모산정 요청] RE: SKB(분사) AI DC",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "팀장 요청으로 금주 비용 산정 필요",
            "major_points": [
                "비용 산정 요청 — 차주 금요일까지 제출 필요",
                "팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상이며 ERP 예산 초과로 규모 전달 시 제외 가능성 있음. - 백민준 팀장은 고객 보안 우려로 ERP 예산 이슈를 강조하고 있으며 차주 산정 필요.",
                "감사합니다.시스템항목비고금액(매출액기준)SSO+넷츠 SSO연동시스템 20개기준 계정관리+넷츠 NSMM365",
            ],
            "required_actions": ["비용 산정 요청 — 차주 금요일까지 제출 필요"],
            "one_line_summary": "비용 산정과 추가 검토가 필요한 상황",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("1. 비용 산정 요청", result)
        self.assertNotIn("팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상", result)
        self.assertNotIn("감사합니다.시스템항목비고금액", result)

    def test_standard_summary_does_not_use_body_excerpt_for_major_point_supplements(self) -> None:
        """
        standard_summary major_points 보강은 summary_text만 사용하고 body_excerpt 장문은 사용하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심 이슈",
            "major_points": ["핵심 사항 확인 필요"],
            "required_actions": [],
            "one_line_summary": "요약",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "summary_text": "M365 프로그램 목록 재확인 요청. 설치 방식(setup.exe/setup.bat) 확인 필요.",
                    "body_excerpt": "From: user@x.com Sent: ... 아니면 setup.bat으로 설치하면 되는지요? Setup.exe 오류 팝업 발생",
                }
            },
        )
        self.assertIn("M365 프로그램 목록 재확인 요청", result)
        self.assertNotIn("아니면 setup.bat으로 설치하면 되는지요", result)

    def test_standard_summary_hides_duplicate_one_line_summary(self) -> None:
        """
        one_line_summary가 주요 내용 첫 줄과 중복이면 하단 요약 문장을 생략해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["서비스 CI 변경 요청 — 즉시 적용 필요"],
            "required_actions": ["조치 요청"],
            "one_line_summary": "서비스 CI 변경 요청 — 즉시 적용 필요",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("> **요약:**", result)

    def test_standard_summary_recovers_points_from_answer_when_fields_missing(self) -> None:
        """
        표준 요약 필드가 비어 있어도 answer 본문에서 주요 내용을 복원해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "",
            "answer": "차단 의심 상황 확인 필요. 조치 결과 회신 요청.",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### 📌 주요 내용", result)
        self.assertIn("차단 의심 상황 확인 필요.", result)

    def test_standard_summary_enriches_major_points_from_tool_mail_context(self) -> None:
        """
        표준 요약 major_points가 부족하면 mail_context 기반으로 주요 내용을 보강해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트 제목",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심 이슈",
            "major_points": ["핵심 사항 확인 필요"],
            "required_actions": [],
            "one_line_summary": "요약",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "body_excerpt": (
                        "서비스 CI 변경 요청이 접수되었습니다. "
                        "기존 이미지와 신규 이미지를 비교 검토해야 합니다. "
                        "회신 일정은 금일 18시까지 요청되었습니다."
                    ),
                    "summary_text": "디자인 변경 요청과 검토 일정 확인이 필요합니다.",
                }
            },
        )
        self.assertIn("1. 핵심 사항 확인 필요", result)
        self.assertIn("2. ", result)
        self.assertNotIn("3. ", result)
        self.assertNotIn("5. ", result)

    def test_standard_summary_appends_structured_log_evidence_to_generic_major_points(self) -> None:
        """
        구조화된 로그가 있으면 generic major_points 세부에 근거 문구를 보강해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "협업툴 ldap 연동 실패 관련 문의",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "LDAP 연동 실패",
            "major_points": [
                "에러 로그 분석 결과 SKB.ZN997 그룹을 가져오지 못함 — LDAP 쿼리 가이드 요청 필요.",
                "이전 차수의 유사한 LDAP 명령어로는 조회 성공 — 환경적 요인 점검 필요.",
                "방화벽 등의 물리적 변경 사항이 원인일 가능성 있음 — 추가 확인 필요.",
            ],
            "required_actions": ["ldap 쿼리 가이드 요청 / 담당:정진식 / 기한:미상"],
            "one_line_summary": "LDAP 연동 실패로 그룹 조회 오류 발생",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "summary_text": "SKB.ZN997 그룹 조회 오류",
                    "body_excerpt": (
                        "2026-03-10 02:01:17,046 CrowdUsnChangedCacheRefresher:thread-2 ERROR "
                        "[ldap.mapper.entity.LDAPGroupAttributesMapper] The following record does not have a groupname: "
                        "{objectguid=objectGUID: [B@3593116d, cn=cn: SKB.ZN997}\n"
                        "2026-03-10 02:01:17,048 CrowdUsnChangedCacheRefresher:thread-2 ERROR "
                        "[ldap.mapper.entity.LDAPGroupAttributesMapper] failed to map LDAP group attributes"
                    ),
                }
            },
        )
        self.assertIn("근거:", result)
        self.assertIn("LDAPGroupAttributesMapper", result)
        self.assertIn("groupname 누락", result)

    def test_standard_summary_quality_log_contains_missing_fields(self) -> None:
        """
        표준 요약 렌더 시 필드 누락 진단 로그가 남아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "",
            "answer": "확인 필요",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
        }
        with self.assertLogs("app.services.answer_postprocessor_rendering", level="INFO") as captured:
            _ = postprocess_final_answer(
                user_message="현재메일 요약해줘",
                answer=json.dumps(payload, ensure_ascii=False),
            )
        joined = "\n".join(captured.output)
        self.assertIn("missing_fields=", joined)

    def test_mail_search_no_result_returns_standard_template_message(self) -> None:
        """
        mail_search 결과가 0건이면 줄수 요청이어도 단일 안내 문장을 반환해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "결과 없음 1",
                "결과 없음 2",
                "결과 없음 3",
            ],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="M365 관련 최근메일 6줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={"action": "mail_search", "count": 0, "results": []},
        )
        self.assertIn("조회 결과: 조건에 맞는 메일이 없습니다.", result)
        self.assertIn("다음 제안:", result)

    def test_mail_search_query_renders_bullet_overview_without_summary_keyword(self) -> None:
        """
        메일 조회 질의는 `요약` 키워드가 없어도 상단을 주요 내용 불릿으로 정규화해야 한다.
        """
        answer = (
            "비용 산정 요청 — 팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상이며 ERP 예산 초과로 "
            "규모 전달 시 제외 가능성 있음. 새해 인사 — 조영득이 새해 인사와 설날 연휴 안전하고 즐겁게 보내길 기원함. "
            "물리 본사 검토 — 물리 본사 여부를 우선 검토해야 하며, 자료 공유를 요청합니다."
        )
        tool_payload = {
            "action": "mail_search",
            "results": [
                {
                    "message_id": "msg-abc==",
                    "subject": "FW: [규모산정 요청] RE: SKB(분사) AI DC",
                    "summary_text": "비용 산정 요청 — 팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상이며 ERP 예산 초과로 규모 전달 시 제외 가능성 있음 - 백민준 팀장은 고객 보안 우려로 ERP 예산 이슈를 강조하고 있으며 차주 산정 필요",
                    "web_link": "https://outlook.live.com/owa/?ItemID=abc",
                },
                {
                    "message_id": "msg-def",
                    "subject": "FW: 새해 복 많이 받으시고 즐거운 설날 연휴 보내세요",
                    "summary_text": "새해 인사 — 조영득이 새해 인사와 설날 연휴 안전하고 즐겁게 보내길 기원함",
                    "web_link": "https://outlook.live.com/owa/?ItemID=def",
                },
            ],
            "aggregated_summary": [
                "비용 산정 요청 — 팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상이며 ERP 예산 초과로 규모 전달 시 제외 가능성 있음 - 백민준 팀장은 고객 보안 우려로 ERP 예산 이슈를 강조하고 있으며 차주 산정 필요",
                "새해 인사 — 조영득이 새해 인사와 설날 연휴 안전하고 즐겁게 보내길 기원함",
                "물리 본사 검토 — 물리 본사 여부를 우선 검토해야 하며, 자료 공유를 요청합니다",
            ],
        }
        result = postprocess_final_answer(
            user_message="조영득 관련 2월 메일 조회",
            answer=answer,
            tool_payload=tool_payload,
        )
        self.assertIn("## 📌 주요 내용", result)
        self.assertIn(
            "1. [FW: \\[규모산정 요청\\] RE: SKB(분사) AI DC](https://outlook.live.com/owa/?ItemID=abc&moldubot_mid=msg-abc%3D%3D)",
            result,
        )
        self.assertIn("- 보낸 사람: -", result)
        self.assertIn("- 수신일: -", result)
        self.assertIn("- 요약: 비용 산정 요청 — 팀장님, 차주 금요일까지 비용 산정 요청 및 150명 대상이며 ERP 예산 초과로 규모 전달 시 제외 가능성 있음", result)
        self.assertIn(
            "2. [FW: 새해 복 많이 받으시고 즐거운 설날 연휴 보내세요](https://outlook.live.com/owa/?ItemID=def&moldubot_mid=msg-def)",
            result,
        )
        self.assertIn("- 요약: 새해 인사 — 조영득이 새해 인사와 설날 연휴 안전하고 즐겁게 보내길 기원함", result)

    def test_mail_search_summary_query_prefers_digest_over_result_listing(self) -> None:
        """
        조회+요약 복합 질의는 결과 목록 대신 summary_text 기반 digest를 주요내용으로 렌더링해야 한다.
        """
        result = postprocess_final_answer(
            user_message="M365 프로젝트 진행, 일정 관련 메일을 찾아서 요약해줘. 기술적 이슈도 검색해서 같이 알려줘",
            answer="모델 응답 원문",
            tool_payload={
                "action": "mail_search",
                "query_summaries": [
                    {
                        "query": "M365 프로젝트 진행",
                        "lines": [
                            "M365 일정 관련 메일에서 일정 지연 가능성이 반복적으로 언급됩니다.",
                            "정책 변경 후속 검증과 담당자 확인이 필요합니다.",
                        ],
                    },
                    {"query": "기술적 이슈", "lines": ["기술 이슈 관련 긴급 회의 요청이 확인됩니다."]},
                ],
                "aggregated_summary": [
                    "M365 일정 관련 메일에서 일정 지연 가능성이 반복적으로 언급됩니다.",
                    "정책 변경 후속 검증과 담당자 확인이 필요합니다.",
                    "기술 이슈 관련 긴급 회의 요청이 확인됩니다.",
                ],
                "results": [
                    {
                        "message_id": "mid-1",
                        "subject": "[긴급] 회의 요청",
                        "summary_text": "다음 주 화요일 시스템 긴급 이슈 관련 회의 요청.",
                        "web_link": "https://outlook.live.com/owa/?ItemID=mid-1",
                        "sender_names": "izocuna@sk.com",
                        "received_date": "2026-02-26T09:10:51Z",
                    },
                ],
            },
        )
        self.assertIn("## 📌 주요 내용", result)
        self.assertIn("1. M365 일정 관련 메일에서 일정 지연 가능성이 반복적으로 언급됩니다.", result)
        self.assertIn("### 🛠 기술 이슈", result)
        self.assertIn("### 📬 근거 메일", result)
        self.assertNotIn("1. [\\[긴급\\] 회의 요청]", result)

    def test_recent_sorted_mail_request_renders_deterministic_result_lines(self) -> None:
        """
        최근순 조회 요청은 received_date를 포함한 고정 목록 포맷으로 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "summary_lines": ["모델 요약"],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="M365 전환 관련 메일을 최근순으로 2개 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "action": "mail_search",
                "results": [
                    {
                        "subject": "첫 번째 메일",
                        "received_date": "2026-03-01",
                        "sender_names": "홍길동",
                        "summary_text": "첫 번째 요약",
                    },
                    {
                        "subject": "두 번째 메일",
                        "received_date": "2026-02-28",
                        "sender_names": "박정호",
                        "summary_text": "두 번째 요약",
                    },
                ],
            },
        )
        self.assertIn("최근순 메일 2건 정리 결과:", result)
        self.assertIn("(조회 결과 기준 총 2건 중 2건)", result)
        self.assertIn("[2026-03-01] 첫 번째 메일 (홍길동)", result)
        self.assertIn("[2026-02-28] 두 번째 메일 (박정호)", result)

    def test_recent_sorted_mail_request_sorts_dates_and_caps_to_available_results(self) -> None:
        """
        최근순 요청은 날짜 내림차순으로 정렬하고, 요청 개수가 많아도 실제 결과 개수까지만 렌더링해야 한다.
        """
        result = postprocess_final_answer(
            user_message="M365 전환 관련 메일을 최근순으로 5개 정리해줘",
            answer="{}",
            tool_payload={
                "action": "mail_search",
                "results": [
                    {"subject": "둘째", "received_date": "2026-02-25", "sender_names": "B"},
                    {"subject": "셋째", "received_date": "2026-02-24", "sender_names": "C"},
                    {"subject": "첫째", "received_date": "2026-02-26", "sender_names": "A"},
                ],
            },
        )
        self.assertIn("최근순 메일 3건 정리 결과:", result)
        self.assertIn("(조회 결과 기준 총 3건 중 3건)", result)
        self.assertTrue(result.index("[2026-02-26] 첫째") < result.index("[2026-02-25] 둘째"))
        self.assertTrue(result.index("[2026-02-25] 둘째") < result.index("[2026-02-24] 셋째"))

    def test_current_mail_recipients_table_request_forces_markdown_table(self) -> None:
        """
        현재메일 수신자 표 요청은 markdown table 형태로 강제 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {"수신자": "eva1397@sk.com, kimth@cnthoth.com"},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 주요 수신자 정보를 표로 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 주요 수신자 정보", result)
        self.assertIn("| 번호 | 수신자 |", result)
        self.assertIn("| 1 | eva1397@sk.com |", result)

    def test_current_mail_recipients_request_uses_tool_payload_fallback(self) -> None:
        """
        현재메일 수신자 질의는 JSON 파싱 실패 시에도 tool payload 본문에서 수신자를 렌더링해야 한다.
        """
        result = postprocess_final_answer(
            user_message="현재메일의 수신자는 누구누구야?",
            answer='{"format_type":',
            tool_payload={
                "mail_context": {
                    "body_excerpt": "From: sender@example.com\nTo: alpha@example.com; beta@example.com\nSubject: 테스트",
                }
            },
        )
        self.assertIn("현재메일 수신자:", result)
        self.assertIn("1. alpha@example.com", result)
        self.assertIn("2. beta@example.com", result)

    def test_current_mail_recipients_table_request_uses_tool_payload_fallback(self) -> None:
        """
        현재메일 수신자 표 요청은 JSON 파싱 실패 시에도 tool payload 기반 표를 렌더링해야 한다.
        """
        result = postprocess_final_answer(
            user_message="현재메일에서 수신자를 표로 보여줘",
            answer='{"format_type":',
            tool_payload={
                "mail_context": {
                    "body_excerpt": "To: alpha@example.com, beta@example.com",
                }
            },
        )
        self.assertIn("| 번호 | 수신자 |", result)
        self.assertIn("| 1 | alpha@example.com |", result)

    def test_generic_table_request_renders_deterministic_markdown_table(self) -> None:
        """
        일반 표 요청은 계약 필드를 markdown 표로 결정론 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "DB 연결 오류 분석",
            "answer": "",
            "summary_lines": ["IM DB 연결 오류 발생"],
            "key_points": [],
            "action_items": ["로그 오류코드 확인"],
            "basic_info": {},
            "core_issue": "조직도 DB 프로비전 지연",
            "major_points": ["CA 체인 B 설치 필요"],
            "required_actions": ["인증서 체인 반영 점검"],
            "one_line_summary": "핵심은 인증서 체인 누락입니다.",
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 주요 이슈를 표 형식으로 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 표 정리", result)
        self.assertIn("| 구분 | 내용 |", result)
        self.assertIn("| 한줄요약 | 핵심은 인증서 체인 누락입니다. |", result)
        self.assertIn("| 핵심이슈 | 조직도 DB 프로비전 지연 |", result)
        self.assertIn("| 조치 | 인증서 체인 반영 점검 |", result)

    def test_generic_table_request_excludes_chart_keywords(self) -> None:
        """
        차트/그래프 요청은 일반 표 강제 렌더 대상에서 제외되어야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": ["A 항목"],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 내용을 그래프로 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 표 정리", result)

    def test_current_mail_issue_action_request_forces_split_sections(self) -> None:
        """
        현재메일 핵심문제/해야할일 분리 요청은 섹션 분리 포맷으로 강제 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "M365 접근 정책 변경으로 일부 사용자 접속 차단 우려",
            "major_points": [],
            "required_actions": ["정책 적용 대상 확인", "예외 사용자 목록 검토"],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 핵심 문제와 해야 할 일을 분리해서 알려줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 핵심 문제", result)
        self.assertIn("## 해야 할 일", result)
        self.assertIn("1. 정책 적용 대상 확인", result)

    def test_current_mail_manager_single_paragraph_request_forces_one_paragraph(self) -> None:
        """
        팀장 보고용 한 단락 요약 요청은 표/섹션 없이 단일 문단으로 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "M365 정책 안내",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "조건부 액세스 정책 변경으로 일부 접속 차단 위험",
            "major_points": ["공인 IP만 허용", "예외 계정 검토 필요"],
            "required_actions": ["적용 범위 확인", "예외자 승인 요청"],
            "one_line_summary": "정책 변경 영향이 있어 선제 점검이 필요합니다",
        }
        result = postprocess_final_answer(
            user_message="현재메일을 보고 팀장 보고용 한 단락 요약 만들어줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("제목은 'M365 정책 안내'입니다", result)
        self.assertNotIn("## ", result)
        self.assertNotIn("| 항목 |", result)

    def test_standard_summary_uses_subject_from_answer_when_title_missing(self) -> None:
        """
        title/basic_info가 비어 있으면 answer의 Subject 라인에서 제목을 추출해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "",
            "answer": "Subject: FW: 테스트 메일 제목\n본문 요약",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["포인트"],
            "required_actions": ["조치"],
            "one_line_summary": "요약",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("### 🧾 제목", result)
        self.assertIn("FW: 테스트 메일 제목", result)

    def test_non_current_mail_standard_summary_does_not_use_standard_template(self) -> None:
        """
        조회성 메일 요약 질의는 standard_summary 포맷이 와도 현재메일 템플릿을 강제하지 않아야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "조회 결과 제목",
            "answer": "",
            "summary_lines": ["첫째", "둘째"],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "",
            "major_points": [],
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="M365 관련 최근메일 3개 조회후 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 이메일 요약", result)
        self.assertIn("## 📌 주요 내용", result)
        self.assertIn("- 첫째", result)

    def test_standard_summary_uses_tool_payload_subject_when_missing(self) -> None:
        """
        title/basic_info/answer가 비어도 tool payload subject로 제목을 보강해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "핵심",
            "major_points": ["포인트"],
            "required_actions": ["조치"],
            "one_line_summary": "요약",
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "subject": "FW: 툴 기반 제목",
                    "from_address": "sender@example.com",
                    "received_date": "2026-03-01",
                }
            },
        )
        self.assertIn("### 🧾 제목", result)
        self.assertIn("FW: 툴 기반 제목", result)

    def test_current_mail_summary_without_n_lines_uses_standard_template(self) -> None:
        """
        현재메일 요약(줄 수 미명시)은 format_type=summary여도 표준 템플릿으로 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "이메일 요약",
            "answer": "",
            "summary_lines": ["핵심 A", "핵심 B"],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 이메일 요약", result)
        self.assertIn("### 📌 주요 내용", result)
        self.assertIn("1. 핵심 A", result)

    def test_current_mail_summary_with_space_uses_standard_template(self) -> None:
        """
        `현재 메일 요약` 입력도 표준 현재메일 요약 템플릿으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "이메일 요약",
            "answer": "",
            "summary_lines": ["핵심 A", "핵심 B"],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재 메일 요약",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("요약 결과:", result)
        self.assertIn("### 📌 주요 내용", result)
        self.assertIn("1. 핵심 A", result)

    def test_explicit_line_request_ignores_standard_summary_format_type(self) -> None:
        """
        현재메일 N줄 요약 요청에서는 format_type=standard_summary여도 N줄 요약 렌더를 우선해야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "무시될 제목",
            "answer": "",
            "summary_lines": ["A", "B", "C", "D", "E"],
            "major_points": ["A", "B", "C", "D", "E"],
            "key_points": [],
            "action_items": [],
            "basic_info": {"최종 발신자": "홍길동"},
            "core_issue": "",
            "required_actions": [],
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 5줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertNotIn("## 이메일 요약", result)
        self.assertIn("1. **A**", result)

    def test_explicit_line_request_fills_to_requested_count(self) -> None:
        """
        현재메일 N줄 요약에서 모델 라인이 부족하면 후처리가 요청 줄 수를 보완해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["첫째", "둘째", "셋째", "넷째"],
            "key_points": [],
            "action_items": [],
            "major_points": [],
            "required_actions": [],
            "basic_info": {},
            "core_issue": "",
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 5줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertGreaterEqual(result.count("\n\n"), 4)
        self.assertIn("5. **", result)

    def test_explicit_line_request_ignores_tool_generated_summary_lines(self) -> None:
        """
        명시 줄수 요약에서 tool payload의 생성 요약 라인은 사용하지 않아야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["확인 부탁드립니다.", "국가과학기술연구회 문수연입니다."],
            "key_points": [],
            "action_items": [],
            "major_points": [],
            "required_actions": [],
            "basic_info": {},
            "core_issue": "",
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 3줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "summary_lines": [
                    "KISTI 로그에 수신 이력이 없어 차단 여부 확인이 필요합니다.",
                    "발송 서버 IP와 수신 서버 정보가 공유되었습니다.",
                    "조치 결과 회신 및 정상 수신 이력 제공 요청이 있습니다.",
                ]
            },
        )
        self.assertNotIn("KISTI 로그에 수신 이력이 없어", result)
        self.assertIn("1. **추가 핵심 정보 확인 필요**", result)

    def test_explicit_line_request_uses_model_only_when_sufficient(self) -> None:
        """
        모델 summary_lines가 요청 줄 수를 충족하면 tool 후보와 혼합하지 않아야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "핵심 이슈 A — 상세",
                "핵심 이슈 B — 상세",
                "핵심 이슈 C — 상세",
            ],
            "key_points": [],
            "action_items": [],
            "major_points": [],
            "required_actions": [],
            "basic_info": {},
            "core_issue": "",
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 3줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "summary_lines": [
                    "유선상 문의 드렸던 내용 메일로 재문의 드립니다.",
                    "확인 부탁드립니다.",
                ],
                "mail_context": {
                    "summary_text": "- 유선상 문의 드렸던 내용 메일로 재문의 드립니다."
                },
            },
        )
        self.assertIn("1. **핵심 이슈 A** — 상세", result)
        self.assertNotIn("유선상 문의", result)

    def test_explicit_line_request_prioritizes_grounded_body_excerpt(self) -> None:
        """
        body_excerpt 기반 핵심문장이 충분하면 모델 summary_lines보다 우선 적용해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["확인 부탁드립니다.", "유선상 문의 드렸던 내용 메일로 재문의 드립니다."],
            "key_points": [],
            "action_items": [],
            "major_points": [],
            "required_actions": [],
            "basic_info": {},
            "core_issue": "",
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 4줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "body_excerpt": (
                        "사서함이 가득 차 메일 수신/발송이 불가합니다.\n"
                        "자동 비우기 정책 적용 가능 여부 검토 요청드립니다.\n"
                        "대상 계정은 gnoc@skbroadband.com 입니다.\n"
                        "정상 수신 이력 제공 여부 확인이 필요합니다."
                    )
                }
            },
        )
        self.assertIn("**자동 비우기 정책 적용 가능** — 여부 검토 요청드립니다.", result)
        self.assertNotIn("유선상 문의 드렸던 내용", result)

    def test_explicit_line_request_prefers_summary_text_over_noisy_lines(self) -> None:
        """
        summary_text가 존재하면 noisy body_excerpt/model 라인보다 우선 반영해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["확인 부탁드립니다.", "유선상 문의 드렸던 내용 메일로 재문의 드립니다."],
            "key_points": [],
            "action_items": [],
            "major_points": [],
            "required_actions": [],
            "basic_info": {},
            "core_issue": "",
            "one_line_summary": "",
        }
        result = postprocess_final_answer(
            user_message="현재메일 3줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={
                "mail_context": {
                    "summary_text": (
                        "- 사서함이 가득 차 수신/발송이 불가하여 자동 비우기 설정 가능 여부 문의\n"
                        "- 대상 계정과 장애처리 메일 연동 방식으로 주기적 비움 필요\n"
                        "- 정책 수준 구현 가능 여부와 보관정책 적용 방식 확인 필요"
                    ),
                    "body_excerpt": "유선상 문의 드렸던 내용 메일로 재문의 드립니다. 감사합니다.",
                }
            },
        )
        self.assertIn("자동 비우기 설정 가능 여부", result)
        self.assertNotIn("유선상 문의 드렸던 내용", result)

    def test_explicit_line_request_does_not_split_single_sentence_for_padding(self) -> None:
        """
        명시 줄수 요약은 한 문장을 절단해 라인을 채우지 않고 보조 필드로 보강해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "사서함 자동 비우기 설정 적용 가능 여부를 문의합니다.",
                "대상 계정과 장애처리 메일의 주기적 비움 정책이 필요합니다.",
            ],
            "major_points": [
                "정책 수준 구현 가능 여부 확인이 필요합니다.",
                "보관정책 또는 개별 생성 적용 방법 확인이 필요합니다.",
            ],
            "required_actions": ["운영 정책 담당 부서 회신 요청"],
            "key_points": [],
            "action_items": [],
            "basic_info": {},
            "core_issue": "사서함 포화로 수신/발송 장애 위험",
            "one_line_summary": "자동 비우기 정책 검토 요청 메일",
        }
        result = postprocess_final_answer(
            user_message="현재메일 6줄 요약해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("3. **정책 수준 구현 가능 여부 확인이 필요합니다.**", result)
        self.assertIn("4. **보관정책 또는 개별 생성 적용** — 방법 확인이 필요합니다.", result)
        self.assertNotIn("**사서함 자동 비우기 설정 적용 가능 여부를** — 문의합니다.", result)

    def test_summary_fallback_filters_header_like_lines(self) -> None:
        """
        요약 fallback 추출 시 From/Sent/To/Subject 헤더 라인은 제거되어야 한다.
        """
        answer = "\n".join(
            [
                "From: user@example.com",
                "Sent: Thursday, February 12, 2026 1:42 PM",
                "To: team@example.com",
                "Subject: 테스트",
                "핵심 내용 첫째",
                "핵심 내용 둘째",
            ]
        )
        result = postprocess_final_answer(
            user_message="메일 2줄 요약해줘",
            answer=answer,
        )
        self.assertEqual("요약 결과:\n1. 핵심 내용 첫째\n2. 핵심 내용 둘째", result)

    def test_json_decode_failure_logs_reason_and_uses_fallback(self) -> None:
        """
        JSON decode 실패 시 사유 로그를 남기고 현재메일 요약 가드 문구를 반환해야 한다.
        """
        with self.assertLogs("app.services.answer_postprocessor", level="WARNING") as captured:
            result = postprocess_final_answer(
                user_message="현재메일 요약해줘",
                answer='{"format_type":"summary","summary_lines":["a",]}',
            )
        joined = "\n".join(captured.output)
        self.assertIn("reason=json_decode_error", joined)
        self.assertIn("현재메일 요약 형식 변환에 실패했습니다", result)

    def test_report_sections_are_forced_for_core_action_conclusion_request(self) -> None:
        """
        핵심/조치사항/결론 보고서 요청은 섹션형 템플릿으로 강제 렌더링되어야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "짧은 문장 하나",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일을 보고 보고서 형식으로 핵심/조치사항/결론을 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 핵심", result)
        self.assertIn("## 조치사항", result)
        self.assertIn("## 결론", result)

    def test_schedule_owner_action_sections_are_forced(self) -> None:
        """
        일정/담당/조치 구분 요청은 섹션 템플릿으로 강제 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": ["2026-03-10 배포 예정", "담당: 박준용", "업데이트 적용 요청"],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="본문에 'SSL 인증서'가 들어가고 '업데이트'가 포함된 메일을 찾아서 일정/담당/조치로 구분해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 일정", result)
        self.assertIn("## 담당", result)
        self.assertIn("## 조치", result)

    def test_report_fallback_blocks_raw_json_contract_text(self) -> None:
        """
        보고서 요청에서 raw JSON 문자열 fallback 노출은 차단되어야 한다.
        """
        raw_json = '{"format_type":"general","title":"","answer":"","summary_lines":[],"key_points":[],"action_items":[]}'
        result = postprocess_final_answer(
            user_message="보안 취약점 조치 요청 메일을 보고서 형식으로 정리해줘",
            answer=raw_json,
        )
        self.assertNotEqual(raw_json, result)
        self.assertIn("요청한 보고서 형식으로 정리할 근거를 찾지 못했습니다", result)

    def test_general_contract_renders_action_items_when_answer_empty(self) -> None:
        """
        general 계약에서 answer가 비어도 action_items가 있으면 항목 텍스트를 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": ["도메인별 사용자 수 확인", "추가 요청 여부 확인"],
        }
        result = postprocess_final_answer(
            user_message="액션 아이템만 뽑아줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("도메인별 사용자 수 확인", result)
        self.assertIn("추가 요청 여부 확인", result)

    def test_general_contract_merges_multi_source_lines_when_answer_empty(self) -> None:
        """
        general 계약에서 answer가 비고 summary/major/key가 함께 있으면 병합 불릿으로 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "",
            "answer": "",
            "summary_lines": ["IM DB 연결 오류로 프로비전 지연"],
            "major_points": ["조직도 DB 프로비전 차질 발생"],
            "key_points": ["원인 로그 점검 필요"],
            "action_items": [],
            "required_actions": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 DB 연결 실패오류에 대해 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("- IM DB 연결 오류로 프로비전 지연", result)
        self.assertIn("- 조직도 DB 프로비전 차질 발생", result)
        self.assertIn("- 원인 로그 점검 필요", result)

    def test_general_fallback_blocks_raw_json_contract_text(self) -> None:
        """
        일반 질의 fallback에서도 raw JSON 템플릿 문자열 노출은 차단되어야 한다.
        """
        raw_json = '{"format_type":"standard_summary","title":"x","answer":"","summary_lines":[],"key_points":[],"action_items":[]}'
        result = postprocess_final_answer(
            user_message="이 내용 정리해줘",
            answer=raw_json,
        )
        self.assertNotEqual(raw_json, result)
        self.assertIn("응답 형식 변환에 실패했습니다", result)

    def test_action_items_request_forces_numbered_list_and_cleans_prefix(self) -> None:
        """
        액션아이템 요청은 중복 접두어를 정리한 번호 목록으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "standard_summary",
            "title": "테스트",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [
                "확인 필요: 각 도메인 사용자 수 확인 요청",
                "확인 필요: 센스메일 외 타 메일 사용자 수 공유",
            ],
        }
        result = postprocess_final_answer(
            user_message="액션 아이템만 뽑아줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 액션 아이템", result)
        self.assertIn("1. 각 도메인 사용자 수 확인 요청", result)
        self.assertIn("2. 센스메일 외 타 메일 사용자 수 공유", result)
        self.assertNotIn("확인 필요:", result)

    def test_action_items_request_uses_summary_lines_when_action_items_empty(self) -> None:
        """
        액션아이템 요청에서 action_items가 비어 있으면 summary_lines를 액션 목록으로 보강해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "테스트",
            "answer": "",
            "summary_lines": [
                "2026년 1월분 검수결과에 따라 계산서 발행",
                "담당자 확인 후 회신 요청",
            ],
            "key_points": [],
            "action_items": [],
            "required_actions": [],
        }
        result = postprocess_final_answer(
            user_message="액션 아이템만 뽑아줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 액션 아이템", result)
        self.assertIn("1. 2026년 1월분 검수결과에 따라 계산서 발행", result)
        self.assertIn("2. 담당자 확인 후 회신 요청", result)

    def test_current_mail_summary_recovers_from_malformed_json_fragment(self) -> None:
        """
        현재메일 요약에서 malformed JSON 조각이 섞여도 tool payload로 표준 요약을 복구해야 한다.
        """
        malformed = (
            '요약 결과:\n'
            '1. {"format_type":"standard_summary","title":"Tenant Restriction",'
            '"major_points":["핵심 요약"]});'
        )
        tool_payload = {
            "mail_context": {
                "subject": "Tenant Restriction",
                "from_address": "izocuna@sk.com",
                "received_date": "2026-02-26",
                "summary_text": "크롬에서 특정 URL 접근 시 Edge Redirect 가이드 요청",
            }
        }
        result = postprocess_final_answer(
            user_message="현재메일 요약",
            answer=malformed,
            tool_payload=tool_payload,
        )
        self.assertIn("### 🧾 제목", result)
        self.assertIn("Tenant Restriction", result)
        self.assertNotIn('{"format_type"', result)

    def test_current_mail_summary_malformed_json_without_context_returns_guard_message(self) -> None:
        """
        현재메일 요약에서 malformed JSON 조각만 있어도 raw JSON 노출 없이 템플릿 렌더로 정리되어야 한다.
        """
        malformed = '요약 결과:\n1. {"format_type":"standard_summary","title":"x"});'
        result = postprocess_final_answer(
            user_message="현재메일 요약",
            answer=malformed,
            tool_payload={},
        )
        self.assertIn("### 🧾 제목", result)
        self.assertNotIn('{"format_type"', result)

    def test_current_mail_cause_analysis_request_forces_cause_impact_action_sections(self) -> None:
        """
        현재메일 원인 분석 요청은 원인/영향/대응 섹션으로 강제 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "원인: 배포 스크립트 누락으로 SSL 인증서 체인 미적용",
                "영향: 외부 접속 지연 및 일정 차질",
                "조치: 인증서 체인 재배포 및 검증 로그 확인",
            ],
            "key_points": [],
            "action_items": [],
            "required_actions": ["인증서 체인 재배포", "모니터링 경보 임계치 점검"],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 왜 기술적 이슈가 생기고, 일정에 문제가 생기는거야",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 원인", result)
        self.assertIn("## 영향", result)
        self.assertIn("## 대응", result)
        self.assertIn("1. 조치: 인증서 체인 재배포 및 검증 로그 확인", result)

    def test_current_mail_solution_request_forces_solution_checklist_sections(self) -> None:
        """
        현재메일 해결 요청은 가능한 원인/점검 순서/즉시 조치 섹션으로 강제 렌더링해야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "",
            "answer": "",
            "summary_lines": [
                "가능 원인: SSL 인증서 만료",
                "점검: 만료일과 CN/SAN 일치 여부 확인",
                "조치: 중간 인증서 포함 재배포",
            ],
            "key_points": [],
            "action_items": ["서비스 재시작 전 인증서 체인 검증"],
            "required_actions": ["신뢰 저장소 갱신"],
        }
        result = postprocess_final_answer(
            user_message="현재 메일에서 SSL 인증서 이슈에 대해서 해결 방법을 알려줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 가능한 원인", result)
        self.assertIn("## 점검 순서", result)
        self.assertIn("## 즉시 조치", result)
        self.assertIn("1. 점검: 만료일과 CN/SAN 일치 여부 확인", result)

    def test_current_mail_send_failure_reason_request_forces_cause_sections(self) -> None:
        """
        현재메일 발신 실패 이유 설명 요청은 요약 카드 대신 원인/영향/대응 섹션으로 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "메일 발신 실패 원인 분석",
            "answer": "",
            "summary_lines": [
                "원인: SMTP 인증 토큰 만료로 발신 서버 인증 실패",
                "영향: 대외 메일 발신 지연 및 일부 반송 발생",
                "조치: 토큰 재발급 후 재시도, 인증 실패 로그 점검",
            ],
            "key_points": [],
            "action_items": [],
            "required_actions": ["토큰 만료 주기 점검", "재발송 큐 모니터링"],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 메일 발신 실패 이유를 설명해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 원인", result)
        self.assertIn("## 영향", result)
        self.assertIn("## 대응", result)
        self.assertNotIn("## 📌 주요 내용", result)

    def test_current_mail_cause_and_response_request_omits_impact_section(self) -> None:
        """
        현재메일 원인+대응방안 요청은 영향 섹션 없이 원인/대응방안만 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "DB 연결 오류 분석",
            "answer": "",
            "summary_lines": [
                "원인: DB 연결 문자열 불일치",
                "대응: 연결 문자열 및 인증정보 재배포",
                "영향: 조직도 프로비전 지연",
            ],
            "key_points": [],
            "action_items": [],
            "required_actions": ["연결 문자열 검증", "배포 후 헬스체크"],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 DB 연결 오류 원인과 대응방안을 설명해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 원인", result)
        self.assertIn("## 대응방안", result)
        self.assertNotIn("## 영향", result)

    def test_current_mail_cause_only_request_omits_impact_and_response_sections(self) -> None:
        """
        현재메일 원인 전용 요청은 영향/대응방안 없이 원인 섹션만 렌더링해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "DB 연결 오류 분석",
            "answer": "",
            "summary_lines": [
                "원인: DB 서버 인증서 체인 누락",
                "영향: 조직도 프로비전 지연",
                "대응: 인증서 체인 재배포",
            ],
            "key_points": [],
            "action_items": [],
            "required_actions": ["인증서 체인 재배포"],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 오류 원인 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 원인", result)
        self.assertNotIn("## 영향", result)
        self.assertNotIn("## 대응방안", result)

    def test_current_mail_cause_only_request_supplements_additional_cause_line(self) -> None:
        """
        원인 전용 질의는 core_issue 1줄로 축약되지 않도록 major_points 기반 원인 후보를 보강해야 한다.
        """
        payload = {
            "format_type": "general",
            "title": "DB 연결 오류 분석",
            "answer": "",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
            "core_issue": "IM DB 연결 오류가 발생하여 조직도 DB 프로비전이 필요하다.",
            "major_points": [
                "IM DB 연결 오류 발생 — 조직도 DB 프로비전 진행 불가",
                "CA 체인 B 서버 설치 필요 — 설치 미비로 인해 데이터베이스 연결 지연",
            ],
            "required_actions": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 오류 원인 정리해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("## 원인", result)
        self.assertIn("IM DB 연결 오류 발생", result)
        self.assertIn("CA 체인 B 서버 설치 필요", result)
        self.assertNotIn("## 영향", result)
        self.assertNotIn("## 대응방안", result)

    def test_current_mail_cause_sections_do_not_repeat_same_lines(self) -> None:
        """
        원인 분석 섹션은 원인/영향에 동일 문장이 중복 배치되면 안 된다.
        """
        payload = {
            "format_type": "general",
            "title": "발신 실패 분석",
            "answer": "",
            "summary_lines": [
                "원인: 발신 도메인 SPF 레코드 불일치",
                "영향: 외부 수신처에서 반송 증가",
                "원인: 발신 도메인 SPF 레코드 불일치",
                "영향: 외부 수신처에서 반송 증가",
                "조치: DNS SPF 레코드 정합성 재검증",
            ],
            "required_actions": ["DNS SPF 레코드 정합성 재검증"],
            "action_items": [],
            "key_points": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 메일 발신 실패 이유를 설명해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertEqual(result.count("원인: 발신 도메인 SPF 레코드 불일치"), 1)
        self.assertEqual(result.count("영향: 외부 수신처에서 반송 증가"), 1)
        self.assertIn("1. 조치: DNS SPF 레코드 정합성 재검증", result)

    def test_current_mail_cause_analysis_impact_fallback_avoids_cause_duplication(self) -> None:
        """
        영향 라인이 명시되지 않아도, 영향 섹션이 원인 문장을 그대로 복제하면 안 된다.
        """
        payload = {
            "format_type": "general",
            "title": "발신 실패 분석",
            "answer": "",
            "summary_lines": [
                "원인: SMTP 인증서 체인 누락",
                "외부 메일 반송 증가와 지연 발생",
                "조치: 인증서 체인 재배포",
            ],
            "required_actions": [],
            "action_items": [],
            "key_points": [],
        }
        result = postprocess_final_answer(
            user_message="현재메일에서 메일 발신 실패 이유를 설명해줘",
            answer=json.dumps(payload, ensure_ascii=False),
        )
        self.assertIn("- 원인: SMTP 인증서 체인 누락", result)
        self.assertIn("- 외부 메일 반송 증가와 지연 발생", result)
        self.assertNotIn("- 원인: SMTP 인증서 체인 누락\n\n## 영향\n\n- 원인: SMTP 인증서 체인 누락", result)

    def test_expert_code_review_answer_skips_forced_template_rendering(self) -> None:
        """
        전문가형 코드리뷰 응답은 LLM 원문을 보존해야 한다.
        """
        answer = (
            "## 코드 리뷰 요약\n"
            "- 인증 경계 검증 누락 가능성\n\n"
            "## 주요 Findings\n"
            "1. 심각도: High\n"
            "   근거: 인증 분기에서 서버측 검증 확인 불가\n"
            "   영향: 권한 우회 가능성\n"
            "   개선안: 서버측 권한 검증 강제\n"
        )
        result = postprocess_final_answer(
            user_message="현재메일 코드 리뷰해줘",
            answer=answer,
            tool_payload={"mail_context": {"body_excerpt": "<form><input name='id'/></form>"}},
        )
        self.assertIn("## 코드 리뷰 요약", result)
        self.assertIn("## 주요 Findings", result)
        self.assertIn("심각도: High", result)
        self.assertNotIn("## 주석 리뷰 (핵심 구간)", result)

    def test_code_review_markdown_answer_is_preserved_without_forced_template(self) -> None:
        """
        코드 리뷰 질의의 비-JSON 마크다운 응답은 LLM 원문을 보존해야 한다.
        """
        answer = (
            "### 🧾 현재 메일 코드 스니펫 분석\n\n"
            "| 항목 | 내용 |\n"
            "|------|------|\n"
            "| 코드 분석 | 로그인 입력 검증 누락 가능성 |\n"
            "| 코드 리뷰 | 심각도: High / 근거: 서버측 검증 부재 |\n"
        )
        result = postprocess_final_answer(
            user_message="현재메일 코드 리뷰해줘",
            answer=answer,
            tool_payload={"mail_context": {"body_excerpt": "<form><input name='id'/></form>"}},
        )
        self.assertIn("### 🧾 현재 메일 코드 스니펫 분석", result)
        self.assertIn("| 항목 | 내용 |", result)
        self.assertIn("심각도: High", result)
        self.assertNotIn("## 주석 리뷰 (핵심 구간)", result)

    def test_code_review_prompt_with_summary_keyword_does_not_collapse_to_summary_list(self) -> None:
        """
        코드리뷰 지시문에 `요약` 토큰이 있어도 fallback이 summary_text 경로로 붕괴되면 안 된다.
        """
        user_message = (
            "현재메일 본문에 코드 스니펫이 있으면 아래 형식으로 답변해줘. "
            "1) '## 코드 분석' 섹션: 기능 요약과 보안 리스크를 간결히 정리. "
            "2) '## 코드 리뷰' 섹션: 언어명 표시 후 핵심 코드 스니펫을 ```언어``` 블록으로 보여줘."
        )
        answer = (
            "## 코드 분석\n"
            "- 기능 요약: 로그인 UI 흐름\n"
            "- 보안 리스크: 입력값 검증 누락 가능성\n\n"
            "## 코드 리뷰\n"
            "```jsp\n<input name=\"id\" />\n```"
        )
        result = postprocess_final_answer(
            user_message=user_message,
            answer=answer,
            tool_payload={"mail_context": {"body_excerpt": "<input name='id'/>"}},
        )
        self.assertIn("## 코드 분석", result)
        self.assertIn("## 코드 리뷰", result)
        self.assertIn("```jsp", result)
        self.assertNotIn("요약 결과:", result)

    def test_code_review_non_json_skips_contract_parse(self) -> None:
        """
        코드리뷰 비-JSON 응답은 JSON 계약 파싱을 시도하지 않아야 한다.
        """
        with patch("app.services.answer_postprocessor.parse_llm_response_contract") as parse_contract:
            result = postprocess_final_answer(
                user_message="현재메일 코드 리뷰해줘",
                answer="## 코드 분석\n- 분석\n\n## 코드 리뷰\n```jsp\n<input/>\n```",
                tool_payload={"mail_context": {"body_excerpt": "<input/>"}},
            )
        parse_contract.assert_not_called()
        self.assertIn("## 코드 분석", result)

    def test_generic_json_object_is_rendered_as_readable_text(self) -> None:
        """
        format_type 없는 일반 JSON 객체는 원문 노출 대신 읽기 쉬운 목록 텍스트로 렌더링되어야 한다.
        """
        answer = json.dumps(
            {
                "대상 시스템": [
                    {
                        "시스템명": "IM",
                        "설명": "인사 변경 사항을 AD/Exchange에 반영",
                    },
                    {
                        "시스템명": "NSM",
                        "설명": "인사동기화 데이터 현행화 및 프로비전 활성화",
                    },
                ]
            },
            ensure_ascii=False,
        )
        result = postprocess_final_answer(
            user_message="현재 메일의 대상시스템을 간단히 정리해줘",
            answer=answer,
            tool_payload={"action": "current_mail"},
        )
        self.assertIn("대상 시스템:", result)
        self.assertIn("- 시스템명: IM", result)
        self.assertIn("- 시스템명: NSM", result)
        self.assertNotIn("{", result)
        self.assertNotIn("}", result)

    def test_general_query_auto_wraps_ldap_filters_as_code_snippets(self) -> None:
        """
        일반 질의에서 LDAP 필터 텍스트는 fenced code block으로 일관 렌더링되어야 한다.
        """
        answer = (
            "메일에서 언급된 LDAP 쿼리는 다음과 같습니다: "
            "(&(objectClass=user)(mailNickname=*)(!(|(sAMAccountName=SKB.Z*)(departmentNumber=RETIREE)))) "
            "및 "
            "(&(objectCategory=Group)(sAMAccountName=SKB.*)(!(|(CN=SKB.W0000)(CN=SKB.X0000))))"
        )
        result = postprocess_final_answer(
            user_message="메일에서 언급한 LDAP 쿼리가 어떤것인지 보여줘",
            answer=answer,
            tool_payload={"action": "current_mail"},
        )
        self.assertIn("```text", result)
        self.assertIn("objectClass=user", result)
        self.assertIn("objectCategory=Group", result)

    def test_general_query_auto_wraps_plain_json_as_code_snippet(self) -> None:
        """
        일반 질의에서 plain JSON 응답은 json code block으로 렌더링되어야 한다.
        """
        answer = '{"name":"ldap","enabled":true,"count":2}'
        result = postprocess_final_answer(
            user_message="이 설정값 보여줘",
            answer=answer,
            tool_payload={},
        )
        self.assertIn("```json", result)
        self.assertIn('"name": "ldap"', result)
        self.assertIn('"enabled": true', result)

    def test_contract_summary_answer_with_ldap_is_wrapped_as_code_snippet(self) -> None:
        """
        계약(summary) 렌더 경로에서도 LDAP 필터가 answer 필드에 있으면 코드블록으로 렌더링되어야 한다.
        """
        payload = {
            "format_type": "summary",
            "title": "RE: 협업툴 ldap 연동 실패 관련 문의",
            "answer": "LDAP 쿼리는 다음과 같습니다: (&(objectClass=user)(mailNickname=*)(!(|(sAMAccountName=SKB.Z*)(departmentNumber=RETIREE))))",
            "summary_lines": [],
            "key_points": [],
            "action_items": [],
        }
        result = postprocess_final_answer(
            user_message="메일에서 언급한 LDAP 쿼리가 어떤것인지 보여줘",
            answer=json.dumps(payload, ensure_ascii=False),
            tool_payload={"action": "current_mail"},
        )
        self.assertIn("```text", result)
        self.assertIn("objectClass=user", result)

    def test_code_review_query_preserves_plain_text_without_auto_snippet(self) -> None:
        """
        코드리뷰 질의는 auto_code_snippet 경로를 타지 않고 기존 코드리뷰 경로를 유지해야 한다.
        """
        answer = "분석 결과: 입력값 검증 누락 가능성이 있습니다."
        result = postprocess_final_answer(
            user_message="현재메일 코드 리뷰해줘",
            answer=answer,
            tool_payload={},
        )
        self.assertEqual("코드 스니펫이 없습니다.", result)
        self.assertNotIn("```", result)


if __name__ == "__main__":
    unittest.main()
