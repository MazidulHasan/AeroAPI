from app.collections import find_base_url, parse_collection, parse_environment


def test_parse_collection_extracts_nested_endpoint():
    collection = {
        "info": {"name": "Demo"},
        "item": [
            {
                "name": "Users",
                "item": [
                    {
                        "name": "Create user",
                        "request": {
                            "method": "POST",
                            "url": {
                                "raw": "{{baseUrl}}/api/users?active=true",
                                "query": [{"key": "active", "value": "true"}],
                            },
                            "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
                            "body": {"mode": "raw", "raw": "{\"email\":\"a@example.com\"}"},
                        },
                    }
                ],
            }
        ],
    }

    name, endpoints, variables = parse_collection(collection)

    assert name == "Demo"
    assert variables == {}
    assert len(endpoints) == 1
    assert endpoints[0].name == "Users / Create user"
    assert endpoints[0].method == "POST"
    assert endpoints[0].params == {"active": "true"}
    assert endpoints[0].body == {"email": "a@example.com"}


def test_parse_environment_values():
    env = {"values": [{"key": "baseUrl", "value": "https://api.example.com"}]}
    assert parse_environment(env) == {"baseUrl": "https://api.example.com"}


def test_parse_collection_resolves_environment_variables():
    collection = {
        "info": {"name": "Demo"},
        "item": [
            {
                "name": "List users",
                "request": {
                    "method": "GET",
                    "url": {
                        "raw": "{{baseUrl}}/api/users?active={{active}}",
                        "query": [{"key": "active", "value": "{{active}}"}],
                    },
                    "header": [{"key": "Authorization", "value": "Bearer {{token}}"}],
                },
            }
        ],
    }

    _, endpoints, _ = parse_collection(
        collection,
        {"baseUrl": "https://api.example.com", "active": "true", "token": "secret-token"},
    )

    assert endpoints[0].url == "https://api.example.com/api/users?active=true"
    assert endpoints[0].path == "/api/users"
    assert endpoints[0].params == {"active": "true"}
    assert endpoints[0].headers == {"Authorization": "Bearer secret-token"}


def test_find_base_url_prefers_known_keys():
    assert find_base_url({"token": "abc", "baseUrl": "https://api.example.com"}) == "https://api.example.com"
