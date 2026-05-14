"""
models/settings.py — полная версия, совместимая с реальным проектом.
"""
import json
from datetime import datetime
from models import db


class AppSettings(db.Model):
    """Key-value хранилище всех настроек пользователя (TG, TGStat, парсинг)."""
    __tablename__ = "app_settings"

    id         = db.Column(db.Integer,     primary_key=True)
    key        = db.Column(db.String(100), unique=True, nullable=False)
    value      = db.Column(db.Text,        nullable=True)
    updated_at = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key: str, default=None):
        row = AppSettings.query.filter_by(key=key).first()
        if row is None:
            return default
        try:
            return json.loads(row.value)
        except Exception:
            return row.value

    @staticmethod
    def set(key: str, value):
        row = AppSettings.query.filter_by(key=key).first()
        if row is None:
            row = AppSettings(key=key)
            db.session.add(row)
        row.value      = json.dumps(value, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.session.commit()


class TGAuthSession(db.Model):
    """Статус Telegram-сессии текущего пользователя."""
    __tablename__ = "tg_auth_sessions"

    id              = db.Column(db.Integer,     primary_key=True)
    phone           = db.Column(db.String(50),  nullable=True)   # nullable!
    phone_code_hash = db.Column(db.String(256), nullable=True)
    status          = db.Column(db.String(20),  default="pending")
    authorized_at   = db.Column(db.DateTime,    nullable=True)
    created_at      = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":            self.id,
            "phone":         self.phone,
            "status":        self.status,
            "authorized_at": (
                self.authorized_at.strftime("%Y-%m-%d %H:%M")
                if self.authorized_at else None
            ),
        }


class Keyword(db.Model):
    """Intent / negative ключевые слова для детектора лидов."""
    __tablename__ = "keywords"

    id         = db.Column(db.Integer,     primary_key=True)
    word       = db.Column(db.String(255), unique=True, nullable=False)
    kind       = db.Column(db.String(50),  nullable=False, default="intent")
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "word": self.word, "kind": self.kind}


class NicheGroup(db.Model):
    """Telegram-группы привязанные к нишам."""
    __tablename__ = "niche_groups"

    id            = db.Column(db.Integer,     primary_key=True)
    niche         = db.Column(db.String(100), nullable=False)
    username      = db.Column(db.String(200), nullable=False)
    title         = db.Column(db.String(300), nullable=True)
    members_count = db.Column(db.Integer,     nullable=True)
    source        = db.Column(db.String(20),  default="manual")
    active        = db.Column(db.Boolean,     default=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":            self.id,
            "niche":         self.niche,
            "username":      self.username,
            "title":         self.title or self.username,
            "members_count": self.members_count,
            "source":        self.source,
            "active":        self.active,
        }


class SearchTemplate(db.Model):
    """Сохранённые наборы фильтров (шаблоны поиска)."""
    __tablename__ = "search_templates"

    id              = db.Column(db.Integer,     primary_key=True)
    name            = db.Column(db.String(200), nullable=False)
    description     = db.Column(db.Text,        nullable=True)
    niche           = db.Column(db.String(100), nullable=True)
    min_score       = db.Column(db.Float,       nullable=True)
    keyword_filter  = db.Column(db.String(300), nullable=True)
    date_range_days = db.Column(db.Integer,     nullable=True)
    sort_by         = db.Column(db.String(50),  default="final_score")
    sort_order      = db.Column(db.String(4),   default="desc")
    extra_filters   = db.Column(db.Text,        default="{}")
    created_at      = db.Column(db.DateTime,    default=datetime.utcnow)
    used_count      = db.Column(db.Integer,     default=0)

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "name":            self.name,
            "description":     self.description or "",
            "niche":           self.niche or "",
            "min_score":       self.min_score,
            "keyword_filter":  self.keyword_filter or "",
            "date_range_days": self.date_range_days,
            "sort_by":         self.sort_by,
            "sort_order":      self.sort_order,
            "created_at":      self.created_at.strftime("%Y-%m-%d %H:%M"),
            "used_count":      self.used_count,
        }


class TGStatCache(db.Model):
    """Кэш ответов TGStat API."""
    __tablename__ = "tgstat_cache"

    id               = db.Column(db.Integer,     primary_key=True)
    channel_username = db.Column(db.String(100), unique=True, nullable=False)
    data             = db.Column(db.Text,         nullable=True)
    fetched_at       = db.Column(db.DateTime,     default=datetime.utcnow)

    def get_data(self) -> dict:
        try:
            return json.loads(self.data or "{}")
        except Exception:
            return {}
