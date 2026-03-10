from __future__ import annotations

import re

from app.services.answer_postprocessor_summary_utils import looks_like_org_signature


def is_section_header_line(line: str) -> bool:
    """
    요약 본문이 아닌 섹션 헤더 라인인지 판별한다.

    Args:
        line: 검사할 단일 라인 문자열

    Returns:
        헤더 성격 라인이면 True
    """
    text = str(line or "").strip().strip(":")
    if not text:
        return True
    return text in ("요약", "메일 요약", "요약 결과")


def is_meta_summary_line(line: str) -> bool:
    """
    요약 본문이 아닌 메타 안내 문장인지 판별한다.

    Args:
        line: 검사할 단일 라인 문자열

    Returns:
        메타 안내 문장이면 True
    """
    text = str(line or "").strip()
    if not text:
        return True

    meta_patterns = (
        r"요약(한|했)습니다",
        r"요약.*다음과 같습니다",
        r"\d+줄로 요약",
        r"메일.*요약",
    )
    return any(re.search(pattern, text) for pattern in meta_patterns)


def is_header_like_line(line: str) -> bool:
    """
    이메일 헤더 메타데이터 성격 라인(From/Sent/To 등)인지 판별한다.

    Args:
        line: 검사할 라인

    Returns:
        헤더성 라인이면 True
    """
    text = str(line or "").strip()
    if not text:
        return True
    header_patterns = (
        r"^(from|sent|to|cc|bcc|subject|date)\s*:",
        r"^(발신자|수신자|참조|숨은참조|제목|날짜)\s*:",
        r"^메일\s*(id|ID)\s*:",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in header_patterns):
        return True
    mixed_header_count = 0
    for token in ("From:", "Sent:", "To:", "Cc:", "Subject:"):
        if token.lower() in text.lower():
            mixed_header_count += 1
    return mixed_header_count >= 2


def is_signature_noise_line(line: str) -> bool:
    """
    서명/연락처 등 요약 품질을 떨어뜨리는 노이즈 라인인지 판별한다.

    Args:
        line: 검사할 라인

    Returns:
        노이즈 라인이면 True
    """
    text = str(line or "").strip()
    if not text:
        return True
    noise_patterns = (
        r"^\d{2,3}-\d{3,4}-\d{4}$",
        r"^\+?\d{2,3}\s*\d{2,4}\s*\d{3,4}\s*\d{4}$",
        r"^(감사합니다|고맙습니다|잘 부탁드립니다|문의 부탁드립니다)\.?$",
        r"^[가-힣A-Za-z\s]+드림\.?$",
        r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
        r"^(연락처|contact)\s*[:：]?\s*\d",
    )
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in noise_patterns):
        return True
    if len(text) <= 12 and re.search(r"\d{7,}", text.replace("-", "").replace(" ", "")):
        return True
    return False


def is_low_value_summary_line(line: str) -> bool:
    """
    의미 밀도가 낮은 상투/안내성 문장을 요약 후보에서 제외한다.

    Args:
        line: 검사할 라인

    Returns:
        저가치 문장이면 True
    """
    text = str(line or "").strip()
    if not text:
        return True
    normalized = re.sub(r"\s+", " ", text)
    low_value_patterns = (
        r"^확인 부탁드립니다\.?$",
        r"^확인 필요(합니다)?\.?$",
        r"^추가 확인 부탁드립니다\.?$",
        r"^검토 부탁드립니다\.?$",
        r"^감사합니다\.?$",
        r"^감사드립니다\.?$",
        r"^국가과학기술연구회 .+입니다\.?$",
        r"^유선상 문의 드렸던 내용(을)? 메일로 재문의 드립니다\.?$",
        r"^문의 드립니다\.?$",
    )
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in low_value_patterns):
        return True

    is_short_intro = (
        len(normalized) <= 28
        and normalized.endswith("입니다.")
        and not any(
            keyword in normalized
            for keyword in ("문제", "요청", "확인", "차단", "수신", "발송", "조치", "검토", "회신", "이력")
        )
    )
    if is_short_intro:
        return True
    if looks_like_org_signature(text=normalized):
        return True
    return False

