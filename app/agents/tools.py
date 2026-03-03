from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from langchain.tools import tool

from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.todo_client import GraphTodoClient
from app.agents.tools_schedule import (
    book_meeting_room,
    create_outlook_calendar_event,
    current_date,
    search_meeting_rooms,
)
from app.services.mail_service import MailRecord, MailService
from app.services.mail_search_service import MailSearchService

ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"

_MAIL_SERVICE = MailService(db_path=MAIL_DB_PATH)
_MAIL_SEARCH_SERVICE = MailSearchService(db_path=MAIL_DB_PATH)
_TODO_CLIENT = GraphTodoClient()
logger = get_logger(__name__)
MAIL_SUBJECT_HANGUL_PREFIX_LEN = 5
MAX_TODO_TOPIC_CHARS = 24
TODO_FALLBACK_TOPIC = "후속 작업"
TODO_DEFAULT_SUBJECT = "메일요약"
TODO_NOISE_PHRASES = (
    "액션 아이템을 확인하지 못했습니다",
    "액션 아이템",
    "action item",
    "action items",
)
MAIL_PREFIX_PATTERN = re.compile(
    r"^(?:(?:\s*(?:re|fw|fwd|sv|답장|전달)\s*[:：]\s*)+)",
    flags=re.IGNORECASE,
)


def prime_current_mail(mail: MailRecord) -> None:
    """
    외부 조회 결과 메일을 에이전트 메일 컨텍스트로 주입한다.

    Args:
        mail: 현재 메일로 설정할 레코드
    """
    _MAIL_SERVICE.set_current_mail(mail=mail)


def clear_current_mail() -> None:
    """
    에이전트 메일 컨텍스트 캐시를 초기화한다.
    """
    _MAIL_SERVICE.clear_current_mail()


def _collapse_whitespace(text: str) -> str:
    """
    문자열의 연속 공백을 단일 공백으로 정리한다.

    Args:
        text: 정리 대상 문자열

    Returns:
        공백 정리된 문자열
    """
    return " ".join(str(text or "").replace("\n", " ").replace("\t", " ").split())


def _strip_todo_title_noise(text: str) -> str:
    """
    ToDo 제목에서 마크다운/번호/불필요 접두어를 제거한다.

    Args:
        text: 원본 제목

    Returns:
        정제된 제목
    """
    normalized = _collapse_whitespace(text)
    prefixes = ("## ", "# ", "- ", "* ", "1. ", "2. ", "3. ", "4. ", "5. ")
    while True:
        next_value = normalized
        for prefix in prefixes:
            if next_value.startswith(prefix):
                next_value = next_value[len(prefix):].strip()
        if next_value == normalized:
            break
        normalized = next_value
    for marker in (":", " - ", " — ", "|"):
        if marker in normalized:
            head, tail = normalized.split(marker, 1)
            if any(token in head.lower() for token in ("액션 아이템", "action item")):
                normalized = tail.strip()
                break
    # 모델이 제목 앞에 `[메일제목]` 블록을 붙인 경우 제거한다.
    normalized = re.sub(r"^(?:\s*\[[^\]]+\]\s*)+", "", normalized)
    return _collapse_whitespace(normalized)


def _normalize_outlook_todo_title(title: str, detail: str) -> str:
    """
    Outlook ToDo 제목을 `[{메일제목요약}] {할일주제}` 형식으로 정규화한다.

    Args:
        title: 도구 입력 제목
        detail: 도구 입력 상세

    Returns:
        정규화된 제목 문자열
    """
    cleaned_title = _strip_todo_title_noise(title)
    cleaned_detail = _strip_todo_title_noise(detail)
    candidate = cleaned_title or cleaned_detail
    lower_candidate = candidate.lower()
    if not candidate or any(phrase in lower_candidate for phrase in TODO_NOISE_PHRASES):
        candidate = TODO_FALLBACK_TOPIC
    candidate = _collapse_whitespace(candidate).strip(" .,:;")
    if len(candidate) > MAX_TODO_TOPIC_CHARS:
        candidate = candidate[:MAX_TODO_TOPIC_CHARS].rstrip()
    if not candidate:
        candidate = TODO_FALLBACK_TOPIC
    subject = _resolve_todo_mail_subject()
    return f"[{subject}]{candidate}"


def _resolve_todo_mail_subject() -> str:
    """
    ToDo 제목 접두어로 사용할 메일 제목 요약을 반환한다.

    Returns:
        정제된 제목 요약 문자열
    """
    subject = _extract_subject_from_current_mail()
    if subject:
        return subject
    return TODO_DEFAULT_SUBJECT


