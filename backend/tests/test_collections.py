from app.collections import parse_collection, parse_environment


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
