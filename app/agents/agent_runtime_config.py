from __future__ import annotations

import os


def resolve_agent_skills_paths() -> list[str]:
    """
    환경변수에서 Deep Agents skills 디렉터리 목록을 파싱한다.

    Returns:
        유효한 skills 경로 문자열 목록
    """
    raw_value = str(os.getenv("MOLDUBOT_AGENT_SKILLS_PATHS", "")).strip()
    if not raw_value:
        return []
    normalized = raw_value.replace("\n", ",").replace(";", ",")
    paths: list[str] = []
    for token in normalized.split(","):
        candidate = str(token or "").strip()
        if not candidate or candidate in paths:
            continue
        paths.append(candidate)
    return paths
