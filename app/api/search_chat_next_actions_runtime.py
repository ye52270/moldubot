from __future__ import annotations

import re
from typing import Any

ACTION_ID_REPLY_DRAFT = "draft_reply"
ACTION_ID_CODE_ANALYSIS = "analyze_code_snippet"
ACTION_ID_CREATE_TODO = "create_todo"
ACTION_ID_CREATE_CALENDAR = "create_calendar_event"
ACTION_ID_BOOK_MEETING_ROOM = "book_meeting_room"
ACTION_ID_SEARCH_RELATED_MAILS = "search_related_mails"
ACTION_ID_WEB_SEARCH = "web_search"

NEXT_ACTION_FORCED_QUERIES: dict[str, str] = {
    ACTION_ID_REPLY_DRAFT: "현재메일 기준으로 바로 보낼 수 있는 회신 메일 본문 초안을 작성해줘. 추가 질문 없이 본문만 작성해줘",
    ACTION_ID_CODE_ANALYSIS: (
        "현재메일 본문에 코드 스니펫이 있으면 아래 형식으로 답변해줘. "
        "1) '## 코드 분석' 섹션: 기능 요약과 보안 리스크를 간결히 정리. "
        "2) '## 코드 리뷰' 섹션: 언어명 표시 후 핵심 코드 스니펫을 ```언어``` 블록으로 보여주고, 코드 설명/개선 포인트를 작성. "
        "코드가 없으면 '코드 스니펫이 없습니다.'라고만 답해줘."
    ),
    ACTION_ID_CREATE_TODO: "현재메일 기반으로 조치 필요 사항을 ToDo로 등록해줘",
    ACTION_ID_CREATE_CALENDAR: "현재메일 제안 내용으로 일정 생성해줘",
    ACTION_ID_BOOK_MEETING_ROOM: "현재메일 기준으로 회의실 예약해줘",
    ACTION_ID_SEARCH_RELATED_MAILS: "이 주제 관련 메일 최근순으로 5개 조회해줘",
    ACTION_ID_WEB_SEARCH: "이 이슈 관련 최신 외부 정보 검색해줘",
}


def normalize_next_action_id(runtime_options: dict[str, Any]) -> str:
    """
    런타임 옵션에서 next action 식별자를 정규화한다.

    Args:
        runtime_options: 요청 런타임 옵션

    Returns:
        허용된 next action 식별자. 없거나 미허용 값이면 빈 문자열
    """
    raw_action_id = str(runtime_options.get("next_action_id") or "").strip().lower()
    if raw_action_id not in NEXT_ACTION_FORCED_QUERIES:
        return ""
    return raw_action_id


def _extract_query_keywords_from_mail_context(current_mail_subject: str, current_mail_from: str) -> list[str]:
    """
    현재 메일 컨텍스트에서 강제 질의에 사용할 키워드를 추출한다.

    Args:
        current_mail_subject: 현재 메일 제목
        current_mail_from: 현재 메일 발신자 주소

    Returns:
        중복 제거된 키워드 목록(최대 4개)
    """
    raw_subject = str(current_mail_subject or "").strip()
    normalized_subject = re.sub(
        r"^(?:(?:\s*(?:re|fw|fwd|sv|답장|전달)\s*[:：]\s*)+)",
        "",
        raw_subject,
        flags=re.IGNORECASE,
    )
    tokens = re.findall(r"[A-Za-z0-9가-힣]{2,}", normalized_subject.lower())
    stop_words = {"메일", "확인", "요청", "관련", "문의", "회신", "re", "fw", "fwd"}
    keywords: list[str] = []
    for token in tokens:
        if token in stop_words:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 3:
            break
    sender = str(current_mail_from or "").strip().lower()
    if sender:
        sender_local = sender.split("@", 1)[0].strip()
        if sender_local and sender_local not in keywords:
            keywords.append(sender_local)
    return keywords[:4]


