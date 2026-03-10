from __future__ import annotations

from app.models.response_contracts import LLMResponseContract


def build_semantic_answer_contract(
    contract: LLMResponseContract | None,
    answer: str,
    intent_confidence: float,
    evidence_mails: list[dict[str, str]],
    web_sources: list[dict[str, str]],
) -> dict[str, object]:
    """
    도메인 공통 의미 계약(claim/evidence/action/confidence)을 생성한다.

    Args:
        contract: 파싱된 LLM 응답 계약
        answer: 최종 답변 텍스트
        intent_confidence: 의도 confidence(0~1)
        evidence_mails: 내부 메일 근거 목록
        web_sources: 외부 웹 근거 목록

    Returns:
        공통 의미 계약 사전
    """
    claim_items = _resolve_claim_items(contract=contract, answer=answer)
    action_items = _resolve_action_items(contract=contract)
    evidence_items = _resolve_evidence_items(evidence_mails=evidence_mails, web_sources=web_sources)
    return {
        "claims": claim_items[:5],
        "evidence": evidence_items[:6],
        "actions": action_items[:5],
        "confidence": round(_resolve_confidence(intent_confidence=intent_confidence, contract=contract), 2),
    }


def _resolve_claim_items(contract: LLMResponseContract | None, answer: str) -> list[str]:
    """
    주장(claim) 목록을 추출한다.

    Args:
        contract: 파싱된 계약
        answer: 텍스트 답변

    Returns:
        주장 목록
    """
    if contract is None:
        return _split_lines(text=answer)[:3]
    candidates = [
        str(contract.core_issue or "").strip(),
        *[str(item or "").strip() for item in contract.summary_lines],
        *[str(item or "").strip() for item in contract.major_points],
        *[str(item or "").strip() for item in contract.key_points],
    ]
    return _dedupe_non_empty(candidates)


def _resolve_action_items(contract: LLMResponseContract | None) -> list[str]:
    """
    조치(action) 목록을 추출한다.

    Args:
        contract: 파싱된 계약

    Returns:
        조치 목록
    """
    if contract is None:
        return []
    candidates = [
        *[str(item or "").strip() for item in contract.required_actions],
        *[str(item or "").strip() for item in contract.action_items],
    ]
    return _dedupe_non_empty(candidates)


def _resolve_evidence_items(
    evidence_mails: list[dict[str, str]],
    web_sources: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    근거(evidence) 목록을 직렬화한다.

    Args:
        evidence_mails: 메일 근거 목록
        web_sources: 웹 출처 목록

    Returns:
        근거 메타 목록
    """
    rows: list[dict[str, str]] = []
    for item in evidence_mails:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "type": "mail",
                "title": str(item.get("subject") or "").strip(),
                "source": str(item.get("sender_names") or "").strip(),
                "link": str(item.get("web_link") or "").strip(),
            }
        )
    for item in web_sources:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "type": "web",
                "title": str(item.get("title") or "").strip(),
                "source": str(item.get("site_name") or "").strip(),
                "link": str(item.get("url") or "").strip(),
            }
        )
    return [row for row in rows if any(str(value or "").strip() for value in row.values())]


def _resolve_confidence(intent_confidence: float, contract: LLMResponseContract | None) -> float:
    """
    공통 계약 confidence를 계산한다.

    Args:
        intent_confidence: 의도 confidence
        contract: 파싱된 계약

    Returns:
        confidence 값(0~1)
    """
    base = max(0.0, min(1.0, float(intent_confidence)))
    if contract is None:
        return max(base - 0.1, 0.0)
    claim_count = len(_resolve_claim_items(contract=contract, answer=""))
    action_count = len(_resolve_action_items(contract=contract))
    coverage_bonus = 0.05 if claim_count >= 2 else 0.0
    action_bonus = 0.03 if action_count >= 1 else 0.0
    return min(1.0, base + coverage_bonus + action_bonus)


def _split_lines(text: str) -> list[str]:
    """
    텍스트를 줄 단위로 분리한다.

    Args:
        text: 원본 텍스트

    Returns:
        정제된 줄 목록
    """
    normalized = str(text or "").strip()
    if not normalized:
        return []
    lines = [line.strip("-• \t") for line in normalized.splitlines()]
    return [line for line in lines if line]


def _dedupe_non_empty(values: list[str]) -> list[str]:
    """
    문자열 목록을 공백/중복 제거한다.

    Args:
        values: 원본 문자열 목록

    Returns:
        정제된 문자열 목록
    """
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in deduped:
            continue
        deduped.append(text)
    return deduped
