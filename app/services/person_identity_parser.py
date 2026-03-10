from __future__ import annotations

import html
import re

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KOREAN_NAME_PATTERN = re.compile(r"[가-힣]{2,4}")
ENGLISH_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z\s.'-]{1,40}")
ARTIFACT_TOKENS = {"lt", "gt", "amp", "quot", "nbsp"}


def normalize_person_identity(token: str) -> str:
    """인물 토큰에서 표시용 식별자(이름 우선, 없으면 이메일)를 추출한다.

    Args:
        token: 원본 인물 토큰

    Returns:
        정규화된 인물 문자열. 유효 값이 없으면 빈 문자열
    """
    raw = _normalize_raw_text(token=token)
    if not raw:
        return ""
    name = _extract_name(raw=raw)
    if name:
        return name
    email = _extract_email(raw=raw)
    if email:
        return email
    cleaned = _strip_noise(text=raw)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered in ARTIFACT_TOKENS:
        return ""
    return cleaned


def _normalize_raw_text(token: str) -> str:
    """HTML escape와 공백을 정리한 원문을 반환한다.

    Args:
        token: 원본 토큰

    Returns:
        정규화된 원문 문자열
    """
    unescaped = html.unescape(str(token or "")).strip().strip("\"'")
    if not unescaped:
        return ""
    normalized = re.sub(r"\s+", " ", unescaped)
    return normalized.strip()


def _extract_name(raw: str) -> str:
    """원문에서 이름 후보를 추출한다.

    Args:
        raw: 정규화 원문

    Returns:
        이름 문자열. 없으면 빈 문자열
    """
    head = _extract_head_text(raw=raw)
    korean = KOREAN_NAME_PATTERN.findall(head)
    if korean:
        return korean[0]
    english = ENGLISH_NAME_PATTERN.search(head)
    if english:
        return _strip_noise(text=english.group(0))
    return ""


def _extract_head_text(raw: str) -> str:
    """주소/조직 정보 이전의 이름 영역 텍스트를 반환한다.

    Args:
        raw: 정규화 원문

    Returns:
        이름 후보 영역 텍스트
    """
    without_email = EMAIL_PATTERN.sub(" ", raw)
    primary = without_email.split("<", maxsplit=1)[0]
    primary = primary.split("/", maxsplit=1)[0]
    primary = re.sub(r"\([^)]*\)", " ", primary)
    primary = re.sub(r"[<>]", " ", primary)
    return _strip_noise(text=primary)


def _extract_email(raw: str) -> str:
    """원문에서 첫 이메일 주소를 추출한다.

    Args:
        raw: 정규화 원문

    Returns:
        이메일 주소. 없으면 빈 문자열
    """
    matched = EMAIL_PATTERN.search(raw)
    if not matched:
        return ""
    return str(matched.group(0) or "").strip().lower()


def _strip_noise(text: str) -> str:
    """토큰 양끝의 불필요 문자를 제거한다.

    Args:
        text: 원본 문자열

    Returns:
        정리된 문자열
    """
    compact = str(text or "").strip()
    compact = compact.strip("<>()[]{}:;,.|/")
    compact = re.sub(r"\s+", " ", compact)
    return compact.strip()
