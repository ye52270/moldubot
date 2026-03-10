from __future__ import annotations

from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_summary import extract_summary_lines, sanitize_summary_lines

CAUSE_FALLBACK = "원인 정보를 확인하지 못했습니다."
IMPACT_FALLBACK = "영향 정보를 확인하지 못했습니다."
RESPONSE_FALLBACK = "대응 방안을 확인하지 못했습니다."
LOW_VALUE_PREFIXES: tuple[str, ...] = ("분석 요청", "설명 요청", "정리 요청")
TECH_KEYWORDS: tuple[str, ...] = ("db", "database", "연결", "ca", "인증서", "로그", "권한", "계정")
IMPACT_DOMINANT_TOKENS: tuple[str, ...] = ("영향", "우려", "차질", "리스크", "불가", "중단", "지연")
IMPACT_CONDITION_TOKENS: tuple[str, ...] = ("경우", "시", "하면", "될 경우", "가능성")
RESPONSE_ACTION_TOKENS: tuple[str, ...] = (
    "점검",
    "확인",
    "검증",
    "설치",
    "수집",
    "분석",
    "재시도",
    "재배포",
    "설정",
    "수정",
    "적용",
    "복구",
    "롤백",
    "문의",
    "협의",
    "교체",
)


def render_issue_analysis_sections(contract: LLMResponseContract, sections: tuple[str, ...]) -> str:
    """
    현재메일 이슈 분석 계약을 섹션 계약 기반으로 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약
        sections: 요청 섹션 ID 튜플(`cause`, `impact`, `response`)

    Returns:
        섹션형 문자열
    """
    section_ids = tuple(item for item in sections if item in {"cause", "impact", "response"})
    if not section_ids:
        return ""
    lines = _collect_contract_lines(contract=contract)
    grouped = _classify_issue_lines(lines=lines)
    if "cause" in section_ids:
        grouped["cause"] = _supplement_cause_lines(contract=contract, grouped=grouped)
    if "impact" in section_ids and not grouped["impact"]:
        grouped["impact"] = [line for line in grouped["leftover"] if line not in grouped["cause"]][:2]
    if "response" in section_ids and not grouped["response"]:
        grouped["response"] = sanitize_summary_lines(lines=list(contract.required_actions) + list(contract.action_items))
    if "response" in section_ids:
        grouped["response"] = _augment_with_technical_review(
            response_lines=grouped["response"],
            source_lines=lines,
        )

    blocks: list[str] = []
    if "cause" in section_ids:
        cause_lines = grouped["cause"][:4] if grouped["cause"] else [CAUSE_FALLBACK]
        blocks.extend(["## 원인", "", *[f"- {line}" for line in cause_lines], ""])
    if "impact" in section_ids:
        impact_lines = grouped["impact"][:4] if grouped["impact"] else [IMPACT_FALLBACK]
        blocks.extend(["## 영향", "", *[f"- {line}" for line in impact_lines], ""])
    if "response" in section_ids:
        response_lines = grouped["response"][:5] if grouped["response"] else [RESPONSE_FALLBACK]
        blocks.extend(["## 대응방안", "", *[f"{index}. {line}" for index, line in enumerate(response_lines, start=1)]])
    return "\n".join(blocks).strip()


def _collect_contract_lines(contract: LLMResponseContract) -> list[str]:
    """
    이슈 분석 분류에 사용할 계약 라인을 수집한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        중복 제거된 라인 목록
    """
    candidates: list[str] = []
    candidates.extend(sanitize_summary_lines(lines=list(contract.summary_lines)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.major_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.key_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.required_actions)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.action_items)))
    candidates.extend(extract_summary_lines(answer=contract.answer))
    unique: list[str] = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text or text in unique:
            continue
        if _is_low_value_issue_line(text=text):
            continue
        unique.append(text)
    return unique


def _classify_issue_lines(lines: list[str]) -> dict[str, list[str]]:
    """
    라인 목록을 원인/영향/대응/기타로 분류한다.

    Args:
        lines: 원본 라인 목록

    Returns:
        분류 사전
    """
    grouped = {"cause": [], "impact": [], "response": [], "leftover": []}
    for line in lines:
        text = str(line or "").strip()
        is_cause = _looks_like_cause_line(text=text)
        is_impact = _looks_like_impact_line(text=text)
        is_response = _looks_like_response_line(text=text)
        if is_response:
            _append_unique(grouped["response"], text)
            continue
        if is_cause:
            _append_unique(grouped["cause"], text)
            continue
        if is_impact:
            _append_unique(grouped["impact"], text)
            continue
        _append_unique(grouped["leftover"], text)
    return grouped


def _append_unique(lines: list[str], value: str) -> None:
    """
    리스트에 문자열을 중복 없이 추가한다.

    Args:
        lines: 대상 문자열 리스트
        value: 추가할 문자열
    """
    text = str(value or "").strip()
    if text and text not in lines:
        lines.append(text)


