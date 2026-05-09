"""
app.py — точка входа Flask-приложения
"""
from flask import Flask, render_template, request, jsonify

from config import Config
from models import db
from api.routes import api_bp
from api.settings_routes import settings_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    # Инициализация БД
    db.init_app(app)

    # Регистрация Blueprint'ов
    app.register_blueprint(api_bp)
    app.register_blueprint(settings_bp)

    # Создание таблиц при старте (в продакшн — используй Flask-Migrate)
    with app.app_context():
        db.create_all()

    # ─── Страничные маршруты ─────────────────────────
    @app.route("/")
    def index():
        niches = _get_niches()
        return render_template("index.html", niches=niches)

    @app.route("/leads")
    def leads_page():
        niches = _get_niches()
        return render_template("leads.html", niches=niches)

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    return app


def _get_niches() -> list[str]:
    """
    Возвращает список ниш: сначала из БД (NicheGroup),
    если БД пуста — из config.py.
    """
    try:
        from models.settings import NicheGroup
        niches = db.session.query(NicheGroup.niche).distinct().all()
        if niches:
            return sorted(set(n[0] for n in niches))
    except Exception:
        pass
    return list(Config.NICHE_GROUPS.keys())


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
