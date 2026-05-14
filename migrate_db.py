"""
migrate_db.py — обновление схемы БД.

Запуск для конкретного пользователя:
    python migrate_db.py admin
    python migrate_db.py ivan

Запуск для ВСЕХ пользователей в data/users/:
    python migrate_db.py --all

Без аргументов — старый режим (tg_leads.db в корне):
    python migrate_db.py
"""
import sqlite3
import os
import sys
from pathlib import Path


def get_db_path(login: str | None = None) -> str:
    if login:
        return str(Path(f"data/users/{login}/db.sqlite"))
    return os.getenv("DATABASE_URL", "sqlite:///tg_leads.db").replace("sqlite:///", "")


def column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


MIGRATIONS = [
    ("search_templates", "description",     "TEXT"),
    ("search_templates", "niche",           "TEXT"),
    ("search_templates", "min_score",       "REAL"),
    ("search_templates", "keyword_filter",  "TEXT"),
    ("search_templates", "date_range_days", "INTEGER"),
    ("search_templates", "sort_by",         "TEXT DEFAULT 'final_score'"),
    ("search_templates", "sort_order",      "TEXT DEFAULT 'desc'"),
    ("search_templates", "extra_filters",   "TEXT DEFAULT '{}'"),
    ("search_templates", "used_count",      "INTEGER DEFAULT 0"),
    ("app_settings",     "updated_at",      "DATETIME"),
    ("tg_auth_sessions", "phone_code_hash", "TEXT"),
    ("tg_auth_sessions", "authorized_at",   "DATETIME"),
    ("niche_groups",     "members_count",   "INTEGER"),
    ("niche_groups",     "source",          "TEXT DEFAULT 'manual'"),
    ("niche_groups",     "active",          "BOOLEAN DEFAULT 1"),
    ("leads",            "niche_raw",       "TEXT"),
    ("leads",            "activity_score",  "REAL DEFAULT 0"),
    ("leads",            "niche_score",     "REAL DEFAULT 0"),
    ("leads",            "scan_id",         "TEXT"),
]


def migrate(db_path: str):
    if not os.path.exists(db_path):
        print(f"  ⚠ Файл не найден: {db_path} — пропускаем")
        return

    print(f"\nБД: {db_path}")
    conn = sqlite3.connect(db_path)
    cur  = conn.cursor()
    added = 0

    for table, column, col_type in MIGRATIONS:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            continue
        if not column_exists(cur, table, column):
            print(f"  + ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            added += 1
        else:
            print(f"  ✓ {table}.{column} уже существует")

    conn.commit()
    conn.close()
    print(f"  Добавлено колонок: {added}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--all" in args:
        # Мигрируем все БД в data/users/
        users_root = Path("data/users")
        if not users_root.exists():
            print("Папка data/users/ не найдена")
            sys.exit(1)
        for user_dir in sorted(users_root.iterdir()):
            if user_dir.is_dir():
                migrate(str(user_dir / "db.sqlite"))
    elif args:
        # Конкретный пользователь
        migrate(get_db_path(args[0]))
    else:
        # Обратная совместимость — старый tg_leads.db
        migrate(get_db_path())

    print("\nМиграция завершена.")
