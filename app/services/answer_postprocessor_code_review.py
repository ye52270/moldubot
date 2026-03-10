from __future__ import annotations

import re
from typing import Any

from app.services.answer_postprocessor_summary import extract_summary_lines, sanitize_summary_lines

MAX_CODE_LINES = 40
MAX_CODE_CHARS = 2200
MAIL_HEADER_PREFIXES: tuple[str, ...] = (
    "from:",
    "sent:",
    "to:",
    "cc:",
    "subject:",
    "date:",
    "받는 사람:",
    "보낸 사람:",
    "참조:",
)
INLINE_CODE_MARKERS: tuple[str, ...] = (
    "<%",
    "%>",
    "<div",
    "</div",
    "<form",
    "</form",
    "<input",
    "<button",
    "<script",
    "</script",
    "function ",
    "class ",
    "def ",
    "return ",
)

try:
    from pygments.lexers import guess_lexer
    from pygments.util import ClassNotFound
except ImportError:  # pragma: no cover - optional dependency
    guess_lexer = None
    ClassNotFound = Exception


def render_current_mail_code_review_response(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    코드 스니펫 분석 요청을 결정론 템플릿으로 렌더링한다.

    Args:
        user_message: 사용자 입력
        answer: 모델 원문 응답
        tool_payload: tool payload

    Returns:
        강제 렌더링된 문자열. 대상 질의가 아니면 빈 문자열
    """
    if not _is_code_review_request(user_message=user_message):
        return ""
    context = tool_payload.get("mail_context") if isinstance(tool_payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    body_code_excerpt = str(context.get("body_code_excerpt") or "").strip()
    body_excerpt = str(context.get("body_excerpt") or "").strip()
    source_text = body_code_excerpt or body_excerpt
    code = _extract_code_snippet(text=source_text)
    if not code:
        return "코드 스니펫이 없습니다."
    language = _detect_language(code=code)
    analysis_lines = _build_analysis_lines(answer=answer, code=code, language=language)
    review_lines = _build_review_lines(code=code, language=language)
    blocks = [
        "## 코드 분석",
        "",
        *[f"- {line}" for line in analysis_lines],
        "",
        "## 코드 리뷰",
        "",
        f"### 언어\n- {language.upper()}",
        "",
        f"```{language}",
        code,
        "```",
        "",
        "### 리뷰 포인트",
        "",
        *[f"{index}. {line}" for index, line in enumerate(review_lines, start=1)],
    ]
    return "\n".join(blocks).strip()


def _is_code_review_request(user_message: str) -> bool:
    """
    코드 스니펫 분석 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        코드 분석 요청이면 True
    """
    text = str(user_message or "").replace(" ", "")
    return ("코드" in text and "리뷰" in text) or ("코드스니펫" in text)


def _extract_code_snippet(text: str) -> str:
    """
    본문 발췌에서 코드 스니펫을 추출한다.

    Args:
        text: 본문 발췌

    Returns:
        코드 스니펫 문자열
    """
    source = _strip_mail_header_noise(text=text)
    if not source:
        return ""
    fenced = re.search(r"```[a-zA-Z0-9_+-]*\n([\s\S]+?)```", source)
    if fenced:
        return _truncate_code(code=str(fenced.group(1) or ""))
    inline_block = _extract_inline_markup_block(text=source)
    if inline_block:
        result = _truncate_code(code=inline_block)
        if _is_meaningless_truncated_only(result):
            return ""
        return result
    lines = [line.rstrip() for line in source.split("\n") if line.strip() and "...(truncated)" not in line.strip()]
    best_block: list[str] = []
    current_block: list[str] = []
    for line in lines:
        if _looks_like_code_line(line=line):
            current_block.append(line)
            if len(current_block) > len(best_block):
                best_block = list(current_block)
            continue
        if len(current_block) >= 2:
            current_block = []
            continue
        current_block = []
    if best_block:
        result = _truncate_code(code="\n".join(best_block))
        if _is_meaningless_truncated_only(result):
            return ""
        return result
    tag_block = re.search(r"(<form[\s\S]+?(?:</form>|/?>))", source, flags=re.IGNORECASE)
    if tag_block:
        result = _truncate_code(code=str(tag_block.group(1) or ""))
        if _is_meaningless_truncated_only(result):
            return ""
        return result
    return ""


def _extract_inline_markup_block(text: str) -> str:
    """
    한 줄로 압축된 JSP/HTML 코드 블록을 추출하고 줄바꿈을 복원한다.

    Args:
        text: 정제된 본문 텍스트

    Returns:
        줄복원된 코드 블록. 없으면 빈 문자열
    """
    source = str(text or "").strip()
    if not source:
        return ""
    lower = source.lower()
    positions = [lower.find(marker) for marker in INLINE_CODE_MARKERS if lower.find(marker) >= 0]
    if not positions:
        return ""
    start = min(positions)
    tail = source[start:].strip()
    normalized = re.sub(r">\s*<", ">\n<", tail)
    normalized = re.sub(r"(%>\s*<%)", "%>\n<%", normalized)
    normalized = re.sub(r"(%>\s*<[/a-zA-Z])", lambda m: m.group(0).replace("%>", "%>\n"), normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    normalized = normalized.replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1 and not _looks_like_code_line(lines[0]):
        return ""
    return "\n".join(lines)


def _strip_mail_header_noise(text: str) -> str:
    """
    메일 전달 헤더/서명 노이즈를 제거하고 코드 후보 본문만 남긴다.

    Args:
        text: 원문 본문 발췌(body_clean 기반)

    Returns:
        노이즈 제거 후 텍스트
    """
    lines = [str(line or "").rstrip() for line in str(text or "").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        lowered = stripped.lower()
        if lowered.startswith(MAIL_HEADER_PREFIXES):
            salvaged = _salvage_code_tail_from_header_line(line=stripped)
            if salvaged:
                cleaned.append(salvaged)
            continue
        if "-----original message-----" in lowered:
            continue
        if re.match(r"^[-_]{3,}$", stripped):
            continue
        if _looks_like_signature_line(line=stripped):
            continue
        cleaned.append(line)
    compact = "\n".join(cleaned).strip()
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    return compact


def _salvage_code_tail_from_header_line(line: str) -> str:
    """
    헤더 접두 라인에 코드가 붙어 있을 때 코드 꼬리를 복구한다.

    Args:
        line: 원본 라인

    Returns:
        코드 꼬리 문자열. 복구 실패 시 빈 문자열
    """
    text = str(line or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    marker_positions = [lowered.find(marker) for marker in INLINE_CODE_MARKERS if lowered.find(marker) >= 0]
    if not marker_positions:
        return ""
    start = min(marker_positions)
    tail = text[start:].strip()
    if _looks_like_code_line(line=tail):
        return tail
    return ""


def _looks_like_signature_line(line: str) -> bool:
    """
    일반적인 메일 서명/연락처 라인 여부를 판별한다.

    Args:
        line: 검사할 라인

    Returns:
        서명성 라인이면 True
    """
    text = str(line or "").strip().lower()
    if not text:
        return False
    if "@" in text and " " not in text and "." in text:
        return True
    if text.startswith(("tel.", "t.", "m.", "mobile", "fax")):
        return True
    if re.match(r"^\+?\d[\d\-\s]{7,}$", text):
        return True
    if text in {"best regards,", "regards,", "thanks,", "감사합니다.", "감사합니다"}:
        return True
    return False


def _looks_like_code_line(line: str) -> bool:
    """
    코드 라인 형태를 휴리스틱으로 판별한다.

    Args:
        line: 검사할 라인

    Returns:
        코드 라인이면 True
    """
    text = str(line or "").strip()
    if not text:
        return False
    markers = ("<", ">", "{", "}", ";", "=", "(", ")", "%>", "<%", "</", "/>")
    marker_hits = sum(1 for marker in markers if marker in text)
    if marker_hits >= 2:
        return True
    if re.match(r"^(if|for|while|return|const|let|var|def|class|public|private)\b", text):
        return True
    return False


def _truncate_code(code: str) -> str:
    """
    코드 길이를 UI 적정 크기로 제한한다.

    Args:
        code: 원본 코드

    Returns:
        길이 제한된 코드
    """
    lines = [line for line in str(code or "").strip().split("\n") if line.strip() and "...(truncated)" not in line.strip()]
    if not lines:
        return ""
    clipped_lines = lines[:MAX_CODE_LINES]
    clipped = "\n".join(clipped_lines).strip()
    if len(clipped) > MAX_CODE_CHARS:
        return clipped[:MAX_CODE_CHARS].rstrip() + "\n// ...(truncated)"
    if len(lines) > MAX_CODE_LINES:
        return clipped + "\n// ...(truncated)"
    return clipped


def _is_meaningless_truncated_only(code: str) -> bool:
    """
    의미 있는 코드 없이 truncation 마커만 남은 경우를 판별한다.

    Args:
        code: 코드 문자열

    Returns:
        의미 없는 truncation 마커면 True
    """
    compact = str(code or "").strip().lower()
    if not compact:
        return True
    tokens = compact.replace("//", "").replace(".", "").replace(" ", "").replace("\n", "")
    return tokens in {"(truncated)", "truncated"}


def _detect_language(code: str) -> str:
    """
    코드 스니펫 언어를 추정한다.

    Args:
        code: 코드 문자열

    Returns:
        언어 식별자
    """
    text = str(code or "").lower()
    if "<%" in text:
        return "jsp"
    if re.search(r"</?[a-z][\w:-]*[^>]*>", text):
        return "html"
    if "function " in text or "const " in text or "let " in text:
        return "javascript"
    if re.search(r"\bselect\b|\bfrom\b|\bwhere\b", text):
        return "sql"
    if "def " in text or "import " in text:
        return "python"
    guessed = _guess_language_with_pygments(code=code)
    if guessed:
        return guessed
    return "text"


def _guess_language_with_pygments(code: str) -> str:
    """
    Pygments guess_lexer로 언어를 추정한다.

    Args:
        code: 코드 문자열

    Returns:
        추정 언어 식별자. 실패 시 빈 문자열
    """
    if guess_lexer is None:
        return ""
    sample = str(code or "").strip()
    if not sample:
        return ""
    try:
        lexer = guess_lexer(sample)
    except ClassNotFound:
        return ""
    except Exception:
        return ""
    aliases = list(getattr(lexer, "aliases", []) or [])
    if not aliases:
        return ""
    alias = str(aliases[0] or "").strip().lower()
    if alias == "js":
        return "javascript"
    if alias == "py":
        return "python"
    if alias == "xml":
        return "html"
    return alias


def _build_analysis_lines(answer: str, code: str, language: str) -> list[str]:
    """
    코드 분석 섹션 라인을 구성한다.

    Args:
        answer: 모델 원문 응답
        code: 코드 스니펫
        language: 추정 언어

    Returns:
        분석 라인 목록
    """
    candidates = sanitize_summary_lines(lines=extract_summary_lines(answer=answer))
    filtered = [
        line
        for line in candidates
        if "코드 스니펫이 없습니다" not in line and not _is_json_noise_line(line=line)
    ][:2]
    if filtered:
        return filtered
    if language in {"jsp", "html"}:
        return [
            "로그인/인증 관련 UI 및 입력 처리 흐름을 담당하는 페이지 코드로 보입니다.",
            "입력값 검증, 세션 처리, CSRF/XSS 방어 적용 여부를 우선 점검해야 합니다.",
        ]
    return [
        "메일 본문 코드의 기능 흐름과 입력/출력 경로를 확인했습니다.",
        "외부 입력 처리, 인증/권한 경계, 예외 처리 누락 여부를 우선 점검해야 합니다.",
    ]


def _is_json_noise_line(line: str) -> bool:
    """
    코드 분석 라인 후보가 JSON 원문 조각인지 판별한다.

    Args:
        line: 후보 라인

    Returns:
        JSON 원문/계약 조각으로 보이면 True
    """
    text = str(line or "").strip()
    if not text:
        return True
    if text.startswith("{") or text.startswith("["):
        return True
    if '"format_type"' in text or '"summary_lines"' in text or '"major_points"' in text:
        return True
    if text.count('":') >= 2:
        return True
    return False


def _build_review_lines(code: str, language: str) -> list[str]:
    """
    코드 리뷰 체크포인트를 구성한다.

    Args:
        code: 코드 스니펫
        language: 코드 언어

    Returns:
        리뷰 포인트 목록
    """
    text = str(code or "").lower()
    points: list[str] = []
    if language in {"jsp", "html"} and "<form" in text and "csrf" not in text and "_token" not in text:
        points.append("폼 제출 경로에 CSRF 토큰 검증이 보이지 않습니다. 서버 검증을 추가하세요.")
    if "password" in text or "passwd" in text:
        points.append("비밀번호 필드는 마스킹/전송 구간 암호화(HTTPS)와 로그 비노출 정책을 확인하세요.")
    if "session" in text:
        points.append("세션 생성/고정/만료 정책을 점검하고, 로그인 후 세션 재발급을 적용하세요.")
    if "innerhtml" in text or "document.write" in text:
        points.append("DOM 반영 시 XSS 방지를 위해 escape/sanitize 처리가 필요합니다.")
    if not points:
        points.append("입력값 검증(길이/형식/허용문자)과 예외 처리 흐름을 점검하세요.")
        points.append("인증/권한 경계와 에러 메시지 노출 수준(정보 과다 노출)을 점검하세요.")
    return points[:4]
