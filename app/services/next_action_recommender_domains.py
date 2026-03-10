from __future__ import annotations

import re
from dataclasses import dataclass

MAX_NEXT_ACTIONS = 3
EMBEDDING_MODEL = "text-embedding-3-small"
MAX_EMBEDDING_INPUT_CHARS = 1600
CODE_ANALYSIS_ACTION_ID = "analyze_code_snippet"

CODE_EVIDENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"```[\w+-]*\s"),
    re.compile(r"\b(function|class|def)\s+[a-zA-Z_][\w]*\s*[\(\:]", re.IGNORECASE),
    re.compile(r"\b(if|for|while)\s*\([^)]{1,120}\)\s*\{", re.IGNORECASE),
    re.compile(r"\b(select|insert|update|delete)\s+.+\b(from|into|set)\b", re.IGNORECASE),
    re.compile(r"<%[@=-]?[\s\S]{0,120}%>"),
    re.compile(r"</?[a-z][a-z0-9:-]*(\s+[^>]{0,160})?>", re.IGNORECASE),
    re.compile(r"\b(cat|vi|nano)\s+[^\s]+\.(jsp|js|ts|py|java|sql|xml|html?)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class ActionDomain:
    """
    실행 가능한 후속 액션 도메인 정의.

    Attributes:
        action_id: 내부 식별자
        title: UI 노출 제목
        description: UI 노출 설명
        query_template: 클릭 시 전송할 추천 질의 템플릿
        keywords: 본문 유사도 계산 키워드
        intent_hints: intent task/output 힌트 토큰
        tool_action_hints: 최근 tool action 힌트 토큰
        requires_current_mail: 현재메일 컨텍스트 필수 여부
        capability_env: 기능 on/off 환경변수명
    """

    action_id: str
    title: str
    description: str
    query_template: str
    keywords: tuple[str, ...]
    intent_hints: tuple[str, ...]
    tool_action_hints: tuple[str, ...]
    requires_current_mail: bool
    capability_env: str


ACTION_DOMAINS: tuple[ActionDomain, ...] = (
    ActionDomain(
        action_id="draft_reply",
        title="회신 초안 작성",
        description="현재 메일의 핵심 쟁점을 반영해 회신 초안을 생성합니다.",
        query_template="현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘. 추가 질문 없이 본문만 작성해줘",
        keywords=("회신", "답장", "reply", "요청", "문의", "확인 부탁", "공유"),
        intent_hints=("summary", "analysis", "structured_template"),
        tool_action_hints=("current_mail", "mail_context", "read_current_mail"),
        requires_current_mail=True,
        capability_env="MOLDUBOT_ACTION_ENABLE_REPLY_DRAFT",
    ),
    ActionDomain(
        action_id="analyze_code_snippet",
        title="코드 스니펫 분석",
        description="현재 메일 본문의 코드 스니펫이 하는 일과 보안 점검 포인트를 설명합니다.",
        query_template=(
            "현재메일 본문에 코드 스니펫이 있으면 아래 형식으로 답변해줘. "
            "1) '## 코드 분석' 섹션: 기능 요약과 보안 리스크를 간결히 정리. "
            "2) '## 코드 리뷰' 섹션: 언어명 표시 후 핵심 코드 스니펫을 ```언어``` 블록으로 보여주고, 코드 설명/개선 포인트를 작성. "
            "코드가 없으면 '코드 스니펫이 없습니다.'라고만 답해줘."
        ),
        keywords=(
            "코드",
            "스니펫",
            "코드리뷰",
            "리뷰",
            "보안",
            "정책",
            "스크립트",
            "함수",
            "sql",
            "api",
        ),
        intent_hints=("summary", "analysis", "structured_template", "issue_action"),
        tool_action_hints=("current_mail", "mail_context", "read_current_mail"),
        requires_current_mail=True,
        capability_env="MOLDUBOT_ACTION_ENABLE_CODE_ANALYSIS",
    ),
    ActionDomain(
        action_id="create_todo",
        title="할 일(ToDo) 등록",
        description="조치 필요 사항을 기반으로 담당자 할 일을 등록합니다.",
        query_template="현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘",
        keywords=("조치", "해야", "todo", "to-do", "담당", "기한", "체크", "follow-up"),
        intent_hints=("summary", "action", "structured_template"),
        tool_action_hints=("current_mail", "todo", "create_outlook_todo"),
        requires_current_mail=True,
        capability_env="MOLDUBOT_ACTION_ENABLE_TODO",
    ),
    ActionDomain(
        action_id="create_calendar_event",
        title="일정 생성",
        description="메일의 일정 협의 내용을 바탕으로 캘린더 일정을 생성합니다.",
        query_template="현재메일 제안 내용으로 일정 생성해줘",
        keywords=("일정", "회의", "미팅", "시간", "날짜", "참석", "캘린더", "calendar"),
        intent_hints=("calendar", "schedule", "meeting"),
        tool_action_hints=("calendar", "book_meeting_room", "meeting"),
        requires_current_mail=True,
        capability_env="MOLDUBOT_ACTION_ENABLE_CALENDAR",
    ),
    ActionDomain(
        action_id="book_meeting_room",
        title="회의실 예약",
        description="메일에 나온 회의 일정으로 사용 가능한 회의실을 예약합니다.",
        query_template="현재메일 기준으로 회의실 예약해줘",
        keywords=("회의실", "room", "예약", "빌딩", "층", "인원", "장소"),
        intent_hints=("calendar", "meeting", "schedule"),
        tool_action_hints=("meeting", "book_meeting_room"),
        requires_current_mail=True,
        capability_env="MOLDUBOT_ACTION_ENABLE_MEETING_ROOM",
    ),
    ActionDomain(
        action_id="web_search",
        title="외부 정보 검색",
        description="핵심 이슈와 관련된 외부 기술 문서/공지 정보를 검색합니다.",
        query_template="이 이슈 관련 최신 외부 정보 검색해줘",
        keywords=("원인", "장애", "오류", "정책", "보안", "가이드", "공식문서", "최신"),
        intent_hints=("analysis", "search", "research"),
        tool_action_hints=("mail_search", "web"),
        requires_current_mail=False,
        capability_env="MOLDUBOT_ACTION_ENABLE_WEB_SEARCH",
    ),
    ActionDomain(
        action_id="search_related_mails",
        title="관련 메일 추가 조회",
        description="동일 이슈의 과거/연관 메일을 찾아 근거를 확장합니다.",
        query_template="이 주제 관련 메일 최근순으로 5개 조회해줘",
        keywords=("관련 메일", "추가", "최근", "과거", "스레드", "근거"),
        intent_hints=("search", "summary", "mail"),
        tool_action_hints=("mail_search", "current_mail", "read_current_mail"),
        requires_current_mail=False,
        capability_env="MOLDUBOT_ACTION_ENABLE_MAIL_SEARCH",
    ),
)
