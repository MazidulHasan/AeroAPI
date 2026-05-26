# 05. Administrative Tasks & Security

**Collection Section:** `05. Administrative Tasks & Security`
**Source:** `Practice_API_Collection.json`

This section validates **Role-Based Access Control (RBAC)**. It tests that admin-only endpoints correctly deny access to regular users and grant access to admin users. Both the positive and negative paths hit the same endpoint with different tokens.

---

## Endpoints

### 1. Negative: Regular User Attempts Admin Action

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/admin/users` |
| **Auth** | `Bearer {{accessToken}}` (regular user token) |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

> This uses the **regular user's** `accessToken`, not the admin token — this is intentional.

#### Expected Response — `403 Forbidden`

```json
{
  "error": {
    "code": "FORBIDDEN"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 403 | Role check enforcement — user role is insufficient |
| `error.code` is `"FORBIDDEN"` | Standard RBAC error schema |

#### Dependencies

- **Requires:** `accessToken` (section 01, Login Dynamic User — a regular non-admin user)
- **Produces:** Nothing
- **Note:** The test intentionally uses a valid token — it is testing authorization (role), not authentication (identity). A `401` here would indicate the token is invalid, which would be a different failure.

---

### 2. Admin Action: Get All Users

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/admin/users` |
| **Auth** | `Bearer {{adminAccessToken}}` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{adminAccessToken}}` |

#### Expected Response — `200 OK`

```json
[
  {
    "id": "<string>",
    "email": "<string>",
    "firstName": "<string>",
    "lastName": "<string>",
    "role": "<string>"
  }
]
```

Response is an **array** of user objects.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Admin access granted |
| Response is an array | Data structure check |
| `password` field absent from user objects | Security: no sensitive field leakage |

#### Dependencies

- **Requires:** `adminAccessToken` (section 01, Validate Admin Login)
- **Produces:** Nothing
- **Note:** The `password` field check mirrors the one in section 02 (`GET /users/me`) — both endpoints must omit password data regardless of caller privilege level.

---

## Section Dependency Map

```
[Section 01: Login Dynamic User]
        │  sets: accessToken (regular user)
        ▼
GET /admin/users (with accessToken) ────────────────────────► 403 Forbidden (FORBIDDEN)

[Section 01: Validate Admin Login]
        │  sets: adminAccessToken
        ▼
GET /admin/users (with adminAccessToken) ───────────────────► 200 OK (array of users, no passwords)
```

---

## RBAC Matrix

| Endpoint | Regular User (`accessToken`) | Admin (`adminAccessToken`) |
|----------|------------------------------|---------------------------|
| `GET /users/me` | 200 OK | N/A (tested in section 02) |
| `POST /products` | (not tested — implied 403) | 201 Created |
| `GET /admin/users` | 403 Forbidden | 200 OK |

---

## Security Considerations

- **401 vs 403 distinction:** The test explicitly expects `403` (not `401`) when a regular user hits an admin endpoint. The server must differentiate between "not authenticated" (`401`) and "authenticated but not authorized" (`403`).
- **Password field in admin responses:** Even admin users should not receive raw or hashed passwords through the REST API. The assertion `pm.expect(jsonData[0]).to.not.have.property('password')` enforces this.
- **Token segregation:** The test suite maintains two separate token variables (`accessToken` for users, `adminAccessToken` for admins) to allow precise RBAC testing without cross-contamination.
