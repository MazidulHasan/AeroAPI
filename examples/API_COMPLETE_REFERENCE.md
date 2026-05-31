# Practice API — Complete Reference

**Collection:** Practice API Advanced Test Suite
**Base URL:** `http://localhost:3000`
**Auth Scheme:** Bearer JWT (`Authorization: Bearer <token>`)
**Source Files:** `postman/Practice_API_Collection.json`, `postman/Reg.postman_collection.json`

---

## Table of Contents

1. [Quick Start & Execution Order](#1-quick-start--execution-order)
2. [Environment Variables Reference](#2-environment-variables-reference)
3. [Section 01 — Authentication Flow](#3-section-01--authentication-flow)
4. [Section 02 — Profile Management](#4-section-02--profile-management)
5. [Section 03 — Data & Product Workflows](#5-section-03--data--product-workflows)
6. [Section 04 — E2E Checkout Flow](#6-section-04--e2e-checkout-flow)
7. [Section 05 — Administrative Tasks & Security](#7-section-05--administrative-tasks--security)
8. [Global Dependency Map](#8-global-dependency-map)
9. [RBAC Matrix](#9-rbac-matrix)
10. [Error Code Reference](#10-error-code-reference)
11. [Most Complex Dependency Analysis](#11-most-complex-dependency-analysis)
12. [Common Failure Scenarios (All Sections)](#12-common-failure-scenarios-all-sections)

---

## 1. Quick Start & Execution Order

Run all requests in this exact order for the full happy-path suite to pass:

```
[01.1]  POST   /auth/register        ← pre-request script auto-generates user data
[01.2]  POST   /auth/login           ← uses 01.1 credentials → sets accessToken
[01.3]  POST   /auth/login           ← hardcoded admin creds  → sets adminAccessToken
[02.1]  GET    /users/me             ← needs accessToken (01.2)
[02.2]  GET    /users/me             ← negative test, no token
[03.1]  GET    /products             ← public, no auth
[03.2]  POST   /products             ← needs adminAccessToken (01.3) → sets customProductId
[03.3]  POST   /products             ← negative test, needs adminAccessToken
[04.1]  DELETE /cart                 ← needs accessToken (01.2)
[04.2]  POST   /cart                 ← needs accessToken + customProductId (03.2)
[04.3]  POST   /checkout             ← needs accessToken + non-empty cart → sets latestOrderId
[04.4]  GET    /orders               ← needs accessToken + latestOrderId (04.3)
[05.1]  GET    /admin/users          ← negative test, needs regular accessToken
[05.2]  GET    /admin/users          ← needs adminAccessToken (01.3)
```

> **System prerequisites before running anything:**
> - API server running at `http://localhost:3000`
> - Database accessible and migrations run
> - Admin account `admin@practice.com` / `password123` / role `admin` seeded in DB
> - At least 1 product seeded in DB (for 03.1 ID extraction)

---

## 2. Environment Variables Reference

| Variable | Type | Set By | Consumed By | Notes |
|----------|------|--------|-------------|-------|
| `baseUrl` | default | Static config | All requests | Default: `http://localhost:3000` |
| `dynamicEmail` | default | Pre-request script — 01.1 | 01.2 body, 02.1 assertion | Format: `user_<UUID>@practice.com` |
| `dynamicPassword` | default | Pre-request script — 01.1 | 01.2 body | Format: `Pass123!<int>` |
| `dynamicFirstName` | default | Pre-request script — 01.1 | 02.1 assertion | Random first name |
| `dynamicLastName` | default | Pre-request script — 01.1 | 02.1 assertion | Random last name |
| `accessToken` | secret | Post-response script — 01.2 | 02.1, 04.1, 04.2, 04.3, 04.4, 05.1 | Short-lived JWT for regular user |
| `refreshToken` | secret | Post-response script — 01.2 | (reserved) | Not used in further tests |
| `adminAccessToken` | secret | Post-response script — 01.3 | 03.2, 03.3, 05.2 | JWT with `role: admin` claim |
| `dynamicProductName` | default | Pre-request script — 03.2 | 03.2 body and assertion | Format: `Automated Product <UUID>` |
| `firstProductId` | default | Post-response script — 03.1 | Available, not used in suite | First product from paginated list |
| `customProductId` | default | Post-response script — 03.2 | 04.2 body and assertion | ID of the admin-created product |
| `latestOrderId` | default | Post-response script — 04.3 | 04.4 assertion | ID of the checked-out order |

---

## 3. Section 01 — Authentication Flow

This section is the **root of the entire test suite**. No protected endpoint in any other section works without the tokens produced here.

---

### [01.1] POST /auth/register — Register New Dynamic User

#### Call Chain — Required API Sequence

> This is the **entry point**. No prior API calls are needed.
>
> A **pre-request script** runs automatically before the HTTP call and generates all required credentials:

```
[Pre-request script fires automatically]
   └─ generates: dynamicEmail, dynamicPassword, dynamicFirstName, dynamicLastName
          │
          ▼
✅ [01.1]  POST /auth/register        ← YOU ARE HERE
```

| Step | Action | What It Gives You |
|------|--------|-------------------|
| Pre-request (auto) | Script generates user data | `dynamicEmail`, `dynamicPassword`, `dynamicFirstName`, `dynamicLastName` |
| ✅ **This request** | `POST /auth/register` | User account created in DB |

---

#### Request

```
POST {{baseUrl}}/auth/register
Content-Type: application/json
```

```json
{
  "email":     "{{dynamicEmail}}",
  "password":  "{{dynamicPassword}}",
  "firstName": "{{dynamicFirstName}}",
  "lastName":  "{{dynamicLastName}}"
}
```

#### Request Body Schema

| Field | Type | Required | Constraint |
|-------|------|----------|------------|
| `email` | string | Yes | Valid email format, must be unique in DB |
| `password` | string | Yes | `Pass123!<int>` pattern |
| `firstName` | string | Yes | Non-empty string |
| `lastName` | string | Yes | Non-empty string |

#### Expected Response — `201 Created`

```json
{
  "message":   "User created successfully",
  "userId":    "<string>",
  "createdAt": "<ISO 8601 timestamp>"
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | `response.status === 201` |
| `message` = `"User created successfully"` | Exact match |
| `userId` present | Property exists |
| `createdAt` present | Property exists |
| Response time < 1000ms | Performance check |

**Produces:** `dynamicEmail`, `dynamicPassword`, `dynamicFirstName`, `dynamicLastName`

---

### [01.2] POST /auth/login — Login Dynamic User

#### Call Chain — Required API Sequence

> You must call `POST /auth/register` first so the user account exists in the DB and the credentials (`dynamicEmail`, `dynamicPassword`) are in the environment.

```
[Pre-request script fires automatically on 01.1]
   └─ generates: dynamicEmail, dynamicPassword
          │
          ▼
[01.1]  POST /auth/register        → creates user in DB
          │
          ▼
✅ [01.2]  POST /auth/login          ← YOU ARE HERE
             └─ sets: accessToken, refreshToken
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicPassword` |
| 2 | `POST` | `/auth/register` | User account in DB |
| ✅ **3** | `POST` | `/auth/login` | `accessToken`, `refreshToken` |

---

#### Request

```
POST {{baseUrl}}/auth/login
Content-Type: application/json
```

```json
{
  "email":    "{{dynamicEmail}}",
  "password": "{{dynamicPassword}}"
}
```

#### Expected Response — `200 OK`

```json
{
  "accessToken":  "<JWT>",
  "refreshToken": "<JWT>",
  "tokenType":    "Bearer",
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
| `tokenType` = `"Bearer"` | Exact match |
| `user.email` = `dynamicEmail` | Round-trip validation from registration |

**Post-response script (Token Capture):**
```js
pm.environment.set("accessToken",  jsonData.accessToken);
pm.environment.set("refreshToken", jsonData.refreshToken);
```

**Produces:** `accessToken`, `refreshToken`

---

### [01.3] POST /auth/login — Validate Admin Login

#### Call Chain — Required API Sequence

> No prior API calls needed. Uses **hardcoded** credentials for the seeded admin account. The only prerequisite is the DB seed.

```
[System: DB must have admin@practice.com seeded with role:admin]
          │
          ▼
✅ [01.3]  POST /auth/login (admin creds)   ← YOU ARE HERE
             └─ sets: adminAccessToken
```

| Step | Action | What It Gives You |
|------|--------|-------------------|
| System prereq | Admin account seeded in DB | — |
| ✅ **This request** | `POST /auth/login` with `admin@practice.com` | `adminAccessToken` |

---

#### Request

```
POST {{baseUrl}}/auth/login
Content-Type: application/json
```

```json
{
  "email":    "admin@practice.com",
  "password": "password123"
}
```

> **Note:** These are hardcoded seed credentials — not dynamically generated.

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
| `user.role` = `"admin"` | Admin role verified in response |

**Post-response script (Admin Token Capture):**
```js
pm.environment.set("adminAccessToken", jsonData.accessToken);
```

**Produces:** `adminAccessToken`

---

## 4. Section 02 — Profile Management

---

### [02.1] GET /users/me — Get Profile Validation

#### Call Chain — Required API Sequence

> To read a profile, a user must first exist (register) and be logged in (login). The assertions also compare response data against values generated at registration time, so all three steps below are required.

```
[Pre-request script fires automatically on 01.1]
   └─ generates: dynamicEmail, dynamicFirstName, dynamicLastName
          │
          ▼
[01.1]  POST /auth/register        → creates user in DB
          │
          ▼
[01.2]  POST /auth/login           → sets: accessToken
          │
          ▼
✅ [02.1]  GET /users/me             ← YOU ARE HERE
             └─ asserts email, firstName, lastName match registration data
             └─ asserts password field is NOT in response
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicFirstName`, `dynamicLastName` |
| 2 | `POST` | `/auth/register` | User account in DB |
| 3 | `POST` | `/auth/login` | `accessToken` |
| ✅ **4** | `GET` | `/users/me` | Profile data (asserted against registration values) |

---

#### Request

```
GET {{baseUrl}}/users/me
Authorization: Bearer {{accessToken}}
```

#### Expected Response — `200 OK`

```json
{
  "email":     "user_abc@practice.com",
  "firstName": "Sarah",
  "lastName":  "Mitchell"
}
```

> **Security:** The `password` field must **not** be present in this response, even as a hash.

#### Response Field Reference

| Field | Type | Constraint |
|-------|------|------------|
| `email` | string | Must match `dynamicEmail` |
| `firstName` | string | Must match `dynamicFirstName` |
| `lastName` | string | Must match `dynamicLastName` |
| `password` | — | Must NOT be present |

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `email` = `dynamicEmail` | Data round-trip from registration |
| `firstName` = `dynamicFirstName` | Data round-trip from registration |
| `lastName` = `dynamicLastName` | Data round-trip from registration |
| `password` field absent | Security — must not expose password |

**Produces:** Nothing

---

### [02.2] GET /users/me — Negative: Access Without Token

#### Call Chain — Required API Sequence

> This is a **standalone negative test**. No prior API calls needed. The test deliberately omits the auth header to verify the endpoint rejects unauthenticated requests.

```
[No prior API calls required]
          │
          ▼
✅ [02.2]  GET /users/me  (no Authorization header)   ← YOU ARE HERE
             └─ expects: 401 UNAUTHORIZED
```

| Step | Action | What It Gives You |
|------|--------|-------------------|
| ✅ **This request** | `GET /users/me` with no token | Proves endpoint rejects unauthenticated access |

---

#### Request

```
GET {{baseUrl}}/users/me
(no Authorization header — intentionally omitted)
```

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
| Status is 401 | Authentication required |
| `error.code` = `"UNAUTHORIZED"` | Standard error schema |

---

## 5. Section 03 — Data & Product Workflows

---

### [03.1] GET /products — Get All Products with Pagination

#### Call Chain — Required API Sequence

> This is a **public endpoint** — no auth needed. The only requirement is that the database has at least 1 product seeded.

```
[System: DB must have at least 1 product seeded]
          │
          ▼
✅ [03.1]  GET /products?page=1&limit=5   ← YOU ARE HERE
             └─ sets: firstProductId (from first result)
```

| Step | Action | What It Gives You |
|------|--------|-------------------|
| System prereq | At least 1 product in DB | — |
| ✅ **This request** | `GET /products` | `firstProductId` |

---

#### Request

```
GET {{baseUrl}}/products?page=1&limit=5
```

#### Query Parameters

| Param | Value | Description |
|-------|-------|-------------|
| `page` | `1` | Page number, 1-indexed |
| `limit` | `5` | Max results per page |

#### Expected Response — `200 OK`

```json
{
  "data": [
    { "id": "prod_abc", "name": "Sample Product", "price": 29.99, "category": "Electronics", "stock": 50 }
  ],
  "page":  1,
  "limit": 5,
  "total": 12
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `limit` = `5` | Pagination honoured |
| `data.length <= 5` | Limit enforced server-side |
| `data[0].id` captured as `firstProductId` | DB has at least 1 product |

**Post-response script:**
```js
pm.environment.set("firstProductId", jsonData.data[0].id);
```

**Produces:** `firstProductId`

---

### [03.2] POST /products — Create Product using Admin

#### Call Chain — Required API Sequence

> Creating a product requires an admin JWT. You must first log in as admin. A pre-request script also runs automatically to generate a unique product name.

```
[System: DB has admin@practice.com seeded]
          │
          ▼
[01.3]  POST /auth/login (admin)   → sets: adminAccessToken
          │
          ▼
[Pre-request script fires automatically]
   └─ generates: dynamicProductName = "Automated Product <UUID>"
          │
          ▼
✅ [03.2]  POST /products            ← YOU ARE HERE
             └─ sets: customProductId
             └─ price locked at 149.99 (used in checkout total calculation)
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | `POST` | `/auth/login` (admin creds) | `adminAccessToken` |
| 2 | Pre-request script (auto) | — | `dynamicProductName` |
| ✅ **3** | `POST` | `/products` | `customProductId` (product in DB at price `149.99`) |

---

#### Request

```
POST {{baseUrl}}/products
Authorization: Bearer {{adminAccessToken}}
Content-Type: application/json
```

```json
{
  "name":        "{{dynamicProductName}}",
  "price":       149.99,
  "category":    "Electronics",
  "stock":       10,
  "description": "An amazing QA creation"
}
```

#### Request Body Schema

| Field | Type | Required | Value | Note |
|-------|------|----------|-------|------|
| `name` | string | Yes | `dynamicProductName` | UUID suffix prevents name collision |
| `price` | number | Yes | `149.99` | **Hard-coded** — checkout in 04.3 asserts `149.99 × 2 = 299.98` |
| `category` | string | Yes | `"Electronics"` | — |
| `stock` | integer | Yes | `10` | Checkout adds qty `2` — well within stock |
| `description` | string | No | `"An amazing QA creation"` | — |

#### Expected Response — `201 Created`

```json
{
  "product": {
    "id":          "prod_xyz789",
    "name":        "Automated Product ...",
    "price":       149.99,
    "category":    "Electronics",
    "stock":       10,
    "description": "An amazing QA creation"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | `response.status === 201` |
| `product.name` = `dynamicProductName` | Data integrity check |
| `product.price` = `149.99` | Price stored correctly |
| `product.id` captured as `customProductId` | — |

**Post-response script:**
```js
pm.environment.set("customProductId", jsonData.product.id);
```

**Produces:** `customProductId`

---

### [03.3] POST /products — Negative: Invalid Schema

#### Call Chain — Required API Sequence

> Even though this test sends an invalid body, admin auth is still required — the server checks authentication **before** it validates the request body. Without a valid admin token, the server returns `401` instead of the expected `422`.

```
[System: DB has admin@practice.com seeded]
          │
          ▼
[01.3]  POST /auth/login (admin)   → sets: adminAccessToken
          │
          ▼
✅ [03.3]  POST /products (invalid body)   ← YOU ARE HERE
             └─ expects: 422 VALIDATION_ERROR
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | `POST` | `/auth/login` (admin creds) | `adminAccessToken` (to pass auth layer) |
| ✅ **2** | `POST` | `/products` with invalid body | Proves validation runs and rejects bad payloads |

---

#### Request

```
POST {{baseUrl}}/products
Authorization: Bearer {{adminAccessToken}}
Content-Type: application/json
```

```json
{
  "name": "No Price Or Category Provided"
}
```

**Missing required fields:** `price`, `category`, `stock`

#### Expected Response — `422 Unprocessable Entity`

```json
{
  "error": {
    "code": "VALIDATION_ERROR"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 422 | Validation enforced before persistence |
| `error.code` = `"VALIDATION_ERROR"` | Standard validation error schema |

---

## 6. Section 04 — E2E Checkout Flow

This section orchestrates a **4-step sequential workflow**: clear cart → add product → checkout → verify order. Every step depends on the previous one's side effects. The section has two distinct call chain perspectives documented for each endpoint:

- **Basic Flow** — the minimum steps any real user needs to call this endpoint successfully
- **This Test Suite's Automation Flow** — the full automated path from the Postman collection, which uses a dynamically registered user and an admin-created product

> **For LLM test case generation:** Use the Basic Flow to generate standard user-journey tests. Use the Automation Flow to understand what state this specific test collection builds before each call.

---

### Section 04 — Basic Flow Overview

The simplest real-world path through this entire section is:

```
Step 1 — Login
   POST /auth/login
   → gives you: accessToken

Step 2 — Get a product ID (so you know what to add to cart)
   GET /products
   → gives you: a productId from the catalogue

Step 3 — Add the product to your cart
   POST /cart   { set only one productId from previous response , quantity }
   → side effect: cart now has items

Step 4 — Checkout
   POST /checkout
   → gives you: orderId, amount, status

Step 5 — Verify your order
   GET /orders
   → confirms the order appears in history
```

> The **DELETE /cart** step (04.1) is a **test isolation guard**, not part of the real user journey. A real user does not clear their cart before shopping — this step only exists to prevent leftover test data from corrupting the `amount` assertion.

---

### [04.1] DELETE /cart — Clear Pre-existing Cart

#### What This Step Does

Clears all items from the authenticated user's cart. This is a **test isolation step**, not a normal user action. Its sole purpose is to guarantee the cart is empty before items are added in 04.2, so the checkout total in 04.3 is deterministic.

---

#### Basic Flow — Minimum Steps to Call This Endpoint

> You only need to be logged in. Any valid user account works.

```
POST /auth/login   →  get accessToken
        │
        ▼
✅  DELETE /cart    ←  YOU ARE HERE
        └─ requires: accessToken
        └─ side effect: cart is empty
```

| Step | Method | Endpoint | Body / Params | What It Gives You |
|------|--------|----------|---------------|-------------------|
| 1 | `POST` | `/auth/login` | `{ email, password }` | `accessToken` |
| ✅ **2** | `DELETE` | `/cart` | — | Cart is cleared |

---

#### This Test Suite's Automation Flow

> The test suite uses a dynamically created user (registered in 01.1, logged in in 01.2) rather than a pre-existing account.

```
[Pre-request script — auto]
   └─ generates: dynamicEmail, dynamicPassword
          │
          ▼
POST /auth/register   →  user account created in DB
          │
          ▼
POST /auth/login      →  sets: accessToken
          │
          ▼
✅  DELETE /cart       ← YOU ARE HERE
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicPassword` |
| 2 | `POST` | `/auth/register` | User account in DB |
| 3 | `POST` | `/auth/login` | `accessToken` |
| ✅ **4** | `DELETE` | `/cart` | Empty cart (clean state for 04.2) |

---

#### Request

```
DELETE {{baseUrl}}/cart
Authorization: Bearer {{accessToken}}
```

#### Expected Response — `200 OK`

No specific body structure asserted — only the status code is checked.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Cart cleared successfully |

**Side effect:** The authenticated user's cart is now empty. All subsequent `POST /cart` calls start from a clean state.

---

### [04.2] POST /cart — Add Product to Cart

#### What This Step Does

Adds a product (by ID) at a specified quantity to the authenticated user's cart. The product must already exist in the database. In the test suite, the product is created by the admin in section 03. In a basic flow, you obtain a product ID from `GET /products`.

---

#### Basic Flow — Minimum Steps to Call This Endpoint

> You need a logged-in user and a valid product ID. Use `GET /products` to discover an available product ID if you don't already have one.

```
POST /auth/login   →  get accessToken
        │
        ▼
GET /products      →  get a productId from the catalogue
        │
        ▼
✅  POST /cart      ←  YOU ARE HERE
        └─ body: { productId, quantity }
        └─ requires: accessToken + a valid productId
        └─ side effect: item added to cart
```

| Step | Method | Endpoint | Body / Params | What It Gives You |
|------|--------|----------|---------------|-------------------|
| 1 | `POST` | `/auth/login` | `{ email, password }` | `accessToken` |
| 2 | `GET` | `/products` | `?page=1&limit=5` | A valid `productId` from the catalogue |
| ✅ **3** | `POST` | `/cart` | `{ productId, quantity: 2 }` | Cart populated with chosen product |

> **Note:** `GET /products` is optional if you already know a valid `productId`. But if generating test cases from scratch, always fetch products first to get a real ID.

---

#### This Test Suite's Automation Flow

> The test suite creates its own product (via admin) to control the exact price (`149.99`), which is needed for the hard-coded total assertion (`299.98`) in 04.3. It also clears the cart first (04.1) to prevent stale data.

```
[Pre-request script — auto on 01.1]
   └─ generates: dynamicEmail, dynamicPassword
          │
          ▼
POST /auth/register          →  user in DB
          │
          ▼
POST /auth/login             →  sets: accessToken
          │
          ├─────────────────────────────────────────┐
          │                                         ▼
          │                          POST /auth/login (admin@practice.com)
          │                              →  sets: adminAccessToken
          │                                         │
          │                          [Pre-request script — auto on 03.2]
          │                              └─ generates: dynamicProductName
          │                                         │
          │                          POST /products →  sets: customProductId
          │                                              price locked at 149.99
          │◄────────────────────────────────────────┘
          ▼
DELETE /cart                 →  cart cleared (test isolation)
          │
          ▼
✅  POST /cart                ←  YOU ARE HERE
        └─ body: { productId: customProductId, quantity: 2 }
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicPassword` |
| 2 | `POST` | `/auth/register` | User account in DB |
| 3 | `POST` | `/auth/login` (dynamic user) | `accessToken` |
| 4 | `POST` | `/auth/login` (admin) | `adminAccessToken` |
| 5 | Pre-request script (auto) | — | `dynamicProductName` |
| 6 | `POST` | `/products` | `customProductId` (price: `149.99`) |
| 7 | `DELETE` | `/cart` | Empty cart |
| ✅ **8** | `POST` | `/cart` | Cart has `customProductId × 2` |

---

#### Request

```
POST {{baseUrl}}/cart
Authorization: Bearer {{accessToken}}
Content-Type: application/json
```

```json
{
  "productId": "{{customProductId}}",
  "quantity":  2
}
```

#### Request Body Schema

| Field | Type | Required | Value | Constraint |
|-------|------|----------|-------|------------|
| `productId` | string | Yes | A valid product ID from the DB | Product must exist — use `GET /products` to retrieve IDs |
| `quantity` | integer | Yes | `2` in this test | Must be `2` in this suite — `149.99 × 2 = 299.98` is asserted in 04.3 |

#### Expected Response — `200 OK`

```json
{
  "cart": {
    "items": [
      { "productId": "prod_xyz789", "quantity": 2 }
    ]
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Item added to cart |
| Cart contains item where `productId === customProductId` | Correct product in cart |
| `item.quantity` = `2` | Correct quantity stored |

**Side effect:** Cart now contains `customProductId` at quantity `2` (total value: `$149.99 × 2 = $299.98`).

---

### [04.3] POST /checkout — Checkout Order

#### What This Step Does

Converts the authenticated user's current cart into a confirmed order. There is **no request body** — the server reads the cart state directly. Returns an `orderId`, the computed `amount`, and a `status` of `"confirmed"`.

---

#### Basic Flow — Minimum Steps to Call This Endpoint

> You need to be logged in and have at least one item in your cart. That's all. The total is computed from whatever is in the cart at the time of checkout.

```
POST /auth/login   →  get accessToken
        │
        ▼
GET /products      →  get a productId
        │
        ▼
POST /cart         →  add item to cart  { productId, quantity }
        │              side effect: cart is non-empty
        ▼
✅  POST /checkout  ←  YOU ARE HERE
        └─ no body — reads cart from server state
        └─ requires: accessToken + non-empty cart
        └─ returns: orderId, amount, status: "confirmed"
```

| Step | Method | Endpoint | Body / Params | What It Gives You |
|------|--------|----------|---------------|-------------------|
| 1 | `POST` | `/auth/login` | `{ email, password }` | `accessToken` |
| 2 | `GET` | `/products` | `?page=1&limit=5` | A valid `productId` |
| 3 | `POST` | `/cart` | `{ productId, quantity }` | Cart is non-empty |
| ✅ **4** | `POST` | `/checkout` | — (no body) | `orderId`, `amount`, `status: "confirmed"` |

> **If cart is empty when checkout is called:** The API will either return an error (e.g., `400 Bad Request`) or create a `$0` order, depending on server implementation. Always ensure at least one item is in the cart before calling checkout.

---

#### This Test Suite's Automation Flow

> The test suite hard-codes `price: 149.99` and `quantity: 2` so the `amount` assertion (`299.98`) is deterministic. The cart is also explicitly cleared before adding items to prevent leftover state from previous runs.

```
[Pre-request script — auto on 01.1]
   └─ generates: dynamicEmail, dynamicPassword
          │
          ▼
POST /auth/register          →  user in DB
          │
          ▼
POST /auth/login             →  sets: accessToken
          │
          ├─────────────────────────────────────────┐
          │                                         ▼
          │                          POST /auth/login (admin)
          │                              →  sets: adminAccessToken
          │                                         │
          │                          POST /products →  sets: customProductId
          │                                              price locked at 149.99
          │◄────────────────────────────────────────┘
          ▼
DELETE /cart                 →  cart cleared
          │
          ▼
POST /cart                   →  cart: { customProductId × 2 }
          │
          ▼
✅  POST /checkout            ←  YOU ARE HERE
        └─ asserts: amount = 149.99 × 2 = 299.98
        └─ asserts: status = "confirmed"
        └─ sets: latestOrderId
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicPassword` |
| 2 | `POST` | `/auth/register` | User account in DB |
| 3 | `POST` | `/auth/login` (dynamic user) | `accessToken` |
| 4 | `POST` | `/auth/login` (admin) | `adminAccessToken` |
| 5 | Pre-request script (auto) | — | `dynamicProductName` |
| 6 | `POST` | `/products` | `customProductId` (price: `149.99`) |
| 7 | `DELETE` | `/cart` | Empty cart |
| 8 | `POST` | `/cart` | Cart: `customProductId × 2` |
| ✅ **9** | `POST` | `/checkout` | `latestOrderId`, `amount: 299.98` |

---

#### Request

```
POST {{baseUrl}}/checkout
Authorization: Bearer {{accessToken}}
```

**No request body.** The checkout endpoint reads the cart from server-side state for the authenticated user.

#### Expected Response — `201 Created`

```json
{
  "orderId": "ord_def456",
  "amount":  299.98,
  "status":  "confirmed"
}
```

#### Response Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `orderId` | string | Unique order ID — saved as `latestOrderId` for 04.4 |
| `amount` | number | Total cost computed from cart contents: `price × quantity` |
| `status` | string | Always `"confirmed"` on successful checkout |

#### How `amount` Is Calculated

```
Product price  ×  Quantity in cart  =  Order total
   149.99      ×        2           =    299.98
  (from 03.2)      (from 04.2)         (asserted here)
```

> Changing the price in 03.2 or the quantity in 04.2 will break this assertion. These three values are tightly coupled across sections.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | Order created successfully |
| `amount` = `299.98` | Total is exactly `price × quantity` |
| `orderId` present | Order reference generated |
| `status` = `"confirmed"` | Order immediately confirmed |

**Post-response script:**
```js
pm.environment.set("latestOrderId", jsonData.orderId);
```

**Produces:** `latestOrderId`

---

### [04.4] GET /orders — Verify Order Appears In History

#### What This Step Does

Returns all orders belonging to the authenticated user as a flat array. In this test, it verifies that the order created in 04.3 (`latestOrderId`) is present in the list, confirming the order was persisted correctly.

---

#### Basic Flow A — Read Orders (No Prior Order Required)

> You only need to be logged in. If no orders exist yet, the API returns an empty array `[]`. This is valid.

```
POST /auth/login   →  get accessToken
        │
        ▼
✅  GET /orders     ←  YOU ARE HERE
        └─ requires: accessToken
        └─ returns: [] if no orders, or array of past orders
```

| Step | Method | Endpoint | Body / Params | What It Gives You |
|------|--------|----------|---------------|-------------------|
| 1 | `POST` | `/auth/login` | `{ email, password }` | `accessToken` |
| ✅ **2** | `GET` | `/orders` | — | Array of orders (may be empty) |

---

#### Basic Flow B — Verify a Specific Order Exists (After Checkout)

> To assert that a specific order appears in the list, you must have completed a checkout first. This is the meaningful test — proving end-to-end that checkout produces a visible, persistent order.

```
POST /auth/login   →  get accessToken
        │
        ▼
GET /products      →  get a productId
        │
        ▼
POST /cart         →  add item to cart
        │
        ▼
POST /checkout     →  creates order, returns orderId
        │              save the orderId
        ▼
✅  GET /orders     ←  YOU ARE HERE
        └─ assert: the orderId from checkout is in the array
```

| Step | Method | Endpoint | Body / Params | What It Gives You |
|------|--------|----------|---------------|-------------------|
| 1 | `POST` | `/auth/login` | `{ email, password }` | `accessToken` |
| 2 | `GET` | `/products` | `?page=1&limit=5` | A valid `productId` |
| 3 | `POST` | `/cart` | `{ productId, quantity }` | Non-empty cart |
| 4 | `POST` | `/checkout` | — (no body) | `orderId` |
| ✅ **5** | `GET` | `/orders` | — | Array containing the new order |

---

#### This Test Suite's Automation Flow

> Uses the `latestOrderId` captured by 04.3 to confirm the exact order created by this run is present.

```
POST /auth/register          →  user in DB
POST /auth/login             →  sets: accessToken
POST /auth/login (admin)     →  sets: adminAccessToken
POST /products               →  sets: customProductId
DELETE /cart                 →  cart cleared
POST /cart                   →  cart: { customProductId × 2 }
POST /checkout               →  sets: latestOrderId
          │
          ▼
✅  GET /orders               ←  YOU ARE HERE
        └─ asserts: array.some(order => order.id === latestOrderId) === true
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | `POST` | `/auth/register` | User account |
| 2 | `POST` | `/auth/login` | `accessToken` |
| 3 | `POST` | `/auth/login` (admin) | `adminAccessToken` |
| 4 | `POST` | `/products` | `customProductId` |
| 5 | `DELETE` | `/cart` | Empty cart |
| 6 | `POST` | `/cart` | Cart populated |
| 7 | `POST` | `/checkout` | `latestOrderId` |
| ✅ **8** | `GET` | `/orders` | Confirms order persisted and visible |

---

#### Request

```
GET {{baseUrl}}/orders
Authorization: Bearer {{accessToken}}
```

#### Expected Response — `200 OK`

```json
[
  {
    "id":        "ord_def456",
    "amount":    299.98,
    "status":    "confirmed",
    "createdAt": "2026-05-31T10:05:00.000Z"
  }
]
```

Response is a **flat array** of all orders for the authenticated user.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Orders retrieved |
| Array contains entry where `id === latestOrderId` | Order persisted and belongs to this user |

---

## 7. Section 05 — Administrative Tasks & Security

---

### [05.1] GET /admin/users — Negative: Regular User Attempts Admin Action

#### Call Chain — Required API Sequence

> This test uses a **valid regular-user token** to prove that authentication alone is not enough — the role check must block access. You must be logged in as a regular (non-admin) user.

```
[Pre-request script fires automatically on 01.1]
   └─ generates: dynamicEmail, dynamicPassword
          │
          ▼
[01.1]  POST /auth/register        → creates user with role "user"
          │
          ▼
[01.2]  POST /auth/login           → sets: accessToken  (for a non-admin user)
          │
          ▼
✅ [05.1]  GET /admin/users          ← YOU ARE HERE
             └─ using regular user accessToken (intentional)
             └─ expects: 403 FORBIDDEN  (not 401 — token is valid, but role is wrong)
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | Pre-request script (auto) | — | `dynamicEmail`, `dynamicPassword` |
| 2 | `POST` | `/auth/register` | User account with role `user` |
| 3 | `POST` | `/auth/login` (dynamic user) | `accessToken` (regular user — not admin) |
| ✅ **4** | `GET` | `/admin/users` with regular token | Proves RBAC blocks non-admin users |

> **Key distinction:** `401` = no/invalid token (authentication failure). `403` = valid token, wrong role (authorization failure). This test specifically verifies the **authorization** layer, so a valid token is required.

---

#### Request

```
GET {{baseUrl}}/admin/users
Authorization: Bearer {{accessToken}}
```

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
| Status is 403 | RBAC enforced — role is insufficient |
| `error.code` = `"FORBIDDEN"` | Standard RBAC error schema |

---

### [05.2] GET /admin/users — Admin Action: Get All Users

#### Call Chain — Required API Sequence

> You must be logged in as admin. This is the positive RBAC test — the same endpoint as 05.1 but with the admin token.

```
[System: DB has admin@practice.com seeded with role:admin]
          │
          ▼
[01.3]  POST /auth/login (admin)   → sets: adminAccessToken
          │
          ▼
✅ [05.2]  GET /admin/users          ← YOU ARE HERE
             └─ using adminAccessToken
             └─ expects: 200 OK with user array (no passwords)
```

| Step | Method | Endpoint | What It Gives You |
|------|--------|----------|-------------------|
| 1 | `POST` | `/auth/login` (admin creds) | `adminAccessToken` |
| ✅ **2** | `GET` | `/admin/users` with admin token | Full user list (no password fields) |

---

#### Request

```
GET {{baseUrl}}/admin/users
Authorization: Bearer {{adminAccessToken}}
```

#### Expected Response — `200 OK`

```json
[
  {
    "id":        "usr_abc123",
    "email":     "user_xyz@practice.com",
    "firstName": "Sarah",
    "lastName":  "Mitchell",
    "role":      "user"
  }
]
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Admin access granted |
| Response is an array | Data structure check |
| `password` field absent from all user objects | Security — password must never be exposed, even to admins |

---

## 8. Global Dependency Map

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║  SYSTEM PREREQUISITES                                                         ║
║  • Server running at http://localhost:3000                                    ║
║  • Database accessible and migrations run                                     ║
║  • Seeded: admin@practice.com / password123 / role:admin                     ║
║  • Seeded: ≥1 product in DB                                                  ║
╚══════════════════════════════╦════════════════════════════════════════════════╝
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SECTION 01 — AUTHENTICATION                                                 │
│                                                                              │
│  [Pre-request script]                                                        │
│    └─ sets: dynamicEmail, dynamicPassword, dynamicFirstName, dynamicLastName│
│         │                                                                    │
│         ▼                                                                    │
│  POST /auth/register ─────────────────────────────────► DB: user created    │
│         │                                                                    │
│         ▼ (uses dynamicEmail + dynamicPassword)                              │
│  POST /auth/login (dynamic user) ─────────────────────► sets: accessToken   │
│                                                               refreshToken   │
│  POST /auth/login (admin, hardcoded) ─────────────────► sets: adminAccessToken│
└──────────┬───────────────────────────────────┬─────────────────────────────┘
           │ accessToken                        │ adminAccessToken
           │ dynamicEmail/First/LastName        │
           ▼                                    ▼
┌─────────────────────────┐       ┌─────────────────────────────────────────┐
│  SECTION 02             │       │  SECTION 03                              │
│  PROFILE MANAGEMENT     │       │  DATA & PRODUCT WORKFLOWS                │
│                          │       │                                          │
│  GET /users/me           │       │  GET /products ──► sets firstProductId  │
│  asserts: email/name     │       │  (public, no auth)                      │
│  asserts: no password    │       │                                          │
│                          │       │  [Pre-request: sets dynamicProductName]  │
│  GET /users/me (no token)│       │  POST /products (adminAccessToken)       │
│  expects: 401            │       │  ──────────────► sets: customProductId   │
└─────────────────────────┘       │                  price locked at 149.99  │
                                   │                                          │
                                   │  POST /products (invalid body)           │
                                   │  expects: 422 VALIDATION_ERROR           │
                                   └──────────────────┬───────────────────────┘
                                                      │ customProductId
          accessToken ───────────────────────────────┬┘
                                                     │
                                                     ▼
                                   ┌─────────────────────────────────────────┐
                                   │  SECTION 04 — E2E CHECKOUT FLOW         │
                                   │                                          │
                                   │  1. DELETE /cart  (accessToken)          │
                                   │     └─ effect: cart is empty             │
                                   │          │                               │
                                   │          ▼                               │
                                   │  2. POST /cart  (accessToken)            │
                                   │     body: { customProductId, qty: 2 }    │
                                   │     └─ effect: cart has 1 item           │
                                   │          │                               │
                                   │          ▼                               │
                                   │  3. POST /checkout  (accessToken)        │
                                   │     reads: server cart state             │
                                   │     asserts: amount = 149.99×2 = 299.98  │
                                   │     └─ sets: latestOrderId               │
                                   │          │                               │
                                   │          ▼                               │
                                   │  4. GET /orders  (accessToken)           │
                                   │     asserts: latestOrderId in list       │
                                   └─────────────────────────────────────────┘

          accessToken ─────────────────────────────────────────────┐
          adminAccessToken ─────────────────────────────────────┐  │
                                                                 ▼  ▼
                                   ┌─────────────────────────────────────────┐
                                   │  SECTION 05 — ADMIN & SECURITY          │
                                   │                                          │
                                   │  GET /admin/users (accessToken)         │
                                   │    expects: 403 FORBIDDEN               │
                                   │                                          │
                                   │  GET /admin/users (adminAccessToken)    │
                                   │    expects: 200 OK, no passwords        │
                                   └─────────────────────────────────────────┘
```

---

## 9. RBAC Matrix

| Endpoint | No Token | Regular User | Admin |
|----------|:--------:|:------------:|:-----:|
| `POST /auth/register` | ✅ 201 | ✅ 201 | ✅ 201 |
| `POST /auth/login` | ✅ 200 | ✅ 200 | ✅ 200 |
| `GET /users/me` | ❌ 401 | ✅ 200 | N/A |
| `GET /products` | ✅ 200 | ✅ 200 | ✅ 200 |
| `POST /products` | ❌ 401 | ❌ 403 (implied) | ✅ 201 |
| `DELETE /cart` | ❌ 401 | ✅ 200 | N/A |
| `POST /cart` | ❌ 401 | ✅ 200 | N/A |
| `POST /checkout` | ❌ 401 | ✅ 201 | N/A |
| `GET /orders` | ❌ 401 | ✅ 200 | N/A |
| `GET /admin/users` | ❌ 401 | ❌ **403** | ✅ 200 |

---

## 10. Error Code Reference

| HTTP Status | `error.code` | Meaning | Tested In |
|-------------|-------------|---------|-----------|
| `401` | `UNAUTHORIZED` | No token or invalid/expired token | 02.2 |
| `403` | `FORBIDDEN` | Valid token but insufficient role | 05.1 |
| `422` | `VALIDATION_ERROR` | Request body failed schema validation | 03.3 |

**All error responses follow this shape:**
```json
{
  "error": {
    "code": "<ERROR_CODE>"
  }
}
```

---

## 11. Most Complex Dependency Analysis

### Winner: Section 04 — E2E Checkout Flow (specifically `POST /checkout`)

`POST /checkout` at step 04.3 has the deepest call chain in the entire suite — **9 sequential steps** before it can be called, spanning system setup, two separate login flows, product creation, and cart management.

#### Full Call Chain Depth

| Level | Step | What Must Happen |
|-------|------|-----------------|
| 1 | System | DB running, migrations applied |
| 2 | System | Admin account `admin@practice.com` seeded |
| 3 | Pre-request script | `dynamicEmail`, `dynamicPassword` generated |
| 4 | `POST /auth/register` | User account created in DB |
| 5 | `POST /auth/login` (user) | `accessToken` obtained |
| 6 | `POST /auth/login` (admin) | `adminAccessToken` obtained |
| 7 | `POST /products` | Product created with `customProductId`, price `149.99` |
| 8 | `DELETE /cart` | Cart cleared — no stale items |
| 9 | `POST /cart` | Cart populated with `customProductId × 2` |
| **✅ 10** | **`POST /checkout`** | **Order created, `latestOrderId` set** |

#### Hard-Coded Value Coupling (Most Brittle Dependency)

```
[03.2] POST /products  →  price hardcoded: 149.99
                                │
                                ▼  (stored in DB)
[04.2] POST /cart      →  quantity hardcoded: 2
                                │
                                ▼  (server computes)
[04.3] POST /checkout  →  assert: amount === 299.98  ← BREAKS if price or quantity changes
```

No other section has this type of **value-level coupling** that spans two sections.

#### Token Fan-Out (`accessToken` touches 6 requests)

`accessToken` from `01.2` is consumed by:

| Request | Section |
|---------|---------|
| `GET /users/me` | 02 |
| `DELETE /cart` | 04 |
| `POST /cart` | 04 |
| `POST /checkout` | 04 |
| `GET /orders` | 04 |
| `GET /admin/users` (negative) | 05 |

If `01.2` fails, all 6 of these return `401`.

#### Summary

| Metric | Value |
|--------|-------|
| Call chain depth to reach `POST /checkout` | 9 prior steps |
| Upstream sections depended on | Sections 01 and 03 |
| Hard-coded value coupling across sections | Yes — `149.99 × 2 = 299.98` |
| Number of env variables consumed by section 04 | `accessToken`, `customProductId`, `latestOrderId` |
| Cascade failure risk | Highest — any upstream failure breaks all 4 internal steps |

---

## 12. Common Failure Scenarios (All Sections)

| Step | Scenario | Symptom | Root Cause |
|------|----------|---------|------------|
| 01.1 | Pre-request script not run | Login body has empty strings → `401` | Postman environment not loaded |
| 01.1 | Duplicate email collision | `409 Conflict` on register | UUID not regenerating — stale env var |
| 01.3 | Admin not seeded in DB | `401` on admin login, `adminAccessToken` never set | Seed / migration not run |
| 02.1 | `accessToken` expired | `401` instead of `200` | Token TTL shorter than test runtime |
| 02.1 | `password` in response | Security assertion fails | DTO / serializer not stripping password field |
| 03.1 | No products in DB | `firstProductId` not set | Product seed not run |
| 03.2 | Regular `accessToken` used | `403` instead of `201` | Wrong token variable in header |
| 03.3 | `adminAccessToken` missing | `401` instead of `422` | Auth checked before validation — admin login skipped |
| 04.1 | `accessToken` missing | `401` | Login (01.2) failed |
| 04.2 | `customProductId` is `undefined` | `400` / `404` on cart add | Create Product (03.2) failed or was skipped |
| 04.2 | Step 04.1 skipped | Stale items in cart | Checkout total will be wrong |
| 04.3 | Cart is empty | Checkout fails or `amount = 0` | Step 04.2 failed or cart deleted after 04.2 |
| 04.3 | Product price ≠ `149.99` | `amount !== 299.98` assertion fails | Price changed in Create Product (03.2) |
| 04.4 | `latestOrderId` not set | Order not found in history | Checkout (04.3) failed — order never created |
| 05.1 | `accessToken` missing | `401` instead of `403` | Login (01.2) failed — wrong error path tested |
| 05.2 | `password` in admin response | Security assertion fails | Serializer not stripping password for admin callers |
| 05.2 | Regular user gets `200` on admin route | RBAC check missing | Admin middleware not applied to route |
