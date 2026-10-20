# Verified Muse constraints

Checked 2026-10-20 against [official connector guidelines](https://platform.muse.ai/docs)
and [the platform landing page](https://platform.muse.ai/).

| Topic | Evidence | Consequence |
| --- | --- | --- |
| Identity | Official platform and guideline pages identify Meta | This integration targets Meta Muse |
| Endpoint/authentication | Guidelines §5.4 requests API or MCP docs, endpoint, scopes and credentials such as OAuth clients or API keys | Supply our endpoint and sandbox authentication documentation |
| Transport | No public transport version or required bearer-header wiring found | Streamable HTTP and bearer auth are service choices pending Muse verification |
| Installation | Public flow is submit, review, then directory discovery (§§5–7) | Public docs do not describe GitHub installation; a separate user-reported local custom-client flow is recorded below |
| Submission access | Submit link redirects to `/login?return_to=/submission`, with work-email sign-in | Authenticated portal access needed to inspect further requirements |
| Testing | §5.5 requests a dedicated reviewer account and transaction testing without charges | Keep sandbox account usable for review |
| Permission metadata | §5.6 says portal tool annotation is coming soon | Include classifications and side effects in submitted documentation |
| Discovery | §7.1 describes approved connectors in the agent and Settings > Connectors | GitHub publication alone does not establish discoverability |

The authenticated portal may impose additional requirements. No portal submission
approval or directory listing has been verified. A user-reported local Muse session
read this repository and created a `custom.genie-mobility` client with the six tools
allowlisted and credentials reportedly stored securely. That session's simulated
booking/cancellation report is recorded in [validation evidence](validation.md).
It does not establish a general installation feature or independently verified
Muse UI, credential storage, or permission behavior.
Public documentation is not evidence of a supported OAuth grant, dynamic client
registration, PKCE requirement, token header format, streaming behavior, or a
machine-readable install manifest.

## Permission and transaction behavior

The guidelines distinguish reads, writes, and sensitive writes. Persisted quotes
and capacity holds must be documented as writes. Confirmation and pickup submission
are conservatively submitted as sensitive writes because they represent commitment
and execution triggers; Muse assigns the final classification during review.
Cancellation is also submitted as sensitive when it changes the committed service.

Before commitment, show the total, currency, scope, timing and cancellation terms.
Obtain approval for the exact action and request new approval if those details
change. A caller-supplied `user_confirmed` value is an assertion, not proof that Muse
presented its permission UI. Verify actual Muse approval behavior separately.

Keep quotes, holds, confirmed deliveries, failures and cancellations distinct.
Do not infer payment completion from a reservation or simulated authorization.
Do not retry uncertain writes with fresh keys. Preserve tenant separation and redact
credentials. These acceptance expectations follow guideline §§1, 3, 4.4 and 4.7.
