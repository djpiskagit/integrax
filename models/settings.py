"""
models/settings.py
Модели для настроек, шаблонов и кэша TGStat.
"""
import json
from datetime import datetime
from models import db


class AppSettings(db.Model):
    """Глобальные настройки приложения (ключевые слова, группы)."""
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        row.value = json.dumps(value, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.session.commit()


class NicheGroup(db.Model):
    """Пользовательские ниши и привязанные к ним группы."""
    __tablename__ = "niche_groups"

    id = db.Column(db.Integer, primary_key=True)
    niche = db.Column(db.String(100), unique=True, nullable=False)
    groups = db.Column(db.Text, default="[]")   # JSON list of usernames
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_groups(self) -> list[str]:
        try:
            return json.loads(self.groups)
        except Exception:
            return []

    def set_groups(self, lst: list[str]):
        self.groups = json.dumps(lst, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "niche": self.niche,
            "groups": self.get_groups(),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }


class SearchTemplate(db.Model):
    """Сохранённые шаблоны поиска."""
    __tablename__ = "search_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    niche = db.Column(db.String(100), nullable=True)
    min_score = db.Column(db.Float, nullable=True)
    max_score = db.Column(db.Float, nullable=True)
    keyword = db.Column(db.String(300), nullable=True)
    date_from = db.Column(db.String(20), nullable=True)
    date_to = db.Column(db.String(20), nullable=True)
    sort_by = db.Column(db.String(50), default="final_score")
    sort_order = db.Column(db.String(4), default="desc")
    extra_filters = db.Column(db.Text, default="{}")  # JSON for future fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_count = db.Column(db.Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "niche": self.niche or "",
            "min_score": self.min_score,
            "max_score": self.max_score,
            "keyword": self.keyword or "",
            "date_from": self.date_from or "",
            "date_to": self.date_to or "",
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "used_count": self.used_count,
        }


class TGStatCache(db.Model):
    """Кэш ответов TGStat API."""
    __tablename__ = "tgstat_cache"

    id = db.Column(db.Integer, primary_key=True)
    channel_username = db.Column(db.String(100), unique=True, nullable=False)
    data = db.Column(db.Text, nullable=True)   # JSON
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_data(self) -> dict:
        try:
            return json.loads(self.data or "{}")
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "channel_username": self.channel_username,
            "data": self.get_data(),
            "fetched_at": self.fetched_at.strftime("%Y-%m-%d %H:%M"),
        }
