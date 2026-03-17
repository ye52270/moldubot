from __future__ import annotations

from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Any

from langchain.tools import tool

from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.todo_client import GraphTodoClient
from app.agents.tools_search_helpers import (
    apply_scope_to_query,
    build_scope_blocked_payload,
    search_mails_with_query_fanout,
    should_fanout_tech_issue_query,
)
from app.agents.tools_schedule import (
    book_meeting_room,
    create_outlook_calendar_event,
    current_date,
    search_meeting_rooms,
)
from app.agents.tools_todo_helpers import (
    normalize_outlook_todo_due_date,
    normalize_outlook_todo_title,
    resolve_default_outlook_todo_due_date,
    resolve_todo_client,
)
from app.services.mail_service import MailRecord, MailService
from app.services.mail_search_service import MailSearchService

ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"

_MAIL_SERVICE = MailService(db_path=MAIL_DB_PATH)
_MAIL_SEARCH_SERVICE = MailSearchService(db_path=MAIL_DB_PATH)
_TODO_CLIENT = GraphTodoClient()
logger = get_logger(__name__)
_POST_ACTION_CACHE_CTX: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "agent_tools_post_action_cache",
    default={},
)
_SEARCH_SCOPE_CTX: ContextVar[dict[str, str]] = ContextVar(
    "agent_tools_search_scope_contract",
    default={},
)


def prime_current_mail(mail: MailRecord) -> None:
    """
    외부 조회 결과 메일을 에이전트 메일 컨텍스트로 주입한다.

    Args:
        mail: 현재 메일로 설정할 레코드
    """
    _MAIL_SERVICE.set_current_mail(mail=mail)
    _clear_post_action_cache()


def clear_current_mail() -> None:
    """
    에이전트 메일 컨텍스트 캐시를 초기화한다.
    """
    _MAIL_SERVICE.clear_current_mail()
    _clear_post_action_cache()


def _clear_post_action_cache() -> None:
    """
    후속작업 결과 캐시를 초기화한다.
    """
    _POST_ACTION_CACHE_CTX.set({})


def set_search_scope_contract(contract: dict[str, str]) -> object:
    """
    검색 도구 실행에 사용할 scope 계약을 context-local로 설정한다.

    Args:
        contract: scope 계약 사전

    Returns:
        contextvars reset token
    """
    normalized = contract if isinstance(contract, dict) else {}
    return _SEARCH_SCOPE_CTX.set(dict(normalized))


def reset_search_scope_contract(token: object) -> None:
    """
    검색 도구 scope 계약 context를 이전 상태로 복원한다.

    Args:
        token: `set_search_scope_contract`가 반환한 reset token
    """
    try:
        _SEARCH_SCOPE_CTX.reset(token)
    except Exception:
        _SEARCH_SCOPE_CTX.set({})


def _resolve_search_scope_contract() -> dict[str, str]:
    """
    현재 요청의 검색 scope 계약을 반환한다.

    Returns:
        scope 계약 사전
    """
    contract = _SEARCH_SCOPE_CTX.get()
    return contract if isinstance(contract, dict) else {}


def _apply_scope_to_query(query: str, contract: dict[str, str]) -> str:
    """
    scope 계약에 따라 검색 질의를 보정한다.

    Args:
        query: 원본 검색 질의
        contract: scope 계약 사전

    Returns:
        보정된 질의
    """
    return apply_scope_to_query(query=query, contract=contract)


def _build_scope_blocked_payload(reason: str, query: str) -> dict[str, Any]:
    """
    scope 위반 시 반환할 표준 실패 payload를 생성한다.

    Args:
        reason: 실패 사유
        query: 검색 질의

    Returns:
        mail_search 실패 payload
    """
    return build_scope_blocked_payload(reason=reason, query=query)


def _build_post_action_cache_key(mail: MailRecord, action: str) -> str:
    """
    후속작업 캐시 키를 생성한다.

    Args:
        mail: 현재 메일 컨텍스트
        action: 후속 액션명
    Returns:
        캐시 키 문자열
    """
    normalized_action = str(action or "").strip().lower() or "summary"
    return f"{mail.message_id}:{normalized_action}"


def _normalize_outlook_todo_title(title: str, detail: str) -> str:
    """
    Outlook ToDo 제목을 `[{메일제목요약}] {할일주제}` 형식으로 정규화한다.

    Args:
        title: 도구 입력 제목
        detail: 도구 입력 상세

    Returns:
        정규화된 제목 문자열
    """
    return normalize_outlook_todo_title(title=title, detail=detail, mail_service=_MAIL_SERVICE)


def _resolve_default_outlook_todo_due_date() -> str:
    """
    Outlook ToDo 기본 마감일(오늘)을 반환한다.

    Returns:
        YYYY-MM-DD 형식의 오늘 날짜
    """
    return resolve_default_outlook_todo_due_date()


def _resolve_todo_client() -> GraphTodoClient:
    """
    ToDo 클라이언트를 반환한다.

    설정 미주입 상태라면 재초기화를 1회 시도해 지연 환경 로딩 케이스를 흡수한다.

    Returns:
        사용 가능한 GraphTodoClient 인스턴스
    """
    global _TODO_CLIENT
    resolved_client = resolve_todo_client(todo_client=_TODO_CLIENT)
    if resolved_client is not _TODO_CLIENT and resolved_client.is_configured():
        logger.info("create_outlook_todo GraphTodoClient 재초기화로 설정 감지 성공")
        _TODO_CLIENT = resolved_client
    return _TODO_CLIENT


def _normalize_outlook_todo_due_date(raw_due_date: str) -> str:
    """
    ToDo 마감일 문자열을 YYYY-MM-DD 형식으로 정규화한다.

    Args:
        raw_due_date: 모델이 생성한 마감일 원문

    Returns:
        정규화된 마감일. 파싱 불가하면 빈 문자열
    """
    return normalize_outlook_todo_due_date(raw_due_date=raw_due_date)


