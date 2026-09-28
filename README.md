# Diagnostic Booking Service

A Django REST API backend for booking diagnostic tests at diagnostic centres, with a **simulated** payment provider and an **idempotent** payment webhook.

**Stack:** Python 3.12+ · Django 5.2/6.0 · Django REST Framework · SimpleJWT · PostgreSQL

---

## 1. Setup and run locally

### Prerequisites
- Python 3.12 or newer
- PostgreSQL 14 or newer. You can use a local install, or the included `docker-compose.yml`.

### Steps

```bash
# 1. Create and activate a virtualenv
python -m venv .venv
# Windows (PowerShell):   .venv\Scripts\Activate.ps1
# macOS / Linux:          source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env          # Windows: copy .env.example .env
#    then edit DATABASE_URL (and secrets) in .env

# 4. Start PostgreSQL. Pick one of these:
docker compose up -d db       # a) Docker: creates diagnostic_db, user/password postgres/postgres
# b) Local PostgreSQL: create the database yourself:
#    psql -U postgres -c "CREATE DATABASE diagnostic_db;"

# 5. Create tables
python manage.py migrate

# 6. (Optional) Load demo centres/tests and an admin user
python manage.py seed_demo_data     # admin@example.com / Admin@12345

# 7. Run the server
python manage.py runserver
```

The API is now at `http://127.0.0.1:8000/` and the Django admin is at `/admin/`.

### Run the tests

```bash
python manage.py test
```

The test suite has 42 tests covering auth, centres, bookings, payments and the webhook edge cases. Django creates a throwaway test database on the PostgreSQL server, so the DB user needs the `CREATEDB` privilege. To run the tests without PostgreSQL:
`DATABASE_URL=sqlite:///test.sqlite3 python manage.py test`.

### Environment variables (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgres://postgres:postgres@localhost:5432/diagnostic_db` | Database connection |
| `DJANGO_SECRET_KEY` | dev value | **Set this in any real deployment** |
| `DJANGO_DEBUG` | `True` | |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | `30` / `7` | Token lifetimes |
| `PAYMENT_WEBHOOK_SECRET` | `dev-webhook-secret` | HMAC secret shared with the payment provider |
| `SIMULATED_PAYMENT_SUCCESS_RATE` | `0.8` | Chance a payment succeeds when no outcome is forced |
| `BOOKING_MAX_DAYS_AHEAD` | `90` | How far ahead appointments can be booked |

---

## 2. Project layout

```
config/      settings, root URLs
common/      shared base model, permissions, 409 Conflict exception, error handler, test fixtures
accounts/    custom User (email login), signup / login / refresh / me
centres/     DiagnosticTest catalogue, DiagnosticCentre, CentreTest (test + price per centre)
bookings/    Booking model + state machine, booking APIs
payments/    Payment, WebhookEvent, simulated gateway, services (business logic), webhook
```

The business logic for payments and webhooks lives in `payments/services.py`, so the views stay thin.

---

## 3. Data model

```
User ─┐
      │ 1..*
      ▼
   Booking ──* Payment ──* WebhookEvent
      │  │
      │  └──► DiagnosticTest ◄──┐
      └────► DiagnosticCentre ──┴── CentreTest (price, is_available)
```

| Model | Key fields | Constraints and indexes |
|---|---|---|
| **User** | email (login), name, phone | email unique |
| **DiagnosticTest** | code, name, description | code unique, name unique |
| **DiagnosticCentre** | name, address, city, pincode, phone, is_active | unique (name, address, city); index on city |
| **CentreTest** | centre, test, **price**, is_available | unique (centre, test); `price > 0` |
| **Booking** | UUID id, user, centre, test, appointment_at, **amount**, status, cancelled_at | `amount > 0`; **partial unique** (user, centre, test, appointment_at) where status ≠ CANCELLED; indexes on (user, created_at), (centre, appointment_at), status |
| **Payment** | UUID id, booking, amount, status, provider_reference, idempotency_key, failure_reason | provider_reference unique; **at most one SUCCESS and one PENDING payment per booking** (partial unique indexes); unique (booking, idempotency_key) |
| **WebhookEvent** | event_id, payment, status, payload, payload_hash, result | **event_id unique**. This is what makes the webhook idempotent. |

