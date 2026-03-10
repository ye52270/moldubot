from __future__ import annotations

import re

TECH_KEYWORD_PATTERN = re.compile(r"[A-Za-z]{2,10}|[가-힣]{2,8}")

# 기술 이슈 후보를 좁히기 위한 1차 화이트리스트
TECH_KEYWORD_ALLOWLIST: set[str] = {
    "api",
    "ssl",
    "gpo",
    "eai",
    "sso",
    "m365",
    "cloud",
    "pc",
    "메일",
    "오류",
    "장애",
    "보안",
    "차단",
    "연동",
    "인증",
    "접속",
    "리다이렉트",
    "정책",
    "로그인",
}

TECH_ISSUE_TYPE_MAP: dict[str, str] = {
    "api": "연동/API 이슈",
    "eai": "연동/API 이슈",
    "연동": "연동/API 이슈",
    "오류": "오류/장애 이슈",
    "장애": "오류/장애 이슈",
    "보안": "보안/접근통제 이슈",
    "ssl": "보안/접근통제 이슈",
    "차단": "보안/접근통제 이슈",
    "인증": "인증/계정 이슈",
    "로그인": "인증/계정 이슈",
    "gpo": "정책/설정 이슈",
    "정책": "정책/설정 이슈",
    "리다이렉트": "정책/설정 이슈",
}

