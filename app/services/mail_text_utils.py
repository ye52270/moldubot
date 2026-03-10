from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.mail_service import MailRecord

SUMMARY_NOISE_PATTERNS = (
    r"^(from|sent|to|cc|bcc|subject|date)\s*:",
    r"^(발신자|수신자|참조|숨은참조|제목|날짜)\s*:",
    r"^fw:\s*",
    r"^re:\s*",
    r"^확인 부탁드립니다\.?$",
    r"^감사합니다\.?$",
    r"^[가-힣A-Za-z\s]+드림\.?$",
    r"^\d{2,3}-\d{3,4}-\d{4}$",
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
)
SUMMARY_PRIORITY_KEYWORDS = (
    "차단",
    "수신",
    "발송",
    "오류",
    "장애",
    "요청",
    "확인",
    "조치",
    "검토",
    "회신",
    "필요",
    "불가",
    "문의",
    "보안",
    "로그",
    "ip",
    "서버",
    "사서함",
    "정책",
)
EMAIL_ADDRESS_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MAIL_HEADER_LINE_PATTERN = re.compile(
    r"^\s*(From|To|Cc|Sent|Subject|발신자|보낸 사람|수신자|참조|날짜|제목)\s*:\s*(.+?)\s*$",
    flags=re.IGNORECASE,
)


def normalize_line_target(line_target: int) -> int:
    """
    요약 라인 목표값을 안전 범위(1~20)로 보정한다.

    Args:
        line_target: 입력 라인 목표값

    Returns:
        보정된 라인 목표값
    """
    if line_target < 1:
        return 1
    if line_target > 20:
        return 20
    return line_target


def split_sentences(text: str) -> list[str]:
    """
    본문 문자열을 문장/행 단위로 분리한다.

    Args:
        text: 원본 본문 텍스트

    Returns:
        비어 있지 않은 문장 목록
    """
    cleaned = re.sub(r"\r", "\n", str(text or ""))
    line_chunks = [item.strip() for item in cleaned.split("\n") if item and item.strip()]

    sentences: list[str] = []
    for chunk in line_chunks:
        parts = re.split(r"(?<=[가-힣A-Za-z0-9])[.!?]\s+", chunk)
        for part in parts:
            normalized = part.strip()
            if normalized:
                sentences.append(normalized)
    return sentences


def select_salient_summary_sentences(text: str, line_target: int) -> list[str]:
    """
    본문에서 요약 가치가 높은 문장을 우선 선별한다.

    Args:
        text: 원본 본문 텍스트
        line_target: 목표 라인 수

    Returns:
        우선순위가 적용된 문장 목록
    """
    target = normalize_line_target(line_target=line_target)
    raw_sentences = split_sentences(text=text)
    unique_sentences = _dedupe_sentences(sentences=raw_sentences)
    filtered = [sentence for sentence in unique_sentences if not is_summary_noise_sentence(sentence=sentence)]
    if not filtered:
        filtered = [sentence for sentence in unique_sentences if sentence.strip()]
    scored = [
        (_score_summary_sentence(sentence=sentence), index, sentence)
        for index, sentence in enumerate(filtered)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [trim_sentence(sentence=item[2]) for item in scored[:target]]
    if len(selected) < target:
        remaining = [trim_sentence(sentence=item) for item in filtered if trim_sentence(sentence=item) not in selected]
        selected.extend(remaining[: target - len(selected)])
    return selected[:target]


def is_summary_noise_sentence(sentence: str) -> bool:
    """
    요약 품질을 떨어뜨리는 헤더/서명/상투 문장인지 판별한다.

    Args:
        sentence: 검사할 문장

    Returns:
        노이즈 문장이면 True
    """
    text = str(sentence or "").strip()
    if not text:
        return True
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in SUMMARY_NOISE_PATTERNS):
        return True
    if len(text) < 10:
        return True
    header_token_count = sum(1 for token in ("From:", "Sent:", "To:", "Cc:", "Subject:") if token.lower() in text.lower())
    return header_token_count >= 2


def _score_summary_sentence(sentence: str) -> int:
    """
    요약 문장 우선순위를 계산한다.

    Args:
        sentence: 점수화 대상 문장

    Returns:
        우선순위 점수
    """
    text = str(sentence or "").strip()
    lowered = text.lower()
    score = 0
    for keyword in SUMMARY_PRIORITY_KEYWORDS:
        if keyword in lowered:
            score += 3
    if re.search(r"\d{2,3}(?:\.\d{1,3}){3}", text):
        score += 2
    if 20 <= len(text) <= 140:
        score += 2
    if len(text) > 220:
        score -= 2
    return score


def _dedupe_sentences(sentences: list[str]) -> list[str]:
    """
    문장 목록의 순서를 유지한 채 중복을 제거한다.

    Args:
        sentences: 원본 문장 목록

    Returns:
        중복 제거 문장 목록
    """
    unique: list[str] = []
    for sentence in sentences:
        text = str(sentence or "").strip()
        if not text:
            continue
        if text in unique:
            continue
        unique.append(text)
    return unique


