"""
config.py
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'tg_leads.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # ... остальное без изменений

    # Дефолтные параметры парсинга (переопределяются через UI)
    PARSE_DAYS_BACK = int(os.getenv("PARSE_DAYS_BACK", "30"))
    PARSE_LIMIT     = int(os.getenv("PARSE_LIMIT",     "200"))

    # Fallback-ниши если БД пуста
    NICHE_GROUPS: dict[str, list[str]] = {
        "дизайн":      ["designfeedback", "design_ru", "ux_ui_ru"],
        "маркетинг":   ["marketing_ru", "smm_russia", "targetolog_ru"],
        "разработка":  ["python_ru", "javascript_ru", "freelance_dev_ru"],
        "копирайтинг": ["copywriting_ru", "content_makers"],
        "seo":         ["seo_ru", "webmaster_ru"],
        "бухгалтерия": ["buhgaltery_ru", "nalog_ru_chat"],
    }

    INTENT_KEYWORDS: list[str] = [
        "ищу", "нужен", "нужна", "нужно", "куплю", "хочу купить",
        "посоветуйте", "порекомендуйте", "требуется", "ищем",
        "кто может", "кто делает", "нужна помощь", "ищу специалиста",
    ]
    NEGATIVE_KEYWORDS: list[str] = [
        "бесплатно", "сам сделаю", "даром", "халява",
        "поделитесь", "скиньте", "пришлите", "дайте совет",
    ]
