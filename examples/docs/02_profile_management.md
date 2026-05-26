# 02. Profile Management

**Collection Section:** `02. Profile Management`
**Source:** `Practice_API_Collection.json`

This section covers reading the authenticated user's own profile. It validates both the happy path (valid token) and the negative path (missing token), ensuring the API correctly enforces authentication and does not leak sensitive data.

---

## Endpoints

### 1. Get Profile Validation

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/users/me` |
| **Auth** | `Bearer {{accessToken}}` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

#### Expected Response — `200 OK`

```json
{
  "email": "{{dynamicEmail}}",
  "firstName": "{{dynamicFirstName}}",
  "lastName": "{{dynamicLastName}}"
}
```

> **Security Note:** The `password` field must NOT be present in this response.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `email` matches `dynamicEmail` | Validates data round-trip from registration |
| `firstName` matches `dynamicFirstName` | Validates data round-trip from registration |
| `lastName` matches `dynamicLastName` | Validates data round-trip from registration |
| `password` field is absent | Security: no sensitive data exposure |

#### Dependencies

- **Requires:** `accessToken` (set by Login Dynamic User in section 01)
- **Requires:** `dynamicEmail`, `dynamicFirstName`, `dynamicLastName` (set by Register in section 01)
- **Produces:** Nothing
- **Depends on:** Section 01 — Authentication Flow (both Register and Login must run first)

---

### 2. Negative: Access Profile Without Token

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/users/me` |
| **Auth** | None (intentionally omitted) |

#### Request Headers

None — this test deliberately sends **no Authorization header**.

#### Expected Response — `401 Unauthorized`

```json
{
  "error": {
    "code": "UNAUTHORIZED"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 401 | `response.status === 401` |
| `error.code` is `"UNAUTHORIZED"` | Standard error schema enforced |

#### Dependencies

- **Requires:** Nothing (negative test — no token needed)
- **Produces:** Nothing
- **Note:** This is a standalone negative test that can run at any time. It does not depend on prior steps.

---

## Section Dependency Map

```
[Section 01: Register New Dynamic User]
        │  sets: dynamicEmail, dynamicFirstName, dynamicLastName
        ▼
[Section 01: Login Dynamic User]
        │  sets: accessToken
        ▼
GET /users/me ──────────────────────────────► 200 OK (profile data matches registration)

GET /users/me (no token) ───────────────────► 401 Unauthorized (UNAUTHORIZED error code)
```

---

## Security Considerations

- The `GET /users/me` endpoint must never return the `password` field (even hashed).
- The `UNAUTHORIZED` error response must consistently use the `{ "error": { "code": "UNAUTHORIZED" } }` schema — any deviation means inconsistent error handling.
- This endpoint is scoped to the authenticated user (`/me`) — it should not accept a user ID parameter to prevent IDOR (Insecure Direct Object Reference).
