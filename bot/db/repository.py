"""사용자 및 예약 세션 데이터 접근 계층."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import aiosqlite

from ..security.encryption import FieldEncryptor


class UserRepository:
    """users 테이블 CRUD."""

    # 암호화 대상 필드 접두사 → (enc 컬럼, nonce 컬럼)
    ENCRYPTED_FIELDS = {
        "srt_id": ("srt_id_enc", "srt_id_nonce"),
        "srt_pw": ("srt_pw_enc", "srt_pw_nonce"),
        "ktx_id": ("ktx_id_enc", "ktx_id_nonce"),
        "ktx_pw": ("ktx_pw_enc", "ktx_pw_nonce"),
        "card_number": ("card_number_enc", "card_number_nonce"),
        "card_password": ("card_password_enc", "card_password_nonce"),
        "card_birthday": ("card_birthday_enc", "card_birthday_nonce"),
        "card_expire": ("card_expire_enc", "card_expire_nonce"),
    }

    def __init__(self, db_path: str, encryptor: FieldEncryptor) -> None:
        self._db_path = db_path
        self._enc = encryptor

    async def get_by_discord_id(self, discord_id: str) -> dict[str, Any] | None:
        """Discord ID로 사용자 조회."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE discord_id = ?", (discord_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def upsert_user(
        self, discord_id: str, discord_name: str, **fields: str
    ) -> int:
        """사용자 생성 또는 업데이트. 암호화 필드는 평문으로 전달하면 자동 암호화."""
        existing = await self.get_by_discord_id(discord_id)

        # 암호화 필드 처리
        enc_columns: dict[str, Any] = {}
        for field_name, plaintext in fields.items():
            if field_name in self.ENCRYPTED_FIELDS:
                enc_col, nonce_col = self.ENCRYPTED_FIELDS[field_name]
                enc_blob, nonce = self._enc.encrypt(plaintext)
                enc_columns[enc_col] = enc_blob
                enc_columns[nonce_col] = nonce
            else:
                enc_columns[field_name] = plaintext

        async with aiosqlite.connect(self._db_path) as db:
            if existing is None:
                cols = ["discord_id", "discord_name"] + list(enc_columns.keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_str = ", ".join(cols)
                values = [discord_id, discord_name] + list(enc_columns.values())
                cursor = await db.execute(
                    f"INSERT INTO users ({col_str}) VALUES ({placeholders})", values
                )
                await db.commit()
                return cursor.lastrowid  # type: ignore[return-value]
            else:
                enc_columns["discord_name"] = discord_name
                enc_columns["updated_at"] = datetime.now().isoformat()
                set_clause = ", ".join(f"{k} = ?" for k in enc_columns)
                values = list(enc_columns.values()) + [discord_id]
                await db.execute(
                    f"UPDATE users SET {set_clause} WHERE discord_id = ?", values
                )
                await db.commit()
                return existing["id"]

    async def delete_user(self, discord_id: str) -> bool:
        """사용자 삭제."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM users WHERE discord_id = ?", (discord_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def decrypt_field(self, row: dict[str, Any], field_name: str) -> str:
        """DB row에서 암호화된 필드를 복호화."""
        if field_name not in self.ENCRYPTED_FIELDS:
            return row.get(field_name, "")
        enc_col, nonce_col = self.ENCRYPTED_FIELDS[field_name]
        enc_blob = row.get(enc_col)
        nonce = row.get(nonce_col)
        if not enc_blob or not nonce:
            return ""
        return self._enc.decrypt(enc_blob, nonce)

    async def get_credentials(
        self, discord_id: str, rail_type: str
    ) -> tuple[str, str] | None:
        """열차 종류에 따른 로그인 자격 증명 반환."""
        row = await self.get_by_discord_id(discord_id)
        if row is None:
            return None
        prefix = "srt" if rail_type == "SRT" else "ktx"
        user_id = self.decrypt_field(row, f"{prefix}_id")
        user_pw = self.decrypt_field(row, f"{prefix}_pw")
        if not user_id or not user_pw:
            return None
        return user_id, user_pw

    async def get_card_info(self, discord_id: str) -> dict[str, str] | None:
        """카드 정보 반환."""
        row = await self.get_by_discord_id(discord_id)
        if row is None:
            return None
        number = self.decrypt_field(row, "card_number")
        if not number:
            return None
        return {
            "number": number,
            "password": self.decrypt_field(row, "card_password"),
            "birthday": self.decrypt_field(row, "card_birthday"),
            "expire": self.decrypt_field(row, "card_expire"),
        }


class SessionRepository:
    """booking_sessions 테이블 CRUD."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create_session(self, user_id: int, rail_type: str, channel_id: str) -> int:
        """새 예약 세션 생성."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO booking_sessions (user_id, rail_type, discord_channel_id, status)
                   VALUES (?, ?, ?, 'setup')""",
                (user_id, rail_type, channel_id),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def get_session(self, session_id: int) -> dict[str, Any] | None:
        """세션 ID로 조회."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM booking_sessions WHERE id = ?", (session_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_active_sessions(self, user_id: int | None = None) -> list[dict[str, Any]]:
        """활성 세션 목록 (setup/searching/reserved)."""
        query = """SELECT * FROM booking_sessions
                   WHERE status IN ('setup', 'searching', 'reserved')"""
        params: list[Any] = []
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_session(self, session_id: int, **fields: Any) -> None:
        """세션 필드 업데이트."""
        if not fields:
            return
        # JSON 직렬화가 필요한 필드
        for key in ("passengers_json", "selected_trains_json"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [session_id]
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                f"UPDATE booking_sessions SET {set_clause} WHERE id = ?", values
            )
            await db.commit()

    async def set_status(self, session_id: int, status: str) -> None:
        """세션 상태 변경."""
        update: dict[str, Any] = {"status": status}
        if status == "searching":
            update["started_at"] = datetime.now().isoformat()
        elif status in ("reserved", "paid", "cancelled", "timeout", "error"):
            update["completed_at"] = datetime.now().isoformat()
        await self.update_session(session_id, **update)

    async def increment_attempt(self, session_id: int) -> int:
        """시도 횟수 증가 후 현재 값 반환."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE booking_sessions SET attempt_count = attempt_count + 1 WHERE id = ?",
                (session_id,),
            )
            await db.commit()
            cursor = await db.execute(
                "SELECT attempt_count FROM booking_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_session_by_channel(self, channel_id: str) -> dict[str, Any] | None:
        """채널 ID로 활성 세션 조회."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM booking_sessions
                   WHERE discord_channel_id = ? AND status IN ('setup', 'searching', 'reserved')
                   ORDER BY id DESC LIMIT 1""",
                (channel_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None


class FavoriteRouteRepository:
    """favorite_routes 테이블 CRUD."""

    MAX_FAVORITES = 6

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def add(self, user_id: int, departure: str, arrival: str) -> int:
        """즐겨찾기 추가. 6개 제한 초과 시 ValueError."""
        current = await self.count(user_id)
        if current >= self.MAX_FAVORITES:
            raise ValueError(f"최대 {self.MAX_FAVORITES}개까지 등록 가능합니다.")
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT OR IGNORE INTO favorite_routes (user_id, departure, arrival)
                   VALUES (?, ?, ?)""",
                (user_id, departure, arrival),
            )
            await db.commit()
            if cursor.lastrowid == 0 or cursor.rowcount == 0:
                raise ValueError("이미 등록된 노선입니다.")
            return cursor.lastrowid  # type: ignore[return-value]

    async def get_all(self, user_id: int) -> list[dict[str, Any]]:
        """사용자의 즐겨찾기 전체 조회."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM favorite_routes WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def remove(self, route_id: int, user_id: int) -> bool:
        """즐겨찾기 삭제."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM favorite_routes WHERE id = ? AND user_id = ?",
                (route_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def count(self, user_id: int) -> int:
        """즐겨찾기 개수 조회."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM favorite_routes WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
