"""Discord UI 구성요소 (Select, Button, Modal, View)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine

import discord
from discord import ui


# ──────────────────────────────────────
# 역 선택 Select Menu
# ──────────────────────────────────────

class StationSelect(ui.Select):
    """역 선택 드롭다운."""

    def __init__(self, stations: list[str], placeholder: str = "역을 선택하세요") -> None:
        options = [discord.SelectOption(label=s, value=s) for s in stations]
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_value = self.values[0]  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class StationSelectView(ui.View):
    """역 선택 View.

    Discord Select Menu는 옵션 25개 제한이 있으므로,
    역이 25개를 초과하면 자동으로 2개의 Select로 분할한다.
    """

    def __init__(self, stations: list[str], placeholder: str, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None
        if len(stations) <= 25:
            self.add_item(StationSelect(stations, placeholder))
        else:
            mid = (len(stations) + 1) // 2
            self.add_item(StationSelect(stations[:mid], f"{placeholder} (ㄱ~ㅂ)"))
            self.add_item(StationSelect(stations[mid:], f"{placeholder} (ㅅ~ㅎ)"))

    async def on_timeout(self) -> None:
        self.selected_value = None


# ──────────────────────────────────────
# 날짜 선택
# ──────────────────────────────────────

class DateSelect(ui.Select):
    """날짜 선택 드롭다운."""

    def __init__(self) -> None:
        now = datetime.now()
        options = []
        for i in range(25):  # Discord 최대 25개 옵션
            d = now + timedelta(days=i)
            label = d.strftime("%Y/%m/%d %a")
            value = d.strftime("%Y%m%d")
            options.append(discord.SelectOption(label=label, value=value))
        super().__init__(placeholder="날짜를 선택하세요", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_value = self.values[0]  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class DateSelectView(ui.View):
    """날짜 선택 View."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None
        self.add_item(DateSelect())


# ──────────────────────────────────────
# 시간 선택
# ──────────────────────────────────────

