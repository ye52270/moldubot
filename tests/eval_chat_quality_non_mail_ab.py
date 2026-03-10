from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from statistics import mean
from typing import Any
from urllib import error, request

from tests.fixtures.chat_quality_non_mail_cases import CHAT_QUALITY_NON_MAIL_CASES

logger = logging.getLogger(__name__)
DEFAULT_CHAT_URL = "http://127.0.0.1:8000/search/chat"

FAIL_PATTERNS = (
    "응답을 생성하지 못했습니다",
    "오류가 발생했습니다",
    "선택된 메일을 찾지 못했습니다",
)


@dataclass(frozen=True)
class EvalTarget:
    """A/B 평가 대상 서버 정의."""

    name: str
    chat_url: str


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _run_cases(chat_url: str) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    elapsed_list: list[float] = []

    for case in CHAT_QUALITY_NON_MAIL_CASES:
        payload = {"message": case["utterance"]}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            chat_url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )

        started_at = time.perf_counter()
        try:
            with request.urlopen(req, timeout=90) as resp:
                status_code = int(resp.getcode())
                data = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            elapsed_list.append(elapsed_ms)
            per_case.append(
                {
                    "case_id": case["case_id"],
                    "pattern": case["pattern"],
                    "utterance": case["utterance"],
                    "status_code": 0,
                    "elapsed_ms": elapsed_ms,
                    "success": False,
                    "source": "request-error",
                    "answer": "",
                    "error": str(exc),
                }
            )
            continue

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        elapsed_list.append(elapsed_ms)
        answer = str(data.get("answer") or "").strip()
        source = str(data.get("metadata", {}).get("source") or "")
        success = status_code == 200 and bool(answer)
        has_failure_pattern = any(pattern in answer for pattern in FAIL_PATTERNS)
        per_case.append(
            {
                "case_id": case["case_id"],
                "pattern": case["pattern"],
                "utterance": case["utterance"],
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "success": success,
                "source": source,
                "answer_length": len(answer),
                "has_failure_pattern": has_failure_pattern,
                "answer": answer,
            }
        )

    total = len(per_case)
    success_count = sum(1 for item in per_case if item.get("success"))
    failure_pattern_count = sum(1 for item in per_case if item.get("has_failure_pattern"))
    avg_answer_length = mean([int(item.get("answer_length") or 0) for item in per_case]) if per_case else 0.0

    return {
        "summary": {
            "total": total,
            "success_count": success_count,
            "success_rate": round((success_count / total) * 100, 1) if total else 0.0,
            "avg_elapsed_ms": round(mean(elapsed_list), 1) if elapsed_list else 0.0,
            "max_elapsed_ms": max(elapsed_list) if elapsed_list else 0.0,
            "min_elapsed_ms": min(elapsed_list) if elapsed_list else 0.0,
            "avg_answer_length": round(avg_answer_length, 1),
            "failure_pattern_rate": round((failure_pattern_count / total) * 100, 1) if total else 0.0,
        },
        "cases": per_case,
    }


def build_ab_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    base = baseline.get("summary", {}) if isinstance(baseline, dict) else {}
    cand = candidate.get("summary", {}) if isinstance(candidate, dict) else {}
    return {
        "delta_success_rate": round(_to_float(cand.get("success_rate")) - _to_float(base.get("success_rate")), 1),
        "delta_avg_elapsed_ms": round(_to_float(cand.get("avg_elapsed_ms")) - _to_float(base.get("avg_elapsed_ms")), 1),
        "delta_avg_answer_length": round(
            _to_float(cand.get("avg_answer_length")) - _to_float(base.get("avg_answer_length")),
            1,
        ),
        "delta_failure_pattern_rate": round(
            _to_float(cand.get("failure_pattern_rate")) - _to_float(base.get("failure_pattern_rate")),
            1,
        ),
    }


def run_non_mail_ab(baseline_target: EvalTarget, candidate_target: EvalTarget) -> dict[str, Any]:
    baseline_result = _run_cases(chat_url=baseline_target.chat_url)
    candidate_result = _run_cases(chat_url=candidate_target.chat_url)
    delta = build_ab_delta(baseline=baseline_result, candidate=candidate_result)
    return {
        "baseline": {
            "name": baseline_target.name,
            "chat_url": baseline_target.chat_url,
            **baseline_result,
        },
        "candidate": {
            "name": candidate_target.name,
            "chat_url": candidate_target.chat_url,
            **candidate_result,
        },
        "delta": delta,
    }


def _load_targets_from_env() -> tuple[EvalTarget, EvalTarget]:
    baseline_url = str(os.getenv("MOLDUBOT_CHAT_URL_BASELINE", DEFAULT_CHAT_URL)).strip() or DEFAULT_CHAT_URL
    candidate_url = str(os.getenv("MOLDUBOT_CHAT_URL_CANDIDATE", DEFAULT_CHAT_URL)).strip() or DEFAULT_CHAT_URL
    baseline_name = str(os.getenv("MOLDUBOT_CHAT_NAME_BASELINE", "baseline")).strip() or "baseline"
    candidate_name = str(os.getenv("MOLDUBOT_CHAT_NAME_CANDIDATE", "candidate")).strip() or "candidate"
    return EvalTarget(name=baseline_name, chat_url=baseline_url), EvalTarget(
        name=candidate_name,
        chat_url=candidate_url,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    baseline, candidate = _load_targets_from_env()
    result = run_non_mail_ab(baseline_target=baseline, candidate_target=candidate)
    logger.info("chat_quality_non_mail_ab=%s", json.dumps(result, ensure_ascii=False, indent=2))
