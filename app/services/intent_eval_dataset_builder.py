from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TARGET_CASE_COUNT = 220
DEFAULT_QUERY_TYPE = "current_mail"
QUERY_TYPE_WEIGHT_KEYS = ("current_mail", "mail_search", "general")


def build_intent_eval_dataset(
    log_path: Path,
    target_count: int = DEFAULT_TARGET_CASE_COUNT,
) -> dict[str, Any]:
    """
    client 로그 분포를 반영해 intent 평가용 질의 데이터셋을 생성한다.

    Args:
        log_path: client 로그 ndjson 경로
        target_count: 생성할 최소 질의 수

    Returns:
        메타데이터와 질의 목록을 포함한 데이터셋 사전
    """
    query_type_counts = _collect_query_type_counts(log_path=log_path)
    weighted_types = _expand_weighted_query_types(
        query_type_counts=query_type_counts,
        target_count=max(1, target_count),
    )
    utterance_pool = _build_utterance_pool()
    pool_index: dict[str, int] = {key: 0 for key in utterance_pool.keys()}
    cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for query_type in weighted_types:
        candidates = utterance_pool.get(query_type) or utterance_pool[DEFAULT_QUERY_TYPE]
        selected = _pop_next_candidate(
            query_type=query_type,
            candidates=candidates,
            pool_index=pool_index,
            seen=seen,
        )
        if selected:
            cases.append(
                {
                    "case_id": f"intent_eval_{len(cases) + 1:03d}",
                    "query_type": query_type,
                    "utterance": selected,
                    "source": "log_weighted_template",
                }
            )
        if len(cases) >= target_count:
            break

    if len(cases) < target_count:
        _append_fallback_cases(cases=cases, seen=seen, target_count=target_count, utterance_pool=utterance_pool)

    return {
        "meta": {
            "target_count": target_count,
            "generated_count": len(cases),
            "query_type_counts": query_type_counts,
            "query_type_weights": _normalize_query_type_weights(query_type_counts=query_type_counts),
        },
        "cases": cases,
    }


