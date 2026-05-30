import asyncio
import json
import re
from abc import ABC, abstractmethod

import httpx

from app.schemas import EndpointReference, EndpointSummary


class LLMProvider(ABC):
    def __init__(self, model: str, api_token: str, custom_base_url: str | None = None):
        self.model = model
        self.api_token = api_token
        self.custom_base_url = custom_base_url

    def prompt(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> str:
        docs_context = ""
        if api_docs and api_docs.strip():
            docs_context = f"""
API documentation and business context:
{api_docs[:12000]}

Use the documentation to create business-rule-aware tests, including required workflows, permissions, state transitions, validation rules, error contracts, and domain invariants. Prefer realistic data and assertions over generic probes.
"""
        endpoint_inventory = ""
        if available_endpoints:
            endpoint_inventory = "Available collection endpoints. Dependency steps MUST use only these method/path pairs:\n"
            endpoint_inventory += "\n".join(f"- {item.method} {item.path} ({item.name})" for item in available_endpoints[:80])
        return f"""
Return strict JSON only. Generate 16-24 API tests for this endpoint.
Put positive functional tests first. Cover as many valid combinations as possible: required-only request, full valid request, optional fields, documented query params, filters, sorting, pagination, path IDs, auth headers, valid boundary values, alternate success statuses, and business-valid state transitions.
Then include validation, security, regression, and edge cases. Security cases should include SQLi, IDOR, auth bypass, ORM bypass, malformed payloads, and boundary values where relevant.
Add business-oriented cases when the documentation describes workflows, roles, statuses, limits, or domain rules.
If an endpoint requires workflow setup, include dependency steps. For example, login before cart/checkout, create cart before checkout, create resource before update/delete, cleanup after mutation. Extract values from dependency responses and reference them with {{token}}, {{cartId}}, {{orderId}}, etc.
Never invent dependency endpoints. Use only endpoints listed in the available collection endpoints. If a needed setup endpoint is missing, do not add that dependency; generate a direct test with a clear reasoning note.
Use this exact shape:
{{"endpoint":"METHOD /path","tests":[{{"name":"...","category":"functional|security|edge|regression","severity":"critical|high|medium|low|info","request":{{"method":"...","path":"...","headers":{{}},"query":{{}},"body":{{}},"dependencies":{{"before":[{{"name":"login","method":"POST","path":"/auth/login","headers":{{}},"query":{{}},"body":{{}},"extract":{{"token":"$.token"}}}}],"after":[{{"name":"cleanup","method":"DELETE","path":"/cart/{{cartId}}","headers":{{"Authorization":"Bearer {{token}}"}},"query":{{}},"body":null}}]}}}},"expected":{{"status_codes":[200],"behavior":"..."}},"reasoning":"..."}}]}}

Intensity: {intensity}
{docs_context}
{endpoint_inventory}
Endpoint:
{endpoint.model_dump_json()}
"""

    async def maybe_demo(self, endpoint: EndpointSummary, intensity: str) -> dict | None:
        if self.api_token.lower().startswith("demo"):
            return await DeterministicProvider(self.model, self.api_token, self.custom_base_url).generate_tests(endpoint, intensity)
        return None

    @abstractmethod
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        raise NotImplementedError


class ProviderRateLimitError(RuntimeError):
    pass


class DeterministicProvider(LLMProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        body = endpoint.body if isinstance(endpoint.body, dict) else {}
        valid_query = endpoint.params if isinstance(endpoint.params, dict) else {}
        tests = [
            {
                "name": "Valid primary request",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": endpoint.headers, "query": valid_query, "body": body},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts a representative valid request."},
                "reasoning": "Confirms the documented happy path remains available.",
            },
            {
                "name": "Valid request with required data only",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": endpoint.headers, "query": {}, "body": minimal_body(body)},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts the smallest valid request shape."},
                "reasoning": "Checks the positive path with only required or representative minimal data.",
            },
            {
                "name": "Valid request with full representative payload",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": endpoint.headers, "query": valid_query, "body": enriched_body(body)},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts a complete valid payload."},
                "reasoning": "Covers a richer positive combination with optional-like values included.",
            },
            {
                "name": "Valid pagination query combination",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": endpoint.headers, "query": valid_query | {"page": "1", "limit": "10"}, "body": body},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts normal pagination parameters."},
                "reasoning": "Exercises a common successful list/query variant.",
            },
            {
                "name": "Valid filter and sort query combination",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": endpoint.headers, "query": valid_query | {"sort": "createdAt", "order": "desc"}, "body": body},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts normal filter or sort parameters."},
                "reasoning": "Covers another positive query-parameter combination without invalid input.",
            },
            {
                "name": "Valid path identifier request",
                "category": "functional",
                "severity": "info",
                "request": {"method": endpoint.method, "path": positive_identifier_path(endpoint.path), "headers": endpoint.headers, "query": valid_query, "body": body},
                "expected": {"status_codes": [200, 201, 202, 204], "behavior": "Endpoint accepts a realistic resource identifier."},
                "reasoning": "Covers success behavior for item-specific routes and path parameter replacement.",
            },
            {
                "name": "Missing authentication",
                "category": "security",
                "severity": "high",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": {"Authorization": ""}, "query": {}, "body": body},
                "expected": {"status_codes": [401, 403], "behavior": "Protected endpoint rejects missing credentials."},
                "reasoning": "Checks for auth bypass caused by absent or empty credentials.",
            },
            {
                "name": "SQL injection probe",
                "category": "security",
                "severity": "high",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": {}, "query": {"q": "' OR '1'='1"}, "body": mutate_body(body, "' OR '1'='1")},
                "expected": {"status_codes": [400, 401, 403, 422], "behavior": "Payload is rejected or safely handled."},
                "reasoning": "Looks for classic SQL injection acceptance or unexpected success.",
            },
            {
                "name": "Malformed payload",
                "category": "edge",
                "severity": "low",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": {}, "query": {}, "body": {"malformed": ["unexpected", {"shape": True}]}},
                "expected": {"status_codes": [400, 415, 422], "behavior": "Endpoint validates malformed request bodies."},
                "reasoning": "Exercises request validation and error handling.",
            },
            {
                "name": "IDOR identifier mutation",
                "category": "security",
                "severity": "high",
                "request": {"method": endpoint.method, "path": endpoint.path.replace("{{id}}", "999999").replace(":id", "999999"), "headers": {}, "query": {"id": "999999"}, "body": mutate_body(body, "999999")},
                "expected": {"status_codes": [401, 403, 404], "behavior": "Endpoint does not expose unauthorized resources."},
                "reasoning": "Attempts access to a likely resource identifier outside the user's scope.",
            },
            {
                "name": "Boundary value input",
                "category": "edge",
                "severity": "low",
                "request": {"method": endpoint.method, "path": endpoint.path, "headers": {}, "query": {"limit": "1000000"}, "body": mutate_body(body, "A" * 512)},
                "expected": {"status_codes": [200, 400, 413, 422], "behavior": "Endpoint handles large values predictably."},
                "reasoning": "Checks limits, pagination bounds, and oversized strings.",
            },
        ]
        if intensity == "deep":
            tests.extend(
                [
                    {
                        "name": "ORM bypass object payload",
                        "category": "security",
                        "severity": "high",
                        "request": {"method": endpoint.method, "path": endpoint.path, "headers": {}, "query": {}, "body": mutate_body(body, {"$ne": None})},
                        "expected": {"status_codes": [400, 401, 403, 422], "behavior": "Endpoint rejects query-operator-shaped user input."},
                        "reasoning": "Targets NoSQL/ORM query operator injection patterns.",
                    },
                    {
                        "name": "HTTP method tampering",
                        "category": "security",
                        "severity": "medium",
                        "request": {"method": "PATCH" if endpoint.method != "PATCH" else "DELETE", "path": endpoint.path, "headers": {}, "query": {}, "body": body},
                        "expected": {"status_codes": [400, 401, 403, 405], "behavior": "Unexpected methods are blocked."},
                        "reasoning": "Checks whether alternate verbs expose unintended behavior.",
                    },
                ]
            )
        return {"endpoint": f"{endpoint.method} {endpoint.path}", "tests": tests}