class TimeSelect(ui.Select):
    """시간 선택 드롭다운 (복수 선택 가능)."""

    def __init__(self) -> None:
        options = [
            discord.SelectOption(label=f"{h:02d}시", value=f"{h:02d}0000")
            for h in range(24)
        ]
        super().__init__(
            placeholder="시간을 선택하세요 (복수 선택 가능)",
            options=options,
            min_values=1,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_values = sorted(self.values)  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class TimeSelectView(ui.View):
    """시간 선택 View (복수 선택)."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_values: list[str] | None = None
        self.add_item(TimeSelect())


# ──────────────────────────────────────
# 열차 선택 (복수)
# ──────────────────────────────────────

class TrainSelect(ui.Select):
    """열차 복수 선택."""

    def __init__(self, trains: list[dict[str, str]]) -> None:
        options = []
        for i, t in enumerate(trains[:25]):
            dep = t["dep_time"]
            arr = t["arr_time"]
            label = f"{t.get('train_name', '')} {t.get('train_number', '')} | {dep[:2]}:{dep[2:4]}→{arr[:2]}:{arr[2:4]}"
            desc = t.get("seat_info", "")
            options.append(discord.SelectOption(label=label, value=str(i), description=desc[:100]))
        super().__init__(
            placeholder="열차를 선택하세요 (복수 가능)",
            options=options,
            min_values=1,
            max_values=min(len(trains), 25),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_values = [int(v) for v in self.values]  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class TrainSelectView(ui.View):
    """열차 선택 View."""

    def __init__(self, trains: list[dict[str, str]], timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_values: list[int] | None = None
        self.add_item(TrainSelect(trains))


# ──────────────────────────────────────
# 좌석 유형 버튼
# ──────────────────────────────────────

class SeatTypeView(ui.View):
    """좌석 유형 선택 버튼."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None

    @ui.button(label="일반실 우선", style=discord.ButtonStyle.primary, row=0)
    async def general_first(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "GENERAL_FIRST"
        self.stop()
        await interaction.response.defer()

    @ui.button(label="일반실만", style=discord.ButtonStyle.secondary, row=0)
    async def general_only(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "GENERAL_ONLY"
        self.stop()
        await interaction.response.defer()

    @ui.button(label="특실 우선", style=discord.ButtonStyle.primary, row=1)
    async def special_first(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "SPECIAL_FIRST"
        self.stop()
        await interaction.response.defer()

    @ui.button(label="특실만", style=discord.ButtonStyle.secondary, row=1)
    async def special_only(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "SPECIAL_ONLY"
        self.stop()
        await interaction.response.defer()


# ──────────────────────────────────────
# 승객 수 선택 버튼
# ──────────────────────────────────────

class PassengerCountView(ui.View):
    """승객 수 조절 View."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.adults: int = 1
        self.child_count: int = 0
        self.seniors: int = 0
        self.confirmed: bool = False

    def _make_content(self) -> str:
        parts = []
        if self.adults:
            parts.append(f"어른 {self.adults}명")
        if self.child_count:
            parts.append(f"어린이 {self.child_count}명")
        if self.seniors:
            parts.append(f"경로 {self.seniors}명")
        total = self.adults + self.child_count + self.seniors
        return f"승객: {', '.join(parts)} (총 {total}명)" if parts else "승객을 선택해주세요"

    @ui.button(label="어른 +", style=discord.ButtonStyle.primary, row=0)
    async def adult_plus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.adults + self.child_count + self.seniors < 9:
            self.adults += 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="어른 -", style=discord.ButtonStyle.secondary, row=0)
    async def adult_minus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.adults > 0:
            self.adults -= 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="어린이 +", style=discord.ButtonStyle.primary, row=1)
    async def child_plus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.adults + self.child_count + self.seniors < 9:
            self.child_count += 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="어린이 -", style=discord.ButtonStyle.secondary, row=1)
    async def child_minus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.child_count > 0:
            self.child_count -= 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="경로 +", style=discord.ButtonStyle.primary, row=2)
    async def senior_plus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.adults + self.child_count + self.seniors < 9:
            self.seniors += 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="경로 -", style=discord.ButtonStyle.secondary, row=2)
    async def senior_minus(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.seniors > 0:
            self.seniors -= 1
        await interaction.response.edit_message(content=self._make_content(), view=self)

    @ui.button(label="확인", style=discord.ButtonStyle.success, row=3)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.adults + self.child_count + self.seniors == 0:
            await interaction.response.send_message("승객 수는 0이 될 수 없습니다.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.defer()


# ──────────────────────────────────────
# 자동결제 / 확인 버튼
# ──────────────────────────────────────

class ConfirmView(ui.View):
    """예/아니오 확인 버튼."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.result: bool | None = None

    @ui.button(label="예", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.result = True
        self.stop()
        await interaction.response.defer()

    @ui.button(label="아니오", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.result = False
        self.stop()
        await interaction.response.defer()


class StartCancelView(ui.View):
    """시작/취소 버튼."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.result: bool | None = None

    @ui.button(label="예매 시작", style=discord.ButtonStyle.success, emoji="\U0001f680")
    async def start(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.result = True
        self.stop()
        await interaction.response.defer()

    @ui.button(label="취소", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.result = False
        self.stop()
        await interaction.response.defer()


# ──────────────────────────────────────
# 열차 종류 선택
# ──────────────────────────────────────

class RailTypeView(ui.View):
    """SRT/KTX 선택 버튼."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None

    @ui.button(label="SRT", style=discord.ButtonStyle.danger)
    async def srt(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "SRT"
        self.stop()
        await interaction.response.defer()

    @ui.button(label="KTX", style=discord.ButtonStyle.primary)
    async def ktx(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "KTX"
        self.stop()
        await interaction.response.defer()


# ──────────────────────────────────────
# 편도/왕복 선택
# ──────────────────────────────────────

class TripTypeView(ui.View):
    """편도/왕복 선택 버튼."""

    def __init__(self, timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None

    @ui.button(label="편도", style=discord.ButtonStyle.primary)
    async def oneway(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "oneway"
        self.stop()
        await interaction.response.defer()

    @ui.button(label="왕복", style=discord.ButtonStyle.success)
    async def roundtrip(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.selected_value = "roundtrip"
        self.stop()
        await interaction.response.defer()


# ──────────────────────────────────────
# 프로필 설정 Modal
# ──────────────────────────────────────

class ProfileModal(ui.Modal, title="프로필 설정"):
    """SRT/KTX 자격 증명 입력 모달."""

    def __init__(self, rail_type: str) -> None:
        super().__init__()
        self.rail_type = rail_type
        self.user_id_value: str = ""
        self.user_pw_value: str = ""

    rail_id = ui.TextInput(
        label="아이디 (멤버십 번호, 이메일, 전화번호)",
        placeholder="010-1234-5678",
        required=True,
    )
    rail_pw = ui.TextInput(
        label="비밀번호",
        style=discord.TextStyle.short,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.user_id_value = self.rail_id.value
        self.user_pw_value = self.rail_pw.value
        await interaction.response.defer(ephemeral=True)


# ──────────────────────────────────────
# 즐겨찾기 노선 선택
# ──────────────────────────────────────

class FavoriteRouteSelect(ui.Select):
    """즐겨찾기 노선 선택 드롭다운."""

    def __init__(self, routes: list[dict], placeholder: str = "노선을 선택하세요") -> None:
        options = []
        for r in routes:
            options.append(discord.SelectOption(
                label=f"{r['departure']} → {r['arrival']}",
                value=str(r["id"]),
            ))
        # "직접 선택" 옵션 추가
        options.append(discord.SelectOption(
            label="직접 선택",
            value="manual",
            description="출발역/도착역을 직접 선택합니다",
            emoji="\u270F\uFE0F",
        ))
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_value = self.values[0]  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class FavoriteRouteSelectView(ui.View):
    """즐겨찾기 노선 선택 View."""

    def __init__(self, routes: list[dict], timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None
        self.add_item(FavoriteRouteSelect(routes))

    async def on_timeout(self) -> None:
        self.selected_value = None


class FavoriteDeleteSelect(ui.Select):
    """즐겨찾기 삭제용 선택 드롭다운."""

    def __init__(self, routes: list[dict]) -> None:
        options = [
            discord.SelectOption(
                label=f"{r['departure']} → {r['arrival']}",
                value=str(r["id"]),
            )
            for r in routes
        ]
        super().__init__(placeholder="삭제할 노선을 선택하세요", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.selected_value = self.values[0]  # type: ignore[attr-defined]
        self.view.stop()  # type: ignore[attr-defined]
        await interaction.response.defer()


class FavoriteDeleteView(ui.View):
    """즐겨찾기 삭제 View."""

    def __init__(self, routes: list[dict], timeout: float = 300) -> None:
        super().__init__(timeout=timeout)
        self.selected_value: str | None = None
        self.add_item(FavoriteDeleteSelect(routes))

    async def on_timeout(self) -> None:
        self.selected_value = None


class CardModal(ui.Modal, title="카드 설정"):
    """신용카드 정보 입력 모달."""

    def __init__(self) -> None:
        super().__init__()
        self.card_values: dict[str, str] = {}

    card_number = ui.TextInput(
        label="카드번호 (띄어쓰기/하이픈 가능)",
        placeholder="1234 5678 9012 3456",
        required=True,
    )
    card_password = ui.TextInput(
        label="카드 비밀번호 앞 2자리",
        placeholder="12",
        max_length=2,
        required=True,
    )
    card_birthday = ui.TextInput(
        label="생년월일(YYMMDD) / 사업자등록번호",
        placeholder="981204",
        required=True,
    )
    card_expire = ui.TextInput(
        label="카드 유효기간 (YYMM)",
        placeholder="2812",
        max_length=4,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # 카드번호에서 공백, 하이픈 제거
        card_number_clean = self.card_number.value.replace(" ", "").replace("-", "")

        # 숫자만 입력되었는지 검증
        if not card_number_clean.isdigit():
            await interaction.response.send_message(
                "❌ 카드번호는 숫자만 입력해주세요.", ephemeral=True
            )
            return

        if len(card_number_clean) < 15 or len(card_number_clean) > 16:
            await interaction.response.send_message(
                "❌ 카드번호는 15~16자리여야 합니다.", ephemeral=True
            )
            return

        self.card_values = {
            "card_number": card_number_clean,
            "card_password": self.card_password.value,
            "card_birthday": self.card_birthday.value,
            "card_expire": self.card_expire.value,
        }
        await interaction.response.defer(ephemeral=True)
