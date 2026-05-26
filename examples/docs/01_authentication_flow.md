# 01. Authentication Flow

**Collection Section:** `01. Authentication Flow`
**Source:** `Practice_API_Collection.json` + `Reg.postman_collection.json`

This section covers user registration and login for both regular and admin users. It is the **root of the entire dependency chain** — all protected endpoints in sections 02–05 require tokens produced here.

---

## Endpoints

### 1. Register New Dynamic User

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/auth/register` |
| **Auth** | None |
| **Content-Type** | `application/json` |

#### Pre-request Script (Automation)

Before the request fires, the following environment variables are **auto-generated**:

| Variable | Generated Value |
|----------|----------------|
| `dynamicEmail` | `user_<UUID>@practice.com` |
| `dynamicPassword` | `Pass123!<randomInt>` |
| `dynamicFirstName` | Random first name |
| `dynamicLastName` | Random last name |

#### Request Body

```json
{
  "email": "{{dynamicEmail}}",
  "password": "{{dynamicPassword}}",
  "firstName": "{{dynamicFirstName}}",
  "lastName": "{{dynamicLastName}}"
}
```

#### Expected Response — `201 Created`

```json
{
  "message": "User created successfully",
  "userId": "<string>",
  "createdAt": "<ISO timestamp>"
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | `response.status === 201` |
| `message` equals `"User created successfully"` | Exact match |
| `userId` is present | Property exists |
| `createdAt` is present | Property exists |
| Response time < 1000ms | Performance check |

#### Dependencies

- **Produces:** `dynamicEmail`, `dynamicPassword`, `dynamicFirstName`, `dynamicLastName`
- **Required by:** Login Dynamic User, Get Profile Validation
- **Depends on:** Nothing (entry point)

---

### 2. Login Dynamic User

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/auth/login` |
| **Auth** | None |
| **Content-Type** | `application/json` |

#### Request Body

```json
{
  "email": "{{dynamicEmail}}",
  "password": "{{dynamicPassword}}"
}
```

#### Expected Response — `200 OK`

```json
{
  "accessToken": "<JWT>",
  "refreshToken": "<JWT>",
  "tokenType": "Bearer",
  "user": {
    "email": "{{dynamicEmail}}"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `accessToken` present | Property exists |
| `refreshToken` present | Property exists |
| `tokenType` is `"Bearer"` | Exact match |
| `user.email` matches `dynamicEmail` | Validates registration round-trip |

#### Post-response Script (Token Capture)

```js
pm.environment.set("accessToken", jsonData.accessToken);
pm.environment.set("refreshToken", jsonData.refreshToken);
```

#### Dependencies

- **Requires:** `dynamicEmail`, `dynamicPassword` (set by Register step)
- **Produces:** `accessToken`, `refreshToken`
- **Required by:** Profile Management (02), Cart/Checkout/Orders (04)

---

### 3. Validate Admin Login

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/auth/login` |
| **Auth** | None |
| **Content-Type** | `application/json` |

#### Request Body

```json
{
  "email": "admin@practice.com",
  "password": "password123"
}
```

> **Note:** Uses hardcoded credentials for the seeded admin account — not dynamically generated.

#### Expected Response — `200 OK`

```json
{
  "accessToken": "<JWT>",
  "user": {
    "role": "admin"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `user.role` is `"admin"` | Validates admin role in JWT claims |

#### Post-response Script (Admin Token Capture)

```js
pm.environment.set("adminAccessToken", jsonData.accessToken);
```

#### Dependencies

- **Requires:** Seeded admin account (`admin@practice.com`) to exist in the database
- **Produces:** `adminAccessToken`
- **Required by:** Create Product (03), Admin: Get All Users (05)

---

## Section Dependency Map

```
[Pre-request script]
        │
        ▼ (sets dynamicEmail, dynamicPassword, dynamicFirstName, dynamicLastName)
Register New Dynamic User ──────────────────────────────────► [DB: user record created]
        │
        ▼ (uses dynamicEmail + dynamicPassword)
Login Dynamic User ─────────────────────────────────────────► sets accessToken, refreshToken
        │
Validate Admin Login (independent — uses hardcoded creds) ──► sets adminAccessToken
```
