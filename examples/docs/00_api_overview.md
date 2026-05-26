# API Overview

**Collection:** Practice API Advanced Test Suite
**Base URL:** `http://localhost:3000`
**Auth Scheme:** Bearer JWT (via `Authorization: Bearer <token>` header)

---

## Sections

| # | Section | Description |
|---|---------|-------------|
| 01 | [Authentication Flow](./01_authentication_flow.md) | Register, login (user + admin), token capture |
| 02 | [Profile Management](./02_profile_management.md) | Read own profile, unauthorized access guard |
| 03 | [Data & Product Workflows](./03_data_product_workflows.md) | List products (paginated), create product (admin), validation errors |
| 04 | [E2E Checkout Flow](./04_e2e_checkout_flow.md) | Cart management → checkout → order history |
| 05 | [Administrative Tasks & Security](./05_administrative_tasks_security.md) | Admin-only endpoints, RBAC enforcement |

---

## Environment Variables

| Variable | Type | Set By | Used By |
|----------|------|--------|---------|
| `baseUrl` | default | Static (`http://localhost:3000`) | All requests |
| `accessToken` | secret | `POST /auth/login` (dynamic user) | Profile, Cart, Checkout, Orders |
| `refreshToken` | secret | `POST /auth/login` (dynamic user) | (reserved for token refresh) |
| `adminAccessToken` | secret | `POST /auth/login` (admin) | Create Product, Admin routes |
| `dynamicEmail` | default | Pre-request script (Register) | Login Dynamic User |
| `dynamicPassword` | default | Pre-request script (Register) | Login Dynamic User |
| `dynamicFirstName` | default | Pre-request script (Register) | Profile validation |
| `dynamicLastName` | default | Pre-request script (Register) | Profile validation |
| `dynamicProductName` | default | Pre-request script (Create Product) | Create Product body |
| `firstProductId` | default | Test script (Get All Products) | (available for use) |
| `customProductId` | default | Test script (Create Product) | Add to Cart |
| `latestOrderId` | default | Test script (Checkout) | Verify Order History |

---

## End-to-End Dependency Chain

The full happy-path execution order with data flowing between requests:

```
Register New Dynamic User
  └─► (sets dynamicEmail, dynamicPassword, dynamicFirstName, dynamicLastName)
        │
        ▼
Login Dynamic User
  └─► (sets accessToken, refreshToken)
        │
        ▼
Validate Admin Login
  └─► (sets adminAccessToken)
        │
        ▼
Get All Products with Pagination
  └─► (sets firstProductId)
        │
        ▼
Create Product using Admin (uses adminAccessToken)
  └─► (sets customProductId, uses dynamicProductName)
        │
        ▼
Clear Pre-existing Cart (uses accessToken)
        │
        ▼
Add Extracted Product to Cart (uses accessToken + customProductId)
        │
        ▼
Checkout Order (uses accessToken)
  └─► (sets latestOrderId)
        │
        ▼
Verify Order Appears In History (uses accessToken + latestOrderId)
```

---

## Error Code Reference

| HTTP Status | Error Code | Meaning |
|-------------|------------|---------|
| 401 | `UNAUTHORIZED` | Missing or invalid Bearer token |
| 403 | `FORBIDDEN` | Authenticated but insufficient role (e.g. user hitting admin route) |
| 422 | `VALIDATION_ERROR` | Request body failed schema validation |
