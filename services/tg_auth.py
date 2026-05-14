"""
services/tg_auth.py

SOCKS5 / MTProxy прокси читается из AppSettings:
  proxy_type   — "socks5" | "mtproto" | "" (отключён)
  proxy_host   — hostname или IP
  proxy_port   — порт (int)
  proxy_user   — только для SOCKS5 с авторизацией (опционально)
  proxy_pass   — только для SOCKS5 с авторизацией (опционально)
  proxy_secret — только для MTProto (hex-строка)
"""
import asyncio
import os
import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.network import ConnectionTcpAbridged

logger = logging.getLogger(__name__)


# ── Путь к .session файлу текущего пользователя ─────────────────────
def _get_session_path() -> str:
    try:
        from flask import session as flask_session
        login = flask_session.get("user_login") or "default"
    except RuntimeError:
        login = "default"
    user_dir = Path("data") / "users" / login
    user_dir.mkdir(parents=True, exist_ok=True)
    return str(user_dir / "session")


# ── API credentials из БД ───────────────────────────────────────────
def _get_credentials() -> tuple[int, str]:
    from models.settings import AppSettings
    api_id   = AppSettings.get("tg_api_id")
    api_hash = AppSettings.get("tg_api_hash")
    if not api_id or not api_hash:
        raise ValueError(
            "TG_API_ID и TG_API_HASH не заданы. "
            "Сохраните их в Настройки → Конфигурация."
        )
    return int(api_id), str(api_hash)


# ── Прокси из БД ────────────────────────────────────────────────────
def _get_proxy() -> tuple | None:
    """
    Читает настройки прокси из AppSettings.
    Возвращает tuple для Telethon или None если прокси отключён.

    Форматы Telethon:
      SOCKS5 без auth:   ('socks5', 'host', port)
      SOCKS5 с auth:     ('socks5', 'host', port, True, 'user', 'pass')
      MTProto:           ('mtproto', 'host', port, False, secret_bytes)
    """
    try:
        from models.settings import AppSettings
        proxy_type   = (AppSettings.get("proxy_type")   or "").strip().lower()
        proxy_host   = (AppSettings.get("proxy_host")   or "").strip()
        proxy_port   = AppSettings.get("proxy_port")
        proxy_secret = (AppSettings.get("proxy_secret") or "").strip()
        proxy_user   = (AppSettings.get("proxy_user")   or "").strip() or None
        proxy_pass   = (AppSettings.get("proxy_pass")   or "").strip() or None

        if not proxy_type or not proxy_host or not proxy_port:
            return None

        port = int(proxy_port)

        if proxy_type == "socks5":
            if proxy_user:
                return ("socks5", proxy_host, port, True, proxy_user, proxy_pass or "")
            return ("socks5", proxy_host, port)

        if proxy_type == "mtproto":
            if not proxy_secret:
                raise ValueError("MTProto прокси требует секрет (proxy_secret)")
            secret_bytes = bytes.fromhex(proxy_secret)
            return ("mtproto", proxy_host, port, False, secret_bytes)

    except Exception as e:
        logger.warning(f"Ошибка чтения прокси: {e}")

    return None


# ── Создание клиента ─────────────────────────────────────────────────
def _make_client(session_path: str | None = None) -> TelegramClient:
    api_id, api_hash = _get_credentials()
    proxy = _get_proxy()
    path  = session_path or _get_session_path()

    kwargs = dict(
        connection=ConnectionTcpAbridged,
        connection_retries=3,
        retry_delay=2,
        timeout=20,
        request_retries=3,
        device_model="Desktop",
        system_version="Windows 10",
        app_version="4.16.6",
        lang_code="ru",
        system_lang_code="ru-RU",
    )
    if proxy:
        kwargs["proxy"] = proxy
        logger.info(f"Используем прокси: {proxy[0]} {proxy[1]}:{proxy[2]}")

    return TelegramClient(path, api_id, api_hash, **kwargs)


# ── Публичный API ────────────────────────────────────────────────────

