# Human-pilot independent evidence

This report concerns the isolated test implementation, not the deployed sandbox
or a real courier booking. Test payments use explicit injected fakes unless noted.

Backend review reference: `Genie-Mobility/genie-delivery` draft PR #1, final handoff
commit `b88b92c94657fcb6faf493a658af801be5864b95`. The independent runs below exercised
the isolated branch during development. The backend owner separately reports 143
tests passing at final handoff; that is not an independent Muse or Stripe test.

Public contract snapshots copied without modification from that commit:

| File | SHA-256 |
| --- | --- |
| `contracts/pilot-fixture.json` | `2433606e2887596afe41ea42f05806e336a68d409fc38a28b18266cc077d80eb` |
| `contracts/pilot-mcp-tools.json` | `0765e2d5f20736de69bba7f5c18e61af45e250fd7c6ac4081b890379665661e1` |

These localhost fixture/client identifiers are not Muse callback configuration.

## Protocol probe

On 2026-10-20, `scripts/pilot_probe.py` passed against `https://localhost:8843`,
trusting only the fixture's test certificate through process-local `SSL_CERT_FILE`.
TLS verification was enabled. No customer copied an API key; the probe handled the
authorization code and tokens internally and did not print them.

Observed checks: protected-resource and authorization-server discovery; denied
consent; CSRF and Origin enforcement; exact redirects; rejection of PKCE downgrade,
wrong verifier, code replay, wrong token resource and redirect; secure guest-cookie
attributes; read-only scope; customer/operator separation; refresh rotation and
reuse detection; grant-family revocation and explicit revocation.

This is an independent HTTP protocol client, not actual Muse. Cookie attributes
were inspected; Python's cookie jar does not emulate all browser SameSite behavior.
Five probe regression tests cover malformed consent controls, false-positive error
classification, and refusal of a fixture that redirects customer tokens to another
resource origin. The latter guard was added after the final security review.

## Payment adapter contract

Six independent tests passed using `httpx.MockTransport` and the isolated backend's
Stripe adapter. They verify that completed Checkout is not authorization; amount,
currency, live-mode and other-guest mismatches are rejected; a live API key is
refused; webhook body tampering/live events fail; and an unpaid Checkout session
with an existing pending intent is expired through the proper API.

The latter test initially reproduced a backend cancellation bug. The backend owner
corrected it, and the independent suite passed afterward. These are fake HTTP
fixtures, not evidence of a Stripe test-account interaction.

## Customer and operator flow

`scripts/pilot_flow.py` used actual local HTTPS OAuth, MCP and operator HTTP routes,
with a local protected control file driving an explicitly injected fake provider.
It observed:

- Same-browser OAuth reconnect retained ownership; another guest was denied access.
- Read-only scope could read the original job but could not cancel it.
- Confirmation replay retained one job; unpaid confirmation remained pending.
- Operator acceptance before payment and pickup details before confirmation failed.
- Fake authorization waited for operator acceptance before confirming capacity.
- Authenticated operator progression recorded collection and physical handoff.
- Forced capture failure left the fulfillment state `delivered`; subsequent fake
  capture reconciliation succeeded without another handoff or dispatch.

The runner initially failed on a nullable `next_action` while starting its separate
cancellation case. This was a client bug, not a backend payment failure; the client
was corrected and that affected scenario is tested separately.

The separate cancellation-only rerun passed: an unpaid job was cancelled, then the
fake provider reported late authorization. The backend voided it and retained
`cancelled`; it did not reconfirm the booking. Only this affected case was rerun.

## Remaining external evidence

Actual Muse OAuth discovery/registration/callback, guest consent and resumed
conversation have not been observed for this new pilot interface. Dedicated Stripe
test credentials/webhook configuration and a human-completed hosted test payment
are also absent. No real provider authorization, charge, dispatch or delivery is
claimed. Business policy, verified reachable contact and production readiness
remain gates for any supervised real pilot.
