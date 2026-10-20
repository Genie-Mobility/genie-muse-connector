# Human-pilot onboarding: implementation and evidence boundaries

This branch develops an isolated **human_test** pilot. The existing sandbox
`/mcp` and `/v1` interfaces remain unchanged. Pilot interfaces use `/pilot/mcp`
and `/pilot/v1`; they are not advertised as deployed or connected to Muse.
No real payments, dispatch, or Connector Platform submission are authorized here.

## Intended customer experience

The customer authorizes Genie in a secure browser step without creating a password
or copying an API key. The server creates a pseudonymous guest associated with that
browser session. It is not verification of a real person, email address or phone
number. Contact details are collected when needed for a booking, not for a quote.
Verified reachable contact remains a gate before a real supervised delivery.

The client receives scoped authorization through an authorization-code exchange
with PKCE S256. Tokens are handled by the client, never copied through customer
chat. Customer authorization grants no operator access. Reconnecting within a
valid browser session or refresh grant preserves the guest; losing both does not
permit recovery by merely asserting an email address or phone number. Cross-device
account recovery is outside this test implementation.

After a quote and capacity hold, confirmation may return pending payment or operator
acceptance. The customer completes only the required payment authorization step
in a secure provider interface, and the agent resumes by querying authoritative
booking status. A return URL is not proof of payment. Only verified authorization
and operator acceptance establish confirmed delivery capacity. Restaurant ordering
is separate and should wait until that confirmation.

Physical handoff and payment capture are distinct events: a delivery can be handed
over while capture is pending or failed. A successful-payment claim requires
provider confirmation; a successful-delivery claim requires operator evidence.

## What official sources establish

