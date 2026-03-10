from __future__ import annotations

from pathlib import Path

from app.services.intent_eval_dataset_builder import (
    DEFAULT_TARGET_CASE_COUNT,
    build_intent_eval_dataset,
    save_intent_eval_dataset,
)


def main() -> None:
    """
    intent 평가 데이터셋(200+)을 생성해 fixture JSON으로 저장한다.
    """
    root_dir = Path(__file__).resolve().parents[1]
    log_path = root_dir / "data" / "mock" / "client_logs.ndjson"
    output_path = root_dir / "tests" / "fixtures" / "intent_eval_cases_200.json"
    dataset = build_intent_eval_dataset(
        log_path=log_path,
        target_count=DEFAULT_TARGET_CASE_COUNT,
    )
    save_intent_eval_dataset(output_path=output_path, dataset=dataset)
    generated = int(dataset.get("meta", {}).get("generated_count", 0))
    print(f"generated_intent_eval_cases={generated}")


if __name__ == "__main__":
    main()
