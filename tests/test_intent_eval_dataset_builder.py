from __future__ import annotations

import unittest
from pathlib import Path

from app.services.intent_eval_dataset_builder import build_intent_eval_dataset


class IntentEvalDatasetBuilderTest(unittest.TestCase):
    """
    intent 평가 데이터셋 생성기의 건수/구성 규칙을 검증한다.
    """

    def test_build_dataset_generates_at_least_200_cases(self) -> None:
        """
        로그 기반 생성 결과는 최소 200건 이상이어야 한다.
        """
        root_dir = Path(__file__).resolve().parents[1]
        log_path = root_dir / "data" / "mock" / "client_logs.ndjson"
        dataset = build_intent_eval_dataset(log_path=log_path, target_count=220)
        cases = dataset.get("cases", [])
        self.assertGreaterEqual(len(cases), 200)

    def test_build_dataset_contains_multiple_query_types(self) -> None:
        """
        생성 결과는 current_mail/mail_search/general query_type을 포함해야 한다.
        """
        root_dir = Path(__file__).resolve().parents[1]
        log_path = root_dir / "data" / "mock" / "client_logs.ndjson"
        dataset = build_intent_eval_dataset(log_path=log_path, target_count=220)
        types = {str(item.get("query_type")) for item in dataset.get("cases", [])}
        self.assertIn("current_mail", types)
        self.assertIn("mail_search", types)
        self.assertIn("general", types)


if __name__ == "__main__":
    unittest.main()
