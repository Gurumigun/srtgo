"""환경변수 기반 설정 모듈."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """봇 설정 (환경변수에서 로드)."""

    # Discord
    discord_token: str = ""
    main_channel_id: int = 0
    category_id: int = 0

    # 보안
    master_key: str = ""  # 64자리 hex (32바이트)

    # DB
    db_path: str = "data/srtgo.db"

    # 슬롯
    max_slots: int = 4

    # 대화 타임아웃 (초)
    conversation_timeout: int = 300

    # 예약 폴링 간격 (초)
    poll_interval_shape: float = 4.0
    poll_interval_scale: float = 0.25
    poll_interval_min: float = 0.5

    # ThreadPool
    thread_pool_workers: int = 8

    @classmethod
    def from_env(cls) -> Config:
        """환경변수에서 Config 인스턴스 생성."""
        return cls(
            discord_token=os.environ.get("DISCORD_TOKEN", ""),
            main_channel_id=int(os.environ.get("MAIN_CHANNEL_ID", "0")),
            category_id=int(os.environ.get("CATEGORY_ID", "0")),
            master_key=os.environ.get("SRTGO_MASTER_KEY", ""),
            db_path=os.environ.get("SRTGO_DB_PATH", "data/srtgo.db"),
            max_slots=int(os.environ.get("MAX_SLOTS", "4")),
            conversation_timeout=int(os.environ.get("CONVERSATION_TIMEOUT", "300")),
        )

    def validate(self) -> list[str]:
        """설정 유효성 검사. 오류 목록 반환."""
        errors: list[str] = []
        if not self.discord_token:
            errors.append("DISCORD_TOKEN 누락")
        if not self.master_key or len(self.master_key) != 64:
            errors.append("SRTGO_MASTER_KEY는 64자리 hex 문자열이어야 합니다")
        if self.main_channel_id == 0:
            errors.append("MAIN_CHANNEL_ID 누락")
        if self.category_id == 0:
            errors.append("CATEGORY_ID 누락")
        return errors

    def ensure_db_dir(self) -> None:
        """DB 파일 디렉토리가 존재하도록 생성."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
