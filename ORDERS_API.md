# Orders API

Demo-mode mock checkout for Semester OS. No real money, no card fields, no payment data.

---

## POST /listings/{id}/orders

Create an order for an available listing. Buyer must not be the seller.

**Auth:** JWT required

**Path:** `id` — 8-character listing ID

**Body:**
```json
{ "method": "pickup" | "ship", "note": "optional string ≤500 chars" }
```

**Rules:**
- Listing must be `available` (not pending/sold/removed)
- Kind must be `sell`, `free`, `service`, or `ticket` (not `wanted` / `trade`)
- Buyer cannot order their own listing
- Listing campus must be visible to the buyer (own campus or network)
- Rate-limited: 3/min, 10/day per buyer

**Response 200:**
```json
{
  "order": {
    "id": "abc12345",
    "status": "paid",
    "timeline": [{"status": "paid", "at": "2026-10-17T20:00:00Z"}],
    "listing": {"id": "lst00001", "title": "Calculus Book", "image": "https://…", "campus": "UA"},
    "counterpart": {"name": "Ben K.", "avatar": "robot-03"},
    "amountCents": 2500,
    "method": "pickup",
    "note": null,
    "demo": true,
    "role": "buying",
    "createdAt": "2026-10-17T20:00:00Z"
  }
}
```

**Errors:** `400 validation_error`, `400 not_orderable`, `400 own_listing`, `400 not_visible`, `404 not_found`, `429 rate_limited`

---

## PATCH /orders/{id}

Advance or cancel an order. Only the buyer or seller may act on their own order.

**Auth:** JWT required

**Body:**
```json
{ "action": "handed_over" | "received" | "cancel" | "decline" }
```

| Action | Who | From status | To status | Side effect |
|---|---|---|---|---|
| `handed_over` | Seller | `paid` | `handed_over` | — |
| `received` | Buyer | `handed_over` | `completed` | Listing → `sold` |
| `cancel` | Buyer | `paid` | `refunded` | Listing → `available` |
| `decline` | Seller | `paid` | `refunded` | Listing → `available` |

**Demo listings:** effective status is auto-advanced from `paid` → `handed_over` at read time (no real seller). Buyers on demo orders skip straight to confirming receipt; cancel is not available.

**Response 200:** same shape as create response.

**Errors:** `400 validation_error`, `403 forbidden`, `404 not_found`, `409 wrong_status`

---

## GET /orders?role=buying|selling

List the caller's orders (newest first). Default role: `buying`.

**Auth:** JWT required

**Response 200:**
```json
{
  "orders": [
    {
      "id": "abc12345",
      "status": "paid",
      "timeline": [...],
      "listing": {"id": "…", "title": "…", "image": "…", "campus": "…"},
      "counterpart": {"name": "Ben K.", "avatar": "robot-03"},
      "amountCents": 2500,
      "method": "pickup",
      "note": null,
      "demo": true,
      "role": "buying",
      "createdAt": "2026-10-17T20:00:00Z"
    }
  ]
}
```

---

## GET /orders/{id}

Fetch a single order. Only buyer or seller may access it.

**Response 200:** same shape as a single order object above.

**Errors:** `404 not_found`

---

## Data model (DynamoDB single-table)

| PK | SK | Description |
|---|---|---|
| `ORDER#{id}` | `META` | Order item (contains buyerSub, sellerSub privately; never returned) |
| `USER#{buyerSub}` | `ORDER#buying#{id}` | Buyer pointer for list |
| `USER#{sellerSub}` | `ORDER#selling#{id}` | Seller pointer for list |

Listing status is updated in place: `available` → `pending` on order, `sold` on complete, back to `available` on cancel/decline.

## No new infra

Orders are handled entirely by the existing API Lambda and DynamoDB table. No new Lambdas, event sources, or quotas required.