def _extract_subject_from_current_mail() -> str:
    """
    현재 메일 컨텍스트에서 제목 요약 후보를 추출한다.

    Returns:
        정규화된 제목 요약 문자열
    """
    current_mail = _MAIL_SERVICE.get_current_mail()
    if current_mail is None:
        current_mail = _MAIL_SERVICE.read_current_mail()
    raw_subject = _collapse_whitespace(str(getattr(current_mail, "subject", "") or ""))
    normalized = _trim_subject_prefix_tokens(raw_subject)
    hangul_only = "".join(re.findall(r"[가-힣]", normalized))
    if hangul_only:
        return hangul_only[:MAIL_SUBJECT_HANGUL_PREFIX_LEN]
    compact = re.sub(r"\s+", "", normalized)
    return compact[:MAIL_SUBJECT_HANGUL_PREFIX_LEN]


def _trim_subject_prefix_tokens(subject: str) -> str:
    """
    제목의 회신/전달 접두어와 선행 태그를 제거한다.

    Args:
        subject: 원본 제목

    Returns:
        정제된 제목
    """
    normalized = str(subject or "").strip()
    normalized = MAIL_PREFIX_PATTERN.sub("", normalized)
    normalized = re.sub(r"^(?:\s*\[[^\]]*\]\s*)+", "", normalized)
    normalized = re.sub(r"^(?:\s*\([^)]+\)\s*)+", "", normalized)
    return normalized.strip()


@tool
def run_mail_post_action(action: str = "summary", summary_line_target: int = 5) -> dict[str, Any]:
    """
    메일 조회 후속작업 요청을 context-only 단일 경로로 처리한다.

    Args:
        action: `current_mail`, `summary`, `report`, `key_facts`, `recipients`, `summary_with_key_facts`
        summary_line_target: 요약 줄 수 목표

    Returns:
        후속작업 실행 결과 사전(`current_mail` 외 액션은 context-only)
    """
    mail = _MAIL_SERVICE.get_current_mail()
    if mail is None:
        return {"status": "failed", "reason": "현재 메일을 찾지 못했습니다."}

    payload = _MAIL_SERVICE.run_post_action(
        action=action,
        summary_line_target=summary_line_target,
    )
    return {"status": "completed", **payload}


@tool
def search_mails(
    query: str,
    person: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """
    메일 조건 검색을 수행한다.

    Args:
        query: 검색 질의(키워드/자연어)
        person: 사람명 필터
        start_date: 시작일(YYYY-MM-DD)
        end_date: 종료일(YYYY-MM-DD)
        limit: 반환 개수

    Returns:
        검색 결과 payload
    """
    logger.info(
        "search_mails 호출: query=%s person=%s start_date=%s end_date=%s limit=%s",
        str(query or "")[:80],
        person,
        start_date,
        end_date,
        limit,
    )
    return _MAIL_SEARCH_SERVICE.search(
        query=query,
        person=person,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@tool
def create_outlook_todo(title: str, due_date: str, detail: str = "") -> dict[str, Any]:
    """
    Outlook ToDo에 할 일을 등록한다.

    Args:
        title: 할 일 제목
        due_date: 마감일(YYYY-MM-DD)
        detail: 세부 설명

    Returns:
        ToDo 생성 결과 사전
    """
    normalized_title = _normalize_outlook_todo_title(title=title, detail=detail)
    normalized_due_date = str(due_date or "").strip()
    normalized_detail = str(detail or "").strip()
    if not normalized_title:
        return {"status": "failed", "reason": "title은 필수입니다."}
    try:
        datetime.strptime(normalized_due_date, "%Y-%m-%d")
    except ValueError:
        return {"status": "failed", "reason": "due_date 형식은 YYYY-MM-DD 여야 합니다."}
    task = _TODO_CLIENT.create_task(
        title=normalized_title,
        due_date=normalized_due_date,
        body_text=normalized_detail,
    )
    if task is None:
        return {"status": "failed", "reason": "Outlook ToDo 생성에 실패했습니다. Graph 설정/로그인을 확인해 주세요."}
    return {
        "action": "create_outlook_todo",
        "status": "completed",
        "task": {
            "id": task.task_id,
            "web_link": task.web_link,
            "title": normalized_title,
            "due_date": normalized_due_date,
            "detail": normalized_detail,
        },
    }


def get_agent_tools() -> list[Any]:
    """
    deep agent에 주입할 도구 목록을 반환한다.

    Returns:
        LangChain tool 객체 목록
    """
    return [
        run_mail_post_action,
        search_mails,
        current_date,
        search_meeting_rooms,
        book_meeting_room,
        create_outlook_calendar_event,
        create_outlook_todo,
    ]
