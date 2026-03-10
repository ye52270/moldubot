from __future__ import annotations

import unittest

from app.services.answer_postprocessor_summary import (
    extract_original_user_message,
    extract_summary_lines,
    is_current_mail_summary_request,
    render_summary_lines_for_request,
    sanitize_summary_lines,
)


class AnswerPostprocessorSummaryTest(unittest.TestCase):
    """
    요약 라인 정규화/추출 노이즈 제거 규칙을 검증한다.
    """

    def test_sanitize_summary_lines_removes_signature_noise(self) -> None:
        """
        sanitize 단계에서 연락처/서명 라인은 제거되어야 한다.
        """
        lines = [
            "KISTI 측 수신 로그가 비어 있어 차단 여부 확인이 필요합니다.",
            "010-9002-1397",
            "박정호 드림",
        ]
        sanitized = sanitize_summary_lines(lines=lines)
        self.assertEqual(1, len(sanitized))
        self.assertIn("KISTI 측 수신 로그가 비어 있어 차단 여부 확인이 필요합니다.", sanitized)

    def test_extract_summary_lines_removes_signature_noise(self) -> None:
        """
        자유 텍스트 추출에서도 서명/연락처 라인은 제외되어야 한다.
        """
        answer = (
            "1. KISTI 측 로그에 수신 내역이 없어 차단 가능성이 큽니다.\n"
            "2. 이전 유사 장애 조치 결과 회신이 지연되고 있습니다.\n"
            "3. 010-9002-1397\n"
            "4. 박정호 드림\n"
        )
        extracted = extract_summary_lines(answer=answer)
        self.assertEqual(2, len(extracted))
        self.assertTrue(all("010-9002-1397" not in line for line in extracted))
        self.assertTrue(all("드림" not in line for line in extracted))

    def test_sanitize_summary_lines_removes_low_value_lines(self) -> None:
        """
        상투/자기소개성 문장은 요약 후보에서 제거되어야 한다.
        """
        lines = [
            "KISTI 측 로그에 수신 내역이 없어 차단 여부 확인이 필요합니다.",
            "국가과학기술연구회 문수연입니다.",
            "확인 부탁드립니다.",
        ]
        sanitized = sanitize_summary_lines(lines=lines)
        self.assertEqual(1, len(sanitized))
        self.assertIn("KISTI 측 로그에 수신 내역이 없어 차단 여부 확인이 필요합니다.", sanitized)

    def test_render_summary_lines_for_mail_search_uses_bullet_format(self) -> None:
        """
        메일 조회/검색 요약 요청은 주요 내용 + 하위 불릿 형식으로 렌더링되어야 한다.
        """
        rendered = render_summary_lines_for_request(
            user_message="조영득 관련 2월 메일 조회 요약해줘",
            lines=[
                "비용 산정 요청 — ERP 예산 초과 가능성, 차주 금요일까지 제출 필요 - 추가 산정 영역: M365, 그룹웨어 포탈/전자결재",
                "새해 인사 — 경영 변화에도 업무 최선을 다하자는 메시지",
                "물리 본사 검토 — TNS 프로젝트 사례 공유 요청 필요",
            ],
        )
        self.assertTrue(rendered.startswith("## 📌 주요 내용\n- "))
        self.assertIn("- 비용 산정 요청 — ERP 예산 초과 가능성, 차주 금요일까지 제출 필요", rendered)
        self.assertIn("- 추가 산정 영역: M365, 그룹웨어 포탈/전자결재", rendered)
        self.assertIn("- 새해 인사 — 경영 변화에도 업무 최선을 다하자는 메시지", rendered)
        self.assertIn("- 물리 본사 검토 — TNS 프로젝트 사례 공유 요청 필요", rendered)

    def test_is_current_mail_summary_request_accepts_spaced_phrase(self) -> None:
        """
        `현재 메일 요약`처럼 띄어쓰기 변형도 현재메일 요약 요청으로 인식해야 한다.
        """
        self.assertTrue(is_current_mail_summary_request("현재메일 요약"))
        self.assertTrue(is_current_mail_summary_request("현재 메일 요약"))
        self.assertTrue(is_current_mail_summary_request("/메일요약"))

    def test_extract_original_user_message_strips_scope_prefix(self) -> None:
        """scope prefix가 포함된 주입 문자열에서도 원본 사용자 입력을 복원해야 한다."""
        injected = "[질의 범위] 전체 메일함 기준으로 처리\n/메일요약"
        self.assertEqual("/메일요약", extract_original_user_message(injected))


if __name__ == "__main__":
    unittest.main()