@tool
def run_mail_post_action(action: str = "summary", summary_line_target: int = 5) -> dict[str, Any]:
    """
    메일 조회 후속작업 요청을 context-only 단일 경로로 처리한다.

    Args:
        action: `current_mail`, `summary`, `report`, `key_facts`, `recipients`, `summary_with_key_facts`
        summary_line_target: 하위호환용 인자(현재 미사용)

    Returns:
        후속작업 실행 결과 사전(`current_mail` 외 액션은 context-only)
    """
    _ = summary_line_target
    mail = _MAIL_SERVICE.get_current_mail()
    if mail is None:
        return {"status": "failed", "reason": "현재 메일을 찾지 못했습니다."}

    cache_key = _build_post_action_cache_key(
        mail=mail,
        action=action,
    )
    cache_store = _POST_ACTION_CACHE_CTX.get()
    cached = cache_store.get(cache_key) if isinstance(cache_store, dict) else None
    if isinstance(cached, dict):
        logger.info("run_mail_post_action cache hit: key=%s", cache_key)
        return deepcopy(cached)

    payload = _MAIL_SERVICE.run_post_action(
        action=action,
    )
    result = {"status": "completed", **payload}
    next_cache = dict(cache_store) if isinstance(cache_store, dict) else {}
    next_cache[cache_key] = deepcopy(result)
    _POST_ACTION_CACHE_CTX.set(next_cache)
    return result


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
    scope_contract = _resolve_search_scope_contract()
    scope_mode = str(scope_contract.get("mode") or "").strip().lower()
    if scope_mode == "current_mail":
        logger.warning("search_mails scope 차단: mode=current_mail query=%s", str(query or "")[:80])
        return _build_scope_blocked_payload(
            reason="현재메일 범위에서는 사서함 검색 도구를 실행하지 않습니다.",
            query=query,
        )
    scoped_query = _apply_scope_to_query(query=query, contract=scope_contract)
    if scoped_query != str(query or "").strip():
        logger.info(
            "search_mails scope 질의 보정: original=%s scoped=%s anchor=%s",
            str(query or "")[:80],
            scoped_query[:80],
            str(scope_contract.get("anchor_query") or "")[:60],
        )
    if should_fanout_tech_issue_query(query=scoped_query):
        return _search_mails_with_query_fanout(
            query=scoped_query,
            person=person,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    return _MAIL_SEARCH_SERVICE.search(
        query=scoped_query,
        person=person,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


def _search_mails_with_query_fanout(
    query: str,
    person: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> dict[str, Any]:
    """
    분할 키워드 질의를 다중 검색으로 실행한 뒤 단일 payload로 병합한다.

    Args:
        query: 원본 검색 질의
        person: 사람명 필터
        start_date: 시작일(YYYY-MM-DD)
        end_date: 종료일(YYYY-MM-DD)
        limit: 반환 개수

    Returns:
        병합된 `mail_search` payload
    """
    return search_mails_with_query_fanout(
        query=query,
        person=person,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        search_service=_MAIL_SEARCH_SERVICE,
    )


@tool
def search_meeting_schedule(
    query: str,
    person: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """
    일정/회의 관련 메일 검색을 수행한다.

    Args:
        query: 검색 질의(키워드/자연어)
        person: 사람명 필터
        start_date: 시작일(YYYY-MM-DD)
        end_date: 종료일(YYYY-MM-DD)
        limit: 반환 개수

    Returns:
        검색 결과 payload(`action=mail_search`)
    """
    logger.info(
        "search_meeting_schedule 호출: query=%s person=%s start_date=%s end_date=%s limit=%s",
        str(query or "")[:80],
        person,
        start_date,
        end_date,
        limit,
    )
    scope_contract = _resolve_search_scope_contract()
    scope_mode = str(scope_contract.get("mode") or "").strip().lower()
    if scope_mode == "current_mail":
        logger.warning(
            "search_meeting_schedule scope 차단: mode=current_mail query=%s",
            str(query or "")[:80],
        )
        return _build_scope_blocked_payload(
            reason="현재메일 범위에서는 일정 검색 도구를 실행하지 않습니다.",
            query=query,
        )
    scoped_query = _apply_scope_to_query(query=query, contract=scope_contract)
    if scoped_query != str(query or "").strip():
        logger.info(
            "search_meeting_schedule scope 질의 보정: original=%s scoped=%s anchor=%s",
            str(query or "")[:80],
            scoped_query[:80],
            str(scope_contract.get("anchor_query") or "")[:60],
        )
    return _MAIL_SEARCH_SERVICE.search(
        query=scoped_query,
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
    normalized_due_date = _normalize_outlook_todo_due_date(raw_due_date=due_date)
    normalized_detail = str(detail or "").strip()
    if not normalized_title:
        return {"status": "failed", "reason": "title은 필수입니다."}
    if not normalized_due_date:
        normalized_due_date = _resolve_default_outlook_todo_due_date()
        logger.warning(
            "create_outlook_todo due_date 정규화 실패로 기본일 사용: raw_due_date=%s fallback_due_date=%s",
            str(due_date or "").strip(),
            normalized_due_date,
        )
    todo_client = _resolve_todo_client()
    if not todo_client.is_configured():
        return {"status": "failed", "reason": "Outlook ToDo 연동 설정이 비활성입니다. 서버의 MICROSOFT_APP_ID를 확인해 주세요."}
    task = todo_client.create_task(
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
        search_meeting_schedule,
        current_date,
        search_meeting_rooms,
        book_meeting_room,
        create_outlook_calendar_event,
        create_outlook_todo,
    ]
