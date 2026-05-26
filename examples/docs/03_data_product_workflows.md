# 03. Data & Product Workflows

**Collection Section:** `03. Data & Product Workflows`
**Source:** `Practice_API_Collection.json`

This section covers product catalog operations — listing products with pagination and creating new products. Creating products is an **admin-only** operation. The product ID extracted here is a **critical dependency** for the E2E Checkout Flow in section 04.

---

## Endpoints

### 1. Get All Products with Pagination

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/products?page=1&limit=5` |
| **Auth** | None (public endpoint) |

#### Query Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `page` | `1` | Page number (1-indexed) |
| `limit` | `5` | Maximum items per page |

#### Expected Response — `200 OK`

```json
{
  "data": [
    {
      "id": "<string>",
      "name": "<string>",
      "price": "<number>",
      "category": "<string>",
      "stock": "<number>"
    }
  ],
  "limit": 5,
  "page": 1,
  "total": "<number>"
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | `response.status === 200` |
| `limit` equals `5` | Pagination parameter is honoured |
| `data.length <= 5` | No more items returned than the limit |
| `data[0].id` is captured | `firstProductId` set for downstream use |

#### Post-response Script (ID Capture)

```js
pm.environment.set("firstProductId", jsonData.data[0].id);
```

> If `data` is empty, the test fails with `"No products found to extract ID"` — the database must be seeded with at least one product.

#### Dependencies

- **Requires:** Nothing (public endpoint)
- **Produces:** `firstProductId`
- **Required by:** (available for use; `customProductId` from Create Product is preferred in section 04)

---

### 2. Create Product using Admin

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/products` |
| **Auth** | `Bearer {{adminAccessToken}}` |
| **Content-Type** | `application/json` |

#### Pre-request Script (Name Generation)

```js
pm.environment.set("dynamicProductName", "Automated Product " + pm.variables.replaceIn('{{$randomUUID}}'));
```

A unique product name is generated before each run to prevent name collisions.

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{adminAccessToken}}` |

#### Request Body

```json
{
  "name": "{{dynamicProductName}}",
  "price": 149.99,
  "category": "Electronics",
  "stock": 10,
  "description": "An amazing QA creation"
}
```

#### Request Body Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Product name (must be unique per run) |
| `price` | number | Yes | Unit price in USD |
| `category` | string | Yes | Product category |
| `stock` | number | Yes | Available inventory count |
| `description` | string | No | Human-readable product description |

#### Expected Response — `201 Created`

```json
{
  "product": {
    "id": "<string>",
    "name": "{{dynamicProductName}}",
    "price": 149.99,
    "category": "Electronics",
    "stock": 10,
    "description": "An amazing QA creation"
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | `response.status === 201` |
| `product.name` matches `dynamicProductName` | Data integrity check |
| `product.price` equals `149.99` | Price stored correctly |
| `product.id` is captured | `customProductId` set for downstream use |

#### Post-response Script (ID Capture)

```js
pm.environment.set("customProductId", jsonData.product.id);
```

#### Dependencies

- **Requires:** `adminAccessToken` (set by Validate Admin Login in section 01)
- **Produces:** `customProductId`, `dynamicProductName`
- **Required by:** Add Extracted Product to Cart (section 04, step 2)

---

### 3. Negative: Create Product Invalid Schema

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/products` |
| **Auth** | `Bearer {{adminAccessToken}}` |
| **Content-Type** | `application/json` |

#### Request Body (Intentionally Invalid)

```json
{
  "name": "No Price Or Category Provided"
}
```

Missing required fields: `price` and `category`.

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
| Status is 422 | `response.status === 422` |
| `error.code` is `"VALIDATION_ERROR"` | Standard validation error schema enforced |

#### Dependencies

- **Requires:** `adminAccessToken` (authentication is still needed to reach the validation layer)
- **Produces:** Nothing
- **Note:** This validates that the API rejects incomplete payloads before persisting, not that unauthenticated users can probe the endpoint.

---

## Section Dependency Map

```
[Section 01: Validate Admin Login]
        │  sets: adminAccessToken
        ▼
Create Product using Admin ──────────────────────────────────► sets customProductId
        │                                                       (used in Section 04)
        │
        ├── Negative: Create Product Invalid Schema (uses adminAccessToken only)
        │
GET /products?page=1&limit=5 (public, no auth) ─────────────► sets firstProductId
```

---

## Notes on Price & Stock

- `price` is expected to be a float (`149.99`). The checkout flow in section 04 depends on this exact value to assert `amount = 149.99 * 2 = 299.98`.
- `stock` is set to `10` — the checkout flow adds quantity `2`, so stock depletion is not a concern in this test suite.
