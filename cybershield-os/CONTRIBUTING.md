# Contributing

1. Keep all CyberShield work under this folder; do not replace or modify the sibling Hekayet Hala Store application.
2. Preserve tenant scoping on every new API query and add a cross-organization test for new organization-owned resources.
3. New scan functionality must be read-only, authorization-gated, bounded, and resistant to SSRF. No exploitation, credential collection, evasion, destructive action, or arbitrary Internet scan.
4. Put secrets only in environment variables; never commit `.env`, tokens, passwords, or customer data.
5. Run `pytest` in the project virtual environment and `cd apps/web && npm run build` before proposing changes.
6. Update OpenAPI-facing schemas and the README's known limitations when feature behavior changes.
