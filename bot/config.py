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

    # 예약 폴링 간격 (초) - 기본 랜덤 대기
    poll_interval_shape: float = 5.0    # 감마분포 shape (높을수록 평균 증가)
    poll_interval_scale: float = 0.5    # 감마분포 scale (높을수록 분산 증가)
    poll_interval_min: float = 1.5      # 최소 대기 시간 (초)

    # 미세 휴식 (micro-break): N회 요청마다 짧은 휴식
    micro_break_interval_min: int = 15   # 미세 휴식 간격 최소 (요청 횟수)
    micro_break_interval_max: int = 30   # 미세 휴식 간격 최대 (요청 횟수)
    micro_break_duration_min: float = 10.0   # 미세 휴식 최소 시간 (초)
    micro_break_duration_max: float = 45.0   # 미세 휴식 최대 시간 (초)

    # 활동/휴식 사이클: 일정 시간 검색 후 장시간 휴식
    poll_active_minutes: int = 60        # 활성 검색 기준 시간 (분), 매 사이클 ±15% 편차
    poll_active_jitter: float = 0.15     # 활성 검색 시간 편차 비율 (0.15 = ±15%)
    poll_rest_minutes_min: int = 30      # 휴식 최소 시간 (분) = 30분
    poll_rest_minutes_max: int = 90      # 휴식 최대 시간 (분) = 1시간 30분

    # 전체 검색 제한
    poll_max_hours: float = 0            # 최대 총 검색 시간 (시간, 0=무제한)
    poll_max_cycles: int = 0             # 최대 활동/휴식 사이클 수 (0=무제한)

    # VPN/프록시 (NordVPN SOCKS5)
    proxy_enabled: bool = False
    proxy_user: str = ""          # NordVPN 서비스 사용자명
    proxy_pass: str = ""          # NordVPN 서비스 비밀번호
    proxy_servers: str = ""       # 콤마 구분 서버 목록 (예: "seoul.socks.nordhold.net,tokyo.socks.nordhold.net")
    proxy_port: int = 1080        # SOCKS5 포트
    proxy_rotate: bool = True     # 사이클마다 프록시 서버 로테이션
    gluetun_api_url: str = ""     # Gluetun 제어 API (예: "http://gluetun:8000")

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
            # 폴링 간격
            poll_interval_shape=float(os.environ.get("POLL_INTERVAL_SHAPE", "5.0")),
            poll_interval_scale=float(os.environ.get("POLL_INTERVAL_SCALE", "0.5")),
            poll_interval_min=float(os.environ.get("POLL_INTERVAL_MIN", "1.5")),
            # 미세 휴식
            micro_break_interval_min=int(os.environ.get("MICRO_BREAK_INTERVAL_MIN", "15")),
            micro_break_interval_max=int(os.environ.get("MICRO_BREAK_INTERVAL_MAX", "30")),
            micro_break_duration_min=float(os.environ.get("MICRO_BREAK_DURATION_MIN", "10.0")),
            micro_break_duration_max=float(os.environ.get("MICRO_BREAK_DURATION_MAX", "45.0")),
            # 활동/휴식 사이클
            poll_active_minutes=int(os.environ.get("POLL_ACTIVE_MINUTES", "60")),
            poll_active_jitter=float(os.environ.get("POLL_ACTIVE_JITTER", "0.15")),
            poll_rest_minutes_min=int(os.environ.get("POLL_REST_MINUTES_MIN", "30")),
            poll_rest_minutes_max=int(os.environ.get("POLL_REST_MINUTES_MAX", "90")),
            # 전체 제한
            poll_max_hours=float(os.environ.get("POLL_MAX_HOURS", "0")),
            poll_max_cycles=int(os.environ.get("POLL_MAX_CYCLES", "0")),
            # VPN/프록시
            proxy_enabled=os.environ.get("PROXY_ENABLED", "").lower() in ("true", "1", "yes"),
            proxy_user=os.environ.get("PROXY_USER", ""),
            proxy_pass=os.environ.get("PROXY_PASS", ""),
            proxy_servers=os.environ.get("PROXY_SERVERS", ""),
            proxy_port=int(os.environ.get("PROXY_PORT", "1080")),
            proxy_rotate=os.environ.get("PROXY_ROTATE", "true").lower() in ("true", "1", "yes"),
            gluetun_api_url=os.environ.get("GLUETUN_API_URL", ""),
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
