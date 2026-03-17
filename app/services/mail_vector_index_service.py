from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from importlib import metadata
from json import dumps
from pathlib import Path
from types import ModuleType
from typing import Protocol

from app.core.logging_config import get_logger
from app.services.mail_search_utils import build_hash_embedding

logger = get_logger(__name__)
DEFAULT_MAIL_VECTOR_COLLECTION = "moldubot_emails"
MAIL_VECTOR_ENABLED_ENV = "MOLDUBOT_MAIL_VECTOR_INDEX_ENABLED"
MAIL_VECTOR_DIR_ENV = "MOLDUBOT_MAIL_VECTOR_DIR"
MAIL_VECTOR_COLLECTION_ENV = "MOLDUBOT_MAIL_VECTOR_COLLECTION"


@dataclass(frozen=True)
class MailVectorIndexStatus:
    """
    메일 벡터 인덱스 런타임 상태를 표현한다.

    Attributes:
        enabled: 벡터 인덱싱 활성화 여부
        reason: 비활성 사유
        chromadb_available: chromadb import 가능 여부
        chromadb_version: 설치된 chromadb 버전
        python_version: 현재 Python 버전 문자열
        collection_name: 대상 컬렉션명
        persist_dir: persist 디렉터리 문자열
        backend: 실제 저장 backend
        runtime_blocker: 사전 탐지된 런타임 차단 사유
    """

    enabled: bool
    reason: str
    chromadb_available: bool
    chromadb_version: str
    python_version: str
    collection_name: str
    persist_dir: str
    backend: str
    runtime_blocker: str

    def as_dict(self) -> dict[str, str | bool]:
        """
        상태 객체를 직렬화 가능한 사전으로 변환한다.

        Returns:
            JSON 직렬화 가능한 상태 사전
        """
        return asdict(self)


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
        self._disabled_reason = "disabled_by_env" if not self._enabled else ""
        self._runtime_blocker = _resolve_runtime_blocker()
        self._chromadb: ModuleType | None = None
        self._backend_type = "disabled"
        if self._enabled and not self._runtime_blocker:
            self._chromadb = _load_chromadb_module()
        if self._enabled and self._chromadb is not None:
            self._backend_type = "chromadb"
        elif self._enabled:
            blocker = self._runtime_blocker or "chromadb_import_failed"
            logger.warning("mail_vector_index_disabled: reason=%s", blocker)
            self._backend_type = "sqlite_fallback"
            self._disabled_reason = "fallback_active"
        self._fallback_collection = _SQLiteFallbackCollection(
            db_path=self._persist_dir / "mail_vector_fallback.sqlite3",
            collection_name=self._collection_name,
        )

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
        logger.info(
            "mail_vector_index_upserted: message_id=%s collection=%s backend=%s",
            normalized_id,
            self._collection_name,
            self._backend_type,
        )
        return True

    def get_status(self) -> MailVectorIndexStatus:
        """
        현재 벡터 인덱스 런타임 상태를 반환한다.

        Returns:
            벡터 인덱스 상태 모델
        """
        reason = self._disabled_reason if not self._enabled else "ready"
        return MailVectorIndexStatus(
            enabled=self._enabled,
            reason=reason,
            chromadb_available=self._chromadb is not None,
            chromadb_version=_get_installed_package_version("chromadb"),
            python_version=_get_python_version(),
            collection_name=self._collection_name,
            persist_dir=str(self._persist_dir),
            backend=self._backend_type,
            runtime_blocker=self._runtime_blocker,
        )

    def _get_collection(self) -> "_CollectionProtocol":
        """
        활성 backend 컬렉션을 조회/생성한다.

        Returns:
            컬렉션 객체
        """
        if self._backend_type == "sqlite_fallback":
            return self._fallback_collection
        if self._chromadb is None:
            raise RuntimeError("vector_backend_unavailable")
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        client = self._chromadb.PersistentClient(path=str(self._persist_dir))
        return client.get_or_create_collection(name=self._collection_name)


class _CollectionProtocol(Protocol):
    """벡터 컬렉션 최소 upsert 인터페이스."""

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """문서 배치를 upsert한다."""


class _SQLiteFallbackCollection:
    """
    Chroma 비가용 시 로컬 sqlite에 임베딩을 저장하는 fallback 컬렉션.
    """

    def __init__(self, db_path: Path, collection_name: str) -> None:
        """
        fallback 컬렉션을 초기화한다.

        Args:
            db_path: fallback sqlite 경로
            collection_name: 컬렉션명
        """
        self._db_path = db_path
        self._collection_name = collection_name

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        """
        임베딩 배치를 sqlite 테이블에 upsert한다.

        Args:
            ids: 문서 id 목록
            documents: 문서 본문 목록
            metadatas: 메타데이터 목록
            embeddings: 임베딩 목록
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._db_path))
        try:
            self._ensure_table(connection=connection)
            for message_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings, strict=False):
                connection.execute(
                    "INSERT INTO mail_vector_index (collection_name, message_id, document, metadata_json, embedding_json) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(collection_name, message_id) DO UPDATE SET "
                    "document = excluded.document, metadata_json = excluded.metadata_json, "
                    "embedding_json = excluded.embedding_json, updated_at = CURRENT_TIMESTAMP",
                    (
                        self._collection_name,
                        message_id,
                        document,
                        dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                        dumps(embedding),
                    ),
                )
            connection.commit()
        finally:
            connection.close()

    def _ensure_table(self, connection: sqlite3.Connection) -> None:
        """
        fallback 저장 테이블을 보장한다.

        Args:
            connection: sqlite 연결
        """
        connection.execute(
            "CREATE TABLE IF NOT EXISTS mail_vector_index ("
            "collection_name TEXT NOT NULL, "
            "message_id TEXT NOT NULL, "
            "document TEXT NOT NULL, "
            "metadata_json TEXT NOT NULL, "
            "embedding_json TEXT NOT NULL, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (collection_name, message_id))"
        )


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


def _resolve_runtime_blocker() -> str:
    """
    현재 런타임에서 사전에 알려진 Chroma 비호환 이슈를 반환한다.

    Returns:
        비호환 사유 문자열. 없으면 빈 문자열
    """
    if sys.version_info >= (3, 14):
        return "python_3_14_unsupported"
    return ""


def _get_installed_package_version(package_name: str) -> str:
    """
    설치된 패키지 버전을 안전하게 조회한다.

    Args:
        package_name: 조회 대상 패키지명

    Returns:
        버전 문자열. 미설치 시 빈 문자열
    """
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return ""


def _get_python_version() -> str:
    """
    현재 Python 버전 문자열을 반환한다.

    Returns:
        `major.minor.micro` 형식 버전 문자열
    """
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


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
