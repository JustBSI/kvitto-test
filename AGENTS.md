## Project purpose

This repository contains a Junior Python/FastAPI technical assignment.

Before making any code changes, read `TASK.md` completely.

`TASK.md` is the source of truth for assignment requirements.

The goal is not merely to produce working code. The human developer must be
able to understand and explain every non-trivial line and architectural
decision during a technical interview.

## Working style

Work incrementally.

Do not implement the entire project in one large change unless the user
explicitly asks you to do so.

For each requested stage:

1. Inspect the existing repository first.
2. State the intended changes briefly.
3. Implement only the requested stage.
4. Run the relevant checks.
5. Stop.
6. Explain the result to the user.

Do not automatically continue to the next stage.

## Keep the implementation understandable

Prefer:

- simple over clever;
- explicit over magical;
- small functions over large handlers;
- concrete code over unnecessary abstractions;
- business rules that can be unit-tested directly.

Do not introduce a design pattern merely because it is common in large
production systems.

Avoid unnecessary:

- repository interfaces;
- service interfaces;
- abstract factories;
- dependency injection containers;
- CQRS;
- event buses;
- ports/adapters architecture.

If you believe additional complexity is necessary, explain why before
introducing it.

## Explain generated code

After each implementation stage, summarize:

- files created;
- files changed;
- purpose of each important file;
- important classes/functions;
- request/data flow;
- database behavior;
- transaction boundaries;
- relevant failure cases;
- tests added;
- concepts the developer should understand before an interview.

When the user asks about a piece of code, explain it in the context of this
project rather than giving only a generic definition.

## Core business invariants

These rules must never be violated.

### Money

- All money is stored and transferred as integer kopecks.
- Never use float for money.
- Discount calculations must use integer arithmetic.

### Installments

- Allowed terms are 3, 6 and 12 months.
- Schedule length equals `installment_months`.
- `sum(schedule)` must exactly equal `amount`.
- Remainder kopecks go to the first payments.

### Payment status

Allowed transitions only:

- `pending -> succeeded`
- `pending -> failed`
- `succeeded -> refunded`

An invalid transition must:

- return HTTP 409;
- leave database state unchanged.

### Idempotency

- `Idempotency-Key` must not create duplicate payments.
- Concurrency must be protected by a database constraint.
- Do not rely only on an application-level pre-check.
- Payments without a key must remain possible.

### Webhook security

- Use HMAC-SHA256.
- Verify `X-Signature` against the raw request body.
- Secret comes from `WEBHOOK_SECRET`.
- Never hardcode secrets.
- Use a timing-safe comparison.

## Python and framework rules

Use current stable APIs.

Use:

- modern stable Python;
- FastAPI;
- Pydantic v2;
- SQLAlchemy 2.x async APIs;
- PostgreSQL;
- Alembic;
- pytest;
- pytest-asyncio;
- httpx;
- Ruff.

Database operations in request paths must be asynchronous.

Do not silently introduce deprecated APIs.

Use type hints for application code where useful.

## Database rules

Use:

- `AsyncEngine`;
- `AsyncSession`;
- `async_sessionmaker`.

Keep transaction ownership explicit.

Do not scatter commits across unrelated helper functions.

Do not use SQLAlchemy `create_all()` as a substitute for Alembic migrations.

Model changes must include an Alembic migration.

## Testing rules

Any change to business logic must have relevant tests.

Tests must verify meaningful result data and database state, not only HTTP
status codes.

Before reporting a stage as complete, run the smallest relevant test set.

Before final submission, run the complete test suite.

Never delete or weaken a valid test merely to make the suite pass.

## Security

Never commit or print:

- passwords;
- API keys;
- database credentials;
- `WEBHOOK_SECRET`;
- tokens;
- real personal/payment data.

Use environment variables and `.env.example`.

Do not put real secrets into AI prompts.

## Required checks

Before final completion run, when available:

```bash
ruff check .
ruff format --check .
pytest
```

Also verify:

```bash
alembic upgrade head
docker compose up --build
```

Do not claim a command passed unless it was actually executed successfully.

### Implemented development commands

Docker-only setup and checks (Bash/Zsh, from the repository root):

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD,target=/project" --workdir /project \
  python:3.14-slim python scripts/setup_env.py
docker compose up --build --detach --wait
docker compose exec -T api python scripts/smoke_api.py
docker compose --profile test run --build --rm tests
```

Local Python development only (not required for Docker deployment):

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

`setup_env.py` creates a local .env only if none exists and never prints secrets.
Skip setup when .env is already configured. README.md also lists container-only
Ruff, migration and webhook commands. Do not require a host venv for Docker setup.
For local pytest, set TEST_DATABASE_URL to a dedicated PostgreSQL database whose
name ends in `_test`. Tests migrate and clear their own tables. Never point them
at the application database. See README.md for tested local URL setup and commands.

Tariffs are seeded in lifespan after Alembic migrations. GET sessions use
autobegin; writing services own explicit `session.begin()` transactions.

## Documentation

Keep `README.md` synchronized with the actual project.

README commands must match commands that were really tested.

Keep `AI_LOG.md` truthful.

Do not fabricate:

- prompts;
- models;
- AI mistakes;
- test results.

If AI_LOG information is not known, leave a TODO for the human instead of
inventing it.

## Git behavior

Make changes small enough to review.

Do not rewrite unrelated files.

Do not make destructive Git operations unless explicitly requested.

Do not squash or rewrite the user's history without permission.

## Interview readiness

At the end of each significant stage, identify any code that may be difficult
for a Junior developer to explain.

When multiple reasonable implementations exist, explain the important
trade-offs.

The final implementation should be something the human developer can defend
line-by-line in a technical interview.
