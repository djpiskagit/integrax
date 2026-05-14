"""
users.py — управление пользователями системы.

╔══════════════════════════════════════════════════╗
║  КАК ДОБАВИТЬ ПОЛЬЗОВАТЕЛЯ                       ║
║                                                  ║
║  1. python users.py <пароль>                     ║
║     → скопируйте хэш                            ║
║  2. Добавьте запись в USERS ниже                 ║
║  3. Перезапустите сервер                         ║
╚══════════════════════════════════════════════════╝
"""
import hashlib
import hmac
import sys

# Статическая соль — НЕ МЕНЯТЬ после первого запуска
_SALT = "tgl_2025_xK9#mP2qW"


def _hash(password: str) -> str:
    # Используем hmac.HMAC через конструктор — совместимо со всеми версиями Python 3
    return hmac.HMAC(
        _SALT.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ══════════════════════════════════════════════════
#  СПИСОК ПОЛЬЗОВАТЕЛЕЙ — редактируйте только здесь
# ══════════════════════════════════════════════════
USERS: dict = {

    "admin": {
        # Пароль по умолчанию: admin123
        # Смените перед деплоем: python users.py НовыйПароль
        "password_hash": _hash("admin123"),
        "name": "Admin",
        "active": True,
    },

    # Пример добавления клиента:
    # "ivan": {
    #     "password_hash": _hash("supersecret"),
    #     "name": "Иван Иванов",
    #     "active": True,
    # },

}
# ══════════════════════════════════════════════════


def check_credentials(login: str, password: str):
    """
    Проверяет логин + пароль, защищён от timing-атак.
    Возвращает {"login": ..., "name": ...} или None.
    """
    login      = login.strip().lower()
    user       = USERS.get(login)
    given_hash = _hash(password)
    dummy_hash = _hash("__dummy__")

    if not user or not user.get("active", True):
        hmac.compare_digest(dummy_hash, given_hash)  # timing-safe
        return None

    if hmac.compare_digest(user["password_hash"], given_hash):
        return {"login": login, "name": user["name"]}

    return None


# ── CLI: генерация хэша ────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование:  python users.py <пароль>")
        print("Вставьте хэш в password_hash нужного пользователя в USERS.")
        sys.exit(0)
    pw = sys.argv[1]
    print(f'\n  "password_hash": "{_hash(pw)}",')
    print(f"  # пароль: {pw!r}\n")
