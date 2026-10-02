# Shared contracts

The Python API publishes its canonical OpenAPI contract at `/openapi.json` and `/docs`. Frontend TypeScript response types currently live in `apps/web/src/types.ts`; keep those aligned with the OpenAPI schemas. This folder is reserved for generated, versioned cross-language contracts when the MVP stabilizes; no duplicate hand-maintained API implementation belongs here.
