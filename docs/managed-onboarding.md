# Managed Descope authorization

This is the current integration direction, pending backend validation and reviewed
deployment. Customers use **one Genie connector** at
`https://delivery.geniemobility.ai/mcp`. Descope handles authentication, consent,
client registration and token issuance. Genie validates tokens and applies customer
isolation and tool permissions. The existing sandbox/client stays in place until
the managed replacement is verified. No successful Muse/Descope connection is
claimed yet.

## Customer flow

Connect Genie, complete the configured hosted email OTP step, approve the requested
permissions, and return to Muse. There is no customer API key or password to copy.
Email verification creates a provider identity and an internal customer record:
this is passwordless onboarding, not anonymous guest access. Authentication does
not authorize payment, operator actions or dispatch.

`delivery:read` is required. `delivery:write` is optional in consent and required
for mutations. Declining it must preserve read access. The current quote tool
persists a quote, so it is a mutation; requesting a quote must not silently bypass
write permission. Customer identity comes from a verified issuer and subject, never
an email supplied in chat, an OAuth client ID, or a caller-supplied tenant ID.

## Provider configuration and observed gap

On 2026-10-21, public discovery at the supplied project URL
`https://api.descope.com/v1/apps/P3KyuMNUTqygvFLXVwI34oyhtFTc/.well-known/openid-configuration`
returned 200 using JSON Accept and an explicit User-Agent. It advertised S256,
authorization-code and refresh grants, but only OIDC scopes (`openid`, `profile`,
`email`, `phone`, `offline_access`). It advertised secret-based token authentication
(`client_secret_basic`, `client_secret_post`), no registration endpoint and no CIMD
support flag. This does not establish automatic client-registration readiness or
public-client support. The initial default urllib request returned 403; changing request
headers succeeded without credentials or disabling TLS verification.

The user confirmed this exact URL from the dashboard's generated provider example.
Keep it: current maintained `DescopeProvider` source explicitly accepts and
recommends project-level discovery, although its narrative integration guide shows
a resource-specific path. Do not invent a different Resource ID or ask for the URL
again. Missing delivery scopes in project metadata do not prove they are absent in
the console; advertise the application's read/write scopes explicitly and enforce
them against verified tokens. Public discovery cannot verify email OTP or consent.

The maintained provider's default verifier uses the project ID as audience and
accepts several issuer forms. Genie requires explicit validation of the canonical
MCP resource audience and the reviewed issuer policy; do not blindly copy default
token-verification settings. A usable discovery URL and JWKS do not prove a token
has been issued with that audience or that Muse can register.

Registration readiness is a separate decision. The observed metadata does not
advertise automatic DCR or CIMD. This prevents discovery-driven registration but
does not rule out a preregistered confidential native OAuth client using the
advertised secret-based methods. Do not force such a client to become public.
If Muse uses automatic DCR, Descope's documented setting is the existing Genie
MCP Server's **Settings > MCP Client Registration > DCR**. Disabled DCR omits the
registration endpoint. No setting was changed during this inspection; enabling it
must be followed by rechecking the same confirmed metadata URL. Do not guess or
publish a registration endpoint when discovery does not supply one.

The console owner should verify:

- MCP Server URL/audience is exactly `https://delivery.geniemobility.ai/mcp`.
- Scopes are `delivery:read` (required) and `delivery:write` (allow user to decline),
  with clear consent descriptions.
- The selected registration template or Custom configuration uses the intended
  hosted user-authentication/consent flow, with email OTP and working email delivery.
- Registration and token authentication match Muse's actual native OAuth client.
  Use preregistration, CIMD or provider DCR as supported; do not assume `none`,
  invent a callback, or add a custom registration service.

Public discovery/JWKS validation needs no management key. Console configuration is
separate from token verification. The `fastmcp` package's `DescopeProvider` example
is not an import from the official `mcp` package; follow the backend's reviewed
adapter/dependency choice rather than mixing their APIs.

## One-connector migration and validation

