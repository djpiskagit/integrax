"""
api/settings_routes.py
API для управления настройками: keywords, groups, templates, tg-auth, tgstat.
"""
import json
from datetime import datetime

from flask import Blueprint, request, jsonify

from models import db
from models.settings import Keyword, NicheGroup, SearchTemplate, TGAuthSession

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


# ════════════════════════════════════════════════
# KEYWORDS
# ════════════════════════════════════════════════

@settings_bp.route("/keywords", methods=["GET"])
def get_keywords():
    """Возвращает все keywords, сгруппированные по kind."""
    keywords = Keyword.query.order_by(Keyword.kind, Keyword.word).all()
    return jsonify({
        "intent": [k.to_dict() for k in keywords if k.kind == "intent"],
        "negative": [k.to_dict() for k in keywords if k.kind == "negative"],
    })


@settings_bp.route("/keywords", methods=["POST"])
def add_keyword():
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip().lower()
    kind = data.get("kind", "intent")

    if not word:
        return jsonify({"error": "Слово не указано"}), 400
    if kind not in ("intent", "negative"):
        return jsonify({"error": "kind должен быть intent или negative"}), 400

    if Keyword.query.filter_by(word=word).first():
        return jsonify({"error": "Слово уже существует"}), 409

    kw = Keyword(word=word, kind=kind)
    db.session.add(kw)
    db.session.commit()
    return jsonify(kw.to_dict()), 201


@settings_bp.route("/keywords/<int:kid>", methods=["DELETE"])
def delete_keyword(kid: int):
    kw = db.session.get(Keyword, kid)
    if not kw:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(kw)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/keywords/bulk", methods=["POST"])
def bulk_keywords():
    """Массовое добавление: {'kind': 'intent', 'words': ['слово1', 'слово2']}"""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "intent")
    words = [w.strip().lower() for w in data.get("words", []) if w.strip()]

    if not words:
        return jsonify({"error": "Список слов пуст"}), 400

    added = 0
    skipped = 0
    for word in words:
        if Keyword.query.filter_by(word=word).first():
            skipped += 1
            continue
        db.session.add(Keyword(word=word, kind=kind))
        added += 1

    db.session.commit()
    return jsonify({"added": added, "skipped": skipped})


@settings_bp.route("/keywords/sync-config", methods=["POST"])
def sync_keywords_from_config():
    """Синхронизирует ключевые слова из config.py в БД."""
    from config import Config
    added = 0
    for word in Config.INTENT_KEYWORDS:
        if not Keyword.query.filter_by(word=word).first():
            db.session.add(Keyword(word=word, kind="intent"))
            added += 1
    for word in Config.NEGATIVE_KEYWORDS:
        if not Keyword.query.filter_by(word=word).first():
            db.session.add(Keyword(word=word, kind="negative"))
            added += 1
    db.session.commit()
    return jsonify({"added": added})


# ════════════════════════════════════════════════
# GROUPS
# ════════════════════════════════════════════════

@settings_bp.route("/groups", methods=["GET"])
def get_groups():
    niche = request.args.get("niche", "").strip()
    q = NicheGroup.query
    if niche:
        q = q.filter_by(niche=niche)
    groups = q.order_by(NicheGroup.niche, NicheGroup.username).all()

    # Группируем по нишам
    result: dict[str, list] = {}
    for g in groups:
        result.setdefault(g.niche, []).append(g.to_dict())
    return jsonify(result)


