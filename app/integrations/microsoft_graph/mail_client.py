from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import html
from dataclasses import dataclass
from typing import Any

import msal
import requests
from bs4 import BeautifulSoup

from app.core.logging_config import get_logger

GRAPH_SCOPE = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Tasks.ReadWrite",
]
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MESSAGE_SELECT_FIELDS = (
    "id,subject,receivedDateTime,from,bodyPreview,body,toRecipients,internetMessageId,webLink"
)

logger = get_logger(__name__)
UNKNOWN_VALUE = "-"


@dataclass
class GraphMailMessage:
    """
    Graph 단건 메일 조회 결과 모델.
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str
    internet_message_id: str
    web_link: str


class GraphMailClient:
    """
    Microsoft Graph 단건 메일 조회 클라이언트.
    PublicClientApplication + Delegated 토큰(토큰 캐시 파일) 방식 사용.
    개인 outlook.com 계정을 지원한다.
    """

    def __init__(self) -> None:
        """
        Delegated Graph 클라이언트 설정/캐시를 초기화한다.
        """
        self._client_id = str(os.getenv("MICROSOFT_APP_ID", "")).strip()
        self._tenant_id = str(os.getenv("MICROSOFT_TENANT_ID", "common")).strip() or "common"
        self._email_address = str(os.getenv("MICROSOFT_EMAIL_ADDRESS", "")).strip()
        self._authority = "https://login.microsoftonline.com/common"
        self._token_cache_path = os.getenv(
            "GRAPH_TOKEN_CACHE_PATH",
            os.path.expanduser("~/.m365_graph_token_cache.bin"),
        )
        self._token_cache = msal.SerializableTokenCache()
        self._load_token_cache()
        self._msal_app: msal.PublicClientApplication | None = None
        self._access_token: str = ""

    def is_configured(self) -> bool:
        """
        Graph Delegated 최소 설정 존재 여부를 반환한다.

        Returns:
            client_id가 있으면 True
        """
        return bool(self._client_id)

    def _load_token_cache(self) -> None:
        """
        파일 기반 토큰 캐시를 로드한다.
        """
        if not os.path.exists(self._token_cache_path):
            return
        try:
            with open(self._token_cache_path, "r", encoding="utf-8") as file:
                raw = file.read()
            text = str(raw or "").strip()
            if not text:
                return
            try:
                self._token_cache.deserialize(text)
            except Exception as parse_error:
                decoder = json.JSONDecoder()
                recovered_obj, _ = decoder.raw_decode(text)
                recovered_text = json.dumps(recovered_obj, ensure_ascii=False, separators=(",", ":"))
                self._token_cache.deserialize(recovered_text)
                logger.warning("token cache recovered: error=%s", parse_error)
                self._save_token_cache()
        except Exception as exc:
            logger.warning("token cache load failed: %s", exc)
            try:
                backup_path = f"{self._token_cache_path}.corrupt.{int(time.time())}"
                shutil.copy2(self._token_cache_path, backup_path)
                os.remove(self._token_cache_path)
            except Exception:
                pass

    def _save_token_cache(self) -> None:
        """
        토큰 캐시 변경이 있을 때 파일에 원자적으로 저장한다.
        """
        if not self._token_cache.has_state_changed:
            return
        tmp_path = ""
        try:
            serialized = self._token_cache.serialize()
            cache_dir = os.path.dirname(self._token_cache_path) or "."
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".graph_token_cache.",
                suffix=".tmp",
                dir=cache_dir,
                text=True,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(serialized)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, self._token_cache_path)
            tmp_path = ""
            try:
                os.chmod(self._token_cache_path, 0o600)
            except Exception:
                pass
        except Exception as exc:
            logger.warning("token cache save failed: %s", exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _get_msal_app(self) -> msal.PublicClientApplication:
        """
        PublicClientApplication 인스턴스를 반환한다.

        Returns:
            MSAL PublicClientApplication
        """
        if self._msal_app is None:
            self._msal_app = msal.PublicClientApplication(
                client_id=self._client_id,
                authority=self._authority,
                token_cache=self._token_cache,
            )
        return self._msal_app

    def _acquire_access_token(self, force_refresh: bool = False) -> str:
        """
        Silent -> Interactive 순서로 Delegated 토큰을 획득한다.

        Args:
            force_refresh: True이면 메모리 토큰을 무시하고 다시 획득한다.

        Returns:
            access token 문자열. 실패 시 빈 문자열
        """
        if self._access_token and not force_refresh:
            return self._access_token

        app = self._get_msal_app()
        accounts = (
            app.get_accounts(username=self._email_address)
            if self._email_address
            else app.get_accounts()
        )

        result: dict[str, Any] | None = None
        if accounts:
            result = app.acquire_token_silent(scopes=GRAPH_SCOPE, account=accounts[0])

        if not result:
            logger.info("Graph 토큰 캐시 없음 -> Interactive 로그인 시작")
            result = app.acquire_token_interactive(
                scopes=GRAPH_SCOPE,
                login_hint=self._email_address or None,
            )

        token = str((result or {}).get("access_token") or "").strip()
        if token:
            self._access_token = token
            self._save_token_cache()
            return token

        logger.warning(
            "Graph Delegated 토큰 발급 실패: error=%s error_description=%s",
            (result or {}).get("error"),
            (result or {}).get("error_description"),
        )
        return ""

    def get_message(self, mailbox_user: str, message_id: str) -> GraphMailMessage | None:
        """
        Delegated `/me/messages/{id}`로 단건 메일을 조회한다.

        Args:
            mailbox_user: 호환성 유지를 위한 인자(현재 미사용)
            message_id: Graph 메시지 ID

        Returns:
            조회 성공 시 GraphMailMessage, 실패 시 None
        """
        _ = mailbox_user
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return None
        if not self.is_configured():
            logger.warning("GraphMailClient 설정 누락으로 조회를 건너뜁니다.")
            return None

        access_token = self._acquire_access_token()
        if not access_token:
            return None

        response = self._request_message(
            message_id=normalized_message_id,
            access_token=access_token,
        )
        if response is None:
            return None

        if response.status_code == 401:
            logger.info("Graph 메시지 조회 401 -> 토큰 초기화 후 재시도")
            self._access_token = ""
            refreshed_token = self._acquire_access_token(force_refresh=True)
            if not refreshed_token:
                return None
            response = self._request_message(
                message_id=normalized_message_id,
                access_token=refreshed_token,
            )
            if response is None:
                return None

        if response.status_code != 200:
            error_meta = _extract_graph_error_metadata(response=response)
            logger.warning(
                "Graph 메시지 조회 실패: message_id=%s status=%s graph_error_code=%s request_id=%s",
                _short_value(normalized_message_id),
                response.status_code,
                error_meta["error_code"],
                error_meta["request_id"],
            )
            return None

        return _parse_graph_mail_payload(payload=response.json())

    def acquire_access_token(self, force_refresh: bool = False) -> str:
        """
        Graph Delegated access token을 반환한다.

        Args:
            force_refresh: True이면 캐시 토큰을 무시하고 재획득한다.

        Returns:
            Bearer access token. 실패 시 빈 문자열
        """
        return self._acquire_access_token(force_refresh=force_refresh)

    def reset_access_token(self) -> None:
        """
        메모리의 access token 캐시를 초기화한다.
        """
        self._access_token = ""

    def _request_message(
        self,
        message_id: str,
        access_token: str,
    ) -> requests.Response | None:
        """
        `/me/messages/{id}`로 단건 메일 조회를 수행한다.

        Args:
            message_id: Graph 메시지 ID
            access_token: Graph Delegated Bearer 토큰

        Returns:
            Graph HTTP 응답. 네트워크 실패 시 None
        """
        encoded_message_id = requests.utils.quote(message_id, safe="")
        url = (
            f"{GRAPH_BASE_URL}/me/messages/{encoded_message_id}"
            f"?$select={MESSAGE_SELECT_FIELDS}"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Prefer": 'outlook.body-content-type="html"',
        }
        try:
            return requests.get(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            logger.warning(
                "Graph 메시지 조회 네트워크 실패: message_id=%s error=%s",
                _short_value(message_id),
                str(exc),
            )
            return None


def _parse_graph_mail_payload(payload: dict[str, Any]) -> GraphMailMessage:
    """
    Graph 응답 payload를 GraphMailMessage로 정규화한다.

    Args:
        payload: Graph 메시지 응답

    Returns:
        정규화된 메시지 모델
    """
    from_payload = payload.get("from", {})
    email_address = from_payload.get("emailAddress", {}) if isinstance(from_payload, dict) else {}
    body_payload = payload.get("body", {})
    body_content = ""
    body_content_type = ""
    if isinstance(body_payload, dict):
        body_content = str(body_payload.get("content") or "")
        body_content_type = str(body_payload.get("contentType") or "")
    body_preview = str(payload.get("bodyPreview") or "")
    body_text = _extract_body_text(content=body_content, content_type=body_content_type, body_preview=body_preview)
    return GraphMailMessage(
        message_id=str(payload.get("id") or ""),
        subject=str(payload.get("subject") or ""),
        from_address=str(email_address.get("address") or ""),
        received_date=str(payload.get("receivedDateTime") or ""),
        body_text=body_text,
        internet_message_id=str(payload.get("internetMessageId") or ""),
        web_link=str(payload.get("webLink") or ""),
    )


def _extract_body_text(content: str, content_type: str, body_preview: str) -> str:
    """
    Graph body payload를 contentType 기준으로 텍스트 본문으로 정규화한다.

    Args:
        content: `body.content` 문자열
        content_type: `body.contentType` 값 (`html`/`text`)
        body_preview: Graph `bodyPreview` 문자열

    Returns:
        정규화된 본문 텍스트
    """
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return str(body_preview or "").strip()
    if str(content_type or "").strip().lower() == "html":
        return _html_to_text(content=normalized_content)
    return _normalize_plain_body_text(content=normalized_content)


def _html_to_text(content: str) -> str:
    """
    HTML 본문을 텍스트로 정규화한다.

    Args:
        content: HTML 원문 문자열

    Returns:
        태그 제거/공백 정리된 텍스트
    """
    soup = BeautifulSoup(str(content or ""), "html.parser")
    for removable in soup.find_all(["style", "script", "noscript"]):
        removable.decompose()
    text = soup.get_text(separator="\n")
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_plain_body_text(content: str) -> str:
    """
    text 본문을 줄바꿈/공백 기준으로 정규화한다.

    Args:
        content: text 본문 문자열

    Returns:
        정규화된 text 본문
    """
    text = str(content or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_aadsts_metadata(error_description: str) -> dict[str, str]:
    """
    AADSTS 에러 문자열에서 추적 메타를 파싱한다.

    Args:
        error_description: MSAL 에러 설명 문자열

    Returns:
        trace/correlation/timestamp 메타 정보
    """
    trace_id_match = re.search(r"Trace ID:\s*([a-f0-9-]+)", error_description, flags=re.IGNORECASE)
    correlation_id_match = re.search(r"Correlation ID:\s*([a-f0-9-]+)", error_description, flags=re.IGNORECASE)
    timestamp_match = re.search(r"Timestamp:\s*([0-9TZ:\-\.]+)", error_description)
    return {
        "trace_id": trace_id_match.group(1) if trace_id_match else UNKNOWN_VALUE,
        "correlation_id": correlation_id_match.group(1) if correlation_id_match else UNKNOWN_VALUE,
        "timestamp": timestamp_match.group(1) if timestamp_match else UNKNOWN_VALUE,
    }


def _extract_graph_error_metadata(response: requests.Response) -> dict[str, str]:
    """
    Graph 실패 응답에서 에러 메타를 추출한다.

    Args:
        response: Graph HTTP 응답

    Returns:
        에러 코드/메시지/request-id/client-request-id
    """
    error_code = UNKNOWN_VALUE
    error_message = UNKNOWN_VALUE
    request_id = str(response.headers.get("request-id") or UNKNOWN_VALUE)
    client_request_id = str(response.headers.get("client-request-id") or UNKNOWN_VALUE)
    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        payload = {}
    error_payload = payload.get("error", {})
    if isinstance(error_payload, dict):
        error_code = str(error_payload.get("code") or UNKNOWN_VALUE)
        error_message = str(error_payload.get("message") or UNKNOWN_VALUE)
        inner_error = error_payload.get("innerError", {})
        if isinstance(inner_error, dict):
            request_id = str(inner_error.get("request-id") or request_id or UNKNOWN_VALUE)
            client_request_id = str(inner_error.get("client-request-id") or client_request_id or UNKNOWN_VALUE)
    return {
        "error_code": error_code,
        "error_message": _short_value(error_message, max_len=140),
        "request_id": request_id or UNKNOWN_VALUE,
        "client_request_id": client_request_id or UNKNOWN_VALUE,
    }


def _short_value(value: str, max_len: int = 48) -> str:
    """
    긴 문자열을 로그 출력용으로 축약한다.

    Args:
        value: 원본 문자열
        max_len: 최대 출력 길이

    Returns:
        축약된 문자열
    """
    normalized = str(value or "").strip()
    if not normalized:
        return UNKNOWN_VALUE
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[:max_len]}..."


def _tail_value(value: str, tail_len: int = 6) -> str:
    """
    문자열의 뒷부분만 노출한다.

    Args:
        value: 원본 문자열
        tail_len: 노출할 길이

    Returns:
        뒷부분 문자열
    """
    normalized = str(value or "").strip()
    if not normalized:
        return UNKNOWN_VALUE
    if len(normalized) <= tail_len:
        return normalized
    return normalized[-tail_len:]