class GeminiProvider(DeterministicProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        demo = await self.maybe_demo(endpoint, intensity)
        if demo:
            return demo
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                url,
                params={"key": self.api_token},
                json={"contents": [{"parts": [{"text": self.prompt(endpoint, intensity, api_docs, available_endpoints)}]}]},
            )
        response.raise_for_status()
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parse_model_json(text)


class GroqProvider(DeterministicProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        demo = await self.maybe_demo(endpoint, intensity)
        if demo:
            return demo
        try:
            return await openai_compatible_chat("https://api.groq.com/openai/v1", self.model, self.api_token, self.prompt(endpoint, intensity, api_docs, available_endpoints))
        except (json.JSONDecodeError, ProviderRateLimitError):
            return await DeterministicProvider(self.model, self.api_token, self.custom_base_url).generate_tests(endpoint, intensity)


class ClaudeProvider(DeterministicProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        demo = await self.maybe_demo(endpoint, intensity)
        if demo:
            return demo
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_token,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": self.prompt(endpoint, intensity, api_docs, available_endpoints)}],
                },
            )
        response.raise_for_status()
        text = response.json()["content"][0]["text"]
        return parse_model_json(text)


class OpenAICompatibleProvider(DeterministicProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        demo = await self.maybe_demo(endpoint, intensity)
        if demo:
            return demo
        base_url = self.custom_base_url or "https://api.openai.com/v1"
        return await openai_compatible_chat(base_url, self.model, self.api_token, self.prompt(endpoint, intensity, api_docs, available_endpoints))


class CustomProvider(DeterministicProvider):
    async def generate_tests(self, endpoint: EndpointSummary, intensity: str, api_docs: str | None = None, available_endpoints: list[EndpointReference] | None = None) -> dict:
        demo = await self.maybe_demo(endpoint, intensity)
        if demo:
            return demo
        if not self.custom_base_url:
            raise ValueError("Custom provider requires custom_base_url")
        return await openai_compatible_chat(self.custom_base_url, self.model, self.api_token, self.prompt(endpoint, intensity, api_docs, available_endpoints))


def get_provider(provider: str, model: str, api_token: str, custom_base_url: str | None = None) -> LLMProvider:
    mapping = {
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "claude": ClaudeProvider,
        "openai-compatible": OpenAICompatibleProvider,
        "codex": OpenAICompatibleProvider,
        "custom": CustomProvider,
    }
    return mapping.get(provider, DeterministicProvider)(model=model, api_token=api_token, custom_base_url=custom_base_url)


def mutate_body(body: dict, value) -> dict:
    if not body:
        return {"input": value}
    clone = json.loads(json.dumps(body))
    first_key = next(iter(clone))
    clone[first_key] = value
    return clone


def minimal_body(body: dict) -> dict:
    if not body:
        return {}
    first_key = next(iter(body))
    return {first_key: body[first_key]}


def enriched_body(body: dict) -> dict:
    if not body:
        return {"name": "AeroAPI Valid Case", "description": "Generated positive test payload"}
    clone = json.loads(json.dumps(body))
    clone.setdefault("description", "Generated positive test payload")
    return clone


def positive_identifier_path(path: str) -> str:
    replacements = {
        "{{id}}": "1",
        ":id": "1",
        "{id}": "1",
        "{{userId}}": "1",
        ":userId": "1",
        "{userId}": "1",
    }
    resolved = path
    for token, value in replacements.items():
        resolved = resolved.replace(token, value)
    return resolved


async def openai_compatible_chat(base_url: str, model: str, api_token: str, prompt: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        payload: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You generate strict JSON for API test cases. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if "api.groq.com" in base_url and model.startswith("qwen/"):
            payload["reasoning_format"] = "hidden"

        response = await post_with_rate_limit_retries(client, url, headers, payload)
        if response.status_code == 400 and payload.get("response_format") == {"type": "json_object"}:
            # Some Groq models can reject JSON Object Mode for a given generation.
            # The prompt still asks for strict JSON, so retry once and parse locally.
            payload.pop("response_format")
            response = await post_with_rate_limit_retries(client, url, headers, payload)
    raise_for_status_with_detail(response)
    content = response.json()["choices"][0]["message"]["content"]
    try:
        return parse_model_json(content)
    except json.JSONDecodeError:
        repaired = await repair_model_json(url, headers, payload, content)
        return parse_model_json(repaired)


async def repair_model_json(url: str, headers: dict, original_payload: dict, malformed_json: str) -> str:
    repair_payload = {
        key: value
        for key, value in original_payload.items()
        if key not in {"messages", "response_format", "temperature"}
    }
    repair_payload.update(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "Repair malformed JSON. Return only valid JSON. Do not add markdown, comments, or explanations.",
                },
                {
                    "role": "user",
                    "content": (
                        "Fix this into valid JSON with this shape: "
                        "{\"endpoint\":\"METHOD /path\",\"tests\":[{\"name\":\"...\",\"category\":\"functional|security|edge|regression\","
                        "\"severity\":\"critical|high|medium|low|info\",\"request\":{\"method\":\"...\",\"path\":\"...\","
                        "\"headers\":{},\"query\":{},\"body\":{}},\"expected\":{\"status_codes\":[200],\"behavior\":\"...\"},"
                        "\"reasoning\":\"...\"}]}.\n\n"
                        f"Malformed JSON:\n{malformed_json}"
                    ),
                },
            ],
            "temperature": 0,
        }
    )
    if original_payload.get("response_format"):
        repair_payload["response_format"] = original_payload["response_format"]
    async with httpx.AsyncClient(timeout=60) as client:
        response = await post_with_rate_limit_retries(client, url, headers, repair_payload)
    raise_for_status_with_detail(response)
    return response.json()["choices"][0]["message"]["content"]


async def post_with_rate_limit_retries(client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> httpx.Response:
    response = await client.post(url, headers=headers, json=payload)
    for _ in range(2):
        if response.status_code != 429:
            return response
        retry_after = parse_retry_after(response)
        await asyncio.sleep(min(retry_after, 8))
        response = await client.post(url, headers=headers, json=payload)
    return response


def parse_retry_after(response: httpx.Response) -> float:
    header_value = response.headers.get("retry-after")
    if header_value:
        try:
            return float(header_value)
        except ValueError:
            pass
    match = re.search(r"try again in ([0-9.]+)s", response.text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 5.0


def raise_for_status_with_detail(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text.strip()
        try:
            parsed = response.json()
            error = parsed.get("error", parsed)
            if isinstance(error, dict) and error.get("message"):
                detail = error["message"]
        except ValueError:
            pass
        message = f"{response.status_code} {response.reason_phrase}: {detail}"
        if response.status_code == 429:
            raise ProviderRateLimitError(message) from exc
        raise RuntimeError(message) from exc


def parse_model_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end >= start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)
