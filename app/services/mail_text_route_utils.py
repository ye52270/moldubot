from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime

EMAIL_ADDRESS_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAIL_HEADER_LINE_PATTERN = re.compile(
    r"^\s*(From|To|Cc|Sent|Subject|발신자|보낸 사람|수신자|참조|날짜|제목)\s*:\s*(.+?)\s*$",
    flags=re.IGNORECASE,
)


def normalize_route_step_date(value: str) -> str:
    """단계 헤더의 sent/date 문자열에서 표시용 날짜(YYYY-MM-DD)만 추출한다."""
    text = str(value or "").strip()
    if not text:
        return ""
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return str(iso_match.group(1) or "")
    dotted = re.search(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", text)
    if dotted:
        year = str(dotted.group(1) or "").strip()
        month = str(dotted.group(2) or "").strip().zfill(2)
        day = str(dotted.group(3) or "").strip().zfill(2)
        return f"{year}-{month}-{day}"
    korean = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if korean:
        year = str(korean.group(1) or "").strip()
        month = str(korean.group(2) or "").strip().zfill(2)
        day = str(korean.group(3) or "").strip().zfill(2)
        return f"{year}-{month}-{day}"
    try:
        parsed = parsedate_to_datetime(text)
    except Exception:
        parsed = None
    if parsed is None:
        return ""
    return parsed.date().isoformat()


def decode_recipient_header_text(value: str) -> str:
    """수신자 헤더 원문을 디코딩/정리한다."""
    decoded = html.unescape(str(value or ""))
    decoded = re.sub(r"\s+", " ", decoded)
    return decoded.strip()


def normalize_recipient_name(value: str) -> str:
    """수신자 문자열에서 표시용 이름만 정제한다."""
    text = str(value or "")
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"/[^<>,;]+", " ", text)
    text = re.sub(r"^\s*(to|cc)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;")


def normalize_recipient_entry(value: str) -> str:
    """단일 수신자 문자열을 `이름 <email>` 또는 `email` 형태로 정규화한다."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    email_match = EMAIL_ADDRESS_PATTERN.search(raw)
    if not email_match:
        return normalize_recipient_name(value=raw)
    email = str(email_match.group(0) or "").strip()
    name_raw = raw.replace(email, " ")
    name = normalize_recipient_name(value=name_raw)
    return f"{name} <{email}>" if name else email


def extract_person_name_or_email(value: str) -> str:
    """사람 식별 문자열에서 이름 우선 라벨을 추출한다(이름이 없으면 이메일 사용)."""
    normalized = normalize_recipient_entry(value=value)
    if not normalized:
        return ""
    matched = re.match(r"^(.*?)\s*<([^>]+)>$", normalized)
    if matched:
        name = str(matched.group(1) or "").strip()
        email = str(matched.group(2) or "").strip()
        return name or email
    return normalized


def normalize_mail_header_field(field: str) -> str:
    """헤더 필드명을 표준 키(`from/to/cc/sent/subject`)로 정규화한다."""
    lowered = str(field or "").strip().lower().replace(" ", "")
    if lowered in ("from", "발신자", "보낸사람"):
        return "from"
    if lowered in ("to", "수신자"):
        return "to"
    if lowered in ("cc", "참조"):
        return "cc"
    if lowered in ("sent", "날짜"):
        return "sent"
    if lowered in ("subject", "제목"):
        return "subject"
    return ""


def append_header_value(base: str, value: str) -> str:
    """헤더 필드의 다중 라인 값을 안전하게 이어 붙인다."""
    left = str(base or "").strip()
    right = str(value or "").strip()
    if not left:
        return right
    if not right:
        return left
    return f"{left}, {right}"


def looks_like_header_continuation(line: str) -> bool:
    """헤더 줄의 줄바꿈 이어쓰기 후보인지 판단한다."""
    text = str(line or "").strip()
    if not text:
        return False
    if MAIL_HEADER_LINE_PATTERN.match(text):
        return False
    return bool(EMAIL_ADDRESS_PATTERN.search(text) or "," in text or ";" in text)


def normalize_recipient_list(value: str) -> list[str]:
    """수신자 헤더 문자열을 사람 표시 라벨 목록으로 정규화한다."""
    decoded = decode_recipient_header_text(value=value)
    if not decoded:
        return []
    parts = [item.strip() for item in re.split(r"[;,]", decoded) if item and item.strip()]
    labels: list[str] = []
    for part in parts:
        label = extract_person_name_or_email(value=part)
        if label and label not in labels:
            labels.append(label)
    return labels


def summarize_people(items: list[str]) -> str:
    """사람 목록을 카드 표시용 요약 문자열로 변환한다."""
    if not items:
        return "-"
    if len(items) <= 2:
        return ", ".join(items)
    return ", ".join(items[:2]) + f" 외 {len(items) - 2}명"


def extract_header_route_blocks(text: str) -> list[dict[str, str]]:
    """본문에서 헤더 블록 단위(`From/To/...`)를 추출한다."""
    lines = str(text or "").replace("\r", "\n").split("\n")
    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}
    current_key = ""
    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            current_key = ""
            continue
        matched = MAIL_HEADER_LINE_PATTERN.match(line)
        if matched:
            field = normalize_mail_header_field(str(matched.group(1) or ""))
            value = decode_recipient_header_text(value=str(matched.group(2) or ""))
            if field == "from" and (current.get("from") or current.get("to")):
                blocks.append(dict(current))
                current = {}
            if field:
                current[field] = append_header_value(base=current.get(field, ""), value=value)
                current_key = field
                continue
        if current_key in ("to", "cc") and looks_like_header_continuation(line=line):
            current[current_key] = append_header_value(base=current.get(current_key, ""), value=line)
            continue
        current_key = ""
    if current.get("from") or current.get("to"):
        blocks.append(dict(current))
    return blocks


def extract_mail_route_steps(text: str, max_steps: int = 4) -> list[dict[str, str]]:
    """메일 본문 헤더(`From:/To:`)를 분석해 단계별 발신자/수신자 흐름을 추출한다."""
    blocks = extract_header_route_blocks(text=text)
    steps: list[dict[str, str]] = []
    for block in blocks:
        sender = extract_person_name_or_email(value=str(block.get("from") or ""))
        recipients = normalize_recipient_list(value=str(block.get("to") or ""))
        sent_date = normalize_route_step_date(value=str(block.get("sent") or ""))
        if not sender or not recipients:
            continue
        steps.append(
            {
                "date": sent_date,
                "from": sender or "-",
                "to": summarize_people(items=recipients) if recipients else "-",
            }
        )
    if not steps:
        return []
    ordered = list(reversed(steps))
    return ordered[-max(1, int(max_steps)) :]


def build_mail_route_compact_text(text: str, max_steps: int = 4) -> str:
    """단계별 발신/수신 흐름을 UI 전달용 문자열(`from=>to%%from=>to`)로 변환한다."""
    steps = extract_mail_route_steps(text=text, max_steps=max_steps)
    if not steps:
        return ""
    serialized: list[str] = []
    for step in steps:
        base = f"{step['from']}=>{step['to']}"
        date_label = str(step.get("date") or "").strip()
        serialized.append(f"{date_label}::{base}" if date_label else base)
    return "%%".join(serialized)
