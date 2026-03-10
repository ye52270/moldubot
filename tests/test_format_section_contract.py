from app.services.format_section_contract import build_format_section_contract


def test_mail_search_summary_contract_has_major_and_evidence_sections() -> None:
    contract = build_format_section_contract(
        user_message="M365 관련 메일 조회해서 요약해줘",
        tool_payload={
            "action": "mail_search",
            "aggregated_summary": [
                "M365 및 AD 환경 구축 비용 확인 필요",
                "조건부 액세스 정책 변경 완료",
            ],
            "results": [
                {
                    "subject": "FW: M365 + AD 환경 구축 문의",
                    "received_date": "2026-02-19",
                    "sender_names": "박제영",
                    "web_link": "https://example.com/1",
                }
            ],
        },
    )
    assert contract["template_id"] == "mail_search_summary"
    section_ids = [section["id"] for section in contract["sections"]]
    assert "major" in section_ids
    assert "evidence" in section_ids
    assert "tech_issue" not in section_ids


def test_mail_search_tech_issue_contract_has_tech_issue_section() -> None:
    contract = build_format_section_contract(
        user_message="M365 관련 메일에서 기술적 이슈 정리해줘",
        tool_payload={
            "action": "mail_search",
            "query_summaries": [
                {
                    "query": "기술적 이슈",
                    "lines": [
                        "결재 상태정보변경 API 호출이 되지 않아 확인 요청.",
                    ],
                }
            ],
            "results": [
                {
                    "subject": "API 호출 오류",
                    "received_date": "2026-02-25",
                    "sender_names": "박제영",
                    "web_link": "https://example.com/2",
                }
            ],
        },
    )
    assert contract["template_id"] == "mail_search_tech_issue"
    section_ids = [section["id"] for section in contract["sections"]]
    assert "tech_issue" in section_ids
    assert "evidence" in section_ids


def test_todo_register_contract_marks_hil_required() -> None:
    contract = build_format_section_contract(
        user_message="현재메일에서 할일 todo 등록해줘",
        tool_payload={"action": "create_outlook_todo"},
    )
    assert contract["template_id"] == "current_mail_todo_register"
    action_sections = [section for section in contract["sections"] if section["id"] == "action"]
    assert len(action_sections) == 1
    assert action_sections[0]["requires_hil"] is True


def test_current_mail_analysis_phrase_uses_general_contract() -> None:
    contract = build_format_section_contract(
        user_message="현재메일에서 DB 연결 실패오류에 대해 정리해줘",
        tool_payload={"action": "current_mail"},
    )
    assert contract["template_id"] == "general"
    assert contract["sections"] == []
