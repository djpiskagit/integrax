"""
api/settings_routes.py
"""
import json
import io
import functools
from datetime import datetime

from flask import Blueprint, request, jsonify, send_file, session

from models import db
from models.settings import (
    AppSettings, TGAuthSession, Keyword, NicheGroup, SearchTemplate,
)

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


def api_login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_login"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════

@settings_bp.route("/config", methods=["GET"])
@api_login_required
def get_config():
    return jsonify({
        "tg_api_id":        AppSettings.get("tg_api_id", ""),
        "tg_api_hash_set":  bool(AppSettings.get("tg_api_hash", "")),
        "tg_phone":         AppSettings.get("tg_phone", ""),
        "tgstat_token_set": bool(AppSettings.get("tgstat_token", "")),
        "parse_days_back":  AppSettings.get("parse_days_back", 30),
        "parse_limit":      AppSettings.get("parse_limit", 200),
    })


@settings_bp.route("/config", methods=["POST"])
@api_login_required
def save_config():
    data = request.get_json(silent=True) or {}
    for f in ["tg_api_id", "tg_phone", "parse_days_back", "parse_limit"]:
        if data.get(f) not in (None, ""):
            AppSettings.set(f, data[f])
    if data.get("tg_api_hash"):
        AppSettings.set("tg_api_hash", data["tg_api_hash"])
    if data.get("tgstat_token"):
        AppSettings.set("tgstat_token", data["tgstat_token"])
    return jsonify({"ok": True})


# ════════════════════════════════════════════════
# TELEGRAM AUTH
# ════════════════════════════════════════════════

@settings_bp.route("/tg/status", methods=["GET"])
@api_login_required
def tg_status():
    try:
        from services.tg_auth import is_authorized, get_me
        if is_authorized():
            return jsonify({"authorized": True, "user": get_me()})
        return jsonify({"authorized": False})
    except Exception as e:
        return jsonify({"authorized": False, "error": str(e)})


@settings_bp.route("/tg/send-code", methods=["POST"])
@api_login_required
def tg_send_code():
    data  = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return jsonify({"error": "Телефон не указан"}), 400
    try:
        from services.tg_auth import send_code
        phone_code_hash = send_code(phone)
        sess = TGAuthSession(
            phone=phone,
            phone_code_hash=phone_code_hash,
            status="code_sent",
        )
        db.session.add(sess)
        db.session.commit()
        return jsonify({"ok": True, "phone_code_hash": phone_code_hash})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/tg/sign-in", methods=["POST"])
@api_login_required
def tg_sign_in():
    data            = request.get_json(silent=True) or {}
    phone           = (data.get("phone")           or "").strip()
    code            = (data.get("code")            or "").strip()
    phone_code_hash = (data.get("phone_code_hash") or "").strip()
    password        = data.get("password")

    if not phone or not code or not phone_code_hash:
        return jsonify({"error": "phone, code, phone_code_hash обязательны"}), 400

    try:
        from services.tg_auth import sign_in
        user = sign_in(phone, code, phone_code_hash, password)
        sess = TGAuthSession.query.order_by(TGAuthSession.id.desc()).first()
        if sess:
            sess.status        = "authorized"
            sess.authorized_at = datetime.utcnow()
            db.session.commit()
        return jsonify({"ok": True, "user": user})
    except Exception as e:
        err = str(e)
        if "SessionPasswordNeeded" in err:
            return jsonify({"error": "2fa_required"}), 401
        if "PhoneCodeInvalid" in err:
            return jsonify({"error": "Неверный код"}), 400
        if "PhoneCodeExpired" in err:
            return jsonify({"error": "Код устарел, запросите новый"}), 400
        return jsonify({"error": err}), 500


@settings_bp.route("/tg/logout", methods=["POST"])
@api_login_required
def tg_logout():
    try:
        from services.tg_auth import logout
        logout()
        sess = TGAuthSession.query.order_by(TGAuthSession.id.desc()).first()
        if sess:
            sess.status        = "pending"
            sess.authorized_at = None
            db.session.commit()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════
# KEYWORDS
# ════════════════════════════════════════════════

@settings_bp.route("/keywords", methods=["GET"])
@api_login_required
def get_keywords():
    kws = Keyword.query.order_by(Keyword.kind, Keyword.word).all()
    return jsonify({
        "intent":   [k.to_dict() for k in kws if k.kind == "intent"],
        "negative": [k.to_dict() for k in kws if k.kind == "negative"],
    })


@settings_bp.route("/keywords", methods=["POST"])
@api_login_required
def add_keyword():
    data = request.get_json(silent=True) or {}
    word = (data.get("word") or "").strip().lower()
    kind = data.get("kind", "intent")
    if not word:
        return jsonify({"error": "Слово не указано"}), 400
    if kind not in ("intent", "negative"):
        return jsonify({"error": "kind: intent или negative"}), 400
    if Keyword.query.filter_by(word=word).first():
        return jsonify({"error": "Уже существует"}), 409
    kw = Keyword(word=word, kind=kind)
    db.session.add(kw)
    db.session.commit()
    return jsonify(kw.to_dict()), 201