Design notes:
- `Booking.amount` stores the centre's price at booking time. Later price changes don't affect existing bookings. The price always comes from the database, never from the client.
- Booking and payment IDs are UUIDs, so they can't be enumerated.
- Bookings, centres and tests use `on_delete=PROTECT`. Deleting a centre that has bookings returns `409` instead of deleting the booking history.

### Booking state machine

```
            payment SUCCESS
 PENDING ────────────────────► CONFIRMED
   │  ▲ \                         │
   │  │  \ payment FAILED         │ cancel
   │  │   ▼                       ▼
   │  └─ FAILED ──────────────► CANCELLED   (terminal)
   │  retry payment               ▲
   └──────────── cancel ──────────┘
```

A payment result never pulls a booking out of `CANCELLED`. If a success arrives for a cancelled booking, the payment is recorded and a "refund required" warning is logged. A failure never downgrades a `CONFIRMED` booking.

---

## 4. API

All request and response bodies are JSON. To authenticate, send `Authorization: Bearer <access token>`. List endpoints are paginated (`?page=`, `?page_size=`, max 100).

### Auth
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/signup/` | – | `{email, password, first_name, last_name?, phone?}` → user and tokens |
| POST | `/auth/login/` | – | `{email, password}` → `{access, refresh, user}` |
| POST | `/auth/token/refresh/` | – | `{refresh}` → `{access}` |
| GET | `/auth/me/` | JWT | Current user |

Validation: email format and uniqueness (case-insensitive) and Django's password validators (length, common, numeric, similarity). The auth endpoints are rate-limited (`20/min`).

### Centres and tests
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/centres/` | public | Centres with available tests and prices. Filters: `?city=`, `?test=<id>`, `?search=` |
| GET | `/centres/{id}/` | public | One centre |
| GET | `/centres/{id}/tests/` | public | Tests offered at the centre, with prices |
| POST/PUT/PATCH/DELETE | `/centres/…` | admin | Manage centres |
| GET | `/tests/` | public | Test catalogue (`?search=`) |
| POST/PUT/PATCH/DELETE | `/tests/…` | admin | Manage catalogue |
| GET/POST/PATCH/DELETE | `/centre-tests/` | read public, write admin | Attach a test to a centre with a price: `{centre, test, price, is_available}`. Filters `?centre=`, `?test=` |

The centre list always runs a constant 3 queries, however many centres or tests there are. It uses `Prefetch` + `select_related`, and a test enforces this.

### Bookings (JWT required)
| Method | Path | Description |
|---|---|---|
| POST | `/bookings/` | `{centre_id, test_id, appointment_at}` → booking in `PENDING` |
| GET | `/bookings/` | Your bookings (`?status=PENDING\|CONFIRMED\|FAILED\|CANCELLED`) |
| GET | `/bookings/{id}/` | One booking, with its payments |
| POST | `/bookings/{id}/cancel/` | Cancel (owner only) |

`PUT`, `PATCH` and `DELETE` return `405`. The only way to change a booking's status is through payments or cancellation.

### Payments (JWT required)
| Method | Path | Description |
|---|---|---|
| POST | `/payments/` | `{booking_id, simulate_outcome?}` runs the mock payment |
| GET | `/payments/` · `/payments/{id}/` | Your payments |

- `simulate_outcome` is one of:
  - `SUCCESS` or `FAILED`: the payment settles immediately and the booking becomes `CONFIRMED` or `FAILED`.
  - `PENDING`: the payment stays open until the provider calls the webhook.
  - Omitted: the outcome is random (`SIMULATED_PAYMENT_SUCCESS_RATE`).
- Optional header **`Idempotency-Key: <≤64 chars>`**. Retrying with the same key returns the original payment (`200`) instead of charging again. A new payment returns `201`.
- A failed payment can be retried. The booking goes `FAILED → PENDING → CONFIRMED/FAILED`.

### Payment webhook
`POST /payments/webhook/`. This endpoint takes no JWT. It is authenticated with an HMAC signature instead.

```
Headers:  Content-Type: application/json
          X-Webhook-Signature: sha256=<hex HMAC-SHA256 of the raw body with PAYMENT_WEBHOOK_SECRET>
Body:     {"event_id": "evt_123", "payment_reference": "sim_…", "status": "SUCCESS"|"FAILED",
           "amount": "350.00" (optional, must match), "failure_reason": "..." (optional)}
```

Response `200`: `{"result": "processed" | "ignored" | "duplicate", "payment_status", "booking_status", …}`

To play the provider locally, use the helper command. It signs the body for you:

