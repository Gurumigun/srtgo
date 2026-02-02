"""대화형 질문-응답 흐름 (상태 머신).

전용 예약 채널에서 단계별 질문을 진행하고,
사용자 응답을 받아 BookingSession을 구성한다.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, auto
from typing import Any, TYPE_CHECKING

import discord

from .booking_engine import BookingEngine
from .booking_session import BookingSession, PassengerInfo, SessionStatus
from ..ui.embeds import (
    train_list_embed,
    booking_summary_embed,
    searching_embed,
    success_embed,
    error_embed,
)
from ..ui.formatters import format_train_for_select, format_reservation_detail, format_trains_summary
from ..ui.views import (
    StationSelectView,
    DateSelectView,
    TimeSelectView,
    TrainSelectView,
    SeatTypeView,
    PassengerCountView,
    ConfirmView,
    StartCancelView,
    FavoriteRouteSelectView,
)

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)

# 역 목록 (srtgo.py에서 가져옴)
STATIONS = {
    "SRT": [
        "수서", "동탄", "평택지제", "경주", "곡성", "공주", "광주송정", "구례구", "김천(구미)",
        "나주", "남원", "대전", "동대구", "마산", "목포", "밀양", "부산", "서대구",
        "순천", "여수EXPO", "여천", "오송", "울산(통도사)", "익산", "전주",
        "정읍", "진영", "진주", "창원", "창원중앙", "천안아산", "포항",
    ],
    "KTX": [
        "서울", "용산", "영등포", "광명", "수원", "천안아산", "오송", "대전", "서대전",
        "김천구미", "동대구", "경주", "포항", "밀양", "구포", "부산", "울산(통도사)",
        "마산", "창원중앙", "경산", "논산", "익산", "정읍", "광주송정", "목포",
        "전주", "순천", "여수EXPO", "청량리", "강릉", "행신", "정동진",
    ],
}


class ConvStep(Enum):
    """대화 단계."""
    FAVORITE = auto()
    DEPARTURE = auto()
    ARRIVAL = auto()
    DATE = auto()
    TIME = auto()
    PASSENGERS = auto()
    SEARCH = auto()
    TRAIN_SELECT = auto()
    SEAT_TYPE = auto()
    AUTO_PAY = auto()
    CONFIRM = auto()
    RUNNING = auto()
    DONE = auto()


class ConversationManager:
    """전용 채널에서의 대화형 예약 흐름 관리.

    각 단계마다 View(Select/Button)를 표시하고, 응답을 받아 진행한다.
    5분 무응답 시 자동 타임아웃.
    "종료" 입력 시 취소.
    """

    def __init__(
        self,
        bot: SRTGoBot,
        session: BookingSession,
        channel: discord.TextChannel,
    ) -> None:
        self.bot = bot
        self.session = session
        self.channel = channel
        self.step = ConvStep.FAVORITE
        self.engine = BookingEngine(bot.executor)
        self._polling_task: asyncio.Task | None = None
        self._timeout_task: asyncio.Task | None = None
        self._message_event = asyncio.Event()
        self._latest_message: discord.Message | None = None

    async def start(self) -> None:
        """대화 시작."""
        await self.channel.send(
            f"**{self.session.rail_type}** 예매를 시작합니다.\n"
            f"'종료'를 입력하면 언제든 취소할 수 있습니다.\n"
            f"5분 동안 응답이 없으면 자동으로 취소됩니다."
        )
        self._reset_timeout()
        await self._run_step()

    async def handle_message(self, message: discord.Message) -> None:
        """사용자 메시지 처리."""
        content = message.content.strip()

        # "종료" 명령어
        if content == "종료":
            await self._cancel("사용자가 취소하였습니다.")
            return

        # View 기반이 아닌 텍스트 입력 (현재 단계에 따라 처리)
        self._latest_message = message
        self._message_event.set()
        self._reset_timeout()

    async def _run_step(self) -> None:
        """현재 단계 실행."""
        try:
            if self.step == ConvStep.FAVORITE:
                await self._step_favorite()
            elif self.step == ConvStep.DEPARTURE:
                await self._step_station("출발역을 선택하세요:", is_departure=True)
            elif self.step == ConvStep.ARRIVAL:
                await self._step_station("도착역을 선택하세요:", is_departure=False)
            elif self.step == ConvStep.DATE:
                await self._step_date()
            elif self.step == ConvStep.TIME:
                await self._step_time()
            elif self.step == ConvStep.PASSENGERS:
                await self._step_passengers()
            elif self.step == ConvStep.SEARCH:
                await self._step_search()
            elif self.step == ConvStep.TRAIN_SELECT:
                await self._step_train_select()
            elif self.step == ConvStep.SEAT_TYPE:
                await self._step_seat_type()
            elif self.step == ConvStep.AUTO_PAY:
                await self._step_auto_pay()
            elif self.step == ConvStep.CONFIRM:
                await self._step_confirm()
            elif self.step == ConvStep.RUNNING:
                await self._step_running()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("대화 단계 오류")
            await self.channel.send(embed=error_embed("예기치 않은 오류가 발생했습니다."))
            await self._cleanup()

    # ──────────── 단계별 구현 ────────────

    async def _step_favorite(self) -> None:
        """즐겨찾기 노선 선택 단계."""
        # 즐겨찾기 조회
        user_row = await self.bot.user_repo.get_by_discord_id(self.session.discord_id)
        if user_row is None:
            self.step = ConvStep.DEPARTURE
            await self._run_step()
            return

        routes = await self.bot.fav_repo.get_all(user_row["id"])
        if not routes:
            # 즐겨찾기가 없으면 바로 DEPARTURE로
            self.step = ConvStep.DEPARTURE
            await self._run_step()
            return

        view = FavoriteRouteSelectView(routes, timeout=self.bot.config.conversation_timeout)
        await self.channel.send("노선을 선택하세요:", view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        if view.selected_value == "manual":
            # 직접 선택 → 기존 DEPARTURE 흐름
            self.step = ConvStep.DEPARTURE
        else:
            # 즐겨찾기에서 선택 → 출발/도착 설정 후 DATE로
            route_id = int(view.selected_value)
            for r in routes:
                if r["id"] == route_id:
                    self.session.departure = r["departure"]
                    self.session.arrival = r["arrival"]
                    break
            self.step = ConvStep.DATE

        await self._run_step()

    async def _step_station(self, prompt: str, is_departure: bool) -> None:
        stations = STATIONS[self.session.rail_type]
        view = StationSelectView(stations, prompt, timeout=self.bot.config.conversation_timeout)
        await self.channel.send(prompt, view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        if is_departure:
            self.session.departure = view.selected_value
            self.step = ConvStep.ARRIVAL
        else:
            if view.selected_value == self.session.departure:
                await self.channel.send("출발역과 도착역이 같습니다. 다시 선택해주세요.")
                await self._run_step()
                return
            self.session.arrival = view.selected_value
            self.step = ConvStep.DATE

        await self._run_step()

    async def _step_date(self) -> None:
        view = DateSelectView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("날짜를 선택하세요:", view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        self.session.date = view.selected_value
        self.step = ConvStep.TIME
        await self._run_step()

    async def _step_time(self) -> None:
        view = TimeSelectView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("출발 시간을 선택하세요 (복수 선택 가능):", view=view)
        await view.wait()

        if view.selected_values is None:
            await self._timeout()
            return

        # 복수 시간을 콤마 구분자로 저장
        self.session.time = ",".join(view.selected_values)
        self.step = ConvStep.PASSENGERS
        await self._run_step()

    async def _step_passengers(self) -> None:
        view = PassengerCountView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("승객 수를 선택하세요:", view=view)
        await view.wait()

        if not view.confirmed:
            await self._timeout()
            return

        self.session.passengers = PassengerInfo(
            adults=view.adults,
            children=view.child_count,
            seniors=view.seniors,
        )
        self.step = ConvStep.SEARCH
        await self._run_step()

    async def _step_search(self) -> None:
        msg = await self.channel.send("열차를 검색 중입니다...")

        try:
            trains = await self.engine.search_trains(self.session)
        except Exception as ex:
            await msg.edit(content=f"검색 실패: {ex}")
            await self._cleanup()
            return

        if not trains:
            await msg.edit(content="검색 결과가 없습니다.")
            await self._cleanup()
            return

        # 열차 목록 Embed
        trains_data = [
            format_train_for_select(t, i, self.session.rail_type)
            for i, t in enumerate(trains)
        ]
        embed = train_list_embed(
            trains_data,
            self.session.rail_type,
            self.session.departure,
            self.session.arrival,
            self.session.date,
        )
        await msg.edit(content=None, embed=embed)

        # 열차 데이터를 세션에 캐시
        self.session.trains_cache = trains
        self._trains_data = trains_data
        self.step = ConvStep.TRAIN_SELECT
        await self._run_step()

    async def _step_train_select(self) -> None:
        trains_data = getattr(self, "_trains_data", [])
        view = TrainSelectView(trains_data, timeout=self.bot.config.conversation_timeout)
        await self.channel.send("예매할 열차를 선택하세요 (복수 선택 가능):", view=view)
        await view.wait()

        if view.selected_values is None:
            await self._timeout()
            return

        self.session.selected_train_indices = view.selected_values
        self.step = ConvStep.SEAT_TYPE
        await self._run_step()

    async def _step_seat_type(self) -> None:
        view = SeatTypeView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("좌석 유형을 선택하세요:", view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        self.session.seat_type = view.selected_value
        self.step = ConvStep.AUTO_PAY
        await self._run_step()

    async def _step_auto_pay(self) -> None:
        # 카드 정보가 등록된 경우에만 자동결제 옵션 표시
        card_info = await self.bot.user_repo.get_card_info(self.session.discord_id)
        if card_info:
            view = ConfirmView(timeout=self.bot.config.conversation_timeout)
            await self.channel.send("예매 성공 시 자동으로 카드 결제하시겠습니까?", view=view)
            await view.wait()

            if view.result is None:
                await self._timeout()
                return

            self.session.auto_pay = view.result
        else:
            self.session.auto_pay = False

        self.step = ConvStep.CONFIRM
        await self._run_step()

    async def _step_confirm(self) -> None:
        # 선택된 열차 요약
        trains_data = getattr(self, "_trains_data", [])
        selected_data = [
            trains_data[i] for i in self.session.selected_train_indices
            if i < len(trains_data)
        ]
        selected_desc = format_trains_summary(selected_data)

        embed = booking_summary_embed(
            rail_type=self.session.rail_type,
            departure=self.session.departure,
            arrival=self.session.arrival,
            date=self.session.date,
            time_str=self.session.time,
            passengers_desc=self.session.passengers.description(),
            seat_type_desc=self.session.seat_type_desc,
            selected_trains_desc=selected_desc,
            auto_pay=self.session.auto_pay,
        )

        view = StartCancelView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send(embed=embed, view=view)
        await view.wait()

        if view.result is None or not view.result:
            await self._cancel("예매가 취소되었습니다.")
            return

        # DB에 세션 정보 저장
        await self.bot.session_repo.update_session(
            self.session.session_id,
            departure=self.session.departure,
            arrival=self.session.arrival,
            date=self.session.date,
            time=self.session.time,
            passengers_json=self.session.passengers.to_dict(),
            seat_type=self.session.seat_type,
            selected_trains_json=self.session.selected_train_indices,
            auto_pay=1 if self.session.auto_pay else 0,
        )

        self.step = ConvStep.RUNNING
        await self._run_step()

    async def _step_running(self) -> None:
        """예매 폴링 루프 시작."""
        self._cancel_timeout()

        status_msg = await self.channel.send(
            embed=searching_embed(self.session.rail_type, 0, "00:00:00")
        )
        self.session.status_message = status_msg

        async def on_progress(attempt: int, elapsed: str) -> None:
            try:
                await status_msg.edit(
                    embed=searching_embed(self.session.rail_type, attempt, elapsed)
                )
            except discord.HTTPException:
                pass

        async def on_success(reservation) -> None:
            detail = format_reservation_detail(reservation, self.session.rail_type)
            embed = success_embed(
                self.session.rail_type,
                self.session.reservation_number,
                detail,
            )
            await self.channel.send(embed=embed)

            # 자동 결제
            if self.session.auto_pay:
                card_info = await self.bot.user_repo.get_card_info(self.session.discord_id)
                if card_info and not getattr(reservation, "is_waiting", False):
                    try:
                        paid = await self.engine.pay_with_card(
                            self.session, reservation, card_info
                        )
                        if paid:
                            await self.channel.send("카드 결제가 완료되었습니다!")
                            self.session.status = SessionStatus.PAID
                            await self.bot.session_repo.set_status(
                                self.session.session_id, "paid"
                            )
                    except Exception as ex:
                        await self.channel.send(f"결제 실패: {ex}")

            await self._cleanup(delay=30)

        async def on_error(msg: str) -> None:
            await self.channel.send(embed=error_embed(msg))
            await self.bot.session_repo.set_status(self.session.session_id, "error")
            await self._cleanup(delay=30)

        self._polling_task = asyncio.create_task(
            self.engine.polling_loop(
                self.session, on_progress, on_success, on_error, self.bot
            )
        )

    # ──────────── 유틸리티 ────────────

    def _reset_timeout(self) -> None:
        """타임아웃 타이머 리셋."""
        self._cancel_timeout()
        self._timeout_task = asyncio.create_task(self._timeout_countdown())

    def _cancel_timeout(self) -> None:
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()

    async def _timeout_countdown(self) -> None:
        await asyncio.sleep(self.bot.config.conversation_timeout)
        await self._timeout()

    async def _timeout(self) -> None:
        """타임아웃 처리."""
        await self.channel.send("시간이 초과되어 예매가 취소됩니다.")
        self.session.status = SessionStatus.TIMEOUT
        await self.bot.session_repo.set_status(self.session.session_id, "timeout")
        await self._cleanup(delay=5)

    async def _cancel(self, message: str) -> None:
        """예매 취소."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
        await self.channel.send(message)
        self.session.status = SessionStatus.CANCELLED
        await self.bot.session_repo.set_status(self.session.session_id, "cancelled")
        await self._cleanup(delay=5)

    async def _cleanup(self, delay: int = 10) -> None:
        """리소스 정리 + 채널 삭제."""
        self._cancel_timeout()
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()

        # 슬롯 해제
        await self.bot.slot_manager.release(self.session.session_id)

        # 대화 추적 해제
        self.bot.conversations.pop(self.channel.id, None)

        # 채널 삭제
        if delay > 0:
            await self.channel.send(f"이 채널은 {delay}초 후 삭제됩니다.")
            await asyncio.sleep(delay)

        try:
            await self.channel.delete(reason="예매 세션 종료")
        except discord.Forbidden:
            await self.channel.send("채널 삭제 권한이 없습니다. 관리자에게 문의하세요.")
        except discord.HTTPException:
            pass