def save_intent_eval_dataset(output_path: Path, dataset: dict[str, Any]) -> None:
    """
    intent 평가 데이터셋을 JSON 파일로 저장한다.

    Args:
        output_path: 저장 경로
        dataset: 저장할 데이터셋 사전
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")


def _collect_query_type_counts(log_path: Path) -> dict[str, int]:
    """
    client ndjson 로그에서 query_type 이벤트 빈도를 집계한다.

    Args:
        log_path: client 로그 경로

    Returns:
        query_type별 빈도 사전
    """
    counts = {key: 0 for key in QUERY_TYPE_WEIGHT_KEYS}
    if not log_path.exists():
        counts[DEFAULT_QUERY_TYPE] = 1
        return counts

    with log_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            event = str(payload.get("event") or "")
            nested_payload = payload.get("payload")
            if event not in ("selection_context_before_send", "selection_context_effective_send"):
                continue
            if not isinstance(nested_payload, dict):
                continue
            query_type = str(nested_payload.get("query_type") or "").strip().lower()
            if query_type == "current_mail":
                counts["current_mail"] += 1
            elif query_type in ("mail_search", "search"):
                counts["mail_search"] += 1
            elif query_type:
                counts["general"] += 1

    if sum(counts.values()) == 0:
        counts[DEFAULT_QUERY_TYPE] = 1
    return counts


def _normalize_query_type_weights(query_type_counts: dict[str, int]) -> dict[str, float]:
    """
    query_type 집계값을 정규화한 비율로 변환한다.

    Args:
        query_type_counts: query_type별 빈도 사전

    Returns:
        query_type별 비율(합계 1.0) 사전
    """
    total = sum(max(0, int(value)) for value in query_type_counts.values())
    if total <= 0:
        return {DEFAULT_QUERY_TYPE: 1.0}
    return {
        key: round(max(0, int(value)) / total, 4)
        for key, value in query_type_counts.items()
    }


def _expand_weighted_query_types(query_type_counts: dict[str, int], target_count: int) -> list[str]:
    """
    query_type 비율에 따라 목표 건수만큼 query_type 시퀀스를 확장한다.

    Args:
        query_type_counts: query_type 빈도 사전
        target_count: 생성 목표 건수

    Returns:
        목표 건수 길이의 query_type 목록
    """
    weights = _normalize_query_type_weights(query_type_counts=query_type_counts)
    quotas: dict[str, int] = {}
    for key in QUERY_TYPE_WEIGHT_KEYS:
        ratio = float(weights.get(key, 0.0))
        quotas[key] = max(1, int(round(target_count * ratio)))
    result: list[str] = []
    while len(result) < target_count and any(value > 0 for value in quotas.values()):
        for key in QUERY_TYPE_WEIGHT_KEYS:
            remaining = quotas.get(key, 0)
            if remaining <= 0:
                continue
            result.append(key)
            quotas[key] = remaining - 1
            if len(result) >= target_count:
                break
    while len(result) < target_count:
        result.append(DEFAULT_QUERY_TYPE)
    return result


def _build_utterance_pool() -> dict[str, list[str]]:
    """
    query_type별 템플릿 기반 질의 풀을 생성한다.

    Returns:
        query_type별 질의 후보 목록
    """
    current_mail_bases = [
        "현재메일 요약해줘",
        "현재메일 상세히 요약해줘",
        "현재메일 3줄 요약해줘",
        "현재메일에서 비용이 왜 문제인지 분석해줘",
        "현재메일에서 기술 이슈 때문에 일정이 밀리는 이유 알려줘",
        "현재메일 SSL 인증서 이슈 해결 방법 알려줘",
        "현재메일 수신자 분석해서 역할 표로 정리해줘",
        "현재메일 핵심 문제와 해야 할 일을 분리해줘",
    ]
    mail_search_bases = [
        "지난주 M365 관련 메일 조회해줘",
        "최근 2주 보안 이슈 메일 검색해줘",
        "1월 조영득 관련 메일 찾아서 요약해줘",
        "본문에 SSL 인증서 포함된 메일 찾아줘",
        "지난달 일정 변경 메일 정리해줘",
    ]
    general_bases = [
        "회의실 예약 절차 알려줘",
        "비용정산 핵심 규정 3개로 정리해줘",
        "이번주 할 일 우선순위 정리해줘",
        "팀 보고용 한 단락 문장으로 써줘",
    ]
    modifiers = [
        "",
        " 빠르게",
        " 정확하게",
        " 근거 포함해서",
        " 간단히",
    ]
    endings = ["", " 부탁해", " 해줘", " 해주세요"]
    return {
        "current_mail": _expand_templates(current_mail_bases, modifiers, endings),
        "mail_search": _expand_templates(mail_search_bases, modifiers, endings),
        "general": _expand_templates(general_bases, modifiers, endings),
    }


def _expand_templates(bases: list[str], modifiers: list[str], endings: list[str]) -> list[str]:
    """
    기본 질의 템플릿에 수식어/어미를 조합해 확장 목록을 생성한다.

    Args:
        bases: 기본 질의 목록
        modifiers: 수식어 목록
        endings: 어미 목록

    Returns:
        중복 제거된 확장 질의 목록
    """
    expanded: list[str] = []
    for base in bases:
        for modifier in modifiers:
            for ending in endings:
                utterance = f"{base}{modifier}{ending}".strip()
                if utterance and utterance not in expanded:
                    expanded.append(utterance)
    return expanded


def _append_fallback_cases(
    cases: list[dict[str, str]],
    seen: set[str],
    target_count: int,
    utterance_pool: dict[str, list[str]],
) -> None:
    """
    목표 건수 미달 시 순환 방식으로 fallback 질의를 추가한다.

    Args:
        cases: 현재 케이스 목록
        seen: 중복 제거 집합
        target_count: 목표 건수
        utterance_pool: query_type별 질의 풀
    """
    all_candidates = (
        utterance_pool.get("current_mail", [])
        + utterance_pool.get("mail_search", [])
        + utterance_pool.get("general", [])
    )
    index = 0
    while len(cases) < target_count and all_candidates:
        candidate = all_candidates[index % len(all_candidates)]
        index += 1
        synthetic = f"{candidate} #{index}"
        if synthetic in seen:
            continue
        seen.add(synthetic)
        cases.append(
            {
                "case_id": f"intent_eval_{len(cases) + 1:03d}",
                "query_type": DEFAULT_QUERY_TYPE,
                "utterance": synthetic,
                "source": "fallback_template",
            }
        )


def _pop_next_candidate(
    query_type: str,
    candidates: list[str],
    pool_index: dict[str, int],
    seen: set[str],
) -> str:
    """
    query_type별 후보 목록에서 중복되지 않는 다음 질의를 1건 선택한다.

    Args:
        query_type: query_type 키
        candidates: 후보 질의 목록
        pool_index: query_type별 현재 인덱스
        seen: 중복 제거 집합

    Returns:
        선택된 질의 문자열. 없으면 빈 문자열
    """
    if not candidates:
        return ""
    cursor = int(pool_index.get(query_type, 0))
    attempts = 0
    while attempts < len(candidates):
        candidate = str(candidates[cursor % len(candidates)]).strip()
        cursor += 1
        attempts += 1
        if not candidate or candidate in seen:
            continue
        pool_index[query_type] = cursor % len(candidates)
        seen.add(candidate)
        return candidate
    return ""
