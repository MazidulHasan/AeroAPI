from app.security import redact


def test_redact_masks_nested_secrets():
    payload = {
        "headers": {"Authorization": "Bearer secret", "Accept": "application/json"},
        "body": {"password": "secret", "email": "a@example.com"},
    }

    redacted = redact(payload)

    assert redacted["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["headers"]["Accept"] == "application/json"
    assert redacted["body"]["password"] == "[REDACTED]"
    assert redacted["body"]["email"] == "a@example.com"
