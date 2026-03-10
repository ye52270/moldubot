from __future__ import annotations

from datetime import datetime
import re

from app.integrations.microsoft_graph.todo_client import GraphTodoClient
from app.services.mail_service import MailService

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
DATE_DASH_FORMAT = "%Y-%m-%d"
MAIL_PREFIX_PATTERN = re.compile(
    r"^(?:(?:\s*(?:re|fw|fwd|sv|답장|전달)\s*[:：]\s*)+)",
    flags=re.IGNORECASE,
)


def collapse_whitespace(text: str) -> str:
    """
    문자열의 연속 공백을 단일 공백으로 정리한다.
    """
    return " ".join(str(text or "").replace("\n", " ").replace("\t", " ").split())


def strip_todo_title_noise(text: str) -> str:
    """
    ToDo 제목에서 마크다운/번호/불필요 접두어를 제거한다.
    """
    normalized = collapse_whitespace(text)
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
    normalized = re.sub(r"^(?:\s*\[[^\]]+\]\s*)+", "", normalized)
    return collapse_whitespace(normalized)


def normalize_outlook_todo_title(title: str, detail: str, mail_service: MailService) -> str:
    """
    Outlook ToDo 제목을 `[{메일제목요약}] {할일주제}` 형식으로 정규화한다.
    """
    cleaned_title = strip_todo_title_noise(title)
    cleaned_detail = strip_todo_title_noise(detail)
    candidate = cleaned_title or cleaned_detail
    lower_candidate = candidate.lower()
    if not candidate or any(phrase in lower_candidate for phrase in TODO_NOISE_PHRASES):
        candidate = TODO_FALLBACK_TOPIC
    candidate = collapse_whitespace(candidate).strip(" .,:;")
    if len(candidate) > MAX_TODO_TOPIC_CHARS:
        candidate = candidate[:MAX_TODO_TOPIC_CHARS].rstrip()
    if not candidate:
        candidate = TODO_FALLBACK_TOPIC
    subject = resolve_todo_mail_subject(mail_service=mail_service)
    return f"[{subject}]{candidate}"


def normalize_outlook_todo_due_date(raw_due_date: str) -> str:
    """
    ToDo 마감일 문자열을 YYYY-MM-DD 형식으로 정규화한다.
    """
    normalized = str(raw_due_date or "").strip()
    if not normalized:
        return ""
    if "T" in normalized and len(normalized) >= 10:
        normalized = normalized[:10]
    normalized = normalized.replace("/", "-").replace(".", "-")
    korean_match = re.fullmatch(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", normalized)
    if korean_match:
        year, month, day = korean_match.groups()
        normalized = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    try:
        return datetime.strptime(normalized, DATE_DASH_FORMAT).strftime(DATE_DASH_FORMAT)
    except ValueError:
        return ""


def resolve_default_outlook_todo_due_date() -> str:
    """
    Outlook ToDo 기본 마감일(오늘)을 반환한다.
    """
    return datetime.now().strftime(DATE_DASH_FORMAT)


def resolve_todo_client(todo_client: GraphTodoClient) -> GraphTodoClient:
    """
    ToDo 클라이언트를 반환한다.
    """
    if todo_client.is_configured():
        return todo_client
    refreshed_client = GraphTodoClient()
    if refreshed_client.is_configured():
        return refreshed_client
    return todo_client


def resolve_todo_mail_subject(mail_service: MailService) -> str:
    """
    ToDo 제목 접두어로 사용할 메일 제목 요약을 반환한다.
    """
    subject = extract_subject_from_current_mail(mail_service=mail_service)
    if subject:
        return subject
    return TODO_DEFAULT_SUBJECT


def extract_subject_from_current_mail(mail_service: MailService) -> str:
    """
    현재 메일 컨텍스트에서 제목 요약 후보를 추출한다.
    """
    current_mail = mail_service.get_current_mail()
    if current_mail is None:
        current_mail = mail_service.read_current_mail()
    raw_subject = collapse_whitespace(str(getattr(current_mail, "subject", "") or ""))
    normalized = trim_subject_prefix_tokens(raw_subject)
    hangul_only = "".join(re.findall(r"[가-힣]", normalized))
    if hangul_only:
        return hangul_only[:MAIL_SUBJECT_HANGUL_PREFIX_LEN]
    compact = re.sub(r"\s+", "", normalized)
    return compact[:MAIL_SUBJECT_HANGUL_PREFIX_LEN]


def trim_subject_prefix_tokens(subject: str) -> str:
    """
    제목의 회신/전달 접두어와 선행 태그를 제거한다.
    """
    normalized = str(subject or "").strip()
    normalized = MAIL_PREFIX_PATTERN.sub("", normalized)
    normalized = re.sub(r"^(?:\s*\[[^\]]*\]\s*)+", "", normalized)
    normalized = re.sub(r"^(?:\s*\([^)]+\)\s*)+", "", normalized)
    return normalized.strip()
