"""
api/routes.py
"""
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app, session
import functools

from models import db
from models.lead import Lead, ScanJob
from services.exporter import export_csv, export_xlsx

api_bp = Blueprint("api", __name__, url_prefix="/api")


def api_login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_login"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


_SORT = {
    "final_score":    Lead.final_score,
    "intent_score":   Lead.intent_score,
    "activity_score": Lead.activity_score,
    "niche_score":    Lead.niche_score,
    "message_date":   Lead.message_date,
    "created_at":     Lead.created_at,
}


# ── POST /api/scan ──────────────────────────────────────────────────
@api_bp.route("/scan", methods=["POST"])
@api_login_required
def start_scan():
    data  = request.get_json(silent=True) or {}
    niche = (data.get("niche") or "").strip().lower()
    if not niche:
        return jsonify({"error": "Укажите нишу"}), 400

    from config import Config
    try:
        from models.settings import NicheGroup
        exists = NicheGroup.query.filter_by(niche=niche).first()
        if not exists and niche not in Config.NICHE_GROUPS:
            return jsonify({"error": f"Ниша «{niche}» не найдена. Добавьте её в Настройках."}), 400
    except Exception:
        if niche not in Config.NICHE_GROUPS:
            return jsonify({"error": f"Ниша «{niche}» не найдена."}), 400

    app        = current_app._get_current_object()
    user_login = session.get("user_login")  # захватываем до выхода из контекста запроса

    def _run():
        from parser.tg_parser import run_scan
        try:
            run_scan(niche, app, user_login)
        except Exception as exc:
            app.logger.error(f"Scan error [{niche}] user={user_login}: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "niche": niche}), 202


# ── GET /api/scan/<id> ──────────────────────────────────────────────
@api_bp.route("/scan/<scan_id>", methods=["GET"])
@api_login_required
def scan_status(scan_id: str):
    job = db.session.get(ScanJob, scan_id)
    if not job:
        return jsonify({"error": "Скан не найден"}), 404
    return jsonify(job.to_dict())


# ── GET /api/leads ──────────────────────────────────────────────────
@api_bp.route("/leads", methods=["GET"])
@api_login_required
def get_leads():
    q = db.session.query(Lead)

    niche = request.args.get("niche", "").strip()
    if niche:
        q = q.filter(Lead.niche.ilike(f"%{niche}%"))

    min_score = request.args.get("min_score", type=float)
    if min_score is not None:
        q = q.filter(Lead.final_score >= min_score)

    max_score = request.args.get("max_score", type=float)
    if max_score is not None:
        q = q.filter(Lead.final_score <= max_score)

    keyword = request.args.get("keyword", "").strip()
    if keyword:
        q = q.filter(Lead.message_text.ilike(f"%{keyword}%"))

    date_from = request.args.get("date_from", "").strip()
    if date_from:
        try:
            q = q.filter(Lead.message_date >= datetime.fromisoformat(date_from))
        except ValueError:
            pass

    date_to = request.args.get("date_to", "").strip()
    if date_to:
        try:
            q = q.filter(Lead.message_date <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    chat = request.args.get("chat", "").strip()
    if chat:
        q = q.filter(Lead.chat_username.ilike(f"%{chat}%"))

    sort_by  = request.args.get("sort", "final_score")
    order    = request.args.get("order", "desc")
    sort_col = _SORT.get(sort_by, Lead.final_score)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    page     = max(1, request.args.get("page", 1, type=int))
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    total    = q.count()
    leads    = q.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    max(1, (total + per_page - 1) // per_page),
        "leads":    [l.to_dict() for l in leads],
    })


# ── GET /api/export ─────────────────────────────────────────────────
@api_bp.route("/export", methods=["GET"])
@api_login_required
def export_leads():
    fmt = request.args.get("format", "csv").lower()
    if fmt not in ("csv", "xlsx"):
        return jsonify({"error": "Формат: csv или xlsx"}), 400

    q = db.session.query(Lead)

    niche = request.args.get("niche", "")
    if niche:
        q = q.filter(Lead.niche.ilike(f"%{niche}%"))

    min_score = request.args.get("min_score", type=float)
    if min_score is not None:
        q = q.filter(Lead.final_score >= min_score)

    keyword = request.args.get("keyword", "")
    if keyword:
        q = q.filter(Lead.message_text.ilike(f"%{keyword}%"))

    date_from = request.args.get("date_from", "")
    if date_from:
        try:
            q = q.filter(Lead.message_date >= datetime.fromisoformat(date_from))
        except ValueError:
            pass

    date_to = request.args.get("date_to", "")
    if date_to:
        try:
            q = q.filter(Lead.message_date <= datetime.fromisoformat(date_to))
        except ValueError:
            pass

    q     = q.order_by(Lead.final_score.desc())
    leads = [l.to_dict() for l in q.all()]
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")

    if fmt == "csv":
        return send_file(
            export_csv(leads), mimetype="text/csv; charset=utf-8",
            as_attachment=True, download_name=f"leads_{ts}.csv",
        )
    return send_file(
        export_xlsx(leads),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=f"leads_{ts}.xlsx",
    )


# ── GET /api/stats ──────────────────────────────────────────────────
@api_bp.route("/stats", methods=["GET"])
@api_login_required
def stats():
    from sqlalchemy import func
    rows = (
        db.session.query(Lead.niche, func.count(Lead.id), func.avg(Lead.final_score))
        .group_by(Lead.niche).all()
    )
    return jsonify([
        {"niche": r[0], "total": r[1], "avg_score": round(r[2] or 0, 1)}
        for r in rows
    ])
