"""
services/tg_auth.py
Авторизация в Telegram через Telethon: телефон → SMS-код → сессия.
"""
import asyncio
import os
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    SessionPasswordNeededError,
    FloodWaitError,
)

from config import Config


_CLIENT: TelegramClient | None = None
_PHONE_CODE_HASH: str | None = None


def _get_client() -> TelegramClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = TelegramClient(
            Config.TG_SESSION_NAME,
            Config.TG_API_ID,
            Config.TG_API_HASH,
        )
    return _CLIENT


def is_authorized() -> bool:
    """Синхронная проверка авторизации."""
    async def _check():
        client = _get_client()
        if not client.is_connected():
            await client.connect()
        return await client.is_user_authorized()

    try:
        return asyncio.run(_check())
    except Exception:
        return False


def get_me() -> dict | None:
    """Возвращает данные текущего пользователя или None."""
    async def _me():
        client = _get_client()
        if not client.is_connected():
            await client.connect()
        if not await client.is_user_authorized():
            return None
        me = await client.get_me()
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "phone": me.phone,
        }

    try:
        return asyncio.run(_me())
    except Exception:
        return None


def send_code(phone: str) -> str:
    """
    Отправляет SMS-код на телефон.
    Возвращает phone_code_hash.
    """
    global _PHONE_CODE_HASH

    async def _send():
        client = _get_client()
        if not client.is_connected():
            await client.connect()
        result = await client.send_code_request(phone)
        return result.phone_code_hash

    phone_code_hash = asyncio.run(_send())
    _PHONE_CODE_HASH = phone_code_hash
    return phone_code_hash


def sign_in(phone: str, code: str, phone_code_hash: str, password: str | None = None) -> dict:
    """
    Подтверждает код и авторизует.
    Возвращает dict с данными пользователя.
    Raises: PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError
    """
    async def _signin():
        client = _get_client()
        if not client.is_connected():
            await client.connect()

        if password:
            # 2FA
            me = await client.sign_in(password=password)
        else:
            me = await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash,
            )
        return {
            "id": me.id,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "phone": me.phone,
        }

    return asyncio.run(_signin())


def logout() -> bool:
    """Разлогинивает и удаляет сессию."""
    async def _logout():
        client = _get_client()
        if not client.is_connected():
            await client.connect()
        await client.log_out()
        return True

    try:
        asyncio.run(_logout())
        # Удаляем файл сессии
        session_file = f"{Config.TG_SESSION_NAME}.session"
        if os.path.exists(session_file):
            os.remove(session_file)
        global _CLIENT
        _CLIENT = None
        return True
    except Exception:
        return False
