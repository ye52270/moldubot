from __future__ import annotations

import re


def normalize_action_item_line(text: str) -> str:
    """
    액션 아이템 라인의 반복 접두어/장식 문구를 정리한다.

    Args:
        text: 원본 라인

    Returns:
        정제된 라인
    """
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"^액션\s*아이템\s*[:：]\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^(확인\s*필요\s*[:：]\s*)+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -:")
    return normalized

