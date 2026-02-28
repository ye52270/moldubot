from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


MAX_LATENCY_SAMPLES = 1000


@dataclass
class ChatMetricsState:
    """
    채팅 경로 운영 메트릭 누적 상태를 보관한다.

    Attributes:
        total_requests: 전체 요청 수
        success_requests: 성공 처리 요청 수
        failure_requests: 실패 처리 요청 수
        fallback_responses: fallback 응답 수
        source_counter: source별 건수 카운터
        latency_samples_ms: 최근 지연 시간 샘플(ms)
    """

    total_requests: int = 0
    success_requests: int = 0
    failure_requests: int = 0
    fallback_responses: int = 0
    source_counter: Counter[str] = field(default_factory=Counter)
    latency_samples_ms: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_LATENCY_SAMPLES))


class ChatMetricsTracker:
    """
    `/search/chat` 메트릭을 스레드 안전하게 집계하는 트래커.
    """

    def __init__(self) -> None:
        """
        트래커를 초기화한다.
        """
        self._state = ChatMetricsState()
        self._lock = Lock()

    def record(
        self,
        source: str,
        success: bool,
        elapsed_ms: float,
        is_fallback: bool,
    ) -> None:
        """
        단일 요청의 메트릭을 기록한다.

        Args:
            source: 응답 source 값
            success: 요청 성공 여부
            elapsed_ms: 처리 지연(ms)
            is_fallback: fallback 응답 여부
        """
        with self._lock:
            self._state.total_requests += 1
            if success:
                self._state.success_requests += 1
            else:
                self._state.failure_requests += 1

            if is_fallback:
                self._state.fallback_responses += 1

            self._state.source_counter[source] += 1
            self._state.latency_samples_ms.append(float(elapsed_ms))

    def snapshot(self) -> dict[str, Any]:
        """
        현재 집계 상태를 조회용 사전으로 반환한다.

        Returns:
            성공률/폴백비율/지연 통계를 포함한 스냅샷 사전
        """
        with self._lock:
            total = self._state.total_requests
            success = self._state.success_requests
            failure = self._state.failure_requests
            fallback = self._state.fallback_responses
            samples = list(self._state.latency_samples_ms)
            source_dist = dict(self._state.source_counter)

        success_rate = (success / total) * 100 if total else 0.0
        fallback_rate = (fallback / total) * 100 if total else 0.0
        avg_latency = (sum(samples) / len(samples)) if samples else 0.0
        p95_latency = _percentile(values=samples, percentile=95.0)

        return {
            "total_requests": total,
            "success_requests": success,
            "failure_requests": failure,
            "fallback_responses": fallback,
            "success_rate_percent": round(success_rate, 2),
            "fallback_rate_percent": round(fallback_rate, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "p95_latency_ms": round(p95_latency, 2),
            "latency_sample_count": len(samples),
            "source_distribution": source_dist,
        }


def _percentile(values: list[float], percentile: float) -> float:
    """
    숫자 리스트에서 주어진 분위수를 계산한다.

    Args:
        values: 지연 시간 값 목록
        percentile: 분위수(예: 95.0)

    Returns:
        계산된 분위수 값. 데이터가 없으면 0.0
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * (percentile / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


_CHAT_METRICS_TRACKER = ChatMetricsTracker()


def get_chat_metrics_tracker() -> ChatMetricsTracker:
    """
    전역 채팅 메트릭 트래커 인스턴스를 반환한다.

    Returns:
        ChatMetricsTracker 싱글턴 인스턴스
    """
    return _CHAT_METRICS_TRACKER
