"""열차/예약 정보 텍스트 포맷터."""

from __future__ import annotations

from typing import Any


def format_train_for_select(train, index: int, rail_type: str) -> dict[str, str]:
    """열차 객체를 UI용 딕셔너리로 변환."""
    if rail_type == "SRT":
        return {
            "train_name": getattr(train, "train_name", "SRT"),
            "train_number": getattr(train, "train_number", ""),
            "dep_time": getattr(train, "dep_time", ""),
            "arr_time": getattr(train, "arr_time", ""),
            "seat_info": _srt_seat_info(train),
        }
    else:
        return {
            "train_name": getattr(train, "train_name", "KTX"),
            "train_number": getattr(train, "train_number", ""),
            "dep_time": getattr(train, "dep_time", ""),
            "arr_time": getattr(train, "arr_time", ""),
            "seat_info": _ktx_seat_info(train),
        }


def _srt_seat_info(train) -> str:
    """SRT 좌석 정보 문자열."""
    parts = []
    gen = getattr(train, "general_seat_state", "")
    spc = getattr(train, "special_seat_state", "")
    parts.append(f"일반: {gen}")
    parts.append(f"특실: {spc}")
    if hasattr(train, "reserve_standby_available") and train.reserve_standby_available():
        parts.append("예약대기: 가능")
    return " | ".join(parts)


def _ktx_seat_info(train) -> str:
    """KTX 좌석 정보 문자열."""
    parts = []
    if hasattr(train, "has_general_seat"):
        parts.append(f"일반: {'가능' if train.has_general_seat() else '매진'}")
    if hasattr(train, "has_special_seat"):
        parts.append(f"특실: {'가능' if train.has_special_seat() else '매진'}")
    if hasattr(train, "has_waiting_list") and train.has_waiting_list():
        parts.append("예약대기: 가능")
    return " | ".join(parts)


def format_reservation_detail(reservation, rail_type: str) -> str:
    """예약 결과 상세 문자열."""
    if rail_type == "SRT":
        lines = [str(reservation)]
        if hasattr(reservation, "tickets"):
            for ticket in reservation.tickets:
                lines.append(str(ticket))
        return "\n".join(lines)
    else:
        return str(reservation).strip()


def format_trains_summary(trains_data: list[dict[str, str]]) -> str:
    """선택된 열차 요약 문자열."""
    parts = []
    for t in trains_data:
        dep = t["dep_time"]
        arr = t["arr_time"]
        parts.append(f"{t.get('train_name', '')} {t.get('train_number', '')} ({dep[:2]}:{dep[2:4]}→{arr[:2]}:{arr[2:4]})")
    return "\n".join(parts) if parts else "없음"


def format_elapsed(seconds: float) -> str:
    """경과 시간 포맷."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
