from __future__ import annotations

import json
from pathlib import Path

from app.services.routing_quality_gate import evaluate_routing_quality_gate
from tests.eval_chat_quality_cases import run_chat_quality_cases
from tests.eval_intent_complex_cases import evaluate_intent_complex_cases


def run_routing_quality_gate() -> dict[str, object]:
    """
    intent/chat 평가를 실행하고 KPI 기준선 회귀 게이트를 판정한다.

    Returns:
        게이트 판정 결과 사전
    """
    intent_result = evaluate_intent_complex_cases()
    chat_result = run_chat_quality_cases()
    gate = evaluate_routing_quality_gate(
        intent_summary=intent_result.get("summary", {}),
        chat_summary=chat_result.get("summary", {}),
    )
    return {
        "intent_summary": intent_result.get("summary", {}),
        "chat_summary": chat_result.get("summary", {}),
        "gate": gate,
    }


if __name__ == "__main__":
    result = run_routing_quality_gate()
    output_path = Path("data/reports/chat_eval_latest_gate.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result.get("gate", {}), ensure_ascii=False))
