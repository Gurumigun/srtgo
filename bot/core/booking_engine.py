"""SRT/KTX 비동기 래퍼 + 예약 폴링 루프."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from random import choice as random_choice, gammavariate, randint, uniform
from typing import Any, TYPE_CHECKING

from .booking_session import BookingSession, PassengerInfo, SessionStatus

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)

# 기존 srtgo 모듈 import
from srtgo.srt import (
    SRT,
    SRTError,
    SeatType,
    Adult,
    Child,
    Senior,
)
from srtgo.ktx import (
    Korail,
    KorailError,
    ReserveOption,
    TrainType,
    AdultPassenger,
    ChildPassenger,
    SeniorPassenger,
)


# 감마분포 기반 랜덤 대기 파라미터 (기본값, Config로 오버라이드 됨)
POLL_SHAPE = 5.0
POLL_SCALE = 0.5
POLL_MIN = 1.5


def _build_passengers_srt(info: PassengerInfo) -> list:
    """SRT 승객 객체 목록 생성."""
    passengers = []
    if info.adults > 0:
        passengers.append(Adult(info.adults))
    if info.children > 0:
        passengers.append(Child(info.children))
    if info.seniors > 0:
        passengers.append(Senior(info.seniors))
    return passengers


def _build_passengers_ktx(info: PassengerInfo) -> list:
    """KTX 승객 객체 목록 생성."""
    passengers = []
    if info.adults > 0:
        passengers.append(AdultPassenger(info.adults))
    if info.children > 0:
        passengers.append(ChildPassenger(info.children))
    if info.seniors > 0:
        passengers.append(SeniorPassenger(info.seniors))
    return passengers


def _get_seat_option(seat_type_str: str, is_srt: bool):
    """좌석 유형 문자열 → SeatType/ReserveOption 변환."""
    if is_srt:
        return {
            "GENERAL_FIRST": SeatType.GENERAL_FIRST,
            "GENERAL_ONLY": SeatType.GENERAL_ONLY,
            "SPECIAL_FIRST": SeatType.SPECIAL_FIRST,
            "SPECIAL_ONLY": SeatType.SPECIAL_ONLY,
        }[seat_type_str]
    else:
        return {
            "GENERAL_FIRST": ReserveOption.GENERAL_FIRST,
            "GENERAL_ONLY": ReserveOption.GENERAL_ONLY,
            "SPECIAL_FIRST": ReserveOption.SPECIAL_FIRST,
            "SPECIAL_ONLY": ReserveOption.SPECIAL_ONLY,
        }[seat_type_str]


def _is_seat_available(train, seat_type_str: str, is_srt: bool) -> bool:
    """좌석 가용성 확인 (기존 srtgo.py 로직 동일)."""
    if is_srt:
        seat_type = _get_seat_option(seat_type_str, True)
        if not train.seat_available():
            return train.reserve_standby_available()
        if seat_type in (SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST):
            return train.seat_available()
        if seat_type == SeatType.GENERAL_ONLY:
            return train.general_seat_available()
        return train.special_seat_available()
    else:
        seat_type = _get_seat_option(seat_type_str, False)
        if not train.has_seat():
            return train.has_waiting_list()
        if seat_type in (ReserveOption.GENERAL_FIRST, ReserveOption.SPECIAL_FIRST):
            return train.has_seat()
        if seat_type == ReserveOption.GENERAL_ONLY:
            return train.has_general_seat()
        return train.has_special_seat()


def _has_confirmed_seat(train, seat_type_str: str, is_srt: bool) -> bool:
    """확정 좌석 가용성만 확인 (예약대기/대기 제외)."""
    if is_srt:
        if not train.seat_available():
            return False
        seat_type = _get_seat_option(seat_type_str, True)
        if seat_type in (SeatType.GENERAL_FIRST, SeatType.SPECIAL_FIRST):
            return train.seat_available()
        if seat_type == SeatType.GENERAL_ONLY:
            return train.general_seat_available()
        return train.special_seat_available()
    else:
        if not train.has_seat():
            return False
        seat_type = _get_seat_option(seat_type_str, False)
        if seat_type in (ReserveOption.GENERAL_FIRST, ReserveOption.SPECIAL_FIRST):
            return train.has_seat()
        if seat_type == ReserveOption.GENERAL_ONLY:
            return train.has_general_seat()
        return train.has_special_seat()


class BookingEngine:
    """SRT/KTX 비동기 예약 엔진.

    동기 라이브러리를 ThreadPoolExecutor로 감싸서 비동기로 실행한다.
    """

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor
        self._proxy_servers: list[str] = []
        self._proxy_index: int = 0

    async def _run_sync(self, func, *args, **kwargs):
        """동기 함수를 비동기로 실행."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    def _get_proxy_url(self, bot: SRTGoBot) -> str | None:
        """현재 프록시 URL 반환. 비활성화 시 None."""
        cfg = bot.config
        if not cfg.proxy_enabled or not cfg.proxy_servers:
            return None

        if not self._proxy_servers:
            self._proxy_servers = [
                s.strip() for s in cfg.proxy_servers.split(",") if s.strip()
            ]

        if not self._proxy_servers:
            return None

        server = self._proxy_servers[self._proxy_index % len(self._proxy_servers)]
        return f"socks5://{cfg.proxy_user}:{cfg.proxy_pass}@{server}:{cfg.proxy_port}"

    def _rotate_proxy(self, bot: SRTGoBot) -> None:
        """다음 프록시 서버로 로테이션."""
        if bot.config.proxy_rotate and self._proxy_servers:
            self._proxy_index = (self._proxy_index + 1) % len(self._proxy_servers)
            log.info("프록시 로테이션: %s", self._proxy_servers[self._proxy_index])

    def _apply_proxy(self, client, bot: SRTGoBot) -> None:
        """로그인된 클라이언트에 프록시 설정 적용."""
        proxy_url = self._get_proxy_url(bot)
        if proxy_url and hasattr(client, "_session"):
            client._session.proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }
            log.info("프록시 적용: %s", proxy_url.split("@")[-1])

    async def login(
        self, rail_type: str, user_id: str, user_pw: str,
        verbose: bool = False, bot: SRTGoBot | None = None,
    ):
        """로그인하여 클라이언트 반환. 프록시 설정도 적용."""
        if rail_type == "SRT":
            client = await self._run_sync(SRT, user_id, user_pw, True, verbose)
        else:
            client = await self._run_sync(Korail, user_id, user_pw, True, verbose)

        if bot:
            self._apply_proxy(client, bot)
        return client

    async def search_trains(self, session: BookingSession) -> list:
        """열차 검색. 복수 시간이 콤마로 구분되어 있으면 각각 검색 후 합산."""
        is_srt = session.rail_type == "SRT"

        total_count = session.passengers.total
        if is_srt:
            search_passengers = [Adult(total_count)]
        else:
            search_passengers = [AdultPassenger(total_count)]

        # 복수 시간 지원: 콤마 구분
        times = session.time.split(",") if "," in session.time else [session.time]
        all_trains = []
        seen_keys: set[str] = set()

        for t in times:
            if is_srt:
                params = {
                    "dep": session.departure,
                    "arr": session.arrival,
                    "date": session.date,
                    "time": t,
                    "passengers": search_passengers,
                    "available_only": False,
                }
            else:
                params = {
                    "dep": session.departure,
                    "arr": session.arrival,
                    "date": session.date,
                    "time": t,
                    "passengers": search_passengers,
                    "include_no_seats": True,
                }

            trains = await self._run_sync(session.rail_client.search_train, **params)

            for train in trains:
                # 중복 제거: 열차번호 + 출발시간
                train_no = getattr(train, "train_number", None) or getattr(train, "train_no", "")
                dep_time = getattr(train, "dep_time", "")
                key = f"{train_no}_{dep_time}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_trains.append(train)

        # 출발시간 기준 정렬
        all_trains.sort(key=lambda tr: getattr(tr, "dep_time", ""))
        session.trains_cache = all_trains
        return all_trains

    async def reserve(self, session: BookingSession, train) -> Any:
        """예약 실행."""
        is_srt = session.rail_type == "SRT"
        passengers = _build_passengers_srt(session.passengers) if is_srt else _build_passengers_ktx(session.passengers)
        option = _get_seat_option(session.seat_type, is_srt)

        if is_srt:
            # SRT: 매진이면 예약대기 시도
            if not train.seat_available() and train.reserve_standby_available():
                return await self._run_sync(
                    session.rail_client.reserve_standby,
                    train, passengers, option,
                )
            return await self._run_sync(
                session.rail_client.reserve,
                train, passengers, option,
            )
        else:
            return await self._run_sync(
                session.rail_client.reserve,
                train, passengers, option,
            )

    async def pay_with_card(
        self,
        session: BookingSession,
        reservation,
        card_info: dict[str, str],
    ) -> bool:
        """카드 결제."""
        birthday = card_info["birthday"]
        card_type = "J" if len(birthday) == 6 else "S"
        return await self._run_sync(
            session.rail_client.pay_with_card,
            reservation,
            card_info["number"],
            card_info["password"],
            birthday,
            card_info["expire"],
            0,
            card_type,
        )

    async def get_reservations(self, session: BookingSession) -> list:
        """예약 목록 조회."""
        if session.rail_type == "SRT":
            return await self._run_sync(session.rail_client.get_reservations)
        else:
            return await self._run_sync(session.rail_client.reservations)

    async def cancel_reservation(self, session: BookingSession, reservation) -> bool:
        """예약 취소."""
        return await self._run_sync(session.rail_client.cancel, reservation)

    def _random_delay(self, bot: SRTGoBot) -> float:
        """감마분포 기반 랜덤 대기 시간 생성 (초)."""
        cfg = bot.config
        return gammavariate(cfg.poll_interval_shape, cfg.poll_interval_scale) + cfg.poll_interval_min

    def _next_micro_break_count(self, bot: SRTGoBot) -> int:
        """다음 미세 휴식까지의 요청 횟수 (랜덤)."""
        cfg = bot.config
        return randint(cfg.micro_break_interval_min, cfg.micro_break_interval_max)

    def _micro_break_duration(self, bot: SRTGoBot) -> float:
        """미세 휴식 시간 (랜덤, 초)."""
        cfg = bot.config
        return uniform(cfg.micro_break_duration_min, cfg.micro_break_duration_max)

    def _active_duration(self, bot: SRTGoBot) -> float:
        """활동 시간 (기준값 ± jitter%, 초). 매 사이클마다 다른 값."""
        cfg = bot.config
        base = cfg.poll_active_minutes * 60
        jitter = cfg.poll_active_jitter
        return uniform(base * (1 - jitter), base * (1 + jitter))

    def _rest_duration(self, bot: SRTGoBot) -> float:
        """활동/휴식 사이클의 휴식 시간 (랜덤, 초)."""
        cfg = bot.config
        return uniform(cfg.poll_rest_minutes_min * 60, cfg.poll_rest_minutes_max * 60)

    async def polling_loop(
        self,
        session: BookingSession,
        on_progress: Any,  # Callable[[int, str], Awaitable]
        on_success: Any,   # Callable[[Any], Awaitable]
        on_error: Any,     # Callable[[str], Awaitable]
        bot: SRTGoBot,
        on_waiting: Any = None,  # Callable[[Any], Awaitable] - 예약대기 콜백
        on_rest: Any = None,     # Callable[[int, str], Awaitable] - 휴식 시작 콜백
        on_resume: Any = None,   # Callable[[int], Awaitable] - 검색 재개 콜백
    ) -> None:
        """예매 폴링 루프 (매크로 회피 기능 포함).

        기존 srtgo.py의 reserve() 루프를 비동기로 재현.
        예약대기(standby) 확보 시 on_waiting 호출 후 확정 좌석을 계속 검색한다.

        매크로 회피 전략:
        1. 감마분포 기반 랜덤 대기 (요청마다)
        2. 미세 휴식: N회 요청마다 10~45초 대기
        3. 활동/휴식 사이클: 활성 검색 → 장시간 휴식 → 반복
        4. 최대 시간 제한: 전체 검색 시간 초과 시 자동 종료
        """
        is_srt = session.rail_type == "SRT"
        cfg = bot.config
        session.status = SessionStatus.SEARCHING
        await bot.session_repo.set_status(session.session_id, "searching")

        total_start_time = time.time()
        cycle_start_time = time.time()
        current_active_limit = self._active_duration(bot)  # 이번 사이클 활동 시간 (±jitter)
        has_waiting = False  # 예약대기 확보 여부
        cycle_count = 0      # 현재 사이클 번호
        requests_since_break = 0  # 미세 휴식 이후 요청 수
        next_break_at = self._next_micro_break_count(bot)  # 다음 미세 휴식까지 요청 수

        while session.status == SessionStatus.SEARCHING:
            try:
                # ── 전체 시간 제한 확인 ──
                total_elapsed = time.time() - total_start_time
                if cfg.poll_max_hours > 0 and total_elapsed >= cfg.poll_max_hours * 3600:
                    log.info(
                        "최대 검색 시간 초과 (%.1f시간): 세션 %s 종료",
                        cfg.poll_max_hours, session.session_id,
                    )
                    session.status = SessionStatus.TIMEOUT
                    await bot.session_repo.set_status(session.session_id, "timeout")
                    await on_error(
                        f"최대 검색 시간({cfg.poll_max_hours}시간)이 초과되어 자동 종료됩니다."
                    )
                    return

                # ── 활동/휴식 사이클 확인 ──
                cycle_elapsed = time.time() - cycle_start_time
                if cfg.poll_active_minutes > 0 and cycle_elapsed >= current_active_limit:
                    cycle_count += 1
                    active_mins = int(current_active_limit / 60)

                    # 최대 사이클 수 확인
                    if cfg.poll_max_cycles > 0 and cycle_count >= cfg.poll_max_cycles:
                        log.info(
                            "최대 사이클 초과 (%d회): 세션 %s 종료",
                            cfg.poll_max_cycles, session.session_id,
                        )
                        session.status = SessionStatus.TIMEOUT
                        await bot.session_repo.set_status(session.session_id, "timeout")
                        await on_error(
                            f"최대 검색 사이클({cfg.poll_max_cycles}회)이 초과되어 자동 종료됩니다."
                        )
                        return

                    # 휴식 진입
                    rest_secs = self._rest_duration(bot)
                    rest_mins = int(rest_secs / 60)
                    log.info(
                        "세션 %s: %d분 활동 후 약 %d분 휴식 (사이클 %d)",
                        session.session_id, active_mins, rest_mins, cycle_count,
                    )

                    if on_rest:
                        await on_rest(rest_mins, f"사이클 {cycle_count}")

                    await asyncio.sleep(rest_secs)

                    # 휴식 후 재로그인 (세션 만료 방지)
                    try:
                        creds = await bot.user_repo.get_credentials(
                            session.discord_id, session.rail_type
                        )
                        if creds:
                            session.rail_client = await self.login(
                                session.rail_type, creds[0], creds[1], bot=bot,
                            )
                    except Exception:
                        log.exception("휴식 후 재로그인 실패")
                        session.status = SessionStatus.ERROR
                        await on_error("휴식 후 재로그인 실패")
                        return

                    # 프록시 로테이션 (휴식 후 새 IP로 전환)
                    self._rotate_proxy(bot)

                    cycle_start_time = time.time()
                    current_active_limit = self._active_duration(bot)  # 새 사이클마다 다른 활동 시간
                    requests_since_break = 0
                    next_break_at = self._next_micro_break_count(bot)

                    if on_resume:
                        await on_resume(cycle_count + 1)

                # ── 미세 휴식 확인 ──
                requests_since_break += 1
                if requests_since_break >= next_break_at:
                    break_duration = self._micro_break_duration(bot)
                    log.debug(
                        "세션 %s: 미세 휴식 %.1f초 (%d회 요청 후)",
                        session.session_id, break_duration, requests_since_break,
                    )
                    await asyncio.sleep(break_duration)
                    requests_since_break = 0
                    next_break_at = self._next_micro_break_count(bot)

                # ── 실제 검색/예약 로직 ──
                session.attempt_count += 1
                await bot.session_repo.increment_attempt(session.session_id)

                # 진행 상태 업데이트 (10회마다)
                if session.attempt_count % 10 == 0:
                    elapsed = time.time() - total_start_time
                    hours, remainder = divmod(int(elapsed), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    elapsed_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    await on_progress(session.attempt_count, elapsed_str)

                # 열차 검색
                trains = await self.search_trains(session)

                # 선택된 열차 확인
                for idx in session.selected_train_indices:
                    if idx < len(trains):
                        train = trains[idx]

                        # 예약대기 확보 후에는 확정 좌석만 확인
                        if has_waiting:
                            available = _has_confirmed_seat(train, session.seat_type, is_srt)
                        else:
                            available = _is_seat_available(train, session.seat_type, is_srt)

                        if available:
                            # 예약 시도
                            reservation = await self.reserve(session, train)
                            is_waiting_rsv = getattr(reservation, "is_waiting", False)

                            # 예약번호 저장
                            if is_srt:
                                rsv_number = reservation.reservation_number
                            else:
                                rsv_number = reservation.rsv_id

                            if is_waiting_rsv and not has_waiting:
                                # 예약대기 → 저장하고 계속 진행
                                has_waiting = True
                                session.reservation_number = rsv_number
                                await bot.session_repo.update_session(
                                    session.session_id,
                                    reservation_number=rsv_number,
                                )
                                if on_waiting:
                                    await on_waiting(reservation)
                                break  # 이번 루프의 열차 탐색 중단, 다음 폴링으로

                            elif not is_waiting_rsv:
                                # 확정 예약 → 성공
                                session.status = SessionStatus.RESERVED
                                session.reservation_number = rsv_number

                                await bot.session_repo.set_status(session.session_id, "reserved")
                                await bot.session_repo.update_session(
                                    session.session_id,
                                    reservation_number=rsv_number,
                                )

                                await on_success(reservation)
                                return

                # 감마분포 기반 랜덤 대기
                await asyncio.sleep(self._random_delay(bot))

            except (SRTError, KorailError) as ex:
                msg = str(ex)
                err_msg = getattr(ex, "msg", msg)

                if isinstance(ex, SRTError):
                    if "정상적인 경로로 접근 부탁드립니다" in err_msg:
                        session.rail_client.clear()
                        log.debug("NetFunnel 키 클리어 후 재시도")
                    elif "로그인 후 사용하십시오" in err_msg:
                        log.info("세션 만료, 재로그인 시도")
                        try:
                            creds = await bot.user_repo.get_credentials(
                                session.discord_id, session.rail_type
                            )
                            if creds:
                                session.rail_client = await self.login(
                                    session.rail_type, creds[0], creds[1], bot=bot,
                                )
                        except Exception:
                            log.exception("재로그인 실패")
                            session.status = SessionStatus.ERROR
                            await on_error("재로그인 실패")
                            return
                    elif not any(
                        e in err_msg
                        for e in (
                            "잔여석없음",
                            "사용자가 많아 접속이 원활하지 않습니다",
                            "예약대기 접수가 마감되었습니다",
                            "예약대기자한도수초과",
                        )
                    ):
                        log.warning("SRT 에러: %s", err_msg)
                        session.status = SessionStatus.ERROR
                        await on_error(f"예매 오류: {err_msg}")
                        return
                else:
                    # KorailError
                    if not any(
                        e in msg
                        for e in ("Sold out", "잔여석없음", "예약대기자한도수초과")
                    ):
                        log.warning("Korail 에러: %s", msg)
                        session.status = SessionStatus.ERROR
                        await on_error(f"예매 오류: {msg}")
                        return

                await asyncio.sleep(self._random_delay(bot))

            except asyncio.CancelledError:
                session.status = SessionStatus.CANCELLED
                await bot.session_repo.set_status(session.session_id, "cancelled")
                return

            except Exception as ex:
                log.exception("예기치 않은 오류")
                # 재로그인 시도
                try:
                    creds = await bot.user_repo.get_credentials(
                        session.discord_id, session.rail_type
                    )
                    if creds:
                        session.rail_client = await self.login(
                            session.rail_type, creds[0], creds[1], bot=bot,
                        )
                except Exception:
                    session.status = SessionStatus.ERROR
                    await on_error(f"예기치 않은 오류: {ex}")
                    return

                await asyncio.sleep(self._random_delay(bot))
