# Security model and operational boundaries

## Tenant boundary

Authentication binds a signed session to a user, organization, and server-side session record. Every route that reads or writes organization data filters by the organization from that validated session. The browser cannot choose a tenant identifier. Membership status and role are re-read by the API on each request.

## Authorization gate for scans

New assets begin in `PENDING`. A role with management privileges records a boolean confirmation and a written statement; an audit entry is added. The worker checks organization, active status, and `AUTHORIZED` again immediately before scanning. Revocation prevents new scans. The scan worker resolves DNS, rejects any address not globally routable, then connects to a vetted IP to reduce DNS-rebinding/SSRF risk. It makes a bounded TLS handshake and one HTTPS `HEAD`, disables redirect-following by not using a redirecting HTTP client, and does not probe ports or exploit services.

## Data sensitivity

Conversation context is queried from the active organization only. AI provider configuration is server-side; when no provider key exists, the API returns an explicit configuration error. Audit events are append-only through application APIs but are not cryptographically chained or protected from a database administrator.

## Gaps before production

The current process-local login rate limiter is not a distributed limiter; e-mail verification, password recovery, MFA, SSO, full admin plane, immutable/off-host audit storage, formal privacy retention controls, scheduled scans, operational alerting, PostgreSQL/Redis integration testing, TLS deployment, and independent security review remain to be implemented and verified. The application's security-score model is a transparent heuristic, not a recognized external rating.
