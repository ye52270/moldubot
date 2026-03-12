from __future__ import annotations

import re

_INTENT_BLOB_MARKERS: tuple[str, ...] = (
    "original_query",
    "steps",
    "task_type",
    "output_format",
    "focus_topics",
)


def sanitize_visible_answer_text(text: str) -> str:
    """
    사용자에게 노출할 답변 앞에 붙은 의도 JSON/blob 프리픽스를 제거한다.

    Args:
        text: 모델 원문 또는 후처리된 답변 텍스트

    Returns:
        프리픽스 제거 후 텍스트
    """
    source = str(text or "")
    if not source:
        return ""
    left_trimmed = source.lstrip()
    if not left_trimmed.startswith("{"):
        return source

    lowered = left_trimmed.lower()
    marker_hits = sum(1 for marker in _INTENT_BLOB_MARKERS if marker in lowered)
    if "original_query" not in lowered or marker_hits < 3:
        return source

    closing_index = left_trimmed.find("}")
    if 0 <= closing_index <= 2000:
        tail = left_trimmed[closing_index + 1 :].lstrip()
        return tail if tail else ""

    for pattern in (
        r"llm_fresh[\"'}\]\s]*",
        r"confidence[\"':\s0-9\.\-]*[,}\]]*\s*",
    ):
        matched = re.search(pattern, lowered)
        if matched is None:
            continue
        tail = left_trimmed[matched.end() :].lstrip()
        return tail if tail else ""
    return source


def iter_answer_stream_chunks(text: str) -> list[str]:
    """
    최종 답변을 UI 점진 렌더용 토큰 청크 목록으로 분해한다.

    Args:
        text: 최종 사용자 노출 답변

    Returns:
        공백을 보존한 청크 문자열 목록
    """
    source = str(text or "")
    if not source:
        return []
    chunks = re.findall(r"\S+\s*", source)
    if chunks:
        return chunks
    return [source]
