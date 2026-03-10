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
DEFAULT_TODO_LIST_NAME = "Tasks"


@dataclass
class GraphTodoTask:
    """
    Graph ToDo 생성 결과 모델.
    """

    task_id: str
    web_link: str


class GraphTodoClient:
    """
    Microsoft Graph ToDo(`/me/todo`) 생성 클라이언트.
    """

    def __init__(self, auth_client: GraphMailClient | None = None) -> None:
        """
        Graph ToDo 클라이언트를 초기화한다.

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

    def create_task(self, title: str, due_date: str, body_text: str = "") -> GraphTodoTask | None:
        """
        Outlook ToDo 작업을 생성한다.

        Args:
            title: 할 일 제목
            due_date: 마감일(YYYY-MM-DD)
            body_text: 할 일 본문 설명

        Returns:
            생성 성공 시 GraphTodoTask, 실패 시 None
        """
        if not self.is_configured():
            logger.warning("GraphTodoClient 설정 누락으로 ToDo 생성을 건너뜁니다.")
            return None

        token = self._auth_client.acquire_access_token()
        if not token:
            return None

        list_id = self._resolve_list_id(access_token=token)
        if not list_id:
            return None
        response = self._request_create_task(
            access_token=token,
            list_id=list_id,
            title=title,
            due_date=due_date,
            body_text=body_text,
        )
        if response is None:
            return None
        if response.status_code == 401:
            logger.info("Graph ToDo 생성 401 -> 토큰 초기화 후 재시도")
            self._auth_client.reset_access_token()
            refreshed = self._auth_client.acquire_access_token(force_refresh=True)
            if not refreshed:
                return None
            list_id = self._resolve_list_id(access_token=refreshed)
            if not list_id:
                return None
            response = self._request_create_task(
                access_token=refreshed,
                list_id=list_id,
                title=title,
                due_date=due_date,
                body_text=body_text,
            )
            if response is None:
                return None
        if response.status_code not in (200, 201):
            error_meta = _extract_graph_error_metadata(response=response)
            logger.warning(
                "Graph ToDo 생성 실패: status=%s graph_error_code=%s request_id=%s",
                response.status_code,
                error_meta["error_code"],
                error_meta["request_id"],
            )
            return None
        payload = response.json()
        return GraphTodoTask(
            task_id=str(payload.get("id") or ""),
            web_link=str(payload.get("webLink") or ""),
        )

    def _resolve_list_id(self, access_token: str) -> str:
        """
        사용자 ToDo 목록에서 기본 list id를 찾는다.

        Args:
            access_token: Graph Bearer 토큰

        Returns:
            목록 ID. 찾지 못하면 빈 문자열
        """
        response = self._request_lists(access_token=access_token)
        if response is None:
            return ""
        if response.status_code != 200:
            error_meta = _extract_graph_error_metadata(response=response)
            logger.warning(
                "Graph ToDo 목록 조회 실패: status=%s graph_error_code=%s request_id=%s",
                response.status_code,
                error_meta["error_code"],
                error_meta["request_id"],
            )
            return ""
        items = response.json().get("value")
        if not isinstance(items, list):
            return ""
        fallback_id = ""
        for item in items:
            if not isinstance(item, dict):
                continue
            list_id = str(item.get("id") or "").strip()
            if not fallback_id and list_id:
                fallback_id = list_id
            display_name = str(item.get("displayName") or "").strip()
            if display_name.lower() == DEFAULT_TODO_LIST_NAME.lower() and list_id:
                return list_id
        return fallback_id

    def _request_lists(self, access_token: str) -> requests.Response | None:
        """
        Graph ToDo 목록 조회 요청을 수행한다.

        Args:
            access_token: Graph Bearer 토큰

        Returns:
            HTTP 응답 또는 None
        """
        url = f"{GRAPH_BASE_URL}/me/todo/lists?$top=50"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            return requests.get(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            logger.warning("Graph ToDo 목록 조회 네트워크 실패: error=%s", exc)
            return None

    def _request_create_task(
        self,
        access_token: str,
        list_id: str,
        title: str,
        due_date: str,
        body_text: str,
    ) -> requests.Response | None:
        """
        Graph ToDo 생성 요청을 수행한다.

        Args:
            access_token: Graph Bearer 토큰
            list_id: 대상 ToDo 목록 ID
            title: 할 일 제목
            due_date: 마감일(YYYY-MM-DD)
            body_text: 할 일 설명

        Returns:
            HTTP 응답 또는 None
        """
        url = f"{GRAPH_BASE_URL}/me/todo/lists/{requests.utils.quote(list_id, safe='')}/tasks"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "title": str(title or "").strip(),
            "body": {
                "contentType": "text",
                "content": str(body_text or "").strip(),
            },
            "dueDateTime": {
                "dateTime": f"{str(due_date).strip()}T18:00:00",
                "timeZone": SEOUL_TIMEZONE_NAME,
            },
        }
        try:
            return requests.post(url, headers=headers, json=payload, timeout=10)
        except requests.RequestException as exc:
            logger.warning("Graph ToDo 생성 네트워크 실패: error=%s", exc)
            return None
