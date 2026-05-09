"""
models/settings.py
Модели для хранения настроек: keywords, groups, шаблоны поиска.
"""
from datetime import datetime
from models import db


class Keyword(db.Model):
    """Ключевые слова для определения лидов."""
    __tablename__ = "keywords"

    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(200), nullable=False, unique=True)
    kind = db.Column(db.String(10), nullable=False, default="intent")
    # kind: "intent" | "negative"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "word": self.word, "kind": self.kind}


class NicheGroup(db.Model):
    """Telegram-группы привязанные к нишам."""
    __tablename__ = "niche_groups"

    id = db.Column(db.Integer, primary_key=True)
    niche = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(300), nullable=True)        # человекочитаемое название
    members_count = db.Column(db.Integer, nullable=True)    # из TGStat
    source = db.Column(db.String(20), default="manual")     # "manual" | "tgstat"
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "niche": self.niche,
            "username": self.username,
            "title": self.title or self.username,
            "members_count": self.members_count,
            "source": self.source,
            "active": self.active,
        }


class SearchTemplate(db.Model):
    """Шаблоны поиска — сохранённые наборы фильтров."""
    __tablename__ = "search_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    niche = db.Column(db.String(100), nullable=True)
    min_score = db.Column(db.Float, nullable=True)
    keyword_filter = db.Column(db.String(300), nullable=True)
    date_range_days = db.Column(db.Integer, nullable=True)   # последние N дней
    sort_by = db.Column(db.String(50), default="final_score")
    sort_order = db.Column(db.String(4), default="desc")
    extra_filters = db.Column(db.Text, nullable=True)         # JSON
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "niche": self.niche or "",
            "min_score": self.min_score,
            "keyword_filter": self.keyword_filter or "",
            "date_range_days": self.date_range_days,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order,
            "extra_filters": json.loads(self.extra_filters) if self.extra_filters else {},
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "used_count": self.used_count,
        }


class TGAuthSession(db.Model):
    """Статус Telegram авторизации."""
    __tablename__ = "tg_auth_sessions"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default="pending")
    # pending | code_sent | authorized | error
    phone_code_hash = db.Column(db.String(200), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    authorized_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "authorized_at": self.authorized_at.strftime("%Y-%m-%d %H:%M") if self.authorized_at else None,
        }
