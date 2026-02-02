"""Discord Embed 빌더."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import discord


# 색상 상수
COLOR_SRT = 0xE74C3C  # 빨간색 (SRT)
COLOR_KTX = 0x3498DB  # 파란색 (KTX)
COLOR_SUCCESS = 0x2ECC71
COLOR_ERROR = 0xE74C3C
COLOR_WARNING = 0xF1C40F
COLOR_INFO = 0x3498DB


def rail_color(rail_type: str) -> int:
    return COLOR_SRT if rail_type == "SRT" else COLOR_KTX


def profile_embed(discord_name: str, has_srt: bool, has_ktx: bool, has_card: bool) -> discord.Embed:
    """프로필 정보 Embed."""
    embed = discord.Embed(
        title="프로필 정보",
        color=COLOR_INFO,
    )
    embed.set_author(name=discord_name)
    embed.add_field(name="SRT 계정", value="등록됨" if has_srt else "미등록", inline=True)
    embed.add_field(name="KTX 계정", value="등록됨" if has_ktx else "미등록", inline=True)
    embed.add_field(name="카드 정보", value="등록됨" if has_card else "미등록", inline=True)
    return embed


def train_list_embed(
    trains: list[dict[str, Any]], rail_type: str, departure: str, arrival: str, date: str
) -> discord.Embed:
    """열차 검색 결과 Embed."""
    formatted_date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
    embed = discord.Embed(
        title=f"열차 검색 결과 ({rail_type})",
        description=f"**{departure}** → **{arrival}** | {formatted_date}",
        color=rail_color(rail_type),
    )
    for i, t in enumerate(trains):
        dep_time = t["dep_time"]
        arr_time = t["arr_time"]
        dep_fmt = f"{dep_time[:2]}:{dep_time[2:4]}"
        arr_fmt = f"{arr_time[:2]}:{arr_time[2:4]}"
        seat_info = t.get("seat_info", "")
        name = t.get("train_name", rail_type)
        number = t.get("train_number", "")
        embed.add_field(
            name=f"{i+1}. {name} {number}",
            value=f"{dep_fmt} → {arr_fmt}\n{seat_info}",
            inline=True,
        )
    embed.set_footer(text="열차를 선택해주세요")
    return embed


def booking_summary_embed(
    rail_type: str,
    departure: str,
    arrival: str,
    date: str,
    time_str: str,
    passengers_desc: str,
    seat_type_desc: str,
    selected_trains_desc: str,
    auto_pay: bool,
) -> discord.Embed:
    """예약 요약 확인 Embed."""
    formatted_date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
    time_fmt = f"{time_str[:2]}:{time_str[2:4]}"
    embed = discord.Embed(
        title=f"예약 확인 ({rail_type})",
        color=rail_color(rail_type),
    )
    embed.add_field(name="구간", value=f"{departure} → {arrival}", inline=True)
    embed.add_field(name="날짜", value=formatted_date, inline=True)
    embed.add_field(name="시간", value=f"{time_fmt}~", inline=True)
    embed.add_field(name="승객", value=passengers_desc, inline=True)
    embed.add_field(name="좌석", value=seat_type_desc, inline=True)
    embed.add_field(name="자동결제", value="예" if auto_pay else "아니오", inline=True)
    embed.add_field(name="선택 열차", value=selected_trains_desc, inline=False)
    embed.set_footer(text="시작 버튼을 누르면 예매가 시작됩니다")
    return embed


def searching_embed(rail_type: str, attempt: int, elapsed: str) -> discord.Embed:
    """예매 진행 상태 Embed."""
    embed = discord.Embed(
        title=f"예매 진행 중... ({rail_type})",
        description=f"시도 횟수: **{attempt}**회 | 경과: {elapsed}",
        color=COLOR_WARNING,
    )
    return embed


def success_embed(
    rail_type: str, reservation_number: str, details: str
) -> discord.Embed:
    """예매 성공 Embed."""
    embed = discord.Embed(
        title=f"예매 성공! ({rail_type})",
        description=details,
        color=COLOR_SUCCESS,
    )
    if reservation_number:
        embed.add_field(name="예약번호", value=reservation_number, inline=False)
    embed.set_footer(text="이 채널은 잠시 후 삭제됩니다")
    return embed


def error_embed(message: str) -> discord.Embed:
    """에러 Embed."""
    return discord.Embed(
        title="오류",
        description=message,
        color=COLOR_ERROR,
    )


def slot_status_embed(active: int, max_slots: int, slots_info: list[dict[str, str]]) -> discord.Embed:
    """슬롯 상태 Embed."""
    embed = discord.Embed(
        title="예약 슬롯 현황",
        description=f"사용 중: **{active}** / {max_slots}",
        color=COLOR_INFO if active < max_slots else COLOR_WARNING,
    )
    for i, info in enumerate(slots_info):
        embed.add_field(
            name=f"슬롯 {i+1}",
            value=f"사용자: {info['user']}\n열차: {info['rail_type']}\n채널: {info['channel']}",
            inline=True,
        )
    if not slots_info:
        embed.add_field(name="상태", value="모든 슬롯이 비어있습니다", inline=False)
    return embed
