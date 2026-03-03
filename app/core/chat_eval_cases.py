from __future__ import annotations

from typing import TypedDict


class ChatEvalCase(TypedDict):
    """
    실호출 E2E 채팅 평가 케이스를 표현한다.

    Attributes:
        case_id: 케이스 식별자
        query: 사용자 입력 문장
        expectation: 기대 동작 설명
        requires_current_mail: 선택 메일 컨텍스트 필요 여부
    """

    case_id: str
    query: str
    expectation: str
    requires_current_mail: bool


CHAT_EVAL_CASES: list[ChatEvalCase] = [
    {
        "case_id": "mail-01",
        "query": "M365 프로젝트 일정관련 최근 2주 메일 찾아줘",
        "expectation": "최근 2주 범위와 M365 프로젝트 일정 관련 근거 메일을 조회해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-02",
        "query": "현재메일 요약",
        "expectation": "현재 선택 메일 기준 요약을 제공해야 한다.",
        "requires_current_mail": True,
    },
    {
        "case_id": "mail-03",
        "query": "조영득 관련 2월 메일 요약",
        "expectation": "조영득 관련 2월 메일 결과를 기반으로 요약을 제공해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-04",
        "query": "조영득 관련 2월 메일",
        "expectation": "조영득 관련 2월 메일 목록/근거를 조회해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-05",
        "query": "박준용 관련 2월 메일",
        "expectation": "박준용 관련 2월 메일 목록/근거를 조회해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-06",
        "query": "tenant 이슈관련 최근 메일",
        "expectation": "tenant 이슈 키워드 기준 최근 메일을 조회해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-07",
        "query": "M365 프로젝트 최근 2주 메일의 주요 내용과 수/발신자 표로 정리",
        "expectation": "최근 2주 메일 조회 후 주요 내용과 수/발신자 정보를 표 형태로 제공해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-08",
        "query": "ESG 구축과 관련된 1월 메일 조회하고 todo list를 만들어줘",
        "expectation": "1월 ESG 구축 관련 메일 조회 후 실행 가능한 TODO 목록을 제시해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-09",
        "query": "Sense mail 관련 된 메일 찾아줘",
        "expectation": "Sense mail 관련 근거 메일을 조회해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-10",
        "query": "메일 수발신 실패와 관련된 메일 찾아서 이슈가 뭔지 정리해줘..",
        "expectation": "메일 수발신 실패 관련 메일 조회 후 이슈를 요약해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-11",
        "query": "M365 프로젝트 최근 2주 메일을 3줄로 요약해줘",
        "expectation": "최근 2주 M365 메일 조회 후 3줄 요약 형식을 충족해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-12",
        "query": "tenant 이슈 관련 최근 메일을 보고서 형식으로 작성해줘",
        "expectation": "tenant 이슈 메일을 근거로 보고서 형식 응답을 제공해야 한다.",
        "requires_current_mail": False,
    },
    {
        "case_id": "mail-13",
        "query": "회의실 예약해줘",
        "expectation": "필수 슬롯이 없으면 실패/추가정보 안내를 제공해야 한다.",
        "requires_current_mail": False,
    },
]
