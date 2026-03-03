from __future__ import annotations

import unittest
from datetime import date

from app.core.date_resolver import resolve_booking_date_token


class DateResolverTest(unittest.TestCase):
    """
    예약 날짜 정규화 유틸 동작을 검증한다.
    """

    def test_resolve_tomorrow_token(self) -> None:
        """
        `내일` 토큰은 기준일 +1일로 변환되어야 한다.
        """
        result = resolve_booking_date_token(raw_date="내일", reference_date=date(2026, 2, 28))
        self.assertEqual("2026-03-01", result)

    def test_resolve_this_week_weekday_token(self) -> None:
        """
        `이번주 금요일`은 기준 주의 금요일 날짜로 변환되어야 한다.
        """
        result = resolve_booking_date_token(raw_date="이번주 금요일", reference_date=date(2026, 2, 25))
        self.assertEqual("2026-02-27", result)

    def test_normalize_iso_date(self) -> None:
        """
        ISO 날짜 입력은 0 패딩된 YYYY-MM-DD 형식으로 정규화되어야 한다.
        """
        result = resolve_booking_date_token(raw_date="2026-2-3", reference_date=date(2026, 2, 25))
        self.assertEqual("2026-02-03", result)

    def test_resolve_day_after_tomorrow_token(self) -> None:
        """
        `모레` 토큰은 기준일 +2일로 변환되어야 한다.
        """
        result = resolve_booking_date_token(raw_date="모레", reference_date=date(2026, 2, 28))
        self.assertEqual("2026-03-02", result)

    def test_resolve_next_week_weekday_token(self) -> None:
        """
        `다음주 화요일`은 다음 주 화요일로 변환되어야 한다.
        """
        result = resolve_booking_date_token(raw_date="다음주 화요일", reference_date=date(2026, 2, 25))
        self.assertEqual("2026-03-03", result)


if __name__ == "__main__":
    unittest.main()
