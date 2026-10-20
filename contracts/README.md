# Contract snapshot provenance

Copied without modification from the private Genie delivery backend repository,
commit `ec80173bbf18568584b5c049b00ed19c56523f8f`, on 2026-10-20.
These public interface files contain no backend implementation or credentials.
The production hostname in OpenAPI is the intended target, not deployment evidence.

| File | SHA-256 |
| --- | --- |
| `openapi.json` | `e8afb9eb0a718b8b48690946ecd6b4bc64a2f083e4908e59a3d99b24b3a88421` |
| `mcp-tools.json` | `3a931739b663e551f653cb8898aaac7ac5256ebf96f4ec667c37214036657247` |
| `sandbox-fixture.json` | `94f93fcfe291a255eb379ae609e1f7badbbfe95aa92fd68e2d54e5c4a5fdbc19` |

The fixture uses fictional addresses and already-past UTC readiness timestamps for
immediate simulation. It is not a real restaurant order or delivery request.

Tool annotations describe service-side semantics. Muse assigns its own permission
classification during connector review; MCP annotations do not prove Muse approval.
