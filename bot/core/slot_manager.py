"""동시 예약 슬롯 관리."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class SlotInfo:
    """슬롯에 할당된 예약 정보."""

    session_id: int
    discord_id: str
    channel_id: str
    rail_type: str


class SlotManager:
    """최대 N개 동시 예약 세션 관리 (asyncio.Lock 기반)."""

    def __init__(self, max_slots: int = 4) -> None:
        self._max_slots = max_slots
        self._lock = asyncio.Lock()
        self._slots: dict[int, SlotInfo] = {}  # session_id → SlotInfo

    @property
    def active_count(self) -> int:
        return len(self._slots)

    @property
    def available(self) -> int:
        return self._max_slots - len(self._slots)

    @property
    def is_full(self) -> bool:
        return len(self._slots) >= self._max_slots

    def get_slots(self) -> list[SlotInfo]:
        return list(self._slots.values())

    def get_user_slots(self, discord_id: str) -> list[SlotInfo]:
        return [s for s in self._slots.values() if s.discord_id == discord_id]

    async def acquire(self, session_id: int, discord_id: str, channel_id: str, rail_type: str) -> bool:
        """슬롯 할당 시도. 성공 시 True."""
        async with self._lock:
            if self.is_full:
                return False
            self._slots[session_id] = SlotInfo(
                session_id=session_id,
                discord_id=discord_id,
                channel_id=channel_id,
                rail_type=rail_type,
            )
            return True

    async def release(self, session_id: int) -> bool:
        """슬롯 해제. 존재했으면 True."""
        async with self._lock:
            return self._slots.pop(session_id, None) is not None

    async def force_release_all(self) -> int:
        """모든 슬롯 강제 해제. 해제된 수 반환."""
        async with self._lock:
            count = len(self._slots)
            self._slots.clear()
            return count

    async def force_release_by_channel(self, channel_id: str) -> bool:
        """채널 ID로 슬롯 강제 해제."""
        async with self._lock:
            to_remove = [
                sid for sid, info in self._slots.items()
                if info.channel_id == channel_id
            ]
            for sid in to_remove:
                del self._slots[sid]
            return len(to_remove) > 0
