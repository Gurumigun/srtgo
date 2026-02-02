"""즐겨찾기 노선 관리 슬래시 커맨드."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..core.conversation import STATIONS
from ..ui.embeds import error_embed, favorite_routes_embed
from ..ui.views import (
    FavoriteDeleteView,
    StationSelectView,
)

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)

# 즐겨찾기 등록용 역 목록 (SRT + KTX 합집합, 중복 제거, 가나다순)
ALL_STATIONS = sorted(set(STATIONS["SRT"]) | set(STATIONS["KTX"]))


class FavoriteCog(commands.Cog):
    """즐겨찾기 노선 관련 슬래시 커맨드."""

    def __init__(self, bot: SRTGoBot) -> None:
        self.bot = bot

    # ──────────────────────────────────
    # /즐겨찾기추가
    # ──────────────────────────────────

    @app_commands.command(name="즐겨찾기추가", description="자주 이용하는 노선을 즐겨찾기에 추가합니다")
    async def add_favorite(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)

        # 프로필 확인
        user_row = await self.bot.user_repo.get_by_discord_id(discord_id)
        if user_row is None:
            await interaction.response.send_message(
                embed=error_embed("프로필이 등록되지 않았습니다. `/프로필설정`으로 먼저 등록해주세요."),
                ephemeral=True,
            )
            return

        # 개수 확인
        count = await self.bot.fav_repo.count(user_row["id"])
        if count >= 6:
            await interaction.response.send_message(
                embed=error_embed("최대 6개까지 등록 가능합니다. 기존 노선을 삭제한 후 다시 시도해주세요."),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # 출발역 선택
        dep_view = StationSelectView(ALL_STATIONS, "출발역을 선택하세요", timeout=60)
        dep_msg = await interaction.followup.send("출발역을 선택하세요:", view=dep_view, ephemeral=True, wait=True)
        await dep_view.wait()

        if dep_view.selected_value is None:
            await dep_msg.edit(content="시간이 초과되었습니다.", view=None)
            return

        departure = dep_view.selected_value

        # 도착역 선택
        arr_view = StationSelectView(ALL_STATIONS, "도착역을 선택하세요", timeout=60)
        arr_msg = await interaction.followup.send("도착역을 선택하세요:", view=arr_view, ephemeral=True, wait=True)
        await arr_view.wait()

        if arr_view.selected_value is None:
            await arr_msg.edit(content="시간이 초과되었습니다.", view=None)
            return

        arrival = arr_view.selected_value

        if departure == arrival:
            await interaction.followup.send("출발역과 도착역이 같습니다.", ephemeral=True)
            return

        # DB 저장
        try:
            await self.bot.fav_repo.add(user_row["id"], departure, arrival)
        except ValueError as e:
            await interaction.followup.send(embed=error_embed(str(e)), ephemeral=True)
            return

        await interaction.followup.send(
            f"즐겨찾기에 **{departure} → {arrival}** 노선이 추가되었습니다.",
            ephemeral=True,
        )

    # ──────────────────────────────────
    # /즐겨찾기목록
    # ──────────────────────────────────

    @app_commands.command(name="즐겨찾기목록", description="등록된 즐겨찾기 노선을 확인합니다")
    async def list_favorites(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)

        user_row = await self.bot.user_repo.get_by_discord_id(discord_id)
        if user_row is None:
            await interaction.response.send_message(
                embed=error_embed("프로필이 등록되지 않았습니다. `/프로필설정`으로 먼저 등록해주세요."),
                ephemeral=True,
            )
            return

        routes = await self.bot.fav_repo.get_all(user_row["id"])
        embed = favorite_routes_embed(routes, interaction.user.display_name)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ──────────────────────────────────
    # /즐겨찾기삭제
    # ──────────────────────────────────

    @app_commands.command(name="즐겨찾기삭제", description="즐겨찾기 노선을 삭제합니다")
    async def delete_favorite(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)

        user_row = await self.bot.user_repo.get_by_discord_id(discord_id)
        if user_row is None:
            await interaction.response.send_message(
                embed=error_embed("프로필이 등록되지 않았습니다. `/프로필설정`으로 먼저 등록해주세요."),
                ephemeral=True,
            )
            return

        routes = await self.bot.fav_repo.get_all(user_row["id"])
        if not routes:
            await interaction.response.send_message("등록된 즐겨찾기가 없습니다.", ephemeral=True)
            return

        view = FavoriteDeleteView(routes, timeout=60)
        await interaction.response.send_message("삭제할 노선을 선택하세요:", view=view, ephemeral=True)
        await view.wait()

        if view.selected_value is None:
            return

        route_id = int(view.selected_value)
        # 삭제할 노선 이름 찾기
        route_name = ""
        for r in routes:
            if r["id"] == route_id:
                route_name = f"{r['departure']} → {r['arrival']}"
                break

        deleted = await self.bot.fav_repo.remove(route_id, user_row["id"])
        if deleted:
            await interaction.followup.send(
                f"즐겨찾기에서 **{route_name}** 노선이 삭제되었습니다.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send("삭제에 실패했습니다.", ephemeral=True)


async def setup(bot: SRTGoBot) -> None:
    await bot.add_cog(FavoriteCog(bot))
