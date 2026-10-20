# Sandbox acceptance

Run against a dedicated test tenant. All addresses and pickup details are fictional.
The first test tier exercises the generic MCP endpoint. The second tier must run in
an authenticated Muse client after its integration path is confirmed.

## Generic MCP tier

1. Initialize MCP, list tools, and verify the six expected names and schemas.
2. Create a quote with fictional addresses, requested readiness and handoff details.
   Verify simulation labels, total/currency, expiry, eligibility, ETA and terms.
3. Reserve the quote; inspect the hold expiry. Retry identical arguments/key and
   verify the same reservation. Changed arguments under that key must fail.
4. Confirm the reservation with the caller's explicit approval assertion. Verify
   a durable delivery ID, `awaiting_pickup_details` status, and simulated payment
   authorization. Repeat the request/key and verify no second delivery exists.
5. Submit fictional restaurant confirmation, pickup name/code, readiness and
   instructions. Verify execution waits until readiness and requires confirmation.
6. Poll through simulated execution to completion. Check status after an API/worker
   restart using the same durable database; the delivery and events must survive.
7. Create a separate delivery and cancel before execution. Retry cancellation with
   the same key; verify stable cancellation and truthful payment state.
8. Reject missing/invalid credentials, another tenant's identifiers, expired holds,
   mismatched idempotency payloads and invalid state changes. Ensure errors contain
   no credentials or another tenant's details.

Persistence, concurrency, expiry and isolation also need backend integration tests.
Successful protocol calls alone cannot establish those properties.

## Muse tier — user-reported local workflow

The user reports that local Muse read this repository, built a
`custom.genie-mobility` client with the six tools allowlisted, securely configured
its key, and completed the simulated booking and cancellation scenarios. See
[validation evidence](validation.md) for the report and corroboration boundaries.
This is not a universal installation recipe. Permission-denial and changed-approval
scenarios below remain acceptance criteria, not claimed observations.

Connect using the authenticated platform's confirmed method. Ask Muse to arrange a
**simulated** delivery of an already ordered fictional restaurant package, with no
food purchase and no real payment. It should show the exact sandbox price and terms,
obtain the required permission, reserve/confirm, collect pickup confirmation, submit
details and return a persisted delivery ID. Ask for status through completion, then
run a separate cancellation scenario. Deny a sensitive action and verify no write.
Change approved details and verify a fresh permission request. Exercise ambiguous
responses without duplicates.

Record endpoint version, test time, environment, tool trace and observed permissions
with secrets and personal information removed. Report user observations, backend
corroboration and independently observed client behavior separately. Do not infer
directory approval, general installation support or permission enforcement from
successful backend records alone.