```bash
python manage.py send_webhook <provider_reference> SUCCESS --event-id evt_1
python manage.py send_webhook <provider_reference> SUCCESS --event-id evt_1   # → "duplicate"
```

### Example flow (curl)

```bash
B=http://127.0.0.1:8000
TOKEN=$(curl -s -X POST $B/auth/login/ -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"Admin@12345"}' | python -c "import sys,json;print(json.load(sys.stdin)['access'])")

curl -s "$B/centres/?city=Bengaluru"

curl -s -X POST $B/bookings/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"centre_id":1,"test_id":1,"appointment_at":"2026-12-01T10:00:00Z"}'

curl -s -X POST $B/payments/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: pay-1' -d '{"booking_id":"<booking uuid>","simulate_outcome":"PENDING"}'

python manage.py send_webhook <provider_reference from above> SUCCESS
```

---

## 5. How idempotency and consistency are guaranteed

**Webhook (same event delivered many times):**
1. Every accepted event is stored in `WebhookEvent` with a **unique `event_id`**. A re-delivery is detected, returns `200 {"result": "duplicate"}`, and changes nothing.
2. Processing runs in one transaction that **locks the booking row, then the payment row** (`SELECT … FOR UPDATE`). Concurrent deliveries of the same event are handled one after another. The second one sees the first one's event and returns `duplicate`.
3. The event row is inserted **before** the status change is applied. If the unique index rejects it, the status change is never applied.
4. If an `event_id` is reused with a *different* payload, the server returns `409`. This catches provider bugs and tampering.
5. **State-level idempotency:** payment statuses are final once `SUCCESS` or `FAILED`. A new event that would change a final payment (such as a late `FAILED` after `SUCCESS`) is recorded as `ignored` and doesn't touch the booking. The webhook never creates payments or bookings. It can only move an existing `PENDING` payment to a final state.

**Payments:**
- The payment endpoint locks the booking row the same way, so a double-click or two concurrent requests can't both charge.
- The database enforces **at most one successful and one pending payment per booking** with partial unique indexes. Double payment is impossible even if some future code path skips the checks.
- The `Idempotency-Key` header makes client retries safe.

**Bookings:** a partial unique index prevents duplicate live bookings for the same user, test, centre and time slot, including duplicates from concurrent double-submits.

Every write path (pay, webhook, cancel) takes the booking lock first and the payment lock second. The consistent order means these paths can't deadlock each other.

---

## 6. Edge cases handled

| Case | Behaviour |
|---|---|
| Missing or invalid JWT | `401` |
| Non-admin writes to centres, tests or prices | `403` |
| Accessing, cancelling or paying for **another user's booking** | `404`. Doesn't reveal that the booking exists. |
| Invalid booking ID (malformed UUID or unknown) | `404` on URLs, `400`/`404` in the payment body |
| Appointment in the past, too far ahead, or malformed date | `400` |
| Test not offered or unavailable at the centre, inactive centre | `400` |
| Client sends its own `amount` | Ignored. The price comes from the DB. |
| Duplicate booking for the same slot | `409` |
| Editing or deleting a booking | `405` |
| Cancelling twice, or cancelling a past appointment | `409` |
| Paying an already-paid or cancelled booking, or while a payment is in progress | `409` |
| Paying after the appointment time | `400` |
| Failed payment | Booking → `FAILED`, with `failure_reason`. The user can retry. |
| Repeated webhook event | `200 duplicate`, no changes |
| Same `event_id` with a different payload | `409` |
| Contradicting or late webhook (`FAILED` after `SUCCESS`) | `200 ignored`, state preserved |
| Webhook for a cancelled booking | Payment recorded, booking stays `CANCELLED`, refund warning logged |
| Webhook with bad or missing signature | `401` |
| Webhook with unknown `payment_reference` | `404` |
| Webhook `amount` mismatch, bad status, malformed JSON | `400` |
| Deleting a centre or test that has bookings | `409` instead of a 500 |
| Unknown URL | JSON `404` (when `DEBUG=False`) |

---

## 7. Deliberate simplifications
- The simulated gateway runs inside the payment transaction. With a real provider, the external call would happen outside the DB transaction, and the webhook would be the source of truth.
- Refunds for cancelled paid bookings are only logged, not processed.
- The webhook uses HMAC but doesn't check timestamps against replay. Replays are still harmless because of event-id idempotency.
- There is no slot-capacity management for centres. Only the same user's duplicate bookings are prevented.
