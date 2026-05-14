"""
check_telegram.py — диагностика подключения к Telegram.
Запустите на сервере: python check_telegram.py

Покажет точную причину почему Telethon не может подключиться.
"""
import socket
import sys
import os

TELEGRAM_DCS = [
    ("149.154.167.51", 443,  "DC1 (Лондон)"),
    ("149.154.167.51", 80,   "DC1 (Лондон) port 80"),
    ("149.154.175.52", 443,  "DC2 (Амстердам)"),
    ("149.154.175.100",443,  "DC3"),
    ("149.154.167.91", 443,  "DC4"),
    ("91.108.56.130",  443,  "DC5"),
    ("149.154.167.51", 5222, "DC1 port 5222"),
]

print("=" * 55)
print("Диагностика подключения к Telegram MTProto")
print("=" * 55)

# 1. Проверка DNS
print("\n[1] DNS резолвинг telegram.org...")
try:
    ip = socket.gethostbyname("web.telegram.org")
    print(f"    ✓ web.telegram.org → {ip}")
except Exception as e:
    print(f"    ✗ DNS не работает: {e}")

# 2. Проверка портов MTProto
print("\n[2] Проверка портов MTProto DataCenter серверов...")
any_ok = False
for host, port, label in TELEGRAM_DCS:
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        print(f"    ✓ {label:30s} {host}:{port}")
        any_ok = True
    except Exception as e:
        print(f"    ✗ {label:30s} {host}:{port}  — {type(e).__name__}: {e}")

# 3. Вывод рекомендаций
print()
if not any_ok:
    print("❌ ВЫВОД: Сервер/хостинг БЛОКИРУЕТ все MTProto порты Telegram.")
    print()
    print("РЕШЕНИЯ:")
    print("  A) Если это shared-хостинг (Beget, Timeweb и т.д.):")
    print("     → Telegram MTProto заблокирован провайдером хостинга.")
    print("     → Используйте VPS (DigitalOcean, Hetzner, Vultr).")
    print()
    print("  B) Если это VPS с блокировкой:")
    print("     → Настройте MTProxy или SOCKS5 прокси.")
    print("     → Добавьте в tg_auth.py: proxy=('socks5', 'host', port)")
    print()
    print("  C) Локально на вашем ПК — включите VPN.")
else:
    print("✅ ВЫВОД: Некоторые порты Telegram доступны.")
    print("   Если всё равно ошибка — проблема в API_ID/API_HASH или номере.")
    print("   Проверьте: my.telegram.org/apps → ваш API ID и Hash.")

print()
