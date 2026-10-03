"""The bank signs the original bytes, not a parsed or re-serialized JSON object."""

import hmac


def valid_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if signature is None or len(signature) != 64:
        return False
    try:
        supplied_digest = bytes.fromhex(signature)
    except ValueError:
        return False
    expected_digest = hmac.digest(secret.encode("utf-8"), body, "sha256")
    return hmac.compare_digest(expected_digest, supplied_digest)