After reviewed deployment, use the canonical URL in the existing Genie connector
if Muse supports changing authentication. If that registration is immutable,
replace it once as a developer migration; customers do not use both an API-key
connector and an OAuth compatibility connector. Preserve the current working client
until the replacement passes validation, then retire the superseded entry through
the agreed migration. No separate compatibility connector is needed.

For the real Muse check, connect Genie through its native OAuth setup. Verify that
the hosted flow returns to Muse and that status reads work. In a dedicated test
customer session, decline write scope and confirm a mutating call is denied without
creating records. Separately grant write scope, and exercise only explicitly
authorized simulated/test actions. Check a second test customer cannot access the
first customer's records. Reconnect and refresh should retain the same customer;
disconnect/revocation behavior must be measured, including any remaining JWT
lifetime, rather than promising immediate access-token invalidation.

Record client-observed behavior separately from server evidence. Never paste OTPs,
authorization codes, tokens, cookies, client secrets or payment data into chat or
test reports. No real payment or dispatch is part of authentication validation.

The earlier pilot and custom-DCR experiments remain historical work on separate
branches. They are not dependencies of this integration, and their guest-cookie,
custom authorization-server and callback-rejection procedures are not onboarding
instructions for the managed service.

## Independent validation evidence

On 2026-10-21, the real managed verifier initialized successfully against the
confirmed public Descope discovery URL and JWKS, with normal TLS verification.
This was read-only discovery; no authorization, registration or token issuance was
attempted. The signing-key document contained one public RSA/RS256 key.

The connector's `integration_tests/test_managed_transport_contract.py` passed all
12 cases against the backend's managed-auth worktree. Tests use synthetic RSA-signed
tokens, mock discovery/JWKS responses, the real verifier and SDK HTTP middleware
through Starlette TestClient, and a recording service. They verify metadata and
discovery challenges, all five mutation scope gates before service dispatch,
invalid claim rejection on REST and MCP, issuer/subject-based customer isolation,
identity continuity across email/client-ID changes, and legacy transition behavior.
This proves the HTTP authorization boundary, not persistent database isolation or
network/deployment behavior. One initial run failed because the independent fake
service used the wrong exception argument order; correcting the fixture resolved it.

The backend reviewer's 32 JWT security cases also passed in the independent run
(44 total). These include signature and algorithm rejection, required claims,
issuer/audience/expiry/scope validation, principal isolation, fixed discovery/key
origins and bounded unknown-key requests. Actual Descope-issued customer tokens,
email OTP, consent, refresh and Muse reconnection remain unverified.

The 12 HTTP cases passed again after the final lifecycle and token-parser
hardening changes. Final backend provenance is
`29add386503c43784ce60d243751124256c2f5d5`
([backend draft PR #3](https://github.com/Genie-Mobility/genie-delivery/pull/3)),
based on stable main. The backend owner separately reports 151 full regression
tests passing and no unresolved review blockers. Those broader results are
owner-reported, not a claim that this connector runner repeated them. No managed
deployment or real provider grant was performed as part of this evidence.

```sh
PYTHONPATH=/path/to/genie-delivery-descope /path/to/backend-venv/bin/python \
  -m pytest -q integration_tests/test_managed_transport_contract.py
```

## Sources

- [Descope MCP Server settings](https://docs.descope.com/agentic-identity-hub/core-components/mcp-servers/settings)
- [Maintained FastMCP Descope provider](https://github.com/PrefectHQ/fastmcp/blob/main/docs/v3/integrations/descope.mdx)
- [Descope MCP authorization](https://docs.descope.com/mcp)
- [Maintained DescopeProvider source](https://github.com/PrefectHQ/fastmcp/blob/main/fastmcp_slim/fastmcp/server/auth/providers/descope.py)
- [Project-level authorization-server discovery](https://docs.descope.com/identity-federation/inbound-apps/authorization-server)
- [Registration methods](https://docs.descope.com/agentic-identity-hub/core-components/mcp-servers/registration-methods)
