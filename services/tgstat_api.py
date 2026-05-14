"""
services/tgstat_api.py
TGStat API — токен берётся из AppSettings (БД), не из .env.
"""
import requests
from typing import Optional

TGSTAT_BASE = "https://api.tgstat.ru"


def _get_token(token: str = "") -> str:
    if token:
        return token
    from models.settings import AppSettings
    t = AppSettings.get("tgstat_token", "")
    if not t:
        raise ValueError("TGSTAT_TOKEN не задан в настройках")
    return t


def search_channels(query: str, limit: int = 20,
                    category: Optional[str] = None, token: str = "") -> list[dict]:
    params = {"token": _get_token(token), "q": query, "limit": min(limit, 50)}
    if category:
        params["category"] = category
    try:
        resp = requests.get(f"{TGSTAT_BASE}/channels/search", params=params, timeout=10)
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
                "username":      username.lstrip("@"),
                "title":         item.get("title", username),
                "members_count": item.get("participantsCount") or item.get("members_count", 0),
                "description":   item.get("description", "")[:200],
                "category":      item.get("category", ""),
                "avg_reach":     item.get("avgReach", 0),
                "er":            item.get("er", 0),
            })
        return result
    except requests.RequestException as e:
        raise ConnectionError(f"Ошибка соединения с TGStat: {e}") from e


def tgstat_available() -> bool:
    from models.settings import AppSettings
    return bool(AppSettings.get("tgstat_token", ""))
