import hmac
import secrets

import pytest

from app.security import valid_signature


@pytest.mark.parametrize("signature", [None, "", "bad", "я" * 64, "z" * 64])
def test_malformed_signature(signature: str | None) -> None:
    assert valid_signature(b"{}", signature, secrets.token_hex(32)) is False


def test_signature_uses_exact_bytes() -> None:
    secret = secrets.token_hex(32)
    body = b'{ "status" : "succeeded" }'
    signature = hmac.new(secret.encode(), body, "sha256").hexdigest()
    assert valid_signature(body, signature, secret) is True
    assert valid_signature(body, signature.upper(), secret) is True
    assert valid_signature(body + b"\n", signature, secret) is False
