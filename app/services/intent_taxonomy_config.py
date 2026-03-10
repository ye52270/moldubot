from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_RECIPIENT_TOKENS: tuple[str, ...] = ("수신자", "받는사람")
DEFAULT_TODO_TOKENS: tuple[str, ...] = ("todo", "할일", "조치", "액션")
DEFAULT_DUE_TOKENS: tuple[str, ...] = ("마감", "기한", "due")
DEFAULT_REGISTRATION_TOKENS: tuple[str, ...] = ("등록", "생성", "추가", "만들어")

_CACHE_LOCK = Lock()
_CACHE_PATH: str = ""
_CACHE_MTIME_NS: int = -1
_CACHE_VALUE: "IntentTaxonomyConfig | None" = None


@dataclass(frozen=True)
class RecipientTodoPolicy:
    """수신자별 ToDo 요약/등록 분기 정책."""

    recipient_tokens: tuple[str, ...]
    todo_tokens: tuple[str, ...]
    due_tokens: tuple[str, ...]
    registration_tokens: tuple[str, ...]


@dataclass(frozen=True)
class IntentTaxonomyConfig:
    """의도 taxonomy 설정 모델."""

    recipient_todo_policy: RecipientTodoPolicy
    source_path: str


def get_intent_taxonomy() -> IntentTaxonomyConfig:
    """의도 taxonomy 설정을 조회하고 파일 변경 시 자동 리로드한다."""
    config_path = _resolve_config_path()
    latest_mtime_ns = _resolve_file_mtime_ns(config_path=config_path)
    with _CACHE_LOCK:
        cached = _read_cached_config(config_path=config_path, mtime_ns=latest_mtime_ns)
        if cached is not None:
            return cached
        loaded = _load_intent_taxonomy(config_path=config_path)
        _write_cache(config_path=config_path, mtime_ns=latest_mtime_ns, config=loaded)
        return loaded


def reset_intent_taxonomy_cache() -> None:
    """의도 taxonomy 설정 캐시를 초기화한다."""
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_VALUE
    with _CACHE_LOCK:
        _CACHE_PATH = ""
        _CACHE_MTIME_NS = -1
        _CACHE_VALUE = None


def _resolve_config_path() -> str:
    """의도 taxonomy 설정 파일 경로를 계산한다."""
    env_path = str(os.getenv("INTENT_TAXONOMY_CONFIG_PATH") or "").strip()
    if env_path:
        return str(Path(env_path).expanduser().resolve())
    project_root = Path(__file__).resolve().parents[2]
    return str((project_root / "config" / "intent_taxonomy.json").resolve())


def _resolve_file_mtime_ns(config_path: str) -> int:
    """설정 파일 mtime(ns)를 조회한다."""
    try:
        return int(Path(config_path).stat().st_mtime_ns)
    except OSError:
        return -1


def _read_cached_config(config_path: str, mtime_ns: int) -> IntentTaxonomyConfig | None:
    """현재 캐시가 유효하면 반환한다."""
    if _CACHE_VALUE is None:
        return None
    if _CACHE_PATH != config_path:
        return None
    if _CACHE_MTIME_NS != mtime_ns:
        return None
    return _CACHE_VALUE


def _write_cache(config_path: str, mtime_ns: int, config: IntentTaxonomyConfig) -> None:
    """설정 캐시를 갱신한다."""
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_VALUE
    _CACHE_PATH = config_path
    _CACHE_MTIME_NS = mtime_ns
    _CACHE_VALUE = config


def _load_intent_taxonomy(config_path: str) -> IntentTaxonomyConfig:
    """설정 파일을 읽어 의도 taxonomy 모델을 생성한다."""
    path = Path(config_path)
    if not path.exists():
        logger.warning("intent_taxonomy_config.load_missing: path=%s", config_path)
        return _build_default_config(source_path=config_path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _parse_intent_taxonomy_payload(payload=payload, source_path=config_path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        logger.error("intent_taxonomy_config.load_failed: path=%s error=%s", config_path, error)
        return _build_default_config(source_path=config_path)


def _parse_intent_taxonomy_payload(payload: object, source_path: str) -> IntentTaxonomyConfig:
    """JSON payload를 IntentTaxonomyConfig로 변환한다."""
    if not isinstance(payload, dict):
        raise ValueError("intent taxonomy payload must be a JSON object")
    raw_policy = payload.get("recipient_todo_policy")
    policy = _parse_recipient_todo_policy(raw_policy=raw_policy)
    return IntentTaxonomyConfig(recipient_todo_policy=policy, source_path=source_path)


def _parse_recipient_todo_policy(raw_policy: object) -> RecipientTodoPolicy:
    """recipient_todo_policy payload를 정규화한다."""
    if not isinstance(raw_policy, dict):
        return _build_default_policy()
    return RecipientTodoPolicy(
        recipient_tokens=_normalize_tokens(
            raw_tokens=raw_policy.get("recipient_tokens"),
            defaults=DEFAULT_RECIPIENT_TOKENS,
        ),
        todo_tokens=_normalize_tokens(
            raw_tokens=raw_policy.get("todo_tokens"),
            defaults=DEFAULT_TODO_TOKENS,
        ),
        due_tokens=_normalize_tokens(
            raw_tokens=raw_policy.get("due_tokens"),
            defaults=DEFAULT_DUE_TOKENS,
        ),
        registration_tokens=_normalize_tokens(
            raw_tokens=raw_policy.get("registration_tokens"),
            defaults=DEFAULT_REGISTRATION_TOKENS,
        ),
    )


def _normalize_tokens(raw_tokens: object, defaults: tuple[str, ...]) -> tuple[str, ...]:
    """토큰 배열 payload를 정규화한다."""
    if not isinstance(raw_tokens, list):
        return defaults
    normalized: list[str] = []
    for token in raw_tokens:
        value = str(token or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in normalized:
            continue
        normalized.append(lowered)
    if normalized:
        return tuple(normalized)
    return defaults


def _build_default_policy() -> RecipientTodoPolicy:
    """기본 수신자 ToDo 정책을 생성한다."""
    return RecipientTodoPolicy(
        recipient_tokens=DEFAULT_RECIPIENT_TOKENS,
        todo_tokens=DEFAULT_TODO_TOKENS,
        due_tokens=DEFAULT_DUE_TOKENS,
        registration_tokens=DEFAULT_REGISTRATION_TOKENS,
    )


def _build_default_config(source_path: str) -> IntentTaxonomyConfig:
    """기본 의도 taxonomy 설정 모델을 생성한다."""
    return IntentTaxonomyConfig(recipient_todo_policy=_build_default_policy(), source_path=source_path)
