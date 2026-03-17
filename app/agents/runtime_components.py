from __future__ import annotations

import importlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.memory import InMemorySaver

from app.core.logging_config import get_logger

DEFAULT_CHECKPOINTER_BACKEND = "memory"
DEFAULT_CHECKPOINTER_SQLITE_PATH = Path("data/sqlite/langgraph_checkpoints.db")
SQLITE_CHECKPOINTER_MODULE = "langgraph.checkpoint.sqlite"
SQLITE_SAVER_CLASS_NAME = "SqliteSaver"

logger = get_logger(__name__)
_CHECKPOINTER_RESOURCE_STACK: list[Any] = []


def build_agent_backend(skills_paths: Sequence[str] | None = None) -> FilesystemBackend | None:
    """
    Deep Agents skills 로딩에 사용할 backend를 구성한다.

    Args:
        skills_paths: 활성화할 skills 경로 목록

    Returns:
        skills 경로가 있으면 FilesystemBackend, 없으면 None
    """
    normalized_paths = [str(path or "").strip() for path in skills_paths or [] if str(path or "").strip()]
    if not normalized_paths:
        return None
    root_dir = Path(os.getenv("MOLDUBOT_AGENT_BACKEND_ROOT", ".")).resolve()
    return FilesystemBackend(root_dir=str(root_dir), virtual_mode=True)


def build_agent_checkpointer(cache_namespace: str = "default") -> Any:
    """
    환경설정에 따라 Deep Agent checkpointer를 생성한다.

    Args:
        cache_namespace: 프롬프트 variant 등 캐시 분리 키

    Returns:
        LangGraph checkpointer 인스턴스
    """
    backend_name = str(
        os.getenv("MOLDUBOT_AGENT_CHECKPOINTER_BACKEND", DEFAULT_CHECKPOINTER_BACKEND),
    ).strip().lower() or DEFAULT_CHECKPOINTER_BACKEND
    sqlite_path = str(
        Path(
            os.getenv(
                "MOLDUBOT_AGENT_CHECKPOINTER_SQLITE_PATH",
                str(DEFAULT_CHECKPOINTER_SQLITE_PATH),
            ),
        ).resolve(),
    )
    return _build_agent_checkpointer_cached(
        cache_namespace=cache_namespace,
        backend_name=backend_name,
        sqlite_path=sqlite_path,
    )


@lru_cache(maxsize=16)
def _build_agent_checkpointer_cached(
    cache_namespace: str,
    backend_name: str,
    sqlite_path: str,
) -> Any:
    """
    checkpointer 생성 결과를 설정 단위로 캐시한다.

    Args:
        cache_namespace: 프롬프트 variant 등 캐시 분리 키
        backend_name: `memory|sqlite`
        sqlite_path: sqlite 파일 경로

    Returns:
        LangGraph checkpointer 인스턴스
    """
    del cache_namespace
    if backend_name == "sqlite":
        sqlite_checkpointer = _build_sqlite_checkpointer(sqlite_path=sqlite_path)
        if sqlite_checkpointer is not None:
            return sqlite_checkpointer
        logger.warning("agent.checkpointer sqlite 초기화 실패로 InMemorySaver로 폴백")
    return InMemorySaver()


def _build_sqlite_checkpointer(sqlite_path: str) -> Any | None:
    """
    optional sqlite checkpointer를 생성한다.

    Args:
        sqlite_path: sqlite 파일 경로

    Returns:
        생성된 sqlite saver 또는 None
    """
    try:
        module = importlib.import_module(SQLITE_CHECKPOINTER_MODULE)
    except ModuleNotFoundError:
        logger.warning("agent.checkpointer sqlite 모듈이 없어 persistent memory를 비활성화합니다")
        return None
    saver_class = getattr(module, SQLITE_SAVER_CLASS_NAME, None)
    if saver_class is None:
        logger.warning("agent.checkpointer sqlite saver 클래스를 찾지 못했습니다")
        return None

    target_path = Path(sqlite_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    path_text = str(target_path)

    from_conn_string = getattr(saver_class, "from_conn_string", None)
    if callable(from_conn_string):
        saver = from_conn_string(path_text)
        return _materialize_checkpointer_resource(saver)

    from_path = getattr(saver_class, "from_path", None)
    if callable(from_path):
        saver = from_path(path_text)
        return _materialize_checkpointer_resource(saver)

    try:
        saver = saver_class(path_text)
        return _materialize_checkpointer_resource(saver)
    except TypeError:
        logger.warning("agent.checkpointer sqlite saver 생성 시그니처를 해석하지 못했습니다")
        return None


def _materialize_checkpointer_resource(resource: Any) -> Any:
    """
    context manager 형태의 saver를 실제 checkpointer 객체로 해석한다.

    Args:
        resource: saver 또는 context manager

    Returns:
        실제 사용 가능한 checkpointer 객체
    """
    enter = getattr(resource, "__enter__", None)
    exit_ = getattr(resource, "__exit__", None)
    if callable(enter) and callable(exit_):
        resolved = enter()
        _CHECKPOINTER_RESOURCE_STACK.append(resource)
        return resolved
    return resource
