"""마스터 키 로드 및 생성."""

from __future__ import annotations

import os
import secrets


def load_master_key(hex_key: str) -> bytes:
    """64자리 hex 문자열을 32바이트 키로 변환."""
    if len(hex_key) != 64:
        raise ValueError("마스터 키는 64자리 hex 문자열이어야 합니다 (32바이트)")
    return bytes.fromhex(hex_key)


def generate_master_key() -> str:
    """새 마스터 키 생성 (64자리 hex)."""
    return secrets.token_hex(32)
