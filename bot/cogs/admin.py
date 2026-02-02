"""관리자 슬래시 커맨드."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..ui.embeds import slot_status_embed, error_embed

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """관리자 명령어."""

    def __init__(self, bot: SRTGoBot) -> None:
        self.bot = bot

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        """관리자 권한 확인."""
        if interaction.guild is None:
            return False
        member = interaction.guild.get_member(interaction.user.id)
        if member is None:
            return False
        return member.guild_permissions.administrator

    # ──────────────────────────────────
    # /관리 그룹
    # ──────────────────────────────────

    admin_group = app_commands.Group(name="관리", description="관리자 명령어")

    @admin_group.command(name="슬롯현황", description="전체 예약 슬롯 상태를 확인합니다")
    async def admin_slot_status(self, interaction: discord.Interaction) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        slots = self.bot.slot_manager.get_slots()
        slots_info = []
        for s in slots:
            user = interaction.guild.get_member(int(s.discord_id)) if interaction.guild else None
            slots_info.append({
                "user": user.display_name if user else s.discord_id,
                "rail_type": s.rail_type,
                "channel": f"<#{s.channel_id}>",
            })

        embed = slot_status_embed(
            active=self.bot.slot_manager.active_count,
            max_slots=self.bot.config.max_slots,
            slots_info=slots_info,
        )
        await interaction.response.send_message(embed=embed)

    @admin_group.command(name="슬롯해제", description="특정 채널의 슬롯을 강제 해제합니다")
    @app_commands.describe(channel="해제할 예약 채널")
    async def admin_release_slot(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        released = await self.bot.slot_manager.force_release_by_channel(str(channel.id))

        # 대화 세션도 정리
        conv = self.bot.conversations.pop(channel.id, None)

        # DB 세션 상태 업데이트
        db_session = await self.bot.session_repo.get_session_by_channel(str(channel.id))
        if db_session:
            await self.bot.session_repo.set_status(db_session["id"], "cancelled")

        if released:
            await interaction.response.send_message(
                f"{channel.mention} 슬롯이 해제되었습니다."
            )
        else:
            await interaction.response.send_message(
                f"{channel.mention}에 할당된 슬롯이 없습니다.", ephemeral=True
            )

    @admin_group.command(name="전체해제", description="모든 슬롯을 강제 해제합니다")
    async def admin_release_all(self, interaction: discord.Interaction) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        count = await self.bot.slot_manager.force_release_all()

        # 모든 대화 세션 정리
        self.bot.conversations.clear()

        await interaction.response.send_message(f"{count}개 슬롯이 해제되었습니다.")

    @admin_group.command(name="채널삭제", description="예약 채널을 강제 삭제합니다")
    @app_commands.describe(channel="삭제할 예약 채널")
    async def admin_delete_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        if not self._is_admin(interaction):
            await interaction.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
            return

        # 슬롯 해제
        await self.bot.slot_manager.force_release_by_channel(str(channel.id))
        self.bot.conversations.pop(channel.id, None)

        # DB 세션 상태 업데이트
        db_session = await self.bot.session_repo.get_session_by_channel(str(channel.id))
        if db_session:
            await self.bot.session_repo.set_status(db_session["id"], "cancelled")

        try:
            await channel.delete(reason=f"관리자 {interaction.user.display_name}에 의해 삭제")
            await interaction.response.send_message("채널이 삭제되었습니다.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("채널 삭제 권한이 없습니다."),
                ephemeral=True,
            )


async def setup(bot: SRTGoBot) -> None:
    await bot.add_cog(AdminCog(bot))
