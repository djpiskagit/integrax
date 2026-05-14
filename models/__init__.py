from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Все модели импортируются здесь — db.create_all() их видит
from models.lead import Lead, ScanJob          # noqa
from models.settings import (                  # noqa
    AppSettings,
    TGAuthSession,
    Keyword,
    NicheGroup,
    SearchTemplate,
    TGStatCache,
)