def trim_sentence(sentence: str, max_len: int = 140) -> str:
    """
    문장을 최대 길이로 자른다.

    Args:
        sentence: 원본 문장
        max_len: 최대 길이

    Returns:
        길이 제한이 적용된 문장
    """
    text = sentence.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def extract_recipients_from_body(text: str) -> list[str]:
    """
    메일 본문 헤더 중 `To:` 구간에서 수신자 문자열을 파싱한다.

    Args:
        text: 메일 본문

    Returns:
        파싱된 수신자 목록
    """
    normalized = str(text or "").replace("\r", "\n")
    match = re.search(r"To:\s*(.+?)(?:Cc:|Subject:|From:|$)", normalized, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    raw = match.group(1).replace("\n", " ")
    decoded = _decode_recipient_header_text(value=raw)
    parts = [item.strip() for item in re.split(r"[;,]", decoded) if item and item.strip()]
    deduped: list[str] = []
    for recipient in parts:
        normalized = _normalize_recipient_entry(value=recipient)
        if not normalized:
            continue
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def extract_mail_route_steps(text: str, max_steps: int = 4) -> list[dict[str, str]]:
    """
    메일 본문 헤더(`From:/To:`)를 분석해 단계별 발신자/수신자 흐름을 추출한다.

    Args:
        text: 메일 본문 원문
        max_steps: 최대 단계 수

    Returns:
        오래된 단계부터 최신 단계 순서의 발신/수신 흐름 목록.
        발신자와 수신자가 모두 식별되는 단계만 포함한다.
    """
    blocks = _extract_header_route_blocks(text=text)
    steps: list[dict[str, str]] = []
    for block in blocks:
        sender = extract_person_name_or_email(value=str(block.get("from") or ""))
        recipients = _normalize_recipient_list(value=str(block.get("to") or ""))
        sent_date = _normalize_route_step_date(value=str(block.get("sent") or ""))
        if not sender and not recipients:
            continue
        if not sender or not recipients:
            continue
        steps.append(
            {
                "date": sent_date,
                "from": sender or "-",
                "to": _summarize_people(items=recipients) if recipients else "-",
            }
        )
    if not steps:
        return []
    ordered = list(reversed(steps))
    return ordered[-max(1, int(max_steps)) :]


def build_mail_route_compact_text(text: str, max_steps: int = 4) -> str:
    """
    단계별 발신/수신 흐름을 UI 전달용 문자열(`from=>to%%from=>to`)로 변환한다.

    Args:
        text: 메일 본문 원문
        max_steps: 최대 단계 수

    Returns:
        직렬화된 단계 문자열
    """
    steps = extract_mail_route_steps(text=text, max_steps=max_steps)
    if not steps:
        return ""
    serialized: list[str] = []
    for step in steps:
        base = f"{step['from']}=>{step['to']}"
        date_label = str(step.get("date") or "").strip()
        serialized.append(f"{date_label}::{base}" if date_label else base)
    return "%%".join(serialized)


def _normalize_route_step_date(value: str) -> str:
    """
    단계 헤더의 sent/date 문자열에서 표시용 날짜(YYYY-MM-DD)만 추출한다.

    Args:
        value: sent/date 원문 문자열

    Returns:
        정규화된 날짜 문자열. 추출 실패 시 빈 문자열
    """
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


def _decode_recipient_header_text(value: str) -> str:
    """
    수신자 헤더 원문을 디코딩/정리한다.

    Args:
        value: 헤더 원문

    Returns:
        디코딩/공백 정리된 문자열
    """
    decoded = html.unescape(str(value or ""))
    decoded = re.sub(r"\s+", " ", decoded)
    return decoded.strip()


def extract_person_name_or_email(value: str) -> str:
    """
    사람 식별 문자열에서 이름 우선 라벨을 추출한다(이름이 없으면 이메일 사용).

    Args:
        value: 발신자/수신자 원문 문자열

    Returns:
        표시용 사람 라벨
    """
    normalized = _normalize_recipient_entry(value=value)
    if not normalized:
        return ""
    matched = re.match(r"^(.*?)\s*<([^>]+)>$", normalized)
    if matched:
        name = str(matched.group(1) or "").strip()
        email = str(matched.group(2) or "").strip()
        return name or email
    return normalized


def _normalize_recipient_entry(value: str) -> str:
    """
    단일 수신자 문자열을 `이름 <email>` 또는 `email` 형태로 정규화한다.

    Args:
        value: 수신자 원문

    Returns:
        정규화된 수신자 문자열
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    email_match = EMAIL_ADDRESS_PATTERN.search(raw)
    if not email_match:
        return _normalize_recipient_name(value=raw)
    email = str(email_match.group(0) or "").strip()
    name_raw = raw.replace(email, " ")
    name = _normalize_recipient_name(value=name_raw)
    return f"{name} <{email}>" if name else email


def _normalize_recipient_name(value: str) -> str:
    """
    수신자 문자열에서 표시용 이름만 정제한다.

    Args:
        value: 이름/부서/태그 혼합 문자열

    Returns:
        정제된 이름
    """
    text = str(value or "")
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"/[^<>,;]+", " ", text)
    text = re.sub(r"^\s*(to|cc)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" ,;")


def _extract_header_route_blocks(text: str) -> list[dict[str, str]]:
    """
    본문에서 헤더 블록 단위(`From/To/...`)를 추출한다.

    Args:
        text: 메일 본문 원문

    Returns:
        헤더 블록 목록
    """
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
            field = _normalize_mail_header_field(str(matched.group(1) or ""))
            value = _decode_recipient_header_text(value=str(matched.group(2) or ""))
            if field == "from" and (current.get("from") or current.get("to")):
                blocks.append(dict(current))
                current = {}
            if field:
                current[field] = _append_header_value(base=current.get(field, ""), value=value)
                current_key = field
                continue
        if current_key in ("to", "cc") and _looks_like_header_continuation(line=line):
            current[current_key] = _append_header_value(base=current.get(current_key, ""), value=line)
            continue
        current_key = ""
    if current.get("from") or current.get("to"):
        blocks.append(dict(current))
    return blocks


def _normalize_mail_header_field(field: str) -> str:
    """
    헤더 필드명을 표준 키(`from/to/cc/sent/subject`)로 정규화한다.

    Args:
        field: 원본 헤더 필드명

    Returns:
        정규화된 키
    """
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


def _append_header_value(base: str, value: str) -> str:
    """
    헤더 필드의 다중 라인 값을 안전하게 이어 붙인다.

    Args:
        base: 기존 값
        value: 추가 값

    Returns:
        병합된 값
    """
    left = str(base or "").strip()
    right = str(value or "").strip()
    if not left:
        return right
    if not right:
        return left
    return f"{left}, {right}"


def _looks_like_header_continuation(line: str) -> bool:
    """
    헤더 줄의 줄바꿈 이어쓰기 후보인지 판단한다.

    Args:
        line: 검사 문자열

    Returns:
        이어쓰기 가능하면 True
    """
    text = str(line or "").strip()
    if not text:
        return False
    if MAIL_HEADER_LINE_PATTERN.match(text):
        return False
    return bool(EMAIL_ADDRESS_PATTERN.search(text) or "," in text or ";" in text)


def _normalize_recipient_list(value: str) -> list[str]:
    """
    수신자 헤더 문자열을 사람 표시 라벨 목록으로 정규화한다.

    Args:
        value: 원본 수신자 문자열

    Returns:
        이름/이메일 정규화 목록
    """
    decoded = _decode_recipient_header_text(value=value)
    if not decoded:
        return []
    parts = [item.strip() for item in re.split(r"[;,]", decoded) if item and item.strip()]
    labels: list[str] = []
    for part in parts:
        label = extract_person_name_or_email(value=part)
        if label and label not in labels:
            labels.append(label)
    return labels


def _summarize_people(items: list[str]) -> str:
    """
    사람 목록을 카드 표시용 요약 문자열로 변환한다.

    Args:
        items: 사람 라벨 목록

    Returns:
        요약 문자열
    """
    if not items:
        return "-"
    if len(items) <= 2:
        return ", ".join(items)
    return ", ".join(items[:2]) + f" 외 {len(items) - 2}명"


def extract_sender_display_name(from_address: str) -> str:
    """
    발신자 원문에서 표시용 이름(태그/주소 제거)을 추출한다.

    Args:
        from_address: 발신자 원문 문자열

    Returns:
        표시용 발신자 이름
    """
    raw = str(from_address or "").strip()
    if not raw:
        return "-"
    without_email = re.sub(r"<[^>]*>", " ", raw)
    without_slash_tag = re.sub(r"/[^\\s<>()]+", " ", without_email)
    collapsed = re.sub(r"\\s+", " ", without_slash_tag).strip()
    korean_match = re.search(r"[가-힣]{2,4}", collapsed)
    if korean_match:
        return korean_match.group(0)
    token = collapsed.split(" ")[0].strip()
    return token or "-"


def compose_report_markdown(
    mail: MailRecord,
    summary_lines: list[str],
    key_facts: list[str],
    recipients: list[str],
) -> str:
    """
    메일 분석 결과를 마크다운 보고서 문자열로 합성한다.

    Args:
        mail: 기준 메일 레코드
        summary_lines: 요약 라인 목록
        key_facts: 핵심 포인트 목록
        recipients: 수신자 목록

    Returns:
        마크다운 보고서 문자열
    """
    summary_block = "\n".join([f"- {line}" for line in summary_lines]) or "- 없음"
    facts_block = "\n".join([f"- {fact}" for fact in key_facts]) or "- 없음"
    recipients_block = "\n".join([f"- {recipient}" for recipient in recipients]) or "- 없음"
    return (
        f"## 메일 보고서\n"
        f"- 제목: {mail.subject}\n"
        f"- 발신자: {mail.from_address}\n"
        f"- 수신시각: {mail.received_date}\n\n"
        f"### 요약\n{summary_block}\n\n"
        f"### 중요 내용\n{facts_block}\n\n"
        f"### 수신자\n{recipients_block}"
    )
