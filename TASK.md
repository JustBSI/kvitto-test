# Kvittо Junior Python/FastAPI Test Assignment

## Goal

Build a small payment API for an online school.

The implementation must be simple, reliable, testable and easy for a Junior
Python developer to explain during a technical interview.

Do not overengineer the project.

---

## Required technology stack

Use current stable releases available at implementation time:

- Python, latest stable version suitable for the ecosystem
- FastAPI
- Pydantic v2
- PostgreSQL
- SQLAlchemy 2.x async ORM
- asyncpg or another current stable async PostgreSQL driver if there is a
  justified reason to prefer it
- Alembic
- pytest
- pytest-asyncio
- httpx
- Ruff
- Docker
- Docker Compose
- GitHub Actions

The application must use asynchronous SQLAlchemy database access.

Do not use SQLite for the submitted implementation.

---

## Business rules

### Tariffs

The following tariffs must exist:

- basic: 990000 kopecks
- standard: 1990000 kopecks
- premium: 2990000 kopecks

Tariffs must exist in PostgreSQL and be created reproducibly during project
initialization.

Initialization must be idempotent.

---

### Money

All monetary amounts in the API, Python code and database are integers in
kopecks.

Never use float for monetary values.

Example:

19900 RUB = 1990000 kopecks

---

### Promo code

Supported promo code:

KVITTO10

Rules:

- gives a 10% discount
- case-insensitive
- KVITTO10, kvitto10 and Kvitto10 are equivalent
- unknown promo code must return HTTP 422
- no custom global validation error format is required

If there is no promo code:

discount = 0

If KVITTO10 is used:

discount = 10% of tariff price
amount = tariff price - discount

Use integer arithmetic only.

---

### Payment methods

Allowed values:

- card
- sbp
- installment

For installment:

installment_months is required.

Allowed values:

- 3
- 6
- 12

For card and sbp:

installment_months must be null or omitted.

Invalid combinations must return HTTP 422.

---

### Installment schedule

For installment payments return a list of payment amounts in kopecks.

Rules:

- len(schedule) == installment_months
- sum(schedule) == amount
- distribute the amount as evenly as possible
- extra kopecks go to the first payments
- never use float or round()

Example:

amount = 1990000
months = 3

schedule = [
    663334,
    663333,
    663333
]

For card and sbp:

schedule = null

---

### Payment statuses

A new payment has status:

pending

Allowed transitions:

pending -> succeeded
pending -> failed
succeeded -> refunded

All other transitions are forbidden.

Forbidden transition:

HTTP 409

Response:

{
  "error": "invalid_transition"
}

The database status must not change on an invalid transition.

Keep transition rules in an explicit and easily testable place.

---

## Payment fields

A payment response must contain:

- id
- status
- tariff_id
- amount
- discount
- method
- installment_months
- schedule
- email
- created_at

The database may additionally contain:

- idempotency_key

Use a reasonable ID type such as UUID.

created_at should be timezone-aware.

---

## Endpoints

### GET /tariffs

HTTP 200.

Return:

[
  {
    "id": ...,
    "title": "basic",
    "price": 990000
  }
]

---

### POST /payments

Body:

{
  "tariff_id": ...,
  "email": "...",
  "method": "card | sbp | installment",
  "installment_months": 3 | 6 | 12 | null,
  "promo_code": "..." | null
}

Optional header:

Idempotency-Key

For a newly created payment:

HTTP 201

If a payment with the same Idempotency-Key already exists:

- do not create another payment
- return the existing payment
- HTTP 200

If tariff_id does not exist, use a sensible documented error response.

---

### GET /payments/{id}

Existing payment:

HTTP 200

Missing payment:

HTTP 404

---

### GET /payments

This is a bonus requirement and must be implemented.

Optional filters:

- email
- status

Examples:

GET /payments
GET /payments?email=user@example.com
GET /payments?status=pending
GET /payments?email=user@example.com&status=succeeded

Filters must work together.

Use deterministic ordering.

Do not introduce complex pagination unless there is a concrete reason.

---

### POST /webhooks/bank

Body:

{
  "payment_id": ...,
  "status": "succeeded"
}

Required header:

X-Signature

Missing payment:

HTTP 404

Invalid transition:

HTTP 409

{
  "error": "invalid_transition"
}

Success:

HTTP 200

{
  "result": "ok"
}

---

## Idempotency

Idempotency must be safe under concurrent requests.

Do not rely only on:

SELECT -> if missing -> INSERT

Create a database-level UNIQUE constraint/index for non-null
idempotency_key values.

Correctly handle a conflict between concurrent requests so only one payment
can be persisted.

A repeated request must return the original payment.

Payments without Idempotency-Key must still be allowed.

---

## Webhook signature

Implement the assignment bonus.

Header:

X-Signature

Algorithm:

HMAC-SHA256

The signature must be calculated over the raw HTTP request body.

Secret comes from environment variable:

WEBHOOK_SECRET

