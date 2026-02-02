"""AES-256-GCM 필드 암호화."""

from __future__ import annotations

import os

from Crypto.Cipher import AES


NONCE_SIZE = 12  # 96비트
TAG_SIZE = 16    # 128비트


class FieldEncryptor:
    """AES-256-GCM 기반 필드 단위 암복호화.

    각 필드마다 랜덤 nonce를 생성하고,
    ciphertext + GCM tag를 하나의 BLOB으로 저장한다.
    """

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("마스터 키는 32바이트여야 합니다")
        self._key = master_key

    def encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        """평문을 암호화하여 (ciphertext + tag, nonce) 반환."""
        if not plaintext:
            return b"", b""
        nonce = os.urandom(NONCE_SIZE)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
        return ciphertext + tag, nonce

    def decrypt(self, enc_blob: bytes, nonce: bytes) -> str:
        """(ciphertext + tag, nonce)에서 평문 복원."""
        if not enc_blob or not nonce:
            return ""
        ciphertext = enc_blob[:-TAG_SIZE]
        tag = enc_blob[-TAG_SIZE:]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode("utf-8")