def is_authorized() -> bool:
    async def _check():
        try:
            api_id, api_hash = _get_credentials()
        except ValueError:
            return False
        proxy = _get_proxy()
        kwargs = dict(connection_retries=2, timeout=15)
        if proxy:
            kwargs["proxy"] = proxy
        client = TelegramClient(_get_session_path(), api_id, api_hash, **kwargs)
        try:
            await client.connect()
            return await client.is_user_authorized()
        except Exception as e:
            logger.warning(f"is_authorized error: {e}")
            return False
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    try:
        return asyncio.run(_check())
    except Exception as e:
        logger.warning(f"is_authorized outer: {e}")
        return False


def get_me() -> dict | None:
    async def _me():
        client = _make_client()
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return None
            me = await client.get_me()
            return {
                "id":         me.id,
                "username":   me.username,
                "first_name": me.first_name,
                "last_name":  me.last_name,
                "phone":      me.phone,
            }
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    try:
        return asyncio.run(_me())
    except Exception as e:
        logger.warning(f"get_me error: {e}")
        return None


def send_code(phone: str) -> str:
    async def _send():
        client = _make_client()
        try:
            await client.connect()
            result = await client.send_code_request(phone)
            return result.phone_code_hash
        except ConnectionError as e:
            proxy = _get_proxy()
            hint = (
                "Прокси настроен, но недоступен — проверьте host/port."
                if proxy else
                "Хостинг блокирует MTProto. Настройте SOCKS5 или MTProxy в разделе Конфигурация → Прокси."
            )
            raise ConnectionError(f"Не удалось подключиться к Telegram: {e}. {hint}") from e
        except Exception as e:
            err = str(e)
            if any(w in err.lower() for w in ("connect", "5 time", "timeout", "network", "socket")):
                proxy = _get_proxy()
                hint = (
                    "Прокси настроен, но не работает — проверьте настройки."
                    if proxy else
                    "Хостинг блокирует MTProto. Настройте SOCKS5 или MTProxy в Конфигурация → Прокси."
                )
                raise ConnectionError(f"Ошибка подключения: {e}. {hint}") from e
            raise
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    return asyncio.run(_send())


def sign_in(phone: str, code: str, phone_code_hash: str,
            password: str | None = None) -> dict:
    async def _signin():
        client = _make_client()
        await client.connect()
        try:
            me = await client.sign_in(
                phone=phone, code=code, phone_code_hash=phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not password:
                raise
            me = await client.sign_in(password=password)
        return {
            "id":         me.id,
            "username":   me.username,
            "first_name": me.first_name,
            "last_name":  me.last_name,
            "phone":      me.phone,
        }
    return asyncio.run(_signin())


def logout() -> bool:
    async def _logout():
        client = _make_client()
        try:
            await client.connect()
            await client.log_out()
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    try:
        asyncio.run(_logout())
    except Exception:
        pass
    sf = _get_session_path() + ".session"
    if os.path.exists(sf):
        os.remove(sf)
    return True


def test_proxy() -> dict:
    """
    Проверяет подключение через настроенный прокси.
    Возвращает {"ok": True/False, "message": "...", "proxy_info": "..."}.
    """
    proxy = _get_proxy()
    if not proxy:
        return {"ok": False, "message": "Прокси не настроен — заполните поля ниже"}

    proxy_info = f"{proxy[0].upper()} {proxy[1]}:{proxy[2]}"

    async def _test():
        try:
            api_id, api_hash = _get_credentials()
        except ValueError as e:
            return {"ok": False, "message": str(e), "proxy_info": proxy_info}
        client = TelegramClient(
            _get_session_path(), api_id, api_hash,
            proxy=proxy, connection_retries=2, timeout=15,
        )
        try:
            await client.connect()
            return {"ok": True, "message": "Прокси работает, Telegram доступен ✓", "proxy_info": proxy_info}
        except Exception as e:
            return {"ok": False, "message": f"Ошибка: {e}", "proxy_info": proxy_info}
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    try:
        return asyncio.run(_test())
    except Exception as e:
        return {"ok": False, "message": str(e), "proxy_info": proxy_info}
