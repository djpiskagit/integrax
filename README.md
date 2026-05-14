# TG Leads — MVP для лидогенерации из Telegram

Веб-приложение: Flask + Telethon + SQLite + Jinja2.  
Парсит Telegram-группы по нише, определяет лидов и скорит их.

---

## Новое в этой версии

| Функция | Описание |
|---------|----------|
| 🔑 **Telegram Auth UI** | Вход через телефон + SMS-код + 2FA прямо в браузере |
| 🔍 **Keywords Manager** | Добавление/удаление intent и negative keywords через UI + массовый импорт |
| 👥 **Groups Manager** | Управление группами по нишам, вкл/выкл групп, создание новых ниш |
| 📊 **TGStat API** | Поиск каналов по ключевым словам, добавление в нишу одним кликом |
| 📋 **Templates** | Сохранение наборов фильтров, быстрый переход к лидам по шаблону |

---

## Структура проекта

```
tg_leads/
├── app.py                      # Точка входа Flask
├── config.py                   # Конфигурация (TGSTAT_TOKEN добавлен)
├── requirements.txt
├── seed_demo.py
├── Dockerfile / docker-compose.yml
│
├── models/
│   ├── __init__.py             # SQLAlchemy db + импорт всех моделей
│   ├── lead.py                 # Lead + ScanJob
│   └── settings.py             # Keyword, NicheGroup, SearchTemplate, TGAuthSession
│
├── services/
│   ├── lead_detector.py        # is_lead() — читает keywords из БД (fallback: config)
│   ├── scorer.py               # Скоринг
│   ├── exporter.py             # CSV / XLSX
│   └── tgstat_api.py           # TGStat REST API клиент
│
├── services/tg_auth.py         # Telegram авторизация: send_code / sign_in / logout
│
├── parser/
│   └── tg_parser.py            # Читает группы из БД (fallback: config)
│
├── api/
│   ├── routes.py               # REST: scan, leads, export, stats
│   └── settings_routes.py      # REST: keywords, groups, tgstat, templates, tg-auth
│
└── templates/
    ├── base.html               # Навигация (добавлена кнопка ⚙ Настройки)
    ├── index.html              # Страница запуска скана
    ├── leads.html              # Таблица лидов с фильтрами
    └── settings.html           # ★ Новая страница настроек
```

---

## Быстрый старт

### 1. Установка

```bash
cd tg_leads
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Настройка .env

```env
# Telegram API (получить на https://my.telegram.org)
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890

# TGStat API (получить на https://tgstat.ru/api) — опционально
TGSTAT_TOKEN=your_tgstat_token

FLASK_SECRET_KEY=change-me-in-production
```

> **TG_PHONE больше не нужен в .env** — телефон вводится через UI на странице /settings

### 3. Запуск

```bash
python app.py
```

Откройте: http://localhost:5000

### 4. Первоначальная настройка (через UI)

1. Откройте **⚙ Настройки** в навигации
2. **Telegram Auth** — введите номер телефона, подтвердите SMS-код
3. **Ключевые слова** → нажмите «↻ Sync config» для импорта из config.py
4. **Группы** → нажмите «↻ Sync config» для импорта из config.py
5. Дополнительно: через **TGStat API** найдите новые группы по запросу

---

## API Endpoints

### Основные

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/scan` | Запуск парсинга |
| GET | `/api/leads` | Лиды с фильтрами |
| GET | `/api/export?format=csv` | Экспорт CSV |
| GET | `/api/export?format=xlsx` | Экспорт Excel |
| GET | `/api/stats` | Статистика по нишам |
| GET | `/api/scan/<id>` | Статус скана |

### Настройки (`/api/settings/...`)

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/settings/keywords` | Все keywords |
| POST | `/api/settings/keywords` | Добавить keyword |
| DELETE | `/api/settings/keywords/<id>` | Удалить |
| POST | `/api/settings/keywords/bulk` | Массовое добавление |
| POST | `/api/settings/keywords/sync-config` | Импорт из config.py |
| GET | `/api/settings/groups` | Все группы |
| POST | `/api/settings/groups` | Добавить группу |
| PATCH | `/api/settings/groups/<id>` | Вкл/выкл группы |
| DELETE | `/api/settings/groups/<id>` | Удалить |
| POST | `/api/settings/groups/sync-config` | Импорт из config.py |
| GET | `/api/settings/tgstat/search?q=...` | Поиск в TGStat |
| POST | `/api/settings/tgstat/add` | Добавить из TGStat |
| GET | `/api/settings/templates` | Все шаблоны |
| POST | `/api/settings/templates` | Создать шаблон |
| PATCH | `/api/settings/templates/<id>` | Обновить |
| DELETE | `/api/settings/templates/<id>` | Удалить |
| POST | `/api/settings/templates/<id>/use` | Применить |
| GET | `/api/settings/tg/status` | Статус авторизации |
| POST | `/api/settings/tg/send-code` | Отправить SMS |
| POST | `/api/settings/tg/sign-in` | Подтвердить код |
| POST | `/api/settings/tg/logout` | Выйти |

---

## Шаблоны поиска

Шаблоны позволяют сохранять наборы фильтров и применять их одним кликом:

```json
{
  "name": "Горячие дизайн-лиды",
  "niche": "дизайн",
  "min_score": 70,
  "date_range_days": 7,
  "sort_by": "final_score",
  "sort_order": "desc"
}
```

При нажатии **▶ Применить** открывается `/leads` с уже установленными фильтрами.

---

## Скоринг лидов

| Компонента | Вес | Описание |
|-----------|-----|----------|
| intent_score | 45% | Ключевые слова намерения купить |
| activity_score | 25% | Активность пользователя в группе |
| niche_score | 30% | Совпадение с нишей |
| **final_score** | **100%** | Взвешенная сумма (0–100) |

**Цвета:** 🟢 ≥ 70 горячий · 🟡 40–69 тёплый · 🔴 < 40 холодный

---

## Docker

```bash
docker-compose up --build
```

---

## Известные ограничения

1. **Парсинг синхронный** — для продакшн используйте Celery + Redis
2. **Нет авторизации пользователей** — добавьте Flask-Login для multi-user
3. **TGStat** — платный API, бесплатный tier ограничен
4. **FloodWait** — Telegram ограничивает запросы, парсер ждёт автоматически