Never hardcode the secret.

Use constant-time comparison such as hmac.compare_digest.

Invalid or missing signature:

HTTP 401

Do not calculate the signature from a re-serialized Pydantic object.

---

## Database

Use PostgreSQL and SQLAlchemy 2.x asynchronous APIs.

Use:

- create_async_engine
- async_sessionmaker
- AsyncSession

Database URL comes from:

DATABASE_URL

Do not hardcode database credentials.

Do not use create_all() as a replacement for migrations.

---

## Alembic

Alembic migrations are mandatory.

A clean database must become usable with:

alembic upgrade head

Create an initial migration.

Tariff initialization must be reproducible and idempotent.

---

## Transactions

Payment creation must be atomic.

Webhook status changes must be atomic.

Keep transaction boundaries explicit and understandable.

Avoid commits scattered unpredictably across layers.

---

## Pydantic

Use Pydantic v2 APIs.

Use separate request and response schemas.

Use Enum/Literal where appropriate.

Use EmailStr if appropriate.

Use Pydantic v2 cross-field validation for payment method /
installment_months rules where appropriate.

Do not use deprecated Pydantic v1 syntax.

---

## Tests

Use:

- pytest
- pytest-asyncio
- httpx

Tests must validate business results, not only HTTP status codes.

Required scenarios:

1. payment without promo code
2. KVITTO10 applies 10% discount
3. kvitto10 works in lowercase
4. unknown promo -> 422
5. installment schedule for 3 months
6. installment schedule for 6 months
7. installment schedule for 12 months
8. schedule sum always equals amount
9. repeated Idempotency-Key returns the same payment
10. repeated Idempotency-Key does not create another database row
11. GET existing payment -> 200
12. GET missing payment -> 404
13. pending -> succeeded
14. pending -> failed
15. succeeded -> refunded
16. invalid transition -> 409
17. invalid transition does not modify database state
18. GET /payments filter by email
19. GET /payments filter by status
20. combined filters
21. valid webhook HMAC signature
22. invalid webhook HMAC signature -> 401
23. missing webhook signature -> 401
24. invalid payment method/installment combinations -> 422

If it can be done without excessive complexity, add a concurrency test for
Idempotency-Key.

---

## Docker

The project must support:

docker compose up --build

Docker Compose must start at least:

- API
- PostgreSQL

Use a reasonable readiness/healthcheck mechanism.

Do not put secrets into Docker images.

Add:

- Dockerfile
- docker-compose.yml
- .dockerignore

---

## Configuration

Configuration must use environment variables.

At minimum:

DATABASE_URL
WEBHOOK_SECRET

Create:

.env.example

Real .env must be ignored by Git.

---

## Ruff

Configure Ruff in pyproject.toml.

The project must pass:

ruff check .

Prefer also:

ruff format --check .

Keep lint configuration reasonable and understandable.

---

## GitHub Actions

Implement the assignment bonus.

Run on:

- push
- pull_request

CI must run:

- dependency installation
- Ruff
- pytest

If tests require PostgreSQL, use a PostgreSQL service container or another
simple reproducible solution.

CI must work from a clean checkout.

---

## README.md

README is documentation for a human reviewer.

It must contain:

- short project description
- stack
- architecture overview
- quick start using Docker
- local development instructions
- environment setup
- migrations
- tests
- lint commands
- endpoint overview
- curl examples
- payment with card
- payment with installment
- Idempotency-Key example
- payment retrieval
- payment list/filter examples
- webhook/HMAC example
- business rules summary
- reference to AI_LOG.md

Instructions must be actually tested before submission.

---

## AGENTS.md

The repository must contain instructions for the coding agent.

AGENTS.md must describe:

- project constraints
- business invariants
- development commands
- testing requirements
- security requirements
- rules for keeping the implementation understandable for a Junior developer

---

## AI_LOG.md

This is mandatory.

It must truthfully contain:

- AI tools/models actually used
- 2-3 important prompts actually used
- real mistakes or weak suggestions produced by AI
- how those issues were detected
- how the final result was verified

Never invent an AI mistake just to fill this section.

---

## Scope

Do not implement:

- frontend
- user authentication
- real bank integration
- deployment infrastructure beyond Docker Compose
- unnecessary enterprise architecture

Avoid unnecessary:

- repository interfaces
- abstract factories
- ports/adapters
- CQRS
- event buses
- DI containers

For this project, prefer a simple flow such as:

API -> service/business logic -> SQLAlchemy

unless a concrete requirement justifies something more complex.

---

## Definition of done

Before considering the assignment complete, verify:

- all endpoints work
- all mandatory business rules work
- all bonuses are implemented
- PostgreSQL async access works
- Alembic works from a clean database
- tests pass
- Ruff passes
- Docker Compose starts the application
- GitHub Actions configuration is valid
- README instructions match the actual project
- AGENTS.md is current
- AI_LOG.md contains only truthful information

Do not claim any verification was successful unless it was actually run.
