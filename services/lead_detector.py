"""
services/lead_detector.py
Определяет, является ли сообщение лидом.
Читает ключевые слова из БД; если БД недоступна — из config.py.
"""
from config import Config


def _get_keywords() -> tuple[list[str], list[str]]:
    """
    Возвращает (intent_keywords, negative_keywords).
    Приоритет: БД → config.py.
    """
    try:
        from models.settings import Keyword
        keywords = Keyword.query.all()
        if keywords:
            intent = [k.word for k in keywords if k.kind == "intent"]
            negative = [k.word for k in keywords if k.kind == "negative"]
            if intent:  # Если в БД есть хотя бы intent-слова — используем БД
                return intent, negative
    except Exception:
        pass

    # Fallback к config.py
    return Config.INTENT_KEYWORDS, Config.NEGATIVE_KEYWORDS


def is_lead(text: str) -> tuple[bool, list[str]]:
    """
    Возвращает (is_lead: bool, matched_keywords: list[str])

    Логика:
    - Есть хотя бы одно intent-ключевое слово → кандидат в лид
    - Нет минус-слов → подтверждённый лид
    """
    intent_kws, negative_kws = _get_keywords()
    lower = text.lower()

    # Проверяем минус-слова первыми — быстрый выход
    for neg in negative_kws:
        if neg in lower:
            return False, []

    matched = []
    for kw in intent_kws:
        if kw in lower:
            matched.append(kw)

    return len(matched) > 0, matched


def filter_leads(messages: list[dict]) -> list[dict]:
    """
    Принимает список dict с ключом 'text'.
    Возвращает только те, что являются лидами,
    добавляя поле 'matched_keywords'.
    """
    result = []
    for msg in messages:
        ok, keywords = is_lead(msg.get("text", ""))
        if ok:
            msg["matched_keywords"] = keywords
            result.append(msg)
    return result
