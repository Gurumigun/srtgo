"""DB 초기화 및 마이그레이션."""

from __future__ import annotations

import aiosqlite

from .models import ALL_TABLES


async def init_db(db_path: str) -> None:
    """DB 초기화: 테이블이 없으면 생성."""
    async with aiosqlite.connect(db_path) as db:
        for ddl in ALL_TABLES:
            await db.execute(ddl)
        await db.commit()
