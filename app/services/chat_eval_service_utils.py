from __future__ import annotations

import json
import re
import time
from dataclasses import asdict
from datetime import datetime
from statistics import mean
from typing import Any
from urllib import error, request

from app.core.llm_runtime import invoke_text_messages, resolve_env_model
from app.core.logging_config import get_logger
from app.services.chat_eval_quality_metrics import build_quality_metrics

logger = get_logger(__name__)

ACTION_ITEM_QUERY_TOKEN = "액션 아이템"
ACTION_ITEM_LIST_REGEX = re.compile(r"(?:^|\n)\s*(?:\d+\.\s+\S+|[-*•]\s+\S+)")
GROUNDING_TOKEN_REGEX = re.compile(r"[가-힣A-Za-z0-9]{2,}")
GROUNDING_STOPWORDS = {
    "메일",
    "조회",
    "검색",
    "관련",
    "최근",
    "지난",
    "요약",
    "정리",
    "해주세요",
    "해줘",
    "the",
    "and",
    "for",
    "from",
    "with",
}
EVIDENCE_TOP_K = 5
JUDGE_RAW_LOG_MAX_CHARS = 1200
_EVIDENCE_SNIPPET_FALLBACK_KEYS: tuple[str, ...] = (
    "snippet",
    "summary_text",
    "body_excerpt",
    "body_preview",
)


