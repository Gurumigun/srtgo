"""개별 예약 세션 데이터 클래스."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionStatus(str, Enum):
    SETUP = "setup"
    SEARCHING = "searching"
    RESERVED = "reserved"
    PAID = "paid"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class PassengerInfo:
    """승객 정보."""

    adults: int = 1
    children: int = 0
    seniors: int = 0

    @property
    def total(self) -> int:
        return self.adults + self.children + self.seniors

    def to_dict(self) -> dict[str, int]:
        return {"adults": self.adults, "children": self.children, "seniors": self.seniors}

    @classmethod
    def from_dict(cls, d: dict[str, int]) -> PassengerInfo:
        return cls(
            adults=d.get("adults", 1),
            children=d.get("children", 0),
            seniors=d.get("seniors", 0),
        )

    def description(self) -> str:
        parts = []
        if self.adults:
            parts.append(f"어른 {self.adults}명")
        if self.children:
            parts.append(f"어린이 {self.children}명")
        if self.seniors:
            parts.append(f"경로 {self.seniors}명")
        return ", ".join(parts) if parts else "승객 없음"


@dataclass
class BookingSession:
    """예약 세션 메모리 상태."""

    session_id: int
    user_db_id: int
    discord_id: str
    channel_id: int
    rail_type: str  # "SRT" or "KTX"

    # 예약 파라미터
    departure: str = ""
    arrival: str = ""
    date: str = ""
    time: str = ""
    passengers: PassengerInfo = field(default_factory=PassengerInfo)
    seat_type: str = "GENERAL_FIRST"
    selected_train_indices: list[int] = field(default_factory=list)
    auto_pay: bool = False

    # 상태
    status: SessionStatus = SessionStatus.SETUP
    attempt_count: int = 0
    reservation_number: str = ""

    # 런타임 (DB에 저장하지 않음)
    rail_client: Any = field(default=None, repr=False)
    status_message: Any = field(default=None, repr=False)  # discord.Message
    trains_cache: list[Any] = field(default_factory=list, repr=False)

    @property
    def seat_type_desc(self) -> str:
        mapping = {
            "GENERAL_FIRST": "일반실 우선",
            "GENERAL_ONLY": "일반실만",
            "SPECIAL_FIRST": "특실 우선",
            "SPECIAL_ONLY": "특실만",
        }
        return mapping.get(self.seat_type, self.seat_type)
