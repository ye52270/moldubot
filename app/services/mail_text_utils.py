from __future__ import annotations

import re

from app.services import mail_text_route_utils as _route_utils

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


def normalize_line_target(line_target: int) -> int:
    """요약 라인 목표값을 안전 범위(1~20)로 보정한다."""
    if line_target < 1:
        return 1
    if line_target > 20:
        return 20
    return line_target


def split_sentences(text: str) -> list[str]:
    """본문 문자열을 문장/행 단위로 분리한다."""
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
    """본문에서 요약 가치가 높은 문장을 우선 선별한다."""
    target = normalize_line_target(line_target=line_target)
    raw_sentences = split_sentences(text=text)
    unique_sentences = _dedupe_sentences(sentences=raw_sentences)
    filtered = [sentence for sentence in unique_sentences if not is_summary_noise_sentence(sentence=sentence)]
    if not filtered:
        filtered = [sentence for sentence in unique_sentences if sentence.strip()]
    scored = [(_score_summary_sentence(sentence=sentence), index, sentence) for index, sentence in enumerate(filtered)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [trim_sentence(sentence=item[2]) for item in scored[:target]]
    if len(selected) < target:
        remaining = [trim_sentence(sentence=item) for item in filtered if trim_sentence(sentence=item) not in selected]
        selected.extend(remaining[: target - len(selected)])
    return selected[:target]


def is_summary_noise_sentence(sentence: str) -> bool:
    """요약 품질을 떨어뜨리는 헤더/서명/상투 문장인지 판별한다."""
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
    """요약 문장 우선순위를 계산한다."""
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
    """문장 목록의 순서를 유지한 채 중복을 제거한다."""
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
    """문장을 최대 길이로 자른다."""
    text = sentence.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def extract_recipients_from_body(text: str) -> list[str]:
    """메일 본문 헤더 중 `To:` 구간에서 수신자 문자열을 파싱한다."""
    normalized = str(text or "").replace("\r", "\n")
    match = re.search(r"To:\s*(.+?)(?:Cc:|Subject:|From:|$)", normalized, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    raw = match.group(1).replace("\n", " ")
    decoded = _route_utils.decode_recipient_header_text(value=raw)
    parts = [item.strip() for item in re.split(r"[;,]", decoded) if item and item.strip()]
    deduped: list[str] = []
    for recipient in parts:
        normalized_recipient = _route_utils.normalize_recipient_entry(value=recipient)
        if normalized_recipient and normalized_recipient not in deduped:
            deduped.append(normalized_recipient)
    return deduped


def extract_mail_route_steps(text: str, max_steps: int = 4) -> list[dict[str, str]]:
    """메일 본문 헤더(`From:/To:`)를 분석해 단계별 발신자/수신자 흐름을 추출한다."""
    return _route_utils.extract_mail_route_steps(text=text, max_steps=max_steps)


def build_mail_route_compact_text(text: str, max_steps: int = 4) -> str:
    """단계별 발신/수신 흐름을 UI 전달용 문자열(`from=>to%%from=>to`)로 변환한다."""
    return _route_utils.build_mail_route_compact_text(text=text, max_steps=max_steps)


def extract_person_name_or_email(value: str) -> str:
    """사람 식별 문자열에서 이름 우선 라벨을 추출한다(이름이 없으면 이메일 사용)."""
    return _route_utils.extract_person_name_or_email(value=value)


def extract_sender_display_name(from_address: str) -> str:
    """발신자 원문에서 표시용 이름(태그/주소 제거)을 추출한다."""
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
