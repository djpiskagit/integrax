"""
parser/tg_parser.py

Мульти-тенантность: принимает user_login, использует
data/users/<login>/session.session для TG-авторизации.
"""
import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError, FloodWaitError,
    UsernameNotOccupiedError, UsernameInvalidError,
)
from telethon.tl.types import MessageService

from config import Config
from models import db
from models.lead import Lead, ScanJob
from services.lead_detector import is_lead
from services.scorer import score_lead


def _get_session_name(user_login: str) -> str:
    """Путь к .session файлу пользователя."""
    user_dir = Path(f"data/users/{user_login}")
    user_dir.mkdir(parents=True, exist_ok=True)
    return str(user_dir / "session")


def _get_parse_settings() -> dict:
    from models.settings import AppSettings
    return {
        "api_id":    AppSettings.get("tg_api_id"),
        "api_hash":  AppSettings.get("tg_api_hash"),
        "days_back": int(AppSettings.get("parse_days_back") or Config.PARSE_DAYS_BACK),
        "limit":     int(AppSettings.get("parse_limit")     or Config.PARSE_LIMIT),
    }


def _get_groups_for_niche(niche: str) -> list[str]:
    try:
        from models.settings import NicheGroup
        groups = NicheGroup.query.filter_by(niche=niche.lower(), active=True).all()
        if groups:
            return [g.username for g in groups]
    except Exception:
        pass
    return Config.NICHE_GROUPS.get(niche.lower(), [])


def run_scan(niche: str, app, user_login: str) -> str:
    """
    Запускает скан от имени конкретного пользователя.
    user_login используется для выбора TG-сессии и БД.
    """
    scan_id = str(uuid.uuid4())
    with app.app_context():
        job = ScanJob(id=scan_id, niche=niche, status="running")
        db.session.add(job)
        db.session.commit()
    try:
        asyncio.run(_scan_async(niche, scan_id, app, user_login))
    except Exception as exc:
        with app.app_context():
            job = db.session.get(ScanJob, scan_id)
            if job:
                job.status        = "error"
                job.error_message = str(exc)[:500]
                job.finished_at   = datetime.utcnow()
                db.session.commit()
        raise
    return scan_id


async def _scan_async(niche: str, scan_id: str, app, user_login: str) -> None:
    with app.app_context():
        groups   = _get_groups_for_niche(niche)
        settings = _get_parse_settings()

    if not groups:
        raise ValueError(f"Нет групп для ниши «{niche}». Добавьте группы в Настройках.")

    api_id   = settings["api_id"]
    api_hash = settings["api_hash"]
    if not api_id or not api_hash:
        raise ValueError("TG_API_ID и TG_API_HASH не заданы. Настройте их в разделе Конфигурация.")

    # Используем session-файл конкретного пользователя
    session_name   = _get_session_name(user_login)
    client         = TelegramClient(session_name, int(api_id), str(api_hash))
    cutoff         = datetime.now(timezone.utc) - timedelta(days=settings["days_back"])
    leads_found    = 0
    groups_scanned = 0

    async with client:
        if not await client.is_user_authorized():
            raise ValueError("Telegram не авторизован. Войдите через Настройки → Telegram Auth.")

        for group_username in groups:
            try:
                entity     = await client.get_entity(group_username)
                chat_title = getattr(entity, "title", group_username)
                raw_messages:   list[dict]     = []
                user_msg_count: dict[int, int] = defaultdict(int)

                async for msg in client.iter_messages(entity, limit=settings["limit"]):
                    if isinstance(msg, MessageService):
                        continue
                    if not msg.text:
                        continue
                    msg_dt = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)
                    if msg_dt < cutoff:
                        break
                    if msg.sender_id:
                        user_msg_count[msg.sender_id] += 1
                    raw_messages.append({
                        "message_id":    msg.id,
                        "text":          msg.text,
                        "date":          msg.date,
                        "sender_id":     msg.sender_id,
                        "chat_title":    chat_title,
                        "chat_username": group_username,
                    })

                # Фильтруем лиды
                lead_candidates = []
                for raw in raw_messages:
                    with app.app_context():
                        ok, keywords = is_lead(raw["text"])
                    if not ok:
                        continue

                    sender_id = raw["sender_id"]
                    username = first_name = last_name = None
                    if sender_id:
                        try:
                            sender     = await client.get_entity(sender_id)
                            username   = getattr(sender, "username",   None)
                            first_name = getattr(sender, "first_name", None)
                            last_name  = getattr(sender, "last_name",  None)
                        except Exception:
                            pass

                    scores = score_lead(
                        text=raw["text"],
                        matched_keywords=keywords,
                        niche=niche,
                        chat_username=group_username,
                        user_message_count=user_msg_count.get(sender_id, 1),
                    )
                    lead_candidates.append((raw, keywords, username, first_name, last_name, scores))

                # Батчевое сохранение — один запрос для проверки дублей
                if lead_candidates:
                    with app.app_context():
                        existing_ids = {
                            row[0]
                            for row in db.session.query(Lead.message_id)
                            .filter(Lead.chat_username == group_username)
                            .all()
                        }
                        for raw, keywords, username, first_name, last_name, scores in lead_candidates:
                            if raw["message_id"] in existing_ids:
                                continue
                            lead = Lead(
                                username=username,
                                user_id=raw["sender_id"],
                                first_name=first_name,
                                last_name=last_name,
                                message_text=raw["text"],
                                message_id=raw["message_id"],
                                chat_name=raw["chat_title"],
                                chat_username=group_username,
                                message_date=raw["date"].replace(tzinfo=None),
                                niche=niche,
                                matched_keywords=json.dumps(keywords, ensure_ascii=False),
                                scan_id=scan_id,
                                **scores,
                            )
                            db.session.add(lead)
                            leads_found += 1
                        db.session.commit()

                groups_scanned += 1

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
            except (ChannelPrivateError, UsernameNotOccupiedError, UsernameInvalidError):
                continue
            except Exception as exc:
                with app.app_context():
                    app.logger.warning(f"[parser] {group_username}: {exc}")
                continue

    with app.app_context():
        job = db.session.get(ScanJob, scan_id)
        if job:
            job.status         = "done"
            job.leads_found    = leads_found
            job.groups_scanned = groups_scanned
            job.finished_at    = datetime.utcnow()
            db.session.commit()
