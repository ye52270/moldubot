from __future__ import annotations

from typing import Any

from app.agents.intent_parser import get_intent_parser
from app.agents.intent_schema import IntentDecomposition
from app.core.logging_config import get_logger

SCOPE_PREFIX = "[질의 범위]"
CURRENT_MAIL_SCOPE_TOKEN = "현재 선택 메일"

logger = get_logger(__name__)


def is_current_mail_scope_value(scope_value: str) -> bool:
    """
    resolved scope 문자열이 current_mail인지 판별한다.

    Args:
        scope_value: resolved scope 문자열

    Returns:
        current_mail이면 True
    """
    return str(scope_value or "").strip().lower() == "current_mail"


def is_current_mail_scope_label(scope_label: str) -> bool:
    """
    scope 라벨이 현재 선택 메일 범위를 가리키는지 판별한다.

    Args:
        scope_label: 주입된 scope 라벨 문자열

    Returns:
        현재 선택 메일 범위면 True
    """
    normalized_scope = str(scope_label or "").strip()
    return normalized_scope.startswith(SCOPE_PREFIX) and (CURRENT_MAIL_SCOPE_TOKEN in normalized_scope)


def build_intent_namespace_kwargs(scope_label: str) -> dict[str, bool]:
    """
    scope 라벨에서 intent parser namespace 인자를 계산한다.

    Args:
        scope_label: 주입된 scope 라벨 문자열

    Returns:
        parser.parse 호출용 namespace 인자 사전
    """
    has_selected_mail_scope = is_current_mail_scope_label(scope_label=scope_label)
    return {
        "has_selected_mail": has_selected_mail_scope,
        "selected_message_id_exists": has_selected_mail_scope,
    }


def parse_intent_decomposition_safely(
    user_message: str,
    parser_factory: Any = get_intent_parser,
    has_selected_mail: bool = False,
    selected_message_id_exists: bool = False,
) -> IntentDecomposition | None:
    """
    라우팅 보조용 intent 구조분해를 안전하게 파싱한다.

    Args:
        user_message: 사용자 질의
        parser_factory: 파서 팩토리(테스트 주입용)
        has_selected_mail: selected_mail namespace 플래그
        selected_message_id_exists: selected_message_id namespace 플래그

    Returns:
        파싱 성공 시 IntentDecomposition, 실패 시 None
    """
    normalized = str(user_message or "").strip()
    if not normalized:
        return None
    try:
        parser = parser_factory() if callable(parser_factory) else get_intent_parser()
        try:
            return parser.parse(
                user_message=normalized,
                has_selected_mail=has_selected_mail,
                selected_message_id_exists=selected_message_id_exists,
            )
        except TypeError:
            return parser.parse(user_message=normalized)
    except Exception as exc:
        logger.warning("intent 구조분해 파싱 실패: %s", exc)
        return None


def parse_intent_with_scope_label(user_message: str, scope_label: str) -> IntentDecomposition:
    """
    scope 라벨 namespace를 반영해 intent parser를 호출한다.

    Args:
        user_message: scope prefix 제거된 사용자 질의
        scope_label: 주입된 scope 라벨

    Returns:
        intent 구조분해 결과
    """
    parser = get_intent_parser()
    parse_kwargs = build_intent_namespace_kwargs(scope_label=scope_label)
    try:
        return parser.parse(user_message=user_message, **parse_kwargs)
    except TypeError:
        return parser.parse(user_message=user_message)
