"""SRT/KTX 비동기 래퍼 + 예약 폴링 루프."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from random import gammavariate
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


# 감마분포 기반 랜덤 대기 파라미터
POLL_SHAPE = 4.0
POLL_SCALE = 0.25
POLL_MIN = 0.5


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


class BookingEngine:
    """SRT/KTX 비동기 예약 엔진.

    동기 라이브러리를 ThreadPoolExecutor로 감싸서 비동기로 실행한다.
    """

    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def _run_sync(self, func, *args, **kwargs):
        """동기 함수를 비동기로 실행."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, lambda: func(*args, **kwargs)
        )

    async def login(self, rail_type: str, user_id: str, user_pw: str, verbose: bool = False):
        """로그인하여 클라이언트 반환."""
        if rail_type == "SRT":
            return await self._run_sync(SRT, user_id, user_pw, True, verbose)
        else:
            return await self._run_sync(Korail, user_id, user_pw, True, verbose)

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

    async def polling_loop(
        self,
        session: BookingSession,
        on_progress: Any,  # Callable[[int, str], Awaitable]
        on_success: Any,   # Callable[[Any], Awaitable]
        on_error: Any,     # Callable[[str], Awaitable]
        bot: SRTGoBot,
    ) -> None:
        """예매 폴링 루프.

        기존 srtgo.py의 reserve() 루프를 비동기로 재현.
        """
        is_srt = session.rail_type == "SRT"
        session.status = SessionStatus.SEARCHING
        await bot.session_repo.set_status(session.session_id, "searching")

        start_time = time.time()

        while session.status == SessionStatus.SEARCHING:
            try:
                session.attempt_count += 1
                await bot.session_repo.increment_attempt(session.session_id)

                # 진행 상태 업데이트 (10회마다)
                if session.attempt_count % 10 == 0:
                    elapsed = time.time() - start_time
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
                        if _is_seat_available(train, session.seat_type, is_srt):
                            # 예약 시도
                            reservation = await self.reserve(session, train)
                            session.status = SessionStatus.RESERVED

                            # 예약번호 저장
                            if is_srt:
                                session.reservation_number = reservation.reservation_number
                            else:
                                session.reservation_number = reservation.rsv_id

                            await bot.session_repo.set_status(session.session_id, "reserved")
                            await bot.session_repo.update_session(
                                session.session_id,
                                reservation_number=session.reservation_number,
                            )

                            await on_success(reservation)
                            return

                # 감마분포 기반 대기
                await asyncio.sleep(
                    gammavariate(POLL_SHAPE, POLL_SCALE) + POLL_MIN
                )

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
                                    session.rail_type, creds[0], creds[1]
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

                await asyncio.sleep(
                    gammavariate(POLL_SHAPE, POLL_SCALE) + POLL_MIN
                )

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
                            session.rail_type, creds[0], creds[1]
                        )
                except Exception:
                    session.status = SessionStatus.ERROR
                    await on_error(f"예기치 않은 오류: {ex}")
                    return

                await asyncio.sleep(
                    gammavariate(POLL_SHAPE, POLL_SCALE) + POLL_MIN
                )
