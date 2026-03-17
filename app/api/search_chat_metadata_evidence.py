from __future__ import annotations

import re
from typing import Any

from app.services.text_overlap_utils import extract_overlap_tokens, normalize_compare_text, token_overlap_score


def build_major_point_evidence(
    answer_format: dict[str, Any],
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    주요 내용 항목별 근거(메일 문구/단락)를 구성한다.
    """
    major_points = _extract_major_points_from_answer_format(answer_format=answer_format)
    if not major_points:
        return []
    source_text = _resolve_mail_source_text(tool_payload=tool_payload)
    sentence_candidates = _split_sentences(text=source_text)
    paragraph_candidates = _split_paragraphs(text=source_text)
    normalized_items: list[dict[str, Any]] = []
    for point in major_points[:6]:
        quote, location = _find_best_mail_evidence(
            point=point,
            sentence_candidates=sentence_candidates,
            paragraph_candidates=paragraph_candidates,
        )
        point_evidence: dict[str, Any] = {
            "point": point,
            "mail_quote": quote,
            "mail_location": location,
            "mail_subject": str(evidence_mails[0].get("subject") or "").strip() if evidence_mails else "",
            "related_mails": [],
        }
        normalized_items.append(point_evidence)
    return normalized_items


def _extract_major_points_from_answer_format(answer_format: dict[str, Any]) -> list[str]:
    if not isinstance(answer_format, dict):
        return []
    blocks = answer_format.get("blocks")
    if not isinstance(blocks, list):
        return []
    collecting = False
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type == "heading":
            heading = normalize_compare_text(text=str(block.get("text") or ""))
            collecting = "주요내용" in heading
            continue
        if not collecting:
            continue
        if block_type not in {"ordered_list", "unordered_list"}:
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            text = str(item or "").strip()
            if text:
                lines.append(text)
    return lines


def _resolve_mail_source_text(tool_payload: dict[str, Any]) -> str:
    if not isinstance(tool_payload, dict):
        return ""
    context = tool_payload.get("mail_context")
    if not isinstance(context, dict):
        return ""
    parts = [
        str(context.get("summary_text") or "").strip(),
        str(context.get("body_excerpt") or "").strip(),
        str(context.get("body_preview") or "").strip(),
    ]
    return _clean_mail_text(text="\n".join([part for part in parts if part]))


def _clean_mail_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _split_sentences(text: str) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    fragments = re.split(r"(?<=[.!?。])\s+|(?<=다)\.\s+|;\s+", source)
    sentences = [str(item or "").strip() for item in fragments if str(item or "").strip()]
    return [item for item in sentences if len(item) >= 12][:80]


def _split_paragraphs(text: str) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    raw_parts = re.split(r"\n{2,}|(?<=\.)\s{2,}", source)
    parts = [str(item or "").strip() for item in raw_parts if str(item or "").strip()]
    return [item for item in parts if len(item) >= 24][:40]


def _find_best_mail_evidence(
    point: str,
    sentence_candidates: list[str],
    paragraph_candidates: list[str],
) -> tuple[str, str]:
    point_tokens = set(extract_overlap_tokens(text=point))
    if not point_tokens:
        return "", ""
    best_sentence = ""
    best_score = 0.0
    for sentence in sentence_candidates:
        score = token_overlap_score(point_tokens=point_tokens, candidate=sentence)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    if best_score < 0.12 and sentence_candidates:
        best_sentence = sentence_candidates[0]
    location = _resolve_paragraph_location(sentence=best_sentence, paragraphs=paragraph_candidates)
    return best_sentence[:180], location


def _resolve_paragraph_location(sentence: str, paragraphs: list[str]) -> str:
    target = str(sentence or "").strip()
    if not target:
        return ""
    for index, paragraph in enumerate(paragraphs, start=1):
        if target in paragraph:
            return f"본문 {index}단락"
    return "본문 근거 문장"
