"""SRTGo Discord 봇 진입점."""

from __future__ import annotations

import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .config import Config
from .core.slot_manager import SlotManager
from .db.migrations import init_db
from .db.repository import UserRepository, SessionRepository, FavoriteRouteRepository
from .security.encryption import FieldEncryptor
from .security.key_manager import load_master_key

log = logging.getLogger("srtgo.bot")

# Cog 모듈 경로
INITIAL_COGS = [
    "bot.cogs.profile",
    "bot.cogs.booking",
    "bot.cogs.admin",
    "bot.cogs.favorite",
]


class SRTGoBot(commands.Bot):
    """SRTGo Discord 봇."""

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        self.config = config
        self.slot_manager = SlotManager(max_slots=config.max_slots)
        self.executor = ThreadPoolExecutor(max_workers=config.thread_pool_workers)

        # 보안 및 DB
        master_key = load_master_key(config.master_key)
        self.encryptor = FieldEncryptor(master_key)
        self.user_repo = UserRepository(config.db_path, self.encryptor)
        self.session_repo = SessionRepository(config.db_path)
        self.fav_repo = FavoriteRouteRepository(config.db_path)

        # 활성 대화 세션 추적: channel_id → ConversationManager
        self.conversations: dict[int, object] = {}

    async def setup_hook(self) -> None:
        """봇 시작 시 DB 초기화 + Cog 로드."""
        self.config.ensure_db_dir()
        await init_db(self.config.db_path)
        log.info("DB 초기화 완료: %s", self.config.db_path)

        for cog in INITIAL_COGS:
            try:
                await self.load_extension(cog)
                log.info("Cog 로드: %s", cog)
            except Exception:
                log.exception("Cog 로드 실패: %s", cog)

        # 슬래시 커맨드 동기화
        await self.tree.sync()
        log.info("슬래시 커맨드 동기화 완료")

    async def on_ready(self) -> None:
        log.info("봇 로그인: %s (ID: %s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="열차 예매 대기"
            )
        )

    async def on_message(self, message: discord.Message) -> None:
        """전용 채널의 대화 메시지를 ConversationManager로 라우팅."""
        if message.author.bot:
            return

        # 전용 예약 채널에서의 메시지인지 확인
        conv = self.conversations.get(message.channel.id)
        if conv is not None:
            from .core.conversation import ConversationManager
            if isinstance(conv, ConversationManager):
                await conv.handle_message(message)
                return

        # 일반 명령어 처리
        await self.process_commands(message)

    async def close(self) -> None:
        self.executor.shutdown(wait=False)
        await super().close()


def run_bot() -> None:
    """봇 실행."""
    load_dotenv()
    config = Config.from_env()

    errors = config.validate()
    if errors:
        for e in errors:
            log.error("설정 오류: %s", e)
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    bot = SRTGoBot(config)
    bot.run(config.discord_token, log_handler=None)


if __name__ == "__main__":
    run_bot()
