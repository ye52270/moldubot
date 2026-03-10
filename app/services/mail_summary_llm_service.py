from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from app.core.llm_runtime import invoke_json_object, is_model_provider_configured, resolve_env_model
from app.core.logging_config import get_logger
from app.services.mail_text_utils import select_salient_summary_sentences, trim_sentence

logger = get_logger(__name__)
SUMMARY_LLM_MODEL = resolve_env_model(
    primary_env="MOLDUBOT_SUMMARY_MODEL",
    fallback_envs=("SUMMARIZATION_MODEL", "DEFAULT_CHAT_MODEL"),
    default_model="gpt-4o-mini",
)
SUMMARY_MAX_CHARS = 90
CATEGORY_GENERAL = "일반"
CATEGORY_URGENT = "긴급"
CATEGORY_REPLY_REQUIRED = "회신필요"
VALID_CATEGORIES = {CATEGORY_GENERAL, CATEGORY_URGENT, CATEGORY_REPLY_REQUIRED}


@dataclass
class MailSummaryLLMResult:
    """
    LLM summary 생성 결과 데이터 구조.

    Attributes:
        summary: 압축 요약 텍스트
        category: 분류 카테고리
        model: 사용 모델명
        source: 생성 소스(`llm` 또는 `fallback`)
    """

    summary: str
    category: str
    model: str
    source: str


class MailSummaryLLMService:
    """
    메일 본문을 LLM으로 요약/분류하는 서비스.
    """

    def summarize(self, subject: str, body_text: str) -> MailSummaryLLMResult:
        """
        제목/본문을 입력받아 summary/category를 생성한다.

        Args:
            subject: 메일 제목
            body_text: 메일 본문

        Returns:
            생성 결과 데이터
        """
        if not self._is_llm_available():
            return self._build_fallback(subject=subject, body_text=body_text)
        prompt_payload = {
            "task": "mail_summary",
            "constraints": {
                "summary_max_chars": 140,
                "summary_style": "핵심만 한 문장으로 함축",
                "categories": [CATEGORY_GENERAL, CATEGORY_URGENT, CATEGORY_REPLY_REQUIRED],
            },
            "input": {
                "subject": str(subject or "").strip(),
                "body_text": str(body_text or "").strip()[:6000],
            },
            "output_schema": {"summary": "string", "category": "string"},
        }
        try:
            payload = invoke_json_object(
                model_name=SUMMARY_LLM_MODEL,
                system_prompt=(
                    "너는 메일 요약기다. JSON만 출력한다. "
                    "summary는 140자 이하, 장황한 인사말/헤더 제외, 핵심 이슈만 함축한다. "
                    "category는 일반/긴급/회신필요 중 하나만 선택한다."
                ),
                user_prompt=json.dumps(prompt_payload, ensure_ascii=False),
                timeout_sec=45,
                temperature=0.1,
            )
            summary = self._normalize_summary(value=str(payload.get("summary") or ""))
            category = self._normalize_category(value=str(payload.get("category") or ""))
            if not summary:
                return self._build_fallback(subject=subject, body_text=body_text)
            return MailSummaryLLMResult(
                summary=summary,
                category=category,
                model=SUMMARY_LLM_MODEL,
                source="llm",
            )
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("mail_summary_llm_failed: %s", exc)
            return self._build_fallback(subject=subject, body_text=body_text)
        except Exception as exc:
            logger.warning("mail_summary_llm_failed: %s", exc)
            return self._build_fallback(subject=subject, body_text=body_text)

    def _build_fallback(self, subject: str, body_text: str) -> MailSummaryLLMResult:
        """
        LLM 미사용/실패 시 fallback 요약 결과를 생성한다.

        Args:
            subject: 메일 제목
            body_text: 메일 본문

        Returns:
            fallback 결과 데이터
        """
        sanitized_subject = self._sanitize_text(value=subject)
        sanitized_body = self._sanitize_text(value=body_text)
        lines = select_salient_summary_sentences(text=sanitized_body, line_target=1)
        first_line = str(lines[0] or "").strip() if lines else ""
        if self._is_noisy_candidate(text=first_line):
            first_line = ""
        base_summary = first_line or sanitized_subject
        if self._is_noisy_candidate(text=base_summary):
            base_summary = "시스템/코드 관련 메일"
        compact_summary = trim_sentence(sentence=base_summary, max_len=78) if base_summary else "요약 없음"
        summary = compact_summary if compact_summary else "요약 없음"
        summary = self._normalize_summary(value=summary)
        category = self._classify_fallback(subject=subject, body_text=body_text)
        return MailSummaryLLMResult(summary=summary, category=category, model="fallback", source="fallback")

    def _is_noisy_candidate(self, text: str) -> bool:
        """
        요약 후보 문장이 노이즈성(HTML/코드/헤더)인지 판별한다.

        Args:
            text: 요약 후보 텍스트

        Returns:
            노이즈성 문장이면 True
        """
        normalized = str(text or "").lower()
        noisy_tokens = (
            "&nbsp;",
            "<div",
            "<footer",
            "logger =",
            "apirouter",
            "mail_context_service",
            "from:",
            "subject:",
            "to:",
            "sent:",
            "@ro",
            "rights reserved",
        )
        return any(token in normalized for token in noisy_tokens)

    def _classify_fallback(self, subject: str, body_text: str) -> str:
        """
        fallback 분류를 수행한다.

        Args:
            subject: 메일 제목
            body_text: 본문 텍스트

        Returns:
            분류 카테고리
        """
        text = f"{str(subject or '')}\n{str(body_text or '')}".lower()
        if any(token in text for token in ("긴급", "asap", "장애", "즉시", "오류", "실패", "마감")):
            return CATEGORY_URGENT
        if any(token in text for token in ("회신", "답변", "답장", "확인 부탁", "문의", "검토 요청")):
            return CATEGORY_REPLY_REQUIRED
        return CATEGORY_GENERAL

    def _normalize_summary(self, value: str) -> str:
        """
        summary 텍스트를 길이/공백 기준으로 정규화한다.

        Args:
            value: 원본 summary

        Returns:
            정규화 summary
        """
        normalized = self._sanitize_text(value=value)
        return normalized[:SUMMARY_MAX_CHARS].strip()

    def _normalize_category(self, value: str) -> str:
        """
        category 문자열을 허용된 값으로 정규화한다.

        Args:
            value: 원본 category 문자열

        Returns:
            정규화된 category 값
        """
        normalized = str(value or "").strip()
        if normalized in VALID_CATEGORIES:
            return normalized
        return CATEGORY_GENERAL

    def _is_llm_available(self) -> bool:
        """
        LLM 호출 가능 여부를 확인한다.

        Returns:
            API 키가 있으면 True
        """
        return is_model_provider_configured(model_name=SUMMARY_LLM_MODEL)

    def _sanitize_text(self, value: str) -> str:
        """
        요약 전처리를 위해 HTML 엔티티/태그/헤더 노이즈를 정리한다.

        Args:
            value: 원본 텍스트

        Returns:
            정리된 텍스트
        """
        normalized = str(value or "")
        normalized = normalized.replace("&nbsp;", " ")
        normalized = re.sub(r"<[^>]+>", " ", normalized)
        normalized = re.sub(r"(?i)\\b(from|to|sent|subject)\\s*:\\s*", " ", normalized)
        normalized = re.sub(r"\\s+", " ", normalized).strip()
        return normalized
