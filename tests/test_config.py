"""Configuration tests use temporary files and generated test-only secrets."""

import secrets
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("DATABASE_URL", "WEBHOOK_SECRET", "database_url", "webhook_secret"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def values() -> dict[str, str]:
    return {
        "database_url": "postgresql+asyncpg://localhost/kvitto",
        "webhook_secret": secrets.token_hex(32),
    }


def test_settings_load_environment(
    monkeypatch: pytest.MonkeyPatch, values: dict[str, str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", values["database_url"])
    monkeypatch.setenv("WEBHOOK_SECRET", values["webhook_secret"])

    settings = Settings()

    assert settings.database_url.get_secret_value() == values["database_url"]
    assert settings.webhook_secret.get_secret_value() == values["webhook_secret"]


def test_missing_settings_are_required() -> None:
    with pytest.raises(ValidationError) as error:
        Settings()

    errors = error.value.errors(include_input=False)
    assert {item["loc"] for item in errors} == {
        ("database_url",),
        ("webhook_secret",),
    }
    assert all(item["type"] == "missing" for item in errors)


@pytest.mark.parametrize("missing", ["database_url", "webhook_secret"])
def test_each_setting_is_required(values: dict[str, str], missing: str) -> None:
    values.pop(missing)

    with pytest.raises(ValidationError) as error:
        Settings(**values)

    assert error.value.errors(include_input=False)[0]["loc"] == (missing,)


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "sqlite+aiosqlite:///kvitto.db",
        "postgresql://localhost/kvitto",
        "postgresql+asyncpg://localhost/",
    ],
)
def test_invalid_database_url(values: dict[str, str], url: str) -> None:
    values["database_url"] = url

    with pytest.raises(ValidationError) as error:
        Settings(**values)

    assert error.value.errors(include_input=False)[0]["loc"] == ("database_url",)
    assert url not in str(error.value)


@pytest.mark.parametrize("secret", ["", " ", "\t\n"])
def test_empty_secret(values: dict[str, str], secret: str) -> None:
    values["webhook_secret"] = secret

    with pytest.raises(ValidationError) as error:
        Settings(**values)

    assert error.value.errors(include_input=False)[0]["loc"] == ("webhook_secret",)


def test_nonempty_secret_is_preserved(values: dict[str, str]) -> None:
    values["webhook_secret"] = f" {values['webhook_secret']} "

    settings = Settings(**values)

    assert settings.webhook_secret.get_secret_value() == values["webhook_secret"]


def test_settings_repr_hides_sensitive_values(values: dict[str, str]) -> None:
    settings = Settings(**values)

    assert values["database_url"] not in repr(settings)
    assert values["webhook_secret"] not in repr(settings)


def test_settings_load_dotenv(tmp_path: Path, values: dict[str, str]) -> None:
    (tmp_path / ".env").write_text(
        f"DATABASE_URL={values['database_url']}\n"
        f"WEBHOOK_SECRET={values['webhook_secret']}\n"
        "UNRELATED_VARIABLE=ignored\n",
        encoding="utf-8",
    )

    settings = Settings()

    assert settings.database_url.get_secret_value() == values["database_url"]
    assert settings.webhook_secret.get_secret_value() == values["webhook_secret"]


def test_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, values: dict[str, str]
) -> None:
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://localhost/from_file\n"
        f"WEBHOOK_SECRET={secrets.token_hex(32)}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", values["database_url"])
    monkeypatch.setenv("WEBHOOK_SECRET", values["webhook_secret"])

    settings = Settings()

    assert settings.database_url.get_secret_value() == values["database_url"]
    assert settings.webhook_secret.get_secret_value() == values["webhook_secret"]
