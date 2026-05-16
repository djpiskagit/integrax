"""
app.py — точка входа.

Каждый пользователь получает свою изолированную БД:
  data/users/<login>/db.sqlite
  data/users/<login>/session.session  (TG-сессия)

Объект называется `application` — требование хостинга (Passenger/gunicorn).
"""
import functools
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g

from config import Config
from models import db

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = Path(BASE_DIR) / "data" / "users"


# ── Путь к БД конкретного пользователя ──────────────────────────────
def get_user_db_path(login: str) -> Path:
    d = DATA_ROOT / login
    d.mkdir(parents=True, exist_ok=True)
    return d / "db.sqlite"


# ── Декораторы ───────────────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_login"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def api_login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_login"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(days=14)

    db.init_app(app)

    from api.routes import api_bp
    from api.settings_routes import settings_bp
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)

    # Создаём таблицы в дефолтной БД при старте
    with app.app_context():
        _import_models()
        db.create_all()

    # ── Переключение БД перед каждым запросом ────────────────────────
    @app.before_request
    def switch_db():
        """
        Переключает SQLAlchemy на БД текущего пользователя.
        Если пользователь не залогинен — ничего не делаем.
        """
        login = session.get("user_login")
        if not login:
            return

        target_uri = f"sqlite:///{get_user_db_path(login)}"

        # Переключаем только если URI изменился
        if app.config.get("SQLALCHEMY_DATABASE_URI") != target_uri:
            app.config["SQLALCHEMY_DATABASE_URI"] = target_uri
            with app.app_context():
                db.engine.dispose()

        # Убеждаемся что таблицы созданы в БД пользователя
        with app.app_context():
            _import_models()
            db.create_all()

    # ── Вход ─────────────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login_page():
        if session.get("user_login"):
            return redirect(url_for("index"))

        error     = None
        login_val = ""

        if request.method == "POST":
            from users import check_credentials
            login_val = request.form.get("login", "").strip()
            password  = request.form.get("password", "")
            user = check_credentials(login_val, password)

            if user:
                login = user["login"]

                # Переключаем на БД этого пользователя ДО записи сессии
                target_uri = f"sqlite:///{get_user_db_path(login)}"
                app.config["SQLALCHEMY_DATABASE_URI"] = target_uri
                with app.app_context():
                    db.engine.dispose()
                    _import_models()
                    db.create_all()

                session.permanent        = True
                session["user_login"]    = login
                session["user_name"]     = user["name"]
                return redirect(url_for("index"))

            error = "Неверный логин или пароль"

        return render_template("login.html", error=error, login_val=login_val)

    # ── Выход ─────────────────────────────────────────────────────────
    @app.route("/logout")
    def logout():
        session.clear()
        # Возвращаем дефолтную БД
        app.config["SQLALCHEMY_DATABASE_URI"] = Config.SQLALCHEMY_DATABASE_URI
        with app.app_context():
            db.engine.dispose()
        return redirect(url_for("login_page"))

    # ── Страницы ──────────────────────────────────────────────────────
    @app.route("/")
    @login_required
    def index():
        return render_template("index.html", niches=_get_niches())

    @app.route("/leads")
    @login_required
    def leads_page():
        return render_template("leads.html", niches=_get_niches())

    @app.route("/settings")
    @login_required
    def settings_page():
        return render_template("settings.html")

    return app


def _import_models():
    """Импортирует модели чтобы db.create_all() их видел."""
    from models.lead import Lead, ScanJob                    # noqa
    from models.settings import (                            # noqa
        AppSettings, TGAuthSession, Keyword,
        NicheGroup, SearchTemplate, TGStatCache,
    )


def _get_niches() -> list[str]:
    """Возвращает список ниш из БД текущего пользователя."""
    try:
        from models.settings import NicheGroup
        rows = (
            NicheGroup.query
            .with_entities(NicheGroup.niche)
            .distinct()
            .order_by(NicheGroup.niche)
            .all()
        )
        niches = [r.niche for r in rows]
        if niches:
            return niches
    except Exception:
        pass
    return list(Config.NICHE_GROUPS.keys())


# Объект `application` нужен для Passenger/gunicorn
application = create_app()
app         = application   # псевдоним для обратной совместимости

if __name__ == "__main__":
    application.run(debug=False, host="0.0.0.0", port=5001)
