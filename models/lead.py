from datetime import datetime
from models import db


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.BigInteger, nullable=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)

    message_text = db.Column(db.Text, nullable=False)
    message_id = db.Column(db.BigInteger, nullable=True)
    chat_name = db.Column(db.String(255), nullable=False)
    chat_username = db.Column(db.String(255), nullable=True)
    message_date = db.Column(db.DateTime, nullable=False)

    niche = db.Column(db.String(100), nullable=False)
    niche_raw = db.Column(db.String(200), nullable=True)

    intent_score = db.Column(db.Float, default=0.0)
    activity_score = db.Column(db.Float, default=0.0)
    niche_score = db.Column(db.Float, default=0.0)
    final_score = db.Column(db.Float, default=0.0)

    matched_keywords = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scan_id = db.Column(db.String(36), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username or "—",
            "user_id": self.user_id,
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "display_name": self._display_name(),
            "message_text": self.message_text,
            "message_short": self.message_text[:120] + "…" if len(self.message_text) > 120 else self.message_text,
            "chat_name": self.chat_name,
            "chat_username": self.chat_username or "",
            "message_date": self.message_date.strftime("%Y-%m-%d %H:%M"),
            "niche": self.niche,
            "intent_score": round(self.intent_score, 1),
            "activity_score": round(self.activity_score, 1),
            "niche_score": round(self.niche_score, 1),
            "final_score": round(self.final_score, 1),
            "matched_keywords": self.matched_keywords or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "scan_id": self.scan_id or "",
        }

    def _display_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        if self.username:
            return f"@{self.username}" if not name else f"{name} (@{self.username})"
        return name or f"user_{self.user_id}"

    def __repr__(self):
        return f"<Lead id={self.id} score={self.final_score} niche={self.niche}>"


class ScanJob(db.Model):
    __tablename__ = "scan_jobs"

    id = db.Column(db.String(36), primary_key=True)
    niche = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default="running")
    leads_found = db.Column(db.Integer, default=0)
    groups_scanned = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "niche": self.niche,
            "status": self.status,
            "leads_found": self.leads_found,
            "groups_scanned": self.groups_scanned,
            "error_message": self.error_message,
            "started_at": self.started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else None,
        }