def _is_low_value_issue_line(text: str) -> bool:
    """
    정보 밀도가 낮은 이슈 문장인지 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        저품질 문장이면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return True
    compact = normalized.replace(" ", "")
    if any(compact.startswith(prefix.replace(" ", "")) for prefix in LOW_VALUE_PREFIXES):
        return True
    return False


def _looks_like_cause_line(text: str) -> bool:
    """
    원인 설명 문장인지 휴리스틱으로 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        원인 문장이면 True
    """
    compact = str(text or "")
    return any(token in compact for token in ("원인", "이유", "문제", "오류", "실패", "누락", "불일치", "미비", "만료"))


def _looks_like_impact_line(text: str) -> bool:
    """
    영향 설명 문장인지 휴리스틱으로 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        영향 문장이면 True
    """
    compact = str(text or "")
    return any(token in compact for token in ("영향", "지연", "리스크", "차질", "장애", "반송", "불가"))


def _looks_like_response_line(text: str) -> bool:
    """
    대응방안 문장인지 휴리스틱으로 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        대응 문장이면 True
    """
    compact = str(text or "")
    has_response_token = any(
        token in compact for token in ("대응", "조치", "점검", "확인", "재시도", "재배포", "재발급")
    )
    if not has_response_token:
        return False
    if _is_impact_dominant_sentence(text=compact):
        return False
    if not any(token in compact for token in RESPONSE_ACTION_TOKENS):
        return False
    return True


def _augment_with_technical_review(response_lines: list[str], source_lines: list[str]) -> list[str]:
    """
    대응 라인에 기술 검토 체크리스트를 보강한다.

    Args:
        response_lines: 기존 대응 라인 목록
        source_lines: 원본 이슈 라인 목록

    Returns:
        기술 검토 항목이 보강된 대응 라인 목록
    """
    normalized = _sanitize_response_lines(response_lines=response_lines)
    review_items = _build_technical_review_items(source_lines=source_lines)
    merged: list[str] = []
    for item in normalized + review_items:
        if item not in merged:
            merged.append(item)
    return merged


def _supplement_cause_lines(
    contract: LLMResponseContract,
    grouped: dict[str, list[str]],
) -> list[str]:
    """
    원인 섹션이 과도하게 축약되지 않도록 원인 후보 라인을 보강한다.

    Args:
        contract: 파싱된 LLM 응답 계약
        grouped: 분류된 라인 집합

    Returns:
        보강된 원인 라인 목록
    """
    cause_lines = list(grouped["cause"])
    core_issue = str(contract.core_issue or "").strip()
    if core_issue:
        _append_unique(cause_lines, core_issue)
    candidates = sanitize_summary_lines(lines=list(contract.major_points) + list(contract.summary_lines))
    for candidate in candidates:
        if len(cause_lines) >= 2:
            break
        text = str(candidate or "").strip()
        if not text or text in cause_lines or text in grouped["response"]:
            continue
        if _looks_like_response_line(text=text):
            continue
        if _looks_like_cause_line(text=text) or ("설치" in text and "필요" in text):
            _append_unique(cause_lines, text)
    return cause_lines


def _sanitize_response_lines(response_lines: list[str]) -> list[str]:
    """
    대응방안 후보 라인을 정제해 저품질/영향성 문장을 제거한다.

    Args:
        response_lines: 기존 대응 라인 목록

    Returns:
        정제된 대응 라인 목록
    """
    normalized: list[str] = []
    for line in response_lines:
        text = str(line or "").strip()
        if not text:
            continue
        if _is_impact_dominant_sentence(text=text):
            continue
        if _is_low_value_issue_line(text=text):
            continue
        if not any(token in text for token in RESPONSE_ACTION_TOKENS):
            continue
        if text not in normalized:
            normalized.append(text)
    return normalized


def _is_impact_dominant_sentence(text: str) -> bool:
    """
    문장이 영향/우려 설명 위주인지 판별한다.

    Args:
        text: 검사 대상 문장

    Returns:
        영향 중심 문장이면 True
    """
    compact = str(text or "").strip()
    has_impact = any(token in compact for token in IMPACT_DOMINANT_TOKENS)
    has_condition = any(token in compact for token in IMPACT_CONDITION_TOKENS)
    has_action = any(token in compact for token in RESPONSE_ACTION_TOKENS)
    if not has_impact:
        return False
    if has_condition:
        return True
    return not has_action


def _build_technical_review_items(source_lines: list[str]) -> list[str]:
    """
    이슈 라인에서 기술 검토 체크리스트를 도출한다.

    Args:
        source_lines: 원본 이슈 라인 목록

    Returns:
        기술 검토 항목 목록
    """
    joined = " ".join([str(line or "").lower() for line in source_lines])
    if not any(keyword in joined for keyword in TECH_KEYWORDS):
        return []
    items: list[str] = []
    if "db" in joined or "database" in joined or "연결" in joined:
        items.append("기술 검토: DB 접속 경로/포트/방화벽 정책과 타임아웃 설정을 점검합니다.")
    if "ca" in joined or "인증서" in joined:
        items.append("기술 검토: 서버 인증서 체인(CA 루트/중간) 설치 및 신뢰 저장소 반영 여부를 검증합니다.")
    if "로그" in joined or "오류" in joined or "실패" in joined:
        items.append("기술 검토: 애플리케이션·DB 로그의 오류코드/발생시각을 대조해 재현 경로를 확정합니다.")
    if "권한" in joined or "계정" in joined:
        items.append("기술 검토: 접속 계정 권한, 비밀번호 만료, 인증 정책(SSO/LDAP) 변경 이력을 확인합니다.")
    if not items:
        items.append("기술 검토: 오류코드·스택트레이스·네트워크 경로를 수집해 원인 후보를 축소합니다.")
    return items[:3]
