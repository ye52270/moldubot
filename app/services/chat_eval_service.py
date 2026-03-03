from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable
from urllib import error, request

from openai import OpenAI, OpenAIError

from app.core.chat_eval_cases import CHAT_EVAL_CASES, ChatEvalCase
from app.core.logging_config import get_logger
from app.services.chat_eval_quality_metrics import build_quality_metrics

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "data" / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "chat_eval_latest.json"
DEFAULT_JUDGE_MODEL = "gpt-5-mini"
DEFAULT_CHAT_TIMEOUT_SEC = 90
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

ChatCaller = Callable[[str, dict[str, Any], int], tuple[int, dict[str, Any], float, str | None]]
JudgeCaller = Callable[[str, str, str, str, dict[str, Any]], tuple[dict[str, Any], float]]


@dataclass(frozen=True)
class CaseRunResult:
    """
    단일 평가 케이스 실행 결과를 표현한다.

    Attributes:
        case_id: 케이스 식별자
        query: 사용자 발화
        expectation: 기대 동작 설명
        requires_current_mail: 선택 메일 컨텍스트 요구 여부
        status_code: `/search/chat` 응답 status code
        elapsed_ms: 채팅 API 호출 지연
        source: 응답 메타 source
        answer: 모델 답변 본문
        error: 실행 중 오류 메시지
        judge: LLM-as-Judge 결과 JSON
        judge_elapsed_ms: Judge 호출 지연
    """

    case_id: str
    query: str
    expectation: str
    requires_current_mail: bool
    status_code: int
    elapsed_ms: float
    source: str
    answer: str
    error: str | None
    judge: dict[str, Any]
    judge_elapsed_ms: float


def list_chat_eval_cases() -> list[ChatEvalCase]:
    """
    채팅 평가 케이스 목록을 반환한다.

    Returns:
        케이스 목록 복사본
    """
    return [dict(case) for case in CHAT_EVAL_CASES]


