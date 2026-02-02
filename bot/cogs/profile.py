"""프로필 등록/관리 슬래시 커맨드."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.embeds import profile_embed, error_embed
from ..ui.views import ProfileModal, CardModal

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)


class ProfileCog(commands.Cog):
    """프로필 관련 슬래시 커맨드."""

    def __init__(self, bot: SRTGoBot) -> None:
        self.bot = bot

    # ──────────────────────────────────
    # /프로필설정
    # ──────────────────────────────────

    @app_commands.command(name="프로필설정", description="SRT/KTX 로그인 정보를 등록합니다")
    @app_commands.describe(열차종류="등록할 열차 종류")
    @app_commands.choices(열차종류=[
        app_commands.Choice(name="SRT", value="SRT"),
        app_commands.Choice(name="KTX", value="KTX"),
    ])
    async def set_profile(
        self, interaction: discord.Interaction, 열차종류: app_commands.Choice[str]
    ) -> None:
        rail_type = 열차종류.value
        modal = ProfileModal(rail_type)
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()

        if timed_out or not modal.user_id_value or not modal.user_pw_value:
            return

        discord_id = str(interaction.user.id)
        discord_name = interaction.user.display_name
        prefix = "srt" if rail_type == "SRT" else "ktx"

        await self.bot.user_repo.upsert_user(
            discord_id=discord_id,
            discord_name=discord_name,
            **{f"{prefix}_id": modal.user_id_value, f"{prefix}_pw": modal.user_pw_value},
        )

        await interaction.followup.send(
            f"**{rail_type}** 프로필이 저장되었습니다.",
            ephemeral=True,
        )

    # ──────────────────────────────────
    # /카드설정
    # ──────────────────────────────────

    @app_commands.command(name="카드설정", description="결제용 카드 정보를 등록합니다")
    async def set_card(self, interaction: discord.Interaction) -> None:
        modal = CardModal()
        await interaction.response.send_modal(modal)
        timed_out = await modal.wait()

        if timed_out or not modal.card_values:
            return

        discord_id = str(interaction.user.id)
        discord_name = interaction.user.display_name

        await self.bot.user_repo.upsert_user(
            discord_id=discord_id,
            discord_name=discord_name,
            **modal.card_values,
        )

        await interaction.followup.send("카드 정보가 저장되었습니다.", ephemeral=True)

    # ──────────────────────────────────
    # /프로필확인
    # ──────────────────────────────────

    @app_commands.command(name="프로필확인", description="등록된 프로필 정보를 확인합니다")
    async def check_profile(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)
        row = await self.bot.user_repo.get_by_discord_id(discord_id)

        if row is None:
            await interaction.response.send_message(
                embed=error_embed("등록된 프로필이 없습니다. `/프로필설정`으로 등록해주세요."),
                ephemeral=True,
            )
            return

        has_srt = bool(row.get("srt_id_enc"))
        has_ktx = bool(row.get("ktx_id_enc"))
        has_card = bool(row.get("card_number_enc"))

        embed = profile_embed(
            discord_name=interaction.user.display_name,
            has_srt=has_srt,
            has_ktx=has_ktx,
            has_card=has_card,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ──────────────────────────────────
    # /프로필삭제
    # ──────────────────────────────────

    @app_commands.command(name="프로필삭제", description="등록된 프로필을 삭제합니다")
    async def delete_profile(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)
        deleted = await self.bot.user_repo.delete_user(discord_id)

        if deleted:
            await interaction.response.send_message("프로필이 삭제되었습니다.", ephemeral=True)
        else:
            await interaction.response.send_message("삭제할 프로필이 없습니다.", ephemeral=True)


async def setup(bot: SRTGoBot) -> None:
    await bot.add_cog(ProfileCog(bot))
