from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.mail_client import (
    GRAPH_BASE_URL,
    GraphMailClient,
    _extract_graph_error_metadata,
)

logger = get_logger(__name__)
SEOUL_TIMEZONE_NAME = "Asia/Seoul"


@dataclass
class GraphCalendarEvent:
    """
    Graph 캘린더 이벤트 생성 결과 모델.
    """

    event_id: str
    web_link: str


class GraphCalendarClient:
    """
    Microsoft Graph `/me/events` 생성 클라이언트.
    """

    def __init__(self, auth_client: GraphMailClient | None = None) -> None:
        """
        Graph 캘린더 클라이언트를 초기화한다.

        Args:
            auth_client: 토큰 획득에 사용할 GraphMailClient 인스턴스
        """
        self._auth_client = auth_client or GraphMailClient()

    def is_configured(self) -> bool:
        """
        Graph 설정 여부를 반환한다.

        Returns:
            설정되어 있으면 True
        """
        return self._auth_client.is_configured()

    def create_event(
        self,
        subject: str,
        start_iso: str,
        end_iso: str,
        body_text: str,
        attendees: list[str] | None = None,
    ) -> GraphCalendarEvent | None:
        """
        사용자 캘린더에 이벤트를 생성한다.

        Args:
            subject: 일정 제목
            start_iso: 시작 시각(YYYY-MM-DDTHH:MM:SS)
            end_iso: 종료 시각(YYYY-MM-DDTHH:MM:SS)
            body_text: 일정 본문
            attendees: 참석자 이메일 목록

        Returns:
            성공 시 이벤트 모델, 실패 시 None
        """
        if not self.is_configured():
            logger.warning("GraphCalendarClient 설정 누락으로 일정 생성을 건너뜁니다.")
            return None

        token = self._auth_client.acquire_access_token()
        if not token:
            return None

        response = self._request_create_event(
            access_token=token,
            subject=subject,
            start_iso=start_iso,
            end_iso=end_iso,
            body_text=body_text,
            attendees=attendees,
        )
        if response is None:
            return None

        if response.status_code == 401:
            logger.info("Graph 일정 생성 401 -> 토큰 초기화 후 재시도")
            self._auth_client.reset_access_token()
            refreshed = self._auth_client.acquire_access_token(force_refresh=True)
            if not refreshed:
                return None
            response = self._request_create_event(
                access_token=refreshed,
                subject=subject,
                start_iso=start_iso,
                end_iso=end_iso,
                body_text=body_text,
                attendees=attendees,
            )
            if response is None:
                return None

        if response.status_code not in (200, 201):
            error_meta = _extract_graph_error_metadata(response=response)
            logger.warning(
                "Graph 일정 생성 실패: status=%s graph_error_code=%s request_id=%s",
                response.status_code,
                error_meta["error_code"],
                error_meta["request_id"],
            )
            return None

        payload = response.json()
        return GraphCalendarEvent(
            event_id=str(payload.get("id") or ""),
            web_link=str(payload.get("webLink") or ""),
        )

    def _request_create_event(
        self,
        access_token: str,
        subject: str,
        start_iso: str,
        end_iso: str,
        body_text: str,
        attendees: list[str] | None = None,
    ) -> requests.Response | None:
        """
        Graph `/me/events` POST 요청을 수행한다.

        Args:
            access_token: Bearer 토큰
            subject: 일정 제목
            start_iso: 시작 시각(로컬 시각 문자열)
            end_iso: 종료 시각(로컬 시각 문자열)
            body_text: 일정 본문

        Returns:
            HTTP 응답 또는 None
        """
        url = f"{GRAPH_BASE_URL}/me/events"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "text",
                "content": body_text,
            },
            "start": {
                "dateTime": start_iso,
                "timeZone": SEOUL_TIMEZONE_NAME,
            },
            "end": {
                "dateTime": end_iso,
                "timeZone": SEOUL_TIMEZONE_NAME,
            },
        }
        normalized_attendees = [
            str(item or "").strip()
            for item in attendees or []
            if str(item or "").strip()
        ]
        if normalized_attendees:
            payload["attendees"] = [
                {
                    "emailAddress": {"address": address},
                    "type": "required",
                }
                for address in normalized_attendees
            ]
        try:
            return requests.post(url, headers=headers, json=payload, timeout=10)
        except requests.RequestException as exc:
            logger.warning("Graph 일정 생성 네트워크 실패: error=%s", exc)
            return None