def run_chat_eval_session(
    *,
    chat_url: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    selected_email_id: str = "",
    mailbox_user: str = "",
    request_timeout_sec: int = DEFAULT_CHAT_TIMEOUT_SEC,
    max_cases: int | None = None,
    case_ids: list[str] | None = None,
    chat_caller: ChatCaller | None = None,
    judge_caller: JudgeCaller | None = None,
) -> dict[str, Any]:
    """
    E2E 채팅 품질 세션을 실행하고 리포트를 저장한다.

    Args:
        chat_url: `/search/chat` 엔드포인트 URL
        judge_model: Judge 모델명
        selected_email_id: 현재메일 질의용 message id
        mailbox_user: 현재메일 질의용 mailbox user
        request_timeout_sec: 채팅 API 타임아웃(초)
        max_cases: 실행할 최대 케이스 수
        case_ids: 실행할 케이스 ID 목록
        chat_caller: 채팅 호출 함수(테스트 주입)
        judge_caller: Judge 호출 함수(테스트 주입)

    Returns:
        실행 리포트 JSON
    """
    started_at = datetime.now(tz=timezone.utc)
    active_chat_caller = chat_caller or _default_chat_caller
    active_judge_caller = judge_caller or _build_default_judge_caller(judge_model=judge_model)
    selected = _select_cases(max_cases=max_cases, case_ids=case_ids)

    logger.info(
        "chat_eval.run.start: cases=%s chat_url=%s judge_model=%s timeout=%s",
        len(selected),
        chat_url,
        judge_model,
        request_timeout_sec,
    )

    case_results: list[CaseRunResult] = []
    for index, case in enumerate(selected, start=1):
        thread_id = f"eval_{int(time.time())}_{index}"
        payload = {
            "message": case["query"],
            "thread_id": thread_id,
        }
        if case["requires_current_mail"] and selected_email_id:
            payload["email_id"] = selected_email_id
        if case["requires_current_mail"] and mailbox_user:
            payload["mailbox_user"] = mailbox_user

        status_code, response_json, elapsed_ms, call_error = active_chat_caller(
            chat_url,
            payload,
            request_timeout_sec,
        )
        metadata = response_json.get("metadata", {}) if isinstance(response_json, dict) else {}
        raw_answer = str(response_json.get("answer") or "").strip()
        answer = _resolve_visible_answer(raw_answer=raw_answer, metadata=metadata)
        source = str(metadata.get("source") or "")
        judge_context = _build_judge_context(metadata=metadata)
        format_override = _rule_based_format_guard(
            query=case["query"],
            answer=answer,
        )
        override = _rule_based_no_result_judge(
            query=case["query"],
            answer=answer,
            judge_context=judge_context,
        )
        grounding_override = _rule_based_retrieval_grounding_guard(
            query=case["query"],
            answer=answer,
            judge_context=judge_context,
        )
        if format_override is not None:
            judge_result = format_override
            judge_elapsed_ms = 0.0
        elif override is not None:
            judge_result = override
            judge_elapsed_ms = 0.0
        elif grounding_override is not None:
            judge_result = grounding_override
            judge_elapsed_ms = 0.0
        else:
            judge_result, judge_elapsed_ms = active_judge_caller(
                case["query"],
                answer,
                case["expectation"],
                source,
                judge_context,
            )

        result = CaseRunResult(
            case_id=case["case_id"],
            query=case["query"],
            expectation=case["expectation"],
            requires_current_mail=bool(case["requires_current_mail"]),
            status_code=status_code,
            elapsed_ms=elapsed_ms,
            source=source,
            answer=answer,
            error=call_error,
            judge=judge_result,
            judge_elapsed_ms=judge_elapsed_ms,
        )
        case_results.append(result)

    finished_at = datetime.now(tz=timezone.utc)
    report = _build_report(
        started_at=started_at,
        finished_at=finished_at,
        chat_url=chat_url,
        judge_model=judge_model,
        selected_email_id=selected_email_id,
        mailbox_user=mailbox_user,
        case_results=case_results,
    )
    _persist_report(report=report)
    logger.info(
        "chat_eval.run.completed: total=%s pass_rate=%.1f avg_chat_ms=%.1f avg_judge_ms=%.1f",
        report["summary"]["total_cases"],
        report["summary"]["judge_pass_rate"],
        report["summary"]["avg_chat_elapsed_ms"],
        report["summary"]["avg_judge_elapsed_ms"],
    )
    return report


