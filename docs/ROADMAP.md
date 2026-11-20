# Discount Parser — дорожная карта MVP v1.0

Статус: **готово к реализации**  
Основание: [`TECHNICAL_SPEC_V1.md`](TECHNICAL_SPEC_V1.md)  
Дата фиксации: **2026-08-08**

## Принцип дорожной карты

Работа идёт вертикальными срезами: каждый этап должен оставлять репозиторий в проверяемом состоянии и завершаться конкретным gate. Количество внешних источников наращивается только после того, как корректно работают хранение, дедупликация и жизненный цикл предложения.

```text
R0  Документация и freeze MVP
 ↓
R1  Каркас приложения
 ↓
R2  Домен и persistence
 ↓
R3  Source SDK + первый end-to-end parser
 ↓
R4  Нормализация + dedup + classification
 ↓
R5  5+ реальных источников
 ↓
R6  Lifecycle + scheduler
 ↓
R7  Telegram bot + publishing
 ↓
R8  XLSX correction loop
 ↓
R9  QA + demo + delivery
```

---

## R0 — Specification freeze

**Статус: DONE**

### Результат

- зафиксировано ТЗ MVP v1.0;
- определены scope/non-goals;
- проведён reuse-аудит релевантных репозиториев;
- зафиксирован базовый стек;
- определены критерии приёмки.

### Gate R0

`docs/TECHNICAL_SPEC_V1.md` и `docs/ROADMAP.md` находятся в `main`.

---

## R1 — Project foundation

**Цель:** получить минимальное приложение, которое запускается одинаково локально и в тестах.

### Задачи

- создать `pyproject.toml`;
- создать структуру `src/app`, `src/shared`, `src/modules`;
- перенести адаптированный app-factory pattern из `creative-test-agent`;
- добавить Pydantic Settings с prefix `DP_`;
- добавить `.env.example`;
- добавить structured/plain logging foundation;
- добавить `GET /health`;
- добавить базовый `pytest` setup;
- добавить `.gitignore`;
- описать dev-start в README.

### Reuse

Из `creative-test-agent`:

- `src/main.py -> create_app()`;
- settings pattern;
- модульная структура;
- health endpoint conventions.

### Gate R1

```bash
python -m pytest
uvicorn src.main:app
```

работают в чистом окружении; `/health` возвращает `ok`.

---

## R2 — Offer domain + persistence

**Цель:** сделать БД единственным источником истины.

### Задачи

- SQLAlchemy Base/session factory;
- SQLite WAL + busy timeout;
- Alembic configuration;
- модели:
  - `Source`;
  - `Offer`;
  - `OfferSourceObservation`/provenance;
  - `ParseRun`;
  - `ClassificationRule`;
  - `ManualOverride`;
  - `Publication`;
  - `PublishFilter`/bot settings;
- enum/status constraints;
- timestamps timezone-aware;
- unique indexes для точных dedup keys и publication idempotency;
- repository/service layer для Offer;
- `GET /health/db`;
- seed/test helpers.

### Reuse

Из `creative-test-agent`:

- SQLAlchemy session factory;
- SQLite WAL/busy timeout;
- Alembic foundation;
- DB healthcheck.

### Gate R2

- новая БД создаётся миграцией;
- offer можно создать/прочитать/обновить;
- manual override сохраняется;
- publication uniqueness проверена тестом;
- повторный запуск не пересоздаёт схему вручную.

---

## R3 — Source SDK + первый вертикальный parser slice

**Цель:** доказать полный путь `источник → БД` на одном реальном источнике до масштабирования.

### Задачи

- `SourceAdapter` protocol/base class;
- registry адаптеров;
- `config/sources.yaml`;
- общий HTTP client:
  - timeout;
  - retries/backoff;
  - rate limiting;
  - headers;
  - encoding handling;
- `RawOffer` schema;
- parser runner;
- source-level error isolation;
- parse-run counters;
- первый реальный adapter;
- HTML fixture для offline test;
- CLI/служебная команда запуска одного/всех источников.

### Reuse

Из `doors_parser`:

- BaseAdapter/registry pattern;
- YAML source config;
- HTTP utility ideas;
- isolated per-source processing;
- run-report counters.

### Gate R3

Один реальный источник:

```text
collect → RawOffer → normalize minimally → Offer → SQLite
```

работает повторяемо; второй запуск не создаёт точный дубль той же записи.

---

## R4 — Normalization, deduplication, classification

**Цель:** сделать ядро пригодным для подключения разных источников.

### R4.1 Normalization

- text normalization;
- URL canonicalization + tracking removal;
- percent/amount parsing;
- old/new price parsing;
- promo-code extraction;
- date/time parsing;
- offer type resolution;
- merchant/brand normalization.

### R4.2 Deduplication

- source external ID;
- canonical URL;
- merchant + promo code;
- fingerprint;
- fuzzy candidate matching через RapidFuzz;
- merge policy «лучшее/свежее поле»;
- provenance preservation;
- published offer protection.

### R4.3 Classification

- category taxonomy config;
- merchant/brand rules;
- keyword rules;
- rule priority;
- manual override priority;
- `needs_review` fallback.

### Reuse

Из `doors_parser`:

- `normalize()` style;
- RapidFuzz usage;
- dedup as a separate core operation;
- QA-first status handling.

### Gate R4

Набор fixture/tests доказывает:

- разные формулировки одной акции не размножаются без необходимости;
- два разных предложения одного магазина не схлопываются ошибочно;
- `discount_percent >= 20` можно вычислить по нормализованным данным;
- manual category override имеет приоритет.

---

## R5 — Source pack MVP

**Цель:** довести систему до минимум 5 реально работающих источников.

### R5.1 Source discovery gate

Для кандидатов проверяются:

- публичная доступность;
- стабильность HTML/API;
- полнота скидочных данных;
- наличие URL/image/date;
- отсутствие обязательного CAPTCHA/login;
- разумная стоимость поддержки.

### R5.2 Implementation

- подключить минимум 5 adapters;
- целевой диапазон — 5–10;
- обеспечить разные source fixtures;
- добавить per-source normalization hooks только там, где действительно нужны;
- source health status;
- graceful degradation при изменении страницы.

### Важное ограничение

Ozon/Wildberries/Яндекс Маркет не являются обязательными критериями R5. Они подключаются только если smoke-check показывает стабильный и поддерживаемый способ сбора.

### Gate R5

- минимум 5 adapters дают реальные данные;
- отказ одного источника не ломает общий run;
- повторный полный run не раздувает БД дублями;
- по каждому source есть counters/errors.

**Первый полноценный визуальный результат продукта:** к концу R5 уже можно показать живую XLSX/DB выборку реальных скидок из нескольких источников.

---

## R6 — Offer lifecycle + scheduler

**Цель:** система работает постоянно без ручного запуска parser scripts.

### Задачи

- APScheduler foundation;
- `collect_sources`;
- `expire_offers`;
- stale/missing observation policy;
- `build_publish_queue`;
- `maintenance`;
- job locking/idempotency для single-instance MVP;
- configurable parse intervals;
- configurable application timezone;
- вечерняя maintenance job, default 22:00;
- run history/last success/last error.

### Gate R6

В тестовом ускоренном режиме scheduler:

1. запускает parsing cycle;
2. не создаёт дубли;
3. переводит просроченную запись в `expired`;
4. не помечает предложение expired из-за одного failed fetch;
5. оставляет историю запуска.

---

## R7 — Telegram control plane + publishing

**Цель:** заказчик управляет системой из Telegram и публикует предложения без работы с кодом.

### R7.1 Bot foundation

- aiogram 3;
- admin allowlist;
- `/start`;
- `/status`;
- `/sources`;
- `/new`;
- `/queue`;
- inline keyboards.

### R7.2 Filters

- min discount percent;
- category/subcategory;
- offer type;
- merchant/source optional;
- active/unpublished only;
- save filter config.

### R7.3 Manual publishing

- preview card;
- skip/reject;
- publish;
- image + caption fallback to text;
- Telegram API error handling;
- save `telegram_message_id`.

### R7.4 Autopost