def default_chat_caller(
    chat_url: str,
    payload: dict[str, Any],
    timeout_sec: int,
) -> tuple[int, dict[str, Any], float, str | None]:
    """`/search/chat` 엔드포인트를 HTTP로 호출한다."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        chat_url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            status_code = int(resp.getcode())
            data = json.loads(resp.read().decode("utf-8"))
            return status_code, data, elapsed_ms, None
    except error.URLError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.warning("chat_eval.chat_call_failed: url=%s error=%s", chat_url, exc)
        return 0, {}, elapsed_ms, str(exc)
    except json.JSONDecodeError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.warning("chat_eval.chat_parse_failed: url=%s error=%s", chat_url, exc)
        return 0, {}, elapsed_ms, f"json_decode_error: {exc}"


def build_default_judge_caller(judge_model: str) -> Any:
    """LLM Judge 호출 함수를 생성한다."""
    resolved_model = resolve_env_model(
        primary_env="MOLDUBOT_JUDGE_MODEL",
        fallback_envs=(),
        default_model=judge_model,
    )

    def _judge(
        query: str,
        answer: str,
        expectation: str,
        source: str,
        judge_context: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        """단일 응답을 채점한다."""
        started = time.perf_counter()
        system_prompt = (
            "당신은 한국어 챗봇 E2E 품질 심사관이다. "
            "아래 입력을 보고 반드시 JSON 객체로만 평가를 반환하라. "
            "키는 pass(bool), score(1~5 int), reason(str), "
            "checks(object: intent_match bool, format_match bool, grounded bool)만 사용한다."
        )
        user_prompt = json.dumps(
            {
                "query": query,
                "answer": answer,
                "expectation": expectation,
                "source": source,
                "judge_context": judge_context,
                "rubric": {
                    "intent_match": "질문 의도를 충족했는지",
                    "format_match": "요약 줄수/표/보고서 등 형식 요구를 반영했는지",
                    "grounded": "근거 없이 꾸며내지 않았는지(모르면 모른다고 표현)",
                },
            },
            ensure_ascii=False,
        )
        parsed = _run_judge_once(model_name=resolved_model, system_prompt=system_prompt, user_prompt=user_prompt)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        return parsed, elapsed_ms

    return _judge


def _run_judge_once(model_name: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    """Judge LLM 응답 1회를 실행하고 파싱한다."""
    try:
        raw_text = invoke_text_messages(
            model_name=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout_sec=60,
        )
        logger.info(
            "chat_eval.judge_raw_response: length=%s content=%s",
            len(str(raw_text or "")),
            _truncate_log_text(text=raw_text, max_chars=JUDGE_RAW_LOG_MAX_CHARS),
        )
        return normalize_judge_result(raw_result=_extract_json_payload(raw_text=raw_text))
    except (ValueError, json.JSONDecodeError, TypeError, KeyError) as exc:
        logger.warning("chat_eval.judge_parse_failed: error=%s", exc)
        return judge_failure(reason=f"judge_parse_error: {exc}")
    except Exception as exc:  # pragma: no cover - runtime/provider error
        logger.warning("chat_eval.judge_llm_failed: error=%s", exc)
        return judge_failure(reason=f"judge_llm_error: {exc}")


def _extract_json_payload(raw_text: str) -> str:
    """Judge 응답에서 JSON 객체 문자열을 추출한다."""
    compact = str(raw_text or "").strip()
    if not compact:
        raise ValueError("empty_judge_response")
    if compact.startswith("```"):
        lines = compact.splitlines()
        compact = "\n".join(lines[1:-1] if len(lines) >= 2 else lines).strip()
    if compact.startswith("{") and compact.endswith("}"):
        return compact
    match = re.search(r"\{.*\}", compact, flags=re.DOTALL)
    if not match:
        raise ValueError("json_object_not_found")
    return match.group(0)


def _truncate_log_text(text: str, max_chars: int) -> str:
    """로그 길이 제한을 적용한다."""
    compact = str(text or "")
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}...(truncated)"


def normalize_judge_result(raw_result: str) -> dict[str, Any]:
    """Judge 원문을 표준 JSON 구조로 정규화한다."""
    try:
        parsed = json.loads(raw_result)
    except json.JSONDecodeError:
        return judge_failure(reason="judge_json_decode_error")

    if not isinstance(parsed, dict):
        return judge_failure(reason="judge_payload_not_object")

    checks = parsed.get("checks") if isinstance(parsed.get("checks"), dict) else {}
    try:
        score = max(1, min(int(parsed.get("score")), 5))
    except (TypeError, ValueError):
        score = 1
    return {
        "pass": bool(parsed.get("pass")),
        "score": score,
        "reason": str(parsed.get("reason") or ""),
        "checks": {
            "intent_match": bool(checks.get("intent_match")),
            "format_match": bool(checks.get("format_match")),
            "grounded": bool(checks.get("grounded")),
        },
    }


def judge_failure(reason: str) -> dict[str, Any]:
    """Judge 실패 결과를 생성한다."""
    return {
        "pass": False,
        "score": 1,
        "reason": reason,
        "checks": {
            "intent_match": False,
            "format_match": False,
            "grounded": False,
        },
    }


def build_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    chat_url: str,
    judge_model: str,
    selected_email_id: str,
    mailbox_user: str,
    case_results: list[Any],
) -> dict[str, Any]:
    """케이스 실행 결과를 최종 리포트로 집계한다."""
    passed_count = sum(1 for item in case_results if bool(item.judge.get("pass")))
    total = len(case_results)
    chat_elapsed = [item.elapsed_ms for item in case_results]
    judge_elapsed = [item.judge_elapsed_ms for item in case_results]
    judge_scores = [int(item.judge.get("score", 1)) for item in case_results]
    quality_metrics = build_quality_metrics(per_case=[{"query": item.query, "answer": item.answer} for item in case_results])

    return {
        "meta": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_sec": round((finished_at - started_at).total_seconds(), 2),
            "chat_url": chat_url,
            "judge_model": judge_model,
            "selected_email_id_provided": bool(selected_email_id),
            "mailbox_user_provided": bool(mailbox_user),
        },
        "summary": {
            "total_cases": total,
            "passed_cases": passed_count,
            "judge_pass_rate": round((passed_count / total) * 100, 1) if total else 0.0,
            "avg_judge_score": round(mean(judge_scores), 2) if judge_scores else 0.0,
            "avg_chat_elapsed_ms": round(mean(chat_elapsed), 1) if chat_elapsed else 0.0,
            "avg_judge_elapsed_ms": round(mean(judge_elapsed), 1) if judge_elapsed else 0.0,
            "max_chat_elapsed_ms": max(chat_elapsed) if chat_elapsed else 0.0,
            "min_chat_elapsed_ms": min(chat_elapsed) if chat_elapsed else 0.0,
            **quality_metrics,
        },
        "cases": [asdict(item) for item in case_results],
    }


def build_judge_context(metadata: dict[str, Any]) -> dict[str, Any]:
    """Judge 입력용 실행 컨텍스트를 메타데이터에서 구성한다."""
    evidence = metadata.get("evidence_mails")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    raw_result_count = metadata.get("search_result_count")
    search_result_count = int(raw_result_count) if isinstance(raw_result_count, int) else evidence_count
    evidence_top_k = extract_evidence_top_k(metadata=metadata, top_k=EVIDENCE_TOP_K)
    return {
        "search_result_count": max(0, search_result_count),
        "evidence_count": max(0, max(evidence_count, search_result_count)),
        "source": str(metadata.get("source") or ""),
        "query_type": str(metadata.get("query_type") or ""),
        "resolved_scope": str(metadata.get("resolved_scope") or ""),
        "used_current_mail_context": bool(metadata.get("used_current_mail_context")),
        "evidence_top_k": evidence_top_k,
    }


def resolve_visible_answer(raw_answer: str, metadata: dict[str, Any]) -> str:
    """Judge 입력용 답변 텍스트를 화면 표시 기준으로 정규화한다."""
    raw = str(raw_answer or "").strip()
    answer_format = metadata.get("answer_format") if isinstance(metadata, dict) else None
    blocks = answer_format.get("blocks") if isinstance(answer_format, dict) else None
    if not isinstance(blocks, list) or not blocks:
        return raw
    rendered = render_answer_blocks_to_text(blocks=blocks)
    return rendered or raw


def render_answer_blocks_to_text(blocks: list[Any]) -> str:
    """answer_format blocks를 텍스트로 평탄화한다."""
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type in {"heading", "paragraph", "quote"}:
            text = normalize_visible_text(str(block.get("text") or ""))
            if text:
                lines.append(text)
            continue
        if block_type in {"ordered_list", "unordered_list"}:
            items = block.get("items")
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items, start=1):
                text = normalize_visible_text(str(item or ""))
                if not text:
                    continue
                prefix = f"{index}. " if block_type == "ordered_list" else "- "
                lines.append(f"{prefix}{text}")
            continue
        if block_type == "table":
            _append_table_rows(lines=lines, block=block)
    return "\n".join(lines).strip()


def _append_table_rows(lines: list[str], block: dict[str, Any]) -> None:
    """table block을 텍스트 라인으로 추가한다."""
    headers = block.get("headers")
    rows = block.get("rows")
    if not isinstance(headers, list) or not isinstance(rows, list):
        return
    normalized_headers = [normalize_visible_text(str(header or "")) for header in headers]
    for row in rows:
        if not isinstance(row, list):
            continue
        parts: list[str] = []
        for idx, header in enumerate(normalized_headers):
            value = normalize_visible_text(str(row[idx] if idx < len(row) else ""))
            if not header and not value:
                continue
            parts.append(f"{header}: {value}" if header else value)
        if parts:
            lines.append(" | ".join(parts))


def normalize_visible_text(text: str) -> str:
    """markdown/공백을 화면 표시형 텍스트로 정규화한다."""
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", value)
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = re.sub(r"`(.+?)`", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_evidence_top_k(metadata: dict[str, Any], top_k: int) -> list[dict[str, str]]:
    """metadata.evidence_mails에서 judge 전달용 top-k 근거 요약을 추출한다."""
    evidence = metadata.get("evidence_mails")
    if not isinstance(evidence, list):
        return []
    extracted: list[dict[str, str]] = []
    for item in evidence[: max(0, top_k)]:
        if not isinstance(item, dict):
            continue
        extracted.append(
            {
                "subject": str(item.get("subject") or "").strip(),
                "snippet": extract_evidence_snippet(item=item),
                "received_date": str(item.get("received_date") or "").strip(),
            }
        )
    return extracted


def extract_evidence_snippet(item: dict[str, Any]) -> str:
    """evidence 메일 항목에서 Judge 표시용 스니펫을 추출한다."""
    for key in _EVIDENCE_SNIPPET_FALLBACK_KEYS:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return str(item.get("subject") or "").strip()


def rule_based_no_result_judge(
    query: str,
    answer: str,
    judge_context: dict[str, Any],
) -> dict[str, Any] | None:
    """조회 0건 케이스를 규칙 기반으로 선판정한다."""
    if int(judge_context.get("search_result_count") or 0) != 0:
        return None
    if "메일" not in str(query or ""):
        return None
    answer_text = str(answer or "")
    no_result_tokens = ("조건에 맞는 메일이 없습니다", "관련 메일이 없", "조회 결과: 조건에 맞는 메일이 없습니다")
    if not any(token in answer_text for token in no_result_tokens):
        return None
    return {
        "pass": True,
        "score": 4,
        "reason": "조회 결과가 0건으로 확인되어 부재 안내 응답을 적절히 반환했습니다.",
        "checks": {"intent_match": True, "format_match": True, "grounded": True},
    }


def rule_based_format_guard(query: str, answer: str) -> dict[str, Any] | None:
    """형식 강제 질의에 대한 최소 요건을 규칙 기반으로 선검증한다."""
    if ACTION_ITEM_QUERY_TOKEN not in str(query or ""):
        return None
    if ACTION_ITEM_LIST_REGEX.search(str(answer or "")):
        return None
    return {
        "pass": False,
        "score": 1,
        "reason": "액션 아이템 요청이지만 실행 항목 목록(번호/불릿)이 없어 형식 요구를 충족하지 못했습니다.",
        "checks": {"intent_match": False, "format_match": False, "grounded": True},
    }


def rule_based_retrieval_grounding_guard(
    query: str,
    answer: str,
    judge_context: dict[str, Any],
) -> dict[str, Any] | None:
    """retrieval 질의에서 답변-근거 불일치를 규칙 기반으로 선판정한다."""
    query_type = str(judge_context.get("query_type") or "").strip().lower()
    resolved_scope = str(judge_context.get("resolved_scope") or "").strip().lower()
    if query_type == "current_mail" or resolved_scope == "current_mail" or bool(judge_context.get("used_current_mail_context")):
        return None
    if not is_retrieval_query(query=query):
        return None
    if int(judge_context.get("search_result_count") or 0) <= 0:
        return None
    evidence_top_k = judge_context.get("evidence_top_k")
    if not isinstance(evidence_top_k, list) or not evidence_top_k:
        return None
    evidence_text = " ".join(
        f"{item.get('subject', '')} {item.get('snippet', '')}" for item in evidence_top_k if isinstance(item, dict)
    )
    if not extract_grounding_tokens(text=evidence_text):
        return None
    answer_tokens = extract_grounding_tokens(text=answer)
    if answer_tokens and answer_tokens.intersection(extract_grounding_tokens(text=evidence_text)):
        return None
    return {
        "pass": False,
        "score": 1,
        "reason": "retrieval 질의에서 답변이 근거 메일(subject/snippet)과 정합하지 않아 hard-fail 처리되었습니다.",
        "checks": {"intent_match": False, "format_match": False, "grounded": False},
    }


def is_retrieval_query(query: str) -> bool:
    """검색형 메일 retrieval 질의 여부를 판별한다."""
    compact = str(query or "").strip().replace(" ", "")
    if "메일" not in compact or "현재메일" in compact:
        return False
    retrieval_tokens = ("조회", "검색", "찾아", "관련", "최근", "지난", "에서", "본문에")
    return any(token in compact for token in retrieval_tokens)


def extract_grounding_tokens(text: str) -> set[str]:
    """grounding 비교용 의미 토큰 집합을 추출한다."""
    tokens = {token.lower() for token in GROUNDING_TOKEN_REGEX.findall(str(text or ""))}
    return {token for token in tokens if token not in GROUNDING_STOPWORDS}
