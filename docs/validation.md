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

## Not established by this run

Actual Muse installation, authentication compatibility, approval prompts, booking
within Muse, connector submission/approval/discoverability, public HTTPS deployment,
real service coverage, payments and dispatch are not validated. Concurrency,
expiry, readiness and durable-event checks require separate backend evidence.
The generic client result must not be presented as a Muse demo.

GitHub publication does not establish any of those properties. No website
repository, website deployment or website routing was modified.
