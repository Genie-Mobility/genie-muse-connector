# Genie delivery connector

Integration documentation and an independent MCP acceptance client for the Genie
delivery sandbox. The service lives in the separate `genie-delivery` repository.
The planned public endpoint is `https://delivery.geniemobility.ai/mcp`; this address
is a deployment target, not a claim that a service is deployed or approved.

**Sandbox only:** fictional deliveries, simulated payment authorization, no charges,
no food ordering, no vehicle or human dispatch. A confirmed sandbox delivery is not
a real delivery commitment. The fixed USD 5.00 quote is test data.

## Muse availability

The intended product is Meta's Muse Connector Platform. Its public documentation
describes connector submission and review, with discovery after approval. It accepts
API or MCP documentation and asks for authentication details, including OAuth client
credentials or API keys. It does not specify a GitHub installation mechanism,
supported MCP transport versions, or bearer-header configuration.

This repository is distribution of integration instructions, **not an installable
Muse plugin**. Actual Muse installation, authentication compatibility, approval
prompts, and end-to-end booking have not been verified. The submission portal
requires account sign-in. See [verified platform constraints](docs/muse-platform.md)
and [submission checklist](docs/submission.md).

## Integration contract

The proposed service interface is MCP Streamable HTTP with a dedicated sandbox API
key in `Authorization: Bearer …`. This is our service contract; Muse compatibility
must be confirmed in its authenticated portal. Never put keys in URLs, committed
files, screenshots, conversation prompts, or test output. Use environment variables
or the portal's secure credential intake.

The six tools are:

| Tool | Purpose | Side effects |
| --- | --- | --- |
| `get_delivery_quote` | Return sandbox terms and exact total | Persists an expiring quote |
| `reserve_delivery` | Hold the quoted delivery | Persists an expiring reservation |
| `confirm_delivery` | Confirm the reservation | Persists delivery and simulated authorization |
| `submit_pickup_details` | Provide pickup confirmation | Enables simulated execution after readiness time |
| `get_delivery_status` | Inspect delivery and events | Read only |
| `cancel_delivery` | Cancel an eligible delivery | Persists cancellation |

Every mutating tool requires `idempotency_key`; reuse the same key with identical
arguments after an ambiguous response. Query status before retrying an uncertain
confirmed action. Do not label a hold or quote as a confirmed delivery.

See the [exact contract](docs/contract.md) and
[demo acceptance procedure](docs/demo.md) for testing. A generic MCP client
test is evidence about the service, not evidence of a successful Muse interaction.

With Python 3.12+, provision a dedicated sandbox tenant key, then run:

```sh
read -rsp 'Sandbox token: ' GENIE_SANDBOX_TOKEN; echo
export GENIE_SANDBOX_TOKEN
python3 scripts/mcp_demo.py --endpoint http://127.0.0.1:8800/mcp
unset GENIE_SANDBOX_TOKEN
```

Set `GENIE_SECOND_TENANT_TOKEN` through a similarly secure environment input to
enable isolation checks. The runner creates fictional sandbox records and prints
only check results and delivery IDs. It refuses redirects and remote plaintext
HTTP. It has no automatic write retry after a transport failure. This is a bounded
JSON/finite-SSE acceptance client, not a general MCP SDK or Muse emulator. Response
sizes are capped. Socket timeouts limit inactivity; a slow stream can exceed the
nominal request timeout, so use a process-level timeout for unattended runs against
an untrusted endpoint.

## Sources

- [Muse connector guidelines](https://platform.muse.ai/docs)
- [Muse Connector Platform](https://platform.muse.ai/)
- [Authenticated submission entry](https://platform.muse.ai/submission)

No changes to the Genie website, its deployment, or its routing are needed by this
repository.
