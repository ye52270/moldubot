from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    `/search/chat` 요청 바디 스키마.

    Attributes:
        message: 사용자 입력 문장
        thread_id: 대화 스레드 식별자
        mode: UI 동작 모드
        email_id: 현재 메일 식별자
        mailbox_user: 선택 메일 조회 대상 사용자 메일 주소
        intent_name: 상위 라우팅 의도명
        runtime_options: 런타임 옵션 딕셔너리
    """

    message: str = ""
    thread_id: str | None = None
    mode: str | None = None
    email_id: str | None = None
    mailbox_user: str | None = None
    intent_name: str | None = None
    runtime_options: dict[str, Any] | None = None


class MailContextRequest(BaseModel):
    """
    `/mail/context` 요청 바디 스키마.

    Attributes:
        message_id: Outlook/Graph 메시지 식별자
        mailbox_user: Graph 조회 대상 사용자 UPN/메일 주소
    """

    message_id: str = Field(default="")
    mailbox_user: str = Field(default="")


class ConfirmRequest(BaseModel):
    """
    `/search/chat/confirm` 요청 바디 스키마.

    Attributes:
        thread_id: 승인 대상 스레드 식별자
        approved: 승인 여부
        decision_type: 승인 결정 유형(`approve|edit|reject`)
        confirm_token: 승인 토큰
        edited_action: edit 시 적용할 tool/action payload
        prompt_variant: 승인 대상 에이전트 프롬프트 variant
    """

    thread_id: str = Field(default="")
    approved: bool = False
    decision_type: str | None = None
    confirm_token: str | None = None
    edited_action: dict[str, Any] | None = None
    prompt_variant: str | None = None


class RoomBookingRequest(BaseModel):
    """
    `/api/meeting-rooms/book` 요청 바디 스키마.

    Attributes:
        building: 건물명
        floor: 층수
        room_name: 회의실명
        date: 예약 날짜(YYYY-MM-DD)
        start_time: 시작 시각(HH:MM)
        end_time: 종료 시각(HH:MM)
        attendee_count: 참석 인원
        subject: 회의 제목(옵션)
        body: 본문(옵션)
    """

    building: str
    floor: int
    room_name: str
    date: str
    start_time: str
    end_time: str
    attendee_count: int = 1
    subject: str | None = ""
    body: str | None = ""


class MeetingSuggestionRequest(BaseModel):
    """
    `/api/meeting-rooms/suggest-from-current-mail` 요청 바디 스키마.

    Attributes:
        message_id: Outlook/Graph 메시지 식별자
        mailbox_user: Graph 조회 대상 사용자 UPN/메일 주소
    """

    message_id: str = Field(default="")
    mailbox_user: str = Field(default="")


class CalendarEventCreateRequest(BaseModel):
    """
    `/api/calendar-events/create` 요청 바디 스키마.

    Attributes:
        subject: 일정 제목
        date: 일정 날짜(YYYY-MM-DD)
        start_time: 시작 시각(HH:MM)
        end_time: 종료 시각(HH:MM)
        body: 일정 내용
        attendees: 참석자 목록(이메일 또는 이름)
    """

    subject: str
    date: str
    start_time: str
    end_time: str
    body: str | None = ""
    attendees: list[str] = []


class CalendarSuggestionRequest(BaseModel):
    """
    `/api/calendar-events/suggest-from-current-mail` 요청 바디 스키마.

    Attributes:
        message_id: Outlook/Graph 메시지 식별자
        mailbox_user: Graph 조회 대상 사용자 UPN/메일 주소
    """

    message_id: str = Field(default="")
    mailbox_user: str = Field(default="")


class WeeklyReportExportRequest(BaseModel):
    """
    `/addin/export/weekly-report` 요청 바디 스키마.

    Attributes:
        format: 내보내기 포맷
        markdown: 보고서 원문 마크다운
        file_name: 다운로드 파일명
    """

    format: str = "docx"
    markdown: str = ""
    file_name: str = "weekly-report"


class ChatEvalRunRequest(BaseModel):
    """
    `/qa/chat-eval/run` 요청 바디 스키마.

    Attributes:
        chat_url: 채팅 API 엔드포인트 URL
        judge_model: LLM Judge 모델명
        max_cases: 실행할 최대 케이스 수
        case_ids: 실행할 케이스 ID 목록(지정 시 해당 케이스만 실행)
        selected_email_id: 현재메일 질의용 선택 메일 ID
        mailbox_user: 현재메일 질의용 mailbox user
        request_timeout_sec: 단일 케이스 호출 타임아웃(초)
        cases_file: 외부 케이스 파일 경로(.md/.json)
    """

    chat_url: str | None = None
    judge_model: str = "gpt-5-mini"
    max_cases: int | None = None
    case_ids: list[str] | None = None
    selected_email_id: str | None = None
    mailbox_user: str | None = None
    request_timeout_sec: int = 90
    cases_file: str | None = None


class ChatEvalPipelineRunRequest(BaseModel):
    """
    `/qa/chat-eval/pipeline/run` 요청 바디 스키마.

    Attributes:
        chat_url: 채팅 API 엔드포인트 URL
        judge_model: LLM Judge 모델명
        max_cases: 실행할 최대 케이스 수
        case_ids: 실행할 케이스 ID 목록
        selected_email_id: 현재메일 질의용 선택 메일 ID
        mailbox_user: 현재메일 질의용 mailbox user
        request_timeout_sec: 단일 케이스 호출 타임아웃(초)
        min_pass_rate: 최소 통과율 품질게이트(%)
        min_avg_score: 최소 평균점수 품질게이트
        allow_regression_cases: baseline 대비 허용 회귀 케이스 수
        cases_file: 외부 케이스 파일 경로(.md/.json)
    """

    chat_url: str | None = None
    judge_model: str = "gpt-5-mini"
    max_cases: int | None = None
    case_ids: list[str] | None = None
    selected_email_id: str | None = None
    mailbox_user: str | None = None
    request_timeout_sec: int = 90
    min_pass_rate: float = 85.0
    min_avg_score: float = 3.5
    allow_regression_cases: int = 0
    cases_file: str | None = None


class ReportGenerateRequest(BaseModel):
    """
    `/report/generate` 요청 바디 스키마.

    Attributes:
        email_content: 보고서 생성에 사용할 원문 이메일/대화 내용
        email_subject: 보고서 제목 기본값으로 사용할 메일 제목
        email_received_date: 보고서 표지/타임라인 기준 수신일(YYYY-MM-DD 또는 ISO 문자열)
        email_sender: 보고서 표지에 표시할 발신자 이름/주소
    """

    email_content: str = ""
    email_subject: str = "메일 보고서"
    email_received_date: str = ""
    email_sender: str = ""


class WeeklyReportGenerateRequest(BaseModel):
    """
    `/report/weekly/generate` 요청 바디 스키마.

    Attributes:
        week_offset: 기준 주 오프셋(1=지난주, 2=지지난주)
        report_author: 표지 작성자 표기
    """

    week_offset: int = 1
    report_author: str = ""


class PromiseDraftRequest(BaseModel):
    """
    `/api/promise/drafts` 요청 바디 스키마.

    Attributes:
        project_number: 프로젝트 번호
        project_name: 프로젝트명
        mode: create/edit
        final_cost_total: 집행예산 총액
        reason: 기안 사유
        thread_id: 채팅 스레드 식별자
    """

    project_number: str = ""
    project_name: str = ""
    mode: str = "create"
    final_cost_total: int = 0
    reason: str = ""
    thread_id: str | None = None


class FinanceClaimRequest(BaseModel):
    """
    `/api/finance/claims` 요청 바디 스키마.

    Attributes:
        project_number: 프로젝트 번호
        expense_category: 비용 항목
        amount: 요청 금액
        description: 비고
        evidence_files: 첨부 파일명 목록
        thread_id: 채팅 스레드 식별자
    """

    project_number: str = ""
    expense_category: str = ""
    amount: int = 0
    description: str = ""
    evidence_files: list[str] = []
    thread_id: str | None = None


class HrRequest(BaseModel):
    """
    `/api/myhr/requests` 요청 바디 스키마.

    Attributes:
        request_type: 신청 유형(근태/휴가 등)
        request_date: 신청 날짜(YYYY-MM-DD)
        reason: 신청 사유
        thread_id: 채팅 스레드 식별자
    """

    request_type: str = ""
    request_date: str = ""
    reason: str = ""
    thread_id: str | None = None
