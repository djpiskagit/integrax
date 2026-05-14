"""
services/scorer.py
Скоринг лидов по трём метрикам (0–100).
"""
from datetime import datetime, timezone
from config import Config


# Веса компонент
WEIGHT_INTENT = 0.45
WEIGHT_ACTIVITY = 0.25
WEIGHT_NICHE = 0.30


def compute_intent_score(matched_keywords: list[str], text: str) -> float:
    """
    Intent score (0–100):
    - Базово: +20 за каждое ключевое слово (до 3 слов = 60 макс)
    - Бонус +20 если длина сообщения > 100 символов (детальный запрос)
    - Бонус +20 если упоминается бюджет/цена/оплата
    """
    score = 0.0

    # Ключевые слова
    score += min(len(matched_keywords) * 20, 60)

    # Длина сообщения — признак серьёзного запроса
    if len(text) > 100:
        score += 20

    # Упоминание бюджета
    budget_hints = ["бюджет", "готов платить", "оплачу", "цена", "стоимость", "руб", "₽", "$", "€"]
    lower = text.lower()
    if any(h in lower for h in budget_hints):
        score += 20

    return min(score, 100.0)


def compute_activity_score(user_message_count: int) -> float:
    """
    Activity score (0–100):
    Чем больше сообщений пользователь отправил в группе — тем активнее.
    Шкала логарифмическая: 1 msg=20, 5=60, 10+=100
    """
    if user_message_count <= 0:
        return 0.0
    import math
    score = min(math.log(user_message_count + 1, 10) * 50, 100.0)
    return round(score, 1)


def compute_niche_score(text: str, niche: str, chat_username: str) -> float:
    """
    Niche score (0–100):
    - Совпадение нише в тексте сообщения: +40
    - Группа входит в список групп ниши: +60
    """
    score = 0.0

    # Нишевые слова в тексте
    niche_words = _get_niche_words(niche)
    lower = text.lower()
    hits = sum(1 for w in niche_words if w in lower)
    score += min(hits * 20, 40)

    # Группа из нишевого списка
    niche_groups = Config.NICHE_GROUPS.get(niche.lower(), [])
    if chat_username and chat_username.lstrip("@") in niche_groups:
        score += 60

    return min(score, 100.0)


def compute_final_score(intent: float, activity: float, niche: float) -> float:
    """Взвешенная итоговая оценка 0–100"""
    return round(
        intent * WEIGHT_INTENT + activity * WEIGHT_ACTIVITY + niche * WEIGHT_NICHE,
        1,
    )


def score_lead(
    text: str,
    matched_keywords: list[str],
    niche: str,
    chat_username: str,
    user_message_count: int = 1,
) -> dict:
    """
    Полный скоринг одного лида.
    Возвращает dict со всеми компонентами и final_score.
    """
    intent = compute_intent_score(matched_keywords, text)
    activity = compute_activity_score(user_message_count)
    niche_sc = compute_niche_score(text, niche, chat_username)
    final = compute_final_score(intent, activity, niche_sc)

    return {
        "intent_score": intent,
        "activity_score": activity,
        "niche_score": niche_sc,
        "final_score": final,
    }


def _get_niche_words(niche: str) -> list[str]:
    """Словарь нишевых слов для текстового матчинга"""
    mapping = {
        "дизайн": ["дизайн", "лого", "логотип", "макет", "ui", "ux", "figma", "баннер", "визитка", "брендинг"],
        "маркетинг": ["маркетинг", "реклама", "smm", "таргет", "продвижение", "контент", "трафик", "лиды"],
        "разработка": ["разработка", "программист", "сайт", "бот", "приложение", "python", "backend", "frontend", "api"],
        "копирайтинг": ["текст", "копирайтинг", "статья", "пост", "контент", "описание", "лендинг"],
        "seo": ["seo", "сео", "поисковик", "яндекс", "гугл", "позиции", "оптимизация", "ключевые слова"],
        "бухгалтерия": ["бухгалтер", "налоги", "отчёт", "ип", "ооо", "декларация", "1с", "бухучёт"],
    }
    return mapping.get(niche.lower(), [niche.lower()])
