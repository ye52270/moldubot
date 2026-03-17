from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GraphMailMessage:
    """
    Graph 메일 표준 메시지 모델.
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str
    internet_message_id: str
    web_link: str
