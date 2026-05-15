Content is user-generated and unverified.
"""
services/tg_auth.py

SOCKS5 / MTProxy прокси читается из AppSettings:
  proxy_type   — "socks5" | "mtproto" | "" (отключён)
  proxy_host   — hostname или IP
  proxy_port   — порт (int)
  proxy_user   — только для SOCKS5 с авторизацией (опционально)
  proxy_pass   — только для SOCKS5 с авторизацией (опционально)
  proxy_secret — только для MTProto (hex-строка)

Исправленные баги:
  [1] asyncio.run() блокировал Flask-тред при таймауте MTProto (20 сек и более).
      Теперь каждая async-операция запускается в отдельном потоке через _run_async(),
      с явным таймаутом и чистым event loop.
  [2] proxy_port мог прийти из БД с двойным JSON-encode: "\"1080\"".
      Добавлен strip('"') перед int(), что обезвреживает оба варианта.
  [3] proxy_port == "0" или "" проходил проверку `not proxy_port` некорректно.
      Теперь порт проверяется явно: port > 0.
  [4] is_authorized() создавал клиент без прокси → вис при блокировке хостинга.
      Прокси теперь передаётся, таймаут уменьшен до 10 сек.
  [5] `with ThreadPoolExecutor` вызывает shutdown(wait=True) при выходе —
      при таймауте Flask-тред блокировался до завершения фонового потока
      (воспроизводило исходную проблему зависания). Исправлено: shutdown(wait=False).
  [6] Корутина не отменялась при таймауте — фоновые потоки Telethon накапливались.
      Исправлено: asyncio.wait_for внутри + явная отмена задач перед закрытием loop.
  [7] sign_in() не имел disconnect в finally — утечка TCP-соединения при любом
      исключении после connect(). Добавлен finally блок.
  [8] int(api_id) в _get_credentials без try/except — нечисловое значение из БД
      давало голый ValueError без контекста. Теперь понятное сообщение.
  [9] proxy_secret с пробелами ("dd ab cd") → bytes.fromhex() падал с ValueError.
      Добавлен replace(" ", "") перед fromhex().
  [10] Неизвестный proxy_type молча возвращал None без лога — опечатка пользователя
       была незаметна. Теперь логируется warning.
  [11] logout() вызывал _get_session_path() дважды — разные вызовы могли вернуть
       разный путь если Flask-контекст менялся между ними. Путь фиксируется заранее.
"""
import asyncio
import concurrent.futures
import os
import logging
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.network import ConnectionTcpAbridged

logger = logging.getLogger(__name__)


