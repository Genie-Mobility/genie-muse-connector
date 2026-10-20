# Validation evidence

Date: 2026-10-20. Environment: isolated local PostgreSQL-backed Genie sandbox,
API at `http://127.0.0.1:8800/mcp`, independent Python stdlib client in this repo.
Dedicated tenant credentials were read from a protected local environment file and
were not printed or committed.

## Observed generic MCP run

Passed over actual HTTP:

- Missing and invalid bearer credentials denied.
- MCP initialization and discovery of all six tools.
- Quote, reservation and confirmation replay returned the same identifiers.
- Changed quote payload with a reused key rejected for idempotency conflict.
- False confirmation rejected, and confirmed delivery awaited pickup details.
- A second authenticated tenant could neither read nor cancel the first tenant's
  delivery; both were rejected as not found.
- Valid restaurant order reference/pickup details enabled simulated completion.
- A separate delivery cancelled successfully; replay remained cancelled.

Completed delivery: `5318b3e0-c0ca-4569-be50-e6e7281eea4c`.
Cancelled delivery: `477e4b61-c56f-47c6-85eb-92b8aa002295`.

After the backend owner restarted both API and worker using the same PostgreSQL
database, this independent client initialized a fresh MCP session and read both
IDs again. Their `completed` and `cancelled` states and simulation labels survived.
This verifies persisted terminal-state reads across restart. Worker interruption
mid-execution was tested separately by the backend owner, not by this client.

After the backend's final typed-response update at commit
`ec80173bbf18568584b5c049b00ed19c56523f8f`, a targeted check verified that live
`tools/list` exactly matched the published six-tool input/output schema snapshot.
The independent client also decoded both persisted statuses through the final
typed `structuredContent` interface. The full workflow was not redundantly rerun.

Six acceptance-client regression tests passed. They cover refusing redirects and
credential-bearing/plaintext remote URLs, rejecting malformed protocol envelopes
and error flags, and preventing internal failures or unrelated rejections from
counting as successful negative tests.

## Hosted HTTPS validation

Date: 2026-10-20. Endpoint:
`https://delivery-api-production-8749.up.railway.app/mcp`. Backend deployment commit:
`007a2425432f43bca86cc9b9179dd5d688fc0ea2` (runtime/contract unchanged from the
snapshot source; deployment instructions updated).

The same independent client passed all six check groups listed above over hosted
HTTPS. Its primary credential belonged to `owner-test`; the separately provisioned
`muse-reviewer` tenant could not read or cancel that owner's delivery. Hosted
`tools/list` exactly matched the published six-tool input/output schema snapshot.
Credentials were loaded from a protected local file and not logged or committed.

Completed hosted delivery: `56623efe-1c86-40b8-8896-20904235d682`.
Cancelled hosted delivery: `791327e7-1904-4dac-bd81-55b2ef958506`.

After the backend owner restarted both hosted API and worker, a fresh independent
MCP session read these same IDs with their correct `completed`/`cancelled` states
and simulation labels. No new deliveries were created for the restart check.

## Canonical-domain targeted validation

Endpoint: `https://delivery.geniemobility.ai/mcp`. Backend commit:
`88c9bf4ef760b64d7bdb4f9ba4be0e2b47e9cfed`; runtime and contracts unchanged, with
canonical hosting configuration and deployment documentation updated.

Independent checks passed normal TLS hostname/certificate verification, MCP
initialization, exact equality of the live and published six-tool schemas, and
reads of both previously completed/cancelled hosted deliveries. A request with
`Origin: https://delivery.geniemobility.ai` returned 200; an untrusted Origin
returned 403. No new delivery or repeated full workflow was necessary.

Google public DNS independently resolved the canonical hostname to `69.46.46.57`.
This machine still cached an earlier NXDOMAIN response, so the test used a
process-local resolver override restricted to this hostname and public DNS result.
It retained the canonical URL, SNI and certificate validation. System DNS was not
changed and TLS verification was never disabled. This establishes endpoint TLS and
MCP behavior; resolver caches elsewhere can take time to refresh.

## User-reported local Muse workflow

On 2026-10-20, the user reported that local Muse read this GitHub repository and
built a `custom.genie-mobility` client targeting the canonical MCP endpoint with a
six-tool allowlist. The user reported secure credential storage, with no key in
the client file or chat. We did not independently inspect that client or storage.

The reported workflow returned a USD 5.00 simulation quote with expiry and
idempotent replay, reserved and confirmed into `awaiting_pickup_details` with
`simulated_authorized` payment state, submitted pickup details and reached
`completed`. A separate delivery reached `cancelled`.

The backend owner independently corroborated both reported records with read-only,
authenticated REST GET requests against canonical HTTPS. Both returned 200 in the
`owner-test` tenant, with the respective `completed`/`cancelled` states and
`simulation: true`. TLS hostname verification remained enabled; a process-local
resolver override used an independently queried public DNS result because this
machine still cached NXDOMAIN. No writes or deployments were performed for this
corroboration. The user-session delivery IDs and personal details are omitted here.

Those backend reads establish persisted outcomes, not which client created them.
Muse execution provenance, client construction, secure storage and the displayed
workflow remain user-reported. The local session does not establish one-click
GitHub installation, platform-wide support, directory approval or real delivery.

## Not established by this evidence

General Muse installation/authentication support, independently observed Muse
permission prompts or secure storage, connector submission/approval/discoverability,
real service coverage, payments and dispatch are not validated. Concurrency,
expiry, readiness and durable-event checks require separate backend evidence.
The generic client result must not be presented as a Muse demo.

GitHub publication does not establish any of those properties. No website
repository, website deployment or website routing was modified.
