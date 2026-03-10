from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.core.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_ROLE_HINTS: tuple[tuple[str, str], ...] = (
    ("조치", "실행 담당"),
    ("처리", "실행 담당"),
    ("개발", "실행 담당"),
    ("수정", "실행 담당"),
    ("승인", "승인 담당"),
    ("결재", "승인 담당"),
    ("검토", "검토 담당"),
    ("확인", "검토 담당"),
    ("요청", "요청자"),
    ("문의", "요청자"),
    ("공유", "공유 대상"),
    ("참조", "공유 대상"),
)
DEFAULT_ROLES: dict[str, str] = {
    "to": "수신/실행 대상",
    "cc": "공유 대상",
    "unknown": "역할 미상",
}

_CACHE_LOCK = Lock()
_CACHE_PATH: str = ""
_CACHE_MTIME_NS: int = -1
_CACHE_VALUE: "RoleTaxonomyConfig | None" = None


@dataclass(frozen=True)
class RoleHint:
    """키워드 기반 역할 추정 규칙.

    Attributes:
        keyword: 역할 판단 키워드
        role: 매핑할 역할 레이블
    """

    keyword: str
    role: str


@dataclass(frozen=True)
class RoleTaxonomyConfig:
    """역할 taxonomy 설정 모델.

    Attributes:
        role_hints: 키워드 기반 역할 규칙 목록
        default_roles: 수신자/참조/미상 기본 역할
        source_path: 로드한 설정 파일 경로
    """

    role_hints: tuple[RoleHint, ...]
    default_roles: dict[str, str]
    source_path: str


def get_role_taxonomy() -> RoleTaxonomyConfig:
    """역할 taxonomy 설정을 조회하고 파일 변경 시 자동 리로드한다.

    Returns:
        캐시 또는 최신 파일에서 로드된 역할 taxonomy 설정
    """
    config_path = _resolve_config_path()
    latest_mtime_ns = _resolve_file_mtime_ns(config_path=config_path)
    with _CACHE_LOCK:
        cached = _read_cached_config(config_path=config_path, mtime_ns=latest_mtime_ns)
        if cached is not None:
            return cached
        loaded = _load_role_taxonomy(config_path=config_path)
        _write_cache(config_path=config_path, mtime_ns=latest_mtime_ns, config=loaded)
        return loaded


def reset_role_taxonomy_cache() -> None:
    """역할 taxonomy 캐시를 초기화한다.

    Returns:
        없음
    """
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_VALUE
    with _CACHE_LOCK:
        _CACHE_PATH = ""
        _CACHE_MTIME_NS = -1
        _CACHE_VALUE = None


def _resolve_config_path() -> str:
    """역할 taxonomy 설정 파일 경로를 계산한다.

    Returns:
        설정 파일 절대 경로 문자열
    """
    env_path = str(os.getenv("ROLE_TAXONOMY_CONFIG_PATH") or "").strip()
    if env_path:
        return str(Path(env_path).expanduser().resolve())
    project_root = Path(__file__).resolve().parents[2]
    return str((project_root / "config" / "role_taxonomy.json").resolve())


def _resolve_file_mtime_ns(config_path: str) -> int:
    """설정 파일 mtime(ns)를 조회한다.

    Args:
        config_path: 설정 파일 경로

    Returns:
        mtime(ns). 파일이 없으면 -1
    """
    try:
        return int(Path(config_path).stat().st_mtime_ns)
    except OSError:
        return -1


def _read_cached_config(config_path: str, mtime_ns: int) -> RoleTaxonomyConfig | None:
    """현재 캐시가 유효하면 반환한다.

    Args:
        config_path: 설정 파일 경로
        mtime_ns: 최신 mtime(ns)

    Returns:
        유효 캐시 또는 None
    """
    if _CACHE_VALUE is None:
        return None
    if _CACHE_PATH != config_path:
        return None
    if _CACHE_MTIME_NS != mtime_ns:
        return None
    return _CACHE_VALUE


