"""
parser/tg_parser.py
Парсинг сообщений из Telegram-групп через Telethon.
Работает синхронно (asyncio.run) для совместимости с Flask.
"""
import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
)
from telethon.tl.types import MessageService

from config import Config
from models import db
from models.lead import Lead, ScanJob
from services.lead_detector import is_lead
from services.scorer import score_lead


def _get_groups_for_niche(niche: str) -> list[str]:
    """
    Возвращает список username групп для ниши.
    Приоритет: активные записи из БД → config.py.
    """
    try:
        from models.settings import NicheGroup
        groups = NicheGroup.query.filter_by(niche=niche.lower(), active=True).all()
        if groups:
            return [g.username for g in groups]
    except Exception:
        pass

    # Fallback
    return Config.NICHE_GROUPS.get(niche.lower(), [])


def run_scan(niche: str, app) -> str:
    """
    Точка входа для Flask: запускает скан синхронно.
    Возвращает scan_id.
    """
    scan_id = str(uuid.uuid4())

    with app.app_context():
        job = ScanJob(id=scan_id, niche=niche, status="running")
        db.session.add(job)
        db.session.commit()

    try:
        asyncio.run(_scan_async(niche, scan_id, app))
    except Exception as exc:
        with app.app_context():
            job = db.session.get(ScanJob, scan_id)
            if job:
                job.status = "error"
                job.error_message = str(exc)
                job.finished_at = datetime.utcnow()
                db.session.commit()
        raise

    return scan_id


async def _scan_async(niche: str, scan_id: str, app) -> None:
    """Основная async-логика парсинга."""
    with app.app_context():
        groups = _get_groups_for_niche(niche)

    if not groups:
        raise ValueError(f"Нет групп для ниши: {niche!r}. Добавьте группы в настройках.")

    client = TelegramClient(
        Config.TG_SESSION_NAME,
        Config.TG_API_ID,
        Config.TG_API_HASH,
    )

    leads_found = 0
    groups_scanned = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=Config.PARSE_DAYS_BACK)

    async with client:
        await client.start(phone=Config.TG_PHONE)

        for group_username in groups:
            try:
                entity = await client.get_entity(group_username)
                chat_title = getattr(entity, "title", group_username)

                # Собираем все сообщения группы за период
                raw_messages: list[dict] = []
                user_msg_count: dict[int, int] = defaultdict(int)

                async for msg in client.iter_messages(
                    entity,
                    limit=Config.PARSE_LIMIT_PER_GROUP,
                    offset_date=None,
                    reverse=False,
                ):
                    if isinstance(msg, MessageService):
                        continue
                    if not msg.text:
                        continue
                    if msg.date.replace(tzinfo=timezone.utc) < cutoff:
                        break

                    sender_id = msg.sender_id
                    if sender_id:
                        user_msg_count[sender_id] += 1

                    raw_messages.append({
                        "message_id": msg.id,
                        "text": msg.text,
                        "date": msg.date,
                        "sender_id": sender_id,
                        "chat_title": chat_title,
                        "chat_username": group_username,
                    })

                # Обогащаем данными пользователей и сохраняем лиды
                for raw in raw_messages:
                    with app.app_context():
                        ok, keywords = is_lead(raw["text"])
                    if not ok:
                        continue

                    sender_id = raw["sender_id"]
                    username = first_name = last_name = None

                    if sender_id:
                        try:
                            sender = await client.get_entity(sender_id)
                            username = getattr(sender, "username", None)
                            first_name = getattr(sender, "first_name", None)
                            last_name = getattr(sender, "last_name", None)
                        except Exception:
                            pass

                    msg_count = user_msg_count.get(sender_id, 1)
                    scores = score_lead(
                        text=raw["text"],
                        matched_keywords=keywords,
                        niche=niche,
                        chat_username=group_username,
                        user_message_count=msg_count,
                    )

                    with app.app_context():
                        # Дедупликация: один и тот же message_id в той же группе
                        exists = db.session.query(Lead).filter_by(
                            message_id=raw["message_id"],
                            chat_username=group_username,
                        ).first()
                        if exists:
                            continue

                        lead = Lead(
                            username=username,
                            user_id=sender_id,
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
                        db.session.commit()
                        leads_found += 1

                groups_scanned += 1

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
                continue
            except (ChannelPrivateError, UsernameNotOccupiedError, UsernameInvalidError):
                continue
            except Exception:
                continue

    # Обновляем статус скана
    with app.app_context():
        job = db.session.get(ScanJob, scan_id)
        if job:
            job.status = "done"
            job.leads_found = leads_found
            job.groups_scanned = groups_scanned
            job.finished_at = datetime.utcnow()
            db.session.commit()