@settings_bp.route("/keywords/<int:kid>", methods=["DELETE"])
@api_login_required
def delete_keyword(kid):
    kw = db.session.get(Keyword, kid)
    if not kw:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(kw)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/keywords/bulk", methods=["POST"])
@api_login_required
def bulk_keywords():
    data  = request.get_json(silent=True) or {}
    kind  = data.get("kind", "intent")
    words = [w.strip().lower() for w in data.get("words", []) if w.strip()]
    if not words:
        return jsonify({"error": "Список пуст"}), 400
    added = skipped = 0
    for word in words:
        if Keyword.query.filter_by(word=word).first():
            skipped += 1; continue
        db.session.add(Keyword(word=word, kind=kind))
        added += 1
    db.session.commit()
    return jsonify({"added": added, "skipped": skipped})


@settings_bp.route("/keywords/sync-config", methods=["POST"])
@api_login_required
def sync_keywords():
    from config import Config
    added = 0
    for w in Config.INTENT_KEYWORDS:
        if not Keyword.query.filter_by(word=w).first():
            db.session.add(Keyword(word=w, kind="intent")); added += 1
    for w in Config.NEGATIVE_KEYWORDS:
        if not Keyword.query.filter_by(word=w).first():
            db.session.add(Keyword(word=w, kind="negative")); added += 1
    db.session.commit()
    return jsonify({"added": added})


# ════════════════════════════════════════════════
# GROUPS / NICHES
# ════════════════════════════════════════════════

@settings_bp.route("/groups", methods=["GET"])
@api_login_required
def get_groups():
    niche = request.args.get("niche", "").strip()
    q = NicheGroup.query
    if niche:
        q = q.filter_by(niche=niche)
    groups = q.order_by(NicheGroup.niche, NicheGroup.username).all()
    result: dict = {}
    for g in groups:
        result.setdefault(g.niche, []).append(g.to_dict())
    return jsonify(result)


