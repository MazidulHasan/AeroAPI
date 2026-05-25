SECRET_KEYS = {"authorization", "cookie", "x-api-key", "api-key", "apikey", "token", "password", "secret"}

SQLI_PAYLOADS = ["' OR '1'='1", "'; SELECT 1; --", "\" OR \"1\"=\"1"]
ORM_BYPASS_PAYLOADS = [{"$ne": None}, {"$gt": ""}, {"$where": "1 == 1"}]
AUTH_BYPASS_HEADERS = [{"Authorization": ""}, {"Authorization": "Bearer invalid-token"}]


def severity_for_category(category: str) -> str:
    return {
        "security": "high",
        "regression": "medium",
        "edge": "low",
        "functional": "info",
    }.get(category, "info")


def redact_value(key: str, value):
    normalized = key.lower()
    if any(secret in normalized for secret in SECRET_KEYS):
        return "[REDACTED]"
    return value


def redact(data):
    if isinstance(data, dict):
        return {key: redact_value(key, redact(value)) for key, value in data.items()}
    if isinstance(data, list):
        return [redact(item) for item in data]
    return data