- enable/disable;
- use active saved filter;
- max posts per cycle;
- minimum interval;
- publication ledger;
- retry only safe failed sends;
- no accidental duplicate post.

### Gate R7

Сценарий:

```text
real parsed offer
→ filter discount >= 20%
→ queue
→ bot preview
→ publish
→ Telegram channel
→ publication ledger
```

проходит end-to-end.

Это основной демонстрационный milestone для заказчика.

---

## R8 — XLSX correction loop + rule memory

**Цель:** пользователь может корректировать категории без редактирования БД/кода.

### Задачи

- `offers.xlsx` exporter;
- листы active/needs_review/published/expired/sources;
- `/export`;
- безопасный XLSX importer;
- `/import` file handling;
- разрешённые editable columns;
- manual override persistence;
- conservative classification rule creation;
- report о применённых/пропущенных изменениях;
- roundtrip tests.

### Gate R8

Сценарий:

1. экспортировать XLSX;
2. исправить category/subcategory;
3. импортировать через бота;
4. повторно спарсить источник;
5. убедиться, что manual override не потерян;
6. проверить применение сохранённого безопасного правила к новой аналогичной записи.

---

## R9 — QA, demo, packaging, delivery

**Цель:** превратить работающий прототип в передаваемый MVP.

### R9.1 Automated QA

- полный offline pytest suite;
- adapter fixture tests;
- dedup regression dataset;
- lifecycle tests;
- publication idempotency tests;
- XLSX import/export tests;
- Telegram renderer tests;
- configuration tests.

### R9.2 Operational checks

- clean install check;
- migration from empty DB;
- source smoke run;
- bot startup;
- channel posting smoke;
- scheduler smoke;
- restart/recovery test;
- invalid token/source failure test.

### R9.3 Documentation

README должен содержать:

- назначение;
- installation;
- `.env`;
- migration/init;
- parser run;
- bot run;
- создание Telegram bot;
- добавление bot в channel как admin;
- source configuration;
- добавление нового adapter;
- export/import;
- troubleshooting.

### R9.4 Delivery evidence

Финальный smoke-report фиксирует минимум:

- число sources;
- число fetched/new/duplicate/expired;
- пример filter result;
- Telegram publication ID;
- pytest result;
- schema revision;
- known limitations.

### Gate R9 / MVP DONE

Все критерии раздела 22 `TECHNICAL_SPEC_V1.md` выполняются.

---

# После MVP — backlog v1.1+

Эти задачи **не должны задерживать первую версию**:

- web-admin panel;
- более умная taxonomy editor;
- LLM classification как fallback;
- LLM rewriting/post variants;
- Ozon adapter;
- Wildberries adapter;
- Yandex Market adapter;
- Playwright adapter class для JS-heavy sources;
- Telethon connector для источников, где web preview недостаточен и есть разрешённая учётная запись;
- affiliate link transformation;
- click analytics;
- price history;
- scoring «насколько выгодно предложение»;
- duplicate review UI;
- multi-channel publishing;
- per-channel templates/filters;
- PostgreSQL migration;
- Redis/Celery/RQ/Arq distributed jobs;
- Docker Compose production profile;
- remote monitoring/alerts.

# Definition of done для каждого этапа

Этап нельзя считать завершённым только потому, что написан код. Для каждого `R*` должны одновременно существовать:

1. реализация;
2. тест или воспроизводимый smoke-check;
3. обновлённая документация при изменении пользовательского поведения;
4. отсутствие известных regressions предыдущих gates;
5. commit в репозитории с понятным назначением.

# Текущий следующий шаг

После фиксации R0 реализация начинается с **R1 — Project foundation**. До R3 не подключаем пачку внешних сайтов: сначала создаём устойчивый каркас и persistence, затем доказываем один полный vertical slice и только после этого масштабируем число adapters.

## Spec Kit — candidate linkage (2026-11-20)

[Specification](../specs/001-contained-product-traceability/spec.md) · [Plan](../specs/001-contained-product-traceability/plan.md) · [Integration tasks](../specs/001-contained-product-traceability/tasks.md). Existing native source authority, scope, status and approval boundaries remain unchanged.