@settings_bp.route("/groups", methods=["POST"])
@api_login_required
def add_group():
    data     = request.get_json(silent=True) or {}
    niche    = (data.get("niche")    or "").strip().lower()
    username = (data.get("username") or "").strip().lstrip("@").lower()
    if not niche or not username:
        return jsonify({"error": "niche и username обязательны"}), 400
    if NicheGroup.query.filter_by(niche=niche, username=username).first():
        return jsonify({"error": "Уже добавлена"}), 409
    g = NicheGroup(
        niche=niche, username=username,
        title=data.get("title"),
        members_count=data.get("members_count"),
        source=data.get("source", "manual"),
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201


@settings_bp.route("/groups/<int:gid>", methods=["PATCH"])
@api_login_required
def update_group(gid):
    g = db.session.get(NicheGroup, gid)
    if not g:
        return jsonify({"error": "Не найдено"}), 404
    data = request.get_json(silent=True) or {}
    if "active" in data: g.active = bool(data["active"])
    if "title"  in data: g.title  = data["title"]
    db.session.commit()
    return jsonify(g.to_dict())


@settings_bp.route("/groups/<int:gid>", methods=["DELETE"])
@api_login_required
def delete_group(gid):
    g = db.session.get(NicheGroup, gid)
    if not g:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(g)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/groups/niches", methods=["GET"])
@api_login_required
def get_niches():
    from sqlalchemy import func
    rows = (
        db.session.query(NicheGroup.niche, func.count(NicheGroup.id))
        .group_by(NicheGroup.niche)
        .order_by(NicheGroup.niche)
        .all()
    )
    return jsonify([{"niche": r[0], "count": r[1]} for r in rows])


@settings_bp.route("/groups/sync-config", methods=["POST"])
@api_login_required
def sync_groups():
    from config import Config
    added = 0
    for niche, usernames in Config.NICHE_GROUPS.items():
        for username in usernames:
            if not NicheGroup.query.filter_by(niche=niche, username=username).first():
                db.session.add(NicheGroup(niche=niche, username=username, source="config"))
                added += 1
    db.session.commit()
    return jsonify({"added": added})


# ════════════════════════════════════════════════
# TGSTAT
# ════════════════════════════════════════════════

@settings_bp.route("/tgstat/available", methods=["GET"])
@api_login_required
def tgstat_available():
    token = AppSettings.get("tgstat_token", "")
    return jsonify({"available": bool(token)})


@settings_bp.route("/tgstat/search", methods=["GET"])
@api_login_required
def tgstat_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Запрос не указан"}), 400
    token = AppSettings.get("tgstat_token", "")
    if not token:
        return jsonify({"error": "TGSTAT_TOKEN не задан в настройках"}), 503
    try:
        from services.tgstat_api import search_channels
        results = search_channels(q, limit=request.args.get("limit", 20, type=int), token=token)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/tgstat/add", methods=["POST"])
@api_login_required
def tgstat_add():
    data     = request.get_json(silent=True) or {}
    niche    = (data.get("niche")    or "").strip().lower()
    username = (data.get("username") or "").strip().lstrip("@")
    if not niche or not username:
        return jsonify({"error": "niche и username обязательны"}), 400
    if NicheGroup.query.filter_by(niche=niche, username=username).first():
        return jsonify({"error": "Уже добавлена"}), 409
    g = NicheGroup(
        niche=niche, username=username,
        title=data.get("title"),
        members_count=data.get("members_count"),
        source="tgstat",
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201


# ════════════════════════════════════════════════
# TEMPLATES
# ════════════════════════════════════════════════

@settings_bp.route("/templates", methods=["GET"])
@api_login_required
def get_templates():
    tpls = SearchTemplate.query.order_by(
        SearchTemplate.used_count.desc(), SearchTemplate.created_at.desc()
    ).all()
    return jsonify([t.to_dict() for t in tpls])


@settings_bp.route("/templates", methods=["POST"])
@api_login_required
def create_template():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название обязательно"}), 400
    t = SearchTemplate(
        name=name,
        description=data.get("description"),
        niche=data.get("niche") or None,
        min_score=data.get("min_score"),
        keyword_filter=data.get("keyword_filter") or None,
        date_range_days=data.get("date_range_days"),
        sort_by=data.get("sort_by", "final_score"),
        sort_order=data.get("sort_order", "desc"),
        extra_filters=json.dumps(data.get("extra_filters", {})),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@settings_bp.route("/templates/<int:tid>", methods=["PATCH"])
@api_login_required
def update_template(tid):
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    data = request.get_json(silent=True) or {}
    for f in ("name", "description", "niche", "min_score", "keyword_filter",
              "date_range_days", "sort_by", "sort_order"):
        if f in data:
            setattr(t, f, data[f])
    if "extra_filters" in data:
        t.extra_filters = json.dumps(data["extra_filters"])
    db.session.commit()
    return jsonify(t.to_dict())


@settings_bp.route("/templates/<int:tid>", methods=["DELETE"])
@api_login_required
def delete_template(tid):
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


@settings_bp.route("/templates/<int:tid>/use", methods=["POST"])
@api_login_required
def use_template(tid):
    t = db.session.get(SearchTemplate, tid)
    if not t:
        return jsonify({"error": "Не найдено"}), 404
    t.used_count = (t.used_count or 0) + 1
    db.session.commit()
    return jsonify(t.to_dict())


@settings_bp.route("/templates/export", methods=["GET"])
@api_login_required
def export_templates():
    tpls = SearchTemplate.query.order_by(SearchTemplate.id).all()
    payload = json.dumps([t.to_dict() for t in tpls], ensure_ascii=False, indent=2)
    buf = io.BytesIO(payload.encode("utf-8"))
    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(buf, mimetype="application/json",
                     as_attachment=True, download_name=f"templates_{ts}.json")


@settings_bp.route("/templates/import", methods=["POST"])
@api_login_required
def import_templates():
    if "file" not in request.files:
        return jsonify({"error": "Файл не передан"}), 400
    try:
        raw   = request.files["file"].read().decode("utf-8")
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("Ожидается массив JSON")
    except Exception as e:
        return jsonify({"error": f"Ошибка чтения: {e}"}), 400

    added = skipped = 0
    for item in items:
        name = (item.get("name") or "").strip()
        if not name or SearchTemplate.query.filter_by(name=name).first():
            skipped += 1; continue
        t = SearchTemplate(
            name=name,
            description=item.get("description"),
            niche=item.get("niche") or None,
            min_score=item.get("min_score"),
            keyword_filter=item.get("keyword_filter") or None,
            date_range_days=item.get("date_range_days"),
            sort_by=item.get("sort_by", "final_score"),
            sort_order=item.get("sort_order", "desc"),
            extra_filters=json.dumps(item.get("extra_filters", {})),
        )
        db.session.add(t)
        added += 1
    db.session.commit()
    return jsonify({"added": added, "skipped": skipped})


# ════════════════════════════════════════════════
# PROXY
# ════════════════════════════════════════════════

@settings_bp.route("/proxy", methods=["GET"])
@api_login_required
def get_proxy():
    return jsonify({
        "proxy_type":     AppSettings.get("proxy_type",   ""),
        "proxy_host":     AppSettings.get("proxy_host",   ""),
        "proxy_port":     AppSettings.get("proxy_port",   ""),
        "proxy_user":     AppSettings.get("proxy_user",   ""),
        "proxy_secret":   AppSettings.get("proxy_secret", ""),
        "proxy_pass_set": bool(AppSettings.get("proxy_pass", "")),
    })


@settings_bp.route("/proxy", methods=["POST"])
@api_login_required
def save_proxy():
    data = request.get_json(silent=True) or {}
    for f in ["proxy_type", "proxy_host", "proxy_port", "proxy_user", "proxy_secret"]:
        AppSettings.set(f, str(data.get(f, "")).strip())
    if data.get("proxy_pass") not in (None, ""):
        AppSettings.set("proxy_pass", str(data["proxy_pass"]).strip())
    return jsonify({"ok": True})


@settings_bp.route("/proxy/test", methods=["POST"])
@api_login_required
def proxy_test():
    from services.tg_auth import test_proxy as _test
    result = _test()
    return jsonify(result), (200 if result["ok"] else 503)
