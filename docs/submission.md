# Submission preparation

Status: draft; no submission or terms acceptance performed. Follow the current
[official submission flow](https://platform.muse.ai/submission) after sign-in.
Do not infer field names or automation APIs from this checklist.

Hosted sandbox now available at
`https://delivery-api-production-8749.up.railway.app/mcp`, tested with a generic MCP
client. Separate `owner-test` and `muse-reviewer` tenants are provisioned with
distinct credentials stored outside this repository. No credentials have been
submitted to Muse. Custom-domain DNS and actual Muse connectivity remain pending.

## Prepared product description

Genie delivery sandbox demonstrates quoting, reserving, confirming, providing pickup
details, checking delivery status, and cancellation through an agent interface.
It provides durable transaction state and duplicate-request protection. The current
version simulates execution and payment authorization; it does not buy food,
authorize real payments, dispatch vehicles, or promise real delivery coverage.

## Documented intake categories still needed

The following categories come from public guideline §§5.1–5.5. Exact authenticated
portal field names and any additional requirements remain unverified.

- Authorized submitter's Muse Connector Platform account and authenticated access.
- Organization legal/business verification details and evidence of authority.
- Authorized name, description, logo and other listing assets.
- Actual privacy-policy and product-terms URLs; do not substitute the website's
  unrelated policies without confirming they cover this service.
- Support contact, security contact and responsible maintenance developer.
- Supply the verified hosted endpoint and published API/MCP documentation to the
  authenticated intake, and maintain review-period availability.
- Securely supply the provisioned reviewer's API key, account instructions,
  permissions and restrictions through the platform's confirmed intake mechanism.
- Exact retention/deletion policy, access revocation process, encryption/access
  controls and processors, reconciled with the deployed implementation.
- Documented error cases, rate limits, all inputs/outputs, side effects and tool
  permission designations matching the frozen backend contract.
- Sandbox representative data, test account instructions, and transaction demo
  procedure without real charges.
- Authorized acceptance of applicable terms and any extra authenticated intake.

Provide secrets only through the portal's documented secure mechanism. Do not
commit reviewer credentials to this public-ready repository. Review and approval
remain separate from publication of source code and documentation.

## Integration checks and recommended evidence

These are project acceptance checks, not claims about mandatory portal fields:

- Verify the portal's accepted transport and authentication header setup. Configure
  OAuth only if required and actually implemented; no grant flow is assumed here.
- Observe a real Muse client session, including approval prompts and successful
  simulated completion. A redacted recording is useful evidence; the public docs
  do not establish a mandatory recording format.
- Confirm public DNS/TLS and operational readiness before advertising the target
  endpoint as live. Review production readiness separately from sandbox review.

The verified entry for authenticated intake is
`https://platform.muse.ai/login?return_to=/submission`. No authenticated direct-test
installation path has been observed. Directory approval and direct test
connectivity are distinct milestones; the latter's access path remains unknown.
