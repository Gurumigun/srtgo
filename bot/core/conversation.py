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
    waiting_embed,
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
    TripTypeView,
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
    TRIP_TYPE = auto()
    DATE = auto()
    TIME = auto()
    PASSENGERS = auto()
    SEARCH = auto()
    TRAIN_SELECT = auto()
    SEAT_TYPE = auto()
    AUTO_PAY = auto()
    RETURN_DATE = auto()
    RETURN_TIME = auto()
    RETURN_SEARCH = auto()
    RETURN_TRAIN_SELECT = auto()
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

        # 왕복 예매 상태
        self._is_round_trip: bool = False

        # 오는 편 사전 입력 데이터
        self._return_date: str = ""
        self._return_time: str = ""
        self._return_trains_cache: list[Any] = []
        self._return_trains_data: list[dict[str, str]] = []
        self._return_selected_train_indices: list[int] = []

        # 병렬 실행 상태
        self._return_session: BookingSession | None = None
        self._return_polling_task: asyncio.Task | None = None
        self._legs_done: int = 0
        self._legs_total: int = 1  # 편도=1, 왕복=2
        self._cleanup_done: bool = False

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
            elif self.step == ConvStep.TRIP_TYPE:
                await self._step_trip_type()
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
            elif self.step == ConvStep.RETURN_DATE:
                await self._step_return_date()
            elif self.step == ConvStep.RETURN_TIME:
                await self._step_return_time()
            elif self.step == ConvStep.RETURN_SEARCH:
                await self._step_return_search()
            elif self.step == ConvStep.RETURN_TRAIN_SELECT:
                await self._step_return_train_select()
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
            # 즐겨찾기에서 선택 → 출발/도착 설정 후 TRIP_TYPE으로
            route_id = int(view.selected_value)
            for r in routes:
                if r["id"] == route_id:
                    self.session.departure = r["departure"]
                    self.session.arrival = r["arrival"]
                    break
            self.step = ConvStep.TRIP_TYPE

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
            self.step = ConvStep.TRIP_TYPE

        await self._run_step()

    async def _step_trip_type(self) -> None:
        """편도/왕복 선택 단계."""
        view = TripTypeView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("편도/왕복을 선택하세요:", view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        self._is_round_trip = view.selected_value == "roundtrip"
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

        if self._is_round_trip:
            self.step = ConvStep.RETURN_DATE
        else:
            self.step = ConvStep.CONFIRM
        await self._run_step()

    # ──────────── 오는 편 사전 입력 ────────────

    async def _step_return_date(self) -> None:
        """오는 편 날짜 선택."""
        await self.channel.send(
            f"\n**오는 편** 정보를 입력합니다. "
            f"(**{self.session.arrival}** → **{self.session.departure}**)"
        )
        view = DateSelectView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("오는 편 날짜를 선택하세요:", view=view)
        await view.wait()

        if view.selected_value is None:
            await self._timeout()
            return

        self._return_date = view.selected_value
        self.step = ConvStep.RETURN_TIME
        await self._run_step()

    async def _step_return_time(self) -> None:
        """오는 편 시간 선택."""
        view = TimeSelectView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("오는 편 출발 시간을 선택하세요 (복수 선택 가능):", view=view)
        await view.wait()

        if view.selected_values is None:
            await self._timeout()
            return

        self._return_time = ",".join(view.selected_values)
        self.step = ConvStep.RETURN_SEARCH
        await self._run_step()

    async def _step_return_search(self) -> None:
        """오는 편 열차 검색 (출발/도착 교환)."""
        msg = await self.channel.send("오는 편 열차를 검색 중입니다...")

        # 임시 세션으로 오는 편 검색 (출발/도착 교환)
        temp_session = BookingSession(
            session_id=self.session.session_id,
            user_db_id=self.session.user_db_id,
            discord_id=self.session.discord_id,
            channel_id=self.session.channel_id,
            rail_type=self.session.rail_type,
            departure=self.session.arrival,      # 교환
            arrival=self.session.departure,      # 교환
            date=self._return_date,
            time=self._return_time,
            passengers=self.session.passengers,
            rail_client=self.session.rail_client,
        )

        try:
            trains = await self.engine.search_trains(temp_session)
        except Exception as ex:
            await msg.edit(content=f"오는 편 검색 실패: {ex}")
            await self._cleanup()
            return

        if not trains:
            await msg.edit(
                content="오는 편 검색 결과가 없습니다. 다른 날짜/시간을 선택해주세요."
            )
            self.step = ConvStep.RETURN_DATE
            await self._run_step()
            return

        trains_data = [
            format_train_for_select(t, i, self.session.rail_type)
            for i, t in enumerate(trains)
        ]
        embed = train_list_embed(
            trains_data,
            self.session.rail_type,
            self.session.arrival,       # 오는 편 출발역
            self.session.departure,     # 오는 편 도착역
            self._return_date,
        )
        await msg.edit(content=None, embed=embed)

        self._return_trains_cache = trains
        self._return_trains_data = trains_data
        self.step = ConvStep.RETURN_TRAIN_SELECT
        await self._run_step()

    async def _step_return_train_select(self) -> None:
        """오는 편 열차 선택."""
        view = TrainSelectView(
            self._return_trains_data, timeout=self.bot.config.conversation_timeout
        )
        await self.channel.send("오는 편 열차를 선택하세요 (복수 선택 가능):", view=view)
        await view.wait()

        if view.selected_values is None:
            await self._timeout()
            return

        self._return_selected_train_indices = view.selected_values
        self.step = ConvStep.CONFIRM
        await self._run_step()

    # ──────────── 확인 / 실행 ────────────

    async def _step_confirm(self) -> None:
        # 가는 편 열차 요약
        trains_data = getattr(self, "_trains_data", [])
        selected_data = [
            trains_data[i] for i in self.session.selected_train_indices
            if i < len(trains_data)
        ]
        selected_desc = format_trains_summary(selected_data)

        title_prefix = "가는 편 " if self._is_round_trip else ""
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
        if self._is_round_trip:
            embed.title = f"예약 확인 ({self.session.rail_type}) - 가는 편"
        await self.channel.send(embed=embed)

        # 왕복일 때 오는 편 요약도 표시
        if self._is_round_trip:
            return_selected_data = [
                self._return_trains_data[i]
                for i in self._return_selected_train_indices
                if i < len(self._return_trains_data)
            ]
            return_selected_desc = format_trains_summary(return_selected_data)

            return_embed = booking_summary_embed(
                rail_type=self.session.rail_type,
                departure=self.session.arrival,
                arrival=self.session.departure,
                date=self._return_date,
                time_str=self._return_time,
                passengers_desc=self.session.passengers.description(),
                seat_type_desc=self.session.seat_type_desc,
                selected_trains_desc=return_selected_desc,
                auto_pay=self.session.auto_pay,
                is_return_leg=True,
            )
            await self.channel.send(embed=return_embed)

        view = StartCancelView(timeout=self.bot.config.conversation_timeout)
        await self.channel.send("위 내용으로 예매를 시작하시겠습니까?", view=view)
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
        """예매 폴링 루프 시작 (라우팅)."""
        self._cancel_timeout()

        if self._is_round_trip:
            await self._run_parallel_booking()
        else:
            await self._run_single_booking()

    async def _run_single_booking(self, leg_label: str = "") -> None:
        """편도 예매 폴링 루프."""
        status_msg = await self.channel.send(
            embed=searching_embed(
                self.session.rail_type, 0, "00:00:00", leg_label=leg_label,
            )
        )
        self.session.status_message = status_msg

        async def on_progress(attempt: int, elapsed: str) -> None:
            try:
                await status_msg.edit(
                    embed=searching_embed(
                        self.session.rail_type, attempt, elapsed,
                        leg_label=leg_label,
                    )
                )
            except discord.HTTPException:
                pass

        async def on_success(reservation) -> None:
            detail = format_reservation_detail(reservation, self.session.rail_type)
            embed = success_embed(
                self.session.rail_type,
                self.session.reservation_number,
                detail,
                leg_label=leg_label,
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
                            label_prefix = f"**{leg_label}** " if leg_label else ""
                            await self.channel.send(f"{label_prefix}카드 결제가 완료되었습니다!")
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

        async def on_waiting(reservation) -> None:
            detail = format_reservation_detail(reservation, self.session.rail_type)
            embed = waiting_embed(
                self.session.rail_type,
                self.session.reservation_number,
                detail,
                leg_label=leg_label,
            )
            await self.channel.send(embed=embed)

        self._polling_task = asyncio.create_task(
            self.engine.polling_loop(
                self.session, on_progress, on_success, on_error, self.bot,
                on_waiting=on_waiting,
            )
        )

    async def _create_return_session(self) -> BookingSession:
        """오는 편 BookingSession 생성 (별도 로그인)."""
        old = self.session

        # 새 DB 세션 생성
        new_session_id = await self.bot.session_repo.create_session(
            user_id=old.user_db_id,
            rail_type=old.rail_type,
            channel_id=str(self.channel.id),
        )

        # 새 슬롯 할당
        await self.bot.slot_manager.acquire(
            new_session_id,
            old.discord_id,
            old.rail_type,
            self.channel,
        )

        # 별도 로그인 (thread safety: 각 세션 별도 클라이언트)
        creds = await self.bot.user_repo.get_credentials(old.discord_id, old.rail_type)
        if not creds:
            raise ValueError("계정 정보를 찾을 수 없습니다")
        return_client = await self.engine.login(old.rail_type, creds[0], creds[1])

        session = BookingSession(
            session_id=new_session_id,
            user_db_id=old.user_db_id,
            discord_id=old.discord_id,
            channel_id=old.channel_id,
            rail_type=old.rail_type,
            departure=old.arrival,       # 교환
            arrival=old.departure,       # 교환
            date=self._return_date,
            time=self._return_time,
            passengers=old.passengers,
            seat_type=old.seat_type,
            selected_train_indices=self._return_selected_train_indices,
            auto_pay=old.auto_pay,
            rail_client=return_client,
            trains_cache=self._return_trains_cache,
        )

        # DB에 오는 편 세션 정보 저장
        await self.bot.session_repo.update_session(
            session.session_id,
            departure=session.departure,
            arrival=session.arrival,
            date=session.date,
            time=session.time,
            passengers_json=session.passengers.to_dict(),
            seat_type=session.seat_type,
            selected_trains_json=session.selected_train_indices,
            auto_pay=1 if session.auto_pay else 0,
        )

        return session

    async def _run_parallel_booking(self) -> None:
        """왕복 예매: 가는 편/오는 편 동시 시작."""
        self._legs_total = 2
        self._legs_done = 0

        # 오는 편 세션 생성 (별도 로그인)
        try:
            self._return_session = await self._create_return_session()
        except Exception as ex:
            log.warning("오는 편 세션 생성 실패: %s", ex)
            await self.channel.send(
                embed=error_embed(f"오는 편 세션 생성 실패: {ex}\n가는 편만 진행합니다.")
            )
            self._legs_total = 1
            await self._run_single_booking(leg_label="가는 편")
            return

        await self.channel.send(
            f"**가는 편**과 **오는 편** 예매를 동시에 시작합니다!\n"
            f"가는 편: **{self.session.departure}** → **{self.session.arrival}**\n"
            f"오는 편: **{self._return_session.departure}** → **{self._return_session.arrival}**"
        )

        # 콜백 팩토리
        def _make_callbacks(session: BookingSession, label: str):
            status_msg_holder: list[discord.Message] = []

            async def on_progress(attempt: int, elapsed: str) -> None:
                if not status_msg_holder:
                    return
                try:
                    await status_msg_holder[0].edit(
                        embed=searching_embed(
                            session.rail_type, attempt, elapsed, leg_label=label,
                        )
                    )
                except discord.HTTPException:
                    pass

            async def on_success(reservation) -> None:
                detail = format_reservation_detail(reservation, session.rail_type)
                embed = success_embed(
                    session.rail_type,
                    session.reservation_number,
                    detail,
                    leg_label=label,
                )
                await self.channel.send(embed=embed)

                # 자동 결제
                if session.auto_pay:
                    card_info = await self.bot.user_repo.get_card_info(session.discord_id)
                    if card_info and not getattr(reservation, "is_waiting", False):
                        try:
                            paid = await self.engine.pay_with_card(
                                session, reservation, card_info
                            )
                            if paid:
                                await self.channel.send(
                                    f"**{label}** 카드 결제가 완료되었습니다!"
                                )
                                session.status = SessionStatus.PAID
                                await self.bot.session_repo.set_status(
                                    session.session_id, "paid"
                                )
                        except Exception as ex:
                            await self.channel.send(f"**{label}** 결제 실패: {ex}")

                self._legs_done += 1
                if self._legs_done >= self._legs_total:
                    await self._cleanup(delay=30)

            async def on_error(msg: str) -> None:
                await self.channel.send(embed=error_embed(f"**{label}** {msg}"))
                await self.bot.session_repo.set_status(session.session_id, "error")
                self._legs_done += 1
                if self._legs_done >= self._legs_total:
                    await self._cleanup(delay=30)

            async def on_waiting(reservation) -> None:
                detail = format_reservation_detail(reservation, session.rail_type)
                embed = waiting_embed(
                    session.rail_type,
                    session.reservation_number,
                    detail,
                    leg_label=label,
                )
                await self.channel.send(embed=embed)

            return status_msg_holder, on_progress, on_success, on_error, on_waiting

        # 가는 편 콜백
        out_holder, out_progress, out_success, out_error, out_waiting = _make_callbacks(
            self.session, "가는 편"
        )
        # 오는 편 콜백
        ret_holder, ret_progress, ret_success, ret_error, ret_waiting = _make_callbacks(
            self._return_session, "오는 편"
        )

        # 상태 메시지 생성
        out_msg = await self.channel.send(
            embed=searching_embed(self.session.rail_type, 0, "00:00:00", leg_label="가는 편")
        )
        self.session.status_message = out_msg
        out_holder.append(out_msg)

        ret_msg = await self.channel.send(
            embed=searching_embed(
                self._return_session.rail_type, 0, "00:00:00", leg_label="오는 편"
            )
        )
        self._return_session.status_message = ret_msg
        ret_holder.append(ret_msg)

        # 두 폴링 태스크 동시 시작
        self._polling_task = asyncio.create_task(
            self.engine.polling_loop(
                self.session, out_progress, out_success, out_error, self.bot,
                on_waiting=out_waiting,
            )
        )
        self._return_polling_task = asyncio.create_task(
            self.engine.polling_loop(
                self._return_session, ret_progress, ret_success, ret_error, self.bot,
                on_waiting=ret_waiting,
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
        if self._return_polling_task and not self._return_polling_task.done():
            self._return_polling_task.cancel()

        await self.channel.send(message)
        self.session.status = SessionStatus.CANCELLED
        await self.bot.session_repo.set_status(self.session.session_id, "cancelled")

        if self._return_session:
            self._return_session.status = SessionStatus.CANCELLED
            await self.bot.session_repo.set_status(
                self._return_session.session_id, "cancelled"
            )

        await self._cleanup(delay=5)

    async def _cleanup(self, delay: int = 10) -> None:
        """리소스 정리 + 채널 삭제."""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        self._cancel_timeout()
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
        if self._return_polling_task and not self._return_polling_task.done():
            self._return_polling_task.cancel()

        # 슬롯 해제
        await self.bot.slot_manager.release(self.session.session_id)
        if self._return_session:
            await self.bot.slot_manager.release(self._return_session.session_id)

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
