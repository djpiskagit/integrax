from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Import all models so db.create_all() picks them up
from models.lead import Lead, ScanJob  # noqa
from models.settings import Keyword, NicheGroup, SearchTemplate, TGAuthSession  # noqa
