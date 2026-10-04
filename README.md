# discount-parser

Парсер скидок, промокодов, кэшбэка и выгодных предложений с нормализацией, дедупликацией и автоматической публикацией в Telegram-канал.

## Статус

**Архитектура:** универсальное ядро `arvectum_data` вынесено в отдельный canonical-репозиторий `arvectum2/data-platform`; Discount Parser теперь потребляет пакет `arvectum-data` с зафиксированного Git commit. Продуктовые адаптеры, parity-контроль и бизнес-логика остаются в этом репозитории.

**MVP v1.0 — R1–R8 DONE; R9 code/distribution implementation complete.**

Клиентский installer/web UI и cross-platform QA/delivery workflows реализованы. Финальный GitHub Actions execution сейчас блокируется до первого workflow step на уровне runner/account environment, поэтому `CI green` не заявляется. Live acceptance требует целевой машины, реального доступа к источникам и Telegram credentials.

## Документация

- [Поставка заказчику](docs/CLIENT_DELIVERY_GUIDE.md)
- [Требования к инфраструктуре](docs/INFRASTRUCTURE_REQUIREMENTS.md)
- [R9 QA / delivery status](docs/R9_IMPLEMENTATION.md)
- [Пользовательская инструкция по установке и запуску](docs/USER_INSTALLATION_GUIDE.md)
- [Техническое задание MVP v1.0](docs/TECHNICAL_SPEC_V1.md)
- [Дорожная карта](docs/ROADMAP.md)
- [R1 implementation](docs/R1_IMPLEMENTATION.md)
- [R2 implementation](docs/R2_IMPLEMENTATION.md)
- [R3 implementation](docs/R3_IMPLEMENTATION.md)
- [R4 implementation](docs/R4_IMPLEMENTATION.md)
- [R5 implementation](docs/R5_IMPLEMENTATION.md)
- [R6 implementation](docs/R6_IMPLEMENTATION.md)
- [R7 implementation](docs/R7_IMPLEMENTATION.md)
- [R8 implementation](docs/R8_IMPLEMENTATION.md)

## Реализовано

- FastAPI application factory, конфигурация `DP_*`, logging;
- `/health`, `/health/db`, `/health/sources`;
- SQLAlchemy 2.x + SQLite WAL + Alembic `0001`;
- Offer/Source/provenance/ParseRun/rules/overrides/publications/filters;
- normalization: canonical URL, benefit values, fingerprint, offer type;
- cross-source dedup: URL, promo code, fingerprint, RapidFuzz;
- deterministic taxonomy + DB rules + manual override priority;
- Source SDK, YAML config, HTTP retries/backoff, source/row failure isolation;
- 5 adapters: `promokood`, `promokodik`, `berikod`, `promokodi_net_ru`, `promko`;
- повторный parsing run обновляет Offer/observation вместо создания exact duplicate;
- APScheduler: collection + maintenance + autopost;
- lifecycle: explicit expiry и conservative stale review;
- Telegram control bot на aiogram 3 и deny-by-default admin allowlist;
- `/status`, `/sources`, `/new`, `/queue`, `/filter`, `/autopost`, `/export`, `/import`;
- preview + publish/skip/reject, image → text fallback;
- publication ledger с schema-valid `pending` reservation, `telegram_message_id` и защитой от дублей;
- XLSX export/import + manual overrides + exact-title rule memory;
- локальная web-панель: setup wizard, parser/bot/scheduler controls, schedule, sources, filters, queue, XLSX;
- browser предложений с поиском, фильтрами, карточкой Offer и provenance;
- журнал ParseRun и ошибок;
- System page с process state, PID, bot/scheduler logs и завершением приложения;
- single-instance web launcher;
- persisted enabled/disabled состояния источников в SQLite;
- frozen client delivery: Windows x64, macOS ARM64, macOS Intel;
- Windows `DiscountParser-Setup.exe`;
- macOS installer создаёт `Discount Parser.app` и сохраняет DB/settings при update;
- smoke-report generator для delivery evidence;
- CLI parse/maintenance/scheduler/bot/run/web/smoke-report;
- regression tests и cross-platform GitHub Actions configuration.

## Клиентская установка

Конечному пользователю Python, Git, pip и virtualenv не нужны.

Windows:

```text
DiscountParser-Setup.exe
```

macOS:

```text
discount-parser-macos-arm64
discount-parser-macos-intel
```

После установки пользователь запускает `Discount Parser` / `Discount Parser.app`. Браузер открывает локальную панель на:

```text
http://127.0.0.1:8765
```

На первом запуске web wizard запрашивает Telegram Bot Token, канал и Telegram user ID администратора. `.env` создаётся приложением автоматически.

## Установка для разработки

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

## Запуск для разработки

Web control panel:

```bash
python -m src.cli web
```

API:

```bash
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Парсер:

```bash
python -m src.cli parse
python -m src.cli parse --source promokood
```

Maintenance/scheduler:

```bash
python -m src.cli maintenance
python -m src.cli scheduler
```

Telegram control bot:

```bash
python -m src.cli bot
```

Bot + scheduler together:

```bash
python -m src.cli run
```

Delivery/smoke report:

```bash
python -m src.cli smoke-report
python -m src.cli smoke-report --output output/smoke_report.json
```

## Проверки

```bash
python -m compileall -q src tests
python -m pytest
alembic upgrade head
python -m src.cli smoke-report
```

## Инфраструктура

Для локального сценария отдельный сервер не нужен. Приложение работает на обычном ноутбуке Windows/macOS с интернетом; SQLite, web UI, scheduler и Telegram polling работают локально.

Автоматизация работает, пока ноутбук включён, не находится в sleep/hibernation, имеет интернет и запущен Discount Parser. Для режима 24/7 достаточно небольшой постоянно включённой машины/VPS. Подробности: [docs/INFRASTRUCTURE_REQUIREMENTS.md](docs/INFRASTRUCTURE_REQUIREMENTS.md).

## Pipeline

```text
источники
  ↓
source adapters
  ↓
нормализация
  ↓
дедупликация
  ↓
классификация
  ↓
SQLite
  ↓
lifecycle / scheduler
  ↓
filters / queue
  ↓
Telegram bot / autopost
  ↓
Telegram channel
  ↓
publication ledger
  ↓
XLSX correction / rule memory
```
