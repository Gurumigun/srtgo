"""예매 관련 슬래시 커맨드."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..core.booking_engine import BookingEngine
from ..core.booking_session import BookingSession, SessionStatus
from ..core.conversation import ConversationManager
from ..ui.embeds import error_embed, slot_status_embed

if TYPE_CHECKING:
    from ..main import SRTGoBot

log = logging.getLogger(__name__)


class BookingCog(commands.Cog):
    """예매 관련 슬래시 커맨드."""

    def __init__(self, bot: SRTGoBot) -> None:
        self.bot = bot
        self.engine = BookingEngine(bot.executor)

    # ──────────────────────────────────
    # /예매
    # ──────────────────────────────────

    @app_commands.command(name="예매", description="열차 예매를 시작합니다")
    @app_commands.describe(열차종류="예매할 열차 종류")
    @app_commands.choices(열차종류=[
        app_commands.Choice(name="SRT", value="SRT"),
        app_commands.Choice(name="KTX", value="KTX"),
    ])
    async def start_booking(
        self, interaction: discord.Interaction, 열차종류: app_commands.Choice[str]
    ) -> None:
        rail_type = 열차종류.value
        discord_id = str(interaction.user.id)

        # defer → "봇이 생각 중..." 표시 (3초 제한 해소)
        await interaction.response.defer(ephemeral=True)

        # 슬롯 확인
        if self.bot.slot_manager.is_full:
            await interaction.followup.send(
                embed=error_embed(
                    f"현재 모든 예약 슬롯이 사용 중입니다 "
                    f"({self.bot.slot_manager.active_count}/{self.bot.config.max_slots}). "
                    f"잠시 후 다시 시도해주세요."
                ),
            )
            return

        # 프로필 확인
        user_row = await self.bot.user_repo.get_by_discord_id(discord_id)
        if user_row is None:
            await interaction.followup.send(
                embed=error_embed("프로필이 등록되지 않았습니다. `/프로필설정`으로 먼저 등록해주세요."),
            )
            return

        # 자격 증명 확인
        creds = await self.bot.user_repo.get_credentials(discord_id, rail_type)
        if creds is None:
            await interaction.followup.send(
                embed=error_embed(
                    f"{rail_type} 로그인 정보가 등록되지 않았습니다. "
                    f"`/프로필설정 열차종류:{rail_type}`으로 등록해주세요."
                ),
            )
            return

        # 로그인 시도
        await interaction.followup.send(f"{rail_type} 로그인 중...")
        try:
            rail_client = await self.engine.login(rail_type, creds[0], creds[1])
        except Exception as ex:
            await interaction.followup.send(embed=error_embed(f"로그인 실패: {ex}"))
            return

        # 전용 채널 생성
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("서버에서만 사용할 수 있습니다.")
            return

        category = guild.get_channel(self.bot.config.category_id)
        if category is None or not isinstance(category, discord.CategoryChannel):
            await interaction.followup.send(
                embed=error_embed("예약 카테고리 채널을 찾을 수 없습니다. 관리자에게 문의하세요."),
            )
            return

        # 채널 권한 설정: 해당 사용자 + 봇만 접근 가능
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
            guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }

        timestamp = datetime.now().strftime("%m%d-%H%M")
        channel_name = f"예매-{interaction.user.display_name}-{rail_type}-{timestamp}".lower()
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"{interaction.user.display_name}의 {rail_type} 예매",
            )
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed("채널 생성 권한이 없습니다."))
            return

        # DB 세션 생성
        session_id = await self.bot.session_repo.create_session(
            user_id=user_row["id"],
            rail_type=rail_type,
            channel_id=str(channel.id),
        )

        # 슬롯 할당
        acquired = await self.bot.slot_manager.acquire(
            session_id=session_id,
            discord_id=discord_id,
            channel_id=str(channel.id),
            rail_type=rail_type,
        )
        if not acquired:
            await channel.delete(reason="슬롯 할당 실패")
            await interaction.followup.send(
                embed=error_embed("슬롯 할당 실패. 다시 시도해주세요."),
            )
            return

        # BookingSession 생성
        session = BookingSession(
            session_id=session_id,
            user_db_id=user_row["id"],
            discord_id=discord_id,
            channel_id=channel.id,
            rail_type=rail_type,
            rail_client=rail_client,
        )

        # ConversationManager 시작
        conv = ConversationManager(self.bot, session, channel)
        self.bot.conversations[channel.id] = conv

        await interaction.followup.send(f"예매 채널이 생성되었습니다: {channel.mention}")

        # 대화 시작
        await conv.start()

    # ──────────────────────────────────
    # /내예매
    # ──────────────────────────────────

    @app_commands.command(name="내예매", description="내 활성 예매 세션을 확인합니다")
    async def my_bookings(self, interaction: discord.Interaction) -> None:
        discord_id = str(interaction.user.id)
        user_row = await self.bot.user_repo.get_by_discord_id(discord_id)
        if user_row is None:
            await interaction.response.send_message("등록된 프로필이 없습니다.", ephemeral=True)
            return

        sessions = await self.bot.session_repo.get_active_sessions(user_id=user_row["id"])
        if not sessions:
            await interaction.response.send_message("활성 예매 세션이 없습니다.", ephemeral=True)
            return

        embed = discord.Embed(title="내 예매 현황", color=0x3498DB)
        for s in sessions:
            dep = s.get("departure", "?")
            arr = s.get("arrival", "?")
            status = s.get("status", "?")
            rail = s.get("rail_type", "?")
            channel_id = s.get("discord_channel_id", "")
            channel_mention = f"<#{channel_id}>" if channel_id else "?"
            embed.add_field(
                name=f"{rail} | {dep} → {arr}",
                value=f"상태: {status}\n채널: {channel_mention}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ──────────────────────────────────
    # /슬롯
    # ──────────────────────────────────

    @app_commands.command(name="슬롯", description="예약 슬롯 현황을 확인합니다")
    async def slot_status(self, interaction: discord.Interaction) -> None:
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
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: SRTGoBot) -> None:
    await bot.add_cog(BookingCog(bot))
