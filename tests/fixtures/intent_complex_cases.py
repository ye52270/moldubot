from __future__ import annotations

from typing import TypedDict


class IntentComplexCase(TypedDict):
    """
    복합 의도 구조분해 평가 케이스 타입.

    Attributes:
        case_id: 케이스 식별자
        utterance: 사용자 복합 질의 원문
        pattern: 케이스 설명
        required_steps: 의도 충족을 위한 필수 step 목록
    """

    case_id: int
    utterance: str
    pattern: str
    required_steps: list[str]


INTENT_COMPLEX_CASES: list[IntentComplexCase] = [
    {
        "case_id": 1,
        "utterance": "현재메일에서 주요 수신자 정보를 알려주고 표 형태로 정리해줘. 그리고 요약보고서를 만들어줘.",
        "pattern": "현재메일+수신자+요약보고서",
        "required_steps": ["read_current_mail", "extract_recipients", "summarize_mail"],
    },
    {
        "case_id": 2,
        "utterance": "현재메일 핵심 내용 3줄 요약하고 내가 해야 할 액션아이템도 뽑아줘.",
        "pattern": "현재메일+요약+핵심추출",
        "required_steps": ["read_current_mail", "summarize_mail", "extract_key_facts"],
    },
    {
        "case_id": 3,
        "utterance": "지난주 조영득 관련 메일 5개 조회해서 공통 이슈를 보고서 형태로 정리해줘.",
        "pattern": "검색+요약보고서",
        "required_steps": ["search_mails", "summarize_mail"],
    },
    {
        "case_id": 4,
        "utterance": "1월달 M365 관련 메일 찾아서 중요한 포인트랑 수신자 목록을 같이 보여줘.",
        "pattern": "월기반검색+핵심+수신자",
        "required_steps": ["search_mails", "extract_key_facts", "extract_recipients"],
    },
    {
        "case_id": 5,
        "utterance": "현재메일 읽고 바로 팀 공유용 요약보고서랑 체크리스트까지 만들어줘.",
        "pattern": "현재메일+보고서+체크리스트",
        "required_steps": ["read_current_mail", "summarize_mail", "extract_key_facts"],
    },
    {
        "case_id": 6,
        "utterance": "최근 4주 보안 점검 메일 조회하고 담당자별로 정리한 뒤 핵심만 5줄로 요약해줘.",
        "pattern": "기간검색+요약",
        "required_steps": ["search_mails", "summarize_mail"],
    },
    {
        "case_id": 7,
        "utterance": "현재메일 기준으로 수신자 정보를 먼저 뽑고, 이어서 회의 일정도 같이 확인해줘.",
        "pattern": "현재메일+수신자+회의일정",
        "required_steps": ["read_current_mail", "extract_recipients", "search_meeting_schedule"],
    },
    {
        "case_id": 8,
        "utterance": "김부장 관련 최근 메일 조회해서 보고서로 정리하고 마지막에 한 줄 결론도 써줘.",
        "pattern": "검색+보고서",
        "required_steps": ["search_mails", "summarize_mail"],
    },
    {
        "case_id": 9,
        "utterance": "현재메일 주요내용 요약해주고 중요한 숫자나 일정 정보만 별도로 뽑아줘.",
        "pattern": "현재메일+요약+핵심",
        "required_steps": ["read_current_mail", "summarize_mail", "extract_key_facts"],
    },
    {
        "case_id": 10,
        "utterance": "지난달 ESG 메일 조회하고 수신자와 핵심요약을 같이 표로 정리해줘.",
        "pattern": "검색+수신자+요약",
        "required_steps": ["search_mails", "extract_recipients", "summarize_mail"],
    },
    {
        "case_id": 11,
        "utterance": "현재메일을 기반으로 보고서 만들고, 누가 받았는지도 함께 알려줘.",
        "pattern": "현재메일+보고서+수신자",
        "required_steps": ["read_current_mail", "summarize_mail", "extract_recipients"],
    },
    {
        "case_id": 12,
        "utterance": "최근 메일에서 회의실 예약 관련 건만 찾아서 일정 충돌 가능성까지 정리해줘.",
        "pattern": "검색+회의일정",
        "required_steps": ["search_mails", "search_meeting_schedule"],
    },
    {
        "case_id": 13,
        "utterance": "현재메일에서 수신자 추출하고, 다음으로 요약보고서 작성해줘.",
        "pattern": "현재메일+수신자+보고서",
        "required_steps": ["read_current_mail", "extract_recipients", "summarize_mail"],
    },
    {
        "case_id": 14,
        "utterance": "지난주 메일 조회해서 핵심 포인트를 뽑고 바로 팀 회의 일정도 찾아줘.",
        "pattern": "검색+핵심+회의일정",
        "required_steps": ["search_mails", "extract_key_facts", "search_meeting_schedule"],
    },
    {
        "case_id": 15,
        "utterance": "현재메일 요약해주고, 보고서 형식으로 다시 정리한 버전도 추가해줘.",
        "pattern": "현재메일+요약",
        "required_steps": ["read_current_mail", "summarize_mail"],
    },
    {
        "case_id": 16,
        "utterance": "M365 장애 관련 메일 최근 3개 조회 후 수신자와 조치사항 중심으로 정리해줘.",
        "pattern": "검색+수신자+핵심",
        "required_steps": ["search_mails", "extract_recipients", "extract_key_facts"],
    },
    {
        "case_id": 17,
        "utterance": "현재메일 기반으로 표 형식 수신자 목록과 3단락 요약보고서를 같이 만들어줘.",
        "pattern": "현재메일+수신자+보고서",
        "required_steps": ["read_current_mail", "extract_recipients", "summarize_mail"],
    },
    {
        "case_id": 18,
        "utterance": "지난주부터 이번주까지 결재 지연 메일 조회하고 핵심이슈, 수신자, 요약을 한 번에 보여줘.",
        "pattern": "기간검색+핵심+수신자+요약",
        "required_steps": ["search_mails", "extract_key_facts", "extract_recipients", "summarize_mail"],
    },
    {
        "case_id": 19,
        "utterance": "현재메일 읽고 수신자와 본문 핵심을 정리한 뒤 회의 일정 확인까지 해줘.",
        "pattern": "현재메일+수신자+핵심+회의일정",
        "required_steps": ["read_current_mail", "extract_recipients", "extract_key_facts", "search_meeting_schedule"],
    },
    {
        "case_id": 20,
        "utterance": "최근 2주 메일 조회해서 보고서 요약 만들고 마지막에 액션아이템도 추출해줘.",
        "pattern": "검색+요약+핵심",
        "required_steps": ["search_mails", "summarize_mail", "extract_key_facts"],
    },
]
