"""DB 테이블 DDL 정의."""

USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT UNIQUE NOT NULL,
    discord_name TEXT,
    -- SRT 자격 증명 (AES-256-GCM 암호화)
    srt_id_enc BLOB,
    srt_id_nonce BLOB,
    srt_pw_enc BLOB,
    srt_pw_nonce BLOB,
    -- KTX 자격 증명
    ktx_id_enc BLOB,
    ktx_id_nonce BLOB,
    ktx_pw_enc BLOB,
    ktx_pw_nonce BLOB,
    -- 카드 정보 (암호화)
    card_number_enc BLOB,
    card_number_nonce BLOB,
    card_password_enc BLOB,
    card_password_nonce BLOB,
    card_birthday_enc BLOB,
    card_birthday_nonce BLOB,
    card_expire_enc BLOB,
    card_expire_nonce BLOB,
    -- 설정 (평문)
    preferred_stations TEXT DEFAULT '',
    default_rail_type TEXT DEFAULT 'SRT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

BOOKING_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS booking_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    discord_channel_id TEXT,
    rail_type TEXT NOT NULL,
    departure TEXT,
    arrival TEXT,
    date TEXT,
    time TEXT,
    passengers_json TEXT,
    seat_type TEXT,
    selected_trains_json TEXT,
    auto_pay INTEGER DEFAULT 0,
    status TEXT DEFAULT 'setup',
    reservation_number TEXT,
    attempt_count INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""

FAVORITE_ROUTES_TABLE = """
CREATE TABLE IF NOT EXISTS favorite_routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    departure TEXT NOT NULL,
    arrival TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, departure, arrival)
);
"""

ALL_TABLES = [USERS_TABLE, BOOKING_SESSIONS_TABLE, FAVORITE_ROUTES_TABLE]