@settings_bp.route("/groups", methods=["POST"])
def add_group():
    data = request.get_json(silent=True) or {}
    niche = (data.get("niche") or "").strip().lower()
    username = (data.get("username") or "").strip().lstrip("@").lower()

    if not niche or not username:
        return jsonify({"error": "niche и username обязательны"}), 400

    if NicheGroup.query.filter_by(niche=niche, username=username).first():
        return jsonify({"error": "Группа уже добавлена"}), 409

    g = NicheGroup(
        niche=niche,
        username=username,
        title=data.get("title"),
        members_count=data.get("members_count"),
        source=data.get("source", "manual"),
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201


@settings_bp.route("/groups/<int:gid>", methods=["PATCH"])
def update_group(gid: int):
    g = db.session.get(NicheGroup, gid)
    if not g:
        return jsonify({"error": "Не найдено"}), 404
    data = request.get_json(silent=True) or {}
    if "active" in data:
        g.active = bool(data["active"])
    if "title" in data:
        g.title = data["title"]
    db.session.commit()
    return jsonify(g.to_dict())


@settings_bp.route("/groups/<int:gid>", methods=["DELETE"])
def delete_group(gid: int):
    g = db.session.get(NicheGroup, gid)
    if not g:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(g)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/groups/sync-config", methods=["POST"])
def sync_groups_from_config():
    """Импортирует группы из config.py в БД."""
    from config import Config
    added = 0
    for niche, usernames in Config.NICHE_GROUPS.items():
        for username in usernames:
            if not NicheGroup.query.filter_by(niche=niche, username=username).first():
                db.session.add(NicheGroup(niche=niche, username=username, source="config"))
                added += 1
    db.session.commit()
    return jsonify({"added": added})


@settings_bp.route("/groups/niches", methods=["GET"])
def get_niches():
    """Возвращает список уникальных ниш."""
    from sqlalchemy import func
    rows = db.session.query(NicheGroup.niche, func.count(NicheGroup.id)).group_by(NicheGroup.niche).all()
    return jsonify([{"niche": r[0], "count": r[1]} for r in rows])


# ════════════════════════════════════════════════
# TGSTAT
# ════════════════════════════════════════════════

@settings_bp.route("/tgstat/search", methods=["GET"])
def tgstat_search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Запрос не указан"}), 400

    try:
        from services.tgstat_api import search_channels, tgstat_available
        if not tgstat_available():
            return jsonify({"error": "TGSTAT_TOKEN не задан в .env"}), 503

        limit = request.args.get("limit", 20, type=int)
        results = search_channels(query, limit=limit)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/tgstat/add", methods=["POST"])
def tgstat_add_group():
    """Добавляет группу из результатов TGStat в нишу."""
    data = request.get_json(silent=True) or {}
    niche = (data.get("niche") or "").strip().lower()
    username = (data.get("username") or "").strip().lstrip("@")

    if not niche or not username:
        return jsonify({"error": "niche и username обязательны"}), 400

    if NicheGroup.query.filter_by(niche=niche, username=username).first():
        return jsonify({"error": "Группа уже добавлена"}), 409

    g = NicheGroup(
        niche=niche,
        username=username,
        title=data.get("title"),
        members_count=data.get("members_count"),
        source="tgstat",
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201


@settings_bp.route("/tgstat/available", methods=["GET"])
def tgstat_check():
    from services.tgstat_api import tgstat_available
    return jsonify({"available": tgstat_available()})


# ════════════════════════════════════════════════
# TEMPLATES
# ════════════════════════════════════════════════

@settings_bp.route("/templates", methods=["GET"])
def get_templates():
    templates = SearchTemplate.query.order_by(SearchTemplate.used_count.desc(), SearchTemplate.created_at.desc()).all()
    return jsonify([t.to_dict() for t in templates])


@settings_bp.route("/templates", methods=["POST"])
def create_template():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название обязательно"}), 400

    t = SearchTemplate(
        name=name,
        description=data.get("description"),
        niche=data.get("niche"),
        min_score=data.get("min_score"),
        keyword_filter=data.get("keyword_filter"),
        date_range_days=data.get("date_range_days"),
        sort_by=data.get("sort_by", "final_score"),
        sort_order=data.get("sort_order", "desc"),
        extra_filters=json.dumps(data.get("extra_filters", {})) if data.get("extra_filters") else None,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@settings_bp.route("/templates/<int:tid>", methods=["PATCH"])
def update_template(tid: int):
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    data = request.get_json(silent=True) or {}
    for field in ("name", "description", "niche", "min_score", "keyword_filter", "date_range_days", "sort_by", "sort_order"):
        if field in data:
            setattr(t, field, data[field])
    if "extra_filters" in data:
        t.extra_filters = json.dumps(data["extra_filters"])
    db.session.commit()
    return jsonify(t.to_dict())


@settings_bp.route("/templates/<int:tid>", methods=["DELETE"])
def delete_template(tid: int):
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/templates/<int:tid>/use", methods=["POST"])
def use_template(tid: int):
    """Инкрементирует счётчик использования и возвращает фильтры."""
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    t.used_count += 1
    db.session.commit()
    return jsonify(t.to_dict())


# ════════════════════════════════════════════════
# TELEGRAM AUTH
# ════════════════════════════════════════════════

@settings_bp.route("/tg/status", methods=["GET"])
def tg_status():
    """Проверяет статус авторизации Telegram."""
    try:
        from services.tg_auth import is_authorized, get_me
        if is_authorized():
            me = get_me()
            return jsonify({"authorized": True, "user": me})
        return jsonify({"authorized": False})
    except Exception as e:
        return jsonify({"authorized": False, "error": str(e)})


@settings_bp.route("/tg/send-code", methods=["POST"])
def tg_send_code():
    """Отправляет SMS-код на телефон."""
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Телефон не указан"}), 400

    try:
        from services.tg_auth import send_code
        phone_code_hash = send_code(phone)

        # Сохраняем в БД
        session = TGAuthSession(phone=phone, status="code_sent", phone_code_hash=phone_code_hash)
        db.session.add(session)
        db.session.commit()

        return jsonify({"ok": True, "phone_code_hash": phone_code_hash, "session_id": session.id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/tg/sign-in", methods=["POST"])
def tg_sign_in():
    """Подтверждает код и авторизует."""
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    code = (data.get("code") or "").strip()
    phone_code_hash = (data.get("phone_code_hash") or "").strip()
    password = data.get("password")  # для 2FA

    if not phone or not code or not phone_code_hash:
        return jsonify({"error": "phone, code, phone_code_hash обязательны"}), 400

    try:
        from services.tg_auth import sign_in
        user = sign_in(phone, code, phone_code_hash, password)

        # Обновляем статус
        session = TGAuthSession.query.filter_by(phone=phone).order_by(TGAuthSession.created_at.desc()).first()
        if session:
            session.status = "authorized"
            session.authorized_at = datetime.utcnow()
            db.session.commit()

        return jsonify({"ok": True, "user": user})
    except Exception as e:
        err = str(e)
        if "password" in err.lower() or "2fa" in err.lower() or "SessionPasswordNeeded" in err:
            return jsonify({"error": "2fa_required"}), 401
        if "code" in err.lower() or "invalid" in err.lower():
            return jsonify({"error": "Неверный код"}), 400
        return jsonify({"error": err}), 500


@settings_bp.route("/tg/logout", methods=["POST"])
def tg_logout():
    try:
        from services.tg_auth import logout
        logout()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
