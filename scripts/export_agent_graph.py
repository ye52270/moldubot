from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.deep_chat_agent import get_deep_chat_agent

PLACEHOLDER_OPENAI_KEY = "graph-placeholder-key"
DEFAULT_OUTPUT_RELATIVE_PATH = "docs/agent_graph.mmd"
logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """
    스크립트 로깅 포맷을 초기화한다.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")


@contextmanager
def temporary_openai_key() -> Iterator[None]:
    """
    OPENAI_API_KEY가 없을 때 그래프 생성용 플레이스홀더 키를 임시 주입한다.
    """
    original = os.getenv("OPENAI_API_KEY")
    if original and original.strip():
        yield
        return
    os.environ["OPENAI_API_KEY"] = PLACEHOLDER_OPENAI_KEY
    try:
        yield
    finally:
        os.environ.pop("OPENAI_API_KEY", None)


def generate_agent_graph_mermaid() -> str:
    """
    현재 deep agent 실행 그래프를 Mermaid 문자열로 생성한다.

    Returns:
        Mermaid 다이어그램 문자열
    """
    with temporary_openai_key():
        agent = get_deep_chat_agent()
        graph_view = agent._graph.get_graph()
        return str(graph_view.draw_mermaid()).strip()


def resolve_output_path(raw_output: str, root_dir: Path) -> Path:
    """
    출력 경로를 절대 경로로 정규화한다.

    Args:
        raw_output: CLI 인자로 받은 출력 경로
        root_dir: 프로젝트 루트 경로

    Returns:
        절대 경로로 정규화된 출력 파일 경로
    """
    candidate = Path(raw_output).expanduser()
    if candidate.is_absolute():
        return candidate
    return root_dir / candidate


def parse_args() -> argparse.Namespace:
    """
    CLI 인자를 파싱한다.

    Returns:
        파싱된 인자 네임스페이스
    """
    parser = argparse.ArgumentParser(description="MolduBot deep agent Mermaid 그래프를 파일로 저장한다.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_RELATIVE_PATH,
        help=f"그래프 저장 경로(기본: {DEFAULT_OUTPUT_RELATIVE_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    """
    에이전트 그래프를 생성해 파일로 저장한다.
    """
    configure_logging()
    args = parse_args()
    output_path = resolve_output_path(raw_output=str(args.output), root_dir=ROOT_DIR)
    mermaid = generate_agent_graph_mermaid()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(mermaid + "\n", encoding="utf-8")
    logger.info("에이전트 그래프 저장 완료: %s (length=%s)", output_path, len(mermaid))


if __name__ == "__main__":
    main()
