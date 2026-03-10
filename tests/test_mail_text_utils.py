from __future__ import annotations

import unittest

from app.services.mail_text_utils import (
    build_mail_route_compact_text,
    extract_mail_route_steps,
    extract_person_name_or_email,
    extract_recipients_from_body,
    extract_sender_display_name,
    select_salient_summary_sentences,
)


class MailTextUtilsTest(unittest.TestCase):
    """
    메일 본문 핵심 문장 선별 로직을 검증한다.
    """

    def test_select_salient_summary_sentences_filters_header_noise(self) -> None:
        """
        헤더/상투 문장은 선별 결과에서 제외되어야 한다.
        """
        body = (
            "From: user@example.com\n"
            "Subject: FW: 테스트\n"
            "확인 부탁드립니다.\n"
            "KISTI 측 로그에 수신 이력이 없어 차단 여부 확인이 필요합니다.\n"
            "발송 서버 IP와 수신 서버 IP 정보가 공유되었습니다.\n"
        )
        selected = select_salient_summary_sentences(text=body, line_target=2)
        self.assertEqual(2, len(selected))
        joined = "\n".join(selected)
        self.assertNotIn("From:", joined)
        self.assertNotIn("확인 부탁드립니다", joined)
        self.assertIn("수신 이력", joined)

    def test_select_salient_summary_sentences_prioritizes_actionable_content(self) -> None:
        """
        핵심 키워드가 포함된 문장을 우선 선택해야 한다.
        """
        body = (
            "단순 인사 문장입니다.\n"
            "사서함이 가득 차 메일 수신/발송이 불가하여 정책 적용 검토가 필요합니다.\n"
            "조치 결과 회신과 정상 수신 이력 제공이 요청되었습니다.\n"
        )
        selected = select_salient_summary_sentences(text=body, line_target=2)
        self.assertEqual(2, len(selected))
        self.assertTrue(any("수신/발송이 불가" in line for line in selected))
        self.assertTrue(any("조치 결과 회신" in line for line in selected))

    def test_extract_sender_display_name_strips_tag_and_email(self) -> None:
        """
        발신자 원문에서 태그/이메일을 제거한 이름을 추출해야 한다.
        """
        source = "박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK <izocuna@sk.com>"
        self.assertEqual("박제영", extract_sender_display_name(from_address=source))

    def test_extract_recipients_from_body_normalizes_name_and_email(self) -> None:
        """
        To 헤더의 수신자 문자열은 `이름 <email>` 형태로 정규화되어야 한다.
        """
        body = (
            "From: a@example.com\n"
            "To: 이상수(LEE Sangsoo)/AX Solution서비스4팀/SK <ssl@skcc.com>, "
            "김태호 <kimth@cnthoth.com>\n"
            "Cc: test@example.com\n"
        )
        recipients = extract_recipients_from_body(text=body)
        self.assertEqual(
            ["이상수 <ssl@skcc.com>", "김태호 <kimth@cnthoth.com>"],
            recipients,
        )

    def test_extract_recipients_from_body_decodes_html_entities(self) -> None:
        """
        HTML 엔티티(`&lt;`, `&gt;`)가 포함된 수신자 헤더도 정상 정규화되어야 한다.
        """
        body = (
            "To: 이상수/AX팀 &lt;ssl@skcc.com&gt;, 김태호 &lt;kimth@cnthoth.com&gt;\n"
            "Subject: 테스트\n"
        )
        recipients = extract_recipients_from_body(text=body)
        self.assertEqual(
            ["이상수 <ssl@skcc.com>", "김태호 <kimth@cnthoth.com>"],
            recipients,
        )

    def test_extract_mail_route_steps_parses_thread_flow(self) -> None:
        """
        본문 헤더 체인에서 단계별 발신자/수신자 흐름을 추출해야 한다.
        """
        body = (
            "From: 박제영 <izocuna@sk.com>\n"
            "To: 김태성 <tate.kim@skcc.com>\n"
            "Sent: 2026-03-04\n"
            "\n"
            "From: 황규리 <orange@skcc.com>\n"
            "To: 서관석 <kwansuk.suh@skcc.com>; unknown@partner.com\n"
            "Sent: 2026-03-03\n"
        )
        steps = extract_mail_route_steps(text=body, max_steps=4)
        self.assertEqual(2, len(steps))
        self.assertEqual("2026-03-03", steps[0]["date"])
        self.assertEqual("황규리", steps[0]["from"])
        self.assertIn("unknown@partner.com", steps[0]["to"])
        self.assertEqual("2026-03-04", steps[1]["date"])
        self.assertEqual("박제영", steps[1]["from"])
        compact = build_mail_route_compact_text(text=body, max_steps=4)
        self.assertIn("2026-03-03::황규리=>", compact)
        self.assertIn("%%", compact)

    def test_extract_person_name_or_email_uses_email_when_name_missing(self) -> None:
        """
        이름이 없으면 이메일 주소를 그대로 반환해야 한다.
        """
        self.assertEqual("reply-only@sk.com", extract_person_name_or_email("reply-only@sk.com"))

    def test_extract_mail_route_steps_parses_english_sent_date(self) -> None:
        """
        영문 Sent 헤더 날짜도 YYYY-MM-DD로 정규화해야 한다.
        """
        body = (
            "From: 박정호/AT Infra팀/SKB (eva1397@sk.com)\n"
            "To: 박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK (izocuna@SKCC.COM)\n"
            "Sent: Thu, 5 Mar 2026 11:12:34 +0900\n"
        )
        steps = extract_mail_route_steps(text=body, max_steps=4)
        self.assertEqual(1, len(steps))
        self.assertEqual("2026-03-05", steps[0]["date"])
        compact = build_mail_route_compact_text(text=body, max_steps=4)
        self.assertIn("2026-03-05::박정호=>박제영", compact)

    def test_extract_mail_route_steps_skips_incomplete_from_to_step(self) -> None:
        """
        수신자 또는 발신자가 누락된 단계는 흐름에서 제외해야 한다.
        """
        body = (
            "From: 박철환 <bp000128@hintsmtp.skbroadband.com>\n"
            "Sent: 2026-02-26\n"
            "\n"
            "From: 정유정 <bp000131@hintsmtp.skbroadband.com>\n"
            "To: 강민창 <sc01105936@hintsmtp.skbroadband.com>\n"
            "Sent: 2026-02-26\n"
        )
        steps = extract_mail_route_steps(text=body, max_steps=4)
        self.assertEqual(1, len(steps))
        self.assertEqual("정유정", steps[0]["from"])
        self.assertEqual("강민창", steps[0]["to"])


if __name__ == "__main__":
    unittest.main()
