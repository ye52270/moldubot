from app.services.format_policy_selector import FormatTemplateId, select_format_template


def test_select_current_mail_summary_template() -> None:
    selection = select_format_template(user_message="현재메일 요약해줘")
    assert selection.template_id == FormatTemplateId.CURRENT_MAIL_SUMMARY
    assert "evidence" not in selection.facets


def test_select_mail_search_summary_template() -> None:
    selection = select_format_template(user_message="M365 관련 메일 조회해서 요약해줘")
    assert selection.template_id == FormatTemplateId.MAIL_SEARCH_SUMMARY
    assert "evidence" in selection.facets


def test_select_mail_search_tech_issue_template() -> None:
    selection = select_format_template(
        user_message="M365 관련 메일에서 기술적 이슈를 정리해줘",
        tool_payload={"action": "mail_search"},
    )
    assert selection.template_id == FormatTemplateId.MAIL_SEARCH_TECH_ISSUE
    assert "tech_issue" in selection.facets


def test_select_current_mail_todo_register_template() -> None:
    selection = select_format_template(user_message="현재메일에서 할일 추출해서 todo 등록해줘")
    assert selection.template_id == FormatTemplateId.CURRENT_MAIL_TODO_REGISTER
    assert "todo" in selection.facets
    assert "evidence" not in selection.facets


def test_select_current_mail_meeting_room_template() -> None:
    selection = select_format_template(user_message="현재메일 주요내용으로 회의실 예약해줘")
    assert selection.template_id == FormatTemplateId.CURRENT_MAIL_MEETING_BOOK
    assert "schedule" in selection.facets
    assert "evidence" not in selection.facets


def test_select_calendar_register_by_action_payload() -> None:
    selection = select_format_template(
        user_message="일정 등록",
        tool_payload={"action": "create_outlook_calendar_event"},
    )
    assert selection.template_id == FormatTemplateId.CALENDAR_REGISTER


def test_current_mail_analysis_phrase_prefers_general_template() -> None:
    selection = select_format_template(user_message="현재메일에서 DB 연결 실패오류에 대해 정리해줘")
    assert selection.template_id == FormatTemplateId.GENERAL
    assert "analysis" in selection.facets
