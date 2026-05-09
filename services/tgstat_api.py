"""
services/tgstat_api.py
Интеграция с TGStat API для поиска Telegram-каналов/групп по нише.
Документация: https://tgstat.ru/api/docs
"""
import os
import requests
from typing import Optional

TGSTAT_BASE = "https://api.tgstat.ru"


def _token() -> str:
    token = os.getenv("TGSTAT_TOKEN", "")
    if not token:
        raise ValueError("TGSTAT_TOKEN не задан в .env")
    return token


def search_channels(query: str, limit: int = 20, category: Optional[str] = None) -> list[dict]:
    """
    Поиск каналов/групп в TGStat по запросу.
    Возвращает список dict с полями: username, title, members_count, description, category.
    """
    params = {
        "token": _token(),
        "q": query,
        "limit": min(limit, 50),
    }
    if category:
        params["category"] = category

    try:
        resp = requests.get(
            f"{TGSTAT_BASE}/channels/search",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            raise ValueError(data.get("error", "TGStat API error"))

        items = data.get("response", {}).get("items", [])
        result = []
        for item in items:
            username = item.get("username") or item.get("link", "").replace("https://t.me/", "")
            if not username:
                continue
            result.append({
                "username": username.lstrip("@"),
                "title": item.get("title", username),
                "members_count": item.get("participantsCount") or item.get("members_count", 0),
                "description": item.get("description", "")[:200],
                "category": item.get("category", ""),
                "avg_reach": item.get("avgReach", 0),
                "er": item.get("er", 0),
            })
        return result

    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка соединения с TGStat: {e}") from e


def get_channel_stat(username: str) -> dict:
    """
    Получает статистику конкретного канала.
    """
    params = {
        "token": _token(),
        "channelName": username.lstrip("@"),
    }
    try:
        resp = requests.get(
            f"{TGSTAT_BASE}/channels/stat",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            raise ValueError(data.get("error", "TGStat API error"))

        r = data.get("response", {})
        return {
            "username": username,
            "title": r.get("title", username),
            "members_count": r.get("participantsCount", 0),
            "avg_reach": r.get("avgReach", 0),
            "er": r.get("er", 0),
            "category": r.get("category", ""),
            "description": r.get("description", ""),
        }
    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка соединения с TGStat: {e}") from e


def tgstat_available() -> bool:
    """Проверяет, задан ли токен TGStat."""
    return bool(os.getenv("TGSTAT_TOKEN", ""))
