import json
from urllib.parse import urlparse

from fastapi import HTTPException

from app.schemas import EndpointSummary


def parse_json_bytes(payload: bytes, label: str) -> dict:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {label} JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object")
    return parsed


def parse_environment(env: dict | None) -> dict:
    if not env:
        return {}
    values = {}
    for item in env.get("values", []):
        if isinstance(item, dict) and item.get("key"):
            values[item["key"]] = item.get("value", "")
    return values


def parse_collection(collection: dict) -> tuple[str, list[EndpointSummary], dict]:
    info = collection.get("info", {})
    name = info.get("name") or "Untitled Collection"
    variables = {}
    for item in collection.get("variable", []):
        if isinstance(item, dict) and item.get("key"):
            variables[item["key"]] = item.get("value", "")

    endpoints: list[EndpointSummary] = []
    walk_items(collection.get("item", []), [], collection.get("auth"), endpoints)
    return name, endpoints, variables


def walk_items(items: list, folders: list[str], inherited_auth, endpoints: list[EndpointSummary]) -> None:
    for item in items:
        if "item" in item:
            walk_items(item.get("item", []), folders + [item.get("name", "Folder")], item.get("auth", inherited_auth), endpoints)
            continue
        request = item.get("request")
        if not isinstance(request, dict):
            continue
        endpoints.append(parse_request(item.get("name", "Untitled request"), folders, request, item.get("auth", inherited_auth)))


def parse_request(name: str, folders: list[str], request: dict, inherited_auth) -> EndpointSummary:
    method = str(request.get("method", "GET")).upper()
    url_value = request.get("url", "")
    raw_url = extract_raw_url(url_value)
    parsed = urlparse(raw_url.replace("{{", "").replace("}}", ""))
    path = parsed.path or raw_url
    headers = {h.get("key"): h.get("value", "") for h in request.get("header", []) if h.get("key")}
    params = extract_params(url_value)
    body = extract_body(request.get("body"))
    auth = request.get("auth") or inherited_auth or {}
    auth_type = auth.get("type", "none") if isinstance(auth, dict) else "none"
    display_name = " / ".join(folders + [name]) if folders else name
    return EndpointSummary(
        name=display_name,
        method=method,
        path=path,
        url=raw_url,
        auth_type=auth_type,
        headers=headers,
        params=params,
        body=body,
    )


def extract_raw_url(url_value) -> str:
    if isinstance(url_value, str):
        return url_value
    if isinstance(url_value, dict):
        if url_value.get("raw"):
            return url_value["raw"]
        protocol = url_value.get("protocol", "https")
        host = ".".join(url_value.get("host", []))
        path = "/".join(url_value.get("path", []))
        return f"{protocol}://{host}/{path}".rstrip("/")
    return ""


def extract_params(url_value) -> dict:
    if not isinstance(url_value, dict):
        return {}
    params = {}
    for item in url_value.get("query", []) or []:
        if item.get("key"):
            params[item["key"]] = item.get("value", "")
    return params


def extract_body(body) -> dict | list | str | None:
    if not isinstance(body, dict):
        return None
    mode = body.get("mode")
    if mode == "raw":
        raw = body.get("raw", "")
        try:
            return json.loads(raw)
        except Exception:
            return raw
    if mode == "urlencoded":
        return {item.get("key"): item.get("value", "") for item in body.get("urlencoded", []) if item.get("key")}
    if mode == "formdata":
        return {item.get("key"): item.get("value", "") for item in body.get("formdata", []) if item.get("key")}
    return body
