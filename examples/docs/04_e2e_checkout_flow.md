# 04. E2E Checkout Flow

**Collection Section:** `04. E2E Checkout Flow`
**Source:** `Practice_API_Collection.json`

This is the most complex section of the API. It orchestrates a **4-step sequential workflow** where each step depends on the previous one, and the entire flow depends on tokens and IDs produced in sections 01 and 03. A single failure in any upstream step will cascade and break all steps below it.

---

## Execution Order (Required — Steps are Numbered)

```
Step 1: DELETE /cart            — Clear any pre-existing cart state
Step 2: POST   /cart            — Add the admin-created product to cart
Step 3: POST   /checkout        — Checkout → creates an order
Step 4: GET    /orders          — Verify the new order appears in history
```

---

## Endpoints

### Step 1 — Clear Pre-existing Cart

| Field | Value |
|-------|-------|
| **Method** | `DELETE` |
| **URL** | `{{baseUrl}}/cart` |
| **Auth** | `Bearer {{accessToken}}` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

#### Expected Response — `200 OK`

No body structure is asserted — only status code is checked.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Cart cleared successfully |

#### Dependencies

- **Requires:** `accessToken` (from section 01, Login Dynamic User)
- **Produces:** Nothing (side effect: empties the user's cart)
- **Purpose:** Ensures a clean cart state before the test — prevents leftover items from previous runs from corrupting the checkout total assertion in step 3.

---

### Step 2 — Add Extracted Product to Cart

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/cart` |
| **Auth** | `Bearer {{accessToken}}` |
| **Content-Type** | `application/json` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

#### Request Body

```json
{
  "productId": "{{customProductId}}",
  "quantity": 2
}
```

#### Request Body Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `productId` | string | Yes | ID of the product to add (must exist in DB) |
| `quantity` | integer | Yes | Number of units to add |

#### Expected Response — `200 OK`

```json
{
  "cart": {
    "items": [
      {
        "productId": "{{customProductId}}",
        "quantity": 2
      }
    ]
  }
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Item added successfully |
| Cart contains item with `productId === customProductId` | Product is in cart |
| `item.quantity` equals `2` | Correct quantity stored |

#### Dependencies

- **Requires:** `accessToken` (section 01)
- **Requires:** `customProductId` (section 03, Create Product — the product must exist in DB)
- **Produces:** Nothing (side effect: cart now contains 2× the admin-created product)

---

### Step 3 — Checkout Order

| Field | Value |
|-------|-------|
| **Method** | `POST` |
| **URL** | `{{baseUrl}}/checkout` |
| **Auth** | `Bearer {{accessToken}}` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

> **No request body** — the checkout endpoint reads the cart from server state.

#### Expected Response — `201 Created`

```json
{
  "orderId": "<string>",
  "amount": 299.98,
  "status": "confirmed"
}
```

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 201 | Order created |
| `amount` equals `299.98` | `149.99 (price) × 2 (quantity) = 299.98` |
| `orderId` is present | Order reference generated |
| `status` is `"confirmed"` | Order immediately confirmed |

#### Post-response Script (Order ID Capture)

```js
pm.environment.set("latestOrderId", jsonData.orderId);
```

#### Dependencies

- **Requires:** `accessToken` (section 01)
- **Requires:** Cart to be non-empty with exactly the admin-created product at quantity 2 (steps 1 and 2 must have run)
- **Requires:** Product price to be exactly `149.99` (asserted total is `299.98`)
- **Produces:** `latestOrderId`
- **Required by:** Step 4

#### Critical Dependency Note

The `amount` assertion (`299.98`) is **hard-coded** and depends on:
1. `customProductId` referencing a product priced at exactly `149.99` (set in section 03)
2. Cart containing exactly that product at quantity `2` (set in steps 1–2 of this section)

If any upstream step fails or produces different data, this assertion will fail.

---

### Step 4 — Verify Order Appears In History

| Field | Value |
|-------|-------|
| **Method** | `GET` |
| **URL** | `{{baseUrl}}/orders` |
| **Auth** | `Bearer {{accessToken}}` |

#### Request Headers

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {{accessToken}}` |

#### Expected Response — `200 OK`

```json
[
  {
    "id": "{{latestOrderId}}",
    ...
  }
]
```

Response is an **array** of order objects.

#### Assertions

| Test | Condition |
|------|-----------|
| Status is 200 | Orders retrieved |
| Array contains entry with `id === latestOrderId` | Order created in step 3 is persisted and visible |

#### Dependencies

- **Requires:** `accessToken` (section 01)
- **Requires:** `latestOrderId` (step 3 of this section)
- **Produces:** Nothing

---

## Full Dependency Map for This Section

```
[Section 01]                         [Section 03]
Login Dynamic User                   Create Product using Admin
  └── sets: accessToken                └── sets: customProductId (price: 149.99)
                │                                     │
                ▼                                     │
        Step 1: DELETE /cart ◄────── accessToken ─────┤
                │                                     │
                ▼                                     │
        Step 2: POST /cart ◄──── accessToken ─────────┘
                │                  customProductId
                ▼
        Step 3: POST /checkout ◄── accessToken
                │  └── sets: latestOrderId
                │  └── asserts: amount = 299.98 (depends on price × quantity)
                ▼
        Step 4: GET /orders ◄─── accessToken + latestOrderId
```

---

## Why This Section Has The Most Complex Dependencies

This section is the convergence point of **all previous sections**:

| Dependency | Originates In |
|------------|---------------|
| `accessToken` | Section 01 — Login Dynamic User |
| `customProductId` | Section 03 — Create Product using Admin |
| `adminAccessToken` (indirect) | Section 01 — Validate Admin Login → enables section 03 |
| Seeded admin account | Database precondition |
| Product price of `149.99` | Section 03 — hardcoded in product creation body |
| Cart being empty before step 2 | Step 1 of this section |

A failure at **any** node in the above chain cascades through all remaining steps.
