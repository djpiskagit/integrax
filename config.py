import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    
    SQLALCHEMY_DATABASE_URI = "sqlite:///tg_leads.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Telegram
    TG_API_ID = int(os.getenv("TG_API_ID", "0"))
    TG_API_HASH = os.getenv("TG_API_HASH", "")
    TG_PHONE = os.getenv("TG_PHONE", "")
    TG_SESSION_NAME = "tg_leads_session"

    # TGStat API
    TGSTAT_TOKEN = os.getenv("TGSTAT_TOKEN", "")

    # Лимиты парсинга
    PARSE_LIMIT_PER_GROUP = 200
    PARSE_DAYS_BACK = 30

    # Ниши → группы Telegram (используются как fallback если БД пуста)
    NICHE_GROUPS = {
        "дизайн": ["designfeedback", "design_ru", "ux_ui_ru"],
        "маркетинг": ["marketing_ru", "smm_russia", "targetolog_ru"],
        "разработка": ["python_ru", "javascript_ru", "freelance_dev_ru"],
        "копирайтинг": ["copywriting_ru", "content_makers"],
        "seo": ["seo_ru", "webmaster_ru"],
        "бухгалтерия": ["buhgaltery_ru", "nalog_ru_chat"],
    }

    # Ключевые слова (используются как fallback если БД пуста)
    INTENT_KEYWORDS = [
        "ищу", "нужен", "нужна", "нужно", "куплю", "хочу купить",
        "посоветуйте", "порекомендуйте", "требуется", "ищем",
        "кто может", "кто делает", "нужна помощь", "ищу специалиста",
    ]

    NEGATIVE_KEYWORDS = [
        "бесплатно", "сам сделаю", "даром", "халява",
        "поделитесь", "скиньте", "пришлите", "дайте совет",
    ]
