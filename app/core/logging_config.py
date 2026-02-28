from __future__ import annotations

import logging
import os
from logging.config import dictConfig

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _normalize_log_level(raw_level: str) -> str:
    """
    입력된 로그 레벨 문자열을 표준 대문자 형태로 정규화한다.

    Args:
        raw_level: 환경변수나 외부 입력으로 전달된 로그 레벨 문자열

    Returns:
        logging 모듈이 이해할 수 있는 대문자 로그 레벨 문자열
    """
    level = str(raw_level or "").strip().upper()
    valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
    if level in valid_levels:
        return level
    return DEFAULT_LOG_LEVEL


def configure_logging() -> None:
    """
    애플리케이션 전역 공통 로깅 포맷/레벨/핸들러를 초기화한다.

    Returns:
        없음
    """
    # 운영 환경에서 동적으로 레벨을 제어할 수 있도록 환경변수 값을 우선 사용한다.
    log_level = _normalize_log_level(os.getenv("MOLDUBOT_LOG_LEVEL", DEFAULT_LOG_LEVEL))
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": DEFAULT_LOG_FORMAT,
                "datefmt": DEFAULT_LOG_DATE_FORMAT,
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "standard",
            }
        },
        "root": {
            "level": log_level,
            "handlers": ["console"],
        },
    }
    dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """
    공통 설정을 따르는 모듈 로거를 반환한다.

    Args:
        name: 로거 이름(일반적으로 `__name__`)

    Returns:
        설정된 logging.Logger 인스턴스
    """
    return logging.getLogger(name)
