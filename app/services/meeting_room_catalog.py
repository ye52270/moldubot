from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def load_meeting_rooms(path: Path) -> list[dict[str, Any]]:
    """
    회의실 마스터 파일을 읽어 평탄화된 회의실 목록으로 반환한다.

    Args:
        path: 회의실 데이터 JSON 파일 경로

    Returns:
        `building/floor/room_name` 필드를 포함한 회의실 목록
    """
    payload = _read_json(path=path)
    return normalize_meeting_rooms(payload=payload)


def normalize_meeting_rooms(payload: Any) -> list[dict[str, Any]]:
    """
    회의실 원본 JSON(평탄/계층)을 공통 목록 형태로 정규화한다.

    Args:
        payload: JSON 파싱 결과 객체

    Returns:
        정규화된 회의실 목록
    """
    if isinstance(payload, list):
        return _normalize_flat_rooms(items=payload)
    if isinstance(payload, dict):
        return _normalize_hierarchical_rooms(payload=payload)
    return []


def _read_json(path: Path) -> Any:
    """
    JSON 파일을 읽어 파이썬 객체로 반환한다.

    Args:
        path: JSON 파일 경로

    Returns:
        파싱된 객체. 실패 시 빈 리스트
    """
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("meeting room json parse failed: path=%s error=%s", path, exc)
        return []


def _normalize_flat_rooms(items: list[Any]) -> list[dict[str, Any]]:
    """
    평탄 리스트 회의실 데이터를 표준 목록으로 정규화한다.

    Args:
        items: 회의실 리스트

    Returns:
        정규화된 회의실 목록
    """
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        building = str(item.get("building", "")).strip()
        room_name = str(item.get("room_name", "")).strip() or str(item.get("name", "")).strip()
        if not building or not room_name:
            continue
        try:
            floor = int(item.get("floor", 0))
        except (TypeError, ValueError):
            continue
        normalized: dict[str, Any] = {
            "building": building,
            "floor": floor,
            "room_name": room_name,
            "capacity": int(item.get("capacity", 0) or 0),
            "features": item.get("features") if isinstance(item.get("features"), list) else [],
        }
        if "id" in item:
            normalized["id"] = item.get("id")
        rows.append(normalized)
    return rows


def _normalize_hierarchical_rooms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    계층형(building/floor/rooms) 회의실 데이터를 평탄 목록으로 변환한다.

    Args:
        payload: 계층형 JSON 객체

    Returns:
        정규화된 회의실 목록
    """
    buildings = payload.get("buildings")
    if not isinstance(buildings, list):
        return []
    rows: list[dict[str, Any]] = []
    for building in buildings:
        if not isinstance(building, dict):
            continue
        building_name = str(building.get("name", "")).strip()
        if not building_name:
            continue
        floors = building.get("floors")
        if not isinstance(floors, list):
            continue
        for floor_info in floors:
            if not isinstance(floor_info, dict):
                continue
            try:
                floor = int(floor_info.get("floor", 0))
            except (TypeError, ValueError):
                continue
            rooms = floor_info.get("rooms")
            if not isinstance(rooms, list):
                continue
            for room in rooms:
                if not isinstance(room, dict):
                    continue
                room_name = str(room.get("name", "")).strip()
                if not room_name:
                    continue
                row: dict[str, Any] = {
                    "building": building_name,
                    "floor": floor,
                    "room_name": room_name,
                    "capacity": int(room.get("capacity", 0) or 0),
                    "features": room.get("features") if isinstance(room.get("features"), list) else [],
                }
                if "id" in room:
                    row["id"] = room.get("id")
                if "floor_id" in floor_info:
                    row["floor_id"] = floor_info.get("floor_id")
                if "id" in building:
                    row["building_id"] = building.get("id")
                rows.append(row)
    return rows
