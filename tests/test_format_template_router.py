from app.services.format_template_router import render_template_driven_mail_search


def test_render_template_driven_mail_search_skips_non_mail_action() -> None:
    route, rendered = render_template_driven_mail_search(
        user_message="현재메일 요약해줘",
        answer="",
        tool_payload={"action": "current_mail"},
        section_contract={"template_id": "current_mail_summary", "sections": [{"id": "summary"}]},
    )
    assert route == "skip"
    assert rendered == ""


def test_render_template_driven_mail_search_returns_deterministic_for_mail_template() -> None:
    route, rendered = render_template_driven_mail_search(
        user_message="M365 관련 메일 조회해서 요약해줘",
        answer="",
        tool_payload={
            "action": "mail_search",
            "query_summaries": [
                {"query": "M365", "lines": ["M365 일정 압박 리스크가 확인되었습니다."]},
            ],
            "results": [
                {
                    "message_id": "m-1",
                    "subject": "FW: M365 일정 협의",
                    "summary_text": "M365 일정 압박 리스크가 확인되었습니다.",
                    "web_link": "https://outlook.live.com/owa/?ItemID=m-1",
                    "sender_names": "박제영",
                    "received_date": "2026-02-25",
                }
            ],
        },
        section_contract={
            "template_id": "mail_search_summary",
            "sections": [{"id": "major"}, {"id": "evidence"}],
        },
    )
    assert route == "deterministic"
    assert "## 📌 주요 내용" in rendered


def test_render_template_driven_mail_search_skips_when_template_not_mail_search() -> None:
    route, rendered = render_template_driven_mail_search(
        user_message="메일 조회해서 요약해줘",
        answer="",
        tool_payload={"action": "mail_search", "results": []},
        section_contract={"template_id": "current_mail_summary", "sections": [{"id": "summary"}]},
    )
    assert route == "skip"
    assert rendered == ""


def test_render_template_driven_mail_search_skips_when_answer_is_contract_json() -> None:
    route, rendered = render_template_driven_mail_search(
        user_message="현재 메일의 주요 내용이 뭐야?",
        answer='{"format_type":"standard_summary","summary_lines":[]}',
        tool_payload={"action": "mail_search", "results": []},
        section_contract={"template_id": "mail_search_tech_issue", "sections": [{"id": "major"}]},
    )
    assert route == "skip"
    assert rendered == ""


def test_render_template_driven_mail_search_skips_no_result_when_tool_failed() -> None:
    route, rendered = render_template_driven_mail_search(
        user_message="관련 메일 조회해줘",
        answer="",
        tool_payload={
            "action": "mail_search",
            "status": "failed",
            "reason": "현재메일 범위에서는 사서함 검색 도구를 실행하지 않습니다.",
            "results": [],
            "count": 0,
        },
        section_contract={"template_id": "mail_search_summary", "sections": [{"id": "major"}]},
    )
    assert route == "skip"
    assert rendered == ""
