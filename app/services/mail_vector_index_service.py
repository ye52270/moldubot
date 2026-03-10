from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import ModuleType

from app.core.logging_config import get_logger
from app.services.mail_search_utils import build_hash_embedding

logger = get_logger(__name__)
DEFAULT_MAIL_VECTOR_COLLECTION = "moldubot_emails"
MAIL_VECTOR_ENABLED_ENV = "MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED"
MAIL_VECTOR_DIR_ENV = "MOLDUBOT_MAIL_VECTOR_DIR"
MAIL_VECTOR_COLLECTION_ENV = "MOLDUBOT_MAIL_VECTOR_COLLECTION"


class MailVectorIndexService:
    """
    메일 요약 문서를 Chroma 벡터 스토어에 색인하는 서비스.
    """

    def __init__(self) -> None:
        """
        벡터 색인 서비스 인스턴스를 초기화한다.
        """
        self._enabled = _is_enabled(value=os.getenv(MAIL_VECTOR_ENABLED_ENV, "1"))
        self._persist_dir = _resolve_persist_dir()
        self._collection_name = str(os.getenv(MAIL_VECTOR_COLLECTION_ENV, DEFAULT_MAIL_VECTOR_COLLECTION)).strip()
        self._collection_name = self._collection_name or DEFAULT_MAIL_VECTOR_COLLECTION
        self._chromadb: ModuleType | None = _load_chromadb_module()
        if self._enabled and self._chromadb is None:
            logger.warning("mail_vector_index_disabled: reason=chromadb_import_failed")
            self._enabled = False

    def upsert_mail_document(
        self,
        message_id: str,
        subject: str,
        body_text: str,
        summary: str,
        category: str,
        from_address: str,
        received_date: str,
    ) -> bool:
        """
        메일 문서를 Chroma 컬렉션에 upsert한다.

        Args:
            message_id: 메일 식별자
            subject: 메일 제목
            body_text: 본문 텍스트
            summary: 요약 텍스트
            category: 카테고리
            from_address: 발신자
            received_date: 수신일시

        Returns:
            upsert 수행 여부
        """
        normalized_id = str(message_id or "").strip()
        if not self._enabled or not normalized_id:
            return False
        document = _build_document_text(subject=subject, body_text=body_text, summary=summary)
        embedding = build_hash_embedding(text=document)
        metadata = _build_metadata(
            category=category,
            from_address=from_address,
            received_date=received_date,
            summary=summary,
            subject=subject,
        )
        collection = self._get_collection()
        collection.upsert(
            ids=[normalized_id],
            documents=[document],
            metadatas=[metadata],
            embeddings=[embedding],
        )
        logger.info("mail_vector_index_upserted: message_id=%s collection=%s", normalized_id, self._collection_name)
        return True

    def _get_collection(self):
        """
        Chroma 컬렉션을 조회/생성한다.

        Returns:
            Chroma 컬렉션 객체
        """
        if self._chromadb is None:
            raise RuntimeError("chromadb_unavailable")
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        client = self._chromadb.PersistentClient(path=str(self._persist_dir))
        return client.get_or_create_collection(name=self._collection_name)


def _load_chromadb_module() -> ModuleType | None:
    """
    chromadb 모듈을 지연 로드한다.

    Returns:
        import 성공 시 모듈 객체, 실패 시 None
    """
    try:
        return importlib.import_module("chromadb")
    except Exception as exc:  # noqa: BLE001
        logger.error("mail_vector_index_chromadb_import_failed: %s", exc)
        return None


def _build_document_text(subject: str, body_text: str, summary: str) -> str:
    """
    벡터화 대상 문서 본문을 생성한다.

    Args:
        subject: 메일 제목
        body_text: 메일 본문
        summary: 요약 텍스트

    Returns:
        결합 문서 텍스트
    """
    normalized_subject = str(subject or "").strip()
    normalized_summary = str(summary or "").strip()
    normalized_body = str(body_text or "").strip()[:2000]
    lines = [
        f"subject: {normalized_subject}",
        f"summary: {normalized_summary}",
        f"body: {normalized_body}",
    ]
    return "\n".join(lines).strip()


def _build_metadata(
    category: str,
    from_address: str,
    received_date: str,
    summary: str,
    subject: str,
) -> dict[str, str]:
    """
    Chroma 메타데이터를 생성한다.

    Args:
        category: 카테고리
        from_address: 발신자
        received_date: 수신일시
        summary: 요약
        subject: 제목

    Returns:
        메타데이터 사전
    """
    return {
        "category": str(category or "").strip(),
        "from_address": str(from_address or "").strip(),
        "received_date": str(received_date or "").strip(),
        "summary": str(summary or "").strip()[:500],
        "subject": str(subject or "").strip()[:300],
    }


def _resolve_persist_dir() -> Path:
    """
    Chroma persist 디렉터리를 해석한다.

    Returns:
        persist 디렉터리 경로
    """
    env_path = str(os.getenv(MAIL_VECTOR_DIR_ENV, "")).strip()
    if env_path:
        return Path(env_path)
    root_dir = Path(__file__).resolve().parents[2]
    return root_dir / "data" / "chroma_db"


def _is_enabled(value: str | None) -> bool:
    """
    기능 활성화 플래그 문자열을 bool로 변환한다.

    Args:
        value: 환경변수 문자열

    Returns:
        활성화 여부
    """
    normalized = str(value or "").strip().lower()
    return normalized not in {"0", "false", "off", "no"}