- [Muse Help Center](https://www.meta.com/help/artificial-intelligence/1687253048996149/)
  describes asking Muse to create custom connectors and its Secure Credentials
  Store. It does not specify custom-client OAuth registration, callback addresses,
  grant handling or payment-resume APIs.
- [Muse guidelines](https://platform.muse.ai/docs) contemplate OAuth account
  connection and guest checkout when offered by the service. Necessary sign-in,
  identity or payment verification may involve the user, while the agent must
  preserve progress and complete the supported workflow. Connection is not blanket
  approval for consequential actions.
- [MCP authorization specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)
  defines protected-resource/authorization-server discovery and OAuth security
  requirements. Conformance by our service does not prove Muse implements that
  exact client flow.
- [Muse's platform page](https://platform.muse.ai/) advertises a Stripe Link
  partnership. It does not establish that Muse supplies Genie with customer identity,
  reusable payment credentials or automatic authorization.

## Agreed security boundary

The test implementation uses a preregistered public client, exact registered
redirects, S256 PKCE, resource/audience binding and short-lived single-use codes.
Customer scopes are `delivery:read` and `delivery:write`, with no operator scopes.
Opaque tokens are stored hashed server-side; refresh rotation and revocation must
preserve isolation. Browser consent uses a server-bound guest session, CSRF
protection and HttpOnly cookies. Submitted tenant identifiers are never trusted.

Access and refresh tokens never belong in callback URLs. A standard OAuth callback
does carry a short-lived, single-use, PKCE-bound authorization code; logs and browser
referrer handling must protect that code. Do not promise a POST callback mode unless
the actual client supports it.

An independent client must test state binding, wrong verifier/resource/redirect,
code replay, read-only scopes, tenant isolation, expiration/revocation, refresh
replay, and lack of customer access to operator actions. Operator credentials and
sessions have a separate authority and are never customer OAuth grants.

## Payment evidence tiers

1. **Explicit fake provider:** deterministic state-machine and webhook-contract
   tests. These do not establish Stripe connectivity or a working payment UI.
2. **Stripe test mode:** dedicated test credentials, valid signed webhook handling,
   server-side object verification and hosted test authorization. Require test-mode
   objects, exact amount/currency and booking association. No live key is accepted.
3. **Muse resume:** a fresh local Muse customer uses secure authorization and test
   payment steps, then resumes without copying credentials. Record user-observed
   behavior separately from backend record corroboration.

Dedicated provider test configuration and an actual local Muse interaction are
currently needed to establish tiers 2 and 3. Existing website payment credentials
must not be borrowed. No simulated result is labeled provider-verified.

[Stripe manual capture](https://docs.stripe.com/payments/place-a-hold-on-a-payment-method)
supports Checkout authorization using `payment_intent_data[capture_method]=manual`.
For this pilot, verify `requires_capture`, sufficient capturable amount, test mode,
and exact attempt/quote association before treating payment as authorized. Preserve
the provider's actual authorization-expiry information. The
[hosted Checkout fulfillment guidance](https://docs.stripe.com/checkout/fulfillment?payment-ui=stripe-hosted)
requires server-side fulfillment; the customer may never visit the return page.
Signature verification, deduplication and current-state retrieval must handle
repeated or reordered [webhooks](https://docs.stripe.com/webhooks).

An unpaid open Checkout session can be
[expired](https://docs.stripe.com/api/checkout/sessions/expire); an authorized
PaymentIntent in `requires_capture` can be
[cancelled](https://docs.stripe.com/api/payment_intents/cancel). The latter API
documents the Checkout exception for that state. After operator handoff, capture
must be a durable, idempotent internal action, not a customer-scoped tool. Neither
redirecting to `cancel_url` nor an uncertain provider response proves a void.

## Concrete local Muse experiment, once an isolated endpoint is ready

Ask Muse to connect the isolated pilot endpoint for a new test customer without
manual key entry. First observe whether it discovers OAuth metadata and exposes a
supported registration/callback mechanism. Record the client identifier and exact
redirect URI through appropriate configuration; do not invent them or accept
arbitrary redirects. If unsupported, stop that experiment and report the limitation.

Complete guest consent in the browser and check that Muse resumes with access to
only that guest's pilot data. Decline consent in a separate session. Then request a
test booking, approve its exact terms, complete only the secure test-payment step,
and return to the same booking. Observe pending operator acceptance, confirmation,
and separate handoff/capture outcomes. Revoke access and verify that subsequent
calls fail. Never paste token values, card data or provider secrets into chat.

This is a proposed experiment, not a claim that Muse supports the flow. A generic
OAuth/MCP acceptance client can prove service behavior while this experiment awaits
user interaction and a supported isolated deployment.

## Independent protocol probe

`scripts/pilot_probe.py` uses a browser cookie jar, reads the consent form, and
exchanges the PKCE-bound callback code internally. No customer key is required and
no token is printed. It tests metadata, guest-cookie attributes, code/verifier/
redirect/resource binding, read-only scope, operator separation, refresh reuse and
revocation. It does not claim to emulate browser SameSite enforcement or Muse.

Configure a dedicated HTTPS test server and register the test client's exact
callback. The values in `contracts/pilot-probe.example.json` are example test
configuration, not discovered Muse settings. Trust the test certificate through a
dedicated local CA; do not disable certificate verification or change system DNS.

```sh
SSL_CERT_FILE=/path/to/test-ca.pem python3 scripts/pilot_probe.py \
  --fixture /path/to/actual-pilot-probe.json
```

The callback is inspected without following redirects, so this protocol probe needs
no callback listener. A real Muse client must expose and complete its own actual
callback mechanism. Tests create only isolated guest grants; use a dedicated test
database and an outer process timeout for unattended runs.

The backend's actual `contracts/pilot-fixture.json` defines its preregistered test
client; prefer that file over the illustrative example. For the separate local
human-flow fixture, the backend supplies a protected operator credential file and
fake-provider control file. Both must be mode 600. The runner restricts this flow
to loopback and never opens its fake checkout URLs:

```sh
SSL_CERT_FILE=/path/to/test-ca.pem python3 scripts/pilot_flow.py \
  --fixture /path/to/backend/contracts/pilot-fixture.json \
  --credentials /path/to/protected/credentials.json \
  --provider-controls /path/to/protected/provider-controls.json
```

The credential file includes `operator_credential`; it is an operator test fixture,
not a customer credential or public configuration. Fake controls map a test job ID
to provider status and optional capture failure. The test server injects that
adapter explicitly; no deployed API exposes these controls. `--cancellation-only`
runs only the late-authorization/cancellation case when the fixture slot is free.

Run independent adapter-contract tests using the isolated backend's dependencies
and source on `PYTHONPATH`:

```sh
PYTHONPATH=/path/to/genie-delivery-pilot /path/to/backend-venv/bin/python \
  -m unittest discover -s integration_tests -v
```

Actual Stripe testing needs a dedicated test-mode secret key and webhook signing
secret supplied outside chat/repositories, a reachable test webhook, and a user
completing hosted **test** payment authorization. These are distinct from the fake
fixture controls. Never use the marketing website's payment credentials.
