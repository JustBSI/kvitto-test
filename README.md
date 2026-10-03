# Kvitto Payment API

[Репозиторий](https://github.com/JustBSI/kvitto-test) ·
[GitHub Actions](https://github.com/JustBSI/kvitto-test/actions/workflows/ci.yml)

API платежей онлайн-школы: тарифы, промокод, рассрочка, идемпотентное создание
платежа и подписанные уведомления банка. Реализованы все маршруты и бонусы из
[TASK.md](TASK.md). Правила разработки — [AGENTS.md](AGENTS.md), фактическая
история использования ИИ и проверок — [AI_LOG.md](AI_LOG.md).

## Стек

Python 3.14, FastAPI, Pydantic v2 / pydantic-settings, PostgreSQL 18,
SQLAlchemy 2.1 async ORM, asyncpg, Alembic, pytest / pytest-asyncio / HTTPX,
Ruff, Docker Compose и GitHub Actions. Прямые версии закреплены в
`pyproject.toml`; отдельного lock-файла нет, транзитивные версии не зафиксированы.

## Быстрый запуск через Docker

Нужен только запущенный Docker Engine с Compose. Локальные Python, `uv` и
`.venv` не требуются. Все команды выполняются из корня проекта в Bash/Zsh
(Linux, macOS или WSL).

При первом запуске создайте `.env` одноразовым контейнером:

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD,target=/project" --workdir /project \
  python:3.14-slim python scripts/setup_env.py
```

Затем соберите и запустите приложение:

```bash
docker compose up --build --detach --wait
```

`setup_env.py` создаёт `.env` с новыми случайными паролем и HMAC-секретом,
правами 0600 и адресами сервисов Compose. Значения не выводятся. Существующий
`.env` скрипт не перезаписывает: если файл уже настроен, пропустите генерацию.
`--user` сохраняет владельцем файла текущего пользователя, а bind mount позволяет
контейнеру записать файл в корень проекта. Альтернатива — вручную заполнить
placeholders из `.env.example`; никогда не добавляйте реальные значения в Git.

Compose ожидает готовность PostgreSQL, применяет `alembic upgrade head`, затем
запускает API. В lifespan заполняются три тарифа; повторный запуск не создаёт
дубликатов. API healthcheck обращается к `/tariffs` и проверяет доступность БД.
Данные основной БД хранятся в volume `postgres_data`; обычная остановка их
сохраняет. В образах нет `.env` и секретов, API работает от непривилегированного
пользователя.

Документация: <http://127.0.0.1:8000/docs>.
OpenAPI: <http://127.0.0.1:8000/openapi.json>.

```bash
docker compose exec -T api python scripts/smoke_api.py
```

Эта проверка создаёт синтетические платежи с адресами `@example.com` и проверяет
все бизнес-маршруты через настоящий HTTP-сервер.

## Настройки

| Переменная | Назначение |
| --- | --- |
| `DATABASE_URL` | Async URL основной PostgreSQL, драйвер `postgresql+asyncpg` |
| `WEBHOOK_SECRET` | Непустой секрет HMAC-SHA256 |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Инициализация PostgreSQL в Compose |
| `TEST_DATABASE_URL` | Отдельная тестовая PostgreSQL; имя БД заканчивается на `_test` |
| `API_PORT`, `POSTGRES_PORT`, `TEST_POSTGRES_PORT` | Необязательные порты хоста: по умолчанию 8000, 5432, 5433 |

`Settings` читает окружение с приоритетом над `.env` в текущем рабочем каталоге.
Некорректная конфигурация останавливает запуск. URL и секрет представлены как
`SecretStr`; это маскирование вывода, а не шифрование. Не выводите настройки,
окружение или `.env` в лог. При ручной настройке URL кодируйте специальные
символы пароля; генератор использует безопасные для URL hex-значения.

## Тесты и Ruff

Полный набор с отдельной PostgreSQL, без установки тестовых пакетов в API-образ:

```bash
docker compose --profile test run --build --rm tests
```

Тестовый профиль запускает `test-db`, мигрирует её и выполняет pytest.
Тесты очищают таблицы этой БД перед/после каждого интеграционного теста;
используйте только выделенную тестовую БД. Без `TEST_DATABASE_URL` интеграционные
тесты завершаются ошибкой, а не пропускаются. SQLite не используется.

Фикстура очищает БД до startup и не заполняет тарифы сама: создание проверяется
через настоящий lifespan. Есть проверки повторного startup, восстановления
отсутствующего тарифа и конкурентного seed пустой таблицы.
Тест webhook удерживает строку другой транзакцией, дожидается фактической
блокировки через `pg_locks` / `pg_blocking_pids`, меняет статус и проверяет 409
после освобождения строки. Ожидание ограничено 10 секундами.

Ruff также запускается в контейнере. Исходники монтируются только для чтения;
кэш отключён, PostgreSQL для этих проверок не запускается:

```bash
docker compose --profile test run --build --rm --no-deps \
  --volume "$PWD:/workspace:ro" --workdir /workspace \
  tests python -m ruff check --no-cache .
docker compose --profile test run --rm --no-deps \
  --volume "$PWD:/workspace:ro" --workdir /workspace \
  tests python -m ruff format --check --no-cache .
```

GitHub Actions выполняет установку, обе проверки Ruff и pytest на push и
pull request. PostgreSQL предоставляется service container. Только одноразовый
CI-сервис использует passwordless trust на loopback; обычный Compose требует
пароль. Тесты применяют Alembic из чистого состояния.

## Миграции

Схему меняют только миграции, не `create_all()`. При запуске API-контейнера
`alembic upgrade head` выполняется автоматически; затем lifespan заполняет тарифы.
Повторный запуск миграций и проверка соответствия моделей схеме:

```bash
docker compose exec -T api python -m alembic upgrade head
docker compose exec -T api python -m alembic check
```

## Локальная разработка (не нужна для Docker-запуска)

Только для запуска Python-инструментов на хосте нужны Python 3.14 и `uv`.
В PyCharm используется интерпретатор `.venv/bin/python`. Создайте окружение
и установите зависимости:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python --cache-dir .cache/uv --index-url https://pypi.org/simple -e '.[dev]'
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
uv pip check --python .venv/bin/python --cache-dir .cache/uv
```

Подготовьте `.env` по инструкции выше (или локально через
`.venv/bin/python scripts/setup_env.py`, если файла ещё нет).

Для API вне Docker остановите API-контейнер и оставьте обе PostgreSQL:

```bash
docker compose stop api
docker compose --profile test up --detach --wait db test-db
set -a
source .env
set +a
export DATABASE_URL="${DATABASE_URL/@db:5432/@localhost:5432}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL/@test-db:5432/@localhost:5433}"
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m pytest
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Команды подходят для `.env`, созданного генератором, и стандартных портов.
При изменении портов скорректируйте локальные URL. Переменные экспортируются
только в текущий shell. Для возврата к контейнерам остановите Uvicorn через
Ctrl+C и используйте новый shell с исходным `.env`, затем
`docker compose start --wait api`.

## Маршруты и ошибки

| Метод и путь | Результат |
| --- | --- |
| `GET /tariffs` | Три тарифа, сортировка по цене и ID |
| `POST /payments` | Новый платёж: 201; повторный ключ: 200 с сохранённым платежом |
| `GET /payments/{payment_id}` | Платёж: 200; отсутствующий: 404 |
| `GET /payments` | Список; необязательные `email` и `status` работают совместно |
| `POST /webhooks/bank` | Подписанный допустимый переход: 200, `{"result":"ok"}` |

Неизвестный тариф: 404 `{"detail":"tariff_not_found"}`. Отсутствующий платёж:
404 `{"detail":"payment_not_found"}`. Неизвестный промокод, неверный email,
метод, срок или формат UUID: стандартный 422 FastAPI. Непустой
`Idempotency-Key` ограничен 255 символами; тело повторного запроса также должно
проходить валидацию, но его значения не заменяют сохранённый платёж.

`tariff_id` — целое число от 1 до 2147483647, как PostgreSQL `Integer`.
Значение вне диапазона получает 422 до обращения к тарифу в БД;
отсутствующий ID внутри диапазона — 404.

Отсутствующая/неверная подпись: 401 `{"detail":"invalid_signature"}`.
В OpenAPI заголовок `X-Signature` отмечен обязательным. Обработчик извлекает его
вручную, чтобы отсутствие подписи оставалось ошибкой 401, а не валидационным 422.
Запрещённый переход, включая повтор текущего статуса: 409
`{"error":"invalid_transition"}`, БД не меняется. Подпись проверяется раньше
валидации тела webhook: подписанный некорректный JSON получает 422.

Список платежей упорядочен по `created_at`, затем UUID; фильтр email использует
проверенное значение `EmailStr` и точное совпадение. Пагинации нет.

## Примеры curl

Получите тарифы и выберите фактический ID `standard` из ответа:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/tariffs
TARIFF_ID=2
```

`2` — пример для чистой БД; после тестов/ручных изменений ID могут отличаться.

Карточный платёж с ключом идемпотентности:

```bash
curl --fail --silent --show-error -X POST http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-card-001' \
  --data "{\"tariff_id\":$TARIFF_ID,\"email\":\"student@example.com\",\"method\":\"card\"}"
```

Повтор этой команды возвращает тот же платёж с HTTP 200. Без заголовка каждый
корректный запрос создаёт новый платёж. Для СБП используйте `"method":"sbp"`.

Рассрочка на три месяца со скидкой:

```bash
curl --fail --silent --show-error -X POST http://127.0.0.1:8000/payments \
  -H 'Content-Type: application/json' \
  --data "{\"tariff_id\":$TARIFF_ID,\"email\":\"student@example.com\",\"method\":\"installment\",\"installment_months\":3,\"promo_code\":\"KVITTO10\"}"
```

Для `standard` сумма будет 1791000, скидка 199000, график `[597000,597000,597000]`.
Скопируйте UUID карточного платежа в `PAYMENT_ID`:

```bash
PAYMENT_ID='<UUID из ответа POST /payments>'
curl --fail --silent --show-error "http://127.0.0.1:8000/payments/$PAYMENT_ID"
curl --fail --silent --show-error http://127.0.0.1:8000/payments
curl --fail --silent --show-error -G http://127.0.0.1:8000/payments \
  --data-urlencode 'email=student@example.com'
curl --fail --silent --show-error -G http://127.0.0.1:8000/payments \
  --data-urlencode 'status=pending'
curl --fail --silent --show-error -G http://127.0.0.1:8000/payments \
  --data-urlencode 'email=student@example.com' --data-urlencode 'status=pending'
```

Подписанный webhook:

```bash
docker compose exec -T api python scripts/send_webhook.py "$PAYMENT_ID" succeeded
docker compose exec -T api python scripts/send_webhook.py "$PAYMENT_ID" refunded
```

Утилита работает внутри API-контейнера и получает секрет из его окружения;
локальный Python не нужен. Она формирует тело с `payment_id` и `status`, вычисляет
`hmac.new(secret.encode(), body, "sha256").hexdigest()` и отправляет ровно те
же байты с заголовком `X-Signature`. Секрет и подпись не печатаются. Формат
подписи — 64 hex-символа; допустимы оба регистра. Изменение пробелов или порядка
полей требует пересчёта подписи. Утилита имитирует банк, реальной интеграции нет.

## Архитектура и транзакции

| Файл | Назначение |
| --- | --- |
| `app/config.py`, `app/main.py` | `Settings`, фабрика и lifespan, engine/session factory |
| `app/models.py`, `migrations/` | ORM-таблицы и первоначальная схема Alembic |
| `app/database.py` | Сессия запроса и идемпотентный seed тарифов |
| `app/schemas.py` | Входные/выходные модели, EmailStr, проверки promo/method/months |
| `app/business.py` | Enum, скидка, график и разрешённые переходы; без БД/HTTP |
| `app/services.py` | Операции с БД и владение транзакциями записи |
| `app/api.py`, `app/security.py` | HTTP, сборка ответа, ошибки и HMAC |
| `tests/`, `scripts/` | Unit/API/DB-тесты, безопасная настройка и проверка живого API |

Создание: Pydantic → `create_payment()` → тариф и целочисленный расчёт → INSERT
→ commit → публичный ответ. График вычисляется из сохранённых суммы и срока,
отдельного столбца schedule нет. В ответе не раскрывается ключ идемпотентности.

В `create_payment()` один `session.begin()`. Предварительный SELECT ускоряет
повтор, а UNIQUE в PostgreSQL защищает гонку. При конфликте INSERT адресно
использует `ON CONFLICT DO NOTHING`; после ожидания commit победителя следующий
SELECT видит его строку при стандартном READ COMMITTED. NULL-ключи не конфликтуют.

Webhook: исходные байты → HMAC / `compare_digest` → Pydantic →
`change_payment_status()` → `SELECT FOR UPDATE` → правило перехода → commit.
Блокировка строки сериализует конкурентные уведомления. Исключение внутри
`session.begin()` откатывает транзакцию. GET использует autobegin; закрытие
сессии завершает транзакцию чтения. Helper-функции не делают неожиданных commit.

`expire_on_commit=False` сохраняет загруженные атрибуты ORM после commit,
чтобы формирование ответа не требовало скрытого повторного запроса к БД.

## Бизнес-правила и подготовка к интервью

- Тарифы: basic 990000, standard 1990000, premium 2990000 копеек.
- Деньги всегда integer. Скидка KVITTO10: `price * 10 // 100`, регистр не важен.
- Рассрочка: 3/6/12 месяцев; `divmod` даёт базовый платёж и остаток, лишние
  копейки добавляются первым платежам. Длина и сумма графика точны.
- Для card/sbp срок и график — null. Новый платёж — pending.
- Переходы: pending → succeeded/failed; succeeded → refunded. Других нет.
- На интервью стоит объяснить отличие ORM от Pydantic, lifespan от запроса,
  autobegin от явной транзакции, UNIQUE от предварительного SELECT,
  READ COMMITTED, блокировку строки и необходимость подписывать исходные байты.

Контекстные пояснения следуют официальным документам
[FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) и
[SQLAlchemy async sessions](https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html).

## Фактические проверки

На macOS / Python 3.14.3 и в Linux ARM64 / Python 3.14.8 прошли 142 теста.
Проверены чистая миграция CLI, отсутствие расхождений моделей (`alembic check`),
сборка/healthcheck Compose, локальный Uvicorn, smoke через HTTP и curl-примеры.
`ruff check .`, `ruff format --check .` и `uv pip check` прошли.
Workflow проверен actionlint. После публикации публичного репозитория
[GitHub Actions](https://github.com/JustBSI/kvitto-test/actions/runs/37143328937)
успешно выполнил установку зависимостей, обе проверки Ruff и все 138 тестов.

Docker-only сценарий повторно проверен 2026-10-04 на отдельной копии проекта
без `.venv` и с новой PostgreSQL: генерация `.env` (права 0600, защита от
перезаписи), сборка/healthcheck, 138 тестов, обе проверки Ruff, миграции,
smoke API и webhook-утилита. Все эти команды выполнены в контейнерах;
`pip check` в API-образе также прошёл.

После исправлений по внешнему аудиту прошли 142 теста на обеих платформах,
Ruff, запуск Compose, миграции и smoke. На живом API проверены обязательность
подписи в OpenAPI и сохранение 401 без заголовка. Дополнительно отключение seed
и `FOR UPDATE` только в памяти отдельных процессов вызвало ожидаемые падения
соответствующих новых тестов. Указанный выше запуск GitHub Actions относится
к ранее опубликованной версии с 138 тестами, не к этим локальным изменениям.