# ── Запуск async-кода из синхронного Flask-контекста ─────────────────
# FIX [1][5][6]:
#   • asyncio.run() в Flask-треде блокировал тред навсегда при таймауте.
#   • `with ThreadPoolExecutor` вызывает shutdown(wait=True) при выходе —
#     при таймауте тред всё равно блокировался до конца фоновой операции.
#   • Корутина не отменялась при таймауте → накопление фоновых потоков Telethon.
#
# Решение:
#   • executor.shutdown(wait=False) — не ждём завершения фонового потока.
#   • asyncio.wait_for внутри _runner — корутина отменяется изнутри event loop.
#   • Явная отмена оставшихся задач перед loop.close().
def _run_async(coro, timeout: float = 30):
    """
    Запускает корутину в изолированном потоке с новым event loop.
    Бросает TimeoutError если операция не завершилась за timeout секунд.
    Flask-тред не блокируется даже при зависании фоновой операции.
    """
    inner_timeout = max(timeout - 0.5, 1.0)

    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                asyncio.wait_for(coro, timeout=inner_timeout)
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Операция превысила таймаут {timeout} сек. "
                "Проверьте прокси или доступность Telegram."
            )
        finally:
            # Отменяем все оставшиеся задачи перед закрытием loop
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.close()

    # FIX [5]: shutdown(wait=False) — не блокируем Flask-тред при таймауте
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_runner)
    executor.shutdown(wait=False)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(
            f"Операция превысила таймаут {timeout} сек. "
            "Проверьте прокси или доступность Telegram."
        )


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
    # FIX [8]: int() без try/except давал голый ValueError если api_id нечисловой
    try:
        return int(api_id), str(api_hash)
    except (ValueError, TypeError):
        raise ValueError(
            "TG_API_ID должен быть числом. Проверьте значение в Настройки → Конфигурация."
        )


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
        proxy_secret = (AppSettings.get("proxy_secret") or "").strip()
        proxy_user   = (AppSettings.get("proxy_user")   or "").strip() or None
        proxy_pass   = (AppSettings.get("proxy_pass")   or "").strip() or None

        # FIX [2]: AppSettings сохраняет через json.dumps(str(...)), поэтому
        # proxy_port может вернуться как '\"1080\"' (двойной encode).
        # strip('"') нейтрализует лишние кавычки перед int().
        proxy_port_raw = AppSettings.get("proxy_port") or ""
        if isinstance(proxy_port_raw, str):
            proxy_port_raw = proxy_port_raw.strip().strip('"')

        if not proxy_type or not proxy_host or not proxy_port_raw:
            return None

        port = int(proxy_port_raw)

        # FIX [3]: порт "0" технически не пустая строка, но невалиден.
        if port <= 0:
            logger.warning("proxy_port <= 0, прокси отключён")
            return None

        if proxy_type == "socks5":
            if proxy_user:
                return ("socks5", proxy_host, port, True, proxy_user, proxy_pass or "")
            return ("socks5", proxy_host, port)

        if proxy_type == "mtproto":
            if not proxy_secret:
                raise ValueError("MTProto прокси требует секрет (proxy_secret)")
            # FIX [9]: пробелы в hex-строке ("dd ab cd") ломали bytes.fromhex()
            secret_bytes = bytes.fromhex(proxy_secret.replace(" ", ""))
            return ("mtproto", proxy_host, port, False, secret_bytes)

        # FIX [10]: неизвестный тип молча возвращал None — опечатка пользователя
        # была незаметна. Теперь логируется.
        logger.warning(
            f"Неизвестный тип прокси: {proxy_type!r}. "
            "Допустимые значения: 'socks5', 'mtproto'."
        )

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
    # FIX [1] + FIX [4]:
    #   • Используем _run_async с коротким таймаутом (10 сек) —
    #     страница настроек не висит дольше этого времени.
    #   • Прокси передаётся в клиент (раньше kwargs его не содержал).
    async def _check():
        try:
            api_id, api_hash = _get_credentials()
        except ValueError:
            return False
        proxy = _get_proxy()
        kwargs = dict(connection_retries=2, timeout=8)
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
        return _run_async(_check(), timeout=10)
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
        return _run_async(_me(), timeout=25)
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

    return _run_async(_send(), timeout=30)


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
        finally:
            # FIX [7]: утечка TCP-соединения при исключении после connect()
            try:
                await client.disconnect()
            except Exception:
                pass
        return {
            "id":         me.id,
            "username":   me.username,
            "first_name": me.first_name,
            "last_name":  me.last_name,
            "phone":      me.phone,
        }

    return _run_async(_signin(), timeout=30)


def logout() -> bool:
    # FIX [11]: _get_session_path() вызывался дважды — если Flask-контекст
    # менялся между вызовами, пути могли различаться. Фиксируем заранее.
    session_path = _get_session_path()

    async def _logout():
        client = _make_client(session_path)
        try:
            await client.connect()
            await client.log_out()
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    try:
        _run_async(_logout(), timeout=15)
    except Exception:
        pass

    sf = session_path + ".session"
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
        return _run_async(_test(), timeout=20)
    except Exception as e:
        return {"ok": False, "message": str(e), "proxy_info": proxy_info}