def resolve_forced_next_action_query(
    next_action_id: str,
    fallback_query: str,
    current_mail_subject: str = "",
    current_mail_from: str = "",
) -> str:
    """
    next action 식별자에 대응되는 강제 질의를 반환한다.

    Args:
        next_action_id: next action 식별자
        fallback_query: 식별자 미지정/미지원 시 사용할 원본 질의
        current_mail_subject: 현재 메일 제목(있으면 키워드 기반 강제 질의 생성)
        current_mail_from: 현재 메일 발신자(있으면 키워드 기반 강제 질의 생성)

    Returns:
        강제 질의 또는 원본 질의
    """
    normalized_action_id = str(next_action_id or "").strip().lower()
    if not normalized_action_id:
        return str(fallback_query or "").strip()
    context_keywords = _extract_query_keywords_from_mail_context(
        current_mail_subject=current_mail_subject,
        current_mail_from=current_mail_from,
    )
    if normalized_action_id == ACTION_ID_SEARCH_RELATED_MAILS and context_keywords:
        return f"{' '.join(context_keywords)} 관련 메일 최근순으로 5개 조회해줘"
    if normalized_action_id == ACTION_ID_WEB_SEARCH and context_keywords:
        return f"{' '.join(context_keywords)} 관련 최신 외부 정보 검색해줘"
    forced_query = NEXT_ACTION_FORCED_QUERIES.get(normalized_action_id, "")
    if forced_query:
        return forced_query
    return str(fallback_query or "").strip()


def should_suppress_internal_mail_evidence(next_action_id: str) -> bool:
    """
    액션별로 내부 유사메일 근거 노출을 숨겨야 하는지 반환한다.

    Args:
        next_action_id: next action 식별자

    Returns:
        내부 유사메일 근거를 숨겨야 하면 True
    """
    return str(next_action_id or "").strip().lower() == ACTION_ID_WEB_SEARCH


def should_suppress_web_sources(next_action_id: str) -> bool:
    """
    액션별로 웹 출처 블록 노출을 숨겨야 하는지 반환한다.

    Args:
        next_action_id: next action 식별자

    Returns:
        웹 출처 블록을 숨겨야 하면 True
    """
    normalized_action_id = str(next_action_id or "").strip().lower()
    return normalized_action_id == ACTION_ID_SEARCH_RELATED_MAILS


def _extract_external_issue_keywords(subject: str, summary_text: str) -> list[str]:
    """
    현재 메일 제목/요약에서 외부 검색용 핵심 키워드를 추출한다.

    Args:
        subject: 메일 제목
        summary_text: 메일 요약 텍스트

    Returns:
        중복 제거된 키워드 목록(최대 6개)
    """
    raw = " ".join([str(subject or "").strip(), str(summary_text or "").strip()]).lower()
    tokens = re.findall(r"[A-Za-z0-9가-힣._-]{2,}", raw)
    stop_words = {
        "메일",
        "요청",
        "확인",
        "관련",
        "회신",
        "전달",
        "문의",
        "현재",
        "issue",
        "request",
        "fw",
        "re",
    }
    keywords: list[str] = []
    for token in tokens:
        if token in stop_words:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 6:
            break
    return keywords


def build_external_web_search_query(
    base_query: str,
    current_mail_subject: str,
    current_mail_summary: str,
) -> str:
    """
    현재 메일 이슈 키워드를 반영한 외부 검색 질의를 생성한다.

    Args:
        base_query: 기본 질의
        current_mail_subject: 현재 메일 제목
        current_mail_summary: 현재 메일 요약(summary)

    Returns:
        외부 검색 질의 문자열
    """
    keywords = _extract_external_issue_keywords(
        subject=current_mail_subject,
        summary_text=current_mail_summary,
    )
    if not keywords:
        return str(base_query or "").strip()
    return f"{' '.join(keywords)} 최신 이슈 원인 해결 가이드"


def render_external_web_search_answer(web_query: str, web_sources: list[dict[str, str]]) -> str:
    """
    외부 검색 결과를 사용자 응답용 요약 텍스트로 렌더링한다.

    Args:
        web_query: 실행한 검색 질의
        web_sources: 검색 출처 목록

    Returns:
        렌더링된 답변 문자열
    """
    if not web_sources:
        return (
            "## 📌 주요 내용\n"
            f"- 검색 키워드: {web_query or '-'}\n"
            "- 외부 검색 결과가 없습니다. 키워드를 구체화해 다시 시도해 주세요."
        )
    lines = [
        "## 📌 주요 내용",
        f"- 검색 키워드: {web_query or '-'}",
        f"- 확인한 외부 출처: {len(web_sources)}건",
        "",
        "## 🔎 외부 정보 요약",
    ]
    for index, source in enumerate(web_sources[:4], start=1):
        title = str(source.get("title") or "제목 없음").strip() or "제목 없음"
        site = str(source.get("site_name") or "출처").strip() or "출처"
        snippet = str(source.get("snippet") or "").strip()
        lines.append(f"{index}. {title} ({site})")
        if snippet:
            lines.append(f"- 요약: {snippet}")
    return "\n".join(lines).strip()
