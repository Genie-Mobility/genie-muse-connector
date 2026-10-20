# Local Muse OAuth compatibility experiment

The user inspected the existing `custom.genie-mobility` connector and reports that
it is fixed to API-key/bearer authentication. A **new connector alongside it** is
needed for OAuth. The user reports that Muse offers `oauth2_code` and RFC 7591
dynamic client registration when a registration endpoint is advertised. These are
reported capabilities, not an observed successful OAuth handshake. No existing
Muse client identifier or callback URI has been established.

## Narrow isolated server

The compatibility app reuses the pilot OAuth implementation in an isolated database
and exposes only `get_oauth_probe_status` at `/pilot/mcp`. That tool reports
authenticated status, compatibility mode and resource; it returns no customer
identity, credentials, deliveries or payment data. Delivery, operator and payment
routes are absent. The working sandbox and old Muse connector remain unchanged.

The app advertises `/pilot/oauth/register` only when bounded test registration is
enabled. Initial registration requests with an unknown redirect URI are rejected
with `invalid_redirect_uri`. A private, bounded proposal record allows the operator
to inspect non-secret client metadata, verify the actual Muse callback, and add the
exact URI to the allowlist. Retrying registration then generates the client ID;
there is no need to ask the customer for a nonexistent ID.

Registration is not customer authorization. It grants no access token or identity.
Accept only explicitly supported public-client authentication (`none`), code
response, authorized grants and permitted scopes. Require S256 PKCE, exact approved
redirects and resource binding in the subsequent flow. Do not assume omitted
`token_endpoint_auth_method` means `none`: RFC 7591 defines a different default.
Unsupported methods or missing security parameters must fail, not downgrade.

## What can be observed before customer consent

The discovery challenge, protected-resource metadata, authorization-server metadata,
registration request/response, callback URI, authentication method, scopes, resource
and presence of an S256 challenge can be inspected without granting a guest access.
Record only non-secret facts. Never log authorization codes, verifier, tokens,
cookies or registration credentials. Client names and submitted callback metadata
are untrusted until checked; a name claiming to be Muse proves no affiliation.

## Fresh Muse prompt

The isolated staging endpoint is ready for a callback-discovery attempt:

> Create a NEW Genie OAuth Compatibility Test connector alongside
> custom.genie-mobility, using https://oauth-compat-probe-production.up.railway.app/pilot/mcp. Discover its
> OAuth metadata and attempt oauth2_code with dynamic registration. Do not reuse
> the existing API key or change the old connector. Stop before granting consent.
> Report the observed callback URI, assigned client_id if any, token-endpoint auth
> method, requested scopes/resource, and whether the authorization request uses
> S256 PKCE. Do not reveal tokens, cookies, authorization codes, verifier or
> registration secrets. If setup is rejected, report the error without weakening
> security.

An initial callback rejection is expected. The operator verifies and pins the
actual callback, then repeats the same registration attempt. If the platform cannot
use the required method, resource or S256 challenge, stop and record that specific
incompatibility. Do not add a guessed callback or fall back to customer API keys.

After those checks, the user can consent to read-only guest access. Observe the
code exchange, the harmless probe call, reconnect, refresh rotation and revocation.
Successful backend records alone do not prove what Muse displayed or how it stored
credentials; keep client observations and server evidence distinct.

## Independent protocol probe

`scripts/dcr_probe.py` uses the actual fixture's metadata and approved test callback.
It rejects unsupported registration metadata, validates the generated client ID and
OAuth bindings, checks the single read-only tool and absent business routes, and
exercises dynamic-client refresh/revocation. It prints no credentials. A successful
generic protocol probe is not evidence of actual Muse support.

The independent probe passed against the local HTTPS compatibility app at
`https://localhost:8845`, using its supplied fixture and a process-local trusted CA.
It verified unknown callback rejection, unsupported metadata and omitted client
authentication rejection, generated client IDs, the registered read-only scope
limit, consent denial, S256 PKCE, code replay prevention, resource and exact redirect
binding, the single read-only tool, absent business/operator/payment routes, refresh
rotation with replay-triggered family revocation, and explicit revocation. The
approved callback was the fictional fixture URI `https://connector.example/callback`.
The complete probe passed again after the registration-policy authority fix, against
backend commit `d6d99c5460707065c1a76a44b38ccfb61c78bc21`
([backend draft PR](https://github.com/Genie-Mobility/genie-delivery/pull/2)).
This local result does not establish a successful Muse handshake.

Independent hosted readiness checks subsequently passed over normal certificate
validation at `https://oauth-compat-probe-production.up.railway.app`: both metadata
documents returned 200 with the expected issuer/resource, registration endpoint and
S256 support; unauthenticated MCP returned 401 with a resource-metadata challenge;
operator, delivery and payment routes returned 404. One registration named
`Synthetic independent readiness probe - not Muse`, with callback
`https://independent-readiness.invalid/callback`, returned 400
`invalid_redirect_uri` without a client ID. This deliberately synthetic observation
must not be attributed to Muse. The deployment started with an empty callback
allowlist; no consent, successful hosted registration or allowlist change was
performed by these checks. Actual Muse OAuth compatibility remains unverified.

```sh
SSL_CERT_FILE=/path/to/test-ca.pem python3 scripts/dcr_probe.py \
  --fixture /path/to/actual-oauth-compatibility-fixture.json
```

The fixture extends the pilot probe fields with
`"probe_tool": "get_oauth_probe_status"`. The registered test callback is fixture
data, not a guessed Muse callback. Staging starts with no unverified Muse callback
approved. DCR is a bounded bootstrap feature for this experiment, not an unrestricted
registration service for the delivery backend.

Primary references: [RFC 7591](https://www.rfc-editor.org/info/rfc7591/),
[MCP authorization security](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations),
and [Muse's documented custom-connector flow](https://www.meta.com/help/artificial-intelligence/1687253048996149/).
