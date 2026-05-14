"""
services/tgstat.py
Интеграция с TGStat API для получения статистики каналов/групп.
Документация: https://tgstat.ru/en/api/docs
"""
import json
import time
import requests
from datetime import datetime, timedelta

from models import db


TGSTAT_BASE = "https://api.tgstat.ru"
CACHE_TTL_HOURS = 24  # кэшируем данные на 24 часа


class TGStatClient:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.params = {"token": token}

    # ─── Поиск каналов по запросу ───────────────────────────────────
    def search_channels(self, query: str, limit: int = 20) -> list[dict]:
        """Поиск каналов/групп по ключевому слову."""
        try:
            resp = self.session.get(
                f"{TGSTAT_BASE}/channels/search",
                params={"q": query, "limit": limit, "extended": 1},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("items", [])
        except Exception as e:
            return []

    # ─── Статистика канала ───────────────────────────────────────────
    def get_channel_stat(self, username: str) -> dict | None:
        """Получить статистику канала. Использует кэш."""
        from models.settings import TGStatCache

        username = username.lstrip("@").lower()

        # Проверяем кэш
        cached = TGStatCache.query.filter_by(channel_username=username).first()
        if cached:
            age = datetime.utcnow() - cached.fetched_at
            if age < timedelta(hours=CACHE_TTL_HOURS):
                return cached.get_data()

        # Запрашиваем API
        try:
            resp = self.session.get(
                f"{TGSTAT_BASE}/channels/get",
                params={"channelName": f"@{username}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("response", {})

            # Сохраняем в кэш
            if cached:
                cached.data = json.dumps(data, ensure_ascii=False)
                cached.fetched_at = datetime.utcnow()
            else:
                cached = TGStatCache(
                    channel_username=username,
                    data=json.dumps(data, ensure_ascii=False),
                )
                db.session.add(cached)
            db.session.commit()
            return data
        except Exception:
            return None

    # ─── Статистика нескольких каналов ──────────────────────────────
    def get_channels_bulk(self, usernames: list[str]) -> dict[str, dict]:
        """Получить статистику списка каналов."""
        result = {}
        for uname in usernames:
            stat = self.get_channel_stat(uname)
            if stat:
                result[uname] = stat
            time.sleep(0.3)   # небольшая задержка между запросами
        return result

    # ─── Получение постов канала ─────────────────────────────────────
    def get_channel_posts(self, username: str, limit: int = 50) -> list[dict]:
        """Последние посты канала."""
        username = username.lstrip("@")
        try:
            resp = self.session.get(
                f"{TGSTAT_BASE}/channels/{username}/posts",
                params={"limit": limit},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json().get("response", {}).get("items", [])
        except Exception:
            return []

    # ─── Поиск постов по ключевым словам ────────────────────────────
    def search_posts(self, query: str, limit: int = 100, peer_type: str = "group") -> list[dict]:
        """
        Поиск постов в каналах/группах по ключевому слову.
        peer_type: 'channel' | 'group' | 'all'
        """
        try:
            resp = self.session.get(
                f"{TGSTAT_BASE}/posts/search",
                params={
                    "q": query,
                    "limit": limit,
                    "peerType": peer_type,
                    "extended": 1,
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("response", {}).get("items", [])
        except Exception:
            return []


def get_tgstat_client() -> TGStatClient | None:
    """Создаёт клиент если токен настроен."""
    from models.settings import AppSettings
    token = AppSettings.get("tgstat_token")
    if not token:
        return None
    return TGStatClient(token)


def enrich_lead_with_tgstat(lead_dict: dict) -> dict:
    """
    Обогащает данные лида статистикой TGStat.
    Добавляет поля: tgstat_subscribers, tgstat_avg_reach, tgstat_channel_title
    """
    client = get_tgstat_client()
    if not client:
        return lead_dict

    chat_username = lead_dict.get("chat_username", "")
    if not chat_username:
        return lead_dict

    stat = client.get_channel_stat(chat_username)
    if stat:
        lead_dict["tgstat_subscribers"] = stat.get("subscribersCount", 0)
        lead_dict["tgstat_avg_reach"] = stat.get("avgReachCount", 0)
        lead_dict["tgstat_channel_title"] = stat.get("title", "")
        lead_dict["tgstat_category"] = stat.get("category", "")

    return lead_dict
