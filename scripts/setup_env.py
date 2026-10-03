"""Create local development configuration once, without printing any secrets."""

import os
import secrets
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    password = secrets.token_hex(24)
    secret = secrets.token_hex(32)
    content = (
        "POSTGRES_USER=kvitto\n"
        f"POSTGRES_PASSWORD={password}\n"
        "POSTGRES_DB=kvitto\n"
        f"DATABASE_URL=postgresql+asyncpg://kvitto:{password}@db:5432/kvitto\n"
        f"TEST_DATABASE_URL=postgresql+asyncpg://kvitto:{password}@test-db:5432/kvitto_test\n"
        f"WEBHOOK_SECRET={secret}\n"
    )
    try:
        descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(".env already exists; it was left unchanged") from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(content)
    print("Created .env with random local secrets (permissions 0600)")


if __name__ == "__main__":
    main()