def _write_cache(config_path: str, mtime_ns: int, config: RoleTaxonomyConfig) -> None:
    """설정 캐시를 갱신한다.

    Args:
        config_path: 설정 파일 경로
        mtime_ns: 파일 mtime(ns)
        config: 로드한 설정 모델

    Returns:
        없음
    """
    global _CACHE_PATH, _CACHE_MTIME_NS, _CACHE_VALUE
    _CACHE_PATH = config_path
    _CACHE_MTIME_NS = mtime_ns
    _CACHE_VALUE = config


def _load_role_taxonomy(config_path: str) -> RoleTaxonomyConfig:
    """설정 파일을 읽어 taxonomy 모델을 생성한다.

    Args:
        config_path: 설정 파일 경로

    Returns:
        파싱된 설정 모델. 실패 시 기본 설정 모델
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("role_taxonomy_config.load_missing: path=%s", config_path)
        return _build_default_config(source_path=config_path)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _parse_role_taxonomy_payload(payload=payload, source_path=config_path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        logger.error("role_taxonomy_config.load_failed: path=%s error=%s", config_path, error)
        return _build_default_config(source_path=config_path)


def _parse_role_taxonomy_payload(payload: object, source_path: str) -> RoleTaxonomyConfig:
    """JSON payload를 RoleTaxonomyConfig로 변환한다.

    Args:
        payload: 파싱 대상 payload
        source_path: 설정 파일 경로

    Returns:
        검증된 설정 모델

    Raises:
        ValueError: payload 구조가 유효하지 않을 때
    """
    if not isinstance(payload, dict):
        raise ValueError("role taxonomy payload must be a JSON object")

    raw_default_roles = payload.get("default_roles")
    default_roles = _parse_default_roles(raw_default_roles=raw_default_roles)

    raw_role_hints = payload.get("role_hints")
    role_hints = _parse_role_hints(raw_role_hints=raw_role_hints)

    return RoleTaxonomyConfig(
        role_hints=tuple(role_hints),
        default_roles=default_roles,
        source_path=source_path,
    )


def _parse_default_roles(raw_default_roles: object) -> dict[str, str]:
    """default_roles payload를 정규화한다.

    Args:
        raw_default_roles: JSON `default_roles` 원본 값

    Returns:
        정규화된 기본 역할 맵
    """
    normalized = dict(DEFAULT_ROLES)
    if not isinstance(raw_default_roles, dict):
        return normalized

    for key in ("to", "cc", "unknown"):
        value = str(raw_default_roles.get(key) or "").strip()
        if value:
            normalized[key] = value
    return normalized


def _parse_role_hints(raw_role_hints: object) -> list[RoleHint]:
    """role_hints payload를 정규화한다.

    Args:
        raw_role_hints: JSON `role_hints` 원본 값

    Returns:
        정규화된 RoleHint 목록
    """
    if not isinstance(raw_role_hints, list):
        return [RoleHint(keyword=keyword, role=role) for keyword, role in DEFAULT_ROLE_HINTS]

    parsed: list[RoleHint] = []
    for item in raw_role_hints:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword") or "").strip()
        role = str(item.get("role") or "").strip()
        if not keyword or not role:
            continue
        parsed.append(RoleHint(keyword=keyword.lower(), role=role))

    if parsed:
        return parsed
    return [RoleHint(keyword=keyword, role=role) for keyword, role in DEFAULT_ROLE_HINTS]


def _build_default_config(source_path: str) -> RoleTaxonomyConfig:
    """기본 역할 taxonomy 설정 모델을 생성한다.

    Args:
        source_path: 설정 파일 경로

    Returns:
        기본 설정 모델
    """
    return RoleTaxonomyConfig(
        role_hints=tuple(RoleHint(keyword=keyword, role=role) for keyword, role in DEFAULT_ROLE_HINTS),
        default_roles=dict(DEFAULT_ROLES),
        source_path=source_path,
    )
