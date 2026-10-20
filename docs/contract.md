# Sandbox contract v1

Backend source of truth: `genie-delivery/delivery/models.py` and its exported
contract schemas. This document describes the agreed interface, not a Muse install
manifest. The backend owns both REST and MCP adapters over the same business logic.

Published snapshots: [OpenAPI](../contracts/openapi.json),
[MCP input/output schemas](../contracts/mcp-tools.json), and
[fictional sandbox fixture](../contracts/sandbox-fixture.json). See
[snapshot provenance](../contracts/README.md) before comparing service versions.

Base URL target: `https://delivery.geniemobility.ai`. Local test base:
`http://127.0.0.1:8800`. MCP path: `/mcp`. Use a dedicated bearer API key that the
server maps to a tenant; callers cannot select tenant IDs. Remote connections need
HTTPS. Streamable HTTP compatibility with Muse remains unverified.

All five mutating tools take an `idempotency_key` string (1–128 characters,
letters/digits or `._:-`); REST
uses the `Idempotency-Key` header instead. Use a fresh UUID for a new action and keep
it with the exact request for retry/recovery. Reusing it with different arguments
is a conflict. A replay can return the original response: read current status after
recovery rather than assuming that replayed state is still current.

| MCP tool | REST method/path | Required business inputs |
| --- | --- | --- |
| `get_delivery_quote` | POST `/v1/quotes` | `pickup_address`, `dropoff_address`, `package_description`, `requested_ready_time`, `handoff_type` |
| `reserve_delivery` | POST `/v1/reservations` | `quote_id` |
| `confirm_delivery` | POST `/v1/deliveries` | `reservation_id`, `user_confirmed: true` |
| `submit_pickup_details` | POST `/v1/deliveries/{delivery_id}/pickup-details` | `delivery_id` in MCP; `restaurant_confirmation: true`, `restaurant_order_reference`, `pickup_name`, `ready_at` |
| `get_delivery_status` | GET `/v1/deliveries/{delivery_id}` | `delivery_id` in MCP |
| `cancel_delivery` | POST `/v1/deliveries/{delivery_id}/cancel` | `delivery_id` in MCP; `reason` |

Quote optionally accepts `instructions`. Pickup optionally accepts `pickup_code`,
`instructions`, and `pickup_contact`. Datetimes must include a timezone; examples
use UTC. IDs are UUID strings. Unknown business fields are rejected. Send restaurant
confirmation only after an order exists; this API does not purchase food. The
confirmation boolean records the caller's assertion and cannot prove Muse approval.

Quote results include `quote_id`, `status`, `simulation: true`, `price_cents: 500`,
`currency: "USD"`, `expires_at`, simulated eligibility, estimated delivery time and
terms. USD 5.00 is the entire simulated total; no money is collected. Addresses are
not geocoded or checked against real coverage. ETA is a simulation estimate.

Reservations return `reservation_id`, `quote_id`, `status`, `expires_at`, and the
simulation label. The hold lasts five minutes. Confirmation returns a durable
`delivery_id`, `status: "awaiting_pickup_details"` and
`payment_status: "simulated_authorized"`. Pickup submission queues execution;
the worker waits for readiness before progressing through `in_transit` to
`completed`. Confirmed deliveries cannot execute without valid pickup details.

Cancellation is permitted before `in_transit`; it yields `cancelled` with
`simulated_voided` payment state. Completion, authorization and voiding are all
simulated and never imply actual payment capture, refund or delivery.

## Errors and permissions

REST reports authentication failures (401/403), missing or other-tenant resources
(404), conflicts/capacity/state failures (409), expiry (410), and invalid input (422).
MCP business errors are tool errors (`isError: true`); protocol errors use JSON-RPC
errors. A network timeout is an uncertain outcome, not proof of failure.

Quote persistence, reservations, confirmation, pickup submission and cancellation
are writes. Status is read only. Propose sensitive classification for commitment,
execution and cancellation; final Muse classification is determined during review.
Request only necessary information and obtain approval for the exact commitment.

No production SLA, published rate limit or production data retention commitment is
established by this sandbox contract. Supply and verify these before submission.