def load_latest_chat_eval_report() -> dict[str, Any] | None:
    """
    최근 저장된 채팅 평가 리포트를 로드한다.

    Returns:
        리포트 JSON 또는 None
    """
    if not LATEST_REPORT_PATH.exists():
        return None
    try:
        return json.loads(LATEST_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("chat_eval.load_latest_failed: %s", exc)
        return None


def _select_cases(max_cases: int | None, case_ids: list[str] | None = None) -> list[ChatEvalCase]:
    """
    실행할 평가 케이스를 선택한다.

    Args:
        max_cases: 최대 케이스 수
        case_ids: 실행할 케이스 ID 목록

    Returns:
        선택된 케이스 목록
    """
    cases = list_chat_eval_cases()
    normalized_ids = {
        str(case_id or "").strip() for case_id in (case_ids or []) if str(case_id or "").strip()
    }
    if normalized_ids:
        filtered = [case for case in cases if str(case.get("case_id") or "") in normalized_ids]
    else:
        filtered = cases
    if max_cases is None or max_cases <= 0:
        return filtered
    return filtered[: max_cases]


def _default_chat_caller(
    chat_url: str,
    payload: dict[str, Any],
    timeout_sec: int,
) -> tuple[int, dict[str, Any], float, str | None]:
    """
    `/search/chat` 엔드포인트를 HTTP로 호출한다.

    Args:
        chat_url: 채팅 API URL
        payload: 요청 본문
        timeout_sec: 호출 타임아웃(초)

    Returns:
        (status code, 응답 JSON, 지연 ms, 오류 문자열)
    """
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


def _build_default_judge_caller(judge_model: str) -> JudgeCaller:
    """
    OpenAI 기반 LLM Judge 호출 함수를 생성한다.

    Args:
        judge_model: Judge 모델명

    Returns:
        Judge 호출 함수
    """
    client = OpenAI()

    def _judge(
        query: str,
        answer: str,
        expectation: str,
        source: str,
        judge_context: dict[str, Any],
    ) -> tuple[dict[str, Any], float]:
        """
        단일 응답을 채점한다.

        Args:
            query: 사용자 질의
            answer: 모델 응답
            expectation: 기대 동작
            source: 메타 source

        Returns:
            (채점 JSON, 지연 ms)
        """
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
                "special_rules": {
                    "mail_search_zero_result": (
                        "judge_context.search_result_count가 0이고 답변이 '조건에 맞는 메일이 없습니다' 류라면 "
                        "intent_match/grounded를 True로 평가하고, pass는 기본적으로 True로 평가한다."
                    ),
                    "evidence_count_subset": (
                        "judge_context.evidence_count는 UI 표시용 축약 개수일 수 있다. "
                        "실제 조회 건수 판단은 judge_context.search_result_count를 우선 사용한다."
                    ),
                    "sentence_grounding": (
                        "답변의 각 문장은 judge_context.evidence_top_k(subject/snippet/received_date)와 정합해야 한다. "
                        "근거에 없는 세부 사실이면 grounded=false로 평가한다."
                    ),
                    "retrieval_hard_fail": (
                        "retrieval 질의에서 답변이 evidence_top_k와 명백히 불일치하면 pass=false, score=1로 평가한다."
                    ),
                },
                "scoring": {
                    "5": "의도/형식/근거 모두 우수",
                    "3": "부분 충족",
                    "1": "대부분 실패",
                },
            },
            ensure_ascii=False,
        )

        try:
            completion = client.chat.completions.create(
                model=judge_model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = str(completion.choices[0].message.content or "{}").strip()
            parsed = _normalize_judge_result(raw_result=raw)
        except OpenAIError as exc:
            logger.warning("chat_eval.judge_openai_failed: %s", exc)
            parsed = _judge_failure(reason=f"judge_openai_error: {exc}")
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("chat_eval.judge_response_invalid: %s", exc)
            parsed = _judge_failure(reason=f"judge_response_invalid: {exc}")

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        return parsed, elapsed_ms

    return _judge


def _normalize_judge_result(raw_result: str) -> dict[str, Any]:
    """
    Judge 원문을 표준 JSON 구조로 정규화한다.

    Args:
        raw_result: Judge 모델 원문

    Returns:
        정규화된 채점 결과
    """
    try:
        parsed = json.loads(raw_result)
    except json.JSONDecodeError:
        return _judge_failure(reason="judge_json_decode_error")

    if not isinstance(parsed, dict):
        return _judge_failure(reason="judge_payload_not_object")

    checks = parsed.get("checks")
    normalized_checks = {
        "intent_match": bool(checks.get("intent_match")) if isinstance(checks, dict) else False,
        "format_match": bool(checks.get("format_match")) if isinstance(checks, dict) else False,
        "grounded": bool(checks.get("grounded")) if isinstance(checks, dict) else False,
    }
    score = _normalize_score(parsed.get("score"))
    reason = str(parsed.get("reason") or "")
    passed = bool(parsed.get("pass"))
    return {
        "pass": passed,
        "score": score,
        "reason": reason,
        "checks": normalized_checks,
    }


def _normalize_score(raw_score: Any) -> int:
    """
    점수를 1~5 범위 정수로 정규화한다.

    Args:
        raw_score: 원본 점수

    Returns:
        정규화된 점수
    """
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        return 1
    return max(1, min(score, 5))


def _judge_failure(reason: str) -> dict[str, Any]:
    """
    Judge 실패 결과를 생성한다.

    Args:
        reason: 실패 사유

    Returns:
        실패 결과 JSON
    """
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


def _build_report(
    *,
    started_at: datetime,
    finished_at: datetime,
    chat_url: str,
    judge_model: str,
    selected_email_id: str,
    mailbox_user: str,
    case_results: list[CaseRunResult],
) -> dict[str, Any]:
    """
    케이스 실행 결과를 최종 리포트로 집계한다.

    Args:
        started_at: 실행 시작 시각
        finished_at: 실행 종료 시각
        chat_url: 호출 URL
        judge_model: Judge 모델명
        selected_email_id: 선택 메일 ID
        mailbox_user: 메일박스 사용자
        case_results: 케이스 결과 목록

    Returns:
        리포트 JSON
    """
    passed_count = sum(1 for item in case_results if bool(item.judge.get("pass")))
    total = len(case_results)
    chat_elapsed = [item.elapsed_ms for item in case_results]
    judge_elapsed = [item.judge_elapsed_ms for item in case_results]
    judge_scores = [int(item.judge.get("score", 1)) for item in case_results]
    quality_metrics = build_quality_metrics(
        per_case=[
            {"query": item.query, "answer": item.answer}
            for item in case_results
        ]
    )

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


def _build_judge_context(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Judge 입력용 실행 컨텍스트를 메타데이터에서 구성한다.

    Args:
        metadata: `/search/chat` 응답 metadata

    Returns:
        judge context 사전
    """
    evidence = metadata.get("evidence_mails")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    raw_result_count = metadata.get("search_result_count")
    search_result_count = int(raw_result_count) if isinstance(raw_result_count, int) else evidence_count
    aligned_evidence_count = max(evidence_count, search_result_count)
    evidence_top_k = _extract_evidence_top_k(metadata=metadata, top_k=EVIDENCE_TOP_K)
    return {
        "search_result_count": max(0, search_result_count),
        "evidence_count": max(0, aligned_evidence_count),
        "source": str(metadata.get("source") or ""),
        "evidence_top_k": evidence_top_k,
    }


def _resolve_visible_answer(raw_answer: str, metadata: dict[str, Any]) -> str:
    """
    Judge 입력용 답변 텍스트를 실제 화면 표시 기준으로 정규화한다.

    Args:
        raw_answer: API 원본 answer 문자열
        metadata: API metadata 객체

    Returns:
        화면 표시에 가까운 정규화 답변 문자열
    """
    raw = str(raw_answer or "").strip()
    answer_format = metadata.get("answer_format") if isinstance(metadata, dict) else None
    if not isinstance(answer_format, dict):
        return raw
    blocks = answer_format.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return raw
    rendered = _render_answer_blocks_to_text(blocks=blocks)
    return rendered or raw


def _render_answer_blocks_to_text(blocks: list[Any]) -> str:
    """
    answer_format blocks를 화면 친화 텍스트로 평탄화한다.

    Args:
        blocks: answer_format.blocks 배열

    Returns:
        줄바꿈 기반 평탄화 텍스트
    """
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type == "heading":
            heading = _normalize_visible_text(str(block.get("text") or ""))
            if heading:
                lines.append(heading)
            continue
        if block_type == "paragraph" or block_type == "quote":
            paragraph = _normalize_visible_text(str(block.get("text") or ""))
            if paragraph:
                lines.append(paragraph)
            continue
        if block_type == "ordered_list":
            items = block.get("items")
            if not isinstance(items, list):
                continue
            index = 1
            for item in items:
                text = _normalize_visible_text(str(item or ""))
                if not text:
                    continue
                lines.append(f"{index}. {text}")
                index += 1
            continue
        if block_type == "unordered_list":
            items = block.get("items")
            if not isinstance(items, list):
                continue
            for item in items:
                text = _normalize_visible_text(str(item or ""))
                if text:
                    lines.append(f"- {text}")
            continue
        if block_type == "table":
            headers = block.get("headers")
            rows = block.get("rows")
            if not isinstance(headers, list) or not isinstance(rows, list):
                continue
            normalized_headers = [_normalize_visible_text(str(header or "")) for header in headers]
            for row in rows:
                if not isinstance(row, list):
                    continue
                parts: list[str] = []
                for idx, header in enumerate(normalized_headers):
                    value = _normalize_visible_text(str(row[idx] if idx < len(row) else ""))
                    if not header and not value:
                        continue
                    if header:
                        parts.append(f"{header}: {value}")
                    elif value:
                        parts.append(value)
                if parts:
                    lines.append(" | ".join(parts))
            continue
    return "\n".join(lines).strip()


def _normalize_visible_text(text: str) -> str:
    """
    markdown/공백을 화면 표시형 텍스트로 정규화한다.

    Args:
        text: 원본 텍스트

    Returns:
        정규화 텍스트
    """
    value = str(text or "").strip()
    if not value:
        return ""
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", value)
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = re.sub(r"`(.+?)`", r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _extract_evidence_top_k(metadata: dict[str, Any], top_k: int) -> list[dict[str, str]]:
    """
    metadata.evidence_mails에서 judge 전달용 top-k 근거 요약을 추출한다.

    Args:
        metadata: `/search/chat` 응답 metadata
        top_k: 최대 추출 개수

    Returns:
        subject/snippet/received_date를 포함한 근거 목록
    """
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
                "snippet": str(item.get("snippet") or "").strip(),
                "received_date": str(item.get("received_date") or "").strip(),
            }
        )
    return extracted


def _rule_based_no_result_judge(
    query: str,
    answer: str,
    judge_context: dict[str, Any],
) -> dict[str, Any] | None:
    """
    조회 0건 케이스를 규칙 기반으로 선판정한다.

    Args:
        query: 사용자 질의
        answer: 모델 답변
        judge_context: 실행 컨텍스트

    Returns:
        선판정 결과. 적용 대상이 아니면 None
    """
    search_result_count = int(judge_context.get("search_result_count") or 0)
    if search_result_count != 0:
        return None
    query_text = str(query or "")
    answer_text = str(answer or "")
    if "메일" not in query_text:
        return None
    no_result_tokens = ("조건에 맞는 메일이 없습니다", "관련 메일이 없", "조회 결과: 조건에 맞는 메일이 없습니다")
    if not any(token in answer_text for token in no_result_tokens):
        return None
    return {
        "pass": True,
        "score": 4,
        "reason": "조회 결과가 0건으로 확인되어 부재 안내 응답을 적절히 반환했습니다.",
        "checks": {
            "intent_match": True,
            "format_match": True,
            "grounded": True,
        },
    }


def _rule_based_format_guard(query: str, answer: str) -> dict[str, Any] | None:
    """
    형식 강제 질의에 대한 최소 요건을 규칙 기반으로 선검증한다.

    Args:
        query: 사용자 질의
        answer: 모델 답변

    Returns:
        선판정 결과. 적용 대상이 아니면 None
    """
    query_text = str(query or "")
    answer_text = str(answer or "").strip()
    if ACTION_ITEM_QUERY_TOKEN not in query_text:
        return None
    if _has_structured_action_items(answer=answer_text):
        return None
    return {
        "pass": False,
        "score": 1,
        "reason": "액션 아이템 요청이지만 실행 항목 목록(번호/불릿)이 없어 형식 요구를 충족하지 못했습니다.",
        "checks": {
            "intent_match": False,
            "format_match": False,
            "grounded": True,
        },
    }


def _has_structured_action_items(answer: str) -> bool:
    """
    답변 내 액션 아이템 목록(번호/불릿) 존재 여부를 확인한다.

    Args:
        answer: 모델 답변

    Returns:
        구조화된 항목이 하나 이상 존재하면 True
    """
    if not answer:
        return False
    return bool(ACTION_ITEM_LIST_REGEX.search(answer))


def _rule_based_retrieval_grounding_guard(
    query: str,
    answer: str,
    judge_context: dict[str, Any],
) -> dict[str, Any] | None:
    """
    retrieval 질의에서 답변-근거 불일치를 규칙 기반으로 선판정한다.

    Args:
        query: 사용자 질의
        answer: 모델 답변
        judge_context: Judge 입력 컨텍스트

    Returns:
        불일치 시 FAIL 결과, 아니면 None
    """
    if not _is_retrieval_query(query=query):
        return None
    search_result_count = int(judge_context.get("search_result_count") or 0)
    if search_result_count <= 0:
        return None
    evidence_top_k = judge_context.get("evidence_top_k")
    if not isinstance(evidence_top_k, list) or not evidence_top_k:
        return None
    if not _has_usable_evidence(evidence_top_k=evidence_top_k):
        return None
    if _has_grounding_overlap(answer=answer, evidence_top_k=evidence_top_k):
        return None
    return {
        "pass": False,
        "score": 1,
        "reason": "retrieval 질의에서 답변이 근거 메일(subject/snippet)과 정합하지 않아 hard-fail 처리되었습니다.",
        "checks": {
            "intent_match": False,
            "format_match": False,
            "grounded": False,
        },
    }


def _is_retrieval_query(query: str) -> bool:
    """
    검색형 메일 retrieval 질의 여부를 판별한다.

    Args:
        query: 사용자 질의

    Returns:
        retrieval 질의면 True
    """
    text = str(query or "").strip()
    compact = text.replace(" ", "")
    if "메일" not in compact:
        return False
    if "현재메일" in compact:
        return False
    retrieval_tokens = ("조회", "검색", "찾아", "관련", "최근", "지난", "에서", "본문에")
    return any(token in compact for token in retrieval_tokens)


def _has_grounding_overlap(answer: str, evidence_top_k: list[dict[str, Any]]) -> bool:
    """
    답변 텍스트와 근거 메일 텍스트 간 최소 토큰 겹침 여부를 계산한다.

    Args:
        answer: 모델 답변
        evidence_top_k: 근거 메일 목록

    Returns:
        겹침이 있으면 True
    """
    answer_tokens = _extract_grounding_tokens(text=answer)
    if not answer_tokens:
        return False
    evidence_text = " ".join(
        f"{item.get('subject', '')} {item.get('snippet', '')}" for item in evidence_top_k if isinstance(item, dict)
    )
    evidence_tokens = _extract_grounding_tokens(text=evidence_text)
    if not evidence_tokens:
        return False
    overlap = answer_tokens.intersection(evidence_tokens)
    return len(overlap) >= 1


def _has_usable_evidence(evidence_top_k: list[dict[str, Any]]) -> bool:
    """
    grounding 비교가 가능한 최소 근거 텍스트가 존재하는지 확인한다.

    Args:
        evidence_top_k: 근거 메일 목록

    Returns:
        subject/snippet 중 유의미 텍스트가 있으면 True
    """
    for item in evidence_top_k:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if subject or snippet:
            return True
    return False


def _extract_grounding_tokens(text: str) -> set[str]:
    """
    grounding 비교용 의미 토큰 집합을 추출한다.

    Args:
        text: 원문 문자열

    Returns:
        정규화된 토큰 집합
    """
    tokens = {token.lower() for token in GROUNDING_TOKEN_REGEX.findall(str(text or ""))}
    return {token for token in tokens if token not in GROUNDING_STOPWORDS}


def _persist_report(report: dict[str, Any]) -> None:
    """
    리포트를 최신/타임스탬프 파일로 저장한다.

    Args:
        report: 저장할 리포트
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    started_at = str(report.get("meta", {}).get("started_at") or "")
    stamp = _sanitize_timestamp(started_at=started_at)
    stamped_path = REPORTS_DIR / f"chat_eval_{stamp}.json"
    body = json.dumps(report, ensure_ascii=False, indent=2)
    LATEST_REPORT_PATH.write_text(body, encoding="utf-8")
    stamped_path.write_text(body, encoding="utf-8")


def _sanitize_timestamp(started_at: str) -> str:
    """
    파일명에 안전한 타임스탬프 문자열을 반환한다.

    Args:
        started_at: ISO datetime 문자열

    Returns:
        파일명용 타임스탬프
    """
    if not started_at:
        return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    normalized = started_at.replace(":", "").replace("-", "")
    normalized = normalized.replace("+", "_").replace(".", "_")
    return normalized[:22]
